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
