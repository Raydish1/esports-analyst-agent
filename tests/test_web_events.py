import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))
import events  # noqa: E402

BOOMIE = {"name": "boomie", "status": "confident", "note": "Use player_id 146606.", "candidates": [
    {"player_id": 146606, "name": "Boomie", "display": "Boomie", "matched": "Boomie", "match": "display name",
     "score": 0.98, "official_results": 147, "results_from": "2017-02-04", "results_to": "2024-03-10"}]}
MARKIE = {"name": "markiemoo", "status": "not found", "candidates": [
    {"player_id": 146052, "name": "Marckiem00", "display": "Marckiem00", "official_results": 47,
     "results_from": "2022-01-01", "results_to": "2026-05-01"},
    {"player_id": 101849, "name": "Markled", "official_results": 2, "results_from": "2020-03-01", "results_to": "2020-04-01"},
    {"player_id": 104811, "name": "Arklem", "official_results": 1, "results_from": "2018-01-01", "results_to": "2018-01-01"}]}
GODLY = {"name": "godlyy", "status": "ambiguous", "candidates": [
    {"player_id": 147982, "name": "Zivai", "display": "Zivai (formerly Godly)", "official_results": 60},
    {"player_id": 5, "name": "Godlike", "official_results": 3}]}


def call(name, arguments, observation, **more):
    return {"name": name, "arguments": arguments, "observation": json.dumps(observation), "seconds": 0.1, **more}


def suggested(*observations):
    step = {"step": 1, "thinking": "", "content": "", "tool_calls": [call("resolve_player", {"name": o["name"]}, o)
                                                                     for o in observations],
            "suggestions": {o["name"]: [c["player_id"] for c in o["candidates"][:3]] for o in observations}}
    return {"question": "q", "outcome": "suggestions", "answer": "Which one did you mean?", "steps": [step]}


class LabelTest(unittest.TestCase):
    def test_each_tool_says_what_it_does(self):
        self.assertEqual(events.tool_label("resolve_player", {"name": "boomie"}), "Looking up the player “boomie”")
        self.assertEqual(events.tool_label("resolve_event", {"event": "bcx 2022"}), "Looking up the event “bcx 2022”")
        self.assertEqual(events.tool_label("run_sql", {"query": "SELECT 1"}), "Running a query")
        self.assertEqual(events.tool_label("event_results", {"event": "worlds 2023", "top": 8}),
                         "Getting the results of “worlds 2023”")
        self.assertEqual(events.tool_label("player_results", "not a dict"), "Getting a player's results")
        self.assertEqual(events.tool_label("nonsense", {}), "Calling nonsense")


class RedactTest(unittest.TestCase):
    def test_the_model_server_address_never_leaves(self):
        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://10.0.0.7:11434/"}):
            out = events.redact({"a": ["request error: http://10.0.0.7:11434 refused", {"b": "host 10.0.0.7:11434"}]})
            self.assertNotIn("10.0.0.7", json.dumps(out))
            self.assertIn("[model server]", out["a"][0])
            self.assertNotIn("10.0.0.7", events.error("connect to 10.0.0.7 failed")["message"])

    def test_without_an_address_values_pass_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(events.redact({"a": "x"}), {"a": "x"})


class StepTest(unittest.TestCase):
    def test_a_query_shows_its_sql_and_rows(self):
        raw = {"step": 2, "seconds": 3.0, "thinking": "Count them. Then answer.", "tool_calls": [
            call("run_sql", {"query": "SELECT 1 AS n"}, {"columns": ["n"], "rows": [[1]], "row_count": 1})]}
        out = events.step(raw)
        shown = out["calls"][0]
        self.assertEqual((shown["sql"], shown["result"]["kind"], shown["result"]["tables"][0]["rows"]),
                         (["SELECT 1 AS n"], "query", [[1]]))
        self.assertEqual(out["thought"], "Count them. Then answer.")

    def test_a_result_too_large_says_the_model_got_no_rows(self):
        raw = {"step": 1, "tool_calls": [call("run_sql", '{"query": "SELECT *"}',
                                              {"columns": ["a"], "row_count": 900, "complete": False})]}
        t = events.step(raw)["calls"][0]["result"]["tables"][0]
        self.assertEqual((t["rows"], t["row_count"]), (None, 900))
        self.assertIn("Too large", t["note"])

    def test_an_empty_result_shows_its_diagnosis(self):
        raw = {"step": 1, "tool_calls": [call("run_sql", {"query": "SELECT"}, {"columns": ["a"], "rows": [], "row_count": 0,
                                                                              "diagnosis": {"note": "no row has x"}})]}
        self.assertEqual(events.step(raw)["calls"][0]["result"]["tables"][0]["note"], "no row has x")

    def test_a_template_shows_the_sql_it_ran_and_its_tables(self):
        observation = {"template": "player_results", "scope": "official events, 1v1 and 2v2", "notes": ["a note"],
                       "tables": [{"what": "wins", "columns": ["mode", "results"], "rows": [["1v1", 6]], "row_count": 1},
                                  {"what": "the list", "columns": ["event"], "row_count": 80, "complete": False,
                                   "note": "left out"}]}
        raw = {"step": 1, "tool_calls": [call("player_results", {"player_id": 160000, "top": 1}, observation,
                                              ran=["SELECT a", "SELECT b"])]}
        shown = events.step(raw)["calls"][0]
        self.assertEqual(shown["sql"], ["SELECT a", "SELECT b"])
        self.assertEqual([t["rows"] for t in shown["result"]["tables"]], [[["1v1", 6]], None])
        self.assertEqual(shown["result"]["notes"], ["a note"])

    def test_a_refused_call_and_the_checks_show(self):
        raw = {"step": 3, "tool_calls": [call("head_to_head", {"player_id": 1, "opponent_id": 2}, {"error": "not returned"},
                                              unreturned_players=[1, 2])],
               "answer_check": {"names": {"Lucky": [1]}, "ids": [], "action": "sent back", "message": "Check it."}}
        out = events.step(raw)
        self.assertTrue(out["calls"][0]["refused"])
        self.assertEqual(out["calls"][0]["result"]["status"], "not returned")
        self.assertEqual(out["checks"], [{"check": "Answer check", "action": "sent back", "message": "Check it."}])

    def test_a_player_lookup_shows_its_candidates(self):
        out = events.step({"step": 1, "tool_calls": [call("resolve_player", {"name": "boomie"}, BOOMIE)]})
        result = out["calls"][0]["result"]
        self.assertEqual(result["kind"], "player")
        self.assertEqual(result["tables"][0]["rows"][0][:2], [146606, "Boomie"])

    def test_a_call_not_run_at_the_step_limit(self):
        raw = {"step": 8, "tool_calls": [{"name": "run_sql", "arguments": {"query": "SELECT"}, "observation": None}]}
        self.assertEqual(events.step(raw)["calls"][0]["result"]["kind"], "not run")


