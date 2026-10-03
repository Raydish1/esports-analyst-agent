# Brawlhalla Esports Stats API survey

What the official Brawlhalla Esports Stats API returns, how it behaves, and which of our target questions it can answer. Input for the database schema and agent design; no schema is proposed here.

- **API:** `https://api.brawltools.com/v2`, no authentication. Docs: <https://www.docs.brawltools.com/v2/pages/>
- **SDK:** `@bmg-esports/sdk` 2.2.0 (thin wrapper over `fetch`; see §10 for its quirks)
- **Script:** [`ingest/survey_api.mjs`](../ingest/survey_api.mjs) (`cd ingest && npm install && npm run survey`). The final run made 344 requests, 600 ms apart, on 2026-10-03 (UTC). It calls all 18 SDK methods and saves every raw response to `data/raw/survey/`, with `_manifest.json` mapping each file to its URL, parameters and HTTP status. That folder is git-ignored because the data is for personal use only.
- Example values below are copied from those responses.

## Key takeaways

1. **Majors are `isOfficial` events (decided).** It is the only official/community signal, and it is broad. Besides seasonal championships and Worlds, it covers partner events (CEO, DreamHack), invitationals, qualifiers, 2017 weekly league rounds and a "Community Tournament". Crew battles count as 1v1. 3v3, Triples, Brawlball and Kung Foot events count toward neither mode. A tournament split into phases counts once (§2).
2. **There is no event endpoint.** You cannot list an event's entrants, standings or size. Results are only reachable through a player (placements) or a pair of entrants (matchups).
3. **There is no bracket structure:** no round, seed, bracket side, phase or pool, and match `startTime` is almost always null. The original start.gg and Challengermode IDs are present, so bracket detail could be fetched from those platforms later (§6).
4. **Coverage runs from February 2017 to today, and it is uneven.** Before 2020 only official events exist. Community events peak in 2022. start.gg data stops at CEO 2025 (June 2025). Challengermode-era events are present, but in 2026 they are mostly official (§7).
5. **Medals are top-3 placements at official events (decided), so they must be counted from placements.** The PR `gold`/`silver`/`bronze` fields leave out crew battles and are zero for anyone not currently ranked: Boomie has 80 medals, but PR shows 0. **Earnings** is a single career total that is missing for unranked players. For some of them, such as Boomie, no endpoint has it at all, so linking them needs an external source (§3).
6. **Doubles:** passing two player IDs gives a team's placements, matches and head-to-heads. A single player's 2v2 placement does not say who their teammate was (§4).
7. **Search can't find inactive start.gg-era players.** It only covers players who are currently ranked or have a Challengermode account. Boomie, a five-time 2v2 world champion, is invisible to it and had to be found through megD's match history. It also matches current display names only ("marckiemoo" is Marckiem00), returns at most 25 results with no pagination, and rejects spaces and symbols (§8).
8. **DQs must not count as wins or losses (decided), so head-to-heads must be computed from match-level data.** A DQ is stored as a `-1` game score, and GetMatchup's records count DQs as wins and losses (§5).
9. **Three API bugs affect ingestion:** timestamp page tokens skip events that share a start time, matchup page tokens fail once DQ records appear, and `ListEvents` without `gameMode` returns 500 (§10).

## Test players

