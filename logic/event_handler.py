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
from logic.events import survival_rebuy_awareness
from logic.events import combat_awareness
from logic.events import high_g_warning
from logic import cargo_value_estimator
from logic import player_local_db
from logic.logbook_feed import build_logbook_feed_item
from logic.utils import MSG_QUEUE
from logic.utils.renata_log import log_event, log_event_throttled


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


def _emit_playerdb_updated(
    *,
    source: str,
    event_name: str,
) -> None:
    try:
        MSG_QUEUE.put(
            (
                "playerdb_updated",
                {
                    "source": str(source or "").strip() or "unknown",
                    "event_name": str(event_name or "").strip() or "unknown",
                },
            )
        )
    except Exception as exc:
        _log_router_fallback(
            "playerdb_updated.emit",
            "failed to enqueue playerdb_updated notification",
            exc,
            source=source,
            event=event_name,
        )
        return


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _sell_value_domain_for_event(event_name: str) -> str | None:
    norm = str(event_name or "").strip()
    if norm in {"SellExplorationData", "MultiSellExplorationData"}:
        return "cartography"
    if norm == "SellOrganicData":
        return "exobiology"
    return None


def _extract_multisell_discovered_systems(ev: dict) -> list[str]:
    raw = ev.get("Discovered")
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        system_name = ""
        if isinstance(item, dict):
            system_name = str(
                item.get("StarSystem")
                or item.get("SystemName")
                or item.get("System")
                or item.get("name")
                or ""
            ).strip()
        elif isinstance(item, (list, tuple)) and item:
            system_name = str(item[0] or "").strip()
        elif isinstance(item, str):
            system_name = str(item).strip()
        if not system_name:
            continue
        key = system_name.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(system_name)
    return out


def _sell_reset_target_systems(ev: dict, *, event_name: str, domain: str) -> list[str]:
    if str(domain or "").strip() != "cartography":
        return []
    if str(event_name or "").strip() != "MultiSellExplorationData":
        return []
    return _extract_multisell_discovered_systems(ev)


def _safe_engine_totals_snapshot() -> dict[str, float]:
    try:
        from app.state import app_state

        totals = dict(app_state.system_value_engine.calculate_totals() or {})
    except Exception:
        totals = {}
    return {
        "c_cartography": _safe_float(totals.get("c_cartography")),
        "c_exobiology": _safe_float(totals.get("c_exobiology")),
        "bonus_discovery": _safe_float(totals.get("bonus_discovery")),
        "total": _safe_float(totals.get("total")),
    }


def _apply_sell_value_domain_reset(ev: dict) -> None:
    event_name = str(ev.get("event") or "").strip()
    domain = _sell_value_domain_for_event(event_name)
    if not domain:
        return
    try:
        from app.state import app_state

        engine = getattr(app_state, "system_value_engine", None)
        if engine is None or not hasattr(engine, "clear_value_domain"):
            return

        target_systems = _sell_reset_target_systems(ev, event_name=event_name, domain=domain)
        before = _safe_engine_totals_snapshot()
        if target_systems:
            touched_sum = 0
            per_scope: list[str] = []
            for system_name in target_systems:
                result_one = engine.clear_value_domain(domain=domain, system_name=system_name)
                touched_sum += int((result_one or {}).get("systems_touched") or 0)
                per_scope.append(str(system_name))
            result = {
                "systems_touched": int(touched_sum),
                "scope": "scoped",
                "system_name": ",".join(per_scope),
            }
        else:
            result = engine.clear_value_domain(domain=domain)
        after = _safe_engine_totals_snapshot()
        reset_scope = str((result or {}).get("scope") or ("scoped" if target_systems else "all"))
        scoped_systems = int(len(target_systems))

        log_event(
            "VALUE",
            "cashin_sell_reset",
            event=event_name,
            domain=domain,
            reset_scope=reset_scope,
            scoped_systems=scoped_systems,
            systems_touched=int((result or {}).get("systems_touched") or 0),
            before_total=round(_safe_float(before.get("total")), 2),
            after_total=round(_safe_float(after.get("total")), 2),
            before_carto=round(_safe_float(before.get("c_cartography")), 2),
            after_carto=round(_safe_float(after.get("c_cartography")), 2),
            before_exobio=round(_safe_float(before.get("c_exobiology")), 2),
            after_exobio=round(_safe_float(after.get("c_exobiology")), 2),
            before_bonus=round(_safe_float(before.get("bonus_discovery")), 2),
            after_bonus=round(_safe_float(after.get("bonus_discovery")), 2),
        )
    except Exception as exc:
        _log_router_fallback(
            "sell.value_reset",
            "sell event: value domain reset failed",
            exc,
            event=event_name,
            domain=domain,
        )


