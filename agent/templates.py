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
- Players are given by player_id, from resolve_player, so a name the resolver isn't sure of still goes to the user
  as suggestions. Events are given by name and resolved here, as resolve_event resolves them.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Callable

from tools import ABOUT_ALIAS, EVENT_SCORES, SQL_SECONDS, TOKEN_BUDGET, cell, connect, quoted, tokens

EVENTS_AT_MOST = 60  # a name matching more events gets no results, only the closest few to choose from
CANDIDATES = 10
LINKS_AT_MOST = 4  # bracket links are listed for a tournament's events, not for a whole series
SCOPE = "official events"
LEFT_OUT = "{n} rows, too many to show with the rest: narrow the question (an event, a year, a mode, a lower top)."
DECIDED = re.compile(r"\s*\(decided \d{4}-\d{2}-\d{2}\)")  # a curated note's own bookkeeping, not for an answer


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
        given = {k: v for k, v in arguments.items() if v not in (None, "")}
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
    """An argument as a whole number of at least `least`: 5, 5.0 or '5', since a model writes numbers as text too."""
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        value = int(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < least:
        raise Refused(f"{name} is a whole number, {least} or more, not {value!r}")
    return value


def table(what, columns, rows, optional=False):
    """One table of a result. optional: a list the result does without when it is over the token budget."""
    out = {"what": what, "columns": columns, "rows": [[cell(v) for v in row] for row in rows], "row_count": len(rows)}
    return {**out, "optional": True} if optional else out


def observation(name, scope, notes, tables, ran, event=None):
    """A template's result (the module docstring). Over TOKEN_BUDGET, the optional tables lose their rows, the largest
    first, and keep their row count with a note."""
    out = {"template": name, "scope": scope, **({"event": event} if event else {}), "notes": notes, "tables": tables}
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
    listed = [table("the closest events", ["event", "date", "mode", "status"], closest)] if closest else []
    return observation(name, SCOPE, found.notes, listed, query.ran, found.about)


def in_ids(events):
    return ", ".join(quoted(e["event_id"]) for e in events)


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
        note = DECIDED.sub("", info[e["event_id"]][0] or "").strip().rstrip(".")
        about = f" The data's note on it: {note}." if note else ""
        sides = placed(e, rows.get(e["event_id"], []))
        if e.get("status") == "cancelled":
            notes.append(f"{label(e)} was not held, so it has no results: say it wasn't held, not that its results"
                         f" are missing.{about}")
        elif e.get("status") == "placements_unreliable":
            notes.append(f"{label(e)} has unreliable placements, so they aren't results and it has no reliable winner:"
                         f" say so, and why.{about}")
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
    listed = [[e["name"], e["start_date"], mode_label(e), e.get("status")] + ([info[e["event_id"]][1]] if links else [])
              for e in events]
    what = "each event's winners" if top == 1 else f"each event's top {top}: everyone placed {top} or better"
    return observation("event_results", SCOPE, notes, [
        table("the events the name means", ["event", "date", "mode", "status"] + (["bracket_url"] if links else []), listed),
        table(f"{what}, a team's players together", ["event", "date", "mode", "placement", "players", "player_ids"],
              placements, optional=True)], query.ran, found.about)


TEMPLATES = {t.name: t for t in (
    Template(
        "event_results",
        "An official event's results: its winners, or its top N with top, a team's players together and every tie"
        " included, with the event's date, mode, status (not held, placements unreliable) and bracket link. Use it for"
        " who won an event, its top 8, when it was held or where its bracket is. Give the event's name as the question"
        " writes it, with its year, region and mode if the question has them ('winters 2023 na 1v1', 'bcx 2022',"
        " 'worlds'): the tool finds the events itself.",
        {"event": {"type": "string", "description": "the event's name as the question writes it"},
         "top": {"type": "integer", "description": "how many places to return: 1 for the winners (the default), 8 for"
                                                   " the top 8"}},
        ("event",), event_results),
)}
