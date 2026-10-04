"""Response cache and request log for the crawl (docs/schema-proposal.md §3).

Every response is stored here before anything parses it: the body, gzipped, in
data/raw/cache/<endpoint>/<key[:2]>/<key>.<fetched_at>.json.gz, and one row per request
in the `requests` table of data/db/crawl.sqlite. Files are never modified. Fetching the
same request again adds a file, and readers use the newest one, so older responses stay
available (the builder takes former player names from them).
"""

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "raw" / "cache"
CRAWL_DB = ROOT / "data" / "db" / "crawl.sqlite"


def normalize_params(params):
    """Sorted (name, value) pairs: lists comma-joined, booleans lowercase, None dropped."""
    pairs = []
    for name in sorted(params):
        value = params[name]
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = ",".join(str(v) for v in value)
        elif isinstance(value, bool):
            value = "true" if value else "false"
        pairs.append((name, str(value)))
    return pairs


def request_key(endpoint, params):
    canonical = endpoint + "?" + "&".join(f"{k}={v}" for k, v in normalize_params(params))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def endpoint_dir(endpoint):
    return endpoint.strip("/").replace("/", "_") or "root"  # '/player/placement' -> 'player_placement'


class ResponseCache:
    def __init__(self, cache_dir=CACHE_DIR, db_path=CRAWL_DB):
        self.cache_dir = Path(cache_dir)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_path, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
              id          INTEGER PRIMARY KEY,
              key         TEXT NOT NULL,
              endpoint    TEXT NOT NULL,
              params      TEXT NOT NULL,   -- normalized, as JSON
              url         TEXT NOT NULL,
              status      INTEGER,         -- NULL when no response came back
              error       TEXT,            -- the network error, if any
              ms          INTEGER,
              fetched_at  TEXT NOT NULL,
              path        TEXT,            -- cache file relative to the cache directory
              bytes       INTEGER,         -- size of that file
              task        TEXT             -- the crawl task that made the request
            );
            CREATE INDEX IF NOT EXISTS requests_key ON requests (key, fetched_at);
        """)
        self._migrate()

    def _migrate(self):
        """Add the columns that came after stage 0's first run."""
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(requests)")}
        if "task" not in columns:
            self.db.execute("ALTER TABLE requests ADD COLUMN task TEXT")
            self.db.execute("UPDATE requests SET task = 'events:first-run' WHERE endpoint = '/event'")
        if "bytes" not in columns:
            self.db.execute("ALTER TABLE requests ADD COLUMN bytes INTEGER")
            for row_id, path in self.db.execute("SELECT id, path FROM requests WHERE path IS NOT NULL").fetchall():
                self.db.execute("UPDATE requests SET bytes = ? WHERE id = ?",
                                ((self.cache_dir / path).stat().st_size, row_id))
        self.db.commit()

    def newest(self, endpoint, params):
        """The newest usable cached response, as (status, body bytes), or None.

        Network errors and 5xx responses don't count, so the next run retries them.
        """
        row = self.db.execute(
            "SELECT status, path FROM requests WHERE key = ? AND path IS NOT NULL AND status < 500"
            " ORDER BY fetched_at DESC, id DESC LIMIT 1", (request_key(endpoint, params),)).fetchone()
        if not row:
            return None
        status, path = row
        return status, gzip.decompress((self.cache_dir / path).read_bytes())

    def store(self, endpoint, params, url, status, body, ms, error=None, task=None):
        """Record one request; write its body, if any, to a new cache file."""
        key = request_key(endpoint, params)
        fetched_at = datetime.now(timezone.utc)
        path = size = None
        while body is not None and path is None:
            rel = Path(endpoint_dir(endpoint)) / key[:2] / f"{key}.{fetched_at:%Y%m%dT%H%M%S%fZ}.json.gz"
            (self.cache_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            data = gzip.compress(body)
            try:
                with open(self.cache_dir / rel, "xb") as f:  # "x": never overwrite a cache file
                    f.write(data)
                path, size = rel.as_posix(), len(data)
            except FileExistsError:  # same request stored twice in one microsecond
                fetched_at += timedelta(microseconds=1)
        self.db.execute(
            "INSERT INTO requests (key, endpoint, params, url, status, error, ms, fetched_at, path, bytes, task)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (key, endpoint, json.dumps(normalize_params(params)), url, status, error, ms,
             fetched_at.isoformat(timespec="microseconds"), path, size, task))
        self.db.commit()
        return key
