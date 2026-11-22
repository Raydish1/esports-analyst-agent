import json
import sys
import unittest
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

    def test_a_reply_written_exactly_as_one_candidates_name_with_its_mark_picks_it(self):
        dragons = [{"name": "dragon", "candidates": [  # live, 20261120T050251Z-005: "Dragon!" wasn't taken as a choice
            {"player_id": 88841, "name": "Dragon!", "display": "Dragon!", "matched": "Dragon!"},
            {"player_id": 48834, "name": "Parz", "display": "Parz (formerly Dragon)", "matched": "Frost | Dragon"},
            {"player_id": 1421, "name": "Dragon", "display": "Dragon", "matched": "Dragon"}]}]
        self.assertEqual([c["player_id"] for _, c in settling.choice("Dragon!", dragons)], [88841])
        self.assertEqual([c["player_id"] for _, c in settling.choice("frost | dragon", dragons)], [48834])
        self.assertEqual(settling.choice("dragon", dragons), [])  # without a mark, two of them are 'dragon'
        self.assertEqual([c["player_id"] for _, c in settling.choice("the first one", dragons)], [88841])

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

    def test_a_message_that_opens_as_a_follow_up_and_names_players_continues_with_them(self):
        ranking = Context("top 5 2v2 players in brawlhalla history")  # live, then "what about cody travis and phazon?"
        settled = self.settle("what about cody travis and raydish?", ranking)
        self.assertEqual(settled.text, 'what about cody travis and raydish? [This continues the previous question, "top'
                                       ' 5 2v2 players in brawlhalla history", now about Cody Travis (player_id 21) and'
                                       ' Raydish (player_id 11).]')
        self.assertEqual((settled.how, settled.players, settled.retrieve),
                         ("a follow-up with new names (cues)", [("Cody Travis", 21), ("Raydish", 11)],
                          "top 5 2v2 players in brawlhalla history what about cody travis and raydish?"))
        self.assertEqual(self.settle("what about zivai vs godly").players, [("Zivai", 19)])  # Godly is Zivai: once

    def test_a_question_about_the_previous_answer_gets_a_note_to_check_it_again(self):
        partners = Context("who has megd played with in 2v2", players=[("megD", 7)])
        settled = self.settle("there are not that many events", partners)  # live: repeated the answer, no lookup
        self.assertEqual(settled.text, 'there are not that many events [This questions your answer to the previous'
                                       ' question, "who has megd played with in 2v2", about megD (player_id 7): check'
                                       ' what it questions with the tools again, then say plainly whether that answer'
                                       ' was right, and correct it if it wasn\'t.]')
        self.assertEqual((settled.how, settled.retrieve), (settling.DISPUTED, "who has megd played with in 2v2"))
        why = self.settle("so why did you say cody travis and raydish have won 24 2v2 tournaments", partners)
        self.assertEqual((why.how, why.players), (settling.DISPUTED, [("megD", 7), ("Cody Travis", 21), ("Raydish", 11)]))
        for message in ["are you sure?", "you just said 12", "that's wrong", "is that right", "that can't be right"]:
            self.assertEqual(self.settle(message, partners).how, settling.DISPUTED, message)
        self.assertEqual(settling.by_cues("are you sure", Context(), self.resolver).how, "as asked")  # nothing before

    def test_a_question_about_what_the_page_showed_is_one_about_the_answer(self):
        card = Context("cody travis vs phazon head to head", players=[("Raydish", 11)],
                       shown="Stat cards: Raydish in 2v2 only 3 results, GOLD 4.")
        settled = self.settle("on the card, where does raydish's 4 gold come from? is that medals?", card)  # finding 23
        self.assertEqual(settled.how, settling.PAGED)  # its own note, not a dispute's (finding 32)
        self.assertIn("This asks what the page showed beside your answer to the previous question", settled.text)
        self.assertIn("It doesn't question your answer, so don't say whether that answer was right", settled.text)
        self.assertIn("player_results with no top gives each mode, and both together, at once", settled.text)
        self.assertEqual(self.settle("what does the graphic show for raydish", card).how, settling.PAGED)
        plain = Context("cody travis vs phazon head to head", players=[("Raydish", 11)])  # the page showed nothing
        self.assertEqual(self.settle("show me raydish on a card", plain).how, "as asked")
        self.assertEqual(self.settle("where does that 4 come from?", plain).how, settling.DISPUTED)  # any answer's
        doubted = self.settle("are you sure? you just said raydish has 4 medals in the graphic", card)  # c8 turn 4
        self.assertEqual((doubted.how, doubted.card), (settling.DISPUTED, True))  # checked again with the tools, about
        # the page's figures, so a recheck that calls no tool has player_results run for its players (react.py)
        self.assertFalse(self.settle("where does that 4 come from?", plain).card)
        self.assertIn('This questions what the page showed beside your answer to the previous question, "cody travis vs'
                      ' phazon head to head"', doubted.text)

    def test_a_message_that_names_a_player_or_refers_to_nothing_is_as_asked(self):
        for message in ["rank the top 5 players by official 1v1 wins", "has raydish won worlds", "thanks"]:
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
        self.assertEqual((context.question, context.players, context.events, context.asked),
                         ("did raydish or godly win bcx 2022 [x]", [("megD", 7), ("Raydish", 11), ("Zivai", 19)],
                          [("BCX 2022 / 1v1", "bcx22-1"), ("BCX 2022 / 2v2", "bcx22-2")], []))


if __name__ == "__main__":
    unittest.main()
