"""The ReAct prototype's three tools (agent/react.py), on the frozen snapshot eval-v1.

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

resolve_event(name) finds the official events an event name means, so the model never searches event names with
LIKE: in a live session it searched event_name for 'worlds' and answered that Marckiem00 never won Worlds, though he
won BCX 2025, whose event_name is empty (docs/experiments.md, 2026-10-23). A mode word (1v1, 2v2, singles, doubles)
narrows the events to that mode, and the rest of the name is matched in tiers, compared as event aliases are
(names.normalize_words):
- alias       a curated event alias (event_aliases): 'bcx 2022', 'worlds 2019', 'msi'.
- series      the aliases that are the name and a year, for two years or more: 'worlds' is every 'worlds YYYY'.
- words       events whose name has every word, a year matching the event's year, and a curated term standing for
              the words names use (event_terms: 'winters' for 'winter championship', 'na' for 'north america'). A
              plural also matches its singular, and an alias with every word adds its events ('world championship'
              finds DreamHack Atlanta 2018 through 'world championship 2018'). Qualifiers match only a name that
              asks for one, since the Last Chance Qualifiers aren't Worlds.
- some words  the events with the most of the words, if half or more.
Each tier has a score (EVENT_SCORES), times the share of the words matched for some words. The status:
- confident  an alias or series, or every word matching events of one tournament (its 1v1 and 2v2), or exactly a
             series' events ('world championships' finds what 'worlds' does);
- ambiguous  every word matching several tournaments ('ceo dreamland 2020': the cancelled event and the online one,
             the closer name first), or some words only;
- not_found  nothing matched.
The result has a sql condition on event_id for the events: their IDs when there are few, else a subquery, so the
model needn't copy 34 IDs for 'worlds': on v_event_series for a whole series (series = 'worlds'), else on the
aliases.

run_sql(query) runs one query read-only, stopped after a time limit. It returns every row if the result fits in about
4,000 tokens (TOKEN_BUDGET, an eighth of the context). A bigger result goes back with no rows, only its row count, its
columns and a note to reduce it in SQL and query again. React.py also sends back an answer that comes right after
one. Every result stays in the model's context until the answer, so one query must not fill it: every 1v1 set
Raydish played is 455 rows and about 28,000 tokens. Before 2026-10-19 the limit was 20 rows, with the first 20 shown,
and the model answered from them: question 6's 46 rows (395 tokens) held only 10 or 14 of Raydish's 20 events with
megD (docs/experiments.md). A result with no rows comes back with a diagnosis (diagnose.py): which condition emptied
it, and whether the value it filters on occurs in that column.

Every connection the tools query through (connect) also has the views of ingest/views.sql that the database lacks, as
temporary views: eval-v1 was frozen before v_sets_1v1 and v_event_series were written, and gets them this way, for
that connection only, with its file unchanged (add_views). Likewise resolve_event reads the event terms the database
lacks from curation/event_terms.csv (curated_terms): eval-v1 predates 'cb' for crew battle (2026-11-20).

Not built yet (decided 2026-10-19): when a user explicitly asks for a long list, the answer should summarize it, and
the full table should go to the user directly, without passing through the model.
"""

import bisect
import difflib
import functools
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
from names import normalize, normalize_full, normalize_words  # noqa: E402
import curation  # noqa: E402

SNAPSHOT = ROOT / "data" / "db" / "eval" / "eval-v1.sqlite"
EVENT_TERMS = ROOT / "curation" / "event_terms.csv"
VIEWS = ROOT / "ingest" / "views.sql"
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
# A name several players share exactly is clear-cut when the first has at least this many times the next one's official
# results, and resolves to that player alone. On the evaluation set's shared names (2026-11-09), the first was the
# player meant every time, 14.8 to 48 times ahead, so the 5 isn't tuned: no shared name there is closer.
CLEAR_CUT = 5
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
PLAYER_FILTER = re.compile(r"\b(?:player_id|partner_id|opponent_id|opponent1_id|opponent2_id|winner_id|loser_id)\s*"
                           r"(?:=\s*(-?\d+)|IN\s*\(([-\d,\s]+)\))", re.I)  # the views' player columns
