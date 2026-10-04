# Database schema proposal

**Status: proposal for review. Nothing here is implemented.**

**Scope: official events only** (decided 2026-10-03). Community events can be added later without changing the schema.

This proposal builds on [`api-survey.md`](api-survey.md) and on the rules already decided in [`CLAUDE.md`](../CLAUDE.md).

## Design choices at a glance

1. **SQLite, rebuilt from a raw cache.** The database is one disposable file in `data/db/`. It is rebuilt from cached API responses without calling the API again. The data is small: about 1,800 events, and placements and matches in the hundreds of thousands at most. The DDL is written for SQLite; moving to Postgres would change a few functions, not the design.
2. **Two layers.**
   - A *fetcher* writes every API response to a cache.
   - A *builder* turns the cache, plus the curated files, into the database.

   Only the fetcher talks to the API.
3. **Python for the fetcher, not the Node SDK.** The API is plain unauthenticated HTTP GET. The SDK hides status codes, has a fixed 5-second timeout and never retries. A small Python client avoids all three and keeps the project in one language. The Node survey script stays as an exploration tool.
4. **One row per Stats API event.** The API's "Tournament" is one bracket in one mode, and there is no separate tournaments table:
   - start.gg tournament slugs also group unrelated league weeks and regional brackets (survey §6);
   - Challengermode events have no parent at all.

   The grouping that matters, phases of one competition, is curated.
5. **Facts in tables, rules in views.** Tables store what the API reported. Curated corrections and the decided rules are applied in `v_` views, and the agent queries the views.
6. **Platform IDs on the core tables, and a `source` on every row.** That lets start.gg, Challengermode and Esports Earnings data be added later without changing the core tables (§7).
7. **Hand-made data lives in CSV files** in `curation/` (tiers, nicknames, merges, overrides, known events). The builder loads them on every build, so a rebuild never loses them.

## 1. Schema

### Players

```sql
CREATE TABLE players (
  player_id      INTEGER PRIMARY KEY,   -- Stats API esports ID
  name           TEXT NOT NULL,         -- current display name (newest response)
  sgg_player_id  INTEGER,               -- start.gg player ID
  cm_player_id   TEXT,                  -- Challengermode user UUID
  brawlhalla_id  INTEGER,               -- in-game ID
  country        TEXT,
  twitter        TEXT,
  twitch         TEXT,
  source         TEXT NOT NULL DEFAULT 'stats_api',
  updated_at     TEXT NOT NULL          -- fetch time of the response this row came from
);
CREATE INDEX players_sgg ON players (sgg_player_id);
CREATE INDEX players_cm  ON players (cm_player_id);

CREATE TABLE player_aliases (
  alias      TEXT NOT NULL,      -- normalized: lowercase, no team tag, no punctuation
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  kind       TEXT NOT NULL,      -- 'display_name' | 'former_name' | 'without_tag' | 'nickname'
  shown_as   TEXT NOT NULL,      -- original spelling, e.g. 'ECHO | Marckiemoo'
  source     TEXT NOT NULL,      -- 'stats_api' | 'curated'
  PRIMARY KEY (alias, player_id)
);

CREATE TABLE player_merges (     -- curated: two records that are the same person
  player_id            INTEGER PRIMARY KEY REFERENCES players (player_id),
  canonical_player_id  INTEGER NOT NULL REFERENCES players (player_id),
  note                 TEXT
);
```

- **Missing IDs.** Player objects nested in matches and matchups arrive without `sggPlayerId`/`cmPlayerId`, so the builder never overwrites a known ID with null. Players first seen nested get their IDs from a batched `ListPlayers` call.
- **Aliases are how the agent finds players,** because the API's search misses inactive start.gg-era players.
  - The builder generates `display_name`, `without_tag` ("Pink | Guichabou" → "guichabou") and `former_name` rows. A former name is recorded when a later response shows a different name.
  - `nickname` rows come from `curation/player_aliases.csv`: "marckiemoo" → 146052, "hexo" → 169084, "sandstorm" → 74433 (gdsandstorm).
  - One alias can point to several players ("hardymj"); the agent should ask when it does.
- **Merges** handle one person having two records, e.g. a start.gg-era record plus a Challengermode-era one (survey §4). Views report merged players under the canonical ID.

### Events

```sql
CREATE TABLE tiers (               -- curated; you define the scale
  tier   TEXT PRIMARY KEY,         -- e.g. 'S'
  label  TEXT NOT NULL,            -- e.g. 'World Championship'
  rank   INTEGER NOT NULL          -- 1 = highest
);

CREATE TABLE events (
  event_id             TEXT PRIMARY KEY,  -- start.gg event slug, start.gg series slug (3 events) or Challengermode UUID
  host                 TEXT NOT NULL CHECK (host IN ('SGG', 'CM')),
  tournament_name      TEXT NOT NULL,
  event_name           TEXT,              -- always NULL for Challengermode
  sgg_tournament_slug  TEXT,              -- e.g. 'ceo-2025-6'; groups a start.gg tournament's events for display
  year                 INTEGER NOT NULL,
  start_time           INTEGER NOT NULL,  -- Unix seconds
  is_official          INTEGER NOT NULL,  -- 0/1, as reported
  is_twos              INTEGER NOT NULL,  -- 0/1, as reported (one known error; see mode_override)
  is_online            INTEGER NOT NULL,
  -- curated, from curation/events.csv; NULL means "no override"
  tier                 TEXT REFERENCES tiers (tier),
  format_override      TEXT,              -- beats format_rules for this event
  mode_override        TEXT CHECK (mode_override IN ('1v1', '2v2')),
  competition_id       TEXT,              -- shared by the phases of one competition
  phase_order          INTEGER,           -- 1, 2, ... within a competition
  bracket_url          TEXT GENERATED ALWAYS AS (
                         CASE
                           WHEN host = 'SGG' AND event_id LIKE 'tournament/%'
                             THEN 'https://www.start.gg/' || event_id || '/brackets'
                           WHEN host = 'CM'
                             THEN 'https://www.challengermode.com/s/Brawlhalla/tournaments/' || event_id
                         END) VIRTUAL,            -- NULL for the 'series/...' IDs (no working URL)
  source               TEXT NOT NULL DEFAULT 'stats_api',
  fetched_at           TEXT NOT NULL
);
CREATE INDEX events_start ON events (start_time);

CREATE TABLE event_aliases (       -- curated: names people use for events
  alias     TEXT NOT NULL,         -- normalized, e.g. 'bcx 2022', 'worlds 2019'
  event_id  TEXT NOT NULL REFERENCES events (event_id),
  PRIMARY KEY (alias, event_id)
);
```

- **Curated values in this table:**
  - **The tier list** sits on top of `is_official`. The survey decided that a "major" is any official event, and `tier` adds finer cuts (Worlds, regional championships, …).
  - **The known mode error:** CEO Dreamland 2017's doubles event gets `mode_override = '2v2'`.
  - **Phases:** Brawl League Masters Season 4 NA and EU get a shared `competition_id`, with `phase_order` 1 (Swiss) and 2 (Top 8 Finals).
- **Event aliases** cover names that don't appear in the data. "BCX" never appears in "Brawlhalla World Championship Expo", and the 2019 Worlds is stored as "DreamHack Atlanta 2019".

**Bracket URL formats** (checked on 2026-10-03):

| Platform | URL | How it was checked |
|---|---|---|
| start.gg | `https://www.start.gg/{slug}/brackets`, e.g. `https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/1v1/brackets` | Returns 200 with the page title "… \| Brackets". `https://www.start.gg/{slug}` is the event overview. `start.gg` without `www` redirects there. A made-up slug returns 404. |
| Challengermode | `https://www.challengermode.com/s/Brawlhalla/tournaments/{uuid}` | Returns 200 with the title "Autumn Championship - North America 2026 - 1v1 - Overview - Tournament \| Challengermode". `…/tournaments/{uuid}` without `/s/Brawlhalla` redirects there, and `…/{uuid}/matches` lists the matches. `…/bracket` and `…/brackets` return 404, so the tournament page itself is the bracket link. A made-up UUID returns 404. |
| start.gg series | none | The three Pro Series finals have IDs like `series/pro-series-2021-na`. Both `https://www.start.gg/series/pro-series-2021-na` and `…/brackets` return 404, so `bracket_url` is NULL for them unless a link is curated. |

### Placements and 2v2 teams

```sql
CREATE TABLE teams (               -- a 2v2 pair, order-independent
  team_id     INTEGER PRIMARY KEY,
  player1_id  INTEGER NOT NULL REFERENCES players (player_id),
  player2_id  INTEGER NOT NULL REFERENCES players (player_id),
  CHECK (player1_id < player2_id),
  UNIQUE (player1_id, player2_id)
);

CREATE TABLE placements (
  event_id    TEXT NOT NULL REFERENCES events (event_id),
  player_id   INTEGER NOT NULL REFERENCES players (player_id),
  placement   INTEGER NOT NULL,
  team_id     INTEGER REFERENCES teams (team_id),  -- 2v2, once the partner is known
  source      TEXT NOT NULL DEFAULT 'stats_api',
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (event_id, player_id)
);
CREATE INDEX placements_player ON placements (player_id);
```

- A player's 2v2 placement doesn't name the partner. `team_id` is filled in from team queries (GetPlayerPlacements with both IDs), which return exactly the events a pair played together.
- There is no separate team-placement table. A team's result is the placement its two players share; see `v_team_results` in §2.

### Matches

