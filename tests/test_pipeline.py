import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness  # noqa: E402
import pipeline  # noqa: E402
import react  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402

try:
    import langgraph  # noqa: F401
    LANGGRAPH = True
except ImportError:
    LANGGRAPH = False
COUNT = "SELECT COUNT(*) AS n FROM v_results WHERE player_id = 7"
QUESTION = "How many official results has megd?"
QUIET = {"log": lambda *_: None}


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


class VerifierReplayTest(Fixture):  # harness.py verify RUN: the verifier alone on a run's recorded answers
    def test_the_verifier_replays_on_a_runs_answers_resumes_and_counts_its_flags_by_verdict(self):
        tools = react.Tools(self.path)
        analyst = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]), reply(calls=[("run_sql", {"query": COUNT})]),
                           reply("megD has 2 official results."))
        right = react.run(QUESTION, tools, ask=analyst, **QUIET)
        wrong = {**right, "answer": "megD has 2 official results, as many as **Raydish**."}
        asked = {**right, "outcome": "suggestions"}
        traces = [{"id": "q01", "set": "existing", "seed": 0, **right}, {"id": "q01", "set": "existing", "seed": 1, **wrong},
                  {"id": "q02", "set": "existing", "seed": 0, **asked}, {"id": "h01", "set": "heldout", "seed": 0, **right}]
        judged = {("on", "q01", 0): {"verdict": "right"}, ("on", "q01", 1): {"verdict": "wrong"}}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(harness, "RAW", Path(folder)), \
                mock.patch.object(react, "load_env", lambda: None), mock.patch.object(react, "Tools", lambda: tools):
            (Path(folder) / "r").mkdir()
            (Path(folder) / "r" / "header.json").write_text(json.dumps({"model": "m", "arm": "on"}), encoding="utf-8")
            (Path(folder) / "r" / "traces.jsonl").write_text("".join(json.dumps(t) + "\n" for t in traces), encoding="utf-8")
            with mock.patch.object(pipeline, "chat", Scripted(verdict(), verdict([("as many as Raydish", "no row")]))):
                header, records = harness.verified("r", log=lambda *_: None)
            with mock.patch.object(pipeline, "chat", Scripted()):  # resumed: nothing left to verify
                _, again = harness.verified("r", log=lambda *_: None)
        self.assertEqual(([(r["id"], r["seed"]) for r in records], again), ([("q01", 0), ("q01", 1)], records))
        self.assertEqual([[(f["by"], f["check"]) for f in r["failures"]] for r in records],
                         [[], [("code", "name"), ("model", "unsupported")]])
        table = harness.verifier_table(records, judged, header["arm"])
        self.assertIn("| right | 1 | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) | 0/1 (0%) |", table)
        self.assertIn("| not right | 1 | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 0/1 (0%) |", table)
        self.assertIn("| code: name | 0 | 1 |", table)


class RouteTest(unittest.TestCase):
    def test_return_once_then_pass_or_revise_twice_then_abstain(self):
        failed = [{"by": "model"}]
        self.assertEqual([pipeline.route([], "x", 0, 0), pipeline.route(failed, "x", 2, 0), pipeline.route([], "", 0, 0),
                          pipeline.route([], "x", 0, 1), pipeline.route(failed, "", 1, 0), pipeline.route(failed, "x", 2, 1)],
                         ["return", "return", "pass", "pass", "revise", "abstain"])


class ReporterPromptTest(Fixture):
    def test_the_reporter_keeps_the_agents_reading_counting_and_answering_without_its_tools_and_steps(self):
        prompt = pipeline.reporter_prompt(self.path)
        for kept in ("Reading the packet", "- A word the question leaves open", "- A medal is a 1st, 2nd or 3rd place.",
                     "- Take every fact from the evidence packet: never answer from memory.",
                     "- Never tell the user to query the data", "- Describe a record by its numbers"):
            self.assertIn(kept, prompt)
        for dropped in ("Choosing a tool", "Using the tools", "Views", "- Pass the question's scope",
                        "- You have at most", "[The page showed", "Run every query"):
            self.assertNotIn(dropped, prompt)
        self.assertIn(f"from {react.coverage(self.path)[0]} on", " ".join(prompt.split()))


