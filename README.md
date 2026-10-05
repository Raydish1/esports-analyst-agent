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

Building Phase 1 of the plan in [`docs/schema-proposal.md`](docs/schema-proposal.md) (§9). The crawl runs one stage at a time:

```bash
python ingest/crawl.py status      # progress of every stage; safe to run during a crawl
python ingest/crawl.py events      # 0: official events
python ingest/crawl.py pr          # 1: PR lists, which seed the players
python ingest/crawl.py profiles    # 2: player profiles
python ingest/crawl.py lookups     # 2b: the Stats API record of every start.gg and Challengermode player
python ingest/crawl.py histories   # 3: official placements and teammates (held after its pilot)
python ingest/crawl.py proseries   # 3b: placements at the three Pro Series finals
python ingest/crawl.py teams       # 4: official placements of each 2v2 pair (held after its pilot)
python ingest/crawl.py standings   # P1: start.gg standings of official start.gg events
python ingest/crawl.py brackets    # P4: start.gg sets, pools and last-phase games
python ingest/crawl.py cm          # P5: Challengermode entrant lists and brackets
```

**Order of the Phase 1 platform fetches.** `brackets` is the long one, about 4 hours, and it uses only start.gg, so it can start first and run alongside the rest. Meanwhile, one after another: `cm`, then `lookups` (which needs the Challengermode entrant lists), then `proseries` (which reuses the lookups).

Each run plans its stage's tasks from what earlier stages found, works through them, and logs to `data/logs/crawl-<stage>.log`. Stages on different APIs (the Stats API, start.gg, Challengermode) can run at the same time; two stages on the same API can't. Re-running a command resumes where it stopped, and Ctrl+C stops after the current task. For a pilot, `--event ID` limits `brackets`, `cm`, `lookups` and `proseries` to the events named, and `brackets --max-pools N` fetches only the first N pools of each phase of an event over start.gg's 10,000-set cap. A rejected task (a client error) isn't retried on its own; once its cause is fixed, re-run the stage with `--retry-rejected`.

Tests use only the standard library:

```bash
python -m unittest discover -s tests
```

API findings are in [`docs/api-survey.md`](docs/api-survey.md). To re-run the API survey (Node 18+; it writes to `data/raw/survey/`):

```bash
cd ingest && npm install && npm run survey
```

The start.gg and Challengermode survey ([`docs/platform-api-survey.md`](docs/platform-api-survey.md)) needs API credentials in `.env` (copy `.env.example`):

```bash
python ingest/survey_platforms.py
```

## Data

Data comes from the official Brawlhalla Esports Stats API, which is for personal use only. Downloaded data stays local and is git-ignored. See `CLAUDE.md` for details.
