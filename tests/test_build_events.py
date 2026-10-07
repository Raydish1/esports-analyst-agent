import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import build  # noqa: E402
import build_events  # noqa: E402
from builds import Builds  # noqa: E402
from cache import ResponseCache  # noqa: E402
from cache_reader import CacheReader  # noqa: E402
from curation import CurationError  # noqa: E402

FULL = {"isOfficial": True, "maxResults": 50}


def event(event_id, start, name="Cup", event_name="1v1", twos=False, host="SGG"):
    return {"id": event_id, "tournamentName": name, "eventName": event_name, "year": 2018, "isOfficial": True,
            "isTwos": twos, "isOnline": True, "startTime": start, "host": host}


class EventsStepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        cache = ResponseCache(self.root / "cache", self.root / "crawl.sqlite")

        def listing(params, *events):
            cache.store("/event", params, "u", 200, json.dumps({"tournaments": list(events)}).encode(), 5)
        listing({**FULL, "gameMode": 1}, event("tournament/cup/event/1v1", 100, name="Old name"),
                event("tournament/league/event/swiss", 150), event("tournament/league/event/top-8", 160),
                event("series/pro-series-2019-na", 200, "Pro Series 2019 NA", "Finals"))
        listing({**FULL, "gameMode": 1, "nextToken": "201"}, event("cm-1", 300, "Spring 2025 - 1v1", None, host="CM"))
        listing({**FULL, "gameMode": 2}, event("tournament/cup/event/2v2", 100, event_name="2v2", twos=True))
        listing({**FULL, "gameMode": 1, "year": 2018}, event("tournament/only-in-a-year/event/x", 120))
        listing({**FULL, "gameMode": 1}, event("tournament/cup/event/1v1", 100, name="New name"),  # a newer first page
                event("tournament/league/event/swiss", 150), event("tournament/league/event/top-8", 160),
                event("series/pro-series-2019-na", 200, "Pro Series 2019 NA", "Finals"))
        cache.db.close()
        self.curation = self.root / "curation"
        self.curation.mkdir()
        self.write("format_rules.csv", "pattern,format,priority,note", "%crew battle%,crew_battle,1,")
        self.write("events.csv", "event_id,format_override,mode_override,competition_id,phase_order,status,note",
                   "series/pro-series-2019-na,crew_battle,,,,,", "tournament/league/event/swiss,,,league,1,,",
                   "tournament/league/event/top-8,,,league,2,,", "cm-1,,,,,cancelled,never held: cancelled")
        self.write("event_aliases.csv", "alias,event_id,note", "Cup 2018,tournament/cup/event/1v1,",
                   "cup 2018,tournament/cup/event/2v2,the doubles")
        self.write("event_terms.csv", "term,means,note", "cups,cup,", "msi,midseason invitational,no such event yet")
        self.write("player_aliases.csv", "alias,player_id,note")
        self.write("player_merges.csv", "player_id,canonical_player_id,note")
        self.write("merge_rejections.csv", "player_id,other_player_id,note")
        self.write("check_exceptions.csv", "check,subject,note")
        self.dbs, self.log = [], []

    def tearDown(self):
        for db in self.dbs:
            db.close()
        self.tmp.cleanup()

    def write(self, name, *lines):
        (self.curation / name).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_steps(self, events=None):
        db = sqlite3.connect(":memory:")
        self.dbs.append(db)
        db.executescript(build.SCHEMA.read_text(encoding="utf-8"))
        reader = CacheReader(self.root / "cache", self.root / "crawl.sqlite")
        try:
            b = build.Build(db, reader, self.curation, self.log.append, events, auto_merges=None)
            build.load_curation(b)
            build_events.step(b)
        finally:
            reader.close()
        return db

    def test_events_come_from_the_full_listings_and_the_newest_response(self):
        db = self.run_steps()
        rows = db.execute("SELECT event_id, host, tournament_name, sgg_tournament_slug, is_twos FROM events"
                          " ORDER BY start_time, event_id").fetchall()
        self.assertEqual(rows, [("tournament/cup/event/1v1", "SGG", "New name", "cup", 0),
                                ("tournament/cup/event/2v2", "SGG", "Cup", "cup", 1),
                                ("tournament/league/event/swiss", "SGG", "Cup", "league", 0),
                                ("tournament/league/event/top-8", "SGG", "Cup", "league", 0),
                                ("series/pro-series-2019-na", "SGG", "Pro Series 2019 NA", None, 0),
                                ("cm-1", "CM", "Spring 2025 - 1v1", None, 0)])  # not the event only in a per-year listing

    def test_curated_columns_aliases_rules_and_sources(self):
        db = self.run_steps()
        self.assertEqual(db.execute("SELECT event_id, format_override, competition_id, phase_order FROM events"
                                    " WHERE format_override IS NOT NULL OR competition_id IS NOT NULL"
                                    " ORDER BY start_time").fetchall(),
                         [("tournament/league/event/swiss", None, "league", 1),
                          ("tournament/league/event/top-8", None, "league", 2),
                          ("series/pro-series-2019-na", "crew_battle", None, None)])
        self.assertEqual(db.execute("SELECT event_id, status, note FROM events WHERE status IS NOT NULL").fetchall(),
                         [("cm-1", "cancelled", "never held: cancelled")])
        self.assertEqual(db.execute("SELECT alias, event_id, note FROM event_aliases ORDER BY event_id").fetchall(),
                         [("cup 2018", "tournament/cup/event/1v1", None),
                          ("cup 2018", "tournament/cup/event/2v2", "the doubles")])
        self.assertEqual(db.execute("SELECT * FROM format_rules").fetchall(), [("%crew battle%", "crew_battle", 1)])
        self.assertEqual(db.execute("SELECT term, means FROM event_terms ORDER BY term").fetchall(),
                         [("cups", "cup"), ("msi", "midseason invitational")])
        self.assertTrue(any("'msi': no official event's name has 'midseason invitational'" in line for line in self.log))
        self.assertFalse(any("'cups'" in line for line in self.log))
        self.assertEqual(dict(db.execute("SELECT event_id, platform FROM event_sources")), {
            "tournament/cup/event/1v1": "startgg", "tournament/cup/event/2v2": "startgg",
            "tournament/league/event/swiss": "startgg", "tournament/league/event/top-8": "startgg",
            "series/pro-series-2019-na": "stats_api", "cm-1": "challengermode"})

    def test_a_curated_row_naming_an_unknown_event_stops_the_build(self):
        self.write("events.csv", "event_id,format_override,mode_override,competition_id,phase_order,note",
                   "tournament/nope/event/1v1,,2v2,,,")
        self.write("event_aliases.csv", "alias,event_id,note", "cup,tournament/cup/event/1v1,", "nope,tournament/nope,")
        with self.assertRaises(CurationError) as caught:
            self.run_steps()
        self.assertEqual(caught.exception.problems, ["events.csv:2: no such event: tournament/nope/event/1v1",
                                                     "event_aliases.csv:3: no such event: tournament/nope"])

    def test_the_phases_of_a_competition_must_share_a_mode(self):
        self.write("events.csv", "event_id,format_override,mode_override,competition_id,phase_order,note",
                   "tournament/league/event/swiss,,,league,1,", "tournament/league/event/top-8,,2v2,league,2,")
        with self.assertRaises(CurationError) as caught:
            self.run_steps()
        self.assertIn("the phases of 'league' are in different modes", caught.exception.problems[0])

    def test_a_dev_build_loads_only_its_events_but_checks_every_curated_row(self):
        db = self.run_steps(events={"tournament/cup/event/1v1", "series/pro-series-2019-na"})
        self.assertEqual({r[0] for r in db.execute("SELECT event_id FROM events")},
                         {"tournament/cup/event/1v1", "series/pro-series-2019-na"})
        self.assertEqual(db.execute("SELECT COUNT(*) FROM event_aliases").fetchone()[0], 1)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM event_sources").fetchone()[0], 2)
        with self.assertRaises(CurationError) as caught:
            self.run_steps(events={"tournament/cup/event/1v1", "tournament/missing/event/1v1"})
        self.assertEqual(caught.exception.problems,
                         ["--event tournament/missing/event/1v1: not an official event in the cache"])
        self.write("event_aliases.csv", "alias,event_id,note", "nope,tournament/nope,")  # about an event not chosen
        with self.assertRaises(CurationError):
            self.run_steps(events={"tournament/cup/event/1v1"})

    def test_a_full_build_with_these_steps_goes_live_but_a_dev_build_never_does(self):
        builds = Builds(self.root / "db")
        kwargs = dict(builds=builds, log=self.log.append, cache_dir=self.root / "cache",
                      crawl_db=self.root / "crawl.sqlite", curation_dir=self.curation, auto_merges=None,
                      checks=[])  # every step, but no checks: these events have no results to check
        full, passed = build.make_build(**kwargs)
        self.assertTrue(passed)
        dev, passed = build.make_build(events=["cm-1"], **kwargs)
        self.assertTrue(passed)
        self.assertEqual(builds.live()["build"], full)
        db = sqlite3.connect(builds.path(dev))
        self.dbs.append(db)
        self.assertEqual(dict(db.execute("SELECT key, value FROM build_info WHERE key IN ('scope', 'events')")),
                         {"scope": '["cm-1"]', "events": "1"})


if __name__ == "__main__":
    unittest.main()
