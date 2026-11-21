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

## Third round: more live tests (2026-11-20, same code)

From `data/experiments/web/20261120T050251Z-001` (turns 8–9), `-003`, `-004` and `-005`. Checked on eval-v1 and right:
megD vs Raydish (2–2 in 4 sets, each set named by its event), the top 5 by 2v2 wins, by 1v1 wins and by medals,
whoiskyna vs yüz in 1v1 (17–17 in 34), and the stats of Mojakin, Bagus and Renivic (in `-003`).

### 12. A wrong partner count from a query that multiplied rows, kept when the user objected

- **Seen:** `-003` turn 4 is q06 word for word ("Who has megd played with in 2v2 tournaments, and how did they place?").
  The first query failed (`no such column: t.mode`); the second joined `v_entries` to add the mode and counted the
  joined rows: "Raydish (8,218 events)", "Winged_Shell (7,684 events)". The truth: Raydish 20 events (best 2nd),
  hardymj 4, Winged_Shell 3. Turn 5, "there are not that many events", called no tool and repeated the numbers; the
  no-tool check passed it, since the numbers were in the previous turn's results.
- **Proposed:** finding 7's `team_results` template, with the partner optional, answers "who has X played with" (each
  partner, events together, best placement, wins); a `run_sql` count larger than the player's own number of results is
  flagged back; and a message disputing the answer re-checks it (finding 10).

### 13. A follow-up used the previous turn's player instead of the one it named

- **Seen:** `-004` turn 7, "whats kyna vs yuz head to head in only 1v1", right after the "two" turn (finding 14).
  It called no `resolve_player` and passed `head_to_head` plewchi's ID (168011, from the "two" lookup) for kyna, and
  answered "plewchi vs yuz: 0 sets". The truth (turn 5 of the same conversation): 17–17 in 34. The player check let
  it through, since a tool had returned 168011.
- **Proposed:** every player the question names is resolved in code before the model answers, and a template call
  whose players aren't the ones the question names (where it names two) goes back, naming who was meant.

### 14. A forced lookup took a number word for a player

- **Seen:** `-004` turn 6, "which two players have the biggest head to head record". The model first answered with no
  tool; the forced lookup ran `resolve_player("two")`, which matched plewchi (formerly two) and two others, and the
  answer explained the "two" players. The question is answerable: the most 1v1 sets between two players is 34, by SiB
  | Wess vs lFiend (15–19) and yüz vs whoiskyna (17–17).
- **Proposed:** forced lookups skip ordinary words (numbers, quantity words), unless quoted or capitalized as a name;
  a worked example for "the biggest head-to-head" (the pair with the most sets, from `v_head_to_head_1v1`, each pair
  once).

### 15. "the first one" for Mojakin: an answer invented, then gutted by replacements

- **Seen:** `-001` turn 9, after suggestions for "mojakins" (settled correctly to Mojakin, 77046). The first reply had
  no tool call; then three `player_results` calls, all with `mode="2v2"`; the answers claimed 8 1v1 wins, a 2023
  Winter Royale 2v2 win and a partner "Savage". The number check replaced claims until the final text was half "I
  couldn't confirm …" lines. The truth: no wins, medals or top 8s (9 1v1 results, 17 2v2). 8 steps, 95 s.
- **Proposed:** an answer with two or more claims replaced isn't sent as it is: the turn gets one more step with the
  checks' findings, or the answer becomes a short statement of what was confirmed. And finding 16's one-call stats.

### 16. "stats" takes three calls and still gives partial answers

- **Seen:** every "X stats" turn calls `player_results` three times (top 1, 3, 8) and `run_sql` for the last event:
  - `-004` turn 1: volst's 1 top 8 is right (5th, Autumn Championship NA 2026), but "No 2v2 results" is wrong: he
    has 25 2v2 results, none in a top 8;
  - `-005` turn 3, "Dragon!": only `top=3`, so the answer said he "may have reached top 8"; he has 9 (6 in 1v1, 3 in
    2v2).