# A player looked up by name: a column of players' names compared with a text value (=, LIKE, GLOB or IN, negated or
# not, in any case or collation, on either side, or in instr). players.name and v_career_earnings.name are the only
# bare name columns, so a bare name is a player's; alias counts only on player_aliases, since event_aliases has one too
NAME_COLUMNS = r"(?:name|winner_name|loser_name|entrant_name|shown_as|alias)\b"
NAME_COLUMN = rf"(?<![\w.])(?:[A-Za-z_]\w*\.)?{NAME_COLUMNS}"
FOLDED = rf"(?:(?:lower|upper|trim|ltrim|rtrim)\s*\(\s*{NAME_COLUMN}\s*\)|{NAME_COLUMN})(?:\s+collate\s+\w+)?"
TEXT = r"(?:(?:lower|upper|trim)\s*\(\s*)?'(?:[^']|'')*'"
NAME_FILTER = re.compile(rf"{FOLDED}\s*(?:==?|!=|<>|\b(?:not\s+)?(?:like|glob)\b|\b(?:not\s+)?in\s*\()\s*{TEXT}"
                         rf"(?:\s*,\s*{TEXT})*|{TEXT}\s*\)?\s*==?\s*{FOLDED}|\binstr\s*\(\s*{FOLDED}\s*,\s*{TEXT}", re.I)
CLAUSE_WORDS = r"(?!(?:join|where|on|using|left|right|inner|outer|cross|natural|group|order|limit|union|having)\b)"

EVENT_SCORES = {"alias": 1.0, "series": 0.95, "words": 0.9, "some words": 0.85}  # rankings too, as SCORES
MODE_WORDS = {"1v1": "1v1", "singles": "1v1", "2v2": "2v2", "doubles": "2v2"}
FILLER = {"the", "tournament", "event"}
QUALIFIER = {"qualifier", "qualifiers", "lcq"}
YEAR = re.compile(r"20\d\d")
EVENTS_LISTED = 10
IDS_IN_SQL = 12  # a set this small is given by its IDs; a bigger alias set by a subquery on event_aliases
IDS_AT_MOST = 40  # a bigger set of name matches gets no sql: too many IDs to copy into a query
ABOUT_ALIAS = " About this alias: "  # before an alias's own note, at the end of resolve_event's note


def display(name, former=None):
    """How an answer names a player: the current name, and after it the former name the match went through, without
    its team tag ('Zivai (formerly Godly)' for Kingdom | Godly). Only the team tag changed: the name alone."""
    if not former:
        return name
    old = former.split("|")[-1].strip()
    return name if normalize(old) == normalize(name or "") else f"{name} (formerly {old})"


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
        loose = max(found[pid][4] for pid in ranked) < CONFIDENT
        counts = [self.results.get(pid, (0,))[0] for pid in tied]
        if loose:
            status = "ambiguous"
        elif len(tied) == 1 or (TIERS[best] != "nickname" and len(placed) == 1):
            status = "confident"
        elif counts[0] > 0 and counts[0] >= CLEAR_CUT * counts[1]:
            status, ranked = "confident", ranked[:1]  # the player people mean, alone, so no other can be picked
        else:
            status = "ambiguous"
        candidates = [self.candidate(pid, *found[pid][1:], former=found[pid][0][1] == KINDS["former_name"])
                      for pid in ranked[:CANDIDATES]]
        if loose:
            note = ("No player has exactly this name; these are the closest. Use the first unless the question points to"
                    " another, and say which name you took it as.")
        elif status == "confident":
            note = f"Use player_id {ranked[0]}, and call them {candidates[0]['display']}."
        else:
            note = (f"{len(tied)} players match this name, ranked by official results. Use the first unless the question"
                    " points to another, and say in one short clause which player you took.")
        return {"name": name, "status": status, "note": note, "candidates": candidates}

    def candidate(self, pid, match, shown, note, score, former=False):
        results, first, last = self.results.get(pid, (0, None, None))
        out = {"player_id": pid, "name": self.names.get(pid), "display": display(self.names.get(pid), shown if former else None),
               "matched": shown, "match": MATCH[match], "score": score, "official_results": results}
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


def quoted(text):
    return "'" + text.replace("'", "''") + "'"


def curated_terms(path=EVENT_TERMS):
    """The event terms of curation/event_terms.csv, checked as the build checks them (ingest/curation.py), as (term,
    means). A snapshot frozen before a term was curated gets it this way, as add_views gives it a view: eval-v1
    predates 'cb' for crew battle (decided 2026-11-20). Raises CurationError listing the file's problems."""
    problems, cur = [], curation.Curation()
    curation.load_event_terms(curation.read(Path(path), "event_terms.csv", problems), cur, problems)
    if problems:
        raise curation.CurationError(problems)
    return [(t.term, t.means) for t in cur.event_terms]


