import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402

A, B, C, D, A2, E, F = 1, 2, 3, 4, 5, 6, 7  # A2 is a second record of A, merged into A


class ViewsTest(unittest.TestCase):
    """The decided counting rules, as the views apply them, on a small hand-made database."""

    @classmethod
    def setUpClass(cls):
        db = cls.db = sqlite3.connect(":memory:")
        db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        db.executescript(build.VIEWS.read_text(encoding="utf-8"))
        db.executemany("INSERT INTO players (player_id, name, source, updated_at, canonical_id)"
                       " VALUES (?, ?, 'stats_api', 't', ?)",
                       [(A, "A", A), (B, "B", B), (C, "C", C), (D, "D", D), (A2, "A again", A), (E, "E", E), (F, "F", F)])
        db.execute("INSERT INTO player_merges VALUES (?, ?, 'curated', NULL)", (A2, A))
        db.executemany("INSERT INTO format_rules VALUES (?, ?, ?)", [
            ("%crew battle%", "crew_battle", 1), ("%kung foot%", "kung_foot", 2), ("%3v3%", "3v3", 3),
            ("%beta%", "bbb", 2), ("%alpha%", "aaa", 2)])  # the last two tie on priority: the pattern decides
        events = [  # (ID, name, is_twos, start, mode_override, competition, phase, status)
            ("e1", "Cup", 0, 100, None, None, None, None), ("e2", "Duos", 1, 200, None, None, None, None),
            ("e2b", "Duos 2", 1, 250, None, None, None, None),
            ("swiss", "League", 0, 300, None, "league", 1, None), ("top8", "League", 0, 310, None, "league", 2, None),
            ("crew", "Crew Battle 3v3", 0, 400, None, None, None, None),
            ("kungfoot", "Kung Foot", 1, 500, None, None, None, None),
            ("filed1v1", "Doubles", 0, 600, "2v2", None, None, None),
            ("ab", "Alpha Beta Cup", 0, 700, None, None, None, None),
            ("cancelled", "Dreamland", 0, 800, None, None, None, "cancelled")]
        db.executemany("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official, is_twos,"
                       " is_online, mode_override, competition_id, phase_order, status, fetched_at)"
                       " VALUES (?, 'SGG', ?, 2020, ?, 1, ?, 0, ?, ?, ?, ?, 't')",
                       [(e, name, start, twos, mode, comp, phase, status)
                        for e, name, twos, start, mode, comp, phase, status in events])
        db.executemany("INSERT INTO teams VALUES (?, ?, ?)", [(1, A, B), (2, C, D), (3, B, A2)])
        placements = [("e1", A, 1, None), ("e1", B, 2, None), ("e1", C, 3, None), ("e1", D, 4, None),
                      ("e1", A2, 9, None),  # two records of A in one event: the better placement counts
                      ("e2", A, 1, 1), ("e2", B, 1, 1), ("e2", C, 2, 2), ("e2", D, 2, 2),
                      ("e2b", B, 3, 3), ("e2b", A2, 3, 3),
                      ("swiss", A, 2, None), ("swiss", B, 5, None), ("top8", A, 2, None), ("top8", C, 1, None),
                      ("crew", A, 1, None), ("crew", B, 1, None), ("crew", C, 1, None), ("kungfoot", A, 1, None)]
        db.executemany("INSERT INTO placements VALUES (?, ?, ?, ?, 'startgg', 't')", placements)
        db.execute("INSERT INTO unplaced_entries VALUES ('e1', ?)", (E,))
        matches = [  # (ID, event, score 1, score 2, reported winner, side 1, side 2)
            ("m1", "e1", 3, 1, 1, [A], [B]), ("m2", "e1", 0, -1, 1, [A], [C]),  # C DQ'd: a no-contest
            ("m3", "e1", None, None, 1, [A], [D]),  # a winner but no score
            ("m4", "e1", 2, 0, 1, [B], [C]), ("m5", "e1", 3, 0, 1, [A2], [B]),  # A's other record
            ("m6", "crew", 2, 1, 1, [A, B, C], [D, E, F]),  # crew against crew
            ("m7", "e1", 0, 0, 1, [A], [B]),  # a forfeit
            ("m8", "e1", 1, 1, 1, [A], [B]),  # a tie
            ("m9", "e2", 3, 2, 1, [A, B], [C, D]),
            ("m10", "swiss", 2, 0, 1, [A], [B]), ("m11", "top8", 0, 3, 2, [A], [C])]
        db.executemany("INSERT INTO matches (match_id, event_id, side1_score, side2_score, reported_winner_side,"
                       " source, fetched_at) VALUES (?, ?, ?, ?, ?, 'startgg', 't')", [m[:5] for m in matches])
        db.executemany("INSERT INTO match_players VALUES (?, ?, ?)",
                       [(m[0], side, pid) for m in matches for side, pids in ((1, m[5]), (2, m[6])) for pid in pids])
        db.executemany("INSERT INTO player_earnings VALUES (?, ?, ?, '2026-10-02', 't')",
                       [(A, "stats_api", 100.0), (A2, "stats_api", 150.0), (B, "esportsearnings_manual", 50.0)])

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def rows(self, sql, *args):
        return self.db.execute(sql, args).fetchall()

    def test_events_get_their_mode_format_and_what_they_count_as(self):
        found = {e: rest for e, *rest in self.rows("SELECT event_id, mode, format, counts_as, status, competition_key"
                                                     " FROM v_events")}
        self.assertEqual(found["e1"], ["1v1", "standard", "1v1", None, "e1"])
        self.assertEqual(found["crew"], ["1v1", "crew_battle", "1v1", None, "crew"])  # crew battle beats 3v3
        self.assertEqual(found["kungfoot"], ["2v2", "kung_foot", None, None, "kungfoot"])  # counts toward neither
        self.assertEqual(found["filed1v1"][:3], ["2v2", "standard", "2v2"])  # the mode override
        self.assertEqual(found["ab"][1], "aaa")  # a tie on priority goes to the first pattern
        self.assertEqual(found["cancelled"][3], "cancelled")
        self.assertEqual(found["top8"][4], "league")

    def test_one_result_per_person_per_competition(self):
        results = sorted(self.rows("SELECT event_id, mode, placement, record_id FROM v_results WHERE player_id = ?", A))
        self.assertEqual(results, [("crew", "1v1", 1, A), ("e1", "1v1", 1, A), ("e2", "2v2", 1, A),
                                   ("e2b", "2v2", 3, A2), ("top8", "1v1", 2, A)])  # no swiss, no Kung Foot, no 9th
        self.assertEqual(self.rows("SELECT event_id, placement FROM v_results WHERE player_id = ? AND competition_key"
                                   " = 'league'", B), [("swiss", 5)])  # the last phase B reached

    def test_entries_include_side_formats_and_players_who_played_unplaced(self):
        self.assertIn(("kungfoot", None, 1),
                      self.rows("SELECT event_id, mode, placement FROM v_entries WHERE player_id = ?", A))
        self.assertEqual(self.rows("SELECT event_id, placement FROM v_entries WHERE player_id = ?", E), [("e1", None)])

    def test_medals_and_wins(self):
        self.assertEqual(sorted(self.rows("SELECT mode, gold, silver, bronze, medals FROM v_player_medals"
                                          " WHERE player_id = ?", A)), [("1v1", 2, 1, 0, 3), ("2v2", 1, 0, 1, 2)])
        self.assertEqual(sorted(e for (e,) in self.rows("SELECT event_id FROM v_official_wins WHERE player_id = ?", A)),
                         ["crew", "e1", "e2"])

    def test_team_results_name_each_partner_canonically(self):
        self.assertEqual(sorted(self.rows("SELECT event_id, partner_id, placement FROM v_team_results"
                                          " WHERE player_id = ?", B)), [("e2", A, 1), ("e2b", A, 3)])  # A2 is A
        self.assertEqual(sorted(self.rows("SELECT event_id, partner_id FROM v_team_results WHERE player_id = ?", A)),
                         [("e2", B), ("e2b", B)])

    def test_match_results_leave_out_no_contests_and_ties_and_mark_unscored_sets(self):
        found = {m: rest for m, *rest in self.rows(
            "SELECT match_id, side_players, is_scored, games_won, games_lost, won FROM v_match_results"
            " WHERE player_id = ?", A)}
        self.assertNotIn("m2", found)  # a DQ
        self.assertNotIn("m7", found)  # a forfeit
        self.assertNotIn("m8", found)  # a tie
        self.assertEqual(found["m3"], [1, 0, None, None, 1])  # a win whose games are unknown
        self.assertEqual(found["m5"], [1, 1, 3, 0, 1])  # A's other record
        self.assertEqual(found["m6"], [3, 1, 2, 1, 1])  # crew against crew

    def test_head_to_heads(self):
        self.assertEqual(self.rows("SELECT wins, losses, matches, games_won, games_lost, unscored_matches"
                                   " FROM v_head_to_head_1v1 WHERE player_id = ? AND opponent_id = ?", A, B),
                         [(3, 0, 3, 8, 1, 0)])  # m1, m5, m10; not the forfeit, the tie or the crew battle
        self.assertEqual(self.rows("SELECT wins, matches, games_won, unscored_matches FROM v_head_to_head_1v1"
                                   " WHERE player_id = ? AND opponent_id = ?", A, D), [(1, 1, None, 1)])
        self.assertEqual(self.rows("SELECT wins, losses FROM v_head_to_head_1v1 WHERE player_id = ? AND opponent_id = ?",
                                   A, C), [(0, 1)])  # the DQ doesn't count
        self.assertEqual(self.rows("SELECT opponent1_id, opponent2_id, wins, games_won, games_lost FROM v_head_to_head_2v2"
                                   " WHERE player_id = ? AND partner_id = ?", A, B), [(C, D, 1, 3, 2)])

    def test_career_earnings(self):
        self.assertEqual(sorted(self.rows("SELECT player_id, earnings_usd, source FROM v_career_earnings")),
                         [(A, 150.0, "Stats API"), (B, 50.0, "Esports Earnings snapshot")])  # C has no figure

    def test_win_runs(self):
        runs = {e: rest for e, *rest in self.rows(
            "SELECT event_id, sets_played, sets_dropped, games_won, games_lost, unscored_sets, no_contests,"
            " is_crew_battle FROM v_win_runs WHERE player_id = ?", A)}
        self.assertEqual(runs["e1"], [3, 0, 6, 1, 1, 2, 0])  # m1, m3, m5; the DQ and forfeit are no-contests
        self.assertEqual(runs["crew"][-1], 1)
        self.assertEqual(self.rows("SELECT sets_played, sets_dropped, games_won, games_lost FROM v_win_runs"
                                   " WHERE player_id = ? AND competition_key = 'league'", C),
                         [(1, 0, 3, 0)])  # every phase of the competition counts


if __name__ == "__main__":
    unittest.main()