def _log_sell_value_snapshot(ev: dict) -> None:
    event_name = str(ev.get("event") or "").strip()
    if event_name not in {"SellExplorationData", "MultiSellExplorationData", "SellOrganicData"}:
        return
    try:
        from app.state import app_state

        totals = {}
        try:
            totals = dict(app_state.system_value_engine.calculate_totals() or {})
        except Exception as exc:
            _log_router_fallback(
                "sell.value_snapshot.totals",
                "sell event: value snapshot totals failed",
                exc,
                event=event_name,
            )
            totals = {}

        current_system = str(getattr(app_state, "current_system", "") or "").strip() or "-"
        system_est = 0.0
        try:
            stats = app_state.system_value_engine.get_system_stats(current_system)
            if stats is not None:
                system_est = (
                    float(getattr(stats, "c_cartography", 0.0) or 0.0)
                    + float(getattr(stats, "c_exobiology", 0.0) or 0.0)
                    + float(getattr(stats, "bonus_discovery", 0.0) or 0.0)
                )
        except Exception as exc:
            _log_router_fallback(
                "sell.value_snapshot.system",
                "sell event: current-system estimate snapshot failed",
                exc,
                event=event_name,
                system=current_system,
            )

        earnings = _safe_float(ev.get("TotalEarnings"))
        if earnings <= 0.0:
            earnings = _safe_float(ev.get("Earnings"))

        log_event(
            "VALUE",
            "cashin_sell_snapshot",
            event=event_name,
            sale_earnings=round(float(earnings), 2),
            balance=_safe_float(ev.get("Balance")),
            current_system=current_system,
            estimate_system=round(float(system_est), 2),
            estimate_session_total=round(_safe_float(totals.get("total")), 2),
            estimate_carto=round(_safe_float(totals.get("c_cartography")), 2),
            estimate_exobio=round(_safe_float(totals.get("c_exobiology")), 2),
            estimate_bonus=round(_safe_float(totals.get("bonus_discovery")), 2),
        )
    except Exception as exc:
        _log_router_fallback(
            "sell.value_snapshot",
            "sell event: value snapshot diagnostic failed",
            exc,
            event=event_name,
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
        playerdb_ingest_ok = False
        try:
            from app.state import app_state

            player_local_db.ingest_market_json(
                market_data,
                fallback_system_name=str(getattr(app_state, "current_system", "") or "").strip() or None,
                fallback_station_name=str(getattr(app_state, "current_station", "") or "").strip() or None,
            )
            playerdb_ingest_ok = True
        except Exception as exc:
            _log_router_fallback("market.playerdb_ingest", "market update: playerdb ingest failed", exc)
        if playerdb_ingest_ok:
            _emit_playerdb_updated(source="market_json", event_name="Market")
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

        if typ in {
            "Location",
            "FSDJump",
            "CarrierJump",
            "Docked",
            "SellExplorationData",
            "MultiSellExplorationData",
            "SellOrganicData",
        }:
            playerdb_ingest_ok = False
            try:
                from app.state import app_state

                player_local_db.ingest_journal_event(
                    ev,
                    fallback_system_name=str(getattr(app_state, "current_system", "") or "").strip() or None,
                    fallback_station_name=str(getattr(app_state, "current_station", "") or "").strip() or None,
                )
                playerdb_ingest_ok = True
            except Exception as exc:
                _log_router_fallback(
                    "journal.playerdb_ingest",
                    "journal event: playerdb ingest failed",
                    exc,
                    event=str(typ),
                )
            if playerdb_ingest_ok:
                _emit_playerdb_updated(source="journal", event_name=str(typ))

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

        if typ in {"SellExplorationData", "MultiSellExplorationData", "SellOrganicData"}:
            _log_sell_value_snapshot(ev)
            _apply_sell_value_domain_reset(ev)

        # AUTO-SCHOWEK
        if typ == "FSDJump":
            try:
                navigation_events.handle_fsd_jump_autoschowek(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "journal.fsd_jump_autoschowek",
                    "journal event: autoschowek handler failed",
                    exc,
                    event=str(typ),
                )

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
            try:
                exploration_fss_events.handle_fss_discovery_scan(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "journal.fss_discovery_scan",
                    "journal event: FSSDiscoveryScan handler failed",
                    exc,
                    event=str(typ),
                )
        if typ == "FSSAllBodiesFound":
            try:
                exploration_fss_events.handle_fss_all_bodies_found(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "journal.fss_all_bodies_found",
                    "journal event: FSSAllBodiesFound handler failed",
                    exc,
                    event=str(typ),
                )
            return

        if typ == "NavBeaconScan":
            try:
                navigation_events.handle_nav_beacon_scan(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "journal.nav_beacon_scan",
                    "journal event: NavBeaconScan handler failed",
                    exc,
                    event=str(typ),
                )

        if typ == "Scan":
            # Feed value engine first so F4 summary built on full-scan includes the current body.
            try:
                from app.state import app_state
                app_state.system_value_engine.analyze_scan_event(ev)
            except Exception as exc:
                _log_router_fallback("scan.value_engine", "scan event value analysis failed", exc)
            try:
                exploration_fss_events.handle_scan(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback("scan.fss", "scan event: FSS scan handler failed", exc)
            try:
                exploration_dss_events.handle_dss_target_hint(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback("scan.dss_target_hint", "scan event: DSS target hint failed", exc)
            try:
                from app.state import app_state

                scan_body_type = str(ev.get("BodyType") or "").strip().casefold()
                should_try_star_meta = (not scan_body_type) or (scan_body_type == "star")
                star_meta_out = (
                    player_local_db.ingest_star_metadata_event(
                        ev,
                        fallback_system_name=str(getattr(app_state, "current_system", "") or "").strip() or None,
                    )
                    if should_try_star_meta
                    else {"ok": False, "reason": "scan_not_star_body"}
                )
                if bool((star_meta_out or {}).get("ok")):
                    _emit_playerdb_updated(source="journal", event_name="Scan")
            except Exception as exc:
                _log_router_fallback(
                    "scan.playerdb_star_meta",
                    "scan event: playerdb star metadata ingest failed",
                    exc,
                )
        if typ == "SAASignalsFound":
            try:
                exploration_bio_events.handle_dss_bio_signals(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback("saa.bio_signals", "SAASignalsFound bio-signal handler failed", exc)
        if typ == "SAAScanComplete":
            try:
                exploration_dss_events.handle_dss_scan_complete(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback("saa.dss_scan_complete", "SAAScanComplete DSS handler failed", exc)
            try:
                from app.state import app_state
                app_state.system_value_engine.analyze_dss_scan_complete_event(ev)
            except Exception as exc:
                _log_router_fallback(
                    "saa.dss_value",
                    "SAAScanComplete DSS value analysis failed",
                    exc,
                )
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
            try:
                exploration_bio_events.handle_exobio_progress(ev, gui_ref)
            except Exception as exc:
                _log_router_fallback("journal.exobio_progress", "journal event: exobio progress handler failed", exc)

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

        # StartJump: podsumowanie eksploracji ma pojawic sie przed skokiem (hyperspace)
        if typ == "StartJump":
            try:
                exploration_fss_events.flush_pending_exit_summary_on_jump(gui_ref=gui_ref)
            except Exception as exc:
                _log_router_fallback(
                    "startjump.exploration_summary.flush",
                    "startjump event: failed to flush armed exploration summary",
                    exc,
                    event=str(typ),
                )
            return

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