class EventResolver:
    """Every official event, with the curated event aliases and terms, read once from the database, and the curated
    terms it lacks from the curation file (curated_terms; None: none): event names resolve in memory."""

    def __init__(self, db, curated=EVENT_TERMS):
        self.events = {}
        for event_id, tournament, event, start_date, year, counts_as, fmt, status, slug in db.execute(
                "SELECT event_id, tournament_name, event_name, start_date, year, counts_as, format, status,"
                " sgg_tournament_slug FROM v_events"):
            own = [w for w in normalize_words(tournament).split() if w not in MODE_WORDS and w != "brawlhalla"]
            self.events[event_id] = {
                "name": tournament + (f" / {event}" if event else ""), "start_date": start_date, "year": year,
                "counts_as": counts_as, "format": fmt, "status": status,
                "words": normalize_words(f"{tournament} {event or ''}").split(),
                "own": own,  # the tournament's own words, which a closer name covers more of
                "tournament": slug or " ".join(own)}  # a Challengermode tournament's 1v1 and 2v2 differ by name only
        self.aliases, notes = defaultdict(list), defaultdict(set)
        for alias, event_id, note in db.execute("SELECT alias, event_id, note FROM event_aliases"):
            if event_id in self.events:
                self.aliases[alias].append(event_id)
                notes[alias].add(note)
        # A note shared by all of an alias's events is about the alias ('msi' is a default someone may not mean). The
        # others describe one event each, which the event list shows anyway
        self.notes = {a: n.pop() for a, n in notes.items() if len(n) == 1 and len(self.aliases[a]) > 1 and None not in n}
        self.series = defaultdict(list)  # 'worlds' -> ['worlds 2017', ..., 'worlds 2025']
        for alias in sorted(self.aliases):
            stem, _, year = alias.rpartition(" ")
            if stem and YEAR.fullmatch(year):
                self.series[stem].append(alias)
        self.series = {stem: aliases for stem, aliases in self.series.items() if len(aliases) >= 2}
        self.terms = defaultdict(list)
        for term, means in [*db.execute("SELECT term, means FROM event_terms"), *(curated_terms(curated) if curated else [])]:
            if means not in self.terms[term]:
                self.terms[term].append(means)

    def resolve(self, name, listed=EVENTS_LISTED):
        """{name, status, note, matched, score, event_count, tournament_count, sql, events}: the events an event
        name means (the module docstring). events lists the first `listed` of them, best first (None: all)."""
        tokens = normalize_words(name).split()
        modes = {MODE_WORDS[t] for t in tokens if t in MODE_WORDS}
        mode = modes.pop() if len(modes) == 1 else None
        rest = [t for t in tokens if t not in MODE_WORDS]
        found, tier, matched, closeness, share = self.by_alias(" ".join(rest))
        if mode:
            found = {e for e in found if self.events[e]["counts_as"] == mode}
        if not found:
            found, tier, matched, closeness, share = self.by_words(rest, mode)
            # Words that find exactly a series' events mean that series: 'world championships' is 'worlds'
            matched = next((a for a in self.series.values() if found and self.of(a, mode) == found), [])
        out = {"name": name}
        if not found:
            stem = " ".join(t for t in rest if not YEAR.fullmatch(t))
            near = sorted(a for a in self.aliases if stem and (a == stem or a.startswith(stem + " ")))
            # The model spells a name out itself, rather than the data holding every abbreviation (decided 2026-11-19)
            note = ("No official event matches this name. People shorten event names and use slang: if it has an"
                    " abbreviation or a nickname, spell it out the way official event names write it (as 'bcx' is"
                    " Brawlhalla World Championship Expo) and look it up once more. If that finds nothing either, say"
                    " so. Don't search event names with LIKE.")
            if near:
                note += f" Aliases that start with '{stem}': {', '.join(near[:10])}."
            return {**out, "status": "not_found", "note": note, "events": []}
        tournaments = {self.events[e]["tournament"] for e in found}
        ranked = sorted(found, key=lambda e: (self.events[e]["start_date"] or "", e), reverse=True)  # newest first,
        ranked.sort(key=lambda e: -closeness.get(e, 1.0))  # then the closest names before the others
        sql = self.sql(ranked, tier, matched, mode)
        if tier in ("alias", "series") or (tier == "words" and (len(tournaments) == 1 or matched)):
            status, note = "confident", "These are the events the name means."
        elif tier == "words":
            status, note = "ambiguous", (f"These events come from {len(tournaments)} tournaments, the closest name"
                                         " first. If the question means one of them, filter on its event_ids and say"
                                         " which you took the name to mean; if it means all of them, use the sql.")
        else:
            status, note = "ambiguous", ("No event has all these words; these have the most. Check that they're the"
                                         " event the question means, and say which you took it to mean.")
        if sql:
            note += " Filter on them with the sql condition (write r.event_id, say, if the query joins tables)."
        else:
            note += (f" They're too many to filter by ID ({len(found)}): name the event more precisely, with a year, a"
                     " region or a mode.")
        notes = [self.notes[a] for a in matched if a in self.notes]
        if notes:
            note += ABOUT_ALIAS + " ".join(dict.fromkeys(notes))
        what = {"alias": f"alias '{matched[0]}'" if matched else "alias",
                "series": f"aliases '{matched[0]}' to '{matched[-1]}'" if matched else "aliases",
                "words": f"every word: the events of aliases '{matched[0]}' to '{matched[-1]}'" if matched else "every word",
                "some words": f"some of the words ({share:.0%})"}[tier]
        return {**out, "status": status, "note": note, "matched": what + (f", {mode} only" if mode else ""),
                "score": round(EVENT_SCORES[tier] * share, 2), "event_count": len(found),
                "tournament_count": len(tournaments), "sql": sql, "events": [self.listed(e) for e in ranked[:listed]]}

    def by_alias(self, text):
        """(events, tier, aliases, closeness, share) for an alias or a series of yearly aliases, or nothing."""
        if text in self.aliases:
            return set(self.aliases[text]), "alias", [text], {}, 1.0
        if text in self.series:
            return self.of(self.series[text]), "series", self.series[text], {}, 1.0
        return set(), None, [], {}, 1.0

    def of(self, aliases, mode=None):
        """The events of some aliases, in one mode if given."""
        return {e for a in aliases for e in self.aliases[a] if not mode or self.events[e]["counts_as"] == mode}

    def by_words(self, rest, mode):
        """(events, tier, aliases, closeness, share) for the events whose names have the words: closeness is each
        event's share of its tournament's own words that the name covers, and share the share of the words matched."""
        years = {int(t) for t in rest if YEAR.fullmatch(t)}
        words = [t for t in rest if not YEAR.fullmatch(t) and t not in FILLER]
        if not words:
            return set(), None, [], {}, 1.0
        qualifier = bool(QUALIFIER & set(words))
        aliased = {e for a, ids in self.aliases.items() if all(set(forms(w)) & set(a.split()) for w in words) for e in ids}
        hits, covers = {}, {}
        for event_id, e in self.events.items():
            if (years and e["year"] not in years) or (mode and e["counts_as"] != mode):
                continue
            if not qualifier and QUALIFIER & set(e["words"]):
                continue
            covered = {str(y) for y in years}
            found = 0
            for w in words:
                phrase = self.phrase(w, e["words"])
                if phrase:
                    found, covered = found + 1, covered | set(phrase.split())
            if event_id in aliased:
                found = len(words)
            if found:
                hits[event_id] = found
                covers[event_id] = len(covered & set(e["own"])) / max(len(e["own"]), 1)
        best = max(hits.values(), default=0)
        if not best or best / len(words) < 0.5:
            return set(), None, [], {}, 1.0
        events = {e for e, n in hits.items() if n == best}
        return events, "words" if best == len(words) else "some words", [], {e: covers[e] for e in events}, best / len(words)

    def phrase(self, word, words):
        """The words of an event's name that a word of the question stands for, found in order in the name: a curated
        term's meanings ('na': 'north america'), else the word or its singular; or None. A term's singular doesn't
        count: 'winters' are the seasonal championships, not the Winter Royale or DreamHack Winter."""
        for option in [word, *self.terms[word]] if word in self.terms else forms(word):
            seq = option.split()
            if any(words[i:i + len(seq)] == seq for i in range(len(words) - len(seq) + 1)):
                return option
        return None

    def sql(self, ranked, tier, aliases, mode):
        """A condition on event_id for the events: their IDs; for a bigger set, a subquery on v_event_series if the
        aliases are a whole series, else on the aliases; or None for too many name matches."""
        if len(ranked) <= IDS_IN_SQL or (not aliases and len(ranked) <= IDS_AT_MOST):
            ordered = sorted(ranked, key=lambda e: (self.events[e]["start_date"], e))
            return f"event_id IN ({', '.join(quoted(e) for e in ordered)})"
        series = next((stem for stem, yearly in self.series.items() if yearly == aliases), None)
        if series:  # short enough to copy whole: one run pasted 6 of the 10 IDs listed for the 34 Worlds events
            only = f" AND mode = '{mode}'" if mode else ""
            return f"event_id IN (SELECT event_id FROM v_event_series WHERE series = {quoted(series)}{only})"
        if aliases:
            names = ", ".join(quoted(a) for a in aliases)
            if mode:
                return (f"event_id IN (SELECT a.event_id FROM event_aliases a JOIN v_events v ON v.event_id = a.event_id"
                        f" WHERE a.alias IN ({names}) AND v.counts_as = '{mode}')")
            return f"event_id IN (SELECT event_id FROM event_aliases WHERE alias IN ({names}))"
        return None

    def listed(self, event_id):
        e = self.events[event_id]
        out = {"event_id": event_id, "name": e["name"], "start_date": e["start_date"], "counts_as": e["counts_as"]}
        if e["format"] != "standard":
            out["format"] = e["format"]
        if e["status"]:
            out["status"] = e["status"]
        return out


