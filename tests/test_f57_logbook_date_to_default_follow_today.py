import unittest
from datetime import datetime, timedelta

from gui.tabs.logbook import _normalize_loaded_date_to_filter


class F57LogbookDateToDefaultFollowTodayTests(unittest.TestCase):
    def test_stale_date_to_in_default_filters_is_migrated_to_today(self) -> None:
        stale = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        out = _normalize_loaded_date_to_filter(
            stale,
            {
                "text": "",
                "date_from": "forever",
                "date_to": stale,
                "tag_mode": "ALL",
                "tags": [],
                "pinned_only": False,
                "sort": "Najnowsze",
            },
        )
        self.assertEqual(out, "today")

    def test_explicit_custom_filter_does_not_get_migrated(self) -> None:
        stale = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        out = _normalize_loaded_date_to_filter(
            stale,
            {
                "text": "scan",
                "date_from": "forever",
                "date_to": stale,
            },
        )
        self.assertEqual(out, stale)

    def test_forever_is_preserved(self) -> None:
        self.assertEqual(
            _normalize_loaded_date_to_filter("forever", {"date_from": "forever"}),
            "forever",
        )


if __name__ == "__main__":
    unittest.main()
