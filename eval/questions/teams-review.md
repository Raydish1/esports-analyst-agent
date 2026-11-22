# Test conversations: review

Made by `python eval/conversations.py review` from [`teams.toml`](teams.toml), which is the file to edit.

5 conversations, 9 turns, with expected facts computed from the frozen snapshot `data/db/eval/eval-v1.sqlite` (build 20261007T230135Z). Each turn shows what a right answer says, the automatic checks scoring it, and the queries behind them with their results.

**To verify:** check each turn's expected answer against what you know, then fill in `verified` for its conversation in `teams.toml`: `yes`, or `no: ...` or `partly: ...` with what's right. Then re-run the command to update this page.

**Verified:** 0 of 5.

| Id | Conversation | Turns | Measures | Verified |
|---|---|---|---|---|
| [c20](#c20) | the teams Raydish and megD faced most | 2 | rank_pairs with player_id and partner_id: a duo's opposing teams, not each player's opponents |  |
| [c21](#c21) | Raydish and megD against Zen and hideaway | 2 | team_head_to_head after a choice from suggestions, not a 1v1 head-to-head |  |
| [c22](#c22) | two teams after an event's top 8 | 3 | team_head_to_head; run_sql or a template when the previous turn's results don't hold the answer |  |
| [c23](#c23) | two teams written without an and | 1 | team_head_to_head for 'X Y vs Z W', which the scope check's team pattern doesn't see |  |
| [c24](#c24) | a reply with nothing before it | 1 | the give-up: no fact left once the prompt's 'from 2017' was left out |  |

<a id="c20"></a>

## c20. the teams Raydish and megD faced most

From 20261122T043945Z-001, turns 2-3.

### Turn 1: who have raydish and megd versed the most in 2v2

**Expected:** Raydish and megD together: three teams tied at 5 sets, Marckiem00 and futurebubbles366 (Raydish and megD 5-0), bestjava and fakey7 (2-3) and luna and Snowy!! (2-3), then four teams at 3. A right answer counts their sets as a team, or says which reading it took. Live, it gave each player's own most-played opponents, Pink | Guichabou first.

**Checks:** rows [[["Marckiem00 and futurebubbles366", 146052], 5, 0], [["bestjava and fakey7", 145913], 5, 2, 3], [["luna and Snowy!!", 51494], 5, 2, 3]]; says ["Marckiem00", "bestjava", "luna"]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against each team, the most sets first

```sql
SELECT h.opponent1_id, a.name, h.opponent2_id, b.name, h.matches, h.wins, h.losses, h.games_won, h.games_lost
FROM v_head_to_head_2v2 h JOIN players a ON a.player_id = h.opponent1_id JOIN players b ON b.player_id = h.opponent2_id
WHERE h.player_id = 160000 AND h.partner_id = 142100 ORDER BY h.matches DESC, a.name LIMIT 8
```

| opponent1_id | name | opponent2_id | name | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 146052 | Marckiem00 | 160218 | futurebubbles366 | 5 | 5 | 0 | 15 | 5 |
| 145913 | bestjava | 159255 | fakey7 | 5 | 2 | 3 | 10 | 12 |
| 51494 | luna | 145915 | Snowy!! | 5 | 2 | 3 | 7 | 10 |
| 88841 | Dragon! | 169119 | flowerVS | 3 | 2 | 1 | 7 | 5 |
| 141522 | Pink \| Zen | 142042 | hideawaybh | 3 | 0 | 3 | 3 | 9 |
| 118094 | experiencedoa | 142310 | maidski | 3 | 0 | 3 | 3 | 9 |
| 132 | loreszz | 135748 | whoiskyna | 3 | 2 | 1 | 6 | 5 |
| 111756 | Anon Alex | 158644 | 5p1d3rw3b | 2 | 1 | 1 | 5 | 5 |

### Turn 2: what team has raydish and megd fought the most as a team

**Expected:** The same three teams, tied at 5 sets: Marckiem00 and futurebubbles366 (Raydish and megD 5-0), bestjava and fakey7 (2-3) and luna and Snowy!! (2-3). Live, it said they played 20 events together and left the rest out.

**Checks:** rows [[["Marckiem00 and futurebubbles366", 146052], 5, 0], [["bestjava and fakey7", 145913], 5, 2, 3], [["luna and Snowy!!", 51494], 5, 2, 3]]; says ["Marckiem00", "bestjava", "luna"]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against each team, the most sets first

```sql
SELECT h.opponent1_id, a.name, h.opponent2_id, b.name, h.matches, h.wins, h.losses, h.games_won, h.games_lost
FROM v_head_to_head_2v2 h JOIN players a ON a.player_id = h.opponent1_id JOIN players b ON b.player_id = h.opponent2_id
WHERE h.player_id = 160000 AND h.partner_id = 142100 ORDER BY h.matches DESC, a.name LIMIT 8
```

| opponent1_id | name | opponent2_id | name | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 146052 | Marckiem00 | 160218 | futurebubbles366 | 5 | 5 | 0 | 15 | 5 |
| 145913 | bestjava | 159255 | fakey7 | 5 | 2 | 3 | 10 | 12 |
| 51494 | luna | 145915 | Snowy!! | 5 | 2 | 3 | 7 | 10 |
| 88841 | Dragon! | 169119 | flowerVS | 3 | 2 | 1 | 7 | 5 |
| 141522 | Pink \| Zen | 142042 | hideawaybh | 3 | 0 | 3 | 3 | 9 |
| 118094 | experiencedoa | 142310 | maidski | 3 | 0 | 3 | 3 | 9 |
| 132 | loreszz | 135748 | whoiskyna | 3 | 2 | 1 | 6 | 5 |
| 111756 | Anon Alex | 158644 | 5p1d3rw3b | 2 | 1 | 1 | 5 | 5 |

**Verified:** not yet

<a id="c21"></a>

## c21. Raydish and megD against Zen and hideaway

From 20261122T043945Z-001, turns 4-5.

### Turn 1: what is raydish and megd's 2v2 history with zen and hideaway

**Expected:** "zen" is three players' name: Pink | Zen (66 official results) and two named Zen (31 and 8), no clear cut. So the agent suggests them, Pink | Zen first, before it looks anything up.

**Checks:** suggests 141522; grounded and named (every turn)

**Query 1:** the players named zen, with their official results

```sql
SELECT p.player_id, p.name, COUNT(r.event_id) AS results FROM players p LEFT JOIN v_results r USING (player_id)
WHERE p.player_id IN (141522, 144384, 39618) GROUP BY p.player_id ORDER BY results DESC
```

| player_id | name | results |
|---|---|---|
| 141522 | Pink \| Zen | 66 |
| 144384 | Zen | 31 |
| 39618 | Zen | 8 |

### Turn 2: the first one

**Expected:** The user picked Pink | Zen. Raydish and megD against Pink | Zen and hideawaybh (formerly Hideaway) in 2v2: 0-3 in sets, games 3-9. They lost 0-3 at the Midseason Championship 2026 2v2 (2026-06-12), then 2-3 and 1-3 at the Autumn Championship - North America 2026 - 2v2 (2026-09-27). Live, it gave Raydish's 2v2 meetings with Pink | Zen with any partner (4-6 in 10) as the two teams' record.

**Checks:** players [160000, 142100, 141522, 142042]; rows [[["Raydish and megD", 160000], ["Pink | Zen and hideawaybh", 141522], 0, 3, 9]]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against Pink | Zen and hideawaybh

```sql
SELECT player_id, partner_id, opponent1_id, opponent2_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_2v2 WHERE player_id = 160000 AND partner_id = 142100 AND 141522 IN (opponent1_id, opponent2_id)
AND 142042 IN (opponent1_id, opponent2_id)
```

| player_id | partner_id | opponent1_id | opponent2_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 160000 | 142100 | 141522 | 142042 | 3 | 0 | 3 | 3 | 9 |

**Query 2:** each set between the two teams

```sql
SELECT e.tournament_name, e.event_name, a.start_date, a.won, a.games_won, a.games_lost
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side = a.side AND b.player_id = 142100
JOIN v_match_results c ON c.match_id = a.match_id AND c.side <> a.side AND c.player_id = 141522
JOIN v_match_results d ON d.match_id = a.match_id AND d.side = c.side AND d.player_id = 142042
JOIN events e ON e.event_id = a.event_id
WHERE a.player_id = 160000 AND a.mode = '2v2' ORDER BY a.start_date, a.start_time
```

| tournament_name | event_name | start_date | won | games_won | games_lost |
|---|---|---|---|---|---|
| Midseason Championship 2026 – 2v2 | NULL | 2026-06-12 | 0 | 0 | 3 |
| Autumn Championship - North America 2026 - 2v2 | NULL | 2026-09-27 | 0 | 2 | 3 |
| Autumn Championship - North America 2026 - 2v2 | NULL | 2026-09-27 | 0 | 1 | 3 |

**Verified:** not yet

<a id="c22"></a>

## c22. two teams after an event's top 8

From 20261122T043945Z-001, turns 6-7, and 20261122T043945Z-002, turn 1.

### Turn 1: show a 2v2 graphic from autumn championship 2v2 2026 NA

**Expected:** The Autumn Championship - North America 2026 - 2v2 (2026-09-27): 1st Pink | Zen and hideawaybh, 2nd Raydish and megD, 3rd Moni- and animefan1266, 4th Marckiem00 and futurebubbles366, 5th Bunny meow and SiB Royalty, and Dragon! and flowerVS, 7th Greedy11z and fakey7, and Hexoo and Savior of NA. The agent draws no graphic: a right answer gives the results. Live, it gave only the bracket link.

**Checks:** calls ["event_results"]; rows [[["Pink | Zen / hideawaybh", 141522], 1], [["Raydish / megD", 160000], 2]]; says ["Pink | Zen", "Raydish"]; grounded and named (every turn)

**Query 1:** the event's top 8

```sql
SELECT r.placement, r.player_id, p.name FROM v_results r JOIN players p USING (player_id)
WHERE r.event_id = '774eaef2-3f11-4c7b-f9ab-08ded4cb1c05' AND r.placement <= 8 ORDER BY r.placement, p.name
```

| placement | player_id | name |
|---|---|---|
| 1 | 141522 | Pink \| Zen |
| 1 | 142042 | hideawaybh |
| 2 | 160000 | Raydish |
| 2 | 142100 | megD |
| 3 | 152572 | Moni- |
| 3 | 146616 | animefan1266 |
| 4 | 146052 | Marckiem00 |
| 4 | 160218 | futurebubbles366 |
| 5 | 113110 | Bunny meow |
| 5 | 88841 | Dragon! |
| 5 | 682327 | SiB Royalty |
| 5 | 169119 | flowerVS |
| 7 | 171417 | Greedy11z |
| 7 | 169084 | Hexoo |
| 7 | 684851 | Savior of NA |
| 7 | 159255 | fakey7 |

### Turn 2: raydish and megd vs moni and animefan1266

**Expected:** They met once: Raydish and megD beat Moni- and animefan1266 3-2 at the Autumn Championship - North America 2026 - 2v2 (2026-09-27), so 1-0 in sets. Live, the agent called no tool and answered from the previous turn's top 8, which holds no sets: "they did not face" each other.

**Checks:** players [160000, 142100, 152572, 146616]; rows [[["Raydish and megD", 160000], ["Moni- and animefan1266", 152572], 1, 0, 3, 2]]; not_says ["never met", "did not face", "didn't face", "never faced", "not face"]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against Moni- and animefan1266

```sql
SELECT player_id, partner_id, opponent1_id, opponent2_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_2v2 WHERE player_id = 160000 AND partner_id = 142100 AND 152572 IN (opponent1_id, opponent2_id)
AND 146616 IN (opponent1_id, opponent2_id)
```

| player_id | partner_id | opponent1_id | opponent2_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 160000 | 142100 | 146616 | 152572 | 1 | 1 | 0 | 3 | 2 |

### Turn 3: yes they did

**Expected:** They did meet, once: Raydish and megD won 3-2 at the Autumn Championship - North America 2026 - 2v2. If turn 2 said so, a right reply confirms it; if it said they never met, it looks again and corrects that. Live, this message went to a new conversation by mistake, where it got "I couldn't look this up in the data, so I won't guess." (c24).

**Checks:** rows [[["Raydish and megD", 160000], ["Moni- and animefan1266", 152572], 1, 0, 3, 2]]; says_any ["3-2", "3–2"]; not_says ["couldn't look this up", "never met", "did not face", "didn't face"]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against Moni- and animefan1266

```sql
SELECT player_id, partner_id, opponent1_id, opponent2_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_2v2 WHERE player_id = 160000 AND partner_id = 142100 AND 152572 IN (opponent1_id, opponent2_id)
AND 146616 IN (opponent1_id, opponent2_id)
```

| player_id | partner_id | opponent1_id | opponent2_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 160000 | 142100 | 146616 | 152572 | 1 | 1 | 0 | 3 | 2 |

**Query 2:** the one set between the two teams

```sql
SELECT e.tournament_name, e.event_name, a.start_date, a.won, a.games_won, a.games_lost
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side = a.side AND b.player_id = 142100
JOIN v_match_results c ON c.match_id = a.match_id AND c.side <> a.side AND c.player_id = 152572
JOIN v_match_results d ON d.match_id = a.match_id AND d.side = c.side AND d.player_id = 146616
JOIN events e ON e.event_id = a.event_id
WHERE a.player_id = 160000 AND a.mode = '2v2' ORDER BY a.start_date, a.start_time
```

| tournament_name | event_name | start_date | won | games_won | games_lost |
|---|---|---|---|---|---|
| Autumn Championship - North America 2026 - 2v2 | NULL | 2026-09-27 | 1 | 3 | 2 |

**Verified:** not yet

<a id="c23"></a>

## c23. two teams written without an and

From 20261122T043945Z-002, turn 2.

### Turn 1: raydish megd vs marckiemoo futurebubble

**Expected:** Two teams: Raydish and megD against Marckiem00 and futurebubbles366 (formerly Futurebubble) in 2v2, 5-0 in sets (games 15-5): 3-2 at CEO 2024 Doubles, 3-1 at the Winter Championship - North America 2025 2v2, 3-1 at the Spring Championship - North America 2026 - 2v2, and 3-0 and 3-1 at the Autumn Championship - North America 2026 - 2v2. A right answer reads it as two teams, or says which reading it took. Live, it gave Raydish's 1v1 record against Marckiem00 (6-7) alone.

**Checks:** players [160000, 142100, 146052, 160218]; rows [[["Raydish and megD", 160000], ["Marckiem00 and futurebubbles366", 146052], 5, 0, 15]]; grounded and named (every turn)

**Query 1:** Raydish and megD's 2v2 record against Marckiem00 and futurebubbles366

```sql
SELECT player_id, partner_id, opponent1_id, opponent2_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_2v2 WHERE player_id = 160000 AND partner_id = 142100 AND 146052 IN (opponent1_id, opponent2_id)
AND 160218 IN (opponent1_id, opponent2_id)
```

| player_id | partner_id | opponent1_id | opponent2_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|---|---|
| 160000 | 142100 | 146052 | 160218 | 5 | 5 | 0 | 15 | 5 |

**Verified:** not yet

<a id="c24"></a>

## c24. a reply with nothing before it

From 20261122T043945Z-002, turn 1.

### Turn 1: yes they did

**Expected:** Nothing comes before it, so there's nothing to look up or confirm: a right answer asks what the user means, and states no fact. Live, the answer asked for a question "about an official event, player, or statistic from 2017 onward". The number check left out that sentence's 2017, the prompt's own fact, and with no fact left the whole answer became "I couldn't look this up in the data, so I won't guess."

**Checks:** not_says ["couldn't look this up", "won't guess"]; grounded and named (every turn)

**Verified:** not yet
