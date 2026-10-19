import csv
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import report  # noqa: E402
from checks import Outcome  # noqa: E402
from curation import CheckException, Curation, Merge, Skipped  # noqa: E402

CANDIDATE_COLUMNS = ["tier", "evidence", "player_id", "name", "platform", "region", "first_event", "last_event",
                     "events", "best_placement", "other_player_id", "other_name", "other_platform", "other_region",
                     "other_first_event", "other_last_event", "other_events", "other_best_placement"]


class ReviewListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        self.db.executemany("INSERT INTO players (player_id, name, source, updated_at, canonical_id)"
                            " VALUES (?, ?, 'stats_api', 't', ?)", [(1, "a", 1), (2, "b", 1), (3, "c", 3), (4, "d", 4),
                                                                     (5, "e", 5), (6, "f", 6)])
        self.db.execute("INSERT INTO player_merges VALUES (2, 1, 'auto', 'auto: tier 1 (a and b)')")
        self.candidates = self.root / "merge_candidates.csv"
        with open(self.candidates, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CANDIDATE_COLUMNS)
            for a, b in ((1, 2), (3, 4), (5, 6)):  # 1 and 2 are merged by now; 3 and 4 rejected; 5 and 6 open
                writer.writerow([2, "cross-platform", a, "x", "start.gg", "NA", "2020-01-01", "2021-01-01", 3, 5,
                                 b, "x", "Challengermode", "", "2025-01-01", "", 1, ""])
        cur = Curation()
        cur.rejections = {frozenset((3, 4))}
        cur.dropped_auto = [(Merge(5, 6, "auto", "", 3), "5 and 6 would be one person, but ...")]
        self.build = SimpleNamespace(
            db=self.db, curation=cur, events=None,
            skipped=[Skipped("player_merges.csv:3", "the cache has no player 632566", "player_merges.csv:632566:145900")],
            unused_exceptions=[CheckException("teams", "nowhere", "a typo", 4)])
        self.outcomes = [
            Outcome("new_events", "review", "", "pass", "2 of 3 events have no row in events.csv"),
            Outcome("new_events", "review", "e1", "listed", "Cup (2020-01-01), start.gg: detected 1v1, standard"),
            Outcome("new_events", "review", "e2", "listed", "Showdown (2020-02-01), start.gg: detected 1v1, standard"),
            Outcome("entrant_sizes", "review", "e2", "listed", "held out of the counts until reviewed: ..."),
            Outcome("phase_splits", "review", "e1 e2", "listed", "Showdown may be a phase of Cup"),
            Outcome("winners", "blocking", "e3", "fail", "no 1st place")]

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_items_come_most_pressing_first_with_keys_by_content(self):
        items = report.review_items(self.build, self.outcomes, self.candidates)
        self.assertEqual([(i.kind, i.key) for i in items], [
            ("curated_row_skipped", "curated_row_skipped:player_merges.csv:632566:145900"),
            ("held_out_event", "held_out_event:e2"),
            ("unused_check_exception", "unused_check_exception:teams:nowhere"),
            ("phase_split", "phase_split:e1 e2"),
            ("new_event", "new_event:e1"), ("new_event", "new_event:e2"),
            ("auto_merge", "auto_merge:2 1"), ("auto_merge", "auto_merge:5 6"),
            ("merge_candidate", "merge_candidate:5 6")])  # the merged pair and the rejected one are decided
        self.assertTrue(items[0].detail.startswith("!! "))
        self.assertIn("'x' (Challengermode, region unknown, 2025-01-01, 1 events, best -)", items[-1].detail)

    def test_a_pair_proposed_by_hand_says_so(self):
        path = self.root / "proposed.csv"
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CANDIDATE_COLUMNS)
            writer.writerow(["proposed", "one event, with his usual partner", 7, "Boomie", "start.gg", "NA", "2017-02-04",
                             "2024-03-10", 147, 1, 8, "Boomie", "start.gg", "", "2017-04-01", "2017-04-01", 1, 1])
        [found] = report.candidate_items(self.build, path)
        self.assertEqual(found.key, "merge_candidate:7 8")
        self.assertTrue(found.detail.startswith("proposed by hand: one event, with his usual partner; 'Boomie' (start.gg, NA,"))

    def test_a_dev_build_lists_no_merge_candidates(self):
        self.build.events = {"e1"}
        self.assertNotIn("merge_candidate", {i.kind for i in report.review_items(self.build, self.outcomes,
                                                                                self.candidates)})

    def test_the_files(self):
        items = report.review_items(self.build, self.outcomes, self.candidates)
        review = self.root / "review" / "review.csv"
        report.write_review(review, items)
        with open(review, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["key"], "curated_row_skipped:player_merges.csv:632566:145900")
        self.assertEqual(list(rows[0]), ["key", "kind", "subject", "detail", "resolve"])
        heads = [Outcome("winners", "blocking", "", "fail", "3 counted events; 1 failed"),
                 Outcome("known_events", "blocking", "", "pass", "1 known events"),
                 Outcome("known_events", "blocking", "e3", "pass", "'Dreamland 2020': all 2 placements given match")]
        path = report.write_report(self.root / "reports" / "b1", "b1", {"scope": "all events"}, heads + self.outcomes,
                                   items, "data/review/review.csv", "It's kept.", self.build.skipped,
                                   {"e3": "Dreamland (2020-03-01)"})
        text = path.read_text(encoding="utf-8")
        self.assertLess(text.index("- !! player_merges.csv:3: the cache has no player 632566"), text.index("## Checks"))
        self.assertIn("**Failed:** winners. It's kept.", text)
        self.assertIn("- `e3` (Dreamland (2020-03-01)): no 1st place", text)
        self.assertIn("### 1 curated row skipped", text)
        self.assertIn("- **pass** `e3` (Dreamland (2020-03-01)): 'Dreamland 2020': all 2 placements given match", text)
        self.assertEqual(len((path.parent / "checks.csv").read_text(encoding="utf-8").splitlines()), 10)
        report.prune(self.root / "reports", kept={"b2"})
        self.assertFalse(path.parent.exists())


if __name__ == "__main__":
    unittest.main()
