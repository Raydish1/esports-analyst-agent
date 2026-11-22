"""Stat cards for an answer (docs/stat-cards-proposal.md, design B): built after the turn, from the app's own calls.

The turn's successful template calls say which players and event the answer is about. The cards' figures then come
from calling the template functions again with no top, year or event, so the model's arguments can't change them, and
from queries of the app's own: career earnings, top 32s, a 2v2 head-to-head's sets, and an event's sets between
its top 8 players. Nothing is read from
the model's text.

Cards, at most two per answer:
- head_to_head: two players' lifetime figures mirrored, and their record in each mode (1v1 sets; 2v2 sets with the two
  on opposite teams, from TWOS, counted as head_to_head counts its 2v2 meetings; both summed); followed by sets, their
  sets in both modes, each marked with its mode, which the page's mode switch filters;
- comparison: two players' lifetime figures, for a turn that called player_results for two players;
- lifetime: one player's, for a player_results call without year or event;
- teams: two 2v2 teams, each player's lifetime figures, and the teams' record against each other (2v2 sets with each
  team's two players on one side, from TEAMS); followed by sets, those sets. For a turn that called team_results for
  two partnerships with no players in common;
  For a turn that called team_head_to_head with four players, or whose question names four players who make two
  teams in the data (the pairing with the most events together, each pair partnered at least once), or that looked
  up one held 2v2 event (its winners against its runners-up);
- team: one partnership, each partner's lifetime figures and their 2v2 results together (team_results with no year or
  event), for a turn that called team_results for one;
- sets for an event: the 1v1 sets between its top 8 players, for one held 1v1 event.

A missing value is None ("not recorded" on the page), never 0. With earnings off, cards have no "earnings" key and the
earnings query isn't run.
"""

import csv
import json
import re
from pathlib import Path

import mentions
from templates import TEMPLATES, set_event
from tools import connect

MODES = ("1v1 and 2v2", "1v1", "2v2")
COUNTS = ("results", "first", "second", "third", "top8", "top32")
SCOPE = "All official events, regional championships included. 1v1 and 2v2 counted together unless you pick one."
CREW = "Crew battles count as 1v1."
EARNINGS = "SELECT earnings_usd, source, as_of FROM v_career_earnings WHERE player_id = ?"
# Top 32s by mode, counted on v_results as player_results counts its top 8s (agent/ is frozen for the final runs, so the
# column isn't added there: the model's observations stay the same). Placements are bucketed (17, 25, 33 on start.gg;
# 22, 27, 32 on some Challengermode events), so <= 32 is the top 32 on both.
TOP32 = "SELECT mode, SUM(placement <= 32) FROM v_results WHERE player_id = ? GROUP BY mode"
EVENT_SETS = ("SELECT start_date, winner_name, winner_id, winner_placement, loser_name, loser_id, loser_placement,"
              " winner_games, loser_games, is_scored FROM v_sets_1v1 WHERE event_id = ? AND winner_placement <= 8"
              " AND loser_placement <= 8 ORDER BY start_date, start_time, match_id")
# Each 2v2 set with the two players on opposite teams, from the first player's side, with each one's partner: the
# meetings head_to_head counts (templates.head_to_head), listed. 0.1-0.3 s with the IDs as parameters.
PARTNER = ("(SELECT c.name FROM match_players mp JOIN players i ON i.player_id = mp.player_id"
           " JOIN players c ON c.player_id = i.canonical_id"
           " WHERE mp.match_id = {0}.match_id AND mp.side = {0}.side AND i.canonical_id <> {0}.player_id LIMIT 1)")
TWOS = ("SELECT a.start_date, e.tournament_name, e.event_name, a.won, a.games_won, a.games_lost, a.is_scored, "
        + PARTNER.format("a") + ", " + PARTNER.format("b") +
        " FROM v_match_results a JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side"
        " JOIN v_events e ON e.event_id = a.event_id"
        " WHERE a.player_id = ? AND b.player_id = ? AND a.mode = '2v2'"
        " ORDER BY a.start_date, a.start_time, a.match_id")
