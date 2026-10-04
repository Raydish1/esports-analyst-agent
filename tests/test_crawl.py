import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import crawl  # noqa: E402
from statsapi import ApiError  # noqa: E402
from tasks import MAX_ATTEMPTS, RunLock, StopFlag, TaskQueue, connect  # noqa: E402


class FakeApi:
    """Answers the crawl's requests from canned responses and counts every call."""

    def __init__(self, routes):
        self.routes, self.calls, self.task = routes, [], None
        self.requests_made = self.cache_hits = 0

    def get(self, endpoint, params):
        self.calls.append((endpoint, tuple(sorted((k, str(v)) for k, v in params.items()))))
        self.requests_made += 1
        answer = self.routes[endpoint](params)
        if isinstance(answer, Exception):
            raise answer
        return answer


def pr_route(params):  # three pages of three players per mode and region
    page, base = params["page"], params["gameMode"] * 1000 + crawl.REGIONS.index(params["region"]) * 100
    return {"prPlayers": [{"playerId": base + page * 10 + i} for i in range(3)], "totalPages": 3}


class CrawlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name) / "crawl.sqlite", schema=crawl.CRAWL_SCHEMA)
        self.args = SimpleNamespace(sample=None)
        self.log = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_stage(self, api, stage, stop_after=None):
        stop, ran = StopFlag(), []

        def on_task():
            ran.append(1)
            if stop_after and len(ran) >= stop_after:
                stop.requested = True
        return crawl.run_stage(self.db, api, stage, self.args, self.log.append, stop, on_task)

    def statuses(self, stage):
        return dict(self.db.execute("SELECT status, COUNT(*) FROM tasks WHERE stage = ? GROUP BY status", (stage,)))

    def test_stopping_and_rerunning_never_repeats_a_finished_task(self):
        api = FakeApi({"/pr": pr_route})
        self.assertEqual(self.run_stage(api, "pr", stop_after=4), "stopped")
        self.assertEqual(self.statuses("pr")["done"], 4)
        self.assertEqual(self.run_stage(api, "pr"), "finished")
        self.assertEqual(self.statuses("pr"), {"done": 30})  # 2 modes x 5 regions x 3 pages
        self.assertEqual(len(api.calls), len(set(api.calls)), "a page was requested twice")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM crawl_players").fetchone()[0], 90)

    def test_a_task_left_running_by_a_crash_runs_again(self):
        api = FakeApi({"/pr": pr_route})
        self.run_stage(api, "pr", stop_after=1)
        with self.db:  # as if the process died in the middle of the next task
            self.db.execute("UPDATE tasks SET status = 'running' WHERE task_key = (SELECT task_key FROM tasks"
                            " WHERE status = 'pending' ORDER BY rowid LIMIT 1)")
        self.assertEqual(self.run_stage(api, "pr"), "finished")
        self.assertEqual(self.statuses("pr"), {"done": 30})

    def test_failures_are_retried_on_the_next_run_and_client_errors_are_not(self):
        broken = {"NA": ApiError(503, "/pr", {}, "busy"), "EU": ApiError(400, "/pr", {}, "bad region")}
        api = FakeApi({"/pr": lambda p: broken.get(p["region"]) or pr_route(p)})
        self.assertEqual(self.run_stage(api, "pr"), "stopped")
        self.assertEqual(self.statuses("pr")["failed"], 2)  # NA, both modes
        self.assertEqual(self.statuses("pr")["rejected"], 2)  # EU, both modes
        for _ in range(MAX_ATTEMPTS):
            self.run_stage(api, "pr")
        tries = sum(1 for endpoint, params in api.calls if ("region", "NA") in params)
        self.assertEqual(tries, 2 * MAX_ATTEMPTS)
        self.assertEqual(sum(1 for endpoint, params in api.calls if ("region", "EU") in params), 2)

    def test_planning_twice_adds_nothing(self):
        queue = TaskQueue(self.db)
        with self.db:
            crawl.plan_pr(self.db, queue, self.args)
            crawl.plan_pr(self.db, queue, self.args)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 10)

    def test_profiles_split_a_batch_the_api_refuses(self):
        with self.db:
            self.db.executemany("INSERT INTO crawl_players (player_id, found_by) VALUES (?, 'pr')",
                                [(i,) for i in range(1, 9)])

        def players(params):
            ids = [int(i) for i in str(params["playerIds"]).strip("[]").split(",")]
            if len(ids) > 2:
                return ApiError(400, "/players", params, "too many")
            return {"players": [{"playerId": i} for i in ids if i != 7]}  # 7 is unknown to the API
        self.assertEqual(self.run_stage(FakeApi({"/players": players}), "profiles"), "finished")
        profiles = dict(self.db.execute("SELECT player_id, profile FROM crawl_players"))
        self.assertEqual(profiles, {**{i: 2 for i in range(1, 9)}, 7: 3})

    def test_histories_record_entries_partners_and_pairs(self):
        with self.db:
            self.db.execute("INSERT INTO crawl_players (player_id, found_by) VALUES (160000, 'pr')")

        def placements(p):
            return {"playerPlacements": [{"placement": 1, "tournament": {"id": f"event-{p['gameMode']}", "startTime": 100}}]}

        def teammates(p):
            return {"playerTeammates": [{"player": {"playerId": 142100}, "lastTeamedDate": 50},
                                        {"player": {"playerId": 170000}, "lastTeamedDate": 40}]}
        api = FakeApi({"/player/placement": placements, "/player/teammate": teammates})
        self.assertEqual(self.run_stage(api, "histories"), "finished")
        self.assertEqual(len(api.calls), 3)  # short pages: one request per listing
        self.assertEqual(sorted(self.db.execute("SELECT event_id, mode FROM crawl_entries")), [("event-1", 1), ("event-2", 2)])
        self.assertEqual(sorted(self.db.execute("SELECT * FROM crawl_pairs")),
                         [(142100, 160000, 0, None), (160000, 170000, 0, None)])
        found = dict(self.db.execute("SELECT player_id, found_by FROM crawl_players"))
        self.assertEqual(found, {160000: "pr", 142100: "teammate", 170000: "teammate"})

    def test_histories_sample_is_repeatable_and_limited(self):
        with self.db:
            self.db.executemany("INSERT INTO crawl_players (player_id, found_by) VALUES (?, 'pr')",
                                [(i,) for i in range(1000)])
        queue = TaskQueue(self.db)
        with self.db:
            crawl.plan_histories(self.db, queue, SimpleNamespace(sample=20))
            crawl.plan_histories(self.db, queue, SimpleNamespace(sample=20))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM crawl_players WHERE history_planned = 1").fetchone()[0], 20)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 60)

    def test_matches_skip_series_events_and_find_opponents(self):
        with self.db:
            self.db.executemany("INSERT INTO crawl_entries (player_id, event_id, mode) VALUES (?, ?, 1)",
                                [(160000, "tournament/x/event/1v1"), (160000, "series/pro-series-2021-na")])
        match = {"matchId": "1", "scores": [3, 1], "opponent": [{"playerId": 169084}]}
        api = FakeApi({"/player/match": lambda p: {"playerMatches": [match]}})
        self.assertEqual(self.run_stage(api, "matches"), "finished")
        self.assertEqual([c[0] for c in api.calls], ["/player/match"])
        self.assertEqual(self.db.execute("SELECT found_by FROM crawl_players WHERE player_id = 169084").fetchone(),
                         ("opponent",))


class RunLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name) / "crawl.sqlite")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def open_run(self, pid):
        from tasks import now
        with self.db:
            self.db.execute("INSERT INTO runs (stage, pid, started_at, heartbeat_at) VALUES ('pr', ?, ?, ?)",
                            (pid, now(), now()))

    def test_refuses_while_another_live_crawl_runs(self):
        self.open_run(os.getppid())  # the process that started the tests is alive
        with self.assertRaises(SystemExit):
            RunLock(self.db, "pr").acquire()

    def test_takes_over_from_a_crashed_run(self):
        self.open_run(2 ** 22 + 7)  # no such process
        lock = RunLock(self.db, "pr")
        lock.acquire()
        lock.release("finished")
        outcomes = [r[0] for r in self.db.execute("SELECT outcome FROM runs ORDER BY run_id")]
        self.assertEqual(outcomes, ["interrupted", "finished"])


if __name__ == "__main__":
    unittest.main()
