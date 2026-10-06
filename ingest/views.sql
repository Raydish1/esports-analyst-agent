-- The views (docs/build-plan.md, step 7; schema proposal §2 and §6a). They encode the decided counting
-- rules and reusable building blocks, not answers to particular questions, and the agent queries them
-- rather than the tables. Each view documents its rules inside its definition, after AS, because
-- SQLite keeps that text in sqlite_master, where the agent reads the schema.
-- Changes from the schema proposal: canonical player IDs in the team views; each side's player count
-- and is_scored in v_match_results; ties settled by the better placement in v_results; v_entries also
-- has players who played without a placement; v_win_runs is new; v_match_sides is folded into
-- v_match_results' side_players.

CREATE VIEW v_events AS
-- Every official event with its effective mode and format, and what it counts toward (decided rules).
--   mode       mode_override if set, else what the Stats API reported (is_twos).
--   format     events.csv's format_override if set, else the first matching format rule (lowest
--              priority, then pattern), else 'standard'.
--   counts_as  '1v1' or '2v2'. Crew battles count as 1v1. Other non-standard formats (3v3, Triples,
--              Brawlball, Kung Foot, ...) count toward neither and have NULL here.
--   status     'cancelled' for an official event that was never held (CEO Dreamland 2020, cancelled due
--              to COVID-19). An answer says it wasn't held, not that its results are missing. note
--              gives the reason.
--   competition_key  shared by the phases of one competition (e.g. a Swiss stage and its Top 8 Finals).
SELECT x.*,
       CASE x.format WHEN 'standard' THEN x.mode WHEN 'crew_battle' THEN '1v1' END AS counts_as,
       date(x.start_time, 'unixepoch') AS start_date
FROM (
  SELECT e.*,
         COALESCE(e.mode_override, CASE WHEN e.is_twos = 1 THEN '2v2' ELSE '1v1' END) AS mode,
         COALESCE(e.format_override,
                  (SELECT r.format FROM format_rules r
                    WHERE lower(e.tournament_name || ' ' || COALESCE(e.event_name, '')) LIKE r.pattern
                    ORDER BY r.priority, r.pattern LIMIT 1),
                  'standard') AS format,
         COALESCE(e.competition_id, e.event_id) AS competition_key
  FROM events e
) x;

CREATE VIEW v_player_ids AS
-- Every player record with its canonical player. Two records of one person (player_merges) are
-- reported under canonical_id, and the views below all use canonical IDs.
-- (players.canonical_id holds the merges, set when the database is built, and is indexed.)
SELECT player_id, canonical_id FROM players;

CREATE VIEW v_results AS
-- One result per player (canonical) per competition that counts toward 1v1 or 2v2.
--   * Side formats are left out (v_events.counts_as is NULL); v_entries has them.
--   * A competition in phases counts once, at the last phase reached.
--   * If two of a person's records placed in one event, the better placement counts.
--   * mode is what the event counts as: a crew battle's placement is the crew's, counted as 1v1, and an
--     answer labels it as a team result. So are the Pro Series finals (format crew_battle): team events.
--   * record_id is the player record that placed; source is where the placement came from ('startgg'
--     standings, 'challengermode' entrant lists, 'stats_api' for the Pro Series finals).
--   * The data starts in February 2017 and covers official events only, so answers say "official
--     events".
SELECT player_id, record_id, event_id, competition_key, mode, format, placement, team_id, source,
       is_official, tier, tournament_name, event_name, year, start_date, start_time, host, bracket_url
FROM (
  SELECT i.canonical_id AS player_id, p.player_id AS record_id, p.placement, p.team_id, p.source,
         v.event_id, v.competition_key, v.counts_as AS mode, v.format, v.is_official, v.tier,
         v.tournament_name, v.event_name, v.year, v.start_date, v.start_time, v.host, v.bracket_url,
         ROW_NUMBER() OVER (PARTITION BY v.competition_key, i.canonical_id
                            ORDER BY COALESCE(v.phase_order, 0) DESC, v.start_time DESC, p.placement,
                                     p.player_id) AS nth
  FROM placements p
  JOIN v_events v     ON v.event_id = p.event_id
  JOIN v_player_ids i ON i.player_id = p.player_id
  WHERE v.counts_as IS NOT NULL
) ranked
WHERE nth = 1;

