# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. The start.gg and Challengermode APIs add former player names, prize payouts and bracket details, and Esports Earnings fills gaps in career earnings.

## Data terms
The Stats API is for personal use only, so API responses and the built database (`data/`) must never be committed. The repo stays private, so the hand-made files in `curation/` and the event list in the schema proposal's appendix may be committed, even though they contain event names and IDs from the API.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. The fetcher is Python too: a small HTTP client, not the Node SDK (`@bmg-esports/sdk`), which hides status codes, has a fixed 5-second timeout and never retries. `ingest/survey_api.mjs` stays only as an exploration tool.

## Project status (2026-10-07)
**Phase 1 of the schema proposal's implementation plan (§9) is done** on branch `claude/phase-1`, ready for the user to merge into `main`.
- The builder makes the database from the fetched cache and `curation/`, as [`docs/build-plan.md`](docs/build-plan.md) describes.
- The live build passes every check, and it's frozen as the evaluation snapshot `eval-v1`.

Planning and write-ups:
- Stats API survey (`ingest/survey_api.mjs`) → `docs/api-survey.md`: what the API returns, its bugs and coverage gaps, and which target questions it can answer.
- start.gg and Challengermode survey (`ingest/survey_platforms.py`, clients in `ingest/platform_clients.py`) → `docs/platform-api-survey.md`: brackets, full standings and prize data those platforms add.
- Schema proposal → `docs/schema-proposal.md`: the design to build from.
  - Contents: the SQLite schema, views applying the rules below, crawl and coverage plans, earnings design, the target questions, a three-phase implementation plan, and the list of official events.
  - Its status note lists the decisions of 2026-10-04 and 2026-10-05. §1 has what the fetch found that the builder must handle, and §3 the crawl stages and their results.
- Build plan → [`docs/build-plan.md`](docs/build-plan.md): how the builder makes the database.
  - Contents: what the cache showed, the build order, how curation files are applied, the checks and their gates, when Phase 1 is done, support for the scheduled updater, and the order of work with each step's status.
  - Its decisions of 2026-10-05 are newer than the schema proposal where they differ.

What's fetched, all complete. Responses are in `data/raw/cache/`, and the request log and crawl tables in `data/db/crawl.sqlite`. `python ingest/crawl.py status` shows every stage.
- Stats API:
  - 622 official events (stage 0);
  - PR lists and profiles of 4,981 ranked players (1–2);
  - a 200-player pilot of histories and 2v2 teams (3–4; full runs held, as decided);
  - Stats API records for 146,261 start.gg and Challengermode players (2b; 98 have none, of whom 43 placed or played);
  - the Pro Series finals' placements (3b, 84);
  - a placement check for entrants missing from start.gg standings (3c; the Stats API had none).
- start.gg:
  - the standings of all 529 official start.gg events (P1: 267,697 entrants, 138,696 players);
  - all 536,633 sets with pools, round best-ofs and last-phase games (P4);
  - the entrant lists of the 3 events whose standings miss entrants (P1b).
- Challengermode: entrant lists and brackets of all 90 official events (P5: 11,996 lineups, 23,948 matches).
- Esports Earnings: a one-time snapshot of the top 500 earners (`ingest/snapshot_esports_earnings.py`, 2026-10-04) in `curation/esports_earnings_snapshot.csv`, with the raw HTML in `data/raw/esportsearnings/`. Not refreshed.