```sql
CREATE TABLE matches (
  match_id      TEXT PRIMARY KEY,  -- start.gg set ID or Challengermode match UUID
  event_id      TEXT NOT NULL REFERENCES events (event_id),
  side1_score   INTEGER NOT NULL,  -- games won; -1 = DQ'd
  side2_score   INTEGER NOT NULL,
  is_dq         INTEGER GENERATED ALWAYS AS (side1_score < 0 OR side2_score < 0) VIRTUAL,
  dq_side       INTEGER GENERATED ALWAYS AS (
                  CASE WHEN side1_score < 0 AND side2_score < 0 THEN 0   -- both sides
                       WHEN side1_score < 0 THEN 1
                       WHEN side2_score < 0 THEN 2 END) VIRTUAL,
  winner_side   INTEGER GENERATED ALWAYS AS (
                  CASE WHEN side1_score < 0 OR side2_score < 0 THEN NULL
                       WHEN side1_score > side2_score THEN 1
                       WHEN side2_score > side1_score THEN 2 END) VIRTUAL,
  start_time    INTEGER,           -- usually NULL in the Stats API
  legends_json  TEXT,              -- per side, per game, when reported
  maps_json     TEXT,
  source        TEXT NOT NULL DEFAULT 'stats_api',
  fetched_at    TEXT NOT NULL
);

CREATE TABLE match_players (
  match_id   TEXT NOT NULL REFERENCES matches (match_id),
  side       INTEGER NOT NULL CHECK (side IN (1, 2)),
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  PRIMARY KEY (match_id, player_id)
);
```

- **Sides.** The API returns each match from the side of the player who was requested: `scores` is `[theirs, opponent's]`, and `opponent` lists the other side. The builder puts that player on side 1 the first time it sees a match. When the same `matchId` comes back from the other side, the scores must match in reverse; that is a coverage check (§4).
- **2v2 partners.** In a 2v2 match record the requested player's own partner is missing. The builder adds the partner from `placements.team_id`.
- **DQs.** `is_dq` is the DQ flag. DQ matches stay in the table, because they happened, and are dropped in the record views (§2).

### Rankings

```sql
CREATE TABLE pr_snapshots (        -- a PR row as the Stats API reported it
  player_id      INTEGER NOT NULL REFERENCES players (player_id),
  mode           TEXT NOT NULL CHECK (mode IN ('1v1', '2v2')),
  as_of          TEXT NOT NULL,    -- ListPr lastUpdated
  region         TEXT,
  power_ranking  INTEGER,
  points         REAL,
  top8           INTEGER,
  top32          INTEGER,
  gold           INTEGER,
  silver         INTEGER,
  bronze         INTEGER,
  source         TEXT NOT NULL DEFAULT 'stats_api',
  PRIMARY KEY (player_id, mode, as_of)
);
```

PR rows are kept for questions about current rankings. They are **not** used for medals (survey §3); the earnings tables are in §6.

## 2. Views that apply the decided rules

| Rule | Where it's applied |
|---|---|
| Crew battles count as 1v1 | `v_events.counts_as` |
| Other non-standard formats count toward neither mode | `v_events.counts_as` is NULL; filtered out in `v_results` and `v_match_results` |
| A phased tournament counts once (last phase reached) | `v_results` |
| Medals are top-3 placements at official events | `v_medals`, `v_player_medals` |
| A major is an official event (`tier` refines it) | `v_major_wins` |
| DQs count as neither a win nor a loss | `v_match_results`, and therefore both head-to-head views |

The format rules are data, not code, so they can be adjusted without touching the views:

```sql
CREATE TABLE format_rules (        -- curated, from curation/format_rules.csv; lowest priority wins
  pattern   TEXT PRIMARY KEY,      -- LIKE pattern on lower(tournament_name || ' ' || event_name)
  format    TEXT NOT NULL,
  priority  INTEGER NOT NULL
);
-- Starting rules:
--   '%crew battle%'        crew_battle        1   (checked first: crew battle events are named "... Crew Battle 3v3")
--   '%triples%', '%trios%' triples            2
--   '%brawlball%'          brawlball          2
--   '%kung foot%'          kung_foot          2
--   '%volleybrawl%'        volleybrawl        2
--   '%snowbrawl%'          snowbrawl          2
--   '%capture the flag%'   capture_the_flag   2
--   '%morph%'              morph              2
--   '%3v3%'                3v3                3
-- Anything else is 'standard'. format_override handles exceptions.
```

```sql
-- Events with effective mode, format and whether they count.
CREATE VIEW v_events AS
SELECT x.*,
       CASE x.format
         WHEN 'standard'    THEN x.mode
         WHEN 'crew_battle' THEN '1v1'        -- crew battles count as 1v1
       END AS counts_as,                      -- NULL: counts toward neither mode
       date(x.start_time, 'unixepoch') AS start_date
FROM (
  SELECT e.*,
         COALESCE(e.mode_override, CASE WHEN e.is_twos = 1 THEN '2v2' ELSE '1v1' END) AS mode,
         COALESCE(e.format_override,
                  (SELECT r.format FROM format_rules r
                    WHERE lower(e.tournament_name || ' ' || COALESCE(e.event_name, '')) LIKE r.pattern
                    ORDER BY r.priority LIMIT 1),
                  'standard') AS format,
         COALESCE(e.competition_id, e.event_id) AS competition_key
  FROM events e
) x;

-- Every player record mapped to its canonical player.
CREATE VIEW v_player_ids AS
SELECT p.player_id, COALESCE(m.canonical_player_id, p.player_id) AS canonical_id
FROM players p
LEFT JOIN player_merges m ON m.player_id = p.player_id;

-- One result per player per competition that counts.
CREATE VIEW v_results AS
SELECT player_id, event_id, competition_key, mode, format, placement, team_id,
       is_official, tier, tournament_name, event_name, year, start_date, host, bracket_url
FROM (
  SELECT i.canonical_id AS player_id, p.placement, p.team_id,
         v.event_id, v.competition_key, v.counts_as AS mode, v.format, v.is_official, v.tier,
         v.tournament_name, v.event_name, v.year, v.start_date, v.host, v.bracket_url,
         ROW_NUMBER() OVER (PARTITION BY v.competition_key, i.canonical_id
                            ORDER BY COALESCE(v.phase_order, 0) DESC, v.start_time DESC) AS nth
  FROM placements p
  JOIN v_events v     ON v.event_id = p.event_id
  JOIN v_player_ids i ON i.player_id = p.player_id
  WHERE v.counts_as IS NOT NULL               -- other formats count toward neither mode
) ranked
WHERE nth = 1;                                -- phased competitions: last phase reached only

-- Medals: top-3 placements at official events.
CREATE VIEW v_medals AS
SELECT r.*,
       CASE r.placement WHEN 1 THEN 'gold' WHEN 2 THEN 'silver' ELSE 'bronze' END AS medal
FROM v_results r
WHERE r.is_official = 1 AND r.placement <= 3;

CREATE VIEW v_player_medals AS
SELECT player_id, mode,
       SUM(CASE WHEN placement = 1 THEN 1 ELSE 0 END) AS gold,
       SUM(CASE WHEN placement = 2 THEN 1 ELSE 0 END) AS silver,
       SUM(CASE WHEN placement = 3 THEN 1 ELSE 0 END) AS bronze,
       COUNT(*) AS medals
FROM v_medals
GROUP BY player_id, mode;

-- Major wins: first place at an official event (filter on tier for finer cuts).
CREATE VIEW v_major_wins AS
SELECT * FROM v_results WHERE is_official = 1 AND placement = 1;

-- 2v2 results by team.
CREATE VIEW v_team_results AS
SELECT DISTINCT r.team_id, t.player1_id, t.player2_id, r.event_id, r.competition_key,
       r.placement, r.is_official, r.tier, r.tournament_name, r.year, r.start_date
FROM v_results r
JOIN teams t ON t.team_id = r.team_id
WHERE r.mode = '2v2';

-- One row per player per match that counts. DQs excluded.
CREATE VIEW v_match_results AS
SELECT i.canonical_id AS player_id, m.match_id, mp.side, v.event_id, v.counts_as AS mode,
       v.is_official, v.start_date,
       CASE mp.side WHEN 1 THEN m.side1_score ELSE m.side2_score END AS games_won,
       CASE mp.side WHEN 1 THEN m.side2_score ELSE m.side1_score END AS games_lost,
       CASE WHEN m.winner_side = mp.side THEN 1 ELSE 0 END AS won
FROM matches m
JOIN match_players mp ON mp.match_id = m.match_id
JOIN v_player_ids i   ON i.player_id = mp.player_id
JOIN v_events v       ON v.event_id = m.event_id
WHERE m.is_dq = 0                             -- a DQ is neither a win nor a loss
  AND m.winner_side IS NOT NULL
  AND v.counts_as IS NOT NULL;

CREATE VIEW v_match_sides AS                  -- how many players are on each side
SELECT match_id, side, COUNT(*) AS players, MIN(player_id) AS low_id, MAX(player_id) AS high_id
FROM match_players
GROUP BY match_id, side;

-- 1v1 head-to-head: only matches with one player on each side.
CREATE VIEW v_head_to_head_1v1 AS
SELECT a.player_id, b.player_id AS opponent_id,
       SUM(a.won) AS wins, SUM(1 - a.won) AS losses,
       SUM(a.games_won) AS games_won, SUM(a.games_lost) AS games_lost,
       COUNT(*) AS matches
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
JOIN v_match_sides sa  ON sa.match_id = a.match_id AND sa.side = a.side AND sa.players = 1
JOIN v_match_sides sb  ON sb.match_id = b.match_id AND sb.side = b.side AND sb.players = 1
WHERE a.mode = '1v1'
GROUP BY a.player_id, b.player_id;

-- 2v2 head-to-head, team against team.
CREATE VIEW v_head_to_head_2v2 AS
SELECT ta.team_id, tb.team_id AS opponent_team_id,
       SUM(CASE WHEN m.winner_side = sa.side THEN 1 ELSE 0 END) AS wins,
       SUM(CASE WHEN m.winner_side = sb.side THEN 1 ELSE 0 END) AS losses,
       COUNT(*) AS matches
FROM matches m
JOIN v_events v      ON v.event_id = m.event_id AND v.counts_as = '2v2'
JOIN v_match_sides sa ON sa.match_id = m.match_id AND sa.players = 2
JOIN v_match_sides sb ON sb.match_id = m.match_id AND sb.players = 2 AND sb.side <> sa.side
JOIN teams ta ON ta.player1_id = sa.low_id AND ta.player2_id = sa.high_id
JOIN teams tb ON tb.player1_id = sb.low_id AND tb.player2_id = sb.high_id
WHERE m.is_dq = 0 AND m.winner_side IS NOT NULL
GROUP BY ta.team_id, tb.team_id;
```

