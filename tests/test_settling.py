import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import settling  # noqa: E402
from settling import Context  # noqa: E402
from test_agent import Fixture  # noqa: E402  the tiny database: Raydish (11) and Zivai (19) have 6 results, megD (7) 2

RAYDISH, RADSES, RADISH = ({"player_id": 11, "name": "Raydish", "display": "Raydish", "score": 0.85},
                           {"player_id": 24, "name": "Radses", "display": "Radses", "score": 0.8},
                           {"player_id": 30, "name": "radish", "display": "radish", "score": 0.8})
ASKED = [{"name": "raydishes", "candidates": [RAYDISH, RADSES, RADISH]}]


class ChoiceTest(unittest.TestCase):
    def test_an_ordinal_a_number_or_a_candidates_name_picks_from_the_suggestions(self):
        for reply, picked in [("the first one", RAYDISH), ("2", RADSES), ("#3", RADISH), ("the last one", RADISH),
                              ("yes, the second", RADSES), ("Raydish", RAYDISH), ("i meant radish", RADISH),
                              ("RADSES please", RADSES), ("option 2", RADSES)]:
            self.assertEqual(settling.choice(reply, ASKED), [("raydishes", picked)], reply)

    def test_a_reply_with_anything_else_is_not_a_choice(self):
        for reply in ["none of them", "the first one in 2v2", "who won bcx 2022", "the fourth one", "first or second",
                      "the one with 98 results", ""]:
            self.assertEqual(settling.choice(reply, ASKED), [], reply)
        self.assertEqual(settling.choice("the first one", []), [])  # nothing was asked

    def test_with_several_names_asked_about_a_reply_names_its_choices(self):
        asked = ASKED + [{"name": "megdd", "candidates": [{"player_id": 7, "name": "megD"},
                                                          {"player_id": 8, "name": "megdee"}]}]
        self.assertEqual(settling.choice("the first one", asked), [])
        self.assertEqual(settling.choice("Raydish and megD", asked),
                         [("raydishes", RAYDISH), ("megdd", {"player_id": 7, "name": "megD"})])

    def test_a_choice_becomes_the_question_asked_with_the_chosen_player_written_in(self):
        context = Context("whats megd and raydishes record in 1v1", players=[("megD", 7)], asked=ASKED)
        settled = settling.chosen(context, [("raydishes", RAYDISH)])
        self.assertEqual(settled.text, 'whats megd and Raydish record in 1v1 [Raydish is player_id 11: the user chose'
                                       ' them when asked which player "raydishes" means.]')
        self.assertEqual((settled.retrieve, settled.how, settled.players),
                         ("whats megd and Raydish record in 1v1", "a reply to suggestions", [("megD", 7), ("Raydish", 11)]))
        self.assertEqual(settled.traced()["chosen"], [{"spelling": "raydishes", "player_id": 11, "name": "Raydish"}])

    def test_the_spelling_asked_about_resolves_to_the_player_chosen_alone(self):
        found = settling.resolved("Raydishes", "raydishes", RAYDISH)
        self.assertEqual((found["status"], [c["player_id"] for c in found["candidates"]], found["candidates"][0]["match"],
                          found["candidates"][0]["score"]), ("confident", [11], "chosen by the user", 1.0))
        self.assertIn("Use player_id 11, and call them Raydish.", found["note"])


class CuesTest(Fixture):
    def setUp(self):
        super().setUp()
        self.two = Context("whats raydish's record with zivai", players=[("Raydish", 11), ("Zivai", 19)])

    def settle(self, message, context=None):
        return settling.by_cues(message, context or self.two, self.resolver)

    def test_a_follow_up_that_names_no_one_gets_a_note_on_what_it_continues(self):
        settled = self.settle("tell me about the 2v2 record")
        self.assertEqual(settled.text, 'tell me about the 2v2 record [This continues the previous question, "whats'
                                       ' raydish\'s record with zivai", about Raydish (player_id 11) and Zivai'
                                       ' (player_id 19).]')
        self.assertEqual((settled.retrieve, settled.how, settled.players),
                         ("whats raydish's record with zivai tell me about the 2v2 record", "a follow-up (cues)",
                          [("Raydish", 11), ("Zivai", 19)]))
        for message in ["in 2v2?", "and in 2023", "what about at bcx 2022", "i meant the 2v2 record", "how did they do"]:
            self.assertEqual(self.settle(message).how, "a follow-up (cues)", message)

    def test_a_message_that_names_a_player_or_refers_to_nothing_is_as_asked(self):
        for message in ["what about zivai vs godly", "rank the top 5 players by official 1v1 wins", "has raydish won worlds",
                        "thanks"]:
            self.assertEqual((self.settle(message).how, self.settle(message).text), ("as asked", message), message)
        first = settling.by_cues("tell me about the 2v2 record", Context(), self.resolver)  # nothing to continue
        self.assertEqual(first.how, "as asked")

    def test_he_or_she_gets_the_player_when_the_previous_question_had_one(self):
        one = Context("whats the biggest record raydish has", players=[("Raydish", 11)])
        settled = self.settle("he doesnt have big records vs zivai?", one)
        self.assertEqual((settled.text, settled.how), ("he doesnt have big records vs zivai? [he: Raydish (player_id 11),"
                                                       " from the previous question.]", "a pronoun (cues)"))
        self.assertEqual(self.settle("he doesnt have big records vs zivai?").how, "as asked")  # two players: which?

    def test_a_follow_up_note_lists_the_events_it_continues(self):
        events = Context("who won bcx 2022", events=[("Brawlhalla World Championship Expo 2022 / 1v1", "bcx22-1"),
                                                     ("Brawlhalla World Championship Expo 2022 / 2v2", "bcx22-2")])
        self.assertEqual(self.settle("tell me about the 2v2 one", events).text,
                         'tell me about the 2v2 one [This continues the previous question, "who won bcx 2022", about the'
                         ' events Brawlhalla World Championship Expo 2022 / 1v1 and Brawlhalla World Championship Expo'
                         ' 2022 / 2v2.]')


