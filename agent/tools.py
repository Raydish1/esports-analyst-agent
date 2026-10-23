"""The ReAct prototype's two tools (agent/react.py), on the frozen snapshot eval-v1.

resolve_player(name) finds the players a name may mean, through player_aliases, so the model never looks a name up
in SQL: in the model comparison, that was most of the misses (docs/experiments.md). The name is matched in tiers,
and the first tier that finds anyone is used:
- exact   an alias equal to the name normalized as aliases are (names.py: case, spaces, punctuation, accents and the
          team tag ignored), with or without its tag. A curated nickname ranks above every other alias.
- swap    the same after undoing common character swaps (skeleton): 'marckiem0o' finds Marckiem00, and 'baloonboy'
          finds BBBalloonBoy.
- prefix  a name that starts with it (3 characters or more).
- fuzzy   a similar spelling (difflib's ratio 0.8 or more, 4 characters or more): 'markiemoo' finds marckiemoo.
Within a tier, candidates are ranked by their official results (v_results), most first, like the model comparison
prompt's rule. Each has a score for how well it matches (SCORES): near 1 for an exact name, lower for a prefix or a
similar spelling. The status:
- confident  a curated nickname, or one exact or swap match, or several of which only one has official results;
- ambiguous  several exact or swap matches with results (a shared name, such as Boomie or Impala), or a best match
             scoring below CONFIDENT (prefix and fuzzy matches);
- not_found  nothing matched.
It takes names only. A name of digits only, or an ID written out ('71736', '#71736', 'player_id 71736'), gets an
error that says how to get a player_id's name with run_sql: in the prototype's first run, the model passed an ID as a
name, and the swaps and fuzzy matching made '71736' another player, tike36 (docs/experiments.md). On eval-v1, the 464
players whose only aliases are digits (25 official results at most) can't be found by name.

run_sql(query) runs one query read-only, stopped after a time limit. It returns every row if the result fits in about
4,000 tokens (TOKEN_BUDGET, an eighth of the context). A bigger result goes back with no rows, only its row count, its
columns and a note to reduce it in SQL and query again. React.py also sends back an answer that comes right after
one. Every result stays in the model's context until the answer, so one query must not fill it: every 1v1 set
Raydish played is 455 rows and about 28,000 tokens. Before 2026-10-19 the limit was 20 rows, with the first 20 shown,
and the model answered from them: question 6's 46 rows (395 tokens) held only 10 or 14 of Raydish's 20 events with
megD (docs/experiments.md). A result with no rows comes back with a diagnosis (diagnose.py): which condition emptied
it, and whether the value it filters on occurs in that column.

Not built yet (decided 2026-10-19): when a user explicitly asks for a long list, the answer should summarize it, and
the full table should go to the user directly, without passing through the model.
"""

import bisect
import difflib
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from diagnose import diagnose  # noqa: E402
from names import normalize, normalize_full  # noqa: E402

SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
SQL_SECONDS = 30  # a head-to-head view filtered by a literal player ID takes 0.1-0.4 s; with the ID looked up inside
# the query it takes 18 s to over 90 s (docs/experiments.md), which this limit is meant to catch
TOKEN_BUDGET = 4000  # a result estimated over this goes back without rows
COUNTED_ROWS = 10000  # rows counted for the total; a bigger result is "more than 10000"
CELL_CHARS = 300
CANDIDATES = 5

TIERS = ["nickname", "exact", "swap", "prefix", "fuzzy"]
# A candidate's score is its tier's base times its closeness within the tier: 1 in the exact tiers, the share of the
# alias the name covers for a prefix, difflib's ratio for a similar spelling. Scores rank matches; they aren't
# calibrated probabilities. They measure the match only: candidates are ordered by tier, then by official results, so
# among loose matches a more active player can come before a closer spelling ('rayd': Raydish, 98 results, before
# Raydex). CONFIDENT is the score a best match needs for the agent to use it without asking; below it, react.py shows
# the user the top three as suggestions. 0.9 puts character swaps above it, and prefixes and similar spellings below.
# Tune the scores and CONFIDENT on the evaluation set's misspelling questions (q21, q22).
SCORES = {"nickname": 1.0, "exact": 0.98, "swap": 0.92, "prefix": 0.85, "fuzzy": 0.85}
CONFIDENT = 0.9
MATCH = {"nickname": "curated nickname", "display_name": "display name", "without_tag": "display name without team tag",
         "former_name": "former name", "swap": "spelling variant (character swaps)",
         "prefix": "name starting with it", "fuzzy": "similar spelling"}
