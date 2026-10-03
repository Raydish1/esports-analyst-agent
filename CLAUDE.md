# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/, SDK: `@bmg-esports/sdk` on npm). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. Bracket details may later be supplemented from the start.gg and Challengermode APIs.

## Data terms
The Stats API is for personal use only, so downloaded data must never be committed to the repo.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. Ingestion may use Node if the SDK makes that simpler.

## Current phase
Data exploration. Do not build the database schema or agent yet.

## Conventions
- Explain significant design choices before implementing them.
- Keep changes small and reviewable.
