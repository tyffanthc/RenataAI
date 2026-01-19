import unittest

from logic import neutron_via


class NeutronViaTests(unittest.TestCase):
    def test_empty_value(self) -> None:
        ok, reason, warn_short = neutron_via.validate_via(
            value="",
            existing=[],
            start="Sol",
            end="Colonia",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "empty")
        self.assertFalse(warn_short)

    def test_duplicate_value(self) -> None:
        ok, reason, warn_short = neutron_via.validate_via(
            value="Djabal",
            existing=["djabal", "TY Bootis"],
            start="Sol",
            end="Colonia",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate")
        self.assertFalse(warn_short)

    def test_start_or_end_blocked(self) -> None:
        ok, reason, warn_short = neutron_via.validate_via(
            value="Sol",
            existing=[],
            start="sol",
            end="Colonia",
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "start_or_end")
        self.assertFalse(warn_short)

    def test_warn_short_value(self) -> None:
        ok, reason, warn_short = neutron_via.validate_via(
            value="AB",
            existing=[],
            start="Sol",
            end="Colonia",
        )
        self.assertTrue(ok)
        self.assertIsNone(reason)
        self.assertTrue(warn_short)


if __name__ == "__main__":
    unittest.main()
