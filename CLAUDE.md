# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. The start.gg and Challengermode APIs add former player names, prize payouts and bracket details, and Esports Earnings fills gaps in career earnings.

## Data terms
The Stats API is for personal use only, so API responses and the built database (`data/`) must never be committed. The repo stays private, so the hand-made files in `curation/` and the event list in the schema proposal's appendix may be committed, even though they contain event names and IDs from the API.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. The fetcher is Python too: a small HTTP client, not the Node SDK (`@bmg-esports/sdk`), which hides status codes, has a fixed 5-second timeout and never retries. `ingest/survey_api.mjs` stays only as an exploration tool.

## Project status (2026-10-05)
Phase 1 of the schema proposal's implementation plan (§9) is in progress on branch `claude/phase-1`. All of Phase 1's fetching is done and checked. **The next step is the builder, following [`docs/build-plan.md`](docs/build-plan.md)** (approved 2026-10-05), one step of its order of work at a time (below).

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
- The builder (`docs/build-plan.md`), as far as its order of work has gone:
  - `build.py` runs a build: `python ingest/build.py`, plus `status` and `rollback`. Dev builds use `--dev` or `--event ID` and never go live;
  - `builds.py` handles the build files, the pointer and rollback;
  - `cache_reader.py` gives read-only access to the cache;
  - `curation.py` loads and checks the curated files;
  - `build_events.py` is the events step;
  - `build_players.py` holds the players and standings steps;
  - `build_placements.py` fills placements and 2v2 teams, including the Pro Series finals' placements from the Stats API;
  - `build_matches.py` fills matches and match players from start.gg sets and Challengermode matches;
  - `sources.py` lists the query versions the builder reads;
  - `problems.py` defines `BuildStop` (and `CurationError`), which end a build with a list of problems;
  - `schema.sql` holds the tables;
  - `names.py` holds the name normalization shared with `merge_candidates.py`.

Curation (`curation/`, committed):
- `player_aliases.csv`: nicknames.
- `player_merges.csv`: 2 merges decided by hand and 670 accepted automatically (tier 1).
- `merge_rejections.csv`: empty so far.
- `external_ids.csv`: Esports Earnings links.
- `events.csv`: the three Pro Series finals as crew battles, CEO Dreamland 2017's doubles as 2v2, and the two Brawl League Masters Season 4 phase splits.
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
- Decisions go in `curation/player_merges.csv` (merge) or `curation/merge_rejections.csv` (not one person).
- To undo an automatic merge, move its row from the first file to the second.

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
  - **Correction (found by the builder, 2026-10-05): CEO Dreamland 2020 was never played on start.gg.**
    - All 161 of its sets are unstarted placeholders, and its only phase is still "CREATED". The in-person event seems to have been cancelled; Brawlhalla CEO Dreamland ONLINE followed on 2020-03-28.
    - So it has no results at all. The entrants who really played without a placement are SEA League's and MAX MODE's 70.
- Merge candidates (2026-10-05): built by `ingest/merge_candidates.py` with the tiers in the schema proposal (§1). Tier 1 (a start.gg-only and a Challengermode-only record, each its name's only record on its platform, same region, separate activity) is accepted automatically into `player_merges.csv`. Tiers 2 and 3 wait for review.
- The builder (2026-10-05; details in `docs/build-plan.md`):
  - Builds are versioned files in `data/db/builds/`, and a pointer file, `data/db/current.json`, names the live one. The agent reads the database through the pointer, read-only.
  - Each check has a gate: blocking, no worse than the live build, or review. A build goes live only if its gates pass.
  - A scheduled updater (Windows Task Scheduler) comes later. It fetches only new or recently ended events, rebuilds, and swaps the build in only if the checks pass. New curation needs go to a review list and never block it.
  - Tier-1 merges found by unattended runs go to `data/review/auto_merges.csv`, not `curation/`. New events whose team sizes don't fit their mode stay out of the counts until reviewed.
  - The frozen evaluation snapshot (`data/db/eval/`) is never updated automatically.
  - The §8 survey answers are a regression check, not independent verification. The user has confirmed Raydish's 6 official wins and verifies the others separately.

Next step: **the builder, following `docs/build-plan.md`'s order of work.**
- One step per commit, pushed after each.
- Report after each step for review rather than continuing through the list.
- The plan's status column shows which step is next.

Explain the builder's design before implementing it, and keep it in small steps. The user runs long fetches themselves: don't start any fetch beyond a pilot without asking, and check with the user before starting any new crawl stage.

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
