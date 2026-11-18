# Stat cards for the web app: proposal (2026-11-17, revised 2026-11-18)

Cards shown with an answer, in the figures area the page already keeps (`app/server/figures.py`). Nothing here
changes `agent/`.

**Built 2026-11-18** (design B, with the app's own earnings and event-sets queries): `app/server/figures.py`,
`app/static/cards.js`, tests in `tests/test_web_figures.py`. Earnings are on by default everywhere
(`--card-earnings off` or `CARD_EARNINGS=off` turns them off). Each card's scope box starts "What this counts:" and
says all official events, regional championships included, so it isn't mistaken for a broadcast's mode-only counts
(see the comparison at the end).

The layout ideas come from broadcast screenshots in `docs/graphics-reference/` (git-ignored, never committed). The
cards take only their arrangement: a lifetime panel; two players mirrored around a column of labels, with bars growing
outward; and a list of set scores. They use none of the screenshots' art, logos, torn-paper edges, fonts or colors, and
no character art.

## Rules

1. **No number on a card comes from the model's text.** The app takes the player and event IDs from the turn's tool
   results, then builds each card from its own calls to the template functions (below). An answer the checks couldn't
   confirm can still show a card, since the card doesn't read the answer; the notes box says what wasn't confirmed.
2. **A missing value shows "not recorded", never 0.** Missing: a player with no career earnings figure, a set with a
   reported winner but no game score, and games for sets with no recorded score. A count the data does hold, such as 0
   medals, stays 0. So does a Stats API earnings figure of $0, which is a figure (see Earnings).
3. **Each card states its scope:** "Official events", the mode ("1v1 and 2v2", or one), "crew battles count as 1v1"
   when the template's notes say the player has any, and, when earnings are on, the figure's source and as-of date
   ("Stats API, as of 2026-10-02").
4. **No bracket card.** The data has no rounds, so the cards never place a set in a bracket.

## Where the card data comes from

### The model's own call isn't enough

In the two latest runs (`20261117-templates`, `20261117-grounding-before`), all 60 `player_results` calls passed `top`
(1, 3 or 8), and 10 of them also passed `mode`. Under `top=1`, the summary's `third` and `top8` columns count only wins,
so a card read from the model's observation would show wrong medals and placements.

### Two designs

**A. A hidden `card` field** (the first proposal). Each template returns card data beside `ran`; `react.py` pops it
before the model sees the observation and keeps it in the trace.

**B. The app calls the templates itself (recommended).** After the turn ends, figures.py takes the player IDs from the
turn's successful template calls (their result's `player` and `opponent`, which the template already checked and
mapped through merges). It then calls the template functions directly, through
`templates.TEMPLATES[name].call(tools, arguments)`, with no `top`, `year` or `event`. Checked on eval-v1:
`player_results(player_id=160000)` returns Raydish's lifetime summary (1st 6, 2nd 7, 3rd 9, top 8s 43), and
`head_to_head(168635, 149305)` returns Impala's 2–1 record against BBBalloonBoy, 8–4 in games.

B over A:
- the model's arguments can't affect a card, and the agent loop doesn't change;
- the eval runs aren't touched: the model's observations stay exactly the same;
- every existing recording gets cards in replay mode, since a card depends on nothing recorded but the player IDs.
  With A, only runs recorded after the change would have them;
- `agent/` needs no change for cards. Top 32 still needs the summary change (below), which the guardrail session
  makes.

What B misses, and how the proposal handles each:

| Gap | Why | Handling |
|---|---|---|
| Earnings | No template returns them | One query of the app's own on `v_career_earnings` by player_id, in figures.py, tested on eval-v1. Behind a setting (see Earnings). |
| An event's sets | No template lists an event's sets | One query of the app's own: `v_sets_1v1` for the event, with both players among its top 8 in `v_results`. |
| Top 32 | `player_results`' summary has no `top32` column yet | The card reads columns by name: it shows Top 32 once the column exists, and only Top 8 until then. |
| A long set list | A template drops an optional list's rows when it's over the token budget (about 100 sets for `head_to_head`), and B calls the same code | The card shows the record and "N sets: too many to list here". No pair in the evaluation set comes near that. |
| Crew battles' count, 2v2 meetings | `player_results` and `head_to_head` give these only in their notes' text | The card states the rule ("crew battles count as 1v1") without a count, and leaves the 2v2 meetings out: it doesn't parse numbers from notes. |
| Coupling | figures.py depends on the templates' output shape (column names), which `agent/` owns | figures.py finds tables by their columns, not their titles. Its tests run the real templates on eval-v1, so a change in `agent/` that breaks a card fails a test. |
| Time | The extra calls run on the worker thread | They run after the answer event is sent, so the answer isn't delayed; the cards follow as a `figures` event. On eval-v1 each call takes well under a second (the head-to-head views are fast with literal IDs). |

