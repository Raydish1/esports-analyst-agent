# Testing the agent on the web app: findings (2026-11-19)

The user's own questions in live mode (qwen3:8b, `claude/agent` merged at a74fa73). Transcripts are in
`data/experiments/web/`. Findings in `agent/` are for the agent session; page findings are fixed on `claude/web-app`.

## For the page (claude/web-app)

- **A graphic asked for and not made:** when the question asks for a graphic or card and the turn produced none, say
  so under the answer ("No graphic: the agent didn't look this matchup up"), rather than nothing. Not built yet.

## For the agent session

## Second round: live test with the six fixes (2026-11-20, `claude/agent` at f04eea3)

From `data/experiments/web/20261120T050251Z-001`: "top 5 2v2 players in brawlhalla history", then Cody Travis and Phazon.
Turns 1–2 ("raydishes", then "the first one") worked: the suggestion was settled to megD vs Raydish, and answered.

### 7. "24 tournaments won together": an AND/OR precedence mistake (wrong answer; the truth is 4)

- **Seen:** turn 5, "how many tournaments in 2v2 did cody travis and phazon win". The model's `run_sql`:
  `WHERE (t.player_id = 117179 AND t.partner_id = 147522) OR (t.player_id = 147522 AND t.partner_id = 117179) AND
  t.placement = 1`. AND binds tighter than OR, so the placement applies to the second pair only: it counted the 24
  events they entered as partners, not the 4 they won. No check can see it: the 24 is a tool's number.
- **Proposed:**
  - a template for a duo, `team_results(player_id, partner_id)`: the events two players entered together, their
    placements, and their wins, medals and top 8s together. "How did X and Y do as a team" is a common question, and a
    template can't get this wrong;
  - a code check on `run_sql`: a WHERE that mixes OR and AND at one level without parentheses is refused, with an error
    explaining the precedence. It's a classic mistake, and cheap to catch.

### 8. "what about X and Y?" after a ranking became a 1v1 head-to-head

- **Seen:** turn 3 ranked the top 5 2v2 players by wins; turn 4, "what about cody travis and phazon?", resolved both and
  called `head_to_head`: their 1v1 sets against each other (right numbers, wrong question). The user meant where they
  stand in 2v2. The message names players, so fix 2's cues didn't settle it (`settled` is empty).
- **Proposed:** the cues also settle "what about"/"and" with names: the previous question with the new names in it
  ("top 5 2v2 players …: what about Cody Travis and Phazon" → their 2v2 wins, and rank if asked).

### 9. The model doesn't know what the cards showed

- **Seen:** turn 6, "are you sure? you just said phazon has 12 medals and cody travis has 6 medals in 2v2 in the
  graphic". The card was right: 12 and 6 are their 2v2 wins (gold), from the app's own `player_results` calls. The
  model never sees the cards, so it couldn't tell what the user pointed at; it looked up only Phazon, and invented an
  explanation for Cody Travis's 6 ("likely came from a prior query not shown").
- **Proposed:** the history keeps a one-line summary of what each card showed beside the answer (the web app supplies
  it; it needs a hook in `Conversation` to add it to the turn's history, or an argument to `ask`). And "are you sure"
  about a number re-runs the lookup behind it, for every player it named.

### 10. A question about the agent's own answer was looked up as an event

- **Seen:** turn 7, "so why did you say cody travis and phazon have won 24 2v2 tournaments". The no-tool check sent the
  first reply back, then the loop's forced lookup ran `resolve_event("say cody travis 24")`; the event check then sent
  it back for not retrying, and the answer explained that no event is called "say cody travis 24".
- **Proposed:** a message about the agent's earlier answer (why did you say, are you sure, that's wrong) is answered
  by re-checking that answer's claim with the right tool, not by looking up the message's words; `mentions` leaves out
  "say", "said" and the like; and the forced lookups never call `resolve_event` on words that include a known player.

### 11. The replacement sentence reads as noise

- **Seen:** turns 6 and 7 begin or carry "I couldn't confirm the number from the data." as a sentence of its own, cut
  loose from the claim it replaced. Already open from the number check's measurement (the replacement's wording).

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
- **Turn 18, "show head to head megd vs raydish in a graphic":** again no tool call, the same invented 2–1 with capsar's
  ID, and so no card: the app builds cards only from the turn's own template calls, never from the answer's text. With
  fix 1, the turn would have to call `head_to_head`, and the card follows.
- **What it shows:** the no-tool check's "reply the same if the facts come from earlier tool results" lets a model
  that never looked anything up keep its answer by claiming it did. Fix 1 has to cover this: a fact answer in a turn
  with no tool call is checked against the earlier turns' actual tool results, not the model's say-so, and an answer's
  own earlier numbers never count as evidence.

### 0b. Picking a suggestion answered a worked example's question instead

- **Seen:** a new conversation (`20261119T233544Z-003`). "whats megd and raydishes record in 1v1" gave suggestions for
  "raydishes" (Raydish, Radses, radish), rightly. The user clicked Raydish, which sends "the first one". Retrieval
  embedded those three words alone and returned one example, ex15 "What was Addymestic's first official title?" (0.703,
  on "first"). The model's thinking began "let's tackle the user's question: What was Addymestic's first official
  title?"; it called `player_results` with the example's placeholder ID 222222 (refused by the player check), then
  resolved the real Addymestic and answered about him. The page drew his lifetime card.
- **Why:** a reply to suggestions is handled as a new question: the model has to rebuild the original question from the
  history, and retrieval runs on the bare reply. And the bank's example questions name real players, so one can pass for
  the user's question.
- **Proposed:**
  - in code, a reply to suggestions (an ordinal, a number, or a candidate's name) is turned back into the original
    question with the chosen player settled ("whats megd and Raydish's record in 1v1", Raydish given as player_id
    160000), traced; retrieval and the model see that question, never the bare reply. This is finding 3's rewrite, made
    deterministic for this case;
  - retrieval never runs on a reply too short to carry a question;
  - the examples block makes the user's question unmistakable (it comes last, marked as the question to answer), and
    the bank's questions could use placeholder names instead of real players.

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