# Each 2v2 set with one team's two players on one side and the other's two on the other, from the first team's side:
# parameters (first team's partner, second team's player, second team's partner, first team's player). 0.1-0.5 s.
TEAMS = ("SELECT a.start_date, e.tournament_name, e.event_name, a.won, a.games_won, a.games_lost, a.is_scored"
         " FROM v_match_results a"
         " JOIN v_match_results a2 ON a2.match_id = a.match_id AND a2.side = a.side AND a2.player_id = ?"
         " JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side AND b.player_id = ?"
         " JOIN v_match_results b2 ON b2.match_id = a.match_id AND b2.side = b.side AND b2.player_id = ?"
         " JOIN v_events e ON e.event_id = a.event_id"
         " WHERE a.player_id = ? AND a.mode = '2v2' ORDER BY a.start_date, a.start_time, a.match_id")
# One held 2v2 event's first and second place teams, each once.
FINALISTS = ("SELECT player_id, partner_id, placement FROM v_team_results WHERE event_id = ? AND placement <= 2"
             " AND player_id < partner_id ORDER BY placement, player_id")
# A question naming four players is about two teams only if it says so: "vs", "against", "2v2", "team", ...
TEAM_WORDS = re.compile(r"\b(vs?|versus|against|played|fought|faced|met|beat|2v2|2s|doubles|teams?|duos?)\b", re.I)
TOGETHER = "SELECT COUNT(*) FROM v_team_results WHERE player_id = ? AND partner_id = ?"  # a partnership's events
NARROWING = ("year", "event", "since", "until", "region")  # a call with any of these is about part of a career
TEAM_SCOPE = ("Each player's own figures: all official events, regional championships included, in the mode picked (2v2"
              " when the card opens).")
MOST = 2
ROOT = Path(__file__).resolve().parent.parent.parent
LEGENDS = ROOT / "data" / "curated" / "player_legends.csv"  # player_id,legend: mains, for cards only
ART = ROOT / "app" / "static" / "art" / "legends"  # manifest.json and one transparent WebP per legend


class Legends:
    """Which legend's art a card shows for a player: their main from player_legends.csv, if manifest.json lists it and
    its file exists. Anything else is None, and the card shows its fallback: a legend is never guessed. Read on each
    lookup, so edits to the files show without a restart. The agent never reads these files."""

    def __init__(self, mains=LEGENDS, art=ART):
        self.mains, self.art = Path(mains), Path(art)

    def of(self, player_id):
        try:
            with open(self.mains, encoding="utf-8", newline="") as f:
                legend = next((r["legend"].strip().lower() for r in csv.DictReader(f)
                               if r.get("player_id", "").strip() == str(player_id) and r.get("legend")), None)
            if not legend:
                return None
            entry = json.loads((self.art / "manifest.json").read_text(encoding="utf-8")).get("legends", {}).get(legend)
        except (OSError, ValueError, KeyError):
            return None
        if not entry or not entry.get("file") or not (self.art / entry["file"]).is_file():
            return None
        head = entry.get("head")
        return {"slug": legend, "url": f"art/legends/{entry['file']}", "name": entry.get("name") or legend,
                "head": f"art/legends/{head}" if head and (self.art / head).is_file() else None,
                "offset_x": entry.get("offset_x", 0), "offset_y": entry.get("offset_y", 0), "scale": entry.get("scale", 1)}


def observed(call):
    """A tool call's result as a dict, or None for one that didn't run or failed."""
    if not call.get("observation"):
        return None
    try:
        data = json.loads(call["observation"])
    except ValueError:
        return None
    return None if not isinstance(data, dict) or "error" in data else data


def arguments(call):
    value = call.get("arguments")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def table_with(observation, *columns):
    """The first table holding all these columns."""
    for t in observation.get("tables", []):
        if all(c in t.get("columns", []) for c in columns):
            return t
    return None


def calls(trace, name):
    """(arguments, result) for the turn's successful calls of one tool, in order."""
    return [(arguments(c), data) for s in trace.get("steps", []) for c in s.get("tool_calls", [])
            if c.get("name") == name for data in [observed(c)] if data]


