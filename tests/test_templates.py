import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "tests"))  # for the other tests' fixtures, however this module is run
import react  # noqa: E402
import templates  # noqa: E402
from test_agent import Scripted, reply  # noqa: E402
from test_views import A, A2, B, C, D, E, F, populate  # noqa: E402


class Fixture(unittest.TestCase):
    """The view tests' database in a file, as the tools open one, with a tie added: F shares 3rd place with C at the
    Cup. Its events: Cup (1v1) and Duos (2v2), which the alias 'cup 2020' names together; League, in two phases;
    Crew Battle 3v3; Kung Foot, a side format; Dreamland, cancelled; League Week 1, with unreliable placements."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name) / "db.sqlite"
        db = sqlite3.connect(cls.path)
        populate(db)
        db.execute("INSERT INTO placements VALUES ('e1', ?, 3, NULL, 'startgg', 't')", (F,))
        db.commit()
        db.close()
        cls.tools = react.Tools(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def call(self, name, **arguments):
        return self.tools.call(name, arguments)

    def rows(self, out, what):
        """The rows of the table whose description starts with `what`."""
        return next(t for t in out["tables"] if t["what"].startswith(what))["rows"]


class RegistryTest(Fixture):
    def test_every_template_is_offered_to_the_model_and_called_by_name(self):
        offered = {t["function"]["name"]: t["function"] for t in react.TOOLS}
        for name, template in templates.TEMPLATES.items():
            self.assertEqual(offered[name]["description"], template.description)
            self.assertEqual(set(offered[name]["parameters"]["required"]), set(template.required))
        self.assertEqual(self.call("event_results", event="cup 2020")["template"], "event_results")
        unknown = self.call("nothing")["error"]
        self.assertTrue(unknown.startswith("there is no tool named 'nothing': the tools are resolve_player,"))
        for name in templates.TEMPLATES:
            self.assertIn(name, unknown)

    def test_arguments_a_template_cant_use_get_errors_the_model_can_act_on(self):
        self.assertEqual(self.call("event_results")["error"], "event_results needs event: event_results takes event, top")
        self.assertIn("has no argument 'mode'", self.call("event_results", event="cup 2020", mode="1v1")["error"])
        self.assertIn("top is a whole number, 1 or more", self.call("event_results", event="cup 2020", top=0)["error"])
        self.assertIn("top is a whole number", self.call("event_results", event="cup 2020", top="eight")["error"])
        self.assertEqual(len(self.rows(self.call("event_results", event="cup 2020", top="2"), "each event's top 2")), 4)

    def test_a_template_keeps_the_sql_it_ran_with_the_ids_written_in(self):
        ran = self.call("event_results", event="cup 2020")["ran"]
        self.assertEqual(len(ran), 2)
        self.assertIn("FROM v_results r JOIN players p ON p.player_id = r.player_id WHERE r.event_id IN ('e1', 'e2')"
                      " AND r.placement <= 1", ran[1])

    def test_a_list_over_the_token_budget_is_left_out_with_its_count_and_the_rest_stays(self):
        with patch.object(templates, "TOKEN_BUDGET", 120):
            out = self.call("event_results", event="cup 2020", top=3)
        listed, placements = out["tables"]
        self.assertEqual(len(listed["rows"]), 2)
        self.assertEqual((placements["row_count"], placements["complete"], "rows" in placements), (6, False, False))
        self.assertTrue(placements["note"].startswith("6 rows, too many to show with the rest"))

    def test_the_loop_traces_the_sql_and_shows_the_model_the_result_without_it(self):
        ask = Scripted(reply(calls=[("event_results", {"event": "cup 2020"})]), reply("A won the Cup."))
        trace = react.run("Who won the cup in 2020?", self.tools, ask=ask, log=lambda *_: None)
        call = trace["steps"][0]["tool_calls"][0]
        self.assertEqual(len(call["ran"]), 2)
        self.assertNotIn("ran", json.loads(call["observation"]))
        self.assertNotIn("ran", json.loads(ask.sent[1][-1]["content"]))
        self.assertIn("**The SQL it ran**", react.markdown([{**trace, "number": None, "seed": 0}], {
            "run": "r", "model": "m", "variant": "v", "think": True, "seeds": [0], "snapshot": {"file": "f"},
            "max_steps": 8, "ollama": "0"}))
        self.assertEqual(react.preview(call["observation"]),
                         "the events the name means: 2 rows; each event's winners, a team's players together: 2 rows")

    def test_the_answer_check_counts_the_players_a_template_returned_a_teams_included(self):
        shown = react.Shown(self.tools.resolver)
        out = self.call("event_results", event="cup 2020")
        del out["ran"]
        shown.observe("event_results", out)
        self.assertEqual(shown.players, {A, B})

    def test_a_template_call_is_a_new_query_after_a_result_too_large_to_show(self):
        many = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 3000) SELECT x, 'a name' FROM c"
        ask = Scripted(reply(calls=[("run_sql", {"query": many})]), reply(calls=[("event_results", {"event": "cup 2020"})]),
                       reply("A won the Cup."))
        trace = react.run("Who won the cup in 2020?", self.tools, ask=ask, log=lambda *_: None)
        self.assertEqual((trace["outcome"], trace["steps_used"]), ("answered", 3))
        self.assertFalse(any(s.get("size_check") for s in trace["steps"]))


class EventResultsTest(Fixture):
    def test_winners_come_with_a_teams_players_together_and_names_next_to_ids(self):
        out = self.call("event_results", event="cup 2020")
        self.assertEqual((out["scope"], out["event"]), ("official events", {
            "name": "cup 2020", "status": "confident", "matched": "alias 'cup 2020'"}))
        self.assertEqual(self.rows(out, "the events"), [["Cup", "1970-01-01", "1v1", None, None],
                                                        ["Duos", "1970-01-01", "2v2", None, None]])
        self.assertEqual(self.rows(out, "each event's winners"), [["Cup", "1970-01-01", "1v1", 1, "A", [A]],
                                                                  ["Duos", "1970-01-01", "2v2", 1, "A / B", [A, B]]])

    def test_a_cutoff_never_splits_a_tie(self):
        out = self.call("event_results", event="cup 2020", top=3)
        cup = [row[3:] for row in self.rows(out, "each event's top 3") if row[0] == "Cup"]
        self.assertEqual(cup, [[1, "A", [A]], [2, "B", [B]], [3, "C", [C]], [3, "F", [F]]])
        self.assertIn("Rows on the same placement in one event are tied there: give them the same place.", out["notes"])
        self.assertNotIn("tied", " ".join(self.call("event_results", event="cup 2020", top=2)["notes"]))

    def test_an_event_that_wasnt_held_or_has_unreliable_placements_says_so_first_and_has_no_winner(self):
        out = self.call("event_results", event="dreamland")
        self.assertTrue(out["notes"][0].startswith("Dreamland (1970-01-01) was not held, so it has no results"))
        self.assertEqual((self.rows(out, "the events")[0][3], self.rows(out, "each event's winners")), ("cancelled", []))
        out = self.call("event_results", event="league week 1")
        self.assertIn("has unreliable placements, so they aren't results and it has no reliable winner", out["notes"][0])
        self.assertEqual((self.rows(out, "the events")[0][3], self.rows(out, "each event's winners")),
                         ("placements_unreliable", []))  # C and D both "won" it: neither is listed

    def test_a_crew_is_one_row_and_a_side_format_has_no_results(self):
        out = self.call("event_results", event="crew battle")
        self.assertEqual(self.rows(out, "each event's winners"),
                         [["Crew Battle 3v3", "1970-01-01", "1v1 (crew battle)", 1, "A / B / C", [A, B, C]]])
        self.assertIn("A crew battle's placement is the crew's: a team result, which counts as 1v1.", out["notes"])
        out = self.call("event_results", event="kung foot")
        self.assertEqual(self.rows(out, "the events")[0][2], "kung foot (neither 1v1 nor 2v2)")
        self.assertEqual(self.rows(out, "each event's winners"), [])
        self.assertIn("counts as neither 1v1 nor 2v2, so its placements aren't results here", out["notes"][0])

    def test_a_name_matching_several_tournaments_gets_each_one_labelled_the_closest_first(self):
        out = self.call("event_results", event="league")
        self.assertEqual(out["event"]["status"], "ambiguous")
        self.assertTrue(out["notes"][0].startswith("'league' matches 2 tournaments, the closest name first. Say which"))
        self.assertEqual([row[0] for row in self.rows(out, "the events")][-1], "League Week 1")
        self.assertEqual(self.rows(out, "each event's winners"), [["League", "1970-01-01", "1v1", 1, "C", [C]]])
        phases = next(note for note in out["notes"] if "phases of one competition" in note)
        self.assertIn("each player's result counts once, at the last phase they reached", phases)
        self.assertFalse(any("has no placements" in note for note in out["notes"]))  # the Swiss phase isn't missing any

    def test_a_name_no_event_has_or_only_partly_gets_no_results(self):
        out = self.call("event_results", event="zzz 2031")
        self.assertEqual((out["event"], out["tables"]), ({"name": "zzz 2031", "status": "not_found"}, []))
        self.assertIn("No official event matches this name", out["notes"][0])
        out = self.call("event_results", event="dreamland finals")
        self.assertTrue(out["notes"][0].startswith("No event has all the words of 'dreamland finals'"))
        self.assertEqual([t["what"] for t in out["tables"]], ["the closest events"])
        self.assertEqual(out["ran"], [])  # nothing was queried
        with patch.object(templates, "EVENTS_AT_MOST", 1):
            out = self.call("event_results", event="cup 2020")
        self.assertIn("matches 2 events, too many to answer for", out["notes"][0])
        self.assertIn("event is the event's name", self.call("event_results", event=7)["error"])


class PlayerResultsTest(Fixture):
    def test_results_are_counted_by_mode_with_the_first_the_latest_and_the_list(self):
        out = self.call("player_results", player_id=A)
        self.assertEqual((out["player"], out["scope"]), ({"player_id": A, "name": "A"}, "official events, 1v1 and 2v2"))
        self.assertEqual(self.rows(out, "A's results, counted by mode"), [
            ["A", "1v1", 3, 2, 1, 0, 3, 1], ["A", "2v2", 2, 1, 0, 1, 2, 1], ["A", "1v1 and 2v2", 5, 3, 1, 1, 5, 1]])
        self.assertEqual(self.rows(out, "the first and the latest"), [
            ["first", "1v1", "1970-01-01", "Cup", 1], ["latest", "1v1", "1970-01-01", "Crew Battle 3v3", 1],
            ["first", "2v2", "1970-01-01", "Duos", 1], ["latest", "2v2", "1970-01-01", "Duos 2", 3]])
        self.assertEqual(self.rows(out, "each of them, oldest first"), [
            ["1970-01-01", "Cup", "1v1", 1], ["1970-01-01", "Duos", "2v2", 1], ["1970-01-01", "Duos 2", "2v2", 3],
            ["1970-01-01", "League", "1v1", 2], ["1970-01-01", "Crew Battle 3v3", "1v1 (crew battle)", 1]])
        self.assertEqual(out["notes"], ["1 of the 1v1 results is a crew battle: a team result, counted as 1v1."])
        self.assertEqual(len(out["ran"]), 3)
        self.assertIn(f"WHERE r.player_id = {A} GROUP BY r.mode", out["ran"][0])

    def test_top_mode_year_and_event_narrow_the_results_and_the_scope_says_so(self):
        wins = self.call("player_results", player_id=A, top=1, mode="doubles")
        self.assertEqual((wins["scope"], self.rows(wins, "A's wins (1st places)")),
                         ("official events, 2v2", [["A", "2v2", 1, 1, 0, 0, 1, 1]]))
        self.assertEqual(self.rows(wins, "the first and the latest"), [["only", "2v2", "1970-01-01", "Duos", 1]])
        year = self.call("player_results", player_id=A, year=1970)
        self.assertEqual((year["scope"], self.rows(year, "A's results")[-1][2]), ("official events, 1v1 and 2v2, in 1970", 5))
        cup = self.call("player_results", player_id=A, event="cup 2020")
        self.assertEqual((cup["scope"], cup["event"]["status"]),
                         ("official events, 1v1 and 2v2, at the 2 events the name means", "confident"))
        self.assertEqual([row[1] for row in self.rows(cup, "each of them")], ["Cup", "Duos"])

    def test_a_count_of_zero_says_what_it_is_zero_of(self):
        out = self.call("player_results", player_id=D, top=1)
        self.assertEqual(self.rows(out, "D's wins"), [["D", "1v1", 0, 0, 0, 0, 0, None], ["D", "2v2", 0, 0, 0, 0, 0, None],
                                                      ["D", "1v1 and 2v2", 0, 0, 0, 0, 0, None]])
        self.assertEqual(out["notes"], ["None of D's 2 official results (1 in 1v1, 1 in 2v2) is among these: the count is"
                                        " 0, which isn't the same as never having played."])
        self.assertEqual(len(out["tables"]), 1)  # nothing first or latest, and no list
        self.assertEqual(self.call("player_results", player_id=E)["notes"],
                         ["E has no official 1v1 or 2v2 results in the data."])
        self.assertEqual(self.rows(self.call("player_results", player_id=A, year=2026), "A's results")[-1][2], 0)

    def test_an_event_name_must_be_one_tournament_and_its_status_comes_with_the_results(self):
        out = self.call("player_results", player_id=A, event="league")
        self.assertTrue(out["notes"][0].endswith("Call again with one tournament's name, as listed here."))
        self.assertEqual(([t["what"] for t in out["tables"]], out["ran"]), (["the closest events"], []))
        out = self.call("player_results", player_id=C, event="league week 1")
        self.assertIn("has unreliable placements", out["notes"][0])
        self.assertIn("the count is 0", out["notes"][1])  # C "won" it, but its placements aren't results

    def test_a_player_is_given_by_id_and_a_merged_record_is_the_person(self):
        out = self.call("player_results", player_id=A2)
        self.assertEqual(out["player"], {"player_id": A, "name": "A"})
        self.assertIn(f"player_id {A2} is another record of A (player_id {A}): these are the person's.", out["notes"])
        self.assertEqual(self.call("player_results", player_id=str(A))["player"]["player_id"], A)  # a number as text
        self.assertIn("not a name: call resolve_player with 'Raydish' first", self.call("player_results", player_id="Raydish")["error"])
        self.assertIn("no player has player_id 999", self.call("player_results", player_id=999)["error"])
        self.assertEqual(self.call("player_results", player_id=A, mode="standard")["error"], "mode is '1v1' or '2v2', not 'standard'")
        self.assertIn("top is a whole number, 1 or more", self.call("player_results", player_id=A, top=0)["error"])


class HeadToHeadTest(Fixture):
    def test_the_record_is_the_first_players_with_each_set_and_names_next_to_ids(self):
        out = self.call("head_to_head", player_id=A, opponent_id=B)
        self.assertEqual((out["player"], out["opponent"]), ({"player_id": A, "name": "A"}, {"player_id": B, "name": "B"}))
        self.assertEqual(self.rows(out, "A's 1v1 record against B"), [["A", A, "B", B, 3, 0, 3, 8, 1, 0]])
        self.assertEqual(self.rows(out, "each 1v1 set between them"), [  # not the forfeit, the tie or the crew battle
            ["1970-01-01", "Cup", "A", A, 3, 1], ["1970-01-01", "Cup", "A", A, 3, 0], ["1970-01-01", "League", "A", A, 2, 0]])
        self.assertEqual(self.rows(self.call("head_to_head", player_id=B, opponent_id=A), "B's 1v1 record against A"),
                         [["B", B, "A", A, 0, 3, 3, 1, 8, 0]])

    def test_each_side_of_the_sets_is_its_own_filter_since_an_or_reads_every_set(self):
        ran = " ".join(self.call("head_to_head", player_id=A, opponent_id=B)["ran"])
        self.assertIn(f"WHERE winner_id = {A} AND loser_id = {B} UNION ALL", ran)
        self.assertNotIn(" OR ", ran)

    def test_2v2_meetings_are_counted_apart_from_the_1v1_record(self):
        self.assertIn("In 2v2, A and B never met on opposite teams.",  # partners, never opponents
                      self.call("head_to_head", player_id=A, opponent_id=B)["notes"])
        out = self.call("head_to_head", player_id=A, opponent_id=C)
        self.assertEqual(self.rows(out, "A's 1v1 record"), [["A", A, "C", C, 0, 1, 1, 0, 3, 0]])  # the DQ doesn't count
        self.assertIn("In 2v2, A's teams and C's teams met in 1 set: A's side won 1 and lost 0. Those aren't in the 1v1"
                      " record.", out["notes"])

    def test_unscored_sets_are_flagged_and_players_who_never_met_get_a_record_of_zero(self):
        out = self.call("head_to_head", player_id=A, opponent_id=D)
        self.assertEqual(self.rows(out, "A's 1v1 record"), [["A", A, "D", D, 1, 0, 1, None, None, 1]])
        self.assertIn("1 of the 1 sets has no recorded score, so the games leave it out: say the record includes sets"
                      " with no recorded score.", out["notes"])
        out = self.call("head_to_head", player_id=E, opponent_id=F)
        self.assertEqual(([t["what"] for t in out["tables"]], self.rows(out, "E's 1v1 record")),
                         (["E's 1v1 record against F, in sets"], [["E", E, "F", F, 0, 0, 0, None, None, 0]]))
        self.assertEqual(out["notes"], ["E and F have no counted 1v1 sets against each other at official events (DQs,"
                                        " forfeits and ties aren't counted).", "In 2v2, E and F never met on opposite teams."])

    def test_players_are_given_by_id_and_a_merged_record_is_the_person(self):
        out = self.call("head_to_head", player_id=A2, opponent_id=B)
        self.assertEqual(self.rows(out, "A's 1v1 record against B")[0][4:7], [3, 0, 3])
        self.assertIn(f"player_id {A2} is another record of A (player_id {A}): these are the person's.", out["notes"])
        self.assertEqual(self.call("head_to_head", player_id=A, opponent_id=A2)["error"],
                         "player_id and opponent_id are both A: pass the two players' player_ids")
        self.assertIn("opponent_id is the number resolve_player returns, not a name: call resolve_player with 'B'",
                      self.call("head_to_head", player_id=A, opponent_id="B")["error"])
        self.assertEqual(self.call("head_to_head", player_id=A)["error"],
                         "head_to_head needs opponent_id: head_to_head takes player_id, opponent_id")


class RankPlayersTest(Fixture):
    def test_players_are_ranked_with_every_tie_and_the_split_by_mode(self):
        out = self.call("rank_players", by="wins")
        self.assertEqual(out["scope"], "official events, 1v1 and 2v2")
        self.assertEqual(self.rows(out, "players ranked by wins (1st places), everyone ranked 5th or better"),
                         [[1, "A", A, 3, 2, 1, 1], [2, "B", B, 2, 1, 1, 1], [2, "C", C, 2, 2, 0, 1]])
        self.assertEqual(out["tables"][0]["columns"], ["rank", "player", "player_id", "wins", "1v1", "2v2", "crew battles"])
        self.assertEqual(out["notes"], [
            "Players on the same rank are tied: give them the same place.",
            "A tournament's 1v1 and 2v2 are separate events, and each counts: wins (1st places) at both count twice. Say so.",
            "The crew battles column counts each player's crew battles among these: a crew's placement is a team result,"
            " counted as 1v1. Say so."])
        self.assertEqual([row[:4] for row in self.rows(self.call("rank_players", by="top8s", top=1), "players ranked")],
                         [[1, "A", A, 5], [1, "B", B, 5]])  # a cutoff never splits a tie
        self.assertEqual([row[1] for row in self.rows(self.call("rank_players", by="medals", top=2), "players ranked")],
                         ["A", "B", "C"])

    def test_a_mode_a_year_and_an_event_narrow_the_ranking_and_the_scope_says_so(self):
        out = self.call("rank_players", by="wins", mode="1v1")
        self.assertEqual((out["scope"], out["tables"][0]["columns"]),
                         ("official events, 1v1", ["rank", "player", "player_id", "wins", "crew battles"]))
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 2, 1], [1, "C", C, 2, 1], [3, "B", B, 1, 1]])
        self.assertEqual(self.rows(self.call("rank_players", by="wins", mode="2v2"), "players ranked"),
                         [[1, "A", A, 1], [1, "B", B, 1]])  # no crew battles in 2v2
        cup = self.call("rank_players", by="wins", event="cup 2020")
        self.assertEqual((cup["scope"], cup["event"]["status"]),
                         ("official events, 1v1 and 2v2, at the 2 events the name means", "confident"))
        self.assertEqual(self.rows(cup, "players ranked"), [[1, "A", A, 2, 1, 1, 0], [2, "B", B, 1, 0, 1, 0]])
        empty = self.call("rank_players", by="wins", year=2026)
        self.assertEqual((self.rows(empty, "players ranked"), empty["notes"]), ([], [
            "No player has any wins (1st places) here (official events, 1v1 and 2v2, in 2026), so the ranking is empty."]))

    def test_a_series_with_regional_championships_counts_them_apart_and_statuses_come_first(self):
        out = self.call("rank_players", by="wins", event="cup")
        self.assertEqual(out["tables"][0]["columns"][-1], "at regional championships")
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 2, 1, 1, 0, 0], [2, "B", B, 1, 0, 1, 0, 0]])
        self.assertEqual(sorted(note.split(" (")[0] for note in out["notes"][:2]), ["Dreamland", "League Week 1"])
        self.assertEqual(out["notes"][-1], "'cup 2021' was held as several regional championships, all counted here: 'at"
                                           " regional championships' counts each player's wins at them. Say whether your"
                                           " answer counts them.")

    def test_past_the_rows_listed_a_tie_group_is_counted_whole_not_split(self):
        with patch.object(templates, "RANKED_AT_MOST", 2):
            out = self.call("rank_players", by="wins")
        self.assertEqual(self.rows(out, "players ranked"), [[1, "A", A, 3, 2, 1, 1]])
        self.assertTrue(out["notes"][0].startswith("Past 2 rows a tie isn't split, so these players are counted but not"
                                                   " listed: 2 tied at rank 2 with 2 wins each. Narrow the question"))

    def test_arguments_it_cant_use_get_errors_and_an_event_must_be_one_tournament(self):
        self.assertEqual(self.call("rank_players", by="points")["error"], "by is 'wins', 'medals' or 'top8s', not 'points'")
        self.assertEqual(self.rows(self.call("rank_players", by="Top 8s"), "players ranked by top 8s")[0][:2], [1, "A"])
        self.assertEqual(self.rows(self.call("rank_players", by="titles"), "players ranked by wins")[0][:2], [1, "A"])
        self.assertEqual(self.call("rank_players")["error"],
                         "rank_players needs by: rank_players takes by, top, mode, year, event")
        self.assertEqual(self.call("rank_players", by="wins", mode="crew")["error"], "mode is '1v1' or '2v2', not 'crew'")
        out = self.call("rank_players", by="wins", event="league")
        self.assertEqual(([t["what"] for t in out["tables"]], out["ran"]), (["the closest events"], []))
        self.assertTrue(out["notes"][0].endswith("Call again with one tournament's name, as listed here."))


if __name__ == "__main__":
    unittest.main()
