# Database schema proposal

**Status: approved 2026-10-04; Phase 1 is in progress (§9).** Its fetches were complete on 2026-10-05, and the next step is the builder: the database built from the cache and `curation/`. The 2026-10-04 revision added the start.gg and Challengermode findings from [`platform-api-survey.md`](platform-api-survey.md), the decisions of that day (majors, tiers, crew battle head-to-heads, forfeits, data terms), the target questions (§8) and a three-phase implementation plan (§9).

**Decisions of 2026-10-04 on stage 6 and placements,** applied throughout:
1. **Brackets come from the platforms.** Match data is fetched event by event from start.gg (pool by pool for the four 2020 events over start.gg's 10,000-result cap) and Challengermode, not per player from the Stats API. Platform players are matched to Stats API records with batched ID lookups. A platform player with no Stats API record gets a `players` row with a stable negative ID (§1).
2. **Platform standings are the primary placement source:** start.gg standings for start.gg events, Challengermode entrant lists for Challengermode events. Stats API placements become a cross-check.
3. **Stages 3 and 4 are held** after their 200-player pilot. A small targeted fetch gets the three Pro Series finals' placements, which no platform has (§3, stage 3b).
4. **The two events that seemed one entrant short** in the standings fetch weren't. start.gg returned every entrant, but in each event one player was entered twice, and the crawl table's key kept only one of the two rows. A re-fetch would return the same data, so instead the key gains the entrant and the two events are re-applied from the cache (§1, placements).
5. **Merge candidates** are ranked by confidence. Only the strongest tier is accepted automatically, and the rest go to a review list (§1, players).

**Decisions of 2026-10-05,** after the full fetch:
1. **All three Pro Series finals count like crew battles.** They were team events: eight teams of three in each 2019 region, six teams of six in 2021. So `format_override = 'crew_battle'` is set in `curation/events.csv` (§1, events).
2. **Three start.gg events whose standings miss entrants who played** (SEA League Week 1/4, MAX MODE 2025, CEO Dreamland 2020):
   - their entrant lists were fetched, so all their sets can be attributed (stage P1b);
   - their placements come from the Stats API where it has them (stage 3c), and the rest stay unplaced;
   - placements are never derived from brackets.

   The Stats API had none of the 151, so all stay unplaced (§1, placements).
3. **The merge-candidate review list was built** (§1, players): 670 pairs accepted automatically, 2,187 for review.

**Scope: official events only** (decided 2026-10-03). Community events can be added later without changing the schema.

This proposal builds on [`api-survey.md`](api-survey.md), [`platform-api-survey.md`](platform-api-survey.md) and the rules decided in [`CLAUDE.md`](../CLAUDE.md).

## Design choices at a glance

1. **SQLite, rebuilt from a raw cache.** The database is one disposable file in `data/db/`. It is rebuilt from cached API responses without calling the API again. The data is small: about 1,800 events, and placements and matches in the hundreds of thousands at most. The DDL is written for SQLite; moving to Postgres would change a few functions, not the design.
2. **Two layers.**
   - A *fetcher* writes every API response to a cache.
   - A *builder* turns the cache, plus the curated files, into the database.

   Only the fetcher talks to the API.
3. **Python for the fetcher, not the Node SDK.** The API is plain unauthenticated HTTP GET. The SDK hides status codes, has a fixed 5-second timeout and never retries. A small Python client avoids all three and keeps the project in one language. The Node survey script stays as an exploration tool. The start.gg and Challengermode clients from the platform survey (`ingest/platform_clients.py`) are already Python.
4. **One row per Stats API event.** The API's "Tournament" is one bracket in one mode, and there is no separate tournaments table:
   - start.gg tournament slugs also group unrelated league weeks and regional brackets (survey §6);
   - Challengermode events have no parent at all.

   The grouping that matters, phases of one competition, is curated.
5. **Facts in tables, rules in views.** Tables store what the API reported. Curated corrections and the decided rules are applied in `v_` views, and the agent queries the views.
6. **Platform IDs on the core tables, and a `source` on every row.** That lets start.gg, Challengermode and Esports Earnings data attach without changing the core tables. The IDs are confirmed to line up: a Stats API match ID *is* the start.gg set ID or the Challengermode match ID, and player IDs join directly (§7).
   - **Placements and matches come from the platforms (decided 2026-10-04).** start.gg standings and sets cover start.gg events; Challengermode entrant lists and brackets cover Challengermode events.
   - **The Stats API supplies** player identities, PR, career earnings and the three Pro Series finals' placements, and its placements serve as a cross-check.
7. **Hand-made data lives in CSV files** in `curation/` (nicknames, merges, overrides, known events, prize reviews, and the deferred tiers). The builder loads them on every build, so a rebuild never loses them. They're committed, since the repo stays private (decided 2026-10-04). So far `tiers.csv`, `esports_earnings_snapshot.csv`, and the seed files `player_aliases.csv`, `player_merges.csv`, `merge_rejections.csv`, `external_ids.csv` and `events.csv` exist, holding decisions made so far. Each of the others is created in the phase that first uses it (§9).
8. **Built in three phases** (§9): the core tables and rule views, with placements and matches from the platforms, then earnings, then bracket structure and per-game data.

## 1. Schema

### Players

```sql
CREATE TABLE players (
  player_id      INTEGER PRIMARY KEY,   -- Stats API esports ID; negative for a platform-only player (below)
  name           TEXT NOT NULL,         -- current display name (newest response)
  sgg_player_id  INTEGER,               -- start.gg player ID
  cm_player_id   TEXT,                  -- Challengermode user UUID
  brawlhalla_id  INTEGER,               -- in-game ID
  country        TEXT,
  twitter        TEXT,
  twitch         TEXT,
  in_stats_api   INTEGER GENERATED ALWAYS AS (player_id > 0) VIRTUAL,
  source         TEXT NOT NULL DEFAULT 'stats_api',  -- 'stats_api' | 'startgg' | 'challengermode'
  updated_at     TEXT NOT NULL          -- fetch time of the response this row came from
);
CREATE INDEX players_sgg ON players (sgg_player_id);
CREATE INDEX players_cm  ON players (cm_player_id);

CREATE TABLE player_aliases (
  alias      TEXT NOT NULL,      -- normalized: lowercase, accents folded, no team tag, no punctuation
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  kind       TEXT NOT NULL,      -- 'display_name' | 'former_name' | 'without_tag' | 'nickname'
  shown_as   TEXT NOT NULL,      -- original spelling, e.g. 'ECHO | Marckiemoo'
  source     TEXT NOT NULL,      -- 'stats_api' | 'startgg' | 'curated'
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
  - The builder generates `display_name`, `without_tag` ("Pink | Guichabou" → "guichabou") and `former_name` rows. A former name is recorded when a later Stats API response shows a different name.
  - **start.gg is the main source of former names.** Its standings record the name each player used at each event, with the team tag of the time: BCX 2022's "Kingdom | Godly" is now Zivai, and "Pier" is now antireplay. The builder adds each one as a `former_name` row with source `startgg`, linked through `players.sgg_player_id` (Phase 1, §9). In 2v2 the entrant name is the team's, so only the participants' gamer tags are used.
  - `nickname` rows come from `curation/player_aliases.csv` (`alias`, `player_id`, `note`), seeded on 2026-10-04 with the decided ones:
    - "marckiemoo" → 146052, "hexo" → 169084, "sandstorm" → 74433 (gdsandstorm);
    - "flower" and "flowers" → 169119 (flowerVS);
    - "pugsyxd" → 146298 (Pugsy) and "pier" → 158406 (antireplay).
  - Accents are folded, so "Machèèèèté" and "Macheeeete" normalize alike. Without folding, Esports Earnings' "Macheeeete" missed its player. Folding merged no two different players' names in the cached sample.
  - Possessives are stripped before lookup: "flower's" → "flower", "flowers'" → "flowers".
  - A curated nickname wins over generated aliases, and the answer names any other player the name matches in one line. "flowers" is the case in point. It's also the display name of Flowers (156897, EU, ranked only in 2v2), but it's meant as "flower's", i.e. flowerVS (NA 1v1 PR #5), who played as "little flower" at BCX 2022 and "flower" at the NA Winter Championship 2025. When a curated alias and a generated one coincide, the builder keeps the curated row.
  - Otherwise, one alias can point to several players ("hardymj"), and the agent should ask when it does. It should also ask when a near miss, a letter off, is a far more prominent player than the exact match.
- **Platform IDs link directly.** A start.gg participant's player ID is `sgg_player_id`, and a Challengermode lineup member's user ID is `cm_player_id` (platform survey). Challengermode's Brawlhalla game account ID is a UUID unrelated to `brawlhalla_id`, so it isn't stored.
  - Every platform player is looked up in the Stats API by these IDs (stage 2b, §3): ListPlayers with `sggIds` or `cmIds`, 100 per request. That's about 1,400 requests for the 138,696 start.gg players in the standings.
- **Platform-only players (decided 2026-10-04).** A start.gg or Challengermode player with no Stats API record still gets a `players` row, so their placements and matches aren't lost.
  - **ID:** stable and negative, derived from the platform ID:
    - start.gg: `-sgg_player_id`;
    - Challengermode: `-(2^40 + the first 40 bits of the user UUID)`.

    The ranges can't meet, since start.gg IDs are far below 2^40. The builder stops if two players ever get the same ID.
  - **Marked as not in the Stats API:** `source` is `'startgg'` or `'challengermode'`, and `in_stats_api` is 0.
  - **Name and aliases:** the name comes from their newest standings entry (gamer tag, or the Challengermode username). Every name they used in standings becomes a `former_name` alias, as for other players.
  - **Re-resolved on every rebuild.** The builder looks each platform ID up in the newest cached lookup response. If a later lookup finds a Stats API record, the player moves to that record's ID. A curated row that names a platform-only player by its negative ID keeps working after such a move, because the builder resolves it through the platform ID it encodes.
  - **Rare, as measured on 2026-10-05:** of 146,359 platform players, only 98 have no Stats API record.
    - 42 start.gg players: 27 with placements, and 15 who played at the three events whose standings miss entrants (placements, below).
    - 56 Challengermode users. 55 of them never placed: they registered without playing, mostly as a 2v2 player without a partner.
  - **Only players who placed or played get a row,** so 43 platform-only players get negative IDs.
- **Merges** handle one person having two records, e.g. a start.gg-era record plus a Challengermode-era one (survey §4). Views report merged players under the canonical ID.
  - They come from `curation/player_merges.csv` (`player_id`, `canonical_player_id`, `note`): Remmy (59549 → 79652) and hardymj (632566 → 145900) decided by hand, and 670 pairs accepted automatically (below).
  - The record with more history stays canonical: more official events, then the earlier one.
  - Of the six likely pairs noted on 2026-10-04, three (zyder, SillyGobi, Djessir) were accepted automatically. The other three (Flamethrower, VS MATR1X, Mowgli) are in the review list, since each name also belongs to another start.gg record.
- **Merge candidates (decided 2026-10-04, built 2026-10-05)** come from `python ingest/merge_candidates.py`. It reads only the crawl's cache and tables, makes no requests, and can be re-run. Only 557 of the 4,981 ranked players had their start.gg and Challengermode IDs on one record.
  - **A candidate** is two Stats API records whose names match once normalized as aliases are, and whose official events don't overlap in time.
    - Two records active in the same period are almost always two people, so such pairs aren't listed.
    - Activity is every official event a record placed in or played, from the platform standings and entrant lists and from stages 3b and 3c.
    - A record's region is its PR region, or else the region most of its events name.
  - **Tier 1, accepted automatically (670 pairs).** A start.gg-only record and a Challengermode-only record, the usual duplicate after the 2025 platform switch.
    - Each is its name's only record on its platform, and no record of the name links both platforms.
    - Both are in the same region.
    - They're appended to `player_merges.csv` with a note starting `auto: tier 1`, so every merge in force is in one committed file you can edit.
    - A pair touching a record already in that file goes to review instead.
  - **Tier 2 (434 pairs):** such a cross-platform pair with one piece of evidence missing: a region unknown, or other records of the name on one platform.
  - **Tier 3 (1,753 pairs):**
    - the other cross-platform pairs (883), such as those in different regions;
    - two records on one platform (870), such as Remmy's two start.gg accounts, or a record linked to both platforms and an older start.gg record. They're listed when the name has no other record, their regions don't conflict, and one of them has at least three official events.

    Same-platform pairs are never accepted automatically. Most two-record names on start.gg are two people sharing a tag: there were 5,268 of them.
  - **The review list** is `data/review/merge_candidates.csv`, git-ignored, regenerated on every run.
    - It has the evidence for each pair and both records' names, platforms, regions, first and last events, event counts and best placements.
    - Within a tier, names shared by fewer other records come first, then the more prominent players.
    - A decision goes in `player_merges.csv` (merge) or `curation/merge_rejections.csv` (`player_id`, `other_player_id`, `note`; not one person). Either way, the pair isn't proposed again.
    - To undo an automatic merge, move its row from `player_merges.csv` to `merge_rejections.csv`.
  - **The esports team may share their account-link data** (asked 2026-10-04). That would settle most pairs directly.

### Events

```sql
CREATE TABLE tiers (               -- deferred (§5): curation/tiers.csv is a skeleton, not loaded yet
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
  tier                 TEXT REFERENCES tiers (tier),  -- deferred (§5): stays NULL for now
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
  - **Majors are official events (decided).** The agent filters on `is_official` by default and says "official events" in its answers, so it's clear what was counted. `tier` is kept for finer cuts later (Worlds, regional championships, …), but tiers are deferred: it stays NULL and nothing depends on it (§5). start.gg's own `Event.competitionTier` doesn't help, as it's 5 on all 470 Brawlhalla events checked.
  - **The known mode error:** CEO Dreamland 2017's doubles event gets `mode_override = '2v2'`.
  - **The three Pro Series finals** get `format_override = 'crew_battle'` (decided 2026-10-05). They were team events: eight teams of three in each 2019 region, six teams of six in 2021, each member sharing the team's place. So they count as 1v1, and answers label them as team results, as with crew battles. No payout data exists for them; if some is ever added, the 2021 final's prizes split six ways, not three.
  - These overrides, and the phase splits below, are in `curation/events.csv` (created 2026-10-05).
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
  team_id     INTEGER REFERENCES teams (team_id),  -- 2v2: the pair from the entrant
  source      TEXT NOT NULL,     -- 'startgg' (standings) | 'challengermode' (entrant lists)
                                 -- | 'stats_api' (the Pro Series finals)
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (event_id, player_id)
);
CREATE INDEX placements_player ON placements (player_id);
```

- **Where placements come from (decided 2026-10-04):**
  - start.gg events: start.gg standings (P1), one row per participant of every placed entrant.
  - Challengermode events: the entrant lists (P5), using each lineup's `bestPlacement`.
  - The three Pro Series finals, which neither platform has: the Stats API (stage 3b, §3).
  - Stats API placements from stage 3 are a cross-check (check 8, §4). In the stage 3 pilot, all 563 at start.gg events matched the standings exactly.
- **2v2 partners come with the entrant:** a start.gg 2v2 entrant lists both participants, and a Challengermode lineup both members. So `team_id` needs no team queries, and stage 4 isn't needed for it.
- **A player entered twice in one event.** In 2 of the 529 start.gg events, one participant appears in two entrants:
  - Spring Championship 2020 SA 1v1: P.V player, placed 97 and 513;
  - Low Tier City Midseason Online NA 2v2: ThousandCut / Thepokymater, placed 1025 and DQ'd at 2049.

  In 24 more, a player appears under two participant registrations. `standings` keeps every row, keyed by entrant. `placements` keeps one row per player: the better placement, preferring an entrant that wasn't DQ'd.
- **Three start.gg events' standings miss entrants who played** (found in the full run, 2026-10-05):

  | Event | Entrants in standings | Entrants in sets |
  |---|---|---|
  | SEA League (Week 1/4), 2017 | 37 | 74 |
  | MAX MODE 2025 1v1 | 8 (the top 8 only) | 41 |
  | CEO Dreamland 2020 1v1 (no standings at all) | 0 | 81 |

  Those 151 entrants have no placement from the standings, and the standings were also how an entrant mapped to its players. Decided 2026-10-05:
  - **Entrant lists for their sets.** The events' entrant lists (stage P1b, 197 entrants in 5 requests) map every entrant to its players, so all their sets can be attributed. The builder takes an entrant's players from `standings`, or else from these lists.
  - **Placements from the Stats API, where it has them** (stage 3c). It had none: of the 151 entrants' players, 136 have a Stats API record, and none has a placement at these events. Each check's page listed the player's earlier official events, so the check itself worked.
  - **The rest stay unplaced, as all 151 do.** Placements are never derived from brackets, and answers about these events say their placements are incomplete.
- **Challengermode lineups that never played aren't entrants.** A roster can list lineups with no placement that appear in no series: 83 of 11,996, mostly a 2v2 player without a partner (47 of them at BCX 2025 2v2, which lists 298 lineups for a count of 256). Only lineups with a placement become placements.
- There is no separate team-placement table. A team's result is the placement its two players share; see `v_team_results` in §2.

### Matches

```sql
CREATE TABLE matches (
  match_id      TEXT PRIMARY KEY,  -- start.gg set ID, or Challengermode match UUID (not the series UUID)
  event_id      TEXT NOT NULL REFERENCES events (event_id),
  side1_score   INTEGER NOT NULL,  -- games won; -1 = DQ'd; 0-0 = forfeit
  side2_score   INTEGER NOT NULL,
  is_dq         INTEGER GENERATED ALWAYS AS (side1_score < 0 OR side2_score < 0) VIRTUAL,
  is_no_contest INTEGER GENERATED ALWAYS AS (            -- a DQ or a forfeit: neither a win nor a loss
                  side1_score < 0 OR side2_score < 0
                  OR (side1_score = 0 AND side2_score = 0)) VIRTUAL,
  dq_side       INTEGER GENERATED ALWAYS AS (
                  CASE WHEN side1_score < 0 AND side2_score < 0 THEN 0   -- both sides
                       WHEN side1_score < 0 THEN 1
                       WHEN side2_score < 0 THEN 2 END) VIRTUAL,
  winner_side   INTEGER GENERATED ALWAYS AS (
                  CASE WHEN side1_score < 0 OR side2_score < 0 THEN NULL
                       WHEN side1_score > side2_score THEN 1
                       WHEN side2_score > side1_score THEN 2 END) VIRTUAL,   -- NULL for 0-0
  start_time    INTEGER,           -- start.gg startedAt / Challengermode series startedAt, when reported
  legends_json  TEXT,              -- per side, per game, when reported
  maps_json     TEXT,
  source        TEXT NOT NULL,     -- 'startgg' (sets) | 'challengermode' (matches)
  fetched_at    TEXT NOT NULL
);

CREATE TABLE match_players (
  match_id   TEXT NOT NULL REFERENCES matches (match_id),
  side       INTEGER NOT NULL CHECK (side IN (1, 2)),
  player_id  INTEGER NOT NULL REFERENCES players (player_id),
  PRIMARY KEY (match_id, player_id)
);
```

- **Where matches come from (decided 2026-10-04):** every set of every official start.gg event, and every match of every official Challengermode event, fetched event by event (P4 and P5, §3). The per-player Stats API route (stage 6) isn't used.
- **Sides** follow the platform: side 1 is start.gg's first slot, or Challengermode's lineup number 0.
  - **Players come from the entrant:** a start.gg slot's entrant leads to its participants through the standings, and a Challengermode lineup lists its members. 2v2 partners are therefore always both present.
  - **Byes** (a set or series with fewer than two entrants) aren't matches and aren't stored.
  - **Replayed matches:** a Challengermode series can hold a cancelled match besides the one that was replayed (164 of 23,948 matches in all). Only completed matches are stored.
- **Match IDs.** `match_id` is the start.gg set ID (14 of 14 checked) or the Challengermode *match* UUID, not the match-series UUID. Scores agree with both platforms and the Stats API, so the Stats API's own match records add nothing. The series UUID is kept in `match_bracket_info` (§7).
- **DQs and forfeits are no-contests.** `is_no_contest` covers both, and the record views drop them (§2). The matches stay in the table, because they happened.
  - A DQ is a `-1` score, the same on start.gg as in the Stats API. DQs are common: 352 of BCX 2022's 1,204 1v1 sets.
  - A Challengermode no-show is a match with no scores at all, which the Stats API reports as 0–0. The builder stores it as 0–0 too. The 0–0 doesn't say who advanced (Challengermode's series result does), but under the decided rule a forfeit is neither a win nor a loss anyway.
  - `is_dq` still tells the two apart, so an answer can say "one opponent was DQ'd".
  - No start.gg match in the survey sample was 0–0 (none of 39). A start.gg set with no scores and no winner was never played, so it isn't stored. Check 9 (§4) counts those, and lists any set with a winner but no score for a look.
  - **In the full fetch (2026-10-05):**

    | start.gg's 536,633 sets | Count |
    |---|---|
    | A DQ | 258,886 (48%) |
    | … of which double DQs (−1 against −1) | 106,899 |
    | One score missing (981 of them a −1 against no score) | 989 |
    | A winner but no score | 278 |
    | Never played (no score, no winner) | 173 |
    | Fewer than two entrants | 189 |

    - No start.gg set is 0–0 or any other tie.
    - Challengermode has 2,176 matches without scores (forfeits) among its 23,948.

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
| "Entered" counts every official event, side formats included | `v_entries` |
| Medals are top-3 placements at official events | `v_medals`, `v_player_medals` |
| A "major" is an official event, and answers say "official events" | `is_official` is the default filter; `v_official_wins` |
| Tiers are deferred | `events.tier` stays NULL; `v_tier_results` isn't created yet (§5) |
| DQs (a −1 score) and forfeits (0–0) count as neither a win nor a loss | `matches.is_no_contest`, applied in `v_match_results` and both head-to-head views |
| In head-to-heads, a crew battle match counts only if stored as a one-on-one game | `v_head_to_head_1v1` (one player per side) |
| 2v2 prizes are per team, crew battle prizes per crew | `v_player_event_earnings` (§6b) |

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

-- Every event a player entered, in any format: side formats have mode NULL.
-- For "last event entered" questions (§8, answer rule 2).
CREATE VIEW v_entries AS
SELECT i.canonical_id AS player_id, v.event_id, v.tournament_name, v.event_name,
       v.start_date, v.start_time, v.format, v.counts_as AS mode, v.is_official, p.placement
FROM placements p
JOIN v_events v     ON v.event_id = p.event_id
JOIN v_player_ids i ON i.player_id = p.player_id;

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

-- Wins: first place at an official event. Questions about "majors" use this,
-- and answers say "official events".
CREATE VIEW v_official_wins AS
SELECT * FROM v_results WHERE is_official = 1 AND placement = 1;

-- Deferred (§5): not created until tiers are decided. Results with their tier's rank and label.
CREATE VIEW v_tier_results AS
SELECT r.*, t.rank AS tier_rank, t.label AS tier_label
FROM v_results r
JOIN tiers t ON t.tier = r.tier;

-- 2v2 results by team.
CREATE VIEW v_team_results AS
SELECT DISTINCT r.team_id, t.player1_id, t.player2_id, r.event_id, r.competition_key,
       r.placement, r.is_official, r.tier, r.tournament_name, r.year, r.start_date
FROM v_results r
JOIN teams t ON t.team_id = r.team_id
WHERE r.mode = '2v2';

-- One row per player per match that counts. No-contests (DQs and forfeits) excluded.
CREATE VIEW v_match_results AS
SELECT i.canonical_id AS player_id, m.match_id, mp.side, v.event_id, v.competition_key,
       v.counts_as AS mode, v.format, v.is_official, v.start_date,
       CASE mp.side WHEN 1 THEN m.side1_score ELSE m.side2_score END AS games_won,
       CASE mp.side WHEN 1 THEN m.side2_score ELSE m.side1_score END AS games_lost,
       CASE WHEN m.winner_side = mp.side THEN 1 ELSE 0 END AS won
FROM matches m
JOIN match_players mp ON mp.match_id = m.match_id
JOIN v_player_ids i   ON i.player_id = mp.player_id
JOIN v_events v       ON v.event_id = m.event_id
WHERE m.is_no_contest = 0                     -- a DQ or forfeit is neither a win nor a loss
  AND m.winner_side IS NOT NULL               -- other ties aren't expected (check 9, §4)
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
WHERE m.is_no_contest = 0 AND m.winner_side IS NOT NULL
GROUP BY ta.team_id, tb.team_id;
```

**Crew battle matches (decided 2026-10-04).** Crew battles count as 1v1 for placements. In head-to-heads, `v_head_to_head_1v1` only counts matches with one player per side, so a crew battle match counts only if the API stores it as a one-on-one game. Crew-against-crew matches are left out. The survey didn't fetch a crew battle match, so Phase 1 checks which shape they have.

## 3. Crawl strategy

### Files

```text
data/raw/cache/<endpoint>/<key[:2]>/<key>.<fetched_at>.json.gz   one immutable file per response
data/db/crawl.sqlite                                             request log and task queue
data/db/brawlhalla.sqlite                                        the built database (disposable)
curation/*.csv                                                   hand-made data
```

`key` is a hash of the endpoint and its normalized parameters (sorted, lists comma-joined). The `fetched_at` timestamp in the file name means a refresh adds a file rather than overwriting one.

### Stages

**Scope (decided): official events only.** Every list call passes `isOfficial=true`. Community events, and players who only played community events, are left out for now. The schema doesn't change if they're added later.

| Stage | Calls (rough) | Result | Status (2026-10-04) |
|---|---|---|---|
| 0. Events: ListEvents for both modes with `isOfficial=true`, all pages; per-year crawls as a cross-check | ~13, plus ~20 | All 622 official events | Done |
| 1. Seed: ListPr for NA, EU, SA, SEA and MENA × 1v1/2v2, 100 rows per page | ~70 | ~6,700 PR rows, roughly 4–5k ranked players, with their PR stats and earnings | Done: 4,981 players |
| 2. Profiles: ListPlayers in batches | 1 per batch | start.gg, Challengermode and in-game IDs | Done for the PR players |
| 2b. Platform lookups: ListPlayers by `sggIds` (players in start.gg standings) and `cmIds` (Challengermode entrant lists), 100 per request | ~1,400 + ~100 | The Stats API record of each platform player, or none (a platform-only player, §1) | Done 2026-10-05: 146,258 found, 83 not |
| 3. Histories: GetPlayerPlacements (both modes, `isOfficial=true`) and GetPlayerTeammates (`isOfficial=true`) per player | ~2–4 per player | The official events each known player entered, and their partners | Piloted on 200 players; full run held |
| 3b. Pro Series finals: one GetPlayerPlacements page per candidate and finals | ~990 (153 + 411 + 428) | Placements at the three `series/…` events | Done 2026-10-05: 84 placements |
| 3c. Gaps: the same check for the players of entrants in a start.gg event's sets but not its standings (after P1b and 2b) | 1 per player | Their placements, where the Stats API has them | Done 2026-10-05: 136 checked, none placed |
| 4. Teams: GetPlayerPlacements with both IDs, per partner pair | 1 per pair | `team_id` on 2v2 placements | Piloted; full run held |
| 5. Discovery: new players from official teammates and from opponents in official matches, sent back to stage 2 | — | Unranked and inactive players, such as Boomie | Not needed |
| 6. Matches: GetPlayerMatches per (player, official event), de-duplicated by `matchId` | 1 per pair | Match-level results for official events | Replaced by P4 and P5 |
| 7. Earnings gaps: SearchPlayers by name for unranked players with official results | 1 per player | Stats API earnings where search has them (players with a Challengermode account) | Not started |

- **The platforms replace stages 3–6 (decided 2026-10-04).** Standings and entrant lists list every entrant of every official event, so they give placements and 2v2 pairs without per-player calls, and every player without discovery. Event-level brackets give every match.
  - The 2026-10-04 comparison measured both routes. The platform route takes about 15,500 start.gg requests, 180–270 Challengermode requests and 1,400 lookups, about 5.3 hours in all. The per-player route needs a Stats API call for every (player, event) pair, and every player found first.
  - Stages 3 and 4 stay in the code. Their 200-player pilot is the cross-check for platform placements (check 8, §4), and they can still be run in full later.
  - Stage 6's per-player code is dropped, since it would never run.
- **Stage 3b exists because no platform has the Pro Series finals.** The 2019 NA and EU Finals and the 2021 Finals use `series/…` IDs, which no platform event matches and GetPlayerMatches rejects. The Stats API has their placements but no event endpoint, so they're reached through likely entrants:
  - **Candidates:** the top 32 of every official start.gg event, 1v1 or 2v2, in the year before each final, in the final's region or with no region in its name. Their Stats API records come from the stage 2b lookups, or from ListPlayers by `sggIds` for any not yet looked up.
  - **One request per candidate:** GetPlayerPlacements with `nextToken` set just after the final's start time returns the player's newest official events up to the final, so one page shows whether they played it.
  - **A completeness check:** the placements found should form a complete bracket (1, 2, 3, 4, 5, 5, 7, 7, … for double elimination). A gap means a missing entrant, and the stage reports it.
  - **The 2021 final is a team event** (pilot, 2026-10-04): 36 placements, six teams of six, each member sharing the team's place.
    - The first candidate rule, the top 16 of 1v1 events, found only 29 of them: team sizes 4–6 hinted at gaps.
    - Two finalists never placed better than 17th, and one played mainly 2v2 (Boomie), hence top 32 and both modes.
    - Six even teams suggest the list is now complete, but a team format can't be checked from places alone.
  - **The 2019 finals are team events too** (full run, 2026-10-05). NA and EU have the same shape: 24 placements each, which reads as eight teams of three.
    - 1st and 2nd go to one team each, and two teams share each of 3rd, 4th and 5th.
    - NA was won by gdsandstorm, Remmy and Boomie, and EU by simpLe, blews and VipR3.
    - Both regions having the same eight even teams suggests both lists are complete.
  - These events still have no match data.

### The pagination bugs

- **Timestamp tokens (ListEvents, GetPlayerPlacements, GetPlayerTeammates).** Request the next page with `nextToken = last row's startTime + 1` rather than the server's token, and de-duplicate by ID.
  - That re-reads the boundary timestamp, so tied events can't be skipped.
  - Stop when a page adds nothing new.
  - If a *full* page adds nothing new (more ties than one page holds), fall back to the server token and log it.
  - As a cross-check, event totals must equal the sum of the per-year crawls.
- **GetMatchup tokens.** Used for discovery only. Stop at "Invalid next token" and log it. Never build records from GetMatchup, because it also counts DQs.
- **SearchPlayers.** Not used for crawling: it can't paginate and it misses inactive players.

### Platform crawls (start.gg and Challengermode)

Both platforms use the same cache, request log and task queue as the Stats API. Their clients come from the platform survey (`ingest/platform_clients.py`), adapted to write to the cache. There are 529 official start.gg events with an event to query, and 90 official Challengermode ones.

| Stage | Phase | Calls (rough) | Result | Status (2026-10-04) |
|---|---|---|---|---|
| P1. start.gg standings for each official start.gg event, 64 entrants per page | 1 | 1–10 per event (BCX 2022 1v1, with 603 entrants, takes 10) | Placements for start.gg events, the names players used at each event, and every start.gg player | Done: 267,697 entrants, 138,696 players, 4,455 requests |
| P1b. start.gg entrant lists (`Event.entrants`, 64 per page) of the events whose sets name entrants missing from their standings; it runs after P4, which records every set's entrants | 1 | 1–2 per event | The players of those entrants, so their sets can be attributed | Done 2026-10-05: 3 events, 197 entrants, 5 requests |
| P2. start.gg `Event.prizingInfo` for each official start.gg event | 2 | 1 per event | Structured payouts (§6b) | |
| P3. Challengermode tournament `description` for each official Challengermode event | 2 | 1 per event | Prize splits to parse (§6b) | |
| P4. start.gg brackets: phases and pools (with round best-ofs), every set, and games in the last phase | 1 (was 3) | 12,615 in all, pilot included | `matches`, and later the bracket tables and `match_games` (§7) | Done 2026-10-05: all 536,633 sets |
| P5. Challengermode entrant lists (the roster with placements), and stages, brackets, rounds, series and matches | 1 (was 3) | 2 per event, 183 in all | Placements and `matches` for Challengermode events, and later the bracket tables (§7) | Done 2026-10-05: 90 events, 23,948 matches |

- **Events come from the Stats API.** Each platform is queried by ID: start.gg by event slug (the Stats API event ID), Challengermode by tournament UUID. Challengermode's list queries are capped at about 48 results with no paging, so they're never used to enumerate. The three `series/…` events have no start.gg event to query.
- **P4 and P5 moved to Phase 1 (decided 2026-10-04),** because they're now where matches come from. Phase 3 still builds the bracket tables and `match_games` from their cached responses, with no further fetching.
- **Request gaps:** at least 1 s on start.gg (80 requests per minute allowed) and 3.5 s on Challengermode (bots get 20 per minute). The survey ran at those gaps without throttling and saw no rate-limit headers.
- **start.gg's query limit:** queries over 1,000 objects are rejected, so pages stay small. Each response reports `extensions.queryComplexity`, counted from the objects actually returned. A complexity error is final, not retried. Measured on 2026-10-04:

  | Page | Complexity |
  |---|---|
  | 64 standings | 321 |
  | 50 sets (17 each, with slot scores) | 851–863 |
  | 16 pools with 320 rounds | 353, so pages hold 32 pools |
  | 16 sets with games (1v1) or 8 (2v2) | up to 369 |
- **start.gg field errors:** `PhaseGroup.startAt` fails with an internal error on the 2020 SteelSeries pools, every time, so it isn't fetched. Any GraphQL error now fails a page, even when other data came back, and `status` shows the field that failed.
- **start.gg's 10,000-result cap:** a listing can't be paged past its 10,000th entry ("Cannot query more than the 10,000th entry"). Four official events have more sets than that: the 2020 1v1 events of the NA and EU SteelSeries Championships, Low Tier City Midseason Online NA and the NA Mammoth Cup (10,932–14,478 sets). Their sets are fetched pool by pool, about 70 pools each.
- **Completeness:** for each event, the sets fetched must equal start.gg's own total, and each Challengermode entrant list must hold as many lineups as the roster's count. The stages check both when they finish.
- **Games** are fetched for an event's last phase only, and only when it has at most 16 seeds: a Top 8 or Top 16. The last phase is the smallest one, because start.gg's `phaseOrder` isn't always bracket order: the EU SteelSeries Championship 2020 numbers its Top 256 phase 4, after Top 32 and Top 8.
- **The pilot (2026-10-04)** ran every new stage on a few events, about four minutes in all. Requests: start.gg 95, Stats API 234, Challengermode 2 plus one token exchange.
  - **Standings fix:** the two events were re-applied from the cache with no requests, and none is short now.
  - **start.gg, BCX 2022 1v1:** all 1,204 sets in 31 requests and 33 s. 352 DQs, as the survey found. The Finals' 43 games came back, all with stage and characters.
  - **start.gg, US Winter Championship 2017 2v2:** all 840 sets. 390 are DQs, and 2 have a winner but no score.
  - **start.gg, EU SteelSeries Championship 2020 1v1 (two pools per phase):** 6 of its 70 pools, 641 of its 12,319 sets. Its Top 8 has 46 games, all with stage and characters.
  - **Challengermode, Autumn Championship NA 2026 1v1:**
    - all 284 lineups, and 1,023 series, of which 567 are between two lineups, each with its match;
    - 48 matches have no scores (forfeits);
    - two series also hold a cancelled match that was replayed, so the builder keeps completed matches only;
    - Raydish's 6 Stats API matches agree with it on IDs and scores.
  - **Lookups:** all 7,825 players of those four events have a Stats API record.
  - **Pro Series 2021 final:** 36 placements, a team format (stage 3b above).
  - **Speed:** about 1.05 s per start.gg request, set pages included (median response 1.0 s, at most 4 s). 0.5 s per Stats API request. Challengermode's responses took 4 s for the entrant list and 6 s for the 1,023-series bracket.
- **The full run (2026-10-05)**, against the estimate made from the pilot:

  | Stage | Estimate | Actual |
  |---|---|---|
  | P4 | about 12,800 requests, 3.7–6 hours | 12,521 requests in 4.9 hours (1.4 s each). All 529 events complete: 536,633 sets, and 17,537 games in the 4,750 last-phase sets that report games (13,617 with a stage, 8,732 with characters). |
  | P5 | about 180 requests, 15 minutes | 179 requests in 13 minutes, plus 4 in a retry. All 90 events: 11,996 lineups and 23,948 matches. |
  | 2b | about 1,400 requests, 12 minutes | 1,385 requests in 12 minutes, plus 1 after the retry. 146,258 players found, 83 not (§1). |
  | 3b | 839 requests, 7 minutes | 839 requests in 7 minutes. 24 placements at each 2019 final. |

  - **Challengermode timeouts:** three queries ran past Challengermode's 15 s budget during the run: two brackets and one entrant list, of events with 64–315 lineups. The server answers that with an HTTP 400 and error code HC0045, which the client took as final. It's now logged as a timeout (504) and retried, and the three went through at once with `cm --retry-rejected`.
  - **Since then, every check passes.** The bracket check covers the sets of every start.gg event and a match in every Challengermode series between two lineups. The entrant-list check now confirms that every lineup in a bracket is in its event's entrant list. It used to compare the roster's lineup count, which counts lineups that never played (§1).
- **Challengermode tokens** last 20 minutes. The crawl client reuses the survey client's token handling: it exchanges the refresh key for a token, renews it 2 minutes before its `expiresAt` rather than once at startup, and on an auth error (a 401 or `AUTH_NOT_AUTHENTICATED`) gets a new token and retries once. A test simulates a token expiring mid-crawl.
- **User-Agent:** every request sends a custom one, because Challengermode's Cloudflare front end rejects Python's default (error 1010).
- **Credentials** come only from `.env`: `STARTGG_API_TOKEN` and `CHALLENGERMODE_REFRESH_KEY`, plus an Esports Earnings key once access works (§6a). They go into request headers and nowhere else: not the cache, the request log or any output. The token exchange isn't cached either. `CHALLENGERMODE_APP_ID` turned out not to be needed.
- **Cache keys** hash the platform, the GraphQL document and its variables, so changing a query's fields fetches afresh.

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
- **For each new official event:**
  - fetch its standings or entrant list and its bracket (P1, P4 or P5);
  - if its sets name entrants its standings lack, fetch its entrant list (P1b);
  - look up any new platform players (2b), and check the Stats API for the missing entrants' placements (3c);
  - re-run `ingest/merge_candidates.py`;
  - fetch its prize data once Phase 2 is built.
- **Not refreshed:** the Esports Earnings snapshot (§6a) was a one-time copy, made outside the crawl.

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
4. **Teammates:** every 2v2 placement has a `team_id`. For the players in the stage 3 pilot, GetPlayerTeammates `games` also add up to their number of 2v2 placements.
5. **Platform completeness:** for each event, the sets fetched equal start.gg's own total (summed over pools for the four events fetched pool by pool), and every lineup in a Challengermode bracket is in the event's entrant list, which isn't cut off at the query's limit. The crawl checks this when P4 and P5 finish; both passed on 2026-10-05. P1b then checks that every entrant in a start.gg set is in its event's standings or entrant list: 151 entrants of three events weren't in the standings, and all of them are now in an entrant list (§1).
6. **Match presence:** every placed entrant has at least one set or match, unless they only had byes or were DQ'd before playing.
7. **Earnings:** once payouts exist (§6), a player's summed per-event prizes shouldn't exceed their career figure. This is also the backstop for prize splits copied from another event's description (§6b).
8. **Standings against the Stats API (exact):** platform standings are the placements (decided 2026-10-04), and every Stats API placement we hold is compared with them, player by player, through `sgg_player_id` and `cm_player_id`. The check reports placements the platform lacks and values that differ.
   - The Stats API placements come from the stage 3 pilot (200 players), so this is a sample rather than a census. All 563 of the pilot's placements at start.gg events matched the standings exactly.
   - Phase 1 runs it for both platforms.
9. **No-contests:** count DQs and 0–0 forfeits by platform. A 0–0 on a start.gg event, or a tie other than 0–0, isn't expected, so each one is listed for a look. So are start.gg sets with a winner but no score. Sets never played (no score, no winner) are counted.
10. **Snapshot fallbacks:** every player whose career figure comes from the Esports Earnings snapshot should have an official top-32 placement. One without is listed for a look, since a same-name mismatch is the likely cause (§6a).
11. **Pro Series finals:** the placements found at each of the three finals form a complete bracket (stage 3b, §3).

These results feed a `v_event_coverage` view. For each event it shows placements held, the worst placement seen, players with match data, 2v2 placements with no known partner, and, where standings exist, entrants we hold no placement for.

## 5. Official events for tier assignment

**Tiers are deferred (decided 2026-10-04).** For now "major" means an official event, and the agent filters on `is_official`. The design keeps `events.tier`, the `tiers` table and `v_tier_results` for later, but the builder doesn't read [`curation/tiers.csv`](../curation/tiers.csv) yet, and nothing depends on it.

The full list is in the [appendix](#appendix-official-events): 622 official events (375 1v1, 247 2v2) grouped into 410 tournaments. Each tournament's 1v1 and 2v2 events share a row, and the rows are grouped by year. The "family" column is a name-based guess, there only to make sorting easier.

`curation/tiers.csv` is a skeleton: the example scale (S = World Championship, A = Midseason and major partner events, B = regional championships, C = other official events) with a default tier for each family. It has one row per tier, listing the families that default to it.

| Family (auto-detected) | Key in `tiers.csv` | Tournaments | Default tier |
|---|---|---|---|
| Seasonal championship | `seasonal_championship` | 172 | B |
| Invitational / cup / league | `invitational_cup_league` | 54 | C |
| Partner event (CEO, DreamHack, …) | `partner_event` | 33 | A |
| Other | `other` | 32 | C |
| Qualifier / LCQ | `qualifier` | 31 | C |
| Trial of … (2024) | `trial_of` | 29 | C |
| World Championship | `world_championship` | 16 | S |
| Excluded format | `excluded_format` | 12 | C |
| Royale | `royale` | 9 | C |
| Regional championship (AUS, BRZ, SEA) | `regional_championship` | 8 | B |
| Midseason | `midseason` | 7 | A |
| Crew battle (counts as 1v1) | `crew_battle` | 6 | C |
| Community tournament | `community_tournament` | 1 | C |

Defaults that will need overrides:
- **DreamHack Atlanta 2018** was, as far as I know, the 2018 World Championship. Its events are named just "Brawlhalla 1v1" and "Brawlhalla 2v2", so it's detected as a partner event (A). Confirm, then override it to S.
- **The 2020 and 2021 online Worlds** ran in five regions each, and all ten are in the World Championship family (S). They may deserve a lower tier than BCX.
- **Every partner event defaults to A,** including small ones such as GoTE 4TheKids 2017 and SLAM 2017.

When tiers are picked up:
1. Settle the scale in `curation/tiers.csv`.
2. Turn the family detection into a curated rules file like `format_rules`. Today the families exist only as a column in the appendix.
3. Override individual tournaments in `curation/events.csv`. A tier set on a tournament applies to all of its events (both modes, all phases).
4. The builder then fills `events.tier`, and `v_tier_results` is created.

## 6. Earnings

### 6a. Career earnings

```sql
CREATE TABLE player_external_ids (
  player_id    INTEGER NOT NULL REFERENCES players (player_id),
  source       TEXT NOT NULL,         -- 'esports_earnings' (later perhaps 'liquipedia')
  external_id  TEXT NOT NULL,         -- Esports Earnings player ID
  link_method  TEXT NOT NULL,         -- 'alias' (one player through player_aliases)
                                      -- | 'manual' (curation/external_ids.csv)
  PRIMARY KEY (player_id, source)
);

CREATE TABLE player_earnings (
  player_id   INTEGER NOT NULL REFERENCES players (player_id),
  source      TEXT NOT NULL,          -- 'stats_api' | 'esportsearnings_manual'
  amount_usd  REAL NOT NULL,
  as_of       TEXT NOT NULL,          -- the date the figure is current to (below)
  fetched_at  TEXT NOT NULL,
  PRIMARY KEY (player_id, source)
);

-- One career figure per player: the Stats API's if any of the player's records has one,
-- otherwise the Esports Earnings snapshot's.
CREATE VIEW v_career_earnings AS
SELECT i.canonical_id AS player_id, p.name,
       COALESCE(MAX(CASE WHEN e.source = 'stats_api' THEN e.amount_usd END),
                MAX(CASE WHEN e.source = 'esportsearnings_manual' THEN e.amount_usd END)) AS earnings_usd,
       CASE WHEN MAX(e.source = 'stats_api') = 1 THEN 'Stats API'
            ELSE 'Esports Earnings snapshot' END AS source,
       COALESCE(MAX(CASE WHEN e.source = 'stats_api' THEN e.as_of END),
                MAX(CASE WHEN e.source = 'esportsearnings_manual' THEN e.as_of END)) AS as_of
FROM player_earnings e
JOIN v_player_ids i ON i.player_id = e.player_id
JOIN players p      ON p.player_id = i.canonical_id
GROUP BY i.canonical_id, p.name;
```

**The Stats API figure is the primary source.** It is recorded only when the player has a PR row, or when SearchPlayers returned non-null earnings. GetPlayerPr's `0` for an unranked player means *unknown*, not zero. Its `as_of` is ListPr's `lastUpdated`, or the search date for figures that came from SearchPlayers.

**The fallback is a one-time Esports Earnings snapshot (decided 2026-10-04).** The Esports Earnings API is blocked, because the account login isn't working, so the fallback comes from a copy of the website's Brawlhalla top-players list:
- `ingest/snapshot_esports_earnings.py` fetched the five list pages, covering the top 500 players, on 2026-10-04, at least 2 s apart. The raw HTML is in `data/raw/esportsearnings/`. It isn't a crawl stage, and it isn't refreshed (§3).
- Their robots.txt couldn't be read, because it redirects to itself. RFC 9309 treats a robots.txt not reached within five redirects as unavailable, which permits crawling, and the fetch went ahead on that basis. The script still checks it, and stops if it ever disallows the pages.
- `curation/esports_earnings_snapshot.csv` has the rank, handle, Brawlhalla total in USD (not the site's all-games total), source page, as-of date (2026-10-04) and Esports Earnings player ID. The pages also show real names, which aren't stored.
- Each figure's `as_of` is the snapshot date. The site's Brawlhalla records ran through 2026-07-19 at the time. That lag doesn't matter here: the fallback only covers players without a Stats API figure, meaning no PR row and no Challengermode account, so no official results since mid-2025. The old `may_be_stale` flag is dropped for the same reason.

**Loading the snapshot (Phase 2):**
1. A row is linked to a player through `curation/external_ids.csv` (`source`, `external_id`, `handle`, `player_id`, `note`) when it's listed there. That file is seeded with four links confirmed through start.gg player IDs on 2026-10-04: SAC, Macheeeete, Solarson and TheNinja729. Otherwise its handle is normalized like an alias and looked up in `player_aliases`: a curated nickname wins, and candidates are mapped to canonical players (§1). Exactly one player gives a `player_external_ids` link with `link_method = 'alias'`.
2. Each linked row becomes a `player_earnings` row with source `esportsearnings_manual`, the snapshot's total and its as-of date.
3. Rows with no candidate, several candidates, or a player another row already took go on a review list. A decision goes in `curation/external_ids.csv`, or in `curation/player_aliases.csv` when the handle is a name people use ("godly" → Zivai).
4. `v_career_earnings` uses a snapshot figure only for players without a Stats API figure on any of their records. The other snapshot rows stay in `player_earnings`, unused, so the two sources can still be compared.
5. Check 10 (§4) lists fallback players with no official top-32 placement, since a same-name mismatch is the likely cause.

The handles often differ from our display names:
- Sandstorm = gdsandstorm, Godly = Zivai, Kyna = whoiskyna, Fiend = lFiend, Experience = experiencedoa, lores = loreszz;
- Pier = antireplay, Pugsyxd = Pugsy;
- SAC = sacwastaken, Macheeeete = Machèèèèté, Solarson = solarsontk.

start.gg former names catch many of these, and nicknames and manual links cover the rest. Esports Earnings also has its own duplicates. "Flower" and "little flower" are separate profiles there that both resolve to flowerVS, and two different "Akeno" profiles resolve to one player. Rule 3 sends them to review.

**The Esports Earnings API stays blocked.** If access is resolved, it would add per-tournament rows (§6b) and could refresh the totals. Until then the snapshot provides the career figures.

### 6b. Per-tournament earnings

Per-placement payouts come from a different place in each era. They all map to players the same way: the amount for placement P goes to every player who placed P, split across the team in 2v2 and across the crew in crew battles.

| Official events | Source | Form | Coverage |
|---|---|---|---|
| 2019 to June 2025 (start.gg) | `Event.prizingInfo` | Structured: `{placement, amount, percent}` per paid place, `payoutType: "fixedAmount"`, currency from `Tournament.currency` | 14 of 19 sampled events, including every one from 2019 on except MAX MODE 2025 (table below). Confirmed through the API on BCX 2022 and the NA Winter Championship 2025. |
| 2017–2018, and league or series events (start.gg) | none | — | No payouts, and no prize text anywhere on start.gg. Esports Earnings' per-tournament rows are the only source, and they're blocked for now (§6a), so these events have no payout data. |
| Mid-2025 on (Challengermode) | `Tournament.description` | A PRIZESPLIT text block, parsed | 10 of 11 official events checked; 9 of those 10 add up to the stated total. |

The schema details that were read from documentation on 2026-10-03 were all confirmed through the APIs on 2026-10-04; see the platform survey's [hint checks](platform-api-survey.md#checking-the-hints).

**start.gg payouts, event by event.** I read 19 official event pages, matching each event by its slug.

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

**Challengermode prize splits.** Challengermode's API has no prize fields, but official tournaments' descriptions state the pool and how it's split:

```text
+ **Prizes:** _$5,500_
…
**PRIZESPLIT**
+ **1st** $2000
+ **2nd** $1000
+ **3rd** $700
+ **4th** $500
+ **5th** $250
+ **5th** $250
…
```

- **Parsing.** The format is regular enough for a plain parser. Each split line becomes a `prize_payouts` row with source `parsed_text`. Shared places repeat (two 5th places), and a line's placement uses the Stats API's numbering (Challengermode's `bestPlacement`), so the rows join to `placements` directly. The stated total and the split's sum go into `event_prizes`.
- **Automatic check.** When the split adds up to the stated total, the event is accepted without review.
- **Manual review list.** Everything else is listed in `v_prize_review`, and a person records a decision in `curation/prize_reviews.csv` (event, accept or reject, note). The known cases:
  - Spring Championship SEA 2025 1v1: the split sums to $2,000 against a stated "$4,000", probably the whole championship's pool.
  - BCX 2025 1v1: there's no split, only "$200,000 prize pool" and a link to brawlhalla.com/news/bcx2025. A split copied by hand from that page goes in `curation/prize_payouts.csv` (source `curated`, with the URL). Without one, the event stays `pool_only`.
- **Reused text.** Descriptions are copied from event to event: the Autumn NA 2026 text says the bracket "will begin on Sunday, July 19th". A matching total shows that the text is self-consistent, not that it belongs to this event. Check 7 (§4), against career figures, is the backstop.

**Esports Earnings** has prize money per player, per tournament: `TournamentName`, `EndDate`, `RankText`, `Prize`, `CurrencyCode`, `ExchangeRate` and `TeamPlayers`. It has no start.gg or Challengermode IDs, so matching to our events is by name and date. The API needs a key (free registration) and allows at most one request per second. The site's Brawlhalla records ran through 2026-07-19 when the snapshot was taken (§6a). API access is blocked for now, and the snapshot only has career totals, so these rows are deferred. Until then, 2017–2018 events, league events and MAX MODE 2025 have no payout data, and answers say so.

**Payouts are never estimated from a total prize pool.** An event with only a total stays `pool_only`, and one with nothing stays `unavailable`. Either way, answers say that its payout data isn't available.

**Proposed design:**

```sql
CREATE TABLE event_prizes (        -- one row per official event checked for prize data
  event_id      TEXT PRIMARY KEY REFERENCES events (event_id),
  status        TEXT NOT NULL,     -- 'structured' | 'parsed_text' | 'curated'
                                   -- | 'pool_only' | 'disabled' | 'unavailable'
  review        TEXT NOT NULL,     -- 'not_needed' | 'auto_ok' (split = stated total) | 'pending'
                                   -- | 'accepted' | 'rejected' (from curation/prize_reviews.csv)
  currency      TEXT,
  stated_total  REAL,              -- start.gg payoutTotal, or the description's "Prizes:" amount
  split_total   REAL,              -- sum of this event's prize_payouts
  payout_type   TEXT,              -- start.gg payoutType
  raw_text      TEXT,              -- start.gg prizing markdown or the Challengermode description
  source        TEXT NOT NULL,     -- 'startgg' | 'challengermode' | 'curated'
  fetched_at    TEXT NOT NULL
);

CREATE TABLE prize_payouts (       -- per-placement amounts, never derived from a total
  event_id   TEXT NOT NULL REFERENCES events (event_id),
  slot       INTEGER NOT NULL,     -- start.gg prizing entry, or line number in the parsed split
  placement  INTEGER NOT NULL,
  amount     REAL NOT NULL,        -- per entrant: a team in 2v2, a crew in crew battles
  source     TEXT NOT NULL,        -- 'startgg' | 'parsed_text' | 'curated'
  PRIMARY KEY (event_id, slot)
);

CREATE TABLE player_prizes_external (   -- Esports Earnings per-tournament rows: deferred (§6a)
  player_id         INTEGER NOT NULL REFERENCES players (player_id),
  source            TEXT NOT NULL,      -- 'esports_earnings'
  tournament_name   TEXT NOT NULL,
  end_date          TEXT NOT NULL,
  rank_text         TEXT,
  prize_usd         REAL NOT NULL,
  matched_event_id  TEXT REFERENCES events (event_id),  -- NULL without a confident match
  fetched_at        TEXT NOT NULL
);

-- Events whose prize data needs a person: a split that doesn't add up, no split, or a total only.
CREATE VIEW v_prize_review AS
SELECT e.event_id, e.tournament_name, e.event_name, p.status,
       p.stated_total, p.split_total, p.raw_text
FROM event_prizes p
JOIN events e ON e.event_id = p.event_id
WHERE p.review = 'pending';

-- Payouts the views may use: start.gg's, and splits that passed the automatic check or a review.
CREATE VIEW v_event_payouts AS
SELECT pp.event_id, pp.placement,
       MAX(pp.amount) AS amount,          -- shared places repeat the same amount
       ep.currency, ep.status
FROM prize_payouts pp
JOIN event_prizes ep ON ep.event_id = pp.event_id
WHERE ep.review IN ('not_needed', 'auto_ok', 'accepted')
GROUP BY pp.event_id, pp.placement;

-- Each official result with its prize money, or the reason there is none.
CREATE VIEW v_player_event_earnings AS
SELECT r.player_id, r.event_id, r.tournament_name, r.start_date, r.mode, r.placement,
       CASE WHEN p.amount IS NOT NULL
              THEN p.amount / CASE WHEN r.format = 'crew_battle' THEN 3   -- per crew: a third each (decided)
                                   WHEN r.mode = '2v2' THEN 2             -- per team: half each (decided)
                                   ELSE 1 END
            WHEN e.event_id IS NOT NULL THEN 0       -- the event's payouts are known; none for this place
       END AS prize,                                 -- NULL when the event has no payout data
       CASE WHEN p.amount IS NOT NULL   THEN 'paid'
            WHEN e.event_id IS NOT NULL THEN 'unpaid'
            ELSE 'not_available' END AS prize_status,
       e.currency,
       CASE e.status WHEN 'structured'  THEN 'start.gg'
                     WHEN 'parsed_text' THEN 'Challengermode prize split'
                     WHEN 'curated'     THEN 'curated' END AS source
FROM v_results r
LEFT JOIN (SELECT DISTINCT event_id, currency, status FROM v_event_payouts) e
       ON e.event_id = r.event_id
LEFT JOIN v_event_payouts p ON p.event_id = r.event_id AND p.placement = r.placement
WHERE r.is_official = 1;
-- Esports Earnings' per-tournament rows (deferred, §6a) would later fill 'not_available' results.
```

- **Review states:**
  - start.gg's structured payouts need no review, and neither do start.gg events with prizing disabled or absent.
  - A parsed split is `auto_ok` when it adds up, and `pending` otherwise. A Challengermode event with no split is `pending` too, since a person may find one.
  - A split copied by hand counts as `accepted`.
- **Team splits (decided).** 2v2 amounts are per team, so each player gets half: start.gg's $60,000 for 1st at BCX 2022 2v2 is $30,000 each. Crew battle amounts are per crew and split three ways, which fits the `.33`/`.67` fractions in the Stats API's earnings. No Challengermode description says either way, so the same rules apply there.
- **Prize status:**
  - `paid`: the placement has a payout;
  - `unpaid`: the event's payouts are known, but this placement got none, so $0;
  - `not_available`: the event has no usable payout data, so the answer says so, and never counts it as $0 (§8, answer rule 3).
- **Check:** sum `v_player_event_earnings` for ranked players and compare the totals with their Stats API career figure (check 7 in §4).
- **The Sandstorm question** takes the top `paid` row for player 74433 and names the results whose payout data isn't available (§8, question 9).

## 7. start.gg and Challengermode tables

The core tables already carry what's needed to join platform data, and the platform survey confirmed each link:
- `events.event_id` is the start.gg event slug or the Challengermode tournament UUID;
- `matches.match_id` is the start.gg set ID or the Challengermode match ID, and the scores agree (§1);
- start.gg participant player IDs equal `players.sgg_player_id`, and Challengermode lineup member IDs equal `cm_player_id`;
- every data row has a `source`. Derived tables (`teams`, `match_players`) take the source of the rows they're built from, and curated tables are curated by definition.

Platform data goes into separate tables. The core views never reference them, so everything in §2 works with them empty.
- `standings` is built in Phase 1 for both platforms. It's the source of `placements` (decided 2026-10-04) and of former names.
- The bracket tables and `match_games` come in Phase 3 (§9). Their data is already fetched in Phase 1, by P4 and P5, because `matches` comes from the same responses.

```sql
CREATE TABLE standings (           -- every placed entrant, one row per participant
  event_id         TEXT NOT NULL REFERENCES events (event_id),
  entrant_key      TEXT NOT NULL,  -- start.gg entrant ID / Challengermode lineup ID
  platform_player  TEXT NOT NULL,  -- start.gg player ID / Challengermode user ID
  player_id        INTEGER REFERENCES players (player_id),  -- through sgg_player_id / cm_player_id; NULL if unknown
  entrant_name     TEXT,           -- as shown at the event, e.g. 'Kingdom | Godly'; a party name on Challengermode
  gamer_tag        TEXT,           -- start.gg gamerTag at the event / Challengermode username
  prefix           TEXT,           -- start.gg team tag at the event
  placement        INTEGER NOT NULL,  -- start.gg placement / Challengermode bestPlacement
  worst_placement  INTEGER,        -- Challengermode worstPlacement ('5 - 6' → 6)
  initial_seed     INTEGER,        -- start.gg initialSeedNum / Challengermode seed
  is_disqualified  INTEGER,        -- start.gg isDisqualified / Challengermode disqualified
  source           TEXT NOT NULL,  -- 'startgg' | 'challengermode'
  fetched_at       TEXT NOT NULL,
  PRIMARY KEY (event_id, entrant_key, platform_player)
);

-- Entrant counts come from standings, not start.gg's numEntrants (registrations).
CREATE VIEW v_event_entrants AS
SELECT event_id, COUNT(DISTINCT entrant_key) AS entrants
FROM standings
GROUP BY event_id;

CREATE TABLE phases (              -- start.gg Phase / Challengermode stage
  phase_key     TEXT PRIMARY KEY,  -- 'sgg:<phase ID>' or 'cm:<tournament UUID>:<stage index>'
  event_id      TEXT NOT NULL REFERENCES events (event_id),
  name          TEXT,              -- e.g. 'Phase 1 Pools', 'Top 8'
  phase_order   INTEGER NOT NULL,  -- bracket order, by seeds (largest first): start.gg's phaseOrder isn't
                                   -- always it (EU SteelSeries 2020: Top 256 is 4th) / Challengermode stage index
  bracket_type  TEXT,              -- DOUBLE_ELIMINATION, SINGLE_ELIMINATION, SWISS, ROUND_ROBIN
  seeds         INTEGER,           -- start.gg numSeeds / Challengermode lineupCount
  source        TEXT NOT NULL,
  fetched_at    TEXT NOT NULL
);

CREATE TABLE phase_groups (        -- start.gg pool (PhaseGroup) / Challengermode bracket
  group_key     TEXT PRIMARY KEY,
  phase_key     TEXT NOT NULL REFERENCES phases (phase_key),
  label         TEXT,              -- start.gg displayIdentifier ('A8') / Challengermode bracket title
  side          TEXT,              -- Challengermode bracket labels: 'winners' | 'losers' | 'grand_final';
                                   -- NULL for start.gg pools, which hold both sides
  bracket_url   TEXT,              -- start.gg PhaseGroup.bracketUrl; Challengermode has no bracket page
  source        TEXT NOT NULL
);

CREATE TABLE seeds (               -- seeding per phase
  phase_key    TEXT NOT NULL REFERENCES phases (phase_key),
  entrant_key  TEXT NOT NULL,      -- start.gg entrant ID / Challengermode lineup ID
  seed         INTEGER NOT NULL,   -- start.gg seedNum / Challengermode seed
  group_key    TEXT REFERENCES phase_groups (group_key),
  is_bye       INTEGER,
  source       TEXT NOT NULL,
  PRIMARY KEY (phase_key, entrant_key)
);

CREATE TABLE match_bracket_info (  -- where each match sat in its bracket
  match_id          TEXT PRIMARY KEY REFERENCES matches (match_id),
  group_key         TEXT REFERENCES phase_groups (group_key),
  round             INTEGER,       -- start.gg signed round (negative = losers side) / Challengermode roundNumber
  round_label       TEXT,          -- start.gg fullRoundText ('Losers Quarter-Final') / Challengermode round title
  side              TEXT,          -- 'winners' | 'losers' | 'grand_final'
  set_order         TEXT,          -- start.gg identifier ('AF') / Challengermode ordinal
  best_of           INTEGER,       -- start.gg Round.bestOf; NULL for Challengermode
  side1_seed        INTEGER,
  side2_seed        INTEGER,
  winner_placement  INTEGER,       -- start.gg wPlacement
  loser_placement   INTEGER,       -- start.gg lPlacement
  cm_series_id      TEXT,          -- Challengermode match series UUID (matches.match_id is the match UUID)
  source            TEXT NOT NULL,
  fetched_at        TEXT NOT NULL
);

CREATE TABLE match_games (         -- per game, wherever a source reports games
  match_id      TEXT NOT NULL REFERENCES matches (match_id),
  game_no       INTEGER NOT NULL,  -- start.gg orderNum, or position in the Stats API lists
  source        TEXT NOT NULL,     -- 'startgg' | 'stats_api'
  winner_side   INTEGER,           -- start.gg winnerId mapped to a side; the Stats API doesn't say
  map           TEXT,              -- normalized map name
  side1_legend  TEXT,              -- 1v1 only; 2v2 legends stay in matches.legends_json
  side2_legend  TEXT,
  PRIMARY KEY (match_id, game_no, source)
);
```

- **Bracket side.** On start.gg it's the sign of `round` (positive = winners, negative = losers), with `fullRoundText` marking the grand final and any reset. On Challengermode it's the bracket's labels (`DOUBLE_ELIMINATION_UPPER_BRACKET`, `…_LOWER_BRACKET`, `…_FINALS_BRACKET`).
- **Set order.** start.gg's `identifier` orders sets within a pool, and `sets(sortType: ROUND)` returns them in bracket order. Challengermode's `ordinal` runs across the whole tournament (1–1023 in Autumn NA 2026).
- **Best-of** comes from start.gg's `Round.bestOf`, not `Set.totalGames`, which is 5 on every set. BCX 2022 has no best-ofs at all. Challengermode's `bestOf` is 1 on every series, because the series is just a wrapper whose single match carries the game score, so it's stored as NULL.
- **Entrant counts** come from `standings`. start.gg's `numEntrants` counts registrations: 992 at the NA Winter Championship 2025, where 450 entrants were seeded and placed.
- **Byes,** a set or series with one entrant or none, have no match in `matches` and aren't stored. Autumn NA 2026 had 284 entrants in a 512-slot bracket, so 456 of its 1,023 series were byes.
- **Per-game data.** start.gg reports games only in late phases: BCX 2022's 1v1 Finals had 43 games, all with stage and characters, and its 2v2 Finals had stages but no characters. The Stats API's `legends` and `maps`, present on a minority of matches (more often Challengermode ones), are unpacked into the same table.
  - The two sources name things differently: start.gg uses display names ("Caspian", "Small Fortress of Lions"), and the Stats API uses identifiers (`RED_RAPTOR`, `FortressoftheLions`). So Phase 3 adds a small mapping.
  - A view, `v_match_games`, prefers start.gg's row when both sources report a game.
- **The bottom of brackets.** `standings` lists every placed entrant, which the Stats API only reaches through players we've discovered.

## 8. Target questions

The agent should be able to answer these. The first ten come from [`api-survey.md`](api-survey.md) §9, where each was checked against the API. Questions 11 and 12 were added on 2026-10-04. "Phase" is the first phase that makes a question answerable (§9).

**Answer rules (decided).** Every answer follows the rules in §2, plus these:
1. **Say what was counted.** The scope is official events only, so answers say "official events", even when the question says "majors" or doesn't say. A crew battle result counted as 1v1 is labeled as one.
2. **The last event entered** counts every official event, side formats included. When the newest is a side format (Kung Foot, Triples, Brawlball, …), the answer also gives the newest 1v1 or 2v2 event.
3. **Missing isn't zero.** When an event has no payout data, or a player has no career earnings figure, the answer says so rather than counting $0.
4. **Name the metric** when a question needs one ("best record", "most dominant"), along with any minimum.
5. **Name the player.** When a name could mean more than one player, the answer says which one it used and mentions the others in one line (§1).

| # | Question | How it's answered | Phase |
|---|---|---|---|
| 1 | What was the last tournament Boomie entered? | Resolve "Boomie" through `player_aliases`, because search can't find this player (146606). Take Boomie's newest row in `v_entries`, which keeps the side formats that `v_results` drops. If it's a side format, also give the newest row with a `mode` (answer rule 2). | 1 |
| 2 | How many majors has Raydish won? | Count Raydish's rows in `v_official_wins`, by mode. The answer says "official events": 6, all 1v1, including the 2026 NA Crew Battle Championship (crew battles count as 1v1). | 1 |
| 3 | Has Hexo ever placed top 8 in 1v1? | "hexo" → Hexoo (nickname). Check `v_results` for 1v1 placements ≤ 8. At official events that's once, 5th at Brawlhalla Community Tournament #2. The survey's 8 top 8s included community events, which aren't in the database. | 1 |
| 4 | What does Impala vs Balloonboy's history look like? | `v_head_to_head_1v1` gives the record without DQs and forfeits, and `v_match_results` lists the sets event by event. They never met in 2v2. | 1; Phase 3 adds rounds, bracket side and seeds |
| 5 | List the top 10 highest-earning players in Brawlhalla history. | `v_career_earnings`, naming each figure's source and date. That's the Stats API's figure, or for players without one, such as Boomie, the Esports Earnings snapshot's (2026-10-04, §6a). The answer notes that the two sources count differently: gdsandstorm is $258,984 in the Stats API and $239,831 on Esports Earnings. Players outside the snapshot's top 500 with no Stats API figure have no figure, and the answer says so (answer rule 3). | 2 (Phase 1: Stats API figures only) |
| 6 | Who has megd played with in 2v2 tournaments, and how did they place? | `v_team_results` with `teams`, for megD's teams: partners, events together and best placement. The two "hardymj" records merge through `player_merges`. | 1 |
| 7 | How many medals does Balloonboy have? | `v_player_medals`: 27 by the survey (1v1 2/8/5, 2v2 5/3/4). "Balloonboy" also matches BBBalloonBoy's start.gg name, "M30W \| BalloonBoy". | 1 |
| 8 | Who has the best record against marckiemoo? | "marckiemoo" → Marckiem00 (nickname). `v_head_to_head_1v1` with Marckiem00 as the opponent, ranked by win rate with a minimum number of matches, which the answer states. | 1 |
| 9 | What tournament did sandstorm make the most money from? | "sandstorm" → gdsandstorm (nickname). The top `paid` row of `v_player_event_earnings`, plus the results whose payout data isn't available (`not_available`), so a big early result without payouts isn't silently missed (answer rule 3). | 2 |
| 10 | Give me the bracket link of BCX 2022. | The event alias "bcx 2022" finds both events, and `v_events.bracket_url` gives the links. | 1; Phase 3 adds per-pool links |
| 11 | What is Raydish's most dominant tournament win? | See below. | 1; Phase 3 adds seeds and the path |
| 12 | What was flowers' first top 8? | See below. | 1 |

### Question 11: Raydish's most dominant tournament win

**Dominance is measured by games lost (decided 2026-10-04).** The fewer games the winner lost across the run, the more dominant the win. 3-0 in every set is the most dominant, then a run that dropped one game in one set (one 3-1, 3-0 in the rest), and so on.

- **Candidates:** Raydish's rows in `v_official_wins`. There are six, all 1v1:
  - the NA Summer Championship 2022;
  - the NA Winter Championship 2023;
  - the Trials of Ymir, Heimdall and Laufey (all NA, 2024);
  - the 2026 NA Crew Battle Championship.
- **Per win,** from Raydish's `v_match_results` rows for that competition: games lost, sets dropped, games won and sets played.
  - DQ and forfeit wins contribute no games and don't count as sets played. The answer still mentions them ("plus one opponent DQ'd").
  - In a phased competition, matches from every phase count.
  - A 2-0 in a best-of-3 set loses no games either.
- **Ranking:** fewest games lost. Ties go to fewer sets dropped, then to more games won, so a longer perfect run beats a shorter one.
- **The answer** names the metric and shows the top run's set scores, so a short run, or one with DQ wins, is visible as such.
- **The crew battle win** is only comparable if its matches are stored as one-on-one games (§2). If they're stored crew against crew, it's left out of the ranking, and the answer says why.
- **Wins without match data** sort last, as not comparable.
- **Phase 3** adds context, not a different metric: each set's best-of, opponents' seeds, and the path through the bracket.

```sql
SELECT w.event_id, w.tournament_name, w.start_date,
       SUM(m.games_lost) AS games_lost,
       SUM(1 - m.won)    AS sets_dropped,
       SUM(m.games_won)  AS games_won,
       COUNT(m.match_id) AS sets_played             -- no-contests are already excluded
FROM v_official_wins w
LEFT JOIN v_match_results m ON m.player_id = w.player_id
                           AND m.competition_key = w.competition_key   -- every phase counts
WHERE w.player_id = 160000
GROUP BY w.event_id
ORDER BY games_lost NULLS LAST, sets_dropped, games_won DESC;
```

### Question 12: flowers' first top 8

- **The player is flowerVS (169119, NA 1v1 PR #5).** "flowers'" here means "flower's" (decided 2026-10-04), and "flower" and "flowers" are both curated nicknames for flowerVS (§1).
  - "flowers" is also the display name of Flowers (156897, EU, ranked only in 2v2), so the answer mentions that player in one line (answer rule 5).
  - flowerVS's start.gg names, "little flower" (BCX 2022) and "flower" (NA Winter Championship 2025), also become `former_name` aliases in Phase 1.
- **Query:** the earliest 1v1 row in `v_results` for flowerVS with `placement <= 8`. Then the same for 2v2: if that one is earlier, the answer mentions it too.
- **Wording:** "first top 8 at an official event". The data starts in February 2017 and leaves out community events, so an earlier community top 8 wouldn't show.
- **Rules that apply:**
  - A phased competition counts once, at the last phase reached.
  - Excluded formats don't count.
  - A crew battle counts as 1v1, and if the first top 8 was a crew's placement, the answer says so.

```sql
SELECT mode, tournament_name, event_name, start_date, placement
FROM (SELECT r.*, ROW_NUMBER() OVER (PARTITION BY r.mode ORDER BY r.start_date) AS nth
      FROM v_results r
      WHERE r.player_id = 169119 AND r.is_official = 1 AND r.placement <= 8)
WHERE nth = 1;
```

## 9. Implementation plan

There are three phases, and each ends with a database the agent can use. A phase only adds fetch stages, tables, views and curation files. The database is rebuilt from the cache, so nothing needs migrating.

### Phase 1: core tables, aliases and rule views

- **Fetch** (§3), all done by 2026-10-05:
  - Stats API: events, PR lists and profiles (stages 0–2), with a 200-player pilot of stages 3–4 (full runs held);
  - start.gg standings (P1);
  - Challengermode entrant lists and brackets (P5);
  - Stats API records for every platform player (2b);
  - the Pro Series finals' placements (3b);
  - start.gg brackets (P4).

  Also done: the entrant lists of the three start.gg events whose standings miss entrants (P1b), and the Stats API check for their placements (3c, none found).
- **Build:**
  - players: `players`, including platform-only players (§1); `player_aliases`, with display names, names without tags, former names from the Stats API and both platforms, and curated nicknames; `player_merges`;
  - events and results: `events`, `event_aliases`, `format_rules`, and `standings` for both platforms, with `placements` and `teams` built from it;
  - matches: `matches` (with `is_no_contest`) and `match_players`, from start.gg sets and Challengermode matches;
  - rankings and earnings: `pr_snapshots`, and `player_earnings` with the Stats API figures.
- **Views:** everything in §2 except the deferred `v_tier_results`, plus `v_career_earnings` (Stats API figures only) and `v_event_coverage`.
- **Curation:**
  - `player_aliases.csv` and `player_merges.csv` (seeded, with 670 merges accepted automatically, §1), and `merge_rejections.csv`. The review list's tiers 2 and 3 can be worked through while the builder is built, since a merge only changes `v_player_ids`;
  - `events.csv` (mode and format overrides and the two phase splits, but no tiers), `event_aliases.csv`, `format_rules.csv` and `known_events.csv`;
  - `tiers.csv` exists but isn't read.
- **Why the platforms are in Phase 1 (decided 2026-10-04):** their standings, entrant lists and brackets cover every entrant and every match of every official event. Per-player Stats API calls reach only the players already found. They're also the source of the former names.
- **Done when:**
  - the automatic checks (§4) pass or have explained exceptions, with check 8 covering both platforms;
  - the known-events report is clean;
  - the shape of crew battle matches is known.
- **Answerable:** questions 1–4, 6–8 and 10–12. Question 5 works only for players with a Stats API figure.

### Phase 2: per-tournament earnings and the career fallback

- **No API key needed.** The Esports Earnings API is blocked (2026-10-04), because the account login isn't working. Payouts come from start.gg and Challengermode, and the career fallback comes from the one-time website snapshot (§6a). When an event has no payout data, the agent says so (`prize_status = 'not_available'`, answer rule 3).
- **Fetch:** start.gg `prizingInfo` (P2) and Challengermode descriptions (P3). The snapshot is already in `curation/`.
- **Build:**
  - `event_prizes` and `prize_payouts`, from start.gg and from parsed prize splits;
  - from the snapshot, `player_external_ids` links and `player_earnings` rows with source `esportsearnings_manual`.
- **Views:** `v_prize_review`, `v_event_payouts` and `v_player_event_earnings`. `v_career_earnings` gains the snapshot fallback.
- **Curation:** `prize_reviews.csv`, `prize_payouts.csv` (splits copied by hand, such as BCX 2025's) and `external_ids.csv` (snapshot links that need a person; seeded, §6a).
- **Done when:** every official event has an `event_prizes` row, both review lists are worked through, and checks 7 and 10 pass.
- **Answerable:** questions 5 and 9. Question 9 names the results whose payout data isn't available.
- **Later, if Esports Earnings API access is resolved:** `player_prizes_external`, per-tournament rows that fill in 2017–2018 payouts for question 9. Adding it changes no Phase 2 table; only `v_player_event_earnings` gains a source.

### Phase 3: bracket structure and per-game data

- **Fetch:** nothing new. P4 and P5 moved to Phase 1 (decided 2026-10-04), so Phase 3 builds from their cached responses.
- **Build:** `phases`, `phase_groups`, `seeds`, `match_bracket_info`, and `match_games` (start.gg games plus the Stats API's legends and maps), with the legend and map name mapping.
- **Views:** `v_event_entrants` and `v_match_games`.
- **Done when:**
  - every match at a bracketed event has a `match_bracket_info` row;
  - start.gg's DQs (`displayScore: "DQ"`) and Challengermode's no-shows line up with `is_no_contest`.
- **Answerable:** no target question needs Phase 3. It adds rounds, bracket side and seeds to questions 4 and 11, and pool links to question 10. It also opens new kinds of question: entrant counts, upsets by seed, paths through a bracket, and legends and stages per game.

## Open questions

None block the builder.

**For you, at your own pace:** the merge review list, `data/review/merge_candidates.csv` (§1, players). It has 434 tier-2 and 1,753 tier-3 pairs, strongest first.

**Waiting on others:** whether the esports team can share their account-link data (asked 2026-10-04). It would settle most merge candidates (§1).

**Settled:**
- All three Pro Series finals count like crew battles (2026-10-05): `format_override = 'crew_battle'` in `curation/events.csv` (§1).
- The three start.gg events whose standings miss entrants (2026-10-05):
  - their entrant lists were fetched, so all their sets can be attributed;
  - placements come from the Stats API where it has them (it had none);
  - the rest stay unplaced, and placements are never derived from brackets (§1).
- The merge-candidate review list (2026-10-05): tier 1 accepted automatically, tiers 2 and 3 for review (§1).
- Stage 6 and placements (2026-10-04): matches come from event-level platform brackets, placements from platform standings and entrant lists, and platform-only players get stable negative IDs; stages 3–4 are held after their pilot; the Pro Series finals get a targeted fetch; merge candidates are tiered, with only tier 1 accepted automatically (§1, §3).
- Scope: official events only (2026-10-03).
- Majors are official events, and answers say "official events". Tiers are deferred (§5).
- Crew battle matches count in 1v1 head-to-heads only when stored as one-on-one games (§2).
- DQs and forfeits are no-contests (`is_no_contest`, §1).
- Data terms: the repo stays private, so `curation/` and the appendix are committed.
- Prize money: 2v2 amounts are per team and crew battle amounts per crew; payouts come from start.gg and from parsed Challengermode splits (§6b); career earnings come from the Stats API, with a one-time Esports Earnings snapshot (2026-10-04) as the fallback for players without a Stats API figure (§6a).
- Credentials: the start.gg token and Challengermode access are in hand.
- The answer rules in §8, including the one for "last event entered".
- "flower" and "flowers" mean flowerVS (§1).
- Dominance is measured by games lost (§8, question 11).

**Blocked:** the Esports Earnings API, because the account login isn't working (2026-10-04). The snapshot covers career figures; the API would add per-tournament rows for 2017–2018 payouts (§9).

**Deferred:** the tier scale (§5).

## Appendix: official events

All 622 events with `isOfficial: true` in the 2026-10-03 survey crawl, one row per tournament.
- **Events** lists the modes, the format notes from the decided rules, and the two phase-split tournaments.
- **Family** is the auto-detected guess from §5.
- **Data terms:** this list was extracted from the Stats API. It's committed because the repo stays private (decided 2026-10-04).
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

