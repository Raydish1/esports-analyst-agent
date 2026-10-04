"""Survey of the start.gg and Challengermode APIs: what they add on top of the Stats API
(bracket structure, entrants and standings, prize information).

Every response is saved under data/raw/platforms/<platform>/ (git-ignored), with a
_manifest.json per platform. A few Stats API calls, used to compare match data, go to
data/raw/platforms/statsapi_compare/. Findings are in docs/platform-api-survey.md.

Credentials come from .env (see .env.example) and are never printed or saved.
Usage: python ingest/survey_platforms.py
"""

import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from platform_clients import RAW_DIR, USER_AGENT, Challengermode, Recorder, StartGG, load_env

# Test cases. Stats API IDs are from docs/api-survey.md.
SGG_TOURNAMENT = "brawlhalla-world-championship-expo-2022"
SGG_EVENTS = {
    "bcx2022_1v1": "tournament/brawlhalla-world-championship-expo-2022/event/1v1",
    "bcx2022_2v2": "tournament/brawlhalla-world-championship-expo-2022/event/2v2",
    "na_winter_2025_1v1": "tournament/winter-championship-north-america-2025/event/brawlhalla-championship-1v1",
}
SGG_PLAYERS = {"raydish": 1749170, "boomie": 153043, "marckiem00": 2339938, "megd": 1387617, "impala": 1336840}
CM_TOURNAMENT = "fcb7a286-3f0c-4f68-f9a5-08ded4cb1c05"  # Autumn Championship - North America 2026 - 1v1
CM_PLAYERS = {
    "raydish": "2914557c-90d4-41f4-a58f-73863728667d",
    "marckiem00": "bf544dc0-9e67-4b27-b453-80099bf450cd",
    "megd": "6c92f7c2-e989-404e-a83b-5ed975302322",
    "hexoo": "690a71b2-3e8a-470a-bce0-0b8e4bbbfded",
    "impala": "09636bc1-090e-4a84-b756-ddfbccb116a2",
}
STATS_API_MATCH_RAYDISH_HEXOO = "f706f954-346a-40fc-02a2-08df1591daff"  # Stats API matchId at CM_TOURNAMENT
STATS_API_MATCH_RAYDISH_ZERO_ZERO = "35b308e4-448c-4b1e-0136-08df1591daff"  # scored 0-0 in the Stats API
CM_2025_TOURNAMENTS = {  # tournamentsForSpace only returned 2026 events
    "bcx2025_1v1": "c979b223-7428-4534-97f9-08dd8e232c2e",
    "spring_sea_2025_1v1": "bf29e044-fe33-4882-4209-08dd69fad61e",
}
STATS_API_PLAYER = {"raydish": 160000, "impala": 168635}
AFTER_STATS_API_SGG = 1749945600  # 2025-06-15; the Stats API's last start.gg event is CEO 2025 (2025-06-14)
BRAWLHALLA = 15  # start.gg videogame ID

INTROSPECTION = """
query Introspect { __schema {
  queryType { name } mutationType { name }
  types { kind name description
    fields(includeDeprecated: true) { name description isDeprecated
      args { name type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
      type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
    inputFields { name description type { kind name ofType { kind name ofType { kind name } } } }
    enumValues(includeDeprecated: true) { name description }
    possibleTypes { name } } } }"""

# --- start.gg queries ----------------------------------------------------------------

SGG_Q_TOURNAMENT = """
query Tournament($slug: String!) { tournament(slug: $slug) {
  id name slug url absoluteUrl: url(relative: false) startAt endAt currency numAttendees isOnline rules
  owner { id slug }
  events { id name slug numEntrants competitionTier type state startAt isOnline videogame { id name } } } }"""

