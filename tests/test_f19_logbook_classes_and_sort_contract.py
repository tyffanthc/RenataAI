import os
import unittest

from logic.logbook_feed import build_logbook_feed_item, classify_logbook_event


class F19LogbookClassesAndSortContractTests(unittest.TestCase):
    def test_classify_logbook_event_maps_core_groups(self) -> None:
        self.assertEqual(classify_logbook_event("FSDJump"), "Nawigacja")
        self.assertEqual(classify_logbook_event("Docked"), "Stacja")
        self.assertEqual(classify_logbook_event("SellExplorationData"), "Eksploracja")
        self.assertEqual(classify_logbook_event("SellOrganicData"), "Exobio")
        self.assertEqual(classify_logbook_event("MarketSell"), "Handel")
        self.assertEqual(classify_logbook_event("Interdicted"), "Incydent")
        self.assertEqual(classify_logbook_event("UnderAttack"), "Combat")

    def test_feed_item_contains_event_class(self) -> None:
        item = build_logbook_feed_item(
            {
                "event": "FSDJump",
                "timestamp": "2026-02-22T20:00:00Z",
                "StarSystem": "Diagaundri",
                "JumpDist": 33.9,
            }
        )
        self.assertIsNotNone(item)
        self.assertEqual((item or {}).get("event_class"), "Nawigacja")

    def test_logbook_ui_contains_class_filter_and_sortable_feed_contract(self) -> None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(project_root, "gui", "tabs", "logbook.py")
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            content = handle.read()

        self.assertIn("logbook_class_filter_var", content)
        self.assertIn("Pokaz TECH", content)
        self.assertIn('columns=("time", "class", "event", "system", "location", "summary")', content)
        self.assertIn("def _create_spansh_like_treeview", content)
        self.assertIn('"style": "Treeview"', content)
        self.assertIn("def _update_logbook_feed_sort_indicators", content)
        self.assertIn("_logbook_feed_header_labels", content)
        self.assertIn("classify_logbook_event", content)
        self.assertIn('row["event_class"] = classify_logbook_event(event_name)', content)
        self.assertIn("def _filtered_sorted_logbook_items", content)
        self.assertIn("def _render_logbook_feed_tree", content)


if __name__ == "__main__":
    unittest.main()
