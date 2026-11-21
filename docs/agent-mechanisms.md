# Failure mechanisms: the design note

A running note on the fourth round of fixes. It starts on 2026-11-20 and is updated with each commit, so it can be
read afterwards in one place. The direction comes from the user (2026-11-20): no fix per question. Each fix closes the
mechanism behind a failure, so every question that fails the same way is covered.

The findings are in `docs/web-app-testing-notes.md` on `claude/web-app`, rounds one to four (findings 0 to 29). The
measured misses are in `docs/experiments.md`. The audit of question kinds against the tools is in
[`question-audit.md`](question-audit.md).

## The four mechanisms

| | Mechanism | The principle |
|---|---|---|
| M1 | Reading the question | A vague word gets the model's own reasonable reading, and the answer says which reading it took. The question's scope words (a mode, a year or time window, a region) reach the calls, checked in code. |
| M2 | Tools that can't express the natural reading | Every common question kind has a tool that answers it in one or two calls, with the arguments its natural reading needs. |
| M3 | Facts the model makes itself | Anything counted, ranked or compared comes from a tool, templates included. A record is written from one named player's side. An answer never sends the user to the database. |
| M4 | The conversation | What the page showed is the page's, kept apart from the answers. A question about it is a question about the agent's own answer. A name is read as people write it, possessives included. |

## The failures, grouped

Each finding of the testing notes is listed under the mechanism behind it, and so are the misses that the measured
runs left open. A finding with two mechanisms is listed under both, in brackets the second time.

| Mechanism | Fixed in earlier rounds | Open on 2026-11-20 |
|---|---|---|
| M3 facts | 0 (records invented with no tool), 1 (an answer that looked nothing up), 6 (players named by ID), 11 and 19 (the number check's own failures), 15 | 22 (card figures read against the wrong mode or player, the user told to run a query), 24 (a record under the wrong player's name), 27 (placement counts read off rows, a real placement called an anomaly), q39 seed 0 (Boomie's 1v1 medals read as his total), h04 (long set lists miscounted), q20 (a set time invented) |
| M2 tools | 7 and 12 (team counts in hand-written SQL), 16 (stats in three calls) | 28 (no tool ranks pairs), 29 (no time window, no Power Rankings), megD's most-played opponent (no tool ranks a player's opponents), h15 (`rank_players` can't leave winners out), 26 (the best placement isn't listed with where) |
| M1 reading | 5 ("cb"), 17 (`event="all"`) | 26 ("best placement" asked as `top=1`), 29 (the mode dropped, "right now" read as all time), 22 (a card question asked as one mode with `top=1`), q44 (a placements question asked with `head_to_head`) |
| M4 conversation | 0b, 3, 8, 9, 10, 13, 14, 18 (suggestions, follow-ups, the card, questions about the answer) | 21 (the card tag copied into answers), 23 ("come" looked up as an event), 25 ("renivics" not read as Renivic's) |

The open failures by count are M3 6, M2 5, M1 4 and M4 3, so the work goes in that order. M1's scope check also needs
M2's arguments (a window, a region), so M2 has to come before M1 in any case.

## M3: facts the model makes itself

The number check (2026-11-17) checks where a number came from. It doesn't check what the number is about. 12 is in
the card line, so "Phazon's 12 gold medals in 1v1" passed, though the 12 is his 2v2 figure. 5 is in many rows, so
"25th (5 times)" passed, though the model counted 4 itself. So M3 has three parts:

- **Claims the tools never make.** An answer that sends the user to the database ("you can query v_player_medals"),
  or calls a result an anomaly, an error or a conflict when no tool result says so, goes back once. If the reply still
  does it, those sentences are left out, the way unconfirmed numbers are.
- **A number about one player or one mode comes from a row about them.** The number check's evidence keeps each row's
  player names and mode. A number in a sentence that names one player, or one mode, is supported only by a row that
  doesn't name only other players, or only another mode. It covers the card line's clauses and every template's rows,
  so it isn't a fix for one card.
- **The templates count what answers need.** `player_results` with no `top` lists the results at the player's best
  placement, ties included (26), and how many times each placement happened (27), so no answer counts rows.
  `head_to_head` states a record from both players' sides (24). The prompt's rule, never count rows by reading them,
  now names template results too.

Built so far:

- **The claim check** (`agent/claim_check.py`). It reads two kinds of claim. A referral sends the user to the
  database: a query to run, a view or table to check, fenced SQL, or "further analysis would be needed". A judgment
  calls a result wrong: an anomaly, an error, a glitch, an inconsistency, a discrepancy or a conflict. Either kind
  sends the answer back once. If the reply still makes the claim, it's left out of whatever text is final. A
  referral states nothing, so it goes with no line saying so. A judgment goes with the left-out line, as an
  unconfirmed number does.
  - Judgments aren't checked when a tool result in view marks the data as wrong (a status such as
    `placements_unreliable`, `cancelled` or held out, or unscored sets), or when the question asks about errors
    itself, or when the question is about the previous answer. A denied judgment ("isn't an error") doesn't count.
  - The prompt says to run every query the answer needs, and to call a result wrong only where a tool result says so.
  - Replayed on 784 recorded answers (the template runs, the grounding and web-fixes runs, the three conversation
    runs, and the live web sessions): 7 flagged. All 7 are claims the check is for. They include finding 22's SQL
    for the user, finding 26's "further analysis ... would be needed" and finding 27's "likely a data anomaly". One
    of the 7 is an offer ("I can query the database for entries"), which a send-back turns into a lookup.
