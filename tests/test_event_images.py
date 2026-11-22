import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import event_images  # noqa: E402

EVENTS = [("cm1", "challengermode", "u1", 9), ("sg1", "startgg", "ceo-2025", 8), ("sg2", "startgg", "ceo-2025", 7),
          ("cm2", "challengermode", "u2", 6), ("sg3", "startgg", "old", 1)]


class EventImagesTest(unittest.TestCase):
    def test_the_logo_is_start_ggs_profile_image_or_challengermodes_logo(self):
        sgg = {"tournament": {"images": [{"type": "banner", "url": "b"}, {"type": "profile", "url": "p", "width": 500,
                                                                           "height": 500}]}}
        self.assertEqual(event_images.logo_of("startgg", sgg), ("p", 500, 500))
        self.assertIsNone(event_images.logo_of("startgg", {"tournament": {"images": [{"type": "banner", "url": "b"}]}}))
        cm = {"tournament": {"links": {"logo": {"url": "l", "width": 256, "height": 256}}}}
        self.assertEqual(event_images.logo_of("challengermode", cm), ("l", 256, 256))
        self.assertIsNone(event_images.logo_of("challengermode", {"tournament": {"links": {"logo": None}}}))
        self.assertIsNone(event_images.logo_of("challengermode", None))

    def test_the_pilot_takes_the_newest_of_each_platform_and_the_players_events(self):
        with mock.patch.object(event_images, "PILOT", 1):
            self.assertEqual([r[0] for r in event_images.pick(EVENTS, True)], ["cm1", "sg1"])
            self.assertEqual([r[0] for r in event_images.pick(EVENTS, True, {"sg3"})], ["cm1", "sg1", "sg3"])
        self.assertEqual(event_images.pick(EVENTS, False), EVENTS)

    def test_file_names_are_safe_and_typed(self):
        self.assertEqual(event_images.file_name("startgg-ceo-2024-6", "image/png"), "startgg-ceo-2024-6.png")
        self.assertEqual(event_images.file_name("a/b c", "image/jpeg; q=1"), "a_b_c.jpg")

    def test_the_list_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(event_images, "LIST", Path(tmp) / "l.csv"):
            rows = {"e": {"event_id": "e", "platform": "startgg", "file": "x.png", "width": 500}}
            event_images.write_list(rows)
            self.assertEqual(event_images.read_list()["e"]["file"], "x.png")


if __name__ == "__main__":
    unittest.main()
