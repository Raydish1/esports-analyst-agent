# Web app for the agent: proposal (2026-11-17)

A local demo of the agent in the browser, built so it can be deployed publicly later. Nothing in `agent/` or `eval/`
changes: the app uses the hooks `react.Conversation` already has.

**Approved 2026-11-17** with the decisions at the end. It's built in `app/`, the directory the README already
reserved for the demo, on the branch `claude/web-app`.

## 1. What the agent already offers

`react.Conversation(tools, ask, ..., on_step, retriever, on_examples)` takes everything the app needs as arguments:

| Hook | What it gives the app |
|---|---|
| `ask` (the model call, `react.chat` by default) | A wrapper says "thinking" before each step. Replay mode swaps in recorded replies (§4). |
| `tools` (`react.Tools`) | A subclass whose `call` reports "resolving *boomie*" or "running a query" when the call starts, then calls the parent. |
| `on_step` | Each finished step: its tool calls, arguments, observations, the SQL a template ran (`ran`), and any check (`size_check`, `lookup_check`, `no_tool_check`, `answer_check`, `suggestions`, `name_swaps`). |
| `on_examples` | The worked examples retrieved for the question. |
| The returned trace | The answer, the outcome, and the flags for answers the checks couldn't confirm (`unreturned_names`, `unreturned_ids`, `answered_after_too_big`, `answered_after_lookup_miss`, `answered_without_tools`). |

One limit: a step only reports when it finishes. A model call takes 5–30 s, so the page shows "thinking (step 2)"
during it, then the step's tool calls. Only the start of a tool call comes from the `Tools` subclass.

## 2. Architecture

```
app/
  server/
    main.py        FastAPI: routes, static files, startup (loads Tools once), the --mode switch
    worker.py      one worker thread; a FIFO queue of jobs; per-job event log; the conversations
    runner.py      a conversation's agent: the hooks of §1, replay or live
    events.py      trace and step -> the event stream's events; the check notes; suggestions
    replay.py      recorded traces: the index, the held-out filter, the replayed model
    figures.py     returns [] for now: where stat graphics go later
  static/
    index.html, app.js, style.css
    vendor/        a markdown renderer and a sanitizer, vendored (no CDN at run time)
tests/
  test_web_events.py, test_web_replay.py, test_web_worker.py, test_web_app.py
```

### Backend

- **One worker, one queue.** The agent is synchronous (urllib to Ollama), so one thread runs jobs one at a time from a
  FIFO queue. Each job keeps its own list of events. A client waiting in the queue gets `queued {position}` whenever its
  position changes ("2 questions ahead of yours").
- **Conversations live on the server.** `POST /api/conversations` returns a random ID. Each ID holds one
  `react.Conversation`, so follow-ups and suggestion replies build on what came before, as in `ask.py`. A conversation
  runs one question at a time, expires after 30 idle minutes, and the server keeps at most 50.
- **Shared tools.** `react.Tools()` (the name index, a few seconds to load) loads once at startup. Every conversation
  shares it: conversations only read it, and the single worker means no two calls overlap.
- **Routes:**
  - `GET /api/info`: the mode (replay or live) and the example questions;
  - `POST /api/conversations`;
  - `POST /api/conversations/{id}/questions {question}` returns `{job_id, position}`. A question is 1–500 characters,
    and a full queue (20 jobs) gets a 503;
  - `GET /api/jobs/{job_id}/events`: Server-Sent Events. SSE is enough because events only go one way. The browser
    reconnects on its own, and `Last-Event-ID` replays what it missed from the job's log.
- **Model address.** Live mode reads `OLLAMA_BASE_URL` from `.env` with `load_env()`, as `ask.py` does. It's never sent
  to the browser, and every text the server sends has it redacted, since an error outcome quotes the exception.
- **Binding.** The server binds 127.0.0.1 by default.

### Events

Both modes produce the same events, and the page knows nothing else:

| Event | Data |
|---|---|
| `queued` | position |
| `started` | |
| `examples` | the retrieved examples' IDs and shapes |
| `thinking` | step number |
| `tool_started` | step, tool, a label ("Looking up the player *boomie*", "Running a query", "Getting *Worlds 2023*'s results") |
| `step` | step, a short thought (`ask.thought`), and for each tool call: tool, arguments, the SQL (the query, or the template's `ran`), the observation parsed into status, notes and tables, how long it took, and an error or refusal |
| `answer` | text (markdown), outcome, `notes` (§3), `suggestions` (§3), `name_swaps`, `figures` (empty for now), steps, model seconds |
| `error` | a message safe to show (Ollama unreachable, request error, replay out of sync) |
| `done` | |

`events.py` builds them from the trace and step dicts alone, so it's tested without a model or a server.

### Frontend

Plain HTML, CSS and JavaScript (ES modules), served by FastAPI. There's no build step and no Node: the page is small,
and a framework can come later if it grows.

- **Question box** with example questions as chips. In replay mode, the chips are questions that have a recording.
- **Progress list** while the agent works: one line per event ("Thinking, step 1", "Looking up the player *boomie*",
  "Query: 12 rows"), with the current one animated, and the queue position while waiting.
- **Answer card.** The markdown is rendered and sanitized; every other value from the server goes in with
  `textContent`, never `innerHTML`.
  - Above the answer: a notes box (§3), when there are notes.
  - Below it: a reserved `figures` area, hidden while `figures` is empty.
- **"How I got this"**, collapsed (`<details>`), one block per step:
  - the short thought;
  - each tool call: a template call as `player_results(player_id=146606, top=1)`, a query as formatted SQL;
  - the rows as a table, with what the model didn't see marked: "46 rows, too large to show the model", or "notes:
    ..." for a template;
  - a template's SQL in its own collapsed block;
  - checks that sent an answer back ("Answer check: named Lucky, which no tool returned; sent back"), and name
    corrections;
  - the retrieved examples, as one line at the top.
- **Mode badge**, "Replay" or "Live", always on screen, so a replayed answer is never mistaken for a live one.

## 3. Suggestions and check notes

**Suggestions.** When the outcome is `suggestions`, `step["suggestions"]` gives each unsure name's candidate IDs, and
the step's `resolve_player` observation gives each candidate's name, display and results ("Marckiem00, 47 official
results, 2022–2026"). Each candidate becomes a button. Clicking one sends its ordinal ("the first one") as the next
question in the same conversation, the path the 2026-10-25 run tested (6 of 6), not the name: names repeat (seven
players are called Boomie). The history keeps the clarifying question with the IDs, so the model knows what the reply
answers. With two unsure names, each gets its own row of buttons, and one Send button sends both choices ("the first
one for markiemoo, the second one for godly").

**Check notes.** An answer the checks let through without confirming gets a note above it, written in `events.py`:

| Trace field | Note |
|---|---|
| `unreturned_names` / `unreturned_ids` | Couldn't confirm: the answer names *X*, which the data lookups didn't return. |
| `answered_after_too_big` | Couldn't confirm: the answer came after a result too large to read, so its counts may come from partial data. |
| `answered_after_lookup_miss` | Couldn't confirm: a lookup found no *Y*, so this "none" may be a lookup mistake. |
| `answered_without_tools` | Couldn't confirm: the answer states facts without looking them up. |
| outcome `step limit`, `cut off at the output cap`, a request error | No answer, with the reason. |

A check that sent an answer back and then passed isn't a warning. It shows only in "How I got this".

## 4. Replay mode and the live switch

The mode is a server flag, `--mode replay` (the default) or `--mode live`, not a button on the page: once the app is
public, visitors mustn't be able to switch it.

**Replay, recommended: the recorded model replies, through the real loop.** A trace keeps every step's `thinking`,
`content` and `tool_calls`. `replay.py` gives `Conversation` an `ask` that returns those replies in order, and a
retriever that returns the trace's recorded `examples`. Everything else is the real agent:

- the real `Conversation` loop and checks, and the real tools on eval-v1 (no GPU, no Ollama, no chromadb, so it runs
  on the ARM64 Python too);
- replay and live mode differ only in the model call, so the event stream is tested on the same code path as live mode;
- the recorded steps' seconds are scaled (a tenth, at most 2 s per step), so the progress list has something to show.

If the agent has changed since the recording (a check now sends an answer back where it didn't), the loop asks for a
step the recording doesn't have. The job then ends with "the recording doesn't match the current agent", which also
shows where the other session's changes altered behavior. The alternative, replaying the stored trace as events without
running the loop, can't go out of sync, but it never runs the integration, so live mode would first run on demo day.

**The source.** Until the guardrail session's after-run finishes, the recordings are the existing runs below, and
replays mismatch wherever its new checks fire. After it, the source switches to that run's traces (`--replay-runs`).

**Which recordings.** `replay.py` indexes `data/experiments/*/traces.jsonl` and `data/experiments/sessions/*.jsonl`:

- it skips every record whose `set` is `heldout`, and the run `20261117-heldout` as a whole. It never opens
  `heldout.toml` or `heldout_checks.py`;
- the sessions and the `react.py` runs have no `set` field, but all are from 2026-10-26 or earlier, before the held-out
  set existed (2026-11-08). The index takes records without `set` only from before that date;
- a question matches by its normalized text; the newest run wins, at seed 0 when there is one;
- a follow-up in replay matches the next turn of the same session, so the suggestion buttons replay "did markiemoo
  ever win worlds" and then its follow-ups;
- a question with no recording gets "no recording for this question in replay mode", with the chips to pick from.

**Live mode** uses `react.chat` with the `think` and `seed` settings `ask.py` uses, and the real `retrieval.Retriever`,
so it runs on `py -3.14` (x64), as `ask.py` does. Startup checks that Ollama is reachable and stops with a clear error
if it isn't. Each live conversation's transcript goes to `data/experiments/web/` in the `ask.py` session format.

## 5. Going public later

- **Data terms.** The user has permission from all three data sources to use the data publicly ([`DATA.md`](../DATA.md)).
- **Before deploying:** rate limits per IP; auth or an invite token in front of live mode; the GPU's capacity sets the
  queue's size, and a waiting time shown with the position; logs without the questions' text, or with consent.
- **Already built in from the start:** no secrets in the browser, the 127.0.0.1 binding, size limits, sanitized
  rendering, and same-origin only (no CORS). The tools are already read-only with a 30 s limit.

## 6. Dependencies

`fastapi`, `uvicorn` and `httpx` (for FastAPI's test client), added to `requirements.txt` and installed on both
Pythons. The markdown renderer (`marked`) and the sanitizer (`DOMPurify`) are vendored into `app/static/vendor/` at a
pinned version.

## 7. Testing

- **Unit tests** (`python -m unittest`): `events.py` on saved trace shapes (each note, suggestions with one and with
  two names, a template step, a result too large to show); the replay index skipping held-out records; the worker
  keeping order and positions with two conversations; the SSE route through the test client on a replayed question.
- **In the browser:** replay mode in the browser pane on a template question, a `run_sql` question, the suggestions
  session, a session whose follow-up builds on the first answer, and a recording with a check note. Also checked at
  phone width.
- **Live mode** once the GPU is free, on one question.

## 8. Steps (one commit each, pushed, with a report)

1. `events.py` and `replay.py`, with their tests: no server yet.
2. The worker, the routes and SSE, with their tests.
3. The page: question box, progress, answer, notes, suggestions.
4. "How I got this", and the figures slot.
5. The live switch, checked on one question when the GPU is free.

## Open decisions

1. Replay through the real loop (recommended), or replaying the stored events only.
2. A suggestion button sends the candidate's name (recommended), or "the first one" as the tested follow-up did.
3. No build step for the frontend (recommended), or React with Vite.
4. Installing `fastapi`, `uvicorn` and `httpx` on both Pythons.

Decided (2026-11-17): replay through the real loop; suggestion buttons send the ordinal; no build step; the packages
installed on both Pythons. Live mode is never used while an eval run is going.