Code (`ingest/`; tests: `python -m unittest discover -s tests`):
- Clients: `statsapi.py`, `startgg.py` and `challengermode.py`, all writing every response to the cache in `cache.py` before parsing.
- The crawl: `crawl.py` holds the stages and `status`. `tasks.py` holds the resumable task queue and per-API run locks.
- `merge_candidates.py` builds the merge review list.
- The builder (`docs/build-plan.md`):
  - `build.py` runs a build: `python ingest/build.py`. Dev builds use `--dev` or `--event ID` and never go live. It also has these commands:
    - `status` and `rollback`;
    - `compare A B`: whether two builds hold the same data;
    - `freeze NAME`: a read-only evaluation snapshot in `data/db/eval/`. A name is never reused, so a later freeze is a new version (`eval-v2`);
  - `builds.py` handles the build files, the pointer and rollback;
  - `cache_reader.py` gives read-only access to the cache;
  - `curation.py` loads and checks the curated files;
  - `build_events.py` holds the events step and the hold-outs step: a new event (no row in `events.csv`) whose entrant sizes don't fit its mode stays out of the counts until reviewed;
  - `build_players.py` holds the players and standings steps;
  - `build_placements.py` fills placements and 2v2 teams, including the Pro Series finals' placements from the Stats API;
  - `build_matches.py` fills matches and match players from start.gg sets and Challengermode matches;
  - `build_aliases.py` fills player aliases (curated nicknames, display names, names without tags, former names) and merges;
  - `build_rankings.py` fills PR snapshots and Stats API career earnings;
  - `views.sql` holds the 14 views the agent queries, `v_event_coverage` included:
    - each documents its counting rules inside its definition, which SQLite keeps in `sqlite_master`;
    - the build compiles every view, then runs `ANALYZE`, without which some views take minutes;
  - `checks.py` holds the checks, their gates and the verdict;
  - `report.py` writes each build's report (`data/reports/<build>/report.md`) and the review list;
  - `sources.py` lists the query versions the builder reads;
  - `problems.py` defines `BuildStop` (and `CurationError`), which end a build with a list of problems;
  - `schema.sql` holds the tables;
  - `names.py` holds the name normalization shared with `merge_candidates.py`;
  - `target_questions.py` is the target questions' regression check (`python ingest/target_questions.py`, optionally `--build PATH`). Its expected answers come from our own data, so it isn't the evaluation gold set. New results change some answers, and the expected ones are then updated on purpose.

Curation (`curation/`, committed):
- `player_aliases.csv`: nicknames, among them "bunny", "vem" and "halloween!" from the known events (2026-10-07).
- `player_merges.csv`: 3 merges decided by hand (Remmy, hardymj and karuzzi) and 670 accepted automatically (tier 1).
- `merge_rejections.csv`: empty so far.
- `external_ids.csv`: Esports Earnings links.
- `events.csv`: a row for every official event (2026-10-06). A row without overrides records that the event's detected mode and format were checked, so only events fetched later are new. The overrides:
  - the three Pro Series finals as crew battles, and CEO Dreamland 2017's doubles as 2v2;
  - the two Brawl League Masters Season 4 phase splits;
  - CEO Dreamland 2020 as `cancelled` (not held), and SEA League Week 1/4 as `placements_unreliable`.
