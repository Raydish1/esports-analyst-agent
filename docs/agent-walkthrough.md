# How the agent works

The agent answers questions about official Brawlhalla results. It's a **ReAct loop**: a language model that reasons, calls a tool, reads the result, and repeats until it can answer. Ours runs qwen3:8b with thinking on, through Ollama's native tool calling. It has two tools, `resolve_player` and `run_sql`, and three guardrails in code, all on the frozen snapshot `eval-v1`.

It's a prototype in three files:
- [`agent/ask.py`](../agent/ask.py): the command you run.
- [`agent/react.py`](../agent/react.py): the system prompt, the loop and the guardrails.
- [`agent/tools.py`](../agent/tools.py): the two tools.

Sections 1–7 describe the prototype at commit `2889492`, and their line references are to it. These changes came after it (2026-10-23 to 2026-10-25), and sections 8–11 describe them, with line references to commit `fc41b9b`:
- match scores for `resolve_player`'s candidates, and suggestions instead of a guess when a name matches only loosely, kept in the history as the agent's clarifying question (section 8);
- a third tool, `resolve_event`, for event names (section 8);
- a diagnosis for results with no rows, and the lookup check, which sends back an answer after an empty result that a missing text value explains (section 8);
- quoted names and player IDs in the answer check, and the no-tool check for an answer that states facts without a tool call (section 8);
- retrieval of worked examples by meaning, shown before each question (sections 9–11);
- smaller ones: `ask.py --seed N` and `--examples off`, and `react.py --eval ID` for evaluation set questions.

Since then, `agent/` has five files: [`diagnose.py`](../agent/diagnose.py) explains empty results, and [`retrieval.py`](../agent/retrieval.py) retrieves the examples in [`agent/examples/examples.toml`](../agent/examples/examples.toml). The [experiment log](experiments.md) has every run.

Some terms used throughout:
- A **step** is one model reply.
- A **turn** is one question's steps, up to 8.
- An **observation** is a tool's result, as the model reads it.
- A **trace** is the record of a turn.

```mermaid
flowchart LR
  you[You] -->|question| ask[ask.py]
  ask -->|Conversation.ask| loop[ReAct loop]
  loop -->|answer| ask
  ask -->|prints| you
```

## 1. The entry point: `ask.py`

