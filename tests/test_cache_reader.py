import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from cache import ResponseCache, query_hash  # noqa: E402
from cache_reader import CacheReader, utc_stamp  # noqa: E402


class CacheReaderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")
        self.readers = []

    def tearDown(self):
        for reader in self.readers:
            reader.close()
        self.cache.db.close()
        self.tmp.cleanup()

    def store(self, endpoint, params, body, status=200):
        """Cache a response, a second after the previous one (the clock can repeat a stamp)."""
        self.cache.store(endpoint, params, "u", status, json.dumps(body).encode(), 5)
        n = self.cache.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        stamp = f"2026-10-05T12:00:{n:02d}.000000+00:00"
        self.cache.db.execute("UPDATE requests SET fetched_at = ? WHERE id = (SELECT MAX(id) FROM requests)", (stamp,))
        self.cache.db.commit()
        return stamp

    def reader(self, as_of=None):
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite", as_of=as_of)
        self.readers.append(reader)
        return reader

    def bodies(self, reader, endpoint, versions=None):
        return [r.body["v"] for r in reader.responses(endpoint, versions)]

    def test_the_newest_successful_response_to_each_request(self):
        self.store("/event", {"gameMode": 1}, {"v": "old"})
        self.store("/event", {"gameMode": 2}, {"v": "two"})
        self.store("/event", {"gameMode": 1}, {"v": "new"})
        self.store("/event", {"gameMode": 2}, {"v": "busy"}, status=503)  # a failed refresh doesn't hide the answer
        self.store("/event", {"gameMode": 3}, {"v": "missing"}, status=404)
        self.store("/pr", {"gameMode": 1}, {"v": "other endpoint"})
        responses = list(self.reader().responses("/event"))
        self.assertEqual([r.body["v"] for r in responses], ["two", "new"])  # oldest response first
        self.assertEqual([r.params for r in responses], [{"gameMode": "2"}, {"gameMode": "1"}])

    def test_as_of_hides_later_responses(self):
        first = self.store("/event", {"gameMode": 1}, {"v": 1})
        second = self.store("/event", {"gameMode": 1}, {"v": 2})
        self.store("/event", {"gameMode": 2}, {"v": 3})
        past = self.reader(as_of=first)
        self.assertEqual(self.bodies(past, "/event"), [1])
        self.assertEqual(past.cutoff(), first)
        self.assertEqual(self.bodies(self.reader(as_of=second), "/event"), [2])
        self.assertEqual(self.bodies(self.reader(), "/event"), [2, 3])
        self.assertGreater(self.reader().cutoff(), second)

    def test_as_of_times_are_read_as_utc(self):
        self.assertEqual(utc_stamp("2026-10-05T14:00:00+02:00"), "2026-10-05T12:00:00.000000+00:00")
        self.assertEqual(utc_stamp("2026-10-05T12:00"), "2026-10-05T12:00:00.000000+00:00")
        self.assertIsNone(self.reader(as_of="2000-01-01").cutoff())

    def test_only_known_query_versions_are_read(self):
        old, new = query_hash("query { old }"), query_hash("query { new }")
        self.store("startgg/PhasePools", {"q": old, "phaseId": 1, "page": 1}, {"v": "1 old"})
        self.store("startgg/PhasePools", {"q": old, "phaseId": 2, "page": 1}, {"v": "2 old"})
        self.store("startgg/PhasePools", {"q": new, "phaseId": 1, "page": 1}, {"v": "1 new"})
        self.store("startgg/PhasePools", {"q": query_hash("query { other }"), "phaseId": 3, "page": 1}, {"v": "3 other"})
        reader = self.reader()
        # A request made with both known versions counts once, with its newest response; unknown versions are skipped.
        self.assertEqual(self.bodies(reader, "startgg/PhasePools", {new, old}), ["2 old", "1 new"])
        self.assertEqual(self.bodies(reader, "startgg/PhasePools", {new}), ["1 new"])
        self.assertEqual(next(reader.responses("startgg/PhasePools", {new})).params["q"], new)

    def test_the_reader_cannot_write(self):
        self.store("/event", {"gameMode": 1}, {"v": 1})
        with self.assertRaises(sqlite3.OperationalError):
            self.reader().db.execute("DELETE FROM requests")


if __name__ == "__main__":
    unittest.main()
