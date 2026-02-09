from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable
import re

import config
from app.route_manager import route_manager
from app.state import app_state
from gui import common
from gui.ui_thread import run_on_ui_thread
from logic import utils


ComputeFn = Callable[..., tuple[list[str], list[dict[str, Any]]]]


class SpanshPlannerBase(ttk.Frame):
    def __init__(
        self,
        parent,
        root_window,
        *,
        mode_key: str,
        schema_id: str,
        status_source: str,
        status_target: str,
        emit_busy_status: bool,
    ) -> None:
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        self._mode_key = mode_key
        self._schema_id = schema_id
        self._status_source = status_source
        self._status_target = status_target
        self._emit_busy_status = emit_busy_status

        self._busy = False
        self._use_treeview = bool(config.get("features.tables.treeview_enabled", False)) and bool(
            config.get("features.tables.spansh_schema_enabled", True)
        ) and bool(config.get("features.tables.schema_renderer_enabled", True)) and bool(
            config.get("features.tables.normalized_rows_enabled", True)
        )

        self._range_user_overridden = False
        self._range_updating = False
        self._results_rows: list[dict[str, Any]] = []
        self._results_row_offset = 0

    # ------------------------------------------------------------------ UI helpers

    def hide_suggestions(self) -> None:
        controllers = []
        for attr in ("ac_start", "ac_cel", "ac", "ac_c"):
            controller = getattr(self, attr, None)
            if controller is not None:
                controllers.append(controller)
        for controller in controllers:
            try:
                controller.hide()
            except Exception:
                pass

    def _clear_list_widget(self, list_widget: Any) -> None:
        if isinstance(list_widget, ttk.Treeview):
            list_widget.delete(*list_widget.get_children())
        else:
            list_widget.delete(0, tk.END)
        self._results_rows = []
        self._results_row_offset = 0

    @staticmethod
    def _extract_system_from_text(row_text: str | None) -> str:
        text = (row_text or "").strip()
        if not text:
            return ""
        text = re.sub(r"^\d+\.\s*", "", text)
        if "->" in text:
            text = text.split("->", 1)[-1].strip()
        parts = [part.strip() for part in text.split("  ") if part.strip()]
        if parts:
            text = parts[0]
        return text.split(" (", 1)[0].strip()

    def _extract_row_system(self, row: dict[str, Any]) -> str:
        candidates = (
            row.get("system_name"),
            row.get("to_system"),
            row.get("from_system"),
            row.get("system"),
            row.get("name"),
        )
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return ""

    def _attach_default_results_context_menu(self, list_widget: Any) -> None:
        common.attach_results_context_menu(
            list_widget,
            self._get_results_payload,
            self._get_results_actions,
        )

    def _get_results_payload(self, row_index, row_text=None) -> dict[str, Any] | None:
        try:
            idx = int(row_index) - int(self._results_row_offset)
        except Exception:
            return None
        if idx < 0:
            return None

        row = None
        if idx < len(self._results_rows):
            row = self._results_rows[idx]
        system = self._extract_row_system(row or {})
        if not system:
            system = self._extract_system_from_text(row_text)

        return {
            "row_index": idx,
            "row_text": row_text,
            "schema_id": self._schema_id,
            "row": row or {},
            "system": system,
        }

    def _get_results_actions(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        system = str(payload.get("system") or "").strip()

        if system:
            actions.append(
                {
                    "label": "Kopiuj system",
                    "action": lambda p: common.copy_text_to_clipboard(system, context="results.system"),
                }
            )
            actions.append({"separator": True})
            actions.append(
                {
                    "label": "Ustaw jako Start",
                    "action": lambda p: self._set_var_if_present("var_start", system),
                }
            )
            actions.append(
                {
                    "label": "Ustaw jako Cel",
                    "action": lambda p: self._set_var_if_present("var_cel", system),
                }
            )

        row_text = str(payload.get("row_text") or "").strip()
        if row_text:
            actions.append({"separator": True})
            actions.append(
                {
                    "label": "Kopiuj caly wiersz",
                    "action": lambda p: common.copy_text_to_clipboard(row_text, context="results.row"),
                }
            )

        row = payload.get("row") or {}
        if row:
            csv_text = common.format_row_delimited(self._schema_id, row, ",")
            tsv_text = common.format_row_delimited(self._schema_id, row, "\t")
        else:
            csv_text = ""
            tsv_text = ""
        if csv_text or tsv_text:
            actions.append({"separator": True})
        if csv_text:
            actions.append(
                {
                    "label": "Kopiuj jako CSV",
                    "action": lambda p: common.copy_text_to_clipboard(csv_text, context="results.csv"),
                }
            )
        if tsv_text:
            actions.append(
                {
                    "label": "Kopiuj jako TSV",
                    "action": lambda p: common.copy_text_to_clipboard(tsv_text, context="results.tsv"),
                }
            )

        while actions and actions[-1].get("separator"):
            actions.pop()
        return actions

    def _set_var_if_present(self, var_name: str, value: str) -> None:
        var_obj = getattr(self, var_name, None)
        if var_obj is None:
            return
        try:
            var_obj.set(value)
        except Exception:
            return

    @staticmethod
    def _reset_shared_route_state() -> None:
        config.STATE["rtr_data"] = {}
        config.STATE["trasa"] = []

    # ------------------------------------------------------------------ Busy / lifecycle

    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status(
                "WARN",
                "ROUTE_BUSY",
                text="Laduje...",
                source=self._status_source,
                ui_target=self._status_target,
            )
            return False
        if route_manager.is_busy():
            common.emit_status(
                "WARN",
                "ROUTE_BUSY",
                text="Inny planner juz liczy.",
                source=self._status_source,
                ui_target=self._status_target,
            )
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy and self._emit_busy_status:
            common.emit_status(
                "INFO",
                "ROUTE_BUSY",
                text="Laduje...",
                source=self._status_source,
                ui_target=self._status_target,
            )
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))
        if getattr(self, "lbl_status", None):
            self.lbl_status.config(text=("Laduje..." if busy else "Gotowy"))

    def _start_route_thread(self, target: Callable[..., None], args: tuple[Any, ...]) -> None:
        self._set_busy(True)
        route_manager.start_route_thread(self._mode_key, target, args=args, gui_ref=self.root)

    # ------------------------------------------------------------------ Jump range

    def _setup_range_tracking(self) -> None:
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def apply_jump_range_from_ship(self, value: float | None) -> None:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return
        if self._range_user_overridden:
            return
        if value is None:
            return
        self._set_range_value(value)

    def _on_range_changed(self, *_args) -> None:
        if self._range_updating:
            return
        if not config.get("planner_allow_manual_range_override", True):
            return
        self._range_user_overridden = True

    def _set_range_value(self, value: float) -> None:
        try:
            self._range_updating = True
            self.var_range.set(float(value))
        except Exception:
            pass
        finally:
            self._range_updating = False

    def _resolve_jump_range(self) -> float:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return float(self.var_range.get())
        if self._range_user_overridden:
            return float(self.var_range.get())

        jr = getattr(app_state.ship_state, "jump_range_current_ly", None)
        if jr is not None:
            self._set_range_value(jr)
            return float(jr)

        fallback = config.get("planner_fallback_range_ly", 30.0)
        try:
            fallback = float(fallback)
        except Exception:
            fallback = 30.0
        self._set_range_value(fallback)
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context=self._mode_key):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source=self._status_source,
                notify_overlay=True,
            )
        return fallback

    # ------------------------------------------------------------------ Worker/result

    def _is_schema_render_enabled(self) -> bool:
        return bool(config.get("features.tables.spansh_schema_enabled", True)) and bool(
            config.get("features.tables.schema_renderer_enabled", True)
        ) and bool(config.get("features.tables.normalized_rows_enabled", True))

    def _render_route_rows(
        self,
        list_widget: Any,
        route: list[str],
        rows: list[dict[str, Any]],
    ) -> None:
        if self._is_schema_render_enabled():
            if self._use_treeview:
                common.render_table_treeview(list_widget, self._schema_id, rows)
                common.register_active_route_list(
                    list_widget,
                    [],
                    numerate=False,
                    offset=1,
                    schema_id=self._schema_id,
                    rows=rows,
                )
            else:
                lines = common.render_table_lines(self._schema_id, rows)
                common.register_active_route_list(
                    list_widget,
                    lines,
                    numerate=False,
                    offset=1,
                    schema_id=self._schema_id,
                    rows=rows,
                )
                common.wypelnij_liste(
                    list_widget,
                    lines,
                    numerate=False,
                    show_copied_suffix=False,
                )
            return

        counts: dict[str, int] = {}
        for row in rows:
            sys_name = row.get("system_name")
            if sys_name:
                counts[sys_name] = counts.get(sys_name, 0) + 1
        lines = [f"{sys_name} ({counts.get(sys_name, 0)} cial)" for sys_name in route]
        common.register_active_route_list(list_widget, lines)
        common.wypelnij_liste(list_widget, lines)

    def _apply_route_result(
        self,
        list_widget: Any,
        route: list[str],
        rows: list[dict[str, Any]],
        worker_error: Exception | None,
    ) -> None:
        try:
            self._results_rows = rows or []
            self._results_row_offset = 0
            if worker_error is not None:
                common.emit_status(
                    "ERROR",
                    "ROUTE_ERROR",
                    text="Blad zapytania do Spansh.",
                    source=self._status_source,
                    ui_target=self._status_target,
                )
                return

            if route:
                route_manager.set_route(route, self._mode_key)
                self._render_route_rows(list_widget, route, rows)
                common.handle_route_ready_autoclipboard(self, route, status_target=self._status_target)
                common.emit_status(
                    "OK",
                    "ROUTE_FOUND",
                    text=f"Znaleziono {len(route)}",
                    source=self._status_source,
                    ui_target=self._status_target,
                )
                return

            common.emit_status(
                "ERROR",
                "ROUTE_EMPTY",
                text="Brak wynikow",
                source=self._status_source,
                ui_target=self._status_target,
            )
        finally:
            self._set_busy(False)

    def _execute_route_call(
        self,
        compute_fn: ComputeFn,
        call_args: tuple[Any, ...],
        *,
        list_widget: Any,
    ) -> None:
        route: list[str] = []
        rows: list[dict[str, Any]] = []
        worker_error: Exception | None = None

        try:
            route, rows = compute_fn(*call_args)
        except Exception as exc:  # noqa: BLE001
            worker_error = exc
        finally:
            run_on_ui_thread(
                self.root,
                lambda: self._apply_route_result(list_widget, route, rows, worker_error),
            )
