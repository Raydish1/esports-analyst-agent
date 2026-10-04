# start.gg and Challengermode API survey

What the start.gg and Challengermode APIs can add on top of the Stats API ([`api-survey.md`](api-survey.md)): bracket structure, entrants and standings, and prize information. This is input for the schema in [`schema-proposal.md`](schema-proposal.md), which hasn't been changed yet.

- **Scripts:** [`ingest/survey_platforms.py`](../ingest/survey_platforms.py), with the API clients in [`ingest/platform_clients.py`](../ingest/platform_clients.py).
- **Credentials:** `STARTGG_API_TOKEN`, `CHALLENGERMODE_REFRESH_KEY` and `CHALLENGERMODE_APP_ID`, read from `.env` (see `.env.example`). They are never printed or written to disk, and the Challengermode access token is redacted from the saved token-exchange response.
- **The run, 2026-10-04 (UTC):**
  - start.gg: 110 requests, at least 1 s apart.
  - Challengermode: one token exchange plus 26 GraphQL requests, at least 3.5 s apart.
  - Stats API: 4 requests, for comparison.

  Every response is in `data/raw/platforms/{startgg,challengermode,statsapi_compare}/` (git-ignored), with a `_manifest.json` per folder.
- **Test cases:**
  - start.gg: BCX 2022 1v1 and 2v2, and the NA Winter Championship 2025 1v1.
  - Challengermode: Autumn Championship - North America 2026 - 1v1 (`fcb7a286-…`).
  - Players: Raydish, Boomie, Marckiem00, megD and Impala by their start.gg IDs; Raydish, Marckiem00, megD, Hexoo and Impala by their Challengermode IDs.

## Key takeaways

1. **Both platforms have the bracket structure and full standings that the Stats API lacks.**
   - start.gg: phases → pools → sets, each with a round number, winners/losers side, round name, seeds, and per-game stages and characters in the late phases.
   - Challengermode: stages → upper, lower and grand-finals brackets → rounds → match series, with an ordinal, seeds and placement ranges.
2. **Match IDs line up, so platform data can attach to existing match rows.**
   - The Stats API's `matchId` *is* the start.gg set ID (14 of 14 checked).
   - It is also the Challengermode **match** ID (not the match-series ID).
   - Scores agree exactly.
3. **Prize data is available on both platforms, in different forms.**
   - start.gg has structured per-placement payouts (`Event.prizingInfo`).
   - Challengermode's API has no prize fields at all, but official tournaments' descriptions contain a PRIZESPLIT text block. 10 of 11 sampled official events had one, and 9 of those 10 add up to the stated total.
   - BCX 2025 only states "$200,000 prize pool" and links to brawlhalla.com.
4. **DQs look different on each platform.**
   - start.gg uses −1 vs 0, the same as the Stats API. 29% of BCX 2022's 1v1 sets were DQs.
   - On Challengermode a no-show is a match with **no scores**, and the Stats API reports it as **0–0**, not −1.
   - Decided: forfeits, like DQs, count as neither a win nor a loss.
5. **Players link directly.**
   - A start.gg participant's player ID is the Stats API `sggPlayerId`.
   - A Challengermode lineup member's user ID is the Stats API `cmPlayerId`.
   - start.gg also records the name each player used *at each event*, a ready source of former names.
6. **start.gg has 369 Brawlhalla tournaments (467 events) since June 15, 2025 that the Stats API doesn't.** All are community-run; none is on Blue Mammoth's start.gg account. That doesn't affect the official-only scope.
7. **Practical limits:**
   - start.gg rejects queries over 1,000 objects.
   - Challengermode tokens last 20 minutes.
   - Challengermode's Cloudflare front end blocks Python's default user agent.
   - Challengermode's tournament lists are capped (about 48 results, no paging). So official events should still be listed from the Stats API, with each platform queried by ID.

## Checking the hints

