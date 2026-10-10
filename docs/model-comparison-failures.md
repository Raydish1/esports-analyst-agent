# Model comparison: failure analysis

What went wrong in the model comparison of 2026-10-10 (run `20261010T062843Z`; see [`experiments.md`](experiments.md)), and how much of it is chance.
- Quotes from the models' reasoning are verbatim. Queries are as the models wrote them, with only line breaks and indentation condensed.
- The full replies are in `data/experiments/<run>/replies.jsonl` (git-ignored), and the queries and results in `eval/results/`.
- A query "with the name fixed" changes only the name it looked up, to show what else was wrong.

## 1. Questions 6 and 8: where qwen3:8b diverged from qwen3:4b

qwen3:4b's two rows are one generation, since it thinks either way, so its query is shown once.

### Question 6: "Who has megd played with in 2v2 tournaments, and how did they place?"

**Expected:** 17 partners, the most frequent Raydish (20 events, best 2nd), hardymj (4, best 9th) and Winged_Shell (3, best 17th). megd is player 142100, whose display name is `megD`.

| | qwen3:4b | qwen3:8b, thinking off | qwen3:8b, thinking on |
|---|---|---|---|
| Name lookup | `player_aliases`, the prompt's pattern | `players.name = 'megd'` | `players.name = 'megd'` |
| View | `v_team_results` | `v_team_results` | `v_team_results` |
| Filter | the player | the player, and `t.mode = '2v2'` | the player |
| Outcome | ✓ (46 rows) | unknown column `t.mode` | empty result |

qwen3:4b:
```sql
SELECT t.partner_id, t.placement
FROM v_team_results t
WHERE t.player_id = (
    SELECT p.canonical_id
    FROM player_aliases a
    JOIN players p ON p.player_id = a.player_id
    WHERE a.alias = 'megd'
    ORDER BY a.kind = 'nickname' DESC,
             (SELECT COUNT(*) FROM v_results r WHERE r.player_id = p.canonical_id) DESC
    LIMIT 1
)
```

qwen3:8b, thinking off:
```sql
SELECT t.partner_id AS partner_id, t.event_id, t.tournament_name, t.event_name, t.start_date, t.placement
FROM v_team_results t
WHERE t.player_id = (SELECT canonical_id FROM players WHERE name = 'megd')
    AND t.mode = '2v2'
```

qwen3:8b, thinking on:
```sql
SELECT p.name AS partner, tr.placement
FROM players p
JOIN v_team_results tr ON p.player_id = tr.partner_id
WHERE tr.player_id = (
    SELECT player_id
    FROM players
    WHERE name = 'megd'
)
```

**Where it diverged: the name lookup, in both configurations.** The view and the logic were right.
- `players.name = 'megd'` finds nobody. The display name is `megD`, and SQLite's `=` is case-sensitive.
  - The subquery returns NULL, so the filter matches no rows.
  - `player_aliases` has 'megd' (kind `display_name`) for player 142100.
- With thinking off, it also filtered on `t.mode`, which `v_team_results` doesn't have, since the view holds only 2v2 results. SQLite rejects the query before it runs, so the name problem never shows.
- With the name fixed (`'megD'`), the thinking-on query is correct. So is the thinking-off one once the `mode` filter is also removed.

qwen3:8b's thinking considered the alias lookup and set it aside, assuming 'megd' was a display name, which the question never says:
> "So maybe I should use the method described in the note. But since the user is asking about 'megd', perhaps they are referring to the display name."

> "The problem says that the name is the current display name, so assuming it's unique."

> "Alternatively, perhaps the player_aliases table could have 'megd' as an alias. But the question is about the display name."

qwen3:4b started from the opposite assumption, then copied the prompt's lookup pattern unchanged:
> "Note: "megd" is a player alias. We have to map it to the canonical player_id."

### Question 8: "Who has the best record against marckiemoo?"

**Expected:** V3M_T4NQUIL0 (3–2), ahead of Raydish (6–7) and gdsandstorm (4–7), among the 11 players with at least 5 matches against Marckiem00 (player 146052). 'marckiemoo' is a curated nickname.

| | qwen3:4b | qwen3:8b, thinking off | qwen3:8b, thinking on |
|---|---|---|---|
| Name lookup | `player_aliases`, the prompt's pattern | `players.name = 'marckiemoo'` | `players.name = 'marckiemoo'` |
| View | `v_head_to_head_1v1` | `v_head_to_head_1v1` | `v_head_to_head_1v1` |
| Filter | `opponent_id` is marckiemoo, at least 5 matches | the same | `player_id` or `opponent_id` is marckiemoo |
| Logic | ranks by `wins / matches`, returns `player_id` | ranks the same, returns `opponent_id` | adds up both directions per opponent |
| Outcome | ✓ (V3M_T4NQUIL0; the query took 82–84 s) | empty result | empty result |

