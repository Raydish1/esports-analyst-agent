# Experiment log

One entry per experiment, newest first: what it asked, how it was set up, what it found, and what it decided. Results are in `eval/results/`. The models' full replies, thinking included, are in `data/experiments/` (git-ignored).

## 2026-11-22: the doubled-ending fix, replayed on every recorded run, and the freeze

**What it asked.** The user approved a fix for the bug the targeted run found, with a test and a replay on the
recorded runs. The names correction swapped the question's spelling of a player for their name wherever a non-word
character followed it, so a spelling that is the name's start matched inside the right name: "moni" in "Moni-" gave
"Moni--", and "dragon" in "Dragon!" gave "Dragon!!". After the fix the agent is frozen (the user's decision).

**Setup.** No model. Commit 5c6b769: a match where the answer already writes the player's name or display isn't
swapped. Every recorded run was read, held-out records skipped. Each draft of a turn with a swap of the question's
spelling went through the code before the fix (7f49596, from git) and after it. The turn's resolved players were
rebuilt as the loop builds them, from its confident `resolve_player` results and any choice from suggestions.

**Results.** Of 2,909 turns, 87 had a swap of the question's spelling, and 11 drafts change. Each is a doubled
ending, and each one's final answer held it:
- c13 turn 3, "Dragon!!" becomes "Dragon!": the final run's seeds 0-2, `20261121-conversations`' seeds 0-2, and seed
  0 of the three model comparison runs (qwen3:8b, 14b and 30b);
- c22 turn 2, "Moni--" becomes "Moni-": the targeted run's seeds 1 and 2.

The other 76 turns keep their swaps, so no misspelling stops being corrected. The 546 unit tests pass.

**What it decided.** The fix stands. From here the agent is frozen: no more prompt or check changes, only fixes for
bugs that break a live answer (the user's decision, 2026-11-22). The final entry's section "After the final
measurement" lists every change since, for the report.

## 2026-11-22: the targeted run of the additions after the final measurement

**What it asked.** Do the additions after the final measurement hold up with the model? They are the run_sql rule and
the no-tool check's messages (be0b938), the team templates (8f3409a, 477513d), and the two fixes (8ba7e18, 7f49596). The
run covers the items where the final run's no-tool check fired and the live session's 2v2 turns, as the user asked.

**Setup.** qwen3:30b at 7f49596, seeds 0-2, retrieval on, in the run worktree, approved by the user. Four runs, one
after another: `20261122-targeted-questions` (q09, q35, q36), `-conversations` (c1, c5, c8, c10, c12, c15, c19),
`-audit` (a44, a45, a49) and `-teams` (c20-c24, `eval/questions/teams.toml`). It took 47.5 minutes, with qwen3:30b at
21 GB, 100% GPU and a context of 32768 in all 46 samples. The final run's same items were rescored in memory with
today's scorer, which counts the prompt's facts since 7f49596; its files are unchanged. The question verdicts are
drafted by hand ("needs review").

**Results.**

| Items | Final run, rescored | Targeted run |
|---|---|---|
| q09, q35, q36, by hand | 9 of 9 right | 9 of 9 right |
| 7 conversations, 69 turns passing every check | 53 | 51 |
| 3 audit items, 12 turns passing every check | 11 | 10 |
| c20-c24, 27 turns | (new) | 21 pass every check; by hand 19 right, 5 partly, 3 wrong |
| Turns where the no-tool check fired, of the 90 above | 31 | 27 |
| Answers that gave up ("I couldn't look this up", "I couldn't confirm this") | 2 | 0 |
| After a no-tool send-back, the model queried (a template or run_sql) | 7 of 21 | 6 of 16 |

The give-ups:
- c10 seed 1 turn 2 now stands, through the recheck fix made after the final run (40996f9), not today's changes.
- c19 seed 0 turn 3 ("what are the three sets that volst vs'd raydish"): the model now looked both players up and
  called `head_to_head` itself, and listed the three sets. One run can't tell the new rule from the run's variation.

The new rule doesn't show in the counts: after a send-back the model queried about as often as before, and run_sql
was called once in the 90 turns, against twice. Most of these items are questions no query answers (legends,
community tournaments, prize money per event), where looking the name up is all there is to do.

The turns that changed are spread both ways, as a changed prompt changes every turn's sampling: 4 now pass and 6 now
fail. Among the 6: c12 turn 1, seeds 1 and 2, give the 1v1 record (17-17) without the 2v2 meetings (11-11). c19
seed 2 turn 1 sets itself a 5-set minimum, a known limitation in the final entry. c8 seed 2 turns 3 and 5 give each
player's 2v2 wins in place of the pair's events together. In the audit, a45 seed 1 answered that there's no prize
money per event without looking up Zivai.

The team templates, where the model picked them:
- `team_head_to_head` in all 9 turns that name two teams (c21 turn 2, c22 turn 2, c23), each record right: 0-3
  against Pink | Zen and hideawaybh, 1-0 (3-2) against Moni- and animefan1266, 5-0 against Marckiem00 and
  futurebubbles366. c23 writes the teams without an "and", which the scope check doesn't see, and still got it.
- "yes they did", after the 3-2, confirmed it in all 3 seeds (c22 turn 3). With nothing before it (c24), it asked
  what the user meant in all 3, where the live answer gave up.
- c20 ("who have raydish and megd versed the most in 2v2"): seed 2 ranked the duo's opposing teams (`rank_pairs`
  with a partner) in both turns. Seeds 0 and 1 ranked each player's own opponents in turn 1, as live. Seed 0's turn 2
  went to run_sql, and seed 1's named one of the three teams tied at 5 sets.
- c22 turn 1 ("show a 2v2 graphic"): the top 8 in seed 0, only the bracket link in seeds 1 and 2, as live.

Found in the run, a bug: the names correction writes the question's spelling over the start of the right name when it
is that name's start. "moni" became "Moni--" in c22 seeds 1 and 2 turn 2, and in the final run "dragon" became
"Dragon!!" in c13 turn 3 in all 3 seeds. That's 5 of the 13 name swaps in these runs. Not fixed: it waits for the
user's go-ahead.

**What it decided.** Nothing in the agent changed. The additions stand. The doubled-ending fix is the user's to
approve.

## 2026-11-22: two fixes after the final measurement, replayed on the final run

**What it asked.** The user approved two fixes, one commit each, and asked for the final run to be replayed to show
what each changes:
- the tool-name spacing bug: `claim_check.without_tool_talk` cut a tool's name out of an answer with the spaces on
  both sides, so the words around it fused ("confirmed by thewith top=1");
- the prompt's own facts as evidence for the number check: the data's first year (2017) and its newest results' date
  (2026-09-27). This was the question open since 2026-11-18, and it's the known limitation of q34 in the final entry.

**Setup.** No model. Commits 8ba7e18 (spacing) and 7f49596 (facts). Each replay reads the final run's recorded traces:
the 45 questions, the 19 conversations and the audit set, seeds 0-2, 441 turns. The spacing replay runs every draft
holding tool talk through the old and the new removal, and finds the old text in the final answers. The facts replay
takes every number the number check or the no-tool check flagged, and asks whether the two facts now support it. The
live give-up of 2026-11-22 (20261122T043945Z-002 turn 1) is replayed beside them.

**Results.**

| Fix | Replay | What changes |
|---|---|---|
| A space where a tool's name is cut out (8ba7e18) | 40 drafts with tool talk | 5 final answers, each by a space: c1 seed 0 turn 4 ("by theresult"), c8 seed 0 turn 4 ("bywith"), a49 seeds 0 and 2 turn 2 ("by thewith"), a51 seed 0 turn 1 ("biggestare") |
| The prompt's facts as evidence (7f49596) | 69 check records with flagged numbers | 16 no longer fire, and 2 fire for "$0" only (q05 seed 0, a43 seed 0) |

The 16 records the facts settle:
- q34 ("Who won the 2016 Brawlhalla World Championship?"), seeds 0-2, 6 records. Seed 0's final answer was "I
  couldn't confirm this from the data, so I won't guess.", and its draft, which says the data runs from 2017 on, now
  stands. Seed 1 keeps "Official results begin in 2017."
- One send-back each of "since 2017", "from 2017" or "2026-09-27" in q37 seed 2, q42 seed 2, c13 seed 1 turn 1, a12
  seed 2, a14 seeds 0-2, a31 seeds 0-2 and a41 seed 1.
- The live give-up: the reply asking for a question "from 2017 onward" now stands, instead of "I couldn't look this
  up in the data, so I won't guess."

What the fixes leave:
- With its spaces kept, a clause such as "as confirmed by the with top=1" still reads badly once the name is out.
- a51's draft wrote "biggest `upsets` are", and the cut takes the word itself, since `upsets` is also a template's
  name.
- The number check reads where a number came from, not what it means: q34 seed 1's draft calls Worlds 2017 "the
  earliest recorded event", and that now passes.

The facts come from the snapshot, one query, `react.coverage`, which also formats the prompt, so the two can't
drift. The conversation scorer's grounded check counts them as the agent does. The query reads every result, about 5
s on eval-v1, and it's now read once per snapshot: the newest date's query had run for every question since round
seven.

**What it decided.** Both fixes stand. The targeted run started at 7f49596. The Sonnet experiment is skipped for now,
with its backend in place (the user's decision).

## 2026-11-22: run_sql when no template fits, and a backend for a Sonnet experiment, built offline

**What it asked.** Two requests of the user's, after the final measurement, both offline first:
- When no template fits, the agent queries the views with run_sql, instead of answering without a lookup or giving
  up. Then a small targeted run, by id, on the 2v2 questions from the user's live session and the questions where the
  no-tool check fired, with the team templates.
- A Sonnet experiment for the report, built as a second model backend on the Anthropic API: seed 0 of the 45
  questions in two arms, (A) everything as now and (B) run_sql and the views only, no templates. The tokens
  estimated first.

**Setup.** No model and no API call. Commits be0b938 to 041b38c. The 542 unit tests pass.

**Results.**

| Change | Checked on | Result |
|---|---|---|
| The prompt's rule: if no template fits, query the views with run_sql; every question about the results gets a lookup | unit tests | In "Choosing a tool". The no-tool check's two send-backs and the note after the loop's own lookups say the same, in one phrase (`LOOK_UP`), not only to look the names up |
| `eval/questions/teams.toml`, c20-c24: the live session's 2v2 turns (20261122T043945Z-001 turns 2-7, -002 turns 1-2), 5 conversations and 9 turns | eval-v1, `teams-review.md` | Every row pattern holds on its reference queries. `v_head_to_head_2v2` agrees with `team_head_to_head` and `rank_pairs` on every count |
| The templates switch, `react.Tools(templates=False)` | unit tests | Arm B offers resolve_player, resolve_event and run_sql. Its prompt names none of the 11 templates, its examples show their SQL, and its messages say run_sql. Arm A's prompt, tools, examples and messages are unchanged |
| The Anthropic backend, `agent/anthropic_chat.py` | a fake client | In a three-step question, each request begins with the request before it, and each reply's thinking blocks go back unchanged. The loop's own lookups get ids from their place in the history. Each step keeps its usage by price |

The new conversations' answers, on eval-v1:
- c20: the teams Raydish and megD faced most, three tied at 5 sets: Marckiem00 and futurebubbles366 (5-0), bestjava
  and fakey7 (2-3), luna and Snowy!! (2-3).
- c21: against Pink | Zen and hideawaybh, 0-3 in sets (games 3-9), after "zen" goes to suggestions.
- c22: after the Autumn Championship - North America 2026 - 2v2's top 8, against Moni- and animefan1266, 1-0 (3-2),
  then "yes they did".
- c23: "raydish megd vs marckiemoo futurebubble", two teams written without an "and": 5-0 (games 15-5).
- c24: "yes they did" with nothing before it.

The targeted run, qwen3:30b, seeds 0-2: `harness.py run --ids q09 q35 q36`, `conversations.py run --ids c1 c5 c8 c10
c12 c15 c19`, `audit.py run --ids a44 a45 a49` and `conversations.py --set eval/questions/teams.toml run`. On the final
run's times for the same items, about 31 minutes, plus about 10 for c20-c24.

The Sonnet experiment's estimate: claude-sonnet-5-5, adaptive thinking at effort high, seed 0, the 45 questions per arm.
Per question, the recorded step prompts give how the context grows, and the outputs give the replies: arm A from the
final run (qwen3:30b), arm B from `20261110-templates-before` (qwen3:8b), the last run before the templates. Each step
reads the request before it from the cache and writes the rest. The system prompt and tools (arm A about 8,600 tokens,
arm B about 3,700) are written once and read at every step. At $0.10 a million for cache reads, $2.50 for cache
writes and $10 for output:

| Arm | Steps (recorded) | Cache reads | Cache writes | Output | Cost: low, middle, high |
|---|---|---|---|---|---|
| A, templates | 132 | 1.21M to 1.63M | 103k to 139k | 41k to 123k | $0.79, $1.26, $1.74 |
| B, run_sql only | 127 | 0.53M to 0.72M | 78k to 106k | 30k to 91k | $0.55, $0.89, $1.24 |

Low is Qwen's input tokens with half its output; middle, 1.15 times the input and the same output; high, 1.35 times
the input (the tokenizer's range) and 1.5 times the output. So about $2 for both arms, and $3 at the high end. Output
is most of it: if Sonnet thinks three times as much per step as qwen3:30b and takes half again as many steps, both
arms come to about $8.

Found in passing:
- c24's give-up live: the reply asked for a question "from 2017 onward". The number check left out the prompt's own
  2017, which is the open question of whether the prompt's facts count. With no fact left, the whole answer became "I
  couldn't look this up in the data, so I won't guess." The new rule doesn't reach it.
- Three answers of the final run read "confirmed bywith mode=..." or "confirmed by thewith top=1" (c8 seed 0 turn 4,
  a49 seeds 0 and 2 turn 2). `claim_check.without_tool_talk` cuts a tool's name out with the spaces on both sides of
  it, so the words around it fuse. It's a bug, not fixed yet.

**What it decided.** Nothing run yet. The targeted run waits for the user's go-ahead on the Ollama server. The Sonnet
experiment waits for the SDK's install (it isn't installed), the key in `.env`, and the go-ahead.

## 2026-11-22: team against team, an addition after the final measurement, checked offline

**What it asked.** Can the agent answer two 2v2 teams against each other? In the user's live test, "raydish and megd
vs moni and animefan1266" got a 1v1 head-to-head, or no tool and "they never met". They met in the Autumn
Championship NA 2026's 2v2 elimination final, 3-2. No tool counted one team against another. The user asked for a
template, and for `rank_pairs` to rank a team's opposing teams. It comes after the final measurement, so the report
lists it as an addition: the final numbers don't include it.

**Setup.** No model. The tools ran on eval-v1, timed with the agent's x64 Python, and the scope rule was checked on the
147 texts of the three sets. Commits 8f3409a and 477513d.

**Results.**

| Change | Checked on | Result |
|---|---|---|
| `team_head_to_head(player_id, partner_id, opponent_id, opponent_partner_id)` | eval-v1, the live question | Raydish and megD 1-0 against Moni- and animefan1266, 3-2 in games, at the Autumn Championship - North America 2026 - 2v2 (2026-09-27), in 0.2 s |
| The same without `opponent_partner_id` | eval-v1 | Against Moni- with any partner: 1-1, with the Midseason Championship 2026 set lost 1-3 to Moni- and Marckiem00 |
| `rank_pairs(player_id, partner_id)`, a duo's opposing teams | eval-v1 | Raydish and megD's most-played teams: Marckiem00 and futurebubbles366 (5 sets, 5-0), bestjava and fakey7 (5, 2-3), luna and Snowy!! (5, 2-3) |
| The scope check refusing `head_to_head` once for "X and Y vs Z and W" | the 147 texts of the three sets | None matches, so no recorded call would have been refused |

The 532 unit tests and `retrieval.py check` pass. No worked example was added: one would change the example bank, and
rebuilding its store needs the embedding model on the server.

**What it decided.** Built. Measuring it with the model is a small targeted run, for the user's go-ahead.

## 2026-11-21: the final measurement, and a summary of the results

**What it is.** The agent's final measurement, which the report cites, with a summary of every round before it. After
it the agent changes only for bugs (the user's decision, 2026-11-21).

**Setup.**
- **The agent at 0b7ee3d.** qwen3:30b (the 30B-A3B mixture of experts) with thinking on, retrieval of worked examples
  on, and the eval-v1 snapshot.
- **The server.** Ollama 0.40.16 on a 24 GB GPU. Every `ollama ps` sample shows 21 GB at 100% GPU with a context of
  32768, nomic-embed-text beside it, and no reload.
- **The sets**, each at seeds 0-2, in a worktree with its own `data/rag`:
  - the evaluation set, the 45 questions the user verified (`20261121-final-questions`). Every run was drafted by hand
    ("needs review") and scored by stage, as on 2026-11-08;
  - the 19 conversations, 48 turns (`20261121-final-conversations`). The user verified c1-c13, and c14-c19 aren't
    verified yet. They're scored by their checks, then by hand where a check misread a right answer;
  - the audit set, 51 questions in 54 turns (`20261121-final-audit`). It isn't verified, and its checks look at how a
    turn went.
- **Not rerun.** The held-out set's final measurement is 2026-11-17's, since its questions were read after it.
- **Two bugs found in the final run** were fixed after it (40996f9). Both are in round seven's recheck, and the numbers
  below include them.
- **Changed after it**, and not in its numbers: two additions and three bug fixes, then the freeze (2026-11-22), in
  the section "After the final measurement" at the end of this entry.

**Headline numbers.**

| Set | Measure | Final, qwen3:30b | Earlier |
|---|---|---|---|
| The 45 questions | Runs right by hand | 113 of 135 (84%), 14 partly | 94 of 135 (70%), 18 partly, on 2026-11-08 (qwen3:8b) |
| | Questions right in every seed | 34 of 45 (76%) | 25 of 45 on 2026-11-08 |
| | Automatic stages | 129 of 135 | 130 of 135, qwen3:8b in the comparison |
| | Model time per run | 20.0 s, 3.0 steps | 17.6 s for qwen3:30b in the comparison, 18.4 s for qwen3:8b |
| The 19 conversations | Turns passing every check | 120 of 144 (83%) | 110 of 144 on 2026-11-21 (qwen3:8b, at 8b59815), rescored with today's checks |
| | Turns right by hand | 126 of 144 (88%) | |
| | Conversations passing in every turn | 33 of 57 | 31 of 57 |
| | c1-c7, turns passing | 55 of 60 | 38 before the web app fixes (2026-11-19), 47 after, 51 on 2026-11-21 |
| | c8-c13 and c14-c19, turns passing | 40 of 48 and 25 of 36 | 35 and 24 on 2026-11-21 |
| | Model time per turn | 19.2 s | 19.2 s for qwen3:30b in the comparison, 24.1 s for qwen3:8b |
| The audit set | Turns passing every check | 158 of 162 (98%) | 137 of 162 on 2026-11-21 (qwen3:8b), rescored |

- **The 45 questions** by stage: 22 runs not right, 16 failing first at answer writing, 5 at SQL logic and 1 at name
  resolution. The 1 is q32 seed 2, which is right by hand: the event it never looked up wasn't needed.
- **The conversations' check misreadings** are the 6 right answers from the previous turn's results, which the user
  decided count for c8 (2026-11-21). c15 turn 2 and c19 turn 2 each ask for a call in the turn, though the previous
  turn's result already holds the answer.

**The model comparison** (in its entry), the 45 questions and the 19 conversations at round six's code, seed 0
(qwen3:8b on seeds 0-2 too):

| | qwen3:8b | qwen3:14b | qwen3:30b |
|---|---|---|---|
| Questions right by hand, seed 0 (right, partly, wrong) | 36, 7, 2 | 32, 6, 7 | 36, 6, 3 |
| Conversation turns passing, seed 0 | 34 of 48 | 38 of 48 | 37 of 48 |
| Model time per question | 18.4 s | 25.1 s | 17.6 s |
| Tool calls refused | 30 of 328 | 10 of 164 | 2 of 156 |
| Loaded on the GPU | 10.0 GB | 14 GB | 21 GB |

- qwen3:14b wrote its answer inside its thinking in 6 of 45 answers, which left the reply empty.
- qwen3:30b answered one question from its training's end. qwen3:8b read records from the wrong side and passed
  arguments the templates refuse.
- qwen3:30b became the default for being the fastest, with the fewest refused calls and none of qwen3:8b's
  wrong-side records.

**What each round changed.** Each row is one entry of this log, oldest first, with the measurement it made. Rounds
marked offline were checked without the model, and their effect is in the next measured row.

| Date | Round | What it changed | Measured |
|---|---|---|---|
| 2026-10-10 | One-prompt text-to-SQL, the model comparison | No agent: one prompt, one query per target question | qwen3:8b with thinking and qwen3:4b 8 of 10 target questions, qwen3:8b without thinking 2 of 10. Most misses were name resolution |
| 2026-10-18 | The ReAct prototype | Two tools, `resolve_player` and `run_sql`, at most 8 steps | Questions 4, 6 and 8: every query right (3 of 3, against 1 of 3), but 1 of 3 answers |
| 2026-10-19 | The prototype's fixes, then the result-size fixes | IDs refused by `resolve_player`, an answer check, answer guidance; a 4,000-token result budget | Seeds 0-5: question 4 5 of 6, question 6 0 of 6, question 8 3 then 4 of 6 |
| 2026-10-23 | Checkpoint 2's lookup changes | Match scores, suggestions for a loose match, a diagnosis for an empty result | Questions 4, 6, 8, q21 and q22: 6, 0, 3, 3 and 0 of 6 |
| 2026-10-25 | `resolve_event`, the lookup check, the ID and no-tool checks | Events looked up, not searched with LIKE | q21 5 of 6, q22 6 of 6, the Worlds follow-ups 6 and 5 of 6 |
| 2026-10-25 | Checkpoint 3, retrieval of worked examples | 28 examples retrieved by meaning (nomic-embed-text, Chroma, MMR) | Question 6 0 to 6 of 6, question 4 5 to 6, question 8 3 to 5, q21 4 to 0. A helpful shape in the top 3 for 32 of 39 questions |
| 2026-11-08 | The full evaluation | The 45 verified questions and a held-out set of 16, seeds 0-2, scored by stage | By hand, 130 of 183 runs right (71%), the 45 questions 94 of 135 (70%), the held-out 36 of 48. Retrieval off: 32 of 87 against 53 on |
| 2026-11-09 | Steps 1 and 2 | Earnings and what the data doesn't cover in the prompt; names: clear-cut shared names, the display, corrections in code | Their targets 3 to 16 of 21 runs right, and 3 to 8 of 12 |
| 2026-11-17 | The template tools | Two views and four templates, so the model writes less SQL | Automatic stages 124 to 130 of 135. `run_sql` calls per run 0.95 to 0.28, model time per run 25.0 s to 14.3 s. The targets 1 to 9 of 12 by hand |
| 2026-11-17 | The held-out set's final measurement | None (a measurement) | 32 of 48 runs right, against 36 on 2026-11-08. The set is spent for tuning |
| 2026-11-18 | Grounding | The number check, the name filter, `player_results`' counts | Automatic stages 127 to 131 of 135 |
| 2026-11-19 | The web app testing notes' fixes | Settling of follow-ups (cues), suggestions answered, the event check, names for IDs | The conversations 38 to 47 of 60 turns; the 45 questions 130 of 135 automatic |
| 2026-11-20 and 21 | Rounds four and five (offline) | Fixes by mechanism: the claim check, the agreement check, the scope check, `Narrowing`, `rank_pairs`, `power_rankings`, the page's note, IDs and tool talk out of answers, `upsets` | Measured on 2026-11-21: 109 of 144 conversation turns (after c8's rescoring), 123 of 135 questions automatic, 137 of 162 audit turns. The questions lost 9 runs to a `rank_pairs` regression (q08, q40) and q05 |
| 2026-11-21 | Round six | The opponents' side, a best placement, `never_won`, `player_sets`, `dominant_wins`, the card kept | Reruns: the 13 questions 30 to 35 of 39 automatic, but 7 conversations 37 to 34 of 60 and 16 audit questions 29 to 27 of 48 |
| 2026-11-21 | The model comparison | None (qwen3:8b, qwen3:14b and qwen3:30b at round six's code) | Seed 0 by hand: 36, 32 and 36 of 45 right. Conversations at seed 0: 34, 38 and 37 of 48 turns. qwen3:30b fastest, 17.6 s per question |
| 2026-11-21 | Round seven (offline) | qwen3:30b the default, and fixes 1-10 with six more (in its entry) | The final measurement, above: 113 of 135 questions right by hand, 120 of 144 conversation turns and 158 of 162 audit turns passing |
| 2026-11-22 | After the final measurement | The team templates, the run_sql rule, and three bug fixes (the section below), then the freeze | The fixes replayed on the recorded runs. The targeted run: every two-team record right (9 turns), give-ups 2 to 0, and 51 against 53 of 69 conversation turns |

**Known limitations, by mechanism**, from the final runs:
- **M1, reading the question.**
  - Questions: q12 (2 runs) gives flowerVS's first 1v1 top 8 without the earlier 2v2 one the decided rule mentions.
  - Conversations: "biggest records ... like set/game count" read as the best rate or the most wins, not the most
    sets (c1 turn 2, 2 runs); "who has the biggest head to head record" read as a rate, then the answer left out
    entirely (c16 turn 1); "autumn 2022" read as the season, with BCX 2022 in it (c4 turn 1).
- **M2, the tools.**
  - No template gives a set's details or an event's size. "the score of the 1v1 grand final" is answered "3-0" with no
    players (q20, all 3 runs, failing stage 2). "the biggest official tournament" is answered "the data doesn't track
    size" (q42, 2 runs), though run_sql found it in the third.
  - c5 turn 3 looked the North America Crew Battle Invitational up but never got its results.
- **M3, facts the model makes.**
  - Set scores put at the wrong event (q23, 2 runs), a 1v1 win listed among the 2v2 ones (q21), and V3M_T4NQUIL0's
    earnings said to be unrecorded with no lookup (q32).
  - c8 turn 4 (3 runs): after the recheck called `player_results` for both players, the answers agreed that the
    card's 12 and 6 golds are its "medals", where their 2v2 medals are 33 and 27.
  - c1 turn 3 left one of the three players named out of its lookups, and c10 turn 2's seed 1 summed the partners'
    events itself.
  - The number check doesn't count the prompt's own facts: q34's "the data starts in 2017" is left out (3 runs, a
    question open since 2026-11-18). Fixed after it (7f49596).
- **M4, the conversation.** A question about the card (c14 turn 2, 3 runs) is explained from the page's line without
  the tool check its expected answer asks for.
- **M5, answer writing.**
  - A team string read wrong: "SiB | Wess / V3M_T4NQUIL0" became "SiB and Wess", leaving V3M_T4NQUIL0 out (q16,
    2 runs).
  - Lists cut short or with a figure wrong: megD's partners (q06, 3 runs), and the tied top pairs without their
    records (c18 turn 1).
  - Totals not stated: Mojakin's 26 results (c9 turn 2), Dragon!'s 9 top 8s (c13 turn 3), and c10 turn 2's partner
    figures (2 runs).
  - q05's "only players with a figure" left out (seed 0), and a score written from the loser's side (q27).
  - Dragon! written "Dragon!!" (c13 turn 3, 3 runs), and the words around a tool's name fused once it was cut out (5
    answers, "confirmed by thewith top=1"). Both fixed after it (5c6b769, 8ba7e18).
- **The audit set**, 4 failing turns.
  - "whats volst's best record against anyone" (a50, all 3 runs) is asked with a 5-set minimum the model sets
    itself. The answers give the empty ranking's note (at most 4 sets, with Bunny meow), not a record, though the note
    says to call again without the minimum (M1).
  - a45, seed 2, says Zivai's career earnings aren't given, with no lookup (M3).
- **Every set's runs** took at most 20,254 tokens of context, and no reply reached the output cap.

**After the final measurement** (2026-11-22). The headline numbers above are the final measurement's, and they stay
as measured: nothing after it is in them. Each change below has an entry of its own, above this one:

| Change | Kind | Commits | Checked on | What it changed |
|---|---|---|---|---|
| `team_head_to_head`, `rank_pairs` with a partner, and the scope check's refusal of `head_to_head` for two teams | Addition, from the user's live test | 8f3409a, 477513d | eval-v1, then the targeted run | Every two-team record right in the 9 turns that name two teams. "versed the most" still ranks each player's opponents in 2 of 3 seeds (c20) |
| The prompt's rule to query the views with run_sql when no template fits, and the no-tool check's messages saying so | Addition, the user's request | be0b938 | The targeted run | Give-ups 2 to 0 on the items where the no-tool check had fired, one through 40996f9. After a send-back the model queried 6 of 16 times, against 7 of 21 |
| A space left where a tool's name is cut out of an answer | Bug fix | 8ba7e18 | The final run, replayed | 5 final answers change, each by a space ("confirmed by thewith top=1") |
| The prompt's own facts, the data's first year and its newest results' date, as evidence for the number check | Bug fix, the user's decision | 7f49596 | The final run, replayed | 16 of 69 check records with flagged numbers no longer fire, q34's six among them. q34 seed 0 keeps its draft instead of "I couldn't confirm this from the data" |
| No swap of the question's spelling where the answer writes the right name | Bug fix | 5c6b769 | Every recorded run, replayed | 11 drafts change in 2,909 turns, each a doubled ending: "Dragon!!" (c13 turn 3, the final run's 3 seeds among them) and "Moni--" (c22 turn 2) |
| A second backend on the Anthropic Messages API, and a switch for run_sql and the views only | Built for a Sonnet experiment | 3afe78a, 041b38c | Unit tests, with a fake client | None: the experiment is skipped for now (the user's decision), and the agent runs as before |

The targeted run (qwen3:30b at 7f49596, seeds 0-2, before 5c6b769) covered the items where the final run's no-tool
check fired, and the live session's 2v2 turns:
- q09, q35 and q36: 9 of 9 right by hand, as in the final run.
- The 7 conversations: 51 of 69 turns, against 53 in the final run rescored with the same checks.
- The 3 audit items: 10 of 12 turns, against 11.
- The team conversations, c20-c24: 21 of 27 turns by their checks, and 19 right, 5 partly and 3 wrong by hand.

**The agent is frozen** from 2026-11-22 (the user's decision): no more prompt or check changes, only fixes for bugs
that break a live answer.

## 2026-11-21: round seven, the model comparison's fixes, checked offline

**What it asked.** Do the fixes the user approved after the model comparison catch their failures on eval-v1 and in
replays of the recorded runs, without changing anything else? The user made qwen3:30b the default model and approved
fixes 1-10, with four more and two for qwen3:30b's answer writing, but not the empty-reply fix. The design is in
[`agent-mechanisms.md`](agent-mechanisms.md), under round seven.

**Setup.** No model. The tools ran on eval-v1, timed with the agent's x64 Python where time mattered. The checks were
replayed on the recorded runs (the comparison's, the 2026-11-21 runs and round six's reruns), with no held-out trace.

**Results.**

| Fix | Checked on | Result |
|---|---|---|
| qwen3:30b the default | `react.MODEL` | The harness, the runner, `ask.py` and the web app read it |
| The card line in the scorer's window | the five 2026-11-21 conversation runs, rescored | One check changes: 14b's c14 turn 2 grounded |
| `says_record` reading a list item with its lead-in | the seven recorded conversation runs | 3 turns change, each c14 turn 1 with a right 1v1 record |
| c18 turn 1 and c19 turn 2's checks | the five 2026-11-21 conversation runs | c18 passes every right answer and fails 14b's 34-15 and two off-topic ones; c19 passes 30b's `by="rate"` |
| No default minimum on a player's own records, and the empty-ranking note | eval-v1 | volst by rate: woolala 3-0 first. With `min_sets=5`, the note gives 4 (Bunny meow). q08's side is unchanged |
| The opponents' side's columns by role, and the record check's side | eval-v1, the unit tests | Raydish's side table gives q40's verified 10, 8, 7 and 6. a28's list shape passes; a reversed record still goes back |
| `mode` on `head_to_head` and `team_results` | eval-v1 | kyna vs yüz in 1v1: 17-17 (c12 turn 3). Raydish's teams against whoiskyna's in 2v2: 2-3 (c3 turn 2) |
| `dominant_wins` in two queries | eval-v1 against the committed version, x64 Python | The 6 calls the old one finished give the same observation. Every call takes at most 7.9 s (it took over 30 s) |
| The audit's six `run_sql` checks | the two 2026-11-21 audit runs | Round six's run passes all six on calls; the earlier run fails those that didn't use the condition |
| Request words ("analyze") | the 147 texts of the three sets | 3 change, each losing only its request word |
| A recheck with no call runs the calls the answer rested on | the 16 recorded rechecks that called no tool | c10 turn 2: `team_results` for megD every time. c8 turn 5: a `team_results` call holding the pair's 24 events every time |
| The data's end in the prompt | eval-v1 | "The data's latest results are from 2026-09-27" |
| A ranking's measure in a follow-up | c8 turns 1-2 of five runs, settled again | Each turn 2 names "rank_players by wins, in 2v2" and how to keep it |
| "X's record with Y" read as against each other | the 22 recorded `team_results` calls with a partner | It refuses exactly 14b's c3 turn 1 and 30b's c6 turn 1 |
| An event name covering a 1v1 and a 2v2 | eval-v1 | The note comes with "bcx 2022", "midseason championship 2026" and "worlds", not with "bcx 2025 1v1" |
| A misspelled returned name | 921 recorded answers | 3 swaps, all real: "yüx" to yüz (q17), "BballoonBoy" and "BBalloonBoy" to BBBalloonBoy (a51). The first version would also have cut a list's number and a count out of bold names, now excluded |

The 526 unit tests and `retrieval.py check` on the 35 examples pass.

**What it decided.** All of it is built. The reruns with qwen3:30b wait for the user's go-ahead: the 45 questions,
the 19 conversations and the audit set, seeds 0-2. They're listed in the design note.

## 2026-11-21: the model comparison, qwen3:8b, qwen3:14b and qwen3:30b in the agent

**What it asked.** Which failures does a bigger model not make? The user asked for it before round six's proposed
fixes, since those bugs don't depend on the model and are mostly outside the 45 questions. The point was to know this
before tuning further for qwen3:8b.

**Setup.**
- **The commit.** 87ea61e, whose agent code is 2aecbc7's, in a worktree with its own `data/rag`.
- **The models.** Each ran with the other chat models unloaded, retrieval on, everything else as the agent has it
  (`--model`):
  - qwen3:8b on seeds 0-2: the regression check (`20261121-cmp-8b`);
  - qwen3:14b and qwen3:30b (the 30B-A3B mixture of experts) on seed 0 (`20261121-cmp-14b`, `20261121-cmp-30b`).
- **The questions.** The 45 questions, by id. Then all 19 conversations at seed 0 for each model
  (`...-conversations`).
- **`ollama ps`.** Sampled every minute into `data/experiments/<run>-ps.log`.
- **The hand drafts.** Every seed-0 answer was read by hand, and q08, q40, q42 and q44 at qwen3:8b's other seeds.
  They're in each run's judgments file as "needs review".

**Results.**

| | qwen3:8b | qwen3:14b | qwen3:30b |
|---|---|---|---|
| The 45 questions, automatic stages | 130 of 135 (43, 43, 44) | 44 of 45 | 42 of 45 |
| By hand, seed 0: right, partly, wrong | 36, 7, 2 | 32, 6, 7 | 36, 6, 3 |
| The 19 conversations, seed 0: turns passing every check | 34 of 48 | 38 of 48 | 37 of 48 |
| The same, with the checks' misreadings counted right | 34 | 39 | 38 |
| Model time per question (median) | 18.4 s (17.1) | 25.1 s (23.8) | 17.6 s (16.0) |
| Model time per conversation turn (median) | 24.1 s (18.6) | 31.3 s (28.3) | 19.2 s (16.6) |
| Output tokens per question; tokens a second | 1,311; 71 | 1,144; 46 | 1,761; 100 |
| Tool calls refused (an argument a template doesn't take, a missing one, the player and scope checks) | 30 of 328, every seed | 10 of 164 | 2 of 156 |
| `ollama ps` | 10.0 GB, 100% GPU | 14 GB, 100% GPU | 21 GB, 100% GPU |

- **`ollama ps`.** Every model had a context of 32768, with nomic-embed-text (335 MB, 100% GPU) loaded beside it, and
  no sample showed a reload or a CPU share. The largest context was 19,183 tokens. One step hit the 8,192-token output
  cap, qwen3:8b's c2 turn 2.
- **qwen3:14b's empty replies.**
  - In 6 of its 45 answers and 1 conversation turn, it wrote the answer inside its thinking and left the reply empty,
    so the loop ended with none: q01, q02, q20, q25, q33, q43 and c12 turn 3.
  - The automatic stages pass these runs, so the hand drafts count them as "no answer".
  - Each thinking held a right answer. Sent back once, 14b would likely be at 37-38 right.
- **What qwen3:14b and qwen3:30b avoid**, among qwen3:8b's misses at seed 0:
  - records read from the wrong side (q23's games, q27's set scores);
  - the opponents' side's columns misread (q40: BBBalloonBoy's "4 losses" were Raydish's wins);
  - a tool's note misread (q37: "crew battles not included");
  - `head_to_head` for a placements question (q44: 8b is right in 1 of 3);
  - and arguments the templates don't take. qwen3:8b passed `mode` to `head_to_head` or `team_results` 17 times,
    which they refuse; in c2 turn 2 that sent it into a thinking loop to the output cap, with no answer. qwen3:14b
    did it 3 times, qwen3:30b never.
  - qwen3:30b alone avoids the missing figure taken as $0 (q45: "the higher recorded figure").
- **What the bigger models miss that 8b doesn't**:
  - qwen3:14b: the empty replies; invented Challengermode player links in q19; q39 narrowed to 1v1 itself, then "the
    data only shows 1v1"; q05 without "only the players with a figure".
  - qwen3:30b: half an event pair (q10's 2v2 bracket, q19's 2v2 winners, q12's earlier 2v2 top 8); "yüz" spelled
    "yüx" and "ünl", which the answer check doesn't catch; and q15, where "EU Summers 2026 hasn't happened yet: the
    data only goes up to 2025". That is its training cutoff: the prompt says the data starts in 2017, not when it
    ends. The number check then left out the claim holding 2025, and the answer became the bare "Therefore, Zivai
    could not have won it".
- **Today's open failures, model by model** (questions and conversations, seed 0):

| Open failure | qwen3:8b | qwen3:14b | qwen3:30b |
|---|---|---|---|
| "best record" with a 5-set minimum: c19 turn 1 | fails (`by="rate"`) | fails (`min_sets=5`, its own) | fails (`min_sets=5`, its own) |
| c19 turn 2, "without the 5 set minimum" | fails | right | right (the check asks for `by="record"`) |
| c16 turn 1 and c1 turn 2, the biggest records | both fail | both right | c16 right, c1 fails (`by="record"` for "like set/game count") |
| The opponents' side misread (q40) | partly, wrong, right | right | right |
| A recheck with no call | c8 turn 5 | c10 turn 2 | c8 turns 4 and 5 |
| "analyze" looked up as an event (c15 turn 2) | right | fails | right |
| q44, `head_to_head` for placements | 1 of 3 right | right | right |
| c1 turn 5, no call for "in a graphic" | fails | right | right |
| `dominant_wins` unnarrowed (a35) | not run (audit set) | not run | not run |

- **Failures by mechanism**, the seed-0 questions not right and the conversation turns failing a check:

| Mechanism | qwen3:8b | qwen3:14b | qwen3:30b |
|---|---|---|---|
| M1, reading the question | 3: c3 t2, c8 t2, c16 t1 | 3: c3 t1, c8 t2, q39 | 4: c1 t2, c4 t3, c6 t1, c8 t2 |
| M2, the tools | 10: c1 t2, c1 t3, c2 t2, c4 t1, c12 t3, c19 t1, c19 t2, q40, q42, q44 | 3: c12 t3, c19 t1, q42 | 3: c19 t1, q20, q42 |
| M3, facts the model makes | 6: q06, q23, q27, q34, q37, q45 | 6: c16 t2, c18 t1, q06, q19, q34, q45 | 3: q06, q15, q34 |
| M4, the conversation | 3: c1 t5, c8 t5, c14 t2 | 3: c10 t2, c14 t2, c15 t2 | 3: c8 t4, c8 t5, c14 t2 |
| M5, answer writing | 1: c11 t1 | 1: q05 | 6: c12 t1, c18 t1, q10, q12, q17, q19 |
| No answer (empty reply) | 0 | 6 | 0 |
| The checks' misreadings | 0 | 1: c14 t1 (and c14 t2's grounded, a turn that fails a real check too) | 1: c19 t2 |
| All | 23 | 23 | 20 |

  - M1 common to all three: c8 turn 2, "what about cody travis and phazon?" after a ranking, read as their
    partnership instead of their place in the ranking. "X's record with Y" and "X and Y's record" are read as
    partners by 14b (c3 turn 1) and 30b (c6 turn 1).
- **The checks' misreadings, found here.**
  - The conversation scorer's grounded check leaves out the page's card line, which the agent counts as evidence
    (`Conversation.shown`). Counting it changes one turn in the recorded runs, 14b's c14 turn 2 ("51" from the
    card).
  - `says_record` reads a list item without the line that introduces it. Reading it with that line passes three
    right records it now fails, all c14 turn 1: 14b seed 0, and seed 2 of `20261121-conversations` and of
    `20261121-r6-conversations`.
  - c19 turn 2's `calls_with` asks for `by="record"`, but 30b's `by="rate"` with `min_sets=1` gives woolala 3-0,
    the right answer.
  - c18 turn 1 asks for 28, the third pair, which an answer naming only the tied top two leaves out.
- **The checks that fired**, per question run: the no-tool check in 10%, 7% and 4%; the number check sent back 4%,
  4% and 4%. The scope check refused 1, 1 and 0 calls.

**What it decided.** Nothing yet: the fixes are for the user to approve. The bigger models avoid most of qwen3:8b's
misreadings of records and tools, but no model fixes the "best record" minimum, the recheck with no call, or c8 turn
2's reading. qwen3:14b's empty replies cost it more than it gains. qwen3:30b is the fastest per question, with the most
right on its seed alongside qwen3:8b's. The proposals:
1. The tool and scoring fixes the user named: `rank_pairs`' minimum and its empty-ranking note; the opponents'
   side's columns by role and the record check's side; `dominant_wins` under 30 s; the audit's six `run_sql` checks
   moved to the templates.
2. Found here, model-independent:
   - `head_to_head` and `team_results` take `mode`;
   - the scorer's grounded check counts the card line;
   - `says_record` reads a list item with its lead-in;
   - c19 turn 2's `calls_with` accepts the `by="rate"` call.
3. The behavior fixes the bigger models still need:
   - the recheck making its calls (14b and 30b);
   - "analyze" (14b).
4. Found here, for the user to weigh:
   - an empty reply with an answer in its thinking goes back once (14b only);
   - the prompt saying when the data ends (30b's q15);
   - c8 turn 2's reading, which every model misses.

## 2026-11-21: round six's reruns, 1-3

**What it asked.** Do round six's seven fixes work with the model, and do the controls hold? These are reruns 1-3 of
the design note's list. If they looked right, the model comparison was to run at the same commit instead of rerun 4,
as the user decided.

**Setup.** qwen3:8b with thinking, retrieval on, seeds 0-2, at 2aecbc7, in a worktree with its own `data/rag`. The
runs are `20261121-r6-conversations` (c1, c8, c14, c15, c16, c18, c19), `20261121-r6-questions` (13 questions, by id)
and `20261121-r6-audit` (16 questions). Each is compared with the same items of the 2026-11-21 runs, both scored with
today's checks. The audit's checks on a14, a15, a28, a34, a35 and a39 ask for `run_sql`, written before round six
gave those kinds templates, so those answers were read by hand.

**Results.**

| Run | Pass every check | Before |
|---|---|---|
| The 7 conversations | 34 of 60 turns | 37 |
| The 13 questions, automatic stages | 35 of 39 runs | 30 |
| The 16 audit questions | 27 of 48 turns | 29 |

- **What worked**, by hand:
  - q08 is right in 3 of 3 (0 before), a03 in 3 of 3 (0), c15 turn 1 in 3 of 3 (1) and c8 turn 4 in 2 of 3 (0).
  - The new templates' answers: a39 (`player_sets`), a14 (sphynx. with 36, checked in SQL), a15 (each reading
    named) and a34 (the same win as the old `run_sql` answers) in 3 of 3.
  - Every q05 run lists the top 10 earners, against 1 of 3 before. Seed 0 fails stage 2 only because its query
    selected no names.
  - c18 turn 1 3 of 3 (1), c1 turn 3 2 of 3 (0); q11 and the upsets held.
- **What didn't**, by mechanism:
  1. "best record" read as `by="rate"` with a 5-set minimum (M2, M1). volst has at most 4 sets against any
     opponent.
     - c19 turn 1 and a50: all 6 runs gave a minimum of 5 and answered that no opponent qualifies (3 of 6 before).
     - c16 turn 1 ("who has the biggest head to head record"): all 3 runs called `by="rate"` with no player, which is
       refused. 2 runs then asked the user instead of answering (3 of 3 right before, with `by="sets"`).
     - The cause is the prompt's new line, which ties "best record" to `by="rate"` for the opponents' side, and the
       tool's "at least 5 sets unless min_sets".
  2. The opponents' side misread (M2, M3). In `side="opponents"` rows the `player` column is the other player and
     `opponent` is the player asked about.
     - q40 passes the automatic stages 3 of 3, but only seed 2 is right. Seeds 0 and 1 read Raydish's wins as his
       losses and named Marckiem00.
     - a28 seeds 0 and 1: the record check reads a list headed "against Zivai" as Zivai's own records. It sent the
       right records (Marckiem00 6-1) back as reversed, then left them out, so the answers start at 4th place.
  3. `dominant_wins` with no narrowing is too slow (M2): 22 s with the ARM64 Python, over the 30-s limit with the
     agent's x64 Python. Round six's offline check used the ARM64 one.
     - a35 seeds 0 and 1 were stopped, narrowed to events no word of the question names (bcx 2023, worlds 2023),
       and answered that nobody won without dropping a game.
     - Seed 2 asked for 1v1 and got the 19 wins.
  4. c8 turn 5, 3 → 0 of 3 (M4). Turn 4 now calls `player_results`, which is its fix, so turn 2's `team_results`
     row is no longer in turn 5's window.
     - Turn 5 called no tool in any seed, even after the recheck sent it back. Before, 2 of 3 seeds did the same,
       and turn 4's `team_results` call covered them.
     - The figures are right in seed 0 and partly in seed 1. Seed 2 made up "8 solo" and "2 solo" wins.
  5. c15 turn 2, 1 → 0 of 3 (M4, M3). Turn 1 now gives the placement counts, so turn 2 answered from them without a
     call.
     - The no-tool check took "analyze" for a content word and looked it up as an event, and seed 2's answer then
       said "analyze" is no event.
     - The counts were misread in all 3 (25th "2 times", where the table says 4), as before.
- **Variance and known misses:**
  - c14 turn 1, 2 → 1: the 2v2 meetings were left out.
  - c1 turn 5, 3 → 1. Seed 2's first call passed region na and since 2023-01-01, which no word of the question
    gives, and kept them for four turns. Seed 1 called no tool for "in a graphic".
  - q44, 2 → 1: `head_to_head` for a placements question, the known miss.
  - q45, 3 → 2: scoring, since the query filters on the player without selecting it. Right by hand.
- Model time per run on the 13 questions: 22.7 s, from 24.3 s.

**What it decided.** The reruns don't look right, so the model comparison didn't run. The fixes they point to are for
the user to approve:
1. `rank_pairs`:
   - no minimum on a player's own records unless the question sets one, `by="rate"` included;
   - a note giving the most sets with one opponent when a minimum empties the ranking;
   - the prompt's "best record" line kept to the opponents' side (c19, a50, c16).
2. The opponents' side:
   - columns named for their roles (each opponent's wins against the player and losses to them);
   - the record check reading a list's records from the side its rows give (q40, a28).
3. `dominant_wins` under 30 s with no narrowing, and its timeout suggesting a mode before an event (a35).
4. A recheck that still calls no tool: the loop makes the calls the disputed answer rested on, as the no-tool
   check's lookups do (c8 turn 5).
5. "analyze" and other request words not taken as content words (c15 turn 2).
6. The audit's six `run_sql` checks moved to round six's templates.

## 2026-11-21: round six's fixes, checked offline

**What it asked.** The user approved all seven fixes the measured runs point to, the `rank_pairs` regression first.
Do they catch their failures on eval-v1 and in replays of the recorded runs, without disturbing anything else? And
what does c8 score now that a right answer from the previous turn's results counts, as the user decided? The design
is in [`agent-mechanisms.md`](agent-mechanisms.md), under round six.

**Setup.** No model. The new tools ran on eval-v1. The checks were replayed on the recorded runs, the 2026-11-21 ones
included, with no held-out trace. `20261121-conversations` was rescored from its traces into a scratch file, so the
logged scores stay as they were.

**Results.**

| Fix | Checked on | Result |
|---|---|---|
| The opponents' side (`rank_pairs(side="opponents")`, and the scope check) | q08 and q40 on eval-v1; the 59 recorded `rank_pairs` calls | Both give their verified answers. The check refuses q08's, q40's and a28's 6 distinct calls and no other. Narrowed so "X's record vs Y" isn't refused: c1 turn 3 and q27 stop matching, with the same 6 refused |
| No `top` for a best placement | the 85 distinct recorded `player_results` calls | It refuses exactly the two `top=1` calls of a03 and c15 |
| `rank_players(never_won)` | eval-v1 | The most top 8s without a win: sphynx. 36, Goddess 33, hermisen 32. The most 1v1 wins without a 1v1 Worlds: Zivai 23 |
| `player_sets` | eval-v1, a39 | Zivai at BCX 2023 in 1v1: 10 sets, 8 won, lost 1-3 to yüz and whoiskyna |
| `dominant_wins` | eval-v1, q11 | Raydish's most dominant win is Trial of Laufey NA (Moose Wars), 25 games to 2, q11's verified answer. 19 1v1 wins without a dropped game |
| Earnings in "Choosing a tool" | the prompt | A line of its own, for q05's "no tool covers earnings" |
| The card kept as long as its note | the 144 recorded conversation turns, settled again | Only c8 turn 4's settled text changes, in all three seeds: now a dispute about the card's figures |
| c8's check on the window | `20261121-conversations` rescored | 109 of 144 turns pass every check, from 103: c8 turns 3 and 5 in all three seeds, and no other turn |

`retrieval.py check` passes on the 35 examples, ex23 now showing a `dominant_wins` call, and the 510 unit tests pass.

**What it decided.** All of it is built. The reruns with the model wait for the user's go-ahead. They're listed in
the design note.

## 2026-11-21: the mechanism rounds measured: conversations, the 45 questions, the audit set and retrieval

**What it asked.** How do rounds four and five, and findings 7-20's four commits, do with the model? Rounds four and
five are the failure mechanisms and the fixes for findings 21-35. The user approved five runs after their live test.

**Setup.** qwen3:8b with thinking, retrieval on, seeds 0-2. The runs went one after another so they didn't compete
for the server.
- **The before run.** c8-c13 at 3d42613, the commit before findings 7-20's fixes, as agreed on 2026-11-20. It ran
  in a temporary worktree with that commit's conversation set. That set has c9 turn 1 as "mojakins" and no card
  line for c8.
- **The other runs.** All at 8b59815: all 19 conversations (`20261121-conversations`), the 45 questions
  (`20261121-questions`, by id), the audit set (`20261121-audit`), and `retrieval.py measure`.
- **Scoring.** Every run was scored with the latest checks. The scorers' grounded check reads count words as the
  agent does since 444cb82, a fix found in this measurement. It moved c18 seed 0 to a pass.
- **The example store.** The first try of the before run failed. Chroma's example store is shared by every process
  that opens it, and the web app's two servers were still running from their worktree with another bank of examples.
  Each run then got its own store in its own worktree, linked to the rest of `data/`. The web app's store in the
  main checkout was partly deleted in the process, and restarting the web app rebuilds it.

**Results.**

| Run | Result | Against |
|---|---|---|
| Retrieval, the agent's settings | a helpful shape in the top 3 for 31 of 39 questions; 34 of 39 without the threshold | 32 and 35 on 2026-10-25. The same without ex33-ex35, so the new examples don't move it, and the drop predates them |
| The before run, c8-c13 at 3d42613 | 24 of 48 turns pass every check | |
| All 19 conversations | 103 of 144 turns (71%); 31 of 57 conversation runs pass every turn | |
| c1-c7 | 51 of 60 turns | 47 in `20261119-conversations-cues` |
| c8-c13 | 29 of 48 turns | 24 before |
| c14-c19 | 23 of 36 turns | new |
| The 45 questions, automatic stages | 123 of 135 runs | 130 in `20261119-webfixes` |
| The audit set | 137 of 162 turns (85%); 128 of 153 runs pass every turn | new |

- **The conversations.**
  - c13 went from 3 to 9 of 9 turns ("dragon" gets suggestions, and "Dragon!" picks him). c9 went from 3 to 5 of 6
    ("the first one" gets Mojakin's stats), and c12 from 4 to 5 of 9.
  - c17 passes every turn in every seed: "the strongest 1v1 player right now" is read as now, in 1v1, and the
    follow-up in 2v2 in NA works too.
  - c8 fell from 8 to 3 of 15. Its turns 3 and 5 give the right answers ("4 tournaments", "24 is the events")
    from the previous turn's `team_results` result, without a fresh call, which its verified `players` check counts
    as a failure.
  - Its turn 4 is a real regression. "are you sure? ... in the graphic" asks about the card shown two turns
    back, but the page cue keeps only the last turn's card, so it's read as a dispute and the model defends "4
    tournaments". The before run gave the medals in 2 of 3 seeds.
  - c15 is still weak (2 of 6). "best placement" was asked with `top=1` in 2 seeds, and the placement counts were
    misread (33rd "5 times", the table says 6).
  - c18 seed 1 read "biggest head to head record" as `by="record"`, was refused without a player, and answered
    about Cody Travis.
- **The 45 questions.** 9 runs were lost and 2 won (q05 seed 1, q44 seed 0).
  - q08 lost all 3 seeds and q40 lost 2. "Who has the best record against marckiemoo" and "who has raydish lost
    to the most" ask for the opponents' side. Each was asked as round five's `rank_pairs(by="record")` with that
    player's ID, which ranks the player's own records. That's a regression of round five.
  - q05 lost 2: the model said no tool covers earnings and never queried `v_career_earnings`, though the prompt names
    it.
  - q23 seed 2 resolved "kingdom" alone, and q44 seed 2 is a flaky question.
  - Model time per run went from 22.1 s to 18.9 s. The checks fired: the no-tool check 25 times, the event check 10,
    the number check sent back 4 and left out 7 claims, the scope check refused 3 calls, and the claim check fired
    2.
- **The audit, by mechanism.** The tools fail 20 of 120 tagged turns, reading 7 of 51, facts 7 of 45 and the
  conversation 2 of 21. By kind:
  - Rankings with a condition (kind 7) fail 6 of 6, as "the most top 8s without ever winning" is asked as a plain
    ranking.
  - "best placement" is asked with `top=1` (kind 2, a03 3 of 3).
  - The best record against a player is the `by="record"` regression (kind 14, a28 2 of 3).
  - Whom a player lost to at an event has no tool (kind 19, a39 3 of 3): `head_to_head` is called without an
    opponent.
  - "Without dropping a game" is looked up as an event name (kind 17, a35 3 of 3).
  - The top earners (a43) miss `run_sql` once.
  - Streaks, upsets, current form, regions, the Power Rankings, teams and rivalries (kinds 3-6, 8-10, 12, 15, 16,
    18, 20) pass in every run.

**What it decided.** Nothing yet: the next fixes are for the user to approve. The ones the runs point to are:
- the opponents' side for `rank_pairs` records (q08, q40, a28);
- a refusal of `top` for a best placement (a03, c15);
- a condition for `rank_players` (kind 7);
- a player's sets at an event (a39);
- a flawless-run question (a35);
- earnings named in "Choosing a tool" (q05);
- the card kept in the settling context while its note is in the history (c8 turn 4).

## 2026-11-21: round five's fixes, replayed offline on the recorded runs

**What it asked.** Would the fixes for findings 30-35 catch their failures without disturbing right answers? Every
figure in the fifth round was right, and its failures were in how the answers read. The design is in
[`agent-mechanisms.md`](agent-mechanisms.md), under round five.

**Setup.** As on 2026-11-20: the recorded runs with no held-out trace, plus the fifth round's live sessions
(20261121T045117Z-002 and 20261121T053752Z-002). Drafts, the replies a check sent back, were replayed as well as
final answers.

**Results.**

| Check | Flagged | What they were |
|---|---|---|
| A count word counting a result's rows | finding 30's live draft | It passes clean now: "the top two tied at 34 sets" isn't cut. |
| A record checked from its owner's side | 2 records in 883 drafts and answers | Finding 34's two, volst against Raydish and antireplay, 2-1 where the results give 1-2, in both drafts. The rule's first version also flagged five right records, each of which shaped the final rule. |
| Placeholders, relaxations, characterizations | 14 claims in 751 answers | 7 placeholders (finding 33's five, and q30 seed 1's "[Player Name]" and "[Team Name]"), finding 33's "Removing that condition", and 6 "dominates" on 2-1 records, finding 35's among them. Flagging every "dominates" would have made 15. |
| IDs beside names | 167 of 747 answers (279 IDs) | Taken out of the final answer unless asked for. |
| Tool talk, "as requested" | 40 and 1 | Every tool or call named to the user, and finding 35's "as requested". |
| Draft talk after a send-back | 1 of 89 answers | Finding 34's "**Corrected Answer:**" and its clause about the previous answer. |

The new tools were checked on eval-v1 against the findings' truths. volst's best records are woolala 3-0, then nine
opponents at 2-0. The upsets are BCX 2023's irqqzz (seed 665) over Nomm999 (89), and over every event Commanda Doggo
(7,233) over Phoza (192). Scored on their live transcripts, c18's and c19's turns fail exactly the checks written for
their findings.

**What it decided.** All of it was built, with 503 unit tests passing. Nothing is measured with the model yet. The
runs are listed in the design note.

## 2026-11-20: the failure mechanisms, replayed offline on the recorded runs

**What it asked.** The fourth round of the web app's testing notes (findings 21-29) came with a new direction from the
user: fix the mechanism behind each failure, not the question. Would the new checks catch the failures they're built
for, and would they disturb answers that were right? The design, the grouping of failures by mechanism and every
decision are in [`agent-mechanisms.md`](agent-mechanisms.md). This entry has only the replays, which were the only
measurements possible while the user tested live on the Ollama server.

**Setup.** Each check was run, without the model, on the final answers and tool calls of the recorded runs with no
held-out trace. Those are `20261117-templates`, `20261117-grounding-before`, `20261118-grounding`,
`20261119-webfixes`, the three conversation runs of 2026-11-19, and the live web sessions to 2026-11-20 (784 answers,
545 template calls). Turns were replayed as the loop sees them: this turn's and the previous turn's tool results,
with a page's line added after its turn.

**Results.**

| Check | Flagged | What they were |
|---|---|---|
| The claim check: referrals and judgments | 7 of 784 answers | All claims of its kind. Among them are finding 22's SQL for the user, finding 26's "further analysis would be needed", finding 27's "likely a data anomaly", a SQL block given to the user in "dragon stats", and one offer to query ("I can query the database for entries"). |
| The number check's agreement: a figure needs a row about its player and mode | 5 of 759 answers (7 before years were exempted) | Four wrong figures. q39 seed 0 gave Boomie's 34 to gdsandstorm. c4 seed 1's "out of 16 players" took its 16 from a 2v2 event's date. c6 seed 2's 2v2 top 8s were held only by 1v1 rows. c1 seed 0's "10 games to 8" took its 10 from a date. The fifth is a sentence about tied positions (q14 seed 2). |
| The scope check | 1 of 545 template calls | Finding 29's `rank_players(by="wins", top=5)` for "the strongest 1v1 player right now". |
| The page and dispute cues | 4 messages | The three earlier live disputes and finding 23's question about the card. |
| The possessive retry | 2 of 98 questions | "renivics" (finding 25), and "mojakins", which is c9 turn 1's and conflicts with its verified suggestions. Two event terms were misread first ("winters", "springs"); curated terms now count as event words. |

The new tools were checked on eval-v1 against the findings' truths. Renivic's best 2v2 placement is 17th, twice, with
25th 4 times and 33rd 6. The 1v1 #1s of the Power Rankings are BBBalloonBoy, Zivai, lopesbrawlhalla, marker_bh1 and
keiththepoopoo. megD's most-played opponent is luna (18 sets). The pairs with the most 1v1 sets are SiB | Wess and
lFiend, and yüz and whoiskyna (34 each).

**What it decided.** All of it was built (commits 1d2c4f1 to 5620824), with 490 unit tests passing. Nothing is
measured with the model yet. The runs wanted, asked for together, are the before run of c8-c13 at 3d42613, all 17
conversations, the 45 questions, the audit set and `retrieval.py measure`. They're in the design note.

## 2026-11-19: the fixes for the web app testing notes, on the test conversations and the 45 questions

**Change**, approved 2026-11-19 from the user's live test of the web app that day (`docs/web-app-testing-notes.md` on `claude/web-app`), one commit each:
- **The test conversations** (9250ea1, verified in ae5372a): `eval/questions/conversations.toml`, 7 conversations and 20 turns cut from the live sessions. Each turn has what a right answer says, its reference queries, and checks read on the turn's window (its own and the previous turn's tool results). `eval/conversations.py` plays and scores them.
- **Fix 1, a turn with no tool call** (626cc36). It's checked in code against the window. It goes back once when the question has a content word no result in view holds, or the answer states a player or a number none holds. If the reply still calls no tool, the loop runs the lookups itself (`forced`). With nothing looked up, unsupported claims are replaced.
- **Fix 2, the context settled before retrieval and the model** (44e305b). A reply to suggestions becomes the question it answers, with the chosen player written in. A follow-up is settled one of two ways, behind a switch (`follow_ups`), to be chosen on these runs: hand-written cues (a note with the previous question, its players and events, and "he" when there was one player), or a one-call model rewrite.
- **Fix 3** (b6f55fd): what an answer asks (a sentence ending in "?") and its code state nothing, and a reply that talks about a check keeps the answer it replied about.
- **Fix 4** (1591dce): a player named only by an ID a tool returned gets their name, and a name next to another player's ID, where resolve_player decides the name as someone else, goes back (the pairing check) instead of being renamed.
- **Fix 5** (9066289): an answer after an event lookup that found nothing, with no other spelling tried, goes back once to spell the name out and look again (the event check).
- **Fix 6** (f04eea3): head_to_head's sets lead with their event, and answers name sets by event.

**Runs**, retrieval on, seeds 0–2, Ollama 0.40.16, qwen3:8b with thinking. No run failed.
- The conversations before: `20261119-conversations-before`, at ae5372a.
- After, with cues: `20261119-conversations-cues`, at 31b4ebc (the agent as of f04eea3).
- After, with the model rewrite: `20261119-conversations-model`, at 31b4ebc, `--follow-ups model`.
- The 45 questions: `20261119-webfixes`, at 31b4ebc, against `20261118-grounding` (fdd2496).

**The conversations**, scored with b0f93b7's check for c3 turn 2 (decision 2 below; 31b4ebc's gave 38, 45 and 42 turns):

| Run | Turns passing every check | Later turns (2 on) | Conversations passing in every turn |
|---|---|---|---|
| Before | 38/60 (63%) | 21/39 | 7/21 |
| Cues | 47/60 (78%) | 31/39 | 11/21 |
| Model rewrite | 45/60 (75%) | 29/39 | 10/21 |

| Turn | Message | Before | Cues | Rewrite |
|---|---|---|---|---|
| c1 turn 1 | whats the biggest record megd has | 3/3 | 3/3 | 3/3 |
| c1 turn 2 | i meant biggest records vs other players, like set/game count | 0/3 | 0/3 | 0/3 |
| c1 turn 3 | he doesnt have big records vs raydish or java or guichabou etc? | 1/3 | 1/3 | 2/3 |
| c1 turn 4 | what about megd vs raydish | 3/3 | 3/3 | 3/3 |
| c1 turn 5 | show head to head megd vs raydish in a graphic | 1/3 | 2/3 | 2/3 |
| c2 turn 1 | whats megd and raydishes record in 1v1 | 3/3 | 3/3 | 3/3 |
| c2 turn 2 | the first one | 0/3 | 3/3 | 3/3 |
| c3 turn 1 | whats raydish's record with kyna | 2/3 | 2/3 | 2/3 |
| c3 turn 2 | tell me about the 2v2 record | 0/3 | 3/3 | 3/3 |
| c4 turn 1 | what did raydish get in autumn 2022 | 3/3 | 2/3 | 2/3 |
| c4 turn 2 | when was ceo 2025 | 3/3 | 3/3 | 3/3 |
| c4 turn 3 | who got 2nd at ceo 2025 | 3/3 | 2/3 | 1/3 |
| c5 turn 1 | do you know about the cb tournament in 2022 | 0/3 | 0/3 | 0/3 |
| c5 turn 2 | i meant the crew battle tournament in 2022 | 2/3 | 3/3 | 3/3 |
| c5 turn 3 | tell me about the north america one | 1/3 | 3/3 | 2/3 |
| c6 turn 1 | whats raydish and megd's record | 3/3 | 3/3 | 3/3 |
| c6 turn 2 | raydish lifetime stat card | 1/3 | 2/3 | 1/3 |
| c7 turns 1–3 | three standalone questions | 9/9 | 9/9 | 9/9 |

- **What the fixes fixed:**
  - "the first one" (c2 turn 2): 0 → 3 of 3 in both. It's settled in code into the question it answers, with Raydish (160000) chosen. Before, every seed answered about Addymestic, a worked example's player.
  - "tell me about the 2v2 record" (c3 turn 2): 0 → 3 of 3 in both. Before: a clarifying question, a ranking of 2v2 winners, and the 1v1 record. After, every answer gives the 5 sets and Raydish's side 2-3 from the previous turn's head_to_head result, with no tool call, and the no-tool check rightly let them stand.
  - The crew battle follow-ups (c5 turns 2 and 3): 3 → 6 of 6 with cues. c1 turn 5 and c6 turn 2 gained a run each.
- **What they didn't:**
  - "cb 2022" (c5 turn 1): 0 of 3 in all three runs, the two after runs alike, since turn 1 is the same input with the same seed. The event check fired in every run after, and the model looked again, but as "bcx 2022" (seeds 0 and 1) or "brawlhalla championship 2022" (seed 2), never "crew battle". Decision 5 below.
  - c1 turn 2, megD's head-to-head with the most sets (luna, 18): 0 of 3 in all three runs. No tool ranks a player's opponents.
  - Two turns lost a run: c4 turn 1 seed 2 named a team only by its ID ("team **34656**"), and c4 turn 3 seed 0 looked up only CEO 2025's singles event, so Raydish's 2nd place in doubles went missing.
- **Checks fired** (steps):

| Run | lookup | event | no-tool | pairing | answer | number | reply about a check |
|---|---|---|---|---|---|---|---|
| Before | 3 | 0 | 11 | 0 | 3 | 3 | 2 |
| Cues | 0 | 3 | 9 | 0 | 4 | 4 | 1 |
| Model rewrite | 0 | 3 | 3 | 0 | 2 | 5 | 0 |

**Cues or the model rewrite.** Both runs settle replies to suggestions the same way, in code, and turn 1 is identical, so they differ on the 39 later turns: cues 31, the rewrite 29.
- The cues gave 15 of the 39 a note (12 follow-ups, 3 pronouns); 3 were replies to suggestions and 21 went as asked. The rewrite made 36 calls, one per later turn but the replies to suggestions, 20 s in all: 19 rewritten, 17 kept as written.
- **Where the rewrite went wrong:**
  - It narrowed "who got 2nd at ceo 2025" to "who got 2nd at ceo 2025 / Brawlhalla Singles" in 2 of 3 seeds, losing Raydish's 2nd place in doubles.
  - In c5 turn 3 seed 2, its "What about the North America - Crew Battle Invitational?" read as already answered. The model called no tool and invented that the event was part of the BCX 2022 qualifiers, with no bracket link. The no-tool check couldn't catch it: every name and number was in the previous turn's results.
  - In c3 turn 2 seed 0, the answer placed the 5 2v2 sets at BCX 2024 and the Autumn Royale 2024. They were DreamHack San Diego 2023, BCX 2023, CEO 2024 and twice CEO 2025. The check passes it: the record is right.
- **Where it helped:** c1 turn 3, 2 runs against 1.
- Each difference is one run of three per turn, so the evidence is weak, but it points one way. **Decided 2026-11-20: keep the cues, and remove the model rewrite now that this entry records it.**

**The 45 questions**, automatic stages:

| Group | 2026-11-18 | 2026-11-19 |
|---|---|---|
| tuned | 50/51 | 49/51 |
| existing, known shape | 66/66 | 66/66 |
| existing, new shape | 15/18 | 15/18 |
| **all** | **131/135 (97%)** | **130/135 (96%)** |

- **Lost:**
  - q05 seed 1 listed the top 10 earners as "**PlayerID 74433**" and so on, naming no one. Fix 4 names "Player 74433" and "**74433**" only (decision 4 below).
  - q44 seed 0's WHERE asked one row to be both Ahmet_ and Zivai, so its COUNT gave 0, and the answer said never (it's 3).
- **Gained:** q45 seed 0, whose query now selects player_id, so stage 2 ties the $83,825 to Raydish.
- **The no-tool check** fired in 12 runs (6 on 2026-11-18). In the nine of q09, q32, q35 and q36, the model then looked the name up and said what the data doesn't hold. q36's two false alarms of 2026-11-18 are gone: no number check fired on it.
- **The event check** fired on q34 seeds 0 and 1 ("worlds 2016"), sent back once each. The harness's count of 5 includes the entries that kept the answer after it.
- **The number check** sent back 7 answers (2 on 2026-11-18) and replaced claims in 5 (2):
  - q26 seed 0 was a real catch: "since 2017" became 2020, the year of BBBalloonBoy's first official result.
  - q42 seed 0's "Worlds 2020 and 2021 each had 5 regional..." was dropped.
  - q14 seed 1's invented reason for no 6th and 8th ("not awarded due to tiebreakers") was replaced.
  - So were q39 seed 0's "0 in crew battles", with Boomie's whole line, and q34 seed 1's sentence citing the prompt's "Winters 2023 NA", as "I couldn't confirm the number of NA from the data."
  - q05 seeds 0 and 2 were false alarms, from a bug in fix 3 (below).
- The pairing check, the answer check, the lookup check and the name filter never fired. The names correction swapped 12 names in 9 runs (12 in 7 on 2026-11-18).
- **Tool use per run**, 2026-11-18 and now: resolve_player 0.67 → 0.71, resolve_event 0.16 both, event_results 0.33 → 0.30, player_results 0.22 → 0.21, head_to_head and rank_players 0.07 both, run_sql 0.27 → 0.26. Steps 2.63 → 2.75, output tokens 1,183 → 1,281.
- **Model time** went from 12.1 s to 22.1 s per run, but that's the server. It generated about 106 tokens a second on 2026-11-18, 82 in the before conversations, 70 in the cues run and 61 in the last two, with the same Ollama and model.

**A bug from fix 3:** `number_check.stated()` read " **acno?**" as a question and blanked it, with the space after "3.", so the 3 was no longer a list's numbering. The number check sent it back and replaced it. q05 seeds 0 and 2, two right top-10 lists, came out with "I couldn't confirm the number from the data.. **acno?** - $189,215.00". It was on the live page too, since the web app had merged f04eea3. Decision 3 below fixes it.

**Hand verdicts**, drafts for the user to review (`eval/results/20261119-webfixes-judgments.toml`), for the 19 runs not judged automatically whose stages changed or where a check fired:
- **right (13):** q09 seed 1, q14 seed 1, q26 seed 0, q32, q35 and q36 in every seed, q45 seed 0.
- **partly (4):**
  - q05 seeds 0 and 2: the verified list, but with the acno? bug's sentence in place of a rank, casting doubt on a right figure.
  - q34 seeds 0 and 1: they say 2016's championship isn't in the data, but not that the data starts in 2017, and suggest other spellings would find it. Seed 0 also invents a "BCX (Champions Cup)" series.
- **wrong (2):**
  - q39 seed 0, right on 2026-11-18: it says gdsandstorm has more medals, having read Boomie's 1v1 medals (34) as his total (80), with an invented split. The number check replaced that line, which hid the misreading but didn't cause it.
  - q44 seed 0: the contradictory WHERE above, SQL logic.

**Decided 2026-11-20** (the user's answers). Each was built after the runs, so none is measured yet:
1. Keep the cues; remove the model rewrite once this entry records it.
2. **c3 turn 2's check** (b0f93b7). 31b4ebc's strings ("2-3", "2–3", "won 2 and lost 3") failed 5 of the 6 right answers after, which wrote "Won 2 sets, lost 3 sets" or "2 wins, 3 losses". `says_record` reads the record in any wording, in a sentence about the 2v2 (2v2, team or side). It passes the 6 and fails the before run's 3: a question, a ranking and the 1v1 record, whose sets hold a 2 and a 3 too.
3. **The acno? fix** (3a7981b). A "?" ending one bold or quoted word is a name's, and a question's blanking keeps the spaces before it. Replayed on the run's sent-back answers, q05's two false alarms go and the other six flags stay.
4. **Names for "PlayerID 74433" and "Player ID 74433"** (6e4e12b), except inside parentheses or on a line naming the player ("Marckiem00 is player_id 4", "player_id 146606 (Boomie)"). On the recorded answers it turns q05 seed 1's ten IDs into the verified list.
5. **"cb" for "crew battle"** in `curation/event_terms.csv` (f3b880e): a general abbreviation like "ltc", not an alias for one event. resolve_event reads the curated terms eval-v1 lacks from the file. "cb 2022" now finds 2022's three Crew Battle Invitationals. The event check stays for everything else.

**What's open:**
- The no-tool check reads names and numbers only, so an answer from the previous turn's results can invent the rest (c5 turn 3 seed 2, and c3 turn 2 seed 0's events).
- For the strict replacement, a bold or quoted word that's also a player's name is a player. In c1 turn 5 seed 1 with cues, a turn with no tool call, "Games" became "I couldn't confirm this about Games from the data."
- A team named by its bold ID ("team **34656**") is neither named nor sent back.
- The replacement's wording ("the number of NA"; "the number" for a list's rank), and the prompt's own facts read as claims (q34 seed 1's "Winters 2023 NA"; 2026-11-18's q36 "from 2017").
- The harness counts the event check's entries that kept an answer.
- No tool ranks a player's opponents (c1 turn 2).
- Next: the user's live test, then a run of the conversations and the 45 questions at the user's go-ahead.