@unittest.skipUnless(LANGGRAPH, "langgraph isn't installed for this Python")
class PipelineTest(Fixture):
    def setUp(self):
        super().setUp()
        self.tools = react.Tools(self.path)
        self.analyst = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]), reply(calls=[("run_sql", {"query": COUNT})]),
                                reply("The analyst's own draft."))

    def test_a_draft_the_verifier_passes_is_the_answer_and_the_reporter_sees_only_the_question_and_the_packet(self):
        model = Scripted(reply("megD has 2 official results."), verdict())
        trace = pipeline.run(QUESTION, self.tools, ask=self.analyst, reply=model, **QUIET)
        self.assertEqual((trace["outcome"], trace["answer"]), ("answered", "megD has 2 official results."))
        self.assertEqual(trace["pipeline"], {"path": ["analyst", "reporter", "verifier"], "revisions": 0, "returns": 0,
                                             "analyst": [{"outcome": "evidence", "draft": "The analyst's own draft.",
                                                          "settled": None}]})
        self.assertEqual([(s["step"], s["role"]) for s in trace["steps"]],
                         [(1, "analyst"), (2, "analyst"), (3, "analyst"), (4, "reporter"), (5, "verifier")])
        self.assertEqual((trace["steps_used"], trace["output_tokens"]), (5, 50))
        (system, user), _ = model.sent
        packet = pipeline.packet_of({"steps": trace["steps"][:3]})
        self.assertEqual(system["content"], pipeline.reporter_prompt(self.path))
        self.assertEqual(user["content"], f"Question: {QUESTION}\n\nEvidence packet:\n{pipeline.shown(packet)}")
        self.assertNotIn("analyst's own draft", json.dumps(model.sent))
        self.assertEqual(trace["steps"][4]["verifier"]["decision"], "pass")

    def test_a_failed_draft_is_revised_at_most_twice_then_the_pipeline_abstains(self):
        model = Scripted(reply("megD has 13 official results."), verdict([("13", "the row gives 2")]),
                         reply("megD has 12 official results."), verdict([("12", "the row gives 2")]),
                         reply("megD has 11 official results."), verdict([("11", "the row gives 2")]))
        trace = pipeline.run(QUESTION, self.tools, ask=self.analyst, reply=model, **QUIET)
        self.assertEqual((trace["outcome"], trace["answer"]), ("abstained", pipeline.ABSTAIN))
        self.assertEqual(trace["pipeline"]["path"], ["analyst"] + ["reporter", "verifier"] * 3 + ["abstain"])
        self.assertEqual(trace["pipeline"]["revisions"], 2)
        draft, fix = model.sent[2][-2:]
        self.assertEqual(draft, {"role": "assistant", "content": "megD has 13 official results."})
        self.assertIn('- "13": is a number no result in the packet holds\n- "13": the row gives 2\n', fix["content"])
        self.assertEqual([s["verifier"]["decision"] for s in trace["steps"] if s["role"] == "verifier"],
                         ["revise", "revise", "abstain"])

    def test_a_packet_that_cant_answer_goes_back_to_the_analyst_once_and_keeps_both_passes(self):
        analyst = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]), reply("First draft."),
                           reply(calls=[("run_sql", {"query": COUNT})]), reply("Second draft."))
        model = Scripted(reply("megD's results weren't found."), verdict(answers=False, missing="megD's official results"),
                         reply("megD has 2 official results."), verdict(answers=False, missing="still nothing"))
        trace = pipeline.run(QUESTION, self.tools, ask=analyst, reply=model, **QUIET)
        self.assertEqual(trace["pipeline"]["path"], ["analyst", "reporter", "verifier"] * 2)
        self.assertEqual((trace["outcome"], trace["answer"], trace["pipeline"]["returns"]),
                         ("answered", "megD has 2 official results.", 1))  # once only: then a draft with no failures
        self.assertIn("[What was looked up doesn't answer this yet: megD's official results. Look up what it still"
                      " needs.]", analyst.sent[2][-1]["content"])
        self.assertEqual([m.get("tool_name") for m in analyst.sent[2] if m["role"] == "tool"], ["resolve_player"])  # its
        # first pass, with what it looked up
        fresh = model.sent[2]
        self.assertEqual(len(fresh), 2)  # a fresh draft from both passes' packet, not a revision
        self.assertIn('[1] resolve_player {"name": "megd"}', fresh[1]["content"])
        self.assertIn(f'[2] run_sql {{"query": "{COUNT}"}}', fresh[1]["content"])

    def test_names_the_question_matched_loosely_end_the_pipeline_with_suggestions(self):
        trace = pipeline.run("How many results has impala?", self.tools,
                             ask=Scripted(reply(calls=[("resolve_player", {"name": "impala"})])), reply=Scripted(), **QUIET)
        self.assertEqual((trace["outcome"], trace["pipeline"]["path"]), ("suggestions", ["analyst"]))
        self.assertTrue(trace["answer"])

    def test_the_trace_reads_as_the_loops_does(self):  # the harness writes traces.md with react.markdown
        trace = pipeline.run(QUESTION, self.tools, ask=self.analyst, reply=Scripted(reply("megD has 2."), verdict()),
                             **QUIET)
        header = {"run": "t", "model": "m", "variant": "v", "think": True, "seeds": [0], "max_steps": 8, "ollama": "0",
                  "snapshot": {"file": "f", "build_id": "b"}}
        self.assertIn("megD has 2.", react.markdown([{"id": "q1", "number": "q1", "seed": 0, **trace}], header))

    def test_the_diagram_for_the_slides_is_the_graphs_with_every_decision_named(self):  # docs/figures
        drawn = pipeline.diagram()
        for label in [*pipeline.EDGES.values(), "evidence", "suggestions or error"]:
            self.assertIn(f"&nbsp;{label}&nbsp;", drawn)
        self.assertNotIn(" -.-> ", drawn)  # a decision's edge with no label
        self.assertEqual(drawn.strip(), (ROOT / "docs" / "figures" / "three-agent-pipeline.mmd").read_text(encoding="utf-8").strip())

    def test_the_harness_answers_through_the_pipeline_when_asked(self):  # harness.py run --pipeline three-agent
        header = {"run": "t", "model": "m", "variant": "v", "think": True, "seeds": [0], "max_steps": 8, "ollama": "0",
                  "snapshot": {"file": "f", "build_id": "b"}}
        tools = react.Tools(self.path)
        model = Scripted(reply("megD has 2 official results."), verdict())
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(harness, "RAW", Path(folder)),                 mock.patch.object(react, "load_env", lambda: None),                 mock.patch.object(react, "retriever_or_exit", lambda on, fail: None),                 mock.patch.object(react, "run_header", lambda *a, **k: dict(header)),                 mock.patch.object(react, "Tools", lambda templates=True: tools),                 mock.patch.object(react, "chat", self.analyst), mock.patch.object(pipeline, "chat", model):
            harness.run([{"id": "q01", "set": "existing", "question": QUESTION}], [0], False, run_id="t",
                        log=lambda *_: None, pipeline="three-agent")
            written = json.loads((Path(folder) / "t" / "traces.jsonl").read_text(encoding="utf-8"))
            saved = json.loads((Path(folder) / "t" / "header.json").read_text(encoding="utf-8"))
        self.assertEqual((written["id"], written["outcome"], written["answer"]),
                         ("q01", "answered", "megD has 2 official results."))
        self.assertEqual((written["pipeline"]["path"], saved["pipeline"]), (["analyst", "reporter", "verifier"], "three-agent"))


if __name__ == "__main__":
    unittest.main()
