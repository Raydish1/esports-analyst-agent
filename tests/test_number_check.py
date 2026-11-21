import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import number_check  # noqa: E402
from number_check import Evidence  # noqa: E402

SET = {"complete": True, "columns": ["winner_name", "loser_name", "winner_games", "loser_games", "start_date", "start_time"],
       "rows": [["Zivai", "Impala", 3, 0, "2023-07-07", 1688930865]], "row_count": 1}  # 2023-07-09 19:27:45 UTC
RECORD = {"template": "head_to_head", "tables": [  # q04 in the template tools' after run
    {"what": "Impala's 1v1 record against BBBalloonBoy, in sets", "columns": ["player", "player_id", "opponent",
     "opponent_id", "wins", "losses", "sets", "games_won", "games_lost", "unscored_sets"],
     "rows": [["Impala", 168635, "BBBalloonBoy", 149305, 2, 1, 3, 8, 4, 0]], "row_count": 1}]}
MEDALS = {"complete": True, "columns": ["player_id", "mode", "gold", "silver", "bronze", "total_medals"],
          "rows": [[74433, "1v1", 30, 6, 6, 42], [74433, "2v2", 18, 4, 5, 27]], "row_count": 2}


def evidence(*observations, question="", calls=()):
    found = Evidence()
    found.ask(question)
    for observation in observations:
        found.observe(observation)
    for arguments in calls:
        found.call(arguments)
    return found


def flagged(found, answer):
    return [c.text for c in found.unsupported(answer)]


class ClaimsTest(unittest.TestCase):
    def test_an_answer_is_read_by_kind_so_a_dates_parts_arent_also_numbers(self):
        found = number_check.claims("On March 10, 2024, Boomie placed 2nd of 32 in 2v2 (5-4 in sets, 64% of games) for"
                                    " $1,200, a top 8 and three wins.\n1. Zivai at 19:27 UTC")
        self.assertEqual([(c.kind, c.text) for c in found], [
            ("date", "March 10, 2024"), ("category", "2nd"), ("number", "32"), ("format", "2v2"), ("record", "5-4"),
            ("percent", "64%"), ("money", "$1,200"), ("category", "top 8"), ("word", "three"), ("list", "1."),
            ("time", "19:27 UTC")])

    def test_digits_inside_names_and_fractions_arent_claims(self):
        self.assertEqual(number_check.claims("tike36 and Marckiem00 at SEA League Week 1/4"), [])

    def test_what_an_answer_asks_and_its_code_state_nothing_and_the_rest_keeps_its_place(self):
        live = ('To provide a detailed 2v2 record, please clarify:\n- Or a specific event\'s 2v2 bracket (e.g., "top 8 of'
                ' the Europe Summer 2022 2v2")?\n- **Event-focused**: Use `event_results(event="...", top=8)`.\n'
                "Let me know the specifics!")  # live, 20261119T233544Z-002 turn 7: sent back for 8 and 2022
        said = number_check.stated(live)
        self.assertEqual((len(said), [c.text for c in number_check.claims(said)]), (len(live), ["2v2"]))
        self.assertEqual(said[:50], live[:50])
        answer = "Raydish has 6 wins. Want the 2022 list?\n```sql\nSELECT 7\n```\nUse `top=1` for 3 of them."
        self.assertEqual([(c.text, c.start) for c in number_check.claims(number_check.stated(answer))],
                         [("6", answer.index("6")), ("3", answer.index("3 of"))])
        self.assertEqual(flagged(evidence({"wins": 6}), answer), ["3"])  # the question, the SQL and top=1 aren't claims
        found = evidence(question="what did raydish get on March 10, 2024?")  # a user's question is still evidence
        self.assertEqual(flagged(found, "On March 10, 2024 he placed 5th."), ["5th"])

    def test_a_name_ending_in_a_question_mark_asks_nothing_and_a_question_keeps_the_numbering_before_it(self):
        listed = ("1. **gdsandstorm** - $258,984.17\n2. **Zivai** - $214,458.33\n3. **acno?** - $189,215.00\n"
                  "4. **whoiskyna** - $161,110.00")  # q05 seeds 0 and 2 on 2026-11-19: its 3 went back
        self.assertEqual(number_check.stated(listed), listed)
        earnings = {"complete": True, "columns": ["name", "earnings_usd"], "rows": [
            ["gdsandstorm", 258984.17], ["Zivai", 214458.33], ["acno?", 189215.0], ["whoiskyna", 161110.0]]}
        self.assertEqual(flagged(evidence(earnings), listed), [])
        plain = "2. Zivai - $214,458.33\n3. acno? - $189,215.00"  # not bold: a question to the reader, numbering kept
        self.assertEqual([(c.kind, c.text) for c in number_check.claims(number_check.stated(plain))],
                         [("list", "2."), ("money", "$214,458.33"), ("list", "3."), ("money", "$189,215.00")])
        asked = "1. Did you mean **Raydish**?\n2. Or the top 8?"  # questions in a list still state nothing
        self.assertEqual([c.text for c in number_check.claims(number_check.stated(asked))], ["1.", "2."])


