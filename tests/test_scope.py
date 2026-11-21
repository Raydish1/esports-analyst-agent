import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))
import react  # noqa: E402
import scope  # noqa: E402
from templates import TEMPLATES  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402


class ScopeTest(Fixture):
    def setUp(self):
        super().setUp()
        self.events = react.Tools(self.path).events
        self.events.words = self.events.words | {"bcx", "worlds"}

    def read(self, question):
        return scope.scope(question, self.events)

    def lacks(self, question, name, **arguments):
        return [said for said, _ in scope.lacking(self.read(question), name, arguments, TEMPLATES[name].parameters,
                                                  self.events)]

    def test_the_scope_words_a_question_names(self):
        asked = self.read("who's the strongest 1v1 player right now in na?")  # live, finding 29
        self.assertEqual((asked.mode, asked.present, asked.regions), ("1v1", "right now", ["na"]))
        self.assertEqual(self.read("most wins in 2024").years, ["2024"])
        self.assertEqual(self.read("did the winner of bcx 2022 win 2024 worlds").years, [])  # the events' years
        self.assertEqual((self.read("wins since 2023").since, self.read("wins before 2020").until), ("2023", "2020"))
        self.assertEqual((self.read("between 2019 and 2021").since, self.read("between 2019 and 2021").until),
                         ("2019", "2021"))
        self.assertIsNone(self.read("compare his 1v1 and 2v2 results").mode)
        self.assertIsNone(self.read("his singles or doubles record").mode)
        self.assertFalse(self.read("how many results has megd?"))

    def test_a_call_leaving_out_a_scope_word_it_could_take(self):
        question = "who's the strongest 1v1 player right now?"
        self.assertEqual(self.lacks(question, "rank_players", by="wins"),
                         ["names 1v1", "asks about the present ('right now')"])
        self.assertEqual(self.lacks(question, "rank_players", by="wins", mode="singles", since="2025-10"), [])
        self.assertEqual(self.lacks(question, "power_rankings"), [])  # 1v1 by default, and the present itself
        self.assertEqual(self.lacks("most 2v2 wins in 2024", "rank_players", by="wins", mode="2v2", event="bcx 2024"), [])
        self.assertEqual(self.lacks("most 2v2 wins in 2024", "rank_players", by="wins", mode="2v2"), ["names 2024"])
        self.assertEqual(self.lacks("who won bcx in 2022", "event_results", event="bcx"), ["names 2022"])
        self.assertEqual(self.lacks("most wins in north america", "rank_players", by="wins", region="NA"), [])
        self.assertEqual(self.lacks("most wins in north america", "rank_players", by="wins"), ["names North America"])
        self.assertEqual(self.lacks("top 8 of winters 2023 na", "event_results", event="winters 2023 na"), [])

    def test_the_opponents_side_of_a_players_records_reaches_rank_pairs(self):
        for question in ("Who has the best record against marckiemoo?", "who has raydish lost to the most in 1v1",
                         "who has beaten zivai the most", "Who's got the best 1v1 record against Phazon?"):  # q08, q40
            self.assertEqual(self.lacks(question, "rank_pairs", player_id=1, by="record")[0][:30],
                             "asks for the other players' re", question)
            self.assertEqual(self.lacks(question, "rank_pairs", player_id=1, by="rate", side="opponents"), [])
        for question in ("whats volst's best record against anyone", "who does megd beat the most",
                         "volst's best records vs an opponent", "whats bbballoonboy's 1v1 record vs impala",
                         "he doesnt have big records vs raydish or java or guichabou etc?"):  # q27, c1 turn 3: X's own
            self.assertEqual(self.lacks(question, "rank_pairs", player_id=1, by="record"), [], question)

    def test_a_best_placement_is_asked_with_no_top(self):
        for question in ("what's megd's best placement", "what is renivics best placement in 2v2",
                         "highest finish flowervs has ever had in 2v2"):  # finding 26, c15, audit a03
            self.assertIn("asks for a best placement", self.lacks(question, "player_results", player_id=1, top=1))
            self.assertNotIn("asks for a best placement", self.lacks(question, "player_results", player_id=1))
        self.assertEqual(self.lacks("how many top 8 finishes does megd have", "player_results", player_id=1, top=8), [])

    def test_templates_that_cant_take_a_word_arent_checked_for_it(self):
        self.assertEqual(self.lacks("kyna vs yuz in only 1v1", "head_to_head", player_id=1, opponent_id=2), [])
        self.assertEqual(self.lacks("who did megd team with in 1v1 events", "team_results", player_id=1), [])
        self.assertEqual(self.lacks("who's #1 in 2024", "power_rankings"), [])


class ScopeLoopTest(unittest.TestCase):
    """On the template tests' database, which has the views the templates read."""

    @classmethod
    def setUpClass(cls):
        import test_templates
        test_templates.Fixture.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_call_leaving_out_the_questions_scope_is_refused_once_with_what_to_pass(self):
        ask = Scripted(reply(calls=[("rank_players", {"by": "wins"})]),
                       reply(calls=[("rank_players", {"by": "wins", "mode": "1v1", "since": "2020"})]),
                       reply("By official 1v1 wins since 2020, nobody has any."))
        trace = react.run("who is the strongest 1v1 player right now", self.tools, ask=ask, log=lambda *_: None)
        refused, ran = trace["steps"][0]["tool_calls"][0], trace["steps"][1]["tool_calls"][0]
        self.assertEqual(refused["scope"], ["names 1v1", "asks about the present ('right now')"])
        self.assertIn("This call wasn't run: the question names 1v1 and asks about the present ('right now'), and the"
                      ' call leaves it out. Pass mode="1v1" and a recent window', json.loads(refused["observation"])["error"])
        self.assertNotIn("scope", ran)

    def test_the_same_call_made_again_unchanged_runs(self):
        call = reply(calls=[("rank_players", {"by": "wins"})])
        ask = Scripted(call, call, reply("A has the most official wins."))
        trace = react.run("who has the most wins in 1v1 and who has the most results", self.tools, ask=ask,
                          log=lambda *_: None)
        first, second = trace["steps"][0]["tool_calls"][0], trace["steps"][1]["tool_calls"][0]
        self.assertEqual((first["scope"], "scope" in second), (["names 1v1"], False))
        self.assertIn('"template": "rank_players"', second["observation"])


if __name__ == "__main__":
    unittest.main()