CREATE VIEW v_entries AS
-- Every official event a player (canonical) entered, side formats included (their mode is NULL).
-- For "last event entered" questions. If the newest is a side format, the answer also gives the newest
-- event with a mode (1v1 or 2v2).
--   * Entered means placed or played. placement is NULL for a player who played without a placement
--     (unplaced_entries: the entrants missing from SEA League Week 1/4's and MAX MODE 2025's standings).
--   * A cancelled event has no entrants, so it never shows here.
SELECT i.canonical_id AS player_id, v.event_id, v.tournament_name, v.event_name, v.start_date, v.start_time,
       v.format, v.counts_as AS mode, v.is_official, x.placement
FROM (SELECT event_id, player_id, placement FROM placements
      UNION ALL
      SELECT event_id, player_id, NULL FROM unplaced_entries) x
JOIN v_events v     ON v.event_id = x.event_id
JOIN v_player_ids i ON i.player_id = x.player_id;

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
-- 2v2 results by team: one row per team per competition, with the pair as canonical players
-- (player1_id < player2_id). A person with two records stays one partner, so group by the pair for a
-- team's history.
SELECT DISTINCT MIN(i1.canonical_id, i2.canonical_id) AS player1_id,
       MAX(i1.canonical_id, i2.canonical_id) AS player2_id,
       r.event_id, r.competition_key, r.placement, r.is_official, r.tier, r.tournament_name, r.event_name,
       r.year, r.start_date
FROM v_results r
JOIN teams t         ON t.team_id = r.team_id
JOIN v_player_ids i1 ON i1.player_id = t.player1_id
JOIN v_player_ids i2 ON i2.player_id = t.player2_id
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
JOIN v_player_ids i   ON i.player_id = mp.player_id
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
-- 2v2 head-to-head, team against team. Each team is a pair of canonical players (player1_id <
-- player2_id; opponent1_id < opponent2_id). DQs and forfeits are left out. games_won and games_lost
-- count scored sets only; unscored_matches counts the others.
WITH sides AS (
  SELECT match_id, side, MIN(player_id) AS player1_id, MAX(player_id) AS player2_id, MAX(won) AS won,
         MAX(games_won) AS games_won, MAX(games_lost) AS games_lost, MAX(is_scored) AS is_scored
  FROM v_match_results
  WHERE mode = '2v2' AND side_players = 2
  GROUP BY match_id, side
  HAVING COUNT(DISTINCT player_id) = 2
)
SELECT a.player1_id, a.player2_id, b.player1_id AS opponent1_id, b.player2_id AS opponent2_id,
       SUM(a.won) AS wins, SUM(1 - a.won) AS losses, COUNT(*) AS matches,
       SUM(a.games_won) AS games_won, SUM(a.games_lost) AS games_lost, SUM(1 - a.is_scored) AS unscored_matches
FROM sides a
JOIN sides b ON b.match_id = a.match_id AND b.side <> a.side
GROUP BY a.player1_id, a.player2_id, b.player1_id, b.player2_id;

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
SELECT w.player_id, w.event_id, w.competition_key, w.tournament_name, w.event_name, w.start_date, w.mode,
       w.format, (w.format = 'crew_battle') AS is_crew_battle,
       COUNT(m.match_id) AS sets_played,
       COALESCE(SUM(1 - m.won), 0) AS sets_dropped,
       SUM(m.games_won) AS games_won,
       SUM(m.games_lost) AS games_lost,
       COALESCE(SUM(1 - m.is_scored), 0) AS unscored_sets,
       (SELECT COUNT(DISTINCT x.match_id)
          FROM players xi
          JOIN match_players xp ON xp.player_id = xi.player_id
          JOIN matches x        ON x.match_id = xp.match_id AND x.is_no_contest = 1
          JOIN events xe        ON xe.event_id = x.event_id
         WHERE xi.canonical_id = w.player_id
           AND COALESCE(xe.competition_id, xe.event_id) = w.competition_key) AS no_contests
FROM v_official_wins w
LEFT JOIN v_match_results m ON m.player_id = w.player_id AND m.competition_key = w.competition_key
GROUP BY w.player_id, w.event_id;
