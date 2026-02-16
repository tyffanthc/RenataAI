from __future__ import annotations

import queue
import time
import unittest
from types import SimpleNamespace

import config
from app.state import app_state
from gui.tabs.pulpit import PulpitTab
from logic import cargo_value_estimator
from logic.risk_rebuy_contract import build_risk_rebuy_contract
from logic.utils import MSG_QUEUE


def _drain_queue() -> None:
    try:
        while True:
            MSG_QUEUE.get_nowait()
    except queue.Empty:
        return


class _DummyButton:
    def __init__(self, domain: str, packed: list[str]) -> None:
        self.domain = domain
        self.packed = packed

    def pack_forget(self) -> None:
        return

    def pack(self, **_kwargs) -> None:
        self.packed.append(self.domain)


class F7QualityGatesAndSmokeTests(unittest.TestCase):
    _TTL_KEYS = (
        "mode.ttl.combat_sec",
        "mode.ttl.exploration_sec",
        "mode.ttl.mining_sec",
    )

    def setUp(self) -> None:
        _drain_queue()
        cargo_value_estimator.reset_runtime()
        self._saved_snapshot = app_state.get_mode_state_snapshot()
        self._saved_is_docked = bool(getattr(app_state, "is_docked", False))
        self._saved_state_keys = {
            "mode_id": config.STATE.get("mode_id"),
            "mode_source": config.STATE.get("mode_source"),
            "mode_confidence": config.STATE.get("mode_confidence"),
            "mode_since": config.STATE.get("mode_since"),
            "mode_ttl": config.STATE.get("mode_ttl"),
            "is_docked": config.STATE.get("is_docked"),
        }
        self._saved_signals = {}
        for name in (
            "_mode_signal_docked",
            "_mode_signal_combat_active",
            "_mode_signal_combat_last_ts",
            "_mode_signal_hardpoints_since",
            "_mode_signal_exploration_active",
            "_mode_signal_exploration_last_ts",
            "_mode_signal_mining_active",
            "_mode_signal_mining_last_ts",
            "_mode_signal_mining_loadout",
            "_mode_last_emit_signature",
        ):
            self._saved_signals[name] = getattr(app_state, name)
        self._saved_mode_overlay = getattr(app_state, "mode_overlay", None)
        self._saved_mode_combat_silence = bool(getattr(app_state, "mode_combat_silence", False))

        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        self._saved_settings = {}
        if isinstance(settings, dict):
            for key in self._TTL_KEYS:
                self._saved_settings[key] = settings.get(key)
            settings["mode.ttl.combat_sec"] = 1.0
            settings["mode.ttl.exploration_sec"] = 120.0
            settings["mode.ttl.mining_sec"] = 90.0

        with app_state.lock:
            app_state.mode_id = "NORMAL"
            app_state.mode_source = "AUTO"
            app_state.mode_confidence = 0.60
            app_state.mode_since = time.time()
            app_state.mode_ttl = None
            app_state.mode_overlay = None
            app_state.mode_combat_silence = False
            app_state.is_docked = False
            app_state._mode_signal_docked = False
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = 0.0
            app_state._mode_signal_hardpoints_since = None
            app_state._mode_signal_exploration_active = False
            app_state._mode_signal_exploration_last_ts = 0.0
            app_state._mode_signal_mining_active = False
            app_state._mode_signal_mining_last_ts = 0.0
            app_state._mode_signal_mining_loadout = False
            app_state._mode_last_emit_signature = ""
            app_state._persist_mode_state_locked()
        app_state.publish_mode_state(force=True)
        _drain_queue()

    def tearDown(self) -> None:
        with app_state.lock:
            app_state.mode_id = str(self._saved_snapshot.get("mode_id") or "NORMAL")
            app_state.mode_source = str(self._saved_snapshot.get("mode_source") or "AUTO")
            app_state.mode_confidence = float(self._saved_snapshot.get("mode_confidence") or 0.60)
            app_state.mode_since = float(self._saved_snapshot.get("mode_since") or time.time())
            ttl = self._saved_snapshot.get("mode_ttl")
            app_state.mode_ttl = float(ttl) if ttl is not None else None
            app_state.mode_overlay = self._saved_mode_overlay
            app_state.mode_combat_silence = self._saved_mode_combat_silence
            app_state.is_docked = self._saved_is_docked
            for key, value in self._saved_signals.items():
                setattr(app_state, key, value)
            app_state._persist_mode_state_locked()

        for key, value in self._saved_state_keys.items():
            if value is None:
                config.STATE.pop(key, None)
            else:
                config.STATE[key] = value

        settings = getattr(config.config, "_settings", None)  # type: ignore[attr-defined]
        if isinstance(settings, dict):
            for key, value in self._saved_settings.items():
                if value is None:
                    settings.pop(key, None)
                else:
                    settings[key] = value

        app_state.publish_mode_state(force=True)
        cargo_value_estimator.reset_runtime()
        _drain_queue()

    def test_widget_visibility_order_contract(self) -> None:
        self.assertEqual(PulpitTab._WIDGET_ORDER[:4], ["mode", "risk", "cash", "route"])
        self.assertEqual(set(PulpitTab._WIDGET_ALWAYS), {"mode", "risk", "cash", "route"})
        self.assertEqual(PulpitTab._WIDGET_MAX_VISIBLE, 7)
        self.assertEqual(PulpitTab._PANEL_MAX_ACTIONS, 6)

        packed: list[str] = []
        buttons = {
            domain: _DummyButton(domain, packed)
            for domain in PulpitTab._WIDGET_ORDER
        }
        tab = SimpleNamespace(
            _WIDGET_ORDER=list(PulpitTab._WIDGET_ORDER),
            _WIDGET_ALWAYS=set(PulpitTab._WIDGET_ALWAYS),
            _WIDGET_MAX_VISIBLE=PulpitTab._WIDGET_MAX_VISIBLE,
            _widget_buttons=buttons,
            _widget_visible={domain: True for domain in PulpitTab._WIDGET_ORDER},
        )

        PulpitTab._refresh_widget_strip(tab)  # type: ignore[arg-type]
        self.assertEqual(packed, ["mode", "risk", "cash", "route", "summary", "fss", "exo"])

    def test_single_panel_slot_contract_and_p0_override(self) -> None:
        widget_texts: dict[str, str] = {}
        render_calls: list[bool] = []

        tab = SimpleNamespace(
            _current_survival_payload={},
            _current_risk_payload={},
            _current_risk_source="",
            _panel_domain="cash",
            _set_widget_text=lambda domain, text: widget_texts.__setitem__(domain, text),
            _refresh_widget_strip=lambda: None,
            _is_p0_risk=PulpitTab._is_p0_risk,
        )

        def _render_risk_panel(*, force_open: bool = False) -> None:
            render_calls.append(bool(force_open))
            if force_open:
                tab._panel_domain = "risk"

        tab._render_risk_panel = _render_risk_panel

        PulpitTab.update_survival_rebuy(
            tab,  # type: ignore[arg-type]
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 2_000_000.0,
                "rebuy_cost": 1_000_000.0,
            },
        )
        self.assertEqual(tab._panel_domain, "cash")
        self.assertEqual(render_calls, [])
        self.assertTrue(widget_texts.get("risk", "").startswith("RISK: "))

        PulpitTab.update_survival_rebuy(
            tab,  # type: ignore[arg-type]
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 900_000.0,
                "rebuy_cost": 1_000_000.0,
            },
        )
        self.assertEqual(tab._panel_domain, "risk")
        self.assertEqual(render_calls, [True])

    def test_mode_detector_ttl_manual_override_and_safety_contract(self) -> None:
        app_state.set_mode_manual("EXPLORATION", source="test.f7.quality.manual")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"in_combat": True, "risk_status": "RISK_HIGH"},
            source="test.f7.quality.manual.safety",
        )
        snap_manual = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_manual.get("mode_id"), "EXPLORATION")
        self.assertEqual(snap_manual.get("mode_source"), "MANUAL")
        self.assertEqual(snap_manual.get("mode_overlay"), "COMBAT")
        self.assertTrue(bool(snap_manual.get("mode_combat_silence")))

        app_state.set_mode_auto(source="test.f7.quality.auto")
        app_state.update_mode_signal_from_runtime(
            "combat_awareness",
            {"in_combat": True, "risk_status": "RISK_HIGH"},
            source="test.f7.quality.auto.signal",
        )
        snap_auto = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_auto.get("mode_id"), "COMBAT")
        self.assertEqual(snap_auto.get("mode_source"), "AUTO")
        self.assertEqual(snap_auto.get("mode_ttl"), 1.0)

        with app_state.lock:
            app_state._mode_signal_combat_active = False
            app_state._mode_signal_combat_last_ts = time.time() - 2.0
        app_state.refresh_mode_state(source="test.f7.quality.auto.expire")
        snap_expired = app_state.get_mode_state_snapshot()
        self.assertEqual(snap_expired.get("mode_id"), "NORMAL")
        self.assertIsNone(snap_expired.get("mode_ttl"))

    def test_risk_rebuy_mapping_contract(self) -> None:
        contract = build_risk_rebuy_contract(
            {
                "risk_status": "RISK_LOW",
                "exploration_value_estimated": 0.0,
                "exobio_value_estimated": 0.0,
                "credits": 700_000.0,
                "rebuy_cost": 1_000_000.0,
            }
        )
        self.assertEqual(contract.rebuy_label, "NO REBUY")
        self.assertEqual(contract.risk_label, "CRIT")

    def test_cargo_value_estimator_fallback_confidence_contract(self) -> None:
        cargo_value_estimator.update_cargo_snapshot(
            {"Inventory": [{"Name": "Unknown Cargo", "Count": 5}]},
            source="test.f7.quality.cargo",
        )
        estimate = cargo_value_estimator.estimate_cargo_value(cargo_tons=5.0)
        self.assertEqual(estimate.source, "fallback")
        self.assertEqual(estimate.confidence, "LOW")
        self.assertEqual(int(round(estimate.cargo_expected_cr)), 100_000)
        self.assertGreater(estimate.cargo_floor_cr, 0.0)


if __name__ == "__main__":
    unittest.main()

