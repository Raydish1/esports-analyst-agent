import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
from names import normalize  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_drops_tags_accents_case_and_punctuation(self):
        self.assertEqual(normalize("Pink | Guichabou"), "guichabou")
        self.assertEqual(normalize("Machèèèèté"), "macheeeete")
        self.assertEqual(normalize("STING RAY"), normalize("sting-ray!"))
        self.assertEqual(normalize(None), "")


if __name__ == "__main__":
    unittest.main()
