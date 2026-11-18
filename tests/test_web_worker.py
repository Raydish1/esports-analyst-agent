import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))
import replay  # noqa: E402
import worker as workers  # noqa: E402


class FakeAgent:
    def __init__(self, fail=None):
        self.asked, self.fail = [], fail

    def ask(self, question, emit):
        self.asked.append(question)
        if self.fail:
            raise self.fail
        emit({"type": "thinking", "step": 1})
        return {"type": "answer", "text": f"answer to {question}"}


class CardAgent(FakeAgent):
    def __init__(self, cards):
        super().__init__()
        self.cards = cards

    def figures(self):
        if isinstance(self.cards, Exception):
            raise self.cards
        return self.cards


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def types(job):
    return [e["type"] for e in job.events]


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.agents = []
        self.worker = workers.Worker(self.agent, max_waiting=3, conversations=3, idle=60, clock=self.clock)

    def agent(self):
        self.agents.append(FakeAgent())
        return self.agents[-1]

    def test_questions_run_in_order_and_waiting_ones_hear_their_position(self):
        a, b = self.worker.open(), self.worker.open()
        first, second = self.worker.submit(a.id, "one"), self.worker.submit(b.id, "two")
        self.assertEqual((first.position, second.position), (1, 2))
        self.assertTrue(self.worker.run_next())
        self.assertEqual(types(first), ["queued", "started", "thinking", "answer", "done"])
        self.assertEqual(first.events[3]["text"], "answer to one")
        self.assertEqual([e["position"] for e in second.events if e["type"] == "queued"], [2, 1])
        self.assertTrue(first.finished)
        self.assertFalse(second.finished)
        self.worker.run_next()
        self.assertEqual(types(second)[-3:], ["thinking", "answer", "done"])
        self.assertFalse(self.worker.run_next())

    def test_a_conversation_asks_one_question_at_a_time(self):
        a = self.worker.open()
        self.worker.submit(a.id, "one")
        with self.assertRaises(workers.Busy):
            self.worker.submit(a.id, "two")
        self.worker.run_next()
        self.worker.submit(a.id, "two")
        self.worker.run_next()
        self.assertEqual(self.agents[0].asked, ["one", "two"])

    def test_the_queue_has_a_limit(self):
        sessions = [self.worker.open() for _ in range(3)]
        for s in sessions:
            self.worker.submit(s.id, "q")
        self.worker.sessions["extra"] = workers.Session(FakeAgent())
        self.worker.sessions["extra"].id = "extra"
        with self.assertRaises(workers.Full):
            self.worker.submit("extra", "q")

    def test_an_unknown_conversation(self):
        with self.assertRaises(KeyError):
            self.worker.submit("nope", "q")

    def test_idle_conversations_expire_and_the_oldest_idle_one_makes_room(self):
        a = self.worker.open()
        self.clock.now = 61
        b = self.worker.open()
        self.assertNotIn(a.id, self.worker.sessions)
        self.clock.now = 62
        c, d = self.worker.open(), self.worker.open()
        self.clock.now = 63
        self.worker.open()  # full: b, the oldest idle one, goes
        self.assertNotIn(b.id, self.worker.sessions)
        self.assertIn(c.id, self.worker.sessions)
        self.assertIn(d.id, self.worker.sessions)

    def test_all_busy_and_full(self):
        for _ in range(3):
            self.worker.submit(self.worker.open().id, "q")
        with self.assertRaises(workers.Full):
            self.worker.open()

    def test_an_error_ends_the_job_with_a_message(self):
        a = self.worker.open()
        a.agent.fail = replay.Mismatch("asked for step 3")
        job = self.worker.submit(a.id, "one")
        self.worker.run_next()
        self.assertEqual(types(job)[-2:], ["error", "done"])
        self.assertIn("doesn't match the current agent", job.events[-2]["message"])
        self.assertFalse(a.busy)
        a.agent.fail = LookupError("There's no recording of this question.")
        job = self.worker.submit(a.id, "two")
        self.worker.run_next()
        self.assertEqual(job.events[-2]["message"], "There's no recording of this question.")

    def test_the_cards_follow_the_answer_and_a_failing_card_is_left_out(self):
        worker = workers.Worker(lambda: CardAgent([{"kind": "lifetime"}]))
        job = worker.submit(worker.open().id, "one")
        worker.run_next()
        self.assertEqual(types(job)[-3:], ["answer", "figures", "done"])
        self.assertEqual(job.events[-2]["figures"], [{"kind": "lifetime"}])
        for cards in ([], RuntimeError("a card failed")):
            worker = workers.Worker(lambda: CardAgent(cards))
            job = worker.submit(worker.open().id, "one")
            worker.run_next()
            self.assertEqual(types(job)[-2:], ["answer", "done"])

    def test_wait_gives_the_events_after_a_number(self):
        a = self.worker.open()
        job = self.worker.submit(a.id, "one")
        self.worker.run_next()
        found, finished = job.wait(3, timeout=0)
        self.assertTrue(finished)
        self.assertEqual([e["type"] for _, e in found], ["answer", "done"])
        self.assertEqual([n for n, _ in found], [3, 4])


if __name__ == "__main__":
    unittest.main()