SGG_Q_EVENT = """
query Event($slug: String!) { event(slug: $slug) {
  id name slug numEntrants competitionTier isOnline state startAt type entryFee
  teamRosterSize { minPlayers maxPlayers }
  prizingInfo rulesMarkdown matchRulesMarkdown
  league { id slug name }
  tournament { id slug url currency rules }
  phases { id name phaseOrder bracketType numSeeds groupCount state isExhibition }
  phaseGroups { id displayIdentifier bracketType bracketUrl numRounds state startAt
    phase { id name phaseOrder } rounds { number bestOf } } } }"""

SGG_Q_STANDINGS = """
query Standings($slug: String!, $page: Int!) { event(slug: $slug) {
  standings(query: {page: $page, perPage: 64}) {
    pageInfo { total totalPages }
    nodes { placement isFinal
      entrant { id name initialSeedNum isDisqualified
        participants { id gamerTag prefix player { id gamerTag } } } } } } }"""

SGG_Q_SETS = """
query Sets($slug: String!, $page: Int!) { event(slug: $slug) {
  sets(page: $page, perPage: 40, sortType: ROUND) {
    pageInfo { total totalPages }
    nodes { id round fullRoundText identifier displayScore winnerId state totalGames setGamesType
      wPlacement lPlacement startedAt completedAt vodUrl
      phaseGroup { id displayIdentifier phase { id name phaseOrder } }
      slots { slotIndex prereqType entrant { id name }
        standing { placement stats { score { label value } } } seed { seedNum } } } } } }"""

SGG_Q_PHASE_GAMES = """
query PhaseGames($phaseId: ID!) { phase(id: $phaseId) { id name
  sets(page: 1, perPage: 16, sortType: ROUND) {
    pageInfo { total }
    nodes { id fullRoundText displayScore winnerId totalGames
      games { orderNum winnerId entrant1Score entrant2Score stage { id name }
        selections { entrant { id } character { id name } } } } } } }"""

SGG_Q_SEEDS = """
query Seeds($phaseId: ID!) { phase(id: $phaseId) { id name
  seeds(query: {page: 1, perPage: 32}) {
    pageInfo { total }
    nodes { seedNum placement isBye entrant { id name } phaseGroup { displayIdentifier } } } } }"""

SGG_Q_PLAYER = """
query Player($id: ID!) { player(id: $id) { id gamerTag prefix
  user { slug }
  recentStandings(videogameId: 15, limit: 5) { placement container { __typename ... on Event { slug name startAt } } }
  sets(page: 1, perPage: 5) { pageInfo { total } nodes { id displayScore event { slug } } } } }"""

SGG_Q_TOURNAMENTS_AFTER = """
query BrawlhallaTournaments($page: Int!, $after: Timestamp!) {
  tournaments(query: {page: $page, perPage: 50, sortBy: "startAt asc",
                      filter: {videogameIds: [15], afterDate: $after, past: true}}) {
    pageInfo { total totalPages }
    nodes { id name slug startAt numAttendees isOnline countryCode owner { id slug }
      events(filter: {videogameId: [15]}) { id name slug numEntrants competitionTier type state startAt } } } }"""

# --- Challengermode queries ----------------------------------------------------------

CM_Q_TOURNAMENT = """
query Tournament($id: UUID!) { tournament(tournamentId: $id) {
  id name state description contactUrl
  links { overviewUrl }
  hosts { spaces { id name slug verified } }
  gameTitle { id slug title }
  schedule { scheduledStartTimeAt startedAt endedAt }
  attendance { availableSlotCount confirmedLineupCount roster { lineupCount userCount } }
  settings { tournamentSettings { format maxLineupCount maxLineupSize } }
  stages { index format lineupCount
    ... on TournamentEliminationStage { brackets { title labels roundCount
      rounds { roundNumber title labels matchCount lineupCount advancingLineupCount isLastRound } } } } } }"""

CM_Q_ROSTER = """
query Roster($id: UUID!) { tournament(tournamentId: $id) { id
  attendance { roster { lineupCount userCount
    lineups(limit: 600) { id name seed preSeed disqualified
      placement { bestPlacement worstPlacement displayPlacement }
      members { gameAccountId captain user { id username } } } } } } }"""