The two queries of the app's own (earnings, an event's sets) are an exception to "from the templates". They read views
whose rules are documented in the views' definitions, and they take nothing from the model's text. The alternative is a
template for each, in `agent/`.

### Top 32 in `player_results`' summary

This waits until the guardrail session's step is finished and scored, and that session makes the change. What it
involves, in `agent/templates.py`'s `player_results` (line 378 at f05ae4a):
- the summary query gains `SUM(r.placement <= 32)` after `SUM(r.placement <= 8)`. Placements are bucketed (17, 25, 33
  on start.gg; some Challengermode events have 22, 27, 32), so `<= 32` is the top 32 on both;
- the summary table's columns become `player, mode, results, first, second, third, top8, top32, best`;
- the indexes that follow shift by one: `counted[m][:6]` becomes `[:7]` and the empty row gains a 0 (line 400); the
  combined row sums columns 2 to 7 and takes `best` from column 8 (lines 402–403); the crew-battle count moves from
  `figures[6]` to `figures[7]` (line 409);
- tests: `tests/test_templates.py`'s expected summaries gain the column;
- `py -3.14 agent/retrieval.py check` should pass unchanged: it checks that a call's rows hold every cell of its
  query's rows, so an extra column doesn't break it (`retrieval.held`). 11 worked examples call `player_results`;
- the model sees one more column, about 3 tokens per row, in every `player_results` observation, so the questions
  that call it get a regression run.

### Earnings

**The source.** Every figure in eval-v1 comes from the Stats API.
- `v_career_earnings` takes the Stats API's figure first and the Esports Earnings snapshot's otherwise, and its
  `source` column says which.
- In eval-v1, `player_earnings` holds only `stats_api` rows: 4,981 figures, all as of 2026-10-02, so `source` is
  "Stats API" for every player. The view's comment says the Esports Earnings fallback comes in Phase 2, and none is
  loaded yet.
- So the cards show Stats API figures only, which the data sources' permission covers (`DATA.md`).

What that means on a card:
- Only ranked players have a figure: 4,981 of the 145,646 players. Everyone else shows "not recorded".
- 4,581 of the 4,981 figures are $0. The view counts a ranked player's $0 as a Stats API figure, so the card shows $0
  with its source, not "not recorded".
- When a later build adds Esports Earnings figures, the card shows their source ("Esports Earnings snapshot") and
  as-of date. Whether those may be shown publicly is open (`DATA.md`).

**The setting.** `--card-earnings on|off` on `app/server/main.py`, on by default everywhere (decided 2026-11-18), and the
`CARD_EARNINGS` environment variable for a deployment (the flag wins).
- Off: the server doesn't run the earnings query, and the cards have no earnings row, bar or source line at all.
  They don't show "not recorded", which would claim the data lacks a figure.
- The page needs no setting of its own: it draws what the `figures` event holds.

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

- Earnings is the largest figure. A player without one (Boomie in eval-v1) shows "Earnings: not recorded". With
  earnings off, the row and its source line are gone.
- Top 32 appears once `player_results`' summary has the column; until then the placements row has Top 8 alone.
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
  Earnings: Stats API, as of 2026-10-02
