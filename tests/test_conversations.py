import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
import conversations  # noqa: E402
from conversations import Turn, score_turn  # noqa: E402

NAMES = {142100: "megD", 160000: "Raydish", 147569: "capsar"}


def call(name, arguments, observation, **marks):
    return {"name": name, "arguments": arguments, "observation": json.dumps(observation), "seconds": 0.1, **marks}


def sql(query, columns, rows):
    return call("run_sql", {"query": query}, {"complete": True, "columns": columns, "rows": rows, "row_count": len(rows)})


def trace(question, answer, *calls, outcome="answered", **step):
    return {"question": question, "answer": answer, "outcome": outcome, "steps": [{"tool_calls": list(calls), **step}]}


RECORD = sql("SELECT player_id, opponent_id, wins, losses, matches FROM v_head_to_head_1v1 WHERE player_id = 142100"
             " AND opponent_id = 160000", ["player_id", "opponent_id", "wins", "losses", "matches"], [[142100, 160000, 2, 2, 4]])
RESOLVED = call("resolve_player", {"name": "megd"}, {"name": "megd", "status": "confident", "candidates": [
    {"player_id": 142100, "name": "megD", "score": 0.98, "official_results": 104}]})


def checked(turn, **spec):
    return {name: c["passed"] for name, c in score_turn(turn, spec).items()}


class CallsWithTest(unittest.TestCase):
    def test_a_call_that_ran_must_match_one_of_the_wanted_calls(self):
        ranked = call("rank_players", {"by": "wins", "mode": "1v1", "since": "2025-10-01"}, {"template": "rank_players"})
        turn = Turn(trace("who is the strongest 1v1 player right now", "Zivai.", ranked), None, NAMES)
        wanted = [{"tool": "power_rankings"}, {"tool": "rank_players", "mode": "1v1", "since": "*"}]
        self.assertEqual(checked(turn, grounded=False, calls_with=wanted)["calls_with"], True)
        bare = call("rank_players", {"by": "wins"}, {"template": "rank_players"})  # finding 29's call
        turn = Turn(trace("who is the strongest 1v1 player right now", "Zivai.", bare), None, NAMES)
        passed, detail = conversations.CHECKS["calls_with"](turn, wanted)
        self.assertEqual((passed, detail), (False, "no call matches power_rankings() or rank_players(mode=1v1, since=*)"))
        refused = call("power_rankings", {}, {"error": "x"}, scope=["names 1v1"])
        turn = Turn(trace("q", "a", refused), None, NAMES)
        self.assertFalse(checked(turn, grounded=False, calls_with=wanted)["calls_with"])  # a refused call didn't run


class SetTest(unittest.TestCase):
    def test_the_set_has_no_problems(self):
        self.assertEqual(conversations.problems(conversations.load()), [])

    def test_the_team_set_has_no_problems_and_no_id_of_the_main_sets(self):
        teams = conversations.load(conversations.SET.with_name("teams.toml"))
        self.assertEqual(conversations.problems(teams), [])
        main = {c["id"] for c in conversations.load()["conversation"]}
        self.assertEqual(main & {c["id"] for c in teams["conversation"]}, set())

    def test_a_turn_without_expect_or_with_an_unknown_check_is_a_problem_named_without_its_text(self):
        data = {"conversation": [{"id": "x1", "title": "t", "turn": [
            {"say": "a secret question", "expect": "", "rowz": [[1]]}, {"say": "s", "expect": "e", "check": "q09"}]}]}
        found = conversations.problems(data)
        self.assertEqual(found, ["x1 turn 1: no expect", "x1 turn 1: no check named 'rowz'",
                                 "x1 turn 2: check names 'q09', which has no stage 2 check"])  # q09 is unanswerable
        self.assertNotIn("secret", " ".join(found))
        shown = {"conversation": [{"id": "x2", "title": "t", "turn": [{"say": "s", "expect": "e", "shown": "a card"}]}]}
        self.assertEqual(conversations.problems(shown), [])  # what the page showed is a turn's field, not a check


