import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import react  # noqa: E402
import retrieval  # noqa: E402
from test_agent import Fixture, Scripted, reply  # noqa: E402  the tiny database and a scripted model

CHROMA = importlib.util.find_spec("chromadb") is not None  # not on Windows ARM64's Python (retrieval's docstring)
WORDS = ["partner", "won", "record", "worlds", "medal"]


def embed(texts):
    """A stand-in for nomic-embed-text: one dimension per word of WORDS the text has, plus a small constant."""
    return [[float(w in text.lower()) for w in WORDS] + [0.1] for text in texts]


def example(i, question, shape="s"):
    return {"id": i, "shape": shape, "question": question, "note": f"note {i}", "sql": f"SELECT {i!r}"}


class MmrTest(unittest.TestCase):
    def test_mmr_takes_the_closest_first_then_trades_a_near_copy_for_a_different_one(self):
        candidates = [("a", 0.9, [1.0, 0.0]), ("b", 0.89, [1.0, 0.01]), ("c", 0.8, [0.0, 1.0])]
        self.assertEqual([i for i, _, _ in retrieval.mmr(candidates, k=2, lam=0.7)], ["a", "c"])
        self.assertEqual([i for i, _, _ in retrieval.mmr(candidates, k=2, lam=1.0)], ["a", "b"])  # similarity alone
        self.assertEqual(retrieval.mmr([], k=3), [])

    def test_the_prompt_puts_the_examples_and_what_they_are_before_the_question(self):
        found = {"examples": [{**example("ex08", "Who has Phazon partnered with in 2v2?"), "similarity": 0.8, "mmr": 0.5}]}
        text = retrieval.prompt("Who has megd played with?", found)
        self.assertTrue(text.startswith(retrieval.NOTE))
        self.assertIn("query patterns, not facts about players", text)
        self.assertIn("Example 1: Who has Phazon partnered with in 2v2?\nSELECT 'ex08'\nWhy: note ex08", text)
        self.assertTrue(text.endswith("\n\nQuestion: Who has megd played with?"))
        self.assertEqual(retrieval.prompt("q", {"examples": []}), "q")
        self.assertEqual(retrieval.prompt("q", None), "q")


@unittest.skipUnless(CHROMA, "chromadb isn't installed for this Python")
class RetrieverTest(unittest.TestCase):
    def setUp(self):
        import chromadb
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # Windows can keep an index file open
        self.client = chromadb.PersistentClient(path=self.tmp.name, settings=chromadb.Settings(anonymized_telemetry=False))
        self.bank = [example("e1", "Who has X partnered with?", "teammates"), example("e2", "Who has won the most?", "ranking"),
                     example("e3", "What is X's record against Y?", "head_to_head")]

    def tearDown(self):
        self.client.clear_system_cache()  # releases the store's files
        self.tmp.cleanup()

    def test_a_question_retrieves_the_closest_examples_above_the_threshold(self):
        retriever = retrieval.Retriever(self.bank, embed=embed, client=self.client)
        found = retriever.retrieve("who did megd partner with most?", k=2, threshold=0.5)
        self.assertEqual([e["id"] for e in found["examples"]], ["e1"])  # the others are below 0.5
        first = found["examples"][0]
        self.assertEqual((first["shape"], first["sql"], first["note"], found["candidates"]), ("teammates", "SELECT 'e1'", "note e1", 1))
        self.assertGreater(first["similarity"], 0.9)
        self.assertEqual(retriever.retrieve("hello there", threshold=0.5)["examples"], [])

    def test_the_collection_is_rebuilt_when_a_question_changes(self):
        retrieval.Retriever(self.bank, embed=embed, client=self.client)
        changed = [self.bank[0], example("e2", "Who has the most medals?", "ranking"), self.bank[2]]
        retriever = retrieval.Retriever(changed, embed=embed, client=self.client)
        found = retriever.retrieve("medal count leaders", k=1, threshold=0.5)
        self.assertEqual([e["question"] for e in found["examples"]], ["Who has the most medals?"])


class FakeRetriever:
    """Retrieves the same examples for every question."""

    def __init__(self, *examples):
        self.found = {"threshold": 0.7, "candidates": len(examples), "examples": list(examples)}

    def retrieve(self, question, threshold=0.7):
        return self.found


class MeasureTest(unittest.TestCase):
    def test_a_hit_is_a_helpful_shape_in_the_top_k_and_questions_no_shape_helps_are_counted_apart(self):
        found = [{**example("e1", "q1", "ranking"), "similarity": 0.8, "mmr": 0.5},
                 {**example("e2", "q2", "teammates"), "similarity": 0.75, "mmr": 0.3}]
        questions = [{"id": "q01", "question": "a"}, {"id": "q02", "question": "b"}, {"id": "q03", "question": "c"},
                     {"id": "q09", "question": "d"}]
        shapes = {"q01": ["teammates"], "q02": ["ranking"], "q03": ["medals"], "q09": []}
        rows = retrieval.measure(FakeRetriever(*found), questions, shapes)
        self.assertEqual([(r["hit"], r["first"]) for r in rows], [(True, False), (True, True), (False, False), (None, None)])
        self.assertEqual(retrieval.summarize(rows), {"questions": 4, "labelled": 3, "hit_at_k": 2, "hit_at_1": 1,
                                                     "examples_for_labelled": 6, "unlabelled": 1,
                                                     "examples_for_unlabelled": 2, "misses": ["q03"]})


