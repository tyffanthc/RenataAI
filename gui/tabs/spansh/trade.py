import tkinter as tk
from tkinter import ttk
import threading
import config
from logic import trade
from logic import utils
from logic.spansh_client import client as spansh_client
from gui import common
from gui import strings as ui
from gui import ui_layout as layout
from gui.common_autocomplete import AutocompleteController
from app.route_manager import route_manager
from app.state import app_state


class TradeTab(ttk.Frame):
    """
    ZakĹ‚adka: Trade Planner (Spansh)
    """

    def __init__(self, parent, root_window):
        super().__init__(parent)
        self.root = root_window
        self.pack(fill="both", expand=1)

        # Referencja do globalnego AppState (nie tworzymy nowej instancji)
        self.app_state = app_state

        # System / stacja startowa â€“ inicjalnie puste,
        # uzupeĹ‚niane z app_state w refresh_from_app_state().
        self.var_start_system = tk.StringVar()
        self.var_start_station = tk.StringVar()
        self._station_cache = {}
        self._recent_stations = []
        self._recent_limit = 25
        self._station_autocomplete_by_system = bool(
            config.get("features.trade.station_autocomplete_by_system", True)
        )
        self._station_lookup_online = bool(
            config.get("features.trade.station_lookup_online", False)
        )

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

        # D3c â€“ pierwsze uzupeĹ‚nienie pĂłl z app_state
        self.refresh_from_app_state()
        self.bind("<Visibility>", self._on_visibility)

    def _on_visibility(self, _event):
        self.refresh_from_app_state()

    def _build_ui(self):
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True, padx=8, pady=8)

        f_form = ttk.Frame(fr)
        f_form.pack(fill="x", pady=4)
        layout.configure_form_grid(f_form)

        self.e_system = layout.add_labeled_entry(
            f_form,
            0,
            ui.LABEL_SYSTEM,
            self.var_start_system,
            entry_width=layout.ENTRY_W_LONG,
        )
        self.e_station = layout.add_labeled_entry(
            f_form,
            1,
            ui.LABEL_STATION,
            self.var_start_station,
            entry_width=layout.ENTRY_W_LONG,
        )

        # Autocomplete dla systemu
        self.ac_source = AutocompleteController(
            self.root,
            self.e_system,
            suggest_func=self._suggest_system,
        )

        # Autocomplete dla stacji (D3b ??" na podstawie wybranego systemu)
        self.ac_station = AutocompleteController(
            self.root,
            self.e_station,
            min_chars=2,
            suggest_func=self._suggest_station,
        )

        f_detect = ttk.Frame(fr)
        f_detect.pack(fill="x", pady=(0, 6))
        self.lbl_detected = ttk.Label(f_detect, text="")
        self.lbl_detected.pack(side="left", padx=(10, 0))

        layout.add_labeled_pair(
            f_form,
            2,
            ui.LABEL_CAPITAL,
            self.var_capital,
            ui.LABEL_MAX_HOP,
            self.var_max_hop,
            left_entry_width=12,
        )
        layout.add_labeled_pair(
            f_form,
            3,
            ui.LABEL_CARGO,
            self.var_cargo,
            ui.LABEL_MAX_HOPS,
            self.var_max_hops,
        )
        _, max_age_entry = layout.add_labeled_pair(
            f_form,
            4,
            ui.LABEL_MAX_DISTANCE,
            self.var_max_dta,
            ui.LABEL_MAX_AGE,
            self.var_max_age,
        )
        self.e_max_age = max_age_entry

        # --- Flagowe checkboxy -------------------------------------------------
        f_flags1 = ttk.Frame(fr)
        f_flags1.pack(fill="x", pady=4)

        ttk.Checkbutton(
            f_flags1,
            text=ui.FLAG_LARGE_PAD,
            variable=self.var_large_pad,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags1,
            text=ui.FLAG_PLANETARY,
            variable=self.var_planetary,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags1,
            text=ui.FLAG_PLAYER_OWNED,
            variable=self.var_player_owned,
        ).pack(side="left", padx=5)

        f_flags2 = ttk.Frame(fr)
        f_flags2.pack(fill="x", pady=4)

        ttk.Checkbutton(
            f_flags2,
            text=ui.FLAG_RESTRICTED,
            variable=self.var_restricted,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text=ui.FLAG_PROHIBITED,
            variable=self.var_prohibited,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text=ui.FLAG_AVOID_LOOPS,
            variable=self.var_avoid_loops,
        ).pack(side="left", padx=5)
        ttk.Checkbutton(
            f_flags2,
            text=ui.FLAG_ALLOW_PERMITS,
            variable=self.var_allow_permits,
        ).pack(side="left", padx=5)

        # --- Przyciski / status / lista ---------------------------------------
        bf = ttk.Frame(fr)
        bf.pack(pady=6)

        ttk.Button(
            bf,
            text=ui.BUTTON_CALCULATE_TRADE,
            command=self.run_trade,
        ).pack(side="left", padx=5)

        ttk.Button(bf, text=ui.BUTTON_CLEAR, command=self.clear).pack(side="left", padx=5)

        self.lbl_status = ttk.Label(self, text="Gotowy", font=("Arial", 10, "bold"))
        self.lbl_status.pack(pady=(4, 2))

        self.lst_trade = common.stworz_liste_trasy(self, title=ui.LIST_TITLE_TRADE)

    def refresh_from_app_state(self):
        """D3c: uzupeĹ‚nia pola System/Stacja na podstawie AppState.

        UĹĽywamy TEGO SAMEGO app_state, co navigation_events.
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
            self._remember_station(sysname, staname)

        print(f"[TRADE] refresh_from_app_state: {sysname!r} / {staname!r}")
        self._set_detected_label(sysname, staname if is_docked else "")

    # ------------------------------------------------------------------ logika GUI

    def _suggest_station(self, tekst: str):
        """Funkcja podpowiedzi stacji dla AutocompleteController.

        Bazuje najpierw na aktualnym systemie z pola,
        a je‘>li jest puste f?" na app_state.current_system.
        """
        system = (self.var_start_system.get() or "").strip()
        if not system:
            system = (getattr(self.app_state, "current_system", "") or "").strip()

        # Je‘>li kto‘> ma w polu systemu format "System / Stacja" / "System, Stacja",
        # to do zapytania o stacje bierzemy tylko nazwŽt systemu (czŽt‘>ŽA przed separatorem).
        raw = system
        if "/" in raw:
            raw = raw.split("/", 1)[0].strip()
        elif "," in raw:
            raw = raw.split(",", 1)[0].strip()

        q = (tekst or "").strip()
        if not q:
            return []

        if not raw:
            return self._filter_stations(self._recent_stations, q)

        cached = []
        if self._station_autocomplete_by_system:
            cached = self._get_cached_stations(raw)
            if cached:
                return self._filter_stations(cached, q)

        if not self._station_lookup_online:
            return []

        try:
            return spansh_client.stations_for_system(raw, q)
        except Exception as e:
            print(f"[Spansh] Station autocomplete exception ({raw!r}, {q!r}): {e}")
            return []

    def _suggest_system(self, tekst: str):
        """Funkcja podpowiedzi systemĂłw dla AutocompleteController."""
        q = (tekst or "").strip()
        if not q:
            return []

        try:
            return spansh_client.systems_suggest(q)
        except Exception as e:
            print(f"[Spansh] System autocomplete exception ({q!r}): {e}")
            return []

    def _normalize_key(self, value: str) -> str:
        return (value or "").strip().lower()

    def _remember_station(self, system: str, station: str) -> None:
        sys_value = (system or "").strip()
        sta_value = (station or "").strip()
        if not sys_value or not sta_value:
            return
        key = self._normalize_key(sys_value)
        if key not in self._station_cache:
            self._station_cache[key] = set()
        self._station_cache[key].add(sta_value)

        recent = [s for s in self._recent_stations if self._normalize_key(s) != self._normalize_key(sta_value)]
        recent.insert(0, sta_value)
        self._recent_stations = recent[: self._recent_limit]

    def _get_cached_stations(self, system: str) -> list[str]:
        key = self._normalize_key(system)
        stations = list(self._station_cache.get(key, set()))
        stations.sort(key=lambda item: item.lower())
        return stations

    def _filter_stations(self, stations: list[str], query: str) -> list[str]:
        if not stations:
            return []
        q = query.strip().lower()
        if not q:
            return stations
        return [item for item in stations if q in item.lower()]

    def _set_detected_label(self, system: str, station: str) -> None:
        if not getattr(self, "lbl_detected", None):
            return
        sys_value = (system or "").strip()
        sta_value = (station or "").strip()
        if sys_value and sta_value:
            text = f"{ui.DETECTED_PREFIX}: {sys_value} / {sta_value}"
        elif sys_value:
            text = f"{ui.DETECTED_PREFIX}: {sys_value}"
        else:
            text = ""
        self.lbl_detected.config(text=text)

    def hide_suggestions(self):
        self.ac_source.hide()
        if hasattr(self, "ac_station"):
            self.ac_station.hide()

    def clear(self):
        self.lst_trade.delete(0, tk.END)
        self.lbl_status.config(text="Wyczyszczono", foreground="grey")

    def run_trade(self):
        """
        Startuje obliczenia w osobnym wÄ…tku.
        """
        self.clear()

        start_system = self.var_start_system.get().strip()
        start_station = self.var_start_station.get().strip()

        # Fallback do aktualnej lokalizacji z app_state, jeĹ›li pola sÄ… puste
        if not start_system:
            start_system = (getattr(self.app_state, "current_system", "") or "").strip()
        if not start_station and bool(getattr(self.app_state, "is_docked", False)):
            start_station = (getattr(self.app_state, "current_station", "") or "").strip()

        if start_system and start_station:
            self._remember_station(start_system, start_station)

        # Ostateczny fallback do config.STATE (zgodnoĹ›Ä‡ wsteczna)

        if not start_system:
            common.emit_status(
                "ERROR",
                "TRADE_INPUT_MISSING",
                source="spansh.trade",
                ui_target="trade",
            )
            return

        # D3b: dwa tryby wejĹ›cia:
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
        WÄ…tek roboczy: wywoĹ‚uje logikÄ™ trade.oblicz_trade i wypeĹ‚nia listÄ™.
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
                text=f"BĹ‚Ä…d: {e}",
                source="spansh.trade",
                ui_target="trade",
            )






