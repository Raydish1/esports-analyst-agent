import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))  # for the other tests' fixtures, however this module is run
import react  # noqa: E402
import templates  # noqa: E402
from test_agent import Scripted, reply  # noqa: E402
from test_views import A, A2, B, C, D, E, F, populate  # noqa: E402


class Fixture(unittest.TestCase):
    """The view tests' database in a file, as the tools open one, with a tie added: F shares 3rd place with C at the
    Cup. Its events: Cup (1v1) and Duos (2v2), which the alias 'cup 2020' names together; League, in two phases;
    Crew Battle 3v3; Kung Foot, a side format; Dreamland, cancelled; League Week 1, with unreliable placements."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "db.sqlite"
        db = sqlite3.connect(cls.path)
        populate(db)
        db.execute("INSERT INTO placements VALUES ('e1', ?, 3, NULL, 'startgg', 't')", (F,))
        db.commit()
        db.close()
        cls.tools = react.Tools(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def call(self, name, **arguments):
        return self.tools.call(name, arguments)

    def rows(self, out, what):
        """The rows of the table whose description starts with `what`."""
        return next(t for t in out["tables"] if t["what"].startswith(what))["rows"]


class RegistryTest(Fixture):
    def test_every_template_is_offered_to_the_model_and_called_by_name(self):
        offered = {t["function"]["name"]: t["function"] for t in react.TOOLS}
        for name, template in templates.TEMPLATES.items():
            self.assertEqual(offered[name]["description"], template.description)
            self.assertEqual(set(offered[name]["parameters"]["required"]), set(template.required))
        self.assertEqual(self.call("event_results", event="cup 2020")["template"], "event_results")
        unknown = self.call("nothing")["error"]
        self.assertTrue(unknown.startswith("there is no tool named 'nothing': the tools are resolve_player,"))
        for name in templates.TEMPLATES:
            self.assertIn(name, unknown)

    def test_arguments_a_template_cant_use_get_errors_the_model_can_act_on(self):
        self.assertEqual(self.call("event_results")["error"], "event_results needs event: event_results takes event, top")
        self.assertIn("has no argument 'mode'", self.call("event_results", event="cup 2020", mode="1v1")["error"])
        self.assertIn("top is a whole number, 1 or more", self.call("event_results", event="cup 2020", top=0)["error"])
        self.assertIn("top is a whole number", self.call("event_results", event="cup 2020", top="eight")["error"])
        self.assertEqual(len(self.rows(self.call("event_results", event="cup 2020", top="2"), "each event's top 2")), 4)

    def test_a_template_keeps_the_sql_it_ran_with_the_ids_written_in(self):
        ran = self.call("event_results", event="cup 2020")["ran"]
        self.assertEqual(len(ran), 2)
        self.assertIn("FROM v_results r JOIN players p ON p.player_id = r.player_id WHERE r.event_id IN ('e1', 'e2')"
                      " AND r.placement <= 1", ran[1])

    def test_a_list_over_the_token_budget_is_left_out_with_its_count_and_the_rest_stays(self):
        with patch.object(templates, "TOKEN_BUDGET", 120):
            out = self.call("event_results", event="cup 2020", top=3)
        listed, placements = out["tables"]
        self.assertEqual(len(listed["rows"]), 2)
        self.assertEqual((placements["row_count"], placements["complete"], "rows" in placements), (6, False, False))
        self.assertTrue(placements["note"].startswith("6 rows, too many to show with the rest"))

    def test_the_loop_traces_the_sql_and_shows_the_model_the_result_without_it(self):
        ask = Scripted(reply(calls=[("event_results", {"event": "cup 2020"})]), reply("A won the Cup."))
        trace = react.run("Who won the cup in 2020?", self.tools, ask=ask, log=lambda *_: None)
        call = trace["steps"][0]["tool_calls"][0]
        self.assertEqual(len(call["ran"]), 2)
        self.assertNotIn("ran", json.loads(call["observation"]))
        self.assertNotIn("ran", json.loads(ask.sent[1][-1]["content"]))
        self.assertIn("**The SQL it ran**", react.markdown([{**trace, "number": None, "seed": 0}], {
            "run": "r", "model": "m", "variant": "v", "think": True, "seeds": [0], "snapshot": {"file": "f"},
            "max_steps": 8, "ollama": "0"}))
        self.assertEqual(react.preview(call["observation"]),
                         "the events the name means: 2 rows; each event's winners, a team's players together: 2 rows")

    def test_the_answer_check_counts_the_players_a_template_returned_a_teams_included(self):
        shown = react.Shown(self.tools.resolver)
        out = self.call("event_results", event="cup 2020")
        del out["ran"]
        shown.observe("event_results", out)
        self.assertEqual(shown.players, {A, B})

    def test_player_ids_no_tool_returned_are_refused_until_a_template_returns_them(self):
        h2h = ("head_to_head", {"player_id": A, "opponent_id": B})
        ask = Scripted(reply(calls=[h2h]), reply(calls=[("event_results", {"event": "cup 2020"})]), reply(calls=[h2h]),
                       reply("A leads B 3-0."))
        trace = react.run("How has A done against B?", self.tools, ask=ask, log=lambda *_: None)
        refused, _, ran = (s["tool_calls"][0] for s in trace["steps"][:3])
        self.assertTrue(json.loads(refused["observation"])["error"].startswith(
            f"player_ids {A} and {B} weren't returned by any tool in this conversation"))
        self.assertNotIn("ran", refused)  # nothing was queried
        self.assertEqual(json.loads(ran["observation"])["template"], "head_to_head")  # the Cup's winners were A and B

    def test_a_template_call_is_a_new_query_after_a_result_too_large_to_show(self):
        many = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 3000) SELECT x, 'a name' FROM c"
        ask = Scripted(reply(calls=[("run_sql", {"query": many})]), reply(calls=[("event_results", {"event": "cup 2020"})]),
                       reply("A won the Cup."))
        trace = react.run("Who won the cup in 2020?", self.tools, ask=ask, log=lambda *_: None)
        self.assertEqual((trace["outcome"], trace["steps_used"]), ("answered", 3))
        self.assertFalse(any(s.get("size_check") for s in trace["steps"]))


class EventResultsTest(Fixture):
    def test_winners_come_with_a_teams_players_together_and_names_next_to_ids(self):
        out = self.call("event_results", event="cup 2020")
        self.assertEqual((out["scope"], out["event"]), ("official events", {
            "name": "cup 2020", "status": "confident", "matched": "alias 'cup 2020'"}))
        self.assertEqual(self.rows(out, "the events"), [["Cup", "e1", "1970-01-01", "1v1", None, None],
                                                        ["Duos", "e2", "1970-01-01", "2v2", None, None]])
        self.assertEqual(self.rows(out, "each event's winners"), [["Cup", "1970-01-01", "1v1", 1, "A", [A]],
                                                                  ["Duos", "1970-01-01", "2v2", 1, "A / B", [A, B]]])

    def test_each_event_comes_with_its_event_id_for_a_query_of_its_sets(self):
        events = next(t for t in self.call("event_results", event="cup 2020")["tables"]
                      if t["what"] == "the events the name means")
        self.assertEqual((events["columns"][:2], [row[:2] for row in events["rows"]]),
                         (["event", "event_id"], [["Cup", "e1"], ["Duos", "e2"]]))
        final = self.call("run_sql", query="SELECT winner_name, loser_name FROM v_sets_1v1 WHERE event_id ="
                                           f" '{events['rows'][0][1]}' AND winner_placement = 1 AND loser_placement = 2")
        self.assertEqual({tuple(row) for row in final["rows"]}, {("A", "B")})  # the Cup's final, found by its ID
        with patch.object(templates, "IDS_IN_SQL", 1):  # more events than resolve_event gives IDs for, as a series
            many = self.call("event_results", event="cup 2020")
        self.assertNotIn("event_id", many["tables"][0]["columns"])
        self.assertIn("For SQL on these 2 events, use resolve_event's sql condition for 'cup 2020': their IDs are too"
                      " many to list.", many["notes"])

    def test_a_cutoff_never_splits_a_tie(self):
        out = self.call("event_results", event="cup 2020", top=3)
        cup = [row[3:] for row in self.rows(out, "each event's top 3") if row[0] == "Cup"]
        self.assertEqual(cup, [[1, "A", [A]], [2, "B", [B]], [3, "C", [C]], [3, "F", [F]]])
        self.assertIn("Rows on the same placement in one event are tied there: give them the same place.", out["notes"])
        self.assertNotIn("tied", " ".join(self.call("event_results", event="cup 2020", top=2)["notes"]))

    def test_an_event_that_wasnt_held_or_has_unreliable_placements_says_so_first_and_has_no_winner(self):
        out = self.call("event_results", event="dreamland")
        self.assertTrue(out["notes"][0].startswith("Dreamland (1970-01-01) was not held, so it has no results"))
        self.assertEqual((self.rows(out, "the events")[0][4], self.rows(out, "each event's winners")), ("cancelled", []))
        out = self.call("event_results", event="league week 1")
        self.assertIn("has unreliable placements, so they aren't results and it has no reliable winner", out["notes"][0])
        self.assertEqual((self.rows(out, "the events")[0][4], self.rows(out, "each event's winners")),
                         ("placements_unreliable", []))  # C and D both "won" it: neither is listed

    def test_a_crew_is_one_row_and_a_side_format_has_no_results(self):
        out = self.call("event_results", event="crew battle")
        self.assertEqual(self.rows(out, "each event's winners"),
                         [["Crew Battle 3v3", "1970-01-01", "1v1 (crew battle)", 1, "A / B / C", [A, B, C]]])
        self.assertIn("A crew battle's placement is the crew's: a team result, which counts as 1v1.", out["notes"])
        out = self.call("event_results", event="kung foot")
        self.assertEqual(self.rows(out, "the events")[0][3], "kung foot (neither 1v1 nor 2v2)")
        self.assertEqual(self.rows(out, "each event's winners"), [])
        self.assertIn("counts as neither 1v1 nor 2v2, so its placements aren't results here", out["notes"][0])

    def test_a_name_matching_several_tournaments_gets_each_one_labelled_the_closest_first(self):
        out = self.call("event_results", event="league")
        self.assertEqual(out["event"]["status"], "ambiguous")
        self.assertTrue(out["notes"][0].startswith("'league' matches 2 tournaments, the closest name first. Say which"))
        self.assertEqual([row[0] for row in self.rows(out, "the events")][-1], "League Week 1")
        self.assertEqual(self.rows(out, "each event's winners"), [["League", "1970-01-01", "1v1", 1, "C", [C]]])
        phases = next(note for note in out["notes"] if "phases of one competition" in note)
        self.assertIn("each player's result counts once, at the last phase they reached", phases)
        self.assertFalse(any("has no placements" in note for note in out["notes"]))  # the Swiss phase isn't missing any

    def test_a_name_no_event_has_or_only_partly_gets_no_results(self):
        out = self.call("event_results", event="zzz 2031")
        self.assertEqual((out["event"], out["tables"]), ({"name": "zzz 2031", "status": "not_found"}, []))
        self.assertIn("No official event matches this name", out["notes"][0])
        out = self.call("event_results", event="dreamland finals")
        self.assertTrue(out["notes"][0].startswith("No event has all the words of 'dreamland finals'"))
        self.assertEqual([t["what"] for t in out["tables"]], ["the closest events"])
        self.assertEqual(out["ran"], [])  # nothing was queried
        with patch.object(templates, "EVENTS_AT_MOST", 1):
            out = self.call("event_results", event="cup 2020")
        self.assertIn("matches 2 events, too many to answer for", out["notes"][0])
        self.assertIn("event is the event's name", self.call("event_results", event=7)["error"])


class WindowTest(Fixture):
    def test_since_and_until_read_a_day_a_month_or_a_year_each_included(self):
        self.assertEqual([templates.day(v, "since") for v in ("2025-10-01", "2025-10", "2025", 2025)],
                         ["2025-10-01", "2025-10-01", "2025-01-01", "2025-01-01"])
        self.assertEqual([templates.day(v, "until", last=True) for v in ("2024-02", "2024", "2024-12-31")],
                         ["2024-02-29", "2024-12-31", "2024-12-31"])
        for bad in ("last year", "2025-13", "10/01/2025", True):
            with self.assertRaises(templates.Refused):
                templates.day(bad, "since")
        self.assertIn("since (1971-01-01) is after until (1970-12-31)",
                      self.call("player_results", player_id=A, since="1971", until="1970")["error"])

    def test_a_window_narrows_every_template_that_takes_a_year_and_the_scope_says_so(self):
        every = self.call("player_results", player_id=A, since="1970-01-01")  # the fixture's events are all 1970-01-01
        self.assertEqual((every["scope"], self.rows(every, "A's results")[-1][2]),
                         ("official events, 1v1 and 2v2, since 1970-01-01", 5))
        none = self.call("player_results", player_id=A, since="1971")
        self.assertEqual(self.rows(none, "A's results")[-1][2], 0)
        self.assertIn("None of A's 5 official results (3 in 1v1, 2 in 2v2) is among these", " ".join(none["notes"]))
        ranked = self.call("rank_players", by="wins", until="1969")
        self.assertEqual((ranked["scope"], ranked["tables"][0]["rows"]), ("official events, 1v1 and 2v2, until 1969-12-31", []))
        teams = self.call("team_results", player_id=A, since="1970", until="1970")
        self.assertEqual(teams["scope"], "official events, 2v2, from 1970-01-01 to 1970-12-31")

    def test_a_head_to_head_in_a_window_counts_the_sets_in_it(self):
        every = self.call("head_to_head", player_id=A, opponent_id=B)
        within = self.call("head_to_head", player_id=A, opponent_id=B, year=1970)
        self.assertEqual(self.rows(within, "A's 1v1 record")[0][4:7], self.rows(every, "A's 1v1 record")[0][4:7])
        self.assertEqual(within["scope"], f"{templates.SETS_SCOPE}, in 1970")
        later = self.call("head_to_head", player_id=A, opponent_id=B, since="1971")
        self.assertEqual(self.rows(later, "A's 1v1 record")[0][4:7], [0, 0, 0])
        self.assertIn("A and B have no counted 1v1 sets against each other at official events since 1971-01-01",
                      " ".join(later["notes"]))


class RegionTest(Fixture):
    def test_a_region_is_its_code_or_a_name_for_it_and_its_events_are_those_whose_names_name_it(self):
        events = self.tools.events
        events.events["e-na"] = {**events.events["e1"], "name": "Winter Championship - North America", "words":
                                 "winter championship north america".split()}
        events.events["e-us"] = {**events.events["e1"], "name": "US Open", "words": ["us", "open"]}
        events.terms["na"] = ["north america", "us"]
        try:
            for name in ("na", "NA", "north america", "North American"):
                self.assertEqual(events.region(name), ("na", {"e-na", "e-us"}), name)
            self.assertEqual(events.region("oce"), ("aus", set()))
            self.assertIsNone(events.region("mars"))
        finally:
            del events.events["e-na"], events.events["e-us"]

    def test_a_region_narrows_the_results_and_its_note_says_global_events_are_in_none(self):
        out = self.call("player_results", player_id=A, region="eu")  # the fixture's events name no region
        self.assertEqual((out["scope"], self.rows(out, "A's results")[-1][2]), ("official events, 1v1 and 2v2, at"
                                                                                " Europe's events", 0))
        self.assertIn("region counts the 0 events whose names name Europe: global events, such as Worlds and the BCX"
                      " finals, are in no region. Say so.", out["notes"])
        self.assertIn("region is one of na, eu, sa, brz, sea, aus, mena, jpn",
                      self.call("rank_players", by="wins", region="mars")["error"])
        self.assertEqual(self.call("rank_players", by="wins", region="all")["scope"], "official events, 1v1 and 2v2")


class RankPairsTest(Fixture):
    def test_opponents_are_ranked_by_the_sets_between_them_each_pair_once_with_each_ones_wins(self):
        out = self.call("rank_pairs")  # finding 28: the biggest head-to-head, which only hand-written SQL answered
        self.assertEqual(self.rows(out, "pairs of opponents, the most sets first"), [
            [1, "A", A, "B", B, 3, 3, 0], [2, "A", A, "C", C, 1, 0, 1], [2, "A", A, "D", D, 1, 1, 0],
            [2, "B", B, "C", C, 1, 1, 0], [2, "C", C, "D", D, 1, 1, 0]])
        self.assertIn("Pairs on the same rank are tied: give them the same place.", out["notes"])
        mine = self.call("rank_pairs", of="rivals", player_id=A, top=1)  # live: megD's most-played opponent
        self.assertEqual(self.rows(mine, "A's opponents"), [[1, "A", A, "B", B, 3, 3, 0]])
        met = self.call("rank_pairs", player_id=A, mode="2v2")
        self.assertEqual(self.rows(met, "A's opponents, the most meetings first"),
                         [[1, "A", A, "C", C, 1, 1, 0], [1, "A", A, "D", D, 1, 1, 0]])

    def test_teammates_are_ranked_by_their_results_together(self):
        out = self.call("rank_pairs", of="partners")
        self.assertEqual(self.rows(out, "pairs of teammates, the most events together first"),
                         [[1, "A", A, "B", B, 2, 1, 2, 2], [2, "C", C, "D", D, 1, 0, 1, 1]])
        self.assertEqual(self.rows(self.call("rank_pairs", of="teammates", by="wins", top=1), "pairs of teammates"),
                         [[1, "A", A, "B", B, 2, 1, 2, 2]])

    def test_what_it_cant_rank_is_refused_with_the_reason(self):
        self.assertIn("2v2 opponents are ranked for one player only", self.call("rank_pairs", mode="2v2")["error"])
        self.assertIn("of is 'opponents' or 'teammates'", self.call("rank_pairs", of="enemies")["error"])
        self.assertIn("teammates play 2v2 together", self.call("rank_pairs", of="teammates", mode="1v1")["error"])
        self.assertIn("opponents are ranked by the sets", self.call("rank_pairs", by="medals")["error"])
        self.assertIn("give player_id", self.call("rank_pairs", by="record")["error"])

    def test_the_opponents_side_ranks_the_other_players_records_against_the_player(self):
        out = self.call("rank_pairs", player_id=B, side="opponents", by="record")  # live: q08 and q40 asked B's side
        rows = self.rows(out, "records against B")
        self.assertEqual(out["tables"][0]["columns"], ["rank", "player", "player_id", "sets", "wins_vs_B", "losses_vs_B"])
        self.assertEqual(rows[0][1:6], ["A", A, 3, 3, 0])  # A beat B in 3 of 3: from A's side, B's column gone
        self.assertIn("each row is another player's record against B, from that player's side: wins_vs_B are their"
                      " wins against B (B's losses to them)", " ".join(out["notes"]))
        rate = self.call("rank_pairs", player_id=B, side="opponents", by="rate")  # the counting rule: 5 sets at least
        self.assertEqual(rate["tables"], [])
        self.assertIn("with at least 5 sets or meetings between them, the minimum, so the ranking is empty.",
                      rate["notes"][-2])
        self.assertEqual(rate["notes"][-1], "The most sets here is 3 (B with A): if the question sets no minimum, call"
                                            " again without min_sets.")
        self.assertEqual(self.rows(self.call("rank_pairs", player_id=B, side="opponents", by="rate", min_sets=1),
                                   "records against B")[0][-1], 1.0)
        self.assertIn("side is 'player'", self.call("rank_pairs", player_id=B, side="enemies", by="record")["error"])

    def test_one_players_opponents_by_record_the_most_wins_then_the_fewest_losses(self):
        out = self.call("rank_pairs", player_id=A, by="record")  # live, finding 34: "best record" as most sets
        self.assertEqual([r[3] for r in self.rows(out, "A's records against opponents")], ["B", "D", "C"])
        self.assertIn("with no minimum of sets: say how the answer reads 'best record', and the minimum.",
                      " ".join(out["notes"]))
        least = self.call("rank_pairs", player_id=A, by="record", min_sets=2)
        self.assertEqual([r[3] for r in self.rows(least, "A's records")], ["B"])

    def test_a_players_own_records_by_rate_take_no_minimum_the_question_doesnt_set(self):
        out = self.call("rank_pairs", player_id=A, by="rate")  # live, c19: volst's best records came back empty
        self.assertEqual([(r[3], r[-1]) for r in self.rows(out, "A's records")], [("B", 1.0), ("D", 1.0), ("C", 0.0)])
        self.assertIn("with no minimum of sets", " ".join(out["notes"]))  # B's 3-0 before D's 1-0: a tie, more sets
        empty = self.call("rank_pairs", player_id=A, by="rate", min_sets=4)
        self.assertEqual(empty["notes"][-1], "The most sets here is 3 (A with B): if the question sets no minimum, call"
                                             " again without min_sets.")


class PowerRankingsTest(Fixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        db = sqlite3.connect(cls.path)
        db.executemany("INSERT INTO pr_snapshots VALUES (?, ?, '2026-10-02', ?, ?, ?, 5, 9, 2, 1, 0, 'stats_api')",
                       [(A, "1v1", "NA", 1, 500.0), (B, "1v1", "NA", 2, 400.0), (C, "1v1", "EU", 1, 450.0),
                        (A, "2v2", "NA", 3, 300.0)])
        db.commit()
        db.close()

    def test_a_regions_top_or_every_regions_and_a_players_rankings(self):
        out = self.call("power_rankings", region="north america", top=1)
        self.assertEqual(self.rows(out, "the 1v1 Power Rankings of NA"),
                         [["NA", "1v1", 1, "A", A, 500.0, 2, 1, 0, 5, 9]])
        self.assertEqual(out["scope"], "official Power Rankings as of 2026-10-02")
        self.assertIn("not this data's counts of official results", out["notes"][-1])
        each = self.call("power_rankings", top=1)
        self.assertEqual([r[:4] for r in self.rows(each, "the 1v1 Power Rankings, each region")],
                         [["EU", "1v1", 1, "C"], ["NA", "1v1", 1, "A"]])
        mine = self.call("power_rankings", player_id=A)
        self.assertEqual([r[:3] for r in self.rows(mine, "A's Power Rankings")], [["NA", "1v1", 1], ["NA", "2v2", 3]])
        self.assertIn("D isn't in the Power Rankings of 2026-10-02.", self.call("power_rankings", player_id=D)["notes"])

    def test_a_region_the_rankings_dont_have_is_refused(self):
        self.assertIn("the Power Rankings' regions are NA, EU, SA (Brazil's too), SEA and MENA",
                      self.call("power_rankings", region="oce")["error"])


class UpsetsTest(Fixture):
    """Seeds at every event with a set: A the lowest seed (4), then D (3), C (2), and B the top seed (1)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        db = sqlite3.connect(cls.path)
        events = [e for (e,) in db.execute("SELECT DISTINCT event_id FROM matches")]
        db.executemany("INSERT OR IGNORE INTO standings VALUES (?, ?, ?, ?, NULL, NULL, NULL, 9, NULL, ?, 0, 'startgg', 't')",
                       [(e, f"{e}-{pid}", str(pid), pid, seed) for e in events for pid, seed in ((A, 4), (B, 1), (C, 2), (D, 3))])
        db.commit()
        db.close()

    def test_sets_the_lower_seed_won_the_biggest_difference_first_ties_whole(self):
        out = self.call("upsets", top=1)  # the user's definition, 2026-11-21
        rows = self.rows(out, "upsets, the biggest seed difference first")
        self.assertEqual({(r[0], r[3], r[5], r[6], r[8], r[9]) for r in rows}, {(1, "A", 4, "B", 1, 3)})
        self.assertEqual(len(rows), 3)  # A beat B in three sets, all tied at a difference of 3
        self.assertIn("An upset is a set the lower seed won: the higher initial seed number at that event", out["notes"][-2])
        mine = self.call("upsets", player_id=C)  # C, seed 2, beat A (4) and D (3): no upsets
        self.assertEqual(mine["tables"], [])
        self.assertIn("2v2 upsets need an event or a player_id", self.call("upsets", mode="2v2")["error"])