class EvidenceTest(unittest.TestCase):
    def test_a_number_a_result_holds_is_supported_and_one_it_doesnt_isnt(self):
        found = evidence(RECORD)
        self.assertEqual(flagged(found, "Impala won 2 of 3 sets, 8 games to 4."), [])
        self.assertEqual(flagged(found, "BBBalloonBoy won 5 games."), ["5"])  # q04 seed 1: the data has 4

    def test_a_record_needs_both_numbers_in_one_row_in_either_order(self):
        found = evidence(RECORD, {"complete": True, "columns": ["n"], "rows": [[3], [3]], "row_count": 2})
        self.assertEqual(flagged(found, "Impala leads 2-1, and BBBalloonBoy trails 1–2."), [])
        self.assertEqual(flagged(found, "It's 3-3 in all."), ["3-3"])  # two rows' 3s, not one row's
        self.assertEqual(flagged(evidence({"years": [2019, 2021]}), "From 2019–2021."), [])  # a range: each year

    def test_dates_match_a_results_date_or_a_timestamps_utc_date_in_any_form(self):
        found = evidence(SET)
        self.assertEqual(flagged(found, "Held on July 7, 2023 (2023-07-07), the final was on 9 July 2023, in July"
                                        " 2023, on July 9."), [])
        self.assertEqual(flagged(found, "It was on July 8, 2023."), ["July 8, 2023"])

    def test_a_clock_time_must_be_a_timestamps_utc_time(self):
        found = evidence(SET)
        self.assertEqual(flagged(found, "It started at 19:27 UTC, or 7:27 PM."), [])
        for time in ("11:47 AM UTC", "16:47", "1:47:45 PM UTC", "21:27 CEST"):  # q20's answers, and another zone
            self.assertEqual(flagged(found, f"It started at {time}."), [time])

    def test_an_amount_matches_at_the_precision_it_shows_keeping_two_significant_digits(self):
        found = evidence({"complete": True, "columns": ["earnings_usd"], "rows": [[258984.17]], "row_count": 1})
        self.assertEqual(flagged(found, "$258,984.17, or $258,984, $259K, $0.26 million and $260,000."), [])
        self.assertEqual(flagged(found, "About $300K, or $12,500."), ["$300K", "$12,500"])  # q32 seed 2's, unread

    def test_a_rate_is_a_value_as_shown_or_two_numbers_of_one_row_divided(self):
        found = evidence({"complete": True, "columns": ["player_id", "wins", "losses"], "rows": [[71736, 3, 2]],
                          "row_count": 1}, {"rate": 0.6429})
        self.assertEqual(flagged(found, "A 3-2 record: 60%, or 0.6 of their sets, and 64.3% of games (0.64)."), [])
        self.assertEqual(flagged(found, "A 75% win rate."), ["75%"])

    def test_arithmetic_isnt_a_derivation(self):
        self.assertEqual(flagged(evidence(MEDALS), "gdsandstorm has 69 medals: 42 in 1v1 and 27 in 2v2."), ["69"])
        found = evidence({"complete": True, "columns": ["player_id", "wins", "losses"], "rows": [[71736, 3, 2]],
                          "row_count": 1})
        self.assertEqual(flagged(found, "They met 5 times."), ["5"])  # 3 + 2

    def test_the_prompts_categories_formats_and_list_numbers_are_always_supported(self):
        self.assertEqual(flagged(evidence(), "These count 1st, 2nd or 3rd places, in 1v1 and 2v2:\n1. Boomie\n2. Zivai"), [])
        # q35 seed 0 in 20261117-grounding-before, with no tool called: the sentence held the answer's main claim
        self.assertEqual(flagged(evidence(), "Tools give a player's wins, medals, top 8 placements and Top-3s, but no"
                                             " recorded data links players to legends."), [])
        self.assertEqual(flagged(evidence(), "Raydish's top 5."), ["top 5"])  # a cutoff the prompt doesn't define

    def test_a_number_word_after_the_refers_back_to_what_was_named(self):
        found = evidence(question="who has earned more money, raydish or impala?")
        self.assertEqual(flagged(found, "Therefore, Raydish has earned more money between the two."), [])  # q45 seed 1
        self.assertEqual(flagged(found, "These two players, and those three: Raydish won two events."), ["two"])

    def test_a_placement_or_rank_may_restate_the_querys_own_condition(self):
        found = evidence({"complete": True, "columns": ["winner_name", "loser_name"], "rows": [["Zivai", "Impala"]],
                          "row_count": 1}, calls=[{"query": "SELECT ... WHERE winner_placement = 1 AND loser_placement = 2"}])
        self.assertEqual(flagged(found, "Zivai (placement 1) faced Impala (placement 2), as confirmed by the placement"
                                        " (winner_placement = 1, loser_placement = 2)."), [])  # q20 seeds 0 and 2
        self.assertEqual(flagged(found, "Impala was ranked 4 there."), ["ranked 4"])

    def test_what_the_question_writes_is_supported_its_place_words_included(self):
        found = evidence(question="How many times did Ahmet finish second to Godly in 2026? Did he win 3-0?")
        self.assertEqual(flagged(found, "In 2026, a placement of 2 behind Zivai, never 3-0."), [])
        self.assertEqual(flagged(found, "Twice, or four times in 2025."), ["four", "in 2025"])  # 'second' holds 2

    def test_a_scope_phrase_may_cite_the_querys_own_conditions(self):
        found = evidence(calls=[{"query": "SELECT ... HAVING COUNT(*) >= 5"}, {"player_id": 7, "top": 8, "year": 2024}])
        self.assertEqual(flagged(found, "Among players with at least 5 matches, in 2024, in the top 8."), [])
        self.assertEqual(flagged(found, "Boomie has 5 wins."), ["5"])  # a condition isn't a result

    def test_an_error_isnt_evidence_since_it_repeats_what_the_call_asked(self):
        found = evidence({"error": "player_id 12345 wasn't returned by any tool in this conversation"})
        self.assertEqual(flagged(found, "Player 12345 has it."), ["12345"])

    def test_the_numbers_of_a_name_or_an_event_title_a_result_holds_are_supported(self):
        found = evidence({"complete": True, "columns": ["tournament_name"], "rows": [["BCX 2023"], ["Season 4"]],
                          "row_count": 2})
        self.assertEqual(flagged(found, "BCX 2023 and Season 4, not BCX 2022."), ["2022"])


