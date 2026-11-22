import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import react  # noqa: E402
import replay  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402  the tiny database and a scripted model


def trace(question, seed=0, **more):
    return {"question": question, "seed": seed, "steps": [], "answer": "a", "outcome": "answered", **more}


def write(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


class RecordingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def questions(self, **kw):
        return sorted(r.turns[0]["question"] for r in replay.recordings(self.root, **kw))

    def test_the_held_out_set_is_never_replayed(self):
        write(self.root / "20261117-heldout" / "traces.jsonl", trace("h1", set="existing"))
        write(self.root / "20261108-eval-on" / "traces.jsonl", trace("q1", set="existing"), trace("h2", set="heldout"))
        write(self.root / "20261110-smoke" / "traces.jsonl", trace("no set, after the held-out set began"))
        write(self.root / "20261020T011930Z" / "traces.jsonl", trace("no set, before"))
        write(self.root / "sessions" / "20261026T010000Z.jsonl", {**trace("s1"), "turn": 1})
        write(self.root / "sessions" / "20261109T010000Z.jsonl", {**trace("s2"), "turn": 1})
        write(self.root / "web" / "20261117T010000Z.jsonl", {**trace("mine"), "turn": 1})
        self.assertEqual(self.questions(), ["no set, before", "q1", "s1"])

    def test_a_session_is_one_recording_with_its_turns_in_order(self):
        write(self.root / "sessions" / "20261025T010000Z.jsonl", {**trace("follow"), "turn": 2},
              {**trace("did markiemoo win worlds"), "turn": 1})
        (found,) = replay.recordings(self.root)
        self.assertEqual(found.questions, ["did markiemoo win worlds", "follow"])

    def test_only_the_named_runs(self):
        write(self.root / "20261020T011930Z" / "traces.jsonl", trace("a"))
        write(self.root / "20261021T011930Z" / "traces.jsonl", trace("b"))
        self.assertEqual(self.questions(runs={"20261021T011930Z"}), ["b"])

    def test_another_backend_or_no_templates_isnt_replayed(self):
        for run, header in (("20261122-sonnet-templates", {"backend": "anthropic", "templates": "on"}),
                            ("20261122-qwen-sqlonly", {"model": "qwen3:30b", "templates": "off"}),
                            ("20261121-final-questions", {"model": "qwen3:30b"})):
            write(self.root / run / "traces.jsonl", trace(run, set="existing"))
            (self.root / run / "header.json").write_text(json.dumps(header), encoding="utf-8")
        self.assertEqual(self.questions(), ["20261121-final-questions"])


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.old = replay.Recording("20261010T000000Z", "20261010", 0, [trace("Who won BCX 2022?")])
        self.new1 = replay.Recording("20261108-eval-on", "20261108", 1, [trace("who won bcx 2022")])
        self.new0 = replay.Recording("20261108-eval-on", "20261108", 0, [trace("who won bcx 2022")])
        self.session = replay.Recording("session s", "20261025", 0, [trace("did markiemoo win worlds"),
                                                                     trace("the first one")])
        self.single = replay.Recording("20261117-templates", "20261117", 0, [trace("did markiemoo win worlds")])
        self.index = replay.Index([self.old, self.new1, self.new0, self.session, self.single])

    def test_the_newest_at_seed_0_and_spelling_doesnt_count(self):
        self.assertIs(self.index.match(["Who won BCX 2022 ?"]), self.new0)
        self.assertIs(self.index.match(["Who won BCX 2022"], current=self.old), self.old)
        self.assertIsNone(self.index.match(["something never asked"]))

    def test_a_follow_up_finds_the_session_that_has_it(self):
        self.assertIs(self.index.match(["did markiemoo win worlds"]), self.single)
        self.assertIs(self.index.match(["did markiemoo win worlds", "The first one."], current=self.single), self.session)

    def test_the_questions_offered(self):
        self.assertEqual(self.index.questions(), ["Who won BCX 2022?", "did markiemoo win worlds"])


class ReplayModelTest(Fixture):
    """Replay through the real loop: a recorded turn's replies, given back to react.Conversation, run the same tools."""

    def setUp(self):
        super().setUp()
        self.tools = react.Tools(self.path)
        ask = Scripted(reply(calls=[("resolve_player", {"name": "megd"})], thinking="Find megd first."),
                       reply(calls=[("run_sql", {"query": "SELECT COUNT(*) AS n FROM v_results WHERE player_id = 7"})]),
                       reply("megD has 2 official results."))
        self.recorded = react.run("How many results has megd?", self.tools, ask=ask, log=lambda *_: None)
        self.recorded = json.loads(json.dumps(self.recorded))  # as it is read back from a file

    def test_the_replay_runs_the_tools_again_and_gives_the_same_answer(self):
        waited = []
        model = replay.ReplayModel(self.recorded, sleep=waited.append)
        again = react.run("How many results has megd?", self.tools, ask=model, log=lambda *_: None)
        self.assertEqual((again["answer"], again["outcome"], model.left), (self.recorded["answer"], "answered", 0))
        observed = [c["observation"] for s in again["steps"] for c in s["tool_calls"]]
        self.assertEqual(observed, [c["observation"] for s in self.recorded["steps"] for c in s["tool_calls"]])
        self.assertEqual(len(waited), 0)  # the scripted steps took no time

    def test_a_check_that_now_sends_the_answer_back_is_a_mismatch(self):
        cut = {**self.recorded, "steps": self.recorded["steps"][:1]}  # the recording stops before the agent does
        with self.assertRaises(replay.Mismatch):
            react.run("How many results has megd?", self.tools, ask=replay.ReplayModel(cut), log=lambda *_: None)

    def test_recorded_time_is_scaled_and_capped(self):
        waited = []
        model = replay.ReplayModel({"steps": [{"seconds": 5, "content": "a"}, {"seconds": 80, "content": "b"}]},
                                   sleep=waited.append)
        model([]), model([])
        self.assertEqual(waited, [0.5, 2.0])

    def test_the_recorded_examples_come_back(self):
        retriever = replay.ReplayRetriever()
        self.assertEqual(retriever.retrieve("q")["examples"], [])  # a turn recorded without retrieval: none
        retriever.trace = {"examples": {"examples": [], "threshold": 0.7}}
        self.assertEqual(retriever.retrieve("q"), {"examples": [], "threshold": 0.7})


if __name__ == "__main__":
    unittest.main()
