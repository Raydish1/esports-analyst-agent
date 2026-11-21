"""Template tools, offered to the model beside resolve_player, resolve_event and run_sql (agent/react.py): a tested
query for each of the most common kinds of question, so the model picks a tool and fills in two or three arguments
instead of writing SQL. In the 2026-11-08 evaluation, SQL the model wrote was the first failing stage in 5 of the
held-out set's 12 misses, and in 20 of 38 with retrieval off: one row kept of a team or of a tie, a head-to-head
query that timed out, a format filter holding a mode (docs/experiments.md).

TEMPLATES is the registry: each entry has the tool's name, what the model reads to choose it, its parameters, and the
function that runs it. react.py builds the tool list and dispatches from it, so a template is added here alone.

Every template returns one shape:
    template  its name
    scope     what was counted, for the answer to state
    event     for a template given an event's name: how the name matched, as resolve_event says it
    notes     what the answer must say: an event that wasn't held, a tie, crew battles among the results
    tables    each with what it holds, its columns, its rows and its row count
    ran       the SQL it executed, which react.py moves to the trace: the model doesn't read it
or {error}, for an argument it can't use, written for the model to act on.

The rules they share:
- Every row names players by name, next to their player_ids.
- Every tied row comes back: a cutoff never splits a tie.
- A team is one row with all its players.
- Counts are counted in SQL. A list (a table made optional) is left out, with its row count and a note, when the
  observation would pass tools.TOKEN_BUDGET, as run_sql leaves out a result that large.
- No count whose value the arguments fix is shown (player_results' COUNTS): read as the player's whole record, the
  2nd and 3rd places under top=1, all 0, made answers wrong (decided 2026-11-17).
- Players are given by player_id, from resolve_player, so a name the resolver isn't sure of still goes to the user
  as suggestions. Events are given by name and resolved here, as resolve_event resolves them.
"""

import calendar
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Callable

from tools import (ABOUT_ALIAS, EVENT_SCORES, IDS_IN_SQL, MODE_WORDS, REGIONS, SQL_SECONDS, TOKEN_BUDGET, cell, connect,
                   quoted, tokens)

EVENTS_AT_MOST = 60  # a name matching more events gets no results, only the closest few to choose from
CANDIDATES = 10
LINKS_AT_MOST = 4  # bracket links are listed for a tournament's events, not for a whole series
SCOPE = "official events"
SETS_SCOPE = "official events, 1v1 sets with one player a side; DQs, forfeits and ties left out"
LEFT_OUT = "{n} rows, too many to show with the rest: narrow the question (an event, a year, a mode, a lower top)."
DECIDED = re.compile(r"\s*\(decided \d{4}-\d{2}-\d{2}\)")  # a curated note's own bookkeeping, not for an answer
CUTS = {1: "wins (1st places)", 3: "medals (placed 3rd or better)", 8: "top 8s (placed 8th or better)"}
BY = {"wins": 1, "medals": 3, "top8s": 8}  # what rank_players counts, and the placement it counts up to
BY_WORDS = {"wins": {"wins", "win", "titles", "title"}, "medals": {"medals", "medal", "podiums", "podium"},
            "top8s": {"top8s", "top8", "top8finishes"}}  # as a model may write them, without spaces or punctuation
RANKED_AT_MOST = 30  # rows of a ranking listed; a tie group past them is counted instead
PLAYER_ARGUMENTS = ("player_id", "opponent_id", "partner_id")  # the arguments that take a player, which person() reads
# An event name that says only the mode, which a list of 1v1 sets leaves out (set_event): 'Brawlhalla Championship
# 1v1', 'Brawlhalla Singles (1v1)', '1v1'. 'World Championship 1v1' says more, and stays
GENERIC_EVENT = re.compile(r"(?:brawlhalla\s*)?(?:championship\s*)?(?:singles|1v1)?\s*(?:\(1v1\))?", re.I)
# player_results' counts after the player and the mode: each one's SQL over a result r, and the cutoffs (top) that fix
# its value, which leave it out. Under top=1, the 2nd and 3rd places were 0 and the top 8s the wins, and answers read
# them as the player's whole record (h03 and h16 in the held-out set's final measurement, docs/experiments.md)
COUNTS = [("results", "COUNT(*)", lambda top: False),
          ("first", "SUM(r.placement = 1)", lambda top: top == 1),
          ("second", "SUM(r.placement = 2)", lambda top: top is not None and top < 2),
          ("third", "SUM(r.placement = 3)", lambda top: top is not None and top < 3),
          ("medals", "SUM(r.placement <= 3)", lambda top: top is not None and top <= 3),
          ("top8", "SUM(r.placement <= 8)", lambda top: top is not None and top <= 8),
          ("best", "MIN(r.placement)", lambda top: top == 1)]
# What the results column counts under a top, as the summary names it: live, a 0 in a column named results read as
# "no 2v2 results" for a player with 25 (docs/web-app-testing-notes.md, finding 16). The web app's cards read the
# summary without a top, by these names: results, first, second, third, top8
COUNTED = {1: "wins", 3: "medals", 8: "top8s"}
BEST_LISTED = 10  # the results at a player's best placement, newest first: a champion's 1st places are their wins
# An event, mode or year argument that asks for no filter: live, event="all" matched Adaptation: Win-ter Takes All,
# and volst's top 8 vanished (finding 17)
NO_FILTER = {"", "all", "any", "every", "everything", "both", "overall", "total", "none", "*", "all events", "every event",
             "any event", "all modes", "both modes", "all years", "any year", "1v1 and 2v2", "1v1 & 2v2", "all time",
             "lifetime", "career"}
FILTERS = ("event", "mode", "year", "since", "until", "region")


class Refused(ValueError):
    """An argument a template can't use. The message is for the model."""


