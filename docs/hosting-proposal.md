# Hosting the agent with a hosted model API: proposal (2026-11-19)

The live page (GitHub Pages) plays back recorded answers only. To answer real questions it needs a server running the
app and the agent, and a model the server can reach without the user's GPU being on. Nothing here is built.

## What the agent needs at run time

| Piece | Now | Hosted |
|---|---|---|
| The model | qwen3:8b with thinking, through Ollama's `/api/chat` (`agent/react.py`, `chat`) | a hosted API (below) |
| Question embeddings, for the worked examples | nomic-embed-text through Ollama's `/api/embed` (`agent/retrieval.py`) | the same, with Ollama on the server's CPU (embeddings only) |
| The database | `data/db/eval/eval-v1.sqlite`, 463 MB, read-only | on the server's persistent disk |
| The examples' index | Chroma in `data/rag/`, 1 MB, rebuilt from `agent/examples/examples.toml` | rebuilt on the server at start |
| The app | `app/server/main.py` (FastAPI, one worker, a queue) | the same, behind HTTPS |

## Decision 1: which hosted model

| Option | For | Against |
|---|---|---|
| **A. The same qwen3:8b, from a hosted provider with an OpenAI-compatible API** (recommended) | The evaluation's numbers still hold, after a check run. An open model, as the project planned. Cheap per question. | Providers differ in tool calling and in how they return the model's thinking: needs a check that tool calls and thinking come through as Ollama gives them. Sampling seeds may not be honored, so runs aren't exactly repeatable. |
| B. A larger open model (a bigger Qwen3, for example), hosted the same way | Likely more accurate, especially at SQL and at answer writing. | A different model: the evaluation runs again, and some tuned prompts may need tuning again. |
| C. A frontier model API (Claude, GPT) | The most capable. | A different model and a different tool-call format. It moves away from the project's open-model plan, and the evaluation runs again. |

With A, the switch is a provider setting, so B stays a one-line change to try later.

**Decided (2026-11-19): A, the same qwen3:8b.** What a search found (2026-11-19):
- Hosted Qwen3-8B is thinning out: one aggregator reports OpenRouter deprecated its listing on 2026-10-09, in favor of
  newer Qwen models. Sources disagree on whether hosted versions support tool calling.
- Still listed: **Alibaba Cloud Model Studio** (Qwen's own platform, OpenAI-compatible, thinking switched by a
  parameter; about $0.18 per million input tokens and $0.70 output, thinking output higher, as of June 2026) and
  **Fireworks** (about $0.20 per million either way).
- So before building: one test request with the chosen provider's key, checking tool calls and thinking come back, and
  that the model's name is still served. If none passes, the fallback is B with the closest newer small Qwen.
- **Embeddings stay off the provider:** nomic-embed-text is small enough for the server's CPU. Ollama runs on the server
  for embeddings only, so `retrieval.py` needs no change; only `chat` moves to the hosted API.

## Decision 2: where the app runs

| Option | For | Against |
|---|---|---|
| **A small VM (a cloud VPS, for example)** (recommended) | A persistent disk for the 463 MB database, a fixed monthly cost, full control. | Its updates and HTTPS are ours to set up, with Caddy for automatic certificates. |
| A container host with a volume (Fly.io, for example) | Deploys from the repo, HTTPS built in. | The database goes on a volume; cold starts load the name index, about 20 s, unless it's kept running. |

Either way, the page on GitHub Pages stays the public demo, and the server also serves the page itself, so there's no
cross-site setup. The model API key lives only in the server's environment, never in the repo or the browser.

## Changes to the code

1. **`agent/react.py`'s `chat`** takes a provider setting (embeddings stay on Ollama, on the server): Ollama as now, or an
   OpenAI-compatible API (`MODEL_PROVIDER`, `MODEL_BASE_URL`, `MODEL_API_KEY`, `MODEL_NAME` in `.env`). The adapter
   converts between the two formats: tool calls with their IDs, tool results, and the thinking text, which the trace
   keeps. This is in `agent/`, which the other session works in (its branch, `claude/agent`, has commits from today),
   so it's either that session's change or one made here after it merges.
2. **A check run:** the evaluation set with the hosted model, scored with the harness, against the last Ollama run. Any
   real drop is reported before switching the public page to live.
3. **Safeguards on the server** (`app/server/`):
   - per-visitor limits, for example 5 questions a minute and 40 a day, with a clear message when hit;
   - a global daily cap on questions, under the provider's spending limit, which is set on the provider's side too;
   - a limit on each question's total model tokens and time (steps are already capped at 8);
   - a switch that turns live mode off (an environment setting) and falls back to the recorded demo, which also happens
     automatically when the model API fails;
   - questions logged without IP addresses, for spotting abuse and bad answers.
   Already in place: read-only database access with a 30-second query limit, a 500-character question limit, a capped
   queue, tool results treated as data rather than instructions, the answer checks, and no server addresses or keys
   sent to the browser.
4. **Deployment:** a `Dockerfile` (or a setup script for the VM), the database copied up once by hand (it never goes
   in git), and a health check.

## Steps, one commit each

1. The provider setting in `chat` and `embed`, with tests on recorded replies. Coordinated with `claude/agent`.
2. A check run of the evaluation set with the hosted model, logged in `docs/experiments.md`.
3. The safeguards, with tests.
4. Deployment files, and the server up behind HTTPS in replay mode.
5. Live mode switched on behind the safeguards, at first for you only (an invite code), then for everyone.

## Needs from you

- The provider and model (decision 1), and an account with an API key, which you'd create and put in the server's
  environment yourself.
- The host (decision 2), and its account.
- Whether the `agent/` change in step 1 is made here, or in the other session.
