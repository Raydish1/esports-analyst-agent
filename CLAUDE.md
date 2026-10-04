# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. The start.gg and Challengermode APIs add former player names, prize payouts and bracket details, and Esports Earnings fills gaps in career earnings.

## Data terms
The Stats API is for personal use only, so API responses and the built database (`data/`) must never be committed. The repo stays private, so the hand-made files in `curation/` and the event list in the schema proposal's appendix may be committed, even though they contain event names and IDs from the API.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. The fetcher is Python too: a small HTTP client, not the Node SDK (`@bmg-esports/sdk`), which hides status codes, has a fixed 5-second timeout and never retries. `ingest/survey_api.mjs` stays only as an exploration tool.

## Project status (2026-10-04)
Planning is finished (committed 2026-10-04), and Phase 1 of the schema proposal's implementation plan (§9) is in progress on branch `claude/phase-1`. Build in the order of that plan, in small steps.

Done, with their write-ups:
- Stats API survey (`ingest/survey_api.mjs`) → `docs/api-survey.md`: what the API returns, its bugs and coverage gaps, and which target questions it can answer.
- start.gg and Challengermode survey (`ingest/survey_platforms.py`, clients in `ingest/platform_clients.py`) → `docs/platform-api-survey.md`: brackets, full standings and prize data those platforms add. Its last section lists the changes the schema proposal needs.
- Schema proposal → `docs/schema-proposal.md`: SQLite schema, views applying the rules below, crawl and coverage plans, earnings design, the target questions, a three-phase implementation plan, and the list of official events. Revised 2026-10-04 with the platform survey findings and the decisions below, including those on stage 6 and placements.
- `curation/tiers.csv`: a skeleton only (see the tiers rule below).
- Esports Earnings snapshot (`ingest/snapshot_esports_earnings.py`, run once on 2026-10-04) → `curation/esports_earnings_snapshot.csv`: the top 500 Brawlhalla earners from their website, with the raw HTML in `data/raw/esportsearnings/`. It isn't part of the crawl and isn't refreshed.
- Curation seed files holding the decisions so far: `curation/player_aliases.csv` (nicknames), `curation/player_merges.csv` (duplicate records of one person) and `curation/external_ids.csv` (confirmed Esports Earnings links).
- Phase 1, step 1: the Stats API fetch layer (`ingest/statsapi.py`, with the response cache and request log in `ingest/cache.py`) and crawl stage 0 (`python ingest/crawl.py events`), which finds all 622 official events. Tests: `python -m unittest discover -s tests`.
- Phase 1, step 2: a resumable task queue and run lock (`ingest/tasks.py`), `python ingest/crawl.py status`, stages 1–2 run in full (4,981 PR players with profiles), and a pilot of stages 3–4 on 200 of those players.
- P1 start.gg standings (`python ingest/crawl.py standings`, with `ingest/startgg.py`): all 529 official start.gg events, 268k placements from 138,696 start.gg players. The run lock is per API, so a start.gg stage can run alongside a Stats API stage.

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
  - Merge candidates are ranked in tiers (exact name, same region, non-overlapping activity). Only tier 1 is accepted automatically; the rest go to a review CSV. The user has asked the esports team for their account-link data.
  - Challengermode: renew the access token shortly before its `expiresAt`, and on an auth error renew it and retry once. Keep at least 3.5 s between requests.

Next step: build the platform fetches (start.gg brackets, Challengermode entrant lists and brackets, the platform-player lookups, the Pro Series finals), pilot them on a few events, and give the user the commands for the full runs. The user runs long fetches themselves. Don't start anything beyond a pilot without asking, and check with the user before starting any new stage.

## Domain definitions (decided)
- Data scope for now: official events only (`isOfficial: true`); community events are left out.
- "Major" means an official event (`is_official`) for now, and that's the agent's default filter. Answers say "official events" rather than "majors", so it's clear what was counted.
- Tiers are deferred. `curation/tiers.csv` is a skeleton (an example scale, with a default tier per auto-detected event family), and nothing reads it or depends on it yet.
- A "medal" is a top-3 placement (1st, 2nd or 3rd) at an official event; community events don't count.
- Crew battles count as 1v1. In head-to-heads, a crew battle match counts only if it's stored as a one-on-one game. Other non-standard formats (3v3, Triples, Brawlball, Kung Foot, Volleybrawl, etc.) count toward neither 1v1 nor 2v2.
- A tournament split into phases (e.g. Swiss stage + Top 8 Finals) counts once, using the last phase reached.
- "The last event a player entered" counts every official event. If the newest is a side format (Kung Foot, Triples, etc.), the answer also gives the newest 1v1 or 2v2 event.
- A tournament win's dominance is measured by games lost across the run: the fewest is the most dominant (3-0 in every set, then one dropped game, and so on). Ties go to fewer sets dropped, then to more games won.
- A DQ (a `-1` game score) or a forfeit (a Challengermode match with no scores, which the Stats API shows as 0-0) is a no-contest, flagged by `matches.is_no_contest`. It counts as neither a win nor a loss and contributes no games.
- 2v2 prize amounts are per team; each player gets half. Crew battle prizes are per crew; each player gets a third.
- People often use names other than a player's current display name ("marckiemoo" is Marckiem00, "Hexo" is Hexoo, "flower" or "flowers" is flowerVS). The API's search also misses inactive players (Boomie is player 146606). Resolve players against our own data, not only the API search. Decided names go in `curation/player_aliases.csv`, and duplicate records of one person in `curation/player_merges.csv`.

## Conventions
- Explain significant design choices before implementing them.
- Keep changes small and reviewable.
