"""The crawl (docs/schema-proposal.md §3), run one stage at a time.

    python ingest/crawl.py status                  progress of every stage
    python ingest/crawl.py events                  stage 0: every official event
    python ingest/crawl.py pr                      stage 1: the PR lists, which seed the players
    python ingest/crawl.py profiles                stage 2: profiles of known players
    python ingest/crawl.py lookups                 stage 2b: the Stats API record of every platform player
    python ingest/crawl.py histories [--sample N]  stage 3: official placements and teammates (held after its pilot)
    python ingest/crawl.py proseries               stage 3b: placements at the three Pro Series finals
    python ingest/crawl.py teams                   stage 4: official placements of each 2v2 pair (held after its pilot)
    python ingest/crawl.py standings               P1: start.gg standings of official start.gg events
    python ingest/crawl.py brackets                P4: start.gg sets, pools and last-phase games
    python ingest/crawl.py cm                      P5: Challengermode entrant lists and brackets

For a pilot, --event ID (repeatable) limits brackets, cm, lookups and proseries to the events
named, and --max-pools N fetches only the first N pools of each phase of an event that start.gg
can't list in one go (over 10,000 sets). Once the cause of a rejected task is fixed,
--retry-rejected puts the stage's rejected tasks back in the queue.

A stage first plans its tasks from what earlier stages found, then works through them.
Stages on different APIs (the Stats API, start.gg, Challengermode) can run at the same time.
Re-running the same command picks up where it stopped: finished tasks are skipped, and
requests already made come back from the cache. Ctrl+C stops after the current task. Each
run also writes a log to data/logs/crawl-<stage>.log.
"""

import argparse
import collections
import hashlib
import logging
import random
import sys
import time
from datetime import datetime, timezone

from cache import ROOT
from challengermode import Challengermode
from startgg import StartGG
from statsapi import ApiError, StatsApi
from tasks import MAX_ATTEMPTS, RunLock, StopFlag, TaskQueue, connect, now, pid_alive

PAGE_SIZE = 50  # the maximum for ListEvents, GetPlayerPlacements and GetPlayerTeammates
PR_PAGE_SIZE = 100
PROFILE_BATCH = 100  # player IDs per ListPlayers request
MODES = {1: "1v1", 2: "2v2"}
REGIONS = ["NA", "EU", "SA", "SEA", "MENA"]  # ListPr's regions with rows
FIRST_YEAR = 2017  # the API has nothing earlier
SAMPLE_SEED = 20261004  # fixes which players `histories --sample` picks
LOG_DIR = ROOT / "data" / "logs"

LOOKUP_PARAMS = {"startgg": ("sggIds", "sggPlayerId"), "challengermode": ("cmIds", "cmPlayerId")}
SERIES_TOP = 32  # Pro Series candidates: everyone placed this high at an event in the year before a final
SERIES_WINDOW = 365 * 86400
SETS_PER_PAGE = 50  # a set costs about 17 of start.gg's 1,000 complexity (measured: 690 for 40)
SETS_CAP = 10_000  # start.gg can't page a listing past its 10,000th entry
POOLS_PER_QUERY = 32  # an event with more pools than this gets them phase by phase, a page at a time
POOLS_PER_PAGE = 32  # a pool costs about 2 + its rounds (measured: 353 for 16 pools with 320 rounds)
GAMES_PER_PAGE = {1: 16, 2: 8}  # sets per page with their games; 2v2 games list twice the characters
GAMES_MAX_SEEDS = 16  # games are fetched for the last phase only, and only when it's this small
ROSTER_LIMIT = 2000  # Challengermode lineups per roster query, which has no paging

STANDINGS_TABLE = """
CREATE TABLE IF NOT EXISTS crawl_standings (         -- P1: every placed participant, by start.gg player ID
  event_id        TEXT NOT NULL,
  participant_id  INTEGER NOT NULL,
  entrant_id      INTEGER NOT NULL,
  sgg_player_id   INTEGER,
  placement       INTEGER,
  disqualified    INTEGER,
  PRIMARY KEY (event_id, entrant_id, participant_id) -- one player can be entered twice in an event
)"""

CRAWL_SCHEMA = """
-- What the crawl has learned so far, used to plan later stages. The builder reads the cache, not these.
CREATE TABLE IF NOT EXISTS crawl_events (       -- stage 0
  event_id    TEXT PRIMARY KEY,
  mode        INTEGER NOT NULL,
  host        TEXT,
  start_time  INTEGER
);
CREATE TABLE IF NOT EXISTS crawl_players (
  player_id        INTEGER PRIMARY KEY,
  found_by         TEXT NOT NULL,                -- 'pr' | 'teammate' | 'opponent'
  profile          INTEGER NOT NULL DEFAULT 0,   -- 0 to do, 1 planned, 2 fetched, 3 unknown to the API
  history_planned  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS crawl_pairs (        -- 2v2 partners, smaller ID first
  player1_id  INTEGER NOT NULL,
  player2_id  INTEGER NOT NULL,
  planned     INTEGER NOT NULL DEFAULT 0,
  events      INTEGER,                          -- official events together, once stage 4 has run
  PRIMARY KEY (player1_id, player2_id)
);
CREATE TABLE IF NOT EXISTS crawl_entries (      -- official events each player entered
  player_id  INTEGER NOT NULL,
  event_id   TEXT NOT NULL,
  mode       INTEGER NOT NULL,
  planned    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, event_id)
);
CREATE TABLE IF NOT EXISTS crawl_platform_events (   -- P1, P5: official events as each platform sees them
  event_id           TEXT PRIMARY KEY,
  platform           TEXT NOT NULL,             -- 'startgg' | 'challengermode'
  platform_event_id  TEXT,
  entrants           INTEGER,                   -- placed entrants (start.gg's standings total, Challengermode's lineupCount)
  registered         INTEGER,                   -- start.gg numEntrants, which counts registrations; lineups returned
  status             TEXT NOT NULL              -- 'ok' | 'missing' (start.gg has no such event)
);
""" + STANDINGS_TABLE + """;
CREATE TABLE IF NOT EXISTS crawl_cm_entrants (       -- P5: every lineup member at each official Challengermode event
  event_id    TEXT NOT NULL,
  lineup_id   TEXT NOT NULL,
  user_id     TEXT NOT NULL,                    -- the Stats API cmPlayerId
  placement   INTEGER,                          -- bestPlacement
  PRIMARY KEY (event_id, lineup_id, user_id)
);
CREATE TABLE IF NOT EXISTS crawl_brackets (          -- P4, P5: each event's bracket
  event_id    TEXT PRIMARY KEY,
  platform    TEXT NOT NULL,                    -- 'startgg' | 'challengermode'
  matches     INTEGER,                          -- start.gg's set total; for Challengermode, the matches returned
  by_pool     INTEGER NOT NULL DEFAULT 0        -- 1: over start.gg's 10,000-result cap, so fetched pool by pool
);
CREATE TABLE IF NOT EXISTS crawl_pools (             -- P4: start.gg pools (phase groups)
  pool_id   INTEGER PRIMARY KEY,
  event_id  TEXT NOT NULL,
  phase_id  INTEGER,
  sets      INTEGER,                            -- the pool's set total, for events fetched pool by pool
  planned   INTEGER NOT NULL DEFAULT 0          -- events fetched pool by pool: 1 once the pool's sets are planned
);
CREATE TABLE IF NOT EXISTS crawl_matches (           -- P4, P5: every set or match returned
  match_id  TEXT PRIMARY KEY,                   -- start.gg set ID / Challengermode match UUID
  event_id  TEXT NOT NULL,
  pool_id   INTEGER                             -- start.gg pool
);
CREATE INDEX IF NOT EXISTS crawl_matches_event ON crawl_matches (event_id);
CREATE TABLE IF NOT EXISTS crawl_platform_players (  -- 2b: platform players and their Stats API records
  platform            TEXT NOT NULL,            -- 'startgg' | 'challengermode'
  platform_player_id  TEXT NOT NULL,            -- start.gg player ID / Challengermode user ID
  status              INTEGER NOT NULL DEFAULT 0,  -- 0 to look up, 1 planned, 2 found, 3 not in the Stats API
  player_id           INTEGER,                  -- the Stats API record, once found
  PRIMARY KEY (platform, platform_player_id)
);
CREATE TABLE IF NOT EXISTS crawl_series_placements ( -- 3b: placements found at the Pro Series finals
  event_id   TEXT NOT NULL,
  player_id  INTEGER NOT NULL,
  placement  INTEGER NOT NULL,
  PRIMARY KEY (event_id, player_id)
);
"""