class WindowTest(unittest.TestCase):
    def test_a_turn_reads_its_own_results_and_the_previous_turns_only(self):
        earlier = trace("whats megd and raydish's record", "2-2.", RESOLVED, RECORD)
        middle = trace("thanks", "Glad to help.")
        late = Turn(trace("and again?", "megD and Raydish are 2-2 in 4 sets.", sql("SELECT 1", ["a"], [[1]])), middle, NAMES)
        self.assertEqual(checked(late, rows=[[[142100, "megD"], 4, 2]]), {"grounded": False, "named": True, "rows": False})
        follow_up = Turn(trace("and again?", "megD and Raydish are 2-2 in 4 sets."), earlier, NAMES)
        self.assertEqual(checked(follow_up, rows=[[[142100, "megD"], 4, 2]]), {"grounded": True, "named": True, "rows": True})

    def test_the_line_the_page_showed_after_the_previous_turn_is_in_the_window(self):
        card = ("Stat cards, at official events. A comparison card of Phazon in 2v2 only 63 results, GOLD 12, SILVER 15,"
                " BRONZE 6, TOP 8 51; Phazon in both modes together 139 results, GOLD 12.")
        asked = "on the card, where does phazon's 12 gold come from?"
        answer = "Phazon's 2v2 figures on the card: **GOLD** 12 and **TOP 8**: 51."
        shown = dict(trace("cody travis vs phazon head to head", "Phazon leads 5-1."), shown=card)
        self.assertTrue(checked(Turn(trace(asked, answer), shown, NAMES))["grounded"])
        unshown = trace("cody travis vs phazon head to head", "Phazon leads 5-1.")
        self.assertFalse(checked(Turn(trace(asked, answer), unshown, NAMES))["grounded"])
        own = dict(trace(asked, answer), shown=card)  # a turn's own card comes after its answer
        self.assertFalse(checked(Turn(own, unshown, NAMES))["grounded"])

    def test_a_pattern_takes_alternatives_and_a_player_id_counts_as_its_returned_name(self):
        turn = Turn(trace("q", "2-2.", RESOLVED, RECORD), None, NAMES)
        self.assertTrue(checked(turn, rows=[["megD", 4, 2], [["nobody", 160000], 2]])["rows"])
        self.assertFalse(checked(turn, rows=[["Raydish", 4]])["rows"])  # no tool returned Raydish's name
        self.assertTrue(checked(turn, rows_any=[["Raydish", 4], [142100, 4]])["rows_any"])