**Caveats:**
- 3 seeds. By the 2026-11-17 rule, a change of one run per turn is noise.
- The conversations' checks are automatic and written from the live failures, so they measure those failures, not right answers in general.
- The 45 questions' drafts are Claude's.
- The server's speed changed during the runs, so time per run isn't comparable.

## 2026-11-18: the number check, the name filter and the template outputs, on the 45 existing questions

**Change** (commits 43f3028 to fdd2496), the proposal approved 2026-11-17, so that the agent never states a fact no tool returned:
- **The number check** (`agent/number_check.py`, 43f3028; in the loop, 3e6de0d). Every number in an answer must come from a tool result in the conversation, or from the user's question, as it stands or by an allowed derivation: a placement from its word, a record of two numbers in one row, a date in any form or a timestamp's UTC date, a clock time only as a timestamp's UTC time, an amount or a rate at the precision shown, a scope phrase (top 5, at least 5, in 2024) from a call's arguments, and the medal places, top 3 and top 8 always. No arithmetic, and the prompt isn't evidence. An answer that fails goes back once, naming the numbers. Whatever text is final then has each sentence, list item or table cell holding one replaced by "I couldn't confirm <x> from the data".
- **The name filter** (9138179). A `run_sql` query that looks a player up by name doesn't run, and its error names the name to give `resolve_player`. This was the q01 gap: in `20261117-playercheck-smoke`, q01 seed 0 filtered on `players.name = 'Boomie'`, which seven players share, took 18411 instead of 146606, and named a 2017 event.
- **Template output** (79bb511). `player_results` leaves out each count its `top` fixes: under `top=1` only the wins are left, since the 1st places and top 8s equalled them and the 2nd and 3rd places were 0. Labels echoing an argument (the player, the mode) and each listed row's own placement stay, as decided, since stage 2 reads them. `player_results`' description adds "With top, it counts only those results, not the player's whole record.", `rank_players`' adds "It can't leave players out or take another condition, such as never having won: use run_sql.", and the prompt's line for `rank_players` adds "with no other condition". `event_results` gets no sentence, since no run has misrouted it, and `head_to_head` keeps the one from f05ae4a.
- **The prompt line on tool results as data** was already there (adf4cf0), pinned by a test: nothing to build.
- **The harness** (41abd64): `score` counts each check's firings, `report` shows them, and `replay RUN` runs the number check and the name filter on a run's traces without the model. a901a17 fixes scoring a `resolve_player` call given a number for a name (q40 seed 2 in the before run passed 74433).

