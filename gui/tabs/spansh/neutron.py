import tkinter as tk
from tkinter import ttk
import json
import time
from itertools import zip_longest
import config
from logic import neutron
from logic import neutron_via
from logic.rows_normalizer import normalize_neutron_rows
from logic import utils
from logic.spansh_client import client as spansh_client
from gui import common
from gui import empty_state
from gui import strings as ui
from gui import ui_layout as layout
from gui.ui_thread import run_on_ui_thread
from gui.common_autocomplete import AutocompleteController, edsm_single_system_lookup
from app.route_manager import route_manager
from app.state import app_state


class NeutronTab(ttk.Frame):
    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        self.var_start = tk.StringVar()
        self.var_cel = tk.StringVar()
        self.var_range = tk.DoubleVar(value=50.0)
        self.var_eff = tk.DoubleVar(value=60.0)
        self.var_supercharge = tk.StringVar(value="Normal")
        self.var_via = tk.StringVar()
        self._via_items = []
        self._via_compact = bool(config.get("features.ui.neutron_via_compact", True))
        self._via_autocomplete = bool(config.get("features.ui.neutron_via_autocomplete", True))
        self._via_online_lookup = bool(config.get("features.providers.system_lookup_online", False))
        self._results_rows: list[dict] = []
        self._results_row_offset = 0
        self._results_widget = None
        self._busy = False
        self._use_treeview = bool(config.get("features.tables.treeview_enabled", False)) and bool(
            config.get("features.tables.spansh_schema_enabled", True)
        ) and bool(config.get("features.tables.schema_renderer_enabled", True)) and bool(
            config.get("features.tables.normalized_rows_enabled", True)
        )
        self._last_req_enabled = bool(config.get("features.debug.panel", False)) or bool(
            config.get("features.debug.spansh_last_request", False)
        )
        self._last_req_visible = False

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        f_form = ttk.Frame(fr)
        f_form.pack(fill="x", pady=4)
        layout.configure_form_grid(f_form)

        self.e_start, self.e_cel = layout.add_labeled_pair(
            f_form,
            0,
            ui.LABEL_START,
            self.var_start,
            ui.LABEL_TARGET,
            self.var_cel,
            left_entry_width=layout.ENTRY_W_LONG,
            right_entry_width=layout.ENTRY_W_LONG,
        )

        # Autocomplete (poprawiona sygnatura)
        self.ac_start = AutocompleteController(
            self.root,
            self.e_start,
            fallback_lookup=edsm_single_system_lookup,
        )
        self.ac_cel = AutocompleteController(
            self.root,
            self.e_cel,
            fallback_lookup=edsm_single_system_lookup,
        )

        layout.add_labeled_pair(
            f_form,
            1,
            ui.LABEL_JUMP_RANGE,
            self.var_range,
            ui.LABEL_EFFICIENCY,
            self.var_eff,
        )

        # Supercharge + Via list
        f_sc = ttk.Frame(fr)
        f_sc.pack(fill="x", pady=4)

        ttk.Label(f_sc, text=ui.LABEL_SUPERCHARGE, width=16).pack(side="left")
        self.cb_supercharge = ttk.Combobox(
            f_sc,
            textvariable=self.var_supercharge,
            values=["Normal", "Overcharge"],
            width=12,
            state="readonly",
        )
        self.cb_supercharge.pack(side="left", padx=(0, 12))

        ttk.Label(f_sc, text=f"{ui.LABEL_VIA}:", width=6).pack(side="left")
        self.e_via = ttk.Entry(f_sc, textvariable=self.var_via, width=18)
        self.e_via.pack(side="left", padx=(0, 6))
        self.e_via.bind("<Return>", self._add_via_event)
        self.e_via.bind("<KP_Enter>", self._add_via_event)
        if self._via_autocomplete:
            self.ac_via = AutocompleteController(
                self.root,
                self.e_via,
                min_chars=2,
                suggest_func=self._suggest_via_system,
            )
        ttk.Button(f_sc, text=ui.BUTTON_ADD, command=self._add_via).pack(side="left")

        f_via = ttk.Frame(fr)
        f_via.pack(fill="x", pady=4)
        if self._via_compact:
            self.via_canvas = tk.Canvas(f_via, height=48, highlightthickness=0)
            self.via_scroll = ttk.Scrollbar(
                f_via,
                orient="vertical",
                command=self.via_canvas.yview,
            )
            self.via_canvas.configure(yscrollcommand=self.via_scroll.set)
            self.via_canvas.pack(side="left", fill="x", expand=True)
            self.via_scroll.pack(side="left", fill="y")

            self.via_frame = ttk.Frame(self.via_canvas)
            self.via_window = self.via_canvas.create_window(
                (0, 0),
                window=self.via_frame,
                anchor="nw",
            )

            self.via_frame.bind("<Configure>", self._on_via_frame_configure)
            self.via_canvas.bind("<Configure>", self._on_via_canvas_configure)
        else:
            self.lst_via = tk.Listbox(f_via, height=3, width=40)
            self.lst_via.pack(side="left", fill="x", expand=True)
            ttk.Button(f_via, text=ui.BUTTON_REMOVE, command=self._remove_via).pack(side="left", padx=6)

        # Pasek akcji + status (tuz nad tabela)
        f_actions = ttk.Frame(fr)
        f_actions.pack(fill="x", pady=(6, 4))
        f_actions.columnconfigure(0, weight=0)
        f_actions.columnconfigure(1, weight=1)
        f_actions.columnconfigure(2, weight=0)

        f_btn = ttk.Frame(f_actions)
        f_btn.grid(row=0, column=0, sticky="w")
        self.btn_run = ttk.Button(f_btn, text=ui.BUTTON_CALCULATE, command=self.run_neutron)
        self.btn_run.pack(side="left", padx=(0, 6))
        ttk.Button(f_btn, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left", padx=(0, 6))
        ttk.Button(f_btn, text=ui.BUTTON_REVERSE, command=self._reverse_route).pack(side="left")

        self.lbl_status = ttk.Label(f_actions, text="Status: Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.grid(row=0, column=1)

        # Lista wynikow
        if self._use_treeview:
            self.lst = common.stworz_tabele_trasy(fr, title=ui.LIST_TITLE_NEUTRON)
        else:
            self.lst = common.stworz_liste_trasy(fr, title=ui.LIST_TITLE_NEUTRON)
        common.attach_results_context_menu(
            self.lst,
            self._get_results_payload,
            self._get_results_actions,
        )
        self._results_widget = self.lst
        title, message = empty_state.get_copy("no_results")
        empty_state.show_state(self.lst, empty_state.UIState.EMPTY, title, message)
        if self._last_req_enabled:
            self._build_last_request_ui(fr)

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()
        if hasattr(self, "ac_via"):
            self.ac_via.hide()

    def clear(self):
        self._clear_results()
        self._set_via_items([])
        try:
            app_state.clear_spansh_milestones(source="spansh.neutron.clear")
        except Exception:
            pass
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.neutron",
            ui_target="neu",
        )
        config.STATE["trasa"] = []
        config.STATE["copied_idx"] = None
        config.STATE["copied_sys"] = None

    @staticmethod
    def _build_neutron_milestones(route: list[str], details: list[dict]) -> list[str]:
        def _is_truthy(value) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            text = str(value).strip().lower()
            return text in {"1", "true", "t", "yes", "y"}

        milestones: list[str] = []
        seen: set[str] = set()

        for system_name, detail in zip_longest(route or [], details or [], fillvalue={}):
            if not system_name:
                continue
            if not isinstance(detail, dict):
                continue
            if not _is_truthy(detail.get("neutron")):
                continue
            raw = str(system_name).strip()
            norm = " ".join(raw.split()).casefold()
            if not raw or norm in seen:
                continue
            seen.add(norm)
            milestones.append(raw)

        # Always include final destination as milestone fallback.
        if route:
            last = str(route[-1]).strip()
            last_norm = " ".join(last.split()).casefold()
            if last and last_norm not in seen:
                milestones.append(last)
        return milestones

    def run_neutron(self):
        if not self._can_start():
            return
        self._clear_results()

        s = self.var_start.get().strip()
        if not s:
            s = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.var_cel.get().strip()
        rng = self._resolve_jump_range()
        eff = self.var_eff.get()
        via = self._get_via_items()
        supercharge_mode = self._resolve_supercharge_mode()

        args = (s, cel, rng, eff, supercharge_mode, via)

        self._set_busy(True)
        route_manager.start_route_thread("neutron", self._th, args=args, gui_ref=self.root)

    def _clear_results(self) -> None:
        if isinstance(self.lst, ttk.Treeview):
            self.lst.delete(*self.lst.get_children())
        else:
            self.lst.delete(0, tk.END)
        self._results_rows = []
        self._results_row_offset = 0
        title, message = empty_state.get_copy("no_results")
        empty_state.show_state(self.lst, empty_state.UIState.EMPTY, title, message)

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
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="neutron"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.neutron",
                ui_target="neu",
                notify_overlay=True,
            )
        return fallback

    def _th(self, s, cel, rng, eff, supercharge_mode, via):
        tr = []
        details = []
        worker_error = None
        try:
            tr, details = neutron.oblicz_spansh_with_details(
                s,
                cel,
                rng,
                eff,
                self.root,
                supercharge_mode=supercharge_mode,
                via=via,
            )
        except Exception as exc:
            worker_error = exc
        finally:
            def _apply_result() -> None:
                try:
                    if worker_error is not None:
                        common.emit_status(
                            "ERROR",
                            "ROUTE_ERROR",
                            text="Blad zapytania do Spansh.",
                            source="spansh.neutron",
                            ui_target="neu",
                        )
                        return

                    if tr:
                        route_manager.set_route(tr, "neutron")
                        try:
                            milestones = self._build_neutron_milestones(tr, details)
                            app_state.set_spansh_milestones(
                                milestones,
                                mode="neutron",
                                source="spansh.neutron",
                            )
                        except Exception:
                            pass
                        if (
                            config.get("features.tables.spansh_schema_enabled", True)
                            and config.get("features.tables.schema_renderer_enabled", True)
                            and config.get("features.tables.normalized_rows_enabled", True)
                        ):
                            rows = normalize_neutron_rows(details)
                            self._results_rows = rows
                            self._results_row_offset = 0
                            if self._use_treeview:
                                common.render_table_treeview(self.lst, "neutron", rows)
                                common.register_active_route_list(
                                    self.lst,
                                    [],
                                    numerate=False,
                                    offset=1,
                                    schema_id="neutron",
                                    rows=rows,
                                )
                            else:
                                opis = common.render_table_lines("neutron", rows)
                                common.register_active_route_list(
                                    self.lst,
                                    opis,
                                    numerate=False,
                                    offset=1,
                                    schema_id="neutron",
                                    rows=rows,
                                )
                                common.wypelnij_liste(
                                    self.lst,
                                    opis,
                                    numerate=False,
                                    show_copied_suffix=False,
                                )
                        else:
                            self._results_rows = normalize_neutron_rows(details)
                            self._results_row_offset = 1
                            header = "{:<30} {:>9} {:>9} {:>5} {:>4}".format(
                                "System",
                                "Dist(LY)",
                                "Rem(LY)",
                                "Neut",
                                "Jmp",
                            )
                            opis = [header]
                            for sys_name, detail in zip_longest(tr, details, fillvalue={}):
                                if not sys_name:
                                    continue
                                opis.append(self._format_jump_row(sys_name, detail))

                            common.register_active_route_list(
                                self.lst,
                                opis,
                                numerate=False,
                                offset=1,
                            )
                            common.wypelnij_liste(self.lst, opis, numerate=False)
                        common.handle_route_ready_autoclipboard(self, tr, status_target="neu")
                        empty_state.hide_state(self.lst)
                        common.emit_status(
                            "OK",
                            "ROUTE_FOUND",
                            text=f"Znaleziono {len(tr)}",
                            source="spansh.neutron",
                            ui_target="neu",
                        )
                    else:
                        common.emit_status(
                            "ERROR",
                            "ROUTE_EMPTY",
                            text="Brak wynikow",
                            source="spansh.neutron",
                            ui_target="neu",
                        )
                        title, message = empty_state.get_copy("no_results")
                        empty_state.show_state(self.lst, empty_state.UIState.EMPTY, title, message)
                except Exception:
                    common.emit_status(
                        "ERROR",
                        "ROUTE_ERROR",
                        text="Blad zapytania do Spansh.",
                        source="spansh.neutron",
                        ui_target="neu",
                    )
                finally:
                    if self._last_req_enabled:
                        self._render_last_request()
                    self._set_busy(False)

            run_on_ui_thread(self.root, _apply_result)

    def _can_start(self) -> bool:
        if self._busy:
            common.emit_status("WARN", "ROUTE_BUSY", text="Laduje...", source="spansh.neutron", ui_target="neu")
            return False
        if route_manager.is_busy():
            common.emit_status("WARN", "ROUTE_BUSY", text="Inny planner juz liczy.", source="spansh.neutron", ui_target="neu")
            return False
        return True

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if getattr(self, "btn_run", None):
            self.btn_run.config(state=("disabled" if busy else "normal"))
        if getattr(self, "lbl_status", None):
            self.set_status_text("Laduje..." if busy else "Gotowy", None)

    def set_status_text(self, text: str | None, color: str | None) -> None:
        raw = (text or "").strip()
        if not raw:
            raw = "Gotowy"
        if not raw.lower().startswith("status:"):
            raw = f"Status: {raw}"
        if color:
            self.lbl_status.config(text=raw, foreground=color)
        else:
            self.lbl_status.config(text=raw)

    def _build_last_request_ui(self, parent: ttk.Frame) -> None:
        self.last_req_frame = ttk.Frame(parent)
        self.last_req_frame.pack(fill="x", pady=(4, 0))

        header = ttk.Frame(self.last_req_frame)
        header.pack(fill="x")
        self.btn_last_req = ttk.Button(
            header,
            text="Ostatnie zapytanie do Spansh >",
            command=self._toggle_last_request,
        )
        self.btn_last_req.pack(side="left")

        self.last_req_body = ttk.Frame(self.last_req_frame)
        self.last_req_body.pack(fill="both", expand=True, pady=(2, 0))
        self.last_req_text = tk.Text(self.last_req_body, height=6, wrap="word")
        self.last_req_text.pack(fill="both", expand=True)
        self.last_req_text.configure(state="disabled")
        self.last_req_body.pack_forget()

    def _toggle_last_request(self) -> None:
        if not self._last_req_enabled:
            return
        self._last_req_visible = not self._last_req_visible
        if self._last_req_visible:
            self.last_req_body.pack(fill="both", expand=True, pady=(2, 0))
            self.btn_last_req.config(text="Ostatnie zapytanie do Spansh v")
            self._render_last_request()
        else:
            self.last_req_body.pack_forget()
            self.btn_last_req.config(text="Ostatnie zapytanie do Spansh >")

    def _render_last_request(self) -> None:
        if not self._last_req_enabled:
            return
        if not getattr(self, "last_req_text", None):
            return
        data = spansh_client.get_last_request()
        text = self._format_last_request(data)
        self._set_last_request_text(text)

    def _set_last_request_text(self, text: str) -> None:
        self.last_req_text.configure(state="normal")
        self.last_req_text.delete("1.0", tk.END)
        self.last_req_text.insert("1.0", text)
        self.last_req_text.configure(state="disabled")

    def _format_last_request(self, data: dict) -> str:
        if not data:
            return "Brak danych."
        ts = data.get("timestamp")
        ts_text = "-"
        if isinstance(ts, (int, float)):
            ts_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        response_ms = data.get("response_ms")
        response_text = "-" if response_ms is None else str(response_ms)
        lines = [
            f"Status: {data.get('status', '-')}",
            f"Endpoint: {data.get('endpoint', '-')}",
            f"Mode: {data.get('mode', '-')}",
            f"Timestamp: {ts_text}",
            f"Response ms: {response_text}",
        ]
        url = data.get("url")
        if url:
            lines.append(f"URL: {url}")
        payload = data.get("payload")
        if payload is not None:
            lines.append("Payload:")
            try:
                lines.append(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
            except Exception:
                lines.append(str(payload))
        return "\n".join(lines)

    def _get_results_payload(self, row_index, row_text=None) -> dict | None:
        try:
            idx = int(row_index) - int(self._results_row_offset)
        except Exception:
            return None
        if idx < 0 or idx >= len(self._results_rows):
            return None
        row = self._results_rows[idx]
        system, has_system = common.resolve_copy_system_value("neutron", row, row_text)
        return {
            "row_index": idx,
            "row_text": row_text,
            "schema_id": "neutron",
            "row": row,
            "system": system,
            "has_system": has_system,
        }

    def _get_results_actions(self, payload: dict) -> list[dict]:
        actions = []
        system = (payload.get("system") or "").strip()
        has_system = bool(payload.get("has_system", False))

        actions.append(
            {
                "label": "Kopiuj system",
                "action": lambda p: common.copy_text_to_clipboard(system, context="results.system"),
            }
        )
        row_idx = int(payload.get("row_index", -1))
        row_exists = 0 <= row_idx < len(self._results_rows)
        selected_exists = bool(self._selected_internal_indices())
        all_exists = bool(self._results_rows)
        actions.append({"separator": True})
        actions.append(
            {
                "label": "Kopiuj wiersze",
                "children": [
                    {
                        "label": "Kopiuj wiersz",
                        "action": lambda p: self._copy_clicked_row(p),
                        "enabled": row_exists,
                    },
                    {
                        "label": "Kopiuj zaznaczone",
                        "action": lambda p: self._copy_selected_rows(p),
                        "enabled": selected_exists or row_exists,
                    },
                    {
                        "label": "Kopiuj wszystko",
                        "action": lambda p: self._copy_all_rows(),
                        "enabled": all_exists,
                    },
                ],
            }
        )
        if has_system:
            actions.append({"separator": True})
            actions.append(
                {
                    "label": "Ustaw jako Start",
                    "action": lambda p: self.var_start.set(system),
                }
            )
            actions.append(
                {
                    "label": "Ustaw jako Cel",
                    "action": lambda p: self.var_cel.set(system),
                }
            )
            actions.append(
                {
                    "label": "Dodaj jako Via",
                    "action": lambda p: self._add_via_from_system(system),
                }
            )

        row = payload.get("row") or {}
        csv_text = common.format_row_delimited("neutron", row, ",")
        csv_with_header = common.format_row_delimited_with_header("neutron", row, ",")
        tsv_text = common.format_row_delimited("neutron", row, "	")
        tsv_with_header = common.format_row_delimited_with_header("neutron", row, "	")
        export_children = []
        if tsv_with_header:
            export_children.append(
                {
                    "label": "Kopiuj jako Exel",
                    "action": lambda p: common.copy_text_to_clipboard(tsv_with_header, context="results.excel"),
                }
            )
        if csv_text:
            export_children.append(
                {
                    "label": "CSV",
                    "action": lambda p: common.copy_text_to_clipboard(csv_text, context="results.csv"),
                }
            )
        if csv_with_header:
            export_children.append(
                {
                    "label": "CSV (naglowki)",
                    "action": lambda p: common.copy_text_to_clipboard(csv_with_header, context="results.csv_headers"),
                }
            )
        if tsv_text:
            export_children.append(
                {
                    "label": "TSV",
                    "action": lambda p: common.copy_text_to_clipboard(tsv_text, context="results.tsv"),
                }
            )
        if tsv_with_header:
            export_children.append(
                {
                    "label": "TSV (naglowki)",
                    "action": lambda p: common.copy_text_to_clipboard(tsv_with_header, context="results.tsv_headers"),
                }
            )
        if export_children:
            actions.append({"separator": True})
        if export_children:
            actions.append(
                {
                    "label": "Kopiuj jako",
                    "children": export_children,
                }
            )

        while actions and actions[-1].get("separator"):
            actions.pop()
        return actions

    def _format_result_line(self, row: dict, row_text: str | None = None) -> str:
        try:
            rendered = common.render_table_lines("neutron", [row])
            if rendered:
                return str(rendered[0]).strip()
        except Exception:
            pass
        return str(row_text or "").strip()

    def _selected_internal_indices(self) -> list[int]:
        widget = self._results_widget
        if widget is None:
            return []
        indices: list[int] = []
        if isinstance(widget, ttk.Treeview):
            selected_ids = set(str(item) for item in (widget.selection() or ()))
            if not selected_ids:
                return []
            for iid in widget.get_children():
                if str(iid) not in selected_ids:
                    continue
                try:
                    idx = int(str(iid)) - int(self._results_row_offset)
                except Exception:
                    continue
                if 0 <= idx < len(self._results_rows):
                    indices.append(idx)
            return indices

        try:
            selected = list(widget.curselection())
        except Exception:
            selected = []
        for item in selected:
            try:
                idx = int(item) - int(self._results_row_offset)
            except Exception:
                continue
            if 0 <= idx < len(self._results_rows):
                indices.append(idx)
        return indices

    def _copy_indices_to_clipboard(self, indices: list[int], *, context: str) -> None:
        lines: list[str] = []
        for idx in indices:
            if idx < 0 or idx >= len(self._results_rows):
                continue
            row = self._results_rows[idx]
            line = self._format_result_line(row)
            if line:
                lines.append(line)
        text = "\n".join(lines).strip()
        if not text:
            return
        common.copy_text_to_clipboard(text, context=context)

    def _copy_clicked_row(self, payload: dict) -> None:
        idx = int(payload.get("row_index", -1))
        if idx < 0 or idx >= len(self._results_rows):
            return
        self._copy_indices_to_clipboard([idx], context="results.row")

    def _copy_selected_rows(self, payload: dict) -> None:
        indices = self._selected_internal_indices()
        if not indices:
            idx = int(payload.get("row_index", -1))
            if idx >= 0:
                indices = [idx]
        if not indices:
            return
        self._copy_indices_to_clipboard(indices, context="results.rows_selected")

    def _copy_all_rows(self) -> None:
        if not self._results_rows:
            return
        self._copy_indices_to_clipboard(list(range(len(self._results_rows))), context="results.rows_all")

    def _add_via_from_system(self, system: str) -> None:
        if not system:
            return
        self.var_via.set(system)
        self._add_via()


    def _format_jump_row(self, system_name, detail):
        def _fmt_num(value):
            try:
                if isinstance(value, str):
                    value = value.replace(",", "").strip()
                num = float(value)
            except Exception:
                return "-"
            return f"{num:.2f}"

        def _fmt_neutron(value):
            if value is True:
                return "YES"
            if value is False:
                return "NO"
            if isinstance(value, str):
                val = value.strip().lower()
                if val in ("yes", "true", "1"):
                    return "YES"
                if val in ("no", "false", "0"):
                    return "NO"
            return "-"

        name = (system_name or "").strip()
        distance = _fmt_num(detail.get("distance"))
        remaining = _fmt_num(detail.get("remaining"))
        neutron_flag = _fmt_neutron(detail.get("neutron"))
        jumps = detail.get("jumps")
        jumps_txt = "-" if jumps is None else str(jumps)

        return f"{name[:30]:<30} {distance:>9} {remaining:>9} {neutron_flag:>5} {jumps_txt:>4}"

    def _add_via(self) -> None:
        value = (self.var_via.get() or "").strip()
        ok, reason, warn_short = neutron_via.validate_via(
            value=value,
            existing=self._get_via_items(),
            start=self.var_start.get(),
            end=self.var_cel.get(),
        )
        if not ok:
            if reason == "empty":
                self._emit_via_warning("Via: puste pole.")
            elif reason == "start_or_end":
                self._emit_via_warning("Via: system taki sam jak Start lub Cel.")
            elif reason == "duplicate":
                self._emit_via_warning("Via: duplikat.")
            return
        if self._via_compact:
            self._via_items.append(value)
            self._render_via_chips()
        else:
            self.lst_via.insert(tk.END, value)
        if warn_short:
            self._emit_via_warning("Via: to wyglada jak literowka.")
        self.var_via.set("")
        self.e_via.focus_set()

    def _add_via_event(self, _event) -> None:
        if hasattr(self, "ac_via") and self.ac_via.sug_list.winfo_ismapped():
            return
        self._add_via()

    def _remove_via(self) -> None:
        if self._via_compact:
            return
        selection = list(self.lst_via.curselection())
        if not selection:
            return
        for index in reversed(selection):
            self.lst_via.delete(index)

    def _reverse_route(self) -> None:
        start = self.var_start.get().strip()
        cel = self.var_cel.get().strip()
        self.var_start.set(cel)
        self.var_cel.set(start)

        items = self._get_via_items()
        self._set_via_items(list(reversed(items)))

    def _resolve_supercharge_mode(self) -> str:
        value = (self.var_supercharge.get() or "").strip().lower()
        if value.startswith("over"):
            return "overcharge"
        return "normal"

    def _emit_via_warning(self, text: str) -> None:
        common.emit_status(
            "WARN",
            "VIA_INPUT",
            text=text,
            source="spansh.neutron",
            ui_target="neu",
        )

    def _local_system_candidates(self) -> list[str]:
        candidates = []
        current = (getattr(app_state, "current_system", "") or "").strip()
        if current:
            candidates.append(current)
        for item in config.STATE.get("trasa", []) or []:
            if item:
                candidates.append(str(item).strip())
        for item in self._get_via_items():
            if item:
                candidates.append(str(item).strip())
        unique = []
        seen = set()
        for item in candidates:
            key = neutron_via.normalize_system_name(item)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _suggest_via_system(self, query: str) -> list[str]:
        if not self._via_autocomplete:
            return []
        q = (query or "").strip()
        if not q:
            return []
        try:
            return utils.pobierz_sugestie(q)
        except Exception:
            return []

    def _filter_systems(self, systems: list[str], query: str) -> list[str]:
        q = query.strip().lower()
        if not q:
            return systems
        return [item for item in systems if q in (item or "").lower()]

    def _get_via_items(self) -> list[str]:
        if self._via_compact:
            return list(self._via_items)
        return [item.strip() for item in self.lst_via.get(0, tk.END) if item.strip()]

    def _set_via_items(self, items: list[str]) -> None:
        if self._via_compact:
            self._via_items = [item.strip() for item in items if item.strip()]
            self._render_via_chips()
        else:
            self.lst_via.delete(0, tk.END)
            for item in items:
                value = (item or "").strip()
                if value:
                    self.lst_via.insert(tk.END, value)

    def _render_via_chips(self) -> None:
        if not self._via_compact:
            return
        for child in self.via_frame.winfo_children():
            child.destroy()

        width = self.via_canvas.winfo_width() or 320
        col_width = 140
        columns = max(1, int(width / col_width))
        row = 0
        col = 0

        for idx, item in enumerate(self._via_items):
            chip = ttk.Frame(self.via_frame)
            label = ttk.Label(chip, text=item)
            label.pack(side="left", padx=(6, 2))
            btn = ttk.Button(
                chip,
                text="x",
                width=2,
                command=lambda i=idx: self._remove_via_index(i),
            )
            btn.pack(side="left", padx=(2, 4))
            chip.grid(row=row, column=col, padx=4, pady=2, sticky="w")

            col += 1
            if col >= columns:
                col = 0
                row += 1

        self.via_frame.update_idletasks()
        self.via_canvas.configure(scrollregion=self.via_canvas.bbox("all"))

    def _remove_via_index(self, index: int) -> None:
        if index < 0 or index >= len(self._via_items):
            return
        del self._via_items[index]
        self._render_via_chips()

    def _on_via_frame_configure(self, _event) -> None:
        self.via_canvas.configure(scrollregion=self.via_canvas.bbox("all"))

    def _on_via_canvas_configure(self, event) -> None:
        if not self._via_compact:
            return
        self.via_canvas.itemconfigure(self.via_window, width=event.width)
        self._render_via_chips()