CM_Q_BRACKET = """
query Bracket($id: UUID!) { tournament(tournamentId: $id) { id
  stages { index format
    ... on TournamentEliminationStage { brackets { title labels
      rounds { roundNumber title labels
        matchSeries { id ordinal state bestOf startedAt labels
          lineups { id name seed disqualified members { user { id } } }
          results { final draw lineupResults { lineupNumber score placement final } } } } } } } } }"""

CM_Q_MATCH_SERIES = """
query MatchSeries($id: UUID!) { matchSeries(matchSeriesId: $id) {
  id ordinal state bestOf startedAt title labels
  lineups { id name seed disqualified placement { displayPlacement }
    members { gameAccountId user { id username } } }
  results { final draw lineupResults { lineupNumber score placement final } }
  matches(includeFailed: true) { id state name
    results { final draw lineupResults { lineupNumber score placement } } } } }"""

CM_Q_MATCH = """
query Match($id: UUID!) { match(matchId: $id) { id state name
  lineups { number lineupName missedReadyCheck members { user { id username } } }
  results { final draw lineupResults { lineupNumber score placement final } } } }"""

CM_Q_GAME_TOURNAMENTS = """
query GameTournaments($game: String!, $after: DateTime!) {
  tournamentsForGame(input: {gameSlug: $game,
                             tournamentFilter: {completedTournamentSelector: {tournamentsAfter: $after}}}) {
    id name state hosts { spaces { name slug } } schedule { startedAt } attendance { confirmedLineupCount } } }"""

CM_Q_USER = """
query User($id: UUID!) { user(userId: $id) { id username profileUrl createdAt
  connectedAccounts { provider id }
  gameAccounts(first: 10) { totalCount nodes { id displayName gameTitle { slug title } } } } }"""

CM_Q_SPACE_TOURNAMENTS = """
query SpaceTournaments($space: UUID!, $after: DateTime!) {
  tournamentsForSpace(input: {spaceId: $space,
                              tournamentFilter: {completedTournamentSelector: {tournamentsAfter: $after}}}) {
    id name state schedule { startedAt endedAt } attendance { confirmedLineupCount } } }"""

CM_Q_DESCRIPTION = """
query Description($id: UUID!) { tournament(tournamentId: $id) { id name description links { overviewUrl } } }"""


class StatsApi:
    """Plain GETs against the Stats API, for comparing match data."""

    base = "https://api.brawltools.com/v2"

    def __init__(self):
        self.recorder = Recorder("statsapi_compare")
        self.last = 0.0

    def get(self, label, path, params=None):
        delay = 0.6 - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                status, raw = res.status, res.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"_nonJsonBody": raw.decode("utf-8", "replace")[:2000]}
        self.recorder.save(label, body, {"label": label, "url": url, "status": status})
        print(f"[stats] {status} {label}")
        return status, body


def dig(body, *keys):
    for key in keys:
        body = (body or {}).get(key) if isinstance(body, dict) else None
    return body


def sgg_pages(sgg, label, query, variables, path, max_pages=60):
    """Fetch every page of a paginated start.gg connection; returns all nodes."""
    nodes, page = [], 1
    while page <= max_pages:
        _, body = sgg.query(f"{label}__p{page:02d}", query, {**variables, "page": page})
        conn = dig(body, "data", *path) or {}
        nodes += conn.get("nodes") or []
        if page >= ((conn.get("pageInfo") or {}).get("totalPages") or 0):
            break
        page += 1
    return nodes


