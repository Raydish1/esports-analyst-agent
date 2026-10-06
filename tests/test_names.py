import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from names import normalize, normalize_full, normalize_words  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_drops_tags_accents_case_and_punctuation(self):
        self.assertEqual(normalize("Pink | Guichabou"), "guichabou")
        self.assertEqual(normalize("Machèèèèté"), "macheeeete")
        self.assertEqual(normalize("STING RAY"), normalize("sting-ray!"))
        self.assertEqual(normalize(None), "")
        self.assertEqual(normalize_full("Pink | Guichabou"), "pinkguichabou")  # a display name keeps its tag
        self.assertEqual(normalize_full("★★"), "")

    def test_event_aliases_keep_one_space_between_words(self):
        self.assertEqual(normalize_words("BCX  2022!"), "bcx 2022")
        self.assertEqual(normalize_words(" Worlds-2019 "), "worlds 2019")
        self.assertEqual(normalize_words("Dreamhack Atlantà_2018"), "dreamhack atlanta 2018")
        self.assertEqual(normalize_words(None), "")


if __name__ == "__main__":
    unittest.main()
