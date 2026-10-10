import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import model_comparison as mc  # noqa: E402

EXPECTED = {number: expected for number, _, _, expected in mc.QUESTIONS}
IDS = {"Raydish": 160000, "hardymj": 145900, "Winged_Shell": 143709, "V3M_T4NQUIL0": 71736, "megD": 142100}


class ExtractTest(unittest.TestCase):
    def test_the_last_sql_block_wins_and_leaked_thinking_is_left_out(self):
        self.assertEqual(mc.extract_sql("<think>```sql\nSELECT 0\n```</think>Try:\n```sql\nSELECT 1;\n```\nor\n```sql\nSELECT 2\n```"),
                         "SELECT 2")
        self.assertEqual(mc.extract_sql("```\nSELECT 3\n```"), "SELECT 3")
        self.assertEqual(mc.extract_sql("We need the count.\nWITH x AS (SELECT 1) SELECT * FROM x;"),
                         "WITH x AS (SELECT 1) SELECT * FROM x")
        self.assertIsNone(mc.extract_sql("I can't answer that."))


class RunQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "db.sqlite"
        db = sqlite3.connect(self.path)
        db.execute("CREATE TABLE t (a)")
        db.executemany("INSERT INTO t VALUES (?)", [(1,), (2,)])
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_but_never_writes_and_stops_a_long_query(self):
        rows, columns, error, _ = mc.run_query("SELECT a FROM t ORDER BY a", self.path)
        self.assertEqual((rows, columns, error), ([(1,), (2,)], ["a"], None))
        self.assertIn("readonly", mc.run_query("DELETE FROM t", self.path)[2])
        forever = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
        error = mc.run_query(forever, self.path, seconds=0.5)[2]
        self.assertEqual(mc.failure("SELECT", None, error), "timeout")


class ChecksTest(unittest.TestCase):
    def check(self, number, rows):
        return mc.CHECKS[number](rows, EXPECTED[number], IDS)

    def test_an_answer_counts_in_any_shape_that_holds_its_facts(self):
        self.assertTrue(self.check(2, [(6,)]))
        self.assertTrue(self.check(2, [("1v1", 6)]))
        self.assertFalse(self.check(2, [(7,)]))
        self.assertTrue(self.check(3, [("Yes",)]))
        self.assertFalse(self.check(3, [(0,)]))
        self.assertTrue(self.check(4, [(1, 2, 3, 4, 8)]))  # BalloonBoy's side of the record
        self.assertTrue(self.check(7, [(27,)]))
        self.assertTrue(self.check(8, [(71736, 3, 2)]))  # the player's ID instead of the name
        self.assertFalse(self.check(8, [("Ahmet_", 3, 1)]))
        self.assertTrue(self.check(11, [("Trial of Laufey - North America (Moose Wars)", 2)]))
        self.assertFalse(self.check(12, []))

    def test_partners_count_in_any_shape_but_the_player_is_never_their_own_partner(self):
        names = [("Raydish", 2)] * 20 + [("hardymj", 9)] * 4 + [("Winged_Shell", 17)] * 3
        partner_ids = [(160000, 2)] * 20 + [(145900, 9)] * 4 + [(143709, 17)] * 3
        grouped = [("Raydish", 20, 2), ("hardymj", 4, 9), ("Winged_Shell", 3, 17)]
        self.assertTrue(self.check(6, names))
        self.assertTrue(self.check(6, partner_ids))
        self.assertTrue(self.check(6, grouped))
        self.assertTrue(self.check(6, [(142100, *row) for row in partner_ids]))  # megD as the player, in every row
        self.assertTrue(self.check(6, [(name, "megD", place) for name, place in names]))  # from the partners' side
        self.assertTrue(self.check(6, [(f"megD / {name}", place) for name, place in names]))  # teams
        # v_team_results read from both sides: megD listed as their own partner, once per team result
        self.assertFalse(self.check(6, names + [("megD", 2)] * 20))
        self.assertFalse(self.check(6, partner_ids + [(142100, 2)] * 20))
        self.assertFalse(self.check(6, grouped + [("MEGD ", 46, 2)]))

    def test_failure_types(self):
        self.assertEqual(mc.failure(None, None, None), "no SQL in the reply")
        self.assertEqual(mc.failure("x", None, "OperationalError: no such column: p.alias"), "unknown column")
        self.assertEqual(mc.failure("x", None, "OperationalError: near \"FROM\": syntax error"), "syntax error")
        self.assertEqual(mc.failure("x", [], None), "empty result")
        self.assertEqual(mc.failure("x", [(1,)], None), "wrong answer")
        self.assertEqual(mc.failure("x", None, "OperationalError: no such column: p.player", "length"),
                         "cut off at the output cap")


if __name__ == "__main__":
    unittest.main()
