# Database build plan

**Status: approved 2026-10-05.** This is the plan for Phase 1's builder (schema proposal §9): the database built from the cache and `curation/` alone. The decisions below settled its open questions. Work goes in the order at the end, one step per commit, pushed after each, with a report after each step for review.

The plan builds on [`schema-proposal.md`](schema-proposal.md) (the schema, rules and checks it implements) and the rules in [`CLAUDE.md`](../CLAUDE.md). Where they differ, the decisions here are newer.

## Decisions of 2026-10-05

1. **Sets with a winner but no score count as a win and a loss with no games.** start.gg has 259 completed sets where the organizer reported only the winner (see "What the cache showed").
   - **Storage:** `matches.side1_score` and `side2_score` may be NULL, and a new `reported_winner_side` holds the platform's own winner. `winner_side` falls back on it when a score is missing.
   - **Games are unknown, not zero.** In any game-based stat (games won or lost, game win rates, question 11's dominance ranking), these sets are left out of the game counts, and the affected result is flagged: "includes sets with no recorded score".
   - **A win with unscored sets never looks like a perfect run.** The views expose how many unscored sets a result includes. Question 11's ranking puts a run with any unscored set after every fully scored run. If such a run would have ranked near the top on its scored games alone, the answer mentions it in one line, so it isn't silently buried.
   - **Challengermode forfeits stay no-contests.** A Challengermode match with no scores is a no-show (decided 2026-10-04), so it's still stored as 0–0. A start.gg set with only a winner was played.
2. **Merges found by an unattended run go to `data/review/auto_merges.csv`,** a machine-owned file the builder applies and the review list shows. Only the strongest tier (tier 1) is accepted automatically. The updater never edits committed files.
   - Running `merge_candidates.py` by hand still appends tier 1 to `curation/player_merges.csv`.
   - A pair in `curation/merge_rejections.csv` overrides an automatic merge.
3. **New events whose team sizes don't fit their mode stay out of the counts until reviewed.** An example is a "1v1" event whose entrants have three players.
4. **Builds are versioned files with a pointer file.** They replace one fixed `data/db/brawlhalla.sqlite` (§5).
5. **Three fixes to the schema proposal's §2 views are approved:**
   - `v_team_results` and `v_head_to_head_2v2` use canonical player IDs, so a merged record doesn't split a team;
   - `v_match_results` gains each side's player count, so crew-against-crew sets can be filtered out (question 11);
   - when two merged records placed in one event, `v_results` keeps the better placement.
6. **The §8 survey answers are a regression check, not independent verification:** they came from the same Stats API. The user has confirmed Raydish's 6 official wins and will verify the other answers separately.
7. **CEO Dreamland 2020 wasn't held (decided after step 5):** it was cancelled due to COVID-19.
   - `events.csv` marks it `status = cancelled`, with the reason in its note. Both go into `events`.
   - A check exception (`winners`) explains why it has no winner.
   - Answers say it wasn't held, not that its results are missing.
8. **Player aliases keep their curated note (decided after step 5),** as event aliases do. For example, "flowers" is also the display name of a different player, and the answer can mention them.

## What the cache showed

Measured on 2026-10-05, read-only, before planning.

- **Size and speed:** about 21,000 cached responses (20,933 with status 200), 96 MB compressed, indexed by the request log in `data/db/crawl.sqlite`.
  - Parsing all 4,455 standings pages took 3.7 s.
  - The 11,157 set pages (9,965 event pages and 1,192 pool pages, 536,633 distinct sets) took 16.7 s.
- **Crew battles are crew against crew on both platforms.** This settles the "shape of crew battle matches" item in Phase 1's done list.
  - start.gg's 2022 Crew Battle Invitationals have entrants of three participants, and their sets are scored crew against crew ("Team Red 0 - Team Pink 2").
  - Challengermode's 2026 Crew Battle Championships have lineups of three, and match sides of three.
  - So crew battle sets never count in 1v1 head-to-heads (one player per side), and question 11 can't rank Raydish's crew battle win; the answer says why.
- **259 start.gg sets have a winner but no game score.**
  - They're completed sets, not DQs: `displayScore` reads like "Boomie W - Fable | Mother Russia L".
  - By year: 2017 135, 2018 13, 2019 79, 2020 18, 2021 7, 2022 1, 2023 3, 2024 3.
  - One more set has one score and a winner ("2" against none). Decision 1 covers it too.
- **Other unscored sets:**
  - 981 have a −1 against no score (DQs, no-contests);
  - 44 were never played (no score, no winner; not stored);
  - 189 have fewer than two entrants (byes; not stored).
- **The recount differs from the schema proposal's §1 table** (278 with a winner but no score, 173 never played, 989 with one score missing). Check 9 recounts with the builder's exact rule, and the table gets corrected.
- **Pool-by-pool set pages don't name their event.** A `PoolSets` request names only the pool. The builder links pools to events through cached responses: an event's first `EventSets` page lists its phases, and `PhasePools` lists each phase's pools. All 1,192 pool pages are linked this way, so the builder never needs the crawl's planning tables.
- **Query versions:** each GraphQL endpoint the builder reads has one cached query version, except `PhasePools`. There, 7 pages exist only in the pilot's version (query hash `4adbea053cfe`) next to 290 in the current one (`27af850a353b`). So the builder accepts a short list of known query versions per endpoint.
- **ListPlayers never returns a country.** It returns `playerId`, `sggPlayerId`, `cmPlayerId`, `brawlhallaId`, `name`, and sometimes `twitter` and `twitch`. `players.country` stays NULL.
- **Entrant sizes always fit the mode or format,** so they can flag new side formats.
  - In start.gg standings, events filed as 1v1 have 206,241 entrants of one player, 200 of three (the 3v3 Championships and the Crew Battle Invitationals) and 17 of two (CEO Dreamland 2017's doubles, which is filed as 1v1).
  - 2v2 events have 61,239 entrants, all of two.
  - All 4,312 placed Challengermode 2v2 lineups have two players.
- **Check 8 can be ten times stronger than planned.** The cache holds 6,093 single-player Stats API placements at platform events: 5,562 at start.gg events and 531 at Challengermode ones. They're the stage 3 pilot plus the up-to-ten events on each stage 3b and 3c page. The pilot alone had 563. The 84 Pro Series placements are the placements themselves, not a check.
- **Platform state can't select old events.**
  - Challengermode reports all 90 events `COMPLETED`.
  - On start.gg, 513 events have every phase completed, 16 have a phase still `ACTIVE`, and 1 has only a `CREATED` phase.
- **Disk:** 244 GB free; a build should be roughly 300 MB.

## 1. Build order

The builder reads only the cache (the response files, plus the request log in `crawl.sqlite` that indexes them) and `curation/`. It never reads the crawl's planning tables (`crawl_*`) and never makes a request.

| Step | Reads | Produces |
|---|---|---|
| 0. Start | — | A new file in `data/db/builds/`, every table from `schema.sql`, and `build_info` (code commit, curation file hashes, cache cutoff) |
| 1. Curation | `curation/*.csv` | Every file validated; the build stops on a bad row before reading the cache |
| 2. Events | `/event` listings, `events.csv`, `format_rules.csv`, `event_aliases.csv` | `events` with the curated columns filled in, `format_rules`, `event_aliases`, `event_sources` |
| 3. Players | start.gg standings and P1b entrant lists, Challengermode rosters, `/players` lookups, PR rows, teammate records | `players`: Stats API records, plus negative IDs for the platform-only players who placed or played (43 today) |
| 4. Standings | the same | `standings`, one row per participant of each placed entrant, `player_id` resolved |
| 5. Placements | `standings`, `/player/placement` | `placements` and `teams` |
| 6. Matches | start.gg set pages, Challengermode brackets | `matches`, `match_players` |
| 7. Aliases | everything above, `player_aliases.csv` | `player_aliases` |
| 8. Merges | `player_merges.csv`, `merge_rejections.csv`, `data/review/auto_merges.csv` | `player_merges` |
| 9. PR | `/pr` | `pr_snapshots`, `player_earnings` (Stats API figures) |
| 10. Views | `views.sql` | Every §2 view except the deferred `v_tier_results`, plus `v_career_earnings` and `v_event_coverage`; then indexes |
| 11. Checks | the new build and the live one | `build_checks`, a report in `data/reports/<build>/`, and a verdict |
| 12. Publish | the verdict | On pass, the build goes live (§5); on fail, it's kept and marked failed, and the live build stays |

**What each step does:**
- **Responses:** the newest successful response to each request, at or before the cutoff when `--as-of` is given. Only known query versions are read (above).
- **Events:** from the full ListEvents listings, one row per Stats API event. The per-year listings are check 1's cross-check.
  - `events.csv` fills `format_override`, `mode_override`, `competition_id` and `phase_order`.
  - New table `event_sources` records each event's platform, platform ID and state, and the platform's own totals: entrants and sets reported. Completeness checks and `v_event_coverage` compare against those totals.
- **Players:**
  - **Stats API records** come from every cached record: ListPlayers (profiles, lookups and Pro Series candidates), teammate records and PR rows. The newest name wins, and a known platform ID is never overwritten with null.
  - **Lookup results:** a platform ID named in a cached lookup request but missing from its response isn't in the Stats API.
  - **Platform-only players** get a stable negative ID: start.gg `-sgg_player_id`; Challengermode `-(2^40 + the first 40 bits of the user UUID)`. Two players with the same ID stop the build.
  - Only platform players who placed or played get a row.
- **Placements:**
  - Each player gets one row per event: from the entrant that wasn't DQ'd first, then the better placement.
  - The Pro Series finals' placements, and any for the three events missing standings (stage 3c; none today), come from the Stats API.
  - A team is made from each entrant with exactly two players in an event whose effective mode is 2v2. The mode override counts, so CEO Dreamland 2017's doubles get teams.
- **Matches:**
  - **start.gg sets:**
    - A set with fewer than two entrants (a bye) or with no score and no winner (never played) isn't stored.
    - A −1 is a DQ, a no-contest; the other side's missing score stays NULL.
    - A set with a winner but no score is stored with NULL scores and its reported winner (decision 1).
    - Every set also stores start.gg's winner as `reported_winner_side`, so check 9 can confirm it matches the scores.
  - **Challengermode matches:** only completed matches in series between two lineups. A match with no scores is a forfeit, stored 0–0 (decision 1).
  - **Sides:** start.gg's slot order; Challengermode's lineup `number` (0 is side 1).
  - **An entrant's players** come from the standings, otherwise from the P1b entrant lists.
- **Aliases:**
  - Generated: display names, names without the team tag, and former names. Former names come from older Stats API names, the start.gg tag and name at each event, and Challengermode usernames.
  - Curated nicknames win when they coincide with a generated alias.
  - Name normalization is shared with `merge_candidates.py` through `names.py`.
- **Merges:**
  - Sources: `player_merges.csv`, plus the automatic merges in `data/review/auto_merges.csv` that no curated row contradicts.
  - Chains (A→B→C) are collapsed, and a cycle stops the build.
- **New tables beyond the schema proposal:** `event_terms` (step 2), `event_sources`, `build_info` and `build_checks`.
- **Schema changes:**
  - nullable scores and `reported_winner_side` on `matches` (decision 1);
  - a `note` on `event_aliases` (step 2, for defaults such as MSI), `events` and `player_aliases` (decisions 7 and 8);
  - a curated `status` on `events` (decision 7).

**Code** (all in `ingest/`):
- `build.py`: the steps and the command line;
- `cache_reader.py`: read-only access to the cache, as above;
- `builds.py`: build files, the pointer, rollback and pruning;
- `names.py`: name normalization, moved out of `merge_candidates.py`;
- `checks.py`;
- `schema.sql` and `views.sql`.

Tests use small JSON fixtures, like `test_crawl.py`.

**Commands:**
- `python ingest/build.py`: build, run the checks, and publish if they pass. Without `--as-of`, the cutoff is the build's start, so a response fetched during the build isn't used;
- `--no-publish`: build and check, leaving the live build as it is;
- `--as-of TIME`: build from the responses fetched up to TIME (UTC unless it gives a zone). Such a build of the past never goes live;
- `--event ID`: a dev build of the named events, never published (from step 2);
- `status`: the live build and the builds kept;
- `rollback`: make the build that was live before live again;
- `freeze NAME`: copy the live build to `data/db/eval/` as a frozen snapshot (step 9).

## 2. Curation files

Tables keep what the platforms reported. Curated values live in their own columns and tables, and the views apply them, so a curation edit only needs a rebuild. A curated row naming an event that doesn't exist stops the build: it's a typo to fix, and the live build stays in place. A row naming a player the cache has no record of is skipped and listed instead (step 6, for review), since it may name a real record with no official results.

| File | Applied as | Validated for |
|---|---|---|
| `events.csv` | `format_override`, `mode_override`, `competition_id`, `phase_order`, `status` and `note` on `events`; `v_events` applies them | Event exists; known format; mode 1v1 or 2v2; status empty or `cancelled`; each competition has at least two phases with distinct orders |
| `format_rules.csv` (new, seeded from §2's starting rules) | `format_rules` → `v_events.format` | Valid pattern and priority |
| `event_aliases.csv` (new, seeded with "bcx 2017" to "bcx 2025", "worlds 2019" and similar) | `event_aliases` | Event exists |
| `event_terms.csv` (new: words people use for words in event names, such as "ltc" and "winters") | `event_terms` | A term doesn't mean itself; a phrase no event has yet is logged |
| `player_aliases.csv` | Rows of kind `nickname`, source `curated`, winning over generated aliases | Player exists |
| `player_merges.csv` | `player_merges` → `v_player_ids` | Both records exist; no cycles; the pair isn't also rejected |
| `merge_rejections.csv` | Read by `merge_candidates.py`; the builder checks it against the merges, manual and automatic | Both records exist |
| `data/review/auto_merges.csv` (machine-owned, decision 2) | Applied like `player_merges.csv` unless a curated row contradicts it | As for merges |
| `known_events.csv` (new; the user fills in about 20 rows, §4 of the schema proposal) | The known-events report | Each row finds its event |
| `check_exceptions.csv` (new; so far the cancelled CEO Dreamland 2020's `winners` row) | Turns a known check failure into an explained one: check ID, subject, note | Known check ID (below); the checks confirm the subject exists |
| `external_ids.csv`, `esports_earnings_snapshot.csv` | Phase 2; not read yet | |
| `tiers.csv` | Not read (tiers are deferred) | |

**Negative IDs in curated rows** resolve through the platform ID they encode. So a row naming a platform-only player keeps working after a later lookup finds that player a Stats API record.

## 3. Checks, gates and when Phase 1 is done

Each check has a gate, which lets a script decide whether to publish without a person:
- **Blocking:** any failure not listed in `check_exceptions.csv` stops the publish.
- **No worse:** stops the publish only if the count is worse than the live build's.
- **Review:** never stops it; the item goes to the review list (§5).

| Check (numbers from the schema proposal's §4) | Gate |
|---|---|
| 1. `event_totals`: the full ListEvents listing equals the per-year listings | Blocking |
| 2. `winners`: one 1st place per counted event (a pair in 2v2, a crew in crew battles, a team at the Pro Series finals) | Blocking |
| 3. `pr_cross_check`: per Stats API record and mode, using PR's own rule (official events; crew battles and Community Tournament #2 left out) | No worse |
| 4. `teams`: every 2v2 placement has a team | No worse |
| 5. `completeness`, from the cache: each event's sets and standings match the platform's totals; every set entrant maps to players; every lineup in a Challengermode bracket is in its entrant list | Blocking |
| 6. `match_presence`: placed entrants with no match, other than byes and DQs | No worse |
| 8. `stats_api_placements`: Stats API placements against the standings, exact: all 6,093 in the cache, on both platforms | Blocking |
| 9. `no_contests`: no-contests and odd scores counted and listed. Every scored set's winner must match the platform's reported winner | No worse |
| 11. `pro_series`: the Pro Series finals form complete teams | Blocking |
| New, `integrity`: unique IDs, valid foreign keys, every platform player looked up, valid curation | Blocking |
| New, `entrant_sizes`: entrant sizes fit each event's mode and format | Blocking for reviewed events; review for new ones (decision 3) |
| New, `regression`: compared with the live build, no event is lost and no event's placements or matches decreased | Blocking |
| `known_events`: the known-events report (`known_events.csv`) | Blocking once filled in |

Checks 7 (`earnings`) and 10 (`snapshot_fallbacks`) wait for Phase 2's prize data and snapshot links. The IDs are what `check_exceptions.csv` names (`curation.CHECK_IDS`).

**`v_event_coverage`** shows per event:
- mode, format and platform state;
- entrants reported and placed, placements held and the worst placement;
- matches reported and held, and players with match data;
- 2v2 placements without a team;
- players who played but have no placement (the 151 entrants of the three events missing standings);
- a short flag the agent can quote, such as "placements incomplete" or "no match data".

**Phase 1 is done when:**
- a full build passes every blocking check, with each exception in `check_exceptions.csv` with a note. Two are expected: the three events missing standings, and the Pro Series finals, which have no match data;
- the known-events report is clean;
- the §8 queries for questions 1–4, 6–8 and 10–12 give the survey's answers, such as Raydish's 6 official wins, Balloonboy's 27 medals and Hexoo's one 1v1 top 8. This is a regression check, not independent verification (decision 6);
- two builds from the same cache and curation have identical table contents;
- the schema proposal, CLAUDE.md and the README are updated.

## 4. Time, and where it runs

- **About 2–4 minutes for a full build, checks included.** This is an estimate, to be replaced by the first full build's real figure.
  - Reading is about 30 s; the biggest parts were measured at 20 s.
  - Then roughly 3 million rows are inserted, followed by the indexes and checks.
- **It runs inside Claude Code:** no network, no credentials, and well within one tool call, so failures can be fixed on the spot. The same command works in PowerShell. Dev builds of a few events take seconds.

## 5. Support for the scheduled updater

The updater comes later (Windows Task Scheduler). It will:
- find new or recently ended official events and fetch only those;
- rebuild into a new database file and run the checks;
- swap the new file in only if they pass, keeping the previous version for rollback.

New curation needs never block an update, and the frozen evaluation snapshot is never updated automatically. The builder supports this as follows.

- **Fetch only new events, rebuild everything.** A full build takes minutes and gives the same result for the same inputs, so the updater never edits a live database.
- **Each build is a new file, and a pointer file names the live one.**
  - **Files** in `data/db/builds/`, named by the build's UTC start time, e.g. `20261005T190000Z`:
    - `<build-id>.partial.sqlite` while it's being made;
    - `<build-id>.sqlite` once its checks pass;
    - `<build-id>.failed.sqlite` if they fail.
  - **The pointer,** `data/db/current.json`, names the live build and lists the builds that were live before it. Publishing rewrites it atomically: Windows won't let a database file be replaced while the app has it open, so the pointer is what changes, not the database file.
  - **Rollback** returns to the build that was live before. So a build that passed but never went live (`--no-publish`, `--as-of`) is never a rollback target, and neither is a build already rolled back from.
  - **The agent** opens the live build read-only through the pointer.
  - **Kept:**
    - the live build and the three that were live before it;
    - the two newest builds that passed but never went live;
    - the two newest failed ones.

    A file still in use is skipped.
  - **One build at a time:** a lock file in `data/db/builds/` makes a second build wait, for up to 20 minutes.
- **The gates are the swap rule:** publish only if no blocking check fails and no "no worse" count got worse.
- **The review list,** `data/review/review.csv`, is rebuilt every time with stable keys. It holds:
  - **new events** with their detected format and mode. An event leaves the list once it has a row in `events.csv`; a row without overrides just records that the detection was checked;
  - **possible phase splits:** two events in one mode of one tournament, or with near-identical names and dates, where one's entrants are mostly the other's top finishers;
  - **merge candidates** from `merge_candidates.py`, and the automatic merges in `data/review/auto_merges.csv` (decision 2);
  - Phase 2's prize reviews, later.
- **New side formats** (decision 3):
  - A new event whose entrant sizes contradict its mode stays out of the counts until reviewed.
  - A new event that only has an unfamiliar name is counted as detected and listed for review.
- **`--as-of`** builds from the responses fetched up to a given time. It reproduces any past build. It also tests the updater by replaying the past: build as of 2026-09-01, then build now, and compare.
- **The frozen evaluation snapshot** is made only by `freeze`: a read-only copy of a published build in `data/db/eval/`, with its `build_info`. Neither pruning, rollback nor the updater touches that folder, and evaluation runs name the snapshot file directly.
- **Crawl changes the updater will need, not part of this plan:**
  - Stage 0 and the PR lists must re-fetch their first pages; today those requests would be answered from the cache.
  - Standings need `--event`.
  - Something must plan fetches for new or recently ended events. `event_sources` keeps each event's platform state for it. State alone can't select old events: 17 start.gg events still show a phase that never finished.

## 6. Order of work

One commit per step, pushed after each, with a report after each step for review. Every step has fixture tests and, from step 2 on, a dev build of a set of awkward events:
- BCX 2022 and Autumn NA 2026;
- a 2020 event fetched pool by pool;
- a crew battle and the Pro Series finals;
- CEO Dreamland 2017's doubles;
- the three events missing standings.

| Step | Work | Status |
|---|---|---|
| 1 | Cache reader, `names.py`, the tables (`schema.sql`), and the build skeleton with publish, pointer and rollback | Done 2026-10-05 |
| 2 | Curation loading and validation; events, format rules and event aliases | Done 2026-10-05 |
| 3 | Players, lookups and negative IDs; standings | Done 2026-10-05 |
| 4 | Placements, teams and the Pro Series placements | Done 2026-10-05 |
| 5 | Matches and match players | Done 2026-10-05 |
| 6 | Aliases, merges, PR and earnings | Done 2026-10-05 |
| 7 | Views, with the approved fixes | In progress (work in progress committed 2026-10-06) |
| 8 | Checks, the report, the review list and `v_event_coverage`, then the first full build, reviewed together | |
| 9 | `known_events.csv` with the user, the check exceptions, `freeze`, and the docs | |

**Step 1 (2026-10-05):**
- **Built:**
  - `cache_reader.py` reads the newest successful response to each request. It accepts only listed query versions and an optional cutoff, and its connection to the request log is read-only.
  - `cache.query_hash` is now the one definition of a query's version, used by both GraphQL clients and the reader.
  - `names.py` holds `normalize`, moved unchanged from `merge_candidates.py`. Its review list came out byte-identical afterwards.
  - `schema.sql` has every Phase 1 table. `player_merges` gains a `source` column ('curated' or 'auto', for decision 2).
  - `builds.py` handles the build files, the pointer, rollback, pruning and the lock.
  - `build.py` runs the build, with `status` and `rollback`. Steps and checks are empty lists that the next steps fill.
- **Tests:** 26 new; the whole suite (89) passes.
- **On the real cache:**
  - The reader indexes all 21,000 requests in 1.6 s.
  - Every Phase 1 endpoint reads in full, including all 297 `PhasePools` requests: 290 in the current version and the pilot's 7.
  - The first real build, with the empty schema, took about a second and is live.

**Step 2 (2026-10-05):**
- **Curation loading:** `curation.py` loads every curated file the builder reads and checks its structure before the cache is read. It reports every problem at once, by file and line.
  - **Columns:** a missing column, an unknown one (a typo), or a row with more fields than columns (an unquoted comma).
  - **Values:** unknown formats or modes, a competition with one phase or a repeated phase order, duplicate rows, IDs that aren't numbers.
  - **Merges:** self-merges, a record merged twice, loops, and merges that make two rejected records one person.
  - **Automatic merges** in `data/review/auto_merges.csv` lose to a curated merge of the same record, a rejection or a loop. They're dropped and logged rather than stopping the build (decision 2).
  - **Whether named events and players exist** is checked by the step that applies each file: events here, players from step 3.
- **Events step:** `build_events.py` fills `events`, `format_rules` and `event_aliases` from the full ListEvents listings and `curation/`.
  - A curated row naming an unknown event, or a competition whose phases are in different modes, stops the build.
  - `event_sources` gets each event's platform here; the steps reading the platforms fill in the rest.
- **New curation files:**
  - `format_rules.csv`: the schema proposal's ten starting rules. On the cache, they classify the 622 events as 601 standard, 9 crew battles (6 by rule, plus the three Pro Series finals by override), and 3 each of 3v3, Brawlball, Triples and Kung Foot, as the appendix lists them. Five rules match nothing yet; they wait for future side formats. The 2022 Crew Battle Invitationals ("Crew Battle 3v3") match two rules, and priority makes them crew battles.
  - `event_aliases.csv`: 54 rows.
    - "bcx 2017" and "bcx 2022" to "bcx 2025" name both modes of each BCX.
    - "worlds 2017" to "worlds 2025" name each year's World Championship. For 2020 and 2021, that's the five regional championships, without the Last Chance Qualifiers (decided).
    - "world championship 2018" names DreamHack Atlanta 2018, whose events are named just "Brawlhalla 1v1" and "Brawlhalla 2v2". It was the 2018 World Championship (confirmed by the user).
  - `event_terms.csv` (community names, added at the user's request): words people use for words in event names, so they keep working for future events.
    - "ltc" means "low tier city": Low Tier City 7 (2019) and Low Tier City Midseason Online (2020).
    - "winters", "springs", "summers" and "autumns" mean "<season> championship" and "<season> doubles championship" (the 2024 seasonals were 2v2 only). They don't mean the bare season word, which also appears in the Royales, DreamHack Winter and the Summer Slam.
    - Region abbreviations for every region in the data, each with the phrases names use:
      - "na" → "north america", plus "us" for 2017's US events;
      - "eu" → "europe", "sa" → "south america";
      - "brz" and "br" → "brazil" (2017-2019; Brazil plays in South America's events from 2020);
      - "sea" → "southeast asia" and 2017's "s e asia";
      - "aus" → "australia" and 2017's "australian"; "oce" → "australia" (Oceania);
      - "mena" → "middle east"; "jpn" and "jp" → "japan".

      "me" and "us" aren't terms, since they're everyday words.
    - Every phrase matches official events: 12 for "low tier city", 75 for "winter championship", 78 for "north america", and so on.
    - **How the agent uses them:**
      - It tries each of the user's words as typed and as each phrase it means, and a phrase as its term ("North America" also finds names that say "(NA)").
      - It then matches those against event names.
      - The event aliases cover the irregular cases.
  - **MSI (decided 2026-10-05):** "msi" first meant "midseason invitational", a name no official event has. It now defaults to the 2022 Brawlhalla Midseason Championship, which people call the Midseason Invitational.
    - The aliases "msi", "msi 2022", "midseason invitational" and "midseason invitational 2022" name its two events.
    - Their note, kept in `event_aliases.note`, says someone may mean another midseason event, so the answer says which one it used.
    - The other midseason events are LTC Midseason Online 2020 and the Midseason Championship 2026. A Midseason Championship 2025 isn't an official event.
- **Dev builds:** `--event ID` builds only the named events, and `--dev` builds the awkward cases in `DEV_EVENTS` (16 events). Neither ever goes live, but both check every curated row, as a full build does. `build_info` records the build's scope.
- **For later steps:**
  - `v_events` should order matching rules by priority, then pattern, so a tie can't change between builds (step 7).
  - An event matched by two rules of the same lowest priority, with different formats, goes to the review list (step 8).
- **Tests:** 13 new; the suite (102) passes. On the cache, a full build loads 622 events (375 listed as 1v1, 247 as 2v2), the 8 curated rows, 46 aliases and 10 event terms, and the dev build loads its 16 events.

**Step 3 (2026-10-05):**
- **Built:**
  - `build_players.py` holds two build steps: players (step 3) and standings (step 4).
  - `sources.py` lists the query versions the builder reads.
  - `problems.py` defines `BuildStop`, for data the build can't work around, such as two players with one negative ID. Curation errors are one kind of it.
- **Players:** 145,608 Stats API records, from 1,523 ListPlayers responses, teammate records and PR rows.
  - A lookup answers an ID it doesn't know with an all-null record. There are 98 of those, one per platform player without a record, and they're skipped.
  - No platform ID is claimed by two records, and no value differs between responses.
  - Every platform player in the standings and entrant lists was looked up.
- **Platform-only players:** 27 start.gg players and 1 Challengermode player who placed have no record, so they get negative IDs.
  - The 15 who only played, at the three events missing standings, come with the matches step.
  - The registry that assigns IDs is kept on the build, so later steps add players through it.
- **Standings:** 346,146 rows at 618 events (start.gg 329,353, Challengermode 16,793).
  - Every start.gg event's placed entrants equal start.gg's own count. CEO Dreamland 2020 has none.
  - 27 (event, player) pairs are entered twice: P.V player, both members of the ThousandCut/Thepokymater team, and 24 more. Step 4 keeps one placement each.
- **For check 5 (step 8):** Challengermode's `reported_entrants` is the roster's `lineupCount`. In 26 events it exceeds the placed lineups, by 1 to 9 (41 in all), because it counts lineups that registered but never played. So check 5 compares brackets with entrant lists, as the crawl's check does, rather than this count.
- **Speed:** the players step takes 6 s, the standings step 17 s. The dev build has standings at 12 of its 16 events: the Pro Series finals and CEO Dreamland 2020 have none.
- **Tests:** 6 new; the suite (108) passes.

**Step 4 (2026-10-05):**
- **Built:** `build_placements.py`, build step 5, which fills `placements` and `teams`.
  - **Placements** come from the standings, one per player per event. A player entered more than once keeps the entrant that wasn't DQ'd first, then the better placement, then the lower entrant ID. The placement keeps that entrant's team.
  - **Teams** are the entrants with exactly two players in events whose effective mode is 2v2, so the mode override counts. Team IDs follow the pairs' order, so the same pairs get the same IDs in every build. The views map merged records to canonical players (step 7).
  - **The Pro Series finals** take their placements from every single-player GetPlayerPlacements page in the cache that lists them, the newest response winning. A 2v2 pair's pages are left out, and the placements get no team ID, which is only for 2v2 pairs.
  - **Stats API placements for entrants missing from standings** (stage 3c; none today) come with the matches step, which finds those entrants.
- **On the cache:** 346,199 placements: start.gg 329,322, Challengermode 16,793 and the Stats API 84.
  - 31 standings rows were folded in, from 24 players entered twice, 2 entered three times and 1 entered four times. Most are "Deleted user" accounts.
  - ThousandCut and Thepokymater keep their 1025th place and team, not the DQ'd 2049th.
  - 44,692 teams, and all 131,134 2v2 placements have one: every 2v2 entrant has two players.
  - CEO Dreamland 2017's doubles get teams through the mode override. Crew battles, 3v3 and 1v1 events get none.
  - The finals: 24, 24 and 36 placements, in their team shapes (places 1-5 shared by teams of three in 2019, six teams of six in 2021).
- **Speed:** the build's connection now uses a 256 MB page cache and in-memory temp storage, rather than SQLite's 2 MB and temp files. Writing players now rechecks only new players and platform-only ones. The build takes about 27 s through this step: players 4 s, standings 14 s, placements 10 s.
- **Tests:** 3 new; the suite (111) passes.

**Step 5 (2026-10-05):**
- **Built:** `build_matches.py`, build step 6, which fills `matches` and `match_players`.
  - **start.gg:**
    - The set pages of every chosen event, plus the pool pages of the four big 2020 events. Pool pages are tied to their events through each event's first page (its phases) and the phases' pool pages.
    - A set seen twice keeps its newest response, players included.
    - Byes and sets never played are left out. Scores are kept as reported (−1 for a DQ, NULL where none was given), and every set keeps start.gg's own winner.
    - Side 1 is slot 0.
    - Players come from the standings, else from the entrant list (P1b). Those met only there are registered as players here, with any Stats API placement (stage 3c; none in the cache).
  - **Challengermode:**
    - Completed matches in two-lineup series. Cancelled matches and byes are left out.
    - Side 1 is lineup 0.
    - No scores means a forfeit, stored 0–0, so it's a no-contest. The reported winner comes from the match result.
  - **`event_sources`** gets start.gg's set totals and phase states.
  - **Left out but counted:** what isn't stored goes in `build_info.match_counts`, for check 9.
- **On the cache:** 560,184 matches and 1,386,358 match players.
  - start.gg: 536,400, which is 536,633 sets minus 189 byes and 44 never played. Challengermode: 23,784, leaving out 164 cancelled matches.
  - Every match has players on both sides, and the players per side fit each format: 1 in 1v1, 2 in 2v2, 3 in crew battles.
  - start.gg: 258,886 DQs (106,899 double) and 260 sets with only a winner (259 plus one with a single score), as in the schema proposal's §1.
  - Challengermode: 2,034 no-contests (2,012 forfeits and 22 explicit 0–0 draws) and 2 ties of 1–1.
  - Reported winners disagree with the scores in 3 matches: a start.gg 2–0 whose reported winner is the other side, and the two 1–1 ties. Check 9 lists them.
- **Correction: CEO Dreamland 2020 was never played on start.gg.**
  - All 161 of its sets are unstarted "preview" placeholders, and its only phase is still "CREATED". The in-person event was apparently cancelled; Brawlhalla CEO Dreamland ONLINE followed on 2020-03-28.
  - So it has no matches and no placements. The crawl's "81 entrants in sets" there were entrants of placeholders.
  - The entrants who played without a placement are SEA League Week 1/4's and MAX MODE 2025's 70. 10 of their players have no Stats API record and get negative IDs here, 37 start.gg platform-only players in all. The crawl's 15 included 5 who appear only in CEO Dreamland 2020's placeholders.
- **Speed:** secondary indexes are now created once, after the steps (as the build order intended), rather than kept up to date row by row. A build through this step takes about 45 s, down from 80: players 2 s, standings 8 s, placements 2 s, matches 30 s, indexes 2 s. Parsing the 11,000 set pages is most of the matches step.
- **Tests:** 4 new; the suite (115) passes.

**Step 6 (2026-10-05):**
- **Built:** `build_aliases.py` (build steps 7 and 8) and `build_rankings.py` (step 9).
  - **Aliases:** one row per (alias, player), keeping the strongest kind:
    1. a curated nickname, with its note;
    2. the display name, whole, tag included;
    3. the name without its tag;
    4. former names: older Stats API names, start.gg tags at each event (from the standings and entrant lists, shown with the event's prefix), and Challengermode usernames. The newest spelling is shown.
  - **Merges:** curated rows first, then the automatic ones that survive.
    - IDs are resolved as players are today: a negative ID through its platform ID.
    - A merge that conflicts once resolved stops the build if it's curated, and is dropped if it's automatic.
    - Chains are collapsed.
  - **Rankings:** one PR row per player, mode and list date, and the Stats API's career earnings for every ranked player, $0 included.
- **On the cache:**
  - 191,472 aliases: 7 nicknames, 145,532 display names, 1,269 names without tags and 44,664 former names. 65 players have none, because their names are only symbols.
  - 671 merges into 671 canonical players.
  - 6,209 PR rows. Career earnings for 4,981 ranked players, 400 of them above $0; gdsandstorm leads at $258,984.17, as the survey found.
  - Spot checks:
    - "godly" finds Zivai through "Kingdom | Godly", "littleflower" finds flowerVS, and "balloonboy" finds BBBalloonBoy through "LGN | BalloonBoy".
    - Curated nicknames win, with their notes.
    - Seven Stats API records are named Boomie, so the agent must choose (146606) and mention the others.
- **Change from the approved plan (for review):**
  - A curated row naming a player the cache has no record of is skipped and listed (`build_info.curated_rows_skipped`, then the review list in step 8). It no longer stops the build.
  - The case behind it: the hand-decided hardymj merge in `player_merges.csv` names record 632566. That's a Challengermode-only record known from the survey, whose only event isn't official, so the crawl never fetched it.
  - From the builder's side such a row looks like a typo, but a merge with it can't change any result.
  - An unknown event still stops the build.
- **Lesson:** steps can't rely on the secondary indexes, which now come at the end. One correlated lookup on `player_aliases.player_id` took 572 s until it moved to Python.
- **Speed:** a full build takes about 25 s on a quiet machine (aliases 3 s; merges and rankings under 1 s). Under load, steps have run up to twice as long.
- **Tests:** 5 new; the suite (121) passes.

**Step 7, in progress (2026-10-06):**
- **Decided by the user:**
  - Curated rows naming unknown players stay skip-and-review. They're listed prominently at the end of every build log and in `status`; the review list (step 8) will list them too.
  - `v_win_runs` is a per-win summary with no rank column. Question 11's ordering is documented in the view, for the agent to apply.
  - Views encode the decided counting rules and reusable building blocks, not answers to particular target questions.
  - Holding out mismatched new events comes in step 8.
- **Done:**
  - `views.sql` holds 13 views, each documented inside its definition (SQLite keeps that text in `sqlite_master`, where the agent reads the schema).
  - The build creates the views after the indexes and compiles each one.
  - The new `unplaced_entries` table holds players who played without a placement.
  - `players.canonical_id` (indexed) holds the merges for the views.
  - Every answer checked matches the survey: BBBalloonBoy 27 medals, Raydish 6 official wins, Hexoo 5th at Community Tournament #2.
- **Left:**
  - Speed up the views still too slow for an agent: `v_win_runs` (20 s for one player), `v_player_medals`, `v_team_results` and `v_head_to_head_2v2` (about 5-6 s each), and `v_entries` (1.7 s). Per-player `v_results`, the 1v1 head-to-heads and match lists already take under 0.1 s. The likely cause is the window over all placements in `v_results` feeding aggregates.
  - Tests for the views' rules.
  - Docs and CLAUDE.md for step 7.
