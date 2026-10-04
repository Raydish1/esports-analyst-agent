"""Small clients for the start.gg and Challengermode GraphQL APIs.

Credentials come from the environment, or from .env at the repo root:
STARTGG_API_TOKEN and CHALLENGERMODE_REFRESH_KEY. They only ever go into request
headers or the token-exchange body; nothing here prints or stores them, and the
Challengermode access token is redacted before its response is saved.

Each client keeps a minimum gap between its requests (start.gg allows 80 per minute,
Challengermode bots 20 per minute) and saves every response body under
data/raw/platforms/<platform>/, with a manifest of what was asked and what came back.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from statsapi import ApiError

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "platforms"
SAFE_HEADERS = re.compile(r"rate|limit|remaining|reset|retry|request-id|^date$", re.I)
# Challengermode's Cloudflare front end rejects Python's default user agent (error 1010).
USER_AGENT = "esports-analyst-agent/0.1 (personal research project)"
CM_AUTH_URL = "https://publicapi.challengermode.com/mk1/v1/auth/access_keys"
CM_REFRESH_MARGIN = 120  # seconds before a Challengermode token's expiresAt to fetch a new one


def load_env(path=ROOT / ".env"):
    """Load KEY=VALUE lines into os.environ without overriding what's already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AccessToken:
    """A Challengermode access token, exchanged for CHALLENGERMODE_REFRESH_KEY.

    get() renews it CM_REFRESH_MARGIN seconds before its expiresAt, so a long crawl never
    sends an expired token; invalidate() forces a new one, for the single retry after an
    auth error. post(url, payload) makes the HTTP call and returns (status, parsed JSON body
    or None); clock() gives Unix seconds. The token is kept in memory only, and
    last_response holds the exchange's response with the token redacted.
    """

    def __init__(self, post, margin=CM_REFRESH_MARGIN, clock=time.time):
        self.post, self.margin, self.clock = post, margin, clock
        self.value, self.expires, self.expires_at = None, 0.0, None
        self.refreshes = 0
        self.last_response = None

    def get(self):
        if not self.value or self.clock() >= self.expires - self.margin:
            self.refresh()
        return self.value

    def invalidate(self):
        self.value = None

    def refresh(self):
        payload = {"refreshKey": os.environ["CHALLENGERMODE_REFRESH_KEY"]}
        status, body = self.post(CM_AUTH_URL, payload)
        if status == 400 and "PackedRefreshKey" in json.dumps(body):  # field name as the API reports it
            payload = {"packedRefreshKey": payload["refreshKey"]}
            status, body = self.post(CM_AUTH_URL, payload)
        if status is None or status >= 500 or status == 429:  # worth trying again later
            raise ApiError(status, "challengermode/auth", {}, "token exchange failed")
        if status != 200 or not isinstance(body, dict):
            raise SystemExit(f"Challengermode token exchange failed with HTTP {status}")
        token_field = next((k for k in ("value", "accessKey", "accessToken", "token") if k in body), None)
        if not token_field:
            raise SystemExit("Challengermode token exchange returned no recognisable token field: "
                             + ", ".join(sorted(body)))
        self.value = body[token_field]
        self.expires_at = body.get("expiresAt")
        if self.expires_at:
            self.expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00")).timestamp()
        else:
            self.expires = self.clock() + 15 * 60
        self.refreshes += 1
        self.last_response = {k: ("<redacted>" if k == token_field else v) for k, v in body.items()}


class Recorder:
    """Saves response bodies (one file each) and a manifest for one platform."""

    def __init__(self, platform):
        self.dir = RAW_DIR / platform
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = []
        self.used = set()

    def save(self, label, body, meta):
        name = re.sub(r"[^A-Za-z0-9._+-]+", "_", label)
        candidate, n = f"{name}.json", 2
        while candidate.lower() in self.used:  # Windows file names are case-insensitive
            candidate, n = f"{name}__{n}.json", n + 1
        self.used.add(candidate.lower())
        (self.dir / candidate).write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        self.manifest.append({"file": candidate, **meta})
        return candidate

    def write_manifest(self):
        (self.dir / "_manifest.json").write_text(json.dumps(self.manifest, indent=2), encoding="utf-8")