**Tuned on the held-out set:** the prompt's "with no other condition" for `rank_players`, and its description's sentence, come from h15's finding in the held-out set's final measurement (the entry below). `player_results`' columns and its sentence come from h03's and h16's. So h03, h15 and h16 count as tuned from 2026-11-17, and the 45 existing questions measure only whether these changes break something.

**The replay gate**, before the after run (`harness.py replay`):
- On the before run, the number check flagged 7 of 135 final answers. Four were false alarms, and two of those would have replaced the sentence holding the answer's main claim:
  - q35 seed 0, with no tool called: "top 8 placements" as a category, in "...there is no recorded data linking players to their preferred legends";
  - q45 seed 1: "Therefore, Raydish has earned more money between the two.";
  - q20 seeds 0 and 2: "Impala (placement 2)" and "loser_placement = 2", restating the query's own condition.
- Fixed in fdd2496: top 3 and top 8 are categories the prompt defines, always allowed; a number word after "the", "these" or "those" refers back to what was named; placement N and rank N are scope phrases; and claims are blanked with a character no pattern skips, since a space had let "placed 2nd of 32" read as a placement of 32.
- After the fixes it flags 3 of the before run's answers, none of them right: q41 seed 0's "12 players" tied for second, counted from the rows (the list names 13, and only yüz has 2 wins; partly); q14 seed 2's STING RAY "6th", a place no one has (5th and 7th are tied; partly); and q44 seed 0's "(2026, 2, 1, 3)" in an answer that called no tool (wrong).
- On the two earlier runs of the 45 questions, the 9 flags stayed as they were: 6 numbers no tool returned (q20's three clock times, q04 seed 1's games won, q34 seed 1's "Worlds 2023" and "Worlds 2022", q32 seed 2's career earnings) and 3 totals the model added up (q21 seeds 1 and 2, q39 seed 0).
- The name filter flags one query in the before run: q01 seed 0 repeated the smoke test's `players.name = 'Boomie'`, and answered with 18411's 2017 event.