def forms(word):
    """A word of the question, and its singular if it may be a plural ('championships', 'dreamhacks')."""
    return [word, word[:-1]] if len(word) > 3 and word.endswith("s") else [word]


def cell(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, str) and len(value) > CELL_CHARS:
        return value[:CELL_CHARS] + f"... ({len(value)} characters)"
    return value


def player_ids(sql):
    """The player IDs a query filters on, written as numbers: player_id = 5, w.winner_id = 5, opponent_id IN (1, 2)."""
    found = []
    for one, many in PLAYER_FILTER.findall(sql):
        found += [int(one)] if one else [int(n) for n in many.split(",") if n.strip()]
    return found


def name_filters(sql):
    """The filters a query looks a player up by name with, as written: in the player check's smoke test, q01 filtered
    on players.name = 'Boomie', which seven players share, and answered for another of them (docs/experiments.md,
    2026-11-17)."""
    read = {t.lower() for t in re.findall(r"\b(player_aliases|event_aliases)\b", sql, re.I)}
    bound = {"player_aliases"} | {a.lower() for a in re.findall(rf"\bplayer_aliases\s+(?:as\s+)?{CLAUSE_WORDS}(\w+)", sql, re.I)}
    found = []
    for m in NAME_FILTER.finditer(sql):
        table, column = re.search(rf"(?<![\w.])(?:([A-Za-z_]\w*)\.)?({NAME_COLUMNS})",
                                  re.sub(r"'(?:[^']|'')*'", "''", m[0]), re.I).group(1, 2)
        if column.lower() == "alias" and not (
                table.lower() in bound if table else "player_aliases" in read and "event_aliases" not in read):
            continue
        found.append(" ".join(m[0].split()))
    return found