```

- Two lifetime cards' figures mirrored around a center column of labels. Each bar grows outward from the labels, scaled
  to the larger of the two values in its row, so a row compares two players, not the whole card.
- The set record sits above the rows, with games below it. If any set has no score, the games line says "games:
  includes sets with no recorded score", and those sets' games show "not recorded".
- A missing earnings figure draws no bar, and its side reads "not recorded". With earnings off, the row is gone.
- The footer leaves the 2v2 meetings out: `head_to_head` gives them only in its notes' text.
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
- For an event, the title is "Sets between top 8 players": the 1v1 sets in which both players placed in the event's
  top 8, by date and time as the data has them. The card puts them in no bracket order and names no rounds.
- At phone width, each set is two lines: the date and event, then the score line.

### d. Later: 2v2 team comparison

Two teams, each as a pair of lifetime columns, with their meetings between them. It needs data no template gives yet:
a pair's results together (`v_team_results`), their 2v2 sets against another pair (`v_match_results`), and prize money
per team (half to each player). It waits for a template of its own.

## Which questions show which card

figures.py picks the cards from the turn's successful template calls, in this order, at most two cards per answer,
and then builds each from its own calls:

| The turn called | Shows, from figures.py's own calls | For questions like |
|---|---|---|
| `head_to_head` | b, then c: `head_to_head` and `player_results` (no `top`) for both players | "whats bbballoonboy's 1v1 record vs impala", "kingdom \| godly vs impala head to head" |
| `player_results` for two players, no `head_to_head` | b's comparison variant: `player_results` (no `top`) for both | "who has more medals, boomie or sandstorm?" |
| `player_results` for one player, without `year` or `event` | a: `player_results` (no `top`) | "how many official events has baloonboy won?", "How many medals does Balloonboy have?", "Has Hexo ever placed top 8 in 1v1?" |
| `event_results` for one held 1v1 event | c, "Sets between top 8 players": the app's event-sets query, on the `event_id` in `event_results`' table of events | "who won worlds 2019 1v1", "top 8 at bcx 2025 1v1?" |
| anything else | none | rankings (`rank_players`), answers from `run_sql`, suggestions, unanswerable questions, cancelled events (CEO Dreamland 2020) and events whose placements are unreliable (SEA League Week 1/4) |

A `player_results` call with `year` or `event` gets no lifetime card: the card would answer a different question than
the one asked. A turn that ends without an answer (an error, the step limit) shows no cards.

## Building it

None of it waits for `agent/`: Top 32 joins the cards when the summary gains the column.

1. figures.py: choose the cards from the turn (the table above) and build them from the template calls and the two
   queries, with the earnings setting. Tests run the real templates on eval-v1 and saved trace shapes:
   - each card;
   - "not recorded" for each missing value, and $0 kept as $0;
   - earnings off removing the row, and not running the query;
   - a lifetime card skipped for a `year` call;
   - Top 8 alone without a `top32` column;
   - at most two cards.
2. The worker sends the cards as a `figures` event after the answer. `app/static/cards.js` renders them, scope line
   included, with `textContent` only.
3. Check in the browser at desktop and phone widths, light and dark, on replayed answers. Existing recordings work, so
   no live run is needed.

## Decided (2026-11-18)

- The event set list is labeled "Sets between top 8 players", with no bracket order.
- Earnings on cards are switchable by a server setting, on by default everywhere: they're the Stats API's, which the
  permission covers.
- Design B, with the app's own earnings and event-sets queries while `agent/` is frozen.
- Top 32 in `player_results` waits until the guardrail session's step is finished and scored; that session makes it.
- Nothing here changes `agent/`, and live mode isn't tested until the eval runs are done.

## Open decisions

1. Esports Earnings figures, once a build has any: whether cards show them publicly (`DATA.md`).
2. Once `agent/` is unfrozen: a template for earnings and an event's sets, in place of the app's two queries.

## Compared with the broadcast's figures (2026-11-18)

The reference screenshots show figures for seven players, taken during the Autumn Championships 2026: the Europe 1v1
semi-final (Godly vs Bamya, and Mounir's lifetime card) and the North America 2v2 elimination final (Moni and
AnimeFan1266 vs Raydish and megD). eval-v1 (through 2026-09-27) holds both events' results.

The broadcast's figures match eval-v1 exactly, for all seven players and all five counts, under one definition:
- official results in the broadcast match's mode only: 1v1 for the singles match, 2v2 for the doubles;
- crew battles left out;
- every official event, regional championships included: no tier filter;
- results before the event being broadcast (so that event isn't counted yet).

The cards count all official events, 1v1 and 2v2 combined, with crew battles as 1v1 and the Autumn events included.

| Player (shown in) | | Earnings | Gold | Silver | Bronze | Top 8 | Top 32 |
|---|---|---|---|---|---|---|---|
| Godly / Zivai (EU 1v1) | broadcast | $211,958 | 21 | 5 | 3 | 35 | 41 |
| | cards (1v1 and 2v2, crew as 1v1) | $214,458 | 31 | 12 | 9 | 66 | 74 |
| | broadcast's definition on eval-v1 | — | 21 | 5 | 3 | 35 | 41 |
| Bamya (EU 1v1) | broadcast | $9,450 | 2 | 0 | 1 | 11 | 16 |
| | cards | $10,200 | 3 | 0 | 3 | 19 | 28 |
| | broadcast's definition | — | 2 | 0 | 1 | 11 | 16 |
| Mounir (EU 1v1) | broadcast | $47,975 | 1 | 3 | 6 | 19 | 32 |
| | cards | $48,125 | 4 | 7 | 6 | 38 | 62 |
| | broadcast's definition | — | 1 | 3 | 6 | 19 | 32 |
| Raydish (NA 2v2) | broadcast | $82,775 | 0 | 2 | 4 | 15 | 36 |
| | cards | $83,825 | 6 | 7 | 9 | 43 | 82 |
| | broadcast's definition | — | 0 | 2 | 4 | 15 | 36 |
| megD (NA 2v2) | broadcast | $63,250 | 0 | 1 | 1 | 14 | 43 |
| | cards | $65,000 | 2 | 4 | 8 | 37 | 97 |
| | broadcast's definition | — | 0 | 1 | 1 | 14 | 43 |
| Moni (NA 2v2) | broadcast | $10,810 | 1 | 1 | 1 | 7 | 17 |
| | cards | $11,410 | 1 | 1 | 2 | 14 | 38 |
| | broadcast's definition | — | 1 | 1 | 1 | 7 | 17 |
| AnimeFan1266 (NA 2v2) | broadcast | $14,008 | 0 | 1 | 1 | 7 | 25 |
| | cards | $14,508 | 0 | 1 | 2 | 18 | 49 |
| | broadcast's definition | — | 0 | 1 | 1 | 7 | 25 |

What settles each part of the definition:
- **The mode:** Raydish's 0 golds are his 2v2 golds; his 6 are all in 1v1.
- **No crew battles:** Godly has 23 1v1 golds with crew battles, 22 without; with the Autumn win left out, 21. Mounir's
  top 8s match only without his crew battle 5th (Eternal Sports Crew Battle Championship 2026 - Europe).
- **Before the event:** each player is off by exactly their Autumn 2026 placement in that mode (Godly 1st, Bamya 5th,
  Mounir 9th in EU 1v1; Raydish and megD 2nd, Moni and AnimeFan1266 3rd in NA 2v2).
- **No tier filter:** the counts match with every official event, regionals included.

Earnings are career figures across modes. The broadcast's are lower by $150 to $2,500 per player. That fits the
Stats API's figure (as of 2026-10-02) including the Autumn 2026 prize money, but eval-v1 has no per-event payouts to
check it against.

## Broadcast-style cards (2026-11-18)

The cards now copy the broadcast graphics as closely as possible, at the producer's suggestion (`DATA.md`, "Broadcast
graphics"). Each card is a fixed 1920x1080 frame (`app/static/broadcast.css`, `broadcast.js`), scaled to the page. The
lifetime card is done; the head-to-head (the Godly vs Bamya image), the set list (the "Matches" sidebar) and the 2v2
elimination final follow.

**Colors**, the median of each region's pixels in the reference: panel cream `#faf2eb`, orange `#c85a41` (the bar,
borders, circles and placement boxes; `#c55d46` for the earnings figure), label boxes `#160c08`, ink `#050000`, and
the background's tones in a gradient standing in for the event art.