**Runs:** both on the 45 existing questions, retrieval on, seeds 0–2, 135 runs each, Ollama 0.40.16, 30 worked examples. No run failed or was retried.
- Before: `20261117-grounding-before`, at 049c647 (the tree clean but for an untracked document the agent doesn't read).
- After: `20261118-grounding`, at fdd2496.

**Automatic stages** (a run passes when neither stage 1 nor stage 2 fails):

| Group | Before | After |
|---|---|---|
| tuned | 47/51 | 50/51 |
| existing, known shape | 65/66 | 66/66 |
| existing, new shape | 15/18 | 15/18 |
| **all** | **127/135 (94%)** | **131/135 (97%)** |

- 5 runs gained: q01 seed 0, q15 seeds 0 and 1, q44 seeds 0 and 1. One was lost: q45 seed 0. No question lost 2 or more runs.
- No new check fired in any of the six. q01 seed 0's before run was the name lookup above, which the filter would have refused; after, it called `resolve_player` first. q15 and q44 took other paths after: before, q15 seed 0 took Godly to be Phazon without resolving the name, q44 seed 0 called no tool, and q44 seed 1's join asked one row to be both players. So the gain isn't the checks' doing. The tool descriptions and the prompt line differ between the runs, so the trajectories part from the first step. By the 2026-11-17 rule a change of one run is noise, and q15's and q44's two runs each aren't explained by this run.
- q45 seed 0's loss is scoring. Its answer is right ($83,825 for Raydish, and Impala's not recorded), but its query filtered on Raydish's player_id without selecting it, so stage 2 can't tie the 83,825 to Raydish.

**Tool use**, per run, before and after: `resolve_player` 0.64 → 0.67, `resolve_event` 0.09 → 0.16, `event_results` 0.34 → 0.33, `player_results` 0.22 and `head_to_head` and `rank_players` 0.07 unchanged, `run_sql` 0.28 → 0.27. Steps 2.59 → 2.63, and model time 12.6 s → 12.1 s.

**The new checks in the after run:**

| Check | Runs it fired in | Times |
|---|---|---|
| number check, sent back | 2/135 (1%) | 2 |
| number check, claims replaced | 2/135 (1%) | 2 |
| name filter, queries refused | 0/135 (0%) | 0 |

- Both firings were on q36, "How many community tournaments has raydish won?", seeds 0 and 1, in answers that called no tool, and both were false alarms. Seed 0 cited the prompt's "official events from 2017 onward", and seed 1 wrote `top=1` as tool syntax. Each answer went back, came back with the number, and had that sentence replaced.
- Neither broke a right answer: all four answers, as first written and final, say the data has no community tournaments, as q36's verified answer needs. But each final answer gained a sentence that reads as noise.
- The check caught nothing in the after run, since no other answer stated an unsupported number. Its catches show only in the replays above.
- Replayed, the after run flags nothing: no final answer states a number no tool returned.

**Replaced answers, verbatim** (the after run's two, then the replays', which replace without the send-back the loop would make first):
- After, q36 seed 0, final: "The data does not track community tournaments. I couldn't confirm the cutoff from the data. Raydish’s wins, if any, would only be counted in official events. To answer this question accurately, you’d need access to community tournament records outside the tracked data." The replaced sentence was "The tools and database only include **official events** from 2017 onward, and there is no record of "community" tournaments in the results."
- After, q36 seed 1, final: "The data does not track community tournaments. Official events are the only ones included in the results database. There is no record of Raydish's participation or wins in community tournaments. I couldn't confirm the number from the data." The replaced sentence was "To find their official event wins, use `player_results(player_id=...)` with `top=1`, but community tournament statistics are not available."
- 2026-11-17's templates run, q20 seed 2: "The 1v1 grand final at **DreamHack Valencia 2023** was won by **Zivai** with a score of **3-0** against **Impala**. I couldn't confirm the time from the data." The replaced sentence was "The match started at **July 7, 2023, 1:47:45 PM UTC**."
- The same run, q04 seed 1: the line "- **BBBalloonBoy's record**: 1 win, 2 losses, 3 sets, 5 games won, 8 games lost." became "- I couldn't confirm the number of games won from the data."
- The before run, q14 seed 2: the line "6. **STING RAY** (6th)" became "6. I couldn't confirm the placement from the data."
- 2026-11-10's run, q39 seed 0, judged right: "I couldn't confirm the number of total medals from the data. Boomie holds the lead in total official medals across both modes." The replaced sentence held the right totals the model had added up, 80 and 69, and with them the per-mode figures a tool had returned (34 and 46, 42 and 27).

**The check's limit:** it checks where a number came from, not what it means. In 2026-11-17's templates run, q20's three answers dated the final July 7, 2023, which passes because a result holds that date as the event's start, though the set was played on July 9: only their clock times were caught. In the after run, no q20 answer gives a date or a time.

**Hand verdicts**, all drafts needing the user's review, only for runs whose verdict changes:
- The six runs whose automatic stages changed, where they pass them: after, q01 seed 0 right, q15 seed 0 right, q15 seed 1 partly (only the 2v2 win, saying the question asked about the 2v2), q44 seeds 0 and 1 right; before, q45 seed 0 right.
- The two runs with a firing, before and after: q36 seeds 0 and 1, right both times.
- For whether the replay's flags hit right answers, the two flagged before-run answers that pass the automatic stages: q41 seed 0 and q14 seed 2, both partly.
- The third rule found no run. A before answer using a column the template change removes would have needed a draft, but under `top=1` no answer stated a 2nd- or 3rd-place count or a best, and under `top=3` or `top=8` only the top-8 count goes, which no answer cited.

**What's open, for the user to decide:**
1. Numbers in inline code (tool syntax such as `top=1`) and the prompt's own facts (official events from 2017 on) are read as claims, and made q36's two false alarms. Exempt them?
2. The replacement's wording: "the cutoff" and "the number" don't say what was dropped, and a replaced sentence takes its supported figures with it (q39 seed 0).
3. Stage 2 for a query that filters on a player_id without selecting it (q45 seed 0).
4. Whether q15's and q44's gains hold in another run.

**Caveats:** the existing set only, 3 seeds, judged by Claude. Before and after differ in the tool descriptions and the prompt line, so the same seed isn't a paired sample; within one trace, though, an answer before and after a check is. The replays apply the replacement without the send-back. The held-out set wasn't run, and is spent.

## 2026-11-17: the held-out set's final measurement, after the template tools

**The held-out set is now spent for tuning.** Its questions, checks and traces were read to score this run, so a change made for anything below would be tuned on it. Measuring such a change needs new held-out questions. Nothing in the agent changed because of this run.

**Question:** how does the agent with the template tools do on the 16 questions it was never tuned on, against the same questions on 2026-11-08?

**Setup:**
- **The agent** at commit f05ae4a: the template tools and the two views (the entry below), then the three fixes decided after them. A tool call on a player_id that no tool returned and the question doesn't give is refused (0a32b79), ex29 orders by `start_time` without selecting it (e59f39d), and `head_to_head`'s description says it counts sets, not placements (f05ae4a). Ollama 0.40.16, 30 worked examples.
- **The run:** `20261117-heldout`, the 16 held-out questions, retrieval on, seeds 0–2, 48 runs. No run failed or was retried. Before it, a smoke test of the player check on q01, q06 and q39 at seed 0 (`20261117-playercheck-smoke`) refused nothing and crashed nothing. In the run itself the check never fired.
- **The baseline:** the same 48 runs in `20261108-eval-on`, at commit adf4cf0, Ollama 0.40.15, 28 examples. It predates the prompt's earnings and coverage lines (step 1) and the names work (step 2) as well as the templates, so this compares all three changes together, not the templates alone.
- **Scoring** as on 2026-11-08: the automatic stages 1 and 2, and every run's verdict drafted by hand, all 48 marked "needs review". The 2026-11-08 verdicts are that session's drafts, compared as they stand, not re-judged.
- **Reading the set:** until the run was done, this session opened no held-out file or trace. The held-out lines of `tests/test_harness.py` were masked, and the leak test's output filtered to test names. Then `heldout.toml`, `eval/heldout_checks.py` and both runs' held-out traces were read to score it.

**Results** (each question kept its group in both runs: 11 known shape, 5 new):

| Group | 2026-11-08: runs right | Runs partly | Questions right in every seed | 2026-11-17: runs right | Runs partly | Questions right in every seed |
|---|---|---|---|---|---|---|
| held-out, known shape | 26/33 (79%) | 5/33 (15%) | 6/11 (55%) | 24/33 (73%) | 5/33 (15%) | 8/11 (73%) |
| held-out, new shape | 10/15 (67%) | 3/15 (20%) | 3/5 (60%) | 8/15 (53%) | 7/15 (47%) | 2/5 (40%) |
| **all** | **36/48 (75%)** | 8/48 (17%) | 9/16 (56%) | **32/48 (67%)** | 12/48 (25%) | 10/16 (62%) |

| First stage that failed | 2026-11-08: 12 of 48 runs not right | 2026-11-17: 16 of 48 |
|---|---|---|
| name resolution | 0 | 0 |
| SQL logic | 5 | 4 |
| empty or insufficient data | 3 | 3 |
| answer writing | 4 | 9 |

The automatic stages passed in 40 of 48 runs before and 41 after. Fewer runs are right, but more questions are right in every seed: the misses now fall on whole questions.

| Question | 2026-11-08, seeds 0 / 1 / 2 | 2026-11-17 | Runs right |
|---|---|---|---|
| h01 pugsyxd's 2v2 titles | right / partly / right | right / right / right | 2 → 3 |
| h02 halloween!'s top 8s | right / right / right | right / right / right | 3 → 3 |
| h03 neze's best 1v1 finish | partly / partly / partly | partly / partly / partly | 0 → 0 |
| h04 Legion \| kaito vs sacwastaken | right / wrong / wrong | partly / partly / partly | 1 → 0 |
| h05 eu springs 2024 | right / partly / right | right / right / right | 2 → 3 |
| h06 the autumn royale | right / right / right | right / right / right | 3 → 3 |
| h07 NA crew battle invitational | right / right / partly | right / right / right | 2 → 3 |
| h08 powerbh's best year | right / right / right | right / right / right | 3 → 3 |
| h09 powerbh's title partners | right / right / right | right / right / partly | 3 → 2 |
| h10 keiththepoopoo's most beaten | right / right / right | right / right / right | 3 → 3 |
| h11 most 1v1 wins in 2024 | right / right / wrong | right / right / right | 2 → 3 |
| h12 himwy's 2024 set record | right / right / right | right / right / right | 3 → 3 |
| h13 Santy at the 2021 Pro Series finals | partly / wrong / partly | wrong / partly / partly | 0 → 0 |
| h14 Fozey's country | right / right / right | right / right / right | 3 → 3 |
| h15 most top 8s, never a win | right / right / right | wrong / wrong / wrong | 3 → 0 |
| h16 Piggers, a 1v1 win? | right / right / right | partly / partly / partly | 3 → 0 |