class Cards:
    """Builds the cards for a trace. tools: react.Tools (the snapshot's path and resolvers); earnings: whether cards show
    career earnings."""

    def __init__(self, tools, earnings=True, legends=None):
        self.tools, self.earnings, self.legends = tools, earnings, legends or Legends()

    def call(self, name, args):
        out = TEMPLATES[name].call(self.tools, args)
        return None if "error" in out else out

    def query(self, sql, params):
        db = connect(self.tools.path, 30)
        try:
            return db.execute(sql, params).fetchall()
        finally:
            db.close()

    # The figures

    def lifetime(self, player_id):
        """One player's lifetime figures, from player_results with no top, year or event."""
        out = self.call("player_results", {"player_id": player_id})
        if out is None:
            return None
        summary = table_with(out, "mode", "first", "second", "third", "top8")
        if summary is None:
            return None
        columns = summary["columns"]
        modes = {}
        for row in summary.get("rows") or []:
            cells = dict(zip(columns, row))
            modes[cells["mode"]] = {k: cells.get(k) for k in COUNTS}
        if "top32" not in columns and modes:  # the app's own count (TOP32), the combined row their sum
            top32 = dict(self.query(TOP32, (player_id,)))
            for mode, m in modes.items():
                m["top32"] = sum(top32.get(x) or 0 for x in ("1v1", "2v2")) if mode == "1v1 and 2v2" else top32.get(mode) or 0
        ends = table_with(out, "which", "date")
        dates = sorted(d for d in (dict(zip(ends["columns"], r)).get("date") for r in ends.get("rows") or []) if d) if ends else []
        player = out.get("player") or {}
        card = {"player_id": player.get("player_id", player_id), "name": player.get("name"), "modes": modes,
                "top32": bool(modes), "crew": any("crew battle" in n for n in out.get("notes", [])),
                "first": dates[0] if dates else None, "latest": dates[-1] if dates else None,
                "legend": self.legends.of(player.get("player_id", player_id))}
        if self.earnings:
            found = self.query(EARNINGS, (card["player_id"],))
            card["earnings"] = ({"amount": found[0][0], "source": found[0][1], "as_of": found[0][2]} if found
                                else {"amount": None, "source": None, "as_of": None})
        return card

    def scope(self, players):
        return SCOPE + (" " + CREW if any(p["crew"] for p in players) else "")

    def team_scope(self, players):
        return TEAM_SCOPE + (" " + CREW if any(p["crew"] for p in players) else "")

    def head_to_head(self, player_id, opponent_id):
        out = self.call("head_to_head", {"player_id": player_id, "opponent_id": opponent_id})
        players = [self.lifetime(player_id), self.lifetime(opponent_id)]
        if out is None or None in players:
            return []
        record = table_with(out, "wins", "losses", "games_won")
        r = dict(zip(record["columns"], record["rows"][0])) if record and record.get("rows") else {}
        a, b = players
        ones = {"wins": r.get("wins"), "losses": r.get("losses"), "sets": r.get("sets"),
                "games_won": r.get("games_won"), "games_lost": r.get("games_lost"), "unscored": r.get("unscored_sets") or 0}
        twos_rows = self.query(TWOS, (a["player_id"], b["player_id"]))
        twos = tally(twos_rows)
        card = {"kind": "head_to_head", "players": players, "scope": self.scope(players), "record": ones,
                "records": {"1v1": ones, "2v2": twos, "1v1 and 2v2": combined(ones, twos)},
                "record_scope": out.get("scope")}
        found = table_with(out, "winner_id", "winner_games", "loser_games")
        names = {a["player_id"]: a["name"], b["player_id"]: b["name"]}
        listed = found.get("rows") if found else []
        singles = None if listed is None else [
            {"date": c["date"], "event": c.get("event"), "mode": "1v1", "first_won": c["winner_id"] == a["player_id"],
             "winner": names.get(c["winner_id"], c.get("winner")),
             "loser": next(n for i, n in names.items() if i != c["winner_id"]) if c["winner_id"] in names else None,
             "winner_games": c["winner_games"], "loser_games": c["loser_games"]}
            for c in (dict(zip(found["columns"], row)) for row in listed)]
        doubles = [team_set(row, a["name"], b["name"]) for row in twos_rows]
        if not singles and not doubles and listed is not None:
            return [card]
        totals = {"1v1": (found.get("row_count") or len(listed or [])) if found else 0, "2v2": len(doubles)}
        sets = None if singles is None else sorted(singles + doubles, key=lambda s: s["date"] or "")  # stable sort
        return [card, {"kind": "sets", "title": f"Sets between {a['name']} and {b['name']}", "sets": sets,
                       "sides": [a["name"], b["name"]],
                       "total": totals["1v1"] + totals["2v2"], "totals": totals, "modes": True,
                       "scope": "Official sets between them, newest first: 1v1 sets with one player a side, and 2v2 sets"
                                " with the two on opposite teams. DQs, forfeits and ties left out."}]

    def event_sets(self, event):
        rows = self.query(EVENT_SETS, (event["event_id"],))
        sets = [{"date": r[0], "event": None, "winner": r[1], "loser": r[4],
                 "winner_games": r[7] if r[9] else None, "loser_games": r[8] if r[9] else None} for r in rows]
        return {"kind": "sets", "title": "Sets between top 8 players", "event": event["name"], "date": event["date"],
                "sets": sets, "total": len(sets),
                "scope": "The event's 1v1 sets in which both players placed top 8, by date as recorded. Not bracket"
                         " order: the data has no rounds."}

    def team(self, player_id, partner_id):
        """One partnership: each partner's lifetime figures, and their results together from team_results."""
        out = self.call("team_results", {"player_id": player_id, "partner_id": partner_id})
        players = [self.lifetime(player_id), self.lifetime(partner_id)]
        if out is None or None in players:
            return None
        found = table_with(out, "events", "wins", "medals", "top8s")
        row = dict(zip(found["columns"], found["rows"][0])) if found and found.get("rows") else {}
        ends = table_with(out, "which", "date")
        dates = sorted(d for d in (dict(zip(ends["columns"], r)).get("date") for r in ends.get("rows") or []) if d) if ends else []
        together = {k: row.get(k, 0 if k != "best" else None) for k in ("events", "wins", "medals", "top8s", "best")}
        together.update(first=dates[0] if dates else None, latest=dates[-1] if dates else None)
        return {"kind": "team", "players": players, "together": together, "mode": "2v2",
                "scope": self.team_scope(players) + " Together: their 2v2 results with each other at official events."}

    def teams(self, first, second, about=None):
        """Two teams (each a (player_id, partner_id) pair): the four players' lifetime figures and the teams' 2v2 sets
        against each other, from the first team's side; then those sets."""
        players = [self.lifetime(p) for p in (*first, *second)]
        if None in players:
            return []
        rows = self.query(TEAMS, (first[1], second[0], second[1], first[0]))
        names = [" & ".join(p["name"] for p in players[:2]), " & ".join(p["name"] for p in players[2:])]
        card = {"kind": "teams", "teams": [players[:2], players[2:]], "names": names, "record": tally(rows),
                "mode": "2v2", "scope": self.team_scope(players) + f" The record: official 2v2 sets with {names[0]} on"
                                        f" one side and {names[1]} on the other, from the first team's side."
                                        + (f" {about}" if about else "")}
        if not rows:
            return [card]
        sets = [{"date": r[0], "event": set_event(r[1], r[2]), "mode": "2v2", "first_won": bool(r[3]),
                 "winner": names[0] if r[3] else names[1], "loser": names[1] if r[3] else names[0],
                 "winner_games": (r[4] if r[3] else r[5]) if r[6] else None,
                 "loser_games": (r[5] if r[3] else r[4]) if r[6] else None} for r in rows]
        return [card, {"kind": "sets", "title": f"Sets between {names[0]} and {names[1]}", "sets": sets,
                       "sides": names, "total": len(sets), "mode": "2v2",
                       "scope": "Official 2v2 sets between the two teams, newest first. DQs, forfeits and ties left out."}]

    def named_teams(self, question):
        """Two teams from a question naming four players, each confidently (mentions.named): the pairing with the most
        events together, each pair partnered at least once, the question's own order first among equals. None else."""
        if not question or self.tools is None or not TEAM_WORDS.search(question):
            return None
        found = mentions.named(question, self.tools.resolver, self.tools.events.words)
        ids = list(dict.fromkeys(out["candidates"][0]["player_id"] for _, out in found
                                 if out.get("status") == "confident" and out.get("candidates")))
        if len(ids) != 4:
            return None
        a, b, c, d = ids
        best = None
        for first, second in (((a, b), (c, d)), ((a, c), (b, d)), ((a, d), (b, c))):
            counts = [self.query(TOGETHER, pair)[0][0] for pair in (first, second)]
            if min(counts) and (best is None or sum(counts) > best[0]):
                best = (sum(counts), first, second)
        return best and best[1:]

    def final(self, event):
        """One held 2v2 event's winners against its runners-up, when exactly one team placed at each."""
        rows = self.query(FINALISTS, (event["event_id"],))
        first = [(r[0], r[1]) for r in rows if r[2] == 1]
        second = [(r[0], r[1]) for r in rows if r[2] == 2]
        if len(first) != 1 or len(second) != 1:
            return []
        return self.teams(first[0], second[0], about=f"Left: {event.get('name') or 'the event'}'s winners; right: its"
                                                       " runners-up. The record counts every official set between them.")

    # Choosing the cards

    def build(self, trace):
        """The cards for a turn (the module docstring), at most MOST."""
        if trace.get("outcome") != "answered":
            return []
        for args, out in calls(trace, "team_head_to_head"):
            four = [(out.get(k) or {}).get("player_id") for k in ("player", "partner", "opponent", "opponent_partner")]
            if None not in four and not any(args.get(k) for k in NARROWING):
                found = self.teams(tuple(four[:2]), tuple(four[2:]))
                if found:
                    return found[:MOST]
        named = self.named_teams(trace.get("question"))
        if named:
            found = self.teams(*named)
            if found:
                return found[:MOST]
        meetings = calls(trace, "head_to_head")
        if meetings:
            _, out = meetings[-1]
            ids = [(out.get("player") or {}).get("player_id"), (out.get("opponent") or {}).get("player_id")]
            if None not in ids:
                return self.head_to_head(*ids)[:MOST]
        cards = []
        pairs = []  # the partnerships the turn looked up, each once, in order
        for args, out in calls(trace, "team_results"):
            pair = ((out.get("player") or {}).get("player_id"), (out.get("partner") or {}).get("player_id"))
            if None not in pair and not any(args.get(k) for k in NARROWING) and set(pair) not in [set(q) for q in pairs]:
                pairs.append(pair)
        if len(pairs) >= 2 and not set(pairs[0]) & set(pairs[1]):
            found = self.teams(pairs[0], pairs[1])
            if found:
                return found[:MOST]
        if pairs:
            one = self.team(*pairs[0])
            if one:
                cards.append(one)
        players = list(dict.fromkeys(
            (out.get("player") or {}).get("player_id") for args, out in calls(trace, "player_results")
            if not args.get("year") and not args.get("event")))
        players = [p for p in players if p is not None]
        if len(players) >= 2:
            two = [self.lifetime(p) for p in players[:2]]
            if None not in two:
                cards.append({"kind": "comparison", "players": two, "scope": self.scope(two)})
        elif players:
            one = self.lifetime(players[0])
            if one:
                cards.append({"kind": "lifetime", "player": one, "scope": self.scope([one])})
        for _, out in calls(trace, "event_results"):
            events = table_with(out, "event_id", "mode", "status")
            rows = [dict(zip(events["columns"], r)) for r in (events.get("rows") or [])] if events else []
            if len(rows) == 1 and not rows[0]["status"]:
                about = {"event_id": rows[0]["event_id"], "name": rows[0].get("event"), "date": rows[0].get("date")}
                if rows[0]["mode"] == "1v1":
                    cards.append(self.event_sets(about))
                elif rows[0]["mode"] == "2v2" and not cards:
                    cards.extend(self.final(about))
                break
        return cards[:MOST]


