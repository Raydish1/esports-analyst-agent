import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import crawl  # noqa: E402


class FakeEventApi:
    """Mimics ListEvents, bug included: newest first, and the next page starts strictly before the token."""

    def __init__(self, start_times):
        self.events = sorted(({"id": f"e{i}", "startTime": t, "year": 2020} for i, t in enumerate(start_times)),
                             key=lambda e: (-e["startTime"], e["id"]))
        self.calls = []

    def get(self, endpoint, params):
        self.calls.append(dict(params))
        token = params.get("nextToken")
        rows = [e for e in self.events if token is None or e["startTime"] < int(token)]
        page = rows[:params["maxResults"]]
        full = len(page) == params["maxResults"]
        return {"tournaments": page, "nextToken": str(page[-1]["startTime"]) if full else None}


def naive_list(api, size):
    """Following the server's own tokens, as the SDK does."""
    events, token = [], None
    while True:
        body = api.get("/event", {"maxResults": size, "nextToken": token})
        events += body["tournaments"]
        token = body["nextToken"]
        if not token:
            return events


@mock.patch.object(crawl, "PAGE_SIZE", 3)
class ListEventsTest(unittest.TestCase):
    def test_tie_at_a_page_boundary_is_kept(self):
        start_times = [100, 90, 80, 80, 70, 60]  # the two 80s straddle the first page boundary
        self.assertEqual(len(naive_list(FakeEventApi(start_times), 3)), 5)  # the bug: one 80 is skipped
        events = crawl.list_events(FakeEventApi(start_times), mode=1, log=lambda *_: None)
        self.assertEqual(sorted(e["id"] for e in events), [f"e{i}" for i in range(6)])

    def test_more_ties_than_a_page_holds_falls_back_and_finishes(self):
        logged = []
        api = FakeEventApi([100, 50, 50, 50, 50, 40])  # four 50s, pages of three
        events = crawl.list_events(api, mode=1, log=logged.append)
        self.assertEqual(len(logged), 1)  # the fallback is reported
        self.assertEqual(len(events), 5)  # one 50 is lost, as documented
        self.assertLess(len(api.calls), 10)

    def test_parameters(self):
        api = FakeEventApi([10])
        crawl.list_events(api, mode=2, year=2024, log=lambda *_: None)
        first = api.calls[0]
        self.assertEqual((first["gameMode"], first["isOfficial"], first["year"], first["nextToken"]), (2, True, 2024, None))


if __name__ == "__main__":
    unittest.main()
