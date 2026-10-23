# Evaluation set v1: review

Made by `python eval/review_questions.py` from [`questions.toml`](questions.toml), which is the file to edit.

45 questions, with candidate answers computed from the frozen snapshot `data/db/eval/eval-v1.sqlite` (build 20261007T230135Z). Each question shows its candidate answer, the players and events its names were resolved to, and the queries behind the answer with their results.

**Accepted answers:** where a reasonable definition changes the answer, the question lists each acceptable answer with the assumption that produces it, the candidate answer's first. An answer gets credit only if it states its assumption.

**Tied to eval-v1:** every answer is computed on eval-v1. A question marked tied has an answer that Phase 2 (or Phase 3) will change even without new events.

**To verify:** check each candidate answer, and each accepted one, against what you know, or against start.gg, Challengermode or Liquipedia, then fill in `verified` in `questions.toml`: `yes`, or `no: ...` or `partly: ...` with what's right. Then re-run the script to update this page.

**Verified:** 45 of 45. **With accepted answers:** 15. **Tied to eval-v1:** 7.

| Category | What it covers | Questions |
|---|---|---|
| player_record | one player's results | 9 |
| event_result | one event's results | 11 |
| head_to_head | records between players | 4 |
| multi_step | comparisons, firsts, mosts and rankings | 11 |
| partial | the data answers part of it: what it shows, then what's missing | 4 |
| unanswerable | the data has nothing that answers it: what isn't available, and why | 6 |