STANDINGS_QUERY = """
query Standings($slug: String!, $page: Int!) { event(slug: $slug) {
  id numEntrants
  standings(query: {page: $page, perPage: 64}) {
    pageInfo { total totalPages }
    nodes { placement isFinal
      entrant { id name initialSeedNum isDisqualified
        participants { id gamerTag prefix player { id } } } } } } }"""

# P4. Sets carry what `matches` and the bracket tables need; seeds come from the standings'
# initialSeedNum. Sorting by round pages stably (no set repeated or skipped in the survey).
SET_FIELDS = """id round fullRoundText identifier displayScore winnerId state wPlacement lPlacement startedAt completedAt
      phaseGroup { id }
      slots { slotIndex entrant { id name } standing { stats { score { value } } } }"""

EVENT_SETS_QUERY = """
query EventSets($slug: String!, $page: Int!, $perPage: Int!) { event(slug: $slug) {
  id
  phases { id name phaseOrder bracketType numSeeds groupCount state isExhibition }
  sets(page: $page, perPage: $perPage, sortType: ROUND) {
    pageInfo { total totalPages }
    nodes { %s } } } }""" % SET_FIELDS

POOL_SETS_QUERY = """
query PoolSets($poolId: ID!, $page: Int!, $perPage: Int!) { phaseGroup(id: $poolId) {
  id
  sets(page: $page, perPage: $perPage, sortType: ROUND) {
    pageInfo { total totalPages }
    nodes { %s } } } }""" % SET_FIELDS

POOL_FIELDS = "id displayIdentifier bracketType bracketUrl numRounds state rounds { number bestOf }"  # startAt fails on 2020 pools

EVENT_POOLS_QUERY = """
query EventPools($slug: String!) { event(slug: $slug) {
  id phaseGroups { %s phase { id } } } }""" % POOL_FIELDS

PHASE_POOLS_QUERY = """
query PhasePools($phaseId: ID!, $page: Int!, $perPage: Int!) { phase(id: $phaseId) {
  id phaseGroups(query: {page: $page, perPage: $perPage}) {
    pageInfo { total totalPages }
    nodes { %s } } } }""" % POOL_FIELDS

PHASE_GAMES_QUERY = """
query PhaseGames($phaseId: ID!, $page: Int!, $perPage: Int!) { phase(id: $phaseId) {
  id sets(page: $page, perPage: $perPage, sortType: ROUND) {
    pageInfo { total totalPages }
    nodes { id games { orderNum winnerId entrant1Score entrant2Score stage { id name }
      selections { entrant { id } character { id name } } } } } } }"""

# P5. A Challengermode match is the set: its result is the game score, and its lineup
# numbers (0, 1) say whose score is whose. The series around it is a best-of-1 wrapper.
CM_ROSTER_QUERY = """
query Roster($id: UUID!, $limit: Int!) { tournament(tournamentId: $id) {
  id name state
  attendance { confirmedLineupCount roster { lineupCount userCount
    lineups(limit: $limit) { id name seed preSeed disqualified
      placement { bestPlacement worstPlacement displayPlacement }
      members { gameAccountId captain user { id username } } } } } } }"""

CM_SERIES_FIELDS = """id ordinal state bestOf startedAt title labels
      lineups { id name seed disqualified members { user { id } } }
      results { final draw lineupResults { lineupNumber score placement } }
      matches(includeFailed: true) { id state
        lineups { number members { user { id } } }
        results { final draw lineupResults { lineupNumber score placement } } }"""

CM_ROUND_FIELDS = "roundNumber title labels matchSeries { %s }" % CM_SERIES_FIELDS

CM_BRACKET_QUERY = """
query Bracket($id: UUID!) { tournament(tournamentId: $id) {
  id
  stages { index format lineupCount
    ... on TournamentEliminationStage { brackets { title labels rounds { %s } } }
    ... on TournamentSwissStage { rounds { %s } }
    ... on TournamentGroupStage { groups { number title matchSeries { %s } } } } } }""" % (
    CM_ROUND_FIELDS, CM_ROUND_FIELDS, CM_SERIES_FIELDS)


def migrate(db):
    """Bring crawl tables made by earlier versions of this file up to date."""
    key = [r[1] for r in sorted(db.execute("PRAGMA table_info(crawl_standings)"), key=lambda r: r[5]) if r[5]]
    if key == ["event_id", "participant_id"]:  # until 2026-10-04 a player entered twice in one event kept one row
        with db:
            db.execute("ALTER TABLE crawl_standings RENAME TO crawl_standings_old")
            db.execute(STANDINGS_TABLE)
            db.execute("INSERT INTO crawl_standings (event_id, participant_id, entrant_id, sgg_player_id, placement, disqualified)"
                       " SELECT event_id, participant_id, entrant_id, sgg_player_id, placement, disqualified"
                       " FROM crawl_standings_old")
            db.execute("DROP TABLE crawl_standings_old")
            short = {r[0] for r in db.execute(
                "SELECT event_id FROM crawl_platform_events p WHERE platform = 'startgg' AND status = 'ok' AND entrants >"
                " (SELECT COUNT(DISTINCT entrant_id) FROM crawl_standings s WHERE s.event_id = p.event_id)")}
            keys = [k for (k,) in db.execute("SELECT task_key FROM tasks WHERE stage = 'standings'")
                    if k.rsplit(":", 1)[0].removeprefix("standings:") in short]
            # Their pages are applied again, from the cache, on the next standings run.
            db.executemany("UPDATE tasks SET status = 'pending', updated_at = ? WHERE task_key = ?", [(now(), k) for k in keys])


def walk_pages(api, endpoint, params, rows_key, row_id, row_time, page_size, log=print):
    """Every row of a listing paged by timestamp tokens, working around the tie bug.

    The next page starts strictly before the token, so rows sharing the boundary timestamp
    can be skipped. Asking for the last timestamp + 1 instead re-reads the boundary, and
    de-duplicating by ID keeps each row once. A short page is the last one. If a full page
    brings nothing new (more ties than a page holds), fall back to the server's token.
    """
    rows, token = {}, None
    while True:
        body = api.get(endpoint, {**params, "maxResults": page_size, "nextToken": token})
        page = body.get(rows_key) or []
        new = [r for r in page if row_id(r) not in rows]
        rows.update((row_id(r), r) for r in new)
        if len(page) < page_size:
            return list(rows.values())
        if new:
            token = str(row_time(page[-1]) + 1)
        elif body.get("nextToken") and body["nextToken"] != token:
            log(f"  {endpoint}: a full page of known rows at {row_time(page[-1])}; using the server's token")
            token = body["nextToken"]
        else:
            return list(rows.values())