CARD = [{"shown": clause} for clause in [  # the page's line, a clause a row, as Conversation.shown observes it (finding 22)
    "Phazon in 1v1 only 76 results, GOLD 0, SILVER 3, BRONZE 9, TOP 8 28",
    "Phazon in 2v2 only 63 results, GOLD 12, SILVER 15, BRONZE 6, TOP 8 51",
    "Phazon in both modes together 139 results, GOLD 12, SILVER 18, BRONZE 15, TOP 8 79",
    "Cody Travis in both modes together 122 results, GOLD 10, SILVER 19, BRONZE 11, TOP 8 71"]]
COUNTED = {"template": "player_results", "tables": [{"what": "Boomie's results, counted by mode",
           "columns": ["player", "mode", "results", "wins"], "rows": [["Boomie", "1v1", 40, 12], ["Boomie", "2v2", 30, 9],
                                                                      ["Boomie", "1v1 and 2v2", 70, 21]]}]}
NAMES = {"phazon": "Phazon", "cody travis": "Cody Travis", "boomie": "Boomie", "impala": "Impala",
         "bbballoonboy": "BBBalloonBoy"}


class AgreementTest(unittest.TestCase):
    def unsupported(self, answer, *observations):
        window = number_check.Window(evidence(*observations), names=NAMES)
        return [(c.text, c.about) for c in window.unsupported(answer)]

    def test_a_figure_about_one_mode_needs_a_row_about_that_mode(self):
        self.assertEqual(self.unsupported("Phazon has 12 gold medals in 1v1.", *CARD), [("12", "Phazon in 1v1")])  # live
        self.assertEqual(self.unsupported("Phazon has 12 golds in 2v2, and 12 in both modes together.", *CARD), [])
        self.assertEqual(self.unsupported("In 1v1, Phazon has 0 golds and 76 results.", *CARD), [])
        self.assertEqual(self.unsupported("Boomie has 21 wins in 1v1.", COUNTED), [("21", "Boomie in 1v1")])
        self.assertEqual(self.unsupported("Boomie has 12 1v1 wins, and 21 in 1v1 and 2v2.", COUNTED), [])

    def test_a_figure_about_one_player_needs_a_row_about_that_player(self):
        self.assertEqual(self.unsupported("Phazon's card shows 10 golds.", *CARD), [("10", "Phazon")])  # live: Cody's 10
        self.assertEqual(self.unsupported("Cody Travis's card shows 10 golds.", *CARD), [])
        self.assertEqual(self.unsupported("Cody Travis has 10 golds and Phazon 12.", *CARD), [])  # two players: either row

    def test_a_row_naming_no_player_or_mode_fits_any_claim_and_a_record_needs_a_fitting_row(self):
        self.assertEqual(self.unsupported("Phazon has 12 wins in 1v1.", *CARD, {"wins": 12}), [])
        self.assertEqual(self.unsupported("Impala is 2-1 against BBBalloonBoy in 1v1.", RECORD), [])
        self.assertEqual(self.unsupported("In 2v2, Phazon is 15-6.", *CARD), [])
        self.assertEqual(self.unsupported("In 1v1, Phazon is 15-6.", *CARD), [("15-6", "Phazon in 1v1")])


