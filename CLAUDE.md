# esports-analyst-agent

## Project
An agentic text-to-SQL data analyst for esports data, currently focused on Brawlhalla. Users ask questions in plain English; the agent explores the database schema, writes and runs SQL, verifies the results, and explains the answer with a chart when useful. This is a capstone for a CMU agentic AI course.

## Data source
The official Brawlhalla Esports Stats API (docs: https://www.docs.brawltools.com/v2/pages/). This is NOT the in-game Brawlhalla API at api.brawlhalla.com; do not use that one. The start.gg and Challengermode APIs add former player names, prize payouts and bracket details, and Esports Earnings fills gaps in career earnings.

## Data terms
The Stats API, start.gg and Challengermode have given permission to use their data publicly (2026-11-17, [`DATA.md`](DATA.md)). That isn't permission to redistribute it here: API responses and the built database (`data/`) must never be committed. The repo stays private, so the hand-made files in `curation/` and the event list in the schema proposal's appendix may be committed, even though they contain event names and IDs from the API.

## Planned stack
Python, LangGraph, SQLite or Postgres, a local open-source model via Ollama as the primary model, Streamlit for the demo. The fetcher is Python too: a small HTTP client, not the Node SDK (`@bmg-esports/sdk`), which hides status codes, has a fixed 5-second timeout and never retries. `ingest/survey_api.mjs` stays only as an exploration tool.

## Project status (2026-11-17)
**Phase 1 of the schema proposal's implementation plan (§9) is done and merged into `main`** (2026-10-07).
- The builder makes the database from the fetched cache and `curation/`, as [`docs/build-plan.md`](docs/build-plan.md) describes.
- The frozen snapshot `eval-v1` (build `20261007T230135Z`, commit 51e98be) is the evaluation's database.

**The agent phase has started** (2026-10-10), on branch `claude/agent`. First, a model comparison: one-prompt text-to-SQL on the target questions, logged in [`docs/experiments.md`](docs/experiments.md).
- qwen3:8b with thinking and qwen3:4b each got 8 of 10, qwen3:8b in about two-thirds of the time. qwen3:8b without thinking got 2 of 10.
- Most failures were name resolution: the model matched display names instead of using the aliases.
- A failure analysis with reruns ([`docs/model-comparison-failures.md`](docs/model-comparison-failures.md)) found that qwen3:8b's misses weren't only name resolution, and set three requirements for the agent, listed in the log:
  - name lookup as a separate tool;
  - schema documentation on reading the views that store each pairing more than once, and a result checker that flags suspicious results;
  - player IDs looked up before head-to-head queries.
- Decided (2026-10-10), provisionally: qwen3:8b with thinking on, for development. Once the agent loop and the verified evaluation set exist, the comparison is rerun inside the agent with qwen3:4b, qwen3:8b and qwen3:14b.
- A minimal ReAct prototype (2026-10-18, `agent/`): qwen3:8b with thinking, two tools (`resolve_player`, `run_sql`), at most 8 steps. On questions 4, 6 and 8, one run each (in the log):
  - every name resolved and every query was right (3 of 3 by the comparison's check, against the baseline's 1 of 3);
  - but only question 4's answer was: question 6 was answered from the 20 rows shown of 46, and question 8 sent an ID to `resolve_player`, which fuzzy-matched it to another player.
- Decided (2026-10-19): the log's three proposals and answer guidance, implemented and unit-tested but not yet run, since the Ollama server was unreachable:
  - `resolve_player` takes names only;
  - a cut-off result is marked incomplete;
  - an answer naming a player no tool returned goes back once;
  - the prompt says how to write the answer.

- The fixed prototype on questions 4, 6 and 8 with seeds 0–5 (2026-10-19, in the log): answers right in 5 of 6 (question 4), 0 of 6 (question 6) and 3 of 6 (question 8); queries right in 16 of 18.
  - Refusing IDs worked, and the answer check caught two invented names with no false alarms.
  - The incomplete mark didn't work: question 6 still answers from the 20 rows shown.
  - The log proposes the next fixes for the user to decide.
- Decided (2026-10-19), the result-size fixes:
  - a token budget of about 4,000 per result instead of 20 rows;
  - no rows for a result over it, only its row count and columns;
  - an answer right after such a result goes back;
  - the prompt's rule is to reduce data in SQL always, never counting, ranking or comparing rows by reading them.

  Not built yet: when a user asks for a long list, the answer summarizes it, and the full table goes to the user directly, not through the model.
- The result-size fixes on questions 4, 6 and 8 with seeds 0–5 (2026-10-19, in the log): answers right in 5 of 6, 0 of 6 and 4 of 6.
  - The cut-off is gone: question 6 got all 46 rows in four runs.
  - But no run aggregated in SQL: the answers read the rows and got the partners' counts and results wrong. Twice more, a `format = '2v2'` filter gave "never played 2v2".
  - The log proposes the next steps.
- Checkpoint 2's lookup changes (2026-10-23, from the checkpoint's feedback): match scores in `resolve_player`, suggestions to the user for a name matched only loosely, and a diagnosis for an empty result. On questions 4, 6 and 8 and the misspelling questions q21 and q22, with seeds 0–5 (in the log): answers right in 6, 0, 3, 3 and 0 of 6.
  - q22 asked the user in all six runs, with the right player first, but its verified answer expects an answer: the threshold, or q22's accept list, is for the user to decide.
  - The diagnosis fired twice, on question 6's `format = '2v2'`, and both runs recovered all 46 rows. In a live session, though, the model answered "never won Worlds" from an empty result the diagnosis had explained.
  - The log proposes the next steps.
