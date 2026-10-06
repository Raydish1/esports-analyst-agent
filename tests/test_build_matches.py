import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_matches  # noqa: E402
import crawl  # noqa: E402
from build_players import Players, negative_id  # noqa: E402
from cache import ResponseCache, query_hash  # noqa: E402
from cache_reader import CacheReader  # noqa: E402

A, BIG, CM = "tournament/a/event/1v1", "tournament/big/event/1v1", "cm-1"
ALICE, BOB = "e2d264bb-027e-44cd-b864-718b9db1b0d7", "2a1b4620-6035-43a6-a4a7-1006ad9e57a4"


def sset(set_id, *slots, winner=None, started=None):
    """A start.gg set; slots are (slot index, entrant ID or None, score)."""
    return {"id": set_id, "winnerId": winner, "startedAt": started, "state": 3,
            "slots": [{"slotIndex": i, "entrant": {"id": e} if e else None,
                       "standing": {"stats": {"score": {"value": score}}}} for i, e, score in slots]}


def sets_page(sets, phases=None, total=None):
    return {"data": {"event": {"phases": phases or [], "sets": {"pageInfo": {"total": total or len(sets)}, "nodes": sets}}}}


def cm_match(match_id, state, *lineups):
    """lineups: (number, user ID, score, placement)"""
    return {"id": match_id, "state": state,
            "lineups": [{"number": n, "members": [{"user": {"id": u}}]} for n, u, _, _ in lineups],
            "results": {"final": True, "lineupResults": [{"lineupNumber": n, "score": s, "placement": p}
                                                         for n, _, s, p in lineups]}}


class MatchesStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")

        def store(endpoint, query, params, body):
            cache.store(endpoint, {"q": query_hash(query), **params}, "u", 200, json.dumps(body).encode(), 5)
        sets_q, page = crawl.EVENT_SETS_QUERY, {"perPage": 50}
        store("startgg/EventSets", sets_q, {"slug": A, "page": 2, **page}, sets_page(  # the older version of set 1007
            [sset(1007, (0, 10, 2), (1, 11, 0), winner=10)]))
        store("startgg/EventSets", sets_q, {"slug": A, "page": 1, **page}, sets_page([
            sset(1001, (0, 10, 2), (1, 11, 1), winner=10, started=1500),
            sset(1002, (0, 10, -1), (1, 11, None), winner=11),  # a DQ
            sset(1003, (0, 10, None), (1, 11, None), winner=11),  # a winner but no score
            sset(1004, (0, 10, None), (1, None, None)),  # a bye
            sset("preview_9_1", (0, 10, None), (1, 11, None)),  # never played
            sset(1005, (0, 10, 3), (1, 12, 0), winner=10),  # entrant 12 is only in the entrant list
            sset(1006, (1, 11, 0), (0, 10, 2), winner=10),  # slots listed out of order
            sset(1008, (0, 13, 2), (1, 11, 0), winner=13)], phases=[{"id": 5, "state": "COMPLETED"}], total=8))
        store("startgg/EventSets", sets_q, {"slug": A, "page": 3, **page}, sets_page(  # the newer version of set 1007
            [sset(1007, (0, 10, 2), (1, 12, 1), winner=10)]))
        store("startgg/EventSets", sets_q, {"slug": BIG, "page": 1, **page}, sets_page(
            [sset(2001, (0, 30, 1), (1, 31, 2), winner=31)],
            phases=[{"id": 9, "state": "COMPLETED"}, {"id": 8, "state": "ACTIVE"}], total=2))
        store("startgg/PhasePools", crawl.PHASE_POOLS_QUERY, {"phaseId": 9, "page": 1, "perPage": 32},
              {"data": {"phase": {"phaseGroups": {"nodes": [{"id": 77}]}}}})
        store("startgg/PoolSets", crawl.POOL_SETS_QUERY, {"poolId": 77, "page": 1, "perPage": 50},
              {"data": {"phaseGroup": {"sets": {"pageInfo": {"total": 2}, "nodes": [
                  sset(2001, (0, 30, 1), (1, 31, 2), winner=31), sset(2002, (0, 30, 0), (1, 31, 3), winner=31)]}}}})
        store("startgg/Entrants", crawl.ENTRANTS_QUERY, {"slug": A, "page": 1}, {"data": {"event": {"entrants": {"nodes": [
            {"id": 12, "participants": [{"id": 120, "gamerTag": "Late", "player": {"id": 400}}]},
            {"id": 13, "participants": [{"id": 130, "gamerTag": "Known", "player": {"id": 401}}]}]}}}})
        store("challengermode/Roster", crawl.CM_ROSTER_QUERY, {"id": CM, "limit": 2000}, {"data": {"tournament": {
            "attendance": {"roster": {"lineups": [{"members": [{"user": {"id": ALICE, "username": "alice"}}]},
                                                  {"members": [{"user": {"id": BOB, "username": "bob"}}]}]}}}}})
        lineups = [{"id": "L1"}, {"id": "L2"}]
        store("challengermode/Bracket", crawl.CM_BRACKET_QUERY, {"id": CM}, {"data": {"tournament": {"stages": [{
            "brackets": [{"rounds": [{"matchSeries": [
                {"lineups": lineups, "startedAt": "2026-08-30T17:07:52.880Z",
                 "matches": [cm_match("m0", "CANCELLED", (0, ALICE, None, None), (1, BOB, None, None)),
                             cm_match("m1", "COMPLETED", (1, BOB, 1, 2), (0, ALICE, 2, 1))]},
                {"lineups": [{"id": "L1"}, None], "matches": []},  # a bye
                {"lineups": lineups, "matches": [cm_match("m3", "COMPLETED", (0, ALICE, None, None),
                                                          (1, BOB, None, None))]}]}]}]}]}}})  # a forfeit
        cache.store("/player/placement", {"playerIds": 4, "gameMode": 1, "isOfficial": True}, "u", 200,
                    json.dumps({"playerPlacements": [{"placement": 9, "tournament": {"id": A}}]}).encode(), 5)
        cache.db.close()

        self.db = sqlite3.connect(":memory:")
        self.db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        for event_id, host in ((A, "SGG"), (BIG, "SGG"), (CM, "CM")):
            self.db.execute("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official, is_twos,"
                            " is_online, fetched_at) VALUES (?, ?, ?, 2020, 1000, 1, 0, 0, 't')", (event_id, host, event_id))
            self.db.execute("INSERT INTO event_sources (event_id, platform, fetched_at) VALUES (?, ?, 't')",
                            (event_id, "challengermode" if host == "CM" else "startgg"))
        self.db.executemany("INSERT INTO standings (event_id, entrant_key, platform_player, player_id, placement, source,"
                            " fetched_at) VALUES (?, ?, ?, ?, ?, 'startgg', 't')",
                            [(A, "10", "100", 1, 1), (A, "11", "200", 2, 2),
                             (BIG, "30", "100", 1, 1), (BIG, "31", "300", 3, 2)])
        self.log = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_step(self, events=None):
        players = Players()
        for pid, sgg, cm in ((1, 100, None), (2, 200, None), (3, 300, None), (4, 401, None), (5, None, ALICE)):
            players.observe({"playerId": pid, "name": f"p{pid}", "sggPlayerId": sgg, "cmPlayerId": cm}, "t")
        players.index()
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite")
        try:
            b = build.Build(self.db, reader, self.root, self.log.append, events, auto_merges=None)
            b.players = players
            build_matches.step(b)
        finally:
            reader.close()
        return b

    def matches(self):
        return {m: rest for m, *rest in self.db.execute(
            "SELECT match_id, event_id, side1_score, side2_score, reported_winner_side, winner_side, is_no_contest"
            " FROM matches")}

    def sides(self, match_id):
        return sorted(self.db.execute("SELECT side, player_id FROM match_players WHERE match_id = ?", (match_id,)))

    def test_start_gg_sets(self):
        b = self.run_step()
        found = self.matches()
        self.assertEqual({k: v for k, v in found.items() if v[0] == A}, {
            "1001": [A, 2, 1, 1, 1, 0], "1002": [A, -1, None, 2, None, 1], "1003": [A, None, None, 2, 2, 0],
            "1005": [A, 3, 0, 1, 1, 0], "1006": [A, 2, 0, 1, 1, 0], "1007": [A, 2, 1, 1, 1, 0], "1008": [A, 2, 0, 1, 1, 0]})
        self.assertEqual(self.sides("1006"), [(1, 1), (2, 2)])  # side 1 is slot 0
        self.assertEqual(self.sides("1007"), [(1, 1), (2, -400)])  # the newer response's entrants
        self.assertEqual({k for k, v in found.items() if v[0] == BIG}, {"2001", "2002"})  # through the pool page
        self.assertEqual(json.loads(b.info["match_counts"])["start.gg byes"], 1)
        self.assertEqual(json.loads(b.info["match_counts"])["start.gg sets never played"], 1)
        self.assertEqual(self.db.execute("SELECT event_id, reported_sets, state FROM event_sources"
                                         " WHERE platform = 'startgg' ORDER BY event_id").fetchall(),
                         [(A, 8, "COMPLETED"), (BIG, 2, "ACTIVE,COMPLETED")])

    def test_players_met_only_in_an_entrant_list(self):
        self.run_step()
        self.assertEqual(self.sides("1005"), [(1, 1), (2, -400)])
        self.assertEqual(self.db.execute("SELECT name, source FROM players WHERE player_id = -400").fetchone(),
                         ("Late", "startgg"))
        self.assertEqual(self.db.execute("SELECT event_id, player_id, placement, source FROM placements").fetchall(),
                         [(A, 4, 9, "stats_api")])  # stage 3c: player 4 has a Stats API placement there

    def test_challengermode_matches(self):
        b = self.run_step()
        found = self.matches()
        self.assertEqual(found["m1"], [CM, 2, 1, 1, 1, 0])
        self.assertEqual(self.sides("m1"), [(1, 5), (2, negative_id("challengermode", BOB))])  # side 1 is lineup 0
        self.assertEqual(found["m3"], [CM, 0, 0, None, None, 1])  # a forfeit: 0-0, a no-contest
        self.assertNotIn("m0", found)  # cancelled
        counts = json.loads(b.info["match_counts"])
        self.assertEqual((counts["Challengermode byes"], counts["Challengermode matches not completed (cancelled)"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT start_time FROM matches WHERE match_id = 'm1'").fetchone(),
                         (int(datetime(2026, 8, 30, 17, 7, 52, tzinfo=timezone.utc).timestamp()),))  # the series start
        self.assertEqual(self.db.execute("SELECT name FROM players WHERE player_id = ?",
                                         (negative_id("challengermode", BOB),)).fetchone(), ("bob",))

    def test_a_dev_build_reads_only_its_events(self):
        self.db.execute("DELETE FROM events WHERE event_id <> ?", (CM,))
        self.run_step()
        self.assertEqual({v[0] for v in self.matches().values()}, {CM})


if __name__ == "__main__":
    unittest.main()
