import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from cache import ResponseCache, request_key  # noqa: E402


class RequestKeyTest(unittest.TestCase):
    def test_order_none_and_list_form_dont_matter(self):
        a = request_key("/event", {"gameMode": 1, "isOfficial": True, "nextToken": None, "ids": [3, 4]})
        b = request_key("/event", {"ids": "3,4", "isOfficial": "true", "gameMode": "1"})
        self.assertEqual(a, b)

    def test_endpoint_and_values_do(self):
        a = request_key("/event", {"gameMode": 1})
        self.assertNotEqual(a, request_key("/player/placement", {"gameMode": 1}))
        self.assertNotEqual(a, request_key("/event", {"gameMode": 2}))


class ResponseCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")

    def tearDown(self):
        self.cache.db.close()
        self.tmp.cleanup()

    def test_files_are_never_overwritten_and_the_newest_wins(self):
        params = {"gameMode": 1}
        self.cache.store("/event", params, "u", 200, b'{"v": 1}', 5)
        self.cache.store("/event", params, "u", 200, b'{"v": 2}', 5)
        self.assertEqual(len(list((self.root / "cache").rglob("*.json.gz"))), 2)
        self.assertEqual(self.cache.newest("/event", params), (200, b'{"v": 2}'))

    def test_client_errors_are_reused_but_server_errors_are_not(self):
        self.cache.store("/player/1", {}, "u", 404, b"not found", 5)
        self.assertEqual(self.cache.newest("/player/1", {}), (404, b"not found"))
        self.cache.store("/event", {"gameMode": 2}, "u", 503, b"busy", 5)
        self.cache.store("/event", {"gameMode": 2}, "u", None, None, 5, error="timeout")
        self.assertIsNone(self.cache.newest("/event", {"gameMode": 2}))
        self.assertEqual(self.cache.db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
