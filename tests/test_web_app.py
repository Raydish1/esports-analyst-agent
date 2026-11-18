import json
import os
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import react  # noqa: E402
import replay  # noqa: E402
import runner  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402  the tiny database and a scripted model

QUESTION = "How many results has megd?"


def read(client, job_id, last=None):
    """A job's events from its stream, until the stream ends."""
    headers = {"Last-Event-ID": str(last)} if last is not None else {}
    found = []
    with client.stream("GET", f"/api/jobs/{job_id}/events", headers=headers) as response:
        for line in response.iter_lines():
            if line.startswith("data: "):
                found.append(json.loads(line[6:]))
    return found


class AppTest(Fixture):
    """The server in replay mode, end to end: a recording made on the tiny database, replayed through the real loop."""

    def setUp(self):
        super().setUp()
        self.tools = runner.ProgressTools(self.path)
        ask = Scripted(reply(calls=[("resolve_player", {"name": "megd"})], thinking="Find megd first."),
                       reply(calls=[("run_sql", {"query": "SELECT COUNT(*) AS n FROM v_results WHERE player_id = 7"})]),
                       reply("megD has 2 official results."))
        recorded = json.loads(json.dumps(react.run(QUESTION, self.tools, ask=ask, log=lambda *_: None)))
        index = replay.Index([replay.Recording("run-a", "20261020", 0, [recorded])])
        source = runner.Replay(index, speed=0)
        self.client = TestClient(main.create_app(source, self.tools, examples=[QUESTION, "never recorded"],
                                                 static=Path(self.tmp.name) / "none"))

    def ask(self, question, conversation=None):
        conversation = conversation or self.client.post("/api/conversations").json()["conversation_id"]
        response = self.client.post(f"/api/conversations/{conversation}/questions", json={"question": question})
        self.assertEqual(response.status_code, 200, response.text)
        return conversation, response.json()["job_id"]

    def test_info_offers_only_recorded_examples(self):
        self.assertEqual(self.client.get("/api/info").json(), {"mode": "replay", "examples": [QUESTION]})

    def test_a_question_streams_its_progress_then_the_answer(self):
        _, job = self.ask(QUESTION)
        found = read(self.client, job)
        kinds = [e["type"] for e in found]
        self.assertEqual(kinds[0], "queued")
        self.assertEqual(kinds[-1], "done")
        self.assertEqual([e for e in kinds if e in ("thinking", "tool_started", "step")],
                         ["thinking", "tool_started", "step", "thinking", "tool_started", "step", "thinking", "step"])
        labels = [e["label"] for e in found if e["type"] == "tool_started"]
        self.assertEqual(labels, ["Looking up the player “megd”", "Running a query"])
        answer = next(e for e in found if e["type"] == "answer")
        self.assertEqual(answer["text"], "megD has 2 official results.")
        self.assertEqual(answer["replay"], {"source": "run-a", "seed": 0})
        query = [e for e in found if e["type"] == "step"][1]["calls"][0]
        self.assertEqual(query["result"]["tables"][0]["rows"], [[2]])

    def test_a_reconnecting_page_gets_only_what_it_missed(self):
        _, job = self.ask(QUESTION)
        everything = read(self.client, job)
        self.assertEqual(read(self.client, job, last=len(everything) - 3), everything[-2:])

    def test_a_question_with_no_recording(self):
        _, job = self.ask("never recorded")
        found = read(self.client, job)
        self.assertEqual([e["type"] for e in found][-2:], ["error", "done"])
        self.assertIn("no recording", found[-2]["message"])

    def test_a_follow_up_without_a_recording_is_refused_and_the_conversation_goes_on(self):
        conversation, job = self.ask(QUESTION)
        read(self.client, job)
        _, job = self.ask("now only 2v2", conversation)
        self.assertIn("follow-up", read(self.client, job)[-2]["message"])

    def test_the_page_is_always_revalidated(self):
        self.assertEqual(self.client.get("/missing.js").headers.get("cache-control"), "no-cache")
        self.assertNotEqual(self.client.get("/api/info").headers.get("cache-control"), "no-cache")

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/api/conversations/nope/questions", json={"question": "q"}).status_code, 404)
        conversation = self.client.post("/api/conversations").json()["conversation_id"]
        url = f"/api/conversations/{conversation}/questions"
        self.assertEqual(self.client.post(url, json={"question": ""}).status_code, 422)
        self.assertEqual(self.client.post(url, json={"question": "x" * 501}).status_code, 422)
        self.assertEqual(self.client.post(url, json={"question": "   "}).status_code, 422)
        self.assertEqual(self.client.get("/api/jobs/nope/events").status_code, 404)


class EarningsSettingTest(unittest.TestCase):
    def test_on_by_default_the_flag_wins_over_the_environment(self):
        self.assertTrue(main.card_earnings(None, None))
        self.assertFalse(main.card_earnings(None, "off"))
        self.assertTrue(main.card_earnings("on", "off"))
        self.assertFalse(main.card_earnings("off", None))
        with self.assertRaises(SystemExit):
            main.card_earnings(None, "maybe")


HEADER = {"run": "20261117T000000Z", "title": "Web app session", "model": "m", "variant": "v", "think": True,
          "seeds": [0], "max_steps": 8, "ollama": "x", "snapshot": {"file": "f", "build_id": "b"}}


class LiveTest(Fixture):
    """Live mode with a scripted model in place of the model server: the same events, and a transcript per conversation."""

    def setUp(self):
        super().setUp()
        self.folder = Path(self.tmp.name) / "web"
        self.tools = runner.ProgressTools(self.path)

    def client(self, chat):
        source = runner.Live(None, HEADER, self.folder, chat=chat)
        return TestClient(main.create_app(source, self.tools, examples=["any question"], static=self.folder / "none"))

    def ask(self, client, question):
        conversation = client.post("/api/conversations").json()["conversation_id"]
        job = client.post(f"/api/conversations/{conversation}/questions", json={"question": question}).json()["job_id"]
        return read(client, job)

    def test_live_mode_streams_and_saves_the_transcript(self):
        chat = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]), reply("megD has 2 official results."))
        client = self.client(chat)
        self.assertEqual(client.get("/api/info").json(), {"mode": "live", "examples": ["any question"]})
        found = self.ask(client, QUESTION)
        answer = next(e for e in found if e["type"] == "answer")
        self.assertEqual((answer["text"], "replay" in answer), ("megD has 2 official results.", False))
        (transcript,) = self.folder.glob("*.jsonl")
        self.assertEqual(json.loads(transcript.read_text(encoding="utf-8"))["question"], QUESTION)
        self.assertTrue(transcript.with_suffix(".md").exists())

    def test_the_model_server_address_never_reaches_the_page(self):
        def down(messages, **model):
            raise urllib.error.URLError("http://10.1.2.3:11434 refused the connection")

        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://10.1.2.3:11434"}):
            found = self.ask(self.client(down), QUESTION)
        answer = next(e for e in found if e["type"] == "answer")
        self.assertIn("request error", answer["problem"])
        self.assertNotIn("10.1.2.3", json.dumps(found))


if __name__ == "__main__":
    unittest.main()
