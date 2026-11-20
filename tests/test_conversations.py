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


class SetTest(unittest.TestCase):
    def test_the_set_has_no_problems(self):
        self.assertEqual(conversations.problems(conversations.load()), [])

    def test_a_turn_without_expect_or_with_an_unknown_check_is_a_problem_named_without_its_text(self):
        data = {"conversation": [{"id": "x1", "title": "t", "turn": [
            {"say": "a secret question", "expect": "", "rowz": [[1]]}, {"say": "s", "expect": "e", "check": "q09"}]}]}
        found = conversations.problems(data)
        self.assertEqual(found, ["x1 turn 1: no expect", "x1 turn 1: no check named 'rowz'",
                                 "x1 turn 2: check names 'q09', which has no stage 2 check"])  # q09 is unanswerable
        self.assertNotIn("secret", " ".join(found))


class WindowTest(unittest.TestCase):
    def test_a_turn_reads_its_own_results_and_the_previous_turns_only(self):
        earlier = trace("whats megd and raydish's record", "2-2.", RESOLVED, RECORD)
        middle = trace("thanks", "Glad to help.")
        late = Turn(trace("and again?", "megD and Raydish are 2-2 in 4 sets.", sql("SELECT 1", ["a"], [[1]])), middle, NAMES)
        self.assertEqual(checked(late, rows=[[[142100, "megD"], 4, 2]]), {"grounded": False, "named": True, "rows": False})
        follow_up = Turn(trace("and again?", "megD and Raydish are 2-2 in 4 sets."), earlier, NAMES)
        self.assertEqual(checked(follow_up, rows=[[[142100, "megD"], 4, 2]]), {"grounded": True, "named": True, "rows": True})

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


class CallsTest(unittest.TestCase):
    def test_only_calls_that_ran_count_as_using_a_player(self):
        refused = call("head_to_head", {"player_id": 222222, "opponent_id": 160000},
                       {"error": "player_id 222222 wasn't returned"}, unreturned_players=[222222])
        turn = Turn(trace("q", "", RESOLVED, refused, RECORD), None, NAMES)
        self.assertEqual(checked(turn, grounded=False, players=[142100, 160000], not_players=[222222],
                                 calls=["head_to_head"]),
                         {"grounded": True, "named": True, "players": True, "not_players": True, "calls": True})
        self.assertFalse(checked(turn, grounded=False, calls=["player_results"])["calls"])

    def test_suggests_wants_suggestions_with_the_player_first(self):
        asked = Turn(trace("q", "I couldn't find...", outcome="suggestions", suggestions={"raydishes": [160000, 24]}),
                     None, NAMES)
        self.assertTrue(checked(asked, suggests=160000)["suggests"])
        self.assertFalse(checked(asked, suggests=24)["suggests"])


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