KINDS = {"nickname": 0, "display_name": 1, "without_tag": 2, "former_name": 3}  # strongest first, as build_aliases.py
CURRENT = {"nickname", "display_name", "without_tag"}  # the names an answer should call a player by
SYMBOLS = str.maketrans({"$": "s", "@": "a"})
SWAPS = str.maketrans({"0": "o", "1": "i", "l": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"})
ID_WRITTEN = re.compile(r"(?:player[\s_-]*)?id\s*[:#=]?\s*(-?\d+)", re.I)
TOO_BIG = ("Too large to show: {total} rows, over the budget of about {budget} tokens, so no rows are shown. Reduce the"
           " result in SQL to what the answer needs (GROUP BY with COUNT, SUM, MIN or MAX; WHERE; ORDER BY ... LIMIT) and"
           " query again.")
MARKS = re.compile(r'[\d\[\]{},:"]')


def skeleton(name):
    """A name with common character swaps undone, for matching spellings: $ and @ as s and a, digits as the letters
    they stand for (0 o, 1 i, 3 e, 4 a, 5 s, 7 t, 8 b), l as i (lFiend, IFiend), and letters repeated in a row as
    one ('Marckiem00' -> 'marckiemo'; 'baloonboy' and 'BBBalloonBoy' -> 'balonboy'). Normalized as aliases are,
    without the team tag."""
    return re.sub(r"(.)\1+", r"\1", normalize((name or "").translate(SYMBOLS)).translate(SWAPS))


def as_player_id(name):
    """The player_id a name is written as, or None: digits only ('71736', '#71736', '-42', '71 736') or an ID spelled
    out ('player_id 71736', 'ID: 5')."""
    text = name.strip()
    written = ID_WRITTEN.fullmatch(text)
    if written:
        return int(written.group(1))
    digits = normalize_full(text)
    if re.fullmatch(r"[0-9]+", digits):
        return -int(digits) if text.lstrip("#").lstrip().startswith("-") else int(digits)
    return None


class Resolver:
    """Every alias, with each person's official results, read once from the database: names resolve in memory."""

    def __init__(self, db):
        self.names = dict(db.execute("SELECT player_id, name FROM players WHERE player_id = canonical_id"))
        self.canonical = dict(db.execute("SELECT player_id, canonical_id FROM players"))
        self.results = {pid: (n, first, last) for pid, n, first, last in db.execute(
            "SELECT player_id, COUNT(*), MIN(start_date), MAX(start_date) FROM v_results GROUP BY player_id")}
        self.aliases = defaultdict(list)  # alias -> [(canonical ID, kind, shown_as, note)]
        self.skeletons = defaultdict(set)  # skeleton -> aliases
        for alias, kind, shown, note, pid in db.execute(
                "SELECT a.alias, a.kind, a.shown_as, a.note, p.canonical_id FROM player_aliases a"
                " JOIN players p USING (player_id)"):
            self.aliases[alias].append((pid, kind, shown, note))
            for form in {skeleton(alias), skeleton(shown)} - {""}:
                self.skeletons[form].add(alias)
        self.forms = sorted(self.skeletons)

    def resolve(self, name):
        """{name, status, note, candidates}: the players the name may mean, best first (the module docstring); or
        {name, error} for an ID."""
        number = as_player_id(name)
        if number is not None:
            return {"name": name, "error": f"{name!r} looks like a player_id, not a name, and resolve_player takes names"
                                          f" only. To get a player_id's name, use run_sql: SELECT player_id, name FROM"
                                          f" players WHERE player_id = {number}"}
        found = {}  # canonical ID -> ((tier, kind, -closeness), match, shown_as, note, score)

        def add(alias, tier, closeness=1.0):
            for pid, kind, shown, note in self.aliases[alias]:
                level = "nickname" if tier == "exact" and kind == "nickname" else tier
                key = (TIERS.index(level), KINDS[kind], -closeness)
                if pid not in found or key < found[pid][0]:
                    found[pid] = (key, tier if tier != "exact" else kind, shown, note, round(SCORES[level] * closeness, 2))

        for alias in {normalize(name), normalize_full(name)} - {""}:
            if alias in self.aliases:
                add(alias, "exact")
        form = skeleton(name)
        if not found:
            for alias in self.skeletons.get(form, ()):
                add(alias, "swap")
        if not found and len(form) >= 3:
            for other in self.forms[bisect.bisect_left(self.forms, form):]:
                if not other.startswith(form):
                    break
                for alias in self.skeletons[other]:
                    add(alias, "prefix", len(form) / len(other))
        if not found and len(form) >= 4:
            for other in difflib.get_close_matches(form, self.forms, n=10, cutoff=0.8):
                for alias in self.skeletons[other]:
                    add(alias, "fuzzy", difflib.SequenceMatcher(None, form, other).ratio())
        if not found:
            return {"name": name, "status": "not_found", "candidates": [],
                    "note": "No player in the data has this name or one close to it. Say so; don't guess an ID."}
        ranked = sorted(found, key=lambda pid: (found[pid][0][0], -self.results.get(pid, (0,))[0], found[pid][0][1:], pid))
        best = found[ranked[0]][0][0]
        tied = [pid for pid in ranked if found[pid][0][0] == best]
        placed = [pid for pid in tied if pid in self.results]
        if max(found[pid][4] for pid in ranked) < CONFIDENT:
            status, note = "ambiguous", ("No player has exactly this name; these are the closest. Use the first unless"
                                         " the question points to another, and say which name you took it as.")
        elif len(tied) == 1 or (TIERS[best] != "nickname" and len(placed) == 1):
            status, note = "confident", f"Use player_id {ranked[0]}."
            if len(ranked) > 1:
                note += " The other candidates share or resemble the name."
        else:
            status, note = "ambiguous", (f"{len(tied)} players match this name, ranked by official results. Use the"
                                         " first unless the question points to another, and say which player you took.")
        return {"name": name, "status": status, "note": note,
                "candidates": [self.candidate(pid, *found[pid][1:]) for pid in ranked[:CANDIDATES]]}

    def candidate(self, pid, match, shown, note, score):
        results, first, last = self.results.get(pid, (0, None, None))
        out = {"player_id": pid, "name": self.names.get(pid), "matched": shown, "match": MATCH[match], "score": score,
               "official_results": results}
        if results:
            out["results_from"], out["results_to"] = first, last
        if match == "nickname" and note:
            out["note"] = note
        return out

    def called(self, name):
        """The players this name is the current name of: a display name, with or without its team tag, or a curated
        nickname (not a former name), compared as aliases are."""
        return {pid for alias in {normalize(name), normalize_full(name)} - {""}
                for pid, kind, _, _ in self.aliases.get(alias, ()) if kind in CURRENT}


def cell(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, str) and len(value) > CELL_CHARS:
        return value[:CELL_CHARS] + f"... ({len(value)} characters)"
    return value


def tokens(text):
    """About how many tokens the model reads for a text. Qwen's tokenizer takes most digits and JSON punctuation as a
    token each, and other text at about four characters a token. Against the server's own counts for ten query
    results (2026-10-19), this was 9% under to 20% over."""
    marks = len(MARKS.findall(text))
    return round(marks + (len(text) - marks) / 4)


def connect(path, seconds):
    """A read-only connection to the snapshot, on which no other database can be attached, and whose queries stop
    after `seconds`."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only = ON")
    db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK)
    deadline = time.monotonic() + seconds
    db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    return db


def probe(sql, path, seconds):
    """A diagnosis probe's rows, or None if it failed or ran out of time."""
    db = connect(path, seconds)
    try:
        return db.execute(sql).fetchall()
    except (sqlite3.Error, sqlite3.Warning):
        return None
    finally:
        db.close()


def run_sql(query, path=SNAPSHOT, seconds=SQL_SECONDS):
    """One query on the snapshot, read-only and stopped after `seconds`: {complete: true, columns, rows, row_count} if
    the result fits in TOKEN_BUDGET, plus a diagnosis if it has no rows (diagnose.py); else {complete: false, note,
    row_count, columns}, with no rows; or {error}."""
    db = connect(path, seconds)
    try:
        cursor = db.execute(query)
        rows = cursor.fetchmany(COUNTED_ROWS + 1)
        columns = [d[0] for d in cursor.description or []]
    except (sqlite3.Error, sqlite3.Warning) as e:
        if "interrupted" in str(e):
            return {"error": f"stopped after {seconds} s. Filter the views by literal player IDs from resolve_player,"
                             " not by a lookup inside the query, and aggregate in SQL."}
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        db.close()
    if not rows and columns:
        return {"complete": True, "columns": columns, "rows": [], "row_count": 0,
                "diagnosis": diagnose(query, lambda sql, left: probe(sql, path, left))}
    total = len(rows) if len(rows) <= COUNTED_ROWS else f"more than {COUNTED_ROWS}"
    out = {"complete": True, "columns": columns, "rows": [], "row_count": total}
    size = tokens(json.dumps(out, ensure_ascii=False))
    for row in rows:
        values = [cell(v) for v in row]
        size += tokens(json.dumps(values, ensure_ascii=False)) + 1  # and the comma between rows
        if size > TOKEN_BUDGET:  # the note first, before anything else the model reads
            return {"complete": False, "note": TOO_BIG.format(total=total, budget=f"{TOKEN_BUDGET:,}"),
                    "row_count": total, "columns": columns}
        out["rows"].append(values)
    return out