def tally(rows):
    """A record from TWOS rows, from the first player's side, in the 1v1 record's shape."""
    scored = [r for r in rows if r[6]]
    wins = sum(1 for r in rows if r[3])
    return {"wins": wins, "losses": len(rows) - wins, "sets": len(rows),
            "games_won": sum(r[4] for r in scored) if scored else None,
            "games_lost": sum(r[5] for r in scored) if scored else None, "unscored": len(rows) - len(scored)}


def combined(*records):
    """Records summed; games summed over the records that have them, None when none does."""
    out = {k: sum(r.get(k) or 0 for r in records) for k in ("wins", "losses", "sets", "unscored")}
    for k in ("games_won", "games_lost"):
        known = [r[k] for r in records if r.get(k) is not None]
        out[k] = sum(known) if known else None
    return out


def team_set(row, first, second):
    """A TWOS row as a set of the list: each side named as its two players."""
    date, tournament, event, won, games_won, games_lost, scored, partner, opposing = row
    mine = f"{first} & {partner}" if partner else first
    theirs = f"{second} & {opposing}" if opposing else second
    return {"date": date, "event": set_event(tournament, event), "mode": "2v2", "first_won": bool(won),
            "winner": mine if won else theirs, "loser": theirs if won else mine,
            "winner_games": (games_won if won else games_lost) if scored else None,
            "loser_games": (games_lost if won else games_won) if scored else None}


