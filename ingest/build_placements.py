"""Build step 5 (docs/build-plan.md §1): `placements` and `teams`.

- Placements come from `standings`, one row per player per event.
  - A player entered twice keeps the entrant that wasn't DQ'd first, then the better placement, then the
    lower entrant ID, so a tie is settled the same way every build.
  - The placement keeps that entrant's team.
- Teams are the 2v2 pairs: each entrant with exactly two players in an event whose effective mode is 2v2
  (the mode override counts).
  - Team IDs follow the pairs' order, so the same pairs get the same IDs in every build.
  - A team is two player records. The views map merged records to their canonical player.
- The Pro Series finals, which no platform has, take their placements from the Stats API (stage 3b):
  - every single-player GetPlayerPlacements page in the cache that lists a final, the newest response
    winning;
  - a 2v2 pair's pages (stage 4) place the pair, not one player, so they're left out;
  - every member of a team shares its place. They get no team ID, which is only for 2v2 pairs.
- Stats API placements for entrants missing from an event's standings (stage 3c) come with the matches
  step, which finds those entrants.
"""

import collections

ENTRANT_PAIRS = """
CREATE TEMP TABLE entrant_pairs AS  -- the two players of each two-player entrant in a 2v2 event
SELECT s.event_id, s.entrant_key, MIN(s.player_id) AS player1_id, MAX(s.player_id) AS player2_id
FROM standings s
JOIN events e USING (event_id)
WHERE COALESCE(e.mode_override, CASE WHEN e.is_twos = 1 THEN '2v2' ELSE '1v1' END) = '2v2'
GROUP BY s.event_id, s.entrant_key
HAVING COUNT(*) = 2 AND COUNT(DISTINCT s.player_id) = 2"""

PLACEMENTS = """
INSERT INTO placements (event_id, player_id, placement, team_id, source, fetched_at)
SELECT k.event_id, k.player_id, k.placement, t.team_id, k.source, k.fetched_at
FROM (SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.event_id, s.player_id
                                     ORDER BY COALESCE(s.is_disqualified, 0), s.placement, s.entrant_key) AS nth
      FROM standings s
      WHERE s.player_id IS NOT NULL) k
LEFT JOIN entrant_pairs p ON p.event_id = k.event_id AND p.entrant_key = k.entrant_key
LEFT JOIN teams t ON t.player1_id = p.player1_id AND t.player2_id = p.player2_id
WHERE k.nth = 1"""


def stats_api_placements(reader, events):
    """{(event ID, player ID): (placement, fetched_at)} at the given events, from single-player pages."""
    found = {}
    for response in reader.responses("/player/placement"):
        ids = response.params.get("playerIds", "")
        if not ids or "," in ids:
            continue
        for row in response.body.get("playerPlacements") or []:
            if row["tournament"]["id"] in events:
                found[(row["tournament"]["id"], int(ids))] = (row["placement"], response.fetched_at)
    return found


def step(build):
    db = build.db
    db.execute("DROP TABLE IF EXISTS temp.entrant_pairs")
    db.execute(ENTRANT_PAIRS)
    db.execute("CREATE INDEX temp.entrant_pairs_key ON entrant_pairs (event_id, entrant_key)")
    db.execute("INSERT INTO teams (player1_id, player2_id) SELECT DISTINCT player1_id, player2_id FROM entrant_pairs"
               " ORDER BY player1_id, player2_id")
    db.execute(PLACEMENTS)
    db.execute("DROP TABLE temp.entrant_pairs")

    finals = {eid for (eid,) in db.execute("SELECT event_id FROM event_sources WHERE platform = 'stats_api'")}
    found = stats_api_placements(build.reader, finals)
    rows = [(eid, pid, place, None, "stats_api", at) for (eid, pid), (place, at) in sorted(found.items())
            if build.players.use(pid)]
    db.executemany("INSERT INTO placements (event_id, player_id, placement, team_id, source, fetched_at)"
                   " VALUES (?, ?, ?, ?, ?, ?)", rows)
    build.players.flush(db)

    if len(rows) < len(found):
        build.log(f"  {len(found) - len(rows)} Pro Series placement(s) left out: no Stats API record for the player")
    by_source = dict(db.execute("SELECT source, COUNT(*) FROM placements GROUP BY source"))
    folded = db.execute("SELECT COUNT(*) FROM standings WHERE player_id IS NOT NULL").fetchone()[0] \
        - by_source.get("startgg", 0) - by_source.get("challengermode", 0)
    teams = db.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
    twos, teamless = db.execute(
        "SELECT COUNT(*), SUM(p.team_id IS NULL) FROM placements p JOIN events e USING (event_id)"
        " WHERE COALESCE(e.mode_override, CASE WHEN e.is_twos = 1 THEN '2v2' ELSE '1v1' END) = '2v2'").fetchone()
    build.info["placements"] = str(sum(by_source.values()))
    build.log(f"  {sum(by_source.values())} placements (start.gg {by_source.get('startgg', 0)}, Challengermode"
              f" {by_source.get('challengermode', 0)}, Stats API {by_source.get('stats_api', 0)});"
              f" {folded} more standings rows of players entered more than once folded in; {teams} 2v2 teams,"
              f" {twos or 0} 2v2 placements, {teamless or 0} without a team")
    places = collections.defaultdict(collections.Counter)
    for eid, _, place, *_ in rows:
        places[eid][place] += 1
    for eid in sorted(places):
        build.log(f"  {eid}: {sum(places[eid].values())} placements, players per place"
                  f" {', '.join(f'{p}: {n}' for p, n in sorted(places[eid].items()))}")