| Hint | Exists? | What was found |
|---|---|---|
| start.gg `prizingInfo` on Event | **Yes** | `Event.prizingInfo: JSON`, "TO settings for prizing" (live introspection). |
| start.gg `prizingInfo` on Tournament | **No** | Tournament has `currency` and a free-text `rules` field only. |
| start.gg Event tier field and its values | **Exists, but carries no information** | `Event.competitionTier: Int`, "Rough categorization of event tier, denoting relative importance in the competitive scene". It's a plain integer, not an enum, so the schema lists no values. Every Brawlhalla event checked (all 470) has `5`. A separate `EventTier {id, name}` type exists only for league application tiers (`League.tiers`), not on events. |
| start.gg standings fields | **Yes** | `Event.standings(query: {page, perPage, sortBy, filter})` returns `{pageInfo, nodes: [Standing]}`. A Standing has `placement`, `isFinal`, `entrant`, `player`, `metadata`, `stats { score }`, `totalPoints`, `setRecordWithoutByes` and `container`. Standings also exist on `PhaseGroup` and `League`, and per entrant as `Entrant.standing`. |
| Challengermode `tournamentsForSpace` | **Yes** | `tournamentsForSpace(input: {spaceId!, tournamentFilter!, gameSettingFilters, includeInviteOnly, includeUnlisted}): [Tournament!]!`. It works with a bot token but looks capped (§ Challengermode 7). |
| Challengermode prizing or rewards fields on tournaments | **No** | With authentication, the schema has 271 types, and no type, field, input or enum value has a prize-like name or description. The only free text is `Tournament.description` (and `Cup.description`). |

## start.gg

### 1. Auth and rate limits

- **Endpoint:** `POST https://api.start.gg/gql/alpha`, with `Authorization: Bearer <token>`.
  - Without a valid token every request fails with HTTP 400 `{"success": false, "message": "Invalid authentication token"}`, introspection included.
  - With a token, introspection works (145 types).
- **Rate limits:** all 110 requests at 1 s gaps returned 200, with no throttling. The responses carry no rate-limit headers.
- **Complexity:** each response reports `extensions.queryComplexity` (the highest seen was 881). start.gg rejects queries over 1,000 objects, so page sizes have to stay small: 64 standings, 40 sets, or 16 sets with games per request worked.
- **Latency:** median about 1 s; set pages took 1.3–3 s.

### 2. Bracket structure

| Level | Fields | Example |
|---|---|---|
| Phase | `name`, `phaseOrder`, `bracketType` (`DOUBLE_ELIMINATION`, `SINGLE_ELIMINATION`, `ROUND_ROBIN`, `SWISS`, …), `numSeeds`, `groupCount` | BCX 2022 1v1: Phase 1 Pools (603 seeds, 32 pools) → Phase 2 Pools (128, 8) → Phase 3 (32) → Finals (8), all double elimination. NA Winter 2025: Bracket (450 seeds, 16 pools) → Top 128 → Top 32 → Top 8. |
| Pool (`PhaseGroup`) | `displayIdentifier` (`A8`, `C8`, …), `bracketUrl`, `rounds { number bestOf }` | NA Winter 2025 has round best-ofs (Bo3 in pools, Bo5 later); BCX 2022's are empty. |
| Set | `round` (positive = winners side, negative = losers side), `fullRoundText` ("Winners Round 1", "Losers Quarter-Final", "Grand Final"), `identifier` (letter code within the pool, e.g. `AF`), `wPlacement` / `lPlacement`, `winnerId`, `slots` (entrant, seed, per-slot score), `entrant1Source`/`entrant2Source`, `startedAt`/`completedAt`, `vodUrl` | BCX 2022 1v1 has 1,204 sets, rounds −8…−3 and 1…4. No VOD links. |
| Seed | `seedNum`, `placement`, `isBye`, `entrant`, `phaseGroup` | BCX 2022 1v1: seed 1 HyP \| luna (pool A8), seed 3 nSig \| Raydish. |
| Game | `orderNum`, `winnerId`, `entrant1Score`/`entrant2Score`, `stage`, `selections` (character per entrant) | Filled in the late phases: BCX 2022 1v1 Finals, 43 games, all with stage and characters (e.g. Caspian vs Asuri on Small Fortress of Lions). 2v2 Finals has stages but no characters. |

