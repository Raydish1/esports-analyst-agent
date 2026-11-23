# Brawlhalla Cortex

Cortex is an agent that answers questions about the history of official Brawlhalla esports events. A caster, producer or player asks a question in plain English, such as "where did this team place at the last tournament?". The agent looks the answer up in a database of every official result since 2017, checks its own answer in code, and can draw the answer as a broadcast-style stat card.

This is the capstone project for the CMU Agentic AI program.

- **Hosted demo:** https://brawlhalla-cortex.fly.dev plays recorded answers and serves the MCP server. It runs no model, so it can't answer new questions.
- **Static demo:** https://raydish1.github.io/esports-analyst-agent/ plays the same recorded answers.

## Use Cortex from your own model

Cortex is also an MCP server, so you can connect your own AI assistant to its data and its stat cards. The server is always on at https://brawlhalla-cortex.fly.dev/mcp/. It has 19 tools: the agent's 14 tools for looking up players, events and results, and 5 tools that return broadcast-style cards as images.

To connect Claude Code, run this command:

```bash
claude mcp add --transport http cortex https://brawlhalla-cortex.fly.dev/mcp/
```

To connect claude.ai, open **Settings**, then **Connectors**, and add a custom connector with the same address.

Your model writes its own answers. Cortex's checks on names and numbers run only inside its own agent loop, so they don't check answers that another model writes.

## What it does

- It answers questions about players, head-to-heads, events, rankings and 2v2 teams at the 622 official events since 2017.
- It turns names written casually ("marckiemoo", "balloonboy", "bcx 2022") into the right player or event. When a name could mean several players, it asks which one.
- It says when the data can't answer a question. A missing earnings figure isn't $0, and a cancelled event wasn't held.
- It draws player, head-to-head, sets, team and leaderboard cards in the style of the official broadcasts. Code fills each card from the query results.
- An MCP server gives other models the same tools and cards.

## Results

These are the final measurement's results (2026-11-21, qwen3:30b, seeds 0, 1 and 2), from its entry in [`docs/experiments.md`](docs/experiments.md). Each run on the 45 questions was judged by hand, and the verdicts were reviewed. The conversation and audit rows count the turns that pass automatic checks.

| Test set | Result | Earlier result |
|---|---|---|
| 45 verified questions, runs right | 113 of 135 (84%) | 94 of 135 (70%), qwen3:8b, 2026-11-08 |
| Questions right in all 3 seeds | 34 of 45 | 25 of 45 |
| 19 conversations, turns that pass every check | 120 of 144 (83%) | |
| 49-question audit set, turns that pass every check | 158 of 162 | |
| Model time per run | 20.0 s | |

The agent was tuned on the 45 questions, and the held-out set of 16 can't measure new changes because it was read on 2026-11-17. The log has the limits of each result, the model comparison (qwen3:8b, 14b and 30b, and Claude Sonnet 5.5), and Checkpoint 5's three-agent experiment, which was measured and not kept.

## How it works

The agent is a single ReAct loop. These are its parts:

- **The database.** A builder makes a SQLite database from the official Brawlhalla Esports Stats API, start.gg and Challengermode. A build goes live only if its checks pass. Sixteen views hold the counting rules, such as "a disqualification is neither a win nor a loss".
- **The loop.** [`agent/react.py`](agent/react.py) runs qwen3:30b through Ollama, with thinking on, for at most 8 steps.
- **The tools.** `resolve_player` and `resolve_event` turn names into IDs. `run_sql` runs one read-only query with a 30-second limit. Eleven template tools in [`agent/templates.py`](agent/templates.py) hold tested SQL for common questions.
- **Retrieval.** Chroma stores 36 worked examples of a question and its SQL ([`agent/examples/examples.toml`](agent/examples/examples.toml)). The model sees the 3 that are closest to the question.
- **The checks.** Before the user sees an answer, code checks every name, ID and number in it against the tool results. A draft that fails goes back to the model once, and a claim that still fails is removed.
- **The web app.** [`app/`](app/) is a FastAPI server and a JavaScript page. The MCP server is [`app/server/mcp_server.py`](app/server/mcp_server.py).

