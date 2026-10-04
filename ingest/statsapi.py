"""Client for the Brawlhalla Esports Stats API (docs/api-survey.md).

Plain HTTP GETs, one at a time and at least 0.5 s apart, with the project's User-Agent.
Timeouts, 429s and 5xx responses are retried with exponential backoff; other 4xx
responses are final and not retried. Every response, errors included, goes into the
cache (cache.py) before anything parses it, and a request that's already cached is
answered from there unless refresh=True.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from cache import ResponseCache, normalize_params

BASE_URL = "https://api.brawltools.com/v2"
USER_AGENT = "esports-analyst-agent/0.1 (personal research project)"
MIN_GAP = 0.5  # seconds between requests
TIMEOUT = 30  # seconds per request
ATTEMPTS = 5  # per request, when it times out or gets a 429 or 5xx


class ApiError(Exception):
    def __init__(self, status, endpoint, params, detail):
        super().__init__(f"HTTP {status} for {endpoint} {params}: {detail}")
        self.status = status


class StatsApi:
    def __init__(self, cache=None, min_gap=MIN_GAP):
        self.cache = cache or ResponseCache()
        self.min_gap = min_gap
        self.last = 0.0
        self.requests_made = 0
        self.cache_hits = 0

    def get(self, endpoint, params=None, refresh=False):
        """The parsed JSON body of GET endpoint?params.

        Raises ApiError for a final non-200 status (already recorded in the cache).
        """
        params = params or {}
        if not refresh:
            cached = self.cache.newest(endpoint, params)
            if cached:
                self.cache_hits += 1
                return self._parse(endpoint, params, *cached)
        url = f"{BASE_URL}{endpoint}?{urllib.parse.urlencode(normalize_params(params), safe=',')}"
        for attempt in range(ATTEMPTS):
            status, body, error, ms = self._fetch(url)
            self.cache.store(endpoint, params, url, status, body, ms, error)
            if status is not None and status < 500 and status != 429:
                return self._parse(endpoint, params, status, body)
            if attempt < ATTEMPTS - 1:
                time.sleep(2 ** attempt)  # 1, 2, 4, 8 s
        raise ApiError(status, endpoint, params, error or "retries exhausted")

    def _fetch(self, url):
        delay = self.min_gap - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()
        self.requests_made += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                status, body, error = res.status, res.read(), None
        except urllib.error.HTTPError as e:
            status, body, error = e.code, e.read(), None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            status, body, error = None, None, repr(e)
        return status, body, error, round((time.monotonic() - started) * 1000)

    @staticmethod
    def _parse(endpoint, params, status, body):
        if status != 200:
            raise ApiError(status, endpoint, params, body[:300].decode("utf-8", "replace"))
        return json.loads(body)
