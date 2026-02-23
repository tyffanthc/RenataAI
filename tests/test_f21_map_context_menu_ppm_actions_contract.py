from __future__ import annotations

import types
import unittest
from unittest.mock import patch


class _DummyOwner:
    def __init__(self) -> None:
        self.created_calls: list[dict] = []

    def map_get_available_entry_categories(self):
        return ["Exploracja/Skoki", "Mapa/Punkty"]

    def map_create_entry_for_system(self, system_name: str, *, category_path=None, edit_after=False):
        payload = {
            "system_name": system_name,
            "category_path": category_path,
            "edit_after": bool(edit_after),
        }
        self.created_calls.append(payload)
        return {"ok": True, "entry_id": "E1", **payload}


class _DummyNeutronVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value) -> None:
        self.value = str(value or "")


class _DummyNeutronTab:
    def __init__(self) -> None:
        self.var_start = _DummyNeutronVar()
        self.var_cel = _DummyNeutronVar()
        self.run_called = False

    def run_neutron(self):
        self.run_called = True


class _DummyApp:
    def __init__(self, neutron_tab=None) -> None:
        self.tab_spansh = types.SimpleNamespace(tab_neutron=neutron_tab)
        self.status_calls: list[str] = []

    def show_status(self, msg: str) -> None:
        self.status_calls.append(str(msg))


class F21MapContextMenuPPMActionsContractTests(unittest.TestCase):
    def test_ppm_actions_route_copy_entry_and_neutron(self) -> None:
        try:
            import tkinter as tk
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"tkinter unavailable: {exc}")

        try:
            from gui.tabs.journal_map import JournalMapTab
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:  # pragma: no cover
            self.skipTest(f"tk unavailable in test environment: {exc}")

        frame = None
        try:
            neutron_tab = _DummyNeutronTab()
            app = _DummyApp(neutron_tab=neutron_tab)
            owner = _DummyOwner()
            frame = JournalMapTab(root, app=app, logbook_owner=owner)
            frame.pack(fill="both", expand=True)
            root.update_idletasks()
            root.geometry("1200x700")
            root.update()

            frame.set_graph_data(
                nodes=[{"key": "A", "system_name": "TEST_SYS", "x": 0.0, "y": 0.0}],
                edges=[],
            )
            frame._map_ppm_node_key = "A"

            # Categories menu is populated from owner callback.
            frame._map_ppm_rebuild_add_entry_menu()
            end_index = int(frame._map_context_menu_add_entry.index("end") or -1)
            labels = [str(frame._map_context_menu_add_entry.entrycget(i, "label")) for i in range(end_index + 1)]
            self.assertIn("Exploracja/Skoki", labels)
            self.assertIn("Mapa/Punkty", labels)

            # Normal route intent + clipboard copy.
            with patch("gui.tabs.journal_map.common.copy_text_to_clipboard", return_value=True) as copy_mock:
                result_route = frame._map_ppm_action_set_route(neutron=False)
            self.assertTrue(bool(result_route.get("ok")))
            self.assertEqual(result_route.get("route"), "normal")
            copy_mock.assert_called()

            # Copy target.
            with patch("gui.tabs.journal_map.common.copy_text_to_clipboard", return_value=True) as copy_mock:
                result_copy = frame._map_ppm_action_copy_target()
            self.assertTrue(bool(result_copy.get("ok")))
            self.assertEqual(result_copy.get("system_name"), "TEST_SYS")
            copy_mock.assert_called()

            # Add entry (category submenu action).
            result_entry = frame._map_ppm_action_add_entry(edit_after=False, category_path="Mapa/Punkty")
            self.assertTrue(bool(result_entry.get("ok")))
            self.assertEqual(owner.created_calls[-1]["system_name"], "TEST_SYS")
            self.assertEqual(owner.created_calls[-1]["category_path"], "Mapa/Punkty")

            # Neutron route starts planner but does not require switching tabs.
            with patch("gui.tabs.journal_map.common.copy_text_to_clipboard", return_value=True):
                result_neu = frame._map_ppm_action_set_route(neutron=True)
            self.assertTrue(bool(result_neu.get("ok")))
            self.assertEqual(result_neu.get("route"), "neutron")
            self.assertTrue(neutron_tab.run_called)
            self.assertEqual(neutron_tab.var_cel.value, "TEST_SYS")
        finally:
            try:
                if frame is not None:
                    frame.destroy()
            except Exception:
                pass
            try:
                root.destroy()  # type: ignore[name-defined]
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()

