# Experiment log

One entry per experiment, newest first: what it asked, how it was set up, what it found, and what it decided. Results are in `eval/results/`. The models' full replies, thinking included, are in `data/experiments/` (git-ignored).

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
- The result checker could also flag an answer that names a player no observation returned, as question 8's did.
- Rerun with seeds 1–5, as the comparison's reruns did, before reading anything into rates.

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