def survey_startgg(sgg, stats):
    sgg.query("introspection", INTROSPECTION)
    sgg.query("tournament__bcx2022", SGG_Q_TOURNAMENT, {"slug": SGG_TOURNAMENT})

    events = {}
    for key, slug in SGG_EVENTS.items():
        _, body = sgg.query(f"event__{key}", SGG_Q_EVENT, {"slug": slug})
        event = dig(body, "data", "event") or {}
        standings = sgg_pages(sgg, f"standings__{key}", SGG_Q_STANDINGS, {"slug": slug}, ["event", "standings"])
        sets = sgg_pages(sgg, f"sets__{key}", SGG_Q_SETS, {"slug": slug}, ["event", "sets"])
        phases = sorted(event.get("phases") or [], key=lambda p: p.get("phaseOrder") or 0)
        if phases:
            sgg.query(f"games__{key}__last_phase", SGG_Q_PHASE_GAMES, {"phaseId": phases[-1]["id"]})
            sgg.query(f"seeds__{key}__first_phase", SGG_Q_SEEDS, {"phaseId": phases[0]["id"]})
        events[key] = {"event": event, "standings": standings, "sets": sets}

    for name, player_id in SGG_PLAYERS.items():
        sgg.query(f"player__{name}", SGG_Q_PLAYER, {"id": player_id})

    sgg_pages(sgg, "brawlhalla_tournaments_after_2025-06-15", SGG_Q_TOURNAMENTS_AFTER,
              {"after": AFTER_STATS_API_SGG}, ["tournaments"], max_pages=40)

    # Compare with the Stats API: the winner's matches, and one DQ'd set.
    slug = SGG_EVENTS["bcx2022_1v1"]
    stats.get("player_match__impala__bcx2022_1v1", "/player/match",
              {"playerIds": STATS_API_PLAYER["impala"], "tournamentId": slug})
    bcx = events["bcx2022_1v1"]
    entrant_players = {
        s["entrant"]["id"]: [p["player"]["id"] for p in s["entrant"].get("participants") or [] if p.get("player")]
        for s in bcx["standings"] if s.get("entrant")
    }
    dq_set = next((s for s in bcx["sets"] if "DQ" in (s.get("displayScore") or "")), None)
    if dq_set:
        for slot in dq_set.get("slots") or []:
            for sgg_player in entrant_players.get((slot.get("entrant") or {}).get("id"), []):
                _, body = stats.get(f"player_by_sggid__{sgg_player}", f"/player/sggId/{sgg_player}")
                player_id = dig(body, "player", "playerId")
                if player_id:
                    stats.get(f"player_match__{player_id}__bcx2022_1v1__dq_set_{dq_set['id']}", "/player/match",
                              {"playerIds": player_id, "tournamentId": slug})
                    return
    print("no DQ'd set found to compare")


