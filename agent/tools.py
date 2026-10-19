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
prompt's rule. The status:
- confident  a curated nickname, or one exact or swap match, or several of which only one has official results;
- ambiguous  several exact or swap matches with results (a shared name, such as Boomie or Impala), or only prefix or
             fuzzy matches;
- not_found  nothing matched.

run_sql(query) runs one query read-only, stopped after a time limit, and returns at most 20 rows with the total.
"""

import bisect
import difflib
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
from names import normalize, normalize_full  # noqa: E402

SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
SQL_SECONDS = 30  # a head-to-head view filtered by a literal player ID takes 0.1-0.4 s; with the ID looked up inside
# the query it takes 18 s to over 90 s (docs/experiments.md), which this limit is meant to catch
SQL_ROWS = 20
COUNTED_ROWS = 1000  # rows counted for the total; a bigger result is "more than 1000"
CELL_CHARS = 300
CANDIDATES = 5

TIERS = ["nickname", "exact", "swap", "prefix", "fuzzy"]
MATCH = {"nickname": "curated nickname", "display_name": "display name", "without_tag": "display name without team tag",
         "former_name": "former name", "swap": "spelling variant (character swaps)",
         "prefix": "name starting with it", "fuzzy": "similar spelling"}
KINDS = {"nickname": 0, "display_name": 1, "without_tag": 2, "former_name": 3}  # strongest first, as build_aliases.py
SYMBOLS = str.maketrans({"$": "s", "@": "a"})
SWAPS = str.maketrans({"0": "o", "1": "i", "l": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b"})


def skeleton(name):
    """A name with common character swaps undone, for matching spellings: $ and @ as s and a, digits as the letters
    they stand for (0 o, 1 i, 3 e, 4 a, 5 s, 7 t, 8 b), l as i (lFiend, IFiend), and letters repeated in a row as
    one ('Marckiem00' -> 'marckiemo'; 'baloonboy' and 'BBBalloonBoy' -> 'balonboy'). Normalized as aliases are,
    without the team tag."""
    return re.sub(r"(.)\1+", r"\1", normalize((name or "").translate(SYMBOLS)).translate(SWAPS))


class Resolver:
    """Every alias, with each person's official results, read once from the database: names resolve in memory."""

    def __init__(self, db):
        self.names = dict(db.execute("SELECT player_id, name FROM players WHERE player_id = canonical_id"))
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
        """{name, status, note, candidates}: the players the name may mean, best first (the module docstring)."""
        found = {}  # canonical ID -> (tier, kind, shown_as, note, closeness)

        def add(alias, tier, closeness=0.0):
            for pid, kind, shown, note in self.aliases[alias]:
                key = (TIERS.index(tier if tier != "exact" or kind != "nickname" else "nickname"), KINDS[kind], -closeness)
                if pid not in found or key < found[pid][0]:
                    found[pid] = (key, tier if tier != "exact" else kind, shown, note)

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
        if TIERS[best] in ("prefix", "fuzzy"):
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

    def candidate(self, pid, match, shown, note):
        results, first, last = self.results.get(pid, (0, None, None))
        out = {"player_id": pid, "name": self.names.get(pid), "matched": shown, "match": MATCH[match],
               "official_results": results}
        if results:
            out["results_from"], out["results_to"] = first, last
        if match == "nickname" and note:
            out["note"] = note
        return out


def cell(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, str) and len(value) > CELL_CHARS:
        return value[:CELL_CHARS] + f"... ({len(value)} characters)"
    return value


def run_sql(query, path=SNAPSHOT, seconds=SQL_SECONDS):
    """One query on the snapshot, read-only (no other database can be attached) and stopped after `seconds`:
    {columns, rows (at most SQL_ROWS), row_count}, or {error}."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.execute("PRAGMA query_only = ON")
    db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK)
    deadline = time.monotonic() + seconds
    db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
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
    out = {"columns": columns, "rows": [[cell(v) for v in row] for row in rows[:SQL_ROWS]],
           "row_count": len(rows) if len(rows) <= COUNTED_ROWS else f"more than {COUNTED_ROWS}"}
    if len(rows) > SQL_ROWS:
        out["note"] = f"only the first {SQL_ROWS} rows are shown: aggregate, or order and limit, in SQL"
    return out