- **Bracket side** comes from the sign of `round`, plus `fullRoundText` for the grand final.
- **Set order** within a pool comes from `identifier`, and `sets(sortType: ROUND)` returns sets in bracket order.
- `Set.totalGames` is 5 on every set, Bo3 pools included, so the best-of has to come from `Round.bestOf`.

### 3. Entrants and standings

- **`numEntrants` counts registrations, not players who played.** It's 603 for BCX 2022 1v1 and 198 for 2v2. NA Winter 2025 shows 992, but only 450 were seeded and placed. Entrant counts should come from standings.
- **`Event.standings` lists every placed entrant:** 603, 198 and 450 rows respectively, with two participants per row in 2v2.
  - Placements follow double elimination: 1, 2, 3, 4, 5, 7, 9, 13, …, 513.
  - Each row has the entrant **name as shown at that event**, with team tag (e.g. "Kingdom \| Godly"), plus `initialSeedNum` and `isDisqualified` (116 entrants at BCX 2022 1v1).
  - Each participant has a `player.id`, which is the Stats API `sggPlayerId`. Every row had one.
- Results: BCX 2022 1v1 went Impala, Kingdom \| Godly, HyP \| luna. 2v2 was won by Snowy / Boomie.

### 4. Prize money

- **Structured, per placement.** When `enablePrizing` is true, `prizingInfo.prizing` lists `{placement, amount, percent}` for each paid place, with `payoutType: "fixedAmount"`. The currency is `Tournament.currency` (USD).

  | Event | Paid places | Total | 1st |
  |---|---|---|---|
  | BCX 2022 1v1 | 128 | $250,000 | $50,000 |
  | BCX 2022 2v2 | 64 | $250,000 | $60,000 (presumably per team) |
  | NA Winter Championship 2025 1v1 | 12 | $5,000 | $1,600 |

- An earlier page-based sample ([`schema-proposal.md`](schema-proposal.md) §6b) found structured payouts on 14 of 19 official start.gg events: everything sampled from 2019 on, except MAX MODE 2025.

### 5. Sets compared with the Stats API

