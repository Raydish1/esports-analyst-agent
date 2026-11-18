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
            ("date", "March 10, 2024"), ("medal", "2nd"), ("number", "32"), ("format", "2v2"), ("record", "5-4"),
            ("percent", "64%"), ("money", "$1,200"), ("scope", "top 8"), ("word", "three"), ("list", "1."),
            ("time", "19:27 UTC")])

    def test_digits_inside_names_and_fractions_arent_claims(self):
        self.assertEqual(number_check.claims("tike36 and Marckiem00 at SEA League Week 1/4"), [])


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

    def test_medal_places_formats_and_list_numbers_are_always_supported(self):
        self.assertEqual(flagged(evidence(), "These count 1st, 2nd or 3rd places, in 1v1 and 2v2:\n1. Boomie\n2. Zivai"), [])

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


class ReplacementTest(unittest.TestCase):
    def replaced(self, answer, *observations):
        found = evidence(*observations)
        return number_check.without(answer, found.unsupported(answer))

    def test_the_sentence_holding_an_unsupported_number_is_replaced_and_the_others_stay(self):
        text, replaced = self.replaced(  # q20 seed 2 in the template tools' after run
            "The 1v1 grand final was won by **Zivai** with a score of **3-0** against **Impala**. The match started at"
            " **July 7, 2023, 1:47:45 PM UTC**.", SET)
        self.assertEqual(text, "The 1v1 grand final was won by **Zivai** with a score of **3-0** against **Impala**."
                               " I couldn't confirm the time from the data.")
        self.assertEqual(replaced, [{"claim": "The match started at **July 7, 2023, 1:47:45 PM UTC**.",
                                     "replacement": "I couldn't confirm the time from the data.",
                                     "numbers": ["1:47:45 PM UTC"]}])

    def test_an_abbreviation_doesnt_end_a_sentence(self):
        text, _ = self.replaced("It was **Zivai (3) vs. Impala (0)**. The match was at 11:47 AM UTC, a 3-0 win.", SET)
        self.assertEqual(text, "It was **Zivai (3) vs. Impala (0)**. I couldn't confirm the time from the data.")

    def test_a_list_item_keeps_its_markup_and_a_table_cell_is_replaced_alone(self):
        text, _ = self.replaced("Their record:\n- **BBBalloonBoy**: 1 win, 2 losses, 5 games won.\n| Impala | 5 |", RECORD)
        self.assertEqual(text, "Their record:\n- I couldn't confirm the number of games won from the data.\n"
                               "| Impala | I couldn't confirm the number from the data. |")

    def test_the_replacement_says_what_the_claim_was_about_without_its_number(self):
        cases = [("V3M_T4NQUIL0 has **$12,500 in career earnings** as of 2023.", "the career earnings"),
                 ("They're called \"Worlds 2016\" in the data.", "the year"),
                 ("His rival is player_id 12345.", "the player ID"),
                 ("A 75% win rate.", "the win rate"),
                 ("On July 8, 2023 at 16:47 UTC.", "the date and the time")]
        for answer, what in cases:
            self.assertEqual(self.replaced(answer, SET)[0], f"I couldn't confirm {what} from the data.", answer)

    def test_a_replaced_answer_holds_no_unsupported_number(self):
        answer = ("Boomie has **80 total medals** (34 in 1v1, 46 in 2v2), and gdsandstorm 69.\n\n- 42 in 1v1\n- 27 in"
                  " 2v2\n\nThat's 11 more.")
        found = evidence(MEDALS)
        text, replaced = number_check.without(answer, found.unsupported(answer))
        self.assertEqual(found.unsupported(text), [])
        self.assertEqual([r["numbers"] for r in replaced], [["80", "34", "46", "69"], ["11"]])


if __name__ == "__main__":
    unittest.main()
