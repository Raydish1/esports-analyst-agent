import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import audit  # noqa: E402
import conversations  # noqa: E402


class AuditSetTest(unittest.TestCase):
    def test_the_set_has_no_problems_and_asks_every_kind_at_least_twice(self):
        data = conversations.load(audit.AUDIT)
        self.assertEqual(conversations.problems(data), [])
        kinds = Counter(c["kind"] for c in data["conversation"])
        self.assertEqual(sorted(k for k in range(1, 23) if kinds[k] < 2), [])  # docs/question-audit.md's 22 kinds
        for c in data["conversation"]:
            self.assertTrue(set(c["mechanism"]) <= set(audit.MECHANISMS), c["id"])
            self.assertFalse(str(c.get("verified", "")).strip(), c["id"])  # nothing in it is verified


class ReportTest(unittest.TestCase):
    def test_failed_checks_are_grouped_by_mechanism_and_kind_the_most_failing_first(self):
        data = {"conversation": [{"id": "a1", "title": "one", "kind": 5, "mechanism": ["M1", "M2"]},
                                 {"id": "a2", "title": "two", "kind": 8, "mechanism": ["M2"]}]}
        scored = [{"id": "a1", "seed": 0, "turns": [{"turn": 1, "checks": {
                       "calls_with": {"passed": False, "detail": "no call matches power_rankings()"},
                       "grounded": {"passed": True, "detail": ""}}}]},
                  {"id": "a2", "seed": 0, "turns": [{"turn": 1, "checks": {"grounded": {"passed": True, "detail": ""}}}]}]
        by_mechanism, by_kind, failing = audit.tally(data, scored)
        self.assertEqual((by_mechanism["M1"]["failed"], by_mechanism["M2"]["failed"], by_mechanism["M2"]["turns"]), (1, 1, 2))
        self.assertEqual((by_kind[5]["check calls_with"], by_kind[8]["failed"]), (1, 0))
        self.assertEqual(failing, [{"id": "a1", "seed": 0, "turn": 1, "title": "one",
                                    "checks": {"calls_with": "no call matches power_rankings()"}}])
        page = audit.lines(by_mechanism, by_kind, failing)
        self.assertIn("| M1 reading the question | 1 of 1 | calls_with 1 |", page)
        self.assertIn("- a1 seed 0 turn 1 (one): calls_with (no call matches power_rankings())", page)


if __name__ == "__main__":
    unittest.main()
