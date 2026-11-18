"""Stat cards for an answer (docs/stat-cards-proposal.md, design B): built after the turn, from the app's own calls.

The turn's successful template calls say which players and event the answer is about. The cards' figures then come
from calling the template functions again with no top, year or event, so the model's arguments can't change them, and
from two queries of the app's own: career earnings, and an event's sets between its top 8 players. Nothing is read from
the model's text.

Cards, at most two per answer:
- head_to_head: two players' lifetime figures mirrored, and their 1v1 record; followed by sets, their 1v1 sets;
- comparison: two players' lifetime figures, for a turn that called player_results for two players;
- lifetime: one player's, for a player_results call without year or event;
- sets for an event: the 1v1 sets between its top 8 players, for one held 1v1 event.

A missing value is None ("not recorded" on the page), never 0. With earnings off, cards have no "earnings" key and the
earnings query isn't run.
"""

import csv
import json
from pathlib import Path

from templates import TEMPLATES
from tools import connect

MODES = ("1v1 and 2v2", "1v1", "2v2")
COUNTS = ("results", "first", "second", "third", "top8", "top32")
SCOPE = "All official events, regional championships included. 1v1 and 2v2 counted together unless you pick one."
CREW = "Crew battles count as 1v1."
EARNINGS = "SELECT earnings_usd, source, as_of FROM v_career_earnings WHERE player_id = ?"
EVENT_SETS = ("SELECT start_date, winner_name, winner_id, winner_placement, loser_name, loser_id, loser_placement,"
              " winner_games, loser_games, is_scored FROM v_sets_1v1 WHERE event_id = ? AND winner_placement <= 8"
              " AND loser_placement <= 8 ORDER BY start_date, start_time, match_id")
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
            modes[cells["mode"]] = {k: cells.get(k) for k in COUNTS}  # top32 None until the summary has the column
        ends = table_with(out, "which", "date")
        dates = sorted(d for d in (dict(zip(ends["columns"], r)).get("date") for r in ends.get("rows") or []) if d) if ends else []
        player = out.get("player") or {}
        card = {"player_id": player.get("player_id", player_id), "name": player.get("name"), "modes": modes,
                "top32": "top32" in columns, "crew": any("crew battle" in n for n in out.get("notes", [])),
                "first": dates[0] if dates else None, "latest": dates[-1] if dates else None,
                "legend": self.legends.of(player.get("player_id", player_id))}
        if self.earnings:
            found = self.query(EARNINGS, (card["player_id"],))
            card["earnings"] = ({"amount": found[0][0], "source": found[0][1], "as_of": found[0][2]} if found
                                else {"amount": None, "source": None, "as_of": None})
        return card

    def scope(self, players):
        return SCOPE + (" " + CREW if any(p["crew"] for p in players) else "")

    def head_to_head(self, player_id, opponent_id):
        out = self.call("head_to_head", {"player_id": player_id, "opponent_id": opponent_id})
        players = [self.lifetime(player_id), self.lifetime(opponent_id)]
        if out is None or None in players:
            return []
        record = table_with(out, "wins", "losses", "games_won")
        r = dict(zip(record["columns"], record["rows"][0])) if record and record.get("rows") else {}
        card = {"kind": "head_to_head", "players": players, "scope": self.scope(players),
                "record": {"wins": r.get("wins"), "losses": r.get("losses"), "sets": r.get("sets"),
                           "games_won": r.get("games_won"), "games_lost": r.get("games_lost"),
                           "unscored": r.get("unscored_sets") or 0},
                "record_scope": out.get("scope")}
        found = table_with(out, "winner_id", "winner_games", "loser_games")
        if not found:
            return [card]
        a, b = players
        names = {a["player_id"]: a["name"], b["player_id"]: b["name"]}
        listed = found.get("rows")
        sets = None if listed is None else [
            {"date": c["date"], "event": c.get("event"), "winner": names.get(c["winner_id"], c.get("winner")),
             "loser": next(n for i, n in names.items() if i != c["winner_id"]) if c["winner_id"] in names else None,
             "winner_games": c["winner_games"], "loser_games": c["loser_games"]}
            for c in (dict(zip(found["columns"], row)) for row in listed)]
        return [card, {"kind": "sets", "title": f"Sets between {a['name']} and {b['name']}", "sets": sets,
                       "total": found.get("row_count"),
                       "scope": "Official 1v1 sets, one player a side, oldest first. DQs, forfeits and ties left out."}]

    def event_sets(self, event):
        rows = self.query(EVENT_SETS, (event["event_id"],))
        sets = [{"date": r[0], "event": None, "winner": r[1], "loser": r[4],
                 "winner_games": r[7] if r[9] else None, "loser_games": r[8] if r[9] else None} for r in rows]
        return {"kind": "sets", "title": "Sets between top 8 players", "event": event["name"], "date": event["date"],
                "sets": sets, "total": len(sets),
                "scope": "The event's 1v1 sets in which both players placed top 8, by date as recorded. Not bracket"
                         " order: the data has no rounds."}

    # Choosing the cards

    def build(self, trace):
        """The cards for a turn (the module docstring), at most MOST."""
        if trace.get("outcome") != "answered":
            return []
        meetings = calls(trace, "head_to_head")
        if meetings:
            _, out = meetings[-1]
            ids = [(out.get("player") or {}).get("player_id"), (out.get("opponent") or {}).get("player_id")]
            if None not in ids:
                return self.head_to_head(*ids)[:MOST]
        cards = []
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
            if len(rows) == 1 and rows[0]["mode"] == "1v1" and not rows[0]["status"]:
                cards.append(self.event_sets({"event_id": rows[0]["event_id"], "name": rows[0].get("event"),
                                              "date": rows[0].get("date")}))
                break
        return cards[:MOST]
