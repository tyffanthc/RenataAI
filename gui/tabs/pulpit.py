import tkinter as tk
from tkinter import ttk, scrolledtext


class PulpitTab(ttk.Frame):
    """
    Zakładka 'Pulpit':
    - mini status (system, ciała)
    - log tekstowy
    - przycisk do generowania danych naukowych (Exobiology + Cartography)
    """

    def __init__(self, parent, *, on_generate_science_excel=None, app_state=None, route_manager=None):
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # callback do generowania Excela
        self._on_generate_science_excel = on_generate_science_excel
        self._app_state = app_state
        self._route_manager = route_manager

        self._init_ui()
        self._update_status_from_state()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _init_ui(self):
        # GŁÓWNY DASHBOARD
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

        self.lbl_status_bodies = ttk.Label(status_frame, text="Ciała: -/-")
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

        # PRZYCISKI / AKCJE
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5, pady=5)

        ttk.Label(
            btn_frame,
            text="Narzędzia naukowe:",
            font=("Arial", 9, "bold")
        ).pack(side="left")

        btn_generate = ttk.Button(
            btn_frame,
            text="Generuj arkusze naukowe",
            command=self._on_click_generate_science,
        )
        btn_generate.pack(side="right")

        # LOG
        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            state="disabled",
            wrap="word",
        )
        self.log_area.pack(fill="both", expand=True)

    # ------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------
    def _update_status_from_state(self):
        """
        Jednorazowy update statusu przy starcie na podstawie app_state / route_manager.
        Nie spina się z eventami w czasie rzeczywistym (tym zajmuje się EventHandler).
        """
        # System
        system = "-"
        if self._app_state is not None:
            try:
                system = getattr(self._app_state, "current_system", None) or "-"
            except Exception:
                pass

        self.lbl_status_system.config(text=f"System: {system}")

        # Uaktualnij też nagłówek dashboardu
        if hasattr(self, "lbl_header_system"):
            if system == "-" or not system:
                header_txt = "Obecny system: [Czekam na dane...]"
            else:
                header_txt = f"Obecny system: {system}"
            self.lbl_header_system.config(text=header_txt)

        # Ciała - na start mamy tylko ogólny placeholder, bo licznik
        # FSS jest trzymany w event_handlerze
        self.lbl_status_bodies.config(text="Ciała: -/-")

        # Trasa - bardzo ogólna informacja
        route_text = "-"
        if self._route_manager is not None:
            try:
                if self._route_manager.route:
                    route_text = f"{len(self._route_manager.route)} punktów"
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
                self.log(f"[SCIENCE_DATA] Błąd przy uruchamianiu generatora: {e}")
        else:
            self.log("[SCIENCE_DATA] Brak podpiętego callbacku on_generate_science_excel.")

    # ------------------------------------------------------------
    # LOG
    # ------------------------------------------------------------
    def log(self, text: str):
        """
        Prosty logger tekstowy używany przez RenataApp.show_status().
        """
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, text + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")
