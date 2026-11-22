import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline  # noqa: E402
import react  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402

COUNT = "SELECT COUNT(*) AS n FROM v_results WHERE player_id = 7"
QUESTION = "How many official results has megd?"


def verdict(unsupported=(), answers=True, missing=""):
    return reply(json.dumps({"unsupported": [{"claim": c, "why": w} for c, w in unsupported],
                             "answers_question": answers, "missing": missing}))


class VerifierTest(Fixture):
    def setUp(self):
        super().setUp()
        self.tools = react.Tools(self.path)
        analyst = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]),
                           reply(calls=[("run_sql", {"query": COUNT}), ("run_sql", {"query": "SELECT nope FROM v_results"})]),
                           reply("The analyst's own draft: megD has 2."))
        conversation = react.Conversation(self.tools, ask=analyst, log=lambda *_: None, evidence_only=True)
        self.trace = conversation.ask(QUESTION)
        self.packet = pipeline.packet_of(self.trace)

    def verify(self, draft, *replies):
        sent = []
        judge = Scripted(*replies)
        failures, missing, step = pipeline.verify(self.tools, QUESTION, self.packet, draft,
                                                  reply=lambda m, **model: sent.append(model) or judge(m))
        return failures, missing, step, judge.sent, sent

    def test_the_packet_is_every_call_that_returned_data(self):
        self.assertEqual([(c["name"], json.loads(c["observation"]).get("rows")) for c in self.packet],
                         [("resolve_player", None), ("run_sql", [[2]])])  # the failed query isn't evidence
        shown = pipeline.shown(self.packet)
        self.assertTrue(shown.startswith('[1] resolve_player {"name": "megd"}\n{"name": "megd", "status": "confident"'))
        self.assertIn(f'[2] run_sql {{"query": "{COUNT}"}}\n', shown)
        self.assertEqual(pipeline.shown([]), pipeline.NO_DATA)

    def test_a_right_draft_passes_both_the_code_and_the_model(self):
        failures, missing, step, seen, sent = self.verify("megD has 2 official results.", verdict())
        self.assertEqual((failures, missing, step["role"], step["verifier"]["parsed"]), ([], "", "verifier", True))
        self.assertEqual(sent, [{"format": pipeline.VERDICT}])

    def test_the_model_sees_the_question_the_packet_and_the_draft_and_nothing_else(self):
        _, _, _, seen, _ = self.verify("megD has 2 official results.", verdict())
        (system, user), = seen
        self.assertEqual(system["content"], pipeline.VERIFIER)
        self.assertEqual(user["content"], f"Question: {QUESTION}\n\nEvidence packet:\n{pipeline.shown(self.packet)}\n\n"
                                          "Draft answer:\nmegD has 2 official results.")
        self.assertNotIn("analyst's own draft", json.dumps(seen))
        self.assertIn("A medal is a 1st, 2nd or 3rd place.", system["content"])  # the counting rules, from the prompt

    def test_the_loops_checks_and_the_model_each_find_what_the_packet_doesnt_hold(self):
        draft = "megD has 13 official results, as many as **Raydish**."  # 7 is megD's player_id here
        failures, missing, step, _, _ = self.verify(draft, verdict([("megD has 13", "the row gives 2")]))
        self.assertEqual([(f["by"], f["check"], f["claim"]) for f in failures],
                         [("code", "name", "Raydish"), ("code", "number", "13"), ("model", "unsupported", "megD has 13")])
        self.assertEqual(failures[2]["why"], "the row gives 2")
        self.assertEqual((missing, step["verifier"]["failures"]), ("", failures))

    def test_a_packet_that_cant_answer_the_question_says_what_is_missing(self):
        _, missing, _, _, _ = self.verify("megD has 2 official results.",
                                          verdict(answers=False, missing="megD's 2v2 results by year."))
        self.assertEqual(missing, "megD's 2v2 results by year.")
        _, missing, _, _, _ = self.verify("megD has 2 official results.", verdict(answers=False))
        self.assertEqual(missing, "what the question asks")

    def test_a_reply_that_isnt_the_json_asked_for_adds_nothing_and_is_marked(self):
        failures, missing, step, _, _ = self.verify("megD has 13 official results.", reply("Looks fine to me."))
        self.assertEqual(([f["by"] for f in failures], missing, step["verifier"]["parsed"]), (["code"], "", False))

    def test_an_empty_draft_fails(self):
        failures, _, _, _, _ = self.verify("", verdict())
        self.assertEqual([(f["check"], f["why"]) for f in failures], [("empty", "no answer was written")])


if __name__ == "__main__":
    unittest.main()
