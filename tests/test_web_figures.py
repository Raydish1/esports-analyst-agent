import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
sys.path.insert(0, str(ROOT / "app" / "server"))
import figures  # noqa: E402
import tools  # noqa: E402

SUMMARY = ["player", "mode", "results", "first", "second", "third", "top8", "best"]


def summary(name, rows, columns=SUMMARY, notes=()):
    return {"template": "player_results", "player": {"player_id": rows[0], "name": name}, "notes": list(notes),
            "tables": [{"what": "counted by mode", "columns": columns, "rows": rows[1]},
                       {"what": "first and latest", "columns": ["which", "mode", "date", "event", "placement"],
                        "rows": [["first", "1v1", "2020-04-25", "e", 9], ["latest", "2v2", "2026-09-27", "f", 2]]}]}


PLAYERS = {
    1: summary("Alpha", (1, [["Alpha", "1v1", 10, 2, 1, 0, 5, 1], ["Alpha", "2v2", 4, 0, 0, 1, 2, 3],
                             ["Alpha", "1v1 and 2v2", 14, 2, 1, 1, 7, 1]]), notes=["1 of the 1v1 results is a crew battle"]),
    2: summary("Beta", (2, [["Beta", "1v1", 3, 0, 0, 0, 0, 9], ["Beta", "2v2", 0, 0, 0, 0, 0, None],
                            ["Beta", "1v1 and 2v2", 3, 0, 0, 0, 0, 9]])),
}
EARNED = {1: [(1200.0, "Stats API", "2026-10-02")], 2: []}
TOPS = {1: [("1v1", 8), ("2v2", 3)], 2: [("1v1", 1)]}  # top 32s by mode (figures.TOP32)


class NoLegends:
    def of(self, player_id):
        return None


class Stub(figures.Cards):
    """Cards with canned template results and earnings, recording what it was asked."""

    def __init__(self, earnings=True, players=PLAYERS, h2h=None, sets=()):
        super().__init__(tools=None, earnings=earnings, legends=NoLegends())
        self.players, self.h2h, self.sets, self.asked, self.queried = players, h2h, list(sets), [], []

    def call(self, name, args):
        self.asked.append((name, args))
        if name == "player_results":
            return self.players.get(args["player_id"])
        return self.h2h

    def query(self, sql, params):
        self.queried.append(sql)
        if sql == figures.TOP32:
            return TOPS.get(params[0], [])
        return EARNED.get(params[0], []) if sql == figures.EARNINGS else self.sets


def call(name, arguments, observation):
    return {"name": name, "arguments": arguments, "observation": json.dumps(observation)}


def turn(*calls, outcome="answered"):
    return {"outcome": outcome, "steps": [{"tool_calls": list(calls)}]}


def results(pid, **args):
    return call("player_results", {"player_id": pid, **args}, {"player": {"player_id": pid}, "tables": []})


EVENTS = ["event", "event_id", "date", "mode", "status"]


def event(*rows):
    return call("event_results", {"event": "x"}, {"tables": [{"columns": EVENTS, "rows": list(rows)}]})


