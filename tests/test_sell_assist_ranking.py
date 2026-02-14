import unittest

from logic.trade import build_sell_assist_decision_space


class SellAssistRankingTests(unittest.TestCase):
    def test_builds_two_to_three_options_and_skip_action(self) -> None:
        rows = [
            {
                "from_system": "A",
                "from_station": "A1",
                "to_system": "B",
                "to_station": "B1",
                "total_profit": 1_200_000,
                "profit": 5000,
                "amount": 240,
                "distance_ly": 40.0,
                "jumps": 1,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 1800,
                "updated_ago": "30m",
            },
            {
                "from_system": "B",
                "from_station": "B1",
                "to_system": "C",
                "to_station": "C1",
                "total_profit": 2_100_000,
                "profit": 8000,
                "amount": 240,
                "distance_ly": 110.0,
                "jumps": 3,
                "source_status": "ONLINE_LIVE",
                "confidence": "medium",
                "data_age_seconds": 3600,
                "updated_ago": "1h",
            },
            {
                "from_system": "C",
                "from_station": "C1",
                "to_system": "D",
                "to_station": "D1",
                "total_profit": 1_000_000,
                "profit": 4200,
                "amount": 240,
                "distance_ly": 15.0,
                "jumps": 1,
                "source_status": "CACHE_TTL_HIT",
                "confidence": "medium",
                "data_age_seconds": 7200,
                "updated_ago": "2h",
            },
        ]
        out = build_sell_assist_decision_space(rows, jump_range=48.0)
        options = out.get("options") or []
        self.assertIn(len(options), {2, 3})
        self.assertEqual((out.get("skip_action") or {}).get("label"), "Pomijam")
        for option in options:
            scores = option.get("scores") or {}
            self.assertIn("price_score", scores)
            self.assertIn("time_score", scores)
            self.assertIn("risk_score", scores)
            self.assertIn("trust_score", scores)

    def test_offline_or_stale_data_switches_to_advisory_mode(self) -> None:
        rows = [
            {
                "from_system": "A",
                "from_station": "A1",
                "to_system": "B",
                "to_station": "B1",
                "total_profit": 900_000,
                "profit": 3000,
                "amount": 200,
                "distance_ly": 70.0,
                "jumps": 2,
                "source_status": "OFFLINE_CACHE_FALLBACK",
                "confidence": "low",
                "data_age_seconds": 172800,
                "updated_ago": "2d",
            },
            {
                "from_system": "B",
                "from_station": "B1",
                "to_system": "C",
                "to_station": "C1",
                "total_profit": 950_000,
                "profit": 3200,
                "amount": 200,
                "distance_ly": 55.0,
                "jumps": 2,
                "source_status": "OFFLINE_CACHE_FALLBACK",
                "confidence": "low",
                "data_age_seconds": 200000,
                "updated_ago": "2d",
            },
        ]
        out = build_sell_assist_decision_space(rows, jump_range=40.0)
        self.assertTrue(bool(out.get("advisory_only")))
        self.assertEqual(out.get("mode"), "fallback")
        self.assertIn("orientacyjnie", str(out.get("note") or "").lower())

    def test_single_row_still_returns_alternative_not_top1(self) -> None:
        rows = [
            {
                "from_system": "A",
                "from_station": "A1",
                "to_system": "B",
                "to_station": "B1",
                "total_profit": 300_000,
                "profit": 1500,
                "amount": 200,
                "distance_ly": 12.0,
                "jumps": 1,
                "source_status": "ONLINE_LIVE",
                "confidence": "high",
                "data_age_seconds": 600,
                "updated_ago": "10m",
            }
        ]
        out = build_sell_assist_decision_space(rows, jump_range=45.0)
        options = out.get("options") or []
        self.assertGreaterEqual(len(options), 2)
        for option in options:
            self.assertNotIn("recommended", option)


if __name__ == "__main__":
    unittest.main()

