import json
import re
import sqlite3
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "agent"))
import result_checks as checks  # noqa: E402
import harness  # noqa: E402
import retrieval  # noqa: E402
from names import normalize  # noqa: E402

HELDOUT = ROOT / "eval" / "questions" / "heldout.toml"


def call(name, arguments, observation):
    return {"name": name, "arguments": arguments, "observation": json.dumps(observation), "seconds": 0.1}


def sql(query, rows):
    return call("run_sql", {"query": query}, {"complete": True, "columns": ["a"] * len(rows[0] if rows else []),
                                              "rows": rows, "row_count": len(rows)})


def player(name, *ids):
    return call("resolve_player", {"name": name},
                {"name": name, "status": "confident", "candidates": [{"player_id": i, "name": f"p{i}"} for i in ids]})


def trace(*calls, outcome="answered", suggestions=None, shapes=None):
    step = {"tool_calls": list(calls), **({"suggestions": suggestions} if suggestions else {})}
    found = None if shapes is None else {"threshold": 0.7, "candidates": len(shapes),
                                         "examples": [{"id": f"ex{i}", "shape": s, "similarity": 0.8} for i, s in enumerate(shapes)]}
    return {"steps": [step], "outcome": outcome, "answer": "an answer", "examples": found, "steps_used": 1,
            "model_seconds": 1.0, "output_tokens": 10}


