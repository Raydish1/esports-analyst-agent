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
from test_views import A, B, C, D, F, populate  # noqa: E402


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
        self.assertIn("run_sql and event_results", self.call("nothing")["error"])

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
        self.assertEqual(self.rows(out, "the events"), [["Cup", "1970-01-01", "1v1", None, None],
                                                        ["Duos", "1970-01-01", "2v2", None, None]])
        self.assertEqual(self.rows(out, "each event's winners"), [["Cup", "1970-01-01", "1v1", 1, "A", [A]],
                                                                  ["Duos", "1970-01-01", "2v2", 1, "A / B", [A, B]]])

    def test_a_cutoff_never_splits_a_tie(self):
        out = self.call("event_results", event="cup 2020", top=3)
        cup = [row[3:] for row in self.rows(out, "each event's top 3") if row[0] == "Cup"]
        self.assertEqual(cup, [[1, "A", [A]], [2, "B", [B]], [3, "C", [C]], [3, "F", [F]]])
        self.assertIn("Rows on the same placement in one event are tied there: give them the same place.", out["notes"])
        self.assertNotIn("tied", " ".join(self.call("event_results", event="cup 2020", top=2)["notes"]))

    def test_an_event_that_wasnt_held_or_has_unreliable_placements_says_so_first_and_has_no_winner(self):
        out = self.call("event_results", event="dreamland")
        self.assertTrue(out["notes"][0].startswith("Dreamland (1970-01-01) was not held, so it has no results"))
        self.assertEqual((self.rows(out, "the events")[0][3], self.rows(out, "each event's winners")), ("cancelled", []))
        out = self.call("event_results", event="league week 1")
        self.assertIn("has unreliable placements, so they aren't results and it has no reliable winner", out["notes"][0])
        self.assertEqual((self.rows(out, "the events")[0][3], self.rows(out, "each event's winners")),
                         ("placements_unreliable", []))  # C and D both "won" it: neither is listed

    def test_a_crew_is_one_row_and_a_side_format_has_no_results(self):
        out = self.call("event_results", event="crew battle")
        self.assertEqual(self.rows(out, "each event's winners"),
                         [["Crew Battle 3v3", "1970-01-01", "1v1 (crew battle)", 1, "A / B / C", [A, B, C]]])
        self.assertIn("A crew battle's placement is the crew's: a team result, which counts as 1v1.", out["notes"])
        out = self.call("event_results", event="kung foot")
        self.assertEqual(self.rows(out, "the events")[0][2], "kung foot (neither 1v1 nor 2v2)")
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


if __name__ == "__main__":
    unittest.main()
