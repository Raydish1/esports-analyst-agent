# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/, SDK: `@bmg-esports/sdk` on npm). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. Bracket details may later be supplemented from the start.gg and Challengermode APIs.

## Data terms
The Stats API is for personal use only, so downloaded data must never be committed to the repo.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. Ingestion may use Node if the SDK makes that simpler.

## Project status (2026-10-04)
Data exploration and design. Nothing is built yet: don't build the database or the agent until the schema proposal has been updated and approved.

Done, with their write-ups:
- Stats API survey (`ingest/survey_api.mjs`) → `docs/api-survey.md`: what the API returns, its bugs and coverage gaps, and which target questions it can answer.
- start.gg and Challengermode survey (`ingest/survey_platforms.py`, clients in `ingest/platform_clients.py`) → `docs/platform-api-survey.md`: brackets, full standings and prize data those platforms add. Its last section lists the changes the schema proposal needs.
- Schema proposal → `docs/schema-proposal.md`: SQLite schema, views applying the rules below, crawl and coverage plans, earnings design, and the list of official events for tier assignment.

Decisions so far: the domain definitions below, plus these.
- Career earnings: the Stats API figure first, with Esports Earnings as the fallback; each figure is stored with its source and as-of date.
- Per-tournament prize money: start.gg's structured payouts; for Challengermode-era events, the prize split parsed from the tournament description. Payouts are never estimated from a total prize pool.
- API credentials live only in `.env` (see `.env.example`).

Next step: update `docs/schema-proposal.md` with the platform survey findings, then settle its open questions (tier scale, whether the event list and curation files may be committed).

## Domain definitions (decided)
- Data scope for now: official events only (`isOfficial: true`); community events are left out.
- "Major" means any event with `isOfficial: true` in the Stats API.
- A "medal" is a top-3 placement (1st, 2nd or 3rd) at an official event; community events don't count.
- Crew battles count as 1v1. Other non-standard formats (3v3, Triples, Brawlball, Kung Foot, Volleybrawl, etc.) count toward neither 1v1 nor 2v2.
- A tournament split into phases (e.g. Swiss stage + Top 8 Finals) counts once, using the last phase reached.
- A DQ (a `-1` game score) or a forfeit (a match with no scores, which the Stats API shows as 0-0) counts as neither a win nor a loss.
- 2v2 prize amounts are per team; each player gets half. Crew battle prizes are per crew; each player gets a third.
- People often use names other than a player's current display name ("marckiemoo" is Marckiem00, "Hexo" is Hexoo). The API's search also misses inactive players (Boomie is player 146606). Resolve players against our own data, not only the API search.

## Conventions
- Explain significant design choices before implementing them.
- Keep changes small and reviewable.
