-- The views (docs/build-plan.md, step 7; schema proposal §2 and §6a). They encode the decided counting
-- rules and reusable building blocks, not answers to particular questions, and the agent queries them
-- rather than the tables. Each view documents its rules inside its definition, after AS, because
-- SQLite keeps that text in sqlite_master, where the agent reads the schema.
-- Changes from the schema proposal:
--   * the team views use canonical player IDs, with one row per player per partner (partner_id), so a
--     filter on a player uses an index;
--   * v_match_results has each side's player count and is_scored; v_match_sides is folded into it;
--   * v_results settles ties by the better placement, and picks a person's result with NOT EXISTS
--     rather than a window function, so the views on top of it stay fast when filtered by player;
--   * v_entries also has players who played without a placement;
--   * v_events leaves a held-out event out of the counts (decision 3);
--   * v_win_runs is new, and v_event_coverage computes per event what the schema proposal's §4 listed;
--   * v_sets_1v1 and v_event_series are new (2026-11-10), written for the agent: a set with both players, and the
--     events of a yearly series. A snapshot frozen before them gets them as temporary views (agent/tools.py).

CREATE VIEW v_events AS
-- Every official event with its effective mode and format, and what it counts toward (decided rules).
--   mode       mode_override if set, else what the Stats API reported (is_twos).
--   format     events.csv's format_override if set, else the first matching format rule (lowest
--              priority, then pattern), else 'standard'.
--   counts_as  '1v1' or '2v2'. Crew battles count as 1v1. Other non-standard formats (3v3, Triples,
--              Brawlball, Kung Foot, ...) count toward neither and have NULL here. So does a held-out event.
--   status     'cancelled' for an official event that was never held (CEO Dreamland 2020, cancelled due
--              to COVID-19). An answer says it wasn't held, not that its results are missing.
--              'placements_unreliable' for an event whose standings are wrong (SEA League Week 1/4, 2017:
--              24 entrants placed 1st). Its placements aren't results, so wins, medals and top 8s leave it
--              out (v_results); its matches still count. An answer about it says why.
--              note gives the reason.
--   held_out   why a new event stays out of the counts until a person reviews it: its entrants' sizes don't
--              fit its mode and format (e.g. a "1v1" event whose entrants have three players). NULL for every
--              other event. An answer that would include it says it was left out and why.
--   competition_key  shared by the phases of one competition (e.g. a Swiss stage and its Top 8 Finals).
-- (The events are classified once per query, MATERIALIZED, rather than once per row that joins them.)
WITH classified AS MATERIALIZED (
  SELECT e.*,
         COALESCE(e.mode_override, CASE WHEN e.is_twos = 1 THEN '2v2' ELSE '1v1' END) AS mode,
         COALESCE(e.format_override,
                  (SELECT r.format FROM format_rules r
                    WHERE lower(e.tournament_name || ' ' || COALESCE(e.event_name, '')) LIKE r.pattern
                    ORDER BY r.priority, r.pattern LIMIT 1),
                  'standard') AS format,
         COALESCE(e.competition_id, e.event_id) AS competition_key
  FROM events e
)
SELECT x.*,
       CASE WHEN x.held_out IS NULL THEN CASE x.format WHEN 'standard' THEN x.mode WHEN 'crew_battle' THEN '1v1' END
       END AS counts_as,
       date(x.start_time, 'unixepoch') AS start_date
FROM classified x;

CREATE VIEW v_player_ids AS
-- Every player record with its canonical player. Two records of one person (player_merges) are
-- reported under canonical_id, and the views below all use canonical IDs.
-- (players.canonical_id holds the merges, set when the database is built, and is indexed.)
SELECT player_id, canonical_id FROM players;

CREATE VIEW v_results AS
-- One result per player (canonical) per competition that counts toward 1v1 or 2v2.
--   * Side formats are left out (v_events.counts_as is NULL); v_entries has them.
--   * An event whose placements are unreliable (v_events.status 'placements_unreliable') is left out.
--   * A competition in phases counts once, at the last phase reached.
--   * If two of a person's records placed in one event, the better placement counts.
--   * mode is what the event counts as: a crew battle's placement is the crew's, counted as 1v1, and an
--     answer labels it as a team result. So are the Pro Series finals (format crew_battle): team events.
--   * record_id is the player record that placed; source is where the placement came from ('startgg'
--     standings, 'challengermode' entrant lists, 'stats_api' for the Pro Series finals).
--   * The data starts in February 2017 and covers official events only, so answers say "official
--     events".
SELECT pl.canonical_id AS player_id, p.player_id AS record_id, v.event_id, v.competition_key,
       v.counts_as AS mode, v.format, p.placement, p.team_id, p.source, v.is_official, v.tier,
       v.tournament_name, v.event_name, v.year, v.start_date, v.start_time, v.host, v.bracket_url
