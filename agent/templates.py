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

from tools import (ABOUT_ALIAS, EVENT_SCORES, IDS_IN_SQL, MODE_WORDS, SQL_SECONDS, TOKEN_BUDGET, cell, connect, quoted,
                   tokens)

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
PLAYER_ARGUMENTS = ("player_id", "opponent_id")  # the arguments that take a player, which person() reads


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


def conditions(mode=None, year=None, events=None):
    """The conditions on a result r that a mode, a year and a set of events make, and the scope they leave."""
    where, said = [], [mode or "1v1 and 2v2"]
    if mode:
        where.append(f"r.mode = '{mode}'")
    if year:
        where.append(f"substr(r.start_date, 1, 4) = '{year}'")
        said.append(f"in {year}")
    if events is not None:
        where.append(f"r.event_id IN ({in_ids(events)})")
        said.append(f"at the {len(events)} event{'' if len(events) == 1 else 's'} the name means")
    return where, f"{SCOPE}, {', '.join(said)}"


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


def player_results(query, tools, player_id, top=None, mode=None, year=None, event=None):
    player, name, given = person(tools, player_id)
    top = None if top is None else whole(top, "top")
    mode = None if mode is None else one_mode(mode)
    year = None if year is None else whole(year, "year")
    found = None if event is None else match_events(tools, event)
    if found and not found.usable:
        return unanswered("player_results", found, query)
    where, scope = conditions(mode, year, found.events if found else None)
    where = " AND ".join([f"r.player_id = {player}"] + ([f"r.placement <= {top}"] if top else []) + where)
    counted = {m: figures for m, *figures in query.rows(
        "SELECT r.mode, COUNT(*), SUM(r.placement = 1), SUM(r.placement = 2), SUM(r.placement = 3),"
        " SUM(r.placement <= 8), MIN(r.placement), SUM(r.format = 'crew_battle')"
        f" FROM v_results r WHERE {where} GROUP BY r.mode")}
    listed = query.rows(
        "SELECT r.start_date, r.tournament_name, r.event_name, r.mode, r.format, r.placement, r.start_time"
        f" FROM v_results r WHERE {where} ORDER BY r.start_time, r.mode")
    every = dict(query.rows(f"SELECT r.mode, COUNT(*) FROM v_results r WHERE r.player_id = {player} GROUP BY r.mode"))
    notes = found.notes + status_notes(query, found.events) if found else []
    if given != player:
        notes.append(merged(given, player, name))
    modes = [mode] if mode else ["1v1", "2v2"]  # a mode has its row even with nothing in it: a 0 to read, not a gap
    summary = [[name, m, *(counted[m][:6] if m in counted else [0, 0, 0, 0, 0, None])] for m in modes]
    if not mode:
        best = min((row[7] for row in summary if row[7] is not None), default=None)
        summary.append([name, "1v1 and 2v2", *(sum(row[i] for row in summary) for i in range(2, 7)), best])
    if not listed:
        notes.append(f"{name} has no official 1v1 or 2v2 results in the data." if not every else
                     f"None of {name}'s {sum(every.values())} official results"
                     f" ({', '.join(f'{n} in {m}' for m, n in sorted(every.items()))}) is among these: the count is 0,"
                     " which isn't the same as never having played.")
    crews = sum(figures[6] or 0 for figures in counted.values())
    if crews:
        notes.append(f"{crews} of the 1v1 {cut(top)} {'is a crew battle: a team result' if crews == 1 else 'are crew battles: team results'},"
                     " counted as 1v1.")
    ends = [[which, m, r[0], event_name(r[1], r[2]), r[5]] for m in modes
            for which, r in first_and_latest([r for r in listed if r[3] == m], lambda r: r[6])]
    each = [[r[0], event_name(r[1], r[2]), f"{r[3]} (crew battle)" if r[4] == "crew_battle" else r[3], r[5]] for r in listed]
    return observation("player_results", scope, notes, [
        table(f"{name}'s {cut(top)}, counted by mode",
              ["player", "mode", "results", "first", "second", "third", "top8", "best"], summary),
        table("the first and the latest of them in each mode", ["which", "mode", "date", "event", "placement"], ends)
        if ends else None,
        table("each of them, oldest first", ["date", "event", "mode", "placement"], each, optional=True)
        if each else None], query.ran, player={"player_id": player, "name": name}, event=found and found.about)


# head_to_head

