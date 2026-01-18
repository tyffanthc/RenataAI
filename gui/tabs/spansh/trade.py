import tkinter as tk
from tkinter import ttk
import threading
from logic import trade
from logic import utils
from logic.spansh_client import client as spansh_client
from gui import common
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class TradeTab(ttk.Frame):
    """
    Zakładka: Trade Planner (Spansh)
    """

    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        # Referencja do globalnego AppState (nie tworzymy nowej instancji)
        self.app_state = app_state

        # System / stacja startowa – inicjalnie puste,
        # uzupełniane z app_state w refresh_from_app_state().
        self.var_start_system = tk.StringVar()
        self.var_start_station = tk.StringVar()

        # Parametry liczbowo-konfiguracyjne
        self.var_capital = tk.IntVar(value=10_000_000)
        self.var_max_hop = tk.DoubleVar(value=20.0)
        self.var_cargo = tk.IntVar(value=256)
        self.var_max_hops = tk.IntVar(value=10)
        self.var_max_dta = tk.IntVar(value=5000)
        self.var_max_age = tk.IntVar(value=2)

        # Flagowe checkboxy
        self.var_large_pad = tk.BooleanVar(value=True)
        self.var_planetary = tk.BooleanVar(value=True)
        self.var_player_owned = tk.BooleanVar(value=False)
        self.var_restricted = tk.BooleanVar(value=False)
        self.var_prohibited = tk.BooleanVar(value=False)
        self.var_avoid_loops = tk.BooleanVar(value=True)
        self.var_allow_permits = tk.BooleanVar(value=True)

        self._build_ui()
        self._hop_user_overridden = False
        self._hop_updating = False
        self.var_max_hop.trace_add("write", self._on_hop_changed)

        # D3c – pierwsze uzupełnienie pól z app_state
        self.refresh_from_app_state()
        self.bind("<Visibility>", self._on_visibility)

    def _on_visibility(self, _event):
        self.refresh_from_app_state()

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        # --- System / stacja ---------------------------------------------------
        f_src = ttk.Frame(fr)
        f_src.pack(fill="x", pady=4)

        ttk.Label(f_src, text="System:", width=10).pack(side="left")
        self.e_system = ttk.Entry(f_src, textvariable=self.var_start_system, width=30)
        self.e_system.pack(side="left", padx=(0, 10))

        # Autocomplete dla systemu
        self.ac_source = AutocompleteController(
            self.root,
            self.e_system,
            suggest_func=self._suggest_system,
        )

        f_sta = ttk.Frame(fr)
        f_sta.pack(fill="x", pady=4)

        ttk.Label(f_sta, text="Stacja:", width=10).pack(side="left")
        self.e_station = ttk.Entry(f_sta, textvariable=self.var_start_station, width=30)
        self.e_station.pack(side="left", padx=(0, 10))

        # Autocomplete dla stacji (D3b – na podstawie wybranego systemu)
        self.ac_station = AutocompleteController(
            self.root,
            self.e_station,
            min_chars=2,
            suggest_func=self._suggest_station,
        )

        # --- Kapitał / hop -----------------------------------------------------
        f_cap = ttk.Frame(fr)
        f_cap.pack(fill="x", pady=4)

        ttk.Label(f_cap, text="Kapitał [Cr]:", width=12).pack(side="left")
        ttk.Entry(
            f_cap,
            textvariable=self.var_capital,
            width=12,
        ).pack(side="left", padx=(0, 12))

        ttk.Label(f_cap, text="Max hop [LY]:", width=12).pack(side="left")
        ttk.Entry(f_cap, textvariable=self.var_max_hop, width=8).pack(side="left")

        # --- Cargo / max hops --------------------------------------------------
        f_cargo = ttk.Frame(fr)
        f_cargo.pack(fill="x", pady=4)

        ttk.Label(f_cargo, text="Cargo:", width=12).pack(side="left")
        ttk.Entry(f_cargo, textvariable=self.var_cargo, width=8).pack(
            side="left", padx=(0, 12)
        )

        ttk.Label(f_cargo, text="Max hops:", width=12).pack(side="left")
        ttk.Entry(f_cargo, textvariable=self.var_max_hops, width=8).pack(side="left")

        # --- Max DTA / Max age -------------------------------------------------
        f_dta = ttk.Frame(fr)
        f_dta.pack(fill="x", pady=4)

        ttk.Label(f_dta, text="Max DTA [ls]:", width=12).pack(side="left")
        ttk.Entry(f_dta, textvariable=self.var_max_dta, width=8).pack(
            side="left", padx=(0, 12)
        )

        ttk.Label(f_dta, text="Max age [dni]:", width=12).pack(side="left")
        ttk.Entry(f_dta, textvariable=self.var_max_age, width=8).pack(side="left")

        # --- Flagowe checkboxy -------------------------------------------------
        f_flags1 = ttk.Frame(fr)
        f_flags1.pack(fill="x", pady=4)

        ttk.Checkbutton(
            f_flags1,
            text="Large pad",
            variable=self.var_large_pad,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags1,
            text="Planetary",
            variable=self.var_planetary,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags1,
            text="Player owned",
            variable=self.var_player_owned,
        ).pack(side="left", padx=5)

        f_flags2 = ttk.Frame(fr)
        f_flags2.pack(fill="x", pady=4)

        ttk.Checkbutton(
            f_flags2,
            text="Restricted",
            variable=self.var_restricted,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text="Prohibited",
            variable=self.var_prohibited,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text="Avoid loops",
            variable=self.var_avoid_loops,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text="Allow permits",
            variable=self.var_allow_permits,
        ).pack(side="left", padx=5)

        # --- Przyciski / status / lista ---------------------------------------
        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        ttk.Button(
            bf,
            text="Szukaj trasy handlowej",
            command=self.run_trade,
        ).pack(side="left", padx=5)

        ttk.Button(bf, text="Wyczyść", command=self.clear).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack(pady=(4, 2))

        self.lst_trade = common.stworz_liste_trasy(self, title="Trade Route")

    def refresh_from_app_state(self):
        """D3c: uzupełnia pola System/Stacja na podstawie AppState.

        Używamy TEGO SAMEGO app_state, co navigation_events.
        """
        try:
            sysname = (getattr(self.app_state, "current_system", "") or "").strip()
            staname = (getattr(self.app_state, "current_station", "") or "").strip()
            is_docked = bool(getattr(self.app_state, "is_docked", False))
        except Exception:
            sysname = ""
            staname = ""
            is_docked = False

        # Traktujemy 'Unknown' / 'Nieznany' jak brak realnej lokalizacji
        if sysname in ("Unknown", "Nieznany"):
            sysname = ""

        if not (self.var_start_system.get() or "").strip() and sysname:
            self.var_start_system.set(sysname)
        if is_docked and not (self.var_start_station.get() or "").strip() and staname:
            self.var_start_station.set(staname)

        print(f"[TRADE] refresh_from_app_state: {sysname!r} / {staname!r}")

    # ------------------------------------------------------------------ logika GUI

    def _suggest_station(self, tekst: str):
        """Funkcja podpowiedzi stacji dla AutocompleteController.

        Bazuje najpierw na aktualnym systemie z pola,
        a jeśli jest puste – na app_state.current_system.
        """
        system = (self.var_start_system.get() or "").strip()
        if not system:
            system = (getattr(self.app_state, "current_system", "") or "").strip()

        if not system:
            return []

        # Jeśli ktoś ma w polu systemu format "System / Stacja" / "System, Stacja",
        # to do zapytania o stacje bierzemy tylko nazwę systemu (część przed separatorem).
        raw = system
        if "/" in raw:
            raw = raw.split("/", 1)[0].strip()
        elif "," in raw:
            raw = raw.split(",", 1)[0].strip()

        if not raw:
            return []

        q = (tekst or "").strip()
        if not q:
            return []

        try:
            return spansh_client.stations_for_system(raw, q)
        except Exception as e:
            print(f"[Spansh] Station autocomplete exception ({raw!r}, {q!r}): {e}")
            return []

    def _suggest_system(self, tekst: str):
        """Funkcja podpowiedzi systemów dla AutocompleteController."""
        q = (tekst or "").strip()
        if not q:
            return []

        try:
            return spansh_client.systems_suggest(q)
        except Exception as e:
            print(f"[Spansh] System autocomplete exception ({q!r}): {e}")
            return []

    def hide_suggestions(self):
        self.ac_source.hide()
        if hasattr(self, "ac_station"):
            self.ac_station.hide()

    def clear(self):
        self.lst_trade.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")

    def run_trade(self):
        """
        Startuje obliczenia w osobnym wątku.
        """
        self.clear()

        start_system = self.var_start_system.get().strip()
        start_station = self.var_start_station.get().strip()

        # Fallback do aktualnej lokalizacji z app_state, jeśli pola są puste
        if not start_system:
            start_system = (getattr(self.app_state, "current_system", "") or "").strip()
        if not start_station and bool(getattr(self.app_state, "is_docked", False)):
            start_station = (getattr(self.app_state, "current_station", "") or "").strip()

        # Ostateczny fallback do config.STATE (zgodność wsteczna)

        if not start_system:
            common.emit_status(
                "ERROR",
                "TRADE_INPUT_MISSING",
                source="spansh.trade",
                ui_target="trade",
            )
            return

        # D3b: dwa tryby wejścia:
        # 1) klasyczny: osobne System + Stacja,
        # 2) kompatybilny z webowym SPANSH: "System / Stacja" w jednym polu,
        #    puste pole "Stacja" -> backend rozbije to w oblicz_trade().
        if not start_station:
            sep_raw = start_system or ""
            if "/" not in sep_raw and "," not in sep_raw:
                common.emit_status(
                    "ERROR",
                    "TRADE_STATION_REQUIRED",
                    source="spansh.trade",
                    ui_target="trade",
                )
                return

        capital = self.var_capital.get()
        max_hop = self._resolve_max_hop()
        cargo = self.var_cargo.get()
        max_hops = self.var_max_hops.get()
        max_dta = self.var_max_dta.get()
        max_age = self.var_max_age.get()

        flags = {
            "large_pad": self.var_large_pad.get(),
            "planetary": self.var_planetary.get(),
            "player_owned": self.var_player_owned.get(),
            "restricted": self.var_restricted.get(),
            "prohibited": self.var_prohibited.get(),
            "avoid_loops": self.var_avoid_loops.get(),
            "allow_permits": self.var_allow_permits.get(),
        }

        args = (
            start_system,
            start_station,
            capital,
            max_hop,
            cargo,
            max_hops,
            max_dta,
            max_age,
            flags,
        )

        route_manager.start_route_thread("trade", self._th, args=args, gui_ref=self.root)

    def apply_jump_range_from_ship(self, value: float | None) -> None:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return
        if self._hop_user_overridden:
            return
        if value is None:
            return
        self._set_max_hop(value)

    def _on_hop_changed(self, *_args) -> None:
        if self._hop_updating:
            return
        if not config.get("planner_allow_manual_range_override", True):
            return
        self._hop_user_overridden = True

    def _set_max_hop(self, value: float) -> None:
        try:
            self._hop_updating = True
            self.var_max_hop.set(float(value))
        except Exception:
            pass
        finally:
            self._hop_updating = False

    def _resolve_max_hop(self) -> float:
        if not config.get("planner_auto_use_ship_jump_range", True):
            return float(self.var_max_hop.get())
        if self._hop_user_overridden:
            return float(self.var_max_hop.get())

        jr = getattr(self.app_state.ship_state, "jump_range_current_ly", None)
        if jr is not None:
            self._set_max_hop(jr)
            return float(jr)

        fallback = config.get("planner_fallback_range_ly", 30.0)
        try:
            fallback = float(fallback)
        except Exception:
            fallback = 30.0
        self._set_max_hop(fallback)
        if utils.DEBOUNCER.is_allowed("jr_fallback", cooldown_sec=10.0, context="trade"):
            common.emit_status(
                "WARN",
                "JR_NOT_READY_FALLBACK",
                source="spansh.trade",
                ui_target="trade",
                notify_overlay=True,
            )
        return fallback

    def _th(
        self,
        start_system,
        start_station,
        capital,
        max_hop,
        cargo,
        max_hops,
        max_dta,
        max_age,
        flags,
    ):
        """
        Wątek roboczy: wywołuje logikę trade.oblicz_trade i wypełnia listę.
        """
        try:
            tr, rows = trade.oblicz_trade(
                start_system,
                start_station,
                capital,
                max_hop,
                cargo,
                max_hops,
                max_dta,
                max_age,
                flags,
                self.root,
            )

            if rows:
                route_manager.set_route(tr, "trade")
                if config.get("features.tables.spansh_schema_enabled", True) and config.get("features.tables.schema_renderer_enabled", True) and config.get("features.tables.normalized_rows_enabled", True):
                    opis = common.render_table_lines("trade", rows)
                    common.register_active_route_list(
                        self.lst_trade,
                        opis,
                        numerate=False,
                        offset=1,
                        schema_id="trade",
                        rows=rows,
                    )
                    common.wypelnij_liste(
                        self.lst_trade,
                        opis,
                        numerate=False,
                        show_copied_suffix=False,
                    )
                else:
                    opis = [f"{row.get('from_system', '')} -> {row.get('to_system', '')}" for row in rows]
                    common.register_active_route_list(self.lst_trade, opis)
                    common.wypelnij_liste(self.lst_trade, opis)
                common.handle_route_ready_autoclipboard(self, tr, status_target="trade")
                common.emit_status(
                    "OK",
                    "TRADE_FOUND",
                    text=f"Znaleziono {len(rows)} propozycji.",
                    source="spansh.trade",
                    ui_target="trade",
                )
            else:
                common.emit_status(
                    "ERROR",
                    "TRADE_NO_RESULTS",
                    source="spansh.trade",
                    ui_target="trade",
                )

        except Exception as e:
            common.emit_status(
                "ERROR",
                "TRADE_ERROR",
                text=f"Błąd: {e}",
                source="spansh.trade",
                ui_target="trade",
            )