def list_events(api, mode, year=None, log=print):
    """Every official event in one mode, and optionally one year."""
    return walk_pages(api, "/event", {"gameMode": mode, "isOfficial": True, "year": year},
                      "tournaments", lambda e: e["id"], lambda e: e["startTime"], PAGE_SIZE, log)


def placement_pages(api, player_ids, mode, log):
    return walk_pages(api, "/player/placement", {"playerIds": player_ids, "gameMode": mode, "isOfficial": True},
                      "playerPlacements", lambda r: r["tournament"]["id"], lambda r: r["tournament"]["startTime"],
                      PAGE_SIZE, log)


def follow_pages(p, kind, key_prefix, page_info):
    """From a listing's first page, the tasks for the rest of its pages."""
    if p["page"] != 1:
        return []
    return [(STAGE_OF[kind], kind, f"{key_prefix}:{page}", {**p, "page": page})
            for page in range(2, ((page_info or {}).get("totalPages") or 1) + 1)]


def chosen_events(db, host, args):
    """The official events a platform stage covers: every one on that platform, or those named with --event."""
    if host == "SGG":  # the 'series/...' events have no start.gg event
        rows = db.execute("SELECT event_id FROM crawl_events WHERE host = 'SGG' AND event_id LIKE 'tournament/%'"
                          " ORDER BY start_time, event_id")
    else:
        rows = db.execute("SELECT event_id FROM crawl_events WHERE host = 'CM' ORDER BY start_time, event_id")
    only = set(getattr(args, "event", None) or [])
    return [eid for (eid,) in rows if not only or eid in only]


# Stage 0: events

def plan_events(db, queue, args):
    for mode in MODES:
        queue.add("events", "event_list", f"events:{mode}", {"mode": mode})
        for year in range(FIRST_YEAR, datetime.now(timezone.utc).year + 1):
            queue.add("events", "event_list", f"events:{mode}:{year}", {"mode": mode, "year": year})


def fetch_event_list(api, p, log):
    return list_events(api, p["mode"], p.get("year"), log)


def apply_event_list(db, p, events):
    if p.get("year") is None:
        db.executemany("INSERT OR REPLACE INTO crawl_events (event_id, mode, host, start_time) VALUES (?, ?, ?, ?)",
                       [(e["id"], p["mode"], e.get("host"), e["startTime"]) for e in events])
    return []


def check_events(db, api, log):
    """The full listing and the per-year listings must hold the same events (the tie bug check)."""
    ok = True
    for mode, label in MODES.items():
        full = {e["id"] for e in list_events(api, mode, log=log)}  # all from the cache by now
        by_year = set()
        for year in range(FIRST_YEAR, datetime.now(timezone.utc).year + 1):
            by_year |= {e["id"] for e in list_events(api, mode, year, log=log)}
        if full == by_year:
            log(f"{label}: {len(full)} official events; the per-year crawls agree")
        else:
            ok = False
            log(f"{label}: MISMATCH, {len(full)} in the full crawl and {len(by_year)} in the per-year crawls")
    return ok


# Stage 1: PR lists

def plan_pr(db, queue, args):
    for mode in MODES:
        for region in REGIONS:
            queue.add("pr", "pr_page", f"pr:{mode}:{region}:1", {"mode": mode, "region": region, "page": 1})


def fetch_pr_page(api, p, log):
    return api.get("/pr", {"gameMode": p["mode"], "region": p["region"], "page": p["page"],
                           "maxResults": PR_PAGE_SIZE})


def apply_pr_page(db, p, body):
    db.executemany("INSERT OR IGNORE INTO crawl_players (player_id, found_by) VALUES (?, 'pr')",
                   [(r["playerId"],) for r in body.get("prPlayers") or []])
    if p["page"] != 1:
        return []
    return [("pr", "pr_page", f"pr:{p['mode']}:{p['region']}:{page}", {**p, "page": page})
            for page in range(2, (body.get("totalPages") or 1) + 1)]


# Stage 2: profiles

def profile_task(ids):
    digest = hashlib.sha1(",".join(map(str, ids)).encode()).hexdigest()[:10]
    return "profiles", "profile_batch", f"profiles:{ids[0]}-{ids[-1]}:{digest}", {"player_ids": ids}


def plan_profiles(db, queue, args):
    ids = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE profile = 0 ORDER BY player_id")]
    for i in range(0, len(ids), PROFILE_BATCH):
        queue.add(*profile_task(ids[i:i + PROFILE_BATCH]))
    db.execute("UPDATE crawl_players SET profile = 1 WHERE profile = 0")


def split_on_refusal(api, endpoint, params, ids):
    """ListPlayers, or {'split': True} when it refuses the batch, which is then tried in halves."""
    try:
        return api.get(endpoint, params)
    except ApiError as e:
        if e.status and 400 <= e.status < 500 and e.status not in (401, 403, 404, 429) and len(ids) > 1:
            return {"split": True}  # too many IDs for one request: try each half
        raise


def fetch_profile_batch(api, p, log):
    return split_on_refusal(api, "/players", {"playerIds": p["player_ids"]}, p["player_ids"])


