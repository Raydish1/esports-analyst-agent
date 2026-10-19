import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "eval"))
import model_comparison as mc  # noqa: E402
import react  # noqa: E402
import tools  # noqa: E402

PLAYERS = [  # (player_id, name, canonical_id, official results)
    (1, "Impala", 1, 3), (2, "Impala", 2, 1), (3, "BBBalloonBoy", 3, 5), (4, "Marckiem00", 4, 4),
    (5, "flowerVS", 5, 2), (6, "Flowers", 6, 1), (7, "megD", 7, 2), (8, "megdee", 7, 0), (9, "Boomie", 9, 2),
    (10, "Boomie", 10, 0), (11, "Raydish", 11, 6), (12, "lFiend", 12, 1), (13, "Ca$h", 13, 1)]
ALIASES = [  # (alias, player_id, kind, shown_as, note)
    ("impala", 1, "display_name", "Impala", None), ("impala", 2, "display_name", "Impala", None),
    ("bbballoonboy", 3, "display_name", "BBBalloonBoy", None), ("balloonboy", 3, "former_name", "LGN | BalloonBoy", None),
    ("marckiem00", 4, "display_name", "Marckiem00", None), ("marckiemoo", 4, "nickname", "marckiemoo", "Marckiem00"),
    ("flowervs", 5, "display_name", "flowerVS", None), ("flowers", 5, "nickname", "flowers", "flowerVS"),
    ("flowers", 6, "display_name", "Flowers", None), ("megd", 7, "display_name", "megD", None),
    ("megdee", 8, "display_name", "megdee", None), ("boomie", 9, "display_name", "Boomie", None),
    ("boomie", 10, "display_name", "Boomie", None), ("raydish", 11, "display_name", "Raydish", None),
    ("lfiend", 12, "display_name", "lFiend", None), ("cah", 13, "display_name", "Ca$h", None)]


def snapshot(path):
    """A tiny database with what the tools read: players, aliases and v_results (a table here)."""
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE players (player_id INTEGER PRIMARY KEY, name TEXT, canonical_id INTEGER);"
                     "CREATE TABLE player_aliases (alias TEXT, player_id INTEGER, kind TEXT, shown_as TEXT, note TEXT);"
                     "CREATE TABLE v_results (player_id INTEGER, start_date TEXT);"
                     "CREATE TABLE t (a, b);")
    db.executemany("INSERT INTO players VALUES (?, ?, ?)", [p[:3] for p in PLAYERS])
    db.executemany("INSERT INTO player_aliases VALUES (?, ?, ?, ?, ?)", ALIASES)
    db.executemany("INSERT INTO v_results VALUES (?, ?)",
                   [(canonical, f"202{i}-01-01") for _, _, canonical, n in PLAYERS for i in range(n)])
    db.executemany("INSERT INTO t VALUES (?, ?)", [(i, i / 3) for i in range(25)])
    db.commit()
    db.close()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "db.sqlite"
        snapshot(self.path)
        db = sqlite3.connect(self.path)
        self.resolver = tools.Resolver(db)
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def resolve(self, name):
        out = self.resolver.resolve(name)
        return out["status"], [c["player_id"] for c in out["candidates"]]


class SkeletonTest(unittest.TestCase):
    def test_common_character_swaps_are_undone(self):
        self.assertEqual(tools.skeleton("Marckiem00"), "marckiemo")
        self.assertEqual(tools.skeleton("marckiemoo"), "marckiemo")
        self.assertEqual(tools.skeleton("baloonboy"), tools.skeleton("BBBalloonBoy"))
        self.assertEqual(tools.skeleton("IFiend"), tools.skeleton("lFiend"))
        self.assertEqual(tools.skeleton("Ca$h"), "cash")
        self.assertEqual(tools.skeleton("Pink | V3M"), "vem")


