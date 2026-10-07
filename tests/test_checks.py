import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_events  # noqa: E402
import checks  # noqa: E402
from build_players import Players  # noqa: E402
from cache import ResponseCache  # noqa: E402
from cache_reader import CacheReader  # noqa: E402
from curation import CheckException, Curation, EventOverride, Skipped  # noqa: E402

PRO = "series/pro-series-x"


def make_db(path=":memory:"):
    db = sqlite3.connect(path)
    db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
    db.executescript(build.VIEWS.read_text(encoding="utf-8"))
    return db


def override(event_id, line, fmt=None, status=None):
    return EventOverride(event_id, fmt, None, None, None, status, None, line)


class ChecksTest(unittest.TestCase):
    """Every check on one small database, each event built to pass or fail particular checks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cache = ResponseCache(root / "cache", root / "crawl.sqlite")
        for params, ids in (({"gameMode": 1, "isOfficial": True}, ["a", "lost"]),
                            ({"gameMode": 1, "isOfficial": True, "year": 2020}, ["a"])):
            cache.store("/event", params, "u", 200, json.dumps({"tournaments": [{"id": i} for i in ids]}).encode(), 5)
        cache.store("/player/placement", {"playerIds": 1, "gameMode": 1}, "u", 200, json.dumps({"playerPlacements": [
            {"placement": 1, "tournament": {"id": "a"}}, {"placement": 4, "tournament": {"id": "e"}},
            {"placement": 1, "tournament": {"id": PRO}}]}).encode(), 5)
        cache.store("/player/placement", {"playerIds": 10, "gameMode": 1}, "u", 200, json.dumps({"playerPlacements": [
            {"placement": 3, "tournament": {"id": "a"}}]}).encode(), 5)  # record 10 is merged into 3, who placed 3rd
        cache.db.close()

        db = cls.db = make_db()
        db.executemany("INSERT INTO players (player_id, name, sgg_player_id, source, updated_at, canonical_id)"
                       " VALUES (?, ?, ?, 'stats_api', 't', ?)",
                       [(i, f"p{i}", 444 if i in (4, 5) else None, 3 if i == 10 else i) for i in range(1, 11)])
        db.execute("INSERT INTO player_aliases VALUES ('ghost', 99, 'nickname', 'Ghost', 'curated', NULL)")  # no player 99
        db.executemany("INSERT INTO format_rules VALUES (?, ?, ?)",
                       [("%crew battle%", "crew_battle", 1), ("%alpha%", "aaa", 2), ("%beta%", "bbb", 2)])
        events = [  # (ID, host, name, is_twos, start, slug, format_override, status)
            ("a", "SGG", "Cup", 0, 100, "cup", None, None),
            ("b", "SGG", "Duos", 1, 200, "duos", None, None),
            ("c", "SGG", "Showdown", 0, 300, "show", None, None),  # entrants of three, new: held out
            ("c2", "SGG", "Second Showdown", 0, 310, "show2", None, None),  # the same, but reviewed
            ("d", "CM", "Spring 1v1", 0, 400, None, None, None),
            ("e", "SGG", "Open", 0, 500, "open", None, None),
            (PRO, "SGG", "Pro Series", 0, 600, None, "crew_battle", None),
            ("gone", "SGG", "Dreamland", 0, 700, "dream", None, "cancelled"),
            ("ab", "SGG", "Alpha Beta Cup", 0, 800, "ab", None, None),  # two rules tie
            ("s1", "SGG", "League Swiss", 0, 900, "league", None, None),  # s2 is its top two
            ("s2", "SGG", "League Finals", 0, 905, "league", None, None)]
        db.executemany("INSERT INTO events (event_id, host, tournament_name, is_twos, start_time, sgg_tournament_slug,"
                       " format_override, status, year, is_official, is_online, fetched_at)"
                       " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 2020, 1, 0, 't')", events)
        db.executemany("INSERT INTO teams VALUES (?, ?, ?)", [(1, 1, 2), (2, 3, 4)])
        standings = [  # (event, entrant, player, placement)
            ("a", "a1", 1, 1), ("a", "a2", 2, 2), ("a", "a3", 3, 3),
            ("b", "b1", 1, 1), ("b", "b1", 2, 1), ("b", "b2", 3, 2), ("b", "b2", 4, 2),
            ("c", "c1", 1, 1), ("c", "c1", 2, 1), ("c", "c1", 3, 1),
            ("c2", "k1", 4, 1), ("c2", "k1", 5, 1), ("c2", "k1", 6, 1),
            ("d", "d1", 1, 1), ("d", "d2", 2, 2),
            ("e", "e1", 5, 1), ("e", "e2", 6, 1), ("e", "e3", 8, 3)]
        db.executemany("INSERT INTO standings (event_id, entrant_key, platform_player, player_id, placement, source,"
                       " fetched_at) VALUES (?, ?, ?, ?, ?, 'startgg', 't')",
                       [(e, k, str(p), p, place) for e, k, p, place in standings])
        team = {("b", 1): 1, ("b", 2): 1, ("b", 3): 2, ("b", 4): 2}
        placements = [(e, p, place, team.get((e, p)), "startgg") for e, _, p, place in standings]
        placements += [(PRO, p, 1 if p <= 3 else 2 if p <= 6 else 3, None, "stats_api") for p in range(1, 9)]
        placements += [("s1", p, p, None, "startgg") for p in range(1, 5)] + [("s2", 1, 1, None, "startgg"),
                                                                               ("s2", 2, 2, None, "startgg")]
        db.executemany("INSERT INTO placements VALUES (?, ?, ?, ?, ?, 't')", placements)
        db.execute("INSERT INTO unplaced_entries VALUES ('e', 7)")
        matches = [  # (ID, event, score 1, score 2, reported winner, source, side 1, side 2)
            ("m1", "a", 2, 0, 1, "startgg", [1], [2]),
            ("m2", "a", 2, 0, 2, "startgg", [1], [3]),  # the reported winner disagrees with the scores
            ("m6", "a", 0, 0, None, "startgg", [2], [3]),  # 0-0 on start.gg
            ("m3", "b", 2, 1, 1, "startgg", [1, 2], [3, 4]),
            ("m4", "d", 1, 1, 1, "challengermode", [1], [2]),  # a tie
            ("m5", "e", 2, 0, 1, "startgg", [5], [7])]  # 7 played without a placement
        db.executemany("INSERT INTO matches (match_id, event_id, side1_score, side2_score, reported_winner_side, source,"
                       " fetched_at) VALUES (?, ?, ?, ?, ?, ?, 't')", [m[:6] for m in matches])
        db.executemany("INSERT INTO match_players VALUES (?, ?, ?)",
                       [(m[0], side, p) for m in matches for side, ps in ((1, m[6]), (2, m[7])) for p in ps])
        db.executemany("INSERT INTO event_sources (event_id, platform, reported_entrants, reported_sets, sets_seen,"
                       " entrants_unknown, series_without_match, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, 't')", [
                           ("a", "startgg", 3, 3, 3, 0, None), ("b", "startgg", 2, 1, 1, 0, None),
                           ("c", "startgg", 1, 0, 0, 0, None), ("c2", "startgg", 1, 0, 0, 0, None),
                           ("d", "challengermode", 2, None, 1, 1, 1), ("e", "startgg", 3, 3, 2, 0, None),
                           (PRO, "stats_api", None, None, None, None, None), ("gone", "startgg", 0, 0, 0, 0, None)])
        db.executemany("INSERT INTO pr_snapshots (player_id, mode, as_of, region, top8, top32, gold, silver, bronze)"
                       " VALUES (?, '1v1', ?, 'NA', ?, ?, ?, ?, ?)",
                       [(1, "2026-10-01", 0, 0, 0, 0, 0), (1, "2026-10-02", 5, 5, 5, 0, 0),  # the newest list counts
                        (2, "2026-10-02", 1, 1, 0, 1, 0)])

        live = cls.live = root / "live.sqlite"
        old = make_db(live)
        old.executemany("INSERT INTO events (event_id, host, tournament_name, year, start_time, is_official, is_twos,"
                        " is_online, fetched_at) VALUES (?, 'SGG', 'x', 2020, 0, 1, 0, 0, 't')", [("a",), ("lost",)])
        old.executemany("INSERT INTO placements VALUES ('a', ?, 1, NULL, 'startgg', 't')", [(p,) for p in range(1, 5)])
        old.executemany("INSERT INTO build_checks VALUES (?, 'no_worse', ?, ?, '')",
                        [("no_contests", "", "pass"), ("no_contests", "m9", "fail"), ("pr_cross_check", "", "pass"),
                         ("pr_cross_check", "9 1v1", "fail")])
        old.commit()
        old.close()

        cur = Curation()
        cur.events = [override("c2", 2), override(PRO, 3, fmt="crew_battle"), override("gone", 4, status="cancelled")]
        cur.check_exceptions = [CheckException("winners", "gone", "not held", 2),
                                CheckException("teams", "nowhere", "a typo", 3)]
        players = Players()
        players.unasked.add(("startgg", "777"))
        cls.reader = CacheReader(root / "cache", root / "crawl.sqlite")
        b = cls.build = build.Build(db, cls.reader, root, lambda *_: None, auto_merges=None)
        b.curation, b.players, b.live = cur, players, live
        b.skipped = [Skipped("player_aliases.csv:2", "the cache has no player 999", "player_aliases.csv:x:999")]
        build_events.hold_out_step(b)
        cls.outcomes = checks.run(b, log=lambda *_: None)

    @classmethod
    def tearDownClass(cls):
        cls.reader.close()
        cls.db.close()
        cls.tmp.cleanup()

    def found(self, check_id):
        """{subject: (outcome, detail)} of a check's rows, '' for its verdict."""
        return {o.subject: (o.outcome, o.detail) for o in self.outcomes if o.check_id == check_id}

    def outcomes_of(self, check_id):
        return {subject: outcome for subject, (outcome, _) in self.found(check_id).items()}

    def test_a_new_event_whose_entrants_dont_fit_is_held_out(self):
        held = dict(self.db.execute("SELECT event_id, held_out FROM events WHERE held_out IS NOT NULL"))
        self.assertEqual(list(held), ["c"])  # c2 has a row in events.csv, so it's counted and fails instead
        self.assertIn("should have entrants of 1 player, but it has entrants of 3 players (1 of 1)", held["c"])
        self.assertEqual(self.db.execute("SELECT counts_as FROM v_events WHERE event_id = 'c'").fetchone(), (None,))
        self.assertEqual(self.outcomes_of("entrant_sizes"), {"": "fail", "c": "listed", "c2": "fail"})

    def test_event_totals(self):
        self.assertEqual(self.outcomes_of("event_totals"), {"": "fail", "lost": "fail"})

    def test_winners(self):
        found = self.found("winners")
        self.assertEqual(found["e"], ("fail", "2 entrants placed 1st (2 players)"))
        self.assertEqual(found["c2"], ("fail", "3 players placed 1st"))
        self.assertEqual(found["gone"][0], "explained")  # check_exceptions.csv
        self.assertIn("check_exceptions.csv:2: not held", found["gone"][1])
        self.assertEqual(set(found) - {""}, {"e", "c2", "gone"})  # a, b's pair, d, the crews and the league pass
        self.assertEqual(found[""][0], "fail")

    def test_pr_cross_check_uses_the_newest_list_and_pr_own_rule(self):
        found = self.found("pr_cross_check")
        self.assertEqual(set(found), {"", "2 1v1"})  # 1: golds at a, c, d, s1 and s2, as PR has it (not the crews')
        self.assertIn("PR top 8/top 32/gold/silver/bronze 1/1/0/1/0, placements give 5/5/1/4/0", found["2 1v1"][1])
        self.assertEqual(found[""][0], "pass")  # no worse than the live build's one
        self.assertIn("the live build had 1", found[""][1])

    def test_teams(self):
        self.assertEqual(self.found("teams")[""][0], "pass")
        self.assertIn("the live build didn't run this check", self.found("teams")[""][1])

    def test_completeness(self):
        found = self.found("completeness")
        self.assertEqual(set(found), {"", "d", "e"})
        self.assertEqual(found["d"][1], "1 lineup in the bracket is missing from the entrant list; 1 series between"
                                        " two lineups has no match")
        self.assertEqual(found["e"][1], "2 sets on the cached pages, but start.gg reports 3; 1 player who played has"
                                        " no placement: their entrant isn't in the standings")

    def test_match_presence(self):
        found = self.found("match_presence")
        self.assertEqual(found["e"], ("fail", "2 of 3 placed players have no match"))
        self.assertEqual(found[PRO], ("fail", "8 of 8 placed players have no match"))
        self.assertNotIn("a", found)

    def test_stats_api_placements_compare_people_not_records(self):
        found = self.found("stats_api_placements")
        self.assertEqual(set(found), {"", "e 1"})  # 10 placed 3rd at a as record 3; the Pro Series isn't compared
        self.assertEqual(found["e 1"][1], "the Stats API places p1 (1) 4th; the standings don't place them")

    def test_no_contests(self):
        found = self.found("no_contests")
        self.assertEqual(set(found), {"", "m2", "m4", "m6"})
        self.assertIn("start.gg reports side 2 as the winner, but the scores make it side 1", found["m2"][1])
        self.assertIn("a tie, so it counts for nobody", found["m4"][1])
        self.assertIn("a 0-0 on start.gg", found["m6"][1])
        self.assertEqual(found[""][0], "fail")  # three, where the live build had one
        self.assertIn("the live build had 1", found[""][1])

    def test_pro_series(self):
        self.assertEqual(self.found("pro_series")[PRO], ("fail", "3rd has 2 players, not whole teams of 3"))

    def test_integrity(self):
        found = self.found("integrity")
        self.assertEqual(found["player_aliases -> players"], ("fail", "1 player_aliases rows point at a missing players row"))
        self.assertEqual(found["sgg_player_id 444"][0], "fail")
        self.assertEqual(found["startgg player 777"][0], "fail")
        self.assertEqual(found["player_aliases.csv:2"], ("listed", "!! curated row skipped: the cache has no player 999"))
        self.assertEqual(found["check_exceptions.csv:3"][0], "listed")  # explains nothing: a typo
        self.assertEqual(self.build.unused_exceptions, [CheckException("teams", "nowhere", "a typo", 3)])

    def test_regression(self):
        found = self.found("regression")
        self.assertEqual(found["lost"], ("fail", "in the live build, not in this one"))
        self.assertEqual(found["a"], ("fail", "fewer than in the live build: placements 4 -> 3"))

    def test_review_checks(self):
        self.assertEqual(set(self.outcomes_of("new_events")) - {""}, {"a", "b", "c", "d", "e", "ab", "s1", "s2"})
        self.assertIn("detected 1v1, aaa (the rule '%alpha%')", self.found("new_events")["ab"][1])
        self.assertEqual(self.found("format_rule_ties")["ab"][1],
                         "matched by '%alpha%' (aaa), '%beta%' (bbb) at priority 2; '%alpha%' wins")
        self.assertEqual(set(self.found("phase_splits")), {"", "s1 s2"})
        self.assertIn("2 of its 2 players placed in the other's top 4", self.found("phase_splits")["s1 s2"][1])

    def test_event_coverage(self):
        flags = dict(self.db.execute("SELECT event_id, flag FROM v_event_coverage"))
        self.assertEqual({e: flags[e] for e in ("a", "b", "c", "e", PRO, "gone", "s1")}, {
            "a": None, "b": None, "c": "held out for review; no match data",
            "e": "placements incomplete; match data incomplete",  # 7 played unplaced; 6 and 8 have no match
            PRO: "no match data", "gone": "not held", "s1": "no match data"})
        self.assertEqual(self.db.execute(
            "SELECT entrants_reported, entrants_placed, placements, worst_placement, matches_reported, matches_seen,"
            " matches_held, players_with_matches, placed_without_match, played_unplaced, twos_without_team"
            " FROM v_event_coverage WHERE event_id = 'e'").fetchone(), (3, 3, 3, 3, 3, 2, 1, 2, 2, 1, 0))

    def test_the_verdict(self):
        self.assertFalse(checks.passed(self.outcomes))
        self.assertTrue(all(o.outcome == "pass" for o in self.outcomes if o.subject == "" and o.gate == "review"))


