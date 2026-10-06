"""Read-only access to the crawl's response cache, for the builder (docs/build-plan.md §1).

The request log in data/db/crawl.sqlite indexes the cache: one row per request, with its
endpoint, normalized parameters, status, fetch time and response file. The builder reads the
newest successful (200) response to each request. Given an as-of time, it reads only responses
fetched up to then, so a build can be repeated later from the same append-only cache. The
builder never reads the crawl's planning tables (crawl_*) and never writes to the log.

A GraphQL request records its query's version in the 'q' parameter (cache.query_hash). Reading
an endpoint with `versions` skips responses to any other version, since the builder can't vouch
for their fields. When one request was made with two known versions, only the newer response
counts. Example: the pilot's PhasePools pages that were never fetched with the current query.
"""

import gzip
import json
import sqlite3
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

from cache import CACHE_DIR, CRAWL_DB

Response = namedtuple("Response", "params fetched_at body")  # params: the request's, as strings; body: parsed JSON


def utc_stamp(text):
    """A time as the request log writes it ('2026-10-05T12:00:00.000000+00:00'), so stamps compare
    as text. A time without a zone is taken as UTC."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


class CacheReader:
    def __init__(self, cache_dir=CACHE_DIR, db_path=CRAWL_DB, as_of=None):
        self.cache_dir = Path(cache_dir)
        self.as_of = utc_stamp(as_of) if as_of else None
        self.db = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)

    def close(self):
        self.db.close()

    def _successful(self, columns, endpoint=None):
        where, args = ["status = 200", "path IS NOT NULL"], []
        if endpoint is not None:
            where.append("endpoint = ?")
            args.append(endpoint)
        if self.as_of:
            where.append("fetched_at <= ?")
            args.append(self.as_of)
        return self.db.execute(f"SELECT {columns} FROM requests WHERE {' AND '.join(where)}"
                               " ORDER BY fetched_at, id", args)

    def cutoff(self):
        """The newest fetch the build can see, or None when the cache has nothing for it."""
        return self._successful("MAX(fetched_at)").fetchone()[0]

    def entries(self, endpoint, versions=None):
        """(params, fetched_at, path) of the newest successful response to each request to an
        endpoint, oldest first. With `versions` (query hashes), only responses to those versions count."""
        newest = {}
        for params_json, fetched_at, path in self._successful("params, fetched_at, path", endpoint):
            params = dict(json.loads(params_json))
            if versions is not None and params.get("q") not in versions:
                continue
            request = tuple(sorted((k, v) for k, v in params.items() if k != "q"))
            newest[request] = (params, fetched_at, path)  # rows come oldest first, so the newest stays
        return sorted(newest.values(), key=lambda entry: entry[1])

    def load(self, path):
        """A cached response's parsed body, by its path from entries()."""
        return json.loads(gzip.decompress((self.cache_dir / path).read_bytes()))

    def responses(self, endpoint, versions=None):
        """Each response from entries(), parsed, one at a time."""
        for params, fetched_at, path in self.entries(endpoint, versions):
            yield Response(params, fetched_at, self.load(path))