class ResolverTest(Fixture):
    def test_exact_matches_ignore_case_spaces_punctuation_and_team_tags(self):
        self.assertEqual(self.resolve(" BalloonBoy "), ("confident", [3]))
        self.assertEqual(self.resolve("M30W | BalloonBoy"), ("confident", [3]))
        self.assertEqual(self.resolve("bbballoon-boy"), ("confident", [3]))
        self.assertEqual(self.resolver.resolve("balloonboy")["candidates"][0]["match"], "former name")

    def test_a_curated_nickname_wins_and_the_others_with_the_name_follow(self):
        self.assertEqual(self.resolve("flowers"), ("confident", [5, 6]))
        out = self.resolver.resolve("marckiemoo")
        self.assertEqual((out["status"], out["candidates"][0]["match"], out["candidates"][0]["note"]),
                         ("confident", "curated nickname", "Marckiem00"))

    def test_a_shared_name_is_ambiguous_unless_only_one_of_them_has_results(self):
        self.assertEqual(self.resolve("IMPALA"), ("ambiguous", [1, 2]))  # most official results first
        self.assertEqual(self.resolve("boomie"), ("confident", [9, 10]))
        first = self.resolver.resolve("impala")["candidates"][0]
        self.assertEqual((first["official_results"], first["results_from"], first["results_to"]), (3, "2020-01-01", "2022-01-01"))

    def test_swaps_are_confident_but_prefixes_and_misspellings_are_ambiguous(self):
        self.assertEqual(self.resolve("baloonboy"), ("confident", [3]))
        self.assertEqual(self.resolve("IFiend"), ("confident", [12]))
        self.assertEqual(self.resolve("cash"), ("confident", [13]))
        self.assertEqual(self.resolve("rayd"), ("ambiguous", [11]))
        self.assertEqual(self.resolve("raydsh"), ("ambiguous", [11]))
        self.assertEqual(self.resolve("markiemoo"), ("ambiguous", [4]))
        self.assertEqual(self.resolver.resolve("markiemoo")["candidates"][0]["match"], "similar spelling")

    def test_a_merged_record_resolves_to_the_person_and_nothing_close_is_not_found(self):
        out = self.resolver.resolve("megdee")
        self.assertEqual((out["status"], out["candidates"][0]["player_id"], out["candidates"][0]["name"]),
                         ("confident", 7, "megD"))
        self.assertEqual(self.resolve("zzqqxx"), ("not_found", []))
        self.assertEqual(self.resolve("!!"), ("not_found", []))


class RunSqlTest(Fixture):
    def test_at_most_20_rows_with_the_total_and_numbers_kept_short(self):
        out = tools.run_sql("SELECT a, b FROM t ORDER BY a", self.path)
        self.assertEqual((out["columns"], len(out["rows"]), out["row_count"]), (["a", "b"], 20, 25))
        self.assertEqual(out["rows"][1], [1, 0.3333])
        self.assertIn("first 20 rows", out["note"])
        self.assertNotIn("note", tools.run_sql("SELECT a FROM t LIMIT 3", self.path))
        long = tools.run_sql("SELECT replace(hex(zeroblob(200)), '0', 'x')", self.path)["rows"][0][0]
        self.assertTrue(long.startswith("x" * 300) and long.endswith("(400 characters)"))

    def test_read_only_on_one_database_stopped_after_the_limit_and_errors_as_text(self):
        self.assertIn("readonly", tools.run_sql("DELETE FROM t", self.path)["error"])
        self.assertIn("not authorized", tools.run_sql("ATTACH DATABASE ':memory:' AS m", self.path)["error"])
        forever = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT COUNT(*) FROM c"
        self.assertTrue(tools.run_sql(forever, self.path, seconds=0.5)["error"].startswith("stopped after 0.5 s"))
        self.assertIn("no such column: nope", tools.run_sql("SELECT nope FROM t", self.path)["error"])
        self.assertIn("one statement", tools.run_sql("SELECT 1; SELECT 2", self.path)["error"])