class ChoosingTest(unittest.TestCase):
    def test_one_player_gets_a_lifetime_card_from_a_call_without_top(self):
        stub = Stub()
        (card,) = stub.build(turn(results(1, top=1)))
        self.assertEqual(card["kind"], "lifetime")
        self.assertEqual(stub.asked, [("player_results", {"player_id": 1})])  # the model's top=1 isn't passed on
        lifetime = card["player"]
        self.assertEqual(lifetime["modes"]["1v1 and 2v2"], {"results": 14, "first": 2, "second": 1, "third": 1, "top8": 7,
                                                            "top32": 11})  # 8 + 3, the app's own count
        self.assertEqual((lifetime["modes"]["1v1"]["top32"], lifetime["modes"]["2v2"]["top32"]), (8, 3))
        self.assertEqual((lifetime["first"], lifetime["latest"], lifetime["top32"]), ("2020-04-25", "2026-09-27", True))
        self.assertEqual(lifetime["earnings"], {"amount": 1200.0, "source": "Stats API", "as_of": "2026-10-02"})
        self.assertIn("All official events, regional championships included", card["scope"])
        self.assertIn("Crew battles count as 1v1", card["scope"])

    def test_a_missing_earnings_figure_is_none_not_zero(self):
        (card,) = Stub().build(turn(results(2)))
        self.assertEqual(card["player"]["earnings"]["amount"], None)
        self.assertNotIn("Crew battles", card["scope"])

    def test_earnings_off_leaves_them_out_and_runs_no_query(self):
        stub = Stub(earnings=False)
        (card,) = stub.build(turn(results(1)))
        self.assertNotIn("earnings", card["player"])
        self.assertNotIn(figures.EARNINGS, stub.queried)

    def test_a_call_for_a_year_or_an_event_gets_no_lifetime_card(self):
        self.assertEqual(Stub().build(turn(results(1, top=1, year=2025))), [])
        self.assertEqual(Stub().build(turn(results(1, event="worlds"))), [])

    def test_two_players_are_compared(self):
        (card,) = Stub().build(turn(results(1, top=3), results(2, top=3), results(1, top=3)))
        self.assertEqual((card["kind"], [p["name"] for p in card["players"]]), ("comparison", ["Alpha", "Beta"]))

    def test_top_32_shows_once_the_summary_has_it(self):
        columns = SUMMARY[:7] + ["top32", "best"]
        players = {1: summary("Alpha", (1, [["Alpha", "1v1 and 2v2", 14, 2, 1, 1, 7, 12, 1]]), columns)}
        (card,) = Stub(players=players).build(turn(results(1)))
        self.assertEqual((card["player"]["top32"], card["player"]["modes"]["1v1 and 2v2"]["top32"]), (True, 12))

    def test_a_head_to_head_gets_its_card_and_its_sets(self):
        h2h = {"player": {"player_id": 1}, "opponent": {"player_id": 2}, "scope": "1v1 sets",
               "tables": [{"columns": ["player", "player_id", "opponent", "opponent_id", "wins", "losses", "sets",
                                       "games_won", "games_lost", "unscored_sets"], "rows": [["Alpha", 1, "Beta", 2, 2, 1, 3, 7, 5, 1]]},
                          {"columns": ["date", "event", "winner", "winner_id", "winner_games", "loser_games"],
                           "rows": [["2024-01-01", "E", "Alpha", 1, 3, 0], ["2024-02-01", "F", "Beta", 2, None, None]],
                           "row_count": 2}]}
        record, sets = Stub(h2h=h2h).build(turn(call("head_to_head", {"player_id": 1, "opponent_id": 2}, h2h),
                                                results(1)))
        self.assertEqual(record["kind"], "head_to_head")
        self.assertEqual(record["record"], {"wins": 2, "losses": 1, "sets": 3, "games_won": 7, "games_lost": 5, "unscored": 1})
        self.assertEqual([s["winner"] for s in sets["sets"]], ["Alpha", "Beta"])
        self.assertEqual(sets["sets"][1], {"date": "2024-02-01", "event": "F", "mode": "1v1", "first_won": False,
                                           "winner": "Beta", "loser": "Alpha", "winner_games": None, "loser_games": None})
        self.assertEqual(record["records"]["2v2"]["sets"], 0)  # no 2v2 rows in the stub

    def test_a_set_list_too_long_for_the_template_keeps_its_count(self):
        h2h = {"player": {"player_id": 1}, "opponent": {"player_id": 2},
               "tables": [{"columns": ["wins", "losses", "games_won"], "rows": [[90, 80, 300]]},
                          {"columns": ["date", "event", "winner", "winner_id", "winner_games", "loser_games"],
                           "row_count": 170, "complete": False}]}
        _, sets = Stub(h2h=h2h).build(turn(call("head_to_head", {}, h2h)))
        self.assertEqual((sets["sets"], sets["total"]), (None, 170))

    def test_one_held_1v1_event_gets_its_top_8_sets(self):
        stub = Stub(sets=[("2019-11-15", "A", 1, 1, "B", 2, 2, 3, 1, 1), ("2019-11-15", "C", 3, 3, "D", 4, 5, 2, 0, 0)])
        (card,) = stub.build(turn(event(["Worlds 2019 / 1v1", "ev1", "2019-11-15", "1v1", None])))
        self.assertEqual((card["kind"], card["title"], card["event"]), ("sets", "Sets between top 8 players", "Worlds 2019 / 1v1"))
        self.assertEqual([(s["winner_games"], s["loser_games"]) for s in card["sets"]], [(3, 1), (None, None)])
        self.assertIn("Not bracket order", card["scope"])

    def test_no_event_card_for_a_cancelled_or_2v2_event_or_several(self):
        for rows in ([["CEO 2020", "e", "2020-03-01", "1v1", "cancelled"]], [["BCX / 2v2", "e", "2022-11-04", "2v2", None]],
                     [["a", "e1", "d", "1v1", None], ["b", "e2", "d", "1v1", None]]):
            self.assertEqual(Stub().build(turn(event(*rows))), [])

    def test_no_cards_without_an_answer_and_at_most_two(self):
        self.assertEqual(Stub().build(turn(results(1), outcome="suggestions")), [])
        two = Stub(sets=[]).build(turn(results(1), event(["a", "e1", "d", "1v1", None]), results(2)))
        self.assertEqual([c["kind"] for c in two], ["comparison", "sets"])

    def test_a_failed_call_is_ignored(self):
        failed = {"name": "player_results", "arguments": {"player_id": 1}, "observation": json.dumps({"error": "x"})}
        self.assertEqual(Stub().build(turn(failed)), [])