| Id | Question | Category | Accepted answers | Tied to eval-v1 | Verified |
|---|---|---|---|---|---|
| [q01](#q01) | What was the last tournament Boomie entered? | player_record |  |  | yes |
| [q02](#q02) | How many majors has Raydish won? | player_record | 2 |  | yes |
| [q03](#q03) | Has Hexo ever placed top 8 in 1v1? | player_record |  |  | yes: technically correct: the only top 8 is at Brawlhalla Community Tournament #2, which is an official event |
| [q04](#q04) | What does Impala vs Balloonboy's history look like? | head_to_head |  |  | yes |
| [q05](#q05) | List the top 10 highest-earning players in Brawlhalla history. | partial |  | yes | partly: candidate list is right, but Boomie is missing because he has no earnings figure; the answer must name him in what's missing |
| [q06](#q06) | Who has megd played with in 2v2 tournaments, and how did they place? | player_record |  |  | yes |
| [q07](#q07) | How many medals does Balloonboy have? | player_record | 3 |  | yes |
| [q08](#q08) | Who has the best record against marckiemoo? | head_to_head | 3 |  | yes: the question gives no minimum; the agent must state the threshold it used, per the accept list |
| [q09](#q09) | What tournament did sandstorm make the most money from? | unanswerable |  | yes | yes: unanswerable as written |
| [q10](#q10) | Give me the bracket link of BCX 2022. | event_result |  |  | yes |
| [q11](#q11) | What is Raydish's most dominant tournament win? | multi_step | 3 |  | yes |
| [q12](#q12) | What was flowers' first top 8? | multi_step | 2 |  | yes |
| [q13](#q13) | who won winters 2023 na 1v1 | event_result |  |  | yes |
| [q14](#q14) | Who made top 8 at Trial of Laufey NA? | event_result |  |  | yes |
| [q15](#q15) | did godly win eu summers 2026 | event_result |  |  | yes |
| [q16](#q16) | who won sa 2v2 springs 2026 | event_result |  |  | yes |
| [q17](#q17) | top 8 at bcx 2025 1v1? | event_result |  |  | yes |
| [q18](#q18) | who won 2v2 at autumns 2023 NA? | event_result |  |  | yes |
| [q19](#q19) | Who won the Midseason Championship 2026? | event_result |  |  | yes |
| [q20](#q20) | what was the score of the 1v1 grand final at dreamhack valencia 2023 | multi_step |  |  | yes |
| [q21](#q21) | how many official events has baloonboy won? | player_record |  |  | yes |
| [q22](#q22) | did markiemoo ever win worlds | player_record | 2 |  | yes |
| [q23](#q23) | kingdom \| godly vs impala head to head | head_to_head | 2 |  | yes |
| [q24](#q24) | who won msi 1v1 | event_result | 2 |  | yes |
| [q25](#q25) | how many official tournaments has RAYDISH won | player_record | 2 |  | yes |
| [q26](#q26) | How many times has M30W \| BalloonBoy finished top 3 at an official event? | player_record | 3 |  | yes |
| [q27](#q27) | whats bbballoonboy's 1v1 record vs impala | head_to_head |  |  | yes |
| [q28](#q28) | who won worlds 2019 1v1 | event_result |  |  | yes |
| [q29](#q29) | Who won the 1v1 at DreamHack Atlanta 2019? | event_result |  |  | yes |
| [q30](#q30) | who won ceo dreamland 2020 | unanswerable |  |  | yes |
| [q31](#q31) | Who won SEA League Week 1/4? | partial |  |  | partly: can't confirm the real winner; kept as a data-quality test, since the expected answer is about unreliable standings |
| [q32](#q32) | how much prize money did vem win at max mode 2025 | unanswerable |  | yes | yes: unanswerable as written |
| [q33](#q33) | how much money has boomie made from brawlhalla | partial |  | yes | yes: not answerable with the current database |
| [q34](#q34) | Who won the 2016 Brawlhalla World Championship? | unanswerable |  |  | yes: unanswerable as written |
| [q35](#q35) | what legend does godly main | unanswerable |  | yes | yes: unanswerable as written |
| [q36](#q36) | How many community tournaments has raydish won? | unanswerable |  |  | yes: unanswerable as written |
| [q37](#q37) | Who has won the most official tournaments? | multi_step | 2 |  | yes |
| [q38](#q38) | rank the top 5 players by official 1v1 wins | multi_step | 2 |  | yes: Boomie's 12 official 1v1 wins (tied 8th) correctly keep him out of the top 5 |
| [q39](#q39) | who has more medals, boomie or sandstorm? | multi_step | 2 |  | yes |
| [q40](#q40) | who has raydish lost to the most in 1v1 | multi_step |  |  | yes |
| [q41](#q41) | Who has won the most 1v1 world championships? | multi_step | 2 |  | yes |
| [q42](#q42) | what was the biggest official brawlhalla tournament ever? | multi_step | 5 | yes | yes: technically correct |
| [q43](#q43) | what was megd's first major win? | multi_step |  |  | yes |
| [q44](#q44) | How many times did Ahmet finish second to Godly in 2026? | multi_step |  |  | partly: probably correct, not yet confirmed |
| [q45](#q45) | who has earned more money, raydish or impala? | partial |  | yes | yes: not answerable because Impala's earnings are unknown |

<a id="q01"></a>

## q01. What was the last tournament Boomie entered?

player_record · target question 1 · shared name · last event entered

- **Boomie** → Boomie (146606, 147 results), by the display name; 6 other players with this name, with at most 9 results

**Candidate answer:**

Boomie last entered an official event on 2024-03-10: the Winter Doubles Championship - North America (2v2), placing 2nd. Boomie's last 1v1 event was the Brawlhalla World Championship Expo 2023 (BCX 2023, 2023-11-03), 49th.

**Notes:** The newest event is 2v2, not a side format, so the newest 1v1 event is extra: answer rule 2 asks for it only after a side format.

**Query 1:** the newest official event entered, side formats included

```sql
SELECT start_date, tournament_name, event_name, mode, format, placement
FROM v_entries WHERE player_id = 146606
ORDER BY start_time DESC LIMIT 1
```

| start_date | tournament_name | event_name | mode | format | placement |
|---|---|---|---|---|---|
| 2024-03-10 | Winter Doubles Championship - North America | Brawlhalla Championship 2v2 | 2v2 | standard | 2 |

**Query 2:** the newest 1v1 event

```sql
SELECT start_date, tournament_name, event_name, mode, placement
FROM v_entries WHERE player_id = 146606 AND mode = '1v1'
ORDER BY start_time DESC LIMIT 1
```

| start_date | tournament_name | event_name | mode | placement |
|---|---|---|---|---|
| 2023-11-03 | Brawlhalla World Championship Expo 2023 | 1v1 | 1v1 | 49 |

**Verified:** yes

<a id="q02"></a>

## q02. How many majors has Raydish won?

player_record · target question 2 · majors means official events · crew battles count as 1v1

- **Raydish** → Raydish (160000, 98 results), by the display name

**Candidate answer:**

6 official event wins, all counted as 1v1:
- North America - Summer Championship 2022 (2022-07-31)
- North America - Winter Championship 2023 (2023-02-05)
- Trial of Ymir - North America (2024-02-18)
- Trial of Heimdall - North America (NSIG) (2024-07-14)
- Trial of Laufey - North America (Moose Wars) (2024-08-25)
- Eternal Sports Crew Battle Championship 2026 - North America (2026-08-30), a crew battle: a team result, counted as 1v1

No 2v2 wins.

**Accepted answers** (each gets credit only with its assumption stated):

- *majors are official events, and a crew battle counts as 1v1 (the decided rules):* 6: five 1v1 wins and the 2026 NA Crew Battle Championship, a team result
- *individual titles only, the crew battle left out as a team event:* 5: the NA Summer Championship 2022, the NA Winter Championship 2023 and the Trials of Ymir, Heimdall and Laufey (2024)

**Notes:** "Majors" are official events (tiers are deferred), and the answer should say "official events". A narrower meaning of "major", only the biggest events, can't be computed from the data until tiers exist.

**Query 1:** official wins

```sql
SELECT start_date, tournament_name, event_name, mode, format
FROM v_official_wins WHERE player_id = 160000
ORDER BY start_time
```

| start_date | tournament_name | event_name | mode | format |
|---|---|---|---|---|
| 2022-07-31 | North America - Summer Championship 2022 | Brawlhalla Championship 1v1 | 1v1 | standard |
| 2023-02-05 | North America - Winter Championship 2023 | Brawlhalla Championship 1v1 | 1v1 | standard |
| 2024-02-18 | Trial of Ymir - North America | Brawlhalla Championship 1v1 | 1v1 | standard |
| 2024-07-14 | Trial of Heimdall - North America (NSIG) | Brawlhalla Championship 1v1 | 1v1 | standard |
| 2024-08-25 | Trial of Laufey - North America (Moose Wars) | Brawlhalla 1v1 | 1v1 | standard |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | NULL | 1v1 | crew_battle |

**Verified:** yes

<a id="q03"></a>

## q03. Has Hexo ever placed top 8 in 1v1?

player_record · target question 3 · nickname · official events only

- **Hexo** → Hexoo (169084, 36 results), by a nickname

**Candidate answer:**

Yes, once at an official event: Hexoo placed 5th at Brawlhalla Community Tournament #2 (2025-09-28). Community events aren't in the data, so top 8s there aren't counted.

**Notes:** "Hexo" is a curated nickname for Hexoo. The API survey's "8 times" counted community events. Brawlhalla Community Tournament #2 is an official event despite its name.

**Query 1:** 1v1 top 8s at official events

```sql
SELECT start_date, tournament_name, event_name, placement
FROM v_results WHERE player_id = 169084 AND mode = '1v1' AND placement <= 8
ORDER BY start_time
```

| start_date | tournament_name | event_name | placement |
|---|---|---|---|
| 2025-09-28 | Brawlhalla Community Tournament #2 | NULL | 5 |

**Verified:** yes: technically correct: the only top 8 is at Brawlhalla Community Tournament #2, which is an official event

<a id="q04"></a>

## q04. What does Impala vs Balloonboy's history look like?

head_to_head · target question 4 · former name · shared name · no-contests left out

- **Impala** → Impala (168635, 48 results), by the display name; 1 other player with this name, with at most 1 result
- **Balloonboy** → BBBalloonBoy (149305, 79 results), by a former name

**Candidate answer:**

Impala leads BBBalloonBoy 2-1 in 1v1 sets at official events (8-4 in games), DQs and forfeits left out:
- Trial of Frigg - North America (Moose Wars), 2024-03-17: Impala won 3-0
- Trial of Skuld - North America, 2024-08-04: Impala won 3-1
- Brawlhalla World Championship Expo 2024 (BCX 2024), 2024-11-15: BBBalloonBoy won 3-2

They never met in 2v2. Both placed at 23 of the same official 1v1 events and 3 of the same 2v2 events.

**Notes:** "Balloonboy" is a former name of BBBalloonBoy (LGN | BalloonBoy). Another record named Impala has one result. q27 asks the same from BBBalloonBoy's side.

**Query 1:** the 1v1 record, from Impala's side

```sql
SELECT wins, losses, matches, games_won, games_lost, unscored_matches
FROM v_head_to_head_1v1 WHERE player_id = 168635 AND opponent_id = 149305
```

| wins | losses | matches | games_won | games_lost | unscored_matches |
|---|---|---|---|---|---|
| 2 | 1 | 3 | 8 | 4 | 0 |

**Query 2:** the sets, from Impala's side

```sql
SELECT a.start_date, v.tournament_name, a.games_won, a.games_lost
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
JOIN v_events v ON v.event_id = a.event_id
WHERE a.player_id = 168635 AND b.player_id = 149305 AND a.mode = '1v1' AND a.side_players = 1
ORDER BY a.start_time
```

| start_date | tournament_name | games_won | games_lost |
|---|---|---|---|
| 2024-03-17 | Trial of Frigg - North America (Moose Wars) | 3 | 0 |
| 2024-08-04 | Trial of Skuld - North America | 3 | 1 |
| 2024-11-15 | Brawlhalla World Championship Expo 2024 | 2 | 3 |

**Query 3:** 2v2 meetings

```sql
SELECT COUNT(*) AS meetings FROM v_head_to_head_2v2
WHERE player_id = 168635 AND 149305 IN (opponent1_id, opponent2_id)
```

| meetings |
|---|
| 0 |

**Query 4:** official events both placed at, by mode

```sql
SELECT a.mode, COUNT(*) AS events
FROM v_results a JOIN v_results b ON b.event_id = a.event_id
WHERE a.player_id = 168635 AND b.player_id = 149305
GROUP BY a.mode ORDER BY a.mode
```

| mode | events |
|---|---|
| 1v1 | 23 |
| 2v2 | 3 |

**Verified:** yes

<a id="q05"></a>

## q05. List the top 10 highest-earning players in Brawlhalla history.

partial · target question 5 · missing isn't zero · name the source


**Candidate answer** (what the data shows):

The top 10 among the 4,981 players with a career earnings figure (Stats API, as of 2026-10-02):
1. gdsandstorm, $258,984.17
2. Zivai, $214,458.33
3. acno?, $189,215.00
4. whoiskyna, $161,110.00
5. SiB | Wess, $131,481.67
6. yüz, $131,421.67
7. Blaze, $120,207.83
8. loreszz, $102,600.00
9. lFiend, $94,261.67
10. Raydish, $83,825.00

**What's missing** (the rest of the expected answer): figures for players without a PR ranking: the Stats API has none for them, so a top earner such as Boomie may be missing from the list

**Tied to eval-v1:** Phase 2 adds the Esports Earnings snapshot (2026-10-04) as the fallback for players without a Stats API figure, so unranked earners join the list: Esports Earnings has Boomie at #2 with $210,282.67.

**Query 1:** the 10 highest career figures

```sql
SELECT name, earnings_usd, source, as_of
FROM v_career_earnings ORDER BY earnings_usd DESC LIMIT 10
```

| name | earnings_usd | source | as_of |
|---|---|---|---|
| gdsandstorm | 258984.17 | Stats API | 2026-10-02 |
| Zivai | 214458.33 | Stats API | 2026-10-02 |
| acno? | 189215.0 | Stats API | 2026-10-02 |
| whoiskyna | 161110.0 | Stats API | 2026-10-02 |
| SiB \| Wess | 131481.67 | Stats API | 2026-10-02 |
| yüz | 131421.67 | Stats API | 2026-10-02 |
| Blaze | 120207.83 | Stats API | 2026-10-02 |
| loreszz | 102600.0 | Stats API | 2026-10-02 |
| lFiend | 94261.67 | Stats API | 2026-10-02 |
| Raydish | 83825.0 | Stats API | 2026-10-02 |

**Query 2:** how many players have a figure, and where from

```sql
SELECT source, COUNT(*) AS players, MIN(as_of) AS as_of
FROM v_career_earnings GROUP BY source
```

| source | players | as_of |
|---|---|---|
| Stats API | 4981 | 2026-10-02 |

**Verified:** partly: candidate list is right, but Boomie is missing because he has no earnings figure; the answer must name him in what's missing

<a id="q06"></a>

## q06. Who has megd played with in 2v2 tournaments, and how did they place?

player_record · target question 6 · case · merged records

- **megd** → megD (142100, 104 results), by the display name

**Candidate answer:**

megD has had 17 partners at official 2v2 events. The most frequent:
- Raydish: 20 events, best 2nd
- hardymj: 4 events, best 9th
- Winged_Shell: 3 events, best 17th
- bestjava and buko pandan: 2 events each, best 5th
- Walshy and Moni-: 2 events each, best 7th
- JuicyDiaper: 2 events, best 25th

and nine more with one event each: Snowy!! (7th), Anon Alex, Cody Travis and flowerVS (9th), Ultra and warmsink26 (13th), wubz (17th), iLLu and .kira (25th).

**Notes:** hardymj's two records (a start.gg one and a Challengermode one) are one person through player_merges, so hardymj counts once. megD never appears as their own partner.

**Query 1:** partners at official 2v2 events, with events together and best placement

```sql
SELECT p.name AS partner, t.partner_id, COUNT(*) AS events, MIN(t.placement) AS best_placement
FROM v_team_results t JOIN players p ON p.player_id = t.partner_id
WHERE t.player_id = 142100
GROUP BY t.partner_id ORDER BY events DESC, best_placement, partner
```

| partner | partner_id | events | best_placement |
|---|---|---|---|
| Raydish | 160000 | 20 | 2 |
| hardymj | 145900 | 4 | 9 |
| Winged_Shell | 143709 | 3 | 17 |
| bestjava | 145913 | 2 | 5 |
| buko pandan | 169120 | 2 | 5 |
| Moni- | 152572 | 2 | 7 |
| Walshy | 147620 | 2 | 7 |
| JuicyDiaper | 101340 | 2 | 25 |
| Snowy!! | 145915 | 1 | 7 |
| Anon Alex | 111756 | 1 | 9 |
| Cody Travis | 117179 | 1 | 9 |
| flowerVS | 169119 | 1 | 9 |
| Ultra | 111613 | 1 | 13 |
| warmsink26 | 162683 | 1 | 13 |
| wubz | 158492 | 1 | 17 |
| .kira | 162681 | 1 | 25 |
| iLLu | 113714 | 1 | 25 |

**Verified:** yes

<a id="q07"></a>

## q07. How many medals does Balloonboy have?

player_record · target question 7 · former name · medal = top 3 · crew battles count as 1v1 · side formats

- **Balloonboy** → BBBalloonBoy (149305, 79 results), by a former name

**Candidate answer:**

27 medals (top-3 placements at official events) for BBBalloonBoy:
- 1v1: 2 gold, 8 silver, 5 bronze (15), including a crew battle silver, a team result
- 2v2: 5 gold, 3 silver, 4 bronze (12)

Silvers in Brawlball and Triples (both 2026) don't count: those formats count toward neither mode.

**Accepted answers** (each gets credit only with its assumption stated):

- *top-3 placements at official 1v1 and 2v2 events, a crew battle counting as 1v1 (the decided rules):* 27: 15 in 1v1 (2 gold, 8 silver, 5 bronze, a crew battle silver included) and 12 in 2v2 (5, 3 and 4)
- *individual results only, the crew battle silver left out as a team result:* 26: 14 in 1v1 (2 gold, 7 silver, 5 bronze) and 12 in 2v2
- *every official event, the side formats (Brawlball, Triples) included:* 29: the 27, plus silvers at the 2026 NA Brawlball and Triples Championships

**Query 1:** medals by mode

```sql
SELECT mode, gold, silver, bronze, medals
FROM v_player_medals WHERE player_id = 149305 ORDER BY mode
```

| mode | gold | silver | bronze | medals |
|---|---|---|---|---|
| 1v1 | 2 | 8 | 5 | 15 |
| 2v2 | 5 | 3 | 4 | 12 |

**Query 2:** top-3 placements in side formats and crew battles

```sql
SELECT start_date, tournament_name, format, mode, placement
FROM v_entries WHERE player_id = 149305 AND format <> 'standard' AND placement <= 3
ORDER BY start_time
```

| start_date | tournament_name | format | mode | placement |
|---|---|---|---|---|
| 2026-02-01 | Eternal Sports Brawlball Championship - North America 2026 | brawlball | NULL | 2 |
| 2026-03-29 | Eternal Sports Triples Championship 2026 - North America | triples | NULL | 2 |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | crew_battle | 1v1 | 2 |

**Verified:** yes

<a id="q08"></a>

## q08. Who has the best record against marckiemoo?

head_to_head · target question 8 · nickname · name the metric · ranking · no-contests left out

- **marckiemoo** → Marckiem00 (146052, 47 results), by a nickname

**Candidate answer:**

By 1v1 set win rate against Marckiem00 at official events, among players with at least 5 sets against them (DQs and forfeits left out):
1. V3M_T4NQUIL0: 3-2 (60%)
2. Raydish: 6-7 (46%)
3. gdsandstorm: 4-7 (36%)

V3M_T4NQUIL0 is the only one of them with a winning record.

**Accepted answers** (each gets credit only with its assumption stated):

- *set win rate, at least 5 sets (the default; game win rate with the same minimum agrees):* V3M_T4NQUIL0, 3-2 (60%); then Raydish 6-7 and gdsandstorm 4-7
- *set win rate, at least 3 or 4 sets:* Ahmet_, 3-1 (75%)
- *net sets won (wins minus losses):* Ahmet_ (3-1) and Snowy!! (2-0), tied at +2

**Notes:** BBBalloonBoy has played Marckiem00 the most (4-13). Raydish has beaten Marckiem00 the most (6-7), but that isn't the best record by win rate or by net wins.

**Query 1:** records against Marckiem00, at least 5 sets, best win rate first

```sql
SELECT p.name, h.player_id, h.wins, h.losses, h.matches,
       ROUND(100.0 * h.wins / h.matches, 1) AS win_pct
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.player_id
WHERE h.opponent_id = 146052 AND h.matches >= 5
ORDER BY 1.0 * h.wins / h.matches DESC, h.matches DESC LIMIT 5
```

| name | player_id | wins | losses | matches | win_pct |
|---|---|---|---|---|---|
| V3M_T4NQUIL0 | 71736 | 3 | 2 | 5 | 60.0 |
| Raydish | 160000 | 6 | 7 | 13 | 46.2 |
| gdsandstorm | 74433 | 4 | 7 | 11 | 36.4 |
| Mounir | 79853 | 2 | 5 | 7 | 28.6 |
| yüz | 73254 | 3 | 9 | 12 | 25.0 |

**Query 2:** set win rate, at least 3 sets

```sql
SELECT p.name, h.wins, h.losses, h.matches
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.player_id
WHERE h.opponent_id = 146052 AND h.matches >= 3
ORDER BY 1.0 * h.wins / h.matches DESC, h.matches DESC LIMIT 3
```

| name | wins | losses | matches |
|---|---|---|---|
| Ahmet_ | 3 | 1 | 4 |
| Dragon! | 2 | 1 | 3 |
| V3M_T4NQUIL0 | 3 | 2 | 5 |

**Query 3:** net sets won

```sql
SELECT p.name, h.wins, h.losses, h.wins - h.losses AS net
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.player_id
WHERE h.opponent_id = 146052
ORDER BY net DESC, h.wins DESC LIMIT 4
```

| name | wins | losses | net |
|---|---|---|---|
| Ahmet_ | 3 | 1 | 2 |
| Snowy!! | 2 | 0 | 2 |
| V3M_T4NQUIL0 | 3 | 2 | 1 |
| Dragon! | 2 | 1 | 1 |

**Verified:** yes: the question gives no minimum; the agent must state the threshold it used, per the accept list

<a id="q09"></a>

## q09. What tournament did sandstorm make the most money from?

unanswerable · target question 9 · nickname · no per-tournament prize data · missing isn't zero

- **sandstorm** → gdsandstorm (74433, 133 results), by a nickname; 8 other players with this name, with at most 6 results

**Candidate answer:**

The data can't say: the database has no prize money per tournament, only career totals. gdsandstorm's career earnings are $258,984.17 (Stats API, as of 2026-10-02), but not which tournaments they came from. Results (such as gdsandstorm's 48 official wins) don't tell how much each paid.

**What's missing:** prize money per tournament: the database has only career totals

**Tied to eval-v1:** Phase 2 adds per-tournament payouts, so the question gets an answer from the events with payout data, with the others named as not available.

**Notes:** "sandstorm" is a curated nickname for gdsandstorm; eight other records have that name or had it as a former name.

**Query 1:** gdsandstorm's career figure

```sql
SELECT name, earnings_usd, source, as_of FROM v_career_earnings WHERE player_id = 74433
```

| name | earnings_usd | source | as_of |
|---|---|---|---|
| gdsandstorm | 258984.17 | Stats API | 2026-10-02 |

**Query 2:** tables and views about money: career figures only, nothing per tournament

```sql
SELECT type, name FROM sqlite_master
WHERE type IN ('table', 'view') AND (name LIKE '%prize%' OR name LIKE '%payout%' OR name LIKE '%earning%')
ORDER BY name
```

| type | name |
|---|---|
| table | player_earnings |
| view | v_career_earnings |

**Verified:** yes: unanswerable as written

<a id="q10"></a>

## q10. Give me the bracket link of BCX 2022.

event_result · target question 10 · event alias

- **BCX 2022** → Brawlhalla World Championship Expo 2022 / 1v1 (2022-11-04); Brawlhalla World Championship Expo 2022 / 2v2 (2022-11-04), by event alias

**Candidate answer:**

BCX 2022 is the Brawlhalla World Championship Expo 2022 (2022-11-04), with two events:
- 1v1: https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/1v1/brackets
- 2v2: https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/2v2/brackets

**Query 1:** the events the alias names, with their links

```sql
SELECT v.tournament_name, v.event_name, v.start_date, v.bracket_url
FROM event_aliases a JOIN v_events v USING (event_id)
WHERE a.alias = 'bcx 2022' ORDER BY v.bracket_url
```

| tournament_name | event_name | start_date | bracket_url |
|---|---|---|---|
| Brawlhalla World Championship Expo 2022 | 1v1 | 2022-11-04 | https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/1v1/brackets |
| Brawlhalla World Championship Expo 2022 | 2v2 | 2022-11-04 | https://www.start.gg/tournament/brawlhalla-world-championship-expo-2022/event/2v2/brackets |

**Verified:** yes

<a id="q11"></a>

## q11. What is Raydish's most dominant tournament win?

multi_step · target question 11 · ranking · name the metric · crew battles left out of dominance

- **Raydish** → Raydish (160000, 98 results), by the display name

**Candidate answer:**

By games lost across the run (fewest first, then fewest sets dropped, then most games won): the Trial of Laufey - North America (Moose Wars) (2024-08-25), where Raydish won all 9 sets, 25 games to 2: two 2-0s, then 3-0, 3-1, 3-0, 3-0, 3-0 (Bunny meow), 3-0 and 3-1 (both against BBBalloonBoy).

The other wins: Trial of Heimdall (10 sets, 27-7 in games), NA Winter Championship 2023 (10 sets, 25-7), Trial of Ymir (10 sets, 27-8), NA Summer Championship 2022 (15 sets, one dropped, 37-9). The 2026 NA Crew Battle Championship win is left out: its sets are crew against crew, so not comparable.

**Accepted answers** (each gets credit only with its assumption stated):

- *fewest games lost, then fewest sets dropped, then most games won (the decided metric); the highest game win rate and the fewest games lost per set agree:* the Trial of Laufey - North America (2024-08-25): 9-0 in sets, 25-2 in games
- *largest game differential (games won minus games lost):* the NA Summer Championship 2022: +28 (37-9 in games over 15 sets, one dropped); the Trial of Laufey is +23
- *most sets won without dropping one:* a three-way tie at 10-0: the Trial of Heimdall (27-7 in games), the Trial of Ymir (27-8) and the NA Winter Championship 2023 (25-7)

**Query 1:** official wins ranked by dominance, crew battles left out

```sql
SELECT tournament_name, start_date, sets_played, sets_dropped, games_won, games_lost, unscored_sets, no_contests
FROM v_win_runs
WHERE player_id = 160000 AND is_crew_battle = 0 AND sets_played > 0
ORDER BY unscored_sets > 0, games_lost, sets_dropped, games_won DESC
```

| tournament_name | start_date | sets_played | sets_dropped | games_won | games_lost | unscored_sets | no_contests |
|---|---|---|---|---|---|---|---|
| Trial of Laufey - North America (Moose Wars) | 2024-08-25 | 9 | 0 | 25 | 2 | 0 | 0 |
| Trial of Heimdall - North America (NSIG) | 2024-07-14 | 10 | 0 | 27 | 7 | 0 | 0 |
| North America - Winter Championship 2023 | 2023-02-05 | 10 | 0 | 25 | 7 | 0 | 0 |
| Trial of Ymir - North America | 2024-02-18 | 10 | 0 | 27 | 8 | 0 | 0 |
| North America - Summer Championship 2022 | 2022-07-31 | 15 | 1 | 37 | 9 | 0 | 0 |

**Query 2:** the top run's sets

```sql
SELECT m.start_time, p.name AS opponent, m.games_won, m.games_lost
FROM v_match_results m
JOIN v_match_results o ON o.match_id = m.match_id AND o.side <> m.side
JOIN players p ON p.player_id = o.player_id
WHERE m.player_id = 160000
  AND m.competition_key = 'tournament/trial-of-laufey-north-america-moose-wars/event/brawlhalla-1v1'
ORDER BY m.start_time
```

| start_time | opponent | games_won | games_lost |
|---|---|---|---|
| 1724602982 | S1MBV | 2 | 0 |
| 1724603647 | Pikadagod | 2 | 0 |
| 1724604928 | Waelpro | 3 | 0 |
| 1724606133 | SweatyMeat | 3 | 1 |
| 1724607873 | Udeaghac | 3 | 0 |
| 1724619678 | Shade 王 | 3 | 0 |
| 1724623024 | Bunny meow | 3 | 0 |
| 1724629288 | BBBalloonBoy | 3 | 0 |
| 1724633555 | BBBalloonBoy | 3 | 1 |

**Query 3:** crew battle wins, left out

```sql
SELECT tournament_name, start_date FROM v_win_runs WHERE player_id = 160000 AND is_crew_battle = 1
```

| tournament_name | start_date |
|---|---|
| Eternal Sports Crew Battle Championship 2026 - North America | 2026-08-30 |

**Query 4:** the other metrics, per run

```sql
SELECT tournament_name, sets_played - sets_dropped AS sets_won, sets_dropped,
       ROUND(100.0 * games_won / (games_won + games_lost), 1) AS game_win_pct,
       games_won - games_lost AS game_differential
FROM v_win_runs
WHERE player_id = 160000 AND is_crew_battle = 0 AND sets_played > 0
ORDER BY game_differential DESC
```

| tournament_name | sets_won | sets_dropped | game_win_pct | game_differential |
|---|---|---|---|---|
| North America - Summer Championship 2022 | 14 | 1 | 80.4 | 28 |
| Trial of Laufey - North America (Moose Wars) | 9 | 0 | 92.6 | 23 |
| Trial of Heimdall - North America (NSIG) | 10 | 0 | 79.4 | 20 |
| Trial of Ymir - North America | 10 | 0 | 77.1 | 19 |
| North America - Winter Championship 2023 | 10 | 0 | 78.1 | 18 |

**Verified:** yes

<a id="q12"></a>

## q12. What was flowers' first top 8?

multi_step · target question 12 · nickname · shared name · first

- **flowers** → flowerVS (169119, 63 results), by a nickname; 1 other player with this name, with at most 3 results

**Candidate answer:**

flowerVS's first 1v1 top 8 at an official event was 7th at the Brawlhalla World Championship Expo 2024 (BCX 2024, 2024-11-15). An earlier top 8 came in 2v2: 7th at the Summer Doubles Championship - North America (2024-07-21).

"flowers" is taken as flowerVS; another player, Flowers (156897), has that display name.

**Accepted answers** (each gets credit only with its assumption stated):

- *the first top 8 in 1v1, with an earlier 2v2 one mentioned (the decided rule):* 7th at BCX 2024 (2024-11-15); earlier, in 2v2, 7th at the Summer Doubles Championship - North America (2024-07-21)
- *the first top 8 in either mode:* 7th in 2v2 at the Summer Doubles Championship - North America (2024-07-21)

**Notes:** "flowers'" means "flower's" (decided 2026-10-04): "flower" and "flowers" are curated nicknames for flowerVS. The schema proposal's rule (§8) is the first 1v1 top 8, with the 2v2 one mentioned if it came earlier.

**Query 1:** the first top 8 in 1v1

```sql
SELECT mode, start_date, tournament_name, event_name, placement
FROM v_results WHERE player_id = 169119 AND mode = '1v1' AND placement <= 8
ORDER BY start_time LIMIT 1
```

| mode | start_date | tournament_name | event_name | placement |
|---|---|---|---|---|
| 1v1 | 2024-11-15 | Brawlhalla World Championship Expo 2024 | 1v1 | 7 |

**Query 2:** the first top 8 in 2v2

```sql
SELECT mode, start_date, tournament_name, event_name, placement
FROM v_results WHERE player_id = 169119 AND mode = '2v2' AND placement <= 8
ORDER BY start_time LIMIT 1
```

| mode | start_date | tournament_name | event_name | placement |
|---|---|---|---|---|
| 2v2 | 2024-07-21 | Summer Doubles Championship - North America | Brawlhalla Championship 2v2 | 7 |

**Verified:** yes

<a id="q13"></a>

## q13. who won winters 2023 na 1v1

event_result · known event · event term

- **winters 2023 na 1v1** → North America - Winter Championship 2023 / Brawlhalla Championship 1v1 (2023-02-05)

**Candidate answer:**

Raydish won the North America - Winter Championship 2023 1v1 (2023-02-05); STING RAY was 2nd.

**Notes:** "winters" means the seasonal Winter Championship (event_terms), not the Winter Royale.

**Query 1:** 1st and 2nd

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'tournament/north-america-winter-championship-2023/event/brawlhalla-championship-1v1'
  AND r.placement <= 2
ORDER BY r.placement
```

| placement | name |
|---|---|
| 1 | Raydish |
| 2 | STING RAY |

**Verified:** yes

<a id="q14"></a>

## q14. Who made top 8 at Trial of Laufey NA?

event_result · known event · event term · tied placements

- **Trial of Laufey NA** → Trial of Laufey - North America (Moose Wars) / Brawlhalla 1v1 (2024-08-25)

**Candidate answer:**

Trial of Laufey - North America (Moose Wars), 1v1, 2024-08-25:
- 1st: Raydish
- 2nd: BBBalloonBoy
- 3rd: Marckiem00
- 4th: gdsandstorm
- 5th: Bunny meow and wrenchd
- 7th: STING RAY and antireplay

**Notes:** Double elimination: 5th and 7th are shared.

**Query 1:** the top 8

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'tournament/trial-of-laufey-north-america-moose-wars/event/brawlhalla-1v1'
  AND r.placement <= 8
ORDER BY r.placement, p.name
```

| placement | name |
|---|---|
| 1 | Raydish |
| 2 | BBBalloonBoy |
| 3 | Marckiem00 |
| 4 | gdsandstorm |
| 5 | Bunny meow |
| 5 | wrenchd |
| 7 | STING RAY |
| 7 | antireplay |

**Verified:** yes

<a id="q15"></a>

## q15. did godly win eu summers 2026

event_result · known event · former name · shared name · event term · both modes

- **godly** → Zivai (147982, 74 results), by a former name; 3 other players with this name, with at most 5 results
- **eu summers 2026** → Summer Championship - Europe 2026 - 1v1 (2026-07-18); Summer Championship - Europe 2026 - 2v2 (2026-07-25)

**Candidate answer:**

Yes, both events. Zivai (formerly Kingdom | Godly) won the Summer Championship - Europe 2026 - 1v1 (2026-07-18), ahead of Ahmet_, and the 2v2 (2026-07-25) with bamya, ahead of acno? and Blaze.

**Notes:** "Godly" is a former name of Zivai; three other records are named Godly, with 5 results or fewer. The known event is the 1v1; the 2v2 is the same tournament's other event.

**Query 1:** 1st and 2nd in both events

```sql
SELECT v.tournament_name, v.start_date, r.placement, GROUP_CONCAT(p.name, ' / ') AS players
FROM v_results r
JOIN players p ON p.player_id = r.player_id
JOIN v_events v ON v.event_id = r.event_id
WHERE r.event_id IN ('44268709-24b7-405c-6d14-08dea8b61f65', 'eb136372-9608-404d-e246-08deac38d3d7')
  AND r.placement <= 2
GROUP BY r.event_id, r.placement, COALESCE(r.team_id, r.player_id)
ORDER BY v.start_time, r.placement
```

| tournament_name | start_date | placement | players |
|---|---|---|---|
| Summer Championship - Europe 2026 - 1v1 | 2026-07-18 | 1 | Zivai |
| Summer Championship - Europe 2026 - 1v1 | 2026-07-18 | 2 | Ahmet_ |
| Summer Championship - Europe 2026 - 2v2 | 2026-07-25 | 1 | Zivai / bamya |
| Summer Championship - Europe 2026 - 2v2 | 2026-07-25 | 2 | acno? / Blaze |

**Verified:** yes

<a id="q16"></a>

## q16. who won sa 2v2 springs 2026

event_result · known event · event term · 2v2

- **sa 2v2 springs 2026** → Spring Championship - South America 2026 - 2v2 (2026-05-02)

**Candidate answer:**

SiB | Wess and V3M_T4NQUIL0 (vem) won the Spring Championship - South America 2026 - 2v2 (2026-05-02), ahead of loreszz and whoiskyna.

**Query 1:** 1st and 2nd

```sql
SELECT r.placement, GROUP_CONCAT(p.name, ' / ') AS team
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = '9ea32cbc-e2b0-4039-d80c-08de6a223b1e' AND r.placement <= 2
GROUP BY r.placement, r.team_id
ORDER BY r.placement
```

| placement | team |
|---|---|
| 1 | SiB \| Wess / V3M_T4NQUIL0 |
| 2 | loreszz / whoiskyna |

**Verified:** yes

<a id="q17"></a>

## q17. top 8 at bcx 2025 1v1?

event_result · known event · event alias · tied placements

- **bcx 2025 1v1** → Brawlhalla World Championship Expo 2025 - 1v1 (2025-11-22), by event alias

**Candidate answer:**

Brawlhalla World Championship Expo 2025 - 1v1 (2025-11-22):
- 1st: Marckiem00
- 2nd: BBBalloonBoy
- 3rd: Raydish
- 4th: STING RAY
- 5th: V3M_T4NQUIL0 and Zivai
- 7th: Mounir and yüz

**Query 1:** the top 8

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'c979b223-7428-4534-97f9-08dd8e232c2e' AND r.placement <= 8
ORDER BY r.placement, p.name
```

| placement | name |
|---|---|
| 1 | Marckiem00 |
| 2 | BBBalloonBoy |
| 3 | Raydish |
| 4 | STING RAY |
| 5 | V3M_T4NQUIL0 |
| 5 | Zivai |
| 7 | Mounir |
| 7 | yüz |

**Verified:** yes

<a id="q18"></a>

## q18. who won 2v2 at autumns 2023 NA?

event_result · known event · event term · 2v2

- **autumns 2023 NA** → North America - Autumn Championship 2023 / Brawlhalla Championship 2v2 (2023-10-01)

**Candidate answer:**

bestjava and fakey7 won the North America - Autumn Championship 2023 2v2 (2023-10-01); megD and Raydish were 2nd.

**Query 1:** 1st and 2nd

```sql
SELECT r.placement, GROUP_CONCAT(p.name, ' / ') AS team
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'tournament/north-america-autumn-championship-2023/event/brawlhalla-championship-2v2'
  AND r.placement <= 2
GROUP BY r.placement, r.team_id
ORDER BY r.placement
```

| placement | team |
|---|---|
| 1 | bestjava / fakey7 |
| 2 | megD / Raydish |

**Verified:** yes

<a id="q19"></a>

## q19. Who won the Midseason Championship 2026?

event_result · known event · both modes · not the msi default

- **Midseason Championship 2026** → Midseason Championship 2026 1v1 (2026-06-12); Midseason Championship 2026 – 2v2 (2026-06-12)

**Candidate answer:**

BBBalloonBoy won both events (2026-06-12): the 1v1, ahead of Marckiem00, and the 2v2 with Mounir, ahead of loreszz and whoiskyna.

**Notes:** The year rules out "MSI", whose default is the 2022 Brawlhalla Midseason Championship.

**Query 1:** 1st and 2nd in both events

```sql
SELECT v.tournament_name, r.placement, GROUP_CONCAT(p.name, ' / ') AS players
FROM v_results r
JOIN players p ON p.player_id = r.player_id
JOIN v_events v ON v.event_id = r.event_id
WHERE r.event_id IN ('b0245d28-3355-4b87-ffac-08de8b2c5870', '658feb16-e07e-403f-c375-08de8b2c6a40')
  AND r.placement <= 2
GROUP BY r.event_id, r.placement, COALESCE(r.team_id, r.player_id)
ORDER BY v.counts_as, r.placement
```

| tournament_name | placement | players |
|---|---|---|
| Midseason Championship 2026 1v1 | 1 | BBBalloonBoy |
| Midseason Championship 2026 1v1 | 2 | Marckiem00 |
| Midseason Championship 2026 – 2v2 | 1 | Mounir / BBBalloonBoy |
| Midseason Championship 2026 – 2v2 | 2 | loreszz / whoiskyna |

**Verified:** yes

<a id="q20"></a>

## q20. what was the score of the 1v1 grand final at dreamhack valencia 2023

multi_step · known event · grand final is the last set · former name

- **dreamhack valencia 2023** → DreamHack Valencia 2023 / Brawlhalla (1v1) (2023-07-07)

**Candidate answer:**

Zivai (formerly Godly) beat Impala 3-0 in the 1v1 grand final of DreamHack Valencia 2023. There was no bracket reset: Zivai came from the winners' side without losing a set (8-0 at the event), and Impala, who had lost the winners' semi-final to luna, came through the losers' side.

**Notes:** Checked against start.gg's bracket in the cache (2026-10-10): the Top 8 pool has one Grand Final set, Kingdom | Godly 3-0 Impala, and no Grand Final Reset. The database stores no rounds until Phase 3, so its queries find the grand final as the winner's last set, against the runner-up, and the missing reset as the winner never losing a set.

**Query 1:** 1st and 2nd

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'tournament/dreamhack-valencia-2023/event/brawlhalla-1v1' AND r.placement <= 2
ORDER BY r.placement
```

| placement | name |
|---|---|
| 1 | Zivai |
| 2 | Impala |

**Query 2:** the winner's sets, in order: the last is the grand final

```sql
SELECT m.start_time, p.name AS opponent, m.games_won, m.games_lost, m.won
FROM v_match_results m
JOIN v_match_results o ON o.match_id = m.match_id AND o.side <> m.side
JOIN players p ON p.player_id = o.player_id
WHERE m.event_id = 'tournament/dreamhack-valencia-2023/event/brawlhalla-1v1' AND m.player_id = 147982
ORDER BY m.start_time
```

| start_time | opponent | games_won | games_lost | won |
|---|---|---|---|---|
| 1688897656 | zBlackneight | 3 | 0 | 1 |
| 1688898440 | EssJay | 3 | 0 | 1 |
| 1688901056 | PavelskiBH | 3 | 1 | 1 |
| 1688911017 | acno? | 3 | 2 | 1 |
| 1688914714 | Sgrape | 3 | 1 | 1 |
| 1688918832 | SiB \| Wess | 3 | 1 | 1 |
| 1688926278 | luna | 3 | 1 | 1 |
| 1688930865 | Impala | 3 | 0 | 1 |

**Query 3:** the runner-up's sets: a loss to luna, the losers' side, then the grand final

```sql
SELECT m.start_time, p.name AS opponent, m.games_won, m.games_lost, m.won
FROM v_match_results m
JOIN v_match_results o ON o.match_id = m.match_id AND o.side <> m.side
JOIN players p ON p.player_id = o.player_id
WHERE m.event_id = 'tournament/dreamhack-valencia-2023/event/brawlhalla-1v1' AND m.player_id = 168635
ORDER BY m.start_time
```

| start_time | opponent | games_won | games_lost | won |
|---|---|---|---|---|
| 1688904727 | ExodiA | 3 | 0 | 1 |
| 1688906209 | Snowb4ll | 3 | 1 | 1 |
| 1688907586 | Mounir | 3 | 0 | 1 |
| 1688911142 | Blaze | 3 | 0 | 1 |
| 1688916718 | megD | 3 | 2 | 1 |
| 1688920129 | luna | 1 | 3 | 0 |
| 1688925355 | Sgrape | 3 | 2 | 1 |
| 1688928635 | loreszz | 3 | 2 | 1 |
| 1688930038 | luna | 3 | 0 | 1 |
| 1688930865 | Zivai | 0 | 3 | 0 |

**Verified:** yes

<a id="q21"></a>

## q21. how many official events has baloonboy won?

player_record · misspelling

- **baloonboy** → BBBalloonBoy (149305, 79 results), no alias matches it

**Candidate answer:**

BBBalloonBoy has won 7 official events: 5 in 2v2 and 2 in 1v1.
- 2v2: Autumn Doubles Championship - North America (2024-10-06), Winter Championship - North America 2025 (2025-03-02), Winter Championship - North America 2026 (2026-03-01), Midseason Championship 2026 (2026-06-12), Summer Championship - North America 2026 (2026-07-26)
- 1v1: Midseason Championship 2026 (2026-06-12), Autumn Championship - North America 2026 (2026-09-20)

**Notes:** No alias matches "baloonboy": the agent has to find BBBalloonBoy by a close match (Balloonboy) and say which player it used.

**Query 1:** official wins

```sql
SELECT start_date, tournament_name, mode, format
FROM v_official_wins WHERE player_id = 149305 ORDER BY start_time
```

| start_date | tournament_name | mode | format |
|---|---|---|---|
| 2024-10-06 | Autumn Doubles Championship - North America | 2v2 | standard |
| 2025-03-02 | Winter Championship - North America 2025 | 2v2 | standard |
| 2026-03-01 | Winter Championship - North America 2026 - 2v2 | 2v2 | standard |
| 2026-06-12 | Midseason Championship 2026 – 2v2 | 2v2 | standard |
| 2026-06-12 | Midseason Championship 2026 1v1 | 1v1 | standard |
| 2026-07-26 | Summer Championship - North America 2026 - 2v2 | 2v2 | standard |
| 2026-09-20 | Autumn Championship - North America 2026 - 1v1 | 1v1 | standard |

**Verified:** yes

<a id="q22"></a>

## q22. did markiemoo ever win worlds

player_record · misspelling · event alias

- **markiemoo** → Marckiem00 (146052, 47 results), no alias matches it

**Candidate answer:**

Yes: Marckiem00 won the 1v1 at the Brawlhalla World Championship Expo 2025 (worlds 2025, 2025-11-22), ahead of BBBalloonBoy. Marckiem00's other world championship results: 7th in the 2025 2v2, and 3rd in both the 1v1 and the 2v2 at BCX 2024.

**Accepted answers** (each gets credit only with its assumption stated):

- *"markiemoo" is Marckiem00, whose curated nickname "marckiemoo" it misspells by one letter (the answer above):* Yes: Marckiem00 won the 1v1 at BCX 2025
- *a name that only a similar spelling matches isn't guessed: the agent asks which player was meant:* offers suggestions with Marckiem00 first

**Notes:** "markiemoo" misspells the curated nickname "marckiemoo", and no alias matches it. "Worlds" are the events the "worlds YYYY" event aliases name. The agent doesn't guess a name that only a similar spelling matches, so asking which player was meant, with Marckiem00 first, is accepted too (decided 2026-10-23).

**Query 1:** results at the events the worlds aliases name

```sql
SELECT a.alias, v.tournament_name, v.event_name, v.counts_as, r.placement
FROM event_aliases a
JOIN v_events v USING (event_id)
JOIN v_results r ON r.event_id = v.event_id AND r.player_id = 146052
WHERE a.alias LIKE 'worlds %'
ORDER BY v.start_time, v.counts_as
```

| alias | tournament_name | event_name | counts_as | placement |
|---|---|---|---|---|
| worlds 2024 | Brawlhalla World Championship Expo 2024 | 1v1 | 1v1 | 3 |
| worlds 2024 | Brawlhalla World Championship Expo 2024 | 2v2 | 2v2 | 3 |
| worlds 2025 | Brawlhalla World Championship Expo 2025 - 2v2 | NULL | 2v2 | 7 |
| worlds 2025 | Brawlhalla World Championship Expo 2025 - 1v1 | NULL | 1v1 | 1 |

**Verified:** yes

<a id="q23"></a>

## q23. kingdom | godly vs impala head to head

head_to_head · team tag · former name · shared name

- **kingdom | godly** → Zivai (147982, 74 results), by a former name; 3 other players with this name, with at most 5 results
- **impala** → Impala (168635, 48 results), by the display name; 1 other player with this name, with at most 1 result

**Candidate answer:**

Zivai (formerly Kingdom | Godly) and Impala are even at 3-3 in 1v1 sets at official events, 12-9 in games to Zivai:
- Brawlhalla World Championship Expo 2022 (2022-11-04): Impala won 3-0 and 3-1
- DreamHack San Diego 2023 (2023-04-07): Impala won 3-2
- DreamHack Valencia 2023 (2023-07-07): Zivai won 3-0
- Brawlhalla World Championship Expo 2023 (2023-11-03): Zivai won 3-0
- Brawlhalla World Championship Expo 2024 (2024-11-15): Zivai won 3-0

They never met in 2v2.

**Accepted answers** (each gets credit only with its assumption stated):

- *counted in sets (the default):* even, 3-3
- *counted in games:* Zivai leads 12-9

**Query 1:** the 1v1 record, from Zivai's side

```sql
SELECT wins, losses, matches, games_won, games_lost, unscored_matches
FROM v_head_to_head_1v1 WHERE player_id = 147982 AND opponent_id = 168635
```

| wins | losses | matches | games_won | games_lost | unscored_matches |
|---|---|---|---|---|---|
| 3 | 3 | 6 | 12 | 9 | 0 |

**Query 2:** the sets, from Zivai's side

```sql
SELECT a.start_date, v.tournament_name, a.games_won, a.games_lost
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
JOIN v_events v ON v.event_id = a.event_id
WHERE a.player_id = 147982 AND b.player_id = 168635 AND a.mode = '1v1' AND a.side_players = 1
ORDER BY a.start_time
```

| start_date | tournament_name | games_won | games_lost |
|---|---|---|---|
| 2022-11-04 | Brawlhalla World Championship Expo 2022 | 0 | 3 |
| 2022-11-04 | Brawlhalla World Championship Expo 2022 | 1 | 3 |
| 2023-04-07 | DreamHack San Diego 2023 | 2 | 3 |
| 2023-07-07 | DreamHack Valencia 2023 | 3 | 0 |
| 2023-11-03 | Brawlhalla World Championship Expo 2023 | 3 | 0 |
| 2024-11-15 | Brawlhalla World Championship Expo 2024 | 3 | 0 |

**Query 3:** 2v2 meetings

```sql
SELECT COUNT(*) AS meetings FROM v_head_to_head_2v2
WHERE player_id = 147982 AND 168635 IN (opponent1_id, opponent2_id)
```

| meetings |
|---|
| 0 |

**Verified:** yes

<a id="q24"></a>

## q24. who won msi 1v1

event_result · event alias · default event · say which event

- **msi** → Brawlhalla Midseason Championship / Brawlhalla Championship 1v1 (2022-06-12), by event alias

**Candidate answer:**

Taking MSI as the 2022 Brawlhalla Midseason Championship, which people call the Midseason Invitational: luna won its 1v1 (2022-06-12), ahead of megD. If another midseason event was meant: BBBalloonBoy won the Midseason Championship 2026 1v1.

**Accepted answers** (each gets credit only with its assumption stated):

- *MSI is the 2022 Brawlhalla Midseason Championship (the decided default):* luna, ahead of megD
- *MSI is the latest midseason event, the Midseason Championship 2026, with the answer acknowledging that "msi" is ambiguous:* BBBalloonBoy, ahead of Marckiem00

**Notes:** "msi" means the 2022 event by default (decided 2026-10-05), and the answer must say which event it used. Low Tier City Midseason Online (2020) is another midseason event someone may mean.

**Query 1:** 1st and 2nd at the 1v1 event the alias names

```sql
SELECT v.tournament_name, v.event_name, v.start_date, r.placement, p.name
FROM event_aliases a
JOIN v_events v USING (event_id)
JOIN v_results r ON r.event_id = v.event_id
JOIN players p ON p.player_id = r.player_id
WHERE a.alias = 'msi' AND v.counts_as = '1v1' AND r.placement <= 2
ORDER BY r.placement
```

| tournament_name | event_name | start_date | placement | name |
|---|---|---|---|---|
| Brawlhalla Midseason Championship | Brawlhalla Championship 1v1 | 2022-06-12 | 1 | luna |
| Brawlhalla Midseason Championship | Brawlhalla Championship 1v1 | 2022-06-12 | 2 | megD |

**Query 2:** the alias's note

```sql
SELECT DISTINCT note FROM event_aliases WHERE alias = 'msi'
```

| note |
|---|
| Default for MSI: the 2022 Brawlhalla Midseason Championship, which people call the Midseason Invitational. Someone may mean another midseason event, such as the Midseason Championship 2026 or LTC Midseason Online 2020 (a Midseason Championship 2025 isn't an official event), so the answer says which one it used |

**Query 3:** 1st and 2nd at the Midseason Championship 2026 1v1

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'b0245d28-3355-4b87-ffac-08de8b2c5870' AND r.placement <= 2
ORDER BY r.placement
```

| placement | name |
|---|---|
| 1 | BBBalloonBoy |
| 2 | Marckiem00 |

**Verified:** yes

<a id="q25"></a>

## q25. how many official tournaments has RAYDISH won

player_record · paraphrase · case · crew battles count as 1v1

- **RAYDISH** → Raydish (160000, 98 results), by the display name

**Candidate answer:**

6, all counted as 1v1: the NA Summer Championship 2022, the NA Winter Championship 2023, the Trials of Ymir, Heimdall and Laufey (NA, 2024), and the Eternal Sports Crew Battle Championship 2026 - North America (a crew battle: a team result, counted as 1v1).

**Accepted answers** (each gets credit only with its assumption stated):

- *every official event win, a crew battle counting as 1v1 (the decided rules):* 6: five 1v1 wins and the 2026 NA Crew Battle Championship, a team result
- *individual titles only, the crew battle left out as a team event:* 5: the NA Summer Championship 2022, the NA Winter Championship 2023 and the Trials of Ymir, Heimdall and Laufey (2024)

**Same answer as:** [q02](#q02)

**Query 1:** official wins

```sql
SELECT start_date, tournament_name, mode, format
FROM v_official_wins WHERE player_id = 160000 ORDER BY start_time
```

| start_date | tournament_name | mode | format |
|---|---|---|---|
| 2022-07-31 | North America - Summer Championship 2022 | 1v1 | standard |
| 2023-02-05 | North America - Winter Championship 2023 | 1v1 | standard |
| 2024-02-18 | Trial of Ymir - North America | 1v1 | standard |
| 2024-07-14 | Trial of Heimdall - North America (NSIG) | 1v1 | standard |
| 2024-08-25 | Trial of Laufey - North America (Moose Wars) | 1v1 | standard |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | 1v1 | crew_battle |

**Verified:** yes

<a id="q26"></a>

## q26. How many times has M30W | BalloonBoy finished top 3 at an official event?

player_record · paraphrase · team tag · medal = top 3 · side formats

- **M30W | BalloonBoy** → BBBalloonBoy (149305, 79 results), by a former name

**Candidate answer:**

27 times, in 1v1 and 2v2: 15 in 1v1 (2 wins, 8 seconds, 5 thirds, a crew battle second included) and 12 in 2v2 (5, 3 and 4). Seconds in Brawlball and Triples aren't counted.

**Accepted answers** (each gets credit only with its assumption stated):

- *official 1v1 and 2v2 events, a crew battle counting as 1v1 (the decided rules):* 27: 15 in 1v1 (a crew battle second included) and 12 in 2v2
- *individual results only, the crew battle second left out as a team result:* 26: 14 in 1v1 and 12 in 2v2
- *every official event, the side formats (Brawlball, Triples) included:* 29: the 27, plus seconds at the 2026 NA Brawlball and Triples Championships

**Same answer as:** [q07](#q07)

**Notes:** The team tag goes: the name without it, "BalloonBoy", is a former name of BBBalloonBoy.

**Query 1:** top-3 placements by mode

```sql
SELECT mode, gold, silver, bronze, medals
FROM v_player_medals WHERE player_id = 149305 ORDER BY mode
```

| mode | gold | silver | bronze | medals |
|---|---|---|---|---|
| 1v1 | 2 | 8 | 5 | 15 |
| 2v2 | 5 | 3 | 4 | 12 |

**Verified:** yes

<a id="q27"></a>

## q27. whats bbballoonboy's 1v1 record vs impala

head_to_head · paraphrase · case · read the view from one side

- **bbballoonboy** → BBBalloonBoy (149305, 79 results), by the display name
- **impala** → Impala (168635, 48 results), by the display name; 1 other player with this name, with at most 1 result

**Candidate answer:**

BBBalloonBoy is 1-2 against Impala in 1v1 sets at official events (4-8 in games): lost 0-3 at the Trial of Frigg NA (2024-03-17) and 1-3 at the Trial of Skuld NA (2024-08-04), won 3-2 at BCX 2024 (2024-11-15).

**Same answer as:** [q04](#q04)

**Notes:** The same three sets as q04, from the other side. A query that reads v_head_to_head_1v1 from both sides double-counts.

**Query 1:** the 1v1 record, from BBBalloonBoy's side

```sql
SELECT wins, losses, matches, games_won, games_lost, unscored_matches
FROM v_head_to_head_1v1 WHERE player_id = 149305 AND opponent_id = 168635
```

| wins | losses | matches | games_won | games_lost | unscored_matches |
|---|---|---|---|---|---|
| 1 | 2 | 3 | 4 | 8 | 0 |

**Query 2:** the sets, from BBBalloonBoy's side

```sql
SELECT a.start_date, v.tournament_name, a.games_won, a.games_lost
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
JOIN v_events v ON v.event_id = a.event_id
WHERE a.player_id = 149305 AND b.player_id = 168635 AND a.mode = '1v1' AND a.side_players = 1
ORDER BY a.start_time
```

| start_date | tournament_name | games_won | games_lost |
|---|---|---|---|
| 2024-03-17 | Trial of Frigg - North America (Moose Wars) | 0 | 3 |
| 2024-08-04 | Trial of Skuld - North America | 1 | 3 |
| 2024-11-15 | Brawlhalla World Championship Expo 2024 | 3 | 2 |

**Verified:** yes

<a id="q28"></a>

## q28. who won worlds 2019 1v1

event_result · paraphrase · event alias

- **worlds 2019 1v1** → DreamHack Atlanta 2019 / Brawlhalla World Championship 1v1 (2019-11-15), by event alias

**Candidate answer:**

gdsandstorm won the 2019 World Championship 1v1 (DreamHack Atlanta 2019, 2019-11-15); simpLe was 2nd.

**Query 1:** 1st and 2nd at the 1v1 event the alias names

```sql
SELECT v.tournament_name, v.event_name, r.placement, p.name
FROM event_aliases a
JOIN v_events v USING (event_id)
JOIN v_results r ON r.event_id = v.event_id
JOIN players p ON p.player_id = r.player_id
WHERE a.alias = 'worlds 2019' AND v.counts_as = '1v1' AND r.placement <= 2
ORDER BY r.placement
```

| tournament_name | event_name | placement | name |
|---|---|---|---|
| DreamHack Atlanta 2019 | Brawlhalla World Championship 1v1 | 1 | gdsandstorm |
| DreamHack Atlanta 2019 | Brawlhalla World Championship 1v1 | 2 | simpLe |

**Verified:** yes

<a id="q29"></a>

## q29. Who won the 1v1 at DreamHack Atlanta 2019?

event_result · paraphrase

- **DreamHack Atlanta 2019** → DreamHack Atlanta 2019 / Brawlhalla World Championship 1v1 (2019-11-15)

**Candidate answer:**

gdsandstorm won DreamHack Atlanta 2019's 1v1, the Brawlhalla World Championship 1v1 (2019-11-15); simpLe was 2nd.

**Same answer as:** [q28](#q28)

**Query 1:** 1st and 2nd

```sql
SELECT r.placement, p.name
FROM v_results r JOIN players p ON p.player_id = r.player_id
WHERE r.event_id = 'tournament/dreamhack-atlanta-2019/event/brawlhalla-1v1' AND r.placement <= 2
ORDER BY r.placement
```

| placement | name |
|---|---|
| 1 | gdsandstorm |
| 2 | simpLe |

**Verified:** yes

<a id="q30"></a>

## q30. who won ceo dreamland 2020

unanswerable · not held

- **ceo dreamland 2020** → CEO Dreamland 2020 / Brawlhalla 1v1 (2020-03-13)

**Candidate answer:**

Nobody: CEO Dreamland 2020 (planned for 2020-03-13) wasn't held. It was cancelled due to COVID-19. Brawlhalla CEO Dreamland ONLINE followed on 2020-03-28 and 29: gdsandstorm won the 1v1, and gdsandstorm and Boomie the 2v2.

**What's missing:** results: CEO Dreamland 2020 wasn't held

**Notes:** The answer must say the event wasn't held, not that its results are missing. Mentioning the online event is a plus, not required.

**Query 1:** the event's status

```sql
SELECT tournament_name, start_date, status, note
FROM v_events WHERE event_id = 'tournament/ceo-dreamland-2020/event/brawlhalla-1v1'
```

| tournament_name | start_date | status | note |
|---|---|---|---|
| CEO Dreamland 2020 | 2020-03-13 | cancelled | Not held: cancelled due to COVID-19 (decided 2026-10-05). Its start.gg event has only unstarted placeholder sets and no standings. Brawlhalla CEO Dreamland ONLINE (2020-03-28) followed |

**Query 2:** the online event that followed

```sql
SELECT v.tournament_name, v.event_name, v.start_date, GROUP_CONCAT(p.name, ' / ') AS winners
FROM v_official_wins w
JOIN v_events v ON v.event_id = w.event_id
JOIN players p ON p.player_id = w.player_id
WHERE w.event_id LIKE 'tournament/brawlhalla-ceo-dreamland-online/%'
GROUP BY w.event_id ORDER BY v.start_time
```

| tournament_name | event_name | start_date | winners |
|---|---|---|---|
| Brawlhalla CEO Dreamland ONLINE | Brawlhalla Championship 2v2 | 2020-03-28 | gdsandstorm / Boomie |
| Brawlhalla CEO Dreamland ONLINE | Brawlhalla Championship 1v1 | 2020-03-29 | gdsandstorm |

**Verified:** yes

<a id="q31"></a>

## q31. Who won SEA League Week 1/4?

partial · placements unreliable

- **SEA League Week 1/4** → SEA League (Week 1/4) / Brawlhalla Singles (2017-04-22)

**Candidate answer** (what the data shows):

In SEA League (Week 1/4)'s matches (2017-04-22), TigerBrawlhalla was the only player who didn't lose a set: 6-0.

**What's missing** (the rest of the expected answer): a reliable winner: start.gg's standings for the event are wrong, with 24 entrants placed 1st and 37 who played left out, so its placements aren't counted as results

**Notes:** Naming TigerBrawlhalla as the winner outright is wrong; naming them as the bracket's only undefeated player is right.

**Query 1:** the event's status

```sql
SELECT tournament_name, start_date, status, note
FROM v_events WHERE event_id = 'tournament/sea-league-week-1-4/event/brawlhalla-singles'
```

| tournament_name | start_date | status | note |
|---|---|---|---|
| SEA League (Week 1/4) | 2017-04-22 | placements_unreliable | Its start.gg standings are wrong: 24 entrants placed 1st (8 at 9th, 5 at 17th), and 37 who played aren't in them. So its placements are left out of results (wins, medals, top 8s), while its matches count (decided 2026-10-06). The bracket's only undefeated player was TigerBrawlhalla (160768, 6-0) |

**Query 2:** the standings as start.gg reported them

```sql
SELECT placement, COUNT(*) AS entrants
FROM placements WHERE event_id = 'tournament/sea-league-week-1-4/event/brawlhalla-singles'
GROUP BY placement ORDER BY placement LIMIT 3
```

| placement | entrants |
|---|---|
| 1 | 24 |
| 9 | 8 |
| 17 | 5 |

**Query 3:** players who won every set they played

```sql
SELECT p.name, SUM(m.won) AS sets_won, SUM(1 - m.won) AS sets_lost
FROM v_match_results m JOIN players p ON p.player_id = m.player_id
WHERE m.event_id = 'tournament/sea-league-week-1-4/event/brawlhalla-singles'
GROUP BY m.player_id HAVING sets_lost = 0
ORDER BY sets_won DESC
```

| name | sets_won | sets_lost |
|---|---|---|
| TigerBrawlhalla | 6 | 0 |

**Verified:** partly: can't confirm the real winner; kept as a data-quality test, since the expected answer is about unreliable standings

<a id="q32"></a>

## q32. how much prize money did vem win at max mode 2025

unanswerable · no per-tournament prize data · nickname · missing isn't zero

- **vem** → V3M_T4NQUIL0 (71736, 77 results), by a nickname
- **max mode 2025** → MAX MODE 2025 / Brawlhalla 1v1 (2025-04-26); MAX MODE 2025 / Brawlhalla 2v2 (2025-04-25)

**Candidate answer:**

The data can't say: the database has no prize money per tournament. V3M_T4NQUIL0 (vem) won the MAX MODE 2025 1v1 (2025-04-26) and was 2nd in the 2v2 (2025-04-25) with SiB | Wess, but how much either paid isn't recorded.

**What's missing:** prize money per tournament: the database has none

**Tied to eval-v1:** Phase 2 adds prize data per event. MAX MODE 2025's start.gg event has no structured payouts (API survey), so the answer stays that it isn't available unless its split is added by hand, but the reason becomes this event's missing payouts.

**Notes:** "vem" is a curated nickname for V3M_T4NQUIL0. MAX MODE 2025's standings hold only 8 of the 1v1's 41 entrants.

**Query 1:** vem's results at MAX MODE 2025

```sql
SELECT v.tournament_name, v.event_name, v.start_date, r.placement
FROM v_results r JOIN v_events v ON v.event_id = r.event_id
WHERE r.player_id = 71736 AND v.tournament_name = 'MAX MODE 2025'
ORDER BY v.start_time
```

| tournament_name | event_name | start_date | placement |
|---|---|---|---|
| MAX MODE 2025 | Brawlhalla 2v2 | 2025-04-25 | 2 |
| MAX MODE 2025 | Brawlhalla 1v1 | 2025-04-26 | 1 |

**Query 2:** tables and views about money: career figures only, nothing per tournament

```sql
SELECT type, name FROM sqlite_master
WHERE type IN ('table', 'view') AND (name LIKE '%prize%' OR name LIKE '%payout%' OR name LIKE '%earning%')
ORDER BY name
```

| type | name |
|---|---|
| table | player_earnings |
| view | v_career_earnings |

**Verified:** yes: unanswerable as written

<a id="q33"></a>

## q33. how much money has boomie made from brawlhalla

partial · missing isn't zero · shared name

- **boomie** → Boomie (146606, 147 results), by the display name; 6 other players with this name, with at most 9 results

**Candidate answer** (what the data shows):

The database's career earnings figures come from the Stats API (as of 2026-10-02), which has them only for the 4,981 players with a PR ranking. Boomie has no PR ranking.

**What's missing** (the rest of the expected answer): Boomie's earnings: there's no figure, so they're unknown, not $0

**Tied to eval-v1:** Phase 2's Esports Earnings fallback gives Boomie $210,282.67 (as of 2026-10-04), from a source that counts differently from the Stats API.

**Query 1:** Boomie's career figure: none

```sql
SELECT name, earnings_usd, source, as_of FROM v_career_earnings WHERE player_id = 146606
```

(no rows)

**Query 2:** Boomie's PR rows: none

```sql
SELECT COUNT(*) AS pr_rows FROM pr_snapshots WHERE player_id = 146606
```

| pr_rows |
|---|
| 0 |

**Verified:** yes: not answerable with the current database

<a id="q34"></a>

## q34. Who won the 2016 Brawlhalla World Championship?

unanswerable · data starts in 2017


**Candidate answer:**

The data can't say: it starts in February 2017 (the first official events are on 2017-02-04), so 2016's World Championship isn't in it.

**What's missing:** anything before February 2017: the data starts on 2017-02-04

**Query 1:** the dates the data covers

```sql
SELECT MIN(start_date) AS first_event, MAX(start_date) AS last_event, COUNT(*) AS events FROM v_events
```

| first_event | last_event | events |
|---|---|---|
| 2017-02-04 | 2026-09-27 | 622 |

**Verified:** yes: unanswerable as written

<a id="q35"></a>

## q35. what legend does godly main

unanswerable · no legend data · former name

- **godly** → Zivai (147982, 74 results), by a former name; 3 other players with this name, with at most 5 results

**Candidate answer:**

The data can't say: the database has no legend (character) data. Godly is Zivai (147982).

**What's missing:** legend (character) data: none in the database

**Tied to eval-v1:** Phase 3 adds the legends picked in each game, where the platforms reported them (a minority of matches), so the answer becomes partial.

**Notes:** An answer from general knowledge, rather than the data, is wrong here.

**Query 1:** matches with legend data: none

```sql
SELECT COUNT(*) AS matches, SUM(legends_json IS NOT NULL) AS with_legends FROM matches
```

| matches | with_legends |
|---|---|
| 560184 | 0 |

**Verified:** yes: unanswerable as written

<a id="q36"></a>

## q36. How many community tournaments has raydish won?

unanswerable · official events only · case

- **raydish** → Raydish (160000, 98 results), by the display name

**Candidate answer:**

The data can't say: it covers official events only, with no community tournaments. Raydish has 6 official event wins. ("Brawlhalla Community Tournament #2", 2025, is an official event despite its name, and Raydish didn't enter it.)

**What's missing:** community tournaments: the data covers official events only

**Notes:** Counting official events whose name says "Community" is wrong.

**Query 1:** events by is_official: all official

```sql
SELECT is_official, COUNT(*) AS events FROM v_events GROUP BY is_official
```

| is_official | events |
|---|---|
| 1 | 622 |

**Query 2:** official events named Community, and Raydish's result there

```sql
SELECT v.tournament_name, v.start_date, v.is_official,
       (SELECT r.placement FROM v_results r WHERE r.event_id = v.event_id AND r.player_id = 160000) AS raydish
FROM v_events v WHERE lower(v.tournament_name) LIKE '%community%'
```

| tournament_name | start_date | is_official | raydish |
|---|---|---|---|
| Brawlhalla Community Tournament #2 | 2025-09-28 | 1 | NULL |

**Verified:** yes: unanswerable as written

<a id="q37"></a>

## q37. Who has won the most official tournaments?

multi_step · most · crew battles count as 1v1 · both modes


**Candidate answer:**

gdsandstorm, with 48 official event wins, a tournament's 1v1 and 2v2 counted separately: 30 in 1v1 (2 of them crew battles, team results) and 18 in 2v2. Next: Boomie 44, acno? 36, TigerBrawlhalla 34 and Zivai 31.

**Accepted answers** (each gets credit only with its assumption stated):

- *wins counted per event, a tournament's 1v1 and 2v2 separately (the default):* gdsandstorm, 48; then Boomie 44 and acno? 36
- *wins counted per tournament, winning both of a tournament's events counting once:* Boomie, 42; then gdsandstorm 37 (who won both events at 11 tournaments) and TigerBrawlhalla 28

**Notes:** Side formats (Triples, Brawlball, ...) aren't counted. Leaving out crew battles (gdsandstorm 46, Boomie 42) or counting side formats (acno? and Zivai each won a Triples event) keeps gdsandstorm first.

**Query 1:** official wins per player

```sql
SELECT p.name, w.player_id, COUNT(*) AS wins, SUM(w.mode = '1v1') AS wins_1v1, SUM(w.mode = '2v2') AS wins_2v2,
       SUM(w.format = 'crew_battle') AS crew_battles
FROM v_official_wins w JOIN players p ON p.player_id = w.player_id
GROUP BY w.player_id ORDER BY wins DESC LIMIT 5
```

| name | player_id | wins | wins_1v1 | wins_2v2 | crew_battles |
|---|---|---|---|---|---|
| gdsandstorm | 74433 | 48 | 30 | 18 | 2 |
| Boomie | 146606 | 44 | 12 | 32 | 2 |
| acno? | 144399 | 36 | 13 | 23 | 0 |
| TigerBrawlhalla | 160768 | 34 | 26 | 8 | 0 |
| Zivai | 147982 | 31 | 23 | 8 | 1 |

**Query 2:** tournaments won per player: a start.gg tournament's events share a slug; Challengermode names each with its mode

```sql
WITH tournaments AS (
  SELECT event_id,
         COALESCE(sgg_tournament_slug,
                  replace(replace(replace(replace(replace(replace(replace(tournament_name, ' - 2v2 - rerun', ''),
                    ' - 1v1', ''), ' - 2v2', ''), ' – 1v1', ''), ' – 2v2', ''), ' 1v1', ''), ' 2v2', '')) AS tournament
  FROM events)
SELECT p.name, w.player_id, COUNT(DISTINCT t.tournament) AS tournaments_won, COUNT(*) AS event_wins
FROM v_official_wins w
JOIN tournaments t ON t.event_id = w.event_id
JOIN players p ON p.player_id = w.player_id
GROUP BY w.player_id ORDER BY tournaments_won DESC LIMIT 5
```

| name | player_id | tournaments_won | event_wins |
|---|---|---|---|
| Boomie | 146606 | 42 | 44 |
| gdsandstorm | 74433 | 37 | 48 |
| TigerBrawlhalla | 160768 | 28 | 34 |
| Zivai | 147982 | 27 | 31 |
| acno? | 144399 | 26 | 36 |

**Verified:** yes

<a id="q38"></a>

## q38. rank the top 5 players by official 1v1 wins

multi_step · ranking · crew battles count as 1v1


**Candidate answer:**

1. gdsandstorm, 30 (2 of them crew battles)
2. TigerBrawlhalla, 26
3. Zivai, 23 (1 crew battle)
4. Kylar Alice, 19
5. yüz, 14 (1 crew battle)

Crew battles count as 1v1, though they're team results. Without them: gdsandstorm 28, TigerBrawlhalla 26, Zivai 22, Kylar Alice 19, then acno?, whoiskyna and yüz tied at 13.

**Accepted answers** (each gets credit only with its assumption stated):

- *crew battle wins counted as 1v1 (the decided rule):* gdsandstorm 30, TigerBrawlhalla 26, Zivai 23, Kylar Alice 19, yüz 14
- *crew battles left out as team events:* gdsandstorm 28, TigerBrawlhalla 26, Zivai 22, Kylar Alice 19, then a three-way tie for 5th at 13: acno?, whoiskyna and yüz

**Query 1:** official 1v1 wins per player, crew battles included

```sql
SELECT p.name, w.player_id, COUNT(*) AS wins_1v1, SUM(w.format = 'crew_battle') AS crew_battles
FROM v_official_wins w JOIN players p ON p.player_id = w.player_id
WHERE w.mode = '1v1'
GROUP BY w.player_id ORDER BY wins_1v1 DESC LIMIT 6
```

| name | player_id | wins_1v1 | crew_battles |
|---|---|---|---|
| gdsandstorm | 74433 | 30 | 2 |
| TigerBrawlhalla | 160768 | 26 | 0 |
| Zivai | 147982 | 23 | 1 |
| Kylar Alice | 79046 | 19 | 0 |
| yüz | 73254 | 14 | 1 |
| acno? | 144399 | 13 | 0 |

**Query 2:** the same without crew battles

```sql
SELECT p.name, w.player_id, COUNT(*) AS wins_1v1
FROM v_official_wins w JOIN players p ON p.player_id = w.player_id
WHERE w.mode = '1v1' AND w.format = 'standard'
GROUP BY w.player_id ORDER BY wins_1v1 DESC, p.name LIMIT 7
```

| name | player_id | wins_1v1 |
|---|---|---|
| gdsandstorm | 74433 | 28 |
| TigerBrawlhalla | 160768 | 26 |
| Zivai | 147982 | 22 |
| Kylar Alice | 79046 | 19 |
| acno? | 144399 | 13 |
| whoiskyna | 135748 | 13 |
| yüz | 73254 | 13 |

**Verified:** yes: Boomie's 12 official 1v1 wins (tied 8th) correctly keep him out of the top 5

<a id="q39"></a>

## q39. who has more medals, boomie or sandstorm?

multi_step · comparison · nickname · shared name · medal = top 3

- **boomie** → Boomie (146606, 147 results), by the display name; 6 other players with this name, with at most 9 results
- **sandstorm** → gdsandstorm (74433, 133 results), by a nickname; 8 other players with this name, with at most 6 results

**Candidate answer:**

Boomie, with 80 medals (top-3 placements at official events) to gdsandstorm's 69:
- Boomie: 1v1 12 gold, 11 silver, 11 bronze (34); 2v2 32, 8 and 6 (46)
- gdsandstorm: 1v1 30, 6 and 6 (42); 2v2 18, 4 and 5 (27)

gdsandstorm has more wins (48 to 44), and Boomie more medals.

**Accepted answers** (each gets credit only with its assumption stated):

- *both modes (the default), or 2v2 only:* Boomie: 80 to 69 in all, 46 to 27 in 2v2
- *1v1 only:* gdsandstorm, 42 to 34

**Query 1:** medals by player and mode

```sql
SELECT p.name, m.mode, m.gold, m.silver, m.bronze, m.medals
FROM v_player_medals m JOIN players p ON p.player_id = m.player_id
WHERE m.player_id IN (146606, 74433)
ORDER BY p.name, m.mode
```

| name | mode | gold | silver | bronze | medals |
|---|---|---|---|---|---|
| Boomie | 1v1 | 12 | 11 | 11 | 34 |
| Boomie | 2v2 | 32 | 8 | 6 | 46 |
| gdsandstorm | 1v1 | 30 | 6 | 6 | 42 |
| gdsandstorm | 2v2 | 18 | 4 | 5 | 27 |

**Verified:** yes

<a id="q40"></a>

## q40. who has raydish lost to the most in 1v1

multi_step · most · head-to-head · case

- **raydish** → Raydish (160000, 98 results), by the display name

**Candidate answer:**

gdsandstorm: 10 of Raydish's 1v1 set losses at official events came against gdsandstorm (Raydish is 3-10 against them). Next: luna 8 (1-8), Marckiem00 7 (6-7) and BBBalloonBoy 6 (4-6).

**Query 1:** Raydish's 1v1 records, most losses first

```sql
SELECT p.name, h.opponent_id, h.losses, h.wins, h.matches
FROM v_head_to_head_1v1 h JOIN players p ON p.player_id = h.opponent_id
WHERE h.player_id = 160000
ORDER BY h.losses DESC, h.matches DESC LIMIT 5
```

| name | opponent_id | losses | wins | matches |
|---|---|---|---|---|
| gdsandstorm | 74433 | 10 | 3 | 13 |
| luna | 51494 | 8 | 1 | 9 |
| Marckiem00 | 146052 | 7 | 6 | 13 |
| BBBalloonBoy | 149305 | 6 | 4 | 10 |
| Mounir | 79853 | 4 | 0 | 4 |

**Verified:** yes

<a id="q41"></a>

## q41. Who has won the most 1v1 world championships?

multi_step · most · event alias · say what was counted


**Candidate answer:**

gdsandstorm, with 3: 2018 (DreamHack Atlanta 2018), 2019 (DreamHack Atlanta 2019) and 2020, when the World Championship was held separately in five regions (gdsandstorm won North America's). yüz has 2 (BCX 2023 and 2024). Counting only the single worldwide championships, leaving out 2020 and 2021's regional ones, gdsandstorm and yüz tie at 2.

**Accepted answers** (each gets credit only with its assumption stated):

- *Worlds are the events the "worlds YYYY" aliases name, the 2020 and 2021 regional championships included (the default):* gdsandstorm, 3 (2018, 2019 and North America's 2020 championship); yüz has 2
- *only the single worldwide championships, 2020 and 2021's regional ones left out:* gdsandstorm and yüz, tied at 2

**Notes:** The 1v1 world champions by year, as the "worlds YYYY" aliases name them: 2017 ZEEKO, 2018 and 2019 gdsandstorm, 2020 and 2021 five regional winners each, 2022 Impala, 2023 and 2024 yüz, 2025 Marckiem00.

**Query 1:** 1v1 wins at the events the worlds aliases name, per player

```sql
SELECT p.name, w.player_id, COUNT(*) AS titles, GROUP_CONCAT(a.alias || ': ' || w.tournament_name, '; ') AS events
FROM event_aliases a
JOIN v_official_wins w ON w.event_id = a.event_id
JOIN players p ON p.player_id = w.player_id
WHERE a.alias LIKE 'worlds %' AND w.mode = '1v1'
GROUP BY w.player_id ORDER BY titles DESC, p.name LIMIT 5
```

| name | player_id | titles | events |
|---|---|---|---|
| gdsandstorm | 74433 | 3 | worlds 2018: DreamHack Atlanta 2018; worlds 2019: DreamHack Atlanta 2019; worlds 2020: North America -  Brawlhalla World Championship 2020 |
| yüz | 73254 | 2 | worlds 2023: Brawlhalla World Championship Expo 2023; worlds 2024: Brawlhalla World Championship Expo 2024 |
| Cody Travis | 117179 | 1 | worlds 2021: North America - Brawlhalla World Championship 2021 |
| Dummy | 147120 | 1 | worlds 2020: Australia -  Brawlhalla World Championship 2020 |
| Impala | 168635 | 1 | worlds 2022: Brawlhalla World Championship Expo 2022 |

**Query 2:** the same without 2020 and 2021's regional championships

```sql
SELECT p.name, w.player_id, COUNT(*) AS titles
FROM event_aliases a
JOIN v_official_wins w ON w.event_id = a.event_id
JOIN players p ON p.player_id = w.player_id
WHERE a.alias LIKE 'worlds %' AND a.alias NOT IN ('worlds 2020', 'worlds 2021') AND w.mode = '1v1'
GROUP BY w.player_id ORDER BY titles DESC, p.name LIMIT 3
```

| name | player_id | titles |
|---|---|---|
| gdsandstorm | 74433 | 2 |
| yüz | 73254 | 2 |
| Impala | 168635 | 1 |

**Verified:** yes

<a id="q42"></a>

## q42. what was the biggest official brawlhalla tournament ever?

multi_step · most · name the metric


**Candidate answer:**

By entrants in one event, the North America - SteelSeries Championship 1v1 (2020-08-22), with 7,240. Next: Low Tier City Midseason Online (NA) 1v1 (2020-07-18), 6,972, and the Europe - SteelSeries Championship 1v1 (2020-08-23), 6,160.

**Accepted answers** (each gets credit only with its assumption stated):

- *most entrants in one event (the default):* the North America - SteelSeries Championship 1v1 (2020-08-22): 7,240 entrants
- *most players in one tournament, its 1v1 and 2v2 events together:* Low Tier City Midseason Online (NA), July 2020: 10,451 players; the North America - SteelSeries Championship has 8,597
- *a series held in several regions counted as one, by entrants:* the 2020 SteelSeries Championship: 18,298 1v1 entrants in five regions (22,269 with the 2v2 teams)
- *a series held in several regions counted as one, by players:* Low Tier City Midseason Online 2020: 22,666 players in five regions, both modes; the 2020 SteelSeries Championship has 21,358
- *largest prize pool:* not in the data, which has no prize pools: the answer says so, and may answer by entrants instead

**Tied to eval-v1:** Phase 2 adds prize pools, so the prize-pool reading gets an answer.

**Notes:** Entrants are as the platform reported them (start.gg's standings total), and a 2v2 event's entrants are teams. Players are distinct people with a placement.

**Query 1:** events with the most entrants

```sql
SELECT tournament_name, event_name, start_date, entrants_reported, placements
FROM v_event_coverage ORDER BY entrants_reported DESC LIMIT 3
```

| tournament_name | event_name | start_date | entrants_reported | placements |
|---|---|---|---|---|
| North America - SteelSeries Championship | Brawlhalla Championship 1v1 | 2020-08-22 | 7240 | 7240 |
| Low Tier City Midseason Online (NA) | Brawlhalla Championship 1v1 | 2020-07-18 | 6972 | 6972 |
| Europe - SteelSeries Championship | Brawlhalla Championship 1v1 | 2020-08-23 | 6160 | 6160 |

**Query 2:** tournaments with the most players, 1v1 and 2v2 together (tournaments grouped as in q37)

```sql
WITH tournaments AS (
  SELECT event_id, tournament_name,
         COALESCE(sgg_tournament_slug,
                  replace(replace(replace(replace(replace(replace(replace(tournament_name, ' - 2v2 - rerun', ''),
                    ' - 1v1', ''), ' - 2v2', ''), ' – 1v1', ''), ' – 2v2', ''), ' 1v1', ''), ' 2v2', '')) AS tournament
  FROM events)
SELECT MIN(t.tournament_name) AS tournament, COUNT(DISTINCT t.event_id) AS events,
       COUNT(DISTINCT q.canonical_id) AS players
FROM tournaments t
JOIN placements pl ON pl.event_id = t.event_id
JOIN players q ON q.player_id = pl.player_id
GROUP BY t.tournament ORDER BY players DESC LIMIT 3
```

| tournament | events | players |
|---|---|---|
| Low Tier City Midseason Online (NA) | 2 | 10451 |
| North America - SteelSeries Championship | 2 | 8597 |
| Low Tier City Midseason Online (EU) | 2 | 7654 |

**Query 3:** series held in several regions, the region taken out of the name, most players first (a series with more 1v1 entrants would have at least as many players, so it would be here too)

```sql
WITH named AS (
  SELECT event_id, year, counts_as,
         trim(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(tournament_name,
           'North America - ', ''), 'Europe - ', ''), 'South America - ', ''), 'Southeast Asia - ', ''),
           'Australia - ', ''), ' (NA)', ''), ' (EU)', ''), ' (SA)', ''), ' (SEA)', ''), ' (AUS)', ''), '  ', ' ')) AS series
  FROM v_events)
SELECT n.series, n.year, COUNT(*) AS events,
       SUM(CASE WHEN n.counts_as = '1v1' THEN c.entrants_reported END) AS entrants_1v1,
       SUM(c.entrants_reported) AS entrants,
       (SELECT COUNT(DISTINCT q.canonical_id) FROM named m
          JOIN placements pl ON pl.event_id = m.event_id
          JOIN players q ON q.player_id = pl.player_id
         WHERE m.series = n.series AND m.year = n.year) AS players
FROM named n JOIN v_event_coverage c ON c.event_id = n.event_id
GROUP BY n.series, n.year ORDER BY players DESC LIMIT 3
```

| series | year | events | entrants_1v1 | entrants | players |
|---|---|---|---|---|---|
| Low Tier City Midseason Online | 2020 | 10 | 15010 | 21378 | 22666 |
| SteelSeries Championship | 2020 | 10 | 18298 | 22269 | 21358 |
| Mammoth Cup | 2020 | 10 | 12706 | 15504 | 14829 |

**Verified:** yes: technically correct

<a id="q43"></a>

## q43. what was megd's first major win?

multi_step · first · case · majors means official events

- **megd** → megD (142100, 104 results), by the display name

**Candidate answer:**

megD's first official event win was the Summer Championship - North America 2026 - 1v1 (2026-07-19). The second came on 2026-08-30, at the Eternal Sports Crew Battle Championship 2026 - North America (a crew battle).

**Query 1:** official wins, oldest first

```sql
SELECT start_date, tournament_name, mode, format
FROM v_official_wins WHERE player_id = 142100 ORDER BY start_time
```

| start_date | tournament_name | mode | format |
|---|---|---|---|
| 2026-07-19 | Summer Championship - North America 2026 - 1v1 | 1v1 | standard |
| 2026-08-30 | Eternal Sports Crew Battle Championship 2026 - North America | 1v1 | crew_battle |

**Verified:** yes

<a id="q44"></a>

## q44. How many times did Ahmet finish second to Godly in 2026?

multi_step · comparison · former name · shared name

- **Ahmet** → Ahmet_ (75405, 38 results), by the display name; 1 other player with this name, with at most 1 result
- **Godly** → Zivai (147982, 74 results), by a former name; 3 other players with this name, with at most 5 results

**Candidate answer:**

3 times, all in 1v1 at official events, each won by Zivai (formerly Godly) with Ahmet_ 2nd: the Spring (2026-04-25), Summer (2026-07-18) and Autumn (2026-09-19) Championships - Europe 2026.

**Notes:** "Ahmet" also names a record with one result; Ahmet_ is the ranked player.

**Query 1:** 2026 events Zivai won with Ahmet_ 2nd

```sql
SELECT a.start_date, a.tournament_name, a.mode
FROM v_results a
JOIN v_results b ON b.event_id = a.event_id AND b.player_id = 75405 AND b.placement = 2
WHERE a.player_id = 147982 AND a.placement = 1 AND a.start_date LIKE '2026-%'
ORDER BY a.start_time
```

| start_date | tournament_name | mode |
|---|---|---|
| 2026-04-25 | Spring Championship - Europe 2026 - 1v1 | 1v1 |
| 2026-07-18 | Summer Championship - Europe 2026 - 1v1 | 1v1 |
| 2026-09-19 | Autumn Championship - Europe 2026 - 1v1 | 1v1 |

**Verified:** partly: probably correct, not yet confirmed

<a id="q45"></a>

## q45. who has earned more money, raydish or impala?

partial · comparison · missing isn't zero

- **raydish** → Raydish (160000, 98 results), by the display name
- **impala** → Impala (168635, 48 results), by the display name; 1 other player with this name, with at most 1 result

**Candidate answer** (what the data shows):

Raydish's career earnings are $83,825 (Stats API, as of 2026-10-02).

**What's missing** (the rest of the expected answer): a figure for Impala, who has no PR ranking, so the Stats API has none: the two can't be compared, and Impala's earnings are unknown, not $0

**Tied to eval-v1:** Phase 2's Esports Earnings fallback gives Impala $84,730 (as of 2026-10-04), from a source that counts differently from the Stats API, so the comparison becomes possible with that caveat.

**Notes:** The API survey found $88,095 for Impala through the Stats API's search, which the database doesn't hold.

**Query 1:** both career figures: only Raydish's exists

```sql
SELECT player_id, name, earnings_usd, source, as_of
FROM v_career_earnings WHERE player_id IN (160000, 168635)
```

| player_id | name | earnings_usd | source | as_of |
|---|---|---|---|---|
| 160000 | Raydish | 83825.0 | Stats API | 2026-10-02 |

**Verified:** yes: not answerable because Impala's earnings are unknown