class GraphQLClient:
    url = None
    min_gap = 1.0

    def __init__(self, platform):
        self.recorder = Recorder(platform)
        self.last_request = 0.0

    def _wait(self):
        delay = self.min_gap - (time.monotonic() - self.last_request)
        if delay > 0:
            time.sleep(delay)
        self.last_request = time.monotonic()

    def _post(self, url, payload, headers):
        """POST JSON; returns (status, parsed body or raw text, safe response headers, ms)."""
        self._wait()
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                status, raw, hdrs = res.status, res.read(), res.headers
        except urllib.error.HTTPError as e:
            status, raw, hdrs = e.code, e.read(), e.headers
        ms = round((time.monotonic() - started) * 1000)
        text = raw.decode("utf-8", "replace")
        try:
            body = json.loads(text)
        except ValueError:
            body = {"_nonJsonBody": text[:2000]}
        safe = {k: v for k, v in (hdrs or {}).items() if SAFE_HEADERS.search(k)}
        return status, body, safe, ms

    def auth_headers(self):
        raise NotImplementedError

    def is_auth_error(self, status, body):
        return status == 401

    def query(self, label, query, variables=None):
        """Run one GraphQL request, save its body, and return (status, body)."""
        for attempt in (1, 2):
            status, body, headers, ms = self._post(self.url, {"query": query, "variables": variables or {}},
                                                   self.auth_headers())
            if attempt == 1 and self.is_auth_error(status, body):
                self.on_auth_error()
                continue
            break
        errors = body.get("errors") if isinstance(body, dict) else None
        self.recorder.save(label, body, {
            "label": label, "url": self.url, "variables": variables or {}, "status": status, "ms": ms,
            "attempts": attempt, "fetched_at": now_iso(), "headers": headers,
            "errors": [e.get("message") for e in errors][:5] if errors else None,
            "query": " ".join(query.split()),
        })
        flag = f"  ERRORS: {errors[0].get('message')[:160]}" if errors else ""
        print(f"[{len(self.recorder.manifest):>3}] {status} {label} ({ms} ms){flag}")
        return status, body

    def on_auth_error(self):
        pass


class StartGG(GraphQLClient):
    url = "https://api.start.gg/gql/alpha"
    min_gap = 1.0  # 80 requests per minute allowed

    def __init__(self):
        super().__init__("startgg")
        if not os.environ.get("STARTGG_API_TOKEN"):
            raise SystemExit("STARTGG_API_TOKEN is not set")

    def auth_headers(self):
        return {"Authorization": "Bearer " + os.environ["STARTGG_API_TOKEN"]}


def is_cm_auth_error(status, body):
    """A 401, or a GraphQL AUTH_NOT_AUTHENTICATED error: the token, not the request, was refused."""
    if status == 401:
        return True
    errors = body.get("errors") if isinstance(body, dict) else None
    return bool(errors) and any((e.get("extensions") or {}).get("code") == "AUTH_NOT_AUTHENTICATED" for e in errors)


class Challengermode(GraphQLClient):
    url = "https://publicapi.challengermode.com/graphql"
    min_gap = 3.5  # bots may make 20 requests per minute

    def __init__(self):
        super().__init__("challengermode")
        if not os.environ.get("CHALLENGERMODE_REFRESH_KEY"):
            raise SystemExit("CHALLENGERMODE_REFRESH_KEY is not set")
        self.token = AccessToken(self._exchange)
        self.token_log = []  # expiry times only, for the report

    def _exchange(self, url, payload):
        status, body, headers, ms = self._post(url, payload, {})
        self._last_exchange = (status, headers, ms)
        return status, body

    def auth_headers(self):
        refreshes = self.token.refreshes
        token = self.token.get()
        if self.token.refreshes != refreshes:  # a new token: record the exchange, token redacted
            status, headers, ms = self._last_exchange
            self.token_log.append({"fetched_at": now_iso(), "expiresAt": self.token.expires_at,
                                   "lifetime_s": round(self.token.expires - time.time())})
            self.recorder.save("auth_access_key", self.token.last_response, {
                "label": "auth_access_key", "url": CM_AUTH_URL, "status": status, "ms": ms,
                "fetched_at": now_iso(), "headers": headers, "note": "token redacted"})
            print(f"[auth] Challengermode token obtained; expires {self.token.expires_at}")
        return {"Authorization": "Bearer " + token}

    def is_auth_error(self, status, body):
        return is_cm_auth_error(status, body)

    def on_auth_error(self):
        self.token.invalidate()  # force a fresh token for the single retry