def reply(content="", calls=(), thinking="", done="stop"):
    return {"message": {"role": "assistant", "content": content, "thinking": thinking,
                        "tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in calls]},
            "done_reason": done, "prompt_eval_count": 100, "prompt_eval_cached_count": 90, "eval_count": 10}


class Scripted:
    """A model that gives the replies it's given, in order, and keeps a copy of every request's messages."""

    def __init__(self, *replies):
        self.replies, self.sent = list(replies), []

    def __call__(self, messages, **model):
        self.sent.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


class LoopTest(Fixture):
    def setUp(self):
        super().setUp()
        self.tools = react.Tools(self.path)

    def test_tools_run_until_the_answer_and_every_step_is_traced(self):
        ask = Scripted(reply(calls=[("resolve_player", {"name": "megd"})], thinking="Find megd first."),
                       reply(calls=[("run_sql", {"query": "SELECT COUNT(*) AS n FROM v_results WHERE player_id = 7"})]),
                       reply("megD has 2 official results."))
        trace = react.run("How many results has megd?", self.tools, ask=ask, log=lambda *_: None)
        self.assertEqual((trace["outcome"], trace["answer"], trace["steps_used"]), ("answered", "megD has 2 official results.", 3))
        first, second = (s["tool_calls"][0] for s in trace["steps"][:2])
        self.assertEqual((trace["steps"][0]["thinking"], json.loads(first["observation"])["status"]), ("Find megd first.", "confident"))
        self.assertEqual(json.loads(second["observation"])["rows"], [[2]])
        self.assertIn("at most 8 steps", ask.sent[0][0]["content"])
        assistant, observation = ask.sent[1][-2:]
        self.assertEqual((assistant["role"], assistant["thinking"], observation["role"], observation["tool_name"]),
                         ("assistant", "Find megd first.", "tool", "resolve_player"))
        self.assertEqual(json.loads(observation["content"]), json.loads(first["observation"]))
        self.assertEqual((trace["output_tokens"], trace["largest_context"]), (30, 110))

    def test_text_beside_tool_calls_is_traced_but_left_out_of_the_history(self):
        ask = Scripted(reply("Let me look them up.", calls=[("resolve_player", {"name": "megd"})]), reply("Done."))
        trace = react.run("q", self.tools, ask=ask, log=lambda *_: None)
        self.assertEqual(trace["steps"][0]["content"], "Let me look them up.")
        self.assertEqual(ask.sent[1][2]["content"], "")
        self.assertEqual(len(ask.sent[1][2]["tool_calls"]), 1)

    def test_the_step_limit_ends_a_question_and_the_observation_before_the_last_step_says_so(self):
        ask = Scripted(*[reply(calls=[("resolve_player", {"name": "megd"}), ("resolve_player", {"name": "boomie"})])] * 3)
        trace = react.run("q", self.tools, ask=ask, max_steps=3, log=lambda *_: None)
        self.assertEqual((trace["outcome"], trace["answer"], trace["steps_used"]), ("step limit", None, 3))
        self.assertEqual([c["observation"] for c in trace["steps"][2]["tool_calls"]], [None, None])
        second = [json.loads(c["observation"]) for c in trace["steps"][1]["tool_calls"]]
        self.assertEqual(["last_step" in o for o in second], [False, True])
        self.assertNotIn("last_step", json.loads(trace["steps"][0]["tool_calls"][1]["observation"]))
        self.assertIn("at most 3 steps", ask.sent[0][0]["content"])

    def test_a_reply_without_tool_calls_ends_the_question(self):
        self.assertEqual(react.ending("", "length"), "cut off at the output cap")
        self.assertEqual(react.ending('<tool_call>{"name": "run_sql"}</tool_call>', "stop"), "tool call in the reply text, not parsed")
        self.assertEqual(react.ending(" ", "stop"), "empty reply")
        self.assertEqual(react.ending("Raydish.", "stop"), "answered")
        trace = react.run("q", self.tools, ask=Scripted(reply(done="length")), log=lambda *_: None)
        self.assertEqual((trace["outcome"], trace["answer"]), ("cut off at the output cap", None))

    def test_bad_tool_calls_get_errors_the_model_can_act_on(self):
        self.assertIn("takes one argument, name", self.tools.call("resolve_player", {})["error"])
        self.assertIn("takes one argument, query", self.tools.call("run_sql", {"sql": "SELECT 1"})["error"])
        self.assertIn("no tool named 'lookup'", self.tools.call("lookup", {"name": "megd"})["error"])
        self.assertEqual(self.tools.call("resolve_player", '{"name": "megd"}')["status"], "confident")

    def test_traces_are_written_in_full_and_summarized_without_the_thinking(self):
        ask = Scripted(reply(calls=[("run_sql", {"query": "SELECT a FROM t"})], thinking="Count them."), reply("25."))
        trace = {"number": 6, **react.run("How many?", self.tools, ask=ask, log=lambda *_: None)}
        header = {"run": "R", "model": "m", "variant": "v", "think": True, "seed": 0, "max_steps": 8, "ollama": "x",
                  "snapshot": {"file": "f", "build_id": "b"}}
        page = react.markdown([trace], header)
        for text in ("## Question 6: How many?", "Count them.", "**Tool call:** `run_sql`", "SELECT a FROM t", "### Answer"):
            self.assertIn(text, page)
        summary = react.summary(trace)
        self.assertEqual(summary["tool_calls"][0]["result"][:9], "25 rows: ")
        self.assertNotIn("Count them.", json.dumps(summary))


class PromptTest(unittest.TestCase):
    def test_the_prompt_keeps_the_comparison_prompts_views_and_counting_rules(self):
        views = mc.PROMPT.split("\nViews\n")[1].split("\n\nCounting rules")[0]
        rules = mc.PROMPT.split("\nCounting rules")[1].split("\n\nWrite one SQLite query")[0]
        self.assertIn("\nViews\n" + views + "\n", react.SYSTEM)
        self.assertIn("\nCounting rules" + rules + "\n", react.SYSTEM)


if __name__ == "__main__":
    unittest.main()
