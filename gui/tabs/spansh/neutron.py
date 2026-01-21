import tkinter as tk
from tkinter import ttk
import threading
from itertools import zip_longest
import config
from logic import neutron
from logic import neutron_via
from logic.rows_normalizer import normalize_neutron_rows
from logic import utils
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController
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
        self.ac_start = AutocompleteController(self.root, self.e_start)
        self.ac_cel = AutocompleteController(self.root, self.e_cel)

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

        # Przyciski
        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=(6, 2))

        ttk.Button(f_btn, text=ui.BUTTON_CALCULATE, command=self.run_neutron).pack(side="left", padx=4)
        ttk.Button(f_btn, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left", padx=4)
        ttk.Button(f_btn, text=ui.BUTTON_REVERSE, command=self._reverse_route).pack(side="left", padx=4)
        f_status = ttk.Frame(fr)
        f_status.pack(pady=(2, 2))
        self.lbl_status = ttk.Label(f_status, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack()


        # Lista wyników
        self.lst = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_NEUTRON)
        common.attach_results_context_menu(
            self.lst,
            self._get_results_payload,
            self._get_results_actions,
        )

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()
        if hasattr(self, "ac_via"):
            self.ac_via.hide()

    def clear(self):
        self._clear_results()
        self._set_via_items([])
        common.emit_status(
            "INFO",
            "ROUTE_CLEARED",
            source="spansh.neutron",
            ui_target="neu",
        )
        config.STATE["trasa"] = []
        config.STATE["copied_idx"] = None
        config.STATE["copied_sys"] = None

    def run_neutron(self):
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

        route_manager.start_route_thread("neutron", self._th, args=args, gui_ref=self.root)

    def _clear_results(self) -> None:
        self.lst.delete(0, tk.END)
        self._results_rows = []
        self._results_row_offset = 0

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

            if tr:
                route_manager.set_route(tr, "neutron")
                if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                    rows = normalize_neutron_rows(details)
                    self._results_rows = rows
                    self._results_row_offset = 0
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
                    header = "{:<30} {:>9} {:>9} {:>5} {:>4}".format("System", "Dist(LY)", "Rem(LY)", "Neut", "Jmp")
                    opis = [header]
                    for sys_name, detail in zip_longest(tr, details, fillvalue={}):
                        if not sys_name:
                            continue
                        opis.append(self._format_jump_row(sys_name, detail))

                    common.register_active_route_list(self.lst, opis, numerate=False, offset=1)
                    common.wypelnij_liste(self.lst, opis, numerate=False)
                common.handle_route_ready_autoclipboard(self, tr, status_target="neu")
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
                    text="Brak wyników",
                    source="spansh.neutron",
                    ui_target="neu",
                )
        except Exception as e:  # żeby nie uwalić GUI przy wyjątku w wątku
            common.emit_status(
                "ERROR",
                "ROUTE_ERROR",
                text=f"Błąd: {e}",
                source="spansh.neutron",
                ui_target="neu",
            )

    def _get_results_payload(self, row_index, row_text=None) -> dict | None:
        idx = int(row_index) - int(self._results_row_offset)
        if idx < 0 or idx >= len(self._results_rows):
            return None
        row = self._results_rows[idx]
        return {
            "row_index": idx,
            "row_text": row_text,
            "schema_id": "neutron",
            "row": row,
            "system": row.get("system_name"),
        }

    def _get_results_actions(self, payload: dict) -> list[dict]:
        actions = []
        system = (payload.get("system") or "").strip()

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

        row_text = (payload.get("row_text") or "").strip()
        if row_text:
            actions.append({"separator": True})
            actions.append(
                {
                    "label": "Kopiuj caly wiersz",
                    "action": lambda p: common.copy_text_to_clipboard(row_text, context="results.row"),
                }
            )

        row = payload.get("row") or {}
        csv_text = common.format_row_delimited("neutron", row, ",")
        tsv_text = common.format_row_delimited("neutron", row, "	")
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

        return actions

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
            self._emit_via_warning("Via: to wygląda jak literówka.")
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