FROM placements p
JOIN players pl ON pl.player_id = p.player_id
JOIN v_events v ON v.event_id = p.event_id
WHERE v.counts_as IS NOT NULL AND COALESCE(v.status, '') <> 'placements_unreliable'
  AND NOT EXISTS (  -- another of the person's records placed better in the same event
        SELECT 1 FROM players q
        JOIN placements p2 ON p2.event_id = p.event_id AND p2.player_id = q.player_id
        WHERE q.canonical_id = pl.canonical_id AND (p2.placement, p2.player_id) < (p.placement, p.player_id))
  AND (v.competition_id IS NULL OR NOT EXISTS (  -- the person reached a later phase of the competition
        SELECT 1 FROM events e2
        JOIN placements p2 ON p2.event_id = e2.event_id
        JOIN players q     ON q.player_id = p2.player_id
        WHERE e2.competition_id = v.competition_id AND q.canonical_id = pl.canonical_id
          AND (COALESCE(e2.phase_order, 0), e2.start_time) > (COALESCE(v.phase_order, 0), v.start_time)));

CREATE VIEW v_entries AS
-- Every official event a player (canonical) entered, side formats included (their mode is NULL).
-- For "last event entered" questions. If the newest is a side format, the answer also gives the newest
-- event with a mode (1v1 or 2v2).
--   * Entered means placed or played. placement is NULL for a player who played without a placement
--     (unplaced_entries: the entrants missing from SEA League Week 1/4's and MAX MODE 2025's standings), and
--     at an event whose placements are unreliable (v_events.status).
--   * A cancelled event has no entrants, so it never shows here.
--   * A person whose two records both entered one event has two rows for it.
SELECT pl.canonical_id AS player_id, v.event_id, v.tournament_name, v.event_name, v.start_date, v.start_time,
       v.format, v.counts_as AS mode, v.is_official,
       CASE WHEN COALESCE(v.status, '') <> 'placements_unreliable' THEN p.placement END AS placement
FROM placements p
JOIN players pl ON pl.player_id = p.player_id
JOIN v_events v ON v.event_id = p.event_id
UNION ALL
SELECT pl.canonical_id, v.event_id, v.tournament_name, v.event_name, v.start_date, v.start_time,
       v.format, v.counts_as, v.is_official, NULL
FROM unplaced_entries u
JOIN players pl ON pl.player_id = u.player_id
JOIN v_events v ON v.event_id = u.event_id;

CREATE VIEW v_medals AS
-- Medals: top-3 placements (1st, 2nd or 3rd) at official events, from v_results, so the format and phase
-- rules apply. Bronze is 3rd only: double elimination has a separate 4th.
SELECT r.*,
       CASE r.placement WHEN 1 THEN 'gold' WHEN 2 THEN 'silver' ELSE 'bronze' END AS medal
FROM v_results r
WHERE r.is_official = 1 AND r.placement <= 3;

CREATE VIEW v_player_medals AS
-- Each player's medal count by mode (v_medals). Not the PR gold/silver/bronze fields, which leave out
-- crew battles and are zero for players without a current PR.
SELECT player_id, mode,
       SUM(CASE WHEN placement = 1 THEN 1 ELSE 0 END) AS gold,
       SUM(CASE WHEN placement = 2 THEN 1 ELSE 0 END) AS silver,
       SUM(CASE WHEN placement = 3 THEN 1 ELSE 0 END) AS bronze,
       COUNT(*) AS medals
FROM v_medals
GROUP BY player_id, mode;

CREATE VIEW v_official_wins AS
-- Wins: first place at an official event (v_results). Questions about "majors" use this; tiers are
-- deferred, so answers say "official events".
SELECT * FROM v_results WHERE is_official = 1 AND placement = 1;

CREATE VIEW v_team_results AS
-- 2v2 results by team, one row per player per team result: player_id and partner_id are both canonical, so
-- a person with two records stays one partner. "Who has X played with": WHERE player_id = X, grouped by
-- partner_id. A team's history: WHERE player_id = X AND partner_id = Y.
SELECT r.player_id, partner.canonical_id AS partner_id, r.event_id, r.competition_key, r.placement,
       r.is_official, r.tier, r.tournament_name, r.event_name, r.year, r.start_date