**Crew battle matches.** Crew battles count as 1v1 for placements. `v_head_to_head_1v1` only counts matches with one player per side, so crew battle matches count toward 1v1 head-to-heads only if the API stores them as individual 1v1 games. If it stores them crew against crew, they're left out. The survey didn't fetch a crew battle match, so this needs one check during the crawl.

## 3. Crawl strategy

### Files

```text
data/raw/cache/<endpoint>/<key[:2]>/<key>.json.gz   one immutable file per response
data/db/crawl.sqlite                                request log and task queue
data/db/brawlhalla.sqlite                           the built database (disposable)
curation/*.csv                                      hand-made data
```

`key` is a hash of the endpoint and its normalized parameters (sorted, lists comma-joined).

### Stages

**Scope (decided): official events only.** Every list call passes `isOfficial=true`. Community events, and players who only played community events, are left out for now. The schema doesn't change if they're added later.

| Stage | Calls (rough) | Result |
|---|---|---|
| 0. Events: ListEvents for both modes with `isOfficial=true`, all pages; per-year crawls as a cross-check | ~13, plus ~20 | All 622 official events |
| 1. Seed: ListPr for NA, EU, SA, SEA and MENA × 1v1/2v2, 100 rows per page | ~70 | ~6,700 PR rows, roughly 4–5k ranked players, with their PR stats and earnings |
| 2. Profiles: ListPlayers in batches | 1 per batch | start.gg, Challengermode and in-game IDs |
| 3. Histories: GetPlayerPlacements (both modes, `isOfficial=true`) and GetPlayerTeammates (`isOfficial=true`) per player | ~2–4 per player | The official events each known player entered, and their partners |
| 4. Teams: GetPlayerPlacements with both IDs, per partner pair | 1 per pair | `team_id` on 2v2 placements |
| 5. Discovery: new players from official teammates and from opponents in official matches, sent back to stage 2 | — | Unranked and inactive players, such as Boomie |
| 6. Matches: GetPlayerMatches per (player, official event), de-duplicated by `matchId` | 1 per pair | Match-level results for official events |
| 7. Earnings gaps: SearchPlayers by name for unranked players with official results | 1 per player | Stats API earnings where search has them (players with a Challengermode account) |

- **Stage 6 dominates the cost,** at one call per (player, official event). Real sizes aren't known yet, so a pilot run of stages 0–4 will measure them first. At roughly one request per second, 10,000 calls take about 3 hours.
- **Three official events can't have match data:** the Pro Series 2019 NA and EU Finals and the Pro Series 2021 Finals use `series/…` IDs, which GetPlayerMatches rejects. Their placements still come through.

### The pagination bugs

- **Timestamp tokens (ListEvents, GetPlayerPlacements, GetPlayerTeammates).** Request the next page with `nextToken = last row's startTime + 1` rather than the server's token, and de-duplicate by ID.
  - That re-reads the boundary timestamp, so tied events can't be skipped.
  - Stop when a page adds nothing new.
  - If a *full* page adds nothing new (more ties than one page holds), fall back to the server token and log it.
  - As a cross-check, event totals must equal the sum of the per-year crawls.
- **GetMatchup tokens.** Used for discovery only. Stop at "Invalid next token" and log it. Never build records from GetMatchup, because it also counts DQs.
- **SearchPlayers.** Not used for crawling: it can't paginate and it misses inactive players.

### Cache and rebuild

- Every response is written to the cache before it is parsed, along with its URL, parameters, status and time. That includes 4xx responses, since a 404 is information too.
- Cache files are never modified. A refresh writes a new file, and the request log keeps every version.
- The builder reads only the cache and `curation/`. It uses the newest response per request key, and older ones supply name history (`former_name` aliases).
- Deleting `brawlhalla.sqlite` and running the builder reproduces it exactly, with no API calls.

### Resuming

- `crawl.sqlite` holds a `tasks` table: `task_key` (unique), `kind`, `params`, `priority`, `status` (pending/running/done/failed), `attempts` and `last_error`.
- Finishing a task is one transaction: write the cache entry, mark the task done, and enqueue its follow-up tasks with `INSERT OR IGNORE`. Tasks are therefore idempotent.
- On restart, tasks left `running` go back to `pending`. A task whose response is already cached completes without a network call, unless it asks for a refresh.
- Ctrl+C lets the current request finish, then stops.
- Requests are polite: one at a time, at least 0.5 s apart, with exponential backoff on timeouts and 5xx responses. A 400 is recorded and not retried.

### Keeping it current

- **Daily:** ListPr, the first ListEvents pages, and placements page 1 for active players (ranked, or with an event in the last 90 days).
- **For each new official event:** run stage 6 for its known participants, and discover their opponents.

## 4. Coverage checks

### Against events you know

You list events you know well in `curation/known_events.csv`:

| Column | Example |
|---|---|
| `event` | `https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/2v2`, or a name and date |
| `mode` | `2v2` |
| `winner`, `runner_up` | `Boomie`, … (names or aliases) |
| `top8` | optional, `;`-separated |
| `entrants` | optional, an approximate count |
| `notes` | anything else |

The check report lists, for each row:
- whether the event was found (by URL → `event_id`, otherwise by name and date);
- whether the winner and runner-up match;
- which top-8 players are missing;
- how many placements we hold against your entrant count;
- how many of the top 8 have match data.

About 20 events spread across eras would cover the known risks:
- BCX 2017;
- the 2019 Worlds at DreamHack Atlanta;
- one 2020 online regional Worlds;
- BCX 2022–2024;
- a 2025 and a 2026 Challengermode championship;
- Brawl League Masters Season 4 NA (phases);
- a Crew Battle Invitational;
- a few community events you played in.

### Automatic checks (no input needed)

1. **Event totals:** the full ListEvents crawl equals the sum of the per-year crawls (the tie bug).
2. **Winners:** each counted event has exactly one 1st place in 1v1, or two players sharing a team in 2v2. Crew battles can have three.
3. **PR cross-check:** for every ranked player, compute the counts with PR's own rule (official, crew battles excluded) and compare them with the PR fields. A mismatch means a missing or extra placement. This is the strongest automatic check, because PR covers thousands of players.
4. **Teammates:** a player's GetPlayerTeammates `games` add up to their number of 2v2 placements, and every 2v2 placement has a `team_id`.
5. **Match symmetry:** a match seen from both sides has the same scores reversed.
6. **Match presence:** every (player, event) pair in scope has at least one match.
7. **Earnings:** once payouts exist (§6), a player's summed per-event prizes shouldn't exceed their career figure.

These results feed a `v_event_coverage` view. For each event it shows placements held, the worst placement seen, players with match data, and 2v2 placements with no known partner.

## 5. Official events for tier assignment