def partnership(pid, partner, row=(20, 0, 3, 9, 2), **args):
    out = {"template": "team_results", "player": {"player_id": pid}, "partner": {"player_id": partner},
           "tables": [{"columns": ["player", "partner", "events", "wins", "medals", "top8s", "best"],
                       "rows": [["x", "y", *row]]},
                      {"columns": ["which", "date", "event", "placement"],
                       "rows": [["first", "2022-11-04", "e", 17], ["latest", "2026-09-27", "f", 2]]}]}
    return call("team_results", {"player_id": pid, "partner_id": partner, **args}, out), out


class TeamStub(Stub):
    """A Stub whose team_results calls return the partnership given for that pair."""

    def __init__(self, outs, sets=()):
        super().__init__(players={**PLAYERS, 3: PLAYERS[1], 4: PLAYERS[2]}, sets=sets)
        self.outs = outs

    def call(self, name, args):
        if name == "team_results":
            self.asked.append((name, args))
            return self.outs.get((args["player_id"], args["partner_id"]))
        return super().call(name, args)


class TeamCardsTest(unittest.TestCase):
    def test_two_partnerships_get_the_teams_card_and_their_sets(self):
        (c1, o1), (c2, o2) = partnership(1, 2), partnership(3, 4)
        stub = TeamStub({(1, 2): o1, (3, 4): o2}, sets=[("2026-09-27", "T", None, 1, 3, 2, 1), ("2025-01-01", "U", None, 0, 1, 3, 1)])
        card, listed = stub.build(turn(c1, c2))
        self.assertEqual((card["kind"], card["mode"], card["names"]), ("teams", "2v2", ["Alpha & Beta", "Alpha & Beta"]))
        self.assertEqual({k: card["record"][k] for k in ("wins", "losses", "sets", "games_won", "games_lost")},
                         {"wins": 1, "losses": 1, "sets": 2, "games_won": 4, "games_lost": 5})
        self.assertIn(figures.TEAMS, stub.queried)
        self.assertEqual([(s["winner_games"], s["loser_games"], s["first_won"]) for s in listed["sets"]],
                         [(3, 2, True), (3, 1, False)])
        self.assertEqual(listed["mode"], "2v2")

    def test_one_partnership_gets_the_team_card(self):
        c1, o1 = partnership(1, 2)
        (card,) = TeamStub({(1, 2): o1}).build(turn(c1))
        self.assertEqual(card["kind"], "team")
        self.assertEqual(card["together"], {"events": 20, "wins": 0, "medals": 3, "top8s": 9, "best": 2,
                                            "first": "2022-11-04", "latest": "2026-09-27"})
        self.assertIn("2v2 when the card opens", card["scope"])

    def test_a_narrowed_call_or_a_shared_player_doesnt_make_a_teams_card(self):
        c1, o1 = partnership(1, 2, year=2025)
        self.assertEqual(TeamStub({(1, 2): o1}).build(turn(c1)), [])
        (a, oa), (b, ob) = partnership(1, 2), partnership(1, 3)
        (card,) = TeamStub({(1, 2): oa, (1, 3): ob}).build(turn(a, b))
        self.assertEqual(card["kind"], "team")  # the first partnership only

    def test_the_line_for_the_agent(self):
        (c1, o1), (c2, o2) = partnership(1, 2), partnership(3, 4)
        cards = TeamStub({(1, 2): o1, (3, 4): o2}, sets=[("2026-09-27", "T", None, 1, 3, 2, 1)]).build(turn(c1, c2))
        self.assertIn("A team card: their 2v2 record, Alpha & Beta 1-0 against Alpha & Beta in 1 sets;", figures.summary(cards))
        (card,) = TeamStub({(1, 2): o1}).build(turn(c1))
        self.assertIn("Alpha and Beta together in 2v2: 20 events, 0 wins, 3 medals, 9 top 8s, best placement 2;",
                      figures.summary([card]))

    def test_a_team_head_to_head_call_gets_the_teams_card(self):
        out = {"template": "team_head_to_head", "player": {"player_id": 1}, "partner": {"player_id": 2},
               "opponent": {"player_id": 3}, "opponent_partner": {"player_id": 4}, "tables": []}
        stub = TeamStub({}, sets=[("2026-09-27", "T", None, 1, 3, 2, 1)])
        card, _ = stub.build(turn(call("team_head_to_head", {"player_id": 1, "partner_id": 2, "opponent_id": 3,
                                                             "opponent_partner_id": 4}, out)))
        self.assertEqual((card["kind"], card["record"]["wins"]), ("teams", 1))
        narrowed = call("team_head_to_head", {"player_id": 1, "partner_id": 2, "opponent_id": 3,
                                              "opponent_partner_id": 4, "year": 2025}, out)
        self.assertEqual(TeamStub({}).build(turn(narrowed)), [])
        no_partner = {**out, "opponent_partner": None}
        self.assertEqual(TeamStub({}).build(turn(call("team_head_to_head", {}, no_partner))), [])

    def test_a_held_2v2_event_gets_its_final(self):
        def finalists(rows):
            stub = TeamStub({})
            plain = stub.query
            stub.query = lambda sql, params: rows if sql == figures.FINALISTS else plain(sql, params)
            return stub.build(turn(event(["Autumn / 2v2", "e", "2026-09-27", "2v2", None])))
        (card,) = finalists([(1, 2, 1), (3, 4, 2)])
        self.assertEqual((card["kind"], card["record"]["sets"]), ("teams", 0))
        self.assertIn("Autumn / 2v2's winners", card["scope"])
        self.assertEqual(finalists([(1, 2, 1), (3, 4, 1)]), [])  # a tie at 1st: no final to show


