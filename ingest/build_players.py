"""Build steps 3 and 4 (docs/build-plan.md §1): `players`, and `standings` for both platforms.

Players
- Every Stats API record in the cache: ListPlayers responses (profiles, lookups and Pro Series
  candidates), teammate records and PR rows. For each field, the newest response that has a value wins,
  so a known platform ID is never overwritten with null. A lookup answers an ID it doesn't know with an
  all-null record, which is skipped.
- A start.gg or Challengermode player maps to the Stats API record that claims their platform ID.
- One with no record gets a stable negative ID: -player ID on start.gg, -(2^40 + the first 40 bits of the
  user UUID) on Challengermode. They're named after their newest standings entry, and every rebuild
  resolves them afresh, so a record found later takes over. Two players with one negative ID stop the
  build.
- A platform ID no lookup ever asked about is counted for the check that every platform player was
  looked up. Until a lookup finds a record, it's treated as platform-only.
- A full build writes every Stats API record, a dev build only those its events refer to.
- Platform-only players get a row only once they've placed or played. The standings step registers
  everyone placed; the matches step will add, through the same registry, those who only played (the
  three events whose standings miss entrants).

Standings
- One row per participant of each placed entrant: start.gg's standings, and Challengermode lineups with a
  placement (bestPlacement). A lineup without one never played and isn't an entrant.
- Responses are applied oldest first, so the newest wins.
- The step also fills event_sources: each platform's event ID, Challengermode's tournament state, and
  the platform's own count of entrants.
"""

from collections import namedtuple

import sources
from problems import BuildStop

FIELDS = (("name", "name"), ("sgg", "sggPlayerId"), ("cm", "cmPlayerId"), ("brawlhalla", "brawlhallaId"),
          ("twitter", "twitter"), ("twitch", "twitch"))
LOOKUPS = {"sggIds": "startgg", "cmIds": "challengermode"}  # ListPlayers parameters that look up platform IDs

Entry = namedtuple("Entry", "event_id entrant_key platform platform_player entrant_name gamer_tag prefix"
                            " placement worst_placement initial_seed is_disqualified fetched_at")


def negative_id(platform, platform_id):
    """A platform-only player's stable ID (schema proposal §1)."""
    if platform == "startgg":
        return -int(platform_id)
    return -(2 ** 40 + int(platform_id.replace("-", "")[:10], 16))