The full list is in the [appendix](#appendix-official-events): 622 official events (375 1v1, 247 2v2) grouped into 410 tournaments. Each tournament's 1v1 and 2v2 events share a row, and the rows are grouped by year. The "family" column is a name-based guess, there only to make sorting easier.

| Family (auto-detected) | Tournaments |
|---|---|
| Seasonal championship | 172 |
| Invitational / cup / league | 54 |
| Partner event (CEO, DreamHack, …) | 33 |
| Other | 32 |
| Qualifier / LCQ | 31 |
| Trial of … (2024) | 29 |
| World Championship | 16 |
| Excluded format | 12 |
| Royale | 9 |
| Regional championship (AUS, BRZ, SEA) | 8 |
| Midseason | 7 |
| Crew battle (counts as 1v1) | 6 |
| Community tournament | 1 |

Suggested workflow:

1. Define the tier scale in `curation/tiers.csv`. One possible scale: S = World Championship, A = Midseason and major partner events, B = regional championships, C = other official events. That's only an example; the choice is yours.
2. Assign a default tier per family.
3. Override individual tournaments in `curation/events.csv`. A tier set on a tournament applies to all of its events (both modes, all phases).

## 6. Earnings

### 6a. Career earnings

```sql
CREATE TABLE player_external_ids (
  player_id    INTEGER NOT NULL REFERENCES players (player_id),
  source       TEXT NOT NULL,         -- 'esports_earnings' (later perhaps 'liquipedia')
  external_id  TEXT NOT NULL,         -- Esports Earnings PlayerId
  link_method  TEXT NOT NULL,         -- 'handle+country' | 'handle+social' | 'manual'
  verified     INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (player_id, source)
);

CREATE TABLE player_earnings (
  player_id   INTEGER NOT NULL REFERENCES players (player_id),
  source      TEXT NOT NULL,          -- 'stats_api' | 'esports_earnings'
  amount_usd  REAL NOT NULL,
  as_of       TEXT NOT NULL,          -- the date the figure is current to (below)
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (player_id, source)
);

CREATE VIEW v_career_earnings AS
SELECT p.player_id, p.name,
       COALESCE(s.amount_usd, e.amount_usd) AS earnings_usd,
       CASE WHEN s.player_id IS NOT NULL THEN 'Stats API' ELSE 'Esports Earnings' END AS source,
       COALESCE(s.as_of, e.as_of) AS as_of,
       CASE WHEN s.player_id IS NULL AND EXISTS (
              SELECT 1 FROM v_results r
              WHERE r.player_id = p.player_id AND r.is_official = 1 AND r.start_date > e.as_of)
            THEN 1 ELSE 0 END AS may_be_stale   -- official results after the figure's date
FROM players p
LEFT JOIN player_earnings s ON s.player_id = p.player_id AND s.source = 'stats_api'
LEFT JOIN player_earnings e ON e.player_id = p.player_id AND e.source = 'esports_earnings'
WHERE s.player_id IS NOT NULL OR e.player_id IS NOT NULL;
```

**The Stats API figure is the primary source.** It is recorded only when the player has a PR row, or when SearchPlayers returned non-null earnings. GetPlayerPr's `0` for an unranked player means *unknown*, not zero. Its `as_of` is ListPr's `lastUpdated`, or the search date for figures that came from SearchPlayers.

**Esports Earnings is the fallback.** Its `as_of` is the end date of the latest tournament it lists for that player (from LookupPlayerTournaments), so the agent can say, for example, "Esports Earnings, results through March 2024". `may_be_stale` flags players with official results after that date.

**Linking players to Esports Earnings:**
1. Pull the Brawlhalla top-earner pages (LookupHighestEarningPlayersByGame, game 443, 100 per call).
2. Match each handle against our `player_aliases`. Accept the match automatically only when there's exactly one candidate and the country agrees.
3. Everything else goes to a manual review list in `curation/external_ids.csv`.

The handles often differ from our display names: Sandstorm = gdsandstorm, Godly = Zivai, Kyna = whoiskyna, Fiend = lFiend, Experience = experiencedoa, lores = loreszz. So nicknames in the alias table do most of the work. The top earners are few enough to map by hand.

### 6b. Per-tournament earnings: what each platform actually has

**Schema checks** (2026-10-03):

| Claim | Exists? | Evidence |
|---|---|---|
| start.gg `prizingInfo` on Event | **Yes.** `Event.prizingInfo: JSON`, described as "TO settings for prizing". It holds `enablePrizing`, `payoutType` (`fixedAmount` seen), `payoutTotal`, `markdown` (free text), and `prizing`: a list of `{placement, percent, amount}` with one entry per paid place (two 5th places → two entries). | start.gg's schema reference, plus the event pages, which embed the same object. Introspection needs a token (`Invalid authentication token`), as does the API Explorer, so I used the reference that developer.start.gg links to. One authenticated call should confirm it before anything is built. |
| start.gg `prizingInfo` on Tournament | **No.** Tournament has `currency` and a free-text `rules` field, nothing prize-specific. | Schema reference |
| start.gg Event tier field | **Yes, but useless here.** `Event.competitionTier: Int`, "Rough categorization of event tier, denoting relative importance in the competitive scene". It's a plain integer and the schema lists no values. All 19 official events sampled (2017–2025, BCX down to league weeks) have `5`. | Schema reference, plus the event pages' data |
| start.gg standings | **Yes.** `Event.standings(query: StandingPaginationQuery!)` returns `{ nodes: [Standing] }`. `Standing` has `placement`, `entrant`, `player`, `isFinal`, `metadata` (JSON), `stats { score }`, `totalPoints`, `setRecordWithoutByes` and `container`. Standings also exist on `PhaseGroup`, and a standing's container can be a Tournament, Event, PhaseGroup or Set. **No prize field.** | Schema reference |
| Challengermode `tournamentsForSpace` | **Yes.** `tournamentsForSpace(input: {spaceId, tournamentFilter, gameSettingFilters, includeInviteOnly, includeUnlisted})`, "Find tournaments in a specific Space". `tournamentsForGame(input: {gameSlug, …})` exists too. `tournamentsForGame` returned `AUTH_NOT_AUTHENTICATED`; `tournamentsForSpace` wasn't called (it needs a space ID) but presumably behaves the same. | Live introspection and query |
| Challengermode prizing or rewards on tournaments | **No.** Across all 271 types, no type, field, input or enum value has a prize-like name or description. The only free text is `Tournament.description` and `Cup.description`, and reading them needs credentials. The public tournament page has no prize text either: its server-rendered data is an auto summary ("512 Slots, Free to enter, Double Elimination…"), and the `/rules` page renders only in the browser. | Live introspection, and the page HTML |

**start.gg payouts, event by event.** I read 19 official event pages, matching each event by its slug. An earlier check grabbed the first event on multi-game pages, which is why a previous version of this doc wrongly said CEO 2025 had no payouts.

| Event | Structured payouts | 1st place |
|---|---|---|
| BCX 2017 1v1 | no | — |
| Riddle Brawl #1 (EU), 2017 | no | — |
| BCS Summer Slam NA (Week 1), 2017 | no | — |
| Brawl League Masters S4 NA, Top 8 Finals, 2018 | no | — |
| DreamHack Atlanta 2019 (Worlds) 1v1 | yes, 10 places | $20,000 (of a $50,000 total) |
| Winter Championship 2019 (NA) 1v1 | yes, 12 | $2,000 |
| NA World Championship 2020 1v1 | yes, 32 | $8,000 |
| NA Winter Championship 2021 1v1 | yes, 16 | $5,000 |
| NA Summer Championship 2022 1v1 | yes, 24 | $6,000 |
| BCX 2022 1v1 / 2v2 | yes, 128 / 64 | $50,000 / $60,000 per team |
| DreamHack Dallas 2023 1v1 | yes, 64 | $7,500 |
| Autumn Royale 2023 1v1 | yes, 8 | $1,250 |
| Trial of Freya NA 2024 1v1 | yes, 16 | $1,300 |
| BCX 2024 1v1 | yes, 128 | $20,000 |
| Winter Championship NA 2025 1v1 | yes, 12 | $1,600 |
| CEO 2025 Singles / Doubles | yes, 64 / 32 | $11,000 / $13,000 per team |
| MAX MODE 2025 1v1 | no | — |

- **Coverage:** 14 of 19 have structured payouts, including every sampled event from 2019 on except MAX MODE 2025.
- **No text either:** the five without payouts have no prize text anywhere on start.gg (prizing note, event rules or tournament rules).
- **External link:** CEO 2025's rules also link a "Prizing Breakdown" Google Doc.

**Esports Earnings** has prize money per player, per tournament: `TournamentName`, `EndDate`, `RankText`, `Prize`, `CurrencyCode`, `ExchangeRate` and `TeamPlayers`. It has no start.gg or Challengermode IDs, so matching to our events is by name and date. It needs an API key (free registration), allows at most one request per second, and is about two years out of date.

**Payouts that exist only as text.** These can still be used:
1. Store the text in `event_prizes.raw_text` with status `free_text`.
2. Parse it into `prize_payouts` rows (placement → amount) with source `parsed_text`. A model can draft the parse, but each event should be checked by a person once.
3. Map amounts to players exactly as for structured payouts: the amount for placement P goes to every player who placed P, split across the team in 2v2.

So far, such text can come from:
- start.gg's prizing note and rules fields (none found in the sample);
- linked documents such as CEO 2025's Google Doc;
- Challengermode's `description`, readable with API credentials or copied from the page by hand.

**Payouts are never estimated from a total prize pool.** If no per-placement split exists, the event's status stays `unavailable`.

**What this means for official events:**
- **2019 to June 2025 (start.gg):** structured payouts for most events, BMG-run and partner alike, so amounts come straight from placements × payouts.
- **2017–2018, and league or series events:** no payouts on start.gg. They need Esports Earnings or hand entry.
- **Challengermode era (mid-2025 onward):** nothing structured. Each event needs its description text (via credentials or a manual copy), Esports Earnings, or hand entry.

**Proposed design:**

```sql
CREATE TABLE event_prizes (        -- one row per event checked for prize data
  event_id     TEXT PRIMARY KEY REFERENCES events (event_id),
  status       TEXT NOT NULL,      -- 'structured' | 'disabled' | 'free_text' | 'unavailable'
  payout_type  TEXT,               -- start.gg payoutType
  currency     TEXT,
  total        REAL,
  raw_text     TEXT,               -- markdown or description, kept for manual review
  source       TEXT NOT NULL,      -- 'startgg' | 'challengermode' | 'curated'
  fetched_at   TEXT NOT NULL
);

CREATE TABLE prize_payouts (       -- per-placement amounts, never derived from a total
  event_id   TEXT NOT NULL REFERENCES events (event_id),
  slot       INTEGER NOT NULL,     -- start.gg prizing id, or line number in parsed text
  placement  INTEGER NOT NULL,
  amount     REAL NOT NULL,        -- per entrant (a team, in 2v2), in the event currency
  source     TEXT NOT NULL,        -- 'startgg' | 'parsed_text' | 'curated'
  reviewed   INTEGER NOT NULL DEFAULT 0,   -- parsed text must be confirmed once by a person
  PRIMARY KEY (event_id, slot)
);

CREATE TABLE player_prizes_external (   -- Esports Earnings per-tournament rows
  player_id         INTEGER NOT NULL REFERENCES players (player_id),
  source            TEXT NOT NULL,      -- 'esports_earnings'
  tournament_name   TEXT NOT NULL,
  end_date          TEXT NOT NULL,
  rank_text         TEXT,
  prize_usd         REAL NOT NULL,
  matched_event_id  TEXT REFERENCES events (event_id),  -- NULL without a confident match
  fetched_at        TEXT NOT NULL
);

CREATE VIEW v_player_event_earnings AS
SELECT r.player_id, r.event_id, r.tournament_name, r.start_date, r.placement,
       pp.amount / CASE WHEN r.format = 'crew_battle' THEN 3       -- crews of three
                        WHEN r.mode = '2v2' THEN 2 ELSE 1 END AS prize,
       ep.currency, CASE ep.status WHEN 'structured' THEN 'start.gg' ELSE 'prize text' END AS source
FROM v_results r
JOIN event_prizes ep ON ep.event_id = r.event_id AND ep.status IN ('structured', 'free_text')
JOIN (SELECT event_id, placement, MAX(amount) AS amount
        FROM prize_payouts
        WHERE source = 'startgg' OR reviewed = 1      -- parsed text only once confirmed
        GROUP BY event_id, placement) pp
  ON pp.event_id = r.event_id AND pp.placement = r.placement
UNION ALL
SELECT x.player_id, x.matched_event_id, x.tournament_name, x.end_date, NULL,
       x.prize_usd, 'USD', 'Esports Earnings'
FROM player_prizes_external x
WHERE x.matched_event_id IS NULL
   OR x.matched_event_id NOT IN (SELECT event_id FROM event_prizes WHERE status IN ('structured', 'free_text'));
```

- **Team splits are assumptions to verify.** start.gg's 2v2 amounts look per team ($60,000 for 1st at BCX 2022), so each player gets half. Crew prizes are split three ways, which fits the `.33`/`.67` fractions in the Stats API's earnings.
- **How to verify:** sum `v_player_event_earnings` for ranked players and compare the totals with their Stats API career figure (check 7 in §4).
- **The Sandstorm question:** "What tournament did sandstorm make the most money from?" becomes `SELECT ... FROM v_player_event_earnings WHERE player_id = 74433 ORDER BY prize DESC LIMIT 1`. The answer carries a caveat for any of his events without structured payouts.

## 7. Extending with start.gg and Challengermode

The core tables already carry what's needed to join platform data:
- event slugs and tournament UUIDs (`events.event_id`);
- start.gg set IDs and Challengermode match IDs (`matches.match_id`);
- `players.sgg_player_id` and `cm_player_id`;
- a `source` on every data row. Derived tables (`teams`, `match_players`) take the source of the rows they're built from, and curated tables are curated by definition.

Platform data would go into separate tables. The core views never reference them, so everything above works with these tables empty.

| Table (sketch) | Contents | start.gg | Challengermode |
|---|---|---|---|
| `phases` | event_id, phase id, name, order, bracket type (double elimination, Swiss, round robin) | `Event.phases` | `Tournament.stages` |
| `phase_groups` | phase id, group id, label (pools) | `Event.phaseGroups` | `TournamentBracket` |
| `match_bracket_info` | match_id → `matches`, group, round, round label, bracket side (winners/losers/grand final), set order, best-of | `Event.sets` | `TournamentRound`, `MatchSeries` |
| `seeds` | event_id, phase, entrant, seed | `Phase.seeds` | pre-seeds / lineups |
| `event_entrants` | event_id, entrant count | `Event.numEntrants` | `TournamentAttendance` |
| `standings` | event_id, entrant name, placement, platform player IDs, player_id when known | `Event.standings` | `TournamentLineupPlacement` (best/worst placement) |
| `event_prizes`, `prize_payouts`, `player_prizes_external` | §6 | `Event.prizingInfo` | none |

Things to confirm first:
- that start.gg set IDs equal the Stats API's numeric `matchId` values;
- whether the Stats API's Challengermode match UUIDs equal Challengermode's `MatchSeries` IDs.

The `standings` table would also fill the bottom of brackets, which the Stats API only reaches through players we've discovered.

## Open questions

Settled: the scope is official events only (§3).

1. **Crew battle matches in 1v1 head-to-heads:** count them only when the API stores them as one-on-one games? That's the default above.
2. **The tier scale** (§5).
3. **Credentials,** which you would need to create yourself. They're what unlock per-tournament earnings beyond the 2019–mid-2025 start.gg events:
   - a start.gg personal access token (free), for `prizingInfo` and standings;
   - Challengermode API access (an application), for every Challengermode query, including listing tournaments and reading the `description` text;
   - an Esports Earnings API key (free).
4. **Prize text for Challengermode-era events:** if Challengermode access isn't granted, the alternative is copying each official event's prize text by hand into `curation/`. That's about 50 tournaments since mid-2025.
5. **Data terms:** the appendix below, and the future `curation/` files, contain event names and IDs taken from the Stats API. Should they be committed, or kept out of the repo like `data/`?

## Appendix: official events

All 622 events with `isOfficial: true` in the 2026-10-03 survey crawl, one row per tournament.
- **Events** lists the modes, the format notes from the decided rules, and the two phase-split tournaments.
- **Family** is the auto-detected guess from §5.
- **Data terms:** this list was extracted from the Stats API. Before committing it, decide question 5 above.
- **Three events have no bracket link:** the Pro Series finals (2019 NA and EU, 2021) use `series/…` IDs (§1).

### 2017 (70 tournaments, 81 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2017-02-04 | Brawlhalla EU Winter Championship (Online) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-02-04 | Brawlhalla US Winter Championship (Online) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-02-06 | Brawl League Open Cup - Qualifier #1 (EU) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-10 | Brawl League Open Cup - Qualifier #2 (EU) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-14 | Brawl League Open Cup - Qualifier #1 (US) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-18 | Brawl League Open Cup - Qualifier #2 (US) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-20 | Brawl League Open Cup - Qualifier #3 (EU) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-24 | Brawl League Open Cup - Qualifier #4 (EU) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-02-28 | Brawl League Open Cup - Qualifier #3 (US) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-03-04 | Brawl League Open Cup - February Finals (EU) | 1v1 | start.gg | Invitational / cup / league |
| 2017-03-04 | Brawl League Open Cup - Qualifier #4 (US) | 1v1 | start.gg | Qualifier / LCQ |
| 2017-03-05 | Brawl League Open Cup - February Finals (US) | 1v1 | start.gg | Invitational / cup / league |
| 2017-03-10 | FINAL ROUND 20 | 1v1 | start.gg | Partner event |
| 2017-03-11 | Australian Open Series Qualifier #1 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-03-18 | Australian Open Series Qualifier #2 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-03-25 | Australian Open Series Finals | 1v1 | start.gg | Invitational / cup / league |
| 2017-03-26 | Brazil Brawlhalla Series Tournament #1 | 1v1 | start.gg | Invitational / cup / league |
| 2017-04-01 | Brawl League Open Cup - 2v2 March Finals (EU) | 2v2 | start.gg | Invitational / cup / league |
| 2017-04-01 | Brawl League Open Cup - 2v2 March Finals (US) | 2v2 | start.gg | Invitational / cup / league |
| 2017-04-01 | S.E. Asia Open Series Qualifier #1 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-04-01 | South Louisiana Major 2017 (SLAM 2017) | 1v1 | start.gg | Partner event |
| 2017-04-06 | Riddle Brawl #1 (EU) | 1v1 | start.gg | Other |
| 2017-04-07 | S.E. Asia Open Series Qualifier #2 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-04-14 | CEO: Dreamland | 1v1, 2v2 (filed as 1v1) | start.gg | Partner event |
| 2017-04-14 | S.E. Asia Open Series Finals | 1v1 | start.gg | Invitational / cup / league |
| 2017-04-21 | The BCS Spring Showdown | 1v1 | start.gg | Invitational / cup / league |
| 2017-04-22 | SEA League (Week 1/4) | 1v1 | start.gg | Invitational / cup / league |
| 2017-04-22 | Stream.me Brawlhalla Legend Series (US) | 1v1, 2v2 | start.gg | Invitational / cup / league |
| 2017-04-23 | Stream.me Brawlhalla Legend Series (EU) | 1v1, 2v2 | start.gg | Invitational / cup / league |
| 2017-04-29 | Brawl League Spring Fling (EU) | 1v1 | start.gg | Invitational / cup / league |
| 2017-04-29 | SEA League (Week 2/4) | 1v1 | start.gg | Invitational / cup / league |
| 2017-05-06 | SEA League (Week 3/4) | 1v1 | start.gg | Invitational / cup / league |
| 2017-05-11 | Riddle Brawl #2 (EU) | 1v1 | start.gg | Other |
| 2017-05-13 | Brawlhalla Spring Championship (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-05-13 | Brawlhalla Spring Championship (US) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-05-13 | SEA League (Week 4/4) | 1v1 | start.gg | Invitational / cup / league |
| 2017-05-20 | GoTE 4TheKids 2017 | 1v1 | start.gg | Partner event |
| 2017-05-21 | Brazil Brawlhalla Series Tournament #2 | 1v1 | start.gg | Invitational / cup / league |
| 2017-05-25 | Riddle Brawl #3 (EU) | 2v2 | start.gg | Other |
| 2017-05-26 | Combo Breaker | 1v1 | start.gg | Partner event |
| 2017-06-03 | BCS Summer Slam - NA (Week 1) | 1v1 | start.gg | Invitational / cup / league |
| 2017-06-10 | BCS Summer Slam - EU (Week 1) | 1v1 | start.gg | Invitational / cup / league |
| 2017-06-17 | BCS Summer Slam - NA (Week 2) | 1v1 | start.gg | Invitational / cup / league |
| 2017-06-23 | Gravy Cancel | 2v2 | start.gg | Other |
| 2017-06-24 | BCS Summer Slam - EU (Week 2) | 1v1 | start.gg | Invitational / cup / league |
| 2017-06-24 | SEA Championship #1 | 1v1 | start.gg | Regional championship |
| 2017-07-01 | BCS Summer Slam - EU (Final) | 1v1 | start.gg | Invitational / cup / league |
| 2017-07-01 | Brawlhalla - Trial of Legends | 1v1 | start.gg | Other |
| 2017-07-02 | AUS Championship #1 | 2v2 | start.gg | Regional championship |
| 2017-07-02 | BCS Summer Slam - NA (Final) | 1v1 | start.gg | Invitational / cup / league |
| 2017-07-07 | EasternMediaGG presents: Brawl-A-Palooza | 1v1 | start.gg | Other |
| 2017-07-15 | Brawl League Masters - NA Qualifier #1 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-07-16 | Brawl League Masters - EU Qualifier #1 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-07-22 | Brawl League Masters - NA Qualifier #2 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-07-23 | Brawl League Masters - EU Qualifier #2 | 1v1 | start.gg | Qualifier / LCQ |
| 2017-07-23 | Brazil Brawlhalla Series Tournament #3 (2v2) | 2v2 | start.gg | Invitational / cup / league |
| 2017-07-29 | Brawlhalla Summer Championship (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-07-29 | Brawlhalla Summer Championship (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2017-08-12 | Brawl League Masters (NA) | 1v1 | start.gg | Invitational / cup / league |
| 2017-08-13 | Brawl League Masters (EU) | 1v1 | start.gg | Invitational / cup / league |
| 2017-08-25 | Shine 2017 | 1v1, 2v2 | start.gg | Partner event |
| 2017-08-27 | BL Summer SEAson Showdown | 2v2 | start.gg | Invitational / cup / league |
| 2017-09-02 | BCX Regional Qualifier - AUS | 1v1 | start.gg | Qualifier / LCQ |
| 2017-09-09 | BCX Regional Qualifier - SEA | 1v1 | start.gg | Qualifier / LCQ |
| 2017-09-10 | Adaptation presents: Road to BCX | 1v1 | start.gg | Qualifier / LCQ |
| 2017-09-16 | BCX Regional Qualifier - BRZ | 1v1 | start.gg | Qualifier / LCQ |
| 2017-09-23 | BCX Regional Qualifier - EU | 1v1 | start.gg | Qualifier / LCQ |
| 2017-09-30 | BCX Regional Qualifier - NA-West | 1v1 | start.gg | Qualifier / LCQ |
| 2017-10-07 | BCX Regional Qualifier - NA-East | 1v1 | start.gg | Qualifier / LCQ |
| 2017-11-03 | Brawlhalla World Championship Expo | 1v1, 2v2 | start.gg | World Championship |

### 2018 (34 tournaments, 52 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2018-02-17 | Brawlhalla Winter Championship 2018 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-02-17 | Brawlhalla Winter Championship 2018 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-03-03 | Adaptation Win-ter Takes All | 1v1 | start.gg | Other |
| 2018-03-17 | Brawl League - Spring Fling 2018 (EU) | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2018-03-18 | Brawl League - Spring Fling 2018 (NA) | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2018-04-07 | Brawlhalla - Brazil Championship | 1v1 | start.gg | Regional championship |
| 2018-04-21 | Brawlhalla Spring Championship 2018 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-04-21 | Brawlhalla Spring Championship 2018 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-05-05 | Brawl League - Outplay or Dismay (EU) | 1v1 | start.gg | Invitational / cup / league |
| 2018-05-06 | Brawl League - Outplay or Dismay (NA) | 1v1 | start.gg | Invitational / cup / league |
| 2018-05-26 | StreamMe Brawlhalla Championship (EU) | 2v2 | start.gg | Other |
| 2018-05-27 | StreamMe Brawlhalla Championship (NA) | 2v2 | start.gg | Other |
| 2018-06-01 | DreamHack Austin 2018 | 1v1, 2v2 | start.gg | Partner event |
| 2018-06-02 | Brawlhalla - Southeast Asia Championship | 1v1 | start.gg | Regional championship |
| 2018-06-16 | Brawlhalla - Australia Championship | 1v1 | start.gg | Regional championship |
| 2018-06-16 | DreamHack Summer 2018 | 1v1, 2v2 | start.gg | Partner event |
| 2018-07-12 | DreamHack Valencia | 1v1, 2v2 | start.gg | Partner event |
| 2018-07-21 | Brawlhalla Summer Championship 2018 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-07-21 | Brawlhalla Summer Championship 2018 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-08-04 | Brawl League Masters - Ascension (EU) | 1v1 | start.gg | Invitational / cup / league |
| 2018-08-11 | Brawl League Masters - Ascension (NA) | 1v1 | start.gg | Invitational / cup / league |
| 2018-08-18 | Brawl League Masters - Season 4 (EU) | 1v1 in two phases (EU Swiss Bracket Brawlhalla → Top 8 Updated Finals Brawlhalla) | start.gg | Invitational / cup / league |
| 2018-08-18 | Brawl League Masters - Season 4 (NA) | 1v1 in two phases (NA Swiss Brawlhalla → Top 8 Finals Brawlhalla) | start.gg | Invitational / cup / league |
| 2018-08-25 | Brawlhalla - Brazil Championship #2 | 1v1 | start.gg | Regional championship |
| 2018-08-25 | Brawlhalla - Southeast Asia Championship #2 | 1v1 | start.gg | Regional championship |
| 2018-08-26 | Brawlhalla - Australia Championship #2 | 1v1 | start.gg | Regional championship |
| 2018-09-07 | DreamHack Montreal 2018 | 1v1, 2v2 | start.gg | Partner event |
| 2018-09-22 | Brawl to the Future - EU | 2v2 | start.gg | Other |
| 2018-09-29 | Brawl to the Future - NA | 2v2 | start.gg | Other |
| 2018-10-20 | Brawlhalla Autumn Championship 2018 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-10-20 | Brawlhalla Autumn Championship 2018 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2018-10-27 | Yggdrasils Instinct - Brawlhalla 1v1 | 1v1 | start.gg | Other |
| 2018-11-16 | DreamHack Atlanta 2018 | 2v2, 1v1 | start.gg | Partner event |
| 2018-12-01 | DreamHack Winter | 1v1, 2v2 | start.gg | Partner event |

### 2019 (49 tournaments, 68 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2019-02-09 | Brawlhalla Winter Championship 2019 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-02-09 | Brawlhalla Winter Championship 2019 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-02-23 | Brazil Winter Championship | 1v1 | start.gg | Seasonal championship |
| 2019-02-23 | Southeast Asia Winter Championship | 1v1 | start.gg | Seasonal championship |
| 2019-02-24 | Australia Winter Championship | 1v1 | start.gg | Seasonal championship |
| 2019-03-09 | March of Legends (EU) | 1v1 | start.gg | Other |
| 2019-03-15 | FINAL ROUND 2019 | 2v2, 1v1 | start.gg | Partner event |
| 2019-03-23 | March of Legends (NA) | 1v1 | start.gg | Other |
| 2019-04-06 | Sunny Side Air (EU) | 2v2 | start.gg | Other |
| 2019-04-13 | Sunny Side Air (NA) | 2v2 | start.gg | Other |
| 2019-04-19 | Pro Series 2019 NA | 1v1 | start.gg | Invitational / cup / league |
| 2019-04-20 | Brawlhalla Spring Championship 2019 (AUS) | 1v1 | start.gg | Seasonal championship |
| 2019-04-20 | Brawlhalla Spring Championship 2019 (BRZ) | 1v1 | start.gg | Seasonal championship |
| 2019-04-20 | Brawlhalla Spring Championship 2019 (SEA) | 1v1 | start.gg | Seasonal championship |
| 2019-04-27 | Brawlhalla Spring Championship 2019 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-04-27 | Brawlhalla Spring Championship 2019 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-05-03 | Brawl Experience - LEVEL UP! Brawlhalla BRZ 1v1 | 1v1 | start.gg | Other |
| 2019-05-07 | Pro Series 2019 EU | 1v1 | start.gg | Invitational / cup / league |
| 2019-05-11 | Mayhem of Ragnirock EU | 1v1 | start.gg | Other |
| 2019-05-18 | Mayhem of Ragnirock NA | 1v1 | start.gg | Other |
| 2019-05-18 | MTN DEW AMP GAME FUEL Championship (EU) | 1v1, 2v2 | start.gg | Other |
| 2019-05-18 | MTN DEW AMP GAME FUEL Championship (NA) | 1v1, 2v2 | start.gg | Other |
| 2019-05-31 | DreamHack Dallas 2019 | 2v2, 1v1 | start.gg | Partner event |
| 2019-06-15 | DreamHack Summer 2019 | 1v1, 2v2 | start.gg | Partner event |
| 2019-06-22 | Brawl at the Beach EU | 2v2 | start.gg | Other |
| 2019-06-28 | CEO 2019 Fighting Game Championships | 1v1, 2v2 | start.gg | Partner event |
| 2019-07-06 | Brawl at the Beach NA | 2v2 | start.gg | Other |
| 2019-07-12 | Low Tier City 7 | 1v1, 2v2 | start.gg | Partner event |
| 2019-07-20 | Super Summer Slayem EU | 1v1 | start.gg | Other |
| 2019-07-27 | Brawlhalla Summer Championship 2019 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-07-27 | Brawlhalla Summer Championship 2019 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-08-03 | Brawlhalla Summer Championship 2019 (AUS) | 1v1 | start.gg | Seasonal championship |
| 2019-08-03 | Brawlhalla Summer Championship 2019 (BRZ) | 1v1 | start.gg | Seasonal championship |
| 2019-08-03 | Brawlhalla Summer Championship 2019 (SEA) | 1v1 | start.gg | Seasonal championship |
| 2019-08-10 | Super Summer Slayem NA | 1v1 | start.gg | Other |
| 2019-08-23 | Shine 2019 | 1v1, 2v2 | start.gg | Partner event |
| 2019-09-06 | DreamHack Montreal 2019 | 2v2, 1v1 | start.gg | Partner event |
| 2019-09-28 | Brawlhalla Autumn Championship 2019 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-09-28 | Brawlhalla Autumn Championship 2019 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2019-10-05 | Brawlhalla Autumn Championship (AUS) | 1v1 | start.gg | Seasonal championship |
| 2019-10-05 | Brawlhalla Autumn Championship (BRZ) | 1v1 | start.gg | Seasonal championship |
| 2019-10-05 | Brawlhalla Autumn Championship (SEA) | 1v1 | start.gg | Seasonal championship |
| 2019-10-06 | The Great Brawl - PGW Qualifier #1 | 1v1 | start.gg | Qualifier / LCQ |
| 2019-10-12 | Call of the Octobrawl NA | 2v2 | start.gg | Other |
| 2019-10-13 | The Great Brawl - PGW Qualifier #2 | 1v1 | start.gg | Qualifier / LCQ |
| 2019-10-18 | Dreamhack Rotterdam Smash Championship | 2v2, 1v1 | start.gg | Partner event |
| 2019-10-26 | Call of the Octobrawl EU | 2v2 | start.gg | Other |
| 2019-11-01 | The Great Brawl - Final | 1v1 | start.gg | Other |
| 2019-11-15 | DreamHack Atlanta 2019 | 2v2, 1v1 | start.gg | World Championship |

### 2020 (50 tournaments, 96 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2020-02-21 | Brawlhalla Winter Championship 2020 (SEA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-02-22 | Brawlhalla Winter Championship 2020 (NA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-02-23 | Brawlhalla Winter Championship 2020 (AUS) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-02-23 | Brawlhalla Winter Championship 2020 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-02-23 | Brawlhalla Winter Championship 2020 (SA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-03-13 | CEO Dreamland 2020 | 1v1 | start.gg | Partner event |
| 2020-03-28 | Brawlhalla CEO Dreamland ONLINE | 2v2, 1v1 | start.gg | Partner event |
| 2020-04-11 | Brawlhalla Spring Championship 2020 (AUS) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-04-12 | Brawlhalla Spring Championship 2020 (EU) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-04-12 | Brawlhalla Spring Championship 2020 (SA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-04-12 | Brawlhalla Spring Championship 2020 (SEA) | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-04-18 | Brawlhalla Spring Championship 2020 (NA) | 2v2, 1v1 | start.gg | Seasonal championship |
| 2020-05-30 | Brawlhalla Combo Breaker Online (AUS) | 1v1, 2v2 | start.gg | Partner event |
| 2020-05-30 | Brawlhalla Combo Breaker Online (NA) | 1v1, 2v2 | start.gg | Partner event |
| 2020-05-31 | Brawlhalla Combo Breaker Online (EU) | 1v1, 2v2 | start.gg | Partner event |
| 2020-05-31 | Brawlhalla Combo Breaker Online (SA) | 1v1, 2v2 | start.gg | Partner event |
| 2020-05-31 | Brawlhalla Combo Breaker Online (SEA) | 1v1, 2v2 | start.gg | Partner event |
| 2020-06-20 | Australia - Summer Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-06-20 | North America - Summer Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-06-21 | Europe - Summer Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-06-21 | South America - Summer Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-06-21 | Southeast Asia - Summer Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-07-18 | Low Tier City Midseason Online (AUS) | 1v1, 2v2 | start.gg | Midseason |
| 2020-07-18 | Low Tier City Midseason Online (NA) | 1v1, 2v2 | start.gg | Midseason |
| 2020-07-19 | Low Tier City Midseason Online (EU) | 1v1, 2v2 | start.gg | Midseason |
| 2020-07-19 | Low Tier City Midseason Online (SA) | 1v1, 2v2 | start.gg | Midseason |
| 2020-07-19 | Low Tier City Midseason Online (SEA) | 1v1, 2v2 | start.gg | Midseason |
| 2020-08-15 | Australia - SteelSeries Championship | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-08-15 | North America - SteelSeries Championship | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-08-16 | Europe - SteelSeries Championship | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-08-16 | South America - SteelSeries Championship | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-08-16 | Southeast Asia - SteelSeries Championship | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-09-12 | Australia - Autumn Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-09-12 | North America - Autumn Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-09-13 | Europe - Autumn Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-09-13 | South America - Autumn Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-09-13 | Southeast Asia - Autumn Championship 2020 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2020-10-10 | Australia - Mammoth Cup | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-10-10 | North America - Mammoth Cup | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-10-11 | Europe - Mammoth Cup | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-10-11 | South America - Mammoth Cup | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-10-11 | Southeast Asia - Mammoth Cup | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2020-10-31 | Europe - World Championship Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2020-10-31 | South America - World Championship Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2020-11-01 | North America - World Championship Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2020-11-07 | North America - Brawlhalla World Championship 2020 | 2v2, 1v1 | start.gg | World Championship |
| 2020-11-08 | Australia - Brawlhalla World Championship 2020 | 2v2, 1v1 | start.gg | World Championship |
| 2020-11-08 | Europe - Brawlhalla World Championship 2020 | 2v2, 1v1 | start.gg | World Championship |
| 2020-11-08 | South America - Brawlhalla World Championship 2020 | 2v2, 1v1 | start.gg | World Championship |
| 2020-11-08 | Southeast Asia - Brawlhalla World Championship 2020 | 2v2, 1v1 | start.gg | World Championship |

### 2021 (35 tournaments, 60 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2021-02-27 | Europe - Winter Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-03-05 | Australia - Winter Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-03-06 | South America - Winter Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-03-06 | Southeast Asia - Winter Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-03-13 | North America - Winter Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-04-24 | Europe - Spring Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-04-30 | Australia - Spring Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-05-01 | South America - Spring Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-05-01 | Southeast Asia - Spring Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-05-08 | North America - Spring Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-06-05 | Europe - Parsec Invitational | 1v1 | start.gg | Invitational / cup / league |
| 2021-06-06 | North America - Parsec Invitational | 1v1 | start.gg | Invitational / cup / league |
| 2021-07-10 | Pro Series 2021 | 1v1 | start.gg | Invitational / cup / league |
| 2021-08-14 | Europe - Summer Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-08-20 | Australia - Summer Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-08-21 | South America - Summer Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-08-21 | Southeast Asia - Summer Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-08-28 | North America - Summer Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-09-11 | Europe - Mammoth Arcadian | 1v1 | start.gg | Other |
| 2021-09-12 | North America - Mammoth Arcadian | 1v1 | start.gg | Other |
| 2021-09-18 | Europe - Mammoth Invitational | 1v1 | start.gg | Invitational / cup / league |
| 2021-09-19 | North America - Mammoth Invitational | 1v1 | start.gg | Invitational / cup / league |
| 2021-10-02 | Europe - Autumn Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-10-08 | Australia - Autumn Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-10-09 | South America - Autumn Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-10-09 | Southeast Asia - Autumn Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-10-16 | North America - Autumn Championship 2021 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2021-10-30 | Europe - Brawlhalla World Championship 2021 Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2021-10-30 | South America - Brawlhalla World Championship 2021 Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2021-10-31 | North America - Brawlhalla World Championship 2021 Last Chance Qualifier | 1v1 | start.gg | Qualifier / LCQ |
| 2021-11-05 | Australia - Brawlhalla World Championship 2021 | 2v2, 1v1 | start.gg | World Championship |
| 2021-11-06 | Europe - Brawlhalla World Championship 2021 | 2v2, 1v1 | start.gg | World Championship |
| 2021-11-06 | South America - Brawlhalla World Championship 2021 | 2v2, 1v1 | start.gg | World Championship |
| 2021-11-06 | Southeast Asia - Brawlhalla World Championship 2021 | 2v2, 1v1 | start.gg | World Championship |
| 2021-11-07 | North America - Brawlhalla World Championship 2021 | 2v2, 1v1 | start.gg | World Championship |

### 2022 (33 tournaments, 57 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2022-01-28 | South America - Winter Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-01-29 | Australia - Winter Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-01-29 | Europe - Winter Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-01-29 | Southeast Asia - Winter Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-01-30 | North America - Winter Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-02-26 | Europe - OMEN Oasis Championship | 1v1 | start.gg | Other |
| 2022-02-27 | North America - OMEN Oasis Championship | 1v1 | start.gg | Other |
| 2022-03-18 | South America - Crew Battle Invitational | crew battle (1v1) | start.gg | Crew battle (counts as 1v1) |
| 2022-03-19 | Europe - Crew Battle Invitational | crew battle (1v1) | start.gg | Crew battle (counts as 1v1) |
| 2022-03-20 | North America - Crew Battle Invitational | crew battle (1v1) | start.gg | Crew battle (counts as 1v1) |
| 2022-04-09 | Europe - SteelSeries Invitational 2022 | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2022-04-10 | North America - SteelSeries Invitational 2022 | 2v2, 1v1 | start.gg | Invitational / cup / league |
| 2022-04-29 | Australia - Spring Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-04-30 | Europe - Spring Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-04-30 | South America - Spring Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-04-30 | Southeast Asia - Spring Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-05-01 | North America - Spring Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-06-11 | Brawlhalla Midseason Championship | 2v2, 1v1 | start.gg | Midseason |
| 2022-07-22 | Australia - Summer Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-07-23 | Europe - Summer Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-07-23 | South America - Summer Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-07-23 | Southeast Asia - Summer Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-07-24 | North America - Summer Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-08-20 | South America - Brawlhalla 3v3 Championship | 3v3 (excluded) | start.gg | Excluded format |
| 2022-08-27 | Europe - Brawlhalla 3v3 Championship | 3v3 (excluded) | start.gg | Excluded format |
| 2022-08-28 | North America - Brawlhalla 3v3 Championship | 3v3 (excluded) | start.gg | Excluded format |
| 2022-09-03 | Brawlhalla Japan Invitational | 1v1 | start.gg | Invitational / cup / league |
| 2022-09-16 | Australia - Autumn Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-09-17 | Europe - Autumn Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-09-17 | South America - Autumn Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-09-17 | Southeast Asia - Autumn Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-09-18 | North America - Autumn Championship 2022 | 2v2, 1v1 | start.gg | Seasonal championship |
| 2022-11-04 | Brawlhalla World Championship Expo 2022 | 1v1, 2v2 | start.gg | World Championship |

### 2023 (28 tournaments, 52 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2023-02-04 | Australia - Winter Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-02-04 | Europe - Winter Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-02-04 | South America - Winter Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-02-04 | Southeast Asia - Winter Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-02-05 | North America - Winter Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-03-11 | Brawlhalla - Winter Royale 2023 | 1v1 | start.gg | Royale |
| 2023-03-24 | Australia - Spring Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-03-25 | Europe - Spring Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-03-25 | South America - Spring Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-03-25 | Southeast Asia - Spring Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-03-26 | North America - Spring Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-04-07 | DreamHack San Diego 2023 | 1v1, 2v2 | start.gg | Partner event |
| 2023-04-28 | Brawlhalla - Spring Royale 2023 | 1v1 | start.gg | Royale |
| 2023-06-02 | DreamHack Dallas 2023 | 1v1, 2v2 | start.gg | Partner event |
| 2023-07-07 | DreamHack Valencia 2023 | 1v1, 2v2 | start.gg | Partner event |
| 2023-07-28 | Australia - Summer Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-07-29 | Europe - Summer Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-07-29 | South America - Summer Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-07-29 | Southeast Asia - Summer Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-07-30 | North America - Summer Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-09-02 | Brawlhalla - Summer Royale 2023 | 1v1 | start.gg | Royale |
| 2023-09-22 | Australia - Autumn Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-09-23 | Europe - Autumn Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-09-23 | South America - Autumn Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-09-23 | Southeast Asia - Autumn Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-09-24 | North America - Autumn Championship 2023 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2023-10-14 | Brawlhalla - Autumn Royale 2023 | 1v1 | start.gg | Royale |
| 2023-11-03 | Brawlhalla World Championship Expo 2023 | 1v1, 2v2 | start.gg | World Championship |

### 2024 (50 tournaments, 52 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2024-02-16 | Trial of Ymir - Middle East & North Africa | 1v1 | start.gg | Trial of … (2024) |
| 2024-02-16 | Trial of Ymir - Southeast Asia | 1v1 | start.gg | Trial of … (2024) |
| 2024-02-17 | Trial of Ymir - Europe | 1v1 | start.gg | Trial of … (2024) |
| 2024-02-17 | Trial of Ymir - South America | 1v1 | start.gg | Trial of … (2024) |
| 2024-02-18 | Trial of Ymir - North America | 1v1 | start.gg | Trial of … (2024) |
| 2024-03-08 | Winter Doubles Championship - Southeast Asia | 2v2 | start.gg | Seasonal championship |
| 2024-03-09 | Winter Doubles Championship - Europe | 2v2 | start.gg | Seasonal championship |
| 2024-03-09 | Winter Doubles Championship - South America | 2v2 | start.gg | Seasonal championship |
| 2024-03-10 | Winter Doubles Championship - North America | 2v2 | start.gg | Seasonal championship |
| 2024-03-16 | Trial of Frigg - Europe (Brawl League) | 1v1 | start.gg | Trial of … (2024) |
| 2024-03-16 | Trial of Frigg - South America (Estacao) | 1v1 | start.gg | Trial of … (2024) |
| 2024-03-17 | Trial of Frigg - North America (Moose Wars) | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-06 | Trial of Baldr - Europe (Brawl League) | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-06 | Trial of Baldr - South America (Estacao) | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-07 | Trial of Baldr - North America (Moose Wars) | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-19 | Trial of Skadi - Southeast Asia | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-20 | Trial of Skadi - Europe | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-20 | Trial of Skadi - South America | 1v1 | start.gg | Trial of … (2024) |
| 2024-04-21 | Trial of Skadi - North America | 1v1 | start.gg | Trial of … (2024) |
| 2024-05-03 | Spring Doubles Championship - Southeast Asia | 2v2 | start.gg | Seasonal championship |
| 2024-05-04 | Spring Doubles Championship - Europe | 2v2 | start.gg | Seasonal championship |
| 2024-05-04 | Spring Doubles Championship - South America | 2v2 | start.gg | Seasonal championship |
| 2024-05-05 | Spring Doubles Championship - North America | 2v2 | start.gg | Seasonal championship |
| 2024-05-17 | Brawlhalla - Spring Royale 2024 | 1v1 | start.gg | Royale |
| 2024-06-28 | CEO 2024 | 1v1, 2v2 | start.gg | Partner event |
| 2024-07-13 | Trial of Heimdall - Europe (Brawl League) | 1v1 | start.gg | Trial of … (2024) |
| 2024-07-13 | Trial of Heimdall - South America (Estacao) | 1v1 | start.gg | Trial of … (2024) |
| 2024-07-14 | Trial of Heimdall - North America (NSIG) | 1v1 | start.gg | Trial of … (2024) |
| 2024-07-19 | Summer Doubles Championship - Middle East & North Africa | 2v2 | start.gg | Seasonal championship |
| 2024-07-19 | Summer Doubles Championship - Southeast Asia | 2v2 | start.gg | Seasonal championship |
| 2024-07-20 | Summer Doubles Championship - Europe | 2v2 | start.gg | Seasonal championship |
| 2024-07-20 | Summer Doubles Championship - South America | 2v2 | start.gg | Seasonal championship |
| 2024-07-21 | Summer Doubles Championship - North America | 2v2 | start.gg | Seasonal championship |
| 2024-08-02 | Trial of Skuld - Southeast Asia | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-03 | Trial of Skuld - Europe | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-03 | Trial of Skuld - South America | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-04 | Trial of Skuld - North America | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-24 | Trial of Laufey - Europe (Brawl League) | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-24 | Trial of Laufey - South America (Estacao) | 1v1 | start.gg | Trial of … (2024) |
| 2024-08-25 | Trial of Laufey - North America (Moose Wars) | 1v1 | start.gg | Trial of … (2024) |
| 2024-09-13 | Trial of Freya - Southeast Asia | 1v1 | start.gg | Trial of … (2024) |
| 2024-09-14 | Trial of Freya - Europe | 1v1 | start.gg | Trial of … (2024) |
| 2024-09-14 | Trial of Freya - South America | 1v1 | start.gg | Trial of … (2024) |
| 2024-09-15 | Trial of Freya - North America | 1v1 | start.gg | Trial of … (2024) |
| 2024-10-04 | Autumn Doubles Championship - Southeast Asia | 2v2 | start.gg | Seasonal championship |
| 2024-10-05 | Autumn Doubles Championship - Europe | 2v2 | start.gg | Seasonal championship |
| 2024-10-05 | Autumn Doubles Championship - South America | 2v2 | start.gg | Seasonal championship |
| 2024-10-06 | Autumn Doubles Championship - North America | 2v2 | start.gg | Seasonal championship |
| 2024-10-11 | Brawlhalla - Autumn Royale 2024 | 1v1 | start.gg | Royale |
| 2024-11-15 | Brawlhalla World Championship Expo 2024 | 1v1, 2v2 | start.gg | World Championship |

### 2025 (28 tournaments, 50 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2025-02-21 | Winter Championship - Middle East 2025 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2025-02-21 | Winter Championship - Southeast Asia 2025 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2025-02-22 | Winter Championship - Europe 2025 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2025-02-22 | Winter Championship - South America 2025 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2025-02-23 | Winter Championship - North America 2025 | 1v1, 2v2 | start.gg | Seasonal championship |
| 2025-04-25 | MAX MODE 2025 | 2v2, 1v1 | start.gg | Partner event |
| 2025-05-09 | Spring Championship - Middle East 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-05-09 | Spring Championship - Southeast Asia 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-05-10 | Spring Championship - Europe 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-05-10 | Spring Championship - South America 2025 | 1v1 | Challengermode | Seasonal championship |
| 2025-05-11 | Spring Championship - North America 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-05-25 | Spring Championship - South America 2025 - 2v2 - rerun | 2v2 | Challengermode | Seasonal championship |
| 2025-06-08 | Brawlhalla - Spring Royale 2025 | 1v1 | Challengermode | Royale |
| 2025-06-13 | CEO 2025 | 2v2, 1v1 | start.gg | Partner event |
| 2025-07-18 | Summer Championship - Middle East 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-07-18 | Summer Championship - Southeast Asia 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-07-19 | Summer Championship - Europe 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-07-19 | Summer Championship - South America 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-07-20 | Summer Championship - North America 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-08-17 | Brawlhalla - Summer Royale 2025 | 1v1 | Challengermode | Royale |
| 2025-09-12 | Autumn Championship - Middle East 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-09-12 | Autumn Championship - Southeast Asia 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-09-13 | Autumn Championship - Europe 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-09-13 | Autumn Championship - South America 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-09-14 | Autumn Championship - North America 2025 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2025-09-28 | Brawlhalla Community Tournament #2 | 1v1 | Challengermode | Community tournament |
| 2025-10-12 | Brawlhalla - Autumn Royale 2025 | 1v1 | Challengermode | Royale |
| 2025-11-21 | Brawlhalla World Championship Expo 2025 | 2v2, 1v1 | Challengermode | World Championship |

### 2026 (33 tournaments, 54 events)

| Date | Tournament | Events | Host | Family (auto-detected) |
|---|---|---|---|---|
| 2026-01-31 | Eternal Sports Brawlball Championship - Europe 2026 | Brawlball (excluded) | Challengermode | Excluded format |
| 2026-01-31 | Eternal Sports Brawlball Championship - South America 2026 | Brawlball (excluded) | Challengermode | Excluded format |
| 2026-02-01 | Eternal Sports Brawlball Championship - North America 2026 | Brawlball (excluded) | Challengermode | Excluded format |
| 2026-02-20 | Winter Championship - Middle East 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-02-20 | Winter Championship - Southeast Asia 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-02-21 | Winter Championship - Europe 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-02-21 | Winter Championship - South America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-02-22 | Winter Championship - North America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-03-28 | Eternal Sports Triples Championship 2026 - Europe | triples (excluded) | Challengermode | Excluded format |
| 2026-03-28 | Eternal Sports Triples Championship 2026 - South America | triples (excluded) | Challengermode | Excluded format |
| 2026-03-29 | Eternal Sports Triples Championship 2026 - North America | triples (excluded) | Challengermode | Excluded format |
| 2026-04-24 | Spring Championship - Middle East 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-04-24 | Spring Championship - Southeast Asia 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-04-25 | Spring Championship - Europe 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-04-25 | Spring Championship - South America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-04-26 | Spring Championship - North America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-06-12 | Midseason Championship 2026 | 2v2, 1v1 | Challengermode | Midseason |
| 2026-06-27 | Eternal Sports Kung Foot Championship 2026 - Europe | Kung Foot (excluded) | Challengermode | Excluded format |
| 2026-06-27 | Eternal Sports Kung Foot Championship 2026 - South America | Kung Foot (excluded) | Challengermode | Excluded format |
| 2026-06-28 | Eternal Sports Kung Foot Championship 2026 - North America | Kung Foot (excluded) | Challengermode | Excluded format |
| 2026-07-17 | Summer Championship - Middle East 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-07-17 | Summer Championship - Southeast Asia 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-07-18 | Summer Championship - Europe 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-07-18 | Summer Championship - South America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-07-19 | Summer Championship - North America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-08-29 | Eternal Sports Crew Battle Championship 2026 - Europe | crew battle (1v1) | Challengermode | Crew battle (counts as 1v1) |
| 2026-08-29 | Eternal Sports Crew Battle Championship 2026 - South America | crew battle (1v1) | Challengermode | Crew battle (counts as 1v1) |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | crew battle (1v1) | Challengermode | Crew battle (counts as 1v1) |
| 2026-09-18 | Autumn Championship - Middle East 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-09-18 | Autumn Championship - Southeast Asia 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-09-19 | Autumn Championship - Europe 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-09-19 | Autumn Championship - South America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |
| 2026-09-20 | Autumn Championship - North America 2026 | 1v1, 2v2 | Challengermode | Seasonal championship |