def survey_challengermode(cm, stats):
    cm.query("introspection", INTROSPECTION)
    _, body = cm.query("tournament__autumn_na_2026_1v1", CM_Q_TOURNAMENT, {"id": CM_TOURNAMENT})
    tournament = dig(body, "data", "tournament") or {}
    cm.query("roster__autumn_na_2026_1v1", CM_Q_ROSTER, {"id": CM_TOURNAMENT})
    _, body = cm.query("bracket__autumn_na_2026_1v1", CM_Q_BRACKET, {"id": CM_TOURNAMENT})

    series = []
    for stage in dig(body, "data", "tournament", "stages") or []:
        for bracket in stage.get("brackets") or []:
            for rnd in bracket.get("rounds") or []:
                for ms in rnd.get("matchSeries") or []:
                    series.append({**ms, "_bracket": bracket.get("title"), "_round": rnd.get("title")})

    # Full detail (games included) for the grand final, Raydish's loss to Hexoo, and a DQ.
    def has_user(ms, user_id):
        return any((m.get("user") or {}).get("id") == user_id for lu in ms.get("lineups") or [] if lu
                   for m in lu.get("members") or [])
    picks = {
        "grand_final": next((ms for ms in reversed(series) if ms["_bracket"] == "Grand finals"), None),
        "raydish_vs_hexoo": next((ms for ms in series if has_user(ms, CM_PLAYERS["raydish"])
                                  and has_user(ms, CM_PLAYERS["hexoo"])), None),
        "dq_or_nullified": next((ms for ms in series if ms.get("state") == "NULLIFIED"
                                 or any(lu and lu.get("disqualified") for lu in ms.get("lineups") or [])), None),
    }
    for label, ms in picks.items():
        if ms:
            cm.query(f"match_series__{label}", CM_Q_MATCH_SERIES, {"id": ms["id"]})

    # Is the Stats API's matchId a Challengermode match ID? And how does a 0-0 "win" look?
    cm.query("match__statsapi_matchid", CM_Q_MATCH, {"id": STATS_API_MATCH_RAYDISH_HEXOO})
    cm.query("match__statsapi_zero_zero", CM_Q_MATCH, {"id": STATS_API_MATCH_RAYDISH_ZERO_ZERO})
    stats.get("player_match__raydish__autumn_na_2026_1v1", "/player/match",
              {"playerIds": STATS_API_PLAYER["raydish"], "tournamentId": CM_TOURNAMENT})
    dq = picks["dq_or_nullified"]
    if dq:
        member = next(((m.get("user") or {}).get("id") for lu in dq.get("lineups") or [] if lu
                       for m in lu.get("members") or [] if (m.get("user") or {}).get("id")), None)
        if member:
            _, body = stats.get(f"player_by_cmid__{member}", f"/player/cmId/{member}")
            player_id = dig(body, "player", "playerId")
            if player_id:
                stats.get(f"player_match__{player_id}__autumn_na_2026_1v1__dq_series", "/player/match",
                          {"playerIds": player_id, "tournamentId": CM_TOURNAMENT})

    for name, user_id in CM_PLAYERS.items():
        cm.query(f"user__{name}", CM_Q_USER, {"id": user_id})

    space = ((tournament.get("hosts") or {}).get("spaces") or [{}])[0].get("id")
    if space:
        _, body = cm.query("space_tournaments__brawlhalla_esports", CM_Q_SPACE_TOURNAMENTS,
                           {"space": space, "after": "2025-01-01T00:00:00Z"})
        listed = dig(body, "data", "tournamentsForSpace") or []
        listed = sorted((t for t in listed if t["id"] != CM_TOURNAMENT),
                        key=lambda t: (t.get("schedule") or {}).get("startedAt") or "")
        step = max(1, len(listed) // 8)
        for t in listed[::step][:8]:  # prize text across the Challengermode era
            cm.query(f"description__{t['id']}", CM_Q_DESCRIPTION, {"id": t["id"]})
        # Is the list capped or windowed? Same space, later cut-off.
        cm.query("space_tournaments__after_2026-06-01", CM_Q_SPACE_TOURNAMENTS,
                 {"space": space, "after": "2026-06-01T00:00:00Z"})
    for label, tournament_id in CM_2025_TOURNAMENTS.items():
        cm.query(f"description__{label}", CM_Q_DESCRIPTION, {"id": tournament_id})
    # Does the game-wide list include community tournaments?
    cm.query("game_tournaments__brawlhalla_after_2026-09-01", CM_Q_GAME_TOURNAMENTS,
             {"game": "brawlhalla", "after": "2026-09-01T00:00:00Z"})


def main():
    load_env()
    for sub in ("startgg", "challengermode", "statsapi_compare"):
        shutil.rmtree(RAW_DIR / sub, ignore_errors=True)
    stats = StatsApi()
    sgg = StartGG()
    cm = Challengermode()
    try:
        survey_startgg(sgg, stats)
        survey_challengermode(cm, stats)
    finally:
        for client in (sgg, cm, stats):
            client.recorder.write_manifest()
        (RAW_DIR / "challengermode" / "_token_log.json").write_text(json.dumps(cm.token_log, indent=2))


if __name__ == "__main__":
    main()
