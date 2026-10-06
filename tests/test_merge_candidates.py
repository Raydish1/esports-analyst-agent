import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import merge_candidates as mc  # noqa: E402

YEAR = 365 * 86400


def person(pid, name, sgg=None, cm=None, region=None, years=(), best=None):
    p = mc.Person({"playerId": pid, "name": name, "sggPlayerId": sgg, "cmPlayerId": cm})
    for i, year in enumerate(years):
        p.add(f"e{pid}-{i}", (year - 1970) * YEAR, best)
    p.region = region
    return p


class RegionsTest(unittest.TestCase):
    def test_event_region_reads_event_names(self):
        self.assertEqual(mc.event_region("Autumn Championship - North America 2026 - 1v1"), "NA")
        self.assertEqual(mc.event_region("Brawlhalla Spring Championship 2018 (EU) Brawlhalla Singles"), "EU")
        self.assertEqual(mc.event_region("South America - Mammoth Cup"), "SA")
        self.assertEqual(mc.event_region("Southeast Asia Winter Championship"), "SEA")
        self.assertEqual(mc.event_region("Winter Championship - Middle East 2026 - 2v2"), "MENA")
        self.assertIsNone(mc.event_region("DreamHack Atlanta 2018 Brawlhalla 1v1"))


class TierTest(unittest.TestCase):
    def tier(self, a, b, *others):
        return (mc.pair_tier(a, b, [a, b, *others]) or (None,))[0]

    def test_a_platform_switch_duplicate_is_tier_1(self):
        old, new = person(1, "Yeezy", sgg=11, region="NA", years=(2021, 2024)), person(2, "yeezy.", cm="c2", region="NA", years=(2025, 2026))
        self.assertEqual(self.tier(old, new), 1)

    def test_one_missing_piece_of_evidence_is_tier_2(self):
        old, new = person(1, "Dark", sgg=11, years=(2021,)), person(2, "dark", cm="c2", region="SEA", years=(2026,))
        self.assertEqual(self.tier(old, new), 2)  # region unknown
        other = person(3, "Dark", sgg=13, region="EU", years=(2019,))
        old.region = "SEA"
        self.assertEqual(self.tier(old, new, other), 2)  # two start.gg records of the name

    def test_weaker_cross_platform_pairs_are_tier_3(self):
        old, new = person(1, "Penguin", sgg=11, region="EU", years=(2021,)), person(2, "Penguin.", cm="c2", region="SEA", years=(2026,))
        self.assertEqual(self.tier(old, new), 3)  # different regions
        linked = person(3, "penguin", sgg=13, cm="c3", region="EU", years=(2022, 2026))
        new.region = "EU"
        self.assertEqual(self.tier(old, new, linked), 3)  # a record of the name already links both platforms

    def test_records_active_at_the_same_time_are_not_candidates(self):
        a, b = person(1, "Ace", sgg=11, region="NA", years=(2020, 2023)), person(2, "Ace", cm="c2", region="NA", years=(2022, 2026))
        self.assertIsNone(self.tier(a, b))

    def test_same_platform_pairs_need_a_lone_name_some_history_and_no_region_conflict(self):
        remmy_old = person(59549, "Remmy", sgg=1, years=(2017, 2017))
        remmy = person(79652, "Remmy", sgg=2, region="NA", years=(2018, 2019, 2020))
        self.assertEqual(self.tier(remmy_old, remmy), 3)
        self.assertIsNone(self.tier(person(1, "Kai", sgg=1, years=(2017,)), person(2, "Kai", sgg=2, years=(2019,))))
        third = person(3, "Remmy", sgg=3, years=(2015,))
        self.assertIsNone(self.tier(remmy_old, remmy, third))


class CandidatesTest(unittest.TestCase):
    def people(self, *ps):
        return {p.id: p for p in ps}

    def test_the_record_with_more_history_stays(self):
        old = person(1, "Yeezy", sgg=11, region="NA", years=(2021, 2022, 2023))
        new = person(2, "yeezy.", cm="c2", region="NA", years=(2025,))
        [(tier, _, keep, other)] = mc.candidates(self.people(old, new), {}, set())
        self.assertEqual((tier, keep.id, other.id), (1, 1, 2))

    def test_decided_pairs_are_skipped_and_merged_records_go_to_review(self):
        old = person(1, "Yeezy", sgg=11, region="NA", years=(2021,))
        new = person(2, "yeezy.", cm="c2", region="NA", years=(2025,))
        self.assertEqual(mc.candidates(self.people(old, new), {}, {frozenset((1, 2))}), [])  # rejected
        self.assertEqual(mc.candidates(self.people(old, new), {2: 1, 1: 1}, set()), [])  # merged already
        [(tier, evidence, _, _)] = mc.candidates(self.people(old, new), {1: 9, 9: 9}, set())  # 1 is merged elsewhere
        self.assertEqual(tier, 2)
        self.assertIn("already in player_merges.csv", evidence)


if __name__ == "__main__":
    unittest.main()
