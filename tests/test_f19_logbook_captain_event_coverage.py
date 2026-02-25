import unittest

from logic.logbook_feed import build_logbook_feed_item, is_captain_journal_event


class F19LogbookCaptainEventCoverageTests(unittest.TestCase):
    def test_whitelist_accepts_new_captain_events(self) -> None:
        for event_name in (
            "Touchdown",
            "Liftoff",
            "ApproachBody",
            "Interdicted",
            "EscapeInterdiction",
            "HullDamage",
            "UnderAttack",
            "SellOrganicData",
            "JetConeBoost",
        ):
            with self.subTest(event_name=event_name):
                self.assertTrue(is_captain_journal_event(event_name))

    def test_touchdown_and_liftoff_are_summarized(self) -> None:
        touchdown = build_logbook_feed_item(
            {
                "event": "Touchdown",
                "timestamp": "2026-02-22T18:00:00Z",
                "StarSystem": "Outopps UA-L c22-0",
                "Body": "Outopps UA-L c22-0 D 2",
            }
        )
        liftoff = build_logbook_feed_item(
            {
                "event": "Liftoff",
                "timestamp": "2026-02-22T18:05:00Z",
                "StarSystem": "Outopps UA-L c22-0",
                "Body": "Outopps UA-L c22-0 D 2",
            }
        )
        self.assertIn("Ladowanie", str((touchdown or {}).get("summary") or ""))
        self.assertIn("Start", str((liftoff or {}).get("summary") or ""))

    def test_interdiction_and_escape_have_readable_summaries(self) -> None:
        interdicted = build_logbook_feed_item(
            {
                "event": "Interdicted",
                "timestamp": "2026-02-22T18:10:00Z",
                "Interdictor": "NPC Pirate",
                "Submitted": False,
                "StarSystem": "Outopps UA-L c22-0",
            }
        )
        escaped = build_logbook_feed_item(
            {
                "event": "EscapeInterdiction",
                "timestamp": "2026-02-22T18:10:30Z",
                "Interdictor": "NPC Pirate",
                "StarSystem": "Outopps UA-L c22-0",
            }
        )
        self.assertIn("Proba wyciagniecia", str((interdicted or {}).get("summary") or ""))
        self.assertIn("uciec", str((escaped or {}).get("summary") or ""))
        chip_kinds = {chip.get("kind") for chip in (interdicted or {}).get("chips") or []}
        self.assertIn("INTERDICTOR", chip_kinds)

    def test_hull_damage_summary_and_hull_chip(self) -> None:
        item = build_logbook_feed_item(
            {
                "event": "HullDamage",
                "timestamp": "2026-02-22T18:11:00Z",
                "StarSystem": "Outopps UA-L c22-0",
                "Health": 0.9,
            }
        )
        self.assertIsNotNone(item)
        self.assertIn("kadluba", str((item or {}).get("summary") or ""))
        chips = (item or {}).get("chips") or []
        hull_chip = next((chip for chip in chips if chip.get("kind") == "HULL"), None)
        self.assertIsNotNone(hull_chip)
        self.assertEqual((hull_chip or {}).get("value"), "90%")

    def test_sell_uc_and_vista_summaries_include_total_when_present(self) -> None:
        uc = build_logbook_feed_item(
            {
                "event": "SellExplorationData",
                "timestamp": "2026-02-22T18:20:00Z",
                "StarSystem": "IC 289 Sector TJ-Q b5-0",
                "StationName": "Fan Survey",
                "TotalEarnings": 12500000,
            }
        )
        vista = build_logbook_feed_item(
            {
                "event": "SellOrganicData",
                "timestamp": "2026-02-22T18:20:30Z",
                "StarSystem": "IC 289 Sector TJ-Q b5-0",
                "StationName": "Fan Survey",
                "TotalEarnings": 132555000,
            }
        )
        self.assertIn("12500000 cr", str((uc or {}).get("summary") or ""))
        self.assertIn("132555000 cr", str((vista or {}).get("summary") or ""))
        vista_chip_kinds = {chip.get("kind") for chip in (vista or {}).get("chips") or []}
        self.assertIn("CR", vista_chip_kinds)

    def test_jet_cone_boost_is_classified_and_has_readable_summary(self) -> None:
        item = build_logbook_feed_item(
            {
                "event": "JetConeBoost",
                "timestamp": "2026-02-22T18:30:00Z",
                "StarSystem": "NSV 1056",
                "Body": "NSV 1056 A",
                "BoostValue": 4.0,
            }
        )
        self.assertIsNotNone(item)
        self.assertEqual(str((item or {}).get("event_class") or ""), "Nawigacja")
        self.assertIn("Boost neutronowy", str((item or {}).get("summary") or ""))
        chip_kinds = {chip.get("kind") for chip in (item or {}).get("chips") or []}
        self.assertIn("BOOST", chip_kinds)


if __name__ == "__main__":
    unittest.main()