- **Agreement in the number check** (`number_check.Window.unsupported`). Each row of the evidence keeps its texts.
  A count, an ordinal or a record in a sentence that names one player in view, or one mode, is supported only by a
  row that doesn't name only other players, or only the other mode. A row naming neither fits anything. Such a claim
  goes back once with whom and which mode it's about ("'12' about Phazon in 1v1"), then it's left out.
  - Years aren't checked this way, and neither are sentences about both modes together: "12 in all" can mean all of
    the question's one mode, so checking it could drop a right fact.
  - Replayed on 759 recorded answers: 5 flagged. Four are wrong figures. In q39 seed 0, gdsandstorm's "34 in 1v1" was
    Boomie's figure, which is the open miss. c4 seed 1 said "out of 16 players", a 16 that came from a date of a 2v2
    event. c6 seed 2 gave "11 top 8s" in 2v2, held only by 1v1 rows. c1 seed 0 said "10 games to 8", a 10 from a
    date. The fifth is a sentence about tied positions in q14 seed 2 that names STING RAY. The first replay
    flagged two more, years in event names, which is why years are left out.
  - Its limit: a note that names several players and both modes fits nearly any claim, so a figure from a note can
    still pass for the wrong player.
- **The templates count what answers need.** `player_results` with no `top` now adds two tables. One counts how many
  times each placement happened in each mode, for finding 27. The other lists the results at the best placement in
  each mode, newest first with ties included, for finding 26. It shows at most 10 per mode, with a note when there are
  more, since a champion's 1st places are their wins. On eval-v1, Renivic's 2v2 now reads 17th twice (Winter NA 2026,
  Autumn NA 2025), 25th 4 times and 33rd 6 times, which is the truth the finding gives. gdsandstorm's whole record
  stays at 2,256 tokens.
  - `head_to_head` states each record from both sides ("A won 0 and lost 1 of their 1 set against C; C won 1 and lost
    0", and the same for the 2v2 meetings), for finding 24.
  - The prompt says a best placement comes from `player_results` with no `top`, that a record is written from one
    named player's side, and that the rule never to count rows by reading them covers a template's rows too.

## M2: tools that can't express the natural reading

The audit ([`question-audit.md`](question-audit.md)) lists the kinds no template could answer in one or two calls.
The general gaps are a time window, a region, ranked pairs and the Power Rankings.

- **A time window.** `since` and `until` work on every template that takes a year (`player_results`,
  `team_results`, `rank_players`), and on `head_to_head`, which now takes a year, a window and an event too. Each is
  a day, a month or a year ("2025-10-01", "2025-10", "2025"), and each end is included. The filters live in one
  structure (`templates.Narrowing`), so every template reads them, and says them in its scope, the same way. A
  head-to-head in a window counts the sets in it, since `v_head_to_head_1v1` has no dates. On eval-v1,
  `rank_players(by="wins", mode="1v1", since="2025-10-01")` gives Marckiem00 and Zivai on 3, then six players on 2,
  in 1.0 s.
- **A region.** `region` works on the same four templates. It takes a code (na, eu, sa, brz, sea, aus, mena, jpn) or a
  name for one ("north america", "oce"). Its events are those whose names name it, through the curated terms that
  `resolve_event` reads: "na" covers NA, North America and 2017's US. A region alone used to be an event name that
  matched 131 events, too many to filter. A note tells the answer that global events such as Worlds are in no
  region. On eval-v1 the counts are NA 141 events, EU 144, SA 80, SEA 83, AUS 55, MENA 18, BRZ 11 and JPN 1. Qualifiers
  are included. Region means where an event was held, not where a player is from. For players by region, the Power
  Rankings are the source.
- **Ranked pairs** (`rank_pairs`, for finding 28 and audit kinds 10 and 11). It ranks each pair once, every tie
  included. With `of="opponents"`, the default, it ranks the pairs with the most 1v1 sets between them, with each
  one's wins. With `player_id`, it gives that player's most-played opponents, in 1v1 or, with mode 2v2, in 2v2
  meetings. With `of="teammates"`, it ranks partners by events, wins, medals or top 8s together. It takes the year, the
  window, the region and the event.
  - On eval-v1: SiB | Wess and lFiend, and yüz and whoiskyna, share the most 1v1 sets (34), in 12 s. megD's most-played
    opponent is luna, 18 sets (megD 6-12), in 0.3 s; the 2026-11-19 log had no tool for that. The best duo by wins
    is acno? and Blaze (21), in 3.8 s.
  - Decided: 2v2 meetings are ranked for one player only. Over every player they take 92 s, and 84 s within one
    year, because `v_match_results` counts each side's players row by row, which is over `run_sql`'s 30 s. The call
    is refused with the reason. A fast 2v2 sets view in the next build would lift this.
  - The prompt and `ingest/views.sql` now say the head-to-head views are for one player or one pair at a time. ex32
    shows the call (`rank_pairs()`) in place of its SQL.
- **The Power Rankings** (`power_rankings`, audit kind 8, and half of "right now"). It gives a region's top N in a
  mode, or each region's top N without a region. With `player_id`, it gives each ranking the player is in. A note says
  this is the only snapshot (2026-10-02), and that its medal and top-8 counts are the Stats API's own. Its regions are
  NA, EU, SA (Brazil's too), SEA and MENA, and any other region is refused. On eval-v1, `power_rankings(top=1)` gives
  the 1v1 #1s that finding 29 lists: BBBalloonBoy (NA), Zivai (EU), lopesbrawlhalla (SA), marker_bh1 (MENA) and
  keiththepoopoo (SEA).

The audit's other gaps are listed for the user rather than built: streaks, upsets, and rankings with a condition
(kinds 15, 16 and 7). Streaks and upsets need a definition first.

## M1: reading the question

- **The general rule for open words**, a prompt section "Reading the question". A word the question leaves open
  (best, strongest, top, greatest, most successful, right now, recently) gets the reading the data supports best,
  passed in the calls. The answer says which reading it took ("by official 1v1 wins since 2025-10-01", "by the official
  Power Rankings of 2026-10-02"). A defined word keeps its definition. Words about the present never mean all time:
  they read as the Power Rankings or a recent window, and the answer says which. No current-form word has a
  definition of its own, since that is the user's to decide.
- **The scope check** (`agent/scope.py`), before each template call runs. It reads the scope words from what the
  user wrote, or, for a reply to suggestions, from the question that reply answers. It reads one mode, a year
  standing alone, a window (since, after, before, until, between), a region and the present. A call that could take a
  word but leaves it out is refused with what to pass. An event argument that names it counts ("winters 2023 na
  1v1").
  - Cautious choices. A year next to a word of official event names ("bcx 2022") is the event's, so "did the winner
    of bcx 2022 win worlds" doesn't push 2022 into the worlds lookup. A question naming both modes has no mode. A
    template that can't take a word isn't checked for it: `head_to_head` takes no mode, and `power_rankings` is the
    present itself. Events aren't checked, since they reach the calls already.
  - A refused call made again unchanged runs. The words may not apply to one step of a question about several
    things, and the error says so. `run_sql` isn't checked, since a query may be one step that needs no mode.
  - Replayed on the 545 recorded template calls: 1 would have been refused, finding 29's
    `rank_players(by="wins", top=5)` for "the strongest 1v1 player right now". No false refusals.
- **Finding 26** ("best placement" asked as `top=1`) is covered from two sides. The prompt and the description say a
  best placement is `player_results` with no `top`, and the template lists where it was (M3).
- **Worked examples for the present.** Finding 29's retrieved examples were about pairs, an event's winner and a
  record against one player, and none was about current form. Two new examples cover it. ex33 asks who is ranked
  first in each region "right now" and shows `power_rankings(mode="2v2", top=1)`. ex34 asks for the most 2v2 medals
  since the start of 2025 and shows `rank_players(..., since=...)`. Neither names a player. `retrieval.py check`:
  34 examples, 0 problems. Retrieval quality (`retrieval.py measure`) needs the embedding server, so it waits for
  the runs.

## M4: the conversation

- **The page's note in a message of its own** (finding 21). `Conversation.shown(summary)` adds a user-role message
  after the answer: "[The page showed the user beside the answer above: ...]". It used to append the tag to the
  answer's own message, so the history showed answers ending in such a tag, and the model copied it. The history
  keeps the note with its turn after the turn moves to the older ones. A final answer has any copy of the tag taken
  out, which the trace marks (`page_tag_removed`). The prompt says such a message is the page's, to answer from and
  never to write. The web app's call is unchanged.
- **A question about the page is one about the answer** (finding 23). After the page showed something, a message
  about it ("on the card", "the graphic shows") is settled as a question about the previous answer, as "are you sure"
  is. Its note says to answer from the page's message and check its figures with `player_results` with no `top`,
  which gives each mode, and both together, at once. That's the run-2 failure of finding 22, which asked one mode with
  `top=1`.
  - "where does ... come from" and "where did you get" join the cues for questions about an answer, with or without a
    page.
  - A forced lookup for such a question looks up its named players only, never its other words as an event. "come",
    "means", "shown" and "showed" are function words now.
  - Replayed on every recorded message: the cues catch the three earlier live disputes and finding 23's question,
    and nothing else.
- **Possessives** (finding 25). A name with no exact match is tried once without a possessive ending ("renivic's",
  "renivics'", "renivics"). If an alias is the base exactly, the base's result stands, with a note and `read_as`.
  Otherwise nothing changes, so "renivics" is Renivic, confident. The curated event terms ("winters", "springs", "cb")
  now count as event words, as the words of event names do. Read as possessives, "winters" had named the player Winter
  and "springs" named NurptheDerp.
  - Replayed on the 98 recorded and test questions, two names are now read as possessives: "renivics" (finding 25)
    and "mojakins", which is c9 turn 1's. The 45 questions still give the same 31 names.
  - **This conflicted with a verified answer.** c9 turn 1 ("what are mojakins stats") expected suggestions with
    Mojakin first, and now got Mojakin's stats. Settled on 2026-11-21 by the user: keep the retry, and spell c9 turn 1
    "mojakn", which matches Mojakin only loosely (0.78, first) and isn't a possessive.

## Round five (2026-11-21): findings 30-35 and upsets

The user's fifth round of live tests ran after the mechanism round was merged, at e4f7e1a on `claude/web-app`. Every
figure was right, and the failures are in how the answers read. The user also defined upsets and settled c9 (above).
Grouped by mechanism, with the open failures counted:

| Mechanism | Findings | Open |
|---|---|---|
| M3 facts and claims | 30 (a true sentence cut for "two" in "the top two tied"), 33 (placeholders: "[Opponent Name]", and a condition said to be removed though no query ran without it), 34 (records written backwards, which the number check passes since it takes "2-1" from a row of 1 and 2 in either order), 35 ("dominates" for a 2-1 record) | 4 |
| M5 answer writing, new | 31 (player IDs beside every name, unasked), 32 (the reply listed its tool calls), 35 (an order "as requested" that nobody requested) | 3 |
| M4 the conversation | 32 (a question about the card answered as a dispute: "The previous answer was correct"), 34 (a reply to a check written as a correction of a draft the user never saw) | 2 |
| M2 the tools | 34 (no tool ranks a player's opponents by record, so "best record" fell back to most sets), upsets (defined by the user, no tool) | 2 |
| M1 reading the question | 34 ("best record" read as most sets played) | 1 |

M5 is new. These answers say things beyond what the user asked: IDs, tool calls, and an order "as requested". It's
not about facts, so it gets its own row.

Built in round five:

- **Count words that count a result's rows** (finding 30). A count word from two to ten is supported when that many
  rows of one result share a number its sentence states ("the top two tied at 34 sets"). After "top", it's supported
  when a result has that many rows or more ("the top three"). Such a count is about no one player or mode, so the
  agreement check skips it. When everything left out only restates numbers the answer keeps, no left-out line is
  added. Replayed on finding 30's live turn, its draft now passes with nothing flagged.
- **A record is checked from its owner's side** (finding 34). The number check took "2-1" from any row holding a 1
  and a 2, in either order. Now the evidence reads each row's sides as (player, against whom, wins, losses). That
  covers a table's wins and losses, `player_wins` and `opponent_wins`, a set's winner and loser games, and the notes'
  "X won 1 and lost 2 ... against Y" and the card's "X 1-5 against Y". A record claim's owner is the nearest player
  named before it who isn't an object ("Raydish beat volst 2-1" is Raydish's), or the first of names joined by "and".
  A player a list writes the record right after ("**Raydish** (3 sets, 2-1 record)") is the opponent of the answer's
  subject, the one player the turn's results are about, unless the line calls them a winner. A record that matches
  that pair's sides only the other way round goes back once, saying whose it is and how the results give it, then
  it's left out. A loss ("lost 1-2 to"), whose order people write either way, isn't read.
  - Replayed on 883 recorded drafts and answers: it flags only finding 34's two reversed records (volst against
    Raydish and against antireplay, 2-1 where the results give 1-2), in both drafts. The first version of the owner
    rule flagged five right records, from "A and B have a 2-1 record", "against A (2-2) and B (2-1)", "Winner: Raydish
    (2-0)", "Impala dominates ... (2-1 record)" and the list lines. Each one shaped the rule above.
- **Placeholders, removed conditions and characterizations** (findings 33 and 35), three more kinds of claim:
  - A placeholder ("[Opponent Name]", "[X]", "X wins", "X-Y") goes back once, then is left out with the line.
  - A claim to have removed a condition, after a last query that found no rows, goes back once with "run it without
    that condition", then is dropped silently, since it states nothing.
  - A characterization ("dominates", "crushed", "one-sided", "far superior") is checked against the record behind
    it: the owner's record against the other player, from the results' sides, leaving out one set's game scores.
    It goes back only when that record is close, meaning fewer than twice the losses in wins or fewer than 2 wins
    ahead. A sentence about part of a series isn't checked ("the early matches", a year, "their last three
    meetings"), and neither is a question that uses such a word itself.
  - Replayed on 751 recorded answers: 14 claims. That's 7 placeholders (finding 33's five slots, and q30 seed 1's
    "[Player Name]" and "[Team Name]", which nobody had seen), finding 33's "Removing that condition", and 6
    characterizations. Five are "Impala dominates" on a 2-1 record across runs, and one is finding 35's "Raydish
    dominates" a 2-1 series. Checking every "dominates" would have flagged 15. The record yardstick left out "Phazon
    dominates" at 5-1 and "bestjava dominated, winning 7 of 10". The part-of-a-series rule left out "dominated the
    early matches" and "dominated in 2025".
- **M5, answer writing** (findings 31, 32 and 35):
  - A player_id in parentheses right after that player's name ("**SiB | Wess (37977)**") is taken out of the final
    answer, which the trace keeps as `ids_removed`. It stays when the question asks for IDs, or when two players in
    the answer share the name, since the ID tells them apart. A number after a name that isn't that player's ID (a
    year) isn't touched.
  - Tool talk, a tool or a call the answer names ("checked with `player_results(player_id=147522)`"), goes back once.
    After that, a sentence that states nothing else goes whole, and any other loses only those words.
  - "As requested" about an order, when the question asked for none, goes back once, then its sentence goes.
  - The prompt says to show IDs only when asked or needed, never to name the tools, to keep the tool's order unless
    asked, and to describe a record by its numbers.
  - Replayed on 747 recorded answers: 167 had IDs beside names (279 IDs). Tool talk appears 40 times, all of the
    kind (`resolve_player(name="Ahmet")`, "using the `resolve_player` tool"). "As requested" appears once, in finding
    35.
- **M4, the conversation** (findings 32 and 34):
  - A question about what the page showed has its own kind (`settling.PAGED`) and note: explain the figure it asks
    about, from the page's message and the tools, and don't say whether the answer was right. It's settled before
    the dispute cues, so "where does the card's 12 come from?" isn't a dispute. Like a dispute, its forced lookups
    are its players only. Unlike one, it needs no re-check, and its judgments are checked.
  - Every check's message ends with `DRAFT`: the user hasn't seen the draft, so the reply answers their question and
    never corrects a draft. After a turn whose answer a check sent back, unless the question is about the previous
    answer, the final answer loses a "Corrected Answer:" heading and its talk about its own draft. That's the clause
    up to a colon or semicolon, or the whole sentence when nothing else in it states a fact. A sentence with facts and
    no such clause is kept.
  - Replayed on 89 recorded answers given after a send-back: only finding 34's has draft talk ("**Corrected
    Answer:**", and "The previous answer incorrectly stated a 2-1 record against experiencedoa;"), and both go.
- **A player's best records** (finding 34, M2 and M1). With `player_id`, `rank_pairs(by="record")` ranks that
  player's opponents by the player's wins against them, then the fewest losses. An optional `min_sets` applies only
  when the question sets a minimum, and a note asks the answer to say how it read "best record", and the minimum.
  Without a player it's refused, since a record is one player's. "Choosing a tool" maps a player's best records to
  it. "Who has the best record against a player" keeps the decided counting rule (win rate, at least 5 matches,
  `run_sql`), which q08's verified answer rests on. On eval-v1, volst's best records are woolala 3-0, then nine
  opponents at 2-0, in 0.37 s, which is finding 33's truth.
- **Upsets** (the user's definition, 2026-11-21). `upsets` lists the sets the lower seed won, meaning the higher
  `initial_seed` at that event from its standings, the biggest seed difference first, ties whole, with both seeds and
  the score. A set without both seeds isn't judged, and the note says how many sets were and weren't. With
  `player_id` it gives that player's upset wins. It works in 1v1 over every event or narrowed to a year, window,
  region or event, and in 2v2 for an event or a player, since the 2v2 sets view takes more than a minute over every
  event.
  - Seeds and sets are read separately and joined in memory. The same join in SQL ran past 300 s. The full seed table
    (about 8 s) is kept on the tools object after the first read.
  - On eval-v1: BCX 2023's biggest 1v1 upset is irqqzz (seed 665) over Nomm999 (89), 576 apart. BBBalloonBoy's
    biggest upset win came as seed 1,712 over seed 337, at LTC Midseason Online 2020. Over every event it's Commanda
    Doggo (7,233) over Phoza (192), at the NA SteelSeries Championship's 7,240 entrants, which takes 22.5 s under the
    agent's x64 Python, within the 30 s limit.
  - The scope check reads its default mode as 1v1. ex35 shows the call for the Brawlhalla Japan Invitational. The
    audit's kind 16 now has a template, a32 checks for `upsets`, and a50 and a51 ask a player's best record and
    biggest upsets.
- **The conversation set.** c18 (findings 30 and 31) and c19 (33 to 35) come from the fifth round's sessions, and
  c14 turn 2 now also checks that the card question isn't answered as a dispute (32). None is verified yet. Scored
  on the live transcripts they come from, each turn fails exactly the checks written for its finding: IDs and the
  left-out line (c18); placeholders and woolala's 3-0 (c19 turn 1); `by="record"`, "Corrected Answer" and the
  record (turn 2); "dominates" and "as requested" (turn 3).

## Round six (2026-11-21): the fixes the runs pointed to

The user approved the seven fixes the 2026-11-21 runs point to, the `rank_pairs` regression first, and accepted a
right answer taken from the previous turn's results for c8. Built offline, and the reruns wait for the user.

- **The opponents' side of a player's records** (q08 3 of 3 lost, q40 2 of 3, audit a28 2 of 3). Round five's
  `rank_pairs(by="record")` ranks a player's own records, and the model used it for "who has the best record
  against marckiemoo" and "who has raydish lost to the most", which ask for the other players' records against them.
  - `rank_pairs` now takes `side="opponents"` with a `player_id`. Each row is another player's record against them,
    from that player's side. `by="rate"` ranks by win rate, with at least 5 sets unless `min_sets` says otherwise,
    which is the decided counting rule q08's verified answer rests on.
  - The prompt maps those questions to it. Its line telling the model to use `run_sql` for them hadn't held, so the
    scope check also refuses a `rank_pairs` call with a player and no `side="opponents"`, once, when the question
    asks for that side. That's "record against X", "lost to" or "who beat X", but not "against anyone".
  - On eval-v1 both match their verified answers. Against Marckiem00 by rate it's V3M_T4NQUIL0 3-2 (60%), Raydish 6-7
    (46%) and gdsandstorm 4-7 (36%). Whom Raydish lost to most is gdsandstorm 10, luna 8, then Marckiem00 7.
  - Replayed on the 44 distinct recorded `rank_pairs` calls: the rule refuses the 6 of q08, q40 and a28, and nothing
    else. An empty ranking now says which minimum emptied it.
- **A best placement asked with no `top`** (audit a03 3 of 3, c15 turn 1 2 of 3). The prompt and the description
  already said a best placement is `player_results` with no `top`, and the model still asked `top=1`. So the scope
  check refuses once a `player_results` call with a `top` when the question asks for a best or highest placement,
  finish or result. It skips counts such as "top 8 finishes", which need their `top`. Replayed on the 85 distinct
  recorded `player_results` calls, it refuses exactly the two (a03's and c15's `top=1`).
- **A ranking with a condition** (audit kind 7, 6 of 6). `rank_players` takes `never_won`. It leaves out the players
  who ever won an official event ("any"), or the events a name means ("worlds"), in the ranking's mode when it has
  one, and the scope says so. Any other condition stays with `run_sql`. On eval-v1 the most top 8s without a win are
  sphynx. 36, Goddess 33 and hermisen 32. The most 1v1 wins among players who never won a 1v1 Worlds go to Zivai,
  with 23, then acno? and whoiskyna with 13. Each takes 0.3 s.
- **A player's sets at an event** (audit a39, 3 of 3). "who did zivai lose to at bcx 2023" had no tool, so the model
  called `head_to_head` without an opponent. The new `player_sets` gives one player's sets from their side, each with
  its event, date, opponent, result and score, oldest first, and a summary of wins and losses. It takes
  `result="won"` or `"lost"`, 1v1 or 2v2, and the year, window, region and event filters. A long list is left out
  with its count. On eval-v1, Zivai at BCX 2023 in 1v1 played 10 sets, won 8 and lost 2, both 1-3, to yüz and
  whoiskyna. The live answer had named Kuroyuri. In 2v2 he won all 8 with Pink | Zen.
- **Dominance and flawless wins** (audit a35, 3 of 3). "who won an event without dropping a game" was looked up as an
  event's name. The new `dominant_wins` ranks official wins by the decided rule: the fewest games lost, then the
  fewest sets dropped, then the most games won. A run with an unscored set comes after every fully scored one, a note
  names any that would have ranked near the top, and crew battles are left out. `flawless=true` keeps every win
  without a dropped game. It takes a player, a mode, and the year, window, region and event filters.
  - On eval-v1, Raydish's most dominant win is Trial of Laufey NA (Moose Wars), 25 games to 2, which is q11's verified
    answer. The 1v1 wins without a dropped game number 19, among them gdsandstorm's Mammoth Cup 2020 at 29-0.
  - ex23 shows the call.

## Decisions

All dated 2026-11-20. The user said to make the design calls and take the simpler or more cautious option when unsure.

| Decision | Why |
|---|---|
| A referral goes silently, and a judgment goes with the left-out line. | A referral states no fact. A judgment is a claim no tool made, like an unconfirmed number. |
| Judgments aren't checked with a data-status marker in view, a question about errors, or a dispute. | In each of those, talking about errors is legitimate. |
| The agreement check covers one-player and one-mode sentences only, not "both modes" and not years. | "12 in all" can mean all of the question's one mode, and years in event names flagged falsely in the first replay. |
| The placement counts and the best results come only with no `top`. | Those are whole-record questions. Under a `top`, the counts it fixes stay out, as decided on 2026-11-17. |
| The best results show at most 10 per mode. | A champion's 1st places are their wins, and the list is newest first with a count note. |
| The filters live in one `Narrowing` structure. | Every template then applies and states a year, a window, a region and an event the same way. |
| A region means where an event was held, read from event names. | The data has no region per event. Players by region come from the Power Rankings. |
| 2v2 meetings are ranked for one player only. | Over every player the view takes 84 to 92 s, over `run_sql`'s 30 s. A fast view in the next build would lift this. |
| `power_rankings` maps Brazil to SA and refuses AUS and JPN. | The 2026 Power Rankings have five regions, and Brazil plays in SA from 2020. |
| The scope check is a refusal once, and the same call made again runs. | A scope word may not apply to one step of a question about several things. Nothing on the record was refused falsely. |
| A year next to an event word is the event's, and events and `run_sql` aren't scope-checked. | Pushing 2022 into a worlds lookup would make a right call wrong. Events reach the calls already. |
| No definition for current-form words, only the general rule. | The user said that definition is theirs. |
| Page questions are settled as disputes, which require a re-check with a tool. | The user's direction: a question about what the page showed is one about the agent's own answer. |
| The possessive retry is built and c9 is left as verified. | The user asked for the retry. c9's change is theirs to make, so it's listed below. |
| Streaks, upsets and rankings with a condition aren't built. | Streaks and upsets need a definition, and conditions have `run_sql`. They're listed in the audit. |
| A characterization such as "dominates" is supported when the record behind it has at least twice as many wins as losses and is at least 2 wins ahead (2026-11-21). | Proposed as the reading of finding 35's "stronger than the record supports", and accepted by the user on 2026-11-21. |

## Waiting on the user

- The definition of "strongest right now" and the other current-form words. Until then the general rule applies: the
  model picks a reading and says which one it took. c17 and the audit's a09 and a10 measure it.
- Verifying c14 to c19 (`eval/questions/conversations-review.md`).

- A definition for streaks (events in a row? in one mode?), if that kind should get a template. Upsets were defined
  on 2026-11-21 (round five).

## Runs

All five were made on 2026-11-21, at the user's go-ahead after their live test. The results and the fixes they
point to are in `docs/experiments.md` (2026-11-21, the mechanism rounds measured). They were:

1. The before run of c8-c13 at 3d42613, as agreed on 2026-11-20 (`py -3.14 eval/conversations.py run --seeds 0 1 2
   --ids c8 c9 c10 c11 c12 c13`, from a checkout of 3d42613).
2. The conversations at the latest commit, all 19, seeds 0-2. This measures findings 7-35's fixes on c8-c19, and
   checks c1-c7 for regressions.
3. The 45 questions at the latest commit, seeds 0-2 (`py -3.14 eval/harness.py run --ids q01 ... q45 --seeds 0 1 2`,
   never `--all`). This checks for regressions against `20261119-webfixes`.
4. The audit set, seeds 0-2 (`py -3.14 eval/audit.py run --seeds 0 1 2`), then `python eval/audit.py report RUN`.
   This gives the failures by mechanism on questions nothing was tuned on.
5. `py -3.14 agent/retrieval.py measure`, for the two new examples' effect on retrieval.
