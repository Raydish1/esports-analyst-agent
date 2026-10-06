import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import curation  # noqa: E402
from curation import CurationError  # noqa: E402

HEADERS = {
    "format_rules.csv": "pattern,format,priority,note\n%crew battle%,crew_battle,1,\n%3v3%,3v3,3,\n",
    "events.csv": "event_id,format_override,mode_override,competition_id,phase_order,note\n",
    "event_aliases.csv": "alias,event_id,note\n",
    "event_terms.csv": "term,means,note\n",
    "player_aliases.csv": "alias,player_id,note\n",
    "player_merges.csv": "player_id,canonical_player_id,note\n",
    "merge_rejections.csv": "player_id,other_player_id,note\n",
}


class CurationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name, text in HEADERS.items():
            (self.dir / name).write_text(text, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, *rows, header=None):
        text = header if header is not None else HEADERS[name].splitlines()[0] + "\n"
        (self.dir / name).write_text(text + "".join(row + "\n" for row in rows), encoding="utf-8")

    def load(self):
        return curation.load(self.dir, self.dir / "auto_merges.csv")

    def problems(self):
        with self.assertRaises(CurationError) as caught:
            self.load()
        return caught.exception.problems

    def test_the_committed_curation_files_are_valid(self):
        cur = curation.load(curation.CURATION_DIR, auto_merges=None)
        self.assertIn("crew_battle", cur.formats())
        self.assertIn(("bcx 2022", "tournament/brawlhalla-world-championship-expo-2022/event/1v1"),
                      [(a.alias, a.event_id) for a in cur.event_aliases])
        self.assertIn(("winters", "winter championship"), [(t.term, t.means) for t in cur.event_terms])

    def test_overrides_phases_aliases_and_merges_load(self):
        self.write("events.csv", "series/finals,crew_battle,,,,", "e2v2,,2v2,,,filed as 1v1",
                   "swiss,,,league,1,", "top8,,,league,2,", 'checked,,,,,"detection checked, no override"')
        self.write("event_aliases.csv", "BCX  2022!,e1,", "bcx 2022,e2,")
        self.write("event_terms.csv", "LTC,Low Tier City,", "winters,winter championship,",
                   "winters,Winter Doubles Championship,2024")
        self.write("player_aliases.csv", "Flower's,169119,")
        self.write("player_merges.csv", "1,2,a", "-5,2,a platform-only record")
        cur = self.load()
        self.assertEqual([(t.term, t.means, t.note) for t in cur.event_terms],
                         [("ltc", "low tier city", None), ("winters", "winter championship", None),
                          ("winters", "winter doubles championship", "2024")])
        self.assertEqual([(o.event_id, o.format_override, o.mode_override, o.competition_id, o.phase_order)
                          for o in cur.events],
                         [("series/finals", "crew_battle", None, None, None), ("e2v2", None, "2v2", None, None),
                          ("swiss", None, None, "league", 1), ("top8", None, None, "league", 2),
                          ("checked", None, None, None, None)])
        self.assertEqual([(a.alias, a.event_id) for a in cur.event_aliases], [("bcx 2022", "e1"), ("bcx 2022", "e2")])
        self.assertEqual([(a.alias, a.player_id) for a in cur.player_aliases], [("flowers", 169119)])
        self.assertEqual([(m.player_id, m.canonical_player_id, m.source) for m in cur.merges],
                         [(1, 2, "curated"), (-5, 2, "curated")])

    def test_every_problem_is_listed_by_file_and_line(self):
        self.write("format_rules.csv", "%Crew Battle%,crew_battle,1,", "%x%,x,first,")
        self.write("events.csv", "e1,crewbattle,,,,", "e2,,3v3,,,", "e3,,,solo,1,", "e4,,,,2,", "e1,,,,,",
                   "e5,,,,,a note, unquoted")
        self.write("player_aliases.csv", "pier,antireplay,")
        self.write("event_terms.csv", "Worlds,worlds,", "ltc,low tier city,", "LTC,low-tier city,", ",midseason,")
        found = "\n".join(self.problems())
        for expected in ("format_rules.csv:2: patterns match a lowercase name", "format_rules.csv:3: priority isn't",
                         "events.csv:2: unknown format 'crewbattle'", "events.csv:3: mode_override must be 1v1 or 2v2",
                         "events.csv:4: competition 'solo' has only one phase",
                         "events.csv:5: a phase needs both competition_id and phase_order",
                         "events.csv:6: e1 is listed twice", "events.csv:7: more fields than columns",
                         "player_aliases.csv:2: player_id isn't a player ID",
                         "event_terms.csv:2: 'worlds' means itself",
                         "event_terms.csv:4: 'ltc' for 'low tier city' is listed twice",
                         "event_terms.csv:5: needs a term and what it means"):
            self.assertIn(expected, found)

    def test_a_misspelled_column_or_a_missing_file_is_a_problem(self):
        self.write("events.csv", header="event_id,format_overide,note\n")
        (self.dir / "merge_rejections.csv").unlink()
        found = self.problems()
        self.assertIn("events.csv: unknown column(s) format_overide", found)
        self.assertIn("merge_rejections.csv: missing", found)

    def test_merges_that_contradict_themselves_or_a_rejection(self):
        self.write("player_merges.csv", "1,1,", "2,3,", "2,4,", "5,6,", "6,5,", "7,8,", "8,9,")
        self.write("merge_rejections.csv", "7,9,two people")
        found = "\n".join(self.problems())
        self.assertIn("player_merges.csv:2: a record can't be merged into itself", found)
        self.assertIn("player_merges.csv:4: 2 is already merged into 3", found)
        self.assertIn("player_merges.csv:6: merging 6 into 5 makes a loop", found)
        self.assertIn("player_merges.csv:8: 7 and 9 would be one person", found)  # through the chain 7 -> 8 -> 9

    def test_automatic_merges_yield_to_curated_rows(self):
        self.write("player_merges.csv", "1,2,by hand")
        self.write("merge_rejections.csv", "5,6,two people")
        (self.dir / "auto_merges.csv").write_text(
            "player_id,canonical_player_id,note\n1,3,\n5,6,\n7,8,auto: tier 1\n8,7,\n", encoding="utf-8")
        cur = self.load()
        self.assertEqual([(m.player_id, m.canonical_player_id, m.source) for m in cur.merges],
                         [(1, 2, "curated"), (7, 8, "auto")])
        reasons = {m.player_id: reason for m, reason in cur.dropped_auto}
        self.assertIn("already has a curated merge", reasons[1])
        self.assertIn("merge_rejections.csv says they aren't", reasons[5])
        self.assertIn("makes a loop", reasons[8])


if __name__ == "__main__":
    unittest.main()