class Rephrase:
    """A rewrite model: the replies it's given, in order, and every request it got."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, messages, **model):
        self.sent.append((messages, model))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return {"message": {"role": "assistant", "content": reply}}


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.context = Context("whats raydish's record with zivai", "Raydish leads Zivai 5-2 in 7 sets.",
                               players=[("Raydish", 11), ("Zivai", 19)])

    def test_one_short_call_rewrites_a_follow_up_as_a_question_of_its_own(self):
        rephrase = Rephrase("What is Raydish's 2v2 record against Zivai?")
        settled = settling.by_model("tell me about the 2v2 record", self.context, rephrase, model="m", seed=2)
        self.assertEqual((settled.text, settled.retrieve, settled.how, settled.players),
                         ("What is Raydish's 2v2 record against Zivai?", "What is Raydish's 2v2 record against Zivai?",
                          "rewritten", [("Raydish", 11), ("Zivai", 19)]))
        self.assertEqual(settled.rewrite["reply"], "What is Raydish's 2v2 record against Zivai?")
        (messages, model), = rephrase.sent
        self.assertEqual((messages[0], model), ({"role": "system", "content": settling.REWRITE}, {"model": "m", "seed": 2}))
        self.assertEqual(messages[1]["content"], "Previous question: whats raydish's record with zivai\nPrevious answer:"
                                                 " Raydish leads Zivai 5-2 in 7 sets.\nPlayers it was about: Raydish,"
                                                 " Zivai\n\nLatest message: tell me about the 2v2 record")

    def test_a_kept_message_a_label_and_a_failure(self):
        kept = settling.by_model("who won bcx 2022?", self.context, Rephrase("Who won BCX 2022?"))
        self.assertEqual((kept.text, kept.how), ("who won bcx 2022?", "kept by the rewrite"))
        labelled = settling.by_model("and in 2023", self.context,
                                     Rephrase('Standalone question: "What is Raydish\'s record against Zivai in 2023?"\n'
                                              "I filled in the players."))
        self.assertEqual(labelled.text, "What is Raydish's record against Zivai in 2023?")
        failed = settling.by_model("and in 2023", self.context, Rephrase(urllib.error.URLError("refused")))
        self.assertEqual((failed.text, failed.how, failed.rewrite), ("and in 2023", "as asked: the rewrite failed",
                                                                     {"error": "URLError: <urlopen error refused>"}))
        rambling = settling.by_model("and in 2023", self.context, Rephrase("x" * 500))
        self.assertEqual((rambling.text, rambling.how), ("and in 2023", "as asked: the rewrite gave no question"))

    def test_the_first_message_calls_no_model(self):
        rephrase = Rephrase()
        self.assertEqual(settling.by_model("who won bcx 2022?", Context(), rephrase).how, "as asked")
        self.assertEqual(rephrase.sent, [])


class AfterTest(unittest.TestCase):
    def test_the_context_holds_the_players_the_text_names_and_the_events_found(self):
        def call(name, observation, arguments=None):
            return {"name": name, "arguments": arguments or {}, "observation": json.dumps(observation)}
        trace = {"answer": "Raydish won it.", "asked": [], "steps": [{"tool_calls": [
            call("resolve_player", {"name": "raydish", "status": "confident",
                                    "candidates": [{"player_id": 11, "name": "Raydish"}]}),
            call("resolve_player", {"name": "luna", "status": "confident",  # a name the question doesn't write
                                    "candidates": [{"player_id": 5, "name": "luna"}]}),
            call("resolve_player", {"name": "godly", "status": "ambiguous",
                                    "candidates": [{"player_id": 19, "name": "Zivai"}]}),
            call("resolve_event", {"name": "bcx 2022", "status": "confident",
                                   "events": [{"event_id": "bcx22-1", "name": "BCX 2022 / 1v1"}]}),
            call("event_results", {"template": "event_results", "tables": [
                {"what": "the events the name means", "columns": ["event", "event_id", "date"],
                 "rows": [["BCX 2022 / 2v2", "bcx22-2", "2022-11-04"]]}]}),
            call("head_to_head", {"template": "head_to_head", "player": {"player_id": 11, "name": "Raydish"},
                                  "opponent": {"player_id": 19, "name": "Zivai"}, "tables": []}),
            call("run_sql", {"error": "no such table"}),
            {"name": "run_sql", "arguments": {}, "observation": None}]}]}
        settled = settling.Settled("did raydish or godly win bcx 2022 [x]", "did raydish or godly win bcx 2022",
                                   players=[("megD", 7)])
        context = settling.after(trace, settled)
        self.assertEqual((context.question, context.answer, context.players, context.events, context.asked),
                         ("did raydish or godly win bcx 2022 [x]", "Raydish won it.",
                          [("megD", 7), ("Raydish", 11), ("Zivai", 19)],
                          [("BCX 2022 / 1v1", "bcx22-1"), ("BCX 2022 / 2v2", "bcx22-2")], []))


if __name__ == "__main__":
    unittest.main()
