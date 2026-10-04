import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
os.environ.setdefault("STARTGG_API_TOKEN", "test-token")  # the client never sends a request here
import startgg  # noqa: E402
from cache import ResponseCache  # noqa: E402
from statsapi import ApiError  # noqa: E402

GOOD = (200, b'{"data": {"event": {"id": 1}}}', None, 5)
NO_DATA = (200, b'{"errors": [{"message": "An unknown error has occurred"}], "data": null}', None, 5)
PARTIAL = (200, b'{"errors": [{"message": "An unknown error has occurred"}], "data": {"event": {"sets": null}}}', None, 5)
PAST_CAP = (200, b'{"errors": [{"message": "Cannot query more than the 10,000th entry", "extensions":'
                 b' {"category": "validation"}}], "data": {"event": {"sets": null}}}', None, 5)
BAD_TOKEN = (400, b'{"success": false, "message": "Invalid authentication token"}', None, 5)


class StartGGTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cache = ResponseCache(root / "cache", root / "crawl.sqlite")
        self.client = startgg.StartGG(cache=self.cache, min_gap=0)
        self.responses = []
        self.client._post = lambda payload: self.responses.pop(0)
        patcher = mock.patch.object(startgg.time, "sleep")  # no real backoff waits
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.cache.db.close()
        self.tmp.cleanup()

    def test_data_comes_back_and_is_cached(self):
        self.responses = [GOOD]
        self.assertEqual(self.client.query("Q", "query { x }", {"a": 1}), {"event": {"id": 1}})
        self.assertEqual(self.client.query("Q", "query { x }", {"a": 1}), {"event": {"id": 1}})
        self.assertEqual(self.client.cache_hits, 1)

    def test_a_changed_query_is_fetched_again(self):
        self.responses = [GOOD, GOOD]
        self.client.query("Q", "query { x }", {"a": 1})
        self.client.query("Q", "query { x y }", {"a": 1})
        self.assertEqual(self.responses, [])

    def test_errors_without_data_are_retried_and_never_reused(self):
        self.responses = [NO_DATA] * startgg.ATTEMPTS
        with self.assertRaises(ApiError) as caught:
            self.client.query("Q", "query { x }", {"a": 2})
        self.assertEqual(caught.exception.status, startgg.GRAPHQL_ERROR)
        self.responses = [GOOD]  # the next run asks again rather than replaying the error
        self.assertEqual(self.client.query("Q", "query { x }", {"a": 2}), {"event": {"id": 1}})

    def test_errors_alongside_data_are_retried_too(self):
        self.responses = [PARTIAL, GOOD]
        self.assertEqual(self.client.query("Q", "query { x }", {"a": 4}), {"event": {"id": 1}})

    def test_client_errors_are_final(self):
        self.responses = [(400, b'{"success": false, "message": "Syntax Error"}', None, 5), GOOD]
        with self.assertRaises(ApiError) as caught:
            self.client.query("Q", "query { x }", {"a": 3})
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(len(self.responses), 1)  # no retry

    def test_a_refused_query_is_final(self):
        self.responses = [PAST_CAP, GOOD]
        with self.assertRaises(ApiError) as caught:
            self.client.query("Q", "query { x }", {"page": 251})
        self.assertEqual(caught.exception.status, startgg.QUERY_REFUSED)
        self.assertEqual(len(self.responses), 1)  # no retry

    def test_a_refused_token_is_logged_as_401_and_never_reused(self):
        self.responses = [BAD_TOKEN]
        with self.assertRaises(ApiError) as caught:
            self.client.query("Q", "query { x }", {"a": 5})
        self.assertEqual(caught.exception.status, startgg.AUTH_FAILED)
        self.responses = [GOOD]  # a fixed token: the next run asks again
        self.assertEqual(self.client.query("Q", "query { x }", {"a": 5}), {"event": {"id": 1}})


if __name__ == "__main__":
    unittest.main()