def head_to_head(query, tools, player_id, opponent_id):
    player, name, given = person(tools, player_id)
    opponent, other, given_other = person(tools, opponent_id, "opponent_id")
    if player == opponent:
        raise Refused(f"player_id and opponent_id are both {name}: pass the two players' player_ids")
    (wins, losses, sets, games_won, games_lost, unscored), = query.rows(
        "SELECT wins, losses, matches, games_won, games_lost, unscored_matches FROM v_head_to_head_1v1"
        f" WHERE player_id = {player} AND opponent_id = {opponent}") or [(0, 0, 0, None, None, 0)]
    side = ("SELECT start_date, start_time, event_id, match_id, tournament_name, event_name, winner_name, winner_id,"
            " winner_games, loser_games FROM v_sets_1v1 WHERE winner_id = {} AND loser_id = {}")
    listed = query.rows(f"{side.format(player, opponent)} UNION ALL {side.format(opponent, player)}"
                        " ORDER BY start_date, start_time, event_id, match_id")  # each side alone: an OR reads every set
    (met, won), = query.rows(
        "SELECT COUNT(*), COALESCE(SUM(a.won), 0) FROM v_match_results a JOIN v_match_results b ON b.match_id = a.match_id"
        f" AND b.side <> a.side WHERE a.player_id = {player} AND b.player_id = {opponent} AND a.mode = '2v2'")
    notes = [n for n in (merged(given, player, name), merged(given_other, opponent, other)) if n]
    if not sets:
        notes.append(f"{name} and {other} have no counted 1v1 sets against each other at official events (DQs, forfeits"
                     " and ties aren't counted).")
    if unscored:
        notes.append(f"{unscored} of the {sets} sets {'has' if unscored == 1 else 'have'} no recorded score, so the games"
                     f" leave {'it' if unscored == 1 else 'them'} out: say the record includes sets with no recorded score.")
    notes.append(f"In 2v2, {name} and {other} never met on opposite teams." if not met else
                 f"In 2v2, {name}'s teams and {other}'s teams met in {met} set{'' if met == 1 else 's'}: {name}'s side won"
                 f" {won} and lost {met - won}. Those aren't in the 1v1 record.")
    record = table(f"{name}'s 1v1 record against {other}, in sets",
                   ["player", "player_id", "opponent", "opponent_id", "wins", "losses", "sets", "games_won", "games_lost",
                    "unscored_sets"], [[name, player, other, opponent, wins, losses, sets, games_won, games_lost, unscored]])
    each = table("each 1v1 set between them, oldest first", ["date", "event", "winner", "winner_id", "winner_games",
                                                              "loser_games"],
                 [[r[0], event_name(r[4], r[5]), *r[6:]] for r in listed], optional=True) if listed else None
    return observation("head_to_head", SETS_SCOPE, notes, [record, each], query.ran,
                       player={"player_id": player, "name": name}, opponent={"player_id": opponent, "name": other})


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


def rank_players(query, tools, by, top=5, mode=None, year=None, event=None):
    by, top = one_by(by), whole(top, "top")
    mode = None if mode is None else one_mode(mode)
    year = None if year is None else whole(year, "year")
    found = None if event is None else match_events(tools, event)
    if found and not found.usable:
        return unanswered("rank_players", found, query)
    where, scope = conditions(mode, year, found.events if found else None)
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
    notes = found.notes + status_notes(query, found.events) if found else []
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
        "One player's results at official events: how many, by mode (1st, 2nd and 3rd places, top 8s, the best), the"
        " first and the latest, and the list. Use it for a player's wins, titles or majors (top 1), medals (top 3), top"
        " 8s (top 8) or every result (no top), and narrow it to a mode, a year, or an event or series ('worlds', 'bcx"
        " 2024') when the question does.",
        {"player_id": {"type": "integer", "description": "the player's player_id, from resolve_player"},
         "top": {"type": "integer", "description": "keep results placed this or better: 1 for wins, 3 for medals, 8 for"
                                                   " top 8s; leave out for every result"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "one mode only; leave out for both"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("player_id",), player_results),
    Template(
        "head_to_head",
        "Two players against each other at official events: the first player's 1v1 record against the other in sets"
        " (wins, losses, games), each 1v1 set between them with its winner and score, and whether they met in 2v2. It"
        " counts sets, not placements: for where they placed at the same events, such as how often one finished behind"
        " the other, use run_sql on v_results. Use it for a head-to-head, a rivalry, or one player's record or history"
        " against another, with the player the question asks about first.",
        {"player_id": {"type": "integer", "description": "the first player's player_id, from resolve_player: the record"
                                                         " is theirs"},
         "opponent_id": {"type": "integer", "description": "the other player's player_id, from resolve_player"}},
        ("player_id", "opponent_id"), head_to_head),
    Template(
        "rank_players",
        "Players ranked by their wins (1st places), medals (top 3) or top 8s at official events, every tie included:"
        " the top 5 is everyone ranked 5th or better. Each row has the player's count, its 1v1 and 2v2 split and its"
        " crew battles. Use it for who has the most wins, titles, majors, medals or top 8s, overall or in a mode, a"
        " year, or an event or series ('worlds', 'bcx').",
        {"by": {"type": "string", "enum": list(BY), "description": "what to count: wins, medals or top8s"},
         "top": {"type": "integer", "description": "how many ranks to return: 5 (the default) is everyone ranked 5th or"
                                                   " better"},
         "mode": {"type": "string", "enum": ["1v1", "2v2"], "description": "one mode only; leave out for both"},
         "year": {"type": "integer", "description": "one calendar year only, such as 2026"},
         "event": {"type": "string", "description": "one event or series only: its name as the question writes it"}},
        ("by",), rank_players),
)}
