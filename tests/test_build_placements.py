import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_placements  # noqa: E402
from build_players import Players  # noqa: E402
from cache import ResponseCache  # noqa: E402
from cache_reader import CacheReader  # noqa: E402

FINAL = "series/pro-series-2019-na"


class PlacementsStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")

        def pages(player_ids, *rows):
            cache.store("/player/placement", {"playerIds": player_ids, "gameMode": 1, "isOfficial": True}, "u", 200,
                        json.dumps({"playerPlacements": [{"placement": p, "tournament": {"id": e}} for e, p in rows]})
                        .encode(), 5)
        pages("11", (FINAL, 1), ("solo", 9))  # a final, and an event with standings, which stays a cross-check
        pages("12", (FINAL, 5))
        pages("12", (FINAL, 4))  # a newer response
        pages("11,12", (FINAL, 1))  # a pair's page
        pages("13", (FINAL, 3))  # no Stats API record
        cache.db.close()
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        events = [("solo", 0, None, "startgg"), ("duo", 1, None, "startgg"), ("filed-as-1v1", 0, "2v2", "startgg"),
                  ("crews", 0, None, "startgg"), (FINAL, 0, None, "stats_api")]
        self.db.executemany("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official, is_twos,"
                            " is_online, mode_override, fetched_at) VALUES (?, 'SGG', ?, 2020, 0, 1, ?, 0, ?, 't')",
                            [(e, e, twos, mode) for e, twos, mode, _ in events])
        self.db.executemany("INSERT INTO event_sources (event_id, platform, fetched_at) VALUES (?, ?, 't')",
                            [(e, platform) for e, _, _, platform in events])
        self.log = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def standings(self, event_id, *entrants):
        """entrants: (entrant key, placement, disqualified, player IDs)"""
        self.db.executemany(
            "INSERT INTO standings (event_id, entrant_key, platform_player, player_id, placement, is_disqualified,"
            " source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, 'startgg', 't')",
            [(event_id, key, str(pid), pid, place, dq) for key, place, dq, pids in entrants for pid in pids])

    def run_step(self):
        players = Players()
        for pid in (11, 12):
            players.observe({"playerId": pid, "name": f"p{pid}"}, "t")
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite")
        try:
            b = build.Build(self.db, reader, self.root, self.log.append, auto_merges=None)
            b.players = players
            build_placements.step(b)
        finally:
            reader.close()
        return {(e, p): (place, team, source) for e, p, place, team, source in
                self.db.execute("SELECT event_id, player_id, placement, team_id, source FROM placements")}

    def test_a_player_entered_twice_keeps_one_placement(self):
        self.standings("solo", ("a", 97, 0, [7]), ("b", 513, 0, [7]),  # the better placement
                       ("c", 50, 1, [8]), ("d", 1025, 0, [8]),  # an entrant that wasn't DQ'd first
                       ("e", 5, 1, [9]), ("f", 3, 1, [9]))  # both DQ'd: the better placement
        placed = self.run_step()
        self.assertEqual({p: placed[("solo", p)][0] for p in (7, 8, 9)}, {7: 97, 8: 1025, 9: 3})

    def test_two_player_entrants_of_2v2_events_are_teams(self):
        self.standings("duo", ("x", 1, 0, [3, 4]), ("y", 2, 0, [2, 1]), ("z", 3, 0, [5]))
        self.standings("filed-as-1v1", ("w", 1, 0, [1, 2]))  # a 2v2 event by its mode override
        self.standings("crews", ("c", 1, 0, [1, 2, 3]))
        placed = self.run_step()
        self.assertEqual(self.db.execute("SELECT team_id, player1_id, player2_id FROM teams").fetchall(),
                         [(1, 1, 2), (2, 3, 4)])  # numbered in pair order
        self.assertEqual({k: v[1] for k, v in placed.items() if k[0] != FINAL}, {
            ("duo", 3): 2, ("duo", 4): 2, ("duo", 1): 1, ("duo", 2): 1, ("duo", 5): None,
            ("filed-as-1v1", 1): 1, ("filed-as-1v1", 2): 1,
            ("crews", 1): None, ("crews", 2): None, ("crews", 3): None})

    def test_the_pro_series_finals_take_stats_api_placements(self):
        placed = self.run_step()
        self.assertEqual({k: v for k, v in placed.items() if k[0] == FINAL},
                         {(FINAL, 11): (1, None, "stats_api"), (FINAL, 12): (4, None, "stats_api")})
        self.assertNotIn(("solo", 11), placed)  # Stats API placements at platform events are only a cross-check
        self.assertTrue(any("1 Pro Series placement(s) left out" in line for line in self.log))


if __name__ == "__main__":
    unittest.main()