**Fonts.** The broadcast's own fonts aren't known. My guesses, and the free matches used:

| Text | Likely | Free match | How it was chosen |
|---|---|---|---|
| Name, headings (EARNINGS, MEDALS, PLACEMENT), the figures | a heavy geometric sans, such as Gilroy Black. Not Gotham: Montserrat, built on Gotham's shapes, runs about 10% wider than the reference | Gabarito Black (800 for the earnings figure) | Of 26 free families, measured on the four headings' width per cap height: rms error 4% (Montserrat 900 wasn't in the top 10) |
| LIFETIME STATS, the bar, the row labels, the numerals | a geometric sans, regular to medium, such as Gotham | Montserrat Medium and SemiBold | Shapes and widths by eye; boxes within 5 px |

**Shapes.** The panel's torn edge was traced by scanning each row of the reference for where the cream ends. Its
orange border is the same outline shifted 11 px (in the reference's scale), and four cream shards sit along it. The
legend covers the edge below the bar, so the edge there is interpolated.

**Matching.** `app/dev/compare_card.py` renders a card with Playwright (driving the installed Chrome) and writes the
render, the reference, side by side, a 50% overlay and a difference image, to a folder outside the repo. The
reference (1206x665) is scaled to 1920 wide and top-aligned; it lacks about 21 px at the bottom. On Mounir's card, every
heading, row and box is within 5 px of the reference in the 1920 frame, and the cream, bar orange and box colors match
to the hex digit.

**What differs on purpose:**
- No event logo, and the subtitle bar shows the official results' first and latest years instead of country, team and
  PR rank, which the data doesn't have.
- No Top 32 row until `player_results`' summary has the column.
- The figures are the cards' scope (all official events, both modes, crew battles as 1v1), so Mounir shows 1 / 3 / 6
  and 20 top 8s in 1v1, against the broadcast's 19. A line at the panel's foot states the scope and the earnings'
  source and date, and the page repeats it in the "What this counts" box below the frame, with the mode switch.
- The legend slot (x 400–960, y 560–1080) stays empty until the player's main is in `data/curated/player_legends.csv`
  and its WebP and manifest entry are in `app/static/art/legends/`.