class Players:
    """Every player the build knows about: Stats API records, and the platform-only players met so far."""

    def __init__(self):
        self.records = {}  # Stats API ID -> {field: (fetched_at, value)}
        self.names = {}  # Stats API ID -> {every name a response gave: its newest fetch time}, for former names
        self.claims = {"startgg": {}, "challengermode": {}}  # platform ID -> Stats API ID
        self.asked = {"startgg": set(), "challengermode": set()}  # platform IDs a lookup asked about
        self.platform_only = {}  # negative ID -> {platform, platform_id, name, seen}
        self.referenced = set()  # player IDs the build's rows point at
        self.unasked = set()  # (platform, platform ID) no lookup asked about
        self.written = {}  # player ID -> the row last written
        self._cm_by_negative_id = None

    def observe(self, record, fetched_at):
        pid = record.get("playerId")
        if pid is None:
            return
        fields = self.records.setdefault(pid, {})
        if record.get("name"):
            names = self.names.setdefault(pid, {})
            names[record["name"]] = max(fetched_at, names.get(record["name"], ""))
        for key, source in FIELDS:
            value = record.get(source)
            if value in (None, ""):
                continue
            if key == "cm":
                value = value.lower()
            if key not in fields or fetched_at >= fields[key][0]:
                fields[key] = (fetched_at, value)

    def index(self):
        """Map platform IDs to the records claiming them. Returns (platform, ID, records) claimed twice; the
        record whose claim is newest keeps it."""
        conflicts, when = [], {}
        for pid in sorted(self.records):
            for key, platform in (("sgg", "startgg"), ("cm", "challengermode")):
                if key not in self.records[pid]:
                    continue
                at, value = self.records[pid][key]
                platform_id, other = str(value), self.claims[platform].get(str(value))
                if other is not None:
                    conflicts.append((platform, platform_id, (other, pid)))
                    if at < when[(platform, platform_id)]:
                        continue
                self.claims[platform][platform_id] = pid
                when[(platform, platform_id)] = at
        return conflicts

    def resolve(self, platform, platform_id, name, seen):
        """The player ID of a platform player. `seen` (event start, fetch time) orders their names, so a
        platform-only player is named after their newest entry."""
        pid = self.claims[platform].get(platform_id)
        if pid is not None:
            self.referenced.add(pid)
            return pid
        if platform_id not in self.asked[platform]:
            self.unasked.add((platform, platform_id))
        nid = negative_id(platform, platform_id)
        known = self.platform_only.get(nid)
        if known and known["platform_id"] != platform_id:
            raise BuildStop([f"{platform} players {known['platform_id']} and {platform_id} would both get"
                             f" player ID {nid}"])
        if known is None or (name and seen > known["seen"]):
            self.platform_only[nid] = {"platform": platform, "platform_id": platform_id,
                                       "name": name or (known or {}).get("name") or platform_id, "seen": seen}
        self.referenced.add(nid)
        return nid

    def current_id(self, pid):
        """The player a curated row's ID names today, or None if the cache has no such player. A negative ID is
        resolved through the platform ID it encodes, so it keeps working after a lookup finds the player a
        Stats API record."""
        if pid > 0:
            return pid if pid in self.records else None
        if -pid < 2 ** 40:
            platform, platform_id = "startgg", str(-pid)
        else:
            if self._cm_by_negative_id is None:
                users = set(self.claims["challengermode"]) | {p["platform_id"] for p in self.platform_only.values()
                                                              if p["platform"] == "challengermode"}
                self._cm_by_negative_id = {negative_id("challengermode", u): u for u in users}
            platform, platform_id = "challengermode", self._cm_by_negative_id.get(pid)
        record = self.claims[platform].get(platform_id)
        if record is not None:
            return record
        return pid if pid in self.platform_only else None

    def use(self, pid):
        """Mark a Stats API record as one the build's rows point at. False if the cache has no such record."""
        if pid in self.records:
            self.referenced.add(pid)
            return True
        return False

    def row(self, pid):
        if pid in self.records:
            fields = self.records[pid]
            value = lambda key: fields[key][1] if key in fields else None  # noqa: E731
            sgg = value("sgg")
            return (pid, value("name") or str(pid), int(sgg) if sgg is not None else None, value("cm"),
                    value("brawlhalla"), None, value("twitter"), value("twitch"), "stats_api",
                    max(at for at, _ in fields.values()), pid)
        p = self.platform_only[pid]
        return (pid, p["name"], int(p["platform_id"]) if p["platform"] == "startgg" else None,
                p["platform_id"] if p["platform"] == "challengermode" else None, None, None, None, None,
                p["platform"], p["seen"][1], pid)

    def flush(self, db, everyone=False):
        """Write the players met since the last flush, or whose row changed. `everyone` adds every Stats API
        record, met or not. Returns how many rows were written.

        A Stats API record's row is final once written. Only a platform-only player's can change, when a
        newer entry renames them."""
        ids = (set(self.records) if everyone else self.referenced & self.records.keys()) - self.written.keys()
        ids |= self.referenced & self.platform_only.keys()
        changed = [row for row in map(self.row, sorted(ids)) if self.written.get(row[0]) != row]
        db.executemany("INSERT OR REPLACE INTO players (player_id, name, sgg_player_id, cm_player_id, brawlhalla_id,"
                       " country, twitter, twitch, source, updated_at, canonical_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       changed)  # canonical_id is the player's own ID until the merges step
        self.written.update((row[0], row) for row in changed)
        return len(changed)


def players_step(build):
    """Step 3: every Stats API record, and which platform IDs the lookups asked about."""
    players, responses = Players(), 0
    for response in build.reader.responses("/players"):
        responses += 1
        for param, platform in LOOKUPS.items():
            if param in response.params:
                ids = response.params[param].split(",")
                players.asked[platform].update(i.lower() if platform == "challengermode" else i for i in ids)
        for record in response.body.get("players") or []:
            if record:
                players.observe(record, response.fetched_at)
    for response in build.reader.responses("/player/teammate"):
        for row in response.body.get("playerTeammates") or []:
            if row.get("player"):
                players.observe(row["player"], response.fetched_at)
    for response in build.reader.responses("/pr"):
        for row in response.body.get("prPlayers") or []:
            players.observe({"playerId": row.get("playerId"), "name": row.get("playerName")}, response.fetched_at)
    for platform, platform_id, ids in players.index():
        build.log(f"  {platform} player {platform_id} is claimed by Stats API records {ids[0]} and {ids[1]}")
    build.players = players
    written = players.flush(build.db, everyone=build.events is None)
    build.info["stats_api_records"] = str(len(players.records))
    build.log(f"  {len(players.records)} Stats API records from {responses} ListPlayers responses, teammates and PR"
              f" rows ({written} written); lookups asked about {len(players.asked['startgg'])} start.gg and"
              f" {len(players.asked['challengermode'])} Challengermode players")


def platform_standings(reader, events):
    """(entries, totals): every participant of every placed entrant of the chosen events, oldest response
    first, and per event (event ID, platform event ID, state, entrants reported, fetched_at)."""
    entries, totals = [], []
    for response in reader.responses("startgg/Standings", sources.STANDINGS):
        slug = response.params["slug"]
        if slug not in events:
            continue
        event = response.body["data"].get("event")
        standings = (event or {}).get("standings") or {}
        if response.params.get("page") == "1":
            totals.append((slug, str(event["id"]) if event else None, None if event else "not found",
                           (standings.get("pageInfo") or {}).get("total"), response.fetched_at))
        for node in standings.get("nodes") or []:
            entrant = node.get("entrant")
            if not entrant or node.get("placement") is None:
                continue
            for part in entrant.get("participants") or []:
                player = (part.get("player") or {}).get("id")
                entries.append(Entry(slug, str(entrant["id"]), "startgg",
                                     str(player) if player is not None else f"participant:{part['id']}",
                                     entrant.get("name"), part.get("gamerTag"), part.get("prefix") or None,
                                     node["placement"], None, entrant.get("initialSeedNum"),
                                     int(bool(entrant.get("isDisqualified"))), response.fetched_at))
    for response in reader.responses("challengermode/Roster", sources.ROSTER):
        event_id = response.params["id"]
        tournament = response.body["data"].get("tournament")
        if event_id not in events:
            continue
        roster = ((tournament or {}).get("attendance") or {}).get("roster") or {}
        totals.append((event_id, tournament["id"] if tournament else None,
                       tournament.get("state") if tournament else "not found", roster.get("lineupCount"),
                       response.fetched_at))
        for lineup in roster.get("lineups") or []:
            placement = (lineup or {}).get("placement") or {}
            if placement.get("bestPlacement") is None:  # never played, so not an entrant
                continue
            for member in lineup.get("members") or []:
                user = member.get("user") or {}
                if user.get("id"):
                    entries.append(Entry(event_id, lineup["id"], "challengermode", user["id"].lower(),
                                         lineup.get("name"), user.get("username"), None, placement["bestPlacement"],
                                         placement.get("worstPlacement"), lineup.get("seed"),
                                         int(bool(lineup.get("disqualified"))), response.fetched_at))
    return entries, totals


def standings_step(build):
    """Step 4: `standings`, registering each placed platform player, and event_sources' platform figures."""
    players, starts = build.players, dict(build.db.execute("SELECT event_id, start_time FROM events"))
    entries, totals = platform_standings(build.reader, starts)
    rows = []
    for e in entries:
        pid = None
        if not e.platform_player.startswith("participant:"):
            pid = players.resolve(e.platform, e.platform_player, e.gamer_tag, (starts[e.event_id], e.fetched_at))
        rows.append((e.event_id, e.entrant_key, e.platform_player, pid, e.entrant_name, e.gamer_tag, e.prefix,
                     e.placement, e.worst_placement, e.initial_seed, e.is_disqualified, e.platform, e.fetched_at))
    build.db.executemany(  # oldest response first, so the newest row stays
        "INSERT OR REPLACE INTO standings (event_id, entrant_key, platform_player, player_id, entrant_name, gamer_tag,"
        " prefix, placement, worst_placement, initial_seed, is_disqualified, source, fetched_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    build.db.executemany(
        "UPDATE event_sources SET platform_event_id = ?, state = COALESCE(?, state), reported_entrants = ?,"
        " fetched_at = MAX(fetched_at, ?) WHERE event_id = ?",
        [(platform_id, state, entrants, fetched_at, event_id) for event_id, platform_id, state, entrants, fetched_at
         in totals])
    written = players.flush(build.db)
    placed = {(e.platform, e.platform_player) for e in entries}
    alone = sorted(p["platform"] for p in players.platform_only.values())
    build.info["unasked_platform_players"] = str(len(players.unasked))
    by_source = dict(build.db.execute("SELECT source, COUNT(*) FROM standings GROUP BY source"))
    build.log(f"  {len(rows)} standings rows (start.gg {by_source.get('startgg', 0)}, Challengermode"
              f" {by_source.get('challengermode', 0)}) at {len({e.event_id for e in entries})} events;"
              f" {len(placed)} platform players, {alone.count('startgg')} start.gg and"
              f" {alone.count('challengermode')} Challengermode of them without a Stats API record"
              f" ({written} player rows written); {len(players.unasked)} never looked up")
