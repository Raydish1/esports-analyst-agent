# esports-analyst-agent

An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Ask a question in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer, with a chart when useful.

Capstone project for a CMU agentic AI course.

## Layout

| Directory | Purpose |
|---|---|
| `ingest/` | Data collection from APIs |
| `agent/` | LangGraph agent code |
| `eval/` | Evaluation questions and scoring |
| `app/` | Demo UI (Streamlit) |
| `data/raw/`, `data/db/` | Local data only, never committed |

## Status

Data exploration phase. The database schema and agent are not built yet.

Findings so far are in [`docs/api-survey.md`](docs/api-survey.md). To re-run the API survey (Node 18+; it writes to `data/raw/survey/`):

```bash
cd ingest && npm install && npm run survey
```

The start.gg and Challengermode survey ([`docs/platform-api-survey.md`](docs/platform-api-survey.md)) needs API credentials in `.env` (copy `.env.example`):

```bash
python ingest/survey_platforms.py
```

## Data

Data comes from the official Brawlhalla Esports Stats API, which is for personal use only. Downloaded data stays local and is git-ignored. See `CLAUDE.md` for details.
