import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
from builds import Builds  # noqa: E402
from cache import ResponseCache  # noqa: E402
from curation import Skipped  # noqa: E402

TABLES = {"players", "player_aliases", "player_merges", "tiers", "events", "event_aliases", "event_terms", "format_rules",
          "event_sources", "teams", "placements", "matches", "match_players", "pr_snapshots", "player_earnings",
          "standings", "unplaced_entries", "build_info", "build_checks"}


class MakeBuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")
        cache.store("/event", {"gameMode": 1}, "u", 200, json.dumps({"tournaments": []}).encode(), 5)
        self.fetched = cache.db.execute("SELECT fetched_at FROM requests").fetchone()[0]
        cache.db.close()
        (self.root / "curation").mkdir()
        (self.root / "curation" / "events.csv").write_text("event_id,note\n", encoding="utf-8")
        self.builds = Builds(self.root / "db")
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, **kwargs):
        """A build with no steps unless some are given: these tests are about the build around them."""
        kwargs.setdefault("steps", [])
        return build.make_build(self.builds, log=self.log.append, cache_dir=self.root / "cache",
                                crawl_db=self.root / "crawl.sqlite", curation_dir=self.root / "curation",
                                auto_merges=None, **kwargs)

    def info(self, build_id, state="passed"):
        db = sqlite3.connect(self.builds.path(build_id, state))
        try:
            return dict(db.execute("SELECT key, value FROM build_info")), \
                {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'"
                                          " AND name NOT LIKE 'sqlite_%'")}  # not ANALYZE's statistics
        finally:
            db.close()

    def test_a_build_has_every_table_records_its_inputs_and_goes_live(self):
        steps_run = []
        build_id, passed = self.make(steps=[("events", lambda b: steps_run.append(b.reader.cutoff()))])
        self.assertTrue(passed)
        self.assertEqual(steps_run, [self.fetched])
        info, tables = self.info(build_id)
        self.assertEqual(tables, TABLES)
        self.assertEqual(info["cache_cutoff"], self.fetched)
        self.assertEqual(info["verdict"], "pass")
        self.assertEqual(set(json.loads(info["curation"])), {"events.csv"})
        self.assertEqual(info["as_of"][:16], info["started_at"][:16])  # without --as-of, the cutoff is the start
        self.assertEqual(self.builds.live()["build"], build_id)

    def test_a_build_of_the_past_sees_only_what_was_fetched_by_then(self):
        build_id, _ = self.make(as_of="2000-01-01T00:00:00Z", publish=False)
        info, _ = self.info(build_id)
        self.assertIsNone(info["cache_cutoff"])
        self.assertIsNone(self.builds.live())

    def test_a_failed_blocking_check_keeps_the_live_build(self):
        first, _ = self.make()
        fail = lambda b: [build.Outcome("winners", "blocking", "e1", "fail", "no 1st place")]  # noqa: E731
        listed = lambda b: [build.Outcome("phase_splits", "review", "e2", "listed", "possible phase split")]  # noqa: E731
        second, passed = self.make(checks=[fail, listed])
        self.assertFalse(passed)
        self.assertEqual(self.builds.live()["build"], first)
        db = sqlite3.connect(self.builds.path(second, "failed"))
        try:
            self.assertEqual(db.execute("SELECT check_id, subject, outcome FROM build_checks ORDER BY check_id, subject")
                             .fetchall(), [("phase_splits", "", "pass"), ("phase_splits", "e2", "listed"),
                                           ("winners", "", "fail"), ("winners", "e1", "fail")])  # '': the verdict
        finally:
            db.close()
        third, passed = self.make(checks=[listed])  # a review item never blocks
        self.assertTrue(passed)
        self.assertEqual(self.builds.live()["build"], third)

    def test_reports_and_the_review_list(self):
        skip = ("aliases", lambda b: b.skipped.append(Skipped("player_aliases.csv:2", "the cache has no player 9",
                                                              "player_aliases.csv:x:9")))
        full, _ = self.make(steps=[skip])
        self.assertTrue((self.root / "reports" / full / "report.md").exists())
        self.assertEqual(self.log[-2:], ["!! 1 curated row(s) skipped. Check each for a typo:",
                                         "!!   player_aliases.csv:2: the cache has no player 9"])  # last in the log
        review = self.root / "review" / "review.csv"
        self.assertEqual(review.read_text(encoding="utf-8").splitlines()[1].split(",")[:2],
                         ["curated_row_skipped:player_aliases.csv:x:9", "curated_row_skipped"])
        before = review.read_text(encoding="utf-8")
        past, _ = self.make(as_of="2000-01-01T00:00:00Z", publish=False)  # a build of the past keeps its own list
        self.assertTrue((self.root / "reports" / past / "review.csv").exists())
        self.assertEqual(review.read_text(encoding="utf-8"), before)
        db = sqlite3.connect(self.builds.path(past))
        try:
            self.assertIn("not compared", dict(db.execute("SELECT check_id, detail FROM build_checks"
                                                          " WHERE subject = ''"))["regression"])
        finally:
            db.close()

    def test_a_step_that_raises_leaves_the_live_build_alone(self):
        first, _ = self.make()

        def broken(b):
            raise ValueError("bad row")
        with self.assertRaises(ValueError):
            self.make(steps=[("events", broken)])
        self.assertEqual(self.builds.live()["build"], first)
        self.assertFalse(self.builds.lock_file.exists())
        self.make()  # the next build clears the crashed one's partial file
        self.assertNotIn("partial", {state for _, state in self.builds.files()})