class PlayerSetsTest(Fixture):
    def test_one_players_sets_from_their_side_and_the_losses_alone(self):
        out = self.call("player_sets", player_id=A)  # audit a39: whom a player lost to at an event had no tool
        self.assertEqual(self.rows(out, "A's 1v1 sets here"), [["A", 5, 4, 1]])  # 3 over B, 1 over D, 1 lost to C
        lost = self.call("player_sets", player_id=A, result="lost")
        self.assertEqual([r[2:5] for r in self.rows(lost, "A's sets lost")], [["C", C, "lost"]])
        self.assertIn("Each set is from A's side", lost["notes"][-1])
        self.assertIn("result is 'won' or 'lost'", self.call("player_sets", player_id=A, result="draws")["error"])


class DominantWinsTest(Fixture):
    def test_wins_by_the_dominance_rule_and_the_flawless_ones(self):
        rows = self.rows(self.call("dominant_wins", top=10), "official wins, the most dominant first")  # audit a35
        scored, unscored = [r for r in rows if r[10] == 0], [r for r in rows if r[10] > 0]
        self.assertEqual(rows, scored + unscored)  # a run with an unscored set after every fully scored one
        self.assertEqual([r[9] for r in scored], sorted(r[9] for r in scored))  # the fewest games lost first
        flawless = self.call("dominant_wins", flawless=True)
        self.assertTrue(all(r[9] == 0 and r[10] == 0 for t in flawless["tables"] for r in t.get("rows", [])))
        self.assertIn("without a dropped game", " ".join(flawless["notes"]))

    def test_the_runs_are_v_win_runs_ranked_by_the_rule(self):  # counted in two queries: the view took over 30 s
        db = sqlite3.connect(self.path)
        expected = db.execute(
            "SELECT RANK() OVER (ORDER BY sets_played = 0, unscored_sets > 0, games_lost, sets_dropped, games_won DESC),"
            " player_id, start_date, mode, sets_played, sets_dropped, games_won, games_lost, unscored_sets FROM v_win_runs"
            " WHERE is_crew_battle = 0").fetchall()
        db.close()
        rows = self.rows(self.call("dominant_wins", top=99), "official wins, the most dominant first")
        self.assertEqual(sorted([r[0], r[2], *r[4:]] for r in rows), sorted(list(e) for e in expected))


