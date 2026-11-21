import re
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


class RoundFiveTest(unittest.TestCase):
    def test_placeholder_slots_are_found_and_links_or_the_page_note_are_not(self):
        slots = "**Opponent**: [Opponent Name]\n**Wins**: [X] wins, a X-Y record"  # live, finding 33
        self.assertEqual(texts(claim_check.placeholders(slots)), ["[Opponent Name]", "[X]", "X-Y"])
        self.assertEqual(claim_check.placeholders("See [the bracket](https://start.gg/x) and [The page showed it]"), [])

    def test_a_relaxation_and_a_characterization_are_found_unless_the_question_uses_one(self):
        self.assertEqual(texts(claim_check.relaxed("I removed the 5-set minimum, so here they are.")),
                         ["removed the 5-set minimum"])
        self.assertEqual(texts(claim_check.characterizations("Raydish dominates the head-to-head series.", "q")),
                         ["dominates"])  # live, finding 35: a 2-1 series
        self.assertEqual(claim_check.characterizations("It was dominated by Zivai.", "the most dominant win"), [])
        self.assertEqual(claim_check.characterizations("Neither player dominated.", "q"), [])
        self.assertEqual(claim_check.characterizations("Zivai's most dominant win was BCX 2023.", "q"), [])


class WritingTest(unittest.TestCase):
    def test_tool_talk_is_found_and_a_sentence_keeps_its_facts_without_it(self):
        said = "Phazon's 12 golds are 2v2 1st places (checked with `player_results(player_id=147522)`)."  # finding 32
        self.assertEqual([c.text.strip() for c in claim_check.tool_talk(said)],
                         ["(checked with `player_results(player_id=147522)`)"])
        facts = lambda text: bool(re.search(r"\d", text))  # noqa: E731
        self.assertEqual(claim_check.without_tool_talk(said, facts), "Phazon's 12 golds are 2v2 1st places.")
        self.assertEqual(claim_check.without_tool_talk("I used `rank_pairs` to rank them. Wess leads, 34 sets.", facts),
                         "Wess leads, 34 sets.")
        self.assertEqual(claim_check.tool_talk("The player results are below."), [])

    def test_an_order_said_to_be_requested_is_found_only_when_the_question_asked_for_none(self):
        said = "Here are the three sets, most recent first as requested:"  # live, finding 35
        self.assertEqual(texts(claim_check.unasked(said, "what are the three sets that volst vs'd raydish")),
                         ["as requested"])
        self.assertEqual(claim_check.unasked(said, "list them newest first"), [])


if __name__ == "__main__":
    unittest.main()
