import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import retrieval  # noqa: E402


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