def tables(observation):
    """Every table an observation holds, as (columns, rows): a query's own result, or each table of a template's
    (agent/templates.py). A table too large to show has no rows."""
    if "tables" in observation:
        return [(t.get("columns", []), t.get("rows", [])) for t in observation["tables"]]
    if "columns" in observation:
        return [(observation["columns"], observation.get("rows", []))]
    return []


def tokens(text):
    """About how many tokens the model reads for a text. Qwen's tokenizer takes most digits and JSON punctuation as a
    token each, and other text at about four characters a token. Against the server's own counts for ten query
    results (2026-10-19), this was 9% under to 20% over."""
    marks = len(MARKS.findall(text))
    return round(marks + (len(text) - marks) / 4)


@functools.lru_cache(maxsize=None)
def view_definitions():
    """{name: its CREATE VIEW statement} for every view in ingest/views.sql, read once."""
    found, statement = {}, ""
    for line in VIEWS.read_text(encoding="utf-8").splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            name = re.search(r"^CREATE VIEW (\w+)", statement, re.M)
            if name:
                found[name.group(1)] = statement
            statement = ""
    return found


def add_views(db):
    """Create, as temporary views, the views of ingest/views.sql that the database has nothing named like: a snapshot
    frozen before a view was written gets it for this connection only. Returns their names."""
    have = {name for (name,) in db.execute("SELECT name FROM sqlite_master")}
    added = [name for name in view_definitions() if name not in have]
    for name in added:
        db.execute(re.sub(r"^CREATE VIEW", "CREATE TEMP VIEW", view_definitions()[name], count=1, flags=re.M))
    return added


def connect(path, seconds):
    """A read-only connection to the snapshot, with the views it lacks (add_views), on which no other database can
    be attached, and whose queries stop after `seconds`."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    add_views(db)
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
