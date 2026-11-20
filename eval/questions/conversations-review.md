# Test conversations v1: review

Made by `python eval/conversations.py review` from [`conversations.toml`](conversations.toml), which is the file to edit.

7 conversations, 20 turns, with expected facts computed from the frozen snapshot `data/db/eval/eval-v1.sqlite` (build 20261007T230135Z). Each turn shows what a right answer says, the automatic checks scoring it, and the queries behind them with their results.

**To verify:** check each turn's expected answer against what you know, then fill in `verified` for its conversation in `conversations.toml`: `yes`, or `no: ...` or `partly: ...` with what's right. Then re-run the command to update this page.

**Verified:** 7 of 7.

| Id | Conversation | Turns | Measures | Verified |
|---|---|---|---|---|
| [c1](#c1) | megD's biggest records | 5 | fix 1: no turn keeps records it never looked up; fix 2: 'he' is megD; fix 4: Raydish isn't renamed capsar | yes |
| [c2](#c2) | picking a suggestion | 2 | fix 2: a reply to suggestions answers the original question with the chosen player | yes |
| [c3](#c3) | the 2v2 follow-up | 2 | fix 2: a follow-up without names continues the previous question; fix 3: no clarifying question sent back as an answer; fix 6: sets named by their events | yes |
| [c4](#c4) | CEO 2025 | 3 | fix 1: an event is looked up, never denied from memory | yes |
| [c5](#c5) | the crew battles | 3 | fix 5: 'cb' found by a retry the agent makes itself; fix 4: every player named, not numbered | yes |
| [c6](#c6) | Raydish and megD, then a stat card | 2 | turn 1: control; turn 2 failed live, and no fix targets it: player_results with mode 1v1 and top 1 gave Raydish's wins alone, and the answer said he has no 2v2 results | yes |
| [c7](#c7) | three standalone questions | 3 | control | yes |

<a id="c1"></a>

## c1. megD's biggest records

From 20261119T233544Z-002, turns 14-18.

### Turn 1: whats the biggest record megd has

**Expected:** Ambiguous: a record can be a result or a head-to-head. megD's official wins are 2, both counted as 1v1: the Summer Championship - North America 2026 - 1v1 (2026-07-19) and the Eternal Sports Crew Battle Championship 2026 - North America (2026-08-30), a crew battle. megD's head-to-head with the most sets is against luna: 18 sets, 6-12. A right answer says which reading it took, or asks.

**Checks:** grounded and named (every turn)

**Query 1:** megD's official wins

```sql
SELECT start_date, tournament_name, mode, format FROM v_official_wins WHERE player_id = 142100 ORDER BY start_time
```

| start_date | tournament_name | mode | format |
|---|---|---|---|
| 2026-07-19 | Summer Championship - North America 2026 - 1v1 | 1v1 | standard |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | 1v1 | crew_battle |

### Turn 2: i meant biggest records vs other players, like set/game count

**Expected:** megD's 1v1 head-to-heads with the most sets: luna 18 (megD 6-12, games 26-42), bestjava 10 (3-7, 15-23), STING RAY 9 (6-3, 20-13), then cosolix (5-2) and Impala (1-6) with 7 each.

**Checks:** rows_any [[[51494, "luna"], 18, 6, 12]]; grounded and named (every turn)

**Query 1:** megD's 1v1 head-to-heads, the most sets first

```sql
SELECT h.opponent_id, p.name, h.matches, h.wins, h.losses, h.games_won, h.games_lost
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.opponent_id
WHERE h.player_id = 142100 ORDER BY h.matches DESC, h.wins DESC LIMIT 5
```

| opponent_id | name | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|
| 51494 | luna | 18 | 6 | 12 | 26 | 42 |
| 145913 | bestjava | 10 | 3 | 7 | 15 | 23 |
| 81144 | STING RAY | 9 | 6 | 3 | 20 | 13 |
| 147563 | cosolix | 7 | 5 | 2 | 17 | 8 |
| 168635 | Impala | 7 | 1 | 6 | 7 | 17 |

### Turn 3: he doesnt have big records vs raydish or java or guichabou etc?

**Expected:** "he" is megD, and "java" is bestjava. megD's 1v1 records against them: Raydish 2-2 in 4 sets (games 8-9), bestjava 3-7 in 10 (15-23), and Pink | Guichabou 2-1 in 3 (8-4).

**Checks:** rows [[[160000, "Raydish"], 4, 2], [[145913, "bestjava"], 10, 3, 7], [[142284, "Guichabou"], 3, 2, 1]]; grounded and named (every turn)

**Query 1:** megD against Raydish, bestjava and Pink | Guichabou

```sql
SELECT h.opponent_id, p.name, h.matches, h.wins, h.losses, h.games_won, h.games_lost
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.opponent_id
WHERE h.player_id = 142100 AND h.opponent_id IN (160000, 145913, 142284)
```

| opponent_id | name | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|
| 142284 | Pink \| Guichabou | 3 | 2 | 1 | 8 | 4 |
| 145913 | bestjava | 10 | 3 | 7 | 15 | 23 |
| 160000 | Raydish | 4 | 2 | 2 | 8 | 9 |

### Turn 4: what about megd vs raydish

**Expected:** megD and Raydish are 2-2 in 4 1v1 sets (games 8-9): Raydish 3-1 at the North America - Summer Championship 2022, megD 3-1 at the North America - Autumn Championship 2023, megD 3-2 at Trial of Baldr - North America (Moose Wars) in 2024, and Raydish 3-1 at the Winter Championship - North America 2025. In 2v2, Raydish's teams won all 3 of their sets against megD's.

**Checks:** rows [[[142100, "megD"], [160000, "Raydish"], 4, 2]]; not_says ["147569", "capsar"]; grounded and named (every turn)

**Query 1:** megD's 1v1 record against Raydish

```sql
SELECT player_id, opponent_id, matches, wins, losses, games_won, games_lost, unscored_matches
FROM v_head_to_head_1v1 WHERE player_id = 142100 AND opponent_id = 160000
```

| player_id | opponent_id | matches | wins | losses | games_won | games_lost | unscored_matches |
|---|---|---|---|---|---|---|---|
| 142100 | 160000 | 4 | 2 | 2 | 8 | 9 | 0 |

**Query 2:** their four 1v1 sets

```sql
SELECT start_date, tournament_name, winner_name, winner_games, loser_games FROM v_sets_1v1
WHERE winner_id = 142100 AND loser_id = 160000
UNION ALL
SELECT start_date, tournament_name, winner_name, winner_games, loser_games FROM v_sets_1v1
WHERE winner_id = 160000 AND loser_id = 142100
ORDER BY start_date
```

| start_date | tournament_name | winner_name | winner_games | loser_games |
|---|---|---|---|---|
| 2022-07-31 | North America - Summer Championship 2022 | Raydish | 3 | 1 |
| 2023-09-24 | North America - Autumn Championship 2023 | megD | 3 | 1 |
| 2024-04-07 | Trial of Baldr - North America (Moose Wars) | megD | 3 | 2 |
| 2025-02-23 | Winter Championship - North America 2025 | Raydish | 3 | 1 |

**Query 3:** their teams' 2v2 sets: how many, and how many Raydish's side won

```sql
SELECT COUNT(*) AS sets, SUM(a.won) AS raydish_side_won FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
WHERE a.player_id = 160000 AND b.player_id = 142100 AND a.mode = '2v2'
```

| sets | raydish_side_won |
|---|---|
| 3 | 3 |

### Turn 5: show head to head megd vs raydish in a graphic

**Expected:** The same 2-2 record in 4 sets (games 8-9). The page draws its head-to-head card only from this turn's own head_to_head call, so the turn must make one.

**Checks:** calls ["head_to_head"]; players [142100, 160000]; rows [[[142100, "megD"], [160000, "Raydish"], 4, 2]]; not_says ["147569", "capsar"]; grounded and named (every turn)

**Verified:** yes

<a id="c2"></a>

## c2. picking a suggestion

From 20261119T233544Z-003, turns 1-2.

### Turn 1: whats megd and raydishes record in 1v1

**Expected:** megD resolves (142100), but "raydishes" matches no player exactly, so the agent suggests the closest names instead of guessing: Raydish (160000) first, then Radses and radish.

**Checks:** suggests 160000; grounded and named (every turn)

**Query 1:** the players named Raydish, Radses and radish, with their official results

```sql
SELECT p.player_id, p.name, COUNT(r.event_id) AS results FROM players p LEFT JOIN v_results r USING (player_id)
WHERE p.player_id IN (160000, 24, 169374) GROUP BY p.player_id ORDER BY results DESC
```

| player_id | name | results |
|---|---|---|
| 160000 | Raydish | 98 |
| 24 | Radses | 3 |
| 169374 | radish | 2 |

### Turn 2: the first one

**Expected:** The user picked Raydish: megD and Raydish's 1v1 record, 2-2 in 4 sets (games 8-9), the sets as in c1. Nothing about Addymestic, the worked example the bare reply retrieved.

**Checks:** players [142100, 160000]; not_players [115695, 222222]; rows [[[142100, "megD"], [160000, "Raydish"], 4, 2]]; not_says ["Addymestic"]; grounded and named (every turn)

**Query 1:** megD's 1v1 record against Raydish

```sql
SELECT player_id, opponent_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_1v1 WHERE player_id = 142100 AND opponent_id = 160000
```

| player_id | opponent_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|
| 142100 | 160000 | 4 | 2 | 2 | 8 | 9 |

**Verified:** yes

<a id="c3"></a>

## c3. the 2v2 follow-up

From 20261119T233544Z-002, turns 6-7.

### Turn 1: whats raydish's record with kyna

**Expected:** Kyna is whoiskyna (formerly Kyna). Raydish leads 5-2 in 7 1v1 sets (games 17-10): whoiskyna 3-2 at BCX 2022; Raydish 3-1 and 3-0 at the Winter Royale 2023, 3-0 at the Spring Royale 2024, and 3-1 and 3-2 at the Autumn Royale 2024; whoiskyna 3-0 at BCX 2024. Each set is named by its event, not its date. In 2v2, their teams met in 5 sets, Raydish's side 2-3.

**Checks:** rows [[[160000, "Raydish"], [135748, "whoiskyna"], 7, 5, 2]]; says_any ["Royale", "BCX", "World Championship Expo"]; grounded and named (every turn)

**Query 1:** Raydish's 1v1 record against whoiskyna

```sql
SELECT player_id, opponent_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_1v1 WHERE player_id = 160000 AND opponent_id = 135748
```

| player_id | opponent_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|
| 160000 | 135748 | 7 | 5 | 2 | 17 | 10 |

**Query 2:** their seven 1v1 sets

```sql
SELECT start_date, tournament_name, winner_name, winner_games, loser_games FROM v_sets_1v1
WHERE winner_id = 160000 AND loser_id = 135748
UNION ALL
SELECT start_date, tournament_name, winner_name, winner_games, loser_games FROM v_sets_1v1
WHERE winner_id = 135748 AND loser_id = 160000
ORDER BY start_date
```

| start_date | tournament_name | winner_name | winner_games | loser_games |
|---|---|---|---|---|
| 2022-11-04 | Brawlhalla World Championship Expo 2022 | whoiskyna | 3 | 2 |
| 2023-03-11 | Brawlhalla - Winter Royale 2023 | Raydish | 3 | 0 |
| 2023-03-11 | Brawlhalla - Winter Royale 2023 | Raydish | 3 | 1 |
| 2024-05-17 | Brawlhalla - Spring Royale 2024 | Raydish | 3 | 0 |
| 2024-10-11 | Brawlhalla - Autumn Royale 2024 | Raydish | 3 | 2 |
| 2024-10-11 | Brawlhalla - Autumn Royale 2024 | Raydish | 3 | 1 |
| 2024-11-15 | Brawlhalla World Championship Expo 2024 | whoiskyna | 3 | 0 |

### Turn 2: tell me about the 2v2 record

**Expected:** It continues Raydish and whoiskyna: in 2v2, Raydish's teams and whoiskyna's teams met in 5 sets, and Raydish's side won 2 and lost 3. The previous turn's head_to_head result already holds it, so no question back.

**Checks:** window_has ["met in 5 sets"]; says_numbers [5, 2, 3]; grounded and named (every turn)

**Query 1:** their teams' 2v2 sets: how many, and how many Raydish's side won

```sql
SELECT COUNT(*) AS sets, SUM(a.won) AS raydish_side_won FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
WHERE a.player_id = 160000 AND b.player_id = 135748 AND a.mode = '2v2'
```

| sets | raydish_side_won |
|---|---|
| 5 | 2 |

**Verified:** yes

<a id="c4"></a>

## c4. CEO 2025

From 20261119T233544Z-002, turns 2-4.

### Turn 1: what did raydish get in autumn 2022

**Expected:** At the North America - Autumn Championship 2022, Raydish placed 5th in 1v1 (2022-09-25) and 13th in 2v2 (2022-09-18).

**Checks:** rows [["Autumn Championship 2022", 5], ["Autumn Championship 2022", 13]]; grounded and named (every turn)

**Query 1:** Raydish's results at the 2022 Autumn Championships

```sql
SELECT start_date, tournament_name, event_name, mode, placement FROM v_results
WHERE player_id = 160000 AND start_date LIKE '2022%' AND tournament_name LIKE '%Autumn Championship%'
ORDER BY start_time
```

| start_date | tournament_name | event_name | mode | placement |
|---|---|---|---|---|
| 2022-09-18 | North America - Autumn Championship 2022 | Brawlhalla Championship 2v2 | 2v2 | 13 |
| 2022-09-25 | North America - Autumn Championship 2022 | Brawlhalla Championship 1v1 | 1v1 | 5 |

### Turn 2: when was ceo 2025

**Expected:** CEO 2025's Brawlhalla events: the Doubles (2v2) began on 2025-06-13 and the Singles (1v1) on 2025-06-14. Saying CEO isn't a Brawlhalla event, without looking it up, is wrong.

**Checks:** rows [["CEO 2025", "2025-06-13"], ["CEO 2025", "2025-06-14"]]; says_any ["June 13", "June 14", "2025-06-13", "2025-06-14", "13 June", "14 June"]; grounded and named (every turn)

**Query 1:** CEO 2025's events

```sql
SELECT event_id, tournament_name, event_name, start_date, mode FROM v_events
WHERE tournament_name LIKE 'CEO 2025%' ORDER BY start_date
```

| event_id | tournament_name | event_name | start_date | mode |
|---|---|---|---|---|
| tournament/ceo-2025-6/event/brawlhalla-doubles | CEO 2025 | Brawlhalla Doubles | 2025-06-13 | 2v2 |
| tournament/ceo-2025-6/event/brawlhalla-singles | CEO 2025 | Brawlhalla Singles | 2025-06-14 | 1v1 |

### Turn 3: who got 2nd at ceo 2025

**Expected:** 2nd at CEO 2025: BBBalloonBoy in the Singles (1v1), and BBBalloonBoy and Raydish together in the Doubles (2v2).

**Checks:** rows [[[149305, "BBBalloonBoy"], 2], [[160000, "Raydish"], 2]]; says ["BBBalloonBoy"]; grounded and named (every turn)

**Query 1:** the 2nd places at CEO 2025

```sql
SELECT r.event_name, r.mode, r.player_id, p.name, r.placement FROM v_results r JOIN players p USING (player_id)
WHERE r.event_id IN (SELECT event_id FROM v_events WHERE tournament_name LIKE 'CEO 2025%') AND r.placement = 2
```

| event_name | mode | player_id | name | placement |
|---|---|---|---|---|
| Brawlhalla Doubles | 2v2 | 149305 | BBBalloonBoy | 2 |
| Brawlhalla Doubles | 2v2 | 160000 | Raydish | 2 |
| Brawlhalla Singles | 1v1 | 149305 | BBBalloonBoy | 2 |

**Verified:** yes

<a id="c5"></a>

## c5. the crew battles

From 20261119T233544Z-002, turns 8-10.

### Turn 1: do you know about the cb tournament in 2022

**Expected:** "cb" is crew battle: the 2022 Crew Battle Invitationals, one per region, crew battles counted as 1v1: South America (2022-03-18), Europe (2022-03-19) and North America (2022-03-20). The agent finds them without the user spelling "cb" out.

**Checks:** rows [["South America - Crew Battle Invitational"], ["Europe - Crew Battle Invitational"], ["North America - Crew Battle Invitational"]]; grounded and named (every turn)

**Query 1:** the 2022 Crew Battle Invitationals

```sql
SELECT event_id, tournament_name, event_name, start_date, format FROM v_events
WHERE tournament_name LIKE '%Crew Battle Invitational%' AND start_date LIKE '2022%' ORDER BY start_date
```

| event_id | tournament_name | event_name | start_date | format |
|---|---|---|---|---|
| tournament/south-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | South America - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-18 | crew_battle |
| tournament/europe-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | Europe - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-19 | crew_battle |
| tournament/north-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | North America - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-20 | crew_battle |

### Turn 2: i meant the crew battle tournament in 2022

**Expected:** The same three invitationals, if the first turn didn't find them; if it did, the same answer again.

**Checks:** rows [["South America - Crew Battle Invitational"], ["Europe - Crew Battle Invitational"], ["North America - Crew Battle Invitational"]]; grounded and named (every turn)

**Query 1:** the 2022 Crew Battle Invitationals

```sql
SELECT event_id, tournament_name, event_name, start_date, format FROM v_events
WHERE tournament_name LIKE '%Crew Battle Invitational%' AND start_date LIKE '2022%' ORDER BY start_date
```

| event_id | tournament_name | event_name | start_date | format |
|---|---|---|---|---|
| tournament/south-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | South America - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-18 | crew_battle |
| tournament/europe-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | Europe - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-19 | crew_battle |
| tournament/north-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3 | North America - Crew Battle Invitational | Brawlhalla Crew Battle 3v3 | 2022-03-20 | crew_battle |

### Turn 3: tell me about the north america one

**Expected:** The North America - Crew Battle Invitational (2022-03-20), each crew on one row: 1st Boomie, antireplay and capsar; 2nd Anon Alex, Phazon and Raydish; 3rd Cody Travis, Zinquer and experiencedoa. Every player named, none by ID.

**Checks:** rows [[[146606, "Boomie"], 1], [[158406, "antireplay"], 1], [[147569, "capsar"], 1]]; says ["Boomie", "antireplay", "capsar"]; grounded and named (every turn)

**Query 1:** the NA invitational's top 3 crews

```sql
SELECT r.placement, r.player_id, p.name FROM v_results r JOIN players p USING (player_id)
WHERE r.event_id = 'tournament/north-america-crew-battle-invitational/event/brawlhalla-crew-battle-3v3'
AND r.placement <= 3 ORDER BY r.placement, p.name
```

| placement | player_id | name |
|---|---|---|
| 1 | 146606 | Boomie |
| 1 | 158406 | antireplay |
| 1 | 147569 | capsar |
| 2 | 111756 | Anon Alex |
| 2 | 147522 | Phazon |
| 2 | 160000 | Raydish |
| 3 | 117179 | Cody Travis |
| 3 | 147592 | Zinquer |
| 3 | 118094 | experiencedoa |

**Verified:** yes

<a id="c6"></a>

## c6. Raydish and megD, then a stat card

From 20261119T233544Z-003, turns 3-4.

### Turn 1: whats raydish and megd's record

**Expected:** Raydish and megD are 2-2 in 4 1v1 sets (games 9-8 from Raydish's side), the sets as in c1. In 2v2, Raydish's teams won all 3 of their sets against megD's.

**Checks:** rows [[[160000, "Raydish"], [142100, "megD"], 4, 2]]; grounded and named (every turn)

**Query 1:** Raydish's 1v1 record against megD

```sql
SELECT player_id, opponent_id, matches, wins, losses, games_won, games_lost
FROM v_head_to_head_1v1 WHERE player_id = 160000 AND opponent_id = 142100
```

| player_id | opponent_id | matches | wins | losses | games_won | games_lost |
|---|---|---|---|---|---|---|
| 160000 | 142100 | 4 | 2 | 2 | 9 | 8 |

### Turn 2: raydish lifetime stat card

**Expected:** Raydish's official results: 98, 55 in 1v1 and 43 in 2v2; 6 wins, all 1v1; 22 medals (15 and 7); 43 top 8s (27 and 16); best 1st in 1v1 and 2nd in 2v2. The page's lifetime card comes from player_results.

**Checks:** calls ["player_results"]; players [160000]; rows_any [[[160000, "Raydish"], "1v1", 55], [[160000, "Raydish"], "1v1 and 2v2", 98]]; grounded and named (every turn)

**Query 1:** Raydish's results by mode: results, wins, medals, top 8s, best

```sql
SELECT player_id, mode, COUNT(*) AS results, SUM(placement = 1) AS wins, SUM(placement <= 3) AS medals,
       SUM(placement <= 8) AS top8s, MIN(placement) AS best
FROM v_results WHERE player_id = 160000 GROUP BY mode
```

| player_id | mode | results | wins | medals | top8s | best |
|---|---|---|---|---|---|---|
| 160000 | 1v1 | 55 | 6 | 15 | 27 | 1 |
| 160000 | 2v2 | 43 | 0 | 7 | 16 | 2 |

**Verified:** yes

<a id="c7"></a>

## c7. three standalone questions

From 20261119T233544Z-002, turns 11-13 (the first two are q38 and q06, word for word).

### Turn 1: rank the top 5 players by official 1v1 wins

**Expected:** As q38's verified answer in questions.toml.

**q38's verified answer:** 1. gdsandstorm, 30 (2 of them crew battles) 2. TigerBrawlhalla, 26 3. Zivai, 23 (1 crew battle) 4. Kylar Alice, 19 5. yüz, 14 (1 crew battle) Crew battles count as 1v1, though they're team results. Without them: gdsandstorm 28, TigerBrawlhalla 26, Zivai 22, Kylar Alice 19, then acno?, whoiskyna and yüz tied at 13.

**Checks:** check "q38"; grounded and named (every turn)

### Turn 2: Who has megd played with in 2v2 tournaments, and how did they place?

**Expected:** As q06's verified answer in questions.toml.

**q06's verified answer:** megD has had 17 partners at official 2v2 events. The most frequent: - Raydish: 20 events, best 2nd - hardymj: 4 events, best 9th - Winged_Shell: 3 events, best 17th - bestjava and buko pandan: 2 events each, best 5th - Walshy and Moni-: 2 events each, best 7th - JuicyDiaper: 2 events, best 25th and nine more with one event each: Snowy!! (7th), Anon Alex, Cody Travis and flowerVS (9th), Ultra and warmsink26 (13th), wubz (17th), iLLu and .kira (25th).

**Checks:** check "q06"; grounded and named (every turn)

### Turn 3: has megd won a tournament

**Expected:** Yes: two official events, both counted as 1v1, the Summer Championship - North America 2026 - 1v1 (2026-07-19) and the Eternal Sports Crew Battle Championship 2026 - North America (2026-08-30), a crew battle. No 2v2 wins.

**Checks:** rows [["Summer Championship - North America 2026"], ["Eternal Sports Crew Battle Championship 2026"]]; grounded and named (every turn)

**Query 1:** megD's official wins

```sql
SELECT player_id, start_date, tournament_name, mode, format FROM v_official_wins WHERE player_id = 142100
ORDER BY start_time
```

| player_id | start_date | tournament_name | mode | format |
|---|---|---|---|---|
| 142100 | 2026-07-19 | Summer Championship - North America 2026 - 1v1 | 1v1 | standard |
| 142100 | 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | 1v1 | crew_battle |

**Verified:** yes