class Query:
    """One template call's connection to the snapshot. Each statement is kept as it was executed, for the trace."""

    def __init__(self, path, seconds=SQL_SECONDS):
        self.db, self.ran = connect(path, seconds), []

    def rows(self, sql):
        self.ran.append(" ".join(sql.split()))
        return self.db.execute(sql).fetchall()

    def close(self):
        self.db.close()


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    parameters: dict  # {argument: its JSON schema}
    required: tuple
    run: Callable  # (Query, tools, **arguments) -> observation; tools has the snapshot's path and the two resolvers

    def schema(self):
        """The tool as the model is offered it."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": {"type": "object", "required": list(self.required), "properties": self.parameters}}}

    def call(self, tools, arguments):
        """One call's observation: the result, or {error} for arguments it can't use or a query that failed."""
        takes = f"{self.name} takes {', '.join(self.parameters)}"
        unknown = sorted(set(arguments) - set(self.parameters))
        if unknown:
            return {"error": f"{self.name} has no argument {unknown[0]!r}: {takes}"}
        given = {k: v for k, v in arguments.items() if v is not None and not (
            isinstance(v, str) and (not v.strip() or k in FILTERS and v.strip().casefold() in NO_FILTER))}
        missing = [k for k in self.required if k not in given]
        if missing:
            return {"error": f"{self.name} needs {missing[0]}: {takes}"}
        query = Query(tools.path)
        try:
            return self.run(query, tools, **given)
        except Refused as e:
            return {"error": str(e)}
        except (sqlite3.Error, sqlite3.Warning) as e:
            if "interrupted" in str(e):
                return {"error": f"{self.name} was stopped after {SQL_SECONDS} s. Narrow it: an event, a year or a mode."}
            return {"error": f"{self.name} failed: {type(e).__name__}: {e}"}
        finally:
            query.close()


# What the templates share

def whole(value, name, least=1):
    """An argument as a whole number of at least `least` (None: any): 5, 5.0 or '5', since a model writes numbers as
    text too."""
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        value = int(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or (least is not None and value < least):
        raise Refused(f"{name} is a whole number{'' if least is None else f', {least} or more'}, not {value!r}")
    return value


def person(tools, value, name="player_id"):
    """A player argument as (the person's player_id, their name, the ID given): the number resolve_player returned. A
    name is refused: every name goes through resolve_player, whose doubts go to the user. A merged record's ID is
    the person's."""
    if isinstance(value, str) and not re.fullmatch(r"\s*-?\d+\s*", value):
        raise Refused(f"{name} is the number resolve_player returns, not a name: call resolve_player with {value!r}"
                      " first, and pass the player_id it gives")
    given = whole(value, name, least=None)
    if given not in tools.resolver.canonical:
        raise Refused(f"no player has player_id {given}: pass the player_id resolve_player returns")
    canonical = tools.resolver.canonical[given]
    return canonical, tools.resolver.names.get(canonical), given


def merged(given, player, name):
    """The note for a player given by another of their records' IDs (person), or None."""
    if given == player:
        return None
    return f"player_id {given} is another record of {name} (player_id {player}): these are the person's."


def one_mode(value):
    """A mode argument as '1v1' or '2v2' ('singles' and 'doubles' too). A format isn't a mode."""
    mode = MODE_WORDS.get(value.strip().lower()) if isinstance(value, str) else None
    if mode is None:
        raise Refused(f"mode is '1v1' or '2v2', not {value!r}")
    return mode


def ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def joined(items):
    """'a', 'a and b', 'a, b and c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def cut(top):
    """What a placement cutoff keeps, as a table says it."""
    return "results" if top is None else CUTS.get(top, f"results placed {ordinal(top)} or better")


def counted_as(top):
    """The name of the summary's results column: results, or under a top what it counts (COUNTED)."""
    return "results" if top is None else COUNTED.get(top, f"top{top}s")


def narrowed(top, mode, narrow):
    """What a narrowed player_results counts, as its note says it: 'the wins (1st places) in 2v2'."""
    return " ".join([f"the {cut(top)}" if top else "the results"] + ([f"in {mode}"] if mode else []) + narrow.said)


def table(what, columns, rows, optional=False):
    """One table of a result. optional: a list the result does without when it is over the token budget."""
    out = {"what": what, "columns": columns, "rows": [[cell(v) for v in row] for row in rows], "row_count": len(rows)}
    return {**out, "optional": True} if optional else out


def observation(name, scope, notes, tables, ran, **about):
    """A template's result (the module docstring), with what it is about (event, player) after its name. Tables
    without rows to show are left out. Over TOKEN_BUDGET, the optional tables lose their rows, the largest first, and
    keep their row count with a note."""
    tables = [t for t in tables if t is not None]
    out = {"template": name, **{k: v for k, v in about.items() if v}, "scope": scope, "notes": notes, "tables": tables}
    lists = sorted((t for t in tables if t.pop("optional", False)), key=lambda t: -len(json.dumps(t["rows"])))
    for t in lists:
        if tokens(json.dumps(out, ensure_ascii=False)) <= TOKEN_BUDGET:
            break
        t.update(complete=False, note=LEFT_OUT.format(n=t["row_count"]))
        del t["rows"]
    return {**out, "ran": ran}


@dataclass
class Matched:
    """The events an event name means, for a template: as resolve_event lists them, best first."""
    asked: str
    status: str
    how: str
    events: list
    notes: list  # what an answer must say about the match
    usable: bool  # whether the template can answer for these events

    @property
    def about(self):
        return {"name": self.asked, "status": self.status, **({"matched": self.how} if self.how else {})}


def match_events(tools, name, several=False):
    """The events a name means (tools.EventResolver, as resolve_event). A template answers only for a confident match.
    With several, it also answers for a name whose every word matches several tournaments, each of which it labels;
    a result that merges tournaments (a ranking, a player's results) can't."""
    if not isinstance(name, str) or not name.strip():
        raise Refused("event is the event's name as the question writes it, such as 'winters 2023 na 1v1'")
    found = tools.events.resolve(name, listed=None)
    events, notes, usable = found["events"], [], found["status"] == "confident"
    if found["status"] == "not_found":
        notes.append(found["note"])
    elif found["score"] < EVENT_SCORES["words"]:
        notes.append(f"No event has all the words of {name!r}: these have the most. If one of them is the event meant,"
                     " call again with its name as listed here.")
    elif len(events) > EVENTS_AT_MOST:
        usable = False
        notes.append(f"{name!r} matches {len(events)} events, too many to answer for. Name it more precisely, with a"
                     " year, a region or a mode. These are the closest.")
    elif found["status"] == "ambiguous":
        usable = several
        then = ("Say which one you took the name to mean: the others are different tournaments." if several
                else "Call again with one tournament's name, as listed here.")
        notes.append(f"{name!r} matches {found['tournament_count']} tournaments, the closest name first. {then}")
    about = found["note"].partition(ABOUT_ALIAS)[2]
    if about:
        notes.append(about)
    return Matched(name, found["status"], found.get("matched", ""), events, notes, usable)


def mode_label(event):
    """What an event counts as, as a row says it: '1v1', '2v2', '1v1 (crew battle)', or the format that counts as
    neither."""
    fmt = (event.get("format") or "").replace("_", " ")
    if event["counts_as"] is None:
        return f"{fmt or 'not counted'} (neither 1v1 nor 2v2)"
    return f"{event['counts_as']} (crew battle)" if fmt == "crew battle" else event["counts_as"]


def label(event):
    return f"{event['name']} ({event['start_date']})"


def unanswered(name, found, query):
    """A template's result for an event name it can't answer for: why, and the closest events to choose from."""
    closest = [[e["name"], e["start_date"], mode_label(e), e.get("status")] for e in found.events[:CANDIDATES]]
    listed = table("the closest events", ["event", "date", "mode", "status"], closest) if closest else None
    return observation(name, SCOPE, found.notes, [listed], query.ran, event=found.about)


def in_ids(events):
    return ", ".join(quoted(e["event_id"]) for e in events)


def status_note(event, reason):
    """What an answer must say about an event that wasn't held or whose placements are unreliable, with the data's
    own note on it; None for any other event."""
    reason = DECIDED.sub("", reason or "").strip().rstrip(".")
    about = f" The data's note on it: {reason}." if reason else ""
    if event.get("status") == "cancelled":
        return (f"{label(event)} was not held, so it has no results: say it wasn't held, not that its results are"
                f" missing.{about}")
    if event.get("status") == "placements_unreliable":
        return (f"{label(event)} has unreliable placements, so they aren't results and it has no reliable winner: say"
                f" so, and why.{about}")
    return f"{label(event)} is marked {event['status']}.{about}" if event.get("status") else None


def status_notes(query, events):
    """status_note for each event with a status, for a template that doesn't read the events themselves."""
    marked = [e for e in events if e.get("status")]
    if not marked:
        return []
    reasons = dict(query.rows(f"SELECT event_id, note FROM v_events WHERE event_id IN ({in_ids(marked)})"))
    return [note for note in (status_note(e, reasons.get(e["event_id"])) for e in marked) if note]


def day(value, name, last=False):
    """A since or until argument as an ISO date: '2025-10-01', '2025-10' or '2025' (or 2025), a month or a year
    starting on its first day for since and ending on its last for until."""
    text = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    m = re.fullmatch(r"(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?", text)
    try:
        year, month, d = int(m[1]), int(m[2] or (12 if last else 1)), m[3] and int(m[3])
        return date(year, month, d or (calendar.monthrange(year, month)[1] if last else 1)).isoformat()
    except (TypeError, ValueError):
        raise Refused(f"{name} is a date, as 2025-10-01, 2025-10 or 2025, not {value!r}") from None


@dataclass
class Narrowing:
    """What a call narrows the results to besides its players and mode: a calendar year, a time window (since and
    until, each day included), a region (its code and event_ids), and the events an event name means, as the
    conditions on a result (where) and the words its scope says them in (said)."""
    year: int | None = None
    since: str | None = None
    until: str | None = None
    found: "Matched | None" = None
    region: tuple | None = None

    def where(self, alias="r"):
        out = [f"substr({alias}.start_date, 1, 4) = '{self.year}'"] if self.year else []
        out += [f"{alias}.start_date >= '{self.since}'"] if self.since else []
        out += [f"{alias}.start_date <= '{self.until}'"] if self.until else []
        out += [f"{alias}.event_id IN ({', '.join(quoted(e) for e in sorted(self.region[1])) or 'NULL'})"] if self.region else []
        return out + ([f"{alias}.event_id IN ({in_ids(self.found.events)})"] if self.found else [])

    @property
    def said(self):
        window = (f"from {self.since} to {self.until}" if self.since and self.until else
                  f"since {self.since}" if self.since else f"until {self.until}" if self.until else None)
        n = len(self.found.events) if self.found else 0
        return ([f"in {self.year}"] if self.year else []) + ([window] if window else []) + (
            [f"at {REGIONS[self.region[0]]}'s events"] if self.region else []) + (
            [f"at the event the name means" if n == 1 else f"at the {n} events the name means"] if self.found else [])

    @property
    def notes(self):
        """What an answer must say about the narrowing: a region counts only the events whose names name it."""
        return [f"region counts the {len(self.region[1])} events whose names name {REGIONS[self.region[0]]}: global"
                " events, such as Worlds and the BCX finals, are in no region. Say so."] if self.region else []

    def __bool__(self):
        return bool(self.year or self.since or self.until or self.found or self.region)


def narrowing(tools, year=None, since=None, until=None, event=None, region=None):
    """A call's Narrowing from its arguments, each checked as the model wrote it."""
    year = None if year is None else whole(year, "year")
    since = None if since is None else day(since, "since")
    until = None if until is None else day(until, "until", last=True)
    if since and until and since > until:
        raise Refused(f"since ({since}) is after until ({until}): the window would be empty")
    place = None if region is None else tools.events.region(region)
    if region is not None and place is None:
        raise Refused(f"region is one of {', '.join(REGIONS)}, or a name for one ('north america', 'oce'), not"
                      f" {region!r}")
    return Narrowing(year, since, until, None if event is None else match_events(tools, event), place)


def conditions(mode=None, narrow=None):
    """The conditions on a result r that a mode and a Narrowing make, and the scope they leave."""
    narrow = narrow or Narrowing()
    where = ([f"r.mode = '{mode}'"] if mode else []) + narrow.where("r")
    return where, f"{SCOPE}, {', '.join([mode or '1v1 and 2v2'] + narrow.said)}"


# event_results

def placed(event, rows):
    """An event's (placement, team_id, player_id, name) rows as (placement, names, player_ids): a 2v2 team on one
    row, a crew on one row (a crew battle has no team rows: the players on a placement are the crew), and otherwise
    a player a row."""
    groups = {}
    for placement, team, player, name in rows:
        if event.get("format") == "crew_battle":
            key = (placement,)
        else:
            key = (placement, "team", team) if team is not None else (placement, "player", player)
        groups.setdefault(key, []).append((name, player))
    return [(key[0], " / ".join(n for n, _ in members), [p for _, p in members]) for key, members in groups.items()]


def event_results(query, tools, event, top=1):
    top = whole(top, "top")
    found = match_events(tools, event, several=True)
    if not found.usable:
        return unanswered("event_results", found, query)
    events = found.events  # the closest tournament first for a name that matches several; else in time
    if found.status == "confident":
        events = sorted(events, key=lambda e: (e["start_date"] or "", e["counts_as"] or ""))
    info = {e: rest for e, *rest in query.rows(
        f"SELECT event_id, note, bracket_url, competition_key FROM v_events WHERE event_id IN ({in_ids(events)})")}
    rows = {}
    for e, *row in query.rows(
            "SELECT r.event_id, r.placement, r.team_id, r.player_id, p.name FROM v_results r"
            f" JOIN players p ON p.player_id = r.player_id WHERE r.event_id IN ({in_ids(events)})"
            f" AND r.placement <= {top} ORDER BY r.placement, p.name"):
        rows.setdefault(e, []).append(row)
    phases = {}
    for e in events:
        phases.setdefault(info[e["event_id"]][2], []).append(e)
    notes, placements, tied = list(found.notes), [], False
    for competition in phases.values():
        if len(competition) > 1:
            notes.append(f"{' and '.join(label(e) for e in competition)} are phases of one competition: each player's"
                         " result counts once, at the last phase they reached.")
    for e in events:
        sides = placed(e, rows.get(e["event_id"], []))
        if e.get("status"):
            notes.append(status_note(e, info[e["event_id"]][0]))
        elif e["counts_as"] is None:
            notes.append(f"{label(e)} counts as neither 1v1 nor 2v2, so its placements aren't results here. v_entries"
                         " has them.")
        elif not sides and len(phases[info[e["event_id"]][2]]) == 1:
            notes.append(f"{label(e)} has no placements in the data.")
        tied |= e.get("format") != "crew_battle" and len({s[0] for s in sides}) < len(sides)
        placements += [[e["name"], e["start_date"], mode_label(e), *side] for side in sides]
    if any(e.get("format") == "crew_battle" and e["event_id"] in rows for e in events):
        notes.append("A crew battle's placement is the crew's: a team result, which counts as 1v1.")
    if tied:
        notes.append("Rows on the same placement in one event are tied there: give them the same place.")
    links = len(events) <= LINKS_AT_MOST
    ids = len(events) <= IDS_IN_SQL  # an event_id for any SQL that follows, as resolve_event gives IDs for so few
    if not ids:
        notes.append(f"For SQL on these {len(events)} events, use resolve_event's sql condition for {event!r}: their"
                     " IDs are too many to list.")
    listed = [[e["name"], *([e["event_id"]] if ids else []), e["start_date"], mode_label(e), e.get("status")]
              + ([info[e["event_id"]][1]] if links else []) for e in events]
    what = "each event's winners" if top == 1 else f"each event's top {top}: everyone placed {top} or better"
    return observation("event_results", SCOPE, notes, [
        table("the events the name means", ["event", *(["event_id"] if ids else []), "date", "mode", "status"]
              + (["bracket_url"] if links else []), listed),
        table(f"{what}, a team's players together", ["event", "date", "mode", "placement", "players", "player_ids"],
              placements, optional=True)], query.ran, event=found.about)


# player_results

def event_name(tournament, event):
    return f"{tournament} / {event}" if event else tournament


def set_event(tournament, event):
    """A set's event as a list of sets names it: the tournament, with its event's name only when that says more than
    the mode ('Brawlhalla World Championship Expo 2022', not '... / 1v1'; 'DreamHack Atlanta 2019 / Brawlhalla World
    Championship 1v1'). Live, an answer named each set by its date alone (docs/web-app-testing-notes.md, finding 2)."""
    return tournament if not event or GENERIC_EVENT.fullmatch(event.strip()) else event_name(tournament, event)


def first_and_latest(rows, when):
    """(which, row) for the rows first and latest in time, of rows in time order (`when` gives a row's time). Every
    row sharing the first time is first, and likewise the latest. Rows that all share one time are each 'only'."""
    if not rows:
        return []
    first = [r for r in rows if when(r) == when(rows[0])]
    latest = [r for r in rows if when(r) == when(rows[-1])]
    if when(rows[0]) == when(rows[-1]):
        return [("only", r) for r in first]
    return [("first", r) for r in first] + [("latest", r) for r in latest]


def both(column, values):
    """A summary column over both modes: the better of their best placements, or the sum of a count."""
    if column == "best":
        return min((v for v in values if v is not None), default=None)
    return sum(values)


def player_results(query, tools, player_id, top=None, mode=None, year=None, event=None, since=None, until=None,
                   region=None):
    player, name, given = person(tools, player_id)
    top = None if top is None else whole(top, "top")
    mode = None if mode is None else one_mode(mode)
    narrow = narrowing(tools, year, since, until, event, region)
    found = narrow.found
    if found and not found.usable:
        return unanswered("player_results", found, query)
    where, scope = conditions(mode, narrow)
    where = " AND ".join([f"r.player_id = {player}"] + ([f"r.placement <= {top}"] if top else []) + where)
    shown = [(column, sql) for column, sql, fixed in COUNTS if not fixed(top)]
    counted = {m: figures for m, *figures in query.rows(  # the shown counts, then the crew battles
        f"SELECT r.mode, {', '.join(sql for _, sql in shown)}, SUM(r.format = 'crew_battle')"
        f" FROM v_results r WHERE {where} GROUP BY r.mode")}
    listed = query.rows(
        "SELECT r.start_date, r.tournament_name, r.event_name, r.mode, r.format, r.placement, r.start_time"
        f" FROM v_results r WHERE {where} ORDER BY r.start_time, r.mode")
    every = dict(query.rows(f"SELECT r.mode, COUNT(*) FROM v_results r WHERE r.player_id = {player} GROUP BY r.mode"))
    notes = (found.notes + status_notes(query, found.events) if found else []) + narrow.notes
    if given != player:
        notes.append(merged(given, player, name))
    modes = [mode] if mode else ["1v1", "2v2"]  # a mode has its row even with nothing in it: a 0 to read, not a gap
    nothing = [None if column == "best" else 0 for column, _ in shown]
    summary = [[name, m, *(counted[m][:-1] if m in counted else nothing)] for m in modes]
    if not mode:
        summary.append([name, "1v1 and 2v2", *(both(column, [row[2 + i] for row in summary])
                                               for i, (column, _) in enumerate(shown))])
    split = ", ".join(f"{n} in {m}" for m, n in sorted(every.items()))
    if not listed:
        notes.append(f"{name} has no official 1v1 or 2v2 results in the data." if not every else
                     f"None of {name}'s {sum(every.values())} official results ({split}) is among these: the count is 0,"
                     " which isn't the same as never having played.")
    elif top or mode or narrow:  # what the counts leave out, so a 0 isn't read as never having played
        total = sum(every.values())
        notes.append(f"{name} has {total} official result{'' if total == 1 else 's'} in all ({split}): the counts here"
                     f" are only {narrowed(top, mode, narrow)}.")
    crews = sum(figures[-1] or 0 for figures in counted.values())
    if crews:
        notes.append(f"{crews} of the 1v1 {cut(top)} {'is a crew battle: a team result' if crews == 1 else 'are crew battles: team results'},"
                     " counted as 1v1.")
    ends = [[which, m, r[0], event_name(r[1], r[2]), r[5]] for m in modes
            for which, r in first_and_latest([r for r in listed if r[3] == m], lambda r: r[6])]
    each = [[r[0], event_name(r[1], r[2]), f"{r[3]} (crew battle)" if r[4] == "crew_battle" else r[3], r[5]] for r in listed]
    tally, bests = [], []  # the whole record's: how often each placement happened, and where the best was
    if top is None and listed:
        tally = [[m, p, n] for (m, p), n in sorted(Counter((r[3], r[5]) for r in listed).items())]
        for m in modes:
            placed = [r for r in listed if r[3] == m]
            best = min((r[5] for r in placed), default=None)
            at = [r for r in reversed(placed) if r[5] == best]
            bests += [[m, best, r[0], event_name(r[1], r[2])] for r in at[:BEST_LISTED]]
            if len(at) > BEST_LISTED:
                notes.append(f"{name} placed {ordinal(best)} {len(at)} times in {m}: the latest {BEST_LISTED} are listed"
                             " at the best placement.")
    return observation("player_results", scope, notes, [
        table(f"{name}'s {cut(top)}, counted by mode",
              ["player", "mode", *(counted_as(top) if column == "results" else column for column, _ in shown)], summary),
        table("the first and the latest of them in each mode", ["which", "mode", "date", "event", "placement"], ends)
        if ends else None,
        table("how many times each placement happened, by mode: counted, so don't count the list's rows",
              ["mode", "placement", "times"], tally) if tally else None,
        table("the results at the best placement in each mode, newest first, ties included",
              ["mode", "placement", "date", "event"], bests) if bests else None,
        table("each of them, oldest first", ["date", "event", "mode", "placement"], each, optional=True)
        if each else None], query.ran, player={"player_id": player, "name": name}, event=found and found.about)


# team_results

def team_results(query, tools, player_id, partner_id=None, year=None, event=None, since=None, until=None,
                 region=None):
    player, name, given = person(tools, player_id)
    partner, other, given_partner = person(tools, partner_id, "partner_id") if partner_id is not None else (None, None, None)
    if partner == player:
        raise Refused(f"player_id and partner_id are both {name}: pass the two players' player_ids, or leave partner_id"
                      " out for every partner")
    narrow = narrowing(tools, year, since, until, event, region)
    found = narrow.found
    if found and not found.usable:
        return unanswered("team_results", found, query)
    where = [f"t.player_id = {player}"] + ([f"t.partner_id = {partner}"] if partner else []) + narrow.where("t")
    scope, cond = f"{SCOPE}, {', '.join(['2v2'] + narrow.said)}", " AND ".join(where)
    here = " here" if narrow else ""
    notes = (found.notes + status_notes(query, found.events) if found else []) + narrow.notes + [
        note for note in (merged(given, player, name), partner and merged(given_partner, partner, other)) if note]
    counts = "COUNT(*), SUM(t.placement = 1), SUM(t.placement <= 3), SUM(t.placement <= 8), MIN(t.placement)"
    about = {"player": {"player_id": player, "name": name}, "event": found and found.about}
    if partner is None:
        partners = query.rows(f"SELECT p.name, t.partner_id, {counts} FROM v_team_results t JOIN players p ON"
                              f" p.player_id = t.partner_id WHERE {cond} GROUP BY t.partner_id ORDER BY 3 DESC, 7, p.name")
        results = sum(r[2] for r in partners)
        notes.append(f"{name} has {results} official 2v2 result{'' if results == 1 else 's'} with {len(partners)}"
                     f" partner{'' if len(partners) == 1 else 's'}{here}." if partners else
                     f"{name} has no official 2v2 results{here}.")
        return observation("team_results", scope, notes, [
            table(f"{name}'s 2v2 partners, the most events together first",
                  ["partner", "partner_id", "events", "wins", "medals", "top8s", "best"], partners, optional=True)
            if partners else None], query.ran, **about)
    together = query.rows(f"SELECT {counts} FROM v_team_results t WHERE {cond}")[0]
    listed = query.rows(f"SELECT t.start_date, t.tournament_name, t.event_name, t.placement FROM v_team_results t"
                        f" WHERE {cond} ORDER BY t.start_date, t.event_id")
    if not listed:
        notes.append(f"{name} and {other} have no official 2v2 results together{here}.")
    ends = [[which, r[0], event_name(r[1], r[2]), r[3]] for which, r in first_and_latest(listed, lambda r: r[0])]
    return observation("team_results", scope, notes, [
        table(f"{name} and {other}'s 2v2 results together", ["player", "partner", "events", "wins", "medals", "top8s",
                                                             "best"], [[name, other, *together]]) if listed else None,
        table("the first and the latest of them", ["which", "date", "event", "placement"], ends) if ends else None,
        table("each of them, oldest first", ["date", "event", "placement"],
              [[r[0], event_name(r[1], r[2]), r[3]] for r in listed], optional=True) if listed else None],
        query.ran, **about, partner={"player_id": partner, "name": other})


# head_to_head

def head_to_head(query, tools, player_id, opponent_id, year=None, since=None, until=None, event=None, region=None):
    player, name, given = person(tools, player_id)
    opponent, other, given_other = person(tools, opponent_id, "opponent_id")
    if player == opponent:
        raise Refused(f"player_id and opponent_id are both {name}: pass the two players' player_ids")
    narrow = narrowing(tools, year, since, until, event, region)
    if narrow.found and not narrow.found.usable:
        return unanswered("head_to_head", narrow.found, query)
    within = "".join(f" AND {c}" for c in narrow.where("s"))
    side = ("SELECT s.start_date, s.start_time, s.event_id, s.match_id, s.tournament_name, s.event_name, s.winner_name,"
            " s.winner_id, s.winner_games, s.loser_games, s.is_scored FROM v_sets_1v1 s"
            " WHERE s.winner_id = {} AND s.loser_id = {}" + within)
    listed = query.rows(f"{side.format(player, opponent)} UNION ALL {side.format(opponent, player)}"
                        " ORDER BY start_date, start_time, event_id, match_id")  # each side alone: an OR reads every set
    if narrow:  # the record of the sets in the window, as the view has no dates
        scored = [r for r in listed if r[10]]
        wins, sets = sum(r[7] == player for r in listed), len(listed)
        losses, unscored = sets - wins, sets - len(scored)
        games_won = sum(r[8] if r[7] == player else r[9] for r in scored) if scored else None
        games_lost = sum(r[9] if r[7] == player else r[8] for r in scored) if scored else None
    else:
        (wins, losses, sets, games_won, games_lost, unscored), = query.rows(
            "SELECT wins, losses, matches, games_won, games_lost, unscored_matches FROM v_head_to_head_1v1"
            f" WHERE player_id = {player} AND opponent_id = {opponent}") or [(0, 0, 0, None, None, 0)]
    (met, won), = query.rows(
        "SELECT COUNT(*), COALESCE(SUM(a.won), 0) FROM v_match_results a JOIN v_match_results b ON b.match_id = a.match_id"
        f" AND b.side <> a.side WHERE a.player_id = {player} AND b.player_id = {opponent} AND a.mode = '2v2'"
        + "".join(f" AND {c}" for c in narrow.where("a")))
    notes = [n for n in (merged(given, player, name), merged(given_other, opponent, other)) if n]
    notes += ((narrow.found.notes + status_notes(query, narrow.found.events)) if narrow.found else []) + narrow.notes
    here = f" {', '.join(narrow.said)}" if narrow else ""
    if not sets:
        notes.append(f"{name} and {other} have no counted 1v1 sets against each other at official events{here} (DQs,"
                     " forfeits and ties aren't counted).")
    if unscored:
        notes.append(f"{unscored} of the {sets} sets {'has' if unscored == 1 else 'have'} no recorded score, so the games"
                     f" leave {'it' if unscored == 1 else 'them'} out: say the record includes sets with no recorded score.")
    if sets:  # each record from both sides, so an answer can name whose it is (finding 24)
        notes.append(f"In 1v1, {name} won {wins} and lost {losses} of their {sets} set{'' if sets == 1 else 's'} against"
                     f" {other}; {other} won"
                     f" {losses} and lost {wins}.")
    notes.append(f"In 2v2, {name} and {other} never met on opposite teams{here}." if not met else
                 f"In 2v2, {name}'s teams and {other}'s teams met in {met} set{'' if met == 1 else 's'}: {name}'s side won"
                 f" {won} and lost {met - won}, and {other}'s side won {met - won} and lost {won}. Those aren't in the 1v1"
                 " record.")
    record = table(f"{name}'s 1v1 record against {other}, in sets{here}",
                   ["player", "player_id", "opponent", "opponent_id", "wins", "losses", "sets", "games_won", "games_lost",
                    "unscored_sets"], [[name, player, other, opponent, wins, losses, sets, games_won, games_lost, unscored]])
    each = table("each 1v1 set between them, oldest first", ["event", "date", "winner", "winner_id", "winner_games",
                                                              "loser_games"],
                 [[set_event(r[4], r[5]), r[0], *r[6:10]] for r in listed], optional=True) if listed else None
    return observation("head_to_head", ", ".join([SETS_SCOPE, *narrow.said]), notes, [record, each], query.ran,
                       player={"player_id": player, "name": name}, opponent={"player_id": opponent, "name": other},
                       event=narrow.found and narrow.found.about)


# rank_players

def one_by(value):
    """A by argument as 'wins', 'medals' or 'top8s', as a model may write them ('titles', 'top 8s')."""
    word = re.sub(r"[^a-z0-9]", "", value.lower()) if isinstance(value, str) else ""
    by = next((by for by, words in BY_WORDS.items() if word in words), None)
    if by is None:
        raise Refused(f"by is 'wins', 'medals' or 'top8s', not {value!r}")
    return by


def tie_groups(rows):
    """Ranked rows (rank first, in rank order) as their tie groups, in order."""
    groups = []
    for row in rows:
        if groups and groups[-1][0][0] == row[0]:
            groups[-1].append(row)
        else:
            groups.append([row])
    return groups


def rank_players(query, tools, by, top=5, mode=None, year=None, event=None, since=None, until=None, region=None):
    by, top = one_by(by), whole(top, "top")
    mode = None if mode is None else one_mode(mode)
    narrow = narrowing(tools, year, since, until, event, region)
    found = narrow.found
    if found and not found.usable:
        return unanswered("rank_players", found, query)
    where, scope = conditions(mode, narrow)
    regional = query.rows("SELECT DISTINCT event_id, series || ' ' || year FROM v_event_series WHERE regional = 1 AND"
                          f" event_id IN ({in_ids(found.events)}) ORDER BY 2") if found else []
    counts = {by: "COUNT(*)"}  # each column after the player's, with how it's counted
    if not mode:
        counts.update({"1v1": "SUM(r.mode = '1v1')", "2v2": "SUM(r.mode = '2v2')"})
    if mode != "2v2":
        counts["crew battles"] = "SUM(r.format = 'crew_battle')"
    if regional:
        counts["at regional championships"] = f"SUM(r.event_id IN ({', '.join(quoted(e) for e, _ in regional)}))"
    rows = query.rows(
        f"WITH counted AS (SELECT r.player_id, {', '.join(f'{sql} AS c{i}' for i, sql in enumerate(counts.values()))}"
        f" FROM v_results r WHERE {' AND '.join([f'r.placement <= {BY[by]}'] + where)} GROUP BY r.player_id),"
        " ranked AS (SELECT *, RANK() OVER (ORDER BY c0 DESC) AS rank FROM counted)"
        f" SELECT ranked.rank, p.name, ranked.player_id, {', '.join(f'c{i}' for i in range(len(counts)))} FROM ranked"
        f" JOIN players p ON p.player_id = ranked.player_id WHERE ranked.rank <= {top} ORDER BY ranked.rank, p.name")
    listed, left = [], []  # whole tie groups: past RANKED_AT_MOST rows, a group is counted instead of listed
    for members in tie_groups(rows):
        if left or len(listed) + len(members) > RANKED_AT_MOST:
            left.append(members)
        else:
            listed += members
    notes = (found.notes + status_notes(query, found.events) if found else []) + narrow.notes
    if not rows:
        notes.append(f"No player has any {CUTS[BY[by]]} here ({scope}), so the ranking is empty.")
    if left:
        counted = [f"{len(group)} tied at rank {group[0][0]} with {group[0][3]} {by} each" for group in left[:3]]
        below = sum(len(group) for group in left[3:])
        notes.append(f"Past {RANKED_AT_MOST} rows a tie isn't split, so these players are counted but not listed:"
                     f" {joined(counted)}{f', and {below} ranked below them' if below else ''}. Narrow the question (a"
                     " mode, a year, an event) or ask for fewer ranks to list them.")
    if len({row[0] for row in listed}) < len(listed):
        notes.append("Players on the same rank are tied: give them the same place.")
    if not mode and rows:
        notes.append(f"A tournament's 1v1 and 2v2 are separate events, and each counts: {CUTS[BY[by]]} at both count"
                     " twice. Say so.")
    crews = 3 + list(counts).index("crew battles") if "crew battles" in counts else None
    if crews and any(row[crews] for row in listed):
        notes.append("The crew battles column counts each player's crew battles among these: a crew's placement is a team"
                     " result, counted as 1v1. Say so.")
    if regional:
        years = list(dict.fromkeys(y for _, y in regional))
        notes.append(f"{joined([repr(y) for y in years])} {'was' if len(years) == 1 else 'were each'} held as several"
                     f" regional championships, all counted here: 'at regional championships' counts each player's {by}"
                     " at them. Say whether your answer counts them.")
    return observation("rank_players", scope, notes, [
        table(f"players ranked by {CUTS[BY[by]]}, everyone ranked {ordinal(top)} or better: ties all included",
              ["rank", "player", "player_id", *counts], listed)], query.ran, event=found and found.about)


# rank_pairs

PAIR_WORDS = {"opponents": {"opponents", "opponent", "rivals", "rival", "rivalries", "rivalry", "matchups", "versus", "vs"},
              "teammates": {"teammates", "teammate", "partners", "partner", "teams", "team", "duos", "duo"}}
PAIR_BY = {"events": "COUNT(*)", "wins": "SUM(t.placement = 1)", "medals": "SUM(t.placement <= 3)",
           "top8s": "SUM(t.placement <= 8)"}  # what teammates are ranked by; opponents by the sets between them


def one_of(value):
    """An of argument as 'opponents' or 'teammates', as a model may write them ('rivals', 'partners')."""
    word = re.sub(r"[^a-z]", "", value.lower()) if isinstance(value, str) else ""
    of = next((of for of, words in PAIR_WORDS.items() if word in words), None)
    if of is None:
        raise Refused(f"of is 'opponents' or 'teammates', not {value!r}")
    return of


def ties(rows):
    """Ranked rows (rank first) as (listed, left): whole tie groups, past RANKED_AT_MOST rows counted, not listed."""
    listed, left = [], []
    for members in tie_groups(rows):
        if left or len(listed) + len(members) > RANKED_AT_MOST:
            left.append(members)
        else:
            listed += members
    return listed, left


def rank_pairs(query, tools, of="opponents", by=None, top=5, mode=None, player_id=None, year=None, since=None,
               until=None, event=None, region=None, min_sets=None):
    """Pairs of players ranked: opponents by the 1v1 sets between them, or for one player their 2v2 meetings too;
    teammates by their 2v2 events, wins, medals or top 8s together. Each pair once, every tie included."""
    of, top = one_of(of), whole(top, "top")
    least = None if min_sets is None else whole(min_sets, "min_sets")
    narrow = narrowing(tools, year, since, until, event, region)
    if narrow.found and not narrow.found.usable:
        return unanswered("rank_pairs", narrow.found, query)
    player, name, given = person(tools, player_id) if player_id is not None else (None, None, None)
    notes = ((narrow.found.notes + status_notes(query, narrow.found.events)) if narrow.found else []) + narrow.notes
    if given != player:
        notes.append(merged(given, player, name))
    if of == "opponents":
        mode = "1v1" if mode is None else one_mode(mode)
        record = str(by or "").strip().lower() in ("record", "records", "best record", "wins", "win rate")
        if by is not None and not record and str(by).strip().lower() not in ("sets", "meetings", "matches", "played",
                                                                             "most"):
            raise Refused(f"opponents are ranked by the sets between them, or with player_id by='record', not {by!r}")
        if record and player is None:
            raise Refused("by='record' ranks one player's opponents by that player's record against them: give"
                          " player_id")
        if mode == "2v2" and player is None:
            raise Refused("2v2 opponents are ranked for one player only: give player_id. Over every player the 2v2"
                          " meetings take more than a minute; for the most-played pairs overall, use mode 1v1")
        within = "".join(f" AND {c}" for c in narrow.where("s"))
        if player is None:
            ranked = (f"WITH pairs AS (SELECT MIN(s.winner_id, s.loser_id) AS a, MAX(s.winner_id, s.loser_id) AS b,"
                      f" COUNT(*) AS n, SUM(s.winner_id < s.loser_id) AS a_wins FROM v_sets_1v1 s WHERE 1{within}"
                      " GROUP BY 1, 2)")
        elif mode == "1v1":
            ranked = (f"WITH sides AS (SELECT s.loser_id AS b, 1 AS won FROM v_sets_1v1 s WHERE s.winner_id = {player}"
                      f"{within} UNION ALL SELECT s.winner_id, 0 FROM v_sets_1v1 s WHERE s.loser_id = {player}{within}),"
                      f" pairs AS (SELECT {player} AS a, b, COUNT(*) AS n, SUM(won) AS a_wins FROM sides GROUP BY b)")
        else:
            met = "".join(f" AND {c}" for c in narrow.where("m"))
            ranked = ("WITH pairs AS (SELECT m.player_id AS a, o.player_id AS b, COUNT(*) AS n, SUM(m.won) AS a_wins"
                      " FROM v_match_results m JOIN v_match_results o ON o.match_id = m.match_id AND o.side <> m.side"
                      f" WHERE m.player_id = {player} AND m.mode = '2v2'{met} GROUP BY 2)")
        order = "a_wins DESC, n - a_wins ASC" if record else "n DESC"  # a record: the most wins, then fewest losses
        rows = query.rows(
            f"{ranked}, ranked AS (SELECT *, RANK() OVER (ORDER BY {order}) AS rank FROM pairs"
            f"{f' WHERE n >= {least}' if least else ''})"
            " SELECT ranked.rank, pa.name, ranked.a, pb.name, ranked.b, ranked.n, ranked.a_wins, ranked.n - ranked.a_wins"
            " FROM ranked JOIN players pa ON pa.player_id = ranked.a JOIN players pb ON pb.player_id = ranked.b"
            f" WHERE ranked.rank <= {top} ORDER BY ranked.rank, pa.name, pb.name")
        what = "sets" if mode == "1v1" else "meetings"
        columns = ["rank", "player", "player_id", "opponent", "opponent_id", what, "player_wins", "opponent_wins"]
        title = (f"{name}'s records against opponents, the most wins first, then the fewest losses" if record else
                 f"{name}'s opponents, the most {what} first" if player else "pairs of opponents, the most sets first")
        if record:
            notes.append(f"by='record' ranks {name}'s opponents by {name}'s wins against them, then the fewest losses"
                         + (f", among those with at least {least} {what} between them" if least else
                            ", with no minimum of sets") + ": say how the answer reads 'best record', and the minimum.")
        notes.append("Each pair is on one row, with each player's wins in their 1v1 sets against the other; DQs, forfeits"
                     " and ties are left out." if mode == "1v1" else
                     f"A meeting is a 2v2 set with {name} and the other player on opposite teams; player_wins are"
                     f" {name}'s side's wins.")
        scope = ", ".join([SETS_SCOPE if mode == "1v1" else f"{SCOPE}, 2v2 sets", *narrow.said])
    else:
        if mode is not None and one_mode(mode) != "2v2":
            raise Refused("teammates play 2v2 together: leave mode out")
        by = "events" if by is None else re.sub(r"[^a-z0-9]", "", str(by).lower()).replace("top8", "top8s").replace(
            "top8ss", "top8s")
        if by not in PAIR_BY:
            raise Refused(f"teammates are ranked by events, wins, medals or top8s, not {by!r}")
        where = ([f"t.player_id = {player}"] if player else ["t.player_id < t.partner_id"]) + narrow.where("t")
        rows = query.rows(
            "WITH pairs AS (SELECT t.player_id AS a, t.partner_id AS b, " + ", ".join(
                f"{sql} AS {column}" for column, sql in PAIR_BY.items()) +
            f" FROM v_team_results t WHERE {' AND '.join(where)} GROUP BY 1, 2),"
            f" ranked AS (SELECT *, RANK() OVER (ORDER BY {by} DESC) AS rank FROM pairs)"
            " SELECT ranked.rank, pa.name, ranked.a, pb.name, ranked.b, events, wins, medals, top8s FROM ranked"
            " JOIN players pa ON pa.player_id = ranked.a JOIN players pb ON pb.player_id = ranked.b"
            f" WHERE ranked.rank <= {top} ORDER BY ranked.rank, pa.name, pb.name")
        columns = ["rank", "player", "player_id", "partner", "partner_id", "events", "wins", "medals", "top8s"]
        title = f"{name}'s partners" if player else f"pairs of teammates, the most {by} together first"
        notes.append("Each pair is on one row, with their 2v2 results together: events, wins (1st places), medals (top"
                     " 3) and top 8s.")
        scope = ", ".join([f"{SCOPE}, 2v2", *narrow.said])
    listed, left = ties(rows)
    if not rows:
        notes.append(f"No pair has any here ({scope}), so the ranking is empty.")
    if left:
        notes.append(f"Past {RANKED_AT_MOST} rows a tie isn't split, so {sum(len(g) for g in left)} more pairs are"
                     " counted but not listed: ask for fewer ranks, or narrow the question.")
    if len({row[0] for row in listed}) < len(listed):
        notes.append("Pairs on the same rank are tied: give them the same place.")
    return observation("rank_pairs", scope, notes, [table(f"{title}, everyone ranked {ordinal(top)} or better", columns,
                                                          listed) if listed else None], query.ran,
                       player=player and {"player_id": player, "name": name}, event=narrow.found and narrow.found.about)


# power_rankings

PR_REGIONS = {"na": "NA", "eu": "EU", "sa": "SA", "brz": "SA", "sea": "SEA", "mena": "MENA"}  # Brazil plays in SA


def power_rankings(query, tools, region=None, mode="1v1", top=10, player_id=None):
    """The official Power Rankings in pr_snapshots: a region's top N in a mode, every region's without one, or with
    player_id each ranking the player is in."""
    mode, top = one_mode(mode), whole(top, "top")
    code = None
    if region is not None:
        found = tools.events.region(region)
        code = PR_REGIONS.get(found[0]) if found else None
        if code is None:
            raise Refused(f"the Power Rankings' regions are NA, EU, SA (Brazil's too), SEA and MENA, not {region!r}")
    (as_of,), = query.rows("SELECT MAX(as_of) FROM pr_snapshots")
    columns = ["region", "mode", "rank", "player", "player_id", "points", "gold", "silver", "bronze", "top8", "top32"]
    select = ("SELECT pr.region, pr.mode, pr.power_ranking, pr.player_id, pr.points, pr.gold, pr.silver, pr.bronze,"
              f" pr.top8, pr.top32 FROM pr_snapshots pr WHERE pr.as_of = '{as_of}'")
    canonical, names = tools.resolver.canonical, tools.resolver.names
    about = {}
    if player_id is not None:
        player, name, given = person(tools, player_id)
        records = [pid for pid, c in canonical.items() if c == player]
        rows = query.rows(f"{select} AND pr.player_id IN ({', '.join(map(str, records))})"
                          " ORDER BY pr.mode, pr.power_ranking")
        about["player"] = {"player_id": player, "name": name}
        title = f"{name}'s Power Rankings"
        notes = [f"{name} isn't in the Power Rankings of {as_of}." if not rows else
                 f"{name} is ranked in {len(rows)} of the Power Rankings of {as_of}."]
    else:
        rows = query.rows(f"{select} AND pr.mode = '{mode}' AND pr.power_ranking <= {top}"
                          + (f" AND pr.region = '{code}'" if code else "") + " ORDER BY pr.region, pr.power_ranking")
        title = f"the {mode} Power Rankings{f' of {code}' if code else ', each region'}, everyone ranked {ordinal(top)} or better"
        notes = [] if rows else [f"No player is ranked here ({mode}{f', {code}' if code else ''})."]
    notes.append(f"These are the official Power Rankings as of {as_of}, the only snapshot: the Stats API's ranking by"
                 " points, region by region and mode by mode. Their gold, silver, bronze, top8 and top32 are the Stats"
                 " API's own counts behind the ranking, not this data's counts of official results: say so if you give"
                 " them.")
    listed = [[r[0], r[1], r[2], names.get(canonical.get(r[3], r[3])), canonical.get(r[3], r[3]), *r[4:]] for r in rows]
    return observation("power_rankings", f"official Power Rankings as of {as_of}", notes,
                       [table(title, columns, listed) if listed else None], query.ran, **about)


# upsets

def seeds_at(query, tools, events):
    """{(event_id, person's player_id): their initial seed at that event}, from the standings, for the events given
    (None: every event, read once and kept on tools: about 8 s). A person with two records at one event has the
    better seed. Records map to persons in memory (the resolver's canonical IDs), as a join would cost more."""
    if events is None and getattr(tools, "seeds", None) is not None:
        return tools.seeds
    within = "" if events is None else f" AND event_id IN ({', '.join(quoted(e) for e in sorted(events)) or 'NULL'})"
    canonical, out = tools.resolver.canonical, {}
    for event_id, pid, seed in query.rows("SELECT event_id, player_id, initial_seed FROM standings"
                                          f" WHERE initial_seed IS NOT NULL{within}"):
        key = (event_id, canonical.get(pid, pid))
        if key not in out or seed < out[key]:
            out[key] = seed
    if events is None:
        tools.seeds = out
    return out


def upsets(query, tools, mode="1v1", top=5, player_id=None, year=None, since=None, until=None, event=None, region=None):
    """Sets the lower seed won, the biggest seed difference first (the user's definition, 2026-11-21): the lower
    seed is the higher initial seed number at that event, from its standings; a set without both seeds isn't judged."""
    mode, top = one_mode(mode), whole(top, "top")
    narrow = narrowing(tools, year, since, until, event, region)
    if narrow.found and not narrow.found.usable:
        return unanswered("upsets", narrow.found, query)
    player, name, given = person(tools, player_id) if player_id is not None else (None, None, None)
    if mode == "2v2" and not (narrow.found or player):
        raise Refused("2v2 upsets need an event or a player_id: over every event the 2v2 sets take more than a minute")
    if mode == "1v1":
        within = "".join(f" AND {c}" for c in narrow.where("x")) + (f" AND x.winner_id = {player}" if player else "")
        sets = [(event_id, date, [(winner, wname)], [(loser, lname)], wg, lg) for event_id, date, winner, wname, loser,
                lname, wg, lg in query.rows(
                    "SELECT x.event_id, x.start_date, x.winner_id, x.winner_name, x.loser_id, x.loser_name, x.winner_games,"
                    f" x.loser_games FROM v_sets_1v1 x WHERE 1{within}")]
    else:
        within = "".join(f" AND {c}" for c in narrow.where("m"))
        mine = (f" AND m.match_id IN (SELECT match_id FROM v_match_results WHERE player_id = {player} AND mode = '2v2')"
                if player else "")
        sides = {}
        for match_id, event_id, date, side, pid, won in query.rows(
                "SELECT m.match_id, m.event_id, m.start_date, m.side, m.player_id, m.won FROM v_match_results m"
                f" WHERE m.mode = '2v2'{within}{mine}"):
            entry = sides.setdefault(match_id, {"event": event_id, "date": date, "won": {}, "lost": {}})
            entry["won" if won else "lost"].setdefault(side, []).append((pid, tools.resolver.names.get(pid)))
        sets = [(e["event"], e["date"], next(iter(e["won"].values())), next(iter(e["lost"].values())), None, None)
                for e in sides.values() if len(e["won"]) == 1 and len(e["lost"]) == 1]
        if player:  # the player's side won as the lower seed
            sets = [x for x in sets if any(pid == player for pid, _ in x[2])]
    seeds = seeds_at(query, tools, None if mode == "1v1" and not narrow and not player else {x[0] for x in sets})
    def seed(event_id, team):
        known = [seeds.get((event_id, pid)) for pid, _ in team]
        return min(known) if known and all(k is not None for k in known) else None
    judged, upset = 0, []
    for event_id, date, winners, losers, wg, lg in sets:
        ws, ls = seed(event_id, winners), seed(event_id, losers)
        if ws is None or ls is None:
            continue
        judged += 1
        if ws > ls:
            upset.append((ws - ls, event_id, date, winners, ws, losers, ls, wg, lg))
    upset.sort(key=lambda u: (-u[0], u[2] or "", u[1]))
    rows, rank, last = [], 0, None
    for i, (diff, event_id, date, winners, ws, losers, ls, wg, lg) in enumerate(upset, 1):
        rank = i if diff != last else rank
        last = diff
        if rank > top:
            break
        rows.append([rank, tools.events.events.get(event_id, {}).get("name", event_id), date,
                     " / ".join(n or str(p) for p, n in winners), [p for p, _ in winners] if mode == "2v2" else winners[0][0],
                     ws, " / ".join(n or str(p) for p, n in losers), [p for p, _ in losers] if mode == "2v2" else losers[0][0],
                     ls, diff, wg, lg])
    listed, left = ties(rows)
    notes = ((narrow.found.notes + status_notes(query, narrow.found.events)) if narrow.found else []) + narrow.notes
    if given != player:
        notes.append(merged(given, player, name))
    notes.append(f"An upset is a set the lower seed won: the higher initial seed number at that event, from its"
                 f" standings; the biggest has the largest seed difference. Of the {len(sets)} {mode} sets here,"
                 f" {judged} had both seeds and {len(upset)} were upsets; a set without both seeds isn't judged. Say"
                 " so, and give each upset's seeds.")
    if left:
        notes.append(f"Past {RANKED_AT_MOST} rows a tie isn't split, so {sum(len(g) for g in left)} more upsets are counted"
                     " but not listed.")
    if len({row[0] for row in listed}) < len(listed):
        notes.append("Upsets on the same rank are tied: give them the same place.")
    title = (f"{name}'s upset wins, the biggest seed difference first" if player else
             "upsets, the biggest seed difference first") + f", everyone ranked {ordinal(top)} or better"
    columns = ["rank", "event", "date", "winner", "winner_id", "winner_seed", "loser", "loser_id", "loser_seed",
               "seed_difference", "winner_games", "loser_games"]
    return observation("upsets", ", ".join([SETS_SCOPE if mode == "1v1" else f"{SCOPE}, 2v2 sets", *narrow.said]), notes,
                       [table(title, columns, listed) if listed else None], query.ran,
                       player=player and {"player_id": player, "name": name}, event=narrow.found and narrow.found.about)


TEMPLATES = {t.name: t for t in (
    Template(
        "event_results",
        "An official event's results: its winners, or its top N with top, a team's players together and every tie"
        " included, with the events' event_ids, dates, modes, statuses (not held, placements unreliable) and bracket links."
        " Use it for who won an event, its top 8, when it was held or where its bracket is. Give the event's name as"
        " the question writes it, with its year, region and mode if the question has them ('winters 2023 na 1v1',"
        " 'bcx 2022', 'worlds'): the tool finds the events itself.",
        {"event": {"type": "string", "description": "the event's name as the question writes it"},
         "top": {"type": "integer", "description": "how many places to return: 1 for the winners (the default), 8 for"
                                                   " the top 8"}},
        ("event",), event_results),
    Template(
        "player_results",
        "One player's results at official events: how many, by mode (1st, 2nd and 3rd places, medals, top 8s, the"
        " best), the first and the latest, and the list. With no top it's the player's whole record in one call, with"
        " how many times each placement happened and the results at their best placement (ties included): use it so"
        " for a player's stats, record, profile or card, their best placement and where, or how often they placed"
        " each way. Use top for their wins, titles or majors alone (top 1),"
        " medals (top 3) or top 8s (top 8), and narrow it to a mode, a year, a time window (since, until), a region, or"
        " an event or series ('worlds', 'bcx 2024') when the question does. With top, it counts only those results, not the player's whole record.",
        {"player_id": {"type": "integer", "description": "the player's player_id, from resolve_player"},
         "top": {"type": "integer", "description": "keep results placed this or better: 1 for wins, 3 for medals, 8 for"
                                                   " top 8s; leave out for every result"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "one mode only; leave out for both"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("player_id",), player_results),
    Template(
        "team_results",
        "One player's 2v2 results with partners at official events. With partner_id, the two players' events together:"
        " how many, their wins, medals, top 8s and best placement together, the first and the latest, and each event."
        " Without it, each partner the player has had, with those figures, the most events together first. Use it for"
        " how two players did as a team, how many events they won together, or who a player has played with in 2v2,"
        " and narrow it to a year, a time window, a region, or an event or series, when the question does.",
        {"player_id": {"type": "integer", "description": "the player's player_id, from resolve_player"},
         "partner_id": {"type": "integer", "description": "the partner's player_id, from resolve_player; leave out for"
                                                          " every partner"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("player_id",), team_results),
    Template(
        "head_to_head",
        "Two players against each other at official events: the first player's 1v1 record against the other in sets"
        " (wins, losses, games), each 1v1 set between them with its winner and score, and whether they met in 2v2. It"
        " counts sets, not placements: for where they placed at the same events, such as how often one finished behind"
        " the other, use run_sql on v_results. Use it for a head-to-head, a rivalry, or one player's record or history"
        " against another, with the player the question asks about first, narrowed to a year, a time window, a region"
        " or an event when the question is.",
        {"player_id": {"type": "integer", "description": "the first player's player_id, from resolve_player: the record"
                                                         " is theirs"},
         "opponent_id": {"type": "integer", "description": "the other player's player_id, from resolve_player"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("player_id", "opponent_id"), head_to_head),
    Template(
        "rank_players",
        "Players ranked by their wins (1st places), medals (top 3) or top 8s at official events, every tie included:"
        " the top 5 is everyone ranked 5th or better. Each row has the player's count, its 1v1 and 2v2 split and its"
        " crew battles. Use it for who has the most wins, titles, majors, medals or top 8s, overall or in a mode, a"
        " year, a time window (since, until), a region, or an event or series ('worlds', 'bcx'). It can't leave players out or take another condition, such"
        " as never having won: use run_sql.",
        {"by": {"type": "string", "enum": list(BY), "description": "what to count: wins, medals or top8s"},
         "top": {"type": "integer", "description": "how many ranks to return: 5 (the default) is everyone ranked 5th or"
                                                   " better"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "one mode only; leave out for both"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("by",), rank_players),
    Template(
        "rank_pairs",
        "Pairs of players ranked at official events, each pair once, every tie included. of='opponents' (the default):"
        " the pairs with the most 1v1 sets between them, with each one's wins; with player_id, that player's most-played"
        " opponents, in 1v1 or, with mode 2v2, in 2v2 meetings between their teams. of='teammates': 2v2 partners ranked"
        " by their events together (by='events', the default), wins, medals or top8s together; with player_id, that"
        " player's partners. With player_id and by='record', that player's opponents ranked by the player's record"
        " against them: the most wins, then the fewest losses (min_sets for a minimum). Use it for the biggest"
        " rivalries, who has played whom the most, a player's most-played opponents, a player's best records against"
        " opponents, or the best duos, and narrow it to a year, a time window, a region or an event when the question"
        " does. Don't query v_head_to_head_1v1 for pairs: over every player it takes more than a minute.",
        {"of": {"type": "string", "enum": ["opponents", "teammates"], "description": "opponents (the default) or"
                                                                                     " teammates"},
         "by": {"type": "string", "enum": ["sets", "record", "events", "wins", "medals", "top8s"],
                "description": "opponents: sets (the default), or record with player_id; teammates: events (the"
                               " default), wins, medals or top8s"},
         "top": {"type": "integer", "description": "how many ranks to return: 5 (the default) is every pair ranked 5th"
                                                   " or better"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "for opponents: 1v1 sets (the default), or"
                                                                           " 2v2 meetings, with player_id"},
         "player_id": {"type": "integer", "description": "one player's pairs only: their player_id, from resolve_player"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"},
         "min_sets": {"type": "integer", "description": "only pairs with at least this many sets between them, when the"
                                                        " question sets a minimum"}},
        (), rank_pairs),
    Template(
        "power_rankings",
        "The official Power Rankings (the Stats API's ranking by points, one snapshot, per region and mode): a region's"
        " top N in a mode, or each region's without region; with player_id, each ranking the player is in. Use it for"
        " who is ranked #1 or in the top 10 of a region, a player's PR or ranking, or who is best right now by the"
        " official ranking. Its regions are NA, EU, SA, SEA and MENA.",
        {"region": {"type": "string", "description": "na, eu, sa, sea or mena; leave out for every region"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "1v1 (the default) or 2v2"},
         "top": {"type": "integer", "description": "how many ranks to return: 10 (the default)"},
         "player_id": {"type": "integer", "description": "one player's rankings: their player_id, from resolve_player"}},
        (), power_rankings),
    Template(
        "upsets",
        "Upsets at official events: sets the lower seed won (the higher initial seed number at that event, from its"
        " standings), the biggest seed difference first, every tie included, with both players' seeds and the score;"
        " a set without both seeds isn't judged. With player_id, that player's upset wins. In 1v1 over every event or"
        " narrowed to a year, a time window, a region or an event; in 2v2 for an event or a player. Use it for the"
        " biggest upsets, an event's upsets, or a player's biggest upset wins.",
        {"mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "1v1 (the default) or 2v2"},
         "top": {"type": "integer", "description": "how many ranks to return: 5 (the default)"},
         "player_id": {"type": "integer", "description": "one player's upset wins: their player_id, from resolve_player"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "since": {"type": "string", "description": "only from this day on, included: 2025-10-01, 2025-10 or 2025"},
         "until": {"type": "string", "description": "only up to this day, included: 2024-12-31, 2024-12 or 2024"},
         "region": {"type": "string", "description": "one region's events only: na, eu, sa, brz, sea, aus, mena or jpn"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        (), upsets),
)}
