# Stat cards for the web app: proposal (2026-11-17)

Cards shown with an answer, in the figures area the page already keeps (`app/server/figures.py`, `figures` in the
answer event). Nothing here is built. Two changes it needs are in `agent/`, which another session owns, so they're
described for that session, not made here.

The layout ideas come from broadcast screenshots in `docs/graphics-reference/` (git-ignored, never committed). The
cards take only their arrangement: a lifetime panel; two players mirrored around a column of labels, with bars growing
outward; and a list of set scores. They use none of the screenshots' art, logos, torn-paper edges, fonts or colors, and
no character art.

## Rules

1. **Every number on a card comes from a template's structured output**, never from the model's text. figures.py reads
   the tool calls in the trace, not the answer. An answer the checks couldn't confirm can still show a card: the card
   and the answer come from the same tool result, and the notes box says what wasn't confirmed.
2. **A missing value shows "not recorded", never 0.** Missing: a player with no career earnings figure, a set with a
   reported winner but no game score, and games for sets with no recorded score. A count the data does hold, such as 0
   medals, stays 0.
3. **Each card states its scope:** "Official events", the mode ("1v1 and 2v2", or one), "crew battles count as 1v1"
   when the player has any, and the earnings figure's source and as-of date ("Stats API, as of 2026-10-02").
4. **No bracket card.** The data has no rounds, so the cards never place a set in a bracket.

## What the cards need from `agent/`

### Why the model's own call isn't enough

In the two latest runs (`20261117-templates`, `20261117-grounding-before`), all 60 `player_results` calls passed `top`
(1, 3 or 8), and 10 of them also passed `mode`. Under `top=1`, the summary's `third` and `top8` columns count only wins,
so a lifetime card read from it would show wrong medals and placements. The card needs figures that don't depend on how
the model called the template.

### Change 1: top 32 in `player_results`' summary (as asked)

In `agent/templates.py`, `player_results` (line 378 at f05ae4a):
- the summary query gains `SUM(r.placement <= 32)` after `SUM(r.placement <= 8)`. Placements are bucketed (17, 25, 33
  on start.gg; some Challengermode events have 22, 27, 32), so `<= 32` is the top 32 on both;
- the summary table's columns become `player, mode, results, first, second, third, top8, top32, best`;
- the indexes that follow shift by one: `counted[m][:6]` becomes `[:7]` and the empty row gains a 0 (line 400); the
  combined row sums columns 2 to 7 and takes `best` from column 8 (lines 402–403); the crew-battle count moves from
  `figures[6]` to `figures[7]` (line 409);
- tests: `tests/test_templates.py`'s expected summaries gain the column;
- `py -3.14 agent/retrieval.py check` should pass unchanged: it checks that a call's rows hold every cell of its
  query's rows, so an extra column doesn't break it (`retrieval.held`). 11 worked examples call `player_results`;
- the model sees one more column, about 3 tokens per row. That's small, but it changes every `player_results`
  observation, so the questions that call it get a regression run.

### Change 2: a `card` beside `ran`

Each template that feeds a card returns a `card` dict next to `ran`. `react.py` already pops `ran` before the model sees
the observation and keeps it in the trace (`Conversation.turn`, about line 742). It would pop `card` the same way, and
store it on the trace's tool call. The model's observation doesn't change, so this change needs no regression run.
figures.py reads only `card`.

| Template | `card` |
|---|---|
| `player_results` | `player`: `player_id`, `name`, `display`; `lifetime`: the summary's query without `top`, `year` and `event`, one row per mode and the combined row (results, first, second, third, top8, top32, crew battles); `earnings`: `amount_usd`, `source`, `as_of` from `v_career_earnings`, or null; `active`: the first and latest result dates |
| `head_to_head` | both players' `player`, `lifetime` and `earnings`, as above; `record`: wins, losses, sets, games won and lost, unscored sets; `sets`: every 1v1 set (date, event, winner_id, winner and loser games), in full even when the model's list is cut; `doubles`: sets met and won on opposite 2v2 teams |
| `event_results` | for one held 1v1 event only: `event` (name, date, mode, status); `sets`: the 1v1 sets of `v_sets_1v1` where both players placed in the top 8, in the order played |

The card queries go to `ran` too, so the trace shows every query a card came from.

## The cards

The figures below are eval-v1's (computed from `v_results`, `v_career_earnings` and `v_sets_1v1`). The bars are
sketches, not to scale.

### a. Lifetime stats

```
┌─────────────────────────────────────────────┐
│ LIFETIME STATS                              │
│ Raydish                                     │
│ Official results 2020–2026                  │
│                                             │
│ Earnings  $83,825                           │
│           Stats API, as of 2026-10-02       │
│                                             │
│ Medals      1st  6    2nd  7    3rd  9      │
│ Placements  Top 8  43      Top 32  82       │
│                                             │
│ [ Both ] [ 1v1 ] [ 2v2 ]                    │
│ Official events · 1v1 and 2v2 · 2 crew      │
│ battles counted as 1v1                      │
└─────────────────────────────────────────────┘
```