| Asked for | Resolved to | `playerId` | How | Confidence |
|---|---|---|---|---|
| Boomie | Boomie | 146606 | Not returned by search (the only result is an unrelated "Inboomie Noodles"); found as an opponent in megD's 2v2 head-to-head list | confirmed: exact name, five 2v2 World Championship wins |
| Raydish | Raydish | 160000 | exact match | confirmed |
| Hexo | Hexoo | 169084 | closest search result (NA, 1v1 PR #25) | confirmed (by you) |
| Impala | Impala | 168635 | exact match | confirmed |
| Balloonboy | BBBalloonBoy | 149305 | the only search result (NA 1v1 PR #1) | probable |
| megd | megD | 142100 | exact, case-insensitive | confirmed |
| marckiemoo | Marckiem00 | 146052 | "marckiemoo" finds nothing; "Marckie" finds this player | confirmed (by you). People call him by a name that isn't his display name; expect other cases like this (§8). |

## 1. Endpoints

### Shared objects

**Player**

| Field | Type | Example | Notes |
|---|---|---|---|
| `playerId` | int | `160000` | Esports ID. Most endpoints accept only this ID. |
| `sggPlayerId` | int or null | `1749170` | start.gg player ID |
| `cmPlayerId` | UUID or null | `"2914557c-90d4-41f4-a58f-73863728667d"` | Challengermode user ID |
| `brawlhallaId` | int or null | `30226535` | In-game ID |
| `name` | string | `"Raydish"` | Current display name; can include a team tag (`"Pink \| Guichabou"`) |
| `twitter`, `twitch`, `country` | string, optional | `"ImpalaVS"`, `"impalavs"`, `"United States"` | Omitted, not null, when unknown. Only 1 of 7 test players had them. `pronoun` (in the SDK types) never appeared. |

Player objects nested inside matches and matchups always have `sggPlayerId` and `cmPlayerId` set to null, even for players who have them.

**Tournament.** This is really one *event*: a start.gg tournament with 1v1 and 2v2 brackets appears as two Tournaments.

| Field | Type | Example | Notes |
|---|---|---|---|
| `id` | string | `"tournament/ceo-2025-6/event/brawlhalla-singles"` or `"fcb7a286-3f0c-4f68-f9a5-08ded4cb1c05"` | start.gg event **slug** (the docs wrongly say "a number"), or Challengermode tournament UUID |
| `tournamentName` | string | `"CEO 2025"` | |
| `eventName` | string or null | `"Brawlhalla Singles"` | Always null for Challengermode events |
| `year` | int | `2025` | |
| `isOfficial` | bool | `true` | See §2 |
| `isTwos` | bool | `false` | |
| `isOnline` | bool | `false` | |
| `startTime` | int (Unix seconds) | `1749913200` | |
| `host` | `"SGG"` or `"CM"` | `"SGG"` | |

**PlayerPr** (one per game mode)

| Field | Type | Example | Notes |
|---|---|---|---|
| `top8`, `top32` | int | `25`, `43` | Number of top-8 / top-32 finishes (§3) |
| `gold`, `silver`, `bronze` | int | `5`, `3`, `5` | Number of 1st / 2nd / 3rd places (§3) |
| `powerRanking` | int | `14` | Rank within the region; `0` when unranked |
| `region` | string | `"NA"` | `""` when unranked |

In `SearchPlayers`, an unranked mode has null counts and a null rank; `region` can still be filled from the other mode. Other endpoints return zeros and `""`.

### Endpoints

All endpoints are `GET` requests. List parameters are comma-separated (the SDK joins arrays). "Max" values are the documented limits. The search and placements limits were also confirmed: going over returns 400.

| Endpoint | SDK method | Path | Parameters | Returns |
|---|---|---|---|---|
| SearchPlayers | `searchPlayers` | `/player/search` | `query` (required; must match `[\w.,]+`), `maxResults` (default 10, max 25), `nextToken` (never returned) | `searchPlayers[]`: `{player, pr1v1, pr2v2, earnings: 83825}`; `nextToken` (always null) |
| GetPlayer | `getPlayer` | `/player/{playerId}` | none | `{player}`. An unknown ID gives 404 (the SDK returns null). |
| GetPlayerByBhId | `getPlayerByBrawlhallaId` | `/player/bhId/{id}` | none | `{player}` |
| GetPlayerBySggId | `getPlayerBySggId` | `/player/sggId/{id}` | none | `{player}` |
| GetPlayerByCmId | `getPlayerByCmId` | `/player/cmId/{uuid}` | none | `{player}` |
| ListPlayers | `listPlayers` | `/players` | exactly one of `playerIds`, `bhIds`, `sggIds`, `cmIds` (mixing gives 400) | `players[]` (Player) |
| GetPlayerPr | `getPlayerPR` | `/player/pr` | `playerIds` (one ID; two give 400 "Team PR not supported at this time"), `gameMode` | `{earnings: 83825, pr: PlayerPr}`. Unranked players get `earnings: 0` and an all-zero `pr`, not a 404. |
| ListPlayerPrs | `listPrPlayers` | `/players/pr` | one ID type as in ListPlayers, `gameMode`, `region` (from v2.1; missing from the SDK types but passed through) | `players[]`: `{player, pr}`. With `region`, non-matching players come back as `{player: null, pr: null}` instead of being dropped. |
| ListPr | `listPR` | `/pr` | `gameMode`, `region` (both required), `page`, `maxResults` (default 50; 100 works), `orderBy` (e.g. `"earnings DESC"`; default is `powerRanking` ascending) | `prPlayers[]`: `{playerId: 74433, playerName: "gdsandstorm", top8: 60, top32: 69, gold: 28, silver: 7, bronze: 6, powerRanking: 737, points: 1.269, earnings: 258984.17}`; `totalPages: 12`; `lastUpdated: "2026-10-02"`. `twitter`/`twitch` are in the SDK types but never returned. |
| GetPlayerPlacements | `getPlayerPlacements` | `/player/placement` | `playerIds` (one ID, or two for a 2v2 team), `gameMode` (required), `isOfficial` (true = official only; default all), `maxResults` (default 10, max 50), `nextToken` | `playerPlacements[]`: `{placement: 2, tournament}`, newest first; `nextToken` is the last row's `startTime` (`"1680883200"`) |
| GetPlayerTeammates | `getPlayerTeammates` | `/player/teammate` | `playerId`, `isOfficial`, `maxResults` (max 50), `nextToken` | `playerTeammates[]`: `{player, games: 33, lastTeamedDate: 1790525905}` (§4) |
| GetPlayerMatches | `getPlayerMatches` | `/player/match` | `tournamentId` (a start.gg slug or a UUID; anything else gives 400), `playerIds` (one, or both teammates) | `playerMatches[]`: `{matchId, scores: [3, 1], legends, maps, opponent: Player[], startTime}` (details below) |
| GetPlayerLegends | `getPlayerLegends` | `/player/legend` | `playerIds` (one ID; two give 400 "Only 1v1 supported at this time"), `isOfficial`, `year`, `maxResults` (max 10), `nextToken` | `legends[]`: `{name: "RED_RAPTOR", count: 472}`; `nextToken` `"1-UkFZTUFO"` (a count plus the base64 legend name) |
| GetPlayerRecentLegend | `getPlayerRecentLegend` | `/player/{playerId}/legend` (the docs call this ID `smashId`, its v1 name) | none | `{legend: {name: "RED_RAPTOR", count: 13}}` |
| GetMatchup | `getMatchup` | `/matchup` | `entrant1PlayerIds` (required; one ID, or two for a team), `entrant2PlayerIds`, `gameMode`, `isOfficial`, `maxResults` (max 50), `nextToken` | `matchups[]`: `{matches: [20, 5], games: [61, 38], opponent: Player[]}`, counted from entrant 1's side (§5) |
| GetMatchupPlacements | `getMatchupPlacements` | `/matchup/placement` | both entrants (required), `gameMode`, `isOfficial`, `maxResults`, `nextToken` | `matchupPlacements[]`: `{placements: [7, 5], tournament}` |
| GetMatchupMatches | `getMatchupMatches` | `/matchup/match` | `tournamentId`, `entrant1PlayerIds`, `entrant2PlayerIds` (required in practice, although the SDK marks it optional) | `matchupMatches[]`: `{matchId: "82392891", scores: [2, 3], legends, maps}`, with no opponent or `startTime` |
| ListEvents | `listEvents` | `/event` | `gameMode` (required in practice; omitting it gives 500), `isOfficial`, `year`, `host` (`SGG`/`CM`), `maxResults` (max 50), `nextToken` (a `startTime`) | `tournaments[]` (Tournament), newest first |

**Match fields** (GetPlayerMatches; GetMatchupMatches returns the same fields minus `opponent` and `startTime`):

| Field | Example | Notes |
|---|---|---|
| `matchId` | `"c3336cea-4a41-4c9b-65f4-08df1591daff"` (CM) or `"22016039"` (start.gg set ID) | Always a string |
| `scores` | `[3, 1]` | Games won by the requested player, then by the opponent. A DQ shows as `-1` for the DQ'd side and `0` for the other (§5). |
| `legends` | `[["DIANA","DIANA","DIANA"], ["PETRA","PETRA","PETRA"]]` | One list per side, one entry per game. Usually `[[""],[""]]` or `[[],[]]`: only 41 of 172 matches had any. |
| `maps` | `["FortressoftheLions", "WorldsEnd", …]` | Usually `[""]`: 78 of 172 matches had maps. |
| `opponent` | `[{playerId: 169084, name: "Hexoo", …}]` | Two players in 2v2. The requested player's own partner is never included. |
| `startTime` | `null` | Null in 167 of 172 matches |

Legend and map names are uppercase identifiers (`RED_RAPTOR`, `LIN_FEI`) and CamelCase (`FortressoftheLions`).

## 2. Official vs community tournaments (critical)

**The API has one signal: `Tournament.isOfficial`.** There is also an `isOfficial` filter on ListEvents, GetPlayerPlacements, GetPlayerTeammates, GetPlayerLegends, GetMatchup and GetMatchupPlacements: `true` means official only, and the default (`false`) means everything. The docs define it as "true if the event was hosted by Blue Mammoth Games". There is **no** tier, major flag, prize pool, entrant count, circuit/season ID or points value on events.

`isOfficial=true` means "BMG-run or BMG-sanctioned", not "major". These are the 375 official 1v1 events, grouped by name. The rules are rough, so the counts are approximate.

| Family (by name) | 1v1 events | Years | Examples |
|---|---|---|---|
| Seasonal regional championships | 154 | 2017–2026 | "North America - Summer Championship 2022", "Autumn Championship - Europe 2026 - 1v1" (2v2 also has "… Doubles Championship") |
| Other: early league rounds, regional and sponsored one-offs | 54 | 2017–2021 | "BCS Summer Slam - NA (Week 1)", "SEA League (Week 2/4)", "Brawl League Masters (NA)", "Shine 2019", "MTN DEW AMP GAME FUEL Championship (NA)" |
| Qualifiers and last-chance qualifiers | 32 | 2017–2021 | "North America - Brawlhalla World Championship 2021 Last Chance Qualifier", "Brawl League Open Cup - Qualifier #1 (EU)" |
| "Trial of …" series | 30 | 2024 | "Trial of Freya - North America" (one 2017 "Trial of Legends" also matches) |
| Partner events | 28 | 2017–2025 | CEO, DreamHack, Combo Breaker (Online), Low Tier City, MAX MODE |
| Invitationals, cups, series | 28 | 2017–2022 | "SteelSeries Invitational 2022", "Mammoth Cup", "Pro Series 2021" |
| World Championship | 17 | 2017–2025 | "Brawlhalla World Championship Expo 2024", regional online Worlds in 2020 and 2021 |
| Team and novelty formats **filed under 1v1** (`isTwos: false`) | 15 | 2022–2026 | 6 crew battles ("Crew Battle Invitational", "Eternal Sports Crew Battle Championship 2026"), plus "Brawlhalla 3v3 Championship" and "Eternal Sports Triples / Brawlball Championship 2026". 2v2 also has 3 "Kung Foot" events. See the decisions below. |
| Royales | 9 | 2023–2025 | "Brawlhalla - Autumn Royale 2025" |
| Midseason Championship | 7 | 2020–2026 | "Midseason Championship 2026 1v1" |
| Community tournament flagged official | 1 | 2025 | "Brawlhalla Community Tournament #2" |

Naming is inconsistent across eras, so names alone will misclassify some events:

- The 2019 World Championship is stored as tournament "DreamHack Atlanta 2019", event "Brawlhalla World Championship 1v1".
- No 2018 event has "World Championship" in either name field.
- A community-run "Adaptation presents: Road to BCX" matches a naive "BCX" rule.

**Community events** are simply `isOfficial: false`, with nothing further to classify them. There are none before 2020, apart from three 2v2 events in 2019.

**Decisions**

- **A "major" is any event with `isOfficial: true`.** This includes the 2017–2018 league weeks and qualifiers.
- **Crew battles count as 1v1.** They are still 1v1 fights at their core. There are 6 official crew battle events, all filed under 1v1: "Crew Battle Invitational" (2022; its event is named "Brawlhalla Crew Battle 3v3") and "Eternal Sports Crew Battle Championship 2026", each in three regions. Raydish's six 1v1 majors include the 2026 NA Crew Battle Championship.
- **Other non-standard formats count toward neither 1v1 nor 2v2.** Officially that is 12 events:
  - "Brawlhalla 3v3 Championship" (2022);
  - "Eternal Sports Triples Championship 2026";
  - "Eternal Sports Brawlball Championship 2026";
  - "Eternal Sports Kung Foot Championship 2026" (filed under 2v2).

  Community events add Volleybrawl, Snowbrawl, Capture the Flag and Morph events, plus more Brawlball, Kung Foot and 3v3 ones. Names that merely contain such words (e.g. "MAX MODE 2025", "Brawl at the Beach") are normal 1v1/2v2 events.
- **A tournament split into phases counts once**, using the player's result in the last phase they reached. Only two official tournaments are split this way: Brawl League Masters Season 4 NA and EU (2018), each a Swiss stage plus a Top 8 Finals (§6). With this rule, Boomie's two "wins" there become one.
- **One official event is in the wrong mode:** CEO Dreamland 2017's 2v2 event (`tournament/ceo-dreamland/event/brawlhalla-doubles`) is filed under 1v1 with `isTwos: false`. It appears in 1v1 placement lists (Boomie's shows 9th) and should be treated as 2v2.

Because format and phases are only visible in names, these rules need a small, reviewed list of exceptions rather than a pattern alone. Blue Mammoth's own PR stats use a narrower rule: they also leave out crew battles (§3).

## 3. Prize money, earnings and medals

**Earnings**

- Earnings appear in exactly three places: `SearchPlayers[].earnings`, `GetPlayerPr.earnings` and `ListPr.prPlayers[].earnings`. There is no prize money per placement or event, and no prize pool.
- It is **one career total per player**. All 342 players listed in both the 1v1 and 2v2 PR lists have identical earnings in each. The currency isn't documented; it is presumably USD. Values like `214458.33` and `258984.17` suggest team prizes split between teammates.
- **Coverage gap:** GetPlayerPr returns `earnings: 0` for players without a current PR. Impala gets 0 there but `88095` from SearchPlayers, and ListPr only includes players on a regional PR list (Impala is absent). For inactive players, the only source of earnings is search, and search doesn't cover unranked players without a Challengermode account (§8). **Boomie's earnings are not available from any endpoint.**
- **Earnings live only on a player's PR row.** Other official routes give the same answer:
  - The old v1 API is still live, and returns the same figures: Boomie `0`, gdsandstorm `258984.17`.
  - The official rankings page (brawlhalla.com/rankings/esports) shows only the current PR list.
  - The former stats site, brawltools.com, no longer resolves in DNS.

  So players like Boomie can only be linked to earnings through an external source.
- **External sources and how they compare:**
  - **Esports Earnings** has Boomie at $210,282.67 (#2 all-time, behind Sandstorm). Its figures run below the API's for active players: Sandstorm $239,831 vs $258,984, Zivai $163,858 vs $214,458, Raydish $61,690 vs $83,825. For a player who stopped before the Challengermode switch they are close: Impala $84,730 vs $88,095. So it probably lacks recent official prize money, rather than counting differently.
  - It has an API: free registration with an API key, at most one request per second, and lookups by player ID, tournament history and top earners per game.
  - **Liquipedia** lists Boomie at $131,925, a different methodology again. That figure comes from search results; the site blocked automated fetching.

**Medals**

- **Decision: a medal is a top-3 placement (1st, 2nd or 3rd) at an official event.** Community events don't count. Bronze is placement 3 only, because double elimination has a separate 4th place. The format and phase rules from §2 apply.
- So medals are counted from GetPlayerPlacements. The API's own `gold`, `silver` and `bronze` fields don't fit that definition. Those fields, alongside `top8` and `top32`, appear in every PlayerPr: GetPlayerPr, ListPlayerPrs, ListPr rows, and SearchPlayers' `pr1v1`/`pr2v2`. They are per game mode and cover the player's whole history, but:
  - they leave out crew battles (and "Brawlhalla Community Tournament #2");
  - they are zero for anyone without a current PR. By our rules Boomie has 80 medals (1v1 12/11/11, 2v2 32/8/6) and Impala 7 (1v1 3/3/1), but both show all zeros.

  | Player (1v1) | PR gold/silver/bronze | Our medals | Difference |
  |---|---|---|---|
  | Raydish | 5/3/5 | 6/4/5 | Crew battles: 1st at the 2026 NA Crew Battle Championship, 2nd at the 2022 Crew Battle Invitational |
  | BBBalloonBoy | 2/7/5 | 2/8/5 | Crew battle 2nd (2026). His Triples and Brawlball silvers are excluded under both rules. |
  | Marckiem00 | 9/6/2 | 9/7/2 | Crew battle 2nd (2026) |
  | megD | 1/2/6 | 2/2/7 | Crew battle 1st (2026); 3rd at "Brawlhalla Community Tournament #2" |
  | Hexoo | 0/0/0 | 0/0/0 | none |

  In 2v2, our counts equal the PR fields for all five ranked test players.


**PR fields**

- `points` (ListPr only) is the current PR score; BBBalloonBoy has 528.718.
- `powerRanking` is the rank within a region. Inactive players keep a rank: gdsandstorm is #737 with 1.269 points.
- ListPr data is refreshed daily (`lastUpdated`).

## 4. Doubles data

- **Placements from a one-player query carry no teammate.** You get one row per player per 2v2 event (`isTwos: true`).
- **Team queries work.** Pass both IDs, e.g. `playerIds=142100,160000` (megD and Raydish).
  - GetPlayerPlacements returns exactly the 33 events they played together: best 2nd, 21 top 8s, 20 official.
  - The same works for GetPlayerMatches, GetMatchup (`entrant1PlayerIds=a,b`), GetMatchupPlacements and GetMatchupMatches, including team against team.
  - It does **not** work for GetPlayerPr ("Team PR not supported at this time") or GetPlayerLegends ("Only 1v1 supported at this time").
- **GetPlayerTeammates** gives partners only: `{player, games, lastTeamedDate}`.
  - `games` is the **number of events** together. megD's 26 partner rows sum to 101, her total number of 2v2 events.
  - Rows are sorted by `lastTeamedDate`, newest first. The docs say by frequency.
  - There is no per-event detail; use a team query for that.
- **2v2 matches:** `opponent` lists both opponents, and `scores` are per series.
- **GetMatchup for one player in 2v2** combines all of that player's partners, with opposing teams as `opponent` pairs. Example: megD against futurebubbles366 + Marckiem00 is 9–2 in matches.
- **Don't infer partners from equal placements.** megD and Raydish placed the same in 37 events, but only teamed in 33.
- **One person can have several player records.** megD's partner "hardymj" appears twice:
  - 145900, with start.gg and in-game IDs, last teamed in 2021;
  - 632566, with only a Challengermode ID, in 2025.

  In the survey sample, 5 of 512 names map to more than one `playerId`. It looks like Challengermode-era accounts aren't always merged with older ones.

## 5. Head-to-head data

- **GetMatchup with both entrants** returns one record, from entrant 1's side, with `opponent: null`.
  - Impala vs BBBalloonBoy in 1v1 is `matches: [2, 1]`, `games: [8, 4]`: Impala leads 2–1.
  - In 2v2 they have never played (`[0, 0]`).
  - `isOfficial=true` gives the same 1v1 record.
- **GetMatchup with entrant 1 only** lists every opponent with a record, e.g. Marckiem00 vs BBBalloonBoy is `matches: [20, 5]`, `games: [61, 38]`.
  - Rows are sorted by matches played, then games played, so frequent opponents come first.
  - **DQs are included** (see below). 38 of Marckiem00's first 200 rows visibly contain a `-1`.
  - **Paging bug:** the page token is `<matches played>-<games played>-<opponent ID>`. Once the sort reaches rows with negative game totals, the token (`"0--2-149267"`) is rejected with 400 "Invalid next token". For Marckiem00 the list stops at 200 opponents.
- **GetMatchupPlacements** lists every event both entrants entered, with both placements, whether or not they played each other.
  - Impala and BBBalloonBoy shared 32 1v1 events (e.g. WCX 2024: `[7, 5]`) and 4 2v2 events.
- **GetMatchupMatches** returns their matches in one event: scores, legends and maps only, or an empty array if they didn't meet.
  - Their WCX 2024 set was `[2, 3]` (start.gg set `82392891`).
  - Finding all their sets takes one call per shared event (32 here).
- None of these say which round a match was in.

**DQs (decision: a DQ counts as neither a win nor a loss)**

- In match data, the DQ'd side's score is `-1` and the other side's is `0`. For example, Marckiem00 vs sub_lemon at Moose Wars: Gobble Gauntlet (2023), start.gg set `67607493`, has `scores: [0, -1]`: sub_lemon was DQ'd.
- GetMatchup counts that DQ as a match win for Marckiem00 and adds the `-1` into the game totals. His record against sub_lemon is `matches: [2, 0]`, `games: [3, -1]`: one real 3–0 plus the DQ. A DQ can even vanish from an aggregate, since a real 3–1 plus a DQ sums to 3–0 in games.
- **So head-to-head records must be built from match-level data, dropping any match with a negative score.** Use GetPlayerMatches for each event in a player's placements, or GetMatchupMatches for each event a pair shared. This also avoids the matchup paging bug.

## 6. Bracket fields and original IDs

**Bracket fields**

- **Not present anywhere:** round, seed, bracket side (winners/losers), phase, pool, set order, entrant count.
- Match `startTime` exists but was null for 167 of 172 matches; the only non-null values came from one Challengermode community event.
- **Placements use double-elimination numbering** (1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, …, 2049). So a placement tells you roughly how far a player got, but not their path through the bracket.
- **Some start.gg "events" are really bracket phases:** `tournament/brawl-league-masters-season-4-na-1/event/swiss`. These can double-count results: Boomie "won" both the "NA Swiss" phase and the "Top 8 Finals" of Brawl League Masters Season 4 (NA) in 2018. Under the §2 decision, such a tournament counts once, using the last phase reached. Grouping by start.gg tournament slug doesn't find phases in general. Of 93 start.gg tournaments with several events in one mode, 60 are regional splits and most of the rest are leagues or series of separate competitions; only 3 look like phases. So phase splits need an explicit list.

**Original IDs** (useful for pulling brackets from start.gg or Challengermode later):

- **`Tournament.id`** is either:
  - a start.gg event slug. That is the identifier start.gg's API and URLs use (`https://www.start.gg/tournament/…/event/…`; I haven't checked one).
  - a Challengermode tournament UUID. Verified: `challengermode.com/s/Brawlhalla/tournaments/fcb7a286-3f0c-4f68-f9a5-08ded4cb1c05` opens "Autumn Championship - North America 2026 - 1v1".
- **`matchId`** is either a start.gg set ID (`"82392891"`) or a Challengermode match UUID.
- **Player IDs:** `sggPlayerId`, `cmPlayerId` and `brawlhallaId` on top-level Player objects. They are null inside matches and matchups, so look them up with ListPlayers.

## 7. Date range and the Challengermode era

The full ListEvents crawl returned 1,107 1v1 and 656 2v2 events.

- **Oldest:** 2017-02-04, "Brawlhalla US/EU Winter Championship (Online)". The `year` filter returns nothing for 2014–2016 or 2027.
- **Newest:** 2026-09-27, "Autumn Championship - North America 2026 - 2v2".

| Year | 1v1 official | 1v1 community | 2v2 official | 2v2 community | Host |
|---|---|---|---|---|---|
| 2017 | 64 | 0 | 17 | 0 | start.gg |
| 2018 | 32 | 0 | 20 | 0 | start.gg |
| 2019 | 43 | 0 | 25 | 3 | start.gg |
| 2020 | 50 | 67 | 46 | 39 | start.gg |
| 2021 | 35 | 188 | 25 | 89 | start.gg |
| 2022 | 33 | 243 | 24 | 152 | start.gg |
| 2023 | 28 | 102 | 24 | 66 | start.gg |
| 2024 | 33 | 75 | 19 | 38 | start.gg |
| 2025 | 27 | 42 | 23 | 15 | start.gg to June, then Challengermode (1v1: 10 SGG + 59 CM) |
| 2026 (to Sep) | 30 | 15 | 24 | 7 | Challengermode only |

- **The Challengermode era is present.**
  - The first Challengermode event is a community one on 2025-04-04. The first official one is "Spring Championship - Southeast Asia 2025" on 2025-05-09.
  - The last start.gg event of any kind is **CEO 2025 (2025-06-14)**.
  - Official CM events look complete; for example, the 2026 Summer and Autumn Championships appear for all five regions (NA, EU, SA, SEA, Middle East).
- **Community coverage is thin after the switch**: 15 community 1v1 events in 2026, against 243 in 2022. Any community events run on start.gg after June 2025 are not in the API at all.

## 8. SearchPlayers and name variations

| Variation | Queries | Result |
|---|---|---|
| Names as given | "Raydish", "Impala", "megd" | Found ("megd" returns "megD" plus 9 other players) |
| | "Boomie" | Only "Inboomie Noodles", an unrelated player. The real Boomie (146606) isn't in the search index. |
| | "Hexo" | "Hexoo" plus 6 others |
| | "Balloonboy" | Only "BBBalloonBoy" |
| | "marckiemoo" | **Nothing** |
| Wrong capitalization | "BOOMIE", "boomie", "RAYDISH", "rAyDiSh", "IMPALA", "MEGD", "bbballoonboy", "HEXOO" | Same results as the correctly cased names. **Case-insensitive.** |
| A missing letter | "balonboy", "Ballonboy", "BBBalonBoy" → BBBalloonBoy; "Raydsh" → Raydish; "Impla" → Impala (plus 3 others) | **Found** |
| Swapped letters | "Radyish", "Imapla" | Nothing |
| A wrong letter | "Hexxo", "megf", "Marckiem0o" | Nothing (not even Hexoo, megD or Marckiem00) |
| Partial names | "Balloon", "Rayd", "dish", "Hex", "Imp", "pala", "meg", "Marckie", "Boom" | Target found, often among many (e.g. "Hex" gives 25 results with Hexoo first) |
| Team tag | "Pink" | 25 "Pink \| …" players |
| | "Guichabou" | Finds "Pink \| Guichabou" |
| Full name with tag, or a trailing space | "ECHO \| Marckiemoo", "Raydish " | 400 "Query must match regular expression [\w.,]+" |
| Limits | `maxResults=50` / empty query | 400 "Max results cannot be greater than 25" / 400 "required". `nextToken` is always null, so there is no second page. |

Inferred behaviour:

- **Coverage: only players who are currently ranked or have a Challengermode account.**
  - All 49 search results without a Challengermode ID had a current PR.
  - Boomie (exact name "Boomie", no PR, no Challengermode account) is never returned.
  - Impala has no PR but does have a Challengermode account, and he is returned.

  So inactive start.gg-era players, including some of the most successful ones, can only be found through other players' data (opponents, teammates) or by ID.
- **Matching:** case-insensitive *subsequence* matching ("the query's letters appear in order in the name"). That explains why dropped letters work and swapped or wrong letters don't. A few results don't fit, such as "ZOOM" for "Boom" and "zyder" for "Rayd". So it probably also searches names the response doesn't show, such as start.gg or Challengermode names.
- **Current names only.** Old names don't match: the docs' "ECHO \| Marckiemoo" is now "Marckiem00" with zeros, so "marckiemoo" fails.
- **Ranking:** players ranked in 1v1 come first, in PR order, then players ranked only in 2v2, then unranked players by ID. With a cap of 25 and no paging, unranked players can't be reached through short, common queries.
- **Allowed characters:** only letters, digits, `_`, `.` and `,`. Names with spaces, `|`, `-`, `!` or non-ASCII characters ("Moni-", "Shade 王") can only be found by a fragment.
- **For the agent:** player lookup should run against our own player table, not the API's search.
  - Build that table from every Player object ingestion sees: placements, opponents, teammates and matchups. That's how Boomie was found.
  - Add an alias table for names people actually use ("marckiemoo" → Marckiem00), since there will be more cases like it.
  - Then strip tags and punctuation, try fragments, and ask the user when a match is ambiguous.

## 9. Can the API answer the target questions?

| Question | Answerable? | Endpoints and fields | What the survey found and caveats |
|---|---|---|---|
| What was the last tournament Boomie entered? | **Yes**, once Boomie is resolved through our own player table (search can't find him) | GetPlayerPlacements for `gameMode` 1 and 2. The first row of each is the newest; take the later `tournament.startTime`. | Winter Doubles Championship - North America, 2024-03-10: 2nd place in 2v2. His last 1v1 event was BCX 2023. Caveat: start.gg events after June 2025 aren't in the API. |
| How many majors has Raydish won? | **Yes** (majors = `isOfficial`) | GetPlayerPlacements (`isOfficial=true`, both modes), count `placement == 1` | 6, all in 1v1: NA Summer Championship 2022, NA Winter Championship 2023, three "Trial of …" events (2024), and the 2026 NA Crew Battle Championship (crew battles count as 1v1). No 2v2 majors. |
| Has Hexo ever placed top 8 in 1v1? | **Yes** | GetPlayerPlacements (`gameMode=1`, all pages), any `placement <= 8` | Yes, 8 times. Only one was a major: 5th at "Brawlhalla Community Tournament #2". |
| What does Impala vs Balloonboy's history look like? | **Yes**, using match-level data for exact records | GetMatchupPlacements for shared events, then GetMatchupMatches for each one, dropping DQs. GetMatchup gives a quick record, but it includes DQs. | GetMatchup: Impala leads 2–1 in matches and 8–4 in games across 32 shared 1v1 events; he lost the WCX 2024 set 2–3. They never played each other in 2v2 (4 shared events). The exact DQ-free record takes 32 calls. No round information. |
| List the top 10 highest-earning players in Brawlhalla history. | **No, not completely** | ListPr for 5 regions × 2 modes with `orderBy=earnings DESC`, merged by `playerId`; SearchPlayers for individual names | Earnings exist only for currently ranked players (ListPr, GetPlayerPr) and search-indexed ones (SearchPlayers). Boomie has no earnings figure anywhere, and Impala ($88,095) only through search. Ranked top 10 today: gdsandstorm 258,984; Zivai 214,458; acno? 189,215; whoiskyna 161,110; SiB \| Wess 131,482; yüz 131,422; Blaze 120,208; loreszz 102,600; lFiend 94,262; Raydish 83,825. A complete all-time list needs an external source; Esports Earnings has Boomie at #2 with $210,283 (§3). |
| Who has megd played with in 2v2 tournaments, and how did they place? | **Yes** | GetPlayerTeammates(megD) for partners and event counts; GetPlayerPlacements(`playerIds=megD,partner`, `gameMode=2`) per partner | 26 partner rows (25 names; "hardymj" is split across two IDs). Raydish 33 events (best 2nd), buko pandan 14, Walshy 5, Moni- 5, … One placements call per partner. |
| How many medals does Balloonboy have? | **Yes** (medals = official top-3 placements) | GetPlayerPlacements (`isOfficial=true`, both modes), count `placement <= 3` after applying the format rules (§2) | 27: in 1v1, 2 gold, 8 silver, 5 bronze; in 2v2, 5/3/4. His Triples and Brawlball silvers don't count; his crew battle silver does. The PR fields show 2/7/5 for 1v1. |
| Who has the best record against marckiemoo? | **Yes**, using match-level data | GetPlayerPlacements for Marckiem00's events, then GetPlayerMatches for each one (65 in 1v1). Drop DQs, group by opponent, and rank by win rate. | GetMatchup can't be used as is: it counts DQs, and its paging stops at 200 opponents. "Best" also needs a minimum number of matches, and a choice between official-only and all events. |

## 10. Incomplete, inconsistent or surprising

**The docs don't match the API**

- start.gg `Tournament.id` is an event slug, not a number.
- ListEvents still needs `gameMode`: omitting it returns 500, although the v2.1 notes say it became optional.
- SearchPlayers is capped at 25 results and never paginates (the docs attach the limit to `nextToken`).
- GetPlayerTeammates is sorted by date, not frequency, and its `games` field counts events.
- `PlayerMatches.startTime` (added in v2.1) is almost always null.
- ListPr: LAN is documented but returns no rows. AUS, JPN, BRZ and ALL give 400 "Invalid region".
- GetMatchupMatches needs `entrant2PlayerIds`.
- Doc examples still use v1 field names (`smashId`, `slug`).

**API bugs**

- **Timestamp page tokens drop tied events.** ListEvents and GetPlayerPlacements use the last row's `startTime` as `nextToken`, and the next page starts strictly *before* it. When a page boundary fell between two events with the same `startTime` (the Brawl League Masters Season 4 EU and NA events, both `1534600800`), page 2 skipped the second one. Ingestion should, for example, re-request from `startTime + 1` and de-duplicate by `id`, or cross-check with per-year crawls.
- **Matchup page tokens fail on DQ records** (§5).

**Data quality**

- `isOfficial` is broad, and 3v3, crew battle, triples and Brawlball events are filed under 1v1 with `isTwos: false` (§2).
- At least one 2v2 event is filed as 1v1: CEO Dreamland 2017's doubles (§2).
- Duplicate identities across platforms ("hardymj"), and renamed players (§4, §8).
- DQs appear as `-1` game scores and count as wins and losses in GetMatchup records, so they have to be filtered out of match-level data (§5).
- Search only covers ranked or Challengermode-linked players, so inactive start.gg-era players such as Boomie can't be found by name (§8).
- Bracket phases stored as separate events can double-count results (§6).
- Nested Player objects lose `sggPlayerId` and `cmPlayerId`.
- Legends and maps exist for only a minority of matches. Challengermode matches have them more often than start.gg ones.
- Coverage: nothing before February 2017; no community events before 2020; start.gg stops in June 2025; Challengermode community coverage is thin (§7).
- No event endpoint: no standings, entrants, entrant counts or prize pools.
- Earnings exist only for ranked or search-indexed players, so some players' earnings (Boomie's) aren't available at all. There is no per-event prize money (§3).
- Unranked players come back as zeros in GetPlayerPr but as nulls in SearchPlayers.
- ListPlayerPrs with `region` returns null entries instead of filtering them out.

**SDK quirks**

- It turns 404 into `null` or an empty list, so "not found" and "no results" look the same, and errors come back as message strings without the status code.
- It has a 5-second timeout and no retries, and `getPlayerLegends` prints errors to the console.
- Its TypeScript types lag behind the API: they lack `startTime`, `country`, `lastUpdated` and the `region` parameter. They also include fields that never appear: `pronoun`, and `twitter`/`twitch` on ListPr rows.

**Operations**

- No auth and no rate-limit headers (it sits behind AWS API Gateway). Five full runs of about 300–340 requests each, at roughly one request per second, never hit throttling. Median latency was 180–260 ms per run; the slowest request took 1.1 s.
- Players have no endpoint to enumerate them. ListPr pages (about 1,200 ranked NA 1v1 players) and teammate or matchup lists are the only ways to discover IDs in bulk.

## Open questions

**Settled:**

- Majors are `isOfficial` events.
- Medals are top-3 placements at official events.
- Crew battles count as 1v1; other non-standard formats count toward neither mode.
- A tournament split into phases counts once.
- DQs count as neither a win nor a loss.
- Hexo is Hexoo, and "marckiemoo" means Marckiem00.

**Still open: earnings for players without a PR row, such as Boomie.**

Proposal:

- Keep the API's figure wherever it exists, and fill the gaps from Esports Earnings through its API.
- Store each value with its source and date, so the agent can say which one it's quoting.
- Link players by in-game handle, confirmed by country and Twitter/Twitch handles where both sources have them, plus a hand-checked mapping for the rest.

Prerequisites: an Esports Earnings API key, which you'd register for, and a check of their Development Area terms.

The catch is that the two sources aren't on the same scale, so an all-time ranking that mixes them compares different methodologies. The alternative is to rank everyone by Esports Earnings alone, and use the API's figure only for "official earnings" questions.