def events_db():
    """v_events with a yearly series: the same tournament name in 2024 and 2025."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE v_events (event_id TEXT, tournament_name TEXT, start_date TEXT)")
    db.executemany("INSERT INTO v_events VALUES (?, ?, ?)", [("e24", "Spring Doubles Championship - Europe", "2024-05-04"),
                                                             ("e25", "Spring Doubles Championship - Europe", "2025-05-03")])
    return db


POWERBH = {"id": "h09", "set": "heldout", "players": {"powerbh": 113157}}
MARKIEMOO = {"id": "q22", "set": "existing", "players": {"markiemoo": 146052},
             "accept": [{"assumption": "", "answer": "offers suggestions with Marckiem00 first"}]}
SPRINGS = {"id": "h05", "set": "heldout", "events": {"eu springs 2024": "e24"}}


class ChecksTest(unittest.TestCase):
    def test_values_match_cells_loosely(self):
        self.assertTrue(checks.matches(7, "7"))  # a year as substr() gives it
        self.assertTrue(checks.matches(83825, 83825.004))
        self.assertTrue(checks.matches("raydish", "megD / Raydish"))
        self.assertFalse(checks.matches("yüz", "yüzbaşı"))  # under four characters, text must be the whole cell
        self.assertTrue(checks.matches("yüz", "YÜZ"))
        self.assertFalse(checks.matches(7, "Trial of Laufey 7"))  # a number never matches inside text

    def test_a_result_must_hold_the_facts_in_the_shape_asked(self):
        self.assertTrue(checks.single(4)([[(4,)]]))
        self.assertFalse(checks.single(4)([[(4,), (5,)]]))
        both = checks.rows(("Zivai", 7), ("whoiskyna", 7))
        self.assertFalse(both([[("Zivai", 7)], [("whoiskyna", 7)]]))  # one result must have both
        self.assertTrue(both([[("Zivai", 7), ("whoiskyna", 7), ("Boomie", 5)]]))
        self.assertTrue(checks.listing(2, "lopes")([[("SiB | Wess",), ("lopesbrawlhalla",)]]))
        self.assertFalse(checks.listing(2, "lopes")([[("SiB | Wess",), ("lopesbrawlhalla",), ("DB",)]]))
        self.assertTrue(checks.exactly(147982, 149204)([[(147982,), (149204,)]]))  # a team's two winners
        self.assertFalse(checks.exactly(147982, 149204)([[(147982,), (149204,), (5,)]]))  # or an entrant list

    def test_every_question_of_both_sets_has_a_check(self):
        self.assertEqual(sorted(q["id"] for q in checks.load_questions()), sorted(checks.CHECKS))

    @unittest.skipUnless(harness.SNAPSHOT.exists(), "needs the eval-v1 snapshot (data/ isn't committed)")
    def test_every_check_passes_on_its_questions_reference_queries(self):
        db = sqlite3.connect(harness.SNAPSHOT.resolve().as_uri() + "?mode=ro", uri=True)
        self.assertEqual(checks.verify(db), [])


class NameResolutionTest(unittest.TestCase):
    def test_a_player_passes_when_the_queries_use_their_id(self):
        result = harness.stage1(POWERBH, trace(sql("SELECT * FROM v_team_results WHERE player_id = 113157", [])), None)
        self.assertEqual(result["result"], "pass")

    def test_a_player_fails_when_the_queries_use_another_candidate(self):
        t = trace(player("powerbh", 113157, 22222), sql("SELECT * FROM v_team_results WHERE player_id = 22222", []))
        self.assertEqual(harness.stage1(POWERBH, t, None)["result"], "fail")
        t = trace(player("PowerBH", 22222, 113157))
        self.assertEqual(harness.stage1(POWERBH, t, None), {"result": "fail", "detail": "powerbh: resolved to [22222, 113157]"})

    def test_a_player_fails_when_one_query_takes_every_candidate_for_the_name(self):
        both = trace(player("powerbh", 113157, 22222), sql("SELECT ... WHERE player_id IN (113157, 22222)", []))
        self.assertEqual(harness.stage1(POWERBH, both, None)["result"], "fail")  # the name left unresolved
        explored = trace(player("powerbh", 113157, 22222), sql("SELECT ... WHERE player_id = 22222", []),
                         sql("SELECT ... WHERE player_id = 113157", []))
        self.assertEqual(harness.stage1(POWERBH, explored, None)["result"], "pass")

    def test_suggestions_pass_only_where_the_question_accepts_them_with_the_player_first(self):
        asked = trace(player("markiemoo", 146052, 1, 2), outcome="suggestions", suggestions={"markiemoo": [146052, 1, 2]})
        self.assertEqual(harness.stage1(MARKIEMOO, asked, None)["result"], "pass")
        self.assertEqual(harness.stage1({**MARKIEMOO, "accept": []}, asked, None)["result"], "fail")
        wrong_first = trace(player("markiemoo", 1, 146052, 2), outcome="suggestions",
                            suggestions={"markiemoo": [1, 146052, 2]})
        self.assertEqual(harness.stage1(MARKIEMOO, wrong_first, None)["result"], "fail")

    def test_an_event_passes_by_its_id_or_by_a_resolve_event_condition_the_queries_used(self):
        db = events_db()
        by_id = trace(sql("SELECT * FROM v_placements WHERE event_id = 'e24' AND placement = 1", []))
        self.assertEqual(harness.stage1(SPRINGS, by_id, db)["result"], "pass")
        condition = "event_id IN (SELECT event_id FROM v_events WHERE start_date < '2025')"
        used = trace(call("resolve_event", {"name": "eu springs 2024"}, {"sql": condition}),
                     sql(f"SELECT * FROM v_placements WHERE {condition} AND placement = 1", []))
        self.assertEqual(harness.stage1(SPRINGS, used, db)["result"], "pass")
        unused = trace(call("resolve_event", {"name": "eu springs 2024"}, {"sql": condition}),
                       sql("SELECT * FROM v_placements WHERE placement = 1", []))
        self.assertEqual(harness.stage1(SPRINGS, unused, db)["result"], "fail")

    def test_an_event_found_by_name_passes_only_with_its_year(self):
        db = events_db()
        shown = trace(sql("SELECT tournament_name, start_date FROM v_events WHERE ...",
                          [["Spring Doubles Championship - Europe", "2024-05-04"]]))
        self.assertEqual(harness.stage1(SPRINGS, shown, db)["result"], "pass")
        next_year = trace(sql("SELECT tournament_name, start_date FROM v_events WHERE ...",
                              [["Spring Doubles Championship - Europe", "2025-05-03"]]))
        self.assertEqual(harness.stage1(SPRINGS, next_year, db)["result"], "fail")

    def test_a_question_naming_no_player_or_event_has_no_name_resolution_stage(self):
        self.assertEqual(harness.stage1({"id": "h11", "set": "heldout"}, trace(), None)["result"], "n/a")

    def test_a_run_that_called_no_tool_fails_at_the_query_it_never_ran_not_at_a_lookup(self):
        self.assertEqual(harness.stage1(POWERBH, trace(), None), {"result": "n/a", "detail": "called no tool"})
        with mock.patch.dict(harness.CHECKS, {"h09": checks.single(4)}):
            self.assertEqual(harness.stage2(POWERBH, trace())["result"], "fail")


class SqlLogicTest(unittest.TestCase):
    def test_the_check_reads_the_rows_of_every_result_shown(self):
        with mock.patch.dict(harness.CHECKS, {"x01": checks.row(30, 2)}):
            right = trace(sql("SELECT 1", [[1]]), sql("SELECT wins, losses ...", [[30, 2]]))
            self.assertEqual(harness.stage2({"id": "x01"}, right)["result"], "pass")
            wrong = trace(sql("SELECT wins, losses ...", [[29, 3]]),
                          call("run_sql", {"query": "SELECT ..."}, {"error": "OperationalError: no such column"}),
                          call("run_sql", {"query": "SELECT ..."}, {"complete": False, "row_count": 900, "columns": []}))
            self.assertEqual(harness.stage2({"id": "x01"}, wrong), {"result": "fail", "detail": "2 query results"})

    def test_an_answer_comes_after_an_empty_result_when_the_last_query_found_nothing(self):
        self.assertTrue(harness.ended_empty(trace(sql("SELECT 1", [[30, 2]]), sql("SELECT ...", []))))
        self.assertTrue(harness.ended_empty(trace(sql("SELECT SUM(won), COUNT(*) ...", [[None, 0]]))))  # over no rows
        self.assertFalse(harness.ended_empty(trace(sql("SELECT ...", []), sql("SELECT ...", [[30, 2]]))))
        self.assertFalse(harness.ended_empty(trace()))

    def test_an_events_status_from_resolve_event_counts_as_a_fact_the_agent_saw(self):
        with mock.patch.dict(harness.CHECKS, {"x01": checks.row("cancelled")}):
            looked_up = trace(call("resolve_event", {"name": "ceo dreamland 2020"},
                                   {"events": [{"event_id": "e20", "name": "CEO Dreamland 2020", "status": "cancelled"}]}))
            self.assertEqual(harness.stage2({"id": "x01"}, looked_up)["result"], "pass")

    def test_no_check_applies_to_an_unanswerable_question_or_to_suggestions(self):
        self.assertEqual(harness.stage2({"id": "q35"}, trace())["result"], "n/a")
        self.assertEqual(harness.stage2({"id": "q22"}, trace(outcome="suggestions"))["result"], "n/a")


class GroupTest(unittest.TestCase):
    LABELS = {"h09": ["teammates", "partnership"], "q14": ["event_top8"]}

    def test_a_question_has_a_known_shape_when_retrieval_returns_a_helpful_example(self):
        self.assertEqual(harness.shape(POWERBH, trace(shapes=["ranking", "teammates"]), self.LABELS), "known shape")
        self.assertEqual(harness.shape(POWERBH, trace(shapes=["ranking"]), self.LABELS), "new shape")
        self.assertEqual(harness.shape(POWERBH, trace(shapes=[]), self.LABELS), "new shape")  # none above the threshold
        self.assertIsNone(harness.shape(POWERBH, trace(), self.LABELS))  # retrieval off

    def test_groups_put_the_tuned_questions_apart_and_split_the_rest_by_set_and_shape(self):
        self.assertEqual(harness.group({"id": "q04", "set": "existing"}, "known shape"), "tuned")
        self.assertEqual(harness.group(POWERBH, "known shape"), "held-out, known shape")
        self.assertEqual(harness.group({"id": "q14", "set": "existing"}, "new shape"), "existing, new shape")

    def test_a_question_counts_as_tuned_only_in_runs_from_the_day_it_was_tuned_on(self):
        q05 = {"id": "q05", "set": "existing"}  # tuned on in step 1, 2026-11-09
        self.assertEqual(harness.group(q05, "new shape", "20261108-eval-on"), "existing, new shape")
        self.assertEqual(harness.group(q05, "new shape", "20261109-step1"), "tuned")
        self.assertEqual(harness.group({"id": "q13", "set": "existing"}, "known shape", "my-run"), "existing, known shape")

    def test_a_run_without_retrieval_takes_its_questions_shape_from_a_run_with_it(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(harness, "RAW", Path(folder)):
            for run_id, arm, shapes in (("on", "on", ["teammates"]), ("off", "off", None)):
                (Path(folder) / run_id).mkdir()
                (Path(folder) / run_id / "header.json").write_text(json.dumps({"arm": arm}), encoding="utf-8")
                line = {"id": "h09", "seed": 0, **trace(shapes=shapes)}
                (Path(folder) / run_id / "traces.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
            scored = harness.score(["off", "on"], None, self.LABELS)
        self.assertEqual([(r["arm"], r["group"]) for r in scored["off"] + scored["on"]],
                         [("off", "held-out, known shape"), ("on", "held-out, known shape")])


class DraftTest(unittest.TestCase):
    def record(self, one, two, outcome="answered"):
        return {"outcome": outcome, "stage1": {"result": one, "detail": "d1"}, "stage2": {"result": two, "detail": "d2"}}

    def test_the_first_automatic_stage_that_fails_decides_the_draft(self):
        self.assertEqual(harness.draft(self.record("fail", "fail")),
                         {"verdict": "wrong", "stage": "name resolution", "review": "auto", "note": "d1"})
        self.assertEqual(harness.draft(self.record("n/a", "fail"))["stage"], "SQL logic")

    def test_a_missed_lookup_is_only_a_draft_where_the_right_answer_needs_no_data(self):
        unanswerable = {**self.record("fail", "n/a"), "needs_data": False}  # "the data can't say" needs no lookup
        self.assertEqual(harness.draft(unanswerable)["review"], "needs review")
        self.assertEqual(harness.draft({**self.record("fail", "n/a"), "needs_data": True})["review"], "auto")

    def test_missing_facts_after_an_empty_result_are_drafted_as_empty_data_handling(self):
        after_empty = {**self.record("pass", "fail"), "ended_empty": True}  # "no results" may be true, or a lookup miss
        self.assertEqual({k: harness.draft(after_empty)[k] for k in ("stage", "review")},
                         {"stage": "empty or insufficient data", "review": "needs review"})

    def test_runs_past_the_automatic_stages_are_drafted_for_review(self):
        self.assertEqual(harness.draft(self.record("pass", "pass", "step limit")),
                         {"verdict": "wrong", "stage": "no answer", "review": "needs review", "note": "outcome: step limit"})
        self.assertEqual(harness.draft(self.record("pass", "n/a"))["review"], "needs review")


class JudgmentsTest(unittest.TestCase):
    def test_rewriting_the_judgments_keeps_what_was_judged_and_drafts_the_rest(self):
        records = [{"arm": "on", "id": i, "seed": 0, "outcome": "answered", "stage1": {"result": "pass", "detail": ""},
                    "stage2": {"result": "pass", "detail": ""}, "question": "how many?", "expected": "4",
                    "answer": 'He has "4" titles.\nAll in NA.'} for i in ("h01", "h02")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "judgments.toml"
            harness.write_judgments(path, records)
            judged = harness.read_judgments(path)
            judged[("on", "h01", 0)].update(verdict="partly", stage="answer writing", note='said "4" without the 1v1 split')
            harness.write_judgments(path, records, judged)
            again = harness.read_judgments(path)
        self.assertEqual(again[("on", "h01", 0)]["note"], 'said "4" without the 1v1 split')
        self.assertEqual((again[("on", "h02", 0)]["verdict"], again[("on", "h02", 0)]["review"]), ("", "needs review"))
        self.assertEqual(again[("on", "h02", 0)]["answer"], 'He has "4" titles.\nAll in NA.')  # to judge from

    def test_an_automatic_verdict_follows_a_corrected_check_and_a_confirmed_one_stays(self):
        def record(i, two):
            return {"arm": "on", "id": i, "seed": 0, "outcome": "answered", "stage1": {"result": "n/a", "detail": ""},
                    "stage2": {"result": two, "detail": "1 query results"}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "judgments.toml"
            harness.write_judgments(path, [record("h01", "fail"), record("h02", "fail")])
            judged = harness.read_judgments(path)
            judged[("on", "h02", 0)].update(verdict="right", stage="", review="confirmed", note="the check missed it")
            harness.write_judgments(path, [record("h01", "pass"), record("h02", "fail")], judged)  # h01's check fixed
            again = harness.read_judgments(path)
        self.assertEqual((again[("on", "h01", 0)]["verdict"], again[("on", "h01", 0)]["review"]), ("", "needs review"))
        self.assertEqual((again[("on", "h02", 0)]["verdict"], again[("on", "h02", 0)]["review"]), ("right", "confirmed"))

    def test_a_partly_right_answer_over_a_failed_stage_keeps_its_verdict_while_that_stage_fails(self):
        def record(two):
            return {"arm": "on", "id": "q20", "seed": 0, "outcome": "answered", "stage1": {"result": "pass", "detail": ""},
                    "stage2": {"result": two, "detail": "1 query results"}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "judgments.toml"
            harness.write_judgments(path, [record("fail")])
            judged = harness.read_judgments(path)
            judged[("on", "q20", 0)].update(verdict="partly", review="needs review", note="the score, not the opponent")
            harness.write_judgments(path, [record("fail")], judged)
            still = harness.read_judgments(path)[("on", "q20", 0)]
            harness.write_judgments(path, [record("pass")], harness.read_judgments(path))  # the check widened
            passed = harness.read_judgments(path)[("on", "q20", 0)]
        self.assertEqual((still["verdict"], still["stage"]), ("partly", "SQL logic"))
        self.assertEqual((passed["verdict"], passed["stage"]), ("", ""))


class ReportTest(unittest.TestCase):
    def test_every_rate_comes_with_its_raw_count(self):
        self.assertEqual(harness.counted(11, 16), "11/16 (69%)")
        self.assertEqual(harness.counted(0, 0), "0/0")

    def test_a_question_counts_as_right_only_when_every_seed_is(self):
        records = [{"arm": "on", "id": i, "seed": s} for i in ("h01", "h02") for s in (0, 1, 2)]
        judged = {("on", "h01", s): {"verdict": "right"} for s in (0, 1, 2)}
        judged.update({("on", "h02", 0): {"verdict": "right"}, ("on", "h02", 1): {"verdict": "partly"}})
        self.assertEqual(harness.tally(records, judged),
                         {"runs": 6, "right": 4, "partly": 1, "unjudged": 1, "questions": 2, "all_right": 1})

    def test_the_report_counts_runs_by_the_stage_that_failed(self):
        records = [{"arm": "on", "id": "h01", "set": "heldout", "category": "player records", "seed": s,
                    "group": "held-out, known shape", "shape": "known shape", "label": "official_wins"} for s in (0, 1, 2)]
        judged = {("on", "h01", 0): {"verdict": "right"},
                  ("on", "h01", 1): {"verdict": "wrong", "stage": "SQL logic", "review": "auto"},
                  ("on", "h01", 2): {"verdict": "partly", "stage": "answer writing", "review": "needs review"}}
        lines = harness.report(records, judged)
        self.assertIn("| held-out, known shape | 1/3 (33%) | 1/3 (33%) | 0/1 (0%) |", lines)
        self.assertIn("| known shape, new names | 1/3 (33%) | 1/3 (33%) | 0/1 (0%) |", lines)
        self.assertIn("| official_wins | 1/3 (33%) | 1/3 (33%) | 0/1 (0%) |", lines)
        self.assertIn("| SQL logic | 1/2 (50%) | 0/0 | 0/0 | 1/2 (50%) |", lines)  # all, tuned, existing, held-out
        self.assertIn("Judgments needing review: 1 of 3.", lines)


class FailuresPageTest(unittest.TestCase):
    QUESTIONS = {
        "q01": {"id": "q01", "question": "who won winters 2023 na 1v1", "category": "event_result",
                "answer": "Raydish won it.", "notes": "Say which event.", "accept": [{"assumption": "the 2v2", "answer": "megD"}]},
        "q02": {"id": "q02", "question": "how many wins?", "category": "player_record", "answer": "6", "accept": []},
    }

    def page(self):
        records = [{"arm": "on", "id": q, "seed": s, "group": "existing, known shape", "outcome": "answered", "answer": a}
                   for q, s, a in (("q01", 0, "**Boomie** won.\n<final_answer>"), ("q01", 1, "Raydish"),
                                   ("q01", 2, "Boomie"), ("q02", 0, "6"))]
        judged = {("on", "q01", 0): {"verdict": "wrong", "stage": "SQL logic", "review": "auto", "note": "1 query results"},
                  ("on", "q01", 1): {"verdict": "right", "stage": "", "review": "needs review", "note": ""},
                  ("on", "q01", 2): {"verdict": "", "stage": "", "review": "needs review", "note": ""},
                  ("on", "q02", 0): {"verdict": "right", "stage": "", "review": "needs review", "note": ""}}
        executed = {("q01", 0): [("SELECT name FROM v_results", {"complete": True, "rows": [["Boomie"]], "row_count": 1}),
                                 ("SELECT x", {"error": "OperationalError: no such column: x"})]}
        return harness.failures("r1", records, judged, self.QUESTIONS, executed)

    def test_the_contents_list_each_question_with_a_run_not_right_and_every_seeds_verdict(self):
        lines = self.page()
        self.assertIn("| [q01](#q01) | wrong | right | not judged | SQL logic |", lines)
        self.assertFalse(any("q02" in line for line in lines))  # right in every seed

    def test_each_run_not_right_has_its_judgment_its_full_answer_and_the_sql_it_executed(self):
        text = "\n".join(self.page())
        self.assertEqual(text.count("## q01: who won winters 2023 na 1v1"), 1)  # the question once
        for shown in ("Raydish won it.", "Also accepted, if the 2v2: megD", "Say which event.",
                      "### Seed 0: wrong, SQL logic (auto)", "**Note:** 1 query results",
                      "> **Boomie** won.\n> &lt;final_answer>", "<details><summary>SQL: 2 queries</summary>",
                      "SELECT name FROM v_results\n-- 1 row", "-- error: OperationalError: no such column: x",
                      "### Seed 2: not judged (needs review)", "No SQL was executed."):
            self.assertIn(shown, text)
        self.assertNotIn("### Seed 1", text)  # a right seed isn't shown

    def test_the_subcommand_writes_the_page_by_the_runs_traces_and_leaves_its_judgments_alone(self):
        record = {"arm": "on", "id": "q13", "seed": 0, "group": "existing, known shape", "outcome": "answered",
                  "answer": "Boomie", "stage1": {"result": "pass", "detail": ""},
                  "stage2": {"result": "fail", "detail": "1 query results"}}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(harness, "RESULTS", Path(folder)), \
                mock.patch.object(harness, "RAW", Path(folder)):
            (Path(folder) / "r1-scores.json").write_text(json.dumps([record]), encoding="utf-8")
            harness.write_judgments(Path(folder) / "r1-judgments.toml", [record])
            (Path(folder) / "r1").mkdir()
            (Path(folder) / "r1" / "header.json").write_text(json.dumps({"arm": "on"}), encoding="utf-8")
            line = {"id": "q13", "seed": 0, **trace(sql("SELECT placement FROM v_results", [[1]]))}
            (Path(folder) / "r1" / "traces.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
            judgments = (Path(folder) / "r1-judgments.toml").read_text(encoding="utf-8")
            with mock.patch.object(sys, "argv", ["harness.py", "failures", "r1"]), mock.patch("builtins.print"):
                harness.main()
            page = (Path(folder) / "r1" / "failures.md").read_text(encoding="utf-8")
            self.assertEqual((Path(folder) / "r1-judgments.toml").read_text(encoding="utf-8"), judgments)
        self.assertIn("| [q13](#q13) | wrong | SQL logic |", page)
        self.assertIn("SELECT placement FROM v_results\n-- 1 row", page)


class HeldOutLeakTest(unittest.TestCase):
    """The held-out set must never reach the example bank (decided 2026-11-08), and names players the agent wasn't
    tuned on."""

    @classmethod
    def setUpClass(cls):
        with open(HELDOUT, "rb") as f:
            cls.heldout = tomllib.load(f)["question"]
        cls.bank = retrieval.load()
        cls.bank_text = retrieval.EXAMPLES.read_text(encoding="utf-8")

    def test_no_held_out_question_is_in_the_bank(self):
        bank = {" ".join(e["question"].casefold().split()) for e in self.bank}
        for q in self.heldout:
            self.assertNotIn(" ".join(q["question"].casefold().split()), bank, q["id"])

    def test_no_bank_query_or_text_names_a_held_out_player_or_event(self):
        words = {normalize(w) for w in re.split(r"[\s'\"(),=]+", self.bank_text)} - {""}
        for q in self.heldout:
            for name, pid in (q.get("players") or {}).items():
                self.assertNotIn(pid, [p for e in self.bank for p in retrieval.player_ids(e["sql"])], q["id"])
                self.assertIsNone(re.search(rf"(?<!\d){pid}(?!\d)", self.bank_text), f"{q['id']}: {pid}")
                self.assertNotIn(normalize(name), words, f"{q['id']}: {name}")
            for ids in (q.get("events") or {}).values():
                for event_id in ids if isinstance(ids, list) else [ids]:
                    self.assertNotIn(event_id, self.bank_text, q["id"])

    def test_the_held_out_players_are_new_to_the_evaluation_set(self):
        existing = {pid for q in checks.load_questions() if q["set"] == "existing" for pid in (q.get("players") or {}).values()}
        for q in self.heldout:
            self.assertFalse(set((q.get("players") or {}).values()) & existing, q["id"])


if __name__ == "__main__":
    unittest.main()