class MatchRulesTest(unittest.TestCase):
    """The generated columns of `matches` apply the decided rules for DQs, forfeits and unscored sets."""

    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(build.SCHEMA.read_text(encoding="utf-8"))

    def tearDown(self):
        self.db.close()

    def match(self, side1, side2, reported=None):
        self.db.execute("DELETE FROM matches")
        self.db.execute("INSERT INTO matches (match_id, event_id, side1_score, side2_score, reported_winner_side,"
                        " source, fetched_at) VALUES ('m', 'e', ?, ?, ?, 'startgg', 't')", (side1, side2, reported))
        return self.db.execute("SELECT is_scored, is_dq, is_no_contest, dq_side, winner_side FROM matches").fetchone()

    def test_a_scored_set_is_won_on_games(self):
        self.assertEqual(self.match(3, 1, 1), (1, 0, 0, None, 1))
        self.assertEqual(self.match(0, 2, 2), (1, 0, 0, None, 2))

    def test_a_dq_is_a_no_contest_whoever_advanced(self):
        self.assertEqual(self.match(-1, 0, 2), (1, 1, 1, 1, None))
        self.assertEqual(self.match(None, -1, 1), (0, 1, 1, 2, None))  # a -1 against no score
        self.assertEqual(self.match(-1, -1), (1, 1, 1, 0, None))

    def test_a_challengermode_forfeit_stays_a_no_contest(self):
        self.assertEqual(self.match(0, 0, 1), (1, 0, 1, None, None))

    def test_a_set_with_only_a_winner_counts_but_its_games_are_unknown(self):
        self.assertEqual(self.match(None, None, 2), (0, 0, 0, None, 2))
        self.assertEqual(self.match(2, None, 1), (0, 0, 0, None, 1))

    def test_bracket_links(self):
        rows = [("tournament/bcx-2022/event/1v1", "SGG"), ("series/pro-series-2021-na", "SGG"), ("abc-123", "CM")]
        self.db.executemany("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official,"
                            " is_twos, is_online, fetched_at) VALUES (?, ?, 'T', 2022, 0, 1, 0, 0, 't')", rows)
        self.assertEqual([r[0] for r in self.db.execute("SELECT bracket_url FROM events ORDER BY rowid")], [
            "https://www.start.gg/tournament/bcx-2022/event/1v1/brackets", None,
            "https://www.challengermode.com/s/Brawlhalla/tournaments/abc-123"])


if __name__ == "__main__":
    unittest.main()
