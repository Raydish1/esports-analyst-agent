import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_aliases  # noqa: E402
import build_rankings  # noqa: E402
import crawl  # noqa: E402
from build_players import Players  # noqa: E402
from cache import ResponseCache, query_hash  # noqa: E402
from cache_reader import CacheReader  # noqa: E402
from curation import Curation, Merge, PlayerAlias  # noqa: E402
from problems import CurationError  # noqa: E402


class IdentityStepsTest(unittest.TestCase):
    """Aliases, merges and the PR rows, on a small set of players."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")
        cache.store("startgg/Entrants", {"q": query_hash(crawl.ENTRANTS_QUERY), "slug": "e2", "page": 1}, "u", 200,
                    json.dumps({"data": {"event": {"entrants": {"nodes": [{"id": 9, "participants": [
                        {"gamerTag": "Lately", "prefix": "LT", "player": {"id": 300}}]}]}}}}).encode(), 5)
        for page, rows, updated in ((1, [(1, 100.5, 3), (2, 0, 8)], "2026-10-01"), (2, [(1, 250.0, 2)], "2026-10-02")):
            cache.store("/pr", {"gameMode": 1, "region": "NA", "page": page}, "u", 200, json.dumps({
                "lastUpdated": updated, "prPlayers": [{"playerId": pid, "earnings": earned, "powerRanking": rank,
                                                       "points": 1.5, "top8": 2, "top32": 3, "gold": 1, "silver": 0,
                                                       "bronze": 0} for pid, earned, rank in rows]}).encode(), 5)
        cache.db.close()
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        self.db.executemany("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official,"
                            " is_twos, is_online, fetched_at) VALUES (?, 'SGG', ?, 2020, ?, 1, 0, 0, 't')",
                            [("e1", "e1", 100), ("e2", "e2", 200)])
        self.players = Players()
        records = [(1, "Pink | Guichabou", 100), (2, "★★", 200), (3, "Zivai", 300), (4, "Remmy", 400), (5, "Remmy", 500),
                   (6, "Six", 600)]
        for pid, name, sgg in records:
            self.players.observe({"playerId": pid, "name": name, "sggPlayerId": sgg}, "2026-10-05")
        self.players.observe({"playerId": 3, "name": "Godly"}, "2026-10-01")  # an older name
        self.players.index()
        for sgg in ("100", "200", "300", "400", "500", "600", "700"):
            self.players.resolve("startgg", sgg, "Lost" if sgg == "700" else None, (100, "t"))  # 700: platform-only
        self.players.flush(self.db, everyone=True)
        self.db.executemany(
            "INSERT INTO standings (event_id, entrant_key, platform_player, player_id, gamer_tag, prefix, placement,"
            " source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, 't')",
            [("e1", "1", "300", 3, "Godly", "Kingdom", "startgg"), ("e2", "2", "300", 3, "godly", None, "startgg"),
             ("e1", "3", "100", 1, "guichabou", "Pink", "startgg"), ("e2", "4", "cm-x", 6, "sixer", None, "challengermode")])
        self.log = []

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def run_steps(self, merges=(), rejections=(), nicknames=(), steps=("aliases", "merges")):
        cur = Curation()
        cur.player_aliases = [PlayerAlias(a, shown, pid, note, i) for i, (a, shown, pid, note) in enumerate(nicknames, 2)]
        cur.merges = [Merge(a, b, source, None, i) for i, (a, b, source) in enumerate(merges, 2)]
        cur.rejections = {frozenset(pair) for pair in rejections}
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite")
        try:
            b = build.Build(self.db, reader, self.root, self.log.append, auto_merges=None)
            b.players, b.curation = self.players, cur
            for name, step in build.STEPS:
                if name in steps:
                    step(b)
        finally:
            reader.close()
        return b

    def aliases(self, pid):
        return sorted(self.db.execute("SELECT alias, kind, shown_as, source, note FROM player_aliases WHERE player_id = ?",
                                      (pid,)))

    def test_display_names_names_without_tags_and_former_names(self):
        self.run_steps()
        self.assertEqual(self.aliases(1), [("guichabou", "without_tag", "Pink | Guichabou", "stats_api", None),
                                           ("pinkguichabou", "display_name", "Pink | Guichabou", "stats_api", None)])
        self.assertEqual(self.aliases(3), [
            ("godly", "former_name", "godly", "startgg", None),  # the newest spelling of the alias
            ("lately", "former_name", "LT | Lately", "startgg", None),  # from an entrant list
            ("zivai", "display_name", "Zivai", "stats_api", None)])
        self.assertEqual(self.aliases(6), [("six", "display_name", "Six", "stats_api", None),
                                           ("sixer", "former_name", "sixer", "challengermode", None)])
        self.assertEqual(self.aliases(2), [])  # a name made only of symbols
        self.assertEqual(self.aliases(-700), [("lost", "display_name", "Lost", "startgg", None)])

    def test_a_curated_nickname_wins_and_keeps_its_note(self):
        b = self.run_steps(nicknames=[("godly", "Godly", 3, "Zivai's old name"), ("ghost", "Ghost", 999, None)])
        self.assertIn(("godly", "nickname", "Godly", "curated", "Zivai's old name"), self.aliases(3))
        self.assertEqual([str(s) for s in b.skipped], ["player_aliases.csv:3: the cache has no player 999"])
        self.assertEqual(b.skipped[0].key, "player_aliases.csv:ghost:999")  # the row, for the review list

    def test_merges_resolve_ids_and_collapse_chains(self):
        b = self.run_steps(merges=[(4, 5, "curated"), (5, 6, "curated"), (-700, 1, "auto"), (-100, 3, "curated"),
                                   (888, 1, "curated")])
        self.assertEqual(self.db.execute("SELECT player_id, canonical_player_id, source FROM player_merges"
                                         " ORDER BY player_id").fetchall(),
                         [(-700, 3, "auto"), (1, 3, "curated"), (4, 6, "curated"), (5, 6, "curated")])  # chains collapsed
        self.assertIn("player_merges.csv:6: the cache has no player 888", map(str, b.skipped))  # -100 is now record 1

    def test_a_curated_merge_that_conflicts_once_resolved_stops_the_build(self):
        with self.assertRaises(CurationError) as caught:
            self.run_steps(merges=[(4, 5, "curated")], rejections=[(-400, 5)])  # -400 is record 4
        self.assertIn("would be one person", caught.exception.problems[0])
        b = self.run_steps(merges=[(4, 5, "auto")], rejections=[(-400, 5)], steps=("merges",))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM player_merges").fetchone()[0], 0)
        self.assertTrue(any("would be one person" in s.reason for s in b.skipped))

    def test_pr_rows_and_career_earnings(self):
        self.run_steps(steps=("rankings",))
        self.assertEqual(self.db.execute("SELECT player_id, mode, as_of, region, power_ranking FROM pr_snapshots"
                                         " ORDER BY as_of, player_id").fetchall(),
                         [(1, "1v1", "2026-10-01", "NA", 3), (2, "1v1", "2026-10-01", "NA", 8),
                          (1, "1v1", "2026-10-02", "NA", 2)])
        self.assertEqual(self.db.execute("SELECT player_id, amount_usd, as_of FROM player_earnings ORDER BY player_id")
                         .fetchall(), [(1, 250.0, "2026-10-02"), (2, 0, "2026-10-01")])  # the newest; a ranked 0 is kept


if __name__ == "__main__":
    unittest.main()