class PlayerResultsTest(Fixture):
    def test_results_are_counted_by_mode_with_the_first_the_latest_and_the_list(self):
        out = self.call("player_results", player_id=A)
        self.assertEqual((out["player"], out["scope"]), ({"player_id": A, "name": "A"}, "official events, 1v1 and 2v2"))
        self.assertEqual(self.rows(out, "A's results, counted by mode"), [  # medals counted, not left to add up
            ["A", "1v1", 3, 2, 1, 0, 3, 3, 1], ["A", "2v2", 2, 1, 0, 1, 2, 2, 1], ["A", "1v1 and 2v2", 5, 3, 1, 1, 5, 5, 1]])
        self.assertEqual(self.rows(out, "the first and the latest"), [
            ["first", "1v1", "1970-01-01", "Cup", 1], ["latest", "1v1", "1970-01-01", "Crew Battle 3v3", 1],
            ["first", "2v2", "1970-01-01", "Duos", 1], ["latest", "2v2", "1970-01-01", "Duos 2", 3]])
        self.assertEqual(self.rows(out, "each of them, oldest first"), [
            ["1970-01-01", "Cup", "1v1", 1], ["1970-01-01", "Duos", "2v2", 1], ["1970-01-01", "Duos 2", "2v2", 3],
            ["1970-01-01", "League", "1v1", 2], ["1970-01-01", "Crew Battle 3v3", "1v1 (crew battle)", 1]])
        self.assertEqual(out["notes"], ["1 of the 1v1 results is a crew battle: a team result, counted as 1v1."])
        self.assertEqual(len(out["ran"]), 3)
        self.assertIn(f"WHERE r.player_id = {A} GROUP BY r.mode", out["ran"][0])

    def test_the_whole_record_counts_each_placement_and_lists_where_the_best_was(self):
        out = self.call("player_results", player_id=A)  # live, placement counts made up from the list (finding 27)
        self.assertEqual(self.rows(out, "how many times each placement happened"),
                         [["1v1", 1, 2], ["1v1", 2, 1], ["2v2", 1, 1], ["2v2", 3, 1]])
        self.assertEqual(self.rows(out, "the results at the best placement"), [  # finding 26: the best, and where
            ["1v1", 1, "1970-01-01", "Crew Battle 3v3"], ["1v1", 1, "1970-01-01", "Cup"], ["2v2", 1, "1970-01-01", "Duos"]])
        with patch.object(templates, "BEST_LISTED", 1):
            capped = self.call("player_results", player_id=A)
        self.assertEqual(len(self.rows(capped, "the results at the best placement")), 2)
        self.assertIn("A placed 1st 2 times in 1v1: the latest 1 are listed at the best placement.", capped["notes"])
        narrowed = self.call("player_results", player_id=A, top=8)
        self.assertFalse(any(t["what"].startswith(("how many times", "the results at the best")) for t in narrowed["tables"]))

    def test_top_mode_year_and_event_narrow_the_results_and_the_scope_says_so(self):
        wins = self.call("player_results", player_id=A, top=1, mode="doubles")
        self.assertEqual((wins["scope"], self.rows(wins, "A's wins (1st places)")),
                         ("official events, 2v2", [["A", "2v2", 1]]))
        self.assertEqual(self.rows(wins, "the first and the latest"), [["only", "2v2", "1970-01-01", "Duos", 1]])
        year = self.call("player_results", player_id=A, year=1970)
        self.assertEqual((year["scope"], self.rows(year, "A's results")[-1][2]), ("official events, 1v1 and 2v2, in 1970", 5))
        cup = self.call("player_results", player_id=A, event="cup 2020")
        self.assertEqual((cup["scope"], cup["event"]["status"]),
                         ("official events, 1v1 and 2v2, at the 2 events the name means", "confident"))
        self.assertEqual([row[1] for row in self.rows(cup, "each of them")], ["Cup", "Duos"])

    def test_a_cutoff_leaves_out_the_counts_it_fixes(self):
        def summary(top):
            out = self.call("player_results", player_id=A, **({} if top is None else {"top": top}))
            return next(t for t in out["tables"] if t["what"].endswith("counted by mode"))
        every = ["first", "second", "third", "medals", "top8", "best"]  # the web app's cards read these by name
        for top, columns in ((1, ["player", "mode", "wins"]),  # live, a 0 under 'results' read as no 2v2 results
                             (2, ["player", "mode", "top2s", "first", "second", "best"]),
                             (3, ["player", "mode", "medals", "first", "second", "third", "best"]),
                             (8, ["player", "mode", "top8s", "first", "second", "third", "medals", "best"]),
                             (9, ["player", "mode", "top9s", *every]), (None, ["player", "mode", "results", *every])):
            self.assertEqual(summary(top)["columns"], columns, top)
        self.assertEqual(summary(3)["rows"], [["A", "1v1", 3, 2, 1, 0, 1], ["A", "2v2", 2, 1, 0, 1, 1],
                                              ["A", "1v1 and 2v2", 5, 3, 1, 1, 1]])

    def test_the_model_reads_that_a_cutoff_counts_only_its_results_and_a_ranking_takes_no_condition(self):
        self.assertTrue(templates.TEMPLATES["player_results"].description.endswith(
            "With top, it counts only those results, not the player's whole record."))
        self.assertTrue(templates.TEMPLATES["rank_players"].description.endswith("Any other condition: use run_sql."))
        self.assertIn("  - who has the most wins, medals or top 8s, or the most among players who never won (never_won):"
                      " rank_players\n", react.SYSTEM)

    def test_never_won_leaves_out_every_player_who_won(self):
        out = self.call("rank_players", by="top8s", never_won="any", top=10)  # audit kind 7: rank_players had no condition
        names = [r[1] for r in self.rows(out, "players ranked by top 8s")]
        winners = {r[1] for r in self.rows(self.call("rank_players", by="wins", top=10), "players ranked by wins")}
        self.assertFalse(set(names) & winners)
        self.assertIn("players who never won an official event", out["scope"])
        cup = self.call("rank_players", by="top8s", never_won="cup 2020", top=10)
        self.assertIn("players who never won at the events 'cup 2020' means", cup["scope"])

    def test_a_narrowed_count_says_how_many_results_the_player_has_in_all(self):
        top8 = self.call("player_results", player_id=A, top=8)  # live, volst's 25 2v2 results read as none
        self.assertIn("A has 5 official results in all (3 in 1v1, 2 in 2v2): the counts here are only the top 8s (placed"
                      " 8th or better).", top8["notes"])
        doubles = self.call("player_results", player_id=A, top=1, mode="2v2")
        self.assertIn("the counts here are only the wins (1st places) in 2v2.", doubles["notes"][-1])
        self.assertFalse(any("in all" in n for n in self.call("player_results", player_id=A)["notes"]))  # nothing left out

    def test_all_any_or_empty_asks_for_no_filter(self):
        out = self.call("player_results", player_id=A, event="all", mode="", top=8)  # live: volst's top 8 vanished
        self.assertEqual((out["scope"], "event" in out), ("official events, 1v1 and 2v2", False))
        self.assertEqual(self.rows(out, "A's top 8s")[-1][2], 5)
        self.assertEqual(self.call("player_results", player_id=A, mode="1v1 and 2v2", year="all")["scope"],
                         "official events, 1v1 and 2v2")

    def test_a_count_of_zero_says_what_it_is_zero_of(self):
        out = self.call("player_results", player_id=D, top=1)
        self.assertEqual(self.rows(out, "D's wins"), [["D", "1v1", 0], ["D", "2v2", 0], ["D", "1v1 and 2v2", 0]])
        self.assertEqual(out["notes"], ["None of D's 2 official results (1 in 1v1, 1 in 2v2) is among these: the count is"
                                        " 0, which isn't the same as never having played."])
        self.assertEqual(len(out["tables"]), 1)  # nothing first or latest, and no list
        self.assertEqual(self.call("player_results", player_id=E)["notes"],
                         ["E has no official 1v1 or 2v2 results in the data."])
        self.assertEqual(self.rows(self.call("player_results", player_id=A, year=2026), "A's results")[-1][2], 0)

    def test_an_event_name_must_be_one_tournament_and_its_status_comes_with_the_results(self):
        out = self.call("player_results", player_id=A, event="league")
        self.assertTrue(out["notes"][0].endswith("Call again with one tournament's name, as listed here."))
        self.assertEqual(([t["what"] for t in out["tables"]], out["ran"]), (["the closest events"], []))
        out = self.call("player_results", player_id=C, event="league week 1")
        self.assertIn("has unreliable placements", out["notes"][0])
        self.assertIn("the count is 0", out["notes"][1])  # C "won" it, but its placements aren't results

    def test_a_player_is_given_by_id_and_a_merged_record_is_the_person(self):
        out = self.call("player_results", player_id=A2)
        self.assertEqual(out["player"], {"player_id": A, "name": "A"})
        self.assertIn(f"player_id {A2} is another record of A (player_id {A}): these are the person's.", out["notes"])
        self.assertEqual(self.call("player_results", player_id=str(A))["player"]["player_id"], A)  # a number as text
        self.assertIn("not a name: call resolve_player with 'Raydish' first", self.call("player_results", player_id="Raydish")["error"])
        self.assertIn("no player has player_id 999", self.call("player_results", player_id=999)["error"])
        self.assertEqual(self.call("player_results", player_id=A, mode="standard")["error"], "mode is '1v1' or '2v2', not 'standard'")
        self.assertIn("top is a whole number, 1 or more", self.call("player_results", player_id=A, top=0)["error"])


