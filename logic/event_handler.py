import json
import config

from logic.events import fuel_events
from logic.events import exploration_fss_events
from logic.events import exploration_bio_events
from logic.events import exploration_dss_events
from logic.events import exploration_material_events
from logic.events import exploration_misc_events
from logic.events import navigation_events
from logic.events import trade_events
from logic.events import smuggler_events
from logic.events import cash_in_assistant
from logic.events import survival_rebuy_awareness
from logic.events import combat_awareness
from logic.events import high_g_warning
from logic import cargo_value_estimator
from logic import player_local_db
from logic.logbook_feed import build_logbook_feed_item
from logic.utils import MSG_QUEUE
from logic.utils.renata_log import log_event_throttled


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _log_router_fallback(
    key: str,
    message: str,
    exc: Exception,
    *,
    interval_ms: int = 5000,
    **fields,
) -> None:
    log_event_throttled(
        f"EVENT_ROUTER:{key}",
        interval_ms,
        "EVENT_ROUTER",
        message,
        error=_exc_text(exc),
        **fields,
    )


class EventHandler:
    """
    Obsługuje eventy Elite Dangerous Journal.
    Teraz jako lekki router delegujący do modułów logic/events/*.
    """

    def on_status_update(self, status_data: dict, gui_ref=None) -> None:
        try:
            from app.state import app_state

            app_state.update_mode_signal_from_status(status_data, source="status_json")
        except Exception as exc:
            _log_router_fallback("status.mode_detector", "status update: mode detector failed", exc)
        try:
            fuel_events.handle_status_update(status_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("status.fuel", "status update: fuel handler failed", exc)
        try:
            survival_rebuy_awareness.handle_status_update(status_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("status.survival_rebuy", "status update: survival/rebuy handler failed", exc)
        try:
            combat_awareness.handle_status_update(status_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("status.combat_awareness", "status update: combat awareness handler failed", exc)
        try:
            exploration_bio_events.handle_exobio_status_position(status_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("status.exobio", "status update: exobio handler failed", exc)
        try:
            high_g_warning.handle_status_update(status_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("status.high_g_warning", "status update: high-g handler failed", exc)
        if config.get("ship_state_enabled") and config.get("ship_state_use_status_json"):
            try:
                from app.state import app_state
                app_state.ship_state.update_from_status_json(status_data)
            except Exception as exc:
                _log_router_fallback("status.ship_state", "status update: ship_state sync failed", exc)

    def on_cargo_update(self, cargo_data: dict, gui_ref=None) -> None:
        try:
            cargo_value_estimator.update_cargo_snapshot(cargo_data, source="cargo_json")
        except Exception as exc:
            _log_router_fallback("cargo.value_estimator", "cargo update: value estimator sync failed", exc)
        if not (config.get("ship_state_enabled") and config.get("ship_state_use_cargo_json")):
            return
        try:
            from app.state import app_state
            app_state.ship_state.update_from_cargo_json(cargo_data)
        except Exception as exc:
            _log_router_fallback("cargo.ship_state", "cargo update: ship_state sync failed", exc)

    def on_market_update(self, market_data: dict, gui_ref=None) -> None:
        try:
            from app.state import app_state

            player_local_db.ingest_market_json(
                market_data,
                fallback_system_name=str(getattr(app_state, "current_system", "") or "").strip() or None,
                fallback_station_name=str(getattr(app_state, "current_station", "") or "").strip() or None,
            )
        except Exception as exc:
            _log_router_fallback("market.playerdb_ingest", "market update: playerdb ingest failed", exc)
        try:
            cargo_value_estimator.update_market_snapshot(market_data, source="market_json")
        except Exception as exc:
            _log_router_fallback("market.value_estimator", "market update: value estimator sync failed", exc)
        try:
            trade_events.handle_market_data(market_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("market.trade", "market update: trade handler failed", exc)

    def on_navroute_update(self, navroute_data: dict, gui_ref=None) -> None:
        try:
            navigation_events.handle_navroute_update(navroute_data, gui_ref)
        except Exception as exc:
            _log_router_fallback("navroute.sync", "navroute update failed", exc)

    # ------------------------------------------------------------------ #
    #  STANDARDOWE API (routing journala)
    # ------------------------------------------------------------------ #
    def handle_event(self, line: str, gui_ref=None) -> None:
        """
        Główne wejście dla pojedynczej linii z journala (JSON string).

        - parsuje JSON,
        - sprawdza typ eventu,
        - wywołuje odpowiednie moduły logic/events/*.

        Uwaga:
        - ta funkcja NIE czyta już Status.json ani Market.json,
          robią to watchery w app/status_watchers.py,
        - ta funkcja NIE odpala już logiki paliwa ani marketu — robią to watchery.
        """
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            preview = str(line or "").strip().replace("\n", "\\n")[:120]
            _log_router_fallback(
                "journal.parse",
                "journal line parse failed",
                exc,
                interval_ms=15000,
                line_preview=preview,
            )
            return

        typ = ev.get("event")
        if not typ:
            return

        if typ in {"Location", "FSDJump", "CarrierJump", "Docked", "SellExplorationData", "SellOrganicData"}:
            try:
                from app.state import app_state

                player_local_db.ingest_journal_event(
                    ev,
                    fallback_system_name=str(getattr(app_state, "current_system", "") or "").strip() or None,
                    fallback_station_name=str(getattr(app_state, "current_station", "") or "").strip() or None,
                )
            except Exception as exc:
                _log_router_fallback(
                    "journal.playerdb_ingest",
                    "journal event: playerdb ingest failed",
                    exc,
                    event=str(typ),
                )

        try:
            feed_item = build_logbook_feed_item(ev)
            if feed_item is not None:
                MSG_QUEUE.put(("logbook_journal_feed", feed_item))
        except Exception as exc:
            _log_router_fallback(
                "journal.logbook_feed",
                "journal event: logbook feed enqueue failed",
                exc,
                event=typ,
            )

        try:
            from app.state import app_state

            app_state.update_mode_signal_from_journal(ev, source="journal")
        except Exception as exc:
            _log_router_fallback("journal.mode_detector", "journal event: mode detector failed", exc)
        try:
            high_g_warning.handle_journal_event(ev, gui_ref)
        except Exception as exc:
            _log_router_fallback("journal.high_g_warning", "journal event: high-g handler failed", exc)

        try:
            survival_rebuy_awareness.handle_journal_event(ev, gui_ref)
        except Exception as exc:
            _log_router_fallback("journal.survival_rebuy", "journal event: survival/rebuy handler failed", exc)
        try:
            combat_awareness.handle_journal_event(ev, gui_ref)
        except Exception as exc:
            _log_router_fallback("journal.combat_awareness", "journal event: combat awareness handler failed", exc)

        if typ == "StartJump":
            try:
                cash_in_assistant.trigger_startjump_cash_in_callout(event=ev, gui_ref=gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "journal.cash_in_startjump",
                    "journal event: cash-in startjump callout failed",
                    exc,
                )

        # AUTO-SCHOWEK
        if typ == "FSDJump":
            navigation_events.handle_fsd_jump_autoschowek(ev, gui_ref)

        # SHIP STATE (Loadout)
        if typ == "Loadout":
            if config.get("ship_state_enabled"):
                try:
                    from app.state import app_state
                    app_state.ship_state.update_from_loadout(ev)
                except Exception as exc:
                    if config.get("fit_resolver_fail_on_missing", False):
                        raise
                    _log_router_fallback(
                        "loadout.ship_state",
                        "loadout sync failed; fallback without fit update",
                        exc,
                    )

        # FSS
        if typ == "FSSDiscoveryScan":
            exploration_fss_events.handle_fss_discovery_scan(ev, gui_ref)
        if typ == "FSSAllBodiesFound":
            exploration_fss_events.handle_fss_all_bodies_found(ev, gui_ref)
            return

        if typ == "Scan":
            # Feed value engine first so F4 summary built on full-scan includes the current body.
            try:
                from app.state import app_state
                app_state.system_value_engine.analyze_scan_event(ev)
            except Exception as exc:
                _log_router_fallback("scan.value_engine", "scan event value analysis failed", exc)
            exploration_fss_events.handle_scan(ev, gui_ref)
            exploration_dss_events.handle_dss_target_hint(ev, gui_ref)
        if typ == "SAASignalsFound":
            exploration_bio_events.handle_dss_bio_signals(ev, gui_ref)
        if typ == "SAAScanComplete":
            exploration_dss_events.handle_dss_scan_complete(ev, gui_ref)
            try:
                from app.state import app_state
                app_state.system_value_engine.analyze_discovery_meta_event(ev)
            except Exception as exc:
                _log_router_fallback(
                    "saa.discovery_meta",
                    "SAAScanComplete discovery meta analysis failed",
                    exc,
                )
        if typ in ("ScanOrganic", "CodexEntry"):
            exploration_bio_events.handle_exobio_progress(ev, gui_ref)

        # CARGO
        if typ == "Cargo":
            try:
                cargo_value_estimator.update_cargo_snapshot(ev, source="journal.cargo")
            except Exception as exc:
                _log_router_fallback("journal.cargo_value", "journal cargo: value estimator sync failed", exc)
            smuggler_events.update_illegal_cargo(ev)

        # FOOTFALL
        if typ in ("Footfall", "Touchdown", "Disembark"):
            exploration_misc_events.handle_first_footfall(ev, gui_ref)

        # SMUGGLER ALERT
        if typ in ("ApproachSettlement", "DockingRequested"):
            smuggler_events.handle_smuggler_alert(ev, gui_ref)

        # Pozycja gracza
        if typ in ("Location", "FSDJump", "CarrierJump"):
            navigation_events.handle_location_fsdjump_carrier(ev, gui_ref)
            return

        # Market — usunięto stare I/O (trade_events.handle_market)

        if typ == "Docked":
            navigation_events.handle_docked(ev, gui_ref)
            return

        if typ == "Undocked":
            navigation_events.handle_undocked(ev, gui_ref)
            return

        # Materiały
        if typ == "MaterialCollected":
            exploration_material_events.handle_material_collected(ev, gui_ref)
        if typ == "MaterialDiscarded":
            exploration_material_events.handle_material_discarded(ev, gui_ref)


handler = EventHandler()