qwen3:4b:
```sql
SELECT player_id
FROM v_head_to_head_1v1
WHERE opponent_id = (
    SELECT p.canonical_id
    FROM player_aliases a
    JOIN players p ON p.player_id = a.player_id
    WHERE a.alias = 'marckiemoo'
    ORDER BY a.kind = 'nickname' DESC,
             (SELECT COUNT(*) FROM v_results r WHERE r.player_id = p.canonical_id) DESC
    LIMIT 1
)
    AND matches >= 5
ORDER BY (wins * 1.0) / matches DESC
LIMIT 1
```

qwen3:8b, thinking off:
```sql
SELECT
  v_head_to_head_1v1.opponent_id AS player_id,
  ROUND(CAST(v_head_to_head_1v1.wins * 100.0 / NULLIF(v_head_to_head_1v1.matches, 0) AS REAL), 2) AS win_rate
FROM v_head_to_head_1v1
WHERE v_head_to_head_1v1.opponent_id = (SELECT player_id FROM players WHERE name = 'marckiemoo')
  AND v_head_to_head_1v1.matches >= 5
ORDER BY win_rate DESC
LIMIT 1
```

qwen3:8b, thinking on:
```sql
WITH target_id AS (
    SELECT player_id
    FROM players
    WHERE name = 'marckiemoo'
),
h2h AS (
    SELECT
        CASE
            WHEN player_id = (SELECT player_id FROM target_id) THEN opponent_id
            WHEN opponent_id = (SELECT player_id FROM target_id) THEN player_id
        END AS opponent_id,
        wins,
        losses,
        matches
    FROM v_head_to_head_1v1
    WHERE player_id = (SELECT player_id FROM target_id) OR opponent_id = (SELECT player_id FROM target_id)
),
agg AS (
    SELECT opponent_id, SUM(wins) AS total_wins, SUM(losses) AS total_losses, SUM(matches) AS total_matches
    FROM h2h
    GROUP BY opponent_id
    HAVING SUM(matches) >= 5
)
SELECT p.name, a.total_wins, a.total_losses, a.total_matches, (a.total_wins * 1.0 / a.total_matches) AS win_rate
FROM agg a
JOIN players p ON a.opponent_id = p.player_id
ORDER BY win_rate DESC
LIMIT 1
```

**Where it diverged: the name lookup in both configurations, and the logic in both.** Fixing the name alone wouldn't have saved either query.
- **Name:** no player is named 'marckiemoo'. The display name is `Marckiem00`, with zeros, so even a case-insensitive match finds nobody. Only the curated nickname in `player_aliases` reaches the player.
- **Thinking off:** the filter and the ranking were right, but it returned the wrong column.
  - `opponent_id` is marckiemoo's own ID, which the query labels `player_id`.
  - With the name fixed, it returns `(146052, 60.0)`: marckiemoo, with V3M_T4NQUIL0's win rate.
- **Thinking on:** it read the view in both directions.
  - `v_head_to_head_1v1` already holds every pairing from both sides: Marckiem00 has 105 rows each way.
  - Adding both directions per opponent counts each match twice. An opponent's wins plus marckiemoo's wins against them is every decided match, so all 22 opponents come out at exactly 0.5.
  - Doubled matches also let players with 3 or 4 real matches pass "at least 5" (22 instead of 11), and `LIMIT 1` picks one of the ties arbitrarily.
  - With the name fixed, it returns loreszz, who went 0–4 against marckiemoo.

qwen3:8b's thinking on the name:
> "But maybe there's a possibility that marckiemoo is an alias. But the question is about the player's name, so perhaps it's safe to assume that the name in the players table is correct."

> "Well, the problem states that every player_id is a person's canonical ID, so perhaps the name is unique."

(The prompt says that of every player_id *in a view*, not of names.)

On the direction, it saw that the view holds both sides, and concluded it had to read both:
> "So, for each match between player A and player B, there would be two entries: one where player_id is A and opponent_id is B, and another where player_id is B and opponent_id is A."

> "So to find all matches against marckiemoo, we need to consider both cases where player_id is marckiemoo or opponent_id is marckiemoo."

It also noted that the rows with marckiemoo as `player_id` hold marckiemoo's own record, then added them in anyway:
> "So, if the player_id is the target, then the wins and losses are the target's record against the opponent."

