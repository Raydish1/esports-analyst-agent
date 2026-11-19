import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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


class FakeGraphQL(FakeApi):
    """The same for start.gg and Challengermode, routed by query name."""

    def query(self, name, document, variables):
        return self.get(name, variables)


def sets_page(ids, total, pool=7, per_page=None):
    per_page = per_page or crawl.SETS_PER_PAGE
    return {"pageInfo": {"total": total, "totalPages": -(-total // per_page)},
            "nodes": [{"id": i, "phaseGroup": {"id": pool}} for i in ids]}


def node(placement, entrant, players):
    return {"placement": placement, "entrant": {"id": entrant, "isDisqualified": False, "participants": [
        {"id": entrant * 10 + i, "player": {"id": p}} for i, p in enumerate(players)]}}


def pr_route(params):  # three pages of three players per mode and region
    page, base = params["page"], params["gameMode"] * 1000 + crawl.REGIONS.index(params["region"]) * 100
    return {"prPlayers": [{"playerId": base + page * 10 + i} for i in range(3)], "totalPages": 3}


class CrawlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name) / "crawl.sqlite", schema=crawl.CRAWL_SCHEMA)
        self.args = SimpleNamespace(sample=None, event=None, max_pools=None)
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

    def add_events(self, rows):
        with self.db:
            self.db.executemany("INSERT INTO crawl_events (event_id, mode, host, start_time) VALUES (?, ?, ?, ?)", rows)

    def test_standings_record_participants_and_follow_up_pages(self):
        self.add_events([("tournament/a/event/2v2", 2, "SGG", 0), ("tournament/gone/event/1v1", 1, "SGG", 0),
                         ("series/pro-series-2021-na", 1, "SGG", 0), ("fcb7a286-cm", 1, "CM", 0)])
        pages = {1: [node(1, 1, [101, 102])], 2: [node(3, 2, [103, None])]}

        def standings(v):
            if "gone" in v["slug"]:
                return {"event": None}
            return {"event": {"id": 9, "numEntrants": 5, "standings": {
                "pageInfo": {"total": 2, "totalPages": 2}, "nodes": pages[v["page"]]}}}
        api = FakeGraphQL({"Standings": standings})
        self.assertEqual(self.run_stage(api, "standings"), "finished")
        self.assertEqual(len(api.calls), 3)  # two pages of one event, one of the missing one; no series or CM events
        self.assertEqual(dict(self.db.execute("SELECT event_id, status FROM crawl_platform_events")),
                         {"tournament/a/event/2v2": "ok", "tournament/gone/event/1v1": "missing"})
        self.assertEqual(sorted(self.db.execute("SELECT sgg_player_id, placement FROM crawl_standings"), key=str),
                         sorted([(101, 1), (102, 1), (103, 3), (None, 3)], key=str))

    def test_standings_keep_a_player_entered_twice(self):
        self.add_events([("tournament/a/event/1v1", 1, "SGG", 0)])
        twice = [node(97, 1, [609951]), node(513, 2, [609951])]
        twice[1]["entrant"]["participants"][0]["id"] = twice[0]["entrant"]["participants"][0]["id"]  # one participant
        api = FakeGraphQL({"Standings": lambda v: {"event": {"id": 9, "numEntrants": 2, "standings": {
            "pageInfo": {"total": 2, "totalPages": 1}, "nodes": twice}}}})
        self.assertEqual(self.run_stage(api, "standings"), "finished")  # the check finds both entrants
        self.assertEqual(sorted(self.db.execute("SELECT entrant_id, placement FROM crawl_standings")), [(1, 97), (2, 513)])

    def test_migration_rekeys_standings_and_reapplies_short_events(self):
        old = Path(self.tmp.name) / "old.sqlite"
        db = connect(old)
        with db:  # the table as it was before 2026-10-04, after a run that lost an entrant
            db.executescript(crawl.CRAWL_SCHEMA.replace(crawl.STANDINGS_TABLE + ";", "") + """
                CREATE TABLE crawl_standings (event_id TEXT NOT NULL, participant_id INTEGER NOT NULL, entrant_id INTEGER,
                  sgg_player_id INTEGER, placement INTEGER, disqualified INTEGER, PRIMARY KEY (event_id, participant_id));
                INSERT INTO crawl_standings VALUES ('tournament/a/event/1v1', 10, 1, 609951, 97, 0),
                                                   ('tournament/b/event/1v1', 20, 2, 5, 1, 0);
                INSERT INTO crawl_platform_events VALUES ('tournament/a/event/1v1', 'startgg', '9', 2, 2, 'ok'),
                                                         ('tournament/b/event/1v1', 'startgg', '8', 1, 1, 'ok');""")
            for key in ("standings:tournament/a/event/1v1:1", "standings:tournament/b/event/1v1:1"):
                TaskQueue(db).add("standings", "standings_page", key, {"slug": key.split(":")[1], "page": 1})
                TaskQueue(db).set_status(key, "done")
        crawl.migrate(db)
        crawl.migrate(db)  # a second time changes nothing
        key = [r[1] for r in sorted(db.execute("PRAGMA table_info(crawl_standings)"), key=lambda r: r[5]) if r[5]]
        self.assertEqual(key, ["event_id", "entrant_id", "participant_id"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM crawl_standings").fetchone()[0], 2)
        self.assertEqual(dict(db.execute("SELECT task_key, status FROM tasks")),
                         {"standings:tournament/a/event/1v1:1": "pending", "standings:tournament/b/event/1v1:1": "done"})
        db.close()

    def test_brackets_page_sets_and_fetch_pools_and_last_phase_games(self):
        self.add_events([("tournament/a/event/2v2", 2, "SGG", 0), ("fcb7a286-cm", 1, "CM", 0)])
        phases = [{"id": 51, "phaseOrder": 1, "groupCount": 4, "numSeeds": 200},
                  {"id": 52, "phaseOrder": 2, "groupCount": 1, "numSeeds": 8},
                  {"id": 53, "phaseOrder": 3, "groupCount": 1, "numSeeds": 64}]  # numbered out of bracket order
        total = crawl.SETS_PER_PAGE + 5

        def event_sets(v):
            ids = range(1, crawl.SETS_PER_PAGE + 1) if v["page"] == 1 else range(crawl.SETS_PER_PAGE + 1, total + 1)
            return {"event": {"id": 9, "phases": phases, "sets": sets_page(ids, total)}}
        games = lambda v: {"phase": {"sets": {"pageInfo": {"total": 14, "totalPages": 2}, "nodes": []}}}  # noqa: E731
        pools = lambda v: {"event": {"phaseGroups": [{"id": g, "phase": {"id": 51}} for g in range(1, 5)]}}  # noqa: E731
        api = FakeGraphQL({"EventSets": event_sets, "EventPools": pools, "PhaseGames": games})
        self.assertEqual(self.run_stage(api, "brackets"), "finished")
        self.assertEqual(sorted(name for name, _ in api.calls), ["EventPools", "EventSets", "EventSets", "PhaseGames", "PhaseGames"])
        games_params = [c for name, params in api.calls if name == "PhaseGames" for c in params]
        self.assertIn(("phaseId", "52"), games_params)  # the smallest phase, not the last-numbered one
        self.assertIn(("perPage", "8"), games_params)  # 2v2
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM crawl_matches").fetchone()[0], total)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM crawl_pools").fetchone()[0], 4)

    def test_brackets_fetch_an_event_over_the_cap_pool_by_pool(self):
        self.add_events([("tournament/big/event/1v1", 1, "SGG", 0)])
        phases = [{"id": 51, "phaseOrder": 1, "groupCount": 3, "numSeeds": 7000},
                  {"id": 52, "phaseOrder": 2, "groupCount": 1, "numSeeds": 8}]
        pool_ids = {51: [101, 102, 103], 52: [201]}
        pool_sets = {101: 50, 102: 3, 103: 4, 201: 7}
        total = sum(pool_sets.values()) + crawl.SETS_CAP  # pretend start.gg counts past the cap
        pool_sets[103] += crawl.SETS_CAP

        def event_sets(v):
            return {"event": {"id": 9, "phases": phases, "sets": sets_page([1001], total, pool=101)}}

        def phase_pools(v):
            return {"phase": {"phaseGroups": {"pageInfo": {"total": 3, "totalPages": 1},
                                              "nodes": [{"id": g} for g in pool_ids[v["phaseId"]]]}}}

        def pool_page(v):  # sets numbered by pool; set 1001 is pool 101's first, also on the event's first page
            n, per = pool_sets[v["poolId"]], crawl.SETS_PER_PAGE
            ids = [v["poolId"] * 100000 + i for i in range((v["page"] - 1) * per, min(n, v["page"] * per))]
            if v["poolId"] == 101 and v["page"] == 1:
                ids[0] = 1001
            return {"phaseGroup": {"id": v["poolId"], "sets": sets_page(ids, n, pool=v["poolId"])}}
        api = FakeGraphQL({"EventSets": event_sets, "PhasePools": phase_pools, "PoolSets": pool_page,
                           "PhaseGames": lambda v: {"phase": {"sets": {"pageInfo": {"totalPages": 1}, "nodes": []}}}})
        self.args.max_pools = 1  # the pilot: one pool per phase
        self.assertEqual(self.run_stage(api, "brackets"), "finished")
        planned = sorted(p for name, params in api.calls if name == "PoolSets" for k, p in params if k == "poolId")
        self.assertEqual(sorted(set(planned)), ["101", "201"])
        self.assertTrue(any("2 of 4 pools fetched so far" in line for line in self.log))  # one per phase
        self.args.max_pools = None  # the full run picks up the other pools
        self.assertEqual(self.run_stage(api, "brackets"), "finished")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM crawl_matches").fetchone()[0], total)
        self.assertEqual(len(api.calls), len(set(api.calls)), "a page was requested twice")

    def test_brackets_check_reports_missing_sets(self):
        self.add_events([("tournament/a/event/1v1", 1, "SGG", 0)])
        api = FakeGraphQL({"EventSets": lambda v: {"event": {"id": 9, "phases": [], "sets": sets_page([1, 2], 3)}},
                           "EventPools": lambda v: {"event": {"phaseGroups": []}}})
        self.assertEqual(self.run_stage(api, "brackets"), "stopped")  # start.gg reported 3 sets, 2 came back
        self.assertTrue(any("2 sets fetched, start.gg reports 3" in line for line in self.log))

    def test_cm_records_entrants_and_matches(self):
        self.add_events([("t-1", 1, "CM", 0), ("tournament/a/event/1v1", 1, "SGG", 0)])
        roster = {"tournament": {"id": "t-1", "attendance": {"roster": {"lineupCount": 2, "lineups": [
            {"id": "L1", "placement": {"bestPlacement": 1}, "members": [{"user": {"id": "u1"}}]},
            {"id": "L2", "placement": {"bestPlacement": 2}, "members": [{"user": {"id": "u2"}}]}]}}}}
        series = [{"id": "S1", "lineups": [{"id": "L1"}, {"id": "L2"}], "matches": [{"id": "M1"}]},
                  {"id": "S2", "lineups": [{"id": "L1"}], "matches": []}]  # a bye
        bracket = {"tournament": {"stages": [{"brackets": [{"rounds": [{"matchSeries": series}]}]},
                                             {"rounds": [{"matchSeries": [{"id": "S3", "matches": [{"id": "M3"}]}]}]}]}}
        api = FakeGraphQL({"Roster": lambda v: roster, "Bracket": lambda v: bracket})
        self.assertEqual(self.run_stage(api, "cm"), "finished")
        self.assertEqual(sorted(self.db.execute("SELECT user_id, placement FROM crawl_cm_entrants")), [("u1", 1), ("u2", 2)])
        self.assertEqual(sorted(r[0] for r in self.db.execute("SELECT match_id FROM crawl_matches")), ["M1", "M3"])

    def cm_event(self, lineups, bracket_lineups, lineup_count):
        roster = {"tournament": {"attendance": {"roster": {"lineupCount": lineup_count, "lineups": [
            {"id": lid, "members": [{"user": {"id": f"u-{lid}"}}]} for lid in lineups]}}}}
        series = [{"id": "S1", "lineups": [{"id": lid} for lid in bracket_lineups], "matches": [{"id": "M1"}]}]
        bracket = {"tournament": {"stages": [{"brackets": [{"rounds": [{"matchSeries": series}]}]}]}}
        return FakeGraphQL({"Roster": lambda v: roster, "Bracket": lambda v: bracket})

    def test_cm_check_reports_a_bracket_lineup_missing_from_the_entrant_list(self):
        self.add_events([("t-1", 1, "CM", 0)])
        self.assertEqual(self.run_stage(self.cm_event(["L1"], ["L1", "L2"], 2), "cm"), "stopped")
        self.assertTrue(any("1 of the 2 lineups in the bracket aren't in the entrant list" in line for line in self.log))

    def test_cm_check_accepts_lineups_that_never_played(self):  # BCX 2025 2v2: 298 lineups for a count of 256
        self.add_events([("t-1", 2, "CM", 0)])
        self.assertEqual(self.run_stage(self.cm_event(["L1", "L2", "L3"], ["L1", "L2"], 2), "cm"), "finished")

    def test_cm_check_reports_an_entrant_list_cut_off_at_the_limit(self):
        self.add_events([("t-1", 1, "CM", 0)])
        with mock.patch.object(crawl, "ROSTER_LIMIT", 2):
            self.assertEqual(self.run_stage(self.cm_event(["L1", "L2"], ["L1", "L2"], 3), "cm"), "stopped")
        self.assertTrue(any("may be cut off at 2 lineups" in line for line in self.log))

    def test_rejected_tasks_go_back_in_the_queue_on_request(self):
        queue = TaskQueue(self.db)
        with self.db:
            for key, stage, status in (("a", "cm", "rejected"), ("b", "cm", "done"), ("c", "pr", "rejected")):
                queue.add(stage, "cm_bracket", key, {})
                queue.set_status(key, status, "HTTP 400")
        self.assertEqual(queue.retry_rejected("cm"), 1)
        self.assertEqual(dict(self.db.execute("SELECT task_key, status FROM tasks")), {"a": "pending", "b": "done", "c": "rejected"})

    def test_lookups_mark_each_platform_player_and_split_refused_batches(self):
        with self.db:
            self.db.executemany("INSERT INTO crawl_standings (event_id, participant_id, entrant_id, sgg_player_id) VALUES (?, ?, ?, ?)",
                                [("e", i, i, 1000 + i) for i in range(150)])
            self.db.executemany("INSERT INTO crawl_cm_entrants (event_id, lineup_id, user_id) VALUES ('c', ?, ?)",
                                [("L1", "AB-cd"), ("L2", "ef")])

        def players(params):
            if "sggIds" in params:
                ids = [int(i) for i in params["sggIds"]]
                if len(ids) > 60:
                    return ApiError(400, "/players", params, "too many")
                return {"players": [{"playerId": i - 1000, "sggPlayerId": i} for i in ids if i % 10]}  # every 10th unknown
            return {"players": [{"playerId": 7, "cmPlayerId": "ab-CD"}]}
        self.assertEqual(self.run_stage(FakeApi({"/players": players}), "lookups"), "finished")
        status = dict(self.db.execute("SELECT status, COUNT(*) FROM crawl_platform_players WHERE platform = 'startgg' GROUP BY status"))
        self.assertEqual(status, {2: 135, 3: 15})
        self.assertEqual(dict(self.db.execute("SELECT platform_player_id, player_id FROM crawl_platform_players"
                                              " WHERE platform = 'challengermode'")), {"AB-cd": 7, "ef": None})
        self.assertEqual(self.db.execute(crawl.UNPLANNED["lookups"]).fetchone()[0], 0)

    def test_proseries_checks_regional_candidates_and_records_placements(self):
        final = 1_600_000_000
        self.add_events([("series/pro-series-2021-na", 1, "SGG", final),
                         ("tournament/north-america-winter-2021/event/1v1", 1, "SGG", final - 100),
                         ("tournament/north-america-winter-2021/event/2v2", 2, "SGG", final - 100),
                         ("tournament/europe-winter-2021/event/1v1", 1, "SGG", final - 100),
                         ("tournament/dreamhack-x/event/1v1", 1, "SGG", final - 200),
                         ("tournament/north-america-old/event/1v1", 1, "SGG", final - 400 * 86400)])
        with self.db:
            self.db.executemany("INSERT INTO crawl_standings (event_id, participant_id, entrant_id, sgg_player_id, placement)"
                                " VALUES (?, ?, ?, ?, ?)",
                                [("tournament/north-america-winter-2021/event/1v1", 1, 1, 501, 1),
                                 ("tournament/north-america-winter-2021/event/1v1", 2, 2, 502, 33),  # not top 32
                                 ("tournament/north-america-winter-2021/event/2v2", 6, 6, 506, 3),  # 2v2 counts too
                                 ("tournament/europe-winter-2021/event/1v1", 3, 3, 503, 1),  # another region
                                 ("tournament/dreamhack-x/event/1v1", 4, 4, 504, 2),  # no region: a candidate
                                 ("tournament/north-america-old/event/1v1", 5, 5, 505, 1)])  # over a year before
            self.db.execute("INSERT INTO crawl_platform_players VALUES ('startgg', '506', 2, 6)")  # looked up already
        finalists = {1: 1, 4: 2, 6: 3}  # player IDs are sgg ID - 500

        def placements(p):
            pid = int(p["playerIds"])
            rows = [{"placement": 9, "tournament": {"id": "tournament/north-america-winter-2021/event/1v1"}}]
            if pid in finalists:
                rows.insert(0, {"placement": finalists[pid], "tournament": {"id": "series/pro-series-2021-na"}})
            return {"playerPlacements": rows}
        api = FakeApi({"/players": lambda p: {"players": [{"playerId": int(i) - 500, "sggPlayerId": int(i)} for i in p["sggIds"]]},
                       "/player/placement": placements})
        self.assertEqual(self.run_stage(api, "proseries"), "finished")  # 1, 2, 3 is a complete bracket of three
        checked = sorted(dict(params)["playerIds"] for endpoint, params in api.calls if endpoint == "/player/placement")
        self.assertEqual(checked, ["1", "4", "6"])
        looked_up = [dict(params)["sggIds"] for endpoint, params in api.calls if endpoint == "/players"]
        self.assertEqual(looked_up, [str(["501", "504"])])  # 506 was known already
        token = [dict(params)["nextToken"] for endpoint, params in api.calls if endpoint == "/player/placement"][0]
        self.assertEqual(token, str(final + 1))
        self.assertEqual(sorted(self.db.execute("SELECT player_id, placement FROM crawl_series_placements")),
                         [(1, 1), (4, 2), (6, 3)])

    def test_proseries_check_recognizes_a_team_format_and_a_gap(self):
        self.add_events([("series/a-na", 1, "SGG", 0), ("series/b-na", 1, "SGG", 0)])
        with self.db:
            for final, places in (("series/a-na", [1, 1, 2, 2, 3, 3, 3]), ("series/b-na", [1, 2, 3, 5])):
                for pid, place in enumerate(places):
                    self.db.execute("INSERT INTO crawl_series_placements VALUES (?, ?, ?)", (final, pid, place))
                    TaskQueue(self.db).add("proseries", "series_check", f"series_check:{final}:{pid}", {})
        self.assertFalse(crawl.check_proseries(self.db, None, self.log.append))  # b-na has no 4th place
        self.assertIn("a team format, every place shared (1: 2 players, 2: 2 players, 3: 3 players)", self.log[0])
        self.assertIn("an entrant may be missing", self.log[1])

    def add_standings(self, rows):  # (event, entrant, sgg player, placement)
        with self.db:
            self.db.executemany("INSERT INTO crawl_standings (event_id, participant_id, entrant_id, sgg_player_id, placement)"
                                " VALUES (?, ?, ?, ?, ?)", [(e, ent * 10, ent, p, pl) for e, ent, p, pl in rows])

    def test_sets_record_their_entrants(self):
        self.add_events([("tournament/a/event/1v1", 1, "SGG", 0)])
        sets = sets_page([1, 2], 2)
        sets["nodes"][0]["slots"] = [{"entrant": {"id": 7}}, {"entrant": {"id": 8}}]
        sets["nodes"][1]["slots"] = [{"entrant": {"id": 7}}, {"entrant": None}]  # a bye's empty slot
        api = FakeGraphQL({"EventSets": lambda v: {"event": {"id": 9, "phases": [], "sets": sets}},
                           "EventPools": lambda v: {"event": {"phaseGroups": []}}})
        self.assertEqual(self.run_stage(api, "brackets"), "finished")
        self.assertEqual(sorted(self.db.execute("SELECT entrant_id FROM crawl_set_entrants")), [(7,), (8,)])

    def test_set_entrants_are_backfilled_once_from_the_cache(self):
        from cache import ResponseCache
        cache = ResponseCache(Path(self.tmp.name) / "cache", Path(self.tmp.name) / "crawl.sqlite")
        page = {"data": {"event": {"sets": {"nodes": [{"id": 1, "slots": [{"entrant": {"id": 7}}, {"entrant": {"id": 8}}]}]}}}}
        queue = TaskQueue(self.db)
        with self.db:
            queue.add("brackets", "sgg_sets", "sgg_sets:tournament/a/event/1v1:1", {"slug": "tournament/a/event/1v1", "page": 1})
            queue.set_status("sgg_sets:tournament/a/event/1v1:1", "done")
        cache.store("startgg/EventSets", {"page": 1}, "u", 200, json.dumps(page).encode(), 5,
                    task="sgg_sets:tournament/a/event/1v1:1")
        with mock.patch.object(crawl, "CACHE_DIR", Path(self.tmp.name) / "cache"), self.db:
            crawl.backfill_set_entrants(self.db)
        self.assertEqual(sorted(self.db.execute("SELECT * FROM crawl_set_entrants")),
                         [("tournament/a/event/1v1", 7), ("tournament/a/event/1v1", 8)])
        cache.db.close()

    def test_entrant_lists_fill_in_entrants_missing_from_standings(self):
        self.add_events([("tournament/a/event/1v1", 1, "SGG", 0), ("tournament/b/event/1v1", 1, "SGG", 0)])
        self.add_standings([("tournament/a/event/1v1", 1, 101, 1), ("tournament/b/event/1v1", 3, 103, 1)])
        with self.db:
            self.db.executemany("INSERT INTO crawl_set_entrants VALUES (?, ?)",
                                [("tournament/a/event/1v1", 1), ("tournament/a/event/1v1", 2), ("tournament/b/event/1v1", 3)])
        entrants = [{"id": 1, "participants": [{"id": 10, "player": {"id": 101}}]},
                    {"id": 2, "participants": [{"id": 20, "player": {"id": 102}}]},
                    {"id": 4, "participants": [{"id": 40, "player": {"id": 104}}]}]  # registered, never played
        api = FakeGraphQL({"Entrants": lambda v: {"event": {"entrants": {"pageInfo": {"totalPages": 1}, "nodes": entrants}}}})
        self.assertEqual(self.run_stage(api, "entrants"), "finished")  # every set entrant is known now
        self.assertEqual([dict(params)["slug"] for _, params in api.calls], ["tournament/a/event/1v1"])  # b is complete
        self.assertTrue(any("1 entrant(s) in sets but not in the standings, 1 of them in its entrant list" in line
                            for line in self.log))
        queue = TaskQueue(self.db)
        with self.db:
            crawl.plan_lookups(self.db, queue, self.args)
        ids = {r[0] for r in self.db.execute("SELECT platform_player_id FROM crawl_platform_players")}
        self.assertEqual(ids, {"101", "102", "103"})  # 104 never played, so it isn't looked up

    def test_gaps_take_stats_api_placements_and_leave_the_rest_unplaced(self):
        self.add_events([("tournament/a/event/1v1", 1, "SGG", 5000)])
        self.add_standings([("tournament/a/event/1v1", 1, 101, 1)])
        with self.db:
            self.db.executemany("INSERT INTO crawl_set_entrants VALUES ('tournament/a/event/1v1', ?)", [(1,), (2,), (3,), (4,)])
            self.db.executemany("INSERT INTO crawl_entrants VALUES ('tournament/a/event/1v1', ?, ?, ?)",
                                [(2, 20, 102), (3, 30, 103), (4, 40, 104)])
            self.db.executemany("INSERT INTO crawl_platform_players VALUES ('startgg', ?, ?, ?)",
                                [("102", 2, 2), ("103", 2, 3), ("104", 3, None)])  # 104 has no Stats API record

        def placements(p):
            if p["playerIds"] == 2:
                return {"playerPlacements": [{"placement": 9, "tournament": {"id": "tournament/a/event/1v1"}}]}
            return {"playerPlacements": [{"placement": 1, "tournament": {"id": "tournament/older/event/1v1"}}]}
        api = FakeApi({"/player/placement": placements})
        self.assertEqual(self.run_stage(api, "gaps"), "finished")
        self.assertEqual(sorted(dict(params)["playerIds"] for _, params in api.calls), ["2", "3"])
        self.assertEqual(dict(api.calls[0][1])["nextToken"], "5001")
        self.assertEqual(list(self.db.execute("SELECT player_id, placement FROM crawl_gap_placements")), [(2, 9)])
        self.assertTrue(any("3 entrant(s) missing from the standings, 2 player(s) with a Stats API record,"
                            " 1 placed by the Stats API" in line for line in self.log))

    def test_legends_take_each_regions_top_and_record_three_periods(self):
        def top(region, n):
            return {"NA": [5, 6], "EU": [6, 7]}.get(region, [])[:n]

        def legends(p):
            if p["playerIds"] == [7]:
                return ApiError(404, "/player/legend", p, "no such player")
            return {"legends": [{"name": "RED_RAPTOR", "count": 9 if p.get("year") else 20}, {"name": "", "count": 1}]}
        self.args.top = 2
        with mock.patch.object(crawl, "pr_top", top):
            self.assertEqual(self.run_stage(FakeApi({"/player/legend": legends}), "legends"), "finished")
        self.assertEqual(self.statuses("legends"), {"done": 9})  # 5, 6 (in two regions) and 7 (unknown: done, nothing)
        self.assertEqual(sorted(self.db.execute("SELECT * FROM crawl_legends WHERE player_id = 5")),
                         [(5, "2025", "RED_RAPTOR", 9), (5, "2026", "RED_RAPTOR", 9), (5, "all", "RED_RAPTOR", 20)])
        self.assertEqual(sorted({r[0] for r in self.db.execute("SELECT player_id FROM crawl_legends")}), [5, 6])

    def test_pr_top_reads_cached_pages_in_rank_order(self):
        pages = {1: {"prPlayers": [{"playerId": 2, "powerRanking": 2}, {"playerId": 1, "powerRanking": 1}], "totalPages": 2},
                 2: {"prPlayers": [{"playerId": 3, "powerRanking": 3}], "totalPages": 2}}
        cache = SimpleNamespace(newest=lambda endpoint, p: (200, json.dumps(pages[p["page"]]).encode()))
        self.assertEqual(crawl.pr_top("NA", 3, cache), [1, 2, 3])
        self.assertEqual(crawl.pr_top("NA", 1, cache), [1])

    def test_double_elimination_places(self):
        self.assertEqual(crawl.double_elimination_places(8), [1, 2, 3, 4, 5, 5, 7, 7])
        self.assertEqual(crawl.double_elimination_places(16)[8:], [9] * 4 + [13] * 4)
        self.assertEqual(crawl.double_elimination_places(3), [1, 2, 3])

    def test_refused_credentials_fail_and_are_retried_rather_than_rejected(self):
        api = FakeApi({"/pr": lambda p: ApiError(401, "/pr", {}, "refused")})
        self.assertEqual(self.run_stage(api, "pr"), "stopped")  # ten failures in a row stop the run
        self.assertEqual(self.statuses("pr"), {"failed": 10})

    def test_event_filter_limits_platform_stages(self):
        self.add_events([("t-1", 1, "CM", 0), ("t-2", 1, "CM", 0)])
        queue = TaskQueue(self.db)
        with self.db:
            crawl.plan_cm(self.db, queue, SimpleNamespace(event=["t-2"]))
        self.assertEqual(sorted(r[0] for r in self.db.execute("SELECT task_key FROM tasks")), ["cm_bracket:t-2", "cm_entrants:t-2"])


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

    def test_locks_are_per_api(self):
        self.open_run(os.getppid())  # a live Stats API crawl
        RunLock(self.db, "standings", "startgg").acquire()  # a start.gg crawl may run alongside it
        with self.assertRaises(SystemExit):
            RunLock(self.db, "teams", "statsapi").acquire()

    def test_takes_over_from_a_crashed_run(self):
        self.open_run(2 ** 22 + 7)  # no such process
        lock = RunLock(self.db, "pr")
        lock.acquire()
        lock.release("finished")
        outcomes = [r[0] for r in self.db.execute("SELECT outcome FROM runs ORDER BY run_id")]
        self.assertEqual(outcomes, ["interrupted", "finished"])


if __name__ == "__main__":
    unittest.main()
