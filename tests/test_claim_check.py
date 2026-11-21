import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import claim_check  # noqa: E402


def texts(found):
    return [c.text for c in found]


class ReferralTest(unittest.TestCase):
    def test_sending_the_user_to_the_database_or_deferring_the_analysis_is_found(self):
        for answer in ["For the full medal count, you can query v_player_medals.",  # live, finding 22
                       "To confirm their highest placement, further analysis of each event would be needed.",  # 26
                       "Run this query to see every set.", "Check the v_results view for the rest.",
                       "This would require additional queries."]:
            with self.subTest(answer=answer):
                self.assertTrue(claim_check.referrals(answer), answer)

    def test_a_fenced_block_of_sql_is_found_whole_and_taken_out(self):
        answer = "Here it is:\n\n```sql\nSELECT COUNT(*)\nFROM v_results\n```\n\nmegD has 2 results."
        self.assertEqual(texts(claim_check.referrals(answer)), ["```sql\nSELECT COUNT(*)\nFROM v_results\n```"])
        self.assertEqual(claim_check.without_code(answer), "Here it is:\n\nmegD has 2 results.")

    def test_a_link_for_the_user_or_a_statement_about_the_data_is_no_referral(self):
        for answer in ["You can check the bracket at https://start.gg/tournament/bcx-2022.",
                       "The data covers official events only.", "megD's results are in the table below."]:
            with self.subTest(answer=answer):
                self.assertEqual(claim_check.referrals(answer), [])


class JudgmentTest(unittest.TestCase):
    def test_calling_a_result_wrong_is_found(self):
        for answer in ["The 513th at Combo Breaker Online 2020 is likely a data anomaly.",  # live, finding 27
                       "This conflicts with the stat card's 10 golds.",  # finding 22
                       "There's a discrepancy between the two counts.", "That placement may be an error."]:
            with self.subTest(answer=answer):
                self.assertTrue(claim_check.judgments(answer, "renivic's 2v2 placements", ""), answer)

    def test_a_denied_judgment_a_question_about_errors_or_a_marker_in_view_isnt_checked(self):
        self.assertEqual(claim_check.judgments("There is no discrepancy: both say 12.", "on the card", ""), [])
        self.assertEqual(claim_check.judgments("That isn't an error in the data.", "what?", ""), [])
        self.assertEqual(claim_check.judgments("It's likely a data error.", "is the 513th an error?", ""), [])
        self.assertEqual(claim_check.judgments("Its standings are a data error.", "sea league week 1",
                                               '{"status": "placements_unreliable"}'), [])

    def test_overlapping_patterns_give_one_claim(self):
        self.assertEqual(texts(claim_check.judgments("It is likely an error in the data.", "q", "")), ["likely an error"])


if __name__ == "__main__":
    unittest.main()