# What the cards showed, for the agent (react.Conversation.shown): live, the user asked about a card's "12 medals in
# 2v2", which were Phazon's 2v2 GOLD figure, and the model, which never sees the cards, invented where it came from
# (docs/web-app-testing-notes.md, finding 9). One clause per player and mode, separated by ";", so each record's numbers
# share a clause, as the number check reads them. The card's own labels are named with what they count.

LISTED = 12  # a sets card's sets written out one by one, up to this many; beyond it only their count


def summary(cards):
    """One line saying what the cards showed, in the words the user saw on them, or "" for no cards."""
    parts = [said for said in (card_summary(c) for c in cards or []) if said]
    if not parts:
        return ""
    return ("Stat cards, at official events; on them MEDALS are GOLD (1st places), SILVER (2nd) and BRONZE (3rd). "
            + " ".join(parts))


def card_summary(card):
    kind = card.get("kind")
    if kind == "lifetime":
        return f"A lifetime card of {player_summary(card['player'])}."
    if kind == "comparison":
        return "A comparison card of " + "; and of ".join(player_summary(p) for p in card["players"]) + "."
    if kind == "head_to_head":
        a, b = card["players"]
        r = card.get("record") or {}
        record = (f"their 1v1 record, {a['name']} {r.get('wins')}-{r.get('losses')} against {b['name']} in"
                  f" {r.get('sets')} sets, games {r.get('games_won')}-{r.get('games_lost')}"
                  if r.get("sets") else f"no 1v1 sets between {a['name']} and {b['name']}")
        t = (card.get("records") or {}).get("2v2") or {}
        record += (f"; their 2v2 record, {a['name']}'s teams {t['wins']}-{t['losses']} against {b['name']}'s teams in"
                   f" {t['sets']} sets" if t.get("sets") else
                   f"; no 2v2 sets with {a['name']} and {b['name']} on opposite teams")
        return (f"A head-to-head card: {record}; with the lifetime figures of {player_summary(a)}; and of"
                f" {player_summary(b)}.")
    if kind == "teams":
        r, (one, two) = card["record"], card["names"]
        record = (f"their 2v2 record, {one} {r['wins']}-{r['losses']} against {two} in {r['sets']} sets"
                  if r.get("sets") else f"no 2v2 sets between {one} and {two}")
        figures = "; and of ".join(player_summary(p) for team in card["teams"] for p in team)
        return f"A team card: {record}; with the lifetime figures of {figures}."
    if kind == "team":
        a, b = card["players"]
        t = card["together"]
        together = (f"{a['name']} and {b['name']} together in 2v2: {t['events']} events, {t['wins']} wins,"
                    f" {t['medals']} medals, {t['top8s']} top 8s, best placement {t['best']}")
        return f"A partnership card: {together}; with the lifetime figures of {player_summary(a)}; and of {player_summary(b)}."
    if kind == "sets":
        sets, total = card.get("sets"), card.get("total")
        where = f" at {card['event']}" if card.get("event") else ""
        if not sets or len(sets) > LISTED:
            return f"A list, {card['title']}{where}, of {total if total is not None else 'its'} sets."
        listed = "; ".join(set_summary(s) for s in sets)
        return f"A list, {card['title']}{where}, oldest first: {listed}."
    return ""