[`docs/agent-walkthrough.md`](docs/agent-walkthrough.md) follows one question through the code, and [`docs/agent-mechanisms.md`](docs/agent-mechanisms.md) explains each check.

## How to review this project

1. Read the last entry of [`docs/experiments.md`](docs/experiments.md) for the final results, the changes after them, and the known limitations.
2. Read [`docs/agent-walkthrough.md`](docs/agent-walkthrough.md) to see how the agent works.
3. Open [`eval/questions/questions.toml`](eval/questions/questions.toml) for the 45 questions and their verified answers. The verdicts for each run are in [`eval/results/`](eval/results/), for example `20261121-final-questions-judgments.toml`.
4. Run the tests (see below). They need no database and no model.
5. Try the [hosted demo](https://brawlhalla-cortex.fly.dev).

The experiment log has one entry for each experiment, newest first. Each entry gives the setup, the results and the decision.

## Repository layout

| Folder | Contents |
|---|---|
| [`agent/`](agent/) | The agent: the loop, tools, templates, checks, retrieval, and the three-agent experiment (`pipeline.py`) |
| [`app/`](app/) | The web app, the MCP server, and the broadcast cards |
| [`eval/`](eval/) | The question sets, the evaluation harness, and every run's scores and verdicts |
| [`ingest/`](ingest/) | The API clients, the crawl, and the database builder |
| [`curation/`](curation/) | Hand-made data: nicknames, account merges, event names and overrides |
| [`docs/`](docs/) | The API surveys, the schema and build plans, the experiment log, and the walkthrough |
| [`tests/`](tests/) | Unit tests |
| [`deploy/`](deploy/) | The Fly.io deployment |

## Run it

### Run the tests

The tests need Python 3.12 or newer and the packages in `requirements.txt`. Tests that need the database, LangGraph or the Anthropic SDK skip themselves when those are missing.

```bash
pip install -r requirements.txt
```

```bash
python -m unittest discover -s tests
```

### Try Cortex without building anything

The fastest way to try Cortex is to connect your own model to the hosted MCP server, as [Use Cortex from your own model](#use-cortex-from-your-own-model) describes. The server has the full database, so your model can look up any player, event or record and draw the stat cards. The live demo in the presentation ran on a local model on my own computer, which you can't connect to, and the hosted demo page only plays recorded answers.

### Run the agent

To run Cortex's own agent, you need the model and the database on your machine. The agent needs the database, which isn't in this repository: API responses and the built database stay out of git (see [`DATA.md`](DATA.md)). To build it, you need API credentials for the Stats API, start.gg and Challengermode.

1. Install the packages, as for the tests.
2. Copy `.env.example` to `.env`, and fill in the API credentials and `OLLAMA_BASE_URL`, the address of an Ollama server with `qwen3:30b` and `nomic-embed-text`.
3. Fetch the data. Each stage resumes where it stopped. The full fetch takes several hours, and [`docs/build-plan.md`](docs/build-plan.md) gives the order.

   ```bash
   python ingest/crawl.py status
   ```

4. Build the database. A build goes live only if its checks pass.

   ```bash
   python ingest/build.py
   ```

5. Ask a question, or start a session with no question:

   ```bash
   python agent/ask.py "who won worlds 2019 1v1"
   ```

6. Start the web app in live mode, and open http://127.0.0.1:8000:

   ```bash
   python app/server/main.py --mode live
   ```

Chroma has no build for Python on Windows ARM64. On such a machine, run the agent with an x64 Python, or add `--examples off` to run it without retrieval.

## Data

The data comes from the official Brawlhalla Esports Stats API, start.gg and Challengermode, which gave permission for its public use (2026-11-17). [`DATA.md`](DATA.md) records the permission, what it covers, and the sources of the broadcast graphics and art.
