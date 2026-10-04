"""Cached client for the start.gg GraphQL API (docs/platform-api-survey.md).

Works like the Stats API client: every response goes into the cache (cache.py) before
it's parsed, keyed by the query's name, a hash of its text and its variables, and a query
already cached is answered from there. Requests are at least 1 s apart (start.gg allows 80
a minute), with backoff on timeouts, 429s, 5xx responses and GraphQL errors. A query
start.gg refuses outright (too complex, or paged past its 10,000th entry) is final, and a
refused token is logged as a 401, which the cache never replays. The token comes from
STARTGG_API_TOKEN in .env and only ever goes into the Authorization header.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from cache import ResponseCache
from platform_clients import USER_AGENT, load_env
from statsapi import ApiError

URL = "https://api.start.gg/gql/alpha"
MIN_GAP = 1.0  # seconds between requests
TIMEOUT = 60
ATTEMPTS = 5
GRAPHQL_ERROR = 520  # status recorded for a 200 response with GraphQL errors; retried later
QUERY_REFUSED = 422  # status recorded for a query start.gg refuses outright; final
AUTH_FAILED = 401  # status recorded when start.gg refuses the token


class StartGG:
    def __init__(self, cache=None, min_gap=MIN_GAP):
        load_env()
        if not os.environ.get("STARTGG_API_TOKEN"):
            raise SystemExit("STARTGG_API_TOKEN is not set; add it to .env (see .env.example)")
        self.cache = cache or ResponseCache()
        self.min_gap = min_gap
        self.last = 0.0
        self.requests_made = 0
        self.cache_hits = 0
        self.task = None  # set by the crawl, so the request log says which task made each request

    def query(self, name, document, variables, refresh=False):
        """The `data` of a GraphQL query. Raises ApiError when it can't be had."""
        endpoint = f"startgg/{name}"
        params = {"q": hashlib.sha256(document.encode()).hexdigest()[:12], **variables}
        if not refresh:
            cached = self.cache.newest(endpoint, params)
            if cached:
                self.cache_hits += 1
                status, body = cached
                if status != 200:
                    raise ApiError(status, endpoint, variables, body[:300].decode("utf-8", "replace"))
                return json.loads(body)["data"]
        payload = json.dumps({"query": document, "variables": variables}).encode()
        for attempt in range(ATTEMPTS):
            status, body, error, ms = self._post(payload)
            status, problem = _classify(status, body)
            error = error or problem
            self.cache.store(endpoint, params, URL, status, body, ms, error, task=self.task)
            if status == 200:
                return json.loads(body)["data"]
            if status is not None and 400 <= status < 500 and status != 429:
                raise ApiError(status, endpoint, variables, problem or body[:300].decode("utf-8", "replace"))
            if attempt < ATTEMPTS - 1:
                time.sleep(2 ** attempt)  # 1, 2, 4, 8 s
        raise ApiError(status, endpoint, variables, error or "retries exhausted")

    def _post(self, payload):
        delay = self.min_gap - (time.monotonic() - self.last)
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()
        self.requests_made += 1
        req = urllib.request.Request(URL, data=payload, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT,
            "Authorization": "Bearer " + os.environ["STARTGG_API_TOKEN"]})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                status, body, error = res.status, res.read(), None
        except urllib.error.HTTPError as e:
            status, body, error = e.code, e.read(), None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            status, body, error = None, None, repr(e)
        return status, body, error, round((time.monotonic() - started) * 1000)


def _classify(status, body):
    """The status to record and act on for one response, and a description of what's wrong."""
    if status == 400 and b"Invalid authentication token" in (body or b""):
        return AUTH_FAILED, "start.gg refused the token"
    if status != 200:
        return status, None
    try:
        parsed = json.loads(body)
    except ValueError:
        parsed = None
    if not isinstance(parsed, dict):
        return GRAPHQL_ERROR, "the response isn't a JSON object"
    errors = parsed.get("errors") or []
    if parsed.get("data") is not None and not errors:
        return 200, None
    messages = [str(parsed.get("message") or "")] + [str(e.get("message") or "") for e in errors]
    problem = "; ".join(m for m in messages if m)[:300] or "no data"
    refused = (any((e.get("extensions") or {}).get("category") == "validation" for e in errors)
               or any("complexity" in m.lower() for m in messages))
    return (QUERY_REFUSED if refused else GRAPHQL_ERROR), problem
