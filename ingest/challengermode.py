"""Cached client for the Challengermode GraphQL API (docs/platform-api-survey.md).

Works like the start.gg client (startgg.py): every response goes into the cache (cache.py)
before it's parsed, keyed by the query's name, a hash of its text and its variables, and a
query already cached is answered from there. Requests, token exchanges included, are at
least 3.5 s apart (bots may make 20 a minute), with backoff on timeouts, 429s, 5xx responses
and GraphQL errors that come back without data.

The access token is the survey's (platform_clients.AccessToken): renewed shortly before its
expiresAt, and after an auth error the client gets a new one and retries once. The refresh
key and the token only ever go into the exchange body and the Authorization header; the
exchange isn't cached, and an auth failure is logged with status 401, which the cache never
replays.

A query that runs past the server's 15 s budget comes back as HTTP 400 with error code
HC0045. That's a timeout, not a refusal: it's logged as 504 and retried, and an HC0045 400
logged before this rule existed is never taken as an answer either.
"""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from cache import ResponseCache
from platform_clients import USER_AGENT, AccessToken, is_cm_auth_error, load_env
from statsapi import ApiError

URL = "https://publicapi.challengermode.com/graphql"
MIN_GAP = 3.5  # seconds between requests
TIMEOUT = 60
ATTEMPTS = 5
GRAPHQL_ERROR = 520  # status recorded for a 200 response whose errors left no data; retried later
AUTH_FAILED = 401  # status recorded for any response that refused the token
TIMED_OUT = 504  # status recorded for a query that ran past the server's time budget (HC0045); retried
SERVER_TIMEOUT = b'"HC0045"'


class Challengermode:
    def __init__(self, cache=None, min_gap=MIN_GAP, clock=time.time):
        load_env()
        if not os.environ.get("CHALLENGERMODE_REFRESH_KEY"):
            raise SystemExit("CHALLENGERMODE_REFRESH_KEY is not set; add it to .env (see .env.example)")
        self.cache = cache or ResponseCache()
        self.min_gap = min_gap
        self.last = None
        self.requests_made = 0
        self.cache_hits = 0
        self.task = None  # set by the crawl, so the request log says which task made each request
        self.token = AccessToken(self._exchange, clock=clock)

    def query(self, name, document, variables, refresh=False):
        """The `data` of a GraphQL query. Raises ApiError when it can't be had."""
        endpoint = f"challengermode/{name}"
        params = {"q": hashlib.sha256(document.encode()).hexdigest()[:12], **variables}
        if not refresh:
            cached = self.cache.newest(endpoint, params)
            if cached and not (cached[0] == 400 and SERVER_TIMEOUT in cached[1]):
                self.cache_hits += 1
                status, body = cached
                if status != 200:
                    raise ApiError(status, endpoint, variables, body[:300].decode("utf-8", "replace"))
                return json.loads(body)["data"]
        payload = json.dumps({"query": document, "variables": variables}).encode()
        attempt, renewed = 0, False
        while True:
            status, body, error, ms = self._post(URL, payload, {"Authorization": "Bearer " + self.token.get()})
            parsed = _parse(body)
            if is_cm_auth_error(status, parsed):
                status = AUTH_FAILED
            elif status == 400 and SERVER_TIMEOUT in (body or b""):
                status, error = TIMED_OUT, "the query ran past Challengermode's 15 s budget (HC0045)"
            elif status == 200 and (not isinstance(parsed, dict) or (parsed.get("errors") and not parsed.get("data"))):
                status, error = GRAPHQL_ERROR, body[:300].decode("utf-8", "replace")
            self.cache.store(endpoint, params, URL, status, body, ms, error, task=self.task)
            if status == AUTH_FAILED and not renewed:  # the token was refused: get a new one, once
                self.token.invalidate()
                renewed = True
                continue
            if status == 200:
                return parsed["data"]
            if status is not None and 400 <= status < 500 and status != 429:
                raise ApiError(status, endpoint, variables, body[:300].decode("utf-8", "replace"))
            attempt += 1
            if attempt >= ATTEMPTS:
                raise ApiError(status, endpoint, variables, error or "retries exhausted")
            time.sleep(2 ** (attempt - 1))  # 1, 2, 4, 8 s

    def _exchange(self, url, payload):
        """The token exchange for AccessToken: (status, parsed body). Never cached or logged."""
        data = json.dumps(payload).encode()
        for attempt in range(ATTEMPTS):
            status, body, error, ms = self._post(url, data, {})
            if status is not None and status < 500 and status != 429:
                break
            if attempt < ATTEMPTS - 1:
                time.sleep(2 ** attempt)
        return status, _parse(body)

    def _post(self, url, payload, headers):
        """One request, sent at least min_gap after the previous one started."""
        if self.last is not None:
            delay = self.min_gap - (time.monotonic() - self.last)
            if delay > 0:
                time.sleep(delay)
        self.last = time.monotonic()
        self.requests_made += 1
        return self._send(url, payload, headers)

    def _send(self, url, payload, headers):
        req = urllib.request.Request(url, data=payload, method="POST", headers={
            "Content-Type": "application/json", "User-Agent": USER_AGENT, **headers})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                status, body, error = res.status, res.read(), None
        except urllib.error.HTTPError as e:
            status, body, error = e.code, e.read(), None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            status, body, error = None, None, repr(e)
        return status, body, error, round((time.monotonic() - started) * 1000)


def _parse(body):
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None