def apply_profile_batch(db, p, body):
    ids = p["player_ids"]
    if body.get("split"):
        return [profile_task(ids[:len(ids) // 2]), profile_task(ids[len(ids) // 2:])]
    found = {pl["playerId"] for pl in body.get("players") or [] if pl}
    db.executemany("UPDATE crawl_players SET profile = ? WHERE player_id = ?",
                   [(2 if i in found else 3, i) for i in ids])
    return []


# Stage 2b: lookups. Every player in start.gg standings and Challengermode entrant lists,
# matched to their Stats API record by platform ID; a player with none is platform-only.

def lookup_task(platform, ids):
    digest = hashlib.sha1(",".join(ids).encode()).hexdigest()[:10]
    return "lookups", "lookup", f"lookup:{platform}:{ids[0]}-{ids[-1]}:{digest}", {"platform": platform, "ids": ids}


def plan_lookups(db, queue, args):
    only = list(getattr(args, "event", None) or [])
    where = f" AND event_id IN ({', '.join('?' * len(only))})" if only else ""
    db.execute("INSERT OR IGNORE INTO crawl_platform_players (platform, platform_player_id)"
               " SELECT DISTINCT 'startgg', CAST(sgg_player_id AS TEXT) FROM crawl_standings"
               " WHERE sgg_player_id IS NOT NULL" + where, only)
    db.execute("INSERT OR IGNORE INTO crawl_platform_players (platform, platform_player_id)"
               " SELECT DISTINCT 'challengermode', user_id FROM crawl_cm_entrants WHERE 1" + where, only)
    for platform in LOOKUP_PARAMS:
        ids = [r[0] for r in db.execute("SELECT platform_player_id FROM crawl_platform_players WHERE platform = ?"
                                        " AND status = 0 ORDER BY length(platform_player_id), platform_player_id",
                                        (platform,))]
        for i in range(0, len(ids), PROFILE_BATCH):
            queue.add(*lookup_task(platform, ids[i:i + PROFILE_BATCH]))
        db.execute("UPDATE crawl_platform_players SET status = 1 WHERE platform = ? AND status = 0", (platform,))


def fetch_lookup(api, p, log):
    return split_on_refusal(api, "/players", {LOOKUP_PARAMS[p["platform"]][0]: p["ids"]}, p["ids"])


def record_lookup(db, platform, ids, body):
    """Mark each platform ID found (with its Stats API record) or not in the Stats API. Returns the records found."""
    field = LOOKUP_PARAMS[platform][1]
    found = {str(pl[field]).lower(): pl["playerId"] for pl in body.get("players") or [] if pl and pl.get(field) is not None}
    db.executemany("INSERT INTO crawl_platform_players (platform, platform_player_id, status, player_id) VALUES (?, ?, ?, ?)"
                   " ON CONFLICT (platform, platform_player_id) DO UPDATE SET status = excluded.status,"
                   " player_id = excluded.player_id",
                   [(platform, i, 2 if i.lower() in found else 3, found.get(i.lower())) for i in ids])
    return found


def apply_lookup(db, p, body):
    if body.get("split"):
        half = len(p["ids"]) // 2
        return [lookup_task(p["platform"], p["ids"][:half]), lookup_task(p["platform"], p["ids"][half:])]
    record_lookup(db, p["platform"], p["ids"], body)
    return []


def check_lookups(db, api, log):
    for platform, status, n in db.execute("SELECT platform, status, COUNT(*) FROM crawl_platform_players"
                                          " GROUP BY platform, status ORDER BY platform, status"):
        log(f"  {platform}: {n} {({0: 'to look up', 1: 'planned', 2: 'found', 3: 'not in the Stats API'})[status]}")
    return True


# Stage 3: histories

def plan_histories(db, queue, args):
    ids = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE history_planned = 0 ORDER BY player_id")]
    if getattr(args, "sample", None):
        seeds = [r[0] for r in db.execute("SELECT player_id FROM crawl_players WHERE found_by = 'pr' ORDER BY player_id")]
        chosen = set(random.Random(SAMPLE_SEED).sample(seeds, min(args.sample, len(seeds))))
        ids = [i for i in ids if i in chosen]
    for pid in ids:
        for mode in MODES:
            queue.add("histories", "placements", f"placements:{pid}:{mode}", {"player_id": pid, "mode": mode})
        queue.add("histories", "teammates", f"teammates:{pid}", {"player_id": pid})
    db.executemany("UPDATE crawl_players SET history_planned = 1 WHERE player_id = ?", [(i,) for i in ids])


def fetch_placements(api, p, log):
    return placement_pages(api, p["player_id"], p["mode"], log)


def apply_placements(db, p, rows):
    db.executemany("INSERT OR IGNORE INTO crawl_entries (player_id, event_id, mode) VALUES (?, ?, ?)",
                   [(p["player_id"], r["tournament"]["id"], p["mode"]) for r in rows])
    return []


def fetch_teammates(api, p, log):
    return walk_pages(api, "/player/teammate", {"playerId": p["player_id"], "isOfficial": True},
                      "playerTeammates", lambda r: r["player"]["playerId"], lambda r: r["lastTeamedDate"],
                      PAGE_SIZE, log)


def apply_teammates(db, p, rows):
    me, partners = p["player_id"], [r["player"]["playerId"] for r in rows]
    db.executemany("INSERT OR IGNORE INTO crawl_players (player_id, found_by) VALUES (?, 'teammate')",
                   [(q,) for q in partners])
    db.executemany("INSERT OR IGNORE INTO crawl_pairs (player1_id, player2_id) VALUES (?, ?)",
                   [(min(me, q), max(me, q)) for q in partners if q != me])
    return []


# Stage 3b: the Pro Series finals. No platform has them and the Stats API has no event
# endpoint, so likely entrants are checked one by one: the top of every official start.gg
# event, 1v1 or 2v2, in the year before the final, in its region or in no region (LANs,
# partner events). The 2021 final turned out to be a team format, with 2v2 players.

def slug_region(event_id):
    """'NA', 'EU' or 'other' from the region an event ID names; None when it names none."""
    name = event_id.split("/")[1]
    tokens = set(name.split("-"))
    if name.startswith("north-america") or tokens & {"na", "us"}:
        return "NA"
    if name.startswith("europe") or "eu" in tokens:
        return "EU"
    if tokens & {"sa", "sea", "aus", "brz", "south", "southeast", "asia", "australia", "brazil", "japan", "mena"}:
        return "other"
    return None


def series_check(final, start, player_id):
    return ("proseries", "series_check", f"series_check:{final}:{player_id}",
            {"event_id": final, "start_time": start, "player_id": player_id})


def plan_proseries(db, queue, args):
    only = set(getattr(args, "event", None) or [])
    for final, start in db.execute("SELECT event_id, start_time FROM crawl_events WHERE event_id LIKE 'series/%'"
                                   " ORDER BY start_time").fetchall():
        if only and final not in only:
            continue
        events = [eid for (eid,) in db.execute(
            "SELECT event_id FROM crawl_events WHERE host = 'SGG' AND event_id LIKE 'tournament/%'"
            " AND start_time >= ? AND start_time < ?", (start - SERIES_WINDOW, start))
            if slug_region(eid) in (slug_region(final), None)]
        ids = {str(r[0]) for eid in events for r in db.execute(
            "SELECT sgg_player_id FROM crawl_standings WHERE event_id = ? AND placement <= ? AND sgg_player_id IS NOT NULL",
            (eid, SERIES_TOP))}
        known = dict(db.execute("SELECT platform_player_id, player_id FROM crawl_platform_players"
                                " WHERE platform = 'startgg' AND status IN (2, 3)").fetchall())
        for pid in sorted({known[i] for i in ids if known.get(i)}):  # already looked up (stage 2b)
            queue.add(*series_check(final, start, pid))
        unknown = sorted((i for i in ids if i not in known), key=int)
        for i in range(0, len(unknown), PROFILE_BATCH):
            chunk = unknown[i:i + PROFILE_BATCH]
            digest = hashlib.sha1(",".join(chunk).encode()).hexdigest()[:10]
            queue.add("proseries", "series_candidates", f"series_candidates:{final}:{chunk[0]}-{chunk[-1]}:{digest}",
                      {"event_id": final, "start_time": start, "sgg_ids": chunk})


def fetch_series_candidates(api, p, log):
    return api.get("/players", {"sggIds": p["sgg_ids"]})


def apply_series_candidates(db, p, body):
    found = record_lookup(db, "startgg", p["sgg_ids"], body)  # these are lookups too
    return [series_check(p["event_id"], p["start_time"], pid) for pid in sorted(set(found.values()))]


def fetch_series_check(api, p, log):
    """The player's newest official 1v1 events up to the final's start: one page shows whether they played it."""
    return api.get("/player/placement", {"playerIds": p["player_id"], "gameMode": 1, "isOfficial": True,
                                         "maxResults": 10, "nextToken": p["start_time"] + 1})


def apply_series_check(db, p, body):
    db.executemany("INSERT OR REPLACE INTO crawl_series_placements (event_id, player_id, placement) VALUES (?, ?, ?)",
                   [(p["event_id"], p["player_id"], r["placement"]) for r in body.get("playerPlacements") or []
                    if r["tournament"]["id"] == p["event_id"]])
    return []


def double_elimination_places(n):
    """The places of a complete double elimination of n entrants: 1, 2, 3, 4, 5, 5, 7, 7, 9 x4, 13 x4, 17 x8, ..."""
    places, place, size = [1, 2, 3, 4], 5, 2
    while len(places) < n:
        places += [place] * size + [place + size] * size
        place, size = place + 2 * size, size * 2
    return places[:n]


def check_proseries(db, api, log):
    """The placements found at each final should form a complete bracket; a gap means an entrant was missed.

    A team format, where every member shares the team's place, can't be checked that way: each
    place from 1 down is shared, and only the team sizes hint at a missing member.
    """
    ok = True
    for (final,) in db.execute("SELECT event_id FROM crawl_events WHERE event_id LIKE 'series/%' ORDER BY start_time").fetchall():
        checked = sum(1 for (k,) in db.execute("SELECT task_key FROM tasks WHERE kind = 'series_check'")
                      if k.startswith(f"series_check:{final}:"))
        if not checked:
            continue
        found = sorted(r[0] for r in db.execute("SELECT placement FROM crawl_series_placements WHERE event_id = ?", (final,)))
        sizes = collections.Counter(found)
        if found and found == double_elimination_places(len(found)):
            verdict = f"consistent with a complete double elimination of {len(found)}"
        elif found and found == list(range(1, len(found) + 1)):
            verdict = f"consistent with a complete ranking of {len(found)}"
        elif found and sorted(sizes) == list(range(1, len(sizes) + 1)) and min(sizes.values()) > 1:
            verdict = ("a team format, every place shared (" + ", ".join(f"{place}: {n} players" for place, n in
                                                                         sorted(sizes.items()))
                       + "), so completeness can't be confirmed from places")
        else:
            ok, verdict = False, "not a complete bracket, so an entrant may be missing"
        log(f"{final}: {len(found)} placements among {checked} candidates ({', '.join(map(str, found)) or 'none'}): {verdict}")
    return ok


# Stage 4: teams

def plan_teams(db, queue, args):
    for a, b in db.execute("SELECT player1_id, player2_id FROM crawl_pairs WHERE planned = 0").fetchall():
        queue.add("teams", "team", f"team:{a}:{b}", {"player_ids": [a, b]})
    db.execute("UPDATE crawl_pairs SET planned = 1 WHERE planned = 0")


def fetch_team(api, p, log):
    return placement_pages(api, p["player_ids"], 2, log)


def apply_team(db, p, rows):
    db.execute("UPDATE crawl_pairs SET events = ? WHERE player1_id = ? AND player2_id = ?",
               (len(rows), *p["player_ids"]))
    return []


# P1: start.gg standings for official start.gg events (no Stats API requests, so it can
# run alongside a Stats API stage). The 'series/...' events have no start.gg event.

def plan_standings(db, queue, args):
    for (eid,) in db.execute("SELECT event_id FROM crawl_events WHERE host = 'SGG' AND event_id LIKE 'tournament/%'"):
        queue.add("standings", "standings_page", f"standings:{eid}:1", {"slug": eid, "page": 1})


def fetch_standings_page(api, p, log):
    return api.query("Standings", STANDINGS_QUERY, {"slug": p["slug"], "page": p["page"]})


def apply_standings_page(db, p, data):
    event = data.get("event")
    if not event:
        db.execute("INSERT OR REPLACE INTO crawl_platform_events (event_id, platform, status) VALUES (?, 'startgg', 'missing')",
                   (p["slug"],))
        return []
    standings = event["standings"]
    db.executemany(
        "INSERT OR IGNORE INTO crawl_standings (event_id, participant_id, entrant_id, sgg_player_id, placement, disqualified)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(p["slug"], part["id"], node["entrant"]["id"], (part.get("player") or {}).get("id"), node["placement"],
          int(bool(node["entrant"].get("isDisqualified"))))
         for node in standings.get("nodes") or [] if node.get("entrant")
         for part in node["entrant"].get("participants") or []])
    if p["page"] != 1:
        return []
    db.execute("INSERT OR REPLACE INTO crawl_platform_events (event_id, platform, platform_event_id, entrants, registered, status)"
               " VALUES (?, 'startgg', ?, ?, ?, 'ok')",
               (p["slug"], str(event["id"]), standings["pageInfo"]["total"], event.get("numEntrants")))
    return [("standings", "standings_page", f"standings:{p['slug']}:{page}", {**p, "page": page})
            for page in range(2, (standings["pageInfo"]["totalPages"] or 1) + 1)]


def check_standings(db, api, log):
    """Every event's standings must hold start.gg's own count of placed entrants."""
    short = db.execute("SELECT event_id, entrants, (SELECT COUNT(DISTINCT entrant_id) FROM crawl_standings s"
                       " WHERE s.event_id = p.event_id) AS held FROM crawl_platform_events p"
                       " WHERE platform = 'startgg' AND status = 'ok' AND entrants <> held").fetchall()
    for eid, entrants, held in short:
        log(f"  {eid}: {held} of {entrants} entrants")
    log(f"start.gg standings: {len(short)} event(s) short")
    return not short


# P4: start.gg brackets. Each event's sets, a page at a time, or pool by pool for the four
# events over start.gg's cap; its pools with their round best-ofs; and the games of its
# last phase. start.gg requests only, so it can run alongside a Stats API stage.

def plan_brackets(db, queue, args):
    for slug in chosen_events(db, "SGG", args):
        queue.add("brackets", "sgg_sets", f"sgg_sets:{slug}:1", {"slug": slug, "page": 1})
    # The pools of events fetched pool by pool, once pool tasks have found them.
    only, limit, taken = set(getattr(args, "event", None) or []), getattr(args, "max_pools", None), collections.Counter()
    for pool_id, slug, phase_id, planned in db.execute(
            "SELECT pool_id, event_id, phase_id, planned FROM crawl_pools WHERE event_id IN"
            " (SELECT event_id FROM crawl_brackets WHERE by_pool = 1) ORDER BY event_id, phase_id, pool_id").fetchall():
        if only and slug not in only:
            continue
        if not planned and limit is not None and taken[phase_id] >= limit:
            continue  # a pilot: only the first pools of each phase
        if not planned:
            queue.add("brackets", "sgg_pool_sets", f"sgg_pool_sets:{pool_id}:1", {"slug": slug, "pool_id": pool_id, "page": 1})
            db.execute("UPDATE crawl_pools SET planned = 1 WHERE pool_id = ?", (pool_id,))
        taken[phase_id] += 1


def record_sets(db, slug, sets):
    db.executemany("INSERT OR IGNORE INTO crawl_matches (match_id, event_id, pool_id) VALUES (?, ?, ?)",
                   [(str(s["id"]), slug, (s.get("phaseGroup") or {}).get("id")) for s in sets.get("nodes") or []])


def fetch_sgg_sets(api, p, log):
    return api.query("EventSets", EVENT_SETS_QUERY, {"slug": p["slug"], "page": p["page"], "perPage": SETS_PER_PAGE})


def apply_sgg_sets(db, p, data):
    event, slug = data.get("event"), p["slug"]
    if not event or event.get("sets") is None:
        raise ValueError(f"start.gg returned no sets for {slug}")
    record_sets(db, slug, event["sets"])
    if p["page"] != 1:
        return []
    info = event["sets"]["pageInfo"]
    by_pool = (info["total"] or 0) > SETS_CAP
    db.execute("INSERT OR REPLACE INTO crawl_brackets (event_id, platform, matches, by_pool) VALUES (?, 'startgg', ?, ?)",
               (slug, info["total"], int(by_pool)))
    follow = [] if by_pool else follow_pages(p, "sgg_sets", f"sgg_sets:{slug}", info)
    phases = sorted(event.get("phases") or [], key=lambda ph: ph.get("phaseOrder") or 0)
    if by_pool or sum(ph.get("groupCount") or 1 for ph in phases) > POOLS_PER_QUERY:
        follow += [("brackets", "sgg_phase_pools", f"sgg_phase_pools:{ph['id']}:1", {"slug": slug, "phase_id": ph["id"], "page": 1})
                   for ph in phases]
    else:
        follow.append(("brackets", "sgg_pools", f"sgg_pools:{slug}", {"slug": slug}))
    # The last phase is the smallest: phaseOrder isn't always bracket order (EU SteelSeries 2020 numbers Top 256 4th).
    last = min((ph for ph in phases if not ph.get("isExhibition")),
               key=lambda ph: (ph.get("numSeeds") or SETS_CAP, -(ph.get("phaseOrder") or 0)), default=None)
    if last and (last.get("numSeeds") or SETS_CAP) <= GAMES_MAX_SEEDS:
        mode = (db.execute("SELECT mode FROM crawl_events WHERE event_id = ?", (slug,)).fetchone() or (2,))[0]
        follow.append(("brackets", "sgg_games", f"sgg_games:{last['id']}:1",
                       {"slug": slug, "phase_id": last["id"], "page": 1, "per_page": GAMES_PER_PAGE.get(mode, 8)}))
    return follow


def fetch_sgg_pools(api, p, log):
    return api.query("EventPools", EVENT_POOLS_QUERY, {"slug": p["slug"]})


def apply_sgg_pools(db, p, data):
    db.executemany("INSERT OR IGNORE INTO crawl_pools (pool_id, event_id, phase_id) VALUES (?, ?, ?)",
                   [(g["id"], p["slug"], (g.get("phase") or {}).get("id"))
                    for g in (data.get("event") or {}).get("phaseGroups") or []])
    return []


def fetch_sgg_phase_pools(api, p, log):
    return api.query("PhasePools", PHASE_POOLS_QUERY, {"phaseId": p["phase_id"], "page": p["page"], "perPage": POOLS_PER_PAGE})


def apply_sgg_phase_pools(db, p, data):
    pools = (data.get("phase") or {}).get("phaseGroups")
    if pools is None:
        raise ValueError(f"start.gg returned no pools for phase {p['phase_id']}")
    db.executemany("INSERT OR IGNORE INTO crawl_pools (pool_id, event_id, phase_id) VALUES (?, ?, ?)",
                   [(g["id"], p["slug"], p["phase_id"]) for g in pools.get("nodes") or []])
    return follow_pages(p, "sgg_phase_pools", f"sgg_phase_pools:{p['phase_id']}", pools.get("pageInfo"))


def fetch_sgg_pool_sets(api, p, log):
    return api.query("PoolSets", POOL_SETS_QUERY, {"poolId": p["pool_id"], "page": p["page"], "perPage": SETS_PER_PAGE})


def apply_sgg_pool_sets(db, p, data):
    pool = data.get("phaseGroup")
    if not pool or pool.get("sets") is None:
        raise ValueError(f"start.gg returned no sets for pool {p['pool_id']}")
    record_sets(db, p["slug"], pool["sets"])
    if p["page"] == 1:
        db.execute("UPDATE crawl_pools SET sets = ? WHERE pool_id = ?", (pool["sets"]["pageInfo"]["total"], p["pool_id"]))
    return follow_pages(p, "sgg_pool_sets", f"sgg_pool_sets:{p['pool_id']}", pool["sets"]["pageInfo"])


def fetch_sgg_games(api, p, log):
    return api.query("PhaseGames", PHASE_GAMES_QUERY, {"phaseId": p["phase_id"], "page": p["page"], "perPage": p["per_page"]})


def apply_sgg_games(db, p, data):
    sets = (data.get("phase") or {}).get("sets")
    if sets is None:
        raise ValueError(f"start.gg returned no sets for phase {p['phase_id']}")
    return follow_pages(p, "sgg_games", f"sgg_games:{p['phase_id']}", sets.get("pageInfo"))


def check_brackets(db, api, log):
    """Every event's sets must all have come back: as many distinct sets as start.gg's own total."""
    complete, partial, short = 0, 0, 0
    for slug, total, by_pool, held in db.execute(
            "SELECT event_id, matches, by_pool, (SELECT COUNT(*) FROM crawl_matches m WHERE m.event_id = b.event_id)"
            " FROM crawl_brackets b WHERE platform = 'startgg' ORDER BY event_id").fetchall():
        if by_pool:
            pools, planned, pool_sets = db.execute("SELECT COUNT(*), SUM(planned), SUM(sets) FROM crawl_pools"
                                                   " WHERE event_id = ?", (slug,)).fetchone()
            if not pools or planned < pools:
                partial += 1
                log(f"  {slug}: {planned or 0} of {pools} pools fetched so far ({held} of {total} sets)")
                continue
            if pool_sets != total:
                log(f"  {slug}: its pools hold {pool_sets} sets, start.gg's event total is {total}")
        if held == total:
            complete += 1
        else:
            short += 1
            log(f"  {slug}: {held} sets fetched, start.gg reports {total}")
    log(f"start.gg brackets: {complete} event(s) complete, {partial} partly fetched (--max-pools), {short} with sets missing")
    return not short


# P5: Challengermode entrant lists and brackets (Challengermode requests only, so it can run
# alongside the other stages). The roster has no paging, so ROSTER_LIMIT must exceed the
# largest event; the check makes sure it did.

def plan_cm(db, queue, args):
    for eid in chosen_events(db, "CM", args):
        queue.add("cm", "cm_entrants", f"cm_entrants:{eid}", {"tournament_id": eid})
        queue.add("cm", "cm_bracket", f"cm_bracket:{eid}", {"tournament_id": eid})


def fetch_cm_entrants(api, p, log):
    return api.query("Roster", CM_ROSTER_QUERY, {"id": p["tournament_id"], "limit": ROSTER_LIMIT})


def apply_cm_entrants(db, p, data):
    eid, tournament = p["tournament_id"], data.get("tournament")
    if not tournament:
        raise ValueError(f"Challengermode has no tournament {eid}")
    roster = (tournament.get("attendance") or {}).get("roster") or {}
    lineups = [lu for lu in roster.get("lineups") or [] if lu]
    db.executemany("INSERT OR IGNORE INTO crawl_cm_entrants (event_id, lineup_id, user_id, placement) VALUES (?, ?, ?, ?)",
                   [(eid, lu["id"], m["user"]["id"], (lu.get("placement") or {}).get("bestPlacement"))
                    for lu in lineups for m in lu.get("members") or [] if (m.get("user") or {}).get("id")])
    db.execute("INSERT OR REPLACE INTO crawl_platform_events (event_id, platform, platform_event_id, entrants, registered, status)"
               " VALUES (?, 'challengermode', ?, ?, ?, 'ok')", (eid, eid, roster.get("lineupCount"), len(lineups)))
    return []


def cm_series(tournament):
    """Every match series of a Challengermode tournament, from every kind of stage."""
    for stage in tournament.get("stages") or []:
        for bracket in stage.get("brackets") or [{"rounds": stage.get("rounds") or []}]:
            for rnd in bracket.get("rounds") or []:
                yield from (s for s in rnd.get("matchSeries") or [] if s)
        for group in stage.get("groups") or []:
            yield from (s for s in group.get("matchSeries") or [] if s)


def fetch_cm_bracket(api, p, log):
    return api.query("Bracket", CM_BRACKET_QUERY, {"id": p["tournament_id"]})


def apply_cm_bracket(db, p, data):
    eid, tournament = p["tournament_id"], data.get("tournament")
    if not tournament:
        raise ValueError(f"Challengermode has no tournament {eid}")
    matches = {m["id"] for s in cm_series(tournament) for m in s.get("matches") or [] if m}
    db.executemany("INSERT OR IGNORE INTO crawl_matches (match_id, event_id) VALUES (?, ?)", [(m, eid) for m in matches])
    db.execute("INSERT OR REPLACE INTO crawl_brackets (event_id, platform, matches) VALUES (?, 'challengermode', ?)",
               (eid, len(matches)))
    return []


def check_cm(db, api, log):
    """Every lineup in an event's bracket must be in its entrant list, and every series between two lineups must
    have a match. A roster also lists lineups that never played (in 2v2 mostly a player without a partner): they
    have no placement and aren't entrants, so the roster's own lineup count can exceed the bracket's."""
    problems = 0
    for eid, returned in db.execute("SELECT event_id, registered FROM crawl_platform_events"
                                    " WHERE platform = 'challengermode'").fetchall():
        if returned >= ROSTER_LIMIT:
            problems += 1
            log(f"  {eid}: the entrant list may be cut off at {ROSTER_LIMIT} lineups")
    for (eid,) in db.execute("SELECT event_id FROM crawl_brackets WHERE platform = 'challengermode'").fetchall():
        series = list(cm_series(api.query("Bracket", CM_BRACKET_QUERY, {"id": eid})["tournament"]))  # from the cache
        listed = {r[0] for r in db.execute("SELECT DISTINCT lineup_id FROM crawl_cm_entrants WHERE event_id = ?", (eid,))}
        played = {lu["id"] for s in series for lu in s.get("lineups") or [] if lu}
        if played - listed:
            problems += 1
            log(f"  {eid}: {len(played - listed)} of the {len(played)} lineups in the bracket aren't in the entrant list"
                + ("" if listed else " (it hasn't been fetched)"))
        empty = [s for s in series if sum(1 for lu in s.get("lineups") or [] if lu) == 2 and not s.get("matches")]
        if empty:
            problems += 1
            log(f"  {eid}: {len(empty)} of {len(series)} series between two lineups have no match")
    log(f"Challengermode: {problems} problem(s)")
    return not problems


STAGES = {  # name: (number, plan, check run once the stage has finished, API it calls)
    "events": ("0", plan_events, check_events, "statsapi"),
    "pr": ("1", plan_pr, None, "statsapi"),
    "profiles": ("2", plan_profiles, None, "statsapi"),
    "lookups": ("2b", plan_lookups, check_lookups, "statsapi"),
    "histories": ("3", plan_histories, None, "statsapi"),
    "proseries": ("3b", plan_proseries, check_proseries, "statsapi"),
    "teams": ("4", plan_teams, None, "statsapi"),
    "standings": ("P1", plan_standings, check_standings, "startgg"),
    "brackets": ("P4", plan_brackets, check_brackets, "startgg"),
    "cm": ("P5", plan_cm, check_cm, "challengermode"),
}
CLIENTS = {"statsapi": StatsApi, "startgg": StartGG, "challengermode": Challengermode}
KINDS = {
    "event_list": (fetch_event_list, apply_event_list),
    "pr_page": (fetch_pr_page, apply_pr_page),
    "profile_batch": (fetch_profile_batch, apply_profile_batch),
    "lookup": (fetch_lookup, apply_lookup),
    "placements": (fetch_placements, apply_placements),
    "teammates": (fetch_teammates, apply_teammates),
    "series_candidates": (fetch_series_candidates, apply_series_candidates),
    "series_check": (fetch_series_check, apply_series_check),
    "team": (fetch_team, apply_team),
    "standings_page": (fetch_standings_page, apply_standings_page),
    "sgg_sets": (fetch_sgg_sets, apply_sgg_sets),
    "sgg_pools": (fetch_sgg_pools, apply_sgg_pools),
    "sgg_phase_pools": (fetch_sgg_phase_pools, apply_sgg_phase_pools),
    "sgg_pool_sets": (fetch_sgg_pool_sets, apply_sgg_pool_sets),
    "sgg_games": (fetch_sgg_games, apply_sgg_games),
    "cm_entrants": (fetch_cm_entrants, apply_cm_entrants),
    "cm_bracket": (fetch_cm_bracket, apply_cm_bracket),
}
STAGE_OF = {kind: "brackets" for kind in ("sgg_sets", "sgg_phase_pools", "sgg_pool_sets", "sgg_games")}
REPLAN = {"brackets"}  # stages whose own tasks find work for their planner (pools found by pool tasks)
EVENT_STAGES = {"brackets", "cm", "lookups", "proseries"}  # the stages --event can limit
UNPLANNED = {  # work a stage would add on its next run, as earlier stages find more
    "profiles": "SELECT COUNT(*) FROM crawl_players WHERE profile = 0",
    "lookups": "SELECT COUNT(*) FROM (SELECT DISTINCT 'startgg' AS platform, CAST(sgg_player_id AS TEXT) AS id"
               " FROM crawl_standings WHERE sgg_player_id IS NOT NULL UNION SELECT 'challengermode', user_id"
               " FROM crawl_cm_entrants) x WHERE NOT EXISTS (SELECT 1 FROM crawl_platform_players c"
               " WHERE c.platform = x.platform AND c.platform_player_id = x.id AND c.status > 0)",
    "histories": "SELECT COUNT(*) FROM crawl_players WHERE history_planned = 0",
    "proseries": "SELECT COUNT(*) FROM crawl_events e WHERE event_id LIKE 'series/%' AND NOT EXISTS"
                 " (SELECT 1 FROM tasks WHERE stage = 'proseries' AND (task_key LIKE 'series_check:' || e.event_id || ':%'"
                 " OR task_key LIKE 'series_candidates:' || e.event_id || ':%'))",
    "teams": "SELECT COUNT(*) FROM crawl_pairs WHERE planned = 0",
    "brackets": "SELECT (SELECT COUNT(*) FROM crawl_events e WHERE host = 'SGG' AND event_id LIKE 'tournament/%'"
                " AND NOT EXISTS (SELECT 1 FROM tasks WHERE task_key = 'sgg_sets:' || e.event_id || ':1'))"
                " + (SELECT COUNT(*) FROM crawl_pools WHERE planned = 0 AND event_id IN"
                " (SELECT event_id FROM crawl_brackets WHERE by_pool = 1))",
    "cm": "SELECT COUNT(*) FROM crawl_events e WHERE host = 'CM' AND NOT EXISTS"
          " (SELECT 1 FROM tasks WHERE task_key = 'cm_entrants:' || e.event_id)",
}


def remaining(db, stage):
    return db.execute("SELECT COUNT(*) FROM tasks WHERE stage = ? AND (status IN ('pending', 'running')"
                      " OR (status = 'failed' AND attempts < ?))", (stage, MAX_ATTEMPTS)).fetchone()[0]


def run_stage(db, api, stage, args, log, stop, on_task=None):
    """Plan a stage, then run its tasks until none are left or a stop is requested.

    Returns 'finished' or 'stopped'. on_task, if given, is called after each task; the CLI
    uses it for the run's heartbeat, and tests to stop part-way.
    """
    queue = TaskQueue(db)
    interrupted, retried = queue.requeue(stage)
    if interrupted or retried:
        log(f"Pending again: {interrupted} task(s) an interrupted run left running, {retried} failed task(s) to retry")
    with db:
        STAGES[stage][1](db, queue, args)
    total = remaining(db, stage)
    log(f"{stage}: {total} task(s) to run")
    counts = {"done": 0, "failed": 0, "rejected": 0}
    in_a_row, started, last_report = 0, time.monotonic(), time.monotonic()
    while not stop.requested:
        claimed = queue.claim(stage)
        if not claimed and stage in REPLAN:  # tasks may have found more work to plan
            with db:
                STAGES[stage][1](db, queue, args)
            claimed = queue.claim(stage)
            if claimed:
                log(f"{stage}: planned {remaining(db, stage)} more task(s) from what this run found")
        if not claimed:
            break
        key, kind, params = claimed
        fetch, apply = KINDS[kind]
        api.task = key
        try:
            result = fetch(api, params, log)
            with db:  # the task's findings, its follow-ups and its status are written together
                for follow in apply(db, params, result):
                    queue.add(*follow)
                queue.set_status(key, "done")
            status = "done"
        except Exception as e:
            if isinstance(e, ApiError):  # 404: nothing there; other 4xx: rejected; refused credentials, 429, 5xx or no response: failed
                status = ("done" if e.status == 404 else
                          "rejected" if e.status and e.status < 500 and e.status not in (401, 403, 429) else "failed")
                error = None if status == "done" else str(e)[:500]
            else:  # a bug or an unexpected response
                status, error = "failed", f"{type(e).__name__}: {e}"[:500]
            with db:
                queue.set_status(key, status, error)
            if error:
                log(f"  {status}: {key}: {error}")
        counts[status] += 1
        in_a_row = in_a_row + 1 if status == "failed" else 0
        if in_a_row >= 10:
            log("10 failures in a row, so stopping. Check the network and the last error, then re-run the same command.")
            return "stopped"
        if on_task:
            on_task()
        if time.monotonic() - last_report >= 30:
            last_report = time.monotonic()
            left, rate = remaining(db, stage), sum(counts.values()) / (time.monotonic() - started)
            log(f"  {sum(counts.values())} run ({counts['failed']} failed, {counts['rejected']} rejected),"
                f" {left} left, {api.requests_made} requests, about {left / rate / 60:.0f} min to go")
    left = remaining(db, stage)
    log(f"{stage}: {counts['done']} done, {counts['failed']} failed, {counts['rejected']} rejected, {left} left;"
        f" {api.requests_made} requests made, {api.cache_hits} answered from the cache,"
        f" {time.monotonic() - started:.0f} s")
    if left or stop.requested:
        if counts["failed"] and not stop.requested:
            log("Re-run the same command to retry the failed tasks.")
        return "stopped"
    check = STAGES[stage][2]
    if check and not check(db, api, log):
        log("The check above found a problem; what was fetched is kept.")
        return "stopped"
    return "finished"


def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def show_status(db):
    tasks = {}
    for stage, status, n in db.execute("SELECT stage, status, COUNT(*) FROM tasks GROUP BY stage, status"):
        tasks.setdefault(stage, {})[status] = n
    requests = {stage: (n, size or 0) for stage, n, size in db.execute(
        "SELECT COALESCE(t.stage, substr(r.task, 1, instr(r.task, ':') - 1), 'other'), COUNT(*), SUM(r.bytes)"
        " FROM requests r LEFT JOIN tasks t ON t.task_key = r.task GROUP BY 1")}
    print(f"{'Stage':<13}{'Tasks':>8}{'Done':>8}{'Left':>8}{'Failed':>8}{'To plan':>9}{'Requests':>10}{'Cache':>10}")
    for name, (number, _, _, _) in STAGES.items():
        t = tasks.get(name, {})
        left = remaining(db, name)
        failed = t.get("failed", 0) + t.get("rejected", 0)
        unplanned = db.execute(UNPLANNED[name]).fetchone()[0] if name in UNPLANNED else 0
        n, size = requests.get(name, (0, 0))
        print(f"{number:>2} {name:<10}{sum(t.values()):>8}{t.get('done', 0):>8}{left:>8}{failed:>8}"
              f"{unplanned:>9}{n:>10}{human_bytes(size):>10}")
        last = db.execute("SELECT task_key, last_error, updated_at FROM tasks WHERE stage = ?"
                          " AND status IN ('failed', 'rejected') ORDER BY updated_at DESC LIMIT 1", (name,)).fetchone()
        if last:
            print(f"   last error {last[2]}: {last[0]}: {last[1][:150]}")
    found = dict(db.execute("SELECT found_by, COUNT(*) FROM crawl_players GROUP BY found_by").fetchall())
    print(f"\nPlayers known: {sum(found.values())} ({', '.join(f'{n} from {k}' for k, n in sorted(found.items()))});"
          f" pairs: {db.execute('SELECT COUNT(*) FROM crawl_pairs').fetchone()[0]};"
          f" player-event entries: {db.execute('SELECT COUNT(*) FROM crawl_entries').fetchone()[0]}")
    brackets = dict((p, (e, m)) for p, e, m in db.execute(
        "SELECT b.platform, COUNT(*), (SELECT COUNT(*) FROM crawl_matches m JOIN crawl_brackets c USING (event_id)"
        " WHERE c.platform = b.platform) FROM crawl_brackets b GROUP BY b.platform"))
    looked_up = dict(db.execute("SELECT status, COUNT(*) FROM crawl_platform_players WHERE status >= 2 GROUP BY status"))
    print(f"Brackets: start.gg {brackets.get('startgg', (0, 0))[0]} events, {brackets.get('startgg', (0, 0))[1]} sets;"
          f" Challengermode {brackets.get('challengermode', (0, 0))[0]} events,"
          f" {brackets.get('challengermode', (0, 0))[1]} matches."
          f" Lookups: {looked_up.get(2, 0)} found, {looked_up.get(3, 0)} not in the Stats API."
          f" Pro Series placements: {db.execute('SELECT COUNT(*) FROM crawl_series_placements').fetchone()[0]}")
    local = lambda stamp: datetime.fromisoformat(stamp).astimezone().strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    for stage, api, pid, started, heartbeat, outcome, finished in db.execute(
            "SELECT stage, api, pid, started_at, heartbeat_at, outcome, finished_at FROM runs ORDER BY run_id DESC LIMIT 4"):
        state = (f"{outcome} at {local(finished)}" if finished else
                 f"running now (last heartbeat {local(heartbeat)})" if pid_alive(pid) else
                 "ended without finishing; re-running it resumes")
        print(f"Run: {stage} ({api}), started {local(started)}, {state}")


def make_logger(stage):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"crawl.{stage}")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_DIR / f"crawl-{stage}.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger.info


