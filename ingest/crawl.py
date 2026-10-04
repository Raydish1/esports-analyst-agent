"""The Stats API crawl (docs/schema-proposal.md §3), run one stage at a time.

    python ingest/crawl.py events    # stage 0: every official event, both modes

Responses are cached (cache.py), so re-running a stage only fetches what's missing.
Later stages are added as Phase 1 goes on.
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone

from statsapi import StatsApi

PAGE_SIZE = 50  # ListEvents' maximum
MODES = {1: "1v1", 2: "2v2"}
FIRST_YEAR = 2017  # the API has nothing earlier


def list_events(api, mode, year=None, log=print):
    """Every official event in one mode (and optionally one year), working around the tie bug.

    ListEvents pages by startTime, and the next page starts strictly before the token, so
    events sharing the boundary startTime can be skipped. Asking for the last startTime + 1
    instead re-reads the boundary, and de-duplicating by ID keeps each event once. If a full
    page brings nothing new (more ties than a page holds), fall back to the server's token.
    """
    events, token = {}, None
    while True:
        params = {"gameMode": mode, "isOfficial": True, "maxResults": PAGE_SIZE,
                  "year": year, "nextToken": token}
        body = api.get("/event", params)
        page = body.get("tournaments") or []
        new = [e for e in page if e["id"] not in events]
        events.update((e["id"], e) for e in new)
        if new:
            token = str(page[-1]["startTime"] + 1)
        elif len(page) == PAGE_SIZE and body.get("nextToken") and body["nextToken"] != token:
            log(f"  a full page of known events at startTime {page[-1]['startTime']}; using the server's token")
            token = body["nextToken"]
        else:
            return list(events.values())


def stage_events(api):
    """Stage 0: official events in both modes, cross-checked against per-year crawls."""
    this_year = datetime.now(timezone.utc).year
    ok = True
    for mode, label in MODES.items():
        full = {e["id"]: e for e in list_events(api, mode)}
        by_year = {}
        for year in range(FIRST_YEAR, this_year + 1):
            by_year.update((e["id"], e) for e in list_events(api, mode, year))
        years = Counter(e["year"] for e in full.values())
        print(f"{label}: {len(full)} official events, {len(by_year)} from the per-year crawls"
              f" ({', '.join(f'{y}: {n}' for y, n in sorted(years.items()))})")
        if full.keys() != by_year.keys():
            ok = False
            print(f"  MISMATCH: only per-year {sorted(by_year.keys() - full.keys())[:5]},"
                  f" only full {sorted(full.keys() - by_year.keys())[:5]}")
    return ok


STAGES = {"events": stage_events}


def main():
    parser = argparse.ArgumentParser(description="Run one stage of the Stats API crawl.")
    parser.add_argument("stage", choices=STAGES, help="events: stage 0, every official event")
    args = parser.parse_args()
    api = StatsApi()
    ok = STAGES[args.stage](api)
    print(f"{api.requests_made} requests made, {api.cache_hits} answered from the cache")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
