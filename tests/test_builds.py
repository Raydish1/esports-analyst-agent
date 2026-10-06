import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import builds as builds_module  # noqa: E402
from builds import BuildRunning, Builds  # noqa: E402

START = datetime(2026, 10, 5, 19, 0, 0, tzinfo=timezone.utc)


def at(hour):
    return f"20261005T{hour:02d}0000Z"


class BuildsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.builds = Builds(Path(self.tmp.name) / "db")
        self.log = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, build_id, passed=True, publish=True):
        """A finished build file holding one row, published if it passed and publish is set."""
        db = sqlite3.connect(self.builds.start(build_id))
        db.execute("CREATE TABLE t (build TEXT)")
        db.execute("INSERT INTO t VALUES (?)", (build_id,))
        db.commit()
        db.close()
        self.builds.finish(build_id, passed)
        if passed and publish:
            self.builds.publish(build_id)

    def live_row(self):
        db = self.builds.connect_live()
        try:
            return db.execute("SELECT build FROM t").fetchone()[0]
        finally:
            db.close()

    def test_publishing_points_to_the_build_and_remembers_the_earlier_ones(self):
        self.assertIsNone(self.builds.live())
        self.make(at(19))
        self.make(at(20))
        live = self.builds.live()
        self.assertEqual((live["build"], live["how"], live["history"]), (at(20), "published", [at(19), at(20)]))
        self.assertEqual(self.live_row(), at(20))

    def test_a_failed_build_never_goes_live(self):
        self.make(at(19))
        self.make(at(20), passed=False)
        self.assertEqual(self.builds.live()["build"], at(19))
        self.assertTrue(self.builds.path(at(20), "failed").exists())
        with self.assertRaises(FileNotFoundError):
            self.builds.publish(at(20))

    def test_rollback_returns_to_the_builds_that_were_live_before(self):
        for hour in (17, 18, 19):
            self.make(at(hour))
        self.assertEqual(self.builds.rollback(), at(18))
        self.assertEqual((self.builds.live()["how"], self.live_row()), ("rolled back", at(18)))
        self.assertEqual(self.builds.rollback(), at(17))
        with self.assertRaises(ValueError):
            self.builds.rollback()

    def test_rollback_skips_builds_that_never_went_live_or_were_rolled_back_from(self):
        self.make(at(10))
        self.make(at(11))
        self.make(at(12))  # a bad build
        self.builds.rollback()
        self.make(at(13), publish=False)  # passed, never live (--no-publish or --as-of)
        self.make(at(14))
        self.assertEqual(self.builds.rollback(), at(11))

    def test_pruning_keeps_the_live_build_and_those_before_it(self):
        for hour in range(10, 16):
            self.make(at(hour))
        self.make(at(16), publish=False)
        self.make(at(17), publish=False)
        self.make(at(18), publish=False)
        self.builds.prune(self.log.append)
        # Live (15), the three live before it (12-14), and the two newest that never went live (17, 18).
        self.assertEqual(self.builds.passed(), [at(h) for h in (12, 13, 14, 15, 17, 18)])
        self.assertEqual(self.builds.rollback(), at(14))

    def test_pruning_removes_partial_files_and_old_failed_builds(self):
        self.make(at(10))
        for hour in (11, 12, 13):
            self.make(at(hour), passed=False)
        self.builds.start(at(14)).write_bytes(b"")  # a build that crashed
        self.builds.prune(self.log.append)
        self.assertEqual(self.builds.files(), [(at(10), "passed"), (at(12), "failed"), (at(13), "failed")])

    def test_a_rollback_target_that_was_pruned_is_skipped(self):
        for hour in range(10, 16):
            self.make(at(hour))
        self.builds.prune(self.log.append)
        for target in (14, 13, 12):
            self.assertEqual(self.builds.rollback(), at(target))
        with self.assertRaises(ValueError):  # 10 and 11 were pruned
            self.builds.rollback()

    @unittest.skipUnless(os.name == "nt", "only Windows refuses to delete an open file")
    def test_pruning_skips_a_build_still_in_use(self):
        for hour in range(10, 16):
            self.make(at(hour))
        reader = sqlite3.connect(self.builds.path(at(10)))
        reader.execute("SELECT * FROM t").fetchall()
        try:
            self.builds.prune(self.log.append)
        finally:
            reader.close()
        self.assertIn(at(10), self.builds.passed())
        self.assertNotIn(at(11), self.builds.passed())
        self.assertTrue(any("still in use" in line for line in self.log))

    def test_build_ids_are_start_times_and_never_repeat(self):
        self.assertEqual(self.builds.new_id(START), "20261005T190000Z")
        self.make("20261005T190000Z")
        self.assertEqual(self.builds.new_id(START), "20261005T190000Z-2")
        self.make("20261005T190000Z-2", passed=False)
        self.assertEqual(self.builds.new_id(START), "20261005T190000Z-3")

    def test_one_build_at_a_time(self):
        with self.builds.lock():
            with self.assertRaises(BuildRunning):
                with self.builds.lock(wait=0):
                    pass
        with self.builds.lock(wait=0):  # released once the first build is done
            pass
        self.assertFalse(self.builds.lock_file.exists())

    def test_a_lock_left_by_a_crashed_build_is_taken_over(self):
        self.builds.dir.mkdir(parents=True)
        self.builds.lock_file.write_text("999999999")  # no such process
        alive = builds_module.pid_alive
        builds_module.pid_alive = lambda pid: pid != 999999999 and alive(pid)
        try:
            with self.builds.lock(wait=0):
                self.assertEqual(self.builds.lock_file.read_text(), str(os.getpid()))
        finally:
            builds_module.pid_alive = alive

    def test_the_live_build_is_read_only(self):
        self.make(at(19))
        db = self.builds.connect_live()
        try:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM t")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