**Tool use**, per run: `run_sql` 1.10 → 0.40, and template calls 0.75 (`player_results` 0.38, `event_results` 0.19, `rank_players` 0.12, `head_to_head` 0.06). Steps per run 3.10 → 2.90, and model time per run 31.8 s → 15.9 s. `run_sql` errors went from 8 to 3.

**What got better:**
- h04: in 2026-11-08 every query of seeds 1 and 2 timed out, and both answers invented a record. `head_to_head` gives 5-4 to sacwastaken in every seed.
- h05 seed 1 and h07 seed 2 had named one winner of a team or crew. `event_results` keeps a team whole.
- h11 seed 2 had given Zivai the lead alone, with whoiskyna at 6 instead of tied at 7. `rank_players` keeps the tie.
- h01 seed 1 echoed "pugsyxd". It names Pugsy now, as the names work of step 2 asks.

**What got worse:**
- **h15, 3 of 3 wrong.** "Who has the most official top 8s without ever winning an official event?" went to `rank_players(by="top8s")`, which ranks everyone and can't leave out winners. Every answer then said the ranked players never won: acno? in seed 0 (36 wins), after reading `player_results` that show them; the whole top 5 in seed 1; and Boomie in seed 2 (44 wins), "verified via player_results", a call it never made. On 2026-11-08 all three wrote an anti-join in SQL and were right. The prompt's line "who has the most wins, medals or top 8s: rank_players" matched the question's start, and nothing says the template can't take a condition.
- **h16 and h03, 6 of 6 partly.** Both called `player_results` with `top=1`. Its summary's 2nd, 3rd and top-8 columns then count only within the wins, so they're 0 by construction, and the answers read them as the player's whole record. Piggers has "0 medals and 0 top 8s" in 1v1, though Piggers's best 1v1 finish is 2nd. Neeze has "no other top-3 placements", though Neeze has four 2nd and six 3rd places. h16's answers also turned the note's "48 official results (27 in 1v1, 21 in 2v2)" into "48 official 1v1 results". The main fact, no 1v1 win and a best of 1st, is right in all six.
- **h04, 3 of 3 partly.** The record is right, but each answer misdescribes the 9 sets it lists: a set given to both players, sacwastaken given kaito's win rate, and a set that doesn't exist.
- **h09 seed 2, partly.** It counted four rows of bare partner IDs by reading them, and told the user to look up the names.

**Unchanged:** h13, 0 of 3 right both times. The Pro Series finals have placements but no matches, so every run finds 0 sets and says, or hedges, that Santy didn't take part, without the crew's win. 2026-11-08 proposed a prompt line for this. It wasn't built.

**Findings, not acted on** (any change for them would be tuned on this set):
- `player_results`' 2nd, 3rd and top-8 columns mislead under a `top` filter (h03, h16).
- `rank_players` took a question with a condition it can't express, and the answers invented the condition's result (h15).
- A long list of sets invites misreading (h04).
- The Pro Series finals still read as "didn't take part" (h13).

**Caveats:**
- The judge is Claude in both runs, but in two sessions, and strictness may differ. This reading counts a false secondary claim as partly. The 2026-11-08 draft of h16 seed 0 passed an answer claiming the database had 11 1v1 entries, none of them Piggers's, though Piggers has 27.
- Small groups: with 11 and 5 questions, one question moves a group's all-seed rate by 9 or 20 points.
- The two runs differ in steps 1 and 2, the views and templates, the three fixes, the bank (28 → 30 examples) and the server's patch version (0.40.15 → 0.40.16).
- The held-out set was written by Claude, and the templates were designed without it. Its 16 questions are now spent.

## 2026-11-17: two views and four template tools, so the model writes less SQL

**Change** (commits c0224ec to abb5109), the plan "two views and four template tools", approved 2026-11-09:
- Two views, created on eval-v1 as temporary views from `ingest/views.sql` (19d2dfd). `v_sets_1v1` has one row per 1v1 set with both players, the score and where each finished, and `v_event_series` the events of a yearly series. `resolve_event`'s condition for a whole series is a subquery on `v_event_series`. A worked example, ex29, finds a final's score.
- Four template tools in `agent/templates.py`, each a tested query the model calls with a few arguments: `event_results` (85f74c3), `player_results` (8d43de2), `head_to_head` (d2a3a99) and `rank_players` (b5bc36a). Each takes players as player_ids from `resolve_player` and events by name, keeps ties and teams whole, counts in SQL, says what an empty count is empty of, and leads with an event's status.
- The prompt's "Choosing a tool" section names the question each template answers. 18 worked examples, and a new one ranking players inside a series (ex30), show a template call instead of SQL. `retrieval.py check` requires each call's result to hold its reference query's rows (7c5fb42).
- The harness scores template calls: stage 1 from the SQL each ran, stage 2 from its tables (7178eb0). q39's check accepts its two totals from two calls.
- The held-out checks moved to `eval/heldout_checks.py` (c0224ec). The session that wrote the plan saw their expected values while reading stage 2 in `eval/result_checks.py`, before the move. Nothing in this step uses them.
- Two fixes from the pilots, below: `event_results` lists each event's `event_id` when the name means 12 events or fewer (3cbc853), and `resolve_event` takes the name as `event` too, with an error that names a wrong key (abb5109).

**Runs:** both on the 45 existing questions, retrieval on, seeds 0–2, 135 runs each. No run failed or was retried.
- Before: `20261110-templates-before`, at 3b2c552 with a clean tree, 28 worked examples, Ollama 0.40.15.
- After: `20261117-templates`, at abb5109, 30 worked examples, Ollama 0.40.16.

The server's patch version changed between the runs, so some differences at the same seed may come from it alone (a guess). As the plan says, a change of one run is treated as noise.

**Pilots** (q13, q20, q30 and q41, seed 0). q13, q30 and q41 passed all three.
- `20261117-templates-pilot`: q20 failed stage 2. It planned to take the event_id from `event_results`, which gave none, and filtered `tournament_name` on the template's label, "DreamHack Valencia 2023 / Brawlhalla (1v1)". Fixed in 3cbc853. A whole series still gets no IDs, and a note to use `resolve_event`'s condition: Worlds' 34 IDs took its result to 4,888 tokens, over the 4,000 budget, which left its winners out.
- `20261117-templates-pilot2`: q20 called `resolve_event` with `{"event": ...}` seven times, read the error as a rule about the value, and ran out of steps. Fixed in abb5109.
- `20261117-templates-pilot3`: q20 passed stages 1 and 2.

**Automatic stages** (a run passes when neither stage 1 nor stage 2 fails):

| Group | Before | After |
|---|---|---|
| Targets: q20, q30, q31, q41 | 7/12 | 12/12 |
| Regression checks: the 26 other questions a template takes over | 74/78 | 77/78 |
| Controls: the 15 no template fits | 43/45 | 41/45 |
| **All** | **124/135 (92%)** | **130/135 (96%)** |

- 9 runs gained: q20 seeds 0–2, q41 seeds 1 and 2, q03 and q07 seed 2, q16 and q18 seed 1.
- 3 runs lost, each the only seed its question lost, so none is a regression by the plan's rule: q27 seed 2, a regression check, and q42 and q44 seed 2, controls. Read below.
- By template, the questions each takes over: `event_results` +2 runs, `player_results` +2, `rank_players` +2, `head_to_head` −1 (q27 seed 2).

**Tool use**, calls per run:

| Tool | Before | After |
|---|---|---|
| resolve_player | 0.66 | 0.64 |
| resolve_event | 0.40 | 0.09 |
| event_results | | 0.33 |
| player_results | | 0.22 |
| head_to_head | | 0.07 |
| rank_players | | 0.07 |
| run_sql | 0.95 | 0.28 |

- `run_sql` calls per run, the direct count of SQL the model wrote: targets 1.25 → 0.25, regression checks 0.97 → 0.00, controls 0.82 → 0.78. Every regression check called its template in every seed, except q22, which asked the user in all six runs, as accepted.
- Steps per run 2.87 → 2.54, and model time per run 25.0 s → 14.3 s (56 minutes in all → 32).
- No template or resolver call returned an error. `run_sql` errors went from 9 to 4, all in SQL the model wrote.

**Hand verdicts**, all drafts needing the user's review: the 24 target runs, the 3 runs lost at the automatic stages, and seed 0 of the 26 regression checks, before and after. The other runs have only their automatic results.

| Target | Before, seeds 0 / 1 / 2 | After | Runs right |
|---|---|---|---|
| q20 DreamHack Valencia 2023 final score | wrong / wrong / partly | partly / partly / partly | 0 → 0 |
| q30 who won ceo dreamland 2020 | partly / wrong / partly | right / right / right | 0 → 3 |
| q31 who won SEA League Week 1/4 | partly / partly / partly | right / right / right | 0 → 3 |
| q41 most 1v1 world championships | right / wrong / wrong | right / right / right | 1 → 3 |
| **Targets, 4 questions** | | | **1/12 (8%) → 9/12 (75%)** |

- q20, after: Zivai 3-0 Impala from `v_sets_1v1` in all three, but each answer adds a time for the set (11:47 AM, 16:47 or 1:47 PM UTC, on July 7) that `start_time` doesn't say. The set began on 2023-07-09 at 19:27 UTC. The query selects `start_time`, as ex29's does, and the model converts it wrongly.
- q30, after: every run says the event was cancelled and not held, then gives the ONLINE event's winners. Before, all three gave those winners as CEO Dreamland 2020's.
- q31, after: no reliable winner, and TigerBrawlhalla the only undefeated player (6-0), from the event's data note, which `event_results` passes on. Before, all three stopped at "no winner".
- q41, after: gdsandstorm 3 and yüz 2, saying the regional championships are counted. Before, seeds 1 and 2 copied part of `resolve_event`'s IDs (2021 on) and answered yüz.

Seed 0 of the 26 regression checks: 19 right and 7 partly before, 24 right and 2 partly after, none wrong.
- Better, partly → right: q02, q07, q25, q26 and q38 now mention the crew battle among the counts, as the templates' notes ask. q04 lists the three sets, and q12 says which reading it took.
- Worse, right → partly: q24 adds that other midseason events "aren't officially documented here", though the Midseason Championship 2026 is. q39 says Boomie's 46 2v2 medals surpass gdsandstorm's 69 in all.
- The other 17 were right both times.

The 3 runs lost at the automatic stages, all wrong:
- q27 seed 2: the model skipped `resolve_player` and called `head_to_head` with invented player_ids, 12345 and 67890. Both are real players (Hippo and mely), so the template answered for them, and no check fired, since a tool had returned those names.
- q44 seed 2, a control: `head_to_head` for "how many times did Ahmet finish second to Godly". It counted Zivai's set wins over Ahmet_ in 2026 by reading the list (4), not the events where Ahmet_ placed 2nd behind Zivai (3).
- q42 seed 2, a control: an answer with no tool, sent back, then events ranked by their count of top-8 placements, a proxy, with a claim that the data has no entrant counts. No template took part, and q42 seed 0 fails both before and after.

**What it decided, and what's open:**
- By the plan's noise rule, no question regressed. By its template rule, `head_to_head` would come out, since its questions lost one run overall. That run's cause isn't `head_to_head`'s query: the model invented the IDs, which any template taking a player_id allows. For the user to decide. Proposed: keep `head_to_head` and close the cause.
- Proposed next steps, for the user to decide:
  1. A template refuses a player_id that no tool returned in the conversation, pointing to `resolve_player` (q27 seed 2).
  2. ex29 orders by `start_time` without selecting it, so a final's answer has no raw timestamp to misread (q20, all three after).
  3. `head_to_head`'s description says it counts sets between two players, not where they placed at the same events (q44 seed 2).
  4. Then the held-out set: the templates were designed from the existing set's shapes, and it's the real test.

**Tuned on:** q30, q31 and q41 count as tuned from 2026-11-17, q20 from 2026-11-09. The regression checks' gains are in-sample too.

**Caveats:** the existing set only, 3 seeds, judged by Claude. The hand verdicts cover the targets, the lost runs and seed 0 of the regression checks, so the rest have no "runs right" count. The two runs differ in the prompt, the tools, the bank (28 → 30 examples) and the server's patch version. The held-out set wasn't run.

## 2026-11-09: step 2, clear-cut names, the display, and names corrected in code

**Change** (commits 9d88685, c1d4036, 34c324e and 8b6b9e8), from the 2026-11-08 entry's second proposal, with the user's changes:
- `resolve_player`: a name several players share resolves to the first alone when it has at least 5 times the next one's official results (`CLEAR_CUT`). Each candidate has a display, such as "Zivai (formerly Godly)", and the confident note says to call them by it.
- The prompt: use the display the first time, without explaining the match; for an ambiguous name, one short clause.
- Names corrected in code instead of sent back: the question's spelling of a player the resolver decided becomes the display at its first mention and the name after, and a wrong name just before a player ID becomes the data's name for it. Every swap is in the trace. A name with no ID that no tool returned still goes back once.
- A reply to a check that talks about the answer instead of giving one, with no new number, keeps the answer sent back.
- The harness counts a player ID as a name only if a tool returned that name.

**Run:** `20261109-step2`, retrieval on, seeds 0–2, 45 runs: 4 targets, 8 regression checks whose names go through the changed code, and 3 controls with no player in the question. No run failed or was retried. Judged as before, all drafts needing the user's review.

| Question | Before (20261108-eval-on), seeds 0 / 1 / 2 | After | Runs right |
|---|---|---|---|
| q15 did godly win eu summers 2026 | right / wrong / wrong | right / right / right | 1 → 3 |
| q44 Ahmet second to Godly in 2026 | wrong / right / right | right / right / wrong | 2 → 2 |
| q21 baloonboy's official wins | partly / partly / partly | right / right / right | 0 → 3 |
| q20 DreamHack Valencia 2023 final score | partly / wrong / wrong | partly / wrong / wrong | 0 → 0 |
| **Targets, 4 questions** | | | **3/12 (25%) → 8/12 (67%)** |
| q01 Boomie's last event | right / right / right | right / right / right | 3 → 3 |
| q03 Hexo's 1v1 top 8 | partly / right / right | right / right / right | 2 → 3 |
| q04 Impala vs Balloonboy | right / right / right | right / right / right | 3 → 3 |
| q12 flowers' first top 8 | right / right / right | right / right / right | 3 → 3 |
| q23 kingdom \| godly vs impala | right / right / right | right / right / right | 3 → 3 |
| q26 M30W \| BalloonBoy's top 3s | right / right / right | right / right / right | 3 → 3 |
| q27 bbballoonboy vs impala | right / right / right | right / right / right | 3 → 3 |
| q39 boomie or sandstorm, medals | right / right / right | right / right / right | 3 → 3 |
| **Regression checks, 8 questions** | | | **23/24 (96%) → 24/24 (100%)** |
| q13 winters 2023 na 1v1 (control) | right / right / right | right / right / right | 3 → 3 |
| q17 top 8 at bcx 2025 1v1 (control) | right / right / right | partly / right / right | 3 → 2 |
| q38 top 5 by 1v1 wins (control) | right / right / right | right / right / right | 3 → 3 |
| **Controls, 3 questions** | | | **9/9 (100%) → 8/9 (89%)** |

**Names:**
- The model named players by their display itself in most runs. The code corrected 10 names in 4 of the 45 runs: q44 seeds 0 and 1 (Ahmet and Godly), q39 seed 1 (sandstorm) and q04 seed 2 (Balloonboy). On the same questions in 2026-11-08, replaying the same rule, 23 of 45 answers used the question's spelling.
- Every corrected answer was right, but q44's read "Zivai (formerly Godly) (Zivai)", from the model's "Godly (Zivai)". Fixed in 8b6b9e8: replayed on those replies, the code now gives "Zivai (formerly Godly)".
- No reply talked about the answer instead of giving one, so the model didn't exercise that fix here. Its tests pass.

**Still not right:**
- q20, all 3: seed 0 gave the score without the players, seed 1 named Impala the winner though Zivai won, and seed 2 ended in an empty reply after its queries failed (the missing opponent column again). Step 4's worked example targets this.
- q44 seed 2: the names were right, but the count filtered `format = '1v1'` (1v1 is the mode), counted 0, and no diagnosis runs on a COUNT.
- q17 seed 0, a control: 2nd place written "BBA balloonBoy", though the result had BBBalloonBoy. The model made the same slip in 2026-11-08 (q26), and step 2 doesn't touch this question (inferred).

**Checks widened** after reading this run, to results right answers came from: q15 accepts Zivai's placements at the two events as two rows of 1, and q17 accepts Mounir as the 7th-place witness, since "yüz" can't match inside "yüz / Mounir". Replayed on the 2026-11-08 runs, neither changes a stage-2 result.

**The harness fix on the 2026-11-08 numbers** (replayed, files and tables unchanged): one run changes, q14 seed 1 with retrieval off (bare player IDs), from passing stage 2 to failing it. Its verdict goes from not judged to wrong (SQL logic), so that arm's not-judged count is 16, not 17. No right count, and no retrieval-on number, changes.

**Tuned on:** q15, q20 and q44, counted as tuned from 2026-11-09 (q21 already was). The regression checks and controls weren't tuned on.

**Caveats:** 15 questions and 3 seeds, judged by Claude. The targets are the failures the change was written for, so their gain shows it works where aimed. The held-out set wasn't run.

## 2026-11-09: step 1, the prompt learns about career earnings and what the data doesn't cover

**Change** (commit 268b3a9), from the 2026-11-08 entry's first proposal. The system prompt's views now include `v_career_earnings`, with the rules that a missing figure isn't $0, that a ranking covers only players with a figure, and that there is no prize money per tournament. Two notes say that legends aren't recorded and that every event is official whatever its name says, so community tournaments aren't in the data. A rule says to answer what the data doesn't cover by saying so, and what it does have, never from a nearby table. Nothing else in the agent changed. A new test checks that the prompt describes every view of eval-v1 except `v_player_ids` and `v_event_coverage`, left out on purpose. It failed before the change, on `v_career_earnings` alone.

**Run:** `20261109-step1`, retrieval on, seeds 0–2: the 7 questions the change targets and 3 answerable controls (q02, q26, q37), 30 runs. Judged as before, all drafts needing the user's review. For q09, "the data has no prize money per tournament" counts as right, as the user decided.

| Question | Before (20261108-eval-on), seeds 0 / 1 / 2 | After | Runs right |
|---|---|---|---|
| q05 top 10 earners | wrong / wrong / wrong | partly / partly / partly | 0 → 0 |
| q09 sandstorm's best-paying tournament | partly / partly / partly | right / right / right | 0 → 3 |
| q33 Boomie's earnings | partly / partly / partly | right / right / right | 0 → 3 |
| q34 the 2016 World Championship | partly / right / right | right / partly / right | 2 → 2 |
| q35 godly's legend | wrong / wrong / wrong | right / right / right | 0 → 3 |
| q36 Raydish's community wins | right / wrong / wrong | right / right / right | 1 → 3 |
| q45 Raydish or Impala, earnings | wrong / wrong / wrong | right / wrong / right | 0 → 2 |
| **Targeted, 7 questions** | | | **3/21 (14%) → 16/21 (76%)** |
| q02 Raydish's majors (control) | partly / right / partly | right / right / right | 1 → 3 |
| q26 BalloonBoy's top 3s (control) | right / right / right | right / right / right | 3 → 3 |
| q37 most official wins (control) | right / right / right | right / right / right | 3 → 3 |
| **Controls, 3 questions** | | | **7/9 (78%) → 9/9 (100%)** |

Under the user's calls on the before runs (q02's "across 1v1 and 2v2" and q09's "no prize money" both right), the before counts are 6/21 and 9/9. Questions right in every seed: 2 of 10 before, 7 of 10 after.

**What changed in the answers:**
- Every earnings run used `v_career_earnings`. q05 gave the exact top 10 in all 3 seeds, q33 said Boomie has no figure, and q45 gave Raydish's $83,825 with no figure for Impala. Before, all 12 runs said no earnings are recorded.
- q35 said in all 3 seeds that legends aren't recorded, without calling a tool. Before, all 3 looked up a player named "godly main".
- q36 said in all 3 seeds that community tournaments aren't in the data.
- No control got worse. q02 dropped its claims of 2v2 wins.

**Still not right:**
- q05, 3 partly: the list and its coverage are right, but the verified answer asks it to name Boomie as missing. Boomie has no row, so nothing in the data points the agent to him.
- q45 seed 1: "Raydish has earned more", counting Impala's missing figure as $0 despite the new line.
- q34 seed 1: explains the missing 2016 as "Brawlhalla's major official events began in 2017".