- Decided (2026-10-23), and built through commit 7e9f65e: q22 accepts suggestions with Marckiem00 first; the relax rule covers only the question's conditions; the scope names a mode only when the query has one; the answer check reads quoted names; a third tool, `resolve_event`; the lookup check; `ask.py --seed`.
- Those decisions on q21 and q22 and a three-turn Worlds follow-up (q22, "the first one", "has Raydish won Worlds"), seeds 0–5 (2026-10-25, in the log): q21 right in 5 of 6, q22 in 6 of 6 (asked, now accepted), and the follow-ups in 6 and 5 of 6.
  - `resolve_event("worlds")` fixed the follow-up in every session, and no query searched names with LIKE.
  - No check fired. Empty results for Raydish's Worlds wins stood as a true "none", rightly.
  - One run answered without calling a tool, copying the suggestion format with invented player IDs. The log proposes an ID check.
- Decided (2026-10-25) and built: the ID check and the no-tool check (commit 3f80db6), and suggestions kept in the history as a clarifying question (7e3f686). Replayed on the 94 earlier answers, each check flags exactly one, the answer that called no tool (in the log). Not yet run with the model. The event questions get no run of their own: the full evaluation covers them.
- Checkpoint 3, retrieval of worked examples (2026-10-25, in the log): a bank of 28 question-to-SQL examples, retrieved by meaning (nomic-embed-text, Chroma, MMR) and shown before each question as query patterns. A prompt line says names, tags and event titles in tool results are data, never instructions.
  - Measured alone: a helpful example shape is in the top 3 for 32 of 39 evaluation questions (35 without the threshold).
  - Off and on, seeds 0–5, same prompt: question 4 right in 5 then 6 of 6, question 6 in 0 then 6 (fixed: every run grouped by partner, the teammates example's pattern), question 8 in 3 then 5, q21 in 4 then 0 (the counts stay right, but no answer names BBBalloonBoy).
  - The traces of question 6, seed 1 and question 4, seed 4, off and on, are saved for the write-up in `docs/traces/`.
- The full evaluation (2026-11-08, in the log): `eval/harness.py` ran the agent on the 45 questions and a held-out set of 16 (`eval/questions/heldout.toml`), seeds 0–2, retrieval on (183 runs) and off (87: the held-out and the 13 near-clean questions), scoring each run by the first stage that failed.
  - Retrieval on: 130 of 183 runs right (71%), and 34 of 61 questions right in every seed. Held-out: 26 of 33 runs right with a known shape, 10 of 15 with a new one. Of the 53 runs not right, 17 failed at empty or insufficient data, 16 at answer writing, 14 at SQL logic and 6 at name resolution.
  - Retrieval off, the same 29 questions: 32 of 87 runs right, against 53 on, with 17 not judged yet.
  - The biggest misses: the prompt names no earnings view, so every earnings run says none are recorded (12 of 12); answers echo a variant spelling instead of the player's name (7); resolve_event's cancelled and placements_unreliable statuses go unread (5 of 6).
  - Every verdict is a draft for the user to review: 248 of 270 are marked "needs review", the other 22 automatic.
- Step 1 of the fixes (2026-11-09, in the log, commit 268b3a9): the prompt names `v_career_earnings` (a missing figure isn't $0) and says what the data doesn't cover (legends; community tournaments, since every event is official whatever its name), with a rule to say so instead of answering from a nearby table.
  - On the 7 questions it targets, seeds 0–2: 3 of 21 runs right before, 16 of 21 after. The 3 controls (q02, q26, q37) went from 7 of 9 to 9 of 9.
  - Left: q05 doesn't name Boomie as missing, as its verified answer asks; q45 seed 1 counted Impala's missing figure as $0.
  - The harness now counts q05, q09, q33, q35, q36 and q45 as tuned, in runs from 2026-11-09 on.
- Step 2 of the fixes (2026-11-09, in the log): a shared name resolves to the first player alone when they have at least 5 times the next one's official results; each candidate has a display ("Zivai (formerly Godly)"); names are corrected in code (the question's spelling, a wrong name next to a player ID), every swap traced; a reply about the answer keeps the answer sent back; the harness counts an ID as a name only if a tool returned it.
  - On its 4 targets, seeds 0–2: 3 of 12 runs right before, 8 of 12 after (q15 and q21 right in every seed). The 8 regression checks went from 23 of 24 to 24 of 24, and the 3 controls from 9 of 9 to 8 of 9 (q17 seed 0 misspelled BBBalloonBoy).
  - The code corrected 10 names in 4 of 45 runs; on the same questions in 2026-11-08, 23 of 45 answers had used the question's spelling.
  - Left: q20 (no opponent column), and q44 seed 2 (`format = '1v1'` in a COUNT, which no diagnosis catches). q15, q20 and q44 now count as tuned.
- The template tools (2026-11-17, in the log; commits c0224ec to abb5109), so the model writes less SQL: two views (`v_sets_1v1`, `v_event_series`) and four templates (`event_results`, `player_results`, `head_to_head`, `rank_players`), with a prompt section on choosing a tool and the worked examples showing calls.
  - On the 45 existing questions, seeds 0–2, 135 runs each: the automatic stages passed in 124 runs before and 130 after (the 4 targets, q20, q30, q31 and q41, 7 → 12 of 12). `run_sql` calls per run went from 0.95 to 0.28, and to 0 on the 26 questions a template takes over. Model time per run went from 25.0 s to 14.3 s.
  - Hand drafts: the targets 1 → 9 of 12 runs right (q20's 3 partly, for a set time the answers invent); seed 0 of the 26 regression checks 19 → 24 right.
  - No question lost 2 or more runs. Three lost one each: q27 seed 2 (`head_to_head` called with invented player IDs), q44 seed 2 (`head_to_head` for a placements question) and q42 seed 2. By the plan's template rule `head_to_head` would come out.
  - The before run used Ollama 0.40.15 and the after run 0.40.16. q30, q31 and q41 now count as tuned.
  - Decided (2026-11-17): `head_to_head` stays. Then three fixes: a tool call on a player_id no tool returned is refused (0a32b79), ex29 doesn't select `start_time` (e59f39d), and `head_to_head`'s description says it counts sets, not placements (f05ae4a).
- **The held-out set's final measurement** (2026-11-17, in the log), at f05ae4a, run `20261117-heldout`, seeds 0–2: 32 of 48 runs right, against 36 on 2026-11-08 (which predates steps 1 and 2 and the templates), and 10 of 16 questions right in every seed, against 9.
  - Better: h04's record (no more timeouts), teams and ties kept whole (h05, h07, h11). Worse: h15, 3 of 3 wrong (`rank_players` can't leave out winners); h16 and h03, 6 partly (`player_results` with `top=1` read as the whole record); h04's set lists misdescribed. h13 is unchanged.
  - **The held-out set is now spent for tuning**: its questions, checks and traces were read. Nothing in the agent changed because of it, and measuring a change made for it needs new held-out questions.

**The evaluation set is verified** (2026-10-19): 45 questions in `eval/questions/questions.toml`, with candidate answers computed from eval-v1 (drafted 2026-10-10).
- The user's verdicts: 42 yes, some with a note, and 3 partly (q05, q31, q44), each with what's right.
- q38 (the top 5 by official 1v1 wins): Boomie's 12 official 1v1 wins (tied 8th) keep him out of the top 5.
- From the review: q08 no longer accepts "no minimum" (Snowy!!), and q24 accepts the 2026 reading of "msi" only if the answer says "msi" is ambiguous.
- The answers hold for eval-v1 only. A merge decided before eval-v2 can change them, as Boomie's proposal (in the merge review) would change q37 and q39.

Planning and write-ups:
- Stats API survey (`ingest/survey_api.mjs`) → `docs/api-survey.md`: what the API returns, its bugs and coverage gaps, and which target questions it can answer.
- start.gg and Challengermode survey (`ingest/survey_platforms.py`, clients in `ingest/platform_clients.py`) → `docs/platform-api-survey.md`: brackets, full standings and prize data those platforms add.
- Schema proposal → `docs/schema-proposal.md`: the design to build from.
  - Contents: the SQLite schema, views applying the rules below, crawl and coverage plans, earnings design, the target questions, a three-phase implementation plan, and the list of official events.
  - Its status note lists the decisions of 2026-10-04 and 2026-10-05. §1 has what the fetch found that the builder must handle, and §3 the crawl stages and their results.
- Build plan → [`docs/build-plan.md`](docs/build-plan.md): how the builder makes the database.
  - Contents: what the cache showed, the build order, how curation files are applied, the checks and their gates, when Phase 1 is done, support for the scheduled updater, and the order of work with each step's status.
  - Its decisions of 2026-10-05 are newer than the schema proposal where they differ.
- Experiment log → [`docs/experiments.md`](docs/experiments.md): one entry per experiment, with its setup, results and what it decided.
- Agent walkthrough → [`docs/agent-walkthrough.md`](docs/agent-walkthrough.md): how the prototype works end to end, for a learner. It covers the entry point, the system prompt, the ReAct loop, the tools, the guardrails, question 8 traced step by step, and the known limitations, with line references to commit 2889492. Sections 8–11 (2026-10-26) cover the later guardrails, retrieval of worked examples, question 6 traced with retrieval on, and what retrieval improved and broke, with line references to commit fc41b9b.

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
  - `views.sql` holds the 16 views the agent queries, `v_event_coverage` included. eval-v1 was frozen before `v_sets_1v1` and `v_event_series` (2026-11-10), and gets them as temporary views in each of the agent's connections (`tools.connect`):
    - each documents its counting rules inside its definition, which SQLite keeps in `sqlite_master`;
    - the build compiles every view, then runs `ANALYZE`, without which some views take minutes;
    - the head-to-head views are fast only with a literal player ID: 0.1 s, against about 50 s when the ID comes from a lookup inside the same query (2026-10-10), so look up IDs first;
  - `checks.py` holds the checks, their gates and the verdict;
  - `report.py` writes each build's report (`data/reports/<build>/report.md`) and the review list;
  - `sources.py` lists the query versions the builder reads;
  - `problems.py` defines `BuildStop` (and `CurationError`), which end a build with a list of problems;
  - `schema.sql` holds the tables;
  - `names.py` holds the name normalization shared with `merge_candidates.py`;
  - `target_questions.py` is the target questions' regression check (`python ingest/target_questions.py`, optionally `--build PATH`). Its expected answers come from our own data, so it isn't the evaluation gold set. New results change some answers, and the expected ones are then updated on purpose.

Evaluation (`eval/`):
- `model_comparison.py` runs the model comparison: one prompt and one query per target question, on eval-v1. Results go to `eval/results/` and full replies to `data/experiments/`. It's exploratory, since the expected answers come from our own data.
- `questions/questions.toml` is the evaluation set (v1, verified 2026-10-19): 45 questions, each with its category, what it tests, the players and events its names mean, a candidate answer, the SQL behind it, and `verified`, which the user fills in (`yes`, `yes: ...` with a note, or `no: ...` / `partly: ...` with what's right).
  - Categories: player records, event results, head-to-heads, multi-step (comparisons, firsts, mosts, rankings), partial (what the data shows, then what's missing) and unanswerable (what isn't available, and why).
  - Where a reasonable definition changes the answer (14 questions), `accept` lists each acceptable answer with the assumption that produces it; an answer gets credit only if it states its assumption.
  - q22 also accepts suggestions with Marckiem00 first (decided 2026-10-23): "markiemoo" matches only by a similar spelling, which the agent doesn't guess. Near-misses of curated nicknames stay below the confident threshold.
  - `tied_to_eval_v1` marks the 7 answers that Phase 2 (or, for legends, Phase 3) will change.
  - It covers the target questions, the known events, names written casually (nicknames, former names, case, misspellings, team tags), event aliases and terms, four paraphrase pairs, and questions the data can't answer.
- `review_questions.py` writes `questions/review.md`, the page to review the set from: it runs every question's queries on eval-v1 and shows their results next to each answer (`python eval/review_questions.py`). Edit `questions.toml`, never `review.md`. It doesn't run the agent; `harness.py` does.
- `questions/heldout.toml` is the held-out set (verified 2026-11-08): 16 questions in the same format, never to go into the example bank or tune the agent. `tests/test_harness.py` checks the bank for its questions, players and events. It's spent since 2026-11-17: its final measurement was read, so it no longer measures questions the agent hasn't seen.
- `harness.py` runs the agent on both sets and scores it (2026-11-08):
  - `py -3.14 eval/harness.py run --all --seeds 0 1 2` (or `--ids`, `--near-clean`, `--examples off`) appends each trace to `data/experiments/<run>/`, so a run resumes;
  - `score RUN [RUN ...]` scores stages 1 and 2 offline and writes `eval/results/<run>-scores.json` and `<run>-judgments.toml`, where stages 3 and 4 are drafted by hand ("needs review") and kept across rescoring;
  - a template call is scored as a query (2026-11-17): stage 1 reads the IDs in the SQL it ran, which the trace keeps, and stage 2 reads its tables;
  - `report RUN [RUN ...]` prints the tables by group, held-out shape, query shape, category and failing stage, with raw counts next to every rate, then a tool-use table (each tool's runs and calls, steps and model seconds per run);
  - `failures RUN` writes a page to review from, `data/experiments/<run>/failures.md` (git-ignored, next to the traces it reads): every run not right, grouped by question, with its judgment, full answer and the SQL it executed. It reads the run's files and changes none of them;
  - `result_checks.py` holds stage 2's check per question of the evaluation set; `python eval/result_checks.py` verifies each on its question's reference queries. The held-out set's checks are in `heldout_checks.py` (moved 2026-11-10), which holds that set's answers: don't open it, `heldout.toml` or a held-out trace in a session that must leave the held-out set unread.

Agent (`agent/`, a prototype):
- `ask.py` is for asking the agent yourself: `py -3.14 agent/ask.py "question"` prints the answer, `--trace` also prints each step (its thinking in short, tool calls, observations), `--seed N` picks the sampling seed (default 0), and with no question it starts a session. In a session, follow-ups build on earlier answers, and "exit" quits. Transcripts go to `data/experiments/sessions/`.
- `react.py` is the ReAct loop: `python agent/react.py "question"`, `--target N` for target questions or `--eval ID` for evaluation set questions, with `--seed` repeatable.
  - A name from the question that `resolve_player` matches only below 0.9 (`CONFIDENT`) ends the turn: the user gets the top three candidates as suggestions instead of a guess (outcome "suggestions").
    - The history keeps them as the question the agent asked the user, with the candidates' player IDs, not as an answer (decided 2026-10-25): kept as the suggestions themselves, one later question copied them as its own answer.
  - `Conversation` keeps the previous question in full (tool calls and observations) and older ones as question and answer.
  - Traces go to `data/experiments/<run>/`, and a run of target questions also writes a summary to `eval/results/`.
  - The answer check: an answer naming a player, or citing a player ID, that no tool returned goes back to the model once. It looks only at words shaped like gamer tags and at bold or quoted text (quoted since 2026-10-23), since most ordinary words are some player's display name. IDs count after an ID word (player_id 12345, partner ID 5) or alone in bold or parentheses with five digits or more (since 2026-10-25).
  - The player check (decided 2026-11-17): a tool call on a player_id that no tool returned in the conversation, and the question doesn't give, doesn't run. A `run_sql` query filtering on one (`player_id`, `partner_id`, `opponent_id`, `winner_id`, `loser_id`, ...) or a template's player argument gets an error pointing to `resolve_player` instead. In the templates' after run, q27 seed 2 passed `head_to_head` two invented IDs that were real players.
  - The no-tool check (decided 2026-10-25): an answer stating facts (players, player IDs, numbers other than formats such as 1v1) in a question that called no tool goes back once. The model may reply the same if the facts come from earlier tool results.
  - The lookup check (decided 2026-10-23): an answer right after an empty result whose diagnosis finds no row with a text value the query filters on (a name, an event, a format) goes back once, as a likely lookup mistake. Any other empty result can be a true "none".
  - The names correction (decided 2026-11-09), done in code before the checks, not sent back:
    - the question's spelling of a player `resolve_player` decided becomes their display at its first mention and their name after, unless it's quoted or explains the name just before it; a case variant or a dropped team tag isn't a misspelling;
    - a name just before a player ID that isn't that ID's name becomes the data's name for it ("**Lucky** (player_id 147982)" becomes Zivai);
    - every swap is in the trace (`name_swaps`), and the harness counts them per run, to measure how often the model gets names wrong.
  - A reply to a check that talks about the answer instead of giving one ("The answer is correct"), stating no new number, keeps the answer sent back as final (2026-11-09).
- `retrieval.py` retrieves worked examples by meaning (Checkpoint 3, 2026-10-25): `agent/examples/examples.toml` holds 30 questions of common shapes, each with the query that answers it and why it's shaped that way.
  - The 19 that a template answers also have the call (`call`, with `call_note`), which the model is shown instead of the SQL (2026-11-17). The SQL stays as the reference the call is checked against.
  - None names a player or uses an event from the evaluation set or the target questions. `python agent/retrieval.py check` runs every query and call on eval-v1, and requires each call's result to hold its query's rows.
  - Only the questions are embedded, with nomic-embed-text through Ollama (prefix `clustering: `), in a Chroma collection in `data/rag/chroma` (git-ignored), rebuilt when the bank or the embedding changes.
  - For each user question: the 10 most similar examples, those at 0.70 or more, then MMR (weight 0.7) keeps 3. They go before the question with a note that they show query patterns, not facts about players. The history keeps the bare question, and the answer check doesn't count what examples show.
  - Chroma's index library has no build for Windows ARM64's Python, so the agent runs with the x64 Python 3.14 under emulation (`py -3.14 agent/react.py ...`). `--examples off` (react.py, ask.py) runs without it, on any Python.
  - `py -3.14 agent/retrieval.py measure` measures retrieval alone against `eval/questions/shapes.toml` (hand labels of the shapes that would help each evaluation question): with the agent's settings, a helpful shape is in the top 3 for 32 of 39 questions (2026-10-25, in the log).
- `tools.py` holds the tools:
  - `resolve_player` matches a name against the aliases in tiers (normalized, character swaps undone, prefix, similar spelling), ranks candidates by official results, and gives a status (confident, ambiguous, not found). It refuses IDs and names of digits only.
    - Each candidate has a match score: its tier's base times its closeness (nickname 1.0, exact 0.98, swap 0.92, prefix and similar spelling 0.85 times closeness).
    - Scores rank matches and aren't calibrated probabilities. They and the 0.9 threshold are to be tuned on the evaluation set's misspelling questions;
    - A name several players share exactly resolves to the first alone, as confident, when it has at least 5 times the next one's official results (`CLEAR_CUT`, 2026-11-09). On the existing set's shared names the first was always the player meant, 14.8 to 48 times ahead;
    - Each candidate has a display to name them by: the current name, with the former name the match went through, without its team tag ("Zivai (formerly Godly)"). A confident note says to call them by it;
  - `resolve_event` (decided 2026-10-23) finds the official events an event name means, so the model doesn't search event names with LIKE.
    - A mode word narrows the events. The rest matches, in tiers: a curated alias ('bcx 2022', score 1.0), a series of yearly aliases ('worlds', 0.95), every word with years and curated terms ('winters 2023 na', 0.9; qualifiers only when asked for), or some of the words (0.85 times the share).
    - The statuses are as for players. It's ambiguous when several tournaments match, or only some words. Words that find exactly a series' events count as that series ('world championships' is 'worlds').
    - The result has a sql condition on `event_id`: the IDs, a subquery on `v_event_series` for a whole series, or one on the aliases for another big alias set.
    - It takes the name as `name`, or as `event`, the templates' key (2026-11-17).
    - On eval-v1, 14 of the evaluation set's 15 event phrases resolve to exactly their events. 'ceo dreamland 2020' is ambiguous, with the cancelled event first;
  - `run_sql` runs one read-only query on eval-v1, stopped after 30 s. It returns every row if the result fits in about 4,000 tokens (estimated: digits and JSON punctuation a token each, other text four characters a token).
    - A bigger result comes back with its row count and columns but no rows.
    - `react.py` sends back an answer that comes right after one, until the model queries again.
    - A result with no rows comes back with a diagnosis (`diagnose.py`): which top-level condition emptied it (each is removed in turn and the rows counted), and whether the value it filters on occurs in that column (in the column's own table when the query names it). The prompt says to fix a condition that was the model's own mistake, and to say so only when relaxing a condition the question set (decided 2026-10-23).
- `templates.py` holds the four template tools (2026-11-17), each a tested query the model calls with a few arguments. Its registry (`TEMPLATES`) is what `react.py` offers the model and dispatches to, and the prompt's "Choosing a tool" says which question each answers:
  - `event_results(event, top)`: an event's winners or top N, a team on one row and ties whole, with each event's date, mode, status (a cancelled event is not held), bracket link, and `event_id` when the name means 12 events or fewer;
  - `player_results(player_id, top, mode, year, event)`: one player's results counted by mode (top 1 for wins, 3 for medals, 8 for top 8s), the first and the latest, and the list;
  - `head_to_head(player_id, opponent_id)`: the first player's 1v1 record in sets, each set from `v_sets_1v1`, and their 2v2 meetings;
  - `rank_players(by, top, mode, year, event)`: players ranked by wins, medals or top 8s with `RANK()`, every tie included, with a column for a series' regional championships;
  - every template takes players as player_ids from `resolve_player` (a name is refused) and events by name, resolved inside as `resolve_event` does. A list over the token budget is left out with its count, and the SQL a template ran goes to the trace, not to the model.

Curation (`curation/`, committed):
- `player_aliases.csv`: nicknames, among them "bunny", "vem" and "halloween!" from the known events (2026-10-07).
- `player_merges.csv`: 3 merges decided by hand (Remmy, hardymj and karuzzi) and 670 accepted automatically (tier 1).
- `merge_rejections.csv`: empty so far.
- `merge_proposals.csv`: pairs found by hand that the merge tiers can't see, with their evidence, waiting for the user's decision. `merge_candidates.py` puts them first in the merge review. The build doesn't read them.
  - So far, one: Boomie's second start.gg account (31626 → 146606). It won the 2017 Brawl League Open Cup 2v2 March Finals (US) with ZEEKO, his usual partner.
  - It's high-impact: it changes q37 and q39, so it's decided with the other high-impact merges before eval-v2 (2026-10-19).
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
- It holds the pairs proposed by hand (`curation/merge_proposals.csv`, 1 so far), then 434 tier-2 and 1,753 tier-3 pairs, strongest first, for the user to review at their own pace.
- By impact (2026-10-07), under the curation policy below:
  - 64 pairs involve a top 8 or better: 16 in tier 2 and 48 in tier 3, 8 with official wins and 16 with medals;
  - 178 more involve a player ranked in their region's top 100;
  - the other 1,945 are low-impact.
- Decisions go in `curation/player_merges.csv` (merge) or `curation/merge_rejections.csv` (not one person). A proposal's row moves out of `merge_proposals.csv` when it's decided.
- The high-impact pairs are decided before eval-v2 is frozen, since a merge can change verified answers (decided 2026-10-19).
- To undo an automatic merge, move its row from the first file to the second.

The review list: **`data/review/review.csv`** (git-ignored), rewritten by every full build.
- It holds everything waiting for the user, most pressing first: curated rows skipped (marked `!!`), held-out events, unused check exceptions, possible phase splits, new events (without a row in `events.csv`: none since every event got one, 2026-10-06), automatic merges, and the merge candidates not yet decided.
- Each row has a key that stays the same from build to build, and says what settles it.

Decisions so far: the domain definitions below, plus these.
- Career earnings: the Stats API figure first. For players without one, the fallback is the Esports Earnings snapshot (source `esportsearnings_manual`, as of 2026-10-04), linked to players through `player_aliases`. Each figure is stored with its source and as-of date. The Esports Earnings API is blocked (its account login isn't working).
- Per-tournament prize money: start.gg's structured payouts; for Challengermode-era events, the prize split parsed from the tournament description, accepted automatically when it adds up to the stated total and otherwise reviewed by hand. Payouts are never estimated from a total prize pool.
- Missing isn't zero: when an event has no payout data, or a player has no career figure, answers say so rather than counting $0.
- API credentials, and the Ollama server's address (`OLLAMA_BASE_URL`), live only in `.env` (see `.env.example`).
- Models (2026-10-10): Ollama 0.40.2 runs on another machine, serving qwen3:4b and qwen3:8b.
  - qwen3:4b is Qwen3-4B-Thinking-2507, which always thinks: `think: false` doesn't turn thinking off, it only moves the reasoning into the reply.
  - qwen3:8b is the original hybrid Qwen3-8B, where thinking can be switched off.
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

Next step: **the user's call, after the held-out set's final measurement (2026-11-17)**. Its findings aren't acted on: the template outputs that answers misread (`player_results` under `top`, long set lists), `rank_players` taking a condition it can't express, and h13's Pro Series finals. A change for them would be tuned on the held-out set, so measuring it needs new held-out questions. The user's review of the drafted verdicts (`eval/results/202611*-judgments.toml`) is still pending.
- Still open from before the templates: step 3 of the fixes, `resolve_event` leading with a cancelled or unreliable status, for `run_sql` questions; step 4's answer-check wording (q03), its worked example for a set's two players being ex29 now; step 5, an answer verifier replayed on the recorded runs first; and a `format` filter holding a mode in a COUNT, which no diagnosis catches (q44 seed 2 in step 2; h09 and h11 with retrieval off).
- For the harness: draft the retrieval-off arm's 16 runs left (q14 seed 1 is automatic since the name fix) and read its 11 unread machine verdicts.
- Still open from the 2026-10-19 to 2026-10-25 entries: the retrieval threshold; the prompt lines on `v_team_results` (only 2v2) and integer division; current names, and the minimum number of matches; how to get question 6 aggregated (with retrieval on, all 3 runs did). Then the agent's design, explained before it's built. Before eval-v2 is frozen, the high-impact merges are decided, Boomie's proposal among them.
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