class TeamResultsTest(Fixture):
    def test_2v2_is_its_one_mode(self):
        self.assertEqual(self.call("team_results", player_id=A, partner_id=B, mode="2v2"),
                         self.call("team_results", player_id=A, partner_id=B))
        self.assertIn("team_results counts 2v2 partners only: for two players' 1v1 record against each other use"
                      " head_to_head", self.call("team_results", player_id=A, mode="1v1")["error"])

    def test_two_partners_events_together_are_counted_with_each_event(self):
        out = self.call("team_results", player_id=A, partner_id=B)  # live, an OR counted 24 events as wins (4)
        self.assertEqual((out["player"], out["partner"], out["scope"]),
                         ({"player_id": A, "name": "A"}, {"player_id": B, "name": "B"}, "official events, 2v2"))
        self.assertEqual(self.rows(out, "A and B's 2v2 results together"), [["A", "B", 2, 1, 2, 2, 1]])
        self.assertEqual(self.rows(out, "each of them"), [["1970-01-01", "Duos", 1], ["1970-01-01", "Duos 2", 3]])
        self.assertEqual(self.rows(self.call("team_results", player_id=B, partner_id=A2), "B and A's"),
                         [["B", "A", 2, 1, 2, 2, 1]])  # A2 is a record of A
        none = self.call("team_results", player_id=A, partner_id=C)
        self.assertEqual((none["notes"], none["tables"]), (["A and C have no official 2v2 results together."], []))

    def test_without_a_partner_it_lists_every_partner_the_most_events_first(self):
        out = self.call("team_results", player_id=A)  # live, q06 counted joined rows: "Raydish (8,218 events)"
        self.assertEqual(self.rows(out, "A's 2v2 partners"), [["B", B, 2, 1, 2, 2, 1]])
        self.assertEqual(out["notes"], ["A has 2 official 2v2 results with 1 partner."])
        self.assertEqual(self.rows(self.call("team_results", player_id=C), "C's 2v2 partners"), [["D", D, 1, 0, 1, 1, 2]])
        self.assertEqual(self.call("team_results", player_id=E)["notes"], ["E has no official 2v2 results."])

    def test_a_partner_must_be_another_player_and_players_are_given_by_id(self):
        self.assertIn("player_id and partner_id are both A", self.call("team_results", player_id=A, partner_id=A2)["error"])
        self.assertIn("not a name: call resolve_player", self.call("team_results", player_id=A, partner_id="B")["error"])
        self.assertIn("team_results", [t["function"]["name"] for t in react.TOOLS])
        self.assertIn("  - two players as a team, or who a player has played with in 2v2: team_results\n", react.SYSTEM)
        self.assertIn("  - a player's stats, record, profile or card: player_results with no top, every count in one call\n",
                      react.SYSTEM)


