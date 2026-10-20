import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ask  # noqa: E402
import react  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402  the tiny database and a scripted model

HEADER = {"run": "S", "title": "Agent session S", "model": "m", "variant": "v", "think": True, "seeds": [0],
          "max_steps": 8, "ollama": "x", "snapshot": {"file": "f", "build_id": "b"}}


def reader(*lines):
    """What a person types, line by line, then the end of the input."""
    lines = iter(lines)

    def read(prompt):
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None
    return read


class TraceTest(unittest.TestCase):
    def test_a_thought_is_shown_by_its_last_sentences(self):
        self.assertEqual(ask.thought("Find megd. Then count the results."), "Find megd. Then count the results.")
        long = "Okay, the user asks about megd. " * 20 + "So I'll query v_team_results by player_id 142100."
        self.assertEqual(ask.thought(long, width=60), "... So I'll query v_team_results by player_id 142100.")
        self.assertEqual(ask.thought(" \n"), "(no thinking)")

    def test_observations_are_shown_in_short(self):
        resolved = {"name": "megd", "status": "confident", "note": "Use player_id 7.",
                    "candidates": [{"player_id": 7, "name": "megD", "match": "display name", "official_results": 2}]}
        self.assertEqual(ask.observed(json.dumps(resolved)), ["confident: 7 megD (display name, 2 official results)"])
        rows = {"complete": True, "columns": ["a", "b"], "rows": [[i, None] for i in range(12)], "row_count": 12}
        lines = ask.observed(json.dumps(rows))
        self.assertEqual(lines[:4], ["12 rows", "a | b", "0 | NULL", "1 | NULL"])
        self.assertEqual(lines[-1], "(7 more rows went to the model)")
        too_big = {"complete": False, "note": "Too large to show: ...", "row_count": 455, "columns": ["a", "b"]}
        self.assertEqual(ask.observed(json.dumps(too_big)),
                         ["455 rows, too large to show: no rows went to the model", "a | b"])
        self.assertEqual(ask.observed(json.dumps({"error": "no such column: x"})), ["error: no such column: x"])

    def test_a_step_shows_its_thought_tool_calls_observations_and_answer_check(self):
        step = {"step": 2, "seconds": 3.25, "thinking": "Now count them.", "content": "",
                "tool_calls": [{"name": "run_sql", "arguments": {"query": "SELECT 1"}, "observation":
                                json.dumps({"complete": True, "columns": ["n"], "rows": [[1]], "row_count": 1})},
                               {"name": "resolve_player", "arguments": {"name": "x"}, "observation": None}],
                "answer_check": {"names": {"tike36": [14]}, "action": "sent back"},
                "size_check": {"action": "kept: no steps left to query again"}}
        self.assertEqual(ask.step_lines(step), [
            "Step 2 (3.2 s): Now count them.", "  -> run_sql: SELECT 1", "  <- 1 row", "     n", "     1",
            "  -> resolve_player: x", "  <- not run: no steps left",
            "  !! result-size check: answered right after a result too large to show (kept: no steps left to query again)",
            "  !! answer check: it names tike36, which no tool returned (sent back)"])


class SessionTest(Fixture):
    def setUp(self):
        super().setUp()
        self.out, self.transcript = [], Path(self.tmp.name) / "sessions" / "S"

    def session(self, *replies, on_step=None):
        self.model = Scripted(*replies)
        conversation = react.Conversation(react.Tools(self.path), ask=self.model, log=lambda *_: None, on_step=on_step)
        return ask.Session(conversation, self.transcript, HEADER)

    def test_questions_one_after_another_until_exit_with_the_transcript_rewritten_after_each(self):
        session = self.session(reply(calls=[("resolve_player", {"name": "megd"})]), reply("megD has 2 official results."),
                               reply("In 2v2, megD has 2."))
        read = reader("How many results has megd?", "", "  now only 2v2 ", "exit", "never asked")
        ask.interactive(session, read=read, out=self.out.append)
        self.assertEqual([t["question"] for t in session.traces], ["How many results has megd?", "now only 2v2"])
        self.assertIn("megD has 2 official results.", self.out)
        self.assertIn("In 2v2, megD has 2.", self.out)
        self.assertEqual(self.model.sent[2][1]["content"], "How many results has megd?")  # the follow-up's history
        page = self.transcript.with_suffix(".md").read_text(encoding="utf-8")
        self.assertIn("# Agent session S", page)
        self.assertIn("## 2. now only 2v2", page)
        lines = self.transcript.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["turn"] for line in lines], [1, 2])

    def test_the_end_of_the_input_ends_a_session_and_trace_prints_each_step(self):
        printed = []
        session = self.session(reply(calls=[("resolve_player", {"name": "megd"})], thinking="Find megd first."),
                               reply("megD."), on_step=lambda step: printed.extend(ask.step_lines(step)))
        ask.interactive(session, read=reader("Who is megd?"), out=self.out.append)
        self.assertEqual(len(session.traces), 1)
        self.assertEqual(printed[:3], ["Step 1 (0.0 s): Find megd first.", "  -> resolve_player: megd",
                                       "  <- confident: 7 megD (display name, 2 official results)"])
        self.assertEqual(printed[-1], "Step 2 (0.0 s): (no thinking)")

    def test_an_unfinished_question_says_so(self):
        out = []
        ask.report({"outcome": "step limit", "answer": None, "steps_used": 8, "model_seconds": 41.5}, out.append)
        self.assertEqual(out, ["", "(No answer: step limit.)", "(8 steps, 41.5 s)"])


if __name__ == "__main__":
    unittest.main()