You run `python agent/ask.py "question"` for one question, or `python agent/ask.py` for a session. `main` does four things before the first question reaches the model ([ask.py:136](../agent/ask.py#L136)):

```python
# agent/ask.py:147-156
header = react.run_header(start, title=f"Agent session {start}")
...
show = (lambda step: [out(line) for line in step_lines(step)]) if args.trace else None
conversation = react.Conversation(react.Tools(), log=lambda *_: None, on_step=show, model=react.MODEL, think=True,
                                  seed=0)
session = Session(conversation, SESSIONS / start, header)
```

- **The run header:** `run_header` asks the Ollama server for its version and the model's details, and reads the snapshot's build ID ([react.py:415](../agent/react.py#L415)). So an unreachable server fails here, with a plain message, not mid-question. The server's address is `OLLAMA_BASE_URL` in `.env`, loaded by `load_env()`.
- **The tools:** `react.Tools()` loads every player alias into memory, which takes about 10 seconds (section 4).
- **The conversation:** `react.Conversation` holds the system prompt and the history (section 3). With `--trace`, `on_step` prints each step as it finishes, through `step_lines` ([ask.py:68](../agent/ask.py#L68)).
- **The session:** `Session` wraps the conversation, and saves the transcript after every question ([ask.py:107-118](../agent/ask.py#L107)):

```python
# agent/ask.py:107-111
def ask(self, question):
    trace = {"turn": len(self.traces) + 1, **self.conversation.ask(question)}
    self.traces.append(trace)
    self.save()
    return trace
```

With no question on the command line, `interactive` reads questions until `exit` or the end of the input ([ask.py:121](../agent/ask.py#L121)). Every question goes to the same `Conversation`, which is how a follow-up like "now only 2v2" sees the question before it. Transcripts go to `data/experiments/sessions/`, which is git-ignored.

`react.py` has its own entry point for experiments: `python agent/react.py --target 8 --seed 0`. Its `run()` starts a fresh `Conversation` for each question ([react.py:403](../agent/react.py#L403)), so target questions never share history.

## 2. The system prompt

The system prompt is one string, `SYSTEM`, at [react.py:51-134](../agent/react.py#L51). It's the first message of every request. `Conversation.__init__` fills in its three numbers: the token budget, the query time limit and the step limit ([react.py:291](../agent/react.py#L291)). It has six parts:

| Part | Lines | What it tells the model |
|---|---|---|
| Using the tools | [55-71](../agent/react.py#L55) | resolve every name before any SQL; what each status means; reduce data in SQL; what a result too large to show looks like |
| Tables | [73-77](../agent/react.py#L73) | `players` (for names) and `event_aliases` |
| Views | [79-99](../agent/react.py#L79) | the eleven views it may query, with their columns |
| Views that hold each pairing more than once | [101-110](../agent/react.py#L101) | how to read the head-to-head views and `v_team_results` from one side |
| Counting rules | [112-122](../agent/react.py#L112) | medals, crew battles, DQs, "best record", "first top 8" |
| Answering | [124-134](../agent/react.py#L124) | the step limit, current names, the scope ("official events, in 1v1"), saying what was assumed |

The views and counting rules are copied word for word from the model comparison's prompt ([`eval/model_comparison.py`](../eval/model_comparison.py)). A test checks they stay identical, so results compare across experiments. The rest was added for the agent, one part per failure the experiments found. For example:

```text
# agent/react.py:63
- resolve_player takes names only, never IDs. To get the name of a player_id, query players with run_sql.
```

The model also sees the tools themselves. `TOOLS` describes each one as a JSON schema: its name, what it does and its one argument ([react.py:136-152](../agent/react.py#L136)). Ollama renders these into the prompt in the format the model was trained on.

## 3. The ReAct loop

The loop lives in `Conversation.turn` ([react.py:309](../agent/react.py#L309)). Each pass is one step: send the messages, read the reply, then either run its tool calls or treat it as the answer.

```mermaid
flowchart LR
  you[You] -->|question| ask[ask.py]
  ask --> loop[ReAct loop]
  loop -->|messages and tool schemas| model[qwen3:8b on Ollama]
  model -->|thinking, and tool calls or an answer| loop
  loop -->|answer| ask
  ask --> you
```

### How messages are assembled

A request carries the whole conversation as a list of messages. `messages` puts it together on every step ([react.py:295-297](../agent/react.py#L295)):

```python
# agent/react.py:296-297
def messages(self):
    return [self.system, *self.earlier, *self.previous, *self.current]
```

- **`system`:** the prompt from section 2.
- **`current`:** this question so far. It's the question, then each assistant message with its tool calls, then one `tool` message per observation.
- **`previous`:** the question before, kept in full, so a follow-up can reuse its player IDs and queries.
- **`earlier`:** older questions, cut down to the question and the answer ([react.py:299-307](../agent/react.py#L299)). This keeps the context bounded.

### How Ollama is called

`chat` sends one request to Ollama's `/api/chat` ([react.py:174-177](../agent/react.py#L174)):

```python
# agent/react.py:176-177
return ollama("/api/chat", {"model": model, "stream": False, "think": think, "tools": TOOLS, "messages": messages,
                            "options": {**OPTIONS, "seed": seed}}, timeout=REQUEST_SECONDS)
```

- `"tools": TOOLS` is what makes this native tool calling. Ollama puts the schemas in the prompt, and when the model writes a tool call in its trained format, Ollama parses it into structured data. The loop never parses model text itself.
- `"think": True` turns on qwen3's reasoning, which comes back in its own field.
- The seed fixes the sampling, so the same question with the same seed gives the same reply on this server.
- The options give a 32,768-token context and cap each reply at 8,192 tokens ([react.py:44](../agent/react.py#L44)).

### How a reply is read

The reply's `message` has three parts, and the loop takes them apart in one line ([react.py:330](../agent/react.py#L330)):

```python
# agent/react.py:330
thinking, content, calls = message.get("thinking") or "", message.get("content") or "", message.get("tool_calls") or []
```

- `thinking`: the model's reasoning. It's saved in the trace and sent back in the history, but never shown as the answer.
- `content`: the text reply.
- `tool_calls`: a list like `[{"function": {"name": "resolve_player", "arguments": {"name": "marckiemoo"}}}]`.

### How a tool call is run and fed back

If the reply has tool calls, the loop first adds the assistant message to the history, then runs each call in order ([react.py:375-390](../agent/react.py#L375)):

```python
# agent/react.py:379-388, shortened, with comments added
observation = self.tools.call(name, arguments)          # run it
self.shown.observe(name, observation)                   # remember what the model has now seen (section 5)
...
text = json.dumps(observation, ensure_ascii=False)
self.current.append({"role": "tool", "tool_name": name, "content": text})   # feed it back
```

- `Tools.call` sends each call to the right tool by name ([react.py:191-209](../agent/react.py#L191)). A missing argument or an unknown tool name comes back as an `error` observation, so the model can correct itself rather than the loop crashing.
- The assistant message goes into the history with its content emptied ([react.py:373-375](../agent/react.py#L373)). The server's qwen3 template drops a message's tool calls when it also has text, and the model needs to see its own calls.

```mermaid
flowchart LR
  you[You] -->|question| ask[ask.py]
  ask --> loop[ReAct loop]
  loop -->|messages and tool schemas| model[qwen3:8b on Ollama]
  model -->|tool calls| loop
  loop -->|Tools.call| tools[resolve_player, run_sql]
  tools -->|observation| loop
  tools --- db[(eval-v1.sqlite)]
  model -->|answer| loop
  loop -->|answer| ask
  ask --> you
```

### When the loop stops

A turn ends in one of four ways:
- **A reply with no tool calls:** `ending()` names the outcome ([react.py:272-278](../agent/react.py#L272)). Text is `answered`, then the two answer checks run (section 5). No text is `empty reply`. A reply cut off at the output cap is `cut off at the output cap`, and a tool call written as text that Ollama didn't parse is flagged as such.
- **The 8th step still calling tools:** the outcome is `step limit`, and those calls aren't run ([react.py:366-372](../agent/react.py#L366)). To head this off, the observation before the last step says "You have one step left" ([react.py:384-385](../agent/react.py#L384)).
- **A request error:** the server couldn't be reached, and the outcome says so.
- **A check sends the answer back:** this doesn't end the turn. It adds a message and runs another step.

## 4. The tools

### `resolve_player(name)`: from a name to a player ID

People write names many ways: "megd" for megD, "marckiemoo" for Marckiem00, "Balloonboy" for a former name of BBBalloonBoy. The resolver turns a name into ranked candidate players. Everything it needs is loaded into memory once, by `Resolver.__init__` ([tools.py:96-109](../agent/tools.py#L96)): each player's current name, their canonical ID after merges, their count of official results, and every alias with its kind.

**Normalization:** names are compared as the builder stores aliases ([ingest/names.py:14-17](../ingest/names.py#L14)). That means no team tag, accents folded, lowercase, letters and digits only:

```python
# ingest/names.py:17
return re.sub(r"[\W_]+", "", fold((name or "").split("|")[-1]))
```

So "M30W | BalloonBoy" becomes `balloonboy`. `normalize_full` keeps the tag (`m30wballoonboy`), and the resolver tries both.

**Matching, in tiers:** the first tier that finds anyone wins ([tools.py:127-143](../agent/tools.py#L127)).

| Tier | Matches | Example |
|---|---|---|
| exact | the normalized name equals an alias; a curated nickname ranks first | "megd" → megD |
| swap | equal after undoing common swaps: `$` as s, digits as letters, l as i, doubled letters as one (`skeleton`, [tools.py:72](../agent/tools.py#L72)) | "baloonboy" → BBBalloonBoy |
| prefix | an alias that starts with it (3+ characters) | "rayd" → Raydish, first of several |
| fuzzy | a similar spelling, difflib ratio 0.8 or more (4+ characters) | "markiemoo" → Marckiem00 |

**Ranking:** candidates sort by tier, then by official results (most first), then by how strong the alias is ([tools.py:147](../agent/tools.py#L147)). Most results first reflects that a question about results is almost always about the active player. Two records are named Impala, with 48 results and 1, so "Impala" ranks the active one first.

**Status** ([tools.py:148-160](../agent/tools.py#L148)):
- `confident`: one match in the best tier, or several of which only one has official results.
- `ambiguous`: several matches with results, a shared name like Boomie, or only prefix and fuzzy matches.
- `not_found`: nothing matched.

Each candidate comes back with its `player_id`, current name, the spelling it matched, how it matched, and its results ([tools.py:164-172](../agent/tools.py#L164)). The prompt tells the model to use the first candidate, and to say so when the status is ambiguous.

### `run_sql(query)`: read-only queries with a budget

`run_sql` opens a fresh connection for each query, and locks it down three ways ([tools.py:201-205](../agent/tools.py#L201)):

```python
# agent/tools.py:201-205
db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
db.execute("PRAGMA query_only = ON")
db.set_authorizer(lambda action, *_: sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ATTACH else sqlite3.SQLITE_OK)
deadline = time.monotonic() + seconds
db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
```

- **Read-only:** `mode=ro` opens the file read-only, `query_only` refuses writes, and the authorizer refuses `ATTACH`, so no other database file can be reached.
- **Timeout:** SQLite calls the progress handler every 10,000 instructions, and returning 1 interrupts the query. After 30 seconds the model gets an error saying why queries get slow: a player lookup inside the query instead of a literal ID ([tools.py:211-213](../agent/tools.py#L211)).
- **Errors:** an SQL error comes back as an observation, `{"error": "OperationalError: no such column: format"}`, so the model can fix its query.

**The token budget:** every observation stays in the model's context until the answer, so one huge result could crowd out everything else. Every 1v1 set Raydish played is 455 rows and about 28,000 tokens of a 32,768-token context. So `run_sql` adds up each row's estimated cost as it builds the result ([tools.py:217-227](../agent/tools.py#L217)):

```python
# agent/tools.py:220-226
for row in rows:
    values = [cell(v) for v in row]
    size += tokens(json.dumps(values, ensure_ascii=False)) + 1  # and the comma between rows
    if size > TOKEN_BUDGET:  # the note first, before anything else the model reads
        return {"complete": False, "note": TOO_BIG.format(total=total, budget=f"{TOKEN_BUDGET:,}"),
                "row_count": total, "columns": columns}
    out["rows"].append(values)
```

- `tokens()` estimates cost without calling the model ([tools.py:189-194](../agent/tools.py#L189)). Qwen's tokenizer spends a token on almost every digit and JSON punctuation mark, and about one per four characters of other text. Against the server's real counts, that estimate was 9% under to 20% over.
- **Within the budget** (about 4,000 tokens), the result comes back whole: `{"complete": true, "columns": [...], "rows": [...], "row_count": 46}`.
- **Over it,** no rows come back at all. The model gets the row count, the columns and a note to reduce the result in SQL, for example with `GROUP BY` or `LIMIT`.
- Cells are kept short ([tools.py:181-186](../agent/tools.py#L181)): floats are rounded to 4 places, and text is cut at 300 characters.

## 5. The guardrails in code

The prompt asks for good behavior. These three checks enforce some of it, because the experiments showed the model doesn't always follow the prompt.

```mermaid
flowchart LR
  you[You] -->|question| ask[ask.py]
  ask --> loop[ReAct loop]
  loop -->|messages and tool schemas| model[qwen3:8b on Ollama]
  model -->|tool calls| loop
  loop -->|Tools.call| tools[resolve_player, run_sql]
  tools -->|observation| loop
  model -->|answer| checks{answer checks}
  checks -->|sent back with a note| model
  checks -->|passes| ask
  ask --> you
```

### Refusing IDs in `resolve_player`

In the first prototype run, the model passed a player ID to `resolve_player` to get a name. The character swaps and fuzzy matching then turned "71736" into a different player, tike36, and the answer named him. Now `as_player_id` spots an ID before any matching ([tools.py:80-90](../agent/tools.py#L80)): digits only ("71736", "#71736"), or written out ("player_id 71736"). `resolve` returns an error that says how to get the name instead ([tools.py:114-118](../agent/tools.py#L114)):

```python
# agent/tools.py:116-118
return {"name": name, "error": f"{name!r} looks like a player_id, not a name, and resolve_player takes names"
                              f" only. To get a player_id's name, use run_sql: SELECT player_id, name FROM"
                              f" players WHERE player_id = {number}"}
```

### Sending back an answer that follows a result too large to show

A result over the budget has no rows, so an answer straight after it can't rest on data. The loop keeps a flag, `too_big`, which every `run_sql` call sets or clears ([react.py:382-383](../agent/react.py#L382)). Only a new query clears it, not a name lookup. When an answer arrives while it's set, the loop sends it back ([react.py:338-347](../agent/react.py#L338)):

```python
# agent/react.py:338-342, with a comment added
if outcome == "answered" and too_big:
    if number + 2 <= max_steps:                       # room to query again, then answer
        step["size_check"] = {"action": "sent back", "message": TOO_BIG_ANSWER}
        self.current += [{"role": "assistant", "content": content, "thinking": thinking},
                         {"role": "user", "content": TOO_BIG_ANSWER}]
```

The send-back keeps the rejected answer in the history and adds a short user message explaining why. Without two steps left, the answer is kept, and the trace flags it (`answered_after_too_big`). So far this check has never fired: no result in 18 runs was over the budget.

### Checking for players no tool returned

A model can invent a name when it has only an ID: "Kael" for player 37977. The check asks whether the answer names a player that no tool returned in this conversation. It runs in two parts:
- **What the model has been shown.** `Shown` collects every word of the prompt, the questions and the observations. It also collects every player ID a tool returned, as a resolver candidate or as a number in a query result ([react.py:231-254](../agent/react.py#L231)).
- **Where the answer names a player.** Most ordinary words are some player's display name ("best", "me", "Winter" all are), so `name_spans` looks only where a name can be told apart without a dictionary ([react.py:214-228](../agent/react.py#L214)). That means words shaped like gamer tags (tike36, V3M_T4NQUIL0, megD) and short bold text (`**Raydish**`).

`unreturned` flags a span that is the current name of a real player, and isn't a number or a word the conversation already showed. It also checks that none of that name's players were returned ([react.py:256-267](../agent/react.py#L256)). A flagged answer goes back once, with the names, if a step is left ([react.py:348-358](../agent/react.py#L348)). The next answer counts either way, and the trace records what was flagged. So far it fired twice in 36 runs, both times on invented names.

## 6. A worked example: question 8

The question is "Who has the best record against marckiemoo?". This trace is question 8 at seed 0 from run `20261020T011930Z`. It was recorded with the version before the token budget, but every step below runs the same way in the current code.

Through `ask.py`, the question goes `main` → `Session.ask` → `Conversation.ask` → `turn`. The recorded run came through `react.py`'s `run()`, which joins the same path at `Conversation.ask`. `ask` adds the question to `current` and to `Shown`, and `turn` starts its steps.

| Step | Model time | What the model did | Code that ran | Observation |
|---|---|---|---|---|
| 1 | 7.2 s | thought "I need to figure out who marckiemoo is", called `resolve_player("marckiemoo")` | `chat` → `Tools.call` → `Resolver.resolve`: not an ID; the exact tier finds the curated nickname | `confident`: 146052 Marckiem00 |
| 2 | 10.1 s | queried the 1v1 head-to-head view from Marckiem00's side, with at least 5 matches, best win rate first | `run_sql`: read-only, 0.17 s, 1 row, within budget; `Shown.observe` records ID 71736 | `[[71736, 3, 2, 5]]` |
| 3 | 3.4 s | wanted the name of player 71736, and called `resolve_player("71736")` | `as_player_id` → 71736; `resolve` returns the refusal | error, with `SELECT player_id, name FROM players WHERE player_id = 71736` |
| 4 | 4.8 s | ran the name query it was given | `run_sql` | `[["V3M_T4NQUIL0"]]` |
| 5 | 4.8 s | answered | `ending` → `answered`; no result too large to show; `Shown.unreturned` finds nothing | the answer below |

The step 1 observation, as the model read it:

```json
{"name": "marckiemoo", "status": "confident", "note": "Use player_id 146052.",
 "candidates": [{"player_id": 146052, "name": "Marckiem00", "matched": "marckiemoo", "match": "curated nickname",
                 "official_results": 47, "results_from": "2022-05-08", "results_to": "2026-09-27",
                 "note": "Marckiem00, formerly ECHO | Marckiemoo"}]}
```

The step 2 query, written by the model with the literal ID, as the prompt asks:

```sql
SELECT player_id, wins, losses, (wins + losses) as matches FROM v_head_to_head_1v1
WHERE opponent_id = 146052 AND (wins + losses) >= 5
ORDER BY (wins * 1.0 / (wins + losses)) DESC, wins DESC, losses ASC LIMIT 1;
```

It reads the view from one side (`opponent_id = 146052`), as the pairing section of the prompt says. It also multiplies by `1.0` to avoid integer division.

The answer at step 5 passed both checks. `V3M_T4NQUIL0` and `Marckiem00` are gamer-tag shaped, but both had appeared in observations:

> At official events in 1v1, **V3M_T4NQUIL0** has the best record against **Marckiem00** (player_id 146052), with a **3-2 record (60% win rate)** across 5 matches. This is the highest win rate among players with at least 5 matches against Marckiem00.

That's the expected answer from the evaluation set (q08), with its minimum stated. The whole turn took 30.3 s of model time and 0.2 s in the tools.

The prompt grew with each step: 1,892, 2,445, 3,087, 3,354 and 3,670 tokens. That's every step's thinking, call and observation added to the history. Most of it was already in the server's cache: 1,876 of 1,892 tokens at step 1, and 3,355 of 3,670 at step 5. So each request resends the whole conversation, but the server only processes the new part.

## 7. Known limitations

From the [experiment log](experiments.md), on questions 4, 6 and 8 with six seeds each, as of commit `2889492`. Section 11 says which of these the later changes fixed.

- **Questions that read as a list aren't aggregated.** Question 6 ("who has megd played with, and how did they place?") failed in all 6 runs, twice. The model lists rows instead of grouping them in SQL. Reading 46 rows, it gave results to the wrong partner and got the counts wrong. A prompt rule didn't change that. See "2026-10-19: the result-size fixes".
- **Filtering on a value no row has.** Asked about 2v2, the model filters `format = '2v2'`, which never matches: 2v2 is a mode, and `v_team_results` holds only 2v2. It then takes the empty result as fact ("megD never played 2v2"). This happened in 3 of 12 question 6 runs.
- **Pairings read from both sides.** The head-to-head view holds each pairing twice, and the prompt says so. Even so, one answer added both rows (3–3 instead of 2–1), and another swapped the two players' names.
- **SQL slips.** Integer division (`wins / matches` truncates in SQLite) picked the wrong player once. A `COUNT(*)` on a view that already holds one row per pair made every count 1 and emptied a result once.
- **Answers leave things out.** Question 4's answers give the record but never its sets. Every run called BBBalloonBoy by the question's "Balloonboy", and some question 8 answers don't state the 5-match minimum.
- **The answer check is partial by design.** It only looks at words shaped like gamer tags and at bold text, so a plain invented name, such as Raydish written in plain text, isn't checked.
- **The token estimate is approximate.** It's 9% under to 20% over, and a user who really wants a long list has no way to get it yet. The decided design, not built, sends the full table to the user directly instead of through the model.
- **Players whose only names are digits can't be found by name** (464 on eval-v1), since `resolve_player` refuses digits.
- **Small samples:** three questions and six seeds each, judged by hand against the verified evaluation set. Times depend on the server, whose speed varied between runs.
- **The scope:** one model (qwen3:8b), the frozen eval-v1 snapshot, and official events only. The planned design, with LangGraph and an evaluation harness, isn't built yet.

The next fixes waiting on a decision are listed at the end of the latest entry in the [experiment log](experiments.md).

## 8. The new guardrails

Sections 4 and 5 showed two tools and three checks. This module added a third tool, match scores on both resolvers, a diagnosis for empty results, and three more answer checks. Each one answers a failure from the experiment log. Line references from here on are to commit `fc41b9b`.

```mermaid
flowchart LR
  you[You] -->|question| loop[ReAct loop]
  loop -->|messages| model[qwen3:8b]
  model -->|tool calls| loop
  loop -->|Tools.call| tools[resolve_player, resolve_event, run_sql]
  tools -->|observation, with a diagnosis if empty| loop
  loop -->|a loose name match| sugg[suggestions to you]
  model -->|answer| checks{five answer checks}
  checks -->|sent back with a note| model
  checks -->|passes| you
```

### Match scores and statuses

Before, a prefix or a similar spelling came back as "ambiguous", and the model used the first candidate anyway. So "markiemoo" could quietly become someone else. Now every candidate has a **match score**: its tier's base times how close it is within the tier ([tools.py:83-91](../agent/tools.py#L83)).

```python
# agent/tools.py:90-91
SCORES = {"nickname": 1.0, "exact": 0.98, "swap": 0.92, "prefix": 0.85, "fuzzy": 0.85}
CONFIDENT = 0.9
```

- **Closeness** is 1 in the exact tiers, the share of the alias a prefix covers, and difflib's ratio for a similar spelling. `add` multiplies the two when it records a candidate ([tools.py:164-169](../agent/tools.py#L164)).
- **The status** is now `ambiguous` whenever the best score is under 0.9 ([tools.py:195-197](../agent/tools.py#L195)). That puts character swaps above the line, and prefixes and similar spellings below it.
- The scores rank matches. They aren't probabilities, and the order still follows official results within a tier.

Here is "markiemoo" on eval-v1. It's only a similar spelling of the curated nickname "marckiemoo":

```json
{"name": "markiemoo", "status": "ambiguous",
 "candidates": [{"player_id": 146052, "name": "Marckiem00", "match": "similar spelling", "score": 0.8, "official_results": 47},
                {"player_id": 101849, "name": "Markled", "match": "similar spelling", "score": 0.68, "official_results": 2},
                {"player_id": 104811, "name": "Arklem", "match": "similar spelling", "score": 0.73, "official_results": 1}, ...]}
```

Arklem scores higher than Markled but comes after him, because Markled has more official results.

### Suggestions instead of a guess

When a name from the question matches only below 0.9, the agent stops and asks you. `unsure` decides that ([react.py:365-370](../agent/react.py#L365)):

```python
# agent/react.py:368-370
in_question = normalize_full(name) and normalize_full(name) in normalize_full(question)
candidates = observation.get("candidates") or []
return bool(in_question and candidates and max(c["score"] for c in candidates) < CONFIDENT)
```

- The name must appear in the question. A name the model made up itself, such as a misspelling in its own call, isn't yours to settle.
- After a step's tool calls run, any such names end the turn with the outcome `suggestions` ([react.py:577-582](../agent/react.py#L577)). No more model steps run.
- You see `suggestions()`: "I couldn't find a player named "markiemoo", so I won't guess", then the top three with their results and years, then "Which one did you mean?" ([react.py:373-385](../agent/react.py#L373)).

**How suggestions stay in the history.** The conversation needs a record of this turn, so the next question ("the first one") makes sense. At first it stored the suggestions as the agent's answer. In one session, a later question then copied that format as its own answer, with invented player IDs (12345 for Markled). So now the history holds `clarifying()` instead ([react.py:388-395](../agent/react.py#L388)):

```python
# agent/react.py:395
return f"(A clarifying question to the user, not an answer.) I asked {asked}. Their next message answers it."
```

`asked` lists each candidate with its real player ID. `Conversation.ask` stores this text in place of the answer ([react.py:445](../agent/react.py#L445)). The model sees a question it asked, with the IDs it needs to act on your reply, and nothing shaped like an answer to copy. See "2026-10-23: the lookup changes" and "2026-10-25: the decisions on the lookup run" in the [experiment log](experiments.md).

### `resolve_event(name)`: from an event name to event IDs

In a live session, the model searched `event_name LIKE '%worlds%'`, got nothing, and answered that Marckiem00 never won Worlds. He won BCX 2025, whose `event_name` is empty and which is "worlds" only through an alias. `resolve_event` does for events what `resolve_player` does for players. It loads every official event, the curated aliases and the curated terms into memory once ([tools.py:229-261](../agent/tools.py#L229)).

A mode word (1v1, 2v2, singles, doubles) narrows the events to that mode. The rest of the name is matched in tiers, and the first tier that finds anything wins ([tools.py:263-312](../agent/tools.py#L263)):

| Tier | Matches | Score | Example |
|---|---|---|---|
| alias | a curated alias in `event_aliases` | 1.0 | "bcx 2022" |
| series | an alias stem with two or more years | 0.95 | "worlds" is every "worlds YYYY" |
| words | events whose name has every word, with years and curated terms ("na" for "north america") | 0.9 | "winters 2023 na 1v1" |
| some words | the events with the most words, if half or more | 0.85 × share | |

The statuses work as for players. `ambiguous` means several tournaments matched every word, or only some words matched. The result also carries a ready-made SQL condition ([tools.py:368-380](../agent/tools.py#L368)): the event IDs when there are 12 or fewer, else a subquery on the aliases. The real result for "worlds", trimmed:

```json
{"name": "worlds", "status": "confident", "matched": "aliases 'worlds 2017' to 'worlds 2025'", "score": 0.95,
 "event_count": 34, "tournament_count": 17,
 "sql": "event_id IN (SELECT event_id FROM event_aliases WHERE alias IN ('worlds 2017', ..., 'worlds 2025'))",
 "events": [{"event_id": "c979b223-...", "name": "Brawlhalla World Championship Expo 2025 - 1v1", ...}, ...]}
```

The model pastes the `sql` into its `WHERE`, so it never copies 34 IDs. The prompt tells it to call `resolve_event` for every event the question names and never to search names with LIKE ([react.py:70-75](../agent/react.py#L70)). In the next run, all six sessions resolved "worlds" this way and found the BCX 2025 win.

### The diagnosis of an empty result

An empty result is the hardest one to trust. "No rows" can mean the true answer is none, or that the query had a wrong filter. The model used to take it as fact: asked about megD in 2v2, it filtered `format = '2v2'` (2v2 is a mode, never a format) and answered "megD never played 2v2". Now `run_sql` adds a diagnosis to every result with no rows ([tools.py:451-453](../agent/tools.py#L451)).

`diagnose` works without a SQL parser ([diagnose.py:105-145](../agent/diagnose.py#L105)):
1. **Find the conditions.** A small scanner finds the top-level `WHERE` and `HAVING` and splits them at their top-level `AND`s, skipping quotes, comments, parentheses and the `AND` of a `BETWEEN` ([diagnose.py:62-86](../agent/diagnose.py#L62)). A clause with a top-level `OR` stays whole, and a `UNION` gets no conditions.
2. **Remove each one in turn.** It swaps the condition for `1=1` and counts the rows:

   ```python
   # agent/diagnose.py:123
   rows = probe(f"SELECT COUNT(*) FROM (SELECT 1 FROM ({query[:a]} 1=1 {query[b:]}) LIMIT {COUNTED + 1})")
   ```

3. **Check the value.** For a condition comparing a column with a literal (`format = '2v2'`, `player_id = 142100`), it asks whether the value occurs in that column at all, and lists the column's values when there are 12 or fewer ([diagnose.py:126-143](../agent/diagnose.py#L126)).

Each probe stops after 4 seconds and all of them after 12, so a diagnosis never makes a query slow. `note` turns the findings into a few sentences ([diagnose.py:148-166](../agent/diagnose.py#L148)). Here is the real one from question 6, seed 1, without retrieval, trimmed:

```json
{"rows": [], "row_count": 0,
 "diagnosis": {"note": "Without e.format = '2v2', the query returns 46 rows. No row has e.format = '2v2'. Its column's values there: 'standard', 'crew_battle', '3v3', 'brawlball', 'triples', 'kung_foot'. A text value no row has usually means a lookup went wrong, not that the answer is none. ...",
  "conditions": [{"condition": "tr.player_id = 142100", "rows_without_it": 0, "value_found": true, "value": 142100},
                 {"condition": "e.format = '2v2'", "rows_without_it": 46, "value_found": false, "value": "2v2", ...}]}}
```

It names the culprit exactly: drop the format filter and 46 rows come back.

### The lookup check

A diagnosis the model can ignore is only advice. The lookup check makes one kind of it count. `missing_text` picks out the conditions that compare a column with a **text** value no row has ([diagnose.py:169-174](../agent/diagnose.py#L169)):

```python
# agent/diagnose.py:173-174
return [f["condition"] for f in (diagnosis or {}).get("conditions", ())
        if isinstance(f.get("value"), str) and f.get("value_found") is False]
```

Every `run_sql` call resets the list, so only the latest query counts ([react.py:568](../agent/react.py#L568)). An answer that arrives while it's set goes back once with `LOOKUP_MISS`, if two steps are left to query and answer ([react.py:501-512](../agent/react.py#L501)). The message says the empty result is probably a lookup mistake, and that the same answer may come back if the empty result is right.

Only text counts, by design. A name, an event or a format that no row has is almost always a wrong lookup. A number no row has, or values that exist but never together, can be a true "none". Raydish has no Worlds wins, and those empty results stood, rightly.

The check gives the model a second chance, not a right answer. In question 6, seed 1 without retrieval, it sent the "no 2v2" answer back. The model listed the formats, saw no "2v2" among them, and gave the same wrong answer.

### Three answer checks

Section 5's answer check looked at words shaped like gamer tags and bold text. It now reads more, and two checks joined it. `turn` runs them in this order on every answer ([react.py:489-548](../agent/react.py#L489)), and each sends an answer back at most once:

| Check | Sends back an answer that | Found by | Why it was added |
|---|---|---|---|
| result size | follows a result too large to show | `too_big` flag (section 5) | |
| lookup | follows an empty result missing a text value | `missing_text` | "megD never played 2v2", "never won Worlds" |
| no tool | states facts in a question that called no tool | `Shown.facts` | a turn that imagined its lookup and invented IDs |
| names | names a player no tool returned, now in quotes too | `Shown.unreturned` | "Kappa (hypothetical example)", in quotes |
| IDs | cites a player ID no tool or question showed | `Shown.unreturned_ids` | 12345 and 67890 for Markled and Arklem |

**Quoted names.** `QUOTED` finds text in straight or curly quotes, but not an apostrophe such as megD's ([react.py:202-204](../agent/react.py#L202)). `name_spans` adds quoted text of up to three words beside bold text ([react.py:281-284](../agent/react.py#L281)).

**Player IDs.** `cited_ids` finds the IDs an answer cites ([react.py:288-294](../agent/react.py#L288)): a number after an ID word ("player_id 12345", "partner ID 5"), or a number of five digits or more alone in bold or parentheses ("Impala (168635)"). An event's or a match's ID doesn't count. `unreturned_ids` keeps the ones no observation or question contained ([react.py:340-342](../agent/react.py#L340)):

```python
# agent/react.py:342
return [n for n in cited_ids(answer) if abs(n) not in self.numbers]
```

**Answers with no tool call.** The loop sets `called` when a step runs any tool ([react.py:559](../agent/react.py#L559)). An answer in a question that never called one goes to `Shown.facts`, which collects the players it names, the IDs it cites and its numbers, leaving out formats such as 1v1 ([react.py:344-352](../agent/react.py#L344)). If there are any, the answer goes back with `NO_TOOL` ([react.py:513-528](../agent/react.py#L513)). The message allows the same answer again, since a follow-up can rightly reuse an earlier question's results.

Replayed on all 94 answers since the first prototype run, the ID check and the no-tool check each flag exactly one, the same answer: the turn that invented Markled's and Arklem's IDs. See "2026-10-25: the ID and no-tool checks, replayed on every past answer" in the [experiment log](experiments.md).

## 9. Retrieval of worked examples

Retrieval-augmented prompting means finding relevant text at question time and putting it in the prompt. Here the text is **worked examples**: questions of common shapes, each with the SQL that answers it and why it's shaped that way. Before each question, the agent finds the few examples worded most like it and shows them to the model as patterns. This is often called dynamic few-shot prompting.

What is retrieved is how to query, not data. `run_sql` already retrieves data, exactly, by SQL. The examples fix a different gap: the model knew the views but kept writing the wrong shape of query, such as reading 46 rows instead of grouping them.

### The example bank

[`agent/examples/examples.toml`](../agent/examples/examples.toml) holds 28 examples of 25 shapes. Each is a TOML table, and `load` checks the fields and that IDs aren't repeated ([retrieval.py:58-70](../agent/retrieval.py#L58)). The teammates example:

```toml
# agent/examples/examples.toml:98-109
[[example]]
id = "ex08"
shape = "teammates"
question = "Who has Phazon partnered with in 2v2, and how did they do together?"
note = "Aggregate per partner in SQL (COUNT, MIN) instead of reading every result; v_team_results holds only 2v2, so no mode filter."
sql = '''
SELECT p.name AS partner, COUNT(*) AS events, MIN(t.placement) AS best_placement, SUM(t.placement = 1) AS wins
FROM v_team_results t JOIN players p ON p.player_id = t.partner_id
WHERE t.player_id = 147522
GROUP BY t.partner_id
ORDER BY events DESC, best_placement
'''
```

- `question` is the only part embedded, so retrieval matches questions with questions.
- `note` carries the lesson. It's what tells the model why the query looks this way.
- `shape` names the question shape, used only to measure retrieval. `expect = "empty"` marks a query whose right result has no rows.
- No example names a player or uses an event from the evaluation set or the target questions, so an example never gives an answer away. `python agent/retrieval.py check` runs every query on eval-v1 and checks that rule ([retrieval.py:81-112](../agent/retrieval.py#L81)).

### Embedding and storing the examples

An **embedding** is a list of numbers that places a text by its meaning, so texts with similar meanings get nearby vectors. The examples' questions are embedded with nomic-embed-text, through the same Ollama server as the chat model (`/api/embed`, [retrieval.py:117-123](../agent/retrieval.py#L117)). Each text gets the prefix `clustering: `, nomic's task prefix for comparing texts of one kind. On the evaluation questions it did as well as no prefix, and better than the query and document pair ([retrieval.py:38-42](../agent/retrieval.py#L38)).

The vectors live in **Chroma**, a vector database, in a collection on disk in `data/rag/chroma` (git-ignored). `Retriever.__init__` builds it ([retrieval.py:154-176](../agent/retrieval.py#L154)):

```python
# agent/retrieval.py:170-175
collection = client.create_collection(COLLECTION, embedding_function=None,
                                      metadata={"hnsw:space": "cosine", "fingerprint": stamp})
ids = list(self.examples)
collection.add(ids=ids, documents=[self.examples[i]["question"] for i in ids],
               embeddings=self.embed([prefix + self.examples[i]["question"] for i in ids]),
               metadatas=[{"shape": self.examples[i]["shape"]} for i in ids])
```

- `embedding_function=None` means Chroma stores the vectors it's given and never embeds anything itself.
- `"hnsw:space": "cosine"` makes Chroma measure **cosine distance**. Similarity is 1 minus that distance: 1 for the same direction, lower for less alike.
- `stamp` is a **fingerprint**, a hash of the model, the prefix and every example's ID and question ([retrieval.py:143-146](../agent/retrieval.py#L143)). On startup, a stored collection with another fingerprint is deleted and rebuilt ([retrieval.py:161-168](../agent/retrieval.py#L161)). So editing the bank never leaves stale vectors, and an unchanged bank costs no embedding calls.

```mermaid
flowchart LR
  bank[examples.toml] -->|questions, with the prefix| embed[nomic-embed-text]
  embed -->|28 vectors| chroma[(Chroma collection)]
```

### Retrieving examples for a question

`retrieve` embeds the user's question the same way, asks Chroma for the 10 nearest examples, and keeps those at a similarity of 0.70 or more ([retrieval.py:178-189](../agent/retrieval.py#L178)):

```python
# agent/retrieval.py:182-186
vector = self.embed([self.prefix + question])[0]
found = self.collection.query(query_embeddings=[vector], n_results=min(CANDIDATES, len(self.examples)),
                              include=["distances", "embeddings"])
above = [(i, 1 - d, list(v)) for i, d, v in zip(found["ids"][0], found["distances"][0], found["embeddings"][0])
         if 1 - d >= threshold]
```

**The threshold** (0.70) is meant to give no examples to a question no example fits. It was set at about the 10th percentile of the best helpful example's similarity on the evaluation questions ([retrieval.py:43](../agent/retrieval.py#L43)). Measured, it separates poorly: it took every example from three questions they would have helped, and kept 13 of the 18 given to questions no shape helps. Similar wording drives the scores more than a similar query does.

### How MMR picks three

The 10 nearest examples are often near-duplicates of each other, such as three ranking questions. Showing all three wastes the prompt on one pattern. **Maximal marginal relevance** (MMR) picks one at a time, scoring each candidate by its similarity to the question minus its similarity to the picks so far ([retrieval.py:130-140](../agent/retrieval.py#L130)):

```python
# agent/retrieval.py:135-137
def score(c):
    return lam * c[1] - (1 - lam) * max((cosine(c[2], p[2]) for p in chosen), default=0.0)
best = max(left, key=score)
```

`lam` is 0.7, so similarity to the question weighs more than variety. Question 6's numbers show how it plays out:
- **First pick:** nothing is chosen yet, so the score is 0.7 × similarity. ex17 (ranking, 0.808) wins with 0.566.
- **Second pick:** ex08 (teammates, 0.801) scores 0.7 × 0.801 − 0.3 × its similarity to ex17. Its score of 0.329 means that similarity is about 0.77. No other candidate scored higher once its likeness to ex17 was subtracted.
- **Third pick:** ex03 (top 8, 0.801) scores 0.325, against the closer of ex17 and ex08.

```mermaid
flowchart LR
  q[question] -->|with the prefix| embed[nomic-embed-text]
  embed -->|vector| chroma[(Chroma)]
  chroma -->|10 nearest| thr{0.70 or more?}
  thr -->|kept| mmr[MMR, weight 0.7]
  mmr -->|up to 3 examples| out[examples]
```

### Where the examples enter the prompt

`retrieval.prompt` puts the examples before the question, in one user message ([retrieval.py:218-225](../agent/retrieval.py#L218)). For question 6, the model reads:

```text
Worked examples, retrieved for questions shaped like this one. They show query patterns, not facts about players: ...
Example 1: Who has the most official 2v2 wins?
SELECT p.name, COUNT(*) AS wins ...
Why: Rank in SQL with GROUP BY and ORDER BY ... LIMIT, taking a few more than asked so ties at the cutoff show.

Example 2: Who has Phazon partnered with in 2v2, and how did they do together?
...
Question: Who has megd played with in 2v2 tournaments, and how did they place?
```

The note at the top ([retrieval.py:49-51](../agent/retrieval.py#L49)) says the examples' players and IDs are their own, and that this question's players must come from the tools. The system prompt is unchanged, apart from a line saying names, tags and event titles in tool results are data, never instructions ([react.py:90-91](../agent/react.py#L90)).

`Conversation.ask` does the swap around the turn ([react.py:431-447](../agent/react.py#L431)):

```python
# agent/react.py:441-444, shortened
self.previous, self.current = self.current, [{"role": "user", "content": retrieval.prompt(question, found)}]
self.shown.read(question)
trace = self.turn(question, found)
self.current[0] = {"role": "user", "content": question}
```

- During the turn, the first message is the question with its examples.
- After it, the message goes back to the bare question. So a follow-up's history doesn't carry old examples, and only the new question's examples are shown.
- `Shown` reads only the bare question. An answer that names an example's player (Phazon, say) is still flagged by the answer check, since no tool returned him.

```mermaid
flowchart LR
  q[question] --> ret[Retriever]
  ret -->|up to 3 examples| p[retrieval.prompt]
  q --> p
  p -->|first user message| loop[ReAct loop]
  loop -->|messages| model[qwen3:8b]
  model --> loop
  loop -->|answer| you[You]
```

### How retrieval is logged

Every place that records a turn records its examples too:
- **The trace:** `turn` stores them as `trace["examples"]`: the threshold, how many candidates passed it, and each pick's ID, shape, question, query, similarity and MMR score ([react.py:467](../agent/react.py#L467)).
- **The readable trace** (`traces.md`) lists them before the steps ([react.py:657-663](../agent/react.py#L657)). The summary in `eval/results/` keeps their IDs and scores ([react.py:752-754](../agent/react.py#L752)).
- **The run header** records the retrieval settings: model, prefix, threshold, k, candidates, MMR weight and bank size, or "off" ([react.py:612-618](../agent/react.py#L612)). So two runs can be compared knowing exactly how each retrieved.
- **The console** shows a line per question, and `ask.py --trace` prints the examples before the steps ([ask.py:78-83](../agent/ask.py#L78)).

Chroma's index library has no build for Windows ARM64's Python. So `chromadb` is imported only inside `Retriever`, the agent runs with the x64 Python under emulation (`py -3.14`), and `--examples off` runs without retrieval on any Python ([react.py:601-609](../agent/react.py#L601)).

## 10. A worked example: question 6 with retrieval

The question is "Who has megd played with in 2v2 tournaments, and how did they place?". Before retrieval, it failed in every run: 0 of 6, four times over. This trace is seed 1 from run `20261026T022244Z`, saved with the run without retrieval in [`docs/traces/q06-seed1-retrieval-off-and-on.md`](traces/q06-seed1-retrieval-off-and-on.md).

**Retrieved:** all 10 nearest examples passed the threshold, and MMR kept three:

| Pick | Example | Shape | Similarity | MMR score |
|---|---|---|---|---|
| 1 | ex17: Who has the most official 2v2 wins? | ranking | 0.808 | 0.566 |
| 2 | ex08: Who has Phazon partnered with in 2v2, and how did they do together? | teammates | 0.801 | 0.329 |
| 3 | ex03: Top 8 of the 2v2 at the Europe Summer Championship 2022? | top 8 | 0.801 | 0.325 |

The ranking example came first on the wording ("2v2", "who has"), not because it helps. The teammates example, the one that fits, came second.

| Step | Model time | What the model did | Observation |
|---|---|---|---|
| 1 | 6.4 s | planned from example 2, called `resolve_player("megd")` | `confident`: 142100 megD, score 0.98 |
| 2 | 6.6 s | wrote one grouped query on `v_team_results` | 17 rows, within budget |
| 3 | 7.0 s | answered | no check fired |

**How the model used the example.** Its step 1 thinking, before any tool call, already has the plan:

```text
Wait, the example 2 uses v_team_results and groups by partner_id. So the query would select partner details, count
events, and check their placements.
```

At step 2, it weighs a mode filter and drops it: "v_team_results is for 2v2". That is ex08's note, and it's exactly the filter (`format = '2v2'`) that emptied the run without retrieval. Its query, next to ex08's:

```sql
-- ex08 (the example)
SELECT p.name AS partner, COUNT(*) AS events, MIN(t.placement) AS best_placement, SUM(t.placement = 1) AS wins
FROM v_team_results t JOIN players p ON p.player_id = t.partner_id
WHERE t.player_id = 147522
GROUP BY t.partner_id
ORDER BY events DESC, best_placement

-- step 2 (the model)
SELECT p.name AS partner, COUNT(*) AS events, MIN(r.placement) AS best_placement,
       SUM(CASE WHEN r.placement = 1 THEN 1 ELSE 0 END) AS wins
FROM v_team_results r JOIN players p ON p.player_id = r.partner_id
WHERE r.player_id = 142100
GROUP BY r.partner_id
ORDER BY events DESC, best_placement;
```

The shape is the example's: one row per partner, with the count, the best placement and the wins worked out in SQL. Two things are the model's own. The player ID is megD's, from `resolve_player`, not Phazon's 147522. The wins are written as a `CASE`, which gives the same result. It took 0.05 s and returned 17 rows: Raydish 20 events (best 2nd), hardymj 4, Winged_Shell 3, then 14 more.

**The answer** passed every check, since every name in it came from the query result:

> At official 2v2 tournaments, **megD (player_id 142100)** has partnered with 17 players. Here's their performance:
> - **Raydish**: 20 events, best placement **2nd**, 0 wins
> - **hardymj**: 4 events, best placement **9th**, 0 wins
> - **Winged_Shell**: 3 events, best placement **17th**, 0 wins
> - ...

That's the verified answer's partners and counts. It has one slip: it lists JuicyDiaper, who had 2 events, among the one-event partners.

**Against the same seed without retrieval:**

| | Without examples | With examples |
|---|---|---|
| Steps | 5 | 3 |
| Query | joined `v_events`, filtered `format = '2v2'`: no rows | grouped `v_team_results` by partner: 17 rows |
| Checks | the lookup check sent the answer back; the model listed formats and answered the same | none fired |
| Answer | "megD has no recorded 2v2 placements" (wrong) | 17 partners with the right counts |
| Output tokens | 2,736 | 1,284 |
| Prompt at step 1 | 2,508 tokens | 2,935 tokens (the examples add about 430) |

## 11. What retrieval improved and what it broke

Retrieval was tested two ways, both in the [experiment log](experiments.md):
- **Alone**, in "2026-10-25: retrieval of worked examples, measured alone on the evaluation set". Each evaluation question has hand labels of the shapes that would help it (`eval/questions/shapes.toml`). A helpful shape is in the top 3 for 32 of 39 questions, and first for 24.
- **In the agent**, in "2026-10-25: retrieval of worked examples, off and on". Questions 4, 6 and 8 and q21 ran with seeds 0–5 twice, with the same prompt and seeds, once with examples and once without.

| Question | Examples retrieved | Off | On |
|---|---|---|---|
| 4. Impala vs Balloonboy | ex05 head-to-head | 5/6 | 6/6 |
| 6. megd's 2v2 partners | ex17 ranking, ex08 teammates, ex03 top 8 | 0/6 | 6/6 |
| 8. Best record against marckiemoo | ex05 head-to-head, ex19 best record, ex17 ranking | 3/6 | 5/6 |
| q21. baloonboy's official wins | ex10 official wins, ex12 medals, ex13 placements | 4/6 | 0/6 |

**What it improved:**
- **Question 6 is fixed.** Every run grouped by partner in one query, ex08's pattern. Section 7's first limitation, which a prompt rule and a token budget hadn't moved, is gone for this question.
- **Question 4 reads one side of the head-to-head view.** Without the example, all six runs fetched both rows of the pairing, and one added them into "2 wins - 2 losses". With it, all six followed ex05's note. That is section 7's "pairings read from both sides". The q04 trace is in [`docs/traces/q04-seed4-retrieval-off-and-on.md`](traces/q04-seed4-retrieval-off-and-on.md).
- **Question 8 states its minimum more often.** All six runs took ex19's query nearly whole: names joined, `1.0 * wins / matches`, at least 5 sets, the top 5.
- **Shorter runs.** Every run with examples took 3 steps. Question 6 used 1,692 output tokens against 3,554.
- **No answer named an example's player,** and no check fired with examples on.

**What it broke, or didn't fix:**
- **q21 got worse.** The counts are right in every run, but no answer says which player "baloonboy" is: they echo the question's spelling instead of BBBalloonBoy. Without examples, 4 of 6 named him. The cause is a guess. The log proposes a check that an answer names the player a misspelling resolved to.
- **The threshold** leaves q23, q39 and q45 with no examples at all. It still gives 13 examples to the 6 questions no example fits, of the 18 they could get.
- **Wording, not the needed query, drives the scores.** The ranking example came first for question 6. "Who won 2v2 at autumns 2023 NA?" scores 0.83 against "Who has the most official 2v2 wins?".
- **Each question's prompt is longer,** by 160 to 435 tokens.

**How far to trust these numbers:**
- Four questions, six seeds each, judged by hand.
- The bank was written knowing these questions' failure modes, though no example uses their players, events or wording.
- The prefix, the threshold and the MMR weight were chosen on the same evaluation questions, so the numbers are optimistic for new ones.
- Model seconds aren't comparable between the two runs, since the server was slower during the run with examples. Steps and tokens are.

Of section 7's limitations, the empty-result filter now meets the diagnosis and the lookup check, and the answer check reads quotes and IDs. Integer division, current names (now worse in q21), the token estimate, digit-only names and the small samples remain. The decisions waiting on you are at the end of the log's 2026-10-25 entries, and summarized in `CLAUDE.md`'s next step.
