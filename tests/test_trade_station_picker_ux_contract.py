from __future__ import annotations

import pathlib
import unittest


class TradeStationPickerUxContractTests(unittest.TestCase):
    def test_station_picker_dialog_keeps_scroll_filter_and_large_geometry(self) -> None:
        source_path = pathlib.Path("gui/tabs/spansh/trade.py")
        content = source_path.read_text(encoding="utf-8", errors="ignore")

        self.assertIn('top.geometry("760x520")', content)
        self.assertIn("top.minsize(560, 380)", content)
        self.assertIn("query_var = tk.StringVar()", content)
        self.assertIn("f_filter = tk.Frame(", content)
        self.assertIn("tk.Scrollbar(", content)
        self.assertIn("yscrollcommand=sc.set", content)
        self.assertIn("query_var.trace_add(\"write\", _refresh_list)", content)


if __name__ == "__main__":
    unittest.main()