class HeadToHeadTest(Fixture):
    def test_the_record_is_the_first_players_with_each_set_and_names_next_to_ids(self):
        out = self.call("head_to_head", player_id=A, opponent_id=B)
        self.assertEqual((out["player"], out["opponent"]), ({"player_id": A, "name": "A"}, {"player_id": B, "name": "B"}))
        self.assertEqual(self.rows(out, "A's 1v1 record against B"), [["A", A, "B", B, 3, 0, 3, 8, 1, 0]])
        self.assertEqual(self.rows(out, "each 1v1 set between them"), [  # not the forfeit, the tie or the crew battle
            ["Cup", "1970-01-01", "A", A, 3, 1], ["Cup", "1970-01-01", "A", A, 3, 0], ["League", "1970-01-01", "A", A, 2, 0]])
        self.assertEqual(self.rows(self.call("head_to_head", player_id=B, opponent_id=A), "B's 1v1 record against A"),
                         [["B", B, "A", A, 0, 3, 3, 1, 8, 0]])

    def test_each_set_leads_with_its_event_named_without_a_mode_its_tournament_repeats(self):
        named = [(t, e, templates.set_event(t, e)) for t, e in [
            ("Brawlhalla World Championship Expo 2022", "1v1"), ("CEO 2025", "Brawlhalla Singles (1v1)"),
            ("North America - Winter Championship 2023", "Brawlhalla Championship 1v1"), ("Cup", None),
            ("DreamHack Atlanta 2019", "Brawlhalla World Championship 1v1"),
            ("Brawl League Masters - Season 4 (NA)", "Top 8 Finals Brawlhalla")]]
        self.assertEqual([n for _, _, n in named], [
            "Brawlhalla World Championship Expo 2022", "CEO 2025", "North America - Winter Championship 2023", "Cup",
            "DreamHack Atlanta 2019 / Brawlhalla World Championship 1v1",  # says more than the mode
            "Brawl League Masters - Season 4 (NA) / Top 8 Finals Brawlhalla"])  # a phase of a split tournament
        self.assertIn("- Name a set or a result by its event, written short (BCX 2022, Winter Royale 2023), not by its"
                      " date.", react.SYSTEM)

    def test_the_model_reads_that_it_counts_sets_and_where_placements_are(self):
        description = " ".join(next(t["function"]["description"] for t in react.TOOLS
                                    if t["function"]["name"] == "head_to_head").split())
        self.assertIn("It counts sets, not placements: for where they placed at the same events, such as how often one"
                      " finished behind the other, use run_sql on v_results.", description)  # q44 seed 2 counted sets

    def test_each_side_of_the_sets_is_its_own_filter_since_an_or_reads_every_set(self):
        ran = " ".join(self.call("head_to_head", player_id=A, opponent_id=B)["ran"])
        self.assertIn(f"WHERE s.winner_id = {A} AND s.loser_id = {B} UNION ALL", ran)
        self.assertNotIn(" OR ", ran)

    def test_2v2_meetings_are_counted_apart_from_the_1v1_record(self):
        self.assertIn("In 2v2, A and B never met on opposite teams.",  # partners, never opponents
                      self.call("head_to_head", player_id=A, opponent_id=B)["notes"])
        out = self.call("head_to_head", player_id=A, opponent_id=C)
        self.assertEqual(self.rows(out, "A's 1v1 record"), [["A", A, "C", C, 0, 1, 1, 0, 3, 0]])  # the DQ doesn't count
        self.assertIn("In 2v2, A's teams and C's teams met in 1 set: A's side won 1 and lost 0, and C's side won 0 and"
                      " lost 1. Those aren't in the 1v1 record.", out["notes"])  # both sides, so it reads as whose
        self.assertIn("In 1v1, A won 0 and lost 1 of their 1 set against C; C won 1 and lost 0.", out["notes"])

    def test_a_mode_keeps_one_of_the_two(self):  # qwen3:8b passed mode 17 times in the model comparison, refused
        one = self.call("head_to_head", player_id=A, opponent_id=C, mode="1v1")
        self.assertEqual(self.rows(one, "A's 1v1 record"), [["A", A, "C", C, 0, 1, 1, 0, 3, 0]])
        self.assertFalse([n for n in one["notes"] if "2v2" in n])
        two = self.call("head_to_head", player_id=A, opponent_id=C, mode="2v2")
        self.assertEqual(self.rows(two, "A's teams against C's teams in 2v2"), [["A", A, "C", C, 1, 0, 1]])
        self.assertEqual(two["notes"], ["In 2v2, A's teams and C's teams met in 1 set: A's side won 1 and lost 0, and"
                                        " C's side won 0 and lost 1."])
        self.assertIn("2v2 sets between their teams", two["scope"])
        self.assertIn("mode is '1v1' or '2v2'", self.call("head_to_head", player_id=A, opponent_id=C, mode="3v3")["error"])

    def test_unscored_sets_are_flagged_and_players_who_never_met_get_a_record_of_zero(self):
        out = self.call("head_to_head", player_id=A, opponent_id=D)
        self.assertEqual(self.rows(out, "A's 1v1 record"), [["A", A, "D", D, 1, 0, 1, None, None, 1]])
        self.assertIn("1 of the 1 sets has no recorded score, so the games leave it out: say the record includes sets"
                      " with no recorded score.", out["notes"])
        out = self.call("head_to_head", player_id=E, opponent_id=F)
        self.assertEqual(([t["what"] for t in out["tables"]], self.rows(out, "E's 1v1 record")),
                         (["E's 1v1 record against F, in sets"], [["E", E, "F", F, 0, 0, 0, None, None, 0]]))
        self.assertEqual(out["notes"], ["E and F have no counted 1v1 sets against each other at official events (DQs,"
                                        " forfeits and ties aren't counted).", "In 2v2, E and F never met on opposite teams."])

    def test_players_are_given_by_id_and_a_merged_record_is_the_person(self):
        out = self.call("head_to_head", player_id=A2, opponent_id=B)
        self.assertEqual(self.rows(out, "A's 1v1 record against B")[0][4:7], [3, 0, 3])
        self.assertIn(f"player_id {A2} is another record of A (player_id {A}): these are the person's.", out["notes"])
        self.assertEqual(self.call("head_to_head", player_id=A, opponent_id=A2)["error"],
                         "player_id and opponent_id are both A: pass the two players' player_ids")
        self.assertIn("opponent_id is the number resolve_player returns, not a name: call resolve_player with 'B'",
                      self.call("head_to_head", player_id=A, opponent_id="B")["error"])
        self.assertEqual(self.call("head_to_head", player_id=A)["error"],
                         "head_to_head needs opponent_id: head_to_head takes player_id, opponent_id, mode, year, since,"
                         " until, region, event")