PAIRS = {"template": "rank_pairs", "tables": [{"what": "pairs of opponents", "columns": ["rank", "player", "player_id",
         "opponent", "opponent_id", "sets", "player_wins", "opponent_wins"],
         "rows": [[1, "SiB | Wess", 37977, "lFiend", 148891, 34, 15, 19], [1, "yuz", 73254, "whoiskyna", 135748, 34, 17, 17],
                  [3, "gdsandstorm", 74433, "Boomie", 146606, 28, 19, 9]]}]}


class CountWordTest(unittest.TestCase):
    def unsupported(self, answer):
        return [c.text for c in number_check.Window(evidence(PAIRS)).unsupported(answer)]

    def test_a_count_word_counting_tied_rows_or_the_top_of_a_ranking_is_supported(self):
        self.assertEqual(self.unsupported("The top two tied at 34 sets."), [])  # live, finding 30
        self.assertEqual(self.unsupported("Two pairs share the most sets, 34."), [])
        self.assertEqual(self.unsupported("The top three are below."), [])
        self.assertEqual(self.unsupported("Five pairs tied at 34 sets."), ["Five"])  # two rows hold 34, not five
        self.assertEqual(self.unsupported("The top four are below."), ["four"])  # the ranking has three rows

    def test_a_left_out_claim_that_restates_kept_numbers_needs_no_line(self):
        cut = [{"claim": "The top two tied at 34 sets.", "numbers": ["two"], "replacement": ""}]
        self.assertTrue(number_check.restates(cut, "1. SiB | Wess and lFiend, 34 sets"))
        self.assertFalse(number_check.restates(cut, "1. SiB | Wess and lFiend"))
        self.assertFalse(number_check.restates([{"claim": "Both tied.", "numbers": ["Both"], "replacement": ""}], "34"))


