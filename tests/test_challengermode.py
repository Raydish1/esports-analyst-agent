import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
os.environ.setdefault("CHALLENGERMODE_REFRESH_KEY", "test-refresh-key")  # the client never sends a request here
import challengermode  # noqa: E402
from cache import ResponseCache  # noqa: E402
from platform_clients import CM_AUTH_URL, CM_REFRESH_MARGIN  # noqa: E402
from statsapi import ApiError  # noqa: E402

LIFETIME = 1200  # seconds, as every real token exchange has given
LATENCY = 0.8  # seconds per simulated request


class FakeClock:
    """Wall and monotonic time in one; sleeping just moves it forward."""

    def __init__(self):
        self.now = 1_790_000_000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += max(0.0, seconds)


class FakeChallengermode:
    """The token exchange and the GraphQL endpoint, enforcing token expiry like the real API."""

    def __init__(self, clock, refuse_as="401"):
        self.clock, self.refuse_as = clock, refuse_as
        self.tokens = {}  # token -> expiry (Unix seconds)
        self.revoked = set()
        self.sent = []  # (time, kind, token) for every request
        self.refused = 0
        self.always_refuse = False

    def post(self, url, payload, headers):
        started = self.clock.now
        self.clock.now += LATENCY
        if url == CM_AUTH_URL:
            token = f"token-{len(self.tokens) + 1}"
            expires = started + LIFETIME
            self.tokens[token] = expires
            self.sent.append((started, "exchange", None))
            stamp = datetime.fromtimestamp(expires, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "4Z"  # 7 digits
            return 200, json.dumps({"value": token, "expiresAt": stamp}).encode(), None, 800
        token = headers["Authorization"].removeprefix("Bearer ")
        self.sent.append((started, "query", token))
        if self.always_refuse or token in self.revoked or started >= self.tokens.get(token, 0):
            self.refused += 1
            if self.refuse_as == "401":
                return 401, b'{"message": "Unauthorized"}', None, 800
            return 200, json.dumps({"errors": [{"message": "not authenticated", "extensions": {
                "code": "AUTH_NOT_AUTHENTICATED"}}], "data": None}).encode(), None, 800
        variables = json.loads(payload)["variables"]
        return 200, json.dumps({"data": {"tournament": {"id": variables["id"]}}}).encode(), None, 800


class ChallengermodeClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cache = ResponseCache(root / "cache", root / "crawl.sqlite")
        self.clock = FakeClock()
        for name, fake in (("sleep", self.clock.sleep), ("monotonic", self.clock.time)):
            patcher = mock.patch.object(challengermode.time, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.cache.db.close()
        self.tmp.cleanup()

    def client(self, server):
        api = challengermode.Challengermode(cache=self.cache, clock=self.clock.time)
        api._send = server.post
        return api

    def query(self, api, n):
        return api.query("Tournament", "query T($id: UUID!) { tournament(tournamentId: $id) { id } }", {"id": f"t{n}"})

    def test_the_token_is_renewed_before_it_expires_mid_crawl(self):
        server = FakeChallengermode(self.clock)
        api = self.client(server)
        for n in range(400):  # 400 requests at 3.5 s apart: about 1,400 s, past the first token's 1,200
            self.assertEqual(self.query(api, n), {"tournament": {"id": f"t{n}"}})
        self.assertEqual(server.refused, 0, "a request went out with an expired token")
        exchanges = [t for t, kind, _ in server.sent if kind == "exchange"]
        self.assertEqual(len(exchanges), 2)  # one at the start, one renewal
        renewal = exchanges[1]
        self.assertLess(renewal, server.tokens["token-1"])  # renewed while the first token was still good
        self.assertGreaterEqual(renewal, server.tokens["token-1"] - CM_REFRESH_MARGIN)
        self.assertEqual({token for _, kind, token in server.sent if kind == "query"}, {"token-1", "token-2"})

    def test_requests_and_token_exchanges_are_at_least_3_5_s_apart(self):
        server = FakeChallengermode(self.clock)
        api = self.client(server)
        for n in range(400):
            self.query(api, n)
        starts = [t for t, _, _ in server.sent]
        self.assertGreaterEqual(min(b - a for a, b in zip(starts, starts[1:])), challengermode.MIN_GAP - 1e-9)

    def test_an_auth_error_gets_a_new_token_and_one_retry(self):
        for refuse_as in ("401", "graphql"):
            with self.subTest(refuse_as=refuse_as):
                server = FakeChallengermode(self.clock, refuse_as)
                api = self.client(server)
                self.query(api, f"{refuse_as}-1")
                server.revoked.add("token-1")  # the server drops the token before its expiresAt
                self.assertEqual(self.query(api, f"{refuse_as}-2"), {"tournament": {"id": f"t{refuse_as}-2"}})
                self.assertEqual(server.refused, 1)
                self.assertEqual(sum(kind == "exchange" for _, kind, _ in server.sent), 2)

    def test_a_second_auth_error_is_final_and_not_replayed(self):
        server = FakeChallengermode(self.clock)
        server.always_refuse = True
        api = self.client(server)
        with self.assertRaises(ApiError) as caught:
            self.query(api, 1)
        self.assertEqual(caught.exception.status, challengermode.AUTH_FAILED)
        self.assertEqual([kind for _, kind, _ in server.sent], ["exchange", "query", "exchange", "query"])
        server.always_refuse = False  # the next run asks again rather than replaying the refusal
        self.assertEqual(self.query(api, 1), {"tournament": {"id": "t1"}})

    def test_cached_queries_make_no_request(self):
        server = FakeChallengermode(self.clock)
        api = self.client(server)
        self.query(api, 1)
        self.query(api, 1)
        self.assertEqual(sum(kind == "query" for _, kind, _ in server.sent), 1)
        self.assertEqual(api.cache_hits, 1)

    def test_a_failing_token_exchange_fails_the_task_rather_than_the_crawl(self):
        server = FakeChallengermode(self.clock)
        api = self.client(server)
        api._send = lambda url, payload, headers: (503, b"busy", None, 5)
        with self.assertRaises(ApiError) as caught:  # the crawl marks the task failed and retries it later
            self.query(api, 1)
        self.assertEqual(caught.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
