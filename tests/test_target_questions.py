import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import target_questions  # noqa: E402


class TargetQuestionsTest(unittest.TestCase):
    """The regression script's own logic: its questions need the real data, so they run against a build."""

    def test_an_answer_that_differs_or_a_name_that_finds_nobody_fails(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        db.executescript(build.VIEWS.read_text(encoding="utf-8"))
        db.execute("INSERT INTO players (player_id, name, source, updated_at, canonical_id)"
                   " VALUES (1, 'Boomie', 'stats_api', 't', 1)")
        db.execute("INSERT INTO player_aliases VALUES ('boomie', 1, 'display_name', 'Boomie', 'stats_api', NULL)")
        questions = [(1, "Who?", lambda db: target_questions.person(db, "Boomie", 1), 1),
                     (2, "Who else?", lambda db: target_questions.person(db, "Nobody", 2), 2),
                     (3, "How many?", lambda db: 5, 6)]
        log = []
        with mock.patch.object(target_questions, "QUESTIONS", questions):
            self.assertEqual(target_questions.run(db, log.append), [2, 3])
        self.assertIn("PASS  1. Who?", log)
        self.assertIn("        got:      \"'Nobody' doesn't find player 2 (it finds nobody)\"", log)
        self.assertIn("        expected: 6", log)


if __name__ == "__main__":
    unittest.main()
