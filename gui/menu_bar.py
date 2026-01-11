# gui/menu_bar.py

import tkinter as tk


class RenataMenuBar(tk.Menu):
    """
    Główne menu aplikacji R.E.N.A.T.A.

    Oczekiwane callbacki (przekazywane z gui/app.py):

    - on_quit() -> zamknięcie aplikacji
    - on_open_settings() -> otwarcie okna Konfiguracji (SettingsWindow)
    - on_show_about() -> dialog "O programie"
    - on_switch_tab(tab_key: str) -> przełączenie zakładki w głównym Notebooku
    - on_toggle_always_on_top(is_on: bool) -> włączenie/wyłączenie trybu topmost
    - on_open_link(target: str) -> otwarcie linku (inara/spansh/coriolis/fuelrats)
    """

    def __init__(
        self,
        master,
        *,
        on_quit,
        on_open_settings,
        on_show_about,
        on_switch_tab,
        on_toggle_always_on_top,
        on_open_link,
        tab_labels,
    ):
        super().__init__(master)

        self.on_quit = on_quit
        self.on_open_settings = on_open_settings
        self.on_show_about = on_show_about
        self.on_switch_tab = on_switch_tab
        self.on_toggle_always_on_top = on_toggle_always_on_top
        self.on_open_link = on_open_link
        self.tab_labels = tab_labels or {}

        # stan opcji "Zawsze na wierzchu"
        self._var_always_on_top = tk.BooleanVar(value=False)

        self._build_menu()

    # ------------------------------------------------------------------ #
    #   Budowa menu
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> None:
        # MENU: Plik
        file_menu = tk.Menu(self, tearoff=False)
        file_menu.add_command(
            label="Konfiguracja…",
            command=self._safe_callback(self.on_open_settings),
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Wyjście",
            command=self._safe_callback(self.on_quit),
        )
        self.add_cascade(label="Plik", menu=file_menu)

        # MENU: Widok
        view_menu = tk.Menu(self, tearoff=False)
        view_menu.add_checkbutton(
            label="Zawsze na wierzchu (Overlay Mode)",
            variable=self._var_always_on_top,
            command=self._safe_callback(self._on_view_always_on_top_toggled),
        )
        self.add_cascade(label="Widok", menu=view_menu)

        # MENU: Nawigacja (przełączanie zakładek)
        nav_menu = tk.Menu(self, tearoff=False)
        for key, label in self.tab_labels.items():
            nav_menu.add_command(
                label=label,
                command=self._safe_callback(self.on_switch_tab, key),
            )
        self.add_cascade(label="Nawigacja", menu=nav_menu)

        # MENU: Baza wiedzy – linki
        kb_menu = tk.Menu(self, tearoff=False)
        kb_menu.add_command(
            label="Inara",
            command=self._safe_callback(self.on_open_link, "inara"),
        )
        kb_menu.add_command(
            label="Spansh",
            command=self._safe_callback(self.on_open_link, "spansh"),
        )
        kb_menu.add_command(
            label="Coriolis",
            command=self._safe_callback(self.on_open_link, "coriolis"),
        )
        kb_menu.add_command(
            label="Fuel Rats",
            command=self._safe_callback(self.on_open_link, "fuelrats"),
        )
        self.add_cascade(label="Baza wiedzy", menu=kb_menu)

        # MENU: Pomoc
        help_menu = tk.Menu(self, tearoff=False)
        help_menu.add_command(
            label="O programie",
            command=self._safe_callback(self.on_show_about),
        )
        self.add_cascade(label="Pomoc", menu=help_menu)

    # ------------------------------------------------------------------ #
    #   Handlery
    # ------------------------------------------------------------------ #

    def _on_view_always_on_top_toggled(self) -> None:
        """Przekazuje zmianę stanu 'zawsze na wierzchu' do Gui."""
        value = bool(self._var_always_on_top.get())
        if self.on_toggle_always_on_top is not None:
            try:
                self.on_toggle_always_on_top(value)
            except Exception:
                # tutaj nie panikujemy – log może ogarnąć backend
                pass

    # ------------------------------------------------------------------ #
    #   Helper: bezpieczne owijanie callbacków
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_callback(func, *args, **kwargs):
        def wrapper():
            try:
                if func is not None:
                    func(*args, **kwargs)
            except Exception:
                # podczas dev możemy chcieć to zobaczyć w konsoli:
                import traceback
                traceback.print_exc()
        return wrapper
