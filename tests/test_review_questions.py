import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
sys.path.insert(0, str(ROOT / "eval"))
import build  # noqa: E402
import review_questions as rq  # noqa: E402


def question(**fields):
    return {"id": "q01", "question": "Who?", "category": "player_record", "tests": ["case"], "answer": "Boomie.",
            "query": [{"purpose": "who", "sql": "SELECT 1"}], "verified": "", **fields}


class SetTest(unittest.TestCase):
    def test_the_evaluation_set_is_well_formed(self):
        data = rq.load()
        self.assertEqual(rq.problems(data), [])
        self.assertGreaterEqual(len(data["question"]), 40)

    def test_problems_are_named(self):
        data = {"snapshot": "s", "build": "b", "question": [
            question(), question(category="trivia", verified="maybe"),
            question(id="q02", answer="", same_answer_as="q09", query=[{"purpose": "none"}])]}
        self.assertEqual(rq.problems(data), [
            "q01: the ID is used 2 times",
            "q01: unknown category 'trivia'",
            "q01: verified should be empty, or start with yes, no or partly",
            "q02: no answer",
            "q02: same_answer_as names 'q09', which isn't in the set",
            "q02: a query has no sql"])
        self.assertEqual(rq.problems({"question": [question(verified="no: Godly won it")]}),
                         ["the set doesn't name its snapshot", "the set doesn't name its build"])


class PageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "snapshot.sqlite"
        db = sqlite3.connect(self.path)
        db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        db.executescript(build.VIEWS.read_text(encoding="utf-8"))
        db.executemany("INSERT INTO players (player_id, name, source, updated_at, canonical_id) VALUES (?, ?, 'stats_api', 't', ?)",
                       [(1, "Boomie", 1), (2, "Boomie", 2)])
        db.executemany("INSERT INTO player_aliases VALUES ('boomie', ?, 'display_name', 'Boomie', 'stats_api', NULL)",
                       [(1,), (2,)])
        db.execute("INSERT INTO build_info VALUES ('build_id', 'b1')")
        db.commit()
        db.close()

    def test_the_page_shows_how_names_resolve_and_each_query_result(self):
        data = {"snapshot": "s", "build": "b1", "question": [question(
            players={"Boomie": 1, "boomy": 1}, query=[{"purpose": "a team", "sql": "SELECT 'a | b' AS team, NULL AS note"}])]}
        page, issues = rq.render(data, self.path, log=lambda line: None)
        self.assertEqual(issues, [])
        self.assertIn("- **Boomie** → Boomie (1, 0 results), by the display name; 1 other player with this name,"
                      " with at most 0 results", page)
        self.assertIn("- **boomy** → Boomie (1, 0 results), no alias matches it", page)
        self.assertIn("| a \\| b | NULL |", page)
        self.assertIn("**Verified:** not yet", page)

    def test_a_failing_query_an_unknown_player_or_another_build_is_a_problem(self):
        data = {"snapshot": "s", "build": "b0", "question": [question(
            players={"Nobody": 9}, query=[{"purpose": "broken", "sql": "SELECT x FROM nowhere"}])]}
        _, issues = rq.render(data, self.path, log=lambda line: None)
        self.assertEqual(issues, ["the snapshot is build b1, but the answers were computed on b0",
                                  "q01: no player 9 ('Nobody')",
                                  "q01 query 1: OperationalError: no such table: nowhere"])


if __name__ == "__main__":
    unittest.main()
