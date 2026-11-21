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

Status: not built yet.

## M4: the conversation

Status: not built yet.

## Decisions

Each decision is listed with its date and its reason. The user said to make the design calls and take the simpler or
more cautious option when unsure (2026-11-20).

## Waiting on the user

- The definition of "strongest right now" and the other current-form words. Until then the general rule applies: the
  model picks a reading and says which one it took.

## Runs wanted

None has been made. They wait for the end of the user's live test, and are asked for once, together.
