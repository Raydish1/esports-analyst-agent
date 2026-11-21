# Experiment log

One entry per experiment, newest first: what it asked, how it was set up, what it found, and what it decided. Results are in `eval/results/`. The models' full replies, thinking included, are in `data/experiments/` (git-ignored).

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