- **IDs:** the Stats API `matchId` is the start.gg set ID. All 14 Stats API matches checked at BCX 2022 1v1 (Impala's 10, and 4 for a player with several DQs) have a set with the same ID.
- **Scores** agree, seen from the requested player's side. Impala's grand final is `[3, 1]` in the Stats API and "Impala 3 - Kingdom \| Godly 1" on start.gg.
- **DQs:** start.gg shows `displayScore: "DQ"`, with slot scores −1 and 0, which is exactly the Stats API's −1.
  - BCX 2022 1v1: 352 of 1,204 sets (29%).
  - BCX 2022 2v2: 50 of 394.
  - NA Winter 2025: 97 of 898, including 4 double DQs (−1 / −1) and 7 with −1 against no score.
- **What start.gg adds per set:**
  - round and side, round name, pool and phase;
  - both seeds;
  - per-game stages and characters in late phases;
  - the names players used at the event. The Stats API shows current names: "Kingdom \| Godly" is now "Zivai", "Pier" is now "antireplay".

### 6. URL formats (all checked to load)

| What | URL |
|---|---|
| Tournament | `https://www.start.gg/tournament/<slug>`. `Tournament.url` returns it relative; `url(relative: false)` returns it absolute. |
| Event | `https://www.start.gg/tournament/<t>/event/<e>`, which is the Stats API event ID prefixed with the host |
| Event brackets | `…/event/<e>/brackets` |
| One phase | `…/event/<e>/brackets/<phaseId>` |
| One pool | `…/event/<e>/brackets/<phaseId>/<phaseGroupId>`. `PhaseGroup.bracketUrl` returns this with `events` (plural); the singular form also works. |

The three `series/…` events (the Pro Series finals) have no working URL (api-survey §10).

### 7. Brawlhalla events after June 2025

- **Volume:** `tournaments(filter: {videogameIds: [15], afterDate: 2025-06-15, past: true})` returns **369 tournaments with 467 Brawlhalla events**, dated 2025-06-20 to 2026-10-02 (356 completed, 10 active, 101 created).
- **None is Blue Mammoth's:** none is owned by the start.gg account that owns BCX 2022 (`user/150c13a9`). The championship-sounding names are community series, such as "Final Hit: Spring Championship 2026", "Brawlhalla Israel 2026 Championship" and "Platfight Gaming Championships Online".
- **Size:** mostly small. 53 events have at least 32 entrants, 8 have at least 64, and one has at least 128 ("Guerre au sommet", 220).
- **Missing from the Stats API:** all of them. Its last start.gg event is CEO 2025 (2025-06-14). Player histories show the same gap: megD's and Raydish's recent start.gg standings include Galaxy Cup and Platfight events from late 2025.
- **Scope:** with official events only, this doesn't matter. It would if community events were added.

### Players

`player(id)` returns `gamerTag`, `prefix` (current team tag), `recentStandings` (event and placement), and a full `sets` history across every start.gg event: 1,734 sets for Boomie, 2,366 for megD, 1,821 for Raydish.

## Challengermode

### 1. Auth and rate limits

- **Token exchange:** `POST https://publicapi.challengermode.com/mk1/v1/auth/access_keys` with JSON `{"refreshKey": "<refresh key>"}` returns `{"value": "<access token>", "expiresAt": "…"}`.
  - Every exchange gave a lifetime of **1,200 s (20 minutes)**.
  - The client refreshes 2 minutes before expiry, and retries once after a 401 or `AUTH_NOT_AUTHENTICATED`.
  - The endpoint isn't in the GraphQL schema or the official .NET SDK. I found it from its validation error: an empty body returns 400, "The PackedRefreshKey field is required".
- **App ID:** `CHALLENGERMODE_APP_ID` wasn't needed for the token or for any query.
- **User agent:** Cloudflare in front of the API rejects Python's default user agent with HTTP 403 ("error code: 1010"). A custom `User-Agent` header works.
- **GraphQL:** `POST https://publicapi.challengermode.com/graphql` with `Authorization: Bearer <access token>`.
  - Schema introspection works without a token, with the same 271 types either way.
  - Data queries without a token return `AUTH_NOT_AUTHENTICATED`.
- **Rate limits:** all 26 queries at 3.5 s gaps returned 200, with no rate-limit headers (only `Date` and `x-request-id`). Even the whole 1,023-series bracket came back in one request, in about 1 s.

### 2. Bracket structure

| Level | Fields | Example (Autumn Championship NA 2026 1v1) |
|---|---|---|
| Stage | `index`, `format` (`DOUBLE_ELIMINATION`, `SINGLE_ELIMINATION`, `SWISS`, `ROUND_ROBIN`), `lineupCount`; elimination, group and Swiss stage types | One double-elimination stage with 512 slots |
| Bracket | `title`, `labels`: `DOUBLE_ELIMINATION_UPPER_BRACKET`, `…_LOWER_BRACKET` or `…_FINALS_BRACKET` (the **bracket side**) | Upper bracket, 9 rounds; Lower bracket, 16; Grand finals, 2 (a bracket reset) |
| Round | `roundNumber`, `title` ("Upper Round 1", "Lower Semi finals"), `labels` (`QUARTER_FINALS_ROUND`, `SEMI_FINALS_ROUND`, `FINALS_ROUND`), `matchCount`, `isLastRound` | Upper Round 1 has 256 series |
| Match series | `id`, `ordinal` (1–1023, the **set order**), `state` (`COMPLETED`; `NULLIFIED` exists), `bestOf`, `lineups` (with `seed`), `results` (series win 1, loss 0) | `bestOf` is 1 for all 1,023 series |
| Match | `id`, `state`, `lineups` (with `missedReadyCheck`), `results` (the **game score**, e.g. 3–1) | One match per series |

- **Matches carry the scores.** For Brawlhalla, a Challengermode *match* is the set, and its result is the game score. The series around it is just a best-of-1 wrapper, and there's no per-game data.
- **Byes:** with 284 entrants in a 512-slot bracket, 356 series had one lineup and 100 had none.

### 3. Entrants and standings

- **Attendance:** `confirmedLineupCount` 284, `availableSlotCount` 228, `roster.lineupCount` 284.
- **Roster:** `roster.lineups(limit)` returned all 284 lineups. Each has a `name`, `seed`, `preSeed`, `disqualified`, `placement {bestPlacement, worstPlacement, displayPlacement}` and `members` (user ID, username, game account ID).
- **Placements are ranges,** such as "5 - 6" and "193 - 256". `bestPlacement` matches the Stats API's numbering (1, 2, 3, 4, 5, 7, 9, 13, …). The winner was LGN \| BBBalloonBoy.
- **Lineup names are party names** ("megD's party"), so players should be identified by their members' user IDs (= Stats API `cmPlayerId`).
- **No disqualified lineups** in this event.

### 4. Prize money

- **No structured data.** No field anywhere in the API holds prize money.
- **Free text.** Official tournaments' `description` has a line like `+ **Prizes:** _$5,500_` and a PRIZESPLIT block:

  ```
  **PRIZESPLIT**
  + **1st** $2000
  + **2nd** $1000
  + **3rd** $700
  + **4th** $500
  + **5th** $250
  + **5th** $250
  ...
  ```

  - **Coverage:** of 11 official events checked (2025–2026; regional championships, crew battle, triples), 10 have a split.
  - **Totals:** in 9 of those 10 the split adds up to the stated total. Spring Championship SEA 2025 1v1's split sums to $2,000 against "$4,000", probably the whole championship's pool.
  - **Exception:** BCX 2025 1v1 has no split, only "$200,000 prize pool" and a link to brawlhalla.com/news/bcx2025.
- **Mapping to players works:**
  - Split lines repeat for shared places (two 5th places).
  - A line's placement is a lineup's `bestPlacement`, so each lineup gets the amount for its best placement.
  - None of the 2v2 texts says whether amounts are per team or per player. Decided: they are per team, and each player gets half.
- **Text quality:** descriptions are reused between events. The Autumn NA 2026 text says the bracket "will begin on Sunday, July 19th".

### 5. Matches compared with the Stats API

- **IDs:** the Stats API `matchId` is the Challengermode **match** ID, not the series ID. For example, `f706f954-…` resolves to "Autumn Championship - North America 2026 - 1v1 - Match 484", Raydish 0 – Hexoo 3, the same score as the Stats API. Looking it up as a match series returns "not found".
- **No-shows:** a match can be final with **no scores at all**: both `null`, no placement, no missed ready check. An example is Raydish vs mekhi! (Match 397).
  - The Stats API reports that match as `[0, 0]`, against a player it names "user82943".
  - So **Challengermode-era forfeits appear as 0–0 in the Stats API, not −1.**
  - The 0–0 doesn't say who advanced; the series result (1/0) does.
  - Decided: forfeits count as neither a win nor a loss.
- **What Challengermode adds:** bracket side, round title and labels, set order (`ordinal`), seeds, placement ranges and the series ID. Unlike start.gg, it has no per-game data.

### 6. URL formats (all checked to load)

| What | URL |
|---|---|
| Tournament | `links.overviewUrl` is `https://www.challengermode.com/tournaments/<uuid>`, which redirects to `https://www.challengermode.com/s/Brawlhalla/tournaments/<uuid>`. Both work. |
| Matches | `…/tournaments/<uuid>/matches`. There's no separate bracket page (`/bracket` and `/brackets` return 404). |
| User | `UserProfile.profileUrl`, i.e. `https://www.challengermode.com/users/<uuid>` |

### 7. Listing tournaments

- **`tournamentsForSpace` is capped.** For the official "Brawlhalla Esports" space (`30e5b4f0-…`, slug `Brawlhalla`, verified), "completed after 2025-01-01" returned **48** tournaments.
  - All 48 are official and already in the Stats API.
  - But they only cover Feb–Sep 2026, and some 2026 events are missing (e.g. Winter Championship - Southeast Asia 2026 - 1v1).
  - With "after 2026-06-01" it returns 26. So the list is capped at around 48–50 results, with no paging.
- **`tournamentsForGame`** (`gameSlug: "brawlhalla"`) returned 47 tournaments completed since 2026-09-01: 10 from Brawlhalla Esports, the rest small community events.
- **Conclusion:** keep listing official events from the Stats API, and query Challengermode by tournament UUID.

### Players

`user(userId)` returns `username`, `profileUrl`, `connectedAccounts` (e.g. Twitch), and `gameAccounts`. The Brawlhalla game account has a UUID `id` and an in-game display name ("Raydish_", "MegDDDD", "vImpala"). That UUID is **not** the Stats API's numeric `brawlhallaId`.

## Changes `schema-proposal.md` would need (not made yet)

1. **Matches.**
   - State what `matches.match_id` holds: the start.gg set ID, or the Challengermode **match** ID (both confirmed).
   - Keep Challengermode's series ID separately, in the bracket extension.
2. **DQs and forfeits.** Decided: forfeits, like DQs, count as neither a win nor a loss.
   - `is_dq` only catches −1 scores. Challengermode-era forfeits arrive as 0–0 (null scores on Challengermode itself).
   - `winner_side` already treats 0–0 as no winner, so the record views already leave forfeits out.
   - The flag should name both cases, e.g. an `is_no_contest` column (`is_dq OR both scores 0`), and the rules table in §2 should list forfeits next to DQs.
3. **Per-tournament earnings (§6b).** Challengermode-era payouts come from the description's PRIZESPLIT text (10 of 11 official events), not from structured data.
   - Parse the text into `prize_payouts` with source `parsed_text`.
   - Mark an event reviewed automatically when the split adds up to the stated total; send mismatches (Spring SEA 2025) and events without a split (BCX 2025) to manual review.
   - Drop the "needs credentials or a manual copy" caveat, since we now have access.
4. **Bracket extension tables (§7).** Fill in the mapping:
   - phases: start.gg `Phase` / Challengermode stage;
   - groups: start.gg `PhaseGroup` with its `bracketUrl` / Challengermode bracket, whose labels give the side;
   - `match_bracket_info`: start.gg set `round` (signed), `fullRoundText`, `identifier`, `wPlacement`, `lPlacement`, and best-of from `Round.bestOf` (not `totalGames`) / Challengermode `ordinal`, round title and labels;
   - seeds: from both platforms;
   - standings: start.gg placement plus `isDisqualified` / Challengermode best and worst placement.
5. **Entrant counts** come from standings, not `numEntrants` (992 registered vs 450 placed at NA Winter 2025).
6. **Per-game data:** add an optional `match_games` table (start.gg stage and characters per game). The Stats API's legends and maps could live there too.
7. **Former names:** import start.gg entrant names and participant tags per event as `player_aliases` rows (`former_name`).
8. **Player links:** start.gg participant player IDs and Challengermode member user IDs join directly to `players.sgg_player_id` / `cm_player_id`. Challengermode's Brawlhalla account ID is a UUID, unrelated to `brawlhalla_id`.
9. **Tier:** keep the curated `tier`. `competitionTier` is always 5.
10. **Crawl (§3):**
    - enumerate events from the Stats API, since Challengermode lists are capped;
    - per-platform request gaps (1 s and 3.5 s);
    - start.gg's 1,000-object query limit;
    - Challengermode token refresh;
    - a custom User-Agent;
    - credentials from `.env`.
11. **Coverage checks (§4):** full platform standings make an exact per-event check possible: Stats API placements against the complete entrant list.
12. **2v2 payouts are per team (decided), and each player gets half.** `v_player_event_earnings` already halves 2v2 amounts, so only the comment marking it as an assumption needs to change. Crew battle prizes are per crew, split three ways (also decided), which the view already does.
