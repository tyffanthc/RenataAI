import tkinter as tk
from tkinter import ttk
import threading
from itertools import zip_longest
import config
from logic import neutron
from logic import utils
from gui import common
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
        self.var_eff = tk.DoubleVar(value=0.6)

        self._build_ui()
        self._range_user_overridden = False
        self._range_updating = False
        self.var_range.trace_add("write", self._on_range_changed)

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        # Start / Cel
        f_sys = ttk.Frame(fr)
        f_sys.pack(fill="x", pady=4)

        ttk.Label(f_sys, text="Start:", width=8).pack(side="left")
        self.e_start = ttk.Entry(f_sys, textvariable=self.var_start, width=25)
        self.e_start.pack(side="left", padx=(0, 10))

        ttk.Label(f_sys, text="Cel:", width=8).pack(side="left")
        self.e_cel = ttk.Entry(f_sys, textvariable=self.var_cel, width=25)
        self.e_cel.pack(side="left")

        # Autocomplete (poprawiona sygnatura)
        self.ac_start = AutocompleteController(self.root, self.e_start)
        self.ac_cel = AutocompleteController(self.root, self.e_cel)

        # Range + Efficiency
        f_rng = ttk.Frame(fr)
        f_rng.pack(fill="x", pady=4)

        ttk.Label(f_rng, text="Max range:", width=10).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_range, width=7).pack(side="left", padx=(0, 12))

        ttk.Label(f_rng, text="Eff.:", width=6).pack(side="left")
        ttk.Entry(f_rng, textvariable=self.var_eff, width=7).pack(side="left")

        # Przyciski
        f_btn = ttk.Frame(fr)
        f_btn.pack(pady=6)

        ttk.Button(f_btn, text="Wyznacz trasę", command=self.run_neutron).pack(side="left", padx=4)
        ttk.Button(f_btn, text="Wyczyść", command=self.clear).pack(side="left", padx=4)
        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack(pady=(4, 2))


        # Lista wyników
        self.lst = common.stworz_liste_trasy(self, title="Neutron Route")

    # ------------------------------------------------------------------ public

    def hide_suggestions(self):
        self.ac_start.hide()
        self.ac_cel.hide()

    def clear(self):
        self.lst.delete(0, tk.END)
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
        self.clear()

        s = self.var_start.get().strip()
        if not s:
            s = (getattr(app_state, "current_system", "") or "").strip() or "Nieznany"
        cel = self.var_cel.get().strip()
        rng = self._resolve_jump_range()
        eff = self.var_eff.get()

        args = (s, cel, rng, eff)

        route_manager.start_route_thread("neutron", self._th, args=args, gui_ref=self.root)

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

    def _th(self, s, cel, rng, eff):
        try:
            tr, details = neutron.oblicz_spansh_with_details(s, cel, rng, eff, self.root)

            if tr:
                route_manager.set_route(tr, "neutron")
                header = f"{'System':<30} {'Dist(LY)':>9} {'Rem(LY)':>9} {'Neut':>5} {'Jmp':>4}"
                opis = [header]
                for sys_name, detail in zip_longest(tr, details, fillvalue={}):
                    if not sys_name:
                        continue
                    opis.append(self._format_jump_row(sys_name, detail))

                common.handle_route_ready_autoclipboard(self, tr, status_target="neu")
                common.wypelnij_liste(self.lst, opis, numerate=False)
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
