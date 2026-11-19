import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import legend_mains  # noqa: E402


class MainsTest(unittest.TestCase):
    def test_latest_year_first_then_the_year_before_then_all_time_then_none(self):
        rows = [(1, "2025", "VIVI", 164), (1, "2026", "DIANA", 100), (1, "2026", "VIVI", 41), (1, "all", "ZARIEL", 249),
                (2, "2025", "TEROS", 12), (2, "2026", "SIDRA", 5), (2, "all", "SIDRA", 40),
                (3, "2026", "LIN_FEI", 3), (3, "all", "DIANA", 176),
                (4, "all", "NIX", 4)]
        self.assertEqual(legend_mains.mains(rows), {1: ("diana", 100, "2026"), 2: ("teros", 12, "2025"),
                                                    3: ("diana", 176, "all")})

    def test_a_tie_goes_to_more_games_all_time(self):
        rows = [(1, "2026", "PETRA", 6), (1, "2026", "RED_RAPTOR", 6), (1, "all", "PETRA", 30), (1, "all", "RED_RAPTOR", 40)]
        self.assertEqual(legend_mains.mains(rows)[1][0], "redraptor")

    def test_hand_rows_are_kept_and_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "player_legends.csv"
            path.write_text("player_id,legend\n1,mordex\n", encoding="utf-8")
            self.assertEqual(legend_mains.write({1: ("vivi", 14, "all"), 2: ("diana", 20, "all")}, path), (1, 1))
            self.assertEqual(legend_mains.write({2: ("nix", 12, "all")}, path), (1, 1))  # the API's rows are replaced
            with open(path, encoding="utf-8", newline="") as f:
                rows = [(r["player_id"], r["legend"], r["source"]) for r in csv.DictReader(f)]
        self.assertEqual(rows, [("1", "mordex", "hand"), ("2", "nix", "stats_api")])


if __name__ == "__main__":
    unittest.main()