- **Proposed:** `player_results` with no `top` gives the whole record (results, wins, medals, top 8s by mode, the
  latest event), and the prompt says a player's stats or record is that one call, which is also the lifetime card's.

### 17. `event="all"` was taken as an event, and volst's top 8 vanished

- **Seen:** `-003` turn 6, "volst stats": `player_results(event="all", mode="", top=8)`. "all" resolved as one event,
  confident ("every word"), and the count was 0, though the note said none of his results was there. The answer: no
  top 8s, against `-004` turn 1's right 1.
- **Proposed:** the templates read "all", "any", "everything" and an empty value as no filter; `resolve_event` never
  matches a lone common word.

### 18. "dragon" was ambiguous between exact names, but gave no suggestions

- **Seen:** `-005` turn 2, "dragon stats". `resolve_player("dragon")`: ambiguous, with Dragon!, Parz (formerly Dragon)
  and Dragon all at 0.98. Since the score was above 0.9, the turn didn't end in suggestions; the model wrote SQL for
  the user to run and guessed at a character called Dragon.
- **Proposed:** an ambiguous result between exact matches, with no clear cut (`CLEAR_CUT`), ends the turn in
  suggestions, as a low score does.

### 19. The number check replaced a right 2v2 record

- **Seen:** `-004` turn 5: `head_to_head`'s note said "whoiskyna's side won 11 and lost 11"; the answer's "11-11
  split" was replaced by "I couldn't confirm the record from the data."
- **Proposed:** a record of two numbers is supported by a note's "won X and lost Y" as by a row.

### 20. The trace repeats one name swap dozens of times

- **Seen:** `-004` turn 5's `name_swaps` lists "Yuz" → "yüz" once per mention and per step, dozens of times. Only the
  trace's noise, but the harness counts swaps per run from it.

### 11. The replacement sentence reads as noise

- **Seen:** turns 6 and 7 begin or carry "I couldn't confirm the number from the data." as a sentence of its own, cut
  loose from the claim it replaced. Already open from the number check's measurement (the replacement's wording).

## Fourth round: the card line, after findings 7–20's fixes (2026-11-20, `claude/agent` at 2c80a6c)

The page now calls `Conversation.shown()` after each answer with cards. The line (`figures.summary`) names each card's
labels with what they count: "MEDALS are GOLD (1st places), SILVER (2nd) and BRONZE (3rd)", then each player's figures
by mode, one clause each, then a sets list's sets. Two smoke runs of "cody travis vs phazon head to head", then "on the
card, where does phazon's 12 gold come from? is that medals?" (`20261120T175430Z-001` and the next conversation).
Truth: Phazon's 12 GOLD is 2v2 (12 1st places in 2v2, 0 in 1v1, so 12 in both modes together).

### 21. The answer copies the history's card tag into its own text

- **Seen:** the second run's answer ends "[The page showed beside this answer: Phazon's 12 golds are 1st-place finishes
  (medals) in 1v1 and 2v2, but …]", a tag it wrote itself.
- **Why:** `shown()` appends the tag to the last *assistant* message, so the history shows answers ending in such a
  tag, and the model imitates its own earlier answers.
- **Proposed:** put the line in its own message, not in the answer's (for example a user-role note before the next
  question: "The page showed the user, beside your last answer: …"); and leave any such tag out of a final answer.

### 22. The card's figures were read against the wrong mode or the wrong player

