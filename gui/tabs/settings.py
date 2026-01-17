# gui/tabs/settings.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable, Dict, Any
import os
import config


class SettingsTab(ttk.Frame):
    """
    Okno Konfiguracji w stylu kokpitu, podzielone na zakładki:
    - Ogólne
    - Asystenci
    - Eksploracja
    - Handel
    - Inżynier
    """

    def __init__(
        self,
        parent: tk.Widget,
        controller: Optional[object] = None,
        *,
        get_config: Optional[Callable[[], Dict[str, Any]]] = None,
        save_config: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        :param parent: kontener (w naszym przypadku okno SettingsWindow)
        :param controller: główny obiekt aplikacji (app) z metodą is_science_data_available()
        :param get_config: callback zwracający dict z konfiguracją
        :param save_config: callback przyjmujący dict do zapisania
        """
        super().__init__(parent)

        self.controller = controller
        self._get_config = get_config
        self._save_config = save_config
        self._jackpot_dialog = None

        self._create_vars()
        self._build_ui()
        self._load_initial_values()

    # ------------------------------------------------------------------ #
    # Zmienne stanu (tk.Variable) – czysto wizualne
    # ------------------------------------------------------------------ #

    def _create_vars(self) -> None:
        # język / wygląd
        self.var_language = tk.StringVar(value="pl")
        self.var_theme = tk.StringVar(value="dark")  # backend ma "dark" jako domyślne
        self.var_use_system_theme = tk.BooleanVar(value=True)

        # logi
        self.var_log_path = tk.StringVar(value="")
        self.var_auto_detect_logs = tk.BooleanVar(value=True)

        # SPANSH – nadal frontend only
        self.var_spansh_timeout = tk.StringVar(value="20")
        self.var_spansh_retries = tk.StringVar(value="3")

        # GŁOS / dźwięk – mapujemy to na voice_enabled
        self.var_enable_sounds = tk.BooleanVar(value=True)
        self.var_confirm_exit = tk.BooleanVar(value=True)

        # --- Asystenci / alerty – te mapujemy na klucze JSON --- #
        self.var_read_landing_pad = tk.BooleanVar(value=True)          # landing_pad_speech
        self.var_auto_clipboard = tk.BooleanVar(value=True)            # auto_clipboard

        self.var_route_progress_messages = tk.BooleanVar(value=True)   # route_progress_speech
        self.var_low_fuel_warning = tk.BooleanVar(value=True)          # fuel_warning
        self.var_low_fuel_threshold = tk.StringVar(value="15")         # fuel_warning_threshold_pct

        self.var_fss_assistant = tk.BooleanVar(value=True)             # fss_assistant
        self.var_high_value_planet_alerts = tk.BooleanVar(value=True)  # high_value_planets
        self.var_dss_bio3_assistant = tk.BooleanVar(value=True)        # bio_assistant

        self.var_trade_jackpot_alerts = tk.BooleanVar(value=True)      # trade_jackpot_speech
        self.var_smuggler_alert = tk.BooleanVar(value=False)           # smuggler_alert
        self.var_mining_accountant = tk.BooleanVar(value=False)        # tylko frontend na razie

        # Progi Maklera (dict)
        self.jackpot_thresholds: Dict[str, int] = config.DEFAULT_JACKPOT_THRESHOLDS.copy()

        self.var_bounty_hunter = tk.BooleanVar(value=False)            # frontend
        self.var_preflight_limpets = tk.BooleanVar(value=True)         # frontend
        self.var_high_g_warning = tk.BooleanVar(value=True)            # high_g_warning

        self.var_fdff_notifications = tk.BooleanVar(value=True)        # frontend (na razie)

        # Czytanie systemu po skoku (Exit Summary / info o systemie) – frontend / future
        self.var_read_system_after_jump = tk.BooleanVar(value=True)

        # Debug / advanced
        self.var_debug_autocomplete = tk.BooleanVar(value=False)
        self.var_debug_cache = tk.BooleanVar(value=False)
        self.var_debug_dedup = tk.BooleanVar(value=False)
        self.var_debug_ship_state = tk.BooleanVar(value=False)

        # Status naukowy – StringVar do sekcji Eksploracja
        self.science_status_var = tk.StringVar(value="")

    # ------------------------------------------------------------------ #
    # UI – zakładki
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        # Notebook z zakładkami
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        # Zakładki
        self._tab_general = ttk.Frame(self.nb)
        self._tab_assistants = ttk.Frame(self.nb)
        self._tab_exploration = ttk.Frame(self.nb)
        self._tab_trade = ttk.Frame(self.nb)
        self._tab_engineer = ttk.Frame(self.nb)
        self._tab_advanced = ttk.Frame(self.nb)

        self.nb.add(self._tab_general, text="Ogólne")
        self.nb.add(self._tab_assistants, text="Asystenci")
        self.nb.add(self._tab_exploration, text="Eksploracja")
        self.nb.add(self._tab_trade, text="Handel")
        self.nb.add(self._tab_engineer, text="Inżynier")
        self.nb.add(self._tab_advanced, text="Zaawansowane")

        # Budowa zawartości zakładek
        self._build_tab_general()
        self._build_tab_assistants()
        self._build_tab_exploration()
        self._build_tab_trade()
        self._build_tab_engineer()
        self._build_tab_advanced()
        self.nb.select(self._tab_general)

    def _add_save_bar(self, parent, row: int) -> None:
        btn_bar = ttk.Frame(parent)
        btn_bar.grid(row=row, column=0, padx=12, pady=(0, 12), sticky="e")
        btn_bar.columnconfigure(0, weight=1)
        btn_bar.columnconfigure(1, weight=0)

        btn_reset = ttk.Button(btn_bar, text="Przywróć domyślne", command=self._on_reset)
        btn_reset.grid(row=0, column=0, padx=6, pady=4, sticky="e")

        btn_save = ttk.Button(btn_bar, text="Zapisz ustawienia", command=self._on_save)
        btn_save.grid(row=0, column=1, padx=6, pady=4, sticky="e")

    # ------------------------------------------------------------------ #
    #   Zakładka: OGÓLNE
    # ------------------------------------------------------------------ #

    def _build_tab_general(self) -> None:
        parent = self._tab_general
        parent.columnconfigure(0, weight=1)

        # Sekcja: INTERFEJS
        lf_general = ttk.LabelFrame(parent, text=" Interfejs ")
        lf_general.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="nsew")

        for col in range(3):
            lf_general.columnconfigure(col, weight=1)

        ttk.Label(lf_general, text="Język interfejsu:").grid(
            row=0, column=0, padx=8, pady=6, sticky="w"
        )
        lang_combo = ttk.Combobox(
            lf_general,
            textvariable=self.var_language,
            values=("pl", "en"),
            state="readonly",
            width=10,
        )
        lang_combo.grid(row=0, column=1, padx=8, pady=6, sticky="w")

        ttk.Checkbutton(
            lf_general,
            text="Włącz dźwięki / komunikaty głosowe",
            variable=self.var_enable_sounds,
        ).grid(row=1, column=0, columnspan=3, padx=8, pady=(0, 6), sticky="w")

        ttk.Label(
            lf_general,
            text="Ustawienia języka i motywu interfejsu.",
            foreground="#888888",
        ).grid(row=2, column=0, columnspan=3, padx=8, pady=(0, 8), sticky="w")

        # Sekcja: ZAMKNIĘCIE / ZACHOWANIE
        lf_behavior = ttk.LabelFrame(parent, text=" Zamknięcie / zachowanie aplikacji ")
        lf_behavior.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        lf_behavior.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            lf_behavior,
            text="Pytaj o potwierdzenie przed zamknięciem Renaty",
            variable=self.var_confirm_exit,
        ).grid(row=0, column=0, padx=8, pady=(6, 6), sticky="w")

        ttk.Label(
            lf_behavior,
            text="Ułatwia uniknięcie przypadkowego zamknięcia.",
            foreground="#888888",
        ).grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")

        # Sekcja: ŚCIEŻKI / LOGI
        lf_paths = ttk.LabelFrame(parent, text=" Elite Dangerous – logi ")
        lf_paths.grid(row=2, column=0, padx=12, pady=6, sticky="nsew")

        for col in range(3):
            lf_paths.columnconfigure(col, weight=1)

        chk_auto_logs = ttk.Checkbutton(
            lf_paths,
            text="Automatycznie wykryj folder logów Elite Dangerous (wkrótce)",
            variable=self.var_auto_detect_logs,
        )
        chk_auto_logs.state(["disabled"])
        chk_auto_logs.grid(row=0, column=0, columnspan=3, padx=8, pady=(6, 4), sticky="w")

        ttk.Label(lf_paths, text="Folder logów:").grid(
            row=1, column=0, padx=8, pady=6, sticky="w"
        )
        entry_logs = ttk.Entry(lf_paths, textvariable=self.var_log_path)
        entry_logs.grid(row=1, column=1, padx=8, pady=6, sticky="ew")

        btn_browse = ttk.Button(
            lf_paths,
            text="Przeglądaj…",
            command=self._on_browse_logs,
        )
        btn_browse.grid(row=1, column=2, padx=8, pady=6, sticky="e")

        ttk.Label(
            lf_paths,
            text="Ścieżka do Journal logs używana przez backend.",
            foreground="#888888",
        ).grid(row=2, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="w")

        ttk.Label(
            lf_paths,
            text="Renata spróbuje wykryć folder journali automatycznie (w przyszłości).",
            foreground="#888888",
        ).grid(row=3, column=0, columnspan=3, padx=8, pady=(0, 8), sticky="w")

        # Sekcja: WYGLĄD
        lf_appearance = ttk.LabelFrame(parent, text=" Wygląd interfejsu ")
        lf_appearance.grid(row=3, column=0, padx=12, pady=6, sticky="nsew")

        for col in range(3):
            lf_appearance.columnconfigure(col, weight=1)

        chk_use_system_theme = ttk.Checkbutton(
            lf_appearance,
            text="Użyj systemowego motywu okien",
            variable=self.var_use_system_theme,
            command=self._on_use_system_theme,
        )
        chk_use_system_theme.grid(row=0, column=0, columnspan=3, padx=8, pady=(6, 4), sticky="w")

        ttk.Label(lf_appearance, text="Motyw Renaty (kokpit):").grid(
            row=1, column=0, padx=8, pady=6, sticky="w"
        )
        theme_combo = ttk.Combobox(
            lf_appearance,
            textvariable=self.var_theme,
            values=(
                "dark",        # domyślny – spójny z backendem
                "ed_orange",
                "ed_blue",
                "dark_minimal",
            ),
            state="readonly",
            width=18,
        )
        theme_combo.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        self._theme_combo = theme_combo

        ttk.Label(
            lf_appearance,
            text="Zmiana motywu może wymagać ponownego uruchomienia Renaty.",
            foreground="#888888",
        ).grid(row=2, column=0, columnspan=3, padx=8, pady=(0, 8), sticky="w")

        self._on_use_system_theme()

        # Sekcja: SPANSH / SIEĆ
        lf_spansh = ttk.LabelFrame(parent, text=" SPANSH / Połączenie ")
        lf_spansh.grid(row=4, column=0, padx=12, pady=(6, 12), sticky="nsew")

        for col in range(4):
            lf_spansh.columnconfigure(col, weight=1)

        ttk.Label(lf_spansh, text="Timeout żądania (s):").grid(
            row=0, column=0, padx=8, pady=6, sticky="w"
        )
        entry_timeout = ttk.Entry(lf_spansh, textvariable=self.var_spansh_timeout, width=6)
        entry_timeout.grid(row=0, column=1, padx=8, pady=6, sticky="w")

        ttk.Label(lf_spansh, text="Liczba ponowień:").grid(
            row=0, column=2, padx=8, pady=6, sticky="w"
        )
        entry_retries = ttk.Entry(lf_spansh, textvariable=self.var_spansh_retries, width=6)
        entry_retries.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        ttk.Label(
            lf_spansh,
            text="Dotyczy zapytań do SPANSH oraz pollingu 202.",
            foreground="#888888",
        ).grid(row=1, column=0, columnspan=4, padx=8, pady=(0, 8), sticky="w")

        # Dół zakładki – przyciski
        self._add_save_bar(parent, row=5)

    # ------------------------------------------------------------------ #
    #   Zakładka: ASYSTENCI
    # ------------------------------------------------------------------ #

    def _build_tab_assistants(self) -> None:
        parent = self._tab_assistants
        parent.columnconfigure(0, weight=1)

        # Komunikaty dokowania i stacji
        lf_docking = ttk.LabelFrame(parent, text=" Komunikaty dokowania i stacji ")
        lf_docking.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="nsew")
        lf_docking.columnconfigure(0, weight=1)
        lf_docking.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            lf_docking,
            text="Czytaj numer lądowiska",
            variable=self.var_read_landing_pad,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_docking,
            text="Auto-schowek",
            variable=self.var_auto_clipboard,
        ).grid(row=0, column=1, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_docking,
            text="Smuggler alert – nielegalny towar",
            variable=self.var_smuggler_alert,
        ).grid(row=1, column=0, padx=8, pady=4, sticky="w")

        ttk.Label(
            lf_docking,
            text="Ułatwia dokowanie i szybkie kopiowanie celów.",
            foreground="#888888",
        ).grid(row=2, column=0, columnspan=2, padx=8, pady=(0, 6), sticky="w")

        # Nawigacja i trasy
        lf_navigation = ttk.LabelFrame(parent, text=" Nawigacja i trasy ")
        lf_navigation.grid(row=1, column=0, padx=12, pady=6, sticky="nsew")
        lf_navigation.columnconfigure(0, weight=1)
        lf_navigation.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            lf_navigation,
            text="Komunikaty o postępie trasy",
            variable=self.var_route_progress_messages,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Label(
            lf_navigation,
            text="Komunikaty o trasie i postępie lotu.",
            foreground="#888888",
        ).grid(row=1, column=0, columnspan=2, padx=8, pady=(0, 6), sticky="w")

        # Paliwo i bezpieczeństwo
        lf_fuel_safety = ttk.LabelFrame(parent, text=" Paliwo i bezpieczeństwo ")
        lf_fuel_safety.grid(row=2, column=0, padx=12, pady=(6, 12), sticky="nsew")
        lf_fuel_safety.columnconfigure(0, weight=1)
        lf_fuel_safety.columnconfigure(1, weight=1)
        lf_fuel_safety.columnconfigure(2, weight=1)
        lf_fuel_safety.columnconfigure(3, weight=1)

        ttk.Checkbutton(
            lf_fuel_safety,
            text="Ostrzeżenie o niskim paliwie",
            variable=self.var_low_fuel_warning,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Label(lf_fuel_safety, text="Próg rezerwy:").grid(
            row=1, column=0, padx=8, pady=4, sticky="w"
        )
        combo_fuel_threshold = ttk.Combobox(
            lf_fuel_safety,
            textvariable=self.var_low_fuel_threshold,
            values=("15", "25", "50"),
            state="readonly",
            width=6,
        )
        combo_fuel_threshold.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        chk_preflight = ttk.Checkbutton(
            lf_fuel_safety,
            text="Pre-flight limpets (wkrótce)",
            variable=self.var_preflight_limpets,
        )
        chk_preflight.state(["disabled"])
        chk_preflight.grid(row=0, column=2, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_fuel_safety,
            text="High-G Warning",
            variable=self.var_high_g_warning,
        ).grid(row=0, column=3, padx=8, pady=4, sticky="w")

        ttk.Label(
            lf_fuel_safety,
            text="Bezpieczeństwo lotu i ostrzeżenia krytyczne.",
            foreground="#888888",
        ).grid(row=2, column=0, columnspan=4, padx=8, pady=(0, 6), sticky="w")

        self._add_save_bar(parent, row=3)

    # ------------------------------------------------------------------ #
    #   Zakładka: EKSPLORACJA
    # ------------------------------------------------------------------ #

    def _build_tab_exploration(self) -> None:
        parent = self._tab_exploration
        parent.columnconfigure(0, weight=1)

        lf_exploration = ttk.LabelFrame(parent, text=" Eksploracja (FSS / DSS / biologia) ")
        lf_exploration.grid(row=0, column=0, padx=12, pady=(12, 12), sticky="nsew")

        lf_exploration.columnconfigure(0, weight=1)
        lf_exploration.columnconfigure(1, weight=1)
        lf_exploration.columnconfigure(2, weight=1)

        ttk.Checkbutton(
            lf_exploration,
            text="Asystent FSS (postęp skanowania %)",
            variable=self.var_fss_assistant,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_exploration,
            text="Alerty wysokowartościowych planet (ELW/WW/HMC)",
            variable=self.var_high_value_planet_alerts,
        ).grid(row=0, column=1, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_exploration,
            text="Asystent DSS (biologia 3+ sygnały)",
            variable=self.var_dss_bio3_assistant,
        ).grid(row=0, column=2, padx=8, pady=4, sticky="w")

        chk_fdff = ttk.Checkbutton(
            lf_exploration,
            text="First Discovery / Footfall – komunikaty (wkrótce)",
            variable=self.var_fdff_notifications,
        )
        chk_fdff.state(["disabled"])
        chk_fdff.grid(row=1, column=0, padx=8, pady=4, sticky="w")

        chk_read_sys = ttk.Checkbutton(
            lf_exploration,
            text="Czytaj informacje o systemie po każdym skoku (wkrótce)",
            variable=self.var_read_system_after_jump,
        )
        chk_read_sys.state(["disabled"])
        chk_read_sys.grid(row=1, column=1, padx=8, pady=4, sticky="w")

        # Opisy + status
        self.lbl_exploration_desc = ttk.Label(
            lf_exploration,
            text="Opcje eksploracyjne wymagają wygenerowania danych arkuszy naukowych.",
            wraplength=520,
            justify="left",
        )
        self.lbl_exploration_desc.grid(
            row=2, column=0, columnspan=3, padx=8, pady=(2, 2), sticky="w"
        )

        self.science_status_label = ttk.Label(
            lf_exploration,
            textvariable=self.science_status_var,
            wraplength=520,
            justify="left",
        )
        self.science_status_label.grid(
            row=3, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="w"
        )

        self.lbl_exploration_excel_missing = tk.Label(
            lf_exploration,
            text="",
            fg="red",
            anchor="w",
            justify="left",
        )
        self.lbl_exploration_excel_missing.grid(
            row=4, column=0, columnspan=3, padx=8, pady=(0, 4), sticky="w"
        )

        # Przycisk: Generuj arkusze naukowe
        self.btn_generate_science = ttk.Button(
            lf_exploration,
            text="Generuj arkusze naukowe",
            command=self._on_generate_science_excel,
        )
        self.btn_generate_science.grid(
            row=5, column=0, columnspan=3, padx=8, pady=(4, 6), sticky="w"
        )

        # Początkowy status danych naukowych (na podstawie app/controller)
        initial_loaded = False
        if self.controller and hasattr(self.controller, "is_science_data_available"):
            try:
                initial_loaded = bool(self.controller.is_science_data_available())
            except Exception:
                initial_loaded = False
        self.update_science_status(initial_loaded)
        self._update_exploration_excel_hint()

        self._add_save_bar(parent, row=1)

    # ------------------------------------------------------------------ #
    #   Zakładka: HANDEL
    # ------------------------------------------------------------------ #

    def _build_tab_trade(self) -> None:
        parent = self._tab_trade
        parent.columnconfigure(0, weight=1)

        lf_trade = ttk.LabelFrame(parent, text=" Handel (Makler) ")
        lf_trade.grid(row=0, column=0, padx=12, pady=(12, 12), sticky="nsew")

        lf_trade.columnconfigure(0, weight=1)
        lf_trade.columnconfigure(1, weight=1)
        lf_trade.columnconfigure(2, weight=1)

        ttk.Checkbutton(
            lf_trade,
            text="Makler PRO – alerty jackpotów",
            variable=self.var_trade_jackpot_alerts,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Button(
            lf_trade,
            text="Edytuj progi…",
            command=self._edit_jackpot_thresholds,
        ).grid(row=0, column=1, padx=8, pady=4, sticky="w")

        chk_mining = ttk.Checkbutton(
            lf_trade,
            text="Mining Accountant (wkrótce)",
            variable=self.var_mining_accountant,
        )
        chk_mining.state(["disabled"])
        chk_mining.grid(row=0, column=2, padx=8, pady=4, sticky="w")

        ttk.Label(
            lf_trade,
            text="Progi jackpotów wpływają na alerty w handlu.",
            foreground="#888888",
        ).grid(row=1, column=0, columnspan=3, padx=8, pady=(0, 6), sticky="w")

        self._add_save_bar(parent, row=1)

    def _edit_jackpot_thresholds(self) -> None:
        existing = getattr(self, "_jackpot_dialog", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except Exception:
            self._jackpot_dialog = None

        dialog = tk.Toplevel(self)
        self._jackpot_dialog = dialog
        dialog.title("Progi jackpotów")
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        try:
            dialog.attributes("-topmost", True)
        except Exception:
            pass
        dialog.grab_set()

        entries: Dict[str, tk.Entry] = {}
        row = 0
        for key in sorted(config.DEFAULT_JACKPOT_THRESHOLDS.keys()):
            ttk.Label(dialog, text=key).grid(row=row, column=0, padx=8, pady=4, sticky="w")
            ent = ttk.Entry(dialog, width=10)
            ent.insert(0, str(self.jackpot_thresholds.get(key, 0)))
            ent.grid(row=row, column=1, padx=8, pady=4, sticky="w")
            entries[key] = ent
            row += 1

        def _on_close():
            try:
                dialog.grab_release()
            except Exception:
                pass
            try:
                dialog.destroy()
            finally:
                self._jackpot_dialog = None

        def on_save():
            updated: Dict[str, int] = {}
            for k, ent in entries.items():
                try:
                    val = int(ent.get().strip())
                except Exception:
                    messagebox.showwarning("Błąd", f"Niepoprawna wartość dla: {k}")
                    return
                if val < 0:
                    messagebox.showwarning("Błąd", f"Wartość nie może być ujemna: {k}")
                    return
                updated[k] = val
            self.jackpot_thresholds = updated
            _on_close()

        btn_row = ttk.Frame(dialog)
        btn_row.grid(row=row, column=0, columnspan=2, pady=(6, 8), sticky="e")
        ttk.Button(btn_row, text="Anuluj", command=_on_close).grid(row=0, column=0, padx=6)
        ttk.Button(btn_row, text="Zapisz", command=on_save).grid(row=0, column=1, padx=6)

        dialog.protocol("WM_DELETE_WINDOW", _on_close)
        dialog.focus_force()

    # ------------------------------------------------------------------ #
    #   Zakładka: INŻYNIER
    # ------------------------------------------------------------------ #

    def _build_tab_engineer(self) -> None:
        parent = self._tab_engineer
        parent.columnconfigure(0, weight=1)

        lf_engineer_combat = ttk.LabelFrame(parent, text=" Inżynier pokładowy / bojowe ")
        lf_engineer_combat.grid(row=0, column=0, padx=12, pady=(12, 12), sticky="nsew")

        lf_engineer_combat.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            lf_engineer_combat,
            text="Bounty Hunter",
            variable=self.var_bounty_hunter,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        # future -> disabled
        for child in lf_engineer_combat.winfo_children():
            if isinstance(child, ttk.Checkbutton):
                child.state(["disabled"])
                child.configure(text=f"{child.cget('text')} (wkrótce)")

        self._add_save_bar(parent, row=1)

    def _on_use_system_theme(self) -> None:
        if not hasattr(self, "_theme_combo"):
            return
        if self.var_use_system_theme.get():
            self._theme_combo.state(["disabled"])
        else:
            self._theme_combo.state(["readonly"])

    # ------------------------------------------------------------------ #
    #   Zakładka: ZAAWANSOWANE
    # ------------------------------------------------------------------ #

    def _build_tab_advanced(self) -> None:
        parent = self._tab_advanced
        parent.columnconfigure(0, weight=1)

        lf_debug = ttk.LabelFrame(parent, text=" Debug ")
        lf_debug.grid(row=0, column=0, padx=12, pady=(12, 12), sticky="nsew")
        lf_debug.columnconfigure(0, weight=1)

        ttk.Checkbutton(
            lf_debug,
            text="Debug: autocomplete",
            variable=self.var_debug_autocomplete,
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_debug,
            text="Debug: cache",
            variable=self.var_debug_cache,
        ).grid(row=1, column=0, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_debug,
            text="Debug: dedup",
            variable=self.var_debug_dedup,
        ).grid(row=2, column=0, padx=8, pady=4, sticky="w")

        ttk.Checkbutton(
            lf_debug,
            text="Debug: ShipState",
            variable=self.var_debug_ship_state,
        ).grid(row=3, column=0, padx=8, pady=4, sticky="w")

        ttk.Label(
            lf_debug,
            text="Włącza dodatkowe logi w konsoli i pulpicie.",
            foreground="#888888",
        ).grid(row=4, column=0, padx=8, pady=(2, 8), sticky="w")

        self._add_save_bar(parent, row=1)

    # ------------------------------------------------------------------ #
    # Ładowanie / zapisywanie – połączone z backendowym configiem
    # ------------------------------------------------------------------ #

    def _load_initial_values(self) -> None:
        """Jeśli podano get_config, załaduj wartości startowe z JSON-a."""
        if self._get_config is None:
            return

        cfg = self._get_config() or {}

        # klucze z DEFAULT_SETTINGS
        self.var_language.set(cfg.get("language", self.var_language.get()))
        self.var_theme.set(cfg.get("theme", self.var_theme.get()))

        # główny TTS / głos
        self.var_enable_sounds.set(cfg.get("voice_enabled", self.var_enable_sounds.get()))

        # logi
        self.var_log_path.set(cfg.get("log_dir", self.var_log_path.get()))
        # auto_detect_logs nadal tylko frontendowe – jak jest w JSON, to wczytamy:
        self.var_auto_detect_logs.set(cfg.get("auto_detect_logs", self.var_auto_detect_logs.get()))

        # SPANSH – opcjonalne / frontend
        self.var_spansh_timeout.set(str(cfg.get("spansh_timeout", self.var_spansh_timeout.get())))
        self.var_spansh_retries.set(str(cfg.get("spansh_retries", self.var_spansh_retries.get())))

        self.var_use_system_theme.set(cfg.get("use_system_theme", self.var_use_system_theme.get()))
        self.var_confirm_exit.set(cfg.get("confirm_exit", self.var_confirm_exit.get()))

        # Asystenci – mapowanie na klucze JSON
        self.var_read_landing_pad.set(
            cfg.get("landing_pad_speech", self.var_read_landing_pad.get())
        )
        self.var_auto_clipboard.set(
            cfg.get("auto_clipboard", self.var_auto_clipboard.get())
        )
        self.var_route_progress_messages.set(
            cfg.get("route_progress_speech", self.var_route_progress_messages.get())
        )
        self.var_low_fuel_warning.set(
            cfg.get("fuel_warning", self.var_low_fuel_warning.get())
        )
        self.var_low_fuel_threshold.set(
            str(cfg.get("fuel_warning_threshold_pct", self.var_low_fuel_threshold.get()))
        )
        self.var_high_g_warning.set(
            cfg.get("high_g_warning", self.var_high_g_warning.get())
        )

        self.var_fss_assistant.set(
            cfg.get("fss_assistant", self.var_fss_assistant.get())
        )
        self.var_high_value_planet_alerts.set(
            cfg.get("high_value_planets", self.var_high_value_planet_alerts.get())
        )
        self.var_dss_bio3_assistant.set(
            cfg.get("bio_assistant", self.var_dss_bio3_assistant.get())
        )

        self.var_trade_jackpot_alerts.set(
            cfg.get("trade_jackpot_speech", self.var_trade_jackpot_alerts.get())
        )
        self.var_smuggler_alert.set(
            cfg.get("smuggler_alert", self.var_smuggler_alert.get())
        )

        # pozostałe – czysto frontendowe / future
        self.var_mining_accountant.set(
            cfg.get("mining_accountant", self.var_mining_accountant.get())
        )
        self.var_bounty_hunter.set(
            cfg.get("bounty_hunter", self.var_bounty_hunter.get())
        )
        self.var_preflight_limpets.set(
            cfg.get("preflight_limpets", self.var_preflight_limpets.get())
        )
        self.var_fdff_notifications.set(
            cfg.get("fdff_notifications", self.var_fdff_notifications.get())
        )
        self.var_read_system_after_jump.set(
            cfg.get("read_system_after_jump", self.var_read_system_after_jump.get())
        )

        # progi Maklera
        thresholds = cfg.get("jackpot_thresholds", self.jackpot_thresholds)
        if isinstance(thresholds, dict):
            merged = config.DEFAULT_JACKPOT_THRESHOLDS.copy()
            for key, value in thresholds.items():
                try:
                    merged[key] = int(value)
                except Exception:
                    continue
            self.jackpot_thresholds = merged

        # debug
        self.var_debug_autocomplete.set(
            cfg.get("debug_autocomplete", self.var_debug_autocomplete.get())
        )
        self.var_debug_cache.set(
            cfg.get("debug_cache", self.var_debug_cache.get())
        )
        self.var_debug_dedup.set(
            cfg.get("debug_dedup", self.var_debug_dedup.get())
        )
        self.var_debug_ship_state.set(
            cfg.get("ship_state_debug", self.var_debug_ship_state.get())
        )

        self._on_use_system_theme()

    def _parse_int_range(self, raw: str, *, default: int, min_val: int, max_val: int) -> int:
        try:
            val = int(str(raw).strip())
        except Exception:
            return default
        if val < min_val:
            return min_val
        if val > max_val:
            return max_val
        return val

    def _collect_config(self) -> Dict[str, Any]:
        """
        Zbiera aktualny stan pól do słownika.
        Klucze istotne dla backendu:
            log_dir,
            language, theme,
            voice_enabled,
            landing_pad_speech, auto_clipboard,
            route_progress_speech, fuel_warning, high_g_warning,
            fss_assistant, high_value_planets, bio_assistant,
            trade_jackpot_speech, smuggler_alert.
        Reszta może być traktowana jako rozszerzenie.
        """
        spansh_timeout = self._parse_int_range(
            self.var_spansh_timeout.get(),
            default=int(config.get("spansh_timeout", 20)),
            min_val=5,
            max_val=120,
        )
        spansh_retries = self._parse_int_range(
            self.var_spansh_retries.get(),
            default=int(config.get("spansh_retries", 3)),
            min_val=0,
            max_val=10,
        )
        self.var_spansh_timeout.set(str(spansh_timeout))
        self.var_spansh_retries.set(str(spansh_retries))

        cfg: Dict[str, Any] = {
            # klucze główne (uzgodnione z backendem)
            "log_dir": self.var_log_path.get().strip(),
            "language": self.var_language.get() if self.var_language.get() in ("pl", "en") else "pl",
            "theme": self.var_theme.get() if self.var_theme.get() in ("dark", "ed_orange", "ed_blue", "dark_minimal") else "dark",

            "voice_enabled": self.var_enable_sounds.get(),

            "landing_pad_speech": self.var_read_landing_pad.get(),
            "auto_clipboard": self.var_auto_clipboard.get(),
            "route_progress_speech": self.var_route_progress_messages.get(),
            "fuel_warning": self.var_low_fuel_warning.get(),
            "fuel_warning_threshold_pct": int(
                self.var_low_fuel_threshold.get()
                if self.var_low_fuel_threshold.get() in ("15", "25", "50")
                else 15
            ),
            "high_g_warning": self.var_high_g_warning.get(),

            "fss_assistant": self.var_fss_assistant.get(),
            "high_value_planets": self.var_high_value_planet_alerts.get(),
            "bio_assistant": self.var_dss_bio3_assistant.get(),

            "trade_jackpot_speech": self.var_trade_jackpot_alerts.get(),
            "smuggler_alert": self.var_smuggler_alert.get(),

            # dodatkowe / frontend only (ale możemy też trzymać w JSON)
            "use_system_theme": self.var_use_system_theme.get(),
            "auto_detect_logs": self.var_auto_detect_logs.get(),
            "spansh_timeout": spansh_timeout,
            "spansh_retries": spansh_retries,
            "confirm_exit": self.var_confirm_exit.get(),

            "mining_accountant": self.var_mining_accountant.get(),
            "bounty_hunter": self.var_bounty_hunter.get(),
            "preflight_limpets": self.var_preflight_limpets.get(),
            "fdff_notifications": self.var_fdff_notifications.get(),
            "read_system_after_jump": self.var_read_system_after_jump.get(),

            "jackpot_thresholds": self.jackpot_thresholds,

            "debug_autocomplete": self.var_debug_autocomplete.get(),
            "debug_cache": self.var_debug_cache.get(),
            "debug_dedup": self.var_debug_dedup.get(),
            "ship_state_debug": self.var_debug_ship_state.get(),
        }
        return cfg

    def _update_exploration_excel_hint(self) -> None:
        """
        Sprawdza, czy plik renata_science_data.xlsx istnieje i aktualizuje
        czerwony komunikat pod sekcją Eksploracja.
        """
        excel_path = getattr(config, "SCIENCE_EXCEL_PATH", "renata_science_data.xlsx")

        try:
            has_file = os.path.exists(excel_path)
        except Exception:
            has_file = False

        if has_file:
            # Brak komunikatu, jeśli plik istnieje
            self.lbl_exploration_excel_missing.config(text="")
        else:
            self.lbl_exploration_excel_missing.config(
                text="Brak pliku renata_science_data.xlsx – wygeneruj go w menu."
            )

    def update_science_status(self, loaded: bool) -> None:
        """
        Aktualizuje status danych naukowych w sekcji Eksploracja.

        Wywoływane przy starcie oraz po wygenerowaniu arkuszy:
            settings_tab.update_science_status(app.is_science_data_available())
        """
        if loaded:
            self.science_status_var.set("Dane naukowe załadowane poprawnie.")
            self.science_status_label.configure(foreground="green")
        else:
            self.science_status_var.set("Dane naukowe NIE są dostępne – wygeneruj arkusze.")
            self.science_status_label.configure(foreground="red")

        # Przy każdej zmianie statusu odświeżamy też informację o pliku Excela
        self._update_exploration_excel_hint()

    # ------------------------------------------------------------------ #
    # Akcje przycisków
    # ------------------------------------------------------------------ #

    def _on_browse_logs(self) -> None:
        """
        Otwiera dialog wyboru folderu z logami Elite Dangerous.
        Jeśli użytkownik coś wybierze, aktualizuje pole i zmienną.
        """
        path = filedialog.askdirectory(
            title="Wybierz folder z Journalami Elite Dangerous"
        )
        if path:
            self.var_log_path.set(path)

    def _on_generate_science_excel(self) -> None:
        """
        Handler przycisku 'Generuj arkusze naukowe'.

        Nie generuje nic sam – tylko deleguje do logiki:
        controller.on_generate_science_excel()
        """
        if not self.controller:
            return

        handler = getattr(self.controller, "on_generate_science_excel", None)
        if not callable(handler):
            return

        try:
            handler()
        except Exception:
            # UI nie panikuje – logika może zalogować błąd gdzie indziej.
            pass

    def _on_reset(self) -> None:
        """Przywrócenie domyślnych wartości UI."""
        # język / wygląd
        self.var_language.set("pl")
        self.var_theme.set("dark")
        self.var_use_system_theme.set(True)

        # domyślny log_dir z backendu (jeśli jest)
        try:
            default_log_dir = config.get("log_dir", "")
        except Exception:
            default_log_dir = ""
        self.var_log_path.set(default_log_dir)
        self.var_auto_detect_logs.set(True)

        self.var_spansh_timeout.set("20")
        self.var_spansh_retries.set("3")

        self.var_enable_sounds.set(True)
        self.var_confirm_exit.set(True)

        # Asystenci – domyślnie włączone jak w DEFAULT_SETTINGS
        self.var_read_landing_pad.set(True)
        self.var_auto_clipboard.set(True)

        self.var_route_progress_messages.set(True)
        self.var_low_fuel_warning.set(True)
        self.var_low_fuel_threshold.set("15")
        self.var_fss_assistant.set(True)
        self.var_high_value_planet_alerts.set(True)
        self.var_dss_bio3_assistant.set(True)
        self.var_fdff_notifications.set(True)

        self.var_trade_jackpot_alerts.set(True)
        self.var_smuggler_alert.set(True)
        self.var_mining_accountant.set(False)
        self.jackpot_thresholds = config.DEFAULT_JACKPOT_THRESHOLDS.copy()

        self.var_bounty_hunter.set(False)
        self.var_preflight_limpets.set(True)
        self.var_high_g_warning.set(True)

        self.var_read_system_after_jump.set(True)

        self.var_debug_autocomplete.set(False)
        self.var_debug_cache.set(False)
        self.var_debug_dedup.set(False)
        self.var_debug_ship_state.set(False)

        # Reset statusu naukowego do stanu „brak danych”
        self.update_science_status(False)
        self._on_use_system_theme()

    def _on_save(self) -> None:
        """
        Zbiera wartości z UI i, jeśli podano save_config, przekazuje je dalej.
        Backend (SettingsWindow + ConfigManager) zapisuje to do user_settings.json.
        """
        if self._save_config is None:
            return

        cfg = self._collect_config()
        self._save_config(cfg)
