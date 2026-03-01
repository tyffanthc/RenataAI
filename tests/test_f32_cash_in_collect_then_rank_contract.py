from __future__ import annotations

import unittest

import config  # noqa: F401  # Ensures config bootstrap order matches existing cash-in tests.
from logic.cash_in_station_candidates import collect_then_rank_station_candidates


class F32CashInCollectThenRankContractTests(unittest.TestCase):
    def test_collect_then_rank_dedupes_by_market_and_keeps_newest_freshness(self) -> None:
        rows = {
            "OFFLINE_INDEX": [
                {
                    "market_id": "322100001",
                    "name": "Ray Gateway",
                    "system_name": "Diagaundri",
                    "services": {"has_uc": True},
                    "distance_ly": 12.0,
                    "distance_ls": 1500,
                    "freshness_ts": "2026-02-20T00:00:00Z",
                }
            ],
            "SPANSH": [
                {
                    "market_id": "322100001",
                    "name": "Ray Gateway",
                    "system_name": "Diagaundri",
                    "services": {"has_uc": True, "has_vista": True},
                    "distance_ly": 11.0,
                    "distance_ls": 900,
                    "freshness_ts": "2026-03-01T00:00:00Z",
                }
            ],
        }

        out = collect_then_rank_station_candidates(
            source_rows=rows,
            default_system="Diagaundri",
            limit=10,
        )

        self.assertEqual(len(out), 1)
        row = dict(out[0])
        self.assertEqual(str(row.get("market_id") or ""), "322100001")
        self.assertEqual(str(row.get("freshness_ts") or ""), "2026-03-01T00:00:00Z")
        self.assertIn("OFFLINE_INDEX", str(row.get("source") or ""))
        self.assertIn("SPANSH", str(row.get("source") or ""))
        services = dict(row.get("services") or {})
        self.assertTrue(bool(services.get("has_uc")))
        self.assertTrue(bool(services.get("has_vista")))

    def test_collect_then_rank_sorts_globally_by_ly_then_ls(self) -> None:
        rows = {
            "PLAYERDB": [
                {
                    "name": "A Station",
                    "system_name": "A",
                    "distance_ly": 8.0,
                    "distance_ls": 1200,
                    "services": {"has_uc": True},
                },
                {
                    "name": "B Station",
                    "system_name": "B",
                    "distance_ly": 7.0,
                    "distance_ls": 9000,
                    "services": {"has_uc": True},
                },
            ],
            "EDSM": [
                {
                    "name": "C Station",
                    "system_name": "C",
                    "distance_ly": 7.0,
                    "distance_ls": 500,
                    "services": {"has_uc": True},
                }
            ],
        }

        out = collect_then_rank_station_candidates(
            source_rows=rows,
            default_system="A",
            limit=10,
        )
        names = [str((item or {}).get("name") or "") for item in out]
        self.assertEqual(names[:3], ["C Station", "B Station", "A Station"])

    def test_collect_then_rank_empty_sources_returns_empty_list(self) -> None:
        out = collect_then_rank_station_candidates(source_rows={}, default_system="Sol", limit=5)
        self.assertEqual(out, [])

    def test_collect_then_rank_prefers_spansh_edsm_on_freshness_tie(self) -> None:
        rows = {
            "OFFLINE_INDEX": [
                {
                    "market_id": "322199991",
                    "name": "Legacy Offline Port",
                    "system_name": "Diagaundri",
                    "services": {"has_uc": True},
                    "distance_ly": 18.0,
                    "distance_ls": 4200,
                    "freshness_ts": "2026-03-01T12:00:00Z",
                    "source": "OFFLINE_INDEX",
                }
            ],
            "EDSM": [
                {
                    "market_id": "322199991",
                    "name": "Live EDSM Port",
                    "system_name": "Diagaundri",
                    "services": {"has_uc": True},
                    "distance_ly": 19.0,
                    "distance_ls": 4300,
                    "freshness_ts": "2026-03-01T12:00:00Z",
                    "source": "EDSM",
                }
            ],
        }

        out = collect_then_rank_station_candidates(
            source_rows=rows,
            default_system="Diagaundri",
            limit=10,
        )

        self.assertEqual(len(out), 1)
        row = dict(out[0])
        # Tie on freshness_ts -> source preference picks live provider (EDSM/SPANSH) over offline.
        self.assertEqual(str(row.get("name") or ""), "Live EDSM Port")
        self.assertIn("EDSM", str(row.get("source") or ""))
        self.assertIn("OFFLINE_INDEX", str(row.get("source") or ""))


if __name__ == "__main__":
    unittest.main()