- Earnings is the largest figure. A player without one (Boomie in eval-v1) shows "Earnings: not recorded".
- The mode buttons switch between the lifetime rows the card already has, without asking the server again.
- Medal chips are labeled "1st", "2nd" and "3rd", each tinted gold, silver or bronze, and the label carries the
  meaning, not the color.
- At phone width, the rows stack: earnings, then medals in three equal cells, then placements in two.

### b. Head-to-head

```
        Impala                              BBBalloonBoy
                       2 – 1 sets
                       8 – 4 games
   not recorded         Earnings  ████████████████ $62,915
              3   ███████  1st    █████████████████ 7
              3     █████  2nd    ███████████████████ 11
              1        ██  3rd    █████████████████ 9
             19  ████████  Top 8  ███████████████ 36
             40  ████████  Top 32 ████████████ 58
  Official events · 1v1 and 2v2 · the record counts 1v1 sets, one player a side; DQs, forfeits and ties left out
  Earnings: Stats API, as of 2026-10-02 · In 2v2 they never met on opposite teams
```

- Two lifetime cards' figures mirrored around a center column of labels. Each bar grows outward from the labels, scaled
  to the larger of the two values in its row, so a row compares two players, not the whole card.
- The set record sits above the rows, with games below it. If any set has no score, the games line says "games:
  includes sets with no recorded score", and those sets' games show "not recorded".
- A missing earnings figure draws no bar, and its side reads "not recorded".
- The two players get two colors from the app's palette (its teal and a violet), used only for their bars and names.
- At phone width, the names and record go above, and the mirrored rows stay: label column 72 px, each side's bar up to
  110 px, the number inside the bar's end.
- **Comparison variant:** an answer that called `player_results` for two players and `head_to_head` for neither (such as
  "who has more medals, boomie or sandstorm") shows the same card without the record.

### c. Set results

```
  Sets between Impala and BBBalloonBoy, oldest first
  2024-03-17  Trial of Frigg - North America (Moose Wars) / Brawlhalla 1v1   Impala        3 – 0  BBBalloonBoy
  2024-08-04  Trial of Skuld - North America / Brawlhalla Championship 1v1  Impala        3 – 1  BBBalloonBoy
  2024-11-15  Brawlhalla World Championship Expo 2024 / 1v1                 BBBalloonBoy  3 – 2  Impala
```

- One row per set: date, event (for a head-to-head), winner, the score, loser. The winner's name and score are bold.
- A set with a reported winner and no score shows "score not recorded" in place of the score.
- Ten rows, then "Show all N sets".
- For an event, the title says what the rows are, since there are no rounds: "Sets between players who placed top 8,
  in the order played".
- At phone width, each set is two lines: the date and event, then the score line.

### d. Later: 2v2 team comparison

Two teams, each as a pair of lifetime columns, with their meetings between them. It needs data no template gives yet:
a pair's results together (`v_team_results`), their 2v2 sets against another pair (`v_match_results`), and prize money
per team (half to each player). It waits for a template of its own.

## Which questions show which card

figures.py picks the cards from the turn's template calls, in this order, at most two cards per answer:

| The turn called | Shows | For questions like |
|---|---|---|
| `head_to_head` | b, then c with its sets | "whats bbballoonboy's 1v1 record vs impala", "kingdom \| godly vs impala head to head" |
| `player_results` for two players, no `head_to_head` | b's comparison variant | "who has more medals, boomie or sandstorm?" |
| `player_results` for one player, without `year` or `event` | a | "how many official events has baloonboy won?", "How many medals does Balloonboy have?", "Has Hexo ever placed top 8 in 1v1?" |
| `event_results` for one held 1v1 event | c | "who won worlds 2019 1v1", "top 8 at bcx 2025 1v1?" |
| anything else | none | rankings (`rank_players`), answers from `run_sql`, suggestions, unanswerable questions, cancelled events (CEO Dreamland 2020) and events whose placements are unreliable (SEA League Week 1/4) |

A `player_results` call with `year` or `event` gets no lifetime card: the card would answer a different question than
the one asked. A turn that ends without an answer (an error, the step limit) shows no cards.

## Building it, after the two agent changes

1. figures.py: choose the cards from the trace (the table above), with tests on saved trace shapes: each card, "not
   recorded" for each missing value, a lifetime card skipped for a `year` call, at most two cards.
2. `app/static/cards.js`: render each card, scope line included, with `textContent` only.
3. Check in the browser at desktop and phone widths, light and dark, on replayed answers. Replays from before the
   change have no `card`, so they show no cards; the check needs a run recorded after the agent changes.

## Open decisions

1. The `card` payload beside `ran`, popped by `react.py` (recommended), or cards read straight from the model's
   observation, which would show only when the model happens to call without `top`: none of the 60 recent calls did.
2. Esports Earnings figures: eval-v1 has none (all 4,981 career figures are the Stats API's), but the fallback can add
   them to a later build. `DATA.md` notes the three sources' permission doesn't cover Esports Earnings. Should cards
   show those figures publicly?
3. Card c for an event: the top-8 players' sets (recommended), or none until round data exists.