- **Seen:** run 1, "Phazon's 12 gold medals in 1v1" (his 1v1 GOLD is 0), with BCX Regional Qualifier 2017 and
  DreamHack Atlanta 2019 as examples of his wins: both are events of the sets list, and he lost the 2019 set. Run 2:
  `player_results(147522, top=1, mode="1v1")` returned 0, and the answer said "conflict with the stat card's 10 golds"
  (Cody Travis's figure in both modes), "2v2: 2 wins" (no tool returned it), and told the user to query
  `v_player_medals` themselves, a view it never queried (it exists: corrected 2026-11-20).
- **The page's part, fixed:** run 1's line wrote the combined figure as "Phazon in 1v1 and 2v2 … GOLD 12", read as 1v1.
  It now says "in 1v1 only", "in 2v2 only" and "in both modes together", in that order. Run 2 was after the fix.
- **Why no check caught it:** the number check checks where a number came from, not what it's about: 12 and 10 are in
  the line, and 2 is in many results. And nothing stops an answer from sending the user to the database instead of querying it.
- **Proposed:** a question about the card ("on the card", "the graphic", a card label like GOLD) is answered from the
  line, or from `player_results` with no `top`, which gives every mode at once, never one mode with `top=1`. And an
  answer never tells the user to run a query: the agent runs it.

### 23. "come" was looked up as an event

- **Seen:** run 1, the no-tool check's forced lookups called `resolve_event("come")`, and the answer began "The term
  'come' does not match any official Brawlhalla event".
- **Why:** the question names Phazon, but it's about the card, not the agent's own answer, so the rule of commit 3
  (only the named players are looked up) didn't apply.
- **Proposed:** a question about what the page showed counts as one about the agent's own answer: only the named
  players are looked up, never the message's other words.

### 24. An ambiguous 2v2 sentence

- **Seen:** run 1, turn 1: "In 2v2, Phazon's teams outperformed Cody Travis's teams in 20 sets (8 wins, 12 losses)."
  On eval-v1, Cody Travis's side won 8 of the 20: the numbers are his, under Phazon's name.
- **Proposed:** the answer guidance says a record is written from one named player's side ("Cody Travis's teams won 8
  of the 20, lost 12").

### 25. "renivics" went to suggestions

- **Seen:** "what is renivics best placement in 2v2" (`20261120T175642Z-003`, turn 1): `resolve_player("Renivics")`
  matched Renivic only by a similar spelling (0.79), so the turn asked the user which player.
- **Why:** a possessive written without its apostrophe keeps its "s", and no tier drops it.
- **Proposed:** a name with no exact match is tried once more without a trailing "s" (and "'s"); if that matches exactly,
  it's that player, as confident.

### 26. "best placement" was asked with `top=1`, and the answer gave none

- **Seen:** turn 2 ("the first one"): `player_results(49489, mode="2v2", top=1)` returned 0 wins, and the answer was
  "Renivic's best placement in 2v2 is **no 1st places** … To confirm their highest placement, further analysis … would
  be needed." Turn 3 ("analyze all of renivic's 2v2 placements") called it with no `top` and got `best` = 17.
- **Truth (eval-v1):** 17th, twice: Autumn Championship - North America 2025 - 2v2 (2025-09-21) and Winter
  Championship - North America 2026 - 2v2 (2026-03-01).
- **Proposed:** the description and the prompt's "Choosing a tool" say a player's best placement is `player_results`
  with no `top`, read from `best`; and the template lists the results at the best placement, ties included, so the
  answer can say where.

### 27. Placement counts made up from the list, and a real placement called an anomaly

- **Seen:** turn 3's answer: "Most frequent placements: 25th (5 times) and 33rd (5 times)" (really 4 and 6), best 17th
  given once (it was twice), and the 513th at Combo Breaker Online 2020 "likely a data anomaly" (it's real: 2,296
  players placed there).
- **Why no check caught it:** the counts are the model's own, of rows it read, and 5 occurs in the results; the number
  check checks where a number came from.
- **Proposed:** the rule that counts come from SQL, never from reading rows, applies to template results too: a
  question about how often each placement happened is a `run_sql` GROUP BY. And the answer guidance says not to call a
  result an anomaly without a tool result that says so.

### 28. No template ranks pairs of players

- **Seen (asked, 2026-11-20):** "who has the biggest head-to-head record" is answered only by the model writing SQL
  from ex32. `v_head_to_head_1v1` unfiltered takes 73 s, over `run_sql`'s 30 s, while ex32's `v_sets_1v1` grouping
  takes 4.9 s. A model that picks the view by name times out.
- **Proposed:** a template `rank_pairs(by="sets", mode, top)`: the pairs with the most 1v1 sets (or 2v2 meetings
  between their teams), each pair once, ties whole, both players named, with each one's wins. And a line in
  `v_head_to_head_1v1`'s definition (or the prompt) saying it's for one player or pair at a time.

### 29. "the strongest 1v1 player right now" got the most wins ever, in both modes

- **Seen:** `20261120T175642Z-003`, turn 4: `rank_players(by="wins", top=5)`, with no mode and no year, and the answer
  ranked total wins in both modes as "the strongest 1v1 player right now": gdsandstorm 30 1v1 wins, then Boomie "12",
  ahead of TigerBrawlhalla's 26.
- **Two failures:** the question's mode word wasn't passed to the call, and "right now" was read as all time. The
  retrieved examples were about pairs, an event's winner and a record against one player: none about current form.
- **What the data has for "right now" (eval-v1):** the official Power Rankings in `pr_snapshots`, per region and mode
  as of 2026-10-02 (1v1 #1s: BBBalloonBoy NA, Zivai EU, lopesbrawlhalla SA, marker_bh1 MENA, keiththepoopoo SEA), and
  results by date: 1v1 wins since 2025-10-01 are Marckiem00 3, Zivai 3, then four players with 2. `events.is_online`
  marks 40 official events as offline; the latest is Brawlhalla - Autumn Royale 2025 (2025-10-12, Ahmet_ 1st,
  Marckiem00 2nd). The Royales being offline is the API's flag, not checked.
- **Proposed (the definition is the user's to decide):** current-form words ("right now", "currently", "these days",
  "best", "strongest" without "ever") get a definition in the prompt, as "major" has one, with a worked example; a
  template or `rank_players` arguments for it; and a check that a mode the question names is in the call.

## Fifth round (2026-11-21, after merging the mechanism round, at e4f7e1a)

The two smoke-test turns (`20261121T045117Z-001`) and the user's first question (`-002`). Every figure below was
right: the failures are in how the answers read.

### 30. A true sentence left out for its number word: "the top two tied at 34 sets"

- **Seen:** `-002`, turn 1, "whats the biggest head to head record in 1v1": `rank_pairs(of="opponents", mode="1v1")`,
  then a right list (SiB | Wess vs lFiend and yüz vs whoiskyna at 34 sets, gdsandstorm vs Boomie 28, Remmy vs noeL 25,
  ...). The number check sent it back twice for "two" in "the top two tied at 34 sets", then left the sentence out, so
  the answer ended with "(I left out a statement I couldn't confirm from the data.)" under a right answer.
- **The mechanism:** a count of rows the model read ("the top two", "both", "three players") is arithmetic, which the
  number check refuses, but here the rows are the tool's own ranking and the count is of a tie the result shows. The
  user reads the closing line as the answer being doubtful.
- **Proposed:** the number check accepts a count word (two to ten) when that many rows of one result share the value
  the sentence states (a tie), or for "the top N" of a ranked result; and the left-out line is dropped when what was
  left out restates a number the answer keeps elsewhere.

### 31. Player IDs printed beside every name

- **Seen:** the same answer named each player as "**SiB | Wess (37977)**". `Shown.without_ids` lets an ID through as
  an ID, so no check objects, but the user never asked for IDs and they clutter every line. Also the list items were
  separated by blank lines, which the page's renderer read as separate lists all numbered 1 (fixed in the page,
  `markdown.js`, 2026-11-21).
- **Proposed:** the answer guidance says not to show player IDs unless the user asks for them or two players share
  the name (then the ID tells them apart).

### 32. A question about the card answered as a dispute

- **Seen:** `-001`, turn 2, "on the card, where does phazon's 12 gold come from? is that medals?": settled as a
  question about the previous answer, so the reply opened "The previous answer was **correct**", listed its tool calls
  in backticks, and never said what GOLD is. The figures were right (12 golds, all in 2v2).
- **The mechanism:** fix M4's note for a question about the page tells the model to check the answer again, which is
  the dispute note's job; a question about what a card means needs the figure explained, not the answer defended.
- **Proposed:** a question about the page gets its own note (explain the figure asked about, from the card's line and
  the tools), separate from the dispute note, and the answer guidance says not to list tool calls.

### 33. An answer of placeholders: "[Opponent Name]", "[X]" wins

- **Seen:** `20261121T053752Z-002`, turn 1, "whats volst best records vs an opponent": `run_sql` on
  `v_head_to_head_1v1` with `h.matches >= 5`, empty; the diagnosis said that without it the query returns rows. The
  model answered that it had removed the condition, then gave a template: "**Opponent**: [Opponent Name] ...
  **Wins**: [X]", "the exact opponent and stats depend on the full dataset". It never ran the query again.
- **Right (eval-v1):** volst has 1v1 sets against 223 opponents, at most 4 against one (Bunny meow, 0-4). The best
  record is woolala, 3-0, then nine opponents at 2-0 (blazey., Mr. Schmitty, ...).
- **The mechanism (M3):** no check reads a placeholder as a claim, and nothing checks an answer that says it relaxed
  a condition against the queries actually run. The minimum of 5 was the model's own, not the question's.
- **Proposed:** an answer with placeholder slots (square-bracketed words, "X", "[Name]") goes back once, then is
  replaced as an unconfirmed claim; an answer saying a condition was removed, with no later query without it, goes
  back.

### 34. "Best record" read as most sets played, and two records written backwards

- **Seen:** the same session, turn 3, "whats volsts best records vs an opponent without the 5 set minimum":
  `rank_pairs(of="opponents", player_id=162675)`, which ranks by sets played, so only the 10 opponents with 3 or 4
  sets came back. The answer:
  - wrote volst 2-1 against Raydish and against antireplay, where the rows say 1 win and 2 losses (turn 4's
    `head_to_head` then gave volst 1-2 against Raydish, contradicting it);
  - left out woolala, 3-0, the best record in the very rows it had, and called the 2-1s the best;
  - opened "**Corrected Answer:**" and said "the previous answer incorrectly stated a 2-1 record against
    experiencedoa": a draft the number check sent back, which the user never saw.
- **The mechanisms:** M2, no tool ranks a player's opponents by record (win rate, or wins with a minimum), so "best
  record" fell back to "most sets"; M3, the number check takes "2-1" from a row holding 1 and 2 in either order (it
  checks provenance, not which number is whose), so a reversed record passes; M4, the check's message is answered
  as if the user had sent it.
- **Proposed:** `rank_pairs` takes `by="record"` (wins, then fewest losses, with an optional minimum of sets, stated
  in the answer); a record "W-L" about a player must match that player's wins and losses in that order, as the
  row's columns name them; a reply to a check is written as the answer to the user's question, never as a
  correction of a draft (the prompt's line for checks, and a strip of "corrected answer" and "the previous answer"
  when no answer was sent).

### 35. "Raydish dominates" a 2-1 series, and an ordering the user didn't ask for

- **Seen:** turn 4, "what are the three sets that volst vs'd raydish": the right three sets, but listed "most recent
  first ... as requested" (nobody asked) and summed up as "Raydish dominates the head-to-head series" at 2-1.
- **Proposed:** answer guidance: keep the tool's order unless asked, and no judgment words ("dominates") stronger
  than the record supports.

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