def main():
    sys.stdout.reconfigure(errors="replace")  # player names can't always be printed in the console's code page
    parser = argparse.ArgumentParser(description="Run one stage of the crawl, or show progress.")
    parser.add_argument("stage", choices=["status", *STAGES])
    parser.add_argument("--sample", type=int, help="histories only: plan just this many PR players (the pilot)")
    parser.add_argument("--event", action="append", metavar="ID",
                        help="brackets, cm, lookups, proseries: only this event (repeat for more); for a pilot")
    parser.add_argument("--max-pools", type=int, metavar="N",
                        help="brackets: only the first N pools of each phase of an event fetched pool by pool")
    parser.add_argument("--retry-rejected", action="store_true",
                        help="put this stage's rejected tasks back in the queue first, once their cause is fixed")
    args = parser.parse_args()
    db = connect(schema=CRAWL_SCHEMA)
    migrate(db)
    if args.stage == "status":
        show_status(db)
        return
    if args.event and args.stage not in EVENT_STAGES:
        parser.error(f"--event works with {', '.join(sorted(EVENT_STAGES))}")
    if args.max_pools is not None and args.stage != "brackets":
        parser.error("--max-pools works with brackets only")
    unknown = [e for e in args.event or [] if not db.execute("SELECT 1 FROM crawl_events WHERE event_id = ?", (e,)).fetchone()]
    if unknown:
        parser.error(f"not an official event: {', '.join(unknown)}")
    log = make_logger(args.stage)
    api_name = STAGES[args.stage][3]
    lock = RunLock(db, args.stage, api_name)
    lock.acquire()
    if args.retry_rejected:
        log(f"{TaskQueue(db).retry_rejected(args.stage)} rejected task(s) back in the queue")
    stop = StopFlag()
    stop.install(log)
    outcome = "crashed"
    try:
        outcome = run_stage(db, CLIENTS[api_name](), args.stage, args, log, stop, on_task=lock.heartbeat)
    except KeyboardInterrupt:
        outcome = "interrupted"
        log("Stopped at once; re-run the same command to continue.")
    finally:
        lock.release(outcome)
    log(f"Run {outcome}.")
    sys.exit(0 if outcome == "finished" else 1)


if __name__ == "__main__":
    main()