class RunnerTest(unittest.TestCase):
    """How exceptions, gates and the live build's counts settle a check's verdict."""

    def settle(self, rows, before=None):
        return {o.check_id: o.outcome for o in checks.settle(rows, before) if o.subject == ""}

    def test_gates(self):
        O = checks.Outcome
        rows = [O("x", "blocking", "", "pass", ""), O("x", "blocking", "e1", "explained", ""),
                O("y", "no_worse", "", "pass", ""), O("y", "no_worse", "e1", "fail", ""), O("y", "no_worse", "e2", "fail", ""),
                O("z", "review", "e1", "listed", "")]
        self.assertEqual(self.settle(rows), {"x": "pass", "y": "pass", "z": "pass"})  # nothing to compare with
        self.assertEqual(self.settle(rows, {"y": 2})["y"], "pass")
        self.assertEqual(self.settle(rows, {"y": 1})["y"], "fail")
        self.assertEqual(self.settle(rows + [O("x", "blocking", "e2", "fail", "")])["x"], "fail")

    def test_an_exception_explains_only_a_failure_it_names(self):
        O = checks.Outcome
        rows = [O("x", "blocking", "e1", "fail", "bad"), O("x", "blocking", "e2", "listed", "look")]
        out, unused = checks.explain(rows, [CheckException("x", "e1", "known", 5), CheckException("x", "e2", "?", 6)])
        self.assertEqual(out[0], O("x", "blocking", "e1", "explained", "bad; check_exceptions.csv:5: known"))
        self.assertEqual(out[1].outcome, "listed")
        self.assertEqual(unused, [CheckException("x", "e2", "?", 6)])


if __name__ == "__main__":
    unittest.main()