VOLST = {"template": "rank_pairs", "tables": [{"what": "volst's opponents", "columns": ["rank", "player", "player_id",
         "opponent", "opponent_id", "sets", "player_wins", "opponent_wins"],
         "rows": [[1, "volst", 162675, "Raydish", 160000, 3, 1, 2], [1, "volst", 162675, "woolala", 170001, 3, 3, 0]]}]}
SIDE_NAMES = {"volst": "volst", "raydish": "Raydish", "woolala": "woolala"}


class RecordSideTest(unittest.TestCase):
    def flagged(self, answer, *observations, subject=None):
        window = number_check.Window(evidence(*observations), names=SIDE_NAMES, subject=subject)
        return [(c.text, c.reversed) for c in window.unsupported(answer)]

    def test_a_list_of_one_players_opponents_is_read_from_that_players_side(self):
        listed = "1. **woolala** (3 sets, 3-0 record)\n2. **Raydish** (3 sets, 2-1 record)"  # live, finding 34
        self.assertEqual(self.flagged(listed, VOLST, subject="volst"), [("2-1", True)])
        self.assertEqual(self.flagged("1. **Raydish** (3 sets, 1-2 record)", VOLST, subject="volst"), [])
        self.assertEqual(self.flagged("Raydish holds a 2-1 lead over volst.", VOLST, subject="volst"), [])
        self.assertEqual(self.flagged("volst and Raydish have a 1-2 record.", VOLST), [])  # the first of them
        self.assertEqual(self.flagged("volst does best against **woolala** (3-0) and **Raydish** (1-2).", VOLST), [])
        self.assertEqual(self.flagged("- **Winner**: Raydish (2-1)", VOLST, subject="volst"), [])  # his own score

    def test_a_record_written_the_other_way_round_for_its_player_goes_back(self):
        self.assertEqual(self.flagged("volst is 2-1 against Raydish.", VOLST), [("2-1", True)])  # live, finding 34
        self.assertEqual(self.flagged("volst is 1-2 against Raydish, and 3-0 against woolala.", VOLST), [])
        note = {"notes": ["In 1v1, volst won 1 and lost 2 of their 3 sets against Raydish; Raydish won 2 and lost 1."]}
        self.assertEqual(self.flagged("volst went 2-1 against Raydish.", note), [("2-1", True)])
        self.assertEqual(self.flagged("Raydish went 2-1 against volst.", note), [])

    def test_the_owner_is_the_first_player_named_who_isnt_the_object_and_a_loss_is_left_unread(self):
        self.assertEqual(self.flagged("Raydish beat volst 2-1.", VOLST), [])  # Raydish's record
        self.assertEqual(self.flagged("Against Raydish, volst is 1-2.", VOLST), [])
        self.assertEqual(self.flagged("volst lost 2-1 to Raydish.", VOLST), [])  # a loss, written either way
        self.assertEqual(self.flagged("The series was 2-1.", VOLST), [])  # no one's record