FROM v_results r
JOIN teams t         ON t.team_id = r.team_id
JOIN players partner ON partner.player_id = CASE WHEN t.player1_id = r.record_id THEN t.player2_id
                                                 ELSE t.player1_id END
WHERE r.mode = '2v2';

CREATE VIEW v_match_results AS
-- One row per player (canonical) per match that counts toward 1v1 or 2v2.
--   * A DQ or a forfeit (is_no_contest) is neither a win nor a loss, so it's left out. Query matches for
--     them; v_win_runs counts them.
--   * A tie (two 1-1 Challengermode matches) has no winner and is left out too.
--   * side_players: how many players were on this side (1 in 1v1, 2 in 2v2). A crew battle's matches are
--     crew against crew (3), so they don't count in 1v1 head-to-heads.
--   * is_scored = 0: the set has a winner but no game score (decided 2026-10-05). It counts as a win
--     and a loss, but its games are unknown, not zero: games_won and games_lost are NULL. Any game
--     count or game win rate leaves it out and flags the result ("includes sets with no recorded
--     score").
SELECT i.canonical_id AS player_id, mp.player_id AS record_id, m.match_id, mp.side,
       (SELECT COUNT(*) FROM match_players s WHERE s.match_id = m.match_id AND s.side = mp.side) AS side_players,
       v.event_id, v.competition_key, v.counts_as AS mode, v.format, v.is_official, v.start_date,
       m.start_time, m.is_scored,
       CASE WHEN m.is_scored = 1 THEN CASE mp.side WHEN 1 THEN m.side1_score ELSE m.side2_score END END
         AS games_won,
       CASE WHEN m.is_scored = 1 THEN CASE mp.side WHEN 1 THEN m.side2_score ELSE m.side1_score END END
         AS games_lost,
       CASE WHEN m.winner_side = mp.side THEN 1 ELSE 0 END AS won
FROM matches m
JOIN match_players mp ON mp.match_id = m.match_id
JOIN players i        ON i.player_id = mp.player_id
JOIN v_events v       ON v.event_id = m.event_id
WHERE m.is_no_contest = 0
  AND m.winner_side IS NOT NULL
  AND v.counts_as IS NOT NULL;

CREATE VIEW v_head_to_head_1v1 AS
-- 1v1 head-to-head between two players (canonical), over matches with one player on each side, so a
-- crew battle's crew-against-crew matches are left out. DQs and forfeits are left out (v_match_results).
--   games_won and games_lost count scored sets only. unscored_matches counts those with no game score,
--   so a game-based figure built on them is flagged.
--   When ranking records against someone, name the metric and any minimum number of matches.
SELECT a.player_id, b.player_id AS opponent_id,
       SUM(a.won) AS wins, SUM(1 - a.won) AS losses, COUNT(*) AS matches,
       SUM(a.games_won) AS games_won, SUM(a.games_lost) AS games_lost,
       SUM(1 - a.is_scored) AS unscored_matches
FROM v_match_results a
JOIN v_match_results b ON b.match_id = a.match_id AND b.side <> a.side
WHERE a.mode = '1v1' AND a.side_players = 1 AND b.side_players = 1
GROUP BY a.player_id, b.player_id;

CREATE VIEW v_head_to_head_2v2 AS
-- 2v2 head-to-head, team against team: one row per player per partner per opposing pair, so each team's
-- record appears once for each of its two players. player_id and partner_id are the team; opponent1_id <
-- opponent2_id the opposing team; all canonical. A team's record against everyone: WHERE player_id = X
-- AND partner_id = Y. DQs and forfeits are left out. games_won and games_lost count scored sets only;
-- unscored_matches counts the others.
SELECT a.player_id, p.player_id AS partner_id, o1.player_id AS opponent1_id, o2.player_id AS opponent2_id,
       SUM(a.won) AS wins, SUM(1 - a.won) AS losses, COUNT(*) AS matches,
       SUM(a.games_won) AS games_won, SUM(a.games_lost) AS games_lost, SUM(1 - a.is_scored) AS unscored_matches
FROM v_match_results a
JOIN v_match_results p  ON p.match_id = a.match_id AND p.side = a.side AND p.player_id <> a.player_id
JOIN v_match_results o1 ON o1.match_id = a.match_id AND o1.side <> a.side
JOIN v_match_results o2 ON o2.match_id = a.match_id AND o2.side = o1.side AND o2.player_id > o1.player_id
WHERE a.mode = '2v2' AND a.side_players = 2 AND o1.side_players = 2
GROUP BY a.player_id, p.player_id, o1.player_id, o2.player_id;

CREATE VIEW v_career_earnings AS
-- One career earnings figure per player (canonical): the Stats API's, else the Esports Earnings snapshot's
-- (Phase 2; there are none yet), with its source and as-of date.
--   * Missing isn't zero: a player without a row has no figure, and an answer says so rather than $0.
--     A ranked player's $0 is a Stats API figure. Unranked players have no Stats API figure.
--   * If two of a person's records have figures, the larger is used, since they may overlap.
SELECT i.canonical_id AS player_id, p.name,
       COALESCE(MAX(CASE WHEN e.source = 'stats_api' THEN e.amount_usd END),
                MAX(CASE WHEN e.source = 'esportsearnings_manual' THEN e.amount_usd END)) AS earnings_usd,
       CASE WHEN MAX(e.source = 'stats_api') = 1 THEN 'Stats API' ELSE 'Esports Earnings snapshot' END AS source,
       COALESCE(MAX(CASE WHEN e.source = 'stats_api' THEN e.as_of END),
                MAX(CASE WHEN e.source = 'esportsearnings_manual' THEN e.as_of END)) AS as_of
FROM player_earnings e
JOIN v_player_ids i ON i.player_id = e.player_id
JOIN players p      ON p.player_id = i.canonical_id
GROUP BY i.canonical_id, p.name;

CREATE VIEW v_win_runs AS
-- Each official win (v_official_wins) with the winner's run: their counted sets in that competition,
-- every phase included.
--   sets_played    sets that count (DQs, forfeits and ties left out), unscored ones included.
--   sets_dropped   sets lost on the way.
--   games_won, games_lost  over scored sets only; NULL if no set was scored.
--   unscored_sets  sets with a winner but no game score.
--   no_contests    DQs and forfeits in the run. They're neither wins nor losses and add no games; an
--                  answer mentions them ("plus one opponent DQ'd").
--   is_crew_battle 1 for a crew battle (the Pro Series finals included). Its sets are crew against crew.
-- Ranking wins by dominance (decided, question 11): fewest games_lost first, then fewest sets_dropped,
-- then most games_won.
--   * A run with any unscored set ranks after every fully scored run. If it would have ranked near the
--     top on its scored sets alone, the answer says so in one line, so it isn't silently buried.
--   * A crew battle's run isn't comparable: leave it out and say why.
--   * A win without counted sets (sets_played = 0, e.g. no match data) ranks last.
--   * The answer names the metric and shows the top run's set scores.
-- (Each figure is a subquery per win, so a query for one player reads only that player's matches.)
SELECT w.player_id, w.event_id, w.competition_key, w.tournament_name, w.event_name, w.start_date, w.mode,
       w.format, (w.format = 'crew_battle') AS is_crew_battle,
       (SELECT COUNT(*) FROM v_match_results m
         WHERE m.player_id = w.player_id AND m.competition_key = w.competition_key) AS sets_played,
       (SELECT COALESCE(SUM(1 - m.won), 0) FROM v_match_results m
         WHERE m.player_id = w.player_id AND m.competition_key = w.competition_key) AS sets_dropped,
       (SELECT SUM(m.games_won) FROM v_match_results m
         WHERE m.player_id = w.player_id AND m.competition_key = w.competition_key) AS games_won,
       (SELECT SUM(m.games_lost) FROM v_match_results m
         WHERE m.player_id = w.player_id AND m.competition_key = w.competition_key) AS games_lost,
       (SELECT COALESCE(SUM(1 - m.is_scored), 0) FROM v_match_results m
         WHERE m.player_id = w.player_id AND m.competition_key = w.competition_key) AS unscored_sets,
       (SELECT COUNT(DISTINCT x.match_id)
          FROM players xi
          JOIN match_players xp ON xp.player_id = xi.player_id
          JOIN matches x        ON x.match_id = xp.match_id AND x.is_no_contest = 1
          JOIN events xe        ON xe.event_id = x.event_id
         WHERE xi.canonical_id = w.player_id
           AND COALESCE(xe.competition_id, xe.event_id) = w.competition_key) AS no_contests
FROM v_official_wins w;

CREATE VIEW v_event_coverage AS
-- What the database holds for each official event against what its platform reported, and a short flag an
-- answer can quote when something is missing. Counts are of player records, before merges.
--   platform              'startgg', 'challengermode', or 'stats_api' for the Pro Series finals: no platform has
--                         them, so their placements come from the Stats API and they have no matches.
--   platform_state        start.gg's phase states (e.g. 'ACTIVE,COMPLETED'), or Challengermode's tournament state.
--   entrants_reported     start.gg's standings total, or Challengermode's roster count, which also counts lineups
--                         that registered but never played.
--   entrants_placed       entrants (start.gg) or lineups (Challengermode) with a placement.
--   placements, worst_placement  the player placements held, and the worst of them.
--   matches_reported      start.gg's set total, which counts byes and sets never played. NULL for Challengermode,
--                         which reports none.
--   matches_seen          sets (start.gg) or matches (Challengermode) on the cached pages. Byes, sets never
--                         played and cancelled matches aren't stored, so matches_held can be lower.
--   matches_held          matches stored, DQs and forfeits included.
--   players_with_matches  player records in at least one stored match.
--   played_unplaced       players who played but have no placement, because their entrants are missing from the
--                         standings.
--   twos_without_team     2v2 placements without a team.
--   placed_without_match  placed players with no stored match.
--   flag  NULL when nothing is missing. Otherwise short phrases joined by '; ', for an answer to mention:
--           'not held'               the event was cancelled (status);
--           'placements unreliable'  its placements aren't results (status), though its matches count;
--           'held out for review'    a new event left out of the counts (held_out);
--           'no placements';
--           'placements incomplete'  players who played have no placement;
--           'no match data'          placements but no matches;
--           'match data incomplete'  placed players without a match, or sets missing from the cached pages;
--           'teams incomplete'       2v2 placements without a team.
-- (placed_without_match is placements - players_with_matches + played_unplaced, which needs no per-player
-- lookup, so the view stays fast: about a second for every event.)
SELECT c.*,
       NULLIF(rtrim(CASE c.status WHEN 'cancelled' THEN 'not held; '
                                  WHEN 'placements_unreliable' THEN 'placements unreliable; ' ELSE '' END
                    || CASE WHEN c.held_out IS NOT NULL THEN 'held out for review; ' ELSE '' END
                    || CASE WHEN c.status IS NULL AND c.placements = 0 THEN 'no placements; ' ELSE '' END
                    || CASE WHEN c.played_unplaced > 0 THEN 'placements incomplete; ' ELSE '' END
                    || CASE WHEN c.placements > 0 AND c.matches_held = 0 THEN 'no match data; '
                            WHEN c.placed_without_match > 0 OR c.matches_seen < c.matches_reported
                              THEN 'match data incomplete; '
                            ELSE '' END
                    || CASE WHEN c.twos_without_team > 0 THEN 'teams incomplete; ' ELSE '' END, '; '), '') AS flag
FROM (
  SELECT x.*, x.placements - x.players_with_matches + x.played_unplaced AS placed_without_match
  FROM (
    SELECT v.event_id, v.tournament_name, v.event_name, v.start_date, v.mode, v.format, v.counts_as, v.status,
           v.held_out, s.platform, s.state AS platform_state, s.reported_entrants AS entrants_reported,
           (SELECT COUNT(DISTINCT st.entrant_key) FROM standings st WHERE st.event_id = v.event_id) AS entrants_placed,
           (SELECT COUNT(*) FROM placements p WHERE p.event_id = v.event_id) AS placements,
           (SELECT MAX(p.placement) FROM placements p WHERE p.event_id = v.event_id) AS worst_placement,
           s.reported_sets AS matches_reported, s.sets_seen AS matches_seen,
           (SELECT COUNT(*) FROM matches m WHERE m.event_id = v.event_id) AS matches_held,
           (SELECT COUNT(DISTINCT mp.player_id) FROM matches m JOIN match_players mp ON mp.match_id = m.match_id
             WHERE m.event_id = v.event_id) AS players_with_matches,
           (SELECT COUNT(*) FROM unplaced_entries u WHERE u.event_id = v.event_id) AS played_unplaced,
           (SELECT COUNT(*) FROM placements p WHERE p.event_id = v.event_id AND p.team_id IS NULL AND v.mode = '2v2')
             AS twos_without_team
    FROM v_events v
    LEFT JOIN event_sources s ON s.event_id = v.event_id) x) c;

CREATE VIEW v_sets_1v1 AS
-- One row per counted 1v1 set, with both players, the score, and where each of them finished: the sets
-- v_head_to_head_1v1 counts. One player a side, so a crew battle's crew-against-crew sets are left out, and so are
-- DQs, forfeits and ties (v_match_results).
--   winner_id, loser_id    canonical players; winner_name and loser_name are their current names.
--   winner_games, loser_games  NULL for a set with a winner but no game score (is_scored = 0).
--   winner_placement, loser_placement  each player's result in that competition (v_results). NULL for a player
--                          without one, and at an event whose placements are unreliable.
--   start_time             when the set started, where the platform reported it (some start.gg sets have none).
-- Finding a final: no round names are stored. A final is a set the winner took from the runner-up, winner_placement
-- = 1 AND loser_placement = 2: the last by start_time if they met more than once (an earlier set in the winners'
-- bracket, or the first set of a final that was reset). An event's last set by start_time alone isn't always it: a
-- set's time can be missing or out of order (on eval-v1, the last set is 1st beating 2nd in 331 of 354 standard 1v1
-- events, and DreamHack Dallas 2023's reset has no time).
-- Fast when filtered by event_id, by winner_id, by loser_id, or by both players. winner_id = X OR loser_id = X reads
-- every set, which takes seconds: for one player's sets, won and lost, query each side, or use v_match_results.
-- (Each placement is a subquery per row, read only when a query asks for it. As joins, some queries took 13 s.)
SELECT m.match_id, v.event_id, v.competition_key, v.tournament_name, v.event_name, v.start_date, m.start_time,
       wi.canonical_id AS winner_id, wn.name AS winner_name,
       (SELECT r.placement FROM v_results r
         WHERE r.player_id = wi.canonical_id AND r.competition_key = v.competition_key) AS winner_placement,
       li.canonical_id AS loser_id, ln.name AS loser_name,
       (SELECT r.placement FROM v_results r
         WHERE r.player_id = li.canonical_id AND r.competition_key = v.competition_key) AS loser_placement,
       CASE WHEN m.is_scored = 1 THEN CASE m.winner_side WHEN 1 THEN m.side1_score ELSE m.side2_score END END
         AS winner_games,
       CASE WHEN m.is_scored = 1 THEN CASE m.winner_side WHEN 1 THEN m.side2_score ELSE m.side1_score END END
         AS loser_games,
       m.is_scored
FROM matches m
JOIN match_players w ON w.match_id = m.match_id AND w.side = m.winner_side
JOIN match_players l ON l.match_id = m.match_id AND l.side <> m.winner_side
JOIN players wi      ON wi.player_id = w.player_id
JOIN players wn      ON wn.player_id = wi.canonical_id
JOIN players li      ON li.player_id = l.player_id
JOIN players ln      ON ln.player_id = li.canonical_id
JOIN v_events v      ON v.event_id = m.event_id
WHERE m.is_no_contest = 0
  AND m.winner_side IS NOT NULL
  AND v.counts_as = '1v1'
  AND (SELECT COUNT(*) FROM match_players s WHERE s.match_id = m.match_id) = 2;

CREATE VIEW v_event_series AS
-- The events of each yearly series: an event alias that is a name and a year ('worlds 2019'), for a name with two
-- years or more, as resolve_event reads a series. On eval-v1: 'worlds' (the World Championship, 2017 on) and 'bcx'
-- (the years it was held as the Brawlhalla World Championship Expo).
--   * An event can be in two series (BCX 2022 is also Worlds 2022), so always filter series: series = 'worlds'.
--   * mode is what the event counts as ('1v1' or '2v2').
--   * regional is 1 when that year's championship was several events in that mode: Worlds 2020 and 2021 were held
--     as five regional championships each. An answer that counts titles says whether it counted those.
SELECT substr(a.alias, 1, length(a.alias) - 5) AS series, CAST(substr(a.alias, -4) AS INTEGER) AS year,
       v.event_id, v.tournament_name, v.event_name, v.start_date, v.counts_as AS mode,
       (SELECT COUNT(*) FROM event_aliases a2
          JOIN v_events v2 ON v2.event_id = a2.event_id
         WHERE a2.alias = a.alias AND v2.counts_as IS v.counts_as) > 1 AS regional
FROM event_aliases a
JOIN v_events v ON v.event_id = a.event_id
WHERE a.alias GLOB '* 20[0-9][0-9]'
  AND (SELECT COUNT(DISTINCT a3.alias) FROM event_aliases a3
        WHERE a3.alias GLOB '* 20[0-9][0-9]'
          AND substr(a3.alias, 1, length(a3.alias) - 5) = substr(a.alias, 1, length(a.alias) - 5)) >= 2;
