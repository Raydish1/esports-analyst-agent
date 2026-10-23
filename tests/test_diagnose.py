import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import diagnose  # noqa: E402


def split(query):
    return [query[a:b].strip() for a, b in diagnose.conditions(query)]


class ConditionsTest(unittest.TestCase):
    def test_a_where_splits_at_its_top_level_ands_only(self):
        query = ("SELECT * FROM t WHERE a = 1 AND b = 'x AND y' AND c IN (SELECT d FROM u WHERE e = 1 AND f = 2)"
                 " ORDER BY a LIMIT 5")
        self.assertEqual(split(query), ["a = 1", "b = 'x AND y'", "c IN (SELECT d FROM u WHERE e = 1 AND f = 2)"])
        self.assertEqual(split("SELECT * FROM t WHERE a BETWEEN 1 AND 3 AND b = 'it''s'"), ["a BETWEEN 1 AND 3", "b = 'it''s'"])

    def test_an_or_keeps_a_clause_whole_and_having_counts_too(self):
        self.assertEqual(split("SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3"), ["a = 1 OR b = 2 AND c = 3"])
        self.assertEqual(split("SELECT a, COUNT(*) AS n FROM t WHERE b = 1 GROUP BY a HAVING n >= 5 AND a > 0"),
                         ["b = 1", "n >= 5", "a > 0"])

    def test_the_main_select_is_split_not_a_cte_or_a_compound_query(self):
        self.assertEqual(split("WITH x AS (SELECT * FROM t WHERE a = 1 AND b = 2) SELECT * FROM x WHERE c = 3"), ["c = 3"])
        self.assertEqual(split("SELECT a FROM t WHERE a = 1 UNION SELECT a FROM u WHERE a = 2"), [])
        self.assertEqual(split("SELECT * FROM t -- WHERE a = 1\n"), [])


class NoteTest(unittest.TestCase):
    def test_the_note_names_the_condition_and_the_values_and_says_never_to_relax_the_questions_silently(self):
        findings = [{"condition": "player_id = 7", "rows_without_it": 0, "value_found": True},
                    {"condition": "format = '2v2'", "rows_without_it": 5, "values": ["standard"], "value_found": False}]
        text = diagnose.note(findings)
        self.assertTrue(text.startswith("Without format = '2v2', the query returns 5 rows. No row has format = '2v2'."
                                        " Its column's values there: 'standard'."))
        self.assertIn("If it was your own mistake, fix it.", text)
        self.assertTrue(text.endswith("never relax a condition from the question silently."))
        both = diagnose.note([{"condition": "a = 1", "rows_without_it": 0}, {"condition": "b = 2", "rows_without_it": 0}])
        self.assertIn("No single condition explains it", both)

    def test_probes_stop_when_the_time_is_up(self):
        calls = []
        with patch.object(diagnose, "PROBES_SECONDS", 0):
            out = diagnose.diagnose("SELECT * FROM t WHERE a = 1", lambda sql, left: calls.append(sql) or [[1]])
        self.assertEqual((calls, out["conditions"]), ([], [{"condition": "a = 1", "rows_without_it": "not tested: too slow"}]))


if __name__ == "__main__":
    unittest.main()
