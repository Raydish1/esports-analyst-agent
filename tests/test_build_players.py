import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_events  # noqa: E402
import build_players  # noqa: E402
import crawl  # noqa: E402
from build_players import negative_id  # noqa: E402
from cache import ResponseCache, query_hash  # noqa: E402
from cache_reader import CacheReader  # noqa: E402
from problems import BuildStop  # noqa: E402

ALICE = "e2d264bb-027e-44cd-b864-718b9db1b0d7"  # has a Stats API record
BOB = "2a1b4620-6035-43a6-a4a7-1006ad9e57a4"  # doesn't
CAROL = "b368844e-8e51-48aa-8c0f-000000000000"  # only in a lineup that never played


def event(event_id, start, twos=False, host="SGG"):
    return {"id": event_id, "tournamentName": event_id, "eventName": None, "year": 2020, "isOfficial": True,
            "isTwos": twos, "isOnline": True, "startTime": start, "host": host}


def record(pid, name, sgg=None, cm=None, **more):
    return {"playerId": pid, "sggPlayerId": sgg, "cmPlayerId": cm, "brawlhallaId": None, "name": name, **more}


def entrant(entrant_id, placement, *players, dq=False):
    """A start.gg standings node; players are (player ID, gamer tag, prefix)."""
    return {"placement": placement, "entrant": {"id": entrant_id, "name": "/".join(p[1] for p in players),
                                                "initialSeedNum": placement, "isDisqualified": dq,
                                                "participants": [{"id": entrant_id * 10 + i, "gamerTag": tag,
                                                                  "prefix": prefix, "player": {"id": pid}}
                                                                 for i, (pid, tag, prefix) in enumerate(players)]}}


def lineup(lineup_id, best, *members, worst=None):
    return {"id": lineup_id, "name": f"team {lineup_id}", "seed": 1, "disqualified": False,
            "placement": None if best is None else {"bestPlacement": best, "worstPlacement": worst or best},
            "members": [{"user": {"id": uid, "username": name}} for uid, name in members]}


class PlayersStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")
        self.store("/event", {"gameMode": 1, "isOfficial": True},
                   {"tournaments": [event("tournament/a/event/1v1", 100), event("tournament/b/event/1v1", 200),
                                    event("cm-1", 300, host="CM"), event("series/pro-series-2019-na", 50)]})
        self.store("/players", {"sggIds": "100,101,102"},
                   {"players": [record(1, "Old name", sgg=100), record(2, "Two", sgg=101),
                                record(None, None)]})  # 102 isn't in the Stats API
        self.store("/players", {"cmIds": f"{ALICE},{BOB.upper()}"}, {"players": [record(3, "Alice", cm=ALICE.upper())]})
        self.store("/players", {"playerIds": "1"}, {"players": [record(1, "New name", sgg=None, twitter="new_tw")]})
        self.store("/player/teammate", {"playerId": 9},
                   {"playerTeammates": [{"player": record(4, "Mate", sgg=104), "games": 3}]})
        self.store("/pr", {"gameMode": 1, "region": "NA", "page": 1},
                   {"prPlayers": [{"playerId": 5, "playerName": "Ranked"}]})
        q = query_hash(crawl.STANDINGS_QUERY)
        self.store("startgg/Standings", {"q": q, "slug": "tournament/a/event/1v1", "page": 1}, self.standings(4, [
            entrant(10, 1, (100, "Tag", "PFX")), entrant(11, 2, (102, "Ghost", "")),
            entrant(12, 3, (101, "Two", None)), entrant(13, 4, (101, "Two again", None), dq=True)], event_id=555))
        self.store("startgg/Standings", {"q": q, "slug": "tournament/b/event/1v1", "page": 1}, self.standings(2, [
            entrant(20, 1, (102, "Ghost 2.0", "")), entrant(21, 2, (999, "Nobody asked", ""))], event_id=556))
        self.store("challengermode/Roster", {"q": query_hash(crawl.CM_ROSTER_QUERY), "id": "cm-1", "limit": 2000},
                   {"data": {"tournament": {"id": "cm-1", "state": "COMPLETED", "attendance": {"roster": {
                       "lineupCount": 3, "lineups": [lineup("L1", 1, (ALICE.upper(), "alice")),
                                                     lineup("L2", 5, (BOB, "bob"), worst=6),
                                                     lineup("L3", None, (CAROL, "carol"))]}}}}})
        self.cache.db.close()
        self.curation = self.root / "curation"
        self.curation.mkdir()
        for name, header in (("format_rules.csv", "pattern,format,priority"), ("events.csv", "event_id"),
                             ("event_aliases.csv", "alias,event_id"), ("event_terms.csv", "term,means"),
                             ("player_aliases.csv", "alias,player_id"),
                             ("player_merges.csv", "player_id,canonical_player_id"),
                             ("merge_rejections.csv", "player_id,other_player_id")):
            (self.curation / name).write_text(header + "\n", encoding="utf-8")
        self.dbs, self.log = [], []

    def tearDown(self):
        for db in self.dbs:
            db.close()
        self.tmp.cleanup()

    def store(self, endpoint, params, body):
        self.cache.store(endpoint, params, "u", 200, json.dumps(body).encode(), 5)

    @staticmethod
    def standings(total, nodes, event_id):
        return {"data": {"event": {"id": event_id, "standings": {"pageInfo": {"total": total, "totalPages": 1},
                                                                 "nodes": nodes}}}}

    def run_steps(self, events=None):
        db = sqlite3.connect(":memory:")
        self.dbs.append(db)
        db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite")
        try:
            b = build.Build(db, reader, self.curation, self.log.append, events, auto_merges=None)
            for _, step in build.STEPS[:4]:
                step(b)
        finally:
            reader.close()
        return db, b

    def test_every_stats_api_record_with_its_newest_values(self):
        db, _ = self.run_steps()
        rows = {r[0]: r[1:] for r in db.execute(
            "SELECT player_id, name, sgg_player_id, cm_player_id, twitter, source FROM players WHERE player_id > 0")}
        self.assertEqual(rows, {1: ("New name", 100, None, "new_tw", "stats_api"),  # the newer response had no sgg ID
                                2: ("Two", 101, None, None, "stats_api"), 3: ("Alice", None, ALICE, None, "stats_api"),
                                4: ("Mate", 104, None, None, "stats_api"), 5: ("Ranked", None, None, None, "stats_api")})

    def test_platform_players_without_a_record_get_stable_negative_ids(self):
        db, b = self.run_steps()
        rows = dict(db.execute("SELECT player_id, name FROM players WHERE player_id < 0"))
        self.assertEqual(rows, {-102: "Ghost 2.0",  # named after their newest standings entry
                                -999: "Nobody asked", negative_id("challengermode", BOB): "bob"})
        self.assertEqual(db.execute("SELECT sgg_player_id, source, in_stats_api FROM players WHERE player_id = -102")
                         .fetchone(), (102, "startgg", 0))
        self.assertEqual(b.players.unasked, {("startgg", "999")})
        self.assertNotIn(negative_id("challengermode", CAROL), rows)  # her lineup never played

    def test_standings_rows_for_placed_entrants(self):
        db, _ = self.run_steps()
        rows = db.execute("SELECT event_id, entrant_key, platform_player, player_id, gamer_tag, prefix, placement,"
                          " worst_placement, is_disqualified, source FROM standings"
                          " ORDER BY event_id, entrant_key").fetchall()
        self.assertEqual(rows, [
            ("cm-1", "L1", ALICE, 3, "alice", None, 1, 1, 0, "challengermode"),
            ("cm-1", "L2", BOB, negative_id("challengermode", BOB), "bob", None, 5, 6, 0, "challengermode"),
            ("tournament/a/event/1v1", "10", "100", 1, "Tag", "PFX", 1, None, 0, "startgg"),
            ("tournament/a/event/1v1", "11", "102", -102, "Ghost", None, 2, None, 0, "startgg"),
            ("tournament/a/event/1v1", "12", "101", 2, "Two", None, 3, None, 0, "startgg"),
            ("tournament/a/event/1v1", "13", "101", 2, "Two again", None, 4, None, 1, "startgg"),  # entered twice
            ("tournament/b/event/1v1", "20", "102", -102, "Ghost 2.0", None, 1, None, 0, "startgg"),
            ("tournament/b/event/1v1", "21", "999", -999, "Nobody asked", None, 2, None, 0, "startgg")])
        self.assertEqual(db.execute("SELECT event_id, platform, platform_event_id, state, reported_entrants"
                                    " FROM event_sources ORDER BY event_id").fetchall(), [
            ("cm-1", "challengermode", "cm-1", "COMPLETED", 3),
            ("series/pro-series-2019-na", "stats_api", None, None, None),
            ("tournament/a/event/1v1", "startgg", "555", None, 4), ("tournament/b/event/1v1", "startgg", "556", None, 2)])

    def test_a_dev_build_writes_only_the_players_it_refers_to(self):
        db, _ = self.run_steps(events={"cm-1"})
        self.assertEqual({r[0] for r in db.execute("SELECT player_id FROM players")},
                         {3, negative_id("challengermode", BOB)})

    def test_two_players_with_one_negative_id_stop_the_build(self):
        players = build_players.Players()
        players.resolve("challengermode", "e2d264bb-02aa-0000-0000-000000000000", "a", (1, "t"))
        with self.assertRaises(BuildStop):
            players.resolve("challengermode", "e2d264bb-02bb-0000-0000-000000000000", "b", (1, "t"))

    def test_negative_ids(self):
        self.assertEqual(negative_id("startgg", "4567"), -4567)
        self.assertEqual(negative_id("challengermode", ALICE), -(2 ** 40 + 0xe2d264bb02))
        self.assertLess(negative_id("challengermode", "00000000-0000-0000-0000-000000000000"), -(10 ** 12))


if __name__ == "__main__":
    unittest.main()