class AnswerTest(unittest.TestCase):
    def test_grounded_flags_numbers_and_player_ids_the_window_doesnt_hold(self):
        turn = Turn(trace("what about megd vs raydish", "megD (player_id 147569) leads 3-1 in 4 sets.", RESOLVED, RECORD),
                    None, NAMES)
        self.assertEqual(score_turn(turn, {})["grounded"], {"passed": False,
                                                            "detail": "not in the window: 147569, 3-1"})
        self.assertTrue(checked(turn, grounded=False)["grounded"])

    def test_named_flags_a_player_named_only_by_id(self):
        self.assertFalse(checked(Turn(trace("q", "1st: **Player 147569** and Raydish."), None, NAMES), grounded=False)["named"])
        self.assertTrue(checked(Turn(trace("q", "1st: capsar (player_id 147569)."), None, NAMES), grounded=False)["named"])

    def test_text_and_number_checks_read_the_answer_in_any_case_and_through_bold(self):
        turn = Turn(trace("q", "Their teams met in **5** sets: Raydish's side won 2 and lost 3."), None, NAMES)
        self.assertEqual(checked(turn, grounded=False, says=["RAYDISH'S side"], says_any=["no", "met in 5"],
                                 not_says=["Addymestic"], says_numbers=[5, 2, 3]),
                         {"grounded": True, "named": True, "says": True, "says_any": True, "not_says": True,
                          "says_numbers": True})
        self.assertFalse(checked(turn, grounded=False, says_numbers=[4])["says_numbers"])

    def test_says_record_wants_the_record_in_a_sentence_about_it_in_any_wording(self):
        spec = {"record": [2, 3], "about": ["2v2", "team", "side"]}
        right = ["Raydish's side is **2-3** in 2v2.", "- **Raydish's team**: Won **2 sets**, lost **3 sets**.",
                 "- **Raydish's team**: 2 wins, 3 losses", "In 2v2, Raydish's side won 2 and lost 3.",
                 "They met 5 times in 2v2, with Raydish's team winning 2 sets and whoiskyna's team winning 3 sets."]
        wrong = ["Raydish leads 5-2 in 1v1: whoiskyna won 3-2 at BCX 2022. The 2v2 sets (5 total) aren't in it.",
                 "Raydish's side won 2 of them.", "In 2v2, Raydish's team won 3 and lost 2.", "Is it 2-3 in 2v2?"]
        for answer in right + wrong:
            turn = Turn(trace("q", answer), None, NAMES)
            self.assertEqual(checked(turn, grounded=False, says_record=spec)["says_record"], answer in right, answer)


    def test_says_record_reads_a_list_item_with_the_line_introducing_its_list(self):
        spec = {"record": [1, 5], "about": ["1v1", "sets"]}
        right = ["Cody Travis and Phazon met in **6 official 1v1 sets**. Here's their record:\n\n"
                 "- **Cody Travis**: 1 win (7 games), 5 losses (15 games)\n- **Phazon**: 5 wins, 1 loss",
                 "### 1v1 record (6 sets total)\n- Cody Travis: 1 win, 5 losses"]
        wrong = ["Here's their record:\n- Cody Travis: 1 win, 5 losses",
                 "They met in 6 sets overall:\n- 2v2: Cody Travis's team won 1 and lost 5"]
        for answer in right + wrong:
            turn = Turn(trace("q", answer), None, NAMES)
            self.assertEqual(checked(turn, grounded=False, says_record=spec)["says_record"], answer in right, answer)


class CallsTest(unittest.TestCase):
    def test_only_calls_that_ran_count_as_using_a_player(self):
        refused = call("head_to_head", {"player_id": 222222, "opponent_id": 160000},
                       {"error": "player_id 222222 wasn't returned"}, unreturned_players=[222222])
        turn = Turn(trace("q", "", RESOLVED, refused, RECORD), None, NAMES)
        self.assertEqual(checked(turn, grounded=False, players=[142100, 160000], not_players=[222222],
                                 calls=["head_to_head"]),
                         {"grounded": True, "named": True, "players": True, "not_players": True, "calls": True})
        self.assertFalse(checked(turn, grounded=False, calls=["player_results"])["calls"])

    def test_not_calls_and_not_looked_up_read_every_call_the_loops_own_lookups_included(self):
        forced = call("resolve_event", {"name": "say cody travis 24"},
                      {"name": "say cody travis 24", "status": "not_found", "events": []}, forced=True)
        turn = Turn(trace("q", "", RESOLVED, forced), None, NAMES)  # live, 20261120T050251Z-001 turn 7
        self.assertEqual(checked(turn, grounded=False, not_calls=["head_to_head"], not_looked_up=["two"]),
                         {"grounded": True, "named": True, "not_calls": True, "not_looked_up": True})
        self.assertEqual(score_turn(turn, {"not_looked_up": ["say", "24"]})["not_looked_up"],
                         {"passed": False, "detail": "looked up resolve_event('say cody travis 24')"})
        self.assertFalse(checked(turn, grounded=False, not_calls=["resolve_event"])["not_calls"])
        self.assertFalse(checked(turn, grounded=False, not_looked_up=["MEGD"])["not_looked_up"])  # any case

    def test_unconfirmed_at_most_counts_the_claims_the_number_check_replaced(self):
        replaced = Turn({**trace("q", "x"), "unconfirmed": [{"claim": "a"}, {"claim": "b"}]}, None, NAMES)
        self.assertEqual(score_turn(replaced, {"unconfirmed_at_most": 1})["unconfirmed_at_most"],
                         {"passed": False, "detail": "2 claims replaced"})
        self.assertTrue(checked(replaced, grounded=False, unconfirmed_at_most=2)["unconfirmed_at_most"])
        self.assertTrue(checked(Turn(trace("q", "x"), None, NAMES), grounded=False, unconfirmed_at_most=0)["unconfirmed_at_most"])

    def test_suggests_wants_suggestions_with_the_player_first(self):
        asked = Turn(trace("q", "I couldn't find...", outcome="suggestions", suggestions={"raydishes": [160000, 24]}),
                     None, NAMES)
        self.assertTrue(checked(asked, suggests=160000)["suggests"])
        self.assertFalse(checked(asked, suggests=24)["suggests"])