class ReplacementTest(unittest.TestCase):
    def replaced(self, answer, *observations):
        found = evidence(*observations)
        return number_check.without(answer, found.unsupported(answer))

    def test_the_sentence_holding_an_unsupported_number_is_left_out_and_the_others_stay(self):
        text, replaced = self.replaced(  # q20 seed 2 in the template tools' after run
            "The 1v1 grand final was won by **Zivai** with a score of **3-0** against **Impala**. The match started at"
            " **July 7, 2023, 1:47:45 PM UTC**.", SET)
        self.assertEqual(text, "The 1v1 grand final was won by **Zivai** with a score of **3-0** against **Impala**.")
        self.assertEqual(replaced, [{"claim": "The match started at **July 7, 2023, 1:47:45 PM UTC**.",
                                     "replacement": "", "numbers": ["1:47:45 PM UTC"]}])
        text, _ = self.replaced("It's 1:47:45 PM UTC. Zivai won 3-0.", SET)  # a sentence before another, its space too
        self.assertEqual(text, "Zivai won 3-0.")

    def test_an_abbreviation_doesnt_end_a_sentence(self):
        text, _ = self.replaced("It was **Zivai (3) vs. Impala (0)**. The match was at 11:47 AM UTC, a 3-0 win.", SET)
        self.assertEqual(text, "It was **Zivai (3) vs. Impala (0)**.")

    def test_a_list_item_goes_with_its_line_and_a_table_cell_says_not_confirmed(self):
        text, _ = self.replaced("Their record:\n- **BBBalloonBoy**: 1 win, 2 losses, 5 games won.\n| Impala | 5 |", RECORD)
        self.assertEqual(text, "Their record:\n| Impala | not confirmed |")  # live: half an answer was such lines
        text, _ = self.replaced("### 2024 Spring Championship\nImpala won 2 of 3 sets.", RECORD)  # a heading goes too
        self.assertEqual(text, "Impala won 2 of 3 sets.")

    def test_the_line_saying_claims_were_left_out_states_no_number(self):
        self.assertEqual(number_check.left_out([{}]), "(I left out a statement I couldn't confirm from the data.)")
        self.assertEqual(number_check.left_out([{}, {}]), "(I left out some statements I couldn't confirm from the data.)")
        self.assertEqual([c for line in (number_check.left_out([{}]), number_check.left_out([{}, {}]))
                          for c in number_check.claims(line)], [])  # nothing for a check to read as a claim

    def test_a_number_written_twice_in_a_text_counts_twice(self):
        note = {"notes": ["In 2v2, whoiskyna's teams and yüz's teams met in 22 sets: whoiskyna's side won 11 and lost 11."]}
        self.assertEqual(flagged(evidence(note), "In 2v2 their teams split 11-11 in 22 sets."), [])  # live: replaced
        self.assertEqual(flagged(evidence({"notes": ["won 11 of 22"]}), "It's 11-11."), ["11-11"])  # one 11: no record
        self.assertEqual(flagged(evidence({"notes": ["1,350 games"]}), "1-1"), ["1-1"])  # a comma's parts count once

    def test_a_replaced_answer_holds_no_unsupported_number(self):
        answer = ("Boomie has **80 total medals** (34 in 1v1, 46 in 2v2), and gdsandstorm 69.\n\n- 42 in 1v1\n- 27 in"
                  " 2v2\n\nThat's 11 more.")
        found = evidence(MEDALS)
        text, replaced = number_check.without(answer, found.unsupported(answer))
        self.assertEqual(found.unsupported(text), [])
        self.assertEqual([r["numbers"] for r in replaced], [["80", "34", "46", "69"], ["11"]])


if __name__ == "__main__":
    unittest.main()