class LegendsTest(unittest.TestCase):
    """A card's legend: the player's main, if the manifest lists it and its file exists; never a guess."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mains, self.art = root / "player_legends.csv", root / "legends"
        self.art.mkdir()
        self.mains.write_text("player_id,legend" + chr(10) + "79853,Bodvar" + chr(10) + "5,ghost" + chr(10) + "6,orion" + chr(10), encoding="utf-8")
        (self.art / "manifest.json").write_text(json.dumps({"legends": {
            "bodvar": {"file": "bodvar.webp", "name": "Bödvar", "offset_y": -20, "scale": 1.1},
            "orion": {"file": "orion.webp", "name": "Orion"}}}), encoding="utf-8")
        (self.art / "bodvar.webp").write_bytes(b"RIFF")
        self.legends = figures.Legends(self.mains, self.art)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_main_with_art(self):
        self.assertEqual(self.legends.of(79853), {"slug": "bodvar", "url": "art/legends/bodvar.webp", "name": "Bödvar",
                                                  "head": None, "offset_x": 0, "offset_y": -20, "scale": 1.1})
        (self.art / "heads").mkdir()
        (self.art / "heads" / "bodvar.webp").write_bytes(b"RIFF")
        manifest = json.loads((self.art / "manifest.json").read_text(encoding="utf-8"))
        manifest["legends"]["bodvar"]["head"] = "heads/bodvar.webp"
        (self.art / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(self.legends.of(79853)["head"], "art/legends/heads/bodvar.webp")

    def test_the_fallback_whenever_anything_is_missing(self):
        self.assertIsNone(self.legends.of(1))  # no main
        self.assertIsNone(self.legends.of(5))  # a main the manifest doesn't list
        self.assertIsNone(self.legends.of(6))  # listed, without its file
        self.assertIsNone(figures.Legends(Path(self.tmp.name) / "none.csv", self.art).of(79853))  # no mains file


@unittest.skipUnless(tools.SNAPSHOT.exists(), "needs eval-v1")
class RealTest(unittest.TestCase):
    """On eval-v1, through the real templates and views."""

    @classmethod
    def setUpClass(cls):
        import react
        cls.cards = figures.Cards(react.Tools())

    def test_lifetime_figures(self):
        raydish = self.cards.lifetime(160000)
        self.assertEqual(raydish["modes"]["1v1 and 2v2"], {"results": 98, "first": 6, "second": 7, "third": 9, "top8": 43,
                                                           "top32": 82})  # the stat cards proposal's table
        self.assertEqual((raydish["modes"]["1v1"]["top32"], raydish["modes"]["2v2"]["top32"]), (45, 37))
        self.assertEqual(raydish["earnings"], {"amount": 83825.0, "source": "Stats API", "as_of": "2026-10-02"})
        self.assertTrue(raydish["crew"])
        self.assertIsNone(self.cards.lifetime(168635)["earnings"]["amount"])  # Impala: unranked, no figure

    def test_head_to_head(self):
        record, sets = self.cards.head_to_head(168635, 149305)
        self.assertEqual({k: record["record"][k] for k in ("wins", "losses", "games_won", "games_lost")},
                         {"wins": 2, "losses": 1, "games_won": 8, "games_lost": 4})
        self.assertEqual([(s["winner"], s["loser"]) for s in sets["sets"]],
                         [("Impala", "BBBalloonBoy"), ("Impala", "BBBalloonBoy"), ("BBBalloonBoy", "Impala")])

    def test_a_head_to_head_has_a_record_in_each_mode_and_its_2v2_sets(self):
        # live, the card's 2v2 switch still showed Raydish and flowerVS's 1v1 record and sets
        card, sets = self.cards.head_to_head(160000, 169119)
        pick = lambda r: (r["wins"], r["losses"], r["sets"])
        self.assertEqual({m: pick(r) for m, r in card["records"].items()},
                         {"1v1": (2, 0, 2), "2v2": (8, 1, 9), "1v1 and 2v2": (10, 1, 11)})  # the template's 2v2 note: 8 of 9
        self.assertEqual(sets["totals"], {"1v1": 2, "2v2": 9})
        twos = [s for s in sets["sets"] if s["mode"] == "2v2"]
        self.assertEqual((len(twos), sum(s["first_won"] for s in twos)), (9, 8))
        self.assertTrue(all(" & " in s["winner"] and " & " in s["loser"] for s in twos))
        self.assertEqual([s["date"] for s in sets["sets"]], sorted(s["date"] for s in sets["sets"]))
        self.assertIn("their 2v2 record, Raydish's teams 8-1 against flowerVS's teams in 9 sets", figures.summary([card]))

    def test_the_line_for_the_agent_says_what_the_cards_showed_in_their_own_words(self):
        line = figures.summary(self.cards.head_to_head(168635, 149305))
        self.assertTrue(line.startswith("Stat cards, at official events; on them MEDALS are GOLD (1st places)"))
        self.assertIn("their 1v1 record, Impala 2-1 against BBBalloonBoy in 3 sets, games 8-4;", line)
        self.assertIn("Impala's career earnings not recorded", line)
        self.assertIn(", Impala beat BBBalloonBoy ", line)
        self.assertEqual(figures.summary([]), "")
        raydish = self.cards.lifetime(160000)
        line = figures.summary([{"kind": "lifetime", "player": raydish}])
        self.assertIn("Raydish in both modes together 98 results, GOLD 6, SILVER 7, BRONZE 9, TOP 8 43, TOP 32 82;", line)
        self.assertIn("career earnings $83,825 (Stats API, as of 2026-10-02)", line)
        many = {"kind": "sets", "title": "Sets between top 8 players", "event": "X", "total": 20,
                "sets": [{"date": "2020-01-01", "winner": "a", "loser": "b", "winner_games": 3, "loser_games": 0}] * 20}
        self.assertIn("A list, Sets between top 8 players at X, of 20 sets.", figures.summary([many]))

    def test_teams_and_a_partnership(self):
        card, listed = self.cards.teams((160000, 142100), (152572, 146616))  # Raydish & megD, Moni- & animefan1266
        self.assertEqual({k: card["record"][k] for k in ("wins", "losses", "games_won", "games_lost")},
                         {"wins": 1, "losses": 0, "games_won": 3, "games_lost": 2})  # Autumn NA 2026, elimination final
        self.assertEqual([p["modes"]["2v2"]["top8"] for team in card["teams"] for p in team], [16, 15, 8, 8])
        self.assertEqual(listed["sets"][0]["winner"], "Raydish & megD")
        team = self.cards.team(160000, 142100)
        self.assertEqual({k: team["together"][k] for k in ("events", "wins", "medals", "top8s", "best")},
                         {"events": 20, "wins": 0, "medals": 3, "top8s": 9, "best": 2})

    def test_a_question_naming_two_teams(self):
        trace = {"outcome": "answered", "question": "raydish megd vs moni and animefan1266", "steps": []}
        card, listed = self.cards.build(trace)
        self.assertEqual((card["kind"], card["names"]), ("teams", ["Raydish & megD", "Moni- & animefan1266"]))
        self.assertEqual((card["record"]["wins"], card["record"]["losses"]), (1, 0))
        mixed = self.cards.named_teams("raydish and moni vs megd and animefan1266")  # paired by the data, not the order
        self.assertEqual({frozenset(t) for t in mixed}, {frozenset((160000, 142100)), frozenset((152572, 146616))})
        self.assertIsNone(self.cards.named_teams("raydish vs megd"))
        self.assertIsNone(self.cards.named_teams("compare raydish, megd, moni and animefan1266 wins"))

    def test_a_2v2_events_final(self):
        event = {"event_id": "774eaef2-3f11-4c7b-f9ab-08ded4cb1c05", "name": "Autumn Championship NA 2026 2v2"}
        card = self.cards.final(event)[0]
        self.assertEqual([sorted(p["player_id"] for p in t) for t in card["teams"]],
                         [[141522, 142042], [142100, 160000]])  # Pink | Zen & hideawaybh, then Raydish & megD
        self.assertIn("winners", card["scope"])

    def test_an_events_top_8_sets(self):
        card = self.cards.event_sets({"event_id": "tournament/dreamhack-atlanta-2019/event/brawlhalla-1v1", "name": "x",
                                      "date": "2019-11-15"})
        self.assertGreater(len(card["sets"]), 0)
        rows = self.cards.query("SELECT COUNT(*) FROM v_sets_1v1 WHERE event_id = ? AND (winner_placement > 8 OR"
                                " loser_placement > 8)", ("tournament/dreamhack-atlanta-2019/event/brawlhalla-1v1",))
        self.assertGreater(rows[0][0], 0)  # the event has other sets, which the card leaves out


if __name__ == "__main__":
    unittest.main()