class NotesTest(unittest.TestCase):
    def test_each_unconfirmed_answer_gets_a_note(self):
        trace = {"unreturned_names": {"Lucky": [3]}, "unreturned_ids": [12345], "answered_after_too_big": True,
                 "answered_after_lookup_miss": True, "answered_without_tools": True,
                 "steps": [{"lookup_check": {"conditions": ["e.format = '2v2'"], "action": "kept: sent back once already"}}]}
        found = events.notes(trace)
        self.assertEqual(len(found), 4)
        self.assertIn("“Lucky” and player ID 12345", found[0])
        self.assertIn("too large", found[1])
        self.assertIn("e.format = '2v2'", found[2])
        self.assertIn("without looking them up", found[3])
        self.assertTrue(all(n.startswith("Couldn't confirm") for n in found))

    def test_a_checked_answer_has_none(self):
        self.assertEqual(events.notes({"unreturned_names": {}, "unreturned_ids": [], "steps": []}), [])


class SuggestionsTest(unittest.TestCase):
    def test_buttons_send_the_ordinal_not_the_name(self):
        groups = events.suggestions(suggested(MARKIE))
        self.assertEqual(len(groups), 1)
        options = groups[0]["options"]
        self.assertEqual([o["label"] for o in options], ["Marckiem00", "Markled", "Arklem"])
        self.assertEqual([o["reply"] for o in options], ["the first one", "the second one", "the third one"])
        self.assertEqual(options[0]["detail"], "47 official results, 2022 to 2026")
        self.assertEqual(options[2]["detail"], "1 official result, 2018")

    def test_two_unsure_names_send_one_reply(self):
        groups = events.suggestions(suggested(MARKIE, GODLY))
        self.assertEqual([g["name"] for g in groups], ["markiemoo", "godlyy"])
        self.assertEqual(groups[1]["options"][0]["label"], "Zivai (formerly Godly)")
        self.assertEqual(events.suggestion_reply(groups, {"markiemoo": 0, "godlyy": 1}),
                         "the first one for markiemoo, the second one for godlyy")
        self.assertEqual(events.suggestion_reply(groups[:1], {"markiemoo": 2}), "the third one")

    def test_an_answer_has_no_buttons(self):
        self.assertEqual(events.suggestions({"outcome": "answered", "steps": []}), [])


class AnswerTest(unittest.TestCase):
    def test_an_answer_carries_its_notes(self):
        trace = {"answer": "Boomie has 12.", "outcome": "answered", "unreturned_names": {}, "unreturned_ids": [],
                 "answered_without_tools": True, "steps": [], "steps_used": 2, "model_seconds": 9.5, "name_swaps": []}
        out = events.answer(trace)
        self.assertEqual((out["text"], out["problem"], out["steps"]), ("Boomie has 12.", None, 2))
        self.assertNotIn("figures", out)  # the cards follow in their own event
        self.assertEqual(len(out["notes"]), 1)

    def test_no_answer_says_why(self):
        out = events.answer({"answer": None, "outcome": "step limit", "steps": []})
        self.assertIn("ran out of steps", out["problem"])
        self.assertIn("request error", events.answer({"outcome": "request error at step 1: refused", "steps": []})["problem"])


if __name__ == "__main__":
    unittest.main()
