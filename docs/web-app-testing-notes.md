# Testing the agent on the web app: findings (2026-11-19)

The user's own questions in live mode (qwen3:8b, `claude/agent` merged at a74fa73). Transcripts are in
`data/experiments/web/`. Findings in `agent/` are for the agent session; page findings are fixed on `claude/web-app`.

## For the agent session

### 0. Three turns in a row answered with invented records (the most serious; fix 1 below covers it)

- **Seen:** megD's biggest records (`20261119T233544Z-002`, turns 15–17). No turn called a tool. Turn 15 wrote a
  `v_head_to_head_1v1` query *into its answer* as text, never ran it, and stated results; the no-tool check sent it back,
  the model replied that the facts came from earlier results, and the check kept it. Turns 16 and 17 did the same.
- **What was invented, against eval-v1:**
  - megD against Zivai: "7 sets, 5 won". Really 5 sets, 2–3 (games 8–12).
  - megD against Raydish: "3 sets, 2 won", with Raydish as player 147569 (that's capsar; Raydish is 160000). Really 4
    sets, 2–2 (games 8–9): Raydish 3–1 at NA Summer Championship 2022, megD 3–1 at NA Autumn Championship 2023, megD 3–2
    at Trial of Baldr NA (Moose Wars) 2024, Raydish 3–1 at Winter Championship NA 2025.
  - The number check caught "15–12" and "15–10" in turn 17; the rest passed. Small numbers like 7 and 5 are in some earlier
    tool result of the conversation, and the check asks only whether a number appears in one, not in the row it's
    about (as its docstring says: it checks where a number came from, not what it means). Not yet checked number by
    number.
- **Also:** "biggest records" wasn't read as head-to-head records until the user said so (turn 14).
- **What it shows:** the no-tool check's "reply the same if the facts come from earlier tool results" lets a model
  that never looked anything up keep its answer by claiming it did. Fix 1 has to cover this: a fact answer in a turn
  with no tool call is checked against the earlier turns' actual tool results, not the model's say-so, and an answer's
  own earlier numbers never count as evidence.

### 1. An answer that looks nothing up survives the no-tool check (decided: fix it in code)

- **Seen:** "when was ceo 2025" (`20261119T233544Z-002`, turn 3). The model decided from its own knowledge that CEO isn't
  a Brawlhalla event and answered without a tool call, though its thinking said to call `resolve_event`. The no-tool
  check sent it back once; the reply again called no tool, and stood. The next question, "who got 2nd at ceo 2025",
  called `resolve_event("ceo 2025")`, which matched both CEO 2025 events by their names' words ("every word", 0.9). No
  alias was involved either time.
- **Also:** the check named "Autumn" as a player (a word from the previous turn's answer), and the thinking drifted to
  that turn's Autumn 2022 question.
- **Decided (2026-11-19, the user): fix 1.** When the reply to the no-tool check still calls no tool, the loop doesn't
  keep it: it runs the lookups itself on the question's names (`resolve_event`, `resolve_player`) and gives the model the
  results, or, failing that, replaces the answer with "I couldn't look this up", as the number check replaces claims.
  The model's own knowledge never settles that a player or event doesn't exist.

### 2. A list of sets names each set by its date, not its event

- **Seen:** Raydish's record against Kyna (`20261119T233544Z-002`). The answer's "Key Matches" read "2022-11-04:
  whoiskyna won 3–2", and so on. `head_to_head`'s set table had each set's event ("Brawlhalla World Championship Expo
  2022 / 1v1"), but the answer used only the date.
- **Wanted (the user):** each set named by its tournament, written short (BCX 2022, Winter Royale 2023), rather than by
  date. The prompt's answer guidance, and the worked example showing a `head_to_head` call, say so.

### 3. A follow-up without names is asked back instead of answered from the previous turn

- **Seen:** "whats raydish's record with kyna", then "tell me about the 2v2 record" (`20261119T233544Z-002`, turns 6–7).
  The history was there: the thinking named the previous question, and the previous `head_to_head` result held the
  answer ("In 2v2, Raydish's teams and whoiskyna's teams met in 5 sets: Raydish's side won 2 and lost 3"). The model
  asked which player, team or event was meant.
- **Why:** nothing says a follow-up without names means the previous question's players. Retrieval embedded the bare
  follow-up, and its examples (the most 2v2 wins, an event's 2v2 top 8) suggested other readings.
- **Proposed:** rewrite a follow-up into a standalone question from the history ("Raydish's 2v2 record against
  whoiskyna") before retrieval and before the model sees it, the trace keeping both; and a prompt line that a follow-up
  without names continues the previous question's players and events.

### 4. The no-tool check fires on a clarifying question, and the reply to it reaches the user

- **Seen:** the same turn 7. The clarifying question quoted examples with numbers ("top 8", "2022"), so the no-tool
  check sent it back. The second reply addressed the check, and that became the answer: "The answer includes numbers
  like **8** (top 8) and **2022** (year) from earlier examples, but no specific tools were called…". The rule keeping
  the first answer when a reply talks about the answer (2026-11-09) didn't apply, since the reply's list numbers (1, 2, 3)
  counted as new numbers.
- **Proposed:** a reply that asks the user a question and states no result isn't checked; list numbering isn't a
  number; and a reply that talks about the check never goes to the user.

### 5. "cb 2022" isn't found, and the model doesn't try "crew battle" itself

- **Seen:** "do you know about the cb tournament in 2022" (`20261119T233544Z-002`, turn 8): `resolve_event("cb 2022")`
  came back not found, and the model said so. After "i meant the crew battle tournament in 2022",
  `resolve_event("crew battle tournament 2022")` found the three 2022 Crew Battle Invitationals (EU, NA, SA).
- **Why:** `event_terms.csv` has "ltc" and the region abbreviations, but not "cb". And a not-found result's note says
  only to say so.
- **The user's direction (2026-11-19):** don't rely on hand-made aliases; the agent should work out what the user means.
- **Proposed:** a not-found note that tells the model to retry once with abbreviations and slang spelled out as the
  data names events (cb → crew battle, bcx → Brawlhalla World Championship Expo), and a prompt line saying the same. A
  term in `event_terms.csv` stays possible for common ones, but the retry is what generalizes.

### 6. Players named by their IDs ("Player 147569")

- **Seen:** "tell me about the north america one" (turn 10). The model queried `v_results` with `run_sql`, selecting
  `player_id` and `placement` but no names, instead of calling `event_results`, which gives names, a crew or team on one
  row, and ties whole. The answer listed "**Player 147569** (team placement: 1st)" and two more.
- **Why no check caught it:** the IDs came from a tool, so the answer check allows them; the names correction only
  swaps a wrong name next to an ID, not an ID standing alone.
- **Proposed:** the names correction also replaces a player named only by ID with their display name (in code, traced
  as a swap); and the prompt's "Choosing a tool" says an event's winners or placings always come from `event_results`,
  crew battles included.