class ConversationTest(Fixture):
    def test_the_examples_go_to_the_model_with_the_question_and_the_history_keeps_the_bare_question(self):
        shown = {**example("ex08", "Who has tike36 partnered with in 2v2?", "teammates"), "similarity": 0.8, "mmr": 0.56}
        ask = Scripted(reply(calls=[("resolve_player", {"name": "megd"})]), reply("**tike36** is megD's partner."),
                       reply("megD's partners aren't known yet."), reply(calls=[("run_sql", {"query": "SELECT 1"})]),
                       reply("Still unknown."))
        conversation = react.Conversation(react.Tools(self.path), ask=ask, log=lambda *_: None,
                                          retriever=FakeRetriever(shown))
        trace = conversation.ask("Who has megd partnered with?")
        sent = ask.sent[0][-1]["content"]
        self.assertTrue(sent.startswith(retrieval.NOTE) and sent.endswith("Question: Who has megd partnered with?"))
        self.assertEqual(trace["examples"]["examples"], [shown])
        self.assertIn("Example 1", ask.sent[2][1]["content"])  # every step of the question sees them
        # tike36 came only from an example, which isn't what the conversation showed: the answer check flags it
        self.assertEqual(trace["steps"][1]["answer_check"]["names"], {"tike36": [14]})
        conversation.ask("and in 1v1?")
        self.assertEqual(ask.sent[3][1], {"role": "user", "content": "Who has megd partnered with?"})  # the next question's history
        self.assertIn("Question: and in 1v1?", ask.sent[3][-1]["content"])

    def test_without_a_retriever_the_question_goes_alone(self):
        ask = Scripted(reply("Glad to help."))
        trace = react.run("thanks", react.Tools(self.path), ask=ask, log=lambda *_: None)
        self.assertEqual((ask.sent[0][-1]["content"], trace["examples"], react.summary(trace)["examples"]), ("thanks", None, None))

    def test_every_trace_logs_the_retrieved_examples_and_their_scores(self):
        shown = {**example("ex08", "Who has Phazon partnered with in 2v2?", "teammates"), "similarity": 0.8, "mmr": 0.56}
        seen = []
        conversation = react.Conversation(react.Tools(self.path), ask=Scripted(reply("Glad to help.")), log=lambda *_: None,
                                          retriever=FakeRetriever(shown), on_examples=seen.append)
        trace = {"number": 6, **conversation.ask("thanks")}
        self.assertEqual(seen, [trace["examples"]])  # as the question starts, for ask.py --trace
        self.assertEqual(react.summary(trace)["examples"], {"threshold": 0.7, "candidates": 1, "examples": [
            {"id": "ex08", "shape": "teammates", "similarity": 0.8, "mmr": 0.56}]})
        header = {"run": "R", "model": "m", "variant": "v", "think": True, "seeds": [0], "max_steps": 8, "ollama": "x",
                  "snapshot": {"file": "f", "build_id": "b"}}
        page = react.markdown([trace], header)
        self.assertIn("**Retrieved examples** (1 of the 10 most similar at 0.7 or more; similarity, then MMR score):\n\n"
                      "- ex08 teammates, 0.800, 0.560: Who has Phazon partnered with in 2v2?", page)
        empty = {"number": 6, **react.Conversation(react.Tools(self.path), ask=Scripted(reply("Glad to help.")),
                                                   log=lambda *_: None, retriever=FakeRetriever()).ask("thanks")}
        self.assertIn("**Retrieved examples** (0 of the 10 most similar at 0.7 or more; similarity, then MMR score):\n\n- none",
                      react.markdown([empty], header))

    def test_ask_trace_prints_the_examples_before_the_steps(self):
        import ask
        found = {"threshold": 0.7, "candidates": 1,
                 "examples": [{**example("ex08", "Who has Phazon partnered with?", "teammates"), "similarity": 0.8, "mmr": 0.56}]}
        self.assertEqual(ask.example_lines(found), ["Examples (similarity, MMR score):",
                                                    "  ex08 teammates 0.800, 0.560: Who has Phazon partnered with?"])
        self.assertEqual(ask.example_lines({**found, "examples": []}), ["Examples: none at 0.7 or more"])


class BankTest(unittest.TestCase):
    def test_the_bank_has_about_25_examples_of_varied_shapes_each_with_a_one_line_note(self):
        examples = retrieval.load()
        self.assertGreaterEqual(len(examples), 25)
        self.assertGreaterEqual(len({e["shape"] for e in examples}), 15)
        for e in examples:
            self.assertNotIn("\n", e["note"].strip(), e["id"])
            self.assertIn(e.get("expect", "rows"), ("rows", "empty"), e["id"])
            self.assertTrue(e["sql"].lstrip().upper().startswith(("SELECT", "WITH")), e["id"])

    def test_a_missing_field_or_a_repeated_id_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "examples.toml"
            path.write_text('[[example]]\nid = "a"\nshape = "s"\nquestion = "q"\nsql = "SELECT 1"\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "has no note"):
                retrieval.load(path)
            one = 'id = "a"\nshape = "s"\nquestion = "q"\nnote = "n"\nsql = "SELECT 1"\n'
            path.write_text(f"[[example]]\n{one}[[example]]\n{one}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repeated example ids"):
                retrieval.load(path)

    def test_the_player_ids_a_query_filters_on_are_found(self):
        sql = ("SELECT * FROM v_head_to_head_2v2 WHERE player_id = 110 AND partner_id = 115695 AND"
               " (opponent1_id = 7 OR opponent2_id = -42) AND x.player_id IN (1, 2)")
        self.assertEqual(retrieval.player_ids(sql), [110, 115695, 7, -42, 1, 2])


if __name__ == "__main__":
    unittest.main()