- `check_exceptions.csv`: known check failures with their explanation, by check ID and subject (the build plan's §3):
  - CEO Dreamland 2020 having no winner;
  - the players who played without a placement at SEA League Week 1/4 and MAX MODE 2025 (completeness);
  - the missing match data of the three Pro Series finals and the Brawl League Masters Season 4 Swiss stages (match presence).
- `known_events.csv`: events the user knows well (13, all passing since 2026-10-07), with the winner, runner-up and top 8 the `known_events` check compares, names resolved through aliases.
  - Format: `event` (as the user named it), `event_id`, `mode`, `winner`, `runner_up`, `top8`, `entrants`, `notes`.
  - `top8` goes from 3rd down in placement order: `;` between placements, `+` joining players or pairs tied at one, `/` joining 2v2 partners.
- `format_rules.csv`: name patterns that mark side formats (crew battles, 3v3, Triples, Brawlball, Kung Foot, …); the lowest priority wins.
- `event_aliases.csv`: names people use for events that the data doesn't, such as "bcx 2022" and "worlds 2019". Worlds 2018 was DreamHack Atlanta 2018. The Last Chance Qualifiers aren't Worlds.
  - "msi" (or "midseason invitational") defaults to the 2022 Brawlhalla Midseason Championship (decided 2026-10-05). Someone may mean another midseason event, so the answer says which one it used.
- `event_terms.csv`: words people use for words in event names:
  - "ltc" (Low Tier City);
  - "winters", "springs", "summers" and "autumns" (the seasonal championships);
  - region abbreviations: na, eu, sa, brz/br, sea, aus, oce, mena, jpn/jp.
- `tiers.csv`: a skeleton only (see the tiers rule below).

Merge review: **`data/review/merge_candidates.csv`** (git-ignored; regenerate with `python ingest/merge_candidates.py`, which makes no requests).
- It holds 434 tier-2 and 1,753 tier-3 pairs, strongest first, for the user to review at their own pace.
- By impact (2026-10-07), under the curation policy below:
  - 64 pairs involve a top 8 or better: 16 in tier 2 and 48 in tier 3, 8 with official wins and 16 with medals;
  - 178 more involve a player ranked in their region's top 100;
  - the other 1,945 are low-impact.
- Decisions go in `curation/player_merges.csv` (merge) or `curation/merge_rejections.csv` (not one person).
- To undo an automatic merge, move its row from the first file to the second.

The review list: **`data/review/review.csv`** (git-ignored), rewritten by every full build.
- It holds everything waiting for the user, most pressing first: curated rows skipped (marked `!!`), held-out events, unused check exceptions, possible phase splits, new events (without a row in `events.csv`: none since every event got one, 2026-10-06), automatic merges, and the merge candidates not yet decided.
- Each row has a key that stays the same from build to build, and says what settles it.

Decisions so far: the domain definitions below, plus these.
- Career earnings: the Stats API figure first. For players without one, the fallback is the Esports Earnings snapshot (source `esportsearnings_manual`, as of 2026-10-04), linked to players through `player_aliases`. Each figure is stored with its source and as-of date. The Esports Earnings API is blocked (its account login isn't working).
- Per-tournament prize money: start.gg's structured payouts; for Challengermode-era events, the prize split parsed from the tournament description, accepted automatically when it adds up to the stated total and otherwise reviewed by hand. Payouts are never estimated from a total prize pool.
- Missing isn't zero: when an event has no payout data, or a player has no career figure, answers say so rather than counting $0.
- API credentials live only in `.env` (see `.env.example`).
- Stage 6 and placements (2026-10-04; details in the schema proposal's status note, §1 and §3):
  - Matches come from event-level brackets: start.gg sets (pool by pool for the four 2020 events over start.gg's 10,000-result cap) and Challengermode matches. Not per player from the Stats API; stage 6's per-player code is dropped.
  - Placements come from start.gg standings and Challengermode entrant lists. Stats API placements are a cross-check.
  - Platform players are matched to Stats API records by batched ID lookups. A player with no record gets a `players` row with a stable negative ID derived from the platform ID, marked as not in the Stats API, with aliases from their standings names, re-resolved on every rebuild.
  - Full runs of stages 3 and 4 are held. The three Pro Series finals, which no platform has, get a small targeted Stats API fetch instead.
  - Merge candidates are ranked in tiers (exact name, same region, non-overlapping activity). Only tier 1 is accepted automatically; the rest go to a review CSV. The user has asked the esports team for their account-link data, which would settle most pairs.
  - Challengermode: renew the access token shortly before its `expiresAt`, and on an auth error renew it and retry once. Keep at least 3.5 s between requests.
- All three Pro Series finals count like crew battles (2026-10-05): `format_override = 'crew_battle'` in `curation/events.csv`. They were team events: eight teams of three in each 2019 region, six teams of six in 2021.
- Three start.gg events whose standings miss entrants who played: SEA League Week 1/4 (2017), MAX MODE 2025 and CEO Dreamland 2020 (2026-10-05).
  - Their entrant lists were fetched, so all their sets can be attributed.
  - Placements come from the Stats API where it has them. It had none, so all 151 such entrants stay unplaced.
  - Placements are never derived from brackets.
  - **Correction (found by the builder, 2026-10-05): CEO Dreamland 2020 was never played.** It was cancelled due to COVID-19 (confirmed by the user). Brawlhalla CEO Dreamland ONLINE followed on 2020-03-28.
    - All 161 of its start.gg sets are unstarted placeholders, so it has no results at all.
    - `events.csv` marks it `status = cancelled`, and `check_exceptions.csv` explains its missing winner.
    - The entrants who really played without a placement are SEA League's and MAX MODE's 70.
- Merge candidates (2026-10-05): built by `ingest/merge_candidates.py` with the tiers in the schema proposal (§1). Tier 1 (a start.gg-only and a Challengermode-only record, each its name's only record on its platform, same region, separate activity) is accepted automatically into `player_merges.csv`. Tiers 2 and 3 wait for review.
- The builder (2026-10-05; details in `docs/build-plan.md`):
  - Builds are versioned files in `data/db/builds/`, and a pointer file, `data/db/current.json`, names the live one. The agent reads the database through the pointer, read-only.
  - Each check has a gate: blocking, no worse than the live build, or review. A build goes live only if its gates pass.
  - A scheduled updater (Windows Task Scheduler) comes later. It fetches only new or recently ended events, rebuilds, and swaps the build in only if the checks pass. New curation needs go to a review list and never block it.
  - Tier-1 merges found by unattended runs go to `data/review/auto_merges.csv`, not `curation/`. New events whose team sizes don't fit their mode stay out of the counts until reviewed.
  - The frozen evaluation snapshot (`data/db/eval/`) is never updated automatically.
  - The §8 survey answers are a regression check, not independent verification. The user has confirmed Raydish's 6 official wins and verifies the others separately.
  - Curated rows naming a player the cache has no record of are skipped, not a reason to stop (2026-10-06). They're listed prominently at the end of every build log, in `status`, and in the review list, so typos get caught. The case: the hardymj merge names a Challengermode record with no official results. An unknown event still stops the build.
  - Views encode the decided counting rules and reusable building blocks, not answers to particular target questions (2026-10-06).
    - The agent reads each view's rules from its definition.
    - Question 11's dominance ordering is documented in `v_win_runs` for the agent to apply; the view has no rank column.
    - Views must stay fast when filtered by a player: no window or GROUP BY between the filter and the indexed tables.
- Curation policy (2026-10-06):
  - Low-impact cases (no official wins, medals or top placements): follow the data evidence and Claude's recommendation, with the evidence in the curated row's note.
  - High-impact cases (ranked players, top 8s, wins, medals): bring them to the user. "Ranked" means in a region's top 100 PR (decided 2026-10-07).
  - Outside NA, flag the high-impact cases the user may not know well, so they can ask someone from that scene.
- SEA League Week 1/4 (2026-10-06): start.gg's standings put 24 entrants in 1st place, so `events.csv` marks it `placements_unreliable` (see the domain definitions). It needs no check exception: the winners check skips such an event.

Next step: **the user's call, once `claude/phase-1` is merged:** Phase 2 (per-tournament earnings, schema proposal §9) or the agent.
- Explain designs before implementing them, and keep the work in small steps: one per commit, pushed after each, with a report after each for review.
- The user runs long fetches themselves: don't start any fetch beyond a pilot without asking, and check with the user before starting any new crawl stage.

## Domain definitions (decided)
- Data scope for now: official events only (`isOfficial: true`); community events are left out.
- "Major" means an official event (`is_official`) for now, and that's the agent's default filter. Answers say "official events" rather than "majors", so it's clear what was counted.
- Tiers are deferred. `curation/tiers.csv` is a skeleton (an example scale, with a default tier per auto-detected event family), and nothing reads it or depends on it yet.
- A "medal" is a top-3 placement (1st, 2nd or 3rd) at an official event; community events don't count.
- Crew battles count as 1v1. In head-to-heads, a crew battle match counts only if it's stored as a one-on-one game. Other non-standard formats (3v3, Triples, Brawlball, Kung Foot, Volleybrawl, etc.) count toward neither 1v1 nor 2v2.
- A tournament split into phases (e.g. Swiss stage + Top 8 Finals) counts once, using the last phase reached.
- "The last event a player entered" counts every official event. If the newest is a side format (Kung Foot, Triples, etc.), the answer also gives the newest 1v1 or 2v2 event.
- A tournament win's dominance is measured by games lost across the run: the fewest is the most dominant (3-0 in every set, then one dropped game, and so on). Ties go to fewer sets dropped, then to more games won.
  - A run with any unscored set (below) ranks after every fully scored run (decided 2026-10-05).
  - If such a run would have ranked near the top on its scored games alone, the answer mentions it in one line, so it isn't silently buried.
- An official event that wasn't held (`events.status = 'cancelled'`, such as CEO Dreamland 2020, cancelled due to COVID-19): answers say it wasn't held, not that its results are missing.
- An event whose standings are wrong (`events.status = 'placements_unreliable'`; so far SEA League Week 1/4, 2017, where start.gg placed 24 entrants 1st): its placements are left out of results (wins, medals, top 8s), its matches still count, and answers say why (decided 2026-10-06).
- A DQ (a `-1` game score) or a forfeit (a Challengermode match with no scores, which the Stats API shows as 0-0) is a no-contest, flagged by `matches.is_no_contest`. It counts as neither a win nor a loss and contributes no games.
- A set with a reported winner but no game score (259 start.gg sets, mostly 2017–2019) counts as a win and a loss (decided 2026-10-05). Unlike a forfeit, it was played. Its games are unknown, not zero:
  - game-based stats (games won or lost, game win rates, dominance) leave it out of the game counts;
  - the affected result is flagged: "includes sets with no recorded score";
  - a win with unscored sets never looks like a perfect run.
- 2v2 prize amounts are per team; each player gets half. Crew battle prizes are per crew; each player gets a third.
- People often use names other than a player's current display name ("marckiemoo" is Marckiem00, "Hexo" is Hexoo, "flower" or "flowers" is flowerVS). The API's search also misses inactive players (Boomie is player 146606). Resolve players against our own data, not only the API search. Decided names go in `curation/player_aliases.csv`, and duplicate records of one person in `curation/player_merges.csv`.

## Conventions
- Explain significant design choices before implementing them.
- Keep changes small and reviewable.
