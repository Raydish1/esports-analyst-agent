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

## M2: tools that can't express the natural reading

Status: not built yet.

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