def player_summary(p):
    figures = []
    for mode, said in (("1v1", "in 1v1 only"), ("2v2", "in 2v2 only"), ("1v1 and 2v2", "in both modes together")):
        m = (p.get("modes") or {}).get(mode)  # live, "in 1v1 and 2v2 ... GOLD 12" was read as a 1v1 figure
        if m and m.get("results"):
            figures.append(f"{p['name']} {said} {m['results']} results, GOLD {m['first']}, SILVER {m['second']},"
                           f" BRONZE {m['third']}, TOP 8 {m['top8']}"
                           + (f", TOP 32 {m['top32']}" if m.get("top32") is not None else ""))
    said = "; ".join(figures) or f"{p['name']} with no official results"
    if p.get("first"):
        said += f"; {p['name']}'s first result {p['first']}, latest {p['latest']}"
    earnings = p.get("earnings")
    if earnings is not None:
        said += (f"; {p['name']}'s career earnings ${earnings['amount']:,.0f} ({earnings['source']}, as of"
                 f" {earnings['as_of']})" if earnings.get("amount") is not None
                 else f"; {p['name']}'s career earnings not recorded")
    return said


def set_summary(s):
    score = (f" {s['winner_games']}-{s['loser_games']}" if s.get("winner_games") is not None else " (no score recorded)")
    at = f" at {s['event']}" if s.get("event") else ""
    return f"{s['date']}{at}, {s['winner']} beat {s['loser']}{score}"