class RankPlayersTest(Fixture):
    def test_players_are_ranked_with_every_tie_and_the_split_by_mode(self):
        out = self.call("rank_players", by="wins")
        self.assertEqual(out["scope"], "official events, 1v1 and 2v2")
        self.assertEqual(self.rows(out, "players ranked by wins (1st places), everyone ranked 5th or better"),
                         [[1, "A", A, 3, 2, 1, 1], [2, "B", B, 2, 1, 1, 1], [2, "C", C, 2, 2, 0, 1]])
        self.assertEqual(out["tables"][0]["columns"], ["rank", "player", "player_id", "wins", "1v1", "2v2", "crew battles"])
        self.assertEqual(out["notes"], [
            "Players on the same rank are tied: give them the same place.",
            "A tournament's 1v1 and 2v2 are separate events, and each counts: wins (1st places) at both count twice. Say so.",
            "The crew battles column counts each player's crew battles among these: a crew's placement is a team result,"
            " counted as 1v1. Say so."])
        self.assertEqual([row[:4] for row in self.rows(self.call("rank_players", by="top8s", top=1), "players ranked")],
                         [[1, "A", A, 5], [1, "B", B, 5]])  # a cutoff never splits a tie
        self.assertEqual([row[1] for row in self.rows(self.call("rank_players", by="medals", top=2), "players ranked")],
                         ["A", "B", "C"])

    def test_a_mode_a_year_and_an_event_narrow_the_ranking_and_the_scope_says_so(self):
        out = self.call("rank_players", by="wins", mode="1v1")
        self.assertEqual((out["scope"], out["tables"][0]["columns"]),
                         ("official events, 1v1", ["rank", "player", "player_id", "wins", "crew battles"]))
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 2, 1], [1, "C", C, 2, 1], [3, "B", B, 1, 1]])
        self.assertEqual(self.rows(self.call("rank_players", by="wins", mode="2v2"), "players ranked"),
                         [[1, "A", A, 1], [1, "B", B, 1]])  # no crew battles in 2v2
        cup = self.call("rank_players", by="wins", event="cup 2020")
        self.assertEqual((cup["scope"], cup["event"]["status"]),
                         ("official events, 1v1 and 2v2, at the 2 events the name means", "confident"))
        self.assertEqual(self.rows(cup, "players ranked"), [[1, "A", A, 2, 1, 1, 0], [2, "B", B, 1, 0, 1, 0]])
        empty = self.call("rank_players", by="wins", year=2026)
        self.assertEqual((self.rows(empty, "players ranked"), empty["notes"]), ([], [
            "No player has any wins (1st places) here (official events, 1v1 and 2v2, in 2026), so the ranking is empty."]))

    def test_a_series_with_regional_championships_counts_them_apart_and_statuses_come_first(self):
        out = self.call("rank_players", by="wins", event="cup")
        self.assertEqual(out["tables"][0]["columns"][-1], "at regional championships")
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 2, 1, 1, 0, 0], [2, "B", B, 1, 0, 1, 0, 0]])
        self.assertEqual(sorted(note.split(" (")[0] for note in out["notes"][:2]), ["Dreamland", "League Week 1"])
        self.assertEqual(out["notes"][-1], "'cup 2021' was held as several regional championships, all counted here: 'at"
                                           " regional championships' counts each player's wins at them. Say whether your"
                                           " answer counts them.")

    def test_past_the_rows_listed_a_tie_group_is_counted_whole_not_split(self):
        with patch.object(templates, "RANKED_AT_MOST", 2):
            out = self.call("rank_players", by="wins")
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 3, 2, 1, 1]])
        self.assertTrue(out["notes"][0].startswith("Past 2 rows a tie isn't split, so these players are counted but not"
                                                   " listed: 2 tied at rank 2 with 2 wins each. Narrow the question"))

    def test_arguments_it_cant_use_get_errors_and_an_event_must_be_one_tournament(self):
        self.assertEqual(self.call("rank_players", by="points")["error"], "by is 'wins', 'medals' or 'top8s', not 'points'")
        self.assertEqual(self.rows(self.call("rank_players", by="Top 8s"), "players ranked by top 8s")[0][:2], [1, "A"])
        self.assertEqual(self.rows(self.call("rank_players", by="titles"), "players ranked by wins")[0][:2], [1, "A"])
        self.assertEqual(self.call("rank_players")["error"],
                         "rank_players needs by: rank_players takes by, top, mode, year, since, until, region, event,"
                         " never_won")
        self.assertEqual(self.call("rank_players", by="wins", mode="crew")["error"], "mode is '1v1' or '2v2', not 'crew'")
        out = self.call("rank_players", by="wins", event="league")
        self.assertEqual(([t["what"] for t in out["tables"]], out["ran"]), (["the closest events"], []))
        self.assertTrue(out["notes"][0].endswith("Call again with one tournament's name, as listed here."))


if __name__ == "__main__":
    unittest.main()