class PlayTest(unittest.TestCase):
    def test_the_page_line_goes_to_the_conversation_after_its_turn(self):
        class Fake:  # react.Conversation as play uses it
            def __init__(self):
                self.calls, self.last = [], None

            def ask(self, say):
                self.calls.append(("ask", say))
                self.last = {"question": say, "answer": "a", "steps": []}
                return self.last

            def shown(self, line):
                self.calls.append(("shown", line))
                self.last["shown"] = line
        fake = Fake()
        played = conversations.play({"turn": [{"say": "q1", "shown": "Card: Phazon,\n 2v2: 12 1st"}, {"say": "q2"}]}, fake)
        self.assertEqual(fake.calls, [("ask", "q1"), ("shown", "Card: Phazon, 2v2: 12 1st"), ("ask", "q2")])
        self.assertEqual(([t["turn"] for t in played], played[0]["shown"], "shown" in played[1]),
                         ([1, 2], "Card: Phazon, 2v2: 12 1st", False))


class ScoringTest(unittest.TestCase):
    DATA = {"conversation": [{"id": "x1", "title": "a secret title", "turn": [
        {"say": "q1", "expect": "e", "says": ["secret"]}, {"say": "q2", "expect": "e"}]}]}
    RECORDS = [{"id": "x1", "seed": 0, "turns": [trace("q1", "the secret"), trace("q2", "Player 147569 won.")]}]

    def test_a_played_conversation_is_scored_turn_by_turn_with_each_failing_checks_detail(self):
        (scored,) = conversations.score(self.DATA, self.RECORDS, NAMES)
        self.assertEqual([t["passed"] for t in scored["turns"]], [True, False])
        self.assertEqual(scored["turns"][1]["checks"]["named"], {"passed": False, "detail": "names 'Player 147569'"})
        lines = conversations.report([("R", [scored])], self.DATA)
        self.assertIn("| x1 a secret title | 1 | pass |", lines)
        self.assertIn("|  | 2 | grounded, named |", lines)  # no tool returned 147569 either
        self.assertEqual(lines[-1], "**R:** 1/2 (50%) turns pass every check, and 0/1 (0%) conversations pass in every turn.")

    def test_a_held_out_set_is_scored_and_reported_without_its_text(self):
        data = {**self.DATA, "heldout": True}
        scored = conversations.score(data, self.RECORDS, NAMES)
        report = "\n".join(conversations.report([("R", scored)], data))
        self.assertNotIn("secret", json.dumps(scored) + report)
        self.assertNotIn("147569", json.dumps(scored) + report)
        self.assertIn("| x1 | 1 | pass |\n|  | 2 | grounded, named |", report)

    def test_a_conversation_is_played_turn_after_turn_in_one_conversation(self):
        class Asked:
            def __init__(self):
                self.questions = []

            def ask(self, question):
                self.questions.append(question)
                return {"question": question, "answer": f"answer {len(self.questions)}"}

        asked = Asked()
        turns = conversations.play(self.DATA["conversation"][0], asked)
        self.assertEqual((asked.questions, [t["turn"] for t in turns], turns[1]["answer"]), (["q1", "q2"], [1, 2], "answer 2"))


if __name__ == "__main__":
    unittest.main()
