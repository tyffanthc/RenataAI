import tkinter as tk
from tkinter import ttk
import config


class PulpitTab(ttk.Frame):
    """
    ZakĹ‚adka 'Pulpit':
    - mini status (system, ciaĹ‚a)
    - log tekstowy
    - przycisk do generowania danych naukowych (Exobiology + Cartography)
    """

    def __init__(
        self,
        parent,
        *,
        on_generate_science_excel=None,
        on_generate_modules_data=None,
        on_generate_exploration_summary=None,
        on_generate_cash_in_assistant=None,
        on_skip_cash_in_assistant=None,
        app_state=None,
        route_manager=None,
    ):
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # callback do generowania Excela
        self._on_generate_science_excel = on_generate_science_excel
        self._on_generate_modules_data = on_generate_modules_data
        self._on_generate_exploration_summary = on_generate_exploration_summary
        self._on_generate_cash_in_assistant = on_generate_cash_in_assistant
        self._on_skip_cash_in_assistant = on_skip_cash_in_assistant
        self._app_state = app_state
        self._route_manager = route_manager
        self._current_exploration_summary_payload: dict = {}
        self._current_cash_in_signature: str = ""

        self._init_ui()
        self._update_status_from_state()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _init_ui(self):
        # GĹĂ“WNY DASHBOARD
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=5, pady=(8, 4))

        self.lbl_header_title = ttk.Label(
            header_frame,
            text="R.E.N.A.T.A. SYSTEM ONLINE",
            font=("Eurostile", 14, "bold"),
        )
        self.lbl_header_title.pack(anchor="w", pady=(0, 2))

        self.lbl_header_system = ttk.Label(
            header_frame,
            text="Obecny system: [Czekam na dane...]",
            font=("Eurostile", 10),
        )
        self.lbl_header_system.pack(anchor="w")

        self.lbl_header_status = ttk.Label(
            header_frame,
            text="Status: [W spoczynku]",
            font=("Eurostile", 10),
        )
        self.lbl_header_status.pack(anchor="w", pady=(0, 4))

        # MINI STATUS (S2-GUI-03)
        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=5, pady=(5, 0))

        self.lbl_status_system = ttk.Label(status_frame, text="System: -")
        self.lbl_status_system.pack(side="left", padx=(0, 15))

        self.lbl_status_bodies = ttk.Label(status_frame, text="CiaĹ‚a: -/-")
        self.lbl_status_bodies.pack(side="left", padx=(0, 15))

        # Miejsce na info o trasie (opcjonalnie)
        self.lbl_status_route = ttk.Label(status_frame, text="Trasa: -")
        self.lbl_status_route.pack(side="left", padx=(0, 15))

        self.lbl_status_ship = ttk.Label(status_frame, text="Statek: -")
        self.lbl_status_ship.pack(side="left", padx=(0, 15))

        self.lbl_status_mass = ttk.Label(status_frame, text="Masa: - t")
        self.lbl_status_mass.pack(side="left", padx=(0, 15))

        self.lbl_status_cargo = ttk.Label(status_frame, text="Cargo: - t")
        self.lbl_status_cargo.pack(side="left", padx=(0, 15))

        self.lbl_status_fuel = ttk.Label(status_frame, text="Paliwo: -/- t")
        self.lbl_status_fuel.pack(side="left", padx=(0, 15))

        self.lbl_status_jr = ttk.Label(status_frame, text="JR: -")
        self.lbl_status_jr.pack(side="left", padx=(0, 15))

        # EXPLORATION SUMMARY (F4 baseline)
        summary_frame = ttk.LabelFrame(self, text="Exploration Summary")
        summary_frame.pack(fill="x", padx=5, pady=(2, 5))
        summary_frame.columnconfigure(0, weight=1)

        self.lbl_exploration_summary_title = ttk.Label(
            summary_frame,
            text="Brak podsumowania eksploracji.",
            font=("Eurostile", 10, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_exploration_summary_title.grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")

        self.lbl_exploration_summary_highlights = ttk.Label(
            summary_frame,
            text="Highlights: -",
            anchor="w",
            justify="left",
            wraplength=960,
        )
        self.lbl_exploration_summary_highlights.grid(row=1, column=0, padx=8, pady=2, sticky="w")

        self.lbl_exploration_summary_next = ttk.Label(
            summary_frame,
            text="Co dalej: -",
            anchor="w",
            justify="left",
            wraplength=960,
        )
        self.lbl_exploration_summary_next.grid(row=2, column=0, padx=8, pady=2, sticky="w")

        self.lbl_exploration_summary_cashin = ttk.Label(
            summary_frame,
            text="Cash-in: -",
            anchor="w",
            justify="left",
            wraplength=960,
        )
        self.lbl_exploration_summary_cashin.grid(row=3, column=0, padx=8, pady=(2, 6), sticky="w")

        # CASH-IN ASSISTANT (F4 baseline)
        cash_in_frame = ttk.LabelFrame(self, text="Cash-In Assistant")
        cash_in_frame.pack(fill="x", padx=5, pady=(0, 5))
        cash_in_frame.columnconfigure(0, weight=1)

        self.lbl_cash_in_title = ttk.Label(
            cash_in_frame,
            text="Brak aktywnej sugestii cash-in.",
            font=("Eurostile", 10, "bold"),
            anchor="w",
            justify="left",
        )
        self.lbl_cash_in_title.grid(row=0, column=0, padx=8, pady=(6, 2), sticky="w")

        self.lbl_cash_in_options = ttk.Label(
            cash_in_frame,
            text="Opcje: -",
            anchor="w",
            justify="left",
            wraplength=960,
        )
        self.lbl_cash_in_options.grid(row=1, column=0, padx=8, pady=2, sticky="w")

        self.lbl_cash_in_note = ttk.Label(
            cash_in_frame,
            text="Pomijam: -",
            anchor="w",
            justify="left",
            wraplength=960,
        )
        self.lbl_cash_in_note.grid(row=2, column=0, padx=8, pady=(2, 6), sticky="w")

        # PRZYCISKI / AKCJE
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(
            btn_frame,
            text="NarzÄ™dzia naukowe:",
            font=("Arial", 9, "bold")
        ).pack(side="left")

        btn_generate_science = ttk.Button(
            btn_frame,
            text="Generuj arkusze naukowe",
            command=self._on_click_generate_science,
        )
        btn_generate_science.pack(side="right")

        btn_generate_modules = ttk.Button(
            btn_frame,
            text="Generuj dane moduĹ‚Ăłw",
            command=self._on_click_generate_modules,
        )
        btn_generate_modules.pack(side="right", padx=(0, 8))
        if not config.get("modules_data_autogen_enabled", True):
            btn_generate_modules.state(["disabled"])

        btn_exploration_summary = ttk.Button(
            btn_frame,
            text="Podsumowanie eksploracji",
            command=self._on_click_exploration_summary,
        )
        btn_exploration_summary.pack(side="right", padx=(0, 8))

        btn_cash_in_assistant = ttk.Button(
            btn_frame,
            text="Asystent cash-in",
            command=self._on_click_cash_in_assistant,
        )
        btn_cash_in_assistant.pack(side="right", padx=(0, 8))

        btn_cash_in_skip = ttk.Button(
            btn_frame,
            text="Pomijam cash-in",
            command=self._on_click_cash_in_skip,
        )
        btn_cash_in_skip.pack(side="right", padx=(0, 8))

        # LOG
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        log_text_wrap = ttk.Frame(log_frame)
        log_text_wrap.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(log_text_wrap, orient="vertical", style="Vertical.TScrollbar")
        log_scroll.pack(side="right", fill="y")

        self.log_area = tk.Text(
            log_text_wrap,
            height=20,
            state="disabled",
            wrap="word",
            yscrollcommand=log_scroll.set,
            bg="#1f2833",
            fg="#ffffff",
            insertbackground="#ff7100",
            selectbackground="#ff7100",
            selectforeground="#0b0c10",
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.log_area.pack(side="left", fill="both", expand=True)
        log_scroll.configure(command=self.log_area.yview)

    # ------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------
    def _update_status_from_state(self):
        """
        Jednorazowy update statusu przy starcie na podstawie app_state / route_manager.
        Nie spina siÄ™ z eventami w czasie rzeczywistym (tym zajmuje siÄ™ EventHandler).
        """
        # System
        system = "-"
        live_ready = False
        if self._app_state is not None:
            try:
                system = getattr(self._app_state, "current_system", None) or "-"
                live_ready = bool(getattr(self._app_state, "has_live_system_event", False))
            except Exception:
                pass

        self.set_system_runtime_state(system, live_ready=live_ready)

        # CiaĹ‚a - na start mamy tylko ogĂłlny placeholder, bo licznik
        # FSS jest trzymany w event_handlerze
        self.lbl_status_bodies.config(text="CiaĹ‚a: -/-")

        # Trasa - status awareness/intent
        route_text = "-"
        if self._app_state is not None and hasattr(self._app_state, "get_route_awareness_snapshot"):
            try:
                snap = self._app_state.get_route_awareness_snapshot()
                mode = str(snap.get("route_mode") or "idle")
                target = str(snap.get("route_target") or "").strip()
                progress = int(snap.get("route_progress_percent") or 0)
                off_route = bool(snap.get("is_off_route"))
                if mode == "awareness":
                    if off_route:
                        route_text = f"off-route ({progress}%)"
                    elif target:
                        route_text = f"on-route {progress}% -> {target}"
                    else:
                        route_text = f"on-route {progress}%"
                elif mode == "intent":
                    route_text = f"intent-only -> {target or '-'}"
            except Exception:
                route_text = "-"
        elif self._route_manager is not None:
            try:
                if self._route_manager.route:
                    route_text = f"{len(self._route_manager.route)} punktow"
            except Exception:
                pass

        self.lbl_status_route.config(text=f"Trasa: {route_text}")

        # Statek / paliwo / cargo
        if self._app_state is not None and hasattr(self._app_state, "ship_state"):
            try:
                ship_state = self._app_state.ship_state
                payload = {
                    "ship_id": ship_state.ship_id,
                    "ship_type": ship_state.ship_type,
                    "unladen_mass_t": ship_state.unladen_mass_t,
                    "cargo_mass_t": ship_state.cargo_mass_t,
                    "fuel_main_t": ship_state.fuel_main_t,
                    "fuel_reservoir_t": ship_state.fuel_reservoir_t,
                }
                self.update_ship_state(payload)
            except Exception:
                pass

    def update_ship_state(self, data: dict) -> None:
        ship_type = data.get("ship_type") or "-"
        ship_id = data.get("ship_id")
        if ship_id is not None:
            ship_text = f"{ship_type} (#{ship_id})"
        else:
            ship_text = f"{ship_type}"
        self.lbl_status_ship.config(text=f"Statek: {ship_text}")

        unladen = data.get("unladen_mass_t")
        if unladen is None:
            self.lbl_status_mass.config(text="Masa: - t")
        else:
            self.lbl_status_mass.config(text=f"Masa: {unladen:.1f} t")

        cargo = data.get("cargo_mass_t")
        if cargo is None:
            self.lbl_status_cargo.config(text="Cargo: - t")
        else:
            self.lbl_status_cargo.config(text=f"Cargo: {cargo:.1f} t")

        fuel_main = data.get("fuel_main_t")
        fuel_res = data.get("fuel_reservoir_t")
        if fuel_main is None and fuel_res is None:
            self.lbl_status_fuel.config(text="Paliwo: -/- t")
        else:
            fm = "-" if fuel_main is None else f"{fuel_main:.2f}"
            fr = "-" if fuel_res is None else f"{fuel_res:.2f}"
            self.lbl_status_fuel.config(text=f"Paliwo: {fm}/{fr} t")

        if not config.get("ui_show_jump_range", True):
            self.lbl_status_jr.config(text="JR: -")
            return

        location = str(config.get("ui_jump_range_location", "overlay")).strip().lower()
        if location not in ("statusbar", "both"):
            self.lbl_status_jr.config(text="JR: -")
            return

        jr = data.get("jump_range_current_ly")
        if jr is None:
            self.lbl_status_jr.config(text="JR: -")
            return

        try:
            jr_val = float(jr)
        except Exception:
            self.lbl_status_jr.config(text="JR: -")
            return

        txt = f"JR: {jr_val:.2f} LY"
        if config.get("ui_jump_range_show_limit", True):
            limit = data.get("jump_range_limited_by")
            if limit in ("fuel", "mass"):
                txt += f" ({limit})"
        if config.get("ui_jump_range_debug_details", False):
            fuel_needed = data.get("jump_range_fuel_needed_t")
            if fuel_needed is not None:
                try:
                    txt += f" fuel:{float(fuel_needed):.2f}t"
                except Exception:
                    pass
        self.lbl_status_jr.config(text=txt)

    def set_system_runtime_state(self, system_name: str, live_ready: bool) -> None:
        system = (system_name or "").strip()
        if system in ("", "-", "Unknown", "Nieznany"):
            system = "-"

        if live_ready and system != "-":
            self.lbl_status_system.config(text=f"System: {system}")
            self.lbl_header_system.config(text=f"Obecny system: {system}")
        else:
            self.lbl_status_system.config(text="System: [Czekam na dane...]")
            self.lbl_header_system.config(text="Obecny system: [Czekam na dane...]")

    # ------------------------------------------------------------
    # AKCJE
    # ------------------------------------------------------------
    def _on_click_generate_science(self):
        """
        Handler przycisku 'Generuj arkusze naukowe'.
        """
        if self._on_generate_science_excel is not None:
            try:
                self._on_generate_science_excel()
            except Exception as e:
                self.log(f"[SCIENCE_DATA] BĹ‚Ä…d przy uruchamianiu generatora: {e}")
        else:
            self.log("[SCIENCE_DATA] Brak podpiÄ™tego callbacku on_generate_science_excel.")

    def _on_click_generate_modules(self):
        if self._on_generate_modules_data is not None:
            try:
                self._on_generate_modules_data()
            except Exception as e:
                self.log(f"[MODULES_DATA] BĹ‚Ä…d przy uruchamianiu generatora: {e}")
        else:
            self.log("[MODULES_DATA] Brak podpiÄ™tego callbacku on_generate_modules_data.")

    def _on_click_exploration_summary(self):
        if self._on_generate_exploration_summary is not None:
            try:
                self._on_generate_exploration_summary()
            except Exception as e:
                self.log(f"[EXPLORATION_SUMMARY] Blad triggera podsumowania: {e}")
        else:
            self.log("[EXPLORATION_SUMMARY] Brak podpiętego callbacku on_generate_exploration_summary.")

    def _on_click_cash_in_assistant(self):
        if self._on_generate_cash_in_assistant is not None:
            try:
                self._on_generate_cash_in_assistant()
            except Exception as e:
                self.log(f"[CASH_IN] Blad triggera asystenta cash-in: {e}")
        else:
            self.log("[CASH_IN] Brak podpiętego callbacku on_generate_cash_in_assistant.")

    def _on_click_cash_in_skip(self):
        if self._on_skip_cash_in_assistant is not None:
            try:
                self._on_skip_cash_in_assistant()
                self.lbl_cash_in_note.config(text="Pomijam: aktywne dla biezacego kontekstu.")
            except Exception as e:
                self.log(f"[CASH_IN] Blad akcji Pomijam: {e}")
        else:
            self.log("[CASH_IN] Brak podpiętego callbacku on_skip_cash_in_assistant.")

    # ------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------
    def log(self, text: str):
        """
        Prosty logger tekstowy uĹĽywany przez RenataApp.show_status().
        """
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")


    def get_current_exploration_summary_payload(self) -> dict:
        return dict(self._current_exploration_summary_payload or {})

    def get_current_cash_in_signature(self) -> str:
        return str(self._current_cash_in_signature or "").strip()

    def update_exploration_summary(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._current_exploration_summary_payload = dict(payload)

        system = str(payload.get("system") or "-").strip() or "-"
        scanned = payload.get("scanned_bodies")
        total = payload.get("total_bodies")
        if scanned is not None and total is not None:
            title = f"System: {system} | FSS: {scanned}/{total}"
        else:
            title = f"System: {system}"

        highlights = payload.get("highlights") or []
        if isinstance(highlights, list) and highlights:
            highlights_text = " | ".join(str(item) for item in highlights[:5])
        else:
            highlights_text = "-"

        next_step = str(payload.get("next_step") or "-").strip() or "-"
        signal = str(payload.get("cash_in_signal") or "-").strip() or "-"
        sys_cash = payload.get("cash_in_system_estimated")
        ses_cash = payload.get("cash_in_session_estimated")

        def _fmt_cr(value):
            try:
                return f"{int(round(float(value))):,}".replace(",", " ")
            except Exception:
                return "-"

        cash_text = (
            f"Cash-in ({signal}): system ~{_fmt_cr(sys_cash)} Cr | sesja ~{_fmt_cr(ses_cash)} Cr"
        )

        self.lbl_exploration_summary_title.config(text=title)
        self.lbl_exploration_summary_highlights.config(text=f"Highlights: {highlights_text}")
        self.lbl_exploration_summary_next.config(text=f"Co dalej: {next_step}")
        self.lbl_exploration_summary_cashin.config(text=cash_text)

    def update_cash_in_assistant(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return

        self._current_cash_in_signature = str(payload.get("signature") or "").strip()
        system = str(payload.get("system") or "-").strip() or "-"
        signal = str(payload.get("signal") or "-").strip() or "-"
        session_est = payload.get("session_value_estimated")
        system_est = payload.get("system_value_estimated")

        def _fmt_cr(value):
            try:
                return f"{int(round(float(value))):,}".replace(",", " ")
            except Exception:
                return "-"

        title = (
            f"Cash-in ({signal}) | System: {system} | "
            f"system ~{_fmt_cr(system_est)} Cr | sesja ~{_fmt_cr(session_est)} Cr"
        )
        self.lbl_cash_in_title.config(text=title)

        options = payload.get("options") or []
        option_lines: list[str] = []
        if isinstance(options, list):
            for idx, option in enumerate(options[:3], start=1):
                if not isinstance(option, dict):
                    continue
                label = str(option.get("label") or f"Opcja {idx}").strip() or f"Opcja {idx}"
                eta = option.get("eta_minutes")
                value = option.get("estimated_value")
                risk = str(option.get("risk_label") or "-")
                trust = str(option.get("trust_label") or "-")
                line = (
                    f"{idx}) {label} | ~{_fmt_cr(value)} Cr | ETA {eta if eta is not None else '-'} min "
                    f"| ryzyko {risk} | trust {trust}"
                )
                option_lines.append(line)

        if option_lines:
            self.lbl_cash_in_options.config(text="Opcje: " + " || ".join(option_lines))
        else:
            self.lbl_cash_in_options.config(text="Opcje: -")

        note = str(payload.get("note") or "Pomijam: dostepne").strip()
        self.lbl_cash_in_note.config(text=f"Pomijam: {note}")