qwen3:4b read the view one way, as the prompt describes it (a person's record against an opponent):
> "So for a given opponent (target_player_id), we want the rows where opponent_id = target_player_id."

### Across the run: which name lookup each configuration chose

On the nine questions about a player (all but 10), the configurations didn't choose the lookup the same way every time:

| | Alias lookup | `players.name` |
|---|---|---|
| qwen3:4b | 8 | 1: question 4 (wrong) |
| qwen3:8b, thinking off | 3 | 6: questions 2, 3, 4, 6, 8 and 12 (right only on 2) |
| qwen3:8b, thinking on | 6 | 3: questions 6, 8 and 11 (right on 11) |

`players.name` works only when the question uses the exact display name, as "Raydish" does in questions 2 and 11.

## 2. Reruns: consistent or chance?

**Setup:** questions 6 and 8 again, five times each, with seeds 1 to 5 (the first run used seed 0).
- qwen3:4b and qwen3:8b, both with thinking on.
- Otherwise as in the first run: the same prompt and options, and a 90 s query limit.
- Run `20261010T181126Z`:

```
python eval/model_comparison.py --model qwen3:4b --model qwen3:8b --think on --question 6 --question 8 --seed 1 --seed 2 --seed 3 --seed 4 --seed 5
```

**By the check:**

| Question | qwen3:4b | qwen3:8b |
|---|---|---|
| 6. megd's 2v2 partners | 5/5 | 3/5 |
| 8. Best record against marckiemoo | 1/5 | 0/5 |

**Each run, inspected:**
- "Both sides" means the query read a view that already holds every pairing from both sides (A with B, and B with A) as if it held each once.
- "Correct with the name fixed" means the same query with only the name changed to the display name.

| Question | Seed | qwen3:4b | qwen3:8b |
|---|---|---|---|
| 6 | 1 | ✓ | ✓ |
| 6 | 2 | ✓ | ✓ |
| 6 | 3 | passed the check, but wrong: both sides, so 46 of its 92 rows name megD as their own partner | wrong: both sides, joined with `UNION`, which merged repeated placements with a partner (30 rows instead of 46) |
| 6 | 4 | passed the check, but wrong, as seed 3 | empty: it filtered `v_entries.format = '2v2'`, a value `format` never has (2v2 is the `mode`) |
| 6 | 5 | ✓ | ✓ |
| 8 | 1 | timeout at 90 s, but the query is correct (21 s when run alone) | empty: `players.name`; correct with the name fixed |
| 8 | 2 | cut off at the output cap; its last draft divides integers (`h.wins / h.matches`), which SQLite truncates, so it would have ranked wrongly anyway | wrong: alias lookup, but both sides, with wins and losses swapped (log in §3) |
| 8 | 3 | timeout, but correct (18 s alone) | empty: `players.name`; correct with the name fixed |
| 8 | 4 | timeout, but correct (28 s alone) | empty: `players.name`; with the name fixed, still wrong: both sides doubles every count, so the 5-match minimum let in Ahmet_ (3–1) |
| 8 | 5 | ✓ (the query took 77 s) | empty: `players.name`; correct with the name fixed |

**Name lookups:**
- qwen3:4b used the alias lookup in all ten.
- qwen3:8b used it in all five question 6 runs, and in one of five on question 8.

**What the reruns show:**
- **qwen3:8b's name lookup on question 6 was chance.** Seed 0's `players.name` didn't recur: it used the alias lookup in all five reruns. It still missed two of them, for other reasons.
- **On question 8 it's consistent.**
  - No right answer in six tries, seed 0 included, and `players.name` in five of them.
  - Its reasoning repeats seed 0's: "Let's assume that marckiemoo is the name in the players table." (seed 3).
  - With the name fixed, three of the five rerun queries would have been right.
- **Reading a view from both sides is a second, recurring error, in both models.**
  - `v_team_results` and `v_head_to_head_1v1` hold every pairing from both sides, so a query should read one side.
  - qwen3:8b read both in 4 of its 12 tries at these two questions (six seeds, two questions), qwen3:4b in 2 of 12.
  - Two opposite misreadings lead to the same query.
    - **Knowing the view holds both sides, and reading both anyway:** qwen3:8b three times (question 8 seeds 0 and 2, question 6 seed 3). Question 6, seed 3:
      > "So if the team is A and B, then there would be two rows: one for A (player_id A, partner_id B) and one for B (player_id B, partner_id A). Therefore, to get all partners, we need to check both cases."
    - **Assuming each pairing appears once, with the player in either column:** qwen3:4b twice (question 6 seeds 3 and 4), qwen3:8b once (question 8 seed 4). qwen3:4b, question 6, seed 4:
      > "But in v_team_results, the player_id and partner_id are the two players. So for each row in v_team_results where either player_id or partner_id has the alias 'megd', we need to find the partner."
  - The prompt leaves room for both misreadings. It describes `v_team_results` as one row per person per partner per event, and `v_head_to_head_1v1` as a person's record against an opponent, without saying that every pairing appears from both sides.
  - Turning names into IDs before the SQL wouldn't prevent this. The prompt has to say it, or the agent has to check for it.
- **qwen3:4b's question 8 misses were mostly the time limit, not the logic.**
  - Three of its four misses were correct queries that ran past 90 s, because the ID lookup sits inside the head-to-head query. Looking IDs up first, as the agent will, avoids that.
  - The fourth hit the output cap.
- **Question 6's check is too lenient.** It passed two answers that list megD as their own partner. The check should fail an answer that names the player as their own partner.

**In all, of the ten rerun queries per model:**
- qwen3:4b wrote 7 right ones (3 on question 6, 4 on question 8), though the check counted 6.
- qwen3:8b wrote 3, and would have written 6 with names turned into IDs first.

**Time:** on these two questions the models took about as long, unlike in the full run.
- Over all six seeds: qwen3:4b 38.8 s and 6,194 output tokens per reply, qwen3:8b 35.0 s and 3,901.
- qwen3:8b writes about a third fewer tokens, but more slowly. In the full first run the means were 34.2 s and 22.2 s.

**Query times vary on this machine.**
- The same correct query shape took 77–84 s in the first run, over 90 s three times in the rerun, and 18–28 s when run alone afterwards.
- Other queries ran on the same machine during part of the rerun, one of them for 110 s, overlapping seed 1's query. Seeds 3 and 4 timed out without that.

**Caveat:** five seeds per question and model is still a small sample. It's enough to separate a 0-in-6 from a 5-in-6, not to rank two models that differ by one answer.

## 3. Example failure logs

Four failures, one of each type: three from the first run (`20261010T062843Z`) and one from the reruns (`20261010T181126Z`). qwen3:8b with thinking off replies with the query alone, so one of them has no reasoning to quote.

### Name lookup: qwen3:4b, question 4

- **Question:** "What does Impala vs Balloonboy's history look like?"
- **Run:** qwen3:4b, thinking on (its thinking-off row is the same generation): 7,408 output tokens, 46.9 s.
- **Reasoning:** it read both names as display names from the start, and kept to that though it questioned it more than once:
  > "So we are to look for two players: one with display name "Impala", the other with "Balloonboy"."

  > "But that is for mapping an alias to a player_id. Here we are using the display name, not an alias."

  > "So we assume they are stored with the same case."
- **SQL:**
  ```sql
  SELECT h.player_id, h.opponent_id, h.wins, h.losses, h.matches, h.games_won, h.games_lost, h.unscored_matches
  FROM v_head_to_head_1v1 h
  JOIN players p ON h.player_id = p.player_id AND p.name = 'Impala'
  JOIN players q ON h.opponent_id = q.player_id AND q.name = 'Balloonboy'
  ```
- **Database:** no rows, after 78.9 s.
- **Diagnosis:** "Balloonboy" is a former name of BBBalloonBoy (player 149305), which `player_aliases` has and `players.name` doesn't. With `'BBBalloonBoy'`, the same query returns the right record (2–1, 8–4 in games).

### Unknown column: qwen3:8b with thinking off, question 1

- **Question:** "What was the last tournament Boomie entered?"
- **Run:** qwen3:8b, thinking off: 115 output tokens, 8.4 s.
- **Reasoning:** none to quote.
- **SQL:**
  ```sql
  SELECT e.tournament_name
  FROM v_entries e
  JOIN (
      SELECT p.canonical_id
      FROM player_aliases a
      JOIN players p ON p.player_id = a.player_id
      WHERE a.alias = 'boomie'
      ORDER BY a.kind = 'nickname' DESC,
               (SELECT COUNT(*) FROM v_results r WHERE r.player_id = p.canonical_id) DESC
      LIMIT 1
  ) AS boomie ON e.player_id = boomie.player_id
  ORDER BY e.start_time DESC
  LIMIT 1
  ```
- **Database:** `OperationalError: no such column: boomie.player_id`.
- **Diagnosis:** the lookup is the prompt's pattern and finds the right Boomie (player 146606, of seven), but the join calls the subquery's column `player_id` when it's `canonical_id`. With that one name changed, the query returns the right event, Winter Doubles Championship - North America.

### Wrong ranking: qwen3:8b with thinking on, question 8 (rerun, seed 2)

- **Question:** "Who has the best record against marckiemoo?"
- **Run:** qwen3:8b, thinking on, seed 2 (run `20261010T181126Z`): 5,231 output tokens, 46.9 s.
- **Reasoning:** it used the alias lookup, and worked out correctly how to read a row where marckiemoo is the `player_id`:
  > "In the second case, marckiemoo's wins and losses against X are in that row, but X's record against marckiemoo would be (losses, wins) from that row."

  Then it wrote that mapping backwards in both branches, and took the result for the other player's record:
  > "Wait, but the player_id in the h2h CTE is the player's ID, and the wins_against and losses_against are their wins and losses against marckiemoo."
- **SQL:**
  ```sql
  WITH marckiemoo_id AS (
      SELECT p.canonical_id
      FROM player_aliases a
      JOIN players p ON a.player_id = p.player_id
      WHERE a.alias = 'marckiemoo'
      ORDER BY
          a.kind = 'nickname' DESC,
          (SELECT COUNT(*) FROM v_results r WHERE r.player_id = p.canonical_id) DESC
      LIMIT 1
  ),
  h2h AS (
      SELECT
          CASE
              WHEN player_id = (SELECT canonical_id FROM marckiemoo_id) THEN opponent_id
              ELSE player_id
          END AS player_id,
          CASE
              WHEN player_id = (SELECT canonical_id FROM marckiemoo_id) THEN wins
              ELSE losses
          END AS wins_against,
          CASE
              WHEN player_id = (SELECT canonical_id FROM marckiemoo_id) THEN losses
              ELSE wins
          END AS losses_against
      FROM v_head_to_head_1v1
      WHERE player_id = (SELECT canonical_id FROM marckiemoo_id)
         OR opponent_id = (SELECT canonical_id FROM marckiemoo_id)
  )
  SELECT player_id
  FROM (
      SELECT
          player_id,
          SUM(wins_against) AS total_wins,
          SUM(losses_against) AS total_losses,
          SUM(wins_against) * 1.0 / (SUM(wins_against) + SUM(losses_against)) AS win_rate
      FROM h2h
      GROUP BY player_id
      HAVING SUM(wins_against) + SUM(losses_against) >= 5
      AND player_id != (SELECT canonical_id FROM marckiemoo_id)
  )
  ORDER BY win_rate DESC
  LIMIT 1
  ```
- **Database:** one row, `132`, which is loreszz. The query took 25.7 s.
- **Diagnosis:** the ranking is inverted. In both branches `wins_against` holds marckiemoo's wins, so it ranks players by marckiemoo's win rate against them.
  - loreszz lost all four of their matches against marckiemoo.
  - Reading both sides also doubled every count, so the 5-match minimum let in players with 3 or 4 matches.
- **Another wrong ranking**, with no reasoning to quote: in the first run, qwen3:8b with thinking off ranked Raydish's wins (question 11) by a single match's games lost instead of the whole run's, and picked the Winter Championship 2023 over the Trial of Laufey.

### Cut off at the output cap: qwen3:4b, question 3

- **Question:** "Has Hexo ever placed top 8 in 1v1?"
- **Run:** qwen3:4b, thinking on: 8,192 output tokens (the cap), 52.2 s.
- **Reasoning:** it had a complete, correct query a quarter of the way through its 35,572 characters of thinking. The query returns 1 (yes).
  - It spent the rest going back over the name lookup: the nickname-first rule, and what the prompt's `players.player_id` means next to `canonical_id`. Halfway through:
    > "This is very confusing."

    Three-quarters of the way through:
    > "This is getting too complicated."
  - It wrote the final query out four more times before deciding:
    > "Final query."
- **SQL:** the reply stopped 179 characters in, inside the name lookup:
  ```
  SELECT EXISTS (
      SELECT 1
      FROM v_results r
      WHERE r.player_id = (
          SELECT p.canonical_id
          FROM player_aliases a
          JOIN players p ON p.player
  ```
- **Database:** the script took the fragment's last line starting with SELECT, `SELECT p.canonical_id FROM player_aliases a JOIN players p ON p.player`, which fails with `no such column: p.player`. The record counts it as cut off at the output cap.
- **Diagnosis:** the output cap, not the reasoning. The model had the answer with three-quarters of its budget left and kept checking it. With thinking off, the same generation's draft query was complete in the reply, and right.
