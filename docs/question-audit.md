# The question audit

The kinds of questions a Brawlhalla fan asks, and for each one, the tool that answers it in one or two calls, or the
fact that none does (2026-11-20). The gaps found here are mechanism M2 of [`agent-mechanisms.md`](agent-mechanisms.md).
The audit's question set, `eval/questions/audit.toml`, asks each kind in at least two phrasings. It checks failure
mechanisms. It isn't for scoring, and its questions have no verified answers.

"Today" means the agent at 2c80a6c, before this round. "This round" is what this work adds.

| # | Kind | For example | Today | This round |
|---|---|---|---|---|
| 1 | A player's stats or record | "Boomie stats", "how many 1v1 wins does Boomie have" | `player_results`: with no `top` for the whole record, or with a `top` and a mode | |
| 2 | A player's best placement, and where | "what's renivic's best 2v2 placement" | `player_results` with no `top` gives `best`, but not where it was | The results at the best placement, ties included |
| 3 | How often a player placed each way | "how many times has X got 2nd" | Only by reading the list's rows, which isn't allowed (finding 27) | A placement count per mode |
| 4 | Firsts and lasts | "X's first win", "when did X last place top 8", "the last event X entered" | `player_results` (first and latest); `run_sql` on `v_entries` for side formats | |
| 5 | Current form | "who's the best 1v1 player right now", "how has X done this year" | Only a whole calendar year. No time window, and no Power Rankings | `since` and `until` on every template that takes a year, and the Power Rankings |
| 6 | Rankings, by mode, time and region | "most 1v1 wins in 2024", "most medals in NA" | `rank_players` by mode, year or event. A region as an event ("na") is too many events to filter | `region` and the time window on the templates |
| 7 | Rankings with a condition | "the most top 8s without a win" | None: `rank_players` takes no condition (h15) | Open: `run_sql` |
| 8 | The official Power Rankings | "who's #1 in NA", "what's X's PR" | None: `pr_snapshots` isn't in the prompt | `power_rankings` |
| 9 | Two players against each other | "X vs Y", "X vs Y since 2024" | `head_to_head`, all time only | The time window on `head_to_head` |
| 10 | Rivalries and most-played pairs | "who has the biggest head-to-head", "who has X played the most" | None: `run_sql` from ex32, and `v_head_to_head_1v1` unfiltered times out (finding 28) | `rank_pairs`, for one player too |
| 11 | The best teams | "the best 2v2 team ever", "the most wins as a duo" | None: `team_results` takes one player | `rank_pairs` of teammates |
| 12 | A player's partners, or a team's record | "who has X played 2v2 with", "X and Y as a team" | `team_results` | |
| 13 | Comparisons of two players | "who has more wins, X or Y" | `player_results` twice | |
| 14 | A record against everyone, or the best record against one player | "X's best record against anyone" | `run_sql` on `v_head_to_head_1v1`, filtered by a player | |
| 15 | Streaks | "X's longest win streak", "most top 8s in a row" | None | Open: no template |
| 16 | Upsets and best wins | "the biggest upset at worlds", "X's best win" | `run_sql` on `v_sets_1v1` (each player's placement at the event). No seeds or ranks at the time | Open |
| 17 | Dominance | "the most dominant worlds win" | `run_sql` on `v_win_runs` | |
| 18 | An event's results | "who won bcx 2022", "top 8 of winters 2023 na", "when was it", "the bracket" | `event_results` | |
| 19 | An event's sets and final | "the grand final score", "who did X lose to at bcx" | `run_sql` on `v_sets_1v1` | |
| 20 | A series | "every worlds winner" | `event_results` with the series | |
| 21 | Earnings | "X's career earnings", "the top earners" | `run_sql` on `v_career_earnings` | |
| 22 | What the data doesn't hold | legends, community events, prize money per tournament, seeds, round names, ranked play | The prompt says the data doesn't cover them | |

## The question set

`eval/questions/audit.toml` holds 49 questions in the conversation set's format. There are two or more phrasings for
each of the 22 kinds, and four probes of the conversation: a possessive, a question about a card, a follow-up that
changes the year, and "are you sure?". Each question is tagged with its kind and the mechanisms it probes. Its checks
look at how the turn went:

- the tool and the scope its call carried (`calls`, and `calls_with`, as in "power_rankings, or rank_players with
  mode 1v1 and a window");
- claims no tool makes (`not_says`: "you can query", "further analysis", "anomal");
- words never looked up (`not_looked_up`);
- the defaults on every turn: grounded and named.

`py -3.14 eval/audit.py run --seeds 0 1 2` plays it, and `python eval/audit.py report RUN` gives the failed checks by
mechanism and by kind, the most failing first, then each failing turn. It hasn't been run: runs wait for the end of the
user's live test.

## The gaps left open

Kinds 7, 15 and 16 stay open. Kind 7 has `run_sql` and a template rule (h15). Streaks (15) and upsets (16) are open
because their readings are the user's to define. A streak could count events in a row, or one mode's events. An upset
could be judged by placement at the event, or by Power Ranking, and the data has only one snapshot of the rankings.
They are listed for the user.
