# Testing the agent on the web app: findings (2026-11-19)

The user's own questions in live mode (qwen3:8b, `claude/agent` merged at a74fa73). Transcripts are in
`data/experiments/web/`. Findings in `agent/` are for the agent session; page findings are fixed on `claude/web-app`.

## For the agent session

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