**Changed after this run** (2026-11-09, the user's decision): q05's verified requirement no longer asks the answer to name Boomie as missing. It asks the answer to say the list covers only players with a figure, since Boomie has no row and nothing in the data could point the agent to him. All three q05 runs say so, so under the new requirement they are right, and the targeted questions are 19/21 (90%) right. The table above keeps the verdicts as first drafted.

**Tuned on:** this step tuned on q05, q09, q33, q35, q36 and q45. The harness counts them as tuned in runs from 2026-11-09 on: `TUNED` now holds the day each question was tuned on, so the 2026-11-08 runs keep their groups (checked: their group table is unchanged). `NEAR_CLEAN`, the retrieval-off arm's list, no longer names them (changed after this run).

**Caveats:** 10 questions and 3 seeds, judged by Claude. The gains are on the questions the change was written for, so they show it works where aimed, not that it carries over. The held-out set wasn't run.

## 2026-11-08: the full evaluation, on the evaluation set and a held-out set, retrieval on and off, seeds 0–2

**Question:** where does the agent fall short, measured on questions it wasn't tuned on?

**Setup:** the agent as of commit adf4cf0, unchanged since the retrieval runs: qwen3:8b with thinking, Ollama 0.40.15, eval-v1, the x64 Python 3.14.
- **Questions:** 61, the 45 of the evaluation set and 16 of a held-out set (`eval/questions/heldout.toml`, written and verified on 2026-11-08). `tests/test_harness.py` checks that no held-out question, player, player ID or event is in the example bank, and that its players are new to the evaluation set.
- **Groups:** the 5 questions the agent was tuned on (q04, q06, q08, q21, q22). Every other question is "known shape" when retrieval returns an example of a helpful shape (`eval/questions/shapes.toml`) at 0.70 or more, and "new shape" when it doesn't: 27 and 13 of the existing set, 11 and 5 of the held-out set.
- **Runs:** retrieval on, all 61 questions × seeds 0–2 (run `20261108-eval-on`, 183 runs), then retrieval off, the 16 held-out and the 13 near-clean existing questions (q05, q09, q14, q15, q23, q32–q36, q39, q42, q45) × seeds 0–2 (`20261108-eval-off`, 87 runs). No run failed or was retried.
- **Scoring** (`eval/harness.py`): each run gets a verdict (right, partly, wrong) and the first stage that failed, in the pipeline's order:
  1. name resolution, automatic: the players and events the question names became the right IDs in the queries;
  2. SQL logic, automatic: the tool results hold the facts the answer needs (`eval/result_checks.py`, one check per question, each passing on its question's reference queries);
  3. empty or insufficient data, by hand: a "none", a "not held" or missing data told apart from a lookup mistake, said, and not filled in;
  4. answer writing, by hand: the answer states what the results show, with what the question requires.
- **Judging:** right is the verified answer, or an accepted one with its assumption, with what the question's notes require (the player's name, where they ask for it). Partly is the main fact right with a required part missing or a secondary fact wrong. Wrong is the main fact wrong or missing.
- **All verdicts are drafts pending the user's review: 248 of 270 are marked "needs review"**, and the other 22 are automatic stage-1 or 2 failures. They are in `eval/results/20261108-eval-on-judgments.toml` and `20261108-eval-off-judgments.toml`, next to each run's answer.
- **The retrieval-off arm isn't fully judged.** 17 runs have no verdict: 16 in seed 2 (q23, q33, q34, q36, q39, h01–h03, h06–h10, h14–h16) and q14 seed 1. 11 more in seed 2 carry machine verdicts nobody read: 8 automatic (q14, q15, q42, q45, h04, h05, h11, h12) and 3 drafts (h13, q32, q35). q32's draft says wrong, but its answer reads like the right one. All 9 automatic verdicts of the retrieval-on arm were read.

**Results, retrieval on** (183 runs):

| Group | Runs right | Runs partly | Questions right in every seed |
|---|---|---|---|
| tuned | 10/15 (67%) | 5/15 (33%) | 3/5 (60%) |
| existing, known shape | 67/81 (83%) | 4/81 (5%) | 19/27 (70%) |
| existing, new shape | 17/39 (44%) | 9/39 (23%) | 3/13 (23%) |
| held-out, known shape | 26/33 (79%) | 5/33 (15%) | 6/11 (55%) |
| held-out, new shape | 10/15 (67%) | 3/15 (20%) | 3/5 (60%) |
| all | 130/183 (71%) | 26/183 (14%) | 34/61 (56%) |

| Held-out set, by shape | Runs right | Runs partly | Questions right in every seed |
|---|---|---|---|
| known shape, new names | 26/33 (79%) | 5/33 (15%) | 6/11 (55%) |
| new shape | 10/15 (67%) | 3/15 (20%) | 3/5 (60%) |

Retrieval returned a helpful shape for h01 (ex11, wins list), h05, h06 and h07 (ex01, event winner), h08 (ex10 and ex27), h10 (ex19, best record), h11 and h15 (ranking), h12 and h13 (ex28, set record) and h16 (ex24, empty result), in every seed. It didn't for h02 and h03 (placements), h04 (head-to-head), h09 (teammates) and h14 (no shape helps). Every labelled shape is in the bank, so a new shape here is one retrieval missed.

| Category | Runs right | Runs partly | Questions right in every seed |
|---|---|---|---|
| event_result | 36/42 (86%) | 3/42 (7%) | 9/14 (64%) |
| head_to_head | 16/18 (89%) | 0/18 (0%) | 5/6 (83%) |
| multi_step | 41/48 (85%) | 2/48 (4%) | 11/16 (69%) |
| partial | 0/15 (0%) | 5/15 (33%) | 0/5 (0%) |
| player_record | 27/39 (69%) | 12/39 (31%) | 7/13 (54%) |
| unanswerable | 10/21 (48%) | 4/21 (19%) | 2/7 (29%) |

| First stage that failed | All (53 of 183 not right) | Tuned (5 of 15) | Existing (36 of 120) | Held-out (12 of 48) |
|---|---|---|---|---|
| name resolution | 6/53 (11%) | 0/5 (0%) | 6/36 (17%) | 0/12 (0%) |
| SQL logic | 14/53 (26%) | 0/5 (0%) | 9/36 (25%) | 5/12 (42%) |
| empty or insufficient data | 17/53 (32%) | 0/5 (0%) | 14/36 (39%) | 3/12 (25%) |
| answer writing | 16/53 (30%) | 5/5 (100%) | 7/36 (19%) | 4/12 (33%) |

Every run ended in an answer or in suggestions. With retrieval off, the 38 runs judged not right failed at name resolution 4 times, SQL logic 20 (8 of them the unread automatic verdicts), empty or insufficient data 10 and answer writing 4.

**Retrieval off and on**, the off arm's 29 questions and the same seeds:

| Questions, retrieval | Runs right | Runs partly | Questions right in every seed | Not judged yet |
|---|---|---|---|---|
| held-out, off | 19/48 (40%) | 8/48 (17%) | 0/16 (0%) | 11 |
| held-out, on | 36/48 (75%) | 8/48 (17%) | 9/16 (56%) | 0 |
| existing, near-clean, off | 13/39 (33%) | 6/39 (15%) | 0/13 (0%) | 6 |
| existing, near-clean, on | 17/39 (44%) | 9/39 (23%) | 3/13 (23%) | 0 |
| all, off | 32/87 (37%) | 14/87 (16%) | 0/29 (0%) | 17 |
| all, on | 53/87 (61%) | 17/87 (20%) | 12/29 (41%) | 0 |

Retrieval helps the held-out set: even if all 11 runs not judged were right, it would be 30 of 48 off (63%) against 36 of 48 on (75%). For the near-clean existing questions it isn't settled: 13 to 19 of 39 off (33% to 49%) against 17 on (44%). The off arm's all-seeds column is 0 only because no seed-2 run is judged right yet.

**Where it falls short** (retrieval on, unless marked "off"):
- **Earnings, 12 of 12 runs not right (q05, q09, q33, q45), and the 11 judged off.** Every run says no earnings are recorded, and q05 and q45 call no tool. The system prompt lists the views the agent may query, and `v_career_earnings` isn't one: `agent/react.py` never mentions earnings.
- **The player not named, 7 runs (q21 s0–s2, h01 s1, h03 s0–s2), 3 off.** The answer echoes the question's spelling ("Baloonboy", "Pugsyxd", "Neze") where the notes ask for the player's name.
- **An event's status ignored, 5 of 6 runs of q30 and q31.** resolve_event listed CEO Dreamland 2020 as cancelled and SEA League Week 1/4 as placements_unreliable in every run. q30 s0 gave CEO Dreamland ONLINE's winners as the 2020 event's (s1 ended on a reply to the answer check), and every q31 run called SEA League's event nonexistent or invalid.
- **Placements without matches, h13, 3 of 3 runs, 2 off.** A set count of 0 at the Pro Series finals becomes "Santy may not have taken part", when Santy's crew won.
- **"godly", 6 runs.** q15 s1 and q44 s0 queried the display name Godly (108185), and q15 s2 all four candidates at once, over the resolver's first candidate, Zivai (a former name). In every q35 run the model sent "godly main" as the name, and the turn ended in suggestions about "godly gaming".
- **Community tournaments, q36 s1 and s2, 1 off.** The answers counted official wins, or the official event named "Brawlhalla Community Tournament #2".
- **One row kept of several, 2 runs, 3 off.** h05 s1 and h07 s2 named one winner of a team, as did h07 s0 and s1 off, and h11 s0 off one of two tied players (LIMIT 1, where the query was read).
- **Facts no tool returned.** In h04 s1 and s2 every query timed out (in s1, queries ORing the two pairings), and both answers give the same invented record, 12-8. q20 s1 named two player IDs "Lucky" and "Mao", and h11 s0 off called Zivai's ID "Kappa". The no-tool check fires only when no tool was called.
- **Guardrail side effects.** q03 s0 and q30 s1 end on a reply to the answer check, not an answer (q03 after a false alarm on "did"). In h11 s0 off, the check sent "Kappa" back, and the model looked the name up and switched to another player.
- **A format for a mode, off.** h09 s1 filtered `format = '2v2'` in a COUNT, which returns one row of 0, so no diagnosis ran ("no 2v2 titles"). h11 s1 answered "no official 1v1 events in 2024" after the lookup check had flagged its filter.
- **Off only:** a set record counted in games (h12 s0) or from v_win_runs' winning runs (h12 s1), placements as bare player IDs (q14 s1), and the 2026 events "have not occurred yet" (q15 s1).

**The 16 answer-writing failures (retrieval on):**
- **Name echo or misspelling, 7:** q21 s0–s2, h01 s1, h03 s0–s2.
- **Unsupported claim, a fact in no tool result, 7:** q02 s0 and s2 (wins "in both 1v1 and 2v2"; all six count as 1v1), q06 s0 (Raydish's 20 events as 2), q06 s1 (JuicyDiaper's best as 17th, Raydish "consistently" 2nd), q14 s0 (antireplay 8th, tied 7th), q19 s1 (the 1v1 and 2v2 winners swapped), q20 s2 (3-2 for the 3-0 at the top of the result).
- **Other, 2:** q03 s0 (the final reply answers the answer check) and q42 s0 (the event named by its own title, the tournament only in its ID).

**The partial category, 0 of 15 right:** a real weakness more than strict verdicts. 10 of the 15 are wrong on the facts: q05 and q45 (6, automatic: no query, and earnings denied), q31 (3: an event listed as placements_unreliable called invalid) and h13 s1 (Santy "did not participate"). Only 5 hinge on how strict the verdict is: q33's 3 (right that Boomie's earnings can't be given, wrong that none are recorded) and h13 s0 and s2 (hedged, with a false reason). Counting all 5 right would make 5 of 15. 9 of the 15 runs are earnings questions.

**Scoring changes made while reading the results** (none to the agent; each applies to every run of both arms):
- Checks widened to the results right answers came from: q07 and q26 (medals without a mode column), q15 (a count of 2 wins), q40 and h10 (losses without the record), q42 (the event by its ID), h05, h06 and h07 (winners as player IDs, one per row, through a new `exactly()` that an entrant list doesn't pass).
- Stage 2 reads the events resolve_event listed, with their status. It moved all 6 runs of q30 and q31 from stage 2 to stage 3.
- Stage 2 reads a player ID in an ID column as the player's name. A flaw, found writing this entry: it also passes a run that never fetched the names, and so dropped q14 s1 off's verdict (bare IDs). A name should count only if a tool returned it.
- A stage-2 failure whose last query found nothing (no rows, or one row of nulls and zeros) is drafted as stage 3, not marked wrong automatically.
- A stage-1 miss where the right answer needs no data is a draft. A run that called no tool fails at stage 2, not 1. One query holding several candidates for a name fails stage 1 (q15 s2).
- A verdict by hand over an automatic failure stays while the run still fails that stage, so "wrong" can be "partly" (q20 s0).
- The held-out answers name players instead of using pronouns (no fact changed).

**Caveats:**
- Small groups: with 11 and 5 held-out questions, one question moves a group's all-seeds rate by 9 or 20 points.
- One judge, Claude, who also wrote the held-out set, the example bank and the checks.
- The scoring rules and checks changed while seed 0 was being read. All of them widened what passes, except the several-candidates rule, which failed one run.

**For the agent** (proposals; the decisions are the user's):
- Name `v_career_earnings` in the prompt, with its rule that a missing figure isn't $0 (all 4 earnings questions).
- The check proposed on 2026-10-25, that an answer names the player a variant spelling resolved to (7 runs).
- resolve_event's note saying plainly when an event wasn't held or its placements are unreliable (5 runs), and a prompt line that the Pro Series finals have placements but no matches (h13).
- The no-tool check widened to answers stating facts when no query returned rows (h04, q20), and the empty-result diagnosis run on a COUNT of 0 (h09 off).
- For the harness: count a name only when a tool returned it, then draft the 17 retrieval-off runs left and read its 11 unread machine verdicts.

## 2026-10-25: retrieval of worked examples, off and on, on questions 4, 6 and 8 and q21, seeds 0–5

**Question:** do the retrieved examples change the agent's queries and answers?

**Setup:** commit adf4cf0, which also has the prompt line on names in tool results, so both arms use it.
- Two runs with the same seeds 0–5, prompt and interpreter (the x64 Python 3.14, for Chroma), that differ only in `--examples`: off (run `20261026T020834Z`) and on (`20261026T022244Z`), 24 runs each.
- Retrieval as measured in the entry below: at most 3 examples, at 0.70 or more, chosen by MMR.
- **Judging:** by hand against the verified set, as before. q08 must state its minimum, and q21 must say which player it took "baloonboy" to be.

**Results:**

| Question | Examples retrieved | Off: right | On: right | On: what the query took from an example |
|---|---|---|---|---|
| 4. Impala vs Balloonboy | ex05 head-to-head (the only one at 0.70 or more) | 5/6 | 6/6 | All 6 read one side of `v_head_to_head_1v1`, as ex05's note says. Off, all 6 queried both rows. |
| 6. megd's 2v2 partners | ex17 ranking, ex08 teammates, ex03 top 8 | 0/6 | 6/6 | All 6 grouped by partner_id with COUNT and MIN(placement), ex08's pattern. Off, one grouped, over a wrong join. |
| 8. Best record against marckiemoo | ex05 head-to-head, ex19 best record, ex17 ranking | 3/6 | 5/6 | All 6 took ex19's query nearly whole: names joined, 1.0 * wins / matches, at least 5 sets, the top 5. Off, all 6 had the minimum and float division too. |
| q21. baloonboy's official wins | ex10 official wins, ex12 medals, ex13 placements | 4/6 | 0/6 | 3 of 6 grouped by mode, ex10's pattern, and gave the 5 and 2 split. None said it took "baloonboy" to be BBBalloonBoy. |

| Seed | Question 4: off, on | Question 6: off, on | Question 8: off, on | q21: off, on |
|---|---|---|---|---|
| 0 | ✓, ✓ | ✗ partners as IDs, averaged over a wrong join; ✓ all 17 | ✓, ✓ | ✓ spelled "BBalloonBoy"; ✗ never names him |
| 1 | ✓, ✓ | ✗ "no 2v2 placements", after the lookup check; ✓, but JuicyDiaper among the one-event partners | ✗ no minimum; ✓ | ✓; ✗ never names him (gives the split) |
| 2 | ✓, ✓ | ✗ 46 rows as bare IDs; ✓ the 5 most frequent of 17 | ✗ no minimum, after the answer check ("Kappa"); ✓, but says "5 total games" | ✓; ✗ |
| 3 | ✓, but adds that Impala won their last set (he lost it); ✓ | ✗ bare IDs, counts read from rows; ✓ all 17 | ✓; ✗ no minimum stated | ✗ never names him; ✗ (gives the split) |
| 4 | ✗ "2 wins - 2 losses"; ✓ | ✗ other teams' partners, from a wrong join; ✓ all 17, but calls the 513th place "likely a typo" | ✓, ✓ | ✓; ✗ (gives the split) |
| 5 | ✓; ✓, but spells him "BballoonBoy" | ✗ names with wrong counts; ✓ the main partners, no total | ✗ "highest among players who have faced" him; ✓ | ✗; ✗ |

**What retrieval changed:**
- **Question 6 is fixed.** It had failed in every run (0 of 6 three times): no run had aggregated in SQL. With the teammates example, every run did, in one query, and answered in 3 steps with the right counts: 17 partners, Raydish 20 events, hardymj 4, Winged_Shell 3.
- **Question 4 reads one side of the view.** Without the example, every run fetched both rows of the pairing, and seed 4 added them into "2 wins - 2 losses".
- **Question 8 states its minimum more often**, and lists the top 5 as the verified answer does, since the example's query is shaped that way.
- **q21 got worse.** The counts are right in every run, and three give the split the verified answer has. But no answer says the player is BBBalloonBoy: they echo the question's "Baloonboy", where 4 of 6 runs without examples, and 5 of 6 in the run before, named him (the cause is a guess).
- **Shorter runs:** every run with examples took 3 steps. Question 6 used 1,692 output tokens against 3,554, and question 8 1,878 against 2,352. q21 used more (1,308 against 962), and the examples add 160 to 435 prompt tokens.
- **No answer named an example's player.** No check fired with examples on; off, the lookup check fired once (question 6, seed 1, which still answered wrong) and the answer check once ("Kappa").

**Saved for the write-up:** both arms of question 6, seed 1 (wrong to right) in `docs/traces/q06-seed1-retrieval-off-and-on.md`, and of question 4, seed 4 (both rows added, to one side read) in `docs/traces/q04-seed4-retrieval-off-and-on.md`.

**Time:** model seconds aren't comparable between the arms. The server generated more slowly during the run with examples (a median of 50 output tokens per second of step time, against 68). Steps and tokens are above.

**Caveats:**
- Four questions, six seeds each; judged by hand.
- The bank was written knowing these questions' failure modes (teammates with GROUP BY, a best record with a minimum), though no example uses their players, events or wording. Retrieval found them by wording: the teammates example was second for question 6.
- The retrieval settings were chosen on the evaluation questions (the entry below).

**For the agent** (proposals; the decisions are the user's):
- **Current names:** an answer about a name resolved by a spelling variant ("baloonboy") must name the player the tools returned, as a check, since the prompt's rule alone lost it in every q21 run with examples.
- **The threshold:** 0.70 leaves q23, q39 and q45 without examples (the entry below). A lower one keeps them, and gives more examples to questions no shape helps.
- **The full evaluation, with retrieval off and on,** once the harness exists.

## 2026-10-25: retrieval of worked examples, measured alone on the evaluation set

**Question:** for each evaluation question, does retrieval put an example of a helpful shape in its top 3?

**Setup:** commit fdebd9c, with `agent/retrieval.py measure`.
- **The bank:** 28 worked examples in `agent/examples/examples.toml`, of 25 shapes (event winners and top 8s, head-to-heads, teammates, official wins, medals, firsts, rankings, empty results...). None names a player or uses an event from the evaluation set.
- **Retrieval, as the agent runs it:** only the questions are embedded, with nomic-embed-text and the prefix `clustering: `, in a Chroma collection with cosine distance. The 10 most similar examples go through a threshold of 0.70, then maximal marginal relevance (weight 0.7) keeps 3.
- **The labels:** `eval/questions/shapes.toml`, by hand, lists the shapes that would help each question: 39 questions have one or more. The other 6 have none, since no query answers them (prize money per tournament, career earnings, 2016, legends, community events).
- Results: `eval/results/20261026T020418Z-retrieval.json`.

**Results:**

| Setting | A helpful shape in the top 3 | First | Examples retrieved for the 6 no shape helps |
|---|---|---|---|
| The agent's: threshold 0.70, then MMR | 32 of 39 | 24 of 39 | 13 of 18 |
| No threshold, MMR | 35 of 39 | 27 of 39 | 18 of 18 |

- **The prefix**, with no threshold: `clustering: ` 35 of 39 (27 first), no prefix 35 (26), `search_query: ` on both sides 31 (21). The query/document pair meant for passages scored 30 in an earlier probe, by similarity alone.
- **Misses with the agent's settings:**
  - q14 ("Who made top 8 at Trial of Laufey NA?") got event winner and event facts examples, and q15 ("did godly win eu summers 2026") got the top 8 example first: near shapes;
  - q23 ("kingdom | godly vs impala head to head"), q39 and q45 (who has more medals, or earned more) got nothing at 0.70 or more;
  - q05 and q42 (rankings by earnings and by size) got unrelated shapes.
- **The threshold separates poorly.** It costs three hits (q23, q39, q45 lose every example) and drops only 5 of the 18 examples given to questions no shape helps. Those questions' best matches score 0.71 to 0.81, while a helpful example's best score ranges from 0.65 to 0.90 (median 0.80).
- **For the questions of the run below:** q04 gets one example, the 1v1 head-to-head (0.74); q06 gets the ranking, teammates and top 8 examples; q08 the head-to-head, best record and ranking examples; q21 the official wins, medals and placements examples.

**Caveats:**
- The labels are mine, not reviewed by the user.
- The prefix, the threshold and the MMR weight were chosen looking at these same questions, so the numbers are optimistic for new ones.
- Similar wording, not the query a question needs, drives the scores: "who won 2v2 at autumns 2023 NA?" scores 0.83 against "Who has the most official 2v2 wins?".

## 2026-10-25: the ID and no-tool checks, replayed on every past answer

**Question:** what would the two checks decided after the run below have sent back, had they run on every earlier answer?

**Setup:** commit 3f80db6. Every answer of every run and session since 2026-10-18 (94 answers in 18 files) is replayed with the conversation as it stood at that answer: the prompt, the questions, and every observation before it.
- **The ID check:** an answer citing a player ID that no tool and no question showed. IDs count after an ID word (player_id 12345, partner ID 5), or alone in bold or parentheses with five digits or more.
- **The no-tool check:** an answer stating facts (the players it names, player IDs, numbers other than formats such as 1v1) in a question that called no tool.

**Results:**
- **Each check flags exactly one answer, the same one:** the run below's seed 2 session, turn 3. It called no tool and cited 12345 and 67890 for Markled and Arklem, the IDs of Hippo and mely.
- **The ID check raised no false alarm** on the 93 other answers, many of which cite IDs ("Impala (168635)", "player_id 149305").
- **The no-tool check's false alarms can't be measured here:** only that answer came without a tool call. Its unit tests cover replies without facts, such as "Glad to help.", which stand.

**Also changed, not replayed:** suggestions now stay in the history as the agent's clarifying question (commit 7e3f686), so a later question has no answer-shaped text to copy. Whether that stops the copying needs a run with the model.

**Caveats:** a replay shows what the checks flag, not what the model does once an answer goes back. Real players are named Yes, No and Note, so a bold "**Yes**" in an answer without a tool call counts as naming a player.

## 2026-10-25: the decisions on the lookup run, on q21, q22 and the Worlds follow-ups, seeds 0–5

**Question:** with the user's five decisions on the 2026-10-23 run built, are the misspelling questions answered or asked as the verified set accepts? Does the Worlds follow-up from that run's session get the right answer now?

**Setup:** as in the entry below, with commits 45905ba to 7e9f65e.
- **q22's accept list** takes suggestions with Marckiem00 first. Near-misses of curated nicknames stay below the confident threshold.
- **The prompt:**
  - the "say what you relaxed" rule covers only conditions from the question, and the model fixes its own wrong filters;
  - the scope names a mode only when the query was limited to one;
  - the diagnosis line asks for event IDs from `resolve_event` as well as player IDs.
- **The answer check reads quoted names.** Replayed on the 76 answers of every earlier run and session, it flags exactly one more: question 6's uncaught "Kappa (hypothetical example)".
- **`resolve_event`, a third tool.** A mode word narrows the events, and the rest matches, in tiers.
  - The tiers: a curated alias ('bcx 2022', score 1.0), a series of yearly aliases ('worlds', 0.95), every word with years and curated terms ('winters 2023 na', 0.9), or some of the words (0.85 times the share).
  - The result has a sql condition on event_id: the IDs, or a subquery on the aliases for a big alias set.
  - Before the run, on eval-v1: 14 of the evaluation set's 15 event phrases resolve to exactly their expected events. 'ceo dreamland 2020' is ambiguous by design: the cancelled event first, then the online one, which q30's answer also names.
- **The lookup check:** an answer right after an empty result whose diagnosis finds no row with a text value the query filters on goes back once. Any other empty result can be a true "none".
  - Replayed before the run on the 9 distinct empty queries of the earlier runs and sessions, it flags 6: five filters on 2v2 as a format, and the session's `event_name LIKE '%worlds%'`.
  - It misses two 2v2 filters inside a subquery (`event_id IN (SELECT ... format = '2v2')`), whose conditions the diagnosis can't test. It rightly leaves out question 8's `total_matches >= 5`, a count.
  - The value is now checked in the column's own table when the query names it. Through the join, the session's probe took 1.6 s warm and ran out of time cold.
- **Runs:**
  - q21 and q22 with seeds 0–5: run `20261026T004543Z`, 12 runs.
  - Six sessions, one per seed (`ask.py --seed N`), each asking q22, then "the first one", then "has Raydish won Worlds": 18 turns. No earlier session asked about Raydish; the third turn adds that question to the follow-up.
- **Judging:** by hand, against the verified evaluation set for q21 and q22, and against eval-v1 for the follow-ups:
  - "the first one": yes, Marckiem00 won the 1v1 at BCX 2025 (worlds 2025);
  - "has Raydish won Worlds": no. His best is 3rd in the 1v1 at BCX 2025, then 4th in the 2v2 at BCX 2023 with megD.

**Results**, with the run below:

| Question | Lookup changes (2026-10-23): answer | Decisions (2026-10-25): answer |
|---|---|---|
| q21. baloonboy's official wins | 3/6 | 5/6 |
| q22. did markiemoo win worlds | 0/6 (all six asked, Marckiem00 first) | 6/6: all six asked, Marckiem00 first, now accepted |
| Follow-up: "the first one" | 0/1 (seed 0: "never won Worlds") | 6/6 |
| Follow-up: "has Raydish won Worlds" | not asked | 5/6 |

| Seed | q21 | q22 | "the first one" | "has Raydish won Worlds" |
|---|---|---|---|---|
| 0 | ✓ | ✓ asked | ✓, but adds that the win "would occur in the future relative to the current date (2023)" | ✓ |
| 1 | ✓ | ✓ asked | ✓, from a count: doesn't say which event | ✓ |
| 2 | ✗ "Baloonboy (player_id 149305)": never names BBBalloonBoy | ✓ asked | ✓, but adds an invented "record of 1-0" | ✗ no tool call: "couldn't find Raydish", with invented suggestions |
| 3 | ✓ | ✓ asked | ✓ | ✓ |
| 4 | ✓ spelled "BBalloonBoy" | ✓ asked | ✓ | ✓ |
| 5 | ✓ spelled "BBalloonBoy" | ✓ asked | ✓ | ✓ |

**What the changes did:**
- **`resolve_event` fixed the follow-up.** In all six sessions, "the first one" called `resolve_event("worlds")`, got the 34 Worlds events (confident), and pasted its sql condition into the query. All six found the BCX 2025 1v1 win, where the 2026-10-23 session searched `event_name` with LIKE and answered "never won Worlds".
  - In turn 3, four runs reused the condition from turn 2, and seed 4 resolved "worlds" again.
- **The scope example:** no q21 answer called the 7 wins "1v1", against 2 of 6 before (6 runs, so the change is inferred from the prompt).
- **"None" stood where it was true.** Four Raydish queries came back empty, rightly, since he has no Worlds wins. Their diagnoses named no missing text value, so the lookup check let the answers stand, and all four were right.
- **No check fired:** no lookup, answer or size check in the 12 runs or the 18 turns. No query searched names with LIKE.

**New:**
- **An answer with no tool call** (seed 2, turn 3). Its thinking imagined the lookup: "The tool returns that there's no player named Raydish. The closest names are Marckiem00, Markled, and Arklem."
  - It then copied turn 1's suggestion format, with player IDs 12345 for Markled and 67890 for Arklem, which are other real players (Hippo and mely).
  - The answer check couldn't catch it: the three names were returned in turn 1, and the check doesn't read IDs.
- **False asides** in two answers to "the first one": seed 0's "future relative to the current date (2023)", and seed 2's "record of 1-0 in the tournament" and "Challengers Mode bracket".
- **The Raydish answers stop at "no".** None gives his best Worlds result, 3rd in the 1v1 at BCX 2025. The question doesn't ask for it.

**What didn't change:** q21 spells BBBalloonBoy "BBalloonBoy" twice, and once doesn't name him, as in the run below.

**Time:** q21 took 10.9 s of model time in 3 steps (means), and q22 3.8 s in 1. The session's turns took 4.2, 12.3 and 11.4 s, in 1, 3 and 2.8 steps.
- The server ran at a median of 102 output tokens per second of step time, against 92 in the run below.
- The largest context was 7,518 tokens.

**Caveats:**
- Two questions and one three-turn session, six seeds each.
- The follow-ups aren't in the evaluation set: their expected answers were computed from eval-v1 for this entry.
- These questions exercised only `resolve_event`'s series tier and never triggered the lookup check, so the other tiers rest on the offline check above.
- The prompt changed, so a seed doesn't sample as in the run below. The answers were judged by hand.

**For the agent** (proposals; the decisions are the user's):
- **An ID check:** an answer citing a player_id no tool returned goes back, as the answer check does for names. It would have caught seed 2's 12345 and 67890.
- **Suggestions in the history:** they're stored as the assistant's reply, which seed 2 copied. Recording them as the agent's question to the user might make them less tempting to copy (guess).
- **The event questions:** a run of the evaluation set's event questions (q10, q13 to q20, q24, q28 to q32, q41) would exercise `resolve_event`'s other tiers in the agent, and the lookup check where a model still writes a wrong filter.
- Still waiting from the entries below: question 6's aggregation, `v_team_results` holding only 2v2, SQLite's integer division, current names, and the minimum number of matches.

## 2026-10-23: the lookup changes on questions 4, 6 and 8, q21 and q22, seeds 0–5

**Question:** Checkpoint 2's feedback asked for three changes to how the agent handles failed lookups. Do they work, and do the answers that were right stay right? How do the match scores behave on the evaluation set's two misspelling questions?

**Setup:** as in the entry below, with commits 5d33dd0 and 93b640e.
- **Match scores:** `resolve_player` gives each candidate a score, its tier's base times its closeness within the tier.
  - The bases: curated nickname 1.0, exact name 0.98, character swap 0.92, prefix and similar spelling 0.85.
  - Closeness is 1 in the exact tiers, the share of the alias a prefix covers, and difflib's ratio for a similar spelling.
  - The scores rank matches; they aren't calibrated probabilities.
- **Suggestions:** `CONFIDENT = 0.9`. When a name from the question matches only below it, the turn ends and the user sees the top three candidates, so the model doesn't guess (outcome "suggestions").
- **A diagnosis for an empty result:** the query is rerun without each top-level condition of its WHERE and HAVING, and the rows each rerun returns are reported.
  - For an equality or LIKE filter, it also says whether the value occurs in the column, and lists the column's values when there are at most 12.
  - Its note: check the condition responsible and the player IDs; if you relax a condition, say in the answer which one and why; never relax one silently.
- Questions 4, 6 and 8, and the evaluation set's two misspelling questions: q21 ("how many official events has baloonboy won?") and q22 ("did markiemoo ever win worlds"). Seeds 0–5: 30 runs (run `20261023T215750Z`), the last two with `react.py`'s new `--eval ID`.
- Ollama 0.40.8 (0.40.2 before), with the same model. The system prompt has a new line on the diagnosis, so a seed doesn't sample as it did in the earlier runs.
- One live session (`ask.py`, seed 0) for q22's follow-up: the question, then "the first one".
- **Judging:** by hand, against the verified evaluation set. An answer is right when its main facts match the verified answer; false asides are listed separately. q08 must state its minimum number of sets, and q21 must say which player it took "baloonboy" to be (its note).

**Results**, with the earlier runs:

| Question | Baseline: query right | First run: answer | Incomplete mark: answer | Token budget: answer | Lookup changes: answer | Lookup changes: query right |
|---|---|---|---|---|---|---|
| 4. Impala vs Balloonboy | 1/1 | ✓ | 5/6 | 5/6 | 6/6 | 6/6 |
| 6. megd's 2v2 partners | 3/6 | ✗ | 0/6 | 0/6 | 0/6 | 6/6 |
| 8. Best record against marckiemoo | 0/6 | ✗ | 3/6 | 4/6 | 3/6 (5/6 name the right player) | 5/6 |
| q21. baloonboy's official wins | not run | not run | not run | not run | 3/6 | 6/6 (by hand) |
| q22. did markiemoo win worlds | not run | not run | not run | not run | 0/6: all six asked, with Marckiem00 first | no query |

| Seed | Question 4 | Question 6 | Question 8 | q21 | q22 |
|---|---|---|---|---|---|
| 0 | ✓ | ✗ 14 of 17 partners, 7 of Raydish's 20 events; diagnosed and fixed its `format = '2v2'` | ✓ after the answer check (it first said "Kappa") | ✗ "in 1v1 mode": 5 of the 7 were 2v2 | asked |
| 1 | ✓ mentions the other Impala | ✗ 16 partners, 12 events for Raydish; diagnosed and fixed its `format = '2v2'` | ✗ integer division: SiB \| Wess at 1–5, as a bare ID | ✓ | asked |
| 2 | ✓ | ✗ 15 partners, 14 events for Raydish | ✓ after the answer check ("Cupcake") | ✗ "in 1v1 mode" | asked |
| 3 | ✓ | ✗ "Raydish in 41 of 46 events" (20) | ✗ right player after the answer check ("Kappa"), no minimum stated | ✓ spelled "BBalloonBoy" | asked |
| 4 | ✓ mentions the other Impala | ✗ partners as bare IDs, results given to the wrong partner | ✗ right player, no minimum stated | ✗ "Baloonboy (player_id 149305)": never says which player | asked |
| 5 | ✓ | ✗ bare IDs, 41 events for Raydish | ✓ | ✓ | asked |

**What the changes did:**
- **The threshold separates the two misspelling questions, as designed.**
  - "baloonboy" is a character swap (doubled letters) of "Balloonboy", one of BBBalloonBoy's aliases, at 0.92. q21 was answered in 3 steps every run, and every query counted his 7 wins.
  - "markiemoo" is only a similar spelling of the curated nickname "marckiemoo", at 0.80. q22 asked in all six runs, in one step and 3–8 s, with Marckiem00 first, then Markled (0.68, 2 official results) and Arklem (0.73, 1). Within a tier, candidates are ordered by official results, not by score.
  - No other name from a question fell below the threshold: Impala, Balloonboy, marckiemoo and megd scored 0.98 or 1.0.
- **But q22's verified answer resolves the name and answers yes** (Marckiem00 won the 1v1 at BCX 2025). Under the suggestions rule, a name matched only by a similar spelling never gets an answer, so q22 can't be right as the set stands.
- **The follow-up resolves the pick, but its answer was wrong** (one session, `data/experiments/sessions/20261023T221623Z.md`).
  - After the suggestions, the agent took "the first one" to mean Marckiem00.
  - Its query searched `event_name` for "worlds" and got no rows. Worlds are event aliases (`event_aliases`), and BCX 2025 keeps its name in `tournament_name`, with `event_name` empty.
  - The diagnosis said the query returns 9 rows without that condition: Marckiem00's nine official 1v1 wins, BCX 2025 among them. The model answered that he never won Worlds.
- **The diagnosis fired twice in 30 runs, both on question 6, and both runs recovered.**
  - Each time, the empty result came from the model's own filter on 2v2 as a format (`format = '2v2'`, once inside a subquery). The next query fixed it (`format = 'standard'`, then `counts_as = '2v2'`) and got all 46 rows.
  - So no run answered that megD never played 2v2, against 3 of the 12 question 6 runs in the two earlier seed runs.
  - Neither answer said what it had changed. Both answered for 2v2, as asked: the condition dropped was the model's mistake, not one the question set.
  - It took 1.6 and 0.2 s. Replayed before this run on the four empty results of the two earlier seed runs, it named the condition responsible each time, in 2.5–8.2 s: `format = '2v2'` three times, and question 8's `total_matches >= 5`, a count on a view with one row per pair.

**What didn't change:**
- **Question 6 is 0 of 6 again.** Every final query returned the right 46 rows, and no run aggregated in SQL. The answers listed or counted the rows by reading them, and none got the partners right: 17 of them, with Raydish at 20 events, hardymj 4 and Winged_Shell 3.
- **Integer division** in question 8, seed 1, giving the same wrong player as the incomplete-mark run's seed 4.
- **Current names:** question 4 calls BBBalloonBoy "Balloonboy" in all six runs. q21 spells him "BBalloonBoy" twice, and once never names him.

**New, or more often:**
- **Invented names for an ID.**
  - Question 8's head-to-head query returned a player_id without a name in all six runs. Two runs then looked the name up, and three named an invented player (Kappa twice, Cupcake).
  - The answer check sent all three back, and each then looked up V3M_T4NQUIL0. Without it, question 8 would have named the right player in two runs, not five.
  - Question 6, seed 4 wrote "Kappa (hypothetical example)" in quotes. The check reads bold text and words shaped like gamer tags, so it missed this one.
  - Since the prompt changed, the seeds sample differently, so the rise from 2 in 18 runs (incomplete mark) and 0 in 18 (token budget) may be chance.
- **The prompt's scope example, copied:** q21 seeds 0 and 2 said the 7 wins were "in 1v1 mode", as in the prompt's example ("at official events, in 1v1"), though 5 were 2v2.
- **False asides:**
  - question 4, seed 5 explains Impala's 8 games as "4 games per match × 2 wins" (the sets were 3-0, 3-1 and 2-3);
  - question 8, seed 2 adds that no 2v2 records were found, without a 2v2 query;
  - question 6, seeds 1 and 2 call megD and JuicyDiaper's 513th place a likely typo or error. It's real: the 2020 North America Summer Championship's 2v2 placed teams down to 1,025th.

**Time:** 22.8, 38.3 and 29.1 s of model time per question (means) for questions 4, 6 and 8, in 3.0, 3.7 and 5.0 steps. q21 took 11.5 s in 3 steps, and q22 4.8 s in 1.
- The server was faster: a median of 92 output tokens per second of step time, against 63 in the token-budget run. Output tokens compare better: 1,790, 3,394 and 2,580 per question, against 1,462, 2,662 and 3,145.
- Question 8's extra steps are the three answers sent back.
- The largest context was 8,647 tokens.

**Caveats:**
- Five questions, six seeds each, and one live session.
- The prompt and the server version changed too, so differences from the earlier runs mix the changes with sampling.
- The expected answers come from our own data, verified by the user, and the answers were judged by hand.
- Two misspelling questions are too few to tune the scores or the threshold on.

**For the agent** (proposals; the decisions are the user's):
- **q22 and the threshold.** Either:
  - accept a list of suggestions with the right player first as a right answer when only a similar spelling matches (an `accept` entry for q22, a change to the verified set);
  - or make some similar spellings confident, such as one letter off a curated nickname, so q22 is answered. That needs more misspelling questions to tune on than q21 and q22, since one letter off can also land on another real player.
- **Make the diagnosis count:** like the result-size check, send back once an answer that comes right after an empty result. The model fixes or relaxes the condition the diagnosis named, or gives the same answer again if the empty result is right. It would have sent back the session's "never won Worlds".
- **Event names people use:** a line in the prompt, or an event resolver like `resolve_player`. Names like "worlds" or "bcx 2022" are looked up in `event_aliases`, and searches by name cover `tournament_name`, since many events have no `event_name`.
- **Saying what was relaxed:** limit the rule to conditions the question sets. Fixing its own wrong filter needs no mention.
- **Smaller fixes:** the answer check also reads quoted names, and the scope example names a mode only when the query was limited to one.
- Still waiting from the entries below: `v_team_results` holds only 2v2, SQLite's integer division, current names, and how to get question 6 aggregated.

## 2026-10-19: the result-size fixes on questions 4, 6 and 8, seeds 0–5

**Question:** with the 20-row cap replaced by a token budget, and an answer after a result too large to show sent back, does question 6 get answered?

**Setup:** as in the entry below, with the result-size fixes of commit fc9e607 (the decision is at the end of that entry).
- `run_sql` returns every row if the result fits in about 4,000 tokens, and none if it doesn't.
- An answer right after a result with no rows goes back.
- The prompt's rule: always reduce the data in SQL, and never count, rank or compare rows by reading them.
- 18 runs (run `20261020T021020Z`), judged by hand against the verified evaluation set, as before.

**Results**, with the earlier runs:

| Question | Baseline: query right | First run: answer | Incomplete mark: answer | Token budget: answer | Token budget: query right |
|---|---|---|---|---|---|
| 4. Impala vs Balloonboy | 1/1 | ✓ | 5/6 | 5/6 | 6/6 |
| 6. megd's 2v2 partners | 3/6 | ✗ | 0/6 | 0/6 | 4/6 |
| 8. Best record against marckiemoo | 0/6 | ✗ | 3/6 | 4/6 | 5/6 |

On question 8, five of six answers named the right player in both seed runs. The difference is in stating the minimum number of matches, which q08 requires.

| Seed | Question 4 | Question 6 | Question 8 |
|---|---|---|---|
| 0 | ✗ swapped names: "Balloonboy (Impala)" leads | ✗ read all 46 rows: 15 partners, two results given to the wrong partner | ✓ |
| 1 | ✓ | ✗ read all 46 rows: partners as bare IDs, 43 events for Raydish's (20) | ✓ |
| 2 | ✓ | ✗ "never played 2v2": `format = '2v2'` | ✓ |
| 3 | ✓ | ✗ "never played 2v2": `format = '2v2'` | ✓ |
| 4 | ✓ | ✗ read all 46 rows: some events, no counts | ✗ right player, no minimum stated |
| 5 | ✓ | ✗ read all 46 rows: 10 partners, 9 of Raydish's 20 events | ✗ "no records": `COUNT(*)` on a view with one row per pair |

**What changed:**
- **The cut-off is gone.** Four question 6 runs got all 46 rows; the other two filtered every row out.
- **Neither check fired:** no result in 18 runs was over the budget, and no answer named a player no tool returned.
- **Question 8 stated its minimum in 4 runs, against 3.**

**What didn't: question 6 is still 0 of 6, now for other reasons.**
- **No run aggregated in SQL, despite the new rule.**
  - With all 46 rows in view, the answers listed each partner's events by reading them, and got them wrong. Seed 0 gave hardymj megD's 2023 Autumn 2nd, which was with Raydish, and gave Raydish the 2025 Summer 9th with flowerVS.
  - No answer had the top partners' counts right: Raydish 20, hardymj 4, Winged_Shell 3. The answers listed 16, 9 or (as a selection) 5 of Raydish's events, or gave him 43.
  - The question reads as a list ("who has megd played with, and how did they place?"). The rows fit the budget, and the model listed them.
- **The 2v2 filter mistake, twice more:**
  - `format = '2v2'` (2v2 is a mode, and `v_team_results` holds only 2v2) gave 0 rows, and both runs answered that megD never played 2v2.
  - Across the two seed runs, that's 3 of the 12 question 6 answers.
- **Reducing in SQL can go wrong too:** question 8, seed 5 grouped `v_head_to_head_1v1`, which already holds one row per pair, and required `COUNT(*) >= 5`. Every player counted 1, so it answered that nobody has a 1v1 record against Marckiem00.
- **Question 4, seed 0** joined names onto both rows of the pairing and swapped them in its answer.

**Time:** 22.2, 40.0 and 48.6 s of model time per question (means), in 3.0, 3.7 and 4.0 steps.
- The server ran at the same speed as for the previous seed run (63 output tokens per second against 61), so these compare with its 34.6, 46.4 and 31.2 s.
- Question 8's mean includes seed 5: 126 s and 8,034 output tokens, a 30-s timeout among them.
- The largest context was 10,188 tokens.

**Caveats:** three questions and six seeds each; the expected answers come from our own data, verified by the user; the answers were judged by hand.

**For the agent** (proposals; the decisions are the user's):
- The prompt line still waiting from the entry below: `v_team_results` holds only 2v2, so it's never filtered by mode or format. It would have saved 3 of the 12 question 6 runs.
- A rule alone doesn't make qwen3:8b aggregate a question that reads as a list. Options:
  - an example in the prompt of summarizing per player (GROUP BY partner, with COUNT and MIN(placement));
  - a check that sends back an answer listing many items read from a long result;
  - the planned rerun with qwen3:14b, to see whether a larger model follows the rule.

## 2026-10-19: the fixed prototype on questions 4, 6 and 8, seeds 0–5

**Question:** do the fixes decided on 2026-10-19 turn the prototype's right queries into right answers? How consistent is it over six seeds?

**Setup:** the prototype as of commit ae951ba, with the fixes of f7f9007; otherwise as in the entry below.
- The fixes:
  - `resolve_player` refuses IDs;
  - a cut-off result is marked incomplete;
  - an answer naming a player no tool returned goes back once;
  - the prompt says how to write the answer.
- qwen3:8b with thinking, at most 8 steps, on eval-v1.
- Questions 4, 6 and 8 with seeds 0–5: 18 runs (run `20261020T011930Z`). Seed 0 repeats the first run's sampling, and seeds 1–5 match the baseline's reruns.
- **Judging:** each answer by hand, against the verified evaluation set (q04, q06 and q08). q08's answer must state its minimum number of sets, per the user's note. Each query also went through the comparison's check, on its full result.

**Results:**

| Question | Baseline: query right | First prototype run: answer | Fixed: query right | Fixed: answer right |
|---|---|---|---|---|
| 4. Impala vs Balloonboy | 1/1 (seed 0 only) | ✓ | 6/6 | 5/6 |
| 6. megd's 2v2 partners | 3/6 | ✗ | 5/6 | 0/6 |
| 8. Best record against marckiemoo | 0/6 | ✗ | 5/6 | 3/6 (5/6 name the right player) |

The baseline wrote queries, not answers, so its column is the comparison's check. The first run used seed 0 only.

| Seed | Question 4 | Question 6 | Question 8 |
|---|---|---|---|
| 0 | ✓ | ✗ answered from 20 of 46 rows | ✓ |
| 1 | ✗ added the two rows: "3 wins, 3 losses, 6 matches" | ✗ 20 of 46 rows, partners as bare IDs | ✓ |
| 2 | ✓ | ✗ 20 of 46 rows | ✗ right player, no minimum stated |
| 3 | ✓ | ✗ 20 of 46 rows | ✓ |
| 4 | ✓ | ✗ "no 2v2 events": a filter no row matches | ✗ integer division: SiB \| Wess at 1–5 |
| 5 | ✓ | ✗ empty reply, after invented names were sent back | ✗ right player, no minimum stated |

**What the fixes did:**
- **Refusing IDs worked.** At seed 0, question 8 sent V3M_T4NQUIL0's ID to `resolve_player` again. It got the refusal and its `players` query, ran it, and answered with the right name. The other five got the name with SQL straight away.
- **The incomplete mark didn't.**
  - Five of the six question 6 runs got the 46-row result marked incomplete, and none ran an aggregate query.
  - Four answered from the 20 rows shown. The fifth (seed 5) did too, until the answer check sent it back.
  - Their thinking reads the note, then takes "aggregate" to mean counting the rows in view. Seed 1: "The tool mentioned it's incomplete, so I shouldn't answer from that. Instead, I need to aggregate the data. Looking at the rows, the partner_id appears multiple times."
  - **The cut-off was the main cause.** The 20 rows held only 10 or 14 of Raydish's 20 events with megD (10 in the unsorted queries, his latest 14 in those sorted by date), so a correct count was impossible from them.
  - **The counting evidence is thin.** Two answers gave Raydish a count. One was right: seed 1's 14, matching its 14 rows. The other was two too high: seed 0's 12, for 10.
  - The cut-off wasn't needed either: all 46 rows of seed 0's query come to 395 tokens.
- **The answer check fired twice in 18 runs, both times on invented names, with no false alarms.**
  - Question 6, seed 5 gave names to bare partner IDs (C4, Kappa, Sponge, TNT, Dre). Sent back, it looked up "C4", then gave an empty reply.
  - Question 8, seed 4 called its player "Kael". Sent back, it queried the real name, SiB | Wess, though its record was still wrong.
- **The answer guidance worked in part.**
  - 16 of the 17 answers state the scope ("official events, 1v1").
  - Question 8 used the current name, Marckiem00, in all six runs. Question 4 called BBBalloonBoy "Balloonboy" in all six.
  - Half the question 4 answers mention the other Impala.
  - Two of the five right question 8 answers leave out the minimum. Seed 5 instead calls it "the highest win rate among players who have faced Marckiem00", which is false without a minimum: Snowy!! is 2–0.

**What still goes wrong:**
- **Answering from a cut-off result**, question 6's main failure: 5 of 6 runs.
- **Reading a view from both sides in the answer:** question 4, seed 1 queried both rows of the pairing, then headlined their sum (3–3). In the baseline the same error was in the SQL.
- **A filter value no row has:** question 6 tried `format = '2v2'` in three runs (2v2 is a mode, and `v_team_results` holds only 2v2). Seed 4 took the empty result as fact. The baseline's qwen3:8b made the same mistake in one rerun.
- **Integer division:** `wins / matches`, which SQLite truncates (question 8, seed 4), as in one of the baseline's qwen3:4b drafts.
- **Inventing a name for an ID,** twice; both caught by the answer check.
- **Incomplete answers:** question 4's answers give the record but never its sets, the 2v2 meetings or the shared events.

**Time:** 34.6, 46.4 and 31.2 s of model time per question (means), in 3.0, 4.0 and 4.5 steps. That isn't comparable with the first run (10–21 s):
- the server generated more slowly this time: a median of 61 output tokens per second of step time, against 106 in the first run (a probe after the run gave 76, against about 120 on 2026-10-18);
- the answers were longer: 2,111, 2,808 and 1,900 output tokens per question, against 1,106, 2,153 and 2,026.

**Caveats:**
- Three questions, six seeds each.
- The expected answers come from our own data, now verified by the user, and the answers were judged by hand.
- The fixes changed several things at once.

**For the agent** (proposals; the decisions are the user's):
- **Cut-off results:** the note isn't enough. Either don't show an incomplete result's rows, or refuse an answer that comes right after one and send it back for an aggregate query.
- **One line each in the prompt** on two recurring mistakes:
  - `v_team_results` holds only 2v2, so it's never filtered by mode or format;
  - SQLite divides integers as integers.
- **Current names:** have `resolve_player`'s note give the current name to use (BBBalloonBoy) when the name matched is a former one.
- **The minimum number of matches:** add to the counting rule that the answer states it.

**Decision** (the user's, 2026-10-19): the result-size fixes, replacing the incomplete mark. The other proposals above wait.
- **A token budget instead of 20 rows:** `run_sql` returns every row if the result fits in about 4,000 tokens, an eighth of the context.
  - The cost of a result is estimated without the model: digits and JSON punctuation are a token each, and other text about four characters a token.
  - Against the server's own counts for ten query results, that was 9% under to 20% over.
  - The extremes: question 6's 46 rows with partners and placements are 395 tokens, and every 1v1 set Raydish played is 455 rows and about 28,000.
- **No rows for a result over the budget:** only its row count, its columns, and a note to reduce it in SQL (GROUP BY, WHERE, ORDER BY ... LIMIT) and query again.
- **Enforced:**
  - An answer that comes right after such a result, with no new query since, goes back with a short explanation. A `resolve_player` call isn't a new query.
  - It goes back as long as two steps are left, one to query and one to answer. Otherwise it's kept and flagged.
- **The prompt's rule, made general:**
  - It was: aggregate "to count or summarize (how many, how often, the most, the best)".
  - It's now: always reduce the data in SQL to what the answer needs, and never count, rank or compare rows by reading them.
- **Not built yet:** a user who explicitly wants a long list gets an answer that summarizes it, and the full table goes to them directly, without passing through the model.

## 2026-10-18: a minimal ReAct prototype on questions 4, 6 and 8

**Question:** with names looked up by a tool and a note on the views that hold each pairing more than once, does a small agent loop answer the questions one-prompt qwen3:8b got wrong?

**Exploratory, like the model comparison below:**
- Three questions, one run each (seed 0).
- The expected answers come from our own data (`ingest/target_questions.py`).
- Question 4 wasn't one of the baseline's misses: qwen3:8b with thinking got it right, and missed 6 and 8. It's here because both its names need the aliases: Impala is a shared name, and Balloonboy a former name.

**Setup** (`agent/react.py`, `agent/tools.py`):
- **Model:** qwen3:8b with thinking on, through Ollama's native tool calling. The server is now Ollama 0.40.6.
  - Sampling as in the comparison: the model's defaults, seed 0, at most 8,192 output tokens per reply.
  - The context is 32,768 tokens instead of 16,384: the server's template keeps every step's thinking in the prompt until the answer.
- **Loop:** at most 8 steps, each one model reply. A reply either calls tools, whose results go back as observations, or answers. The observation before the last step says it's the last.
- **System prompt:** the comparison prompt's views and counting rules, word for word, with two changes.
  - The name lookup pattern is replaced by instructions for `resolve_player`: call it for every name before any SQL, query by the ID it returns, and say which player an ambiguous name was taken to mean.
  - A new section on the views that hold each pairing more than once (`v_head_to_head_1v1` twice, `v_head_to_head_2v2` four times, `v_team_results` twice), with how to read each from one side.
- **`resolve_player(name)`:** matches the name against `player_aliases` in tiers, and the first tier that finds anyone is used:
  - normalized as aliases are (case, spaces, punctuation, the team tag);
  - with common character swaps undone (0 as o, 3 as e, l as i, doubled letters, ...);
  - as the start of a name;
  - by similar spelling.

  Candidates are ranked by official results, a curated nickname first. The status is confident, ambiguous (a shared name, or only approximate matches) or not found.
- **`run_sql(query)`:** read-only on eval-v1, stopped after 30 s, at most 20 rows with the total row count.
- **Checking:** each final answer by hand, against the key facts of the expected answer, the ones the comparison's checks looked for. Each query also went through the comparison's own check, on its full result, as the baseline's did.

**Results** (run `20261019T001955Z`; full traces in `data/experiments/20261019T001955Z/traces.md`):

| Question | Baseline (one prompt, seed 0) | Prototype's query | Prototype's answer | Steps | Model time (s) | Output tokens |
|---|---|---|---|---|---|---|
| 4. Impala vs Balloonboy | ✓ | ✓ | ✓ the record (2-1, 8-4 in games) | 3 | 10.4 | 1,106 |
| 6. megd's 2v2 partners | empty result | ✓ | ✗ 6 of 17 partners | 3 | 19.9 | 2,153 |
| 8. Best record against marckiemoo | empty result | ✓ | ✗ names the wrong player | 4 | 20.6 | 2,026 |

The baseline took 19.6, 12.6 and 44.1 s per reply on these questions, plus 82 s and 31 s for its queries of questions 4 and 8.

**What the changes fixed:**
- **Names:** all four resolved to the right player with the right status.
  - Impala: ambiguous, the one with 48 official results first and the other (1 result) second.
  - Balloonboy (a former name of BBBalloonBoy), megd and marckiemoo: confident.
  - No query looked a name up, the baseline's main failure.
- **Pairings:** no query added a view's two sides together. Question 4 fetched both rows of the pairing, but read each as its own player's record.
- **Speed:** queries took 0.06–0.5 s with literal IDs.
- **Queries:** all three passed the comparison's check, against the baseline's one.

**What went wrong: the answers, not the queries.**
- **Question 6 was answered from a cut-off result.**
  - The query listed every team result: 46 rows. `run_sql` showed the first 20, with a note to aggregate in SQL, and the model answered from those 20.
  - So it listed 6 of the 17 partners, missing hardymj and Winged_Shell, the second and third most frequent. It also put one of Raydish's placements (9th) at the wrong event.
  - It did say that only 20 of 46 rows were shown.
  - With every row, as the baseline was checked, the same query passes.
- **Question 8 sent an ID to `resolve_player` as a name.**
  - Its query was the reference one, and returned V3M_T4NQUIL0's ID with the right record (3-2).
  - To get the name, it called `resolve_player("71736")`, as planned in step 1, though the prompt says to join `players`.
  - The resolver read the digits as letters and fuzzy-matched them to tike36 (ratio 0.8, the cutoff), as ambiguous.
  - In step 4, its thinking saw the mistake and planned a `players` query, but the reply named tike36 anyway, with four steps left.
- **Question 4 gave only the record.**
  - Not the sets, the 2v2 meetings or the shared events. The comparison's check accepted the record alone.
  - It didn't follow the answer rules: no "official events", "Balloonboy" without the current name BBBalloonBoy, and nothing about the other Impala.

**Caveats:**
- Three questions, one run each: enough to see the failure types, not their rates.
- The expected answers come from our own data, and the answers were judged by hand.
- Several things changed at once: the resolver, the pairing note, the loop and the 20-row cap. A difference can't be put down to one of them.
- Question 4 wasn't a baseline miss.
- The 32,768-token context wasn't needed this time: the largest context was 5,409 tokens.

**For the agent** (proposals; the decisions are the user's):
- `resolve_player` should take names only. A name of digits only should get no swaps or fuzzy matching, and an answer that it looks like an ID, with how to get the name.
- An answer shouldn't rest on a cut-off result. Options: a firmer note in the observation, a higher cap, or the result checker flagging an answer built on one.
- The result checker could also flag an answer that names a player no observation returned.
  - Correction (2026-10-19): question 8's answer wouldn't have been flagged. The resolver itself had returned tike36, from the ID.
  - Such a check catches that case only once `resolve_player` refuses IDs.
- Rerun with seeds 1–5, as the comparison's reruns did, before reading anything into rates.

**Decision** (the user's, 2026-10-19): all three proposals, plus guidance on writing the answer. They're implemented and unit-tested, but not yet run: the Ollama server was unreachable. The seed runs come next, when the user asks.
- **`resolve_player` takes names only.**
  - A name of digits only, or an ID written out ("71736", "#71736", "player_id 71736"), gets an error saying how to get the name with `run_sql`.
  - On eval-v1, 464 players whose only aliases are digits can't be found by name. Each has at most 25 official results.
- **Cut-off results:**
  - A result of more than 20 rows comes back marked incomplete (`"complete": false`), with its first 20 rows. A note before the rows says not to answer from it, but to aggregate, filter or limit in SQL and query again.
  - The prompt says the same, and to aggregate in SQL when counting or summarizing.
- **An answer check:** a final answer that names a player no tool returned goes back to the model once, with the names. The next answer counts either way, and the trace records what the check found.
  - Most ordinary words are some player's display name: "best", "me" and "Winter" all are. So without a dictionary, the check looks only where a name can be told apart:
    - words shaped like gamer tags: letters with digits, an underscore, or a capital inside (tike36, V3M_T4NQUIL0, megD);
    - bold text that isn't a label.
  - Numbers, ordinals and any words the conversation already showed don't count.
  - A plain name outside bold, such as Raydish, isn't checked.
  - Replayed through the new tools on this run's three answers and a smoke test's (question 7), it flags only question 8's tike36.
- **Answer guidance in the prompt:** players' current display names, the scope ("at official events, in 1v1"), which player an ambiguous name was taken to mean, and the main facts the question asks for.

## 2026-10-10: model comparison for one-prompt text-to-SQL

**Question:** which local model should the agent start from: qwen3:4b or qwen3:8b, with thinking on or off?

**Exploratory, not the formal baseline.**
- The expected answers come from our own data, through the target questions' regression check (`ingest/target_questions.py`).
- So this compares models on the same footing, but it doesn't measure correctness against an independent gold set.
- Ten questions, one run each.

**Setup** (`eval/model_comparison.py`):
- **Questions:** the ten target questions Phase 1 answers (1–4, 6–8 and 10–12).
- **Prompt:** one per question, the same for every model. Its full text is in the results file.
  - A compact description of the tables and views the questions need: aliases, players, events and nine views.
  - The counting rules, and a pattern for turning a name into a player's ID through `player_aliases`.
  - The question, asking for one SQLite query in a code block.
  - No agent loop, no retries and no examples.
- **Query:** runs on `data/db/eval/eval-v1.sqlite`, read-only, stopped after 90 s.
- **Checking:** the result is checked against the key facts of the expected answer, in whatever shape the query returns them. For example, a count of 6 or the six wins listed both count. The checks were validated first with hand-written right and wrong queries.
- **Models:** Ollama 0.40.2 on another machine, with each model's own sampling defaults (temperature 0.6, top_p 0.95, top_k 20). Seed 0, a 16,384-token context and an 8,192-token output cap.
- **qwen3:4b can't turn thinking off.** It's Qwen3-4B-Thinking-2507: with `think: false` it still reasons, only in the reply itself instead of in a separate thinking field.

**Results** (run `20261010T062843Z`):

| Model | Thinking | Correct | Mean time (s) | Mean output tokens | Failures |
|---|---|---|---|---|---|
| qwen3:4b | off* | 9/10 | 35.6 | 5,642 | empty result 1 |
| qwen3:4b | on | 8/10 | 34.2 | 5,537 | cut off at the output cap 1, empty result 1 |
| qwen3:8b | off | 2/10 | 2.1 | 142 | empty result 5, unknown column 2, wrong answer 1 |
| qwen3:8b | on | 8/10 | 22.2 | 2,603 | empty result 2 |

Time runs from request to reply, and output tokens include the thinking.

\*The two qwen3:4b rows are the same generations, token for token, since the model thinks either way.
- On question 3, its reply hit the 8,192-token cap before its final query was complete.
- With thinking off, the reasoning is part of the reply, so the script found a complete draft query in it, which happened to be right.
- Counted as a failure, both rows are 8/10.

| Question | qwen3:4b off | qwen3:4b on | qwen3:8b off | qwen3:8b on |
|---|---|---|---|---|
| 1. Boomie's last tournament | ✓ | ✓ | unknown column | ✓ |
| 2. Raydish's majors | ✓ | ✓ | ✓ | ✓ |
| 3. Hexo's 1v1 top 8 | ✓\* | cut off at the output cap | empty result | ✓ |
| 4. Impala vs Balloonboy | empty result | empty result | empty result | ✓ |
| 6. megd's 2v2 partners | ✓ | ✓ | unknown column | empty result |
| 7. Balloonboy's medals | ✓ | ✓ | ✓ | ✓ |
| 8. Best record against marckiemoo | ✓ | ✓ | empty result | empty result |
| 10. BCX 2022's bracket links | ✓ | ✓ | empty result | ✓ |
| 11. Raydish's most dominant win | ✓ | ✓ | wrong answer | ✓ |
| 12. flowers' first top 8 | ✓ | ✓ | empty result | ✓ |

**What went wrong:**
- **Name resolution, most of all: 9 of the 13 failures.** Instead of the alias lookup the prompt showed, the query matched:
  - a name against `players.name` ('megd', 'Balloonboy', 'flowers', 'marckiemoo', 'Hexo');
  - or an event against `tournament_name` ('BCX').

  It got nothing back, because display names differ in case or spelling: megD, BBBalloonBoy, flowerVS, Marckiem00, Hexoo. qwen3:8b without thinking did this on 5 questions, and both models did it on question 4.
- **Columns that don't exist** (qwen3:8b without thinking, 2): `v_team_results.mode`, and a subquery's column called by the wrong name.
- **A wrong ranking** (qwen3:8b without thinking, question 11).
- **A reply cut off** at the output cap (qwen3:4b, question 3).

**A database finding for the agent:**
- The head-to-head views are fast with a literal player ID (0.1 s), but slow when the ID comes from a lookup inside the same query (43–50 s on their own). SQLite doesn't push such a filter into the grouped view.
- Here, seven such queries took 75–84 s. With a 30 s limit, three correct answers would have been timeouts.
- The agent should look up player IDs first, as a separate step, and query with the IDs.

**Recommendation** (the decision is the user's): **qwen3:8b with thinking on.**
- It matched qwen3:4b's accuracy here (8 of 10), in about two-thirds of the time and half the output tokens.
- Both its failures were name resolution, which the agent should take out of the model's hands: a step that turns names into IDs with the alias rules, before any SQL. That step also avoids the slow head-to-head path. (Only partly: see the failure analysis below.)
- qwen3:4b only comes with thinking, writes about 5,600 tokens per answer, and hit the 8,192-token cap once.
- qwen3:8b without thinking is fast (2 s) but got 2 of 10 on its own. It may do better inside an agent loop with that lookup step and a chance to retry, which this didn't test.

**Caveats:**
- Ten questions, one seed each, so a difference of one question is noise.
- The expected answers come from our own data.
- The checks accept any shape that holds the answer's key facts.

**Decision** (the user's, 2026-10-10, after the failure analysis below): **qwen3:8b with thinking on, for development, provisionally.**
- Once the agent loop and the verified evaluation set exist, the comparison is rerun inside the agent, with qwen3:4b, qwen3:8b and qwen3:14b.

### Failure analysis

Every query, the reruns run by run, and four example failure logs are in [`model-comparison-failures.md`](model-comparison-failures.md).

**Why qwen3:8b missed questions 6 and 8**, with thinking on and off:
- It looked the name up in `players.name`, not `player_aliases`. 'megd' misses `megD` only by case, and 'marckiemoo' is a nickname for `Marckiem00`.
- It chose the same views as qwen3:4b.
- On question 6 the rest of the query was right.
- On question 8 the logic was wrong too, in both configurations, though the empty result hid it.
  - With thinking off, it returned marckiemoo's own ID.
  - With thinking on, it read `v_head_to_head_1v1` from both sides, which scores every opponent 0.5.

**Reruns** (run `20261010T181126Z`): questions 6 and 8 again with seeds 1–5, thinking on, otherwise as above.

| Question | qwen3:4b | qwen3:8b |
|---|---|---|
| 6. megd's 2v2 partners | 5/5 by the check, 3/5 on inspection | 3/5 |
| 8. Best record against marckiemoo | 1/5 by the check, 4/5 correct queries | 0/5 (3/5 with the name fixed) |

- qwen3:4b, question 6: two of the answers that passed list megD as their own partner, which the check missed.
- qwen3:4b, question 8: three misses were correct queries over the 90 s limit (18–28 s when run alone), and one reply hit the output cap.

**Consistent or chance:**
- **qwen3:8b's name lookup:** chance on question 6, where it used the alias lookup in all five reruns. Consistent on question 8: `players.name` in 5 of 6 tries (seed 0 included), and no right answer in 6.
- **A second error in both models:** both read views that hold every pairing from both sides as if they held each pairing once. qwen3:8b did it in 4 of its 12 tries at these questions, qwen3:4b in 2.
  - The prompt doesn't say that each pairing appears twice.
  - A step that turns names into IDs first wouldn't prevent it.
- **Correct queries, of ten reruns each:** qwen3:4b wrote 7 and qwen3:8b 3. qwen3:8b would have written 6 with names turned into IDs first.
- **Time:** on these two questions the models took about as long, 38.8 s and 35.0 s per reply over six seeds.

**Corrections to the entry above:**
- qwen3:8b's two failures weren't only name resolution: question 8 was also wrong logically.
- Question 6's check passes an answer that lists the player as their own partner.
- The correct question 8 query took anywhere from 18 s to over 90 s on this machine, so a 90 s limit isn't a reliable cutoff for it.

**For the agent** (decided 2026-10-10):
- **Name lookup is a separate tool**, not left to the model's SQL.
- **The head-to-head views store each pairing more than once:** `v_head_to_head_1v1` twice, once from each player's side, and `v_head_to_head_2v2` four times, once for each player in the meeting.
  - The agent's schema documentation must state how to read them from one side. `v_head_to_head_1v1`'s definition doesn't say it today, and the comparison's prompt didn't either.
  - The result checker should flag suspicious results, such as every row having the same value.
  - `v_team_results` also stores each team twice, once from each partner's side. The question 6 errors were in that view.
- **Player IDs are looked up before head-to-head queries,** to avoid the slow path: 0.1 s with the ID itself, against 18 s to over 90 s with the lookup inside the query.
