import tkinter as tk
from tkinter import ttk, messagebox
import os
import queue
import config
from logic import utils
from gui import common
from gui import strings as ui
from gui.tabs import pulpit, engineer
from gui.tabs import spansh
from gui.menu_bar import RenataMenuBar
from gui.tabs.settings_window import SettingsWindow
from gui.window_positions import restore_window_geometry, bind_window_geometry, save_window_geometry
from gui.window_chrome import apply_renata_orange_window_chrome
from gui.tabs.logbook import LogbookTab
import webbrowser
from logic.generate_renata_science_data import generate_science_excel
from logic.generate_renata_modules_data import generate_modules_data
from app.state import app_state
from app.route_manager import route_manager
import threading
from logic.science_data import load_science_data
from logic.modules_data import load_modules_data
from logic.utils.renata_log import log_event, log_event_throttled


def _exc_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _log_app_fallback(
    key: str,
    message: str,
    exc: Exception,
    *,
    interval_ms: int = 5000,
    **fields,
) -> None:
    payload = {"error": _exc_text(exc)}
    payload.update(fields)
    log_event_throttled(
        f"APP:{key}",
        interval_ms,
        "APP",
        message,
        **payload,
    )


class RenataApp:
    def __init__(self, root):  # <--- ZAUWAŻ WCIĘCIE (TAB)
        self.root = root
        self.root.title("R.E.N.A.T.A.")
        self.root.geometry("1100x700")
        restore_window_geometry(self.root, "main_window", include_size=True)
        bind_window_geometry(self.root, "main_window", include_size=True)
        self.root.protocol("WM_DELETE_WINDOW", self._on_main_close)
        self._ui_thread_id = threading.get_ident()

        # ==========================================================
        # 🎨 RENATA "BLACKOUT" PROTOCOL - STYLIZACJA TOTALNA
        # ==========================================================
        
        # 1. Definicja Palety (Żeby łatwo zmieniać)
        C_BG = "#0b0c10"       # Głęboka czerń (Tło)
        C_FG = "#ff7100"       # Elite Orange (Tekst)
        C_SEC = "#c5c6c7"      # Szary (Tekst pomocniczy)
        C_ACC = "#1f2833"      # Ciemnoszary (Belki, tła inputów)
        self._overlay_bg = C_ACC
        self._overlay_fg = C_FG
        self._overlay_sec = C_SEC

        # 2. Konfiguracja Głównego Okna
        self.root.configure(bg=C_BG)

        # 3. Baza Opcji (Dla starych widgetów TK: Label, Frame, Canvas)
        # To "maluje" podstawy
        self.root.option_add("*Background", C_BG)
        self.root.option_add("*Foreground", C_SEC)
        self.root.option_add("*Entry.Background", C_ACC)
        self.root.option_add("*Entry.Foreground", "#ffffff")
        self.root.option_add("*Listbox.Background", C_ACC)
        self.root.option_add("*Listbox.Foreground", "#ffffff")
        self.root.option_add("*Button.Background", C_ACC)
        self.root.option_add("*Button.Foreground", C_FG)
        self.root.option_add("*Label.Background", C_BG)
        self.root.option_add("*Label.Foreground", C_FG)
        # Fix dla białych pasków
        self.root.option_add("*Frame.background", C_BG)
        self.root.option_add("*Label.background", C_BG)

        # 4. Stylizacja Nowoczesna (TTK Styles)
        # To "maluje" Zakładki, Drzewa i Ramki
        style = ttk.Style()
        try:
            style.theme_use('clam') # Clam najlepiej przyjmuje kolory
        except tk.TclError as exc:
            _log_app_fallback("style.theme", "ttk theme unavailable", exc, theme="clam")

        # Główne elementy
        style.configure("TFrame", background=C_BG)
        style.configure("TLabel", background=C_BG, foreground=C_FG, font=("Eurostile", 10))
        style.configure("TEntry", background=C_ACC, fieldbackground=C_ACC, foreground="#ffffff")
        
        # Przyciski
        style.configure("TButton", background=C_ACC, foreground=C_FG, borderwidth=1, focuscolor=C_BG)
        style.map("TButton",
            background=[('active', C_FG), ('pressed', C_SEC)],
            foreground=[('active', C_BG), ('pressed', C_BG)]
        )

        # ZAKŁADKI (Notebook) - To jest kluczowe dla "czarnego paska"
        style.configure("TNotebook", background=C_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=C_ACC, foreground=C_SEC, padding=[15, 5], borderwidth=0)
        style.map("TNotebook.Tab", 
            background=[('selected', C_FG)], 
            foreground=[('selected', C_BG)]
        )

        # Drzewo (Treeview) - Globalna definicja
        style.configure("Treeview", 
            background=C_ACC, 
            foreground="white", 
            fieldbackground=C_ACC, 
            borderwidth=0
        )
        style.configure("Treeview.Heading", 
            background=C_BG, 
            foreground=C_FG, 
            relief="flat"
        )
        style.map("Treeview", 
            background=[('selected', C_FG)], 
            foreground=[('selected', C_BG)]
        )

        # Ramki Grupujące
        style.configure("TLabelframe", background=C_BG, foreground=C_FG, borderwidth=2, relief="groove")
        style.configure("TLabelframe.Label", background=C_BG, foreground=C_FG, font=("Eurostile", 11, "bold"))

        # Checkboxy
        style.configure("TCheckbutton", background=C_BG, foreground=C_SEC)
        style.map("TCheckbutton", background=[('active', C_BG)], foreground=[('active', "#ffffff")])

        # Suwaki (Scale) - ciemny tor + czytelny uchwyt
        style.configure(
            "TScale",
            background=C_FG,
            troughcolor=C_ACC,
            bordercolor="#d0ccc6",
            lightcolor=C_BG,
            darkcolor=C_BG,
            borderwidth=0,
            focuscolor="#d0ccc6",
            focusthickness=0,
        )
        style.configure(
            "Horizontal.TScale",
            background=C_FG,
            troughcolor=C_ACC,
            bordercolor="#d0ccc6",
            lightcolor=C_BG,
            darkcolor=C_BG,
            borderwidth=0,
            focuscolor="#d0ccc6",
            focusthickness=0,
        )
        style.map(
            "Horizontal.TScale",
            background=[("active", C_FG), ("!active", C_FG)],
            troughcolor=[("active", C_ACC), ("!active", C_ACC)],
            bordercolor=[("active", "#d0ccc6"), ("!active", "#d0ccc6")],
            lightcolor=[("active", C_BG), ("!active", C_BG)],
            darkcolor=[("active", C_BG), ("!active", C_BG)],
            focuscolor=[("focus", "#d0ccc6"), ("!focus", "#d0ccc6")],
        )

        # Scrollbary (Paski przewijania) - globalny styl (pion/poziom identycznie)
        sb_kwargs = {
            "background": C_ACC,
            "troughcolor": C_BG,
            "borderwidth": 0,
            "arrowcolor": C_FG,
            "relief": "flat",
        }
        style.configure("TScrollbar", **sb_kwargs)
        style.configure("Vertical.TScrollbar", **sb_kwargs)
        style.configure("Horizontal.TScrollbar", **sb_kwargs)
        style.map(
            "TScrollbar",
            background=[("active", C_ACC), ("pressed", C_ACC)],
            arrowcolor=[("active", C_FG), ("pressed", C_FG)],
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", C_ACC), ("pressed", C_ACC)],
            arrowcolor=[("active", C_FG), ("pressed", C_FG)],
        )
        style.map(
            "Horizontal.TScrollbar",
            background=[("active", C_ACC), ("pressed", C_ACC)],
            arrowcolor=[("active", C_FG), ("pressed", C_FG)],
        )

        # Splittery (PanedWindow) - usuniecie jasnego paska/sash
        style.configure(
            "TPanedwindow",
            background=C_ACC,
            sashthickness=8,
            sashrelief="flat",
        )
        style.configure("Vertical.Sash", background=C_ACC)
        style.configure("Horizontal.Sash", background=C_ACC)

        # ==========================================================
        # KONIEC PROTOKOŁU BLACKOUT
        # ==========================================================

        # =========================
        # GŁÓWNY NOTEBOOK
        # =========================
        # Best-effort kolor chrome okna (Windows titlebar + border).
        try:
            apply_renata_orange_window_chrome(self.root)
        except Exception as exc:
            _log_app_fallback("window.chrome", "window chrome color unavailable", exc)

        self.main_nb = ttk.Notebook(self.root)
        self.main_nb.pack(fill="both", expand=1)
        self.main_nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # --- Pulpit ---
        self.tab_pulpit = pulpit.PulpitTab(
            self.main_nb,
            on_generate_science_excel=self.on_generate_science_excel,
            on_generate_modules_data=self.on_generate_modules_data,
            app_state=app_state,
            route_manager=route_manager,
        )
        self.main_nb.add(self.tab_pulpit, text=ui.TAB_MAIN_PULPIT)

        # --- SPANSH ---
        self.tab_spansh = spansh.SpanshTab(self.main_nb, self.root)
        self.main_nb.add(self.tab_spansh, text=ui.TAB_MAIN_SPANSH)

        # --- Inara / EDTools / Inżynier (ukryte w FREE) ---
        self.tab_inara = None
        self.tab_edtools = None
        self.tab_engi = None
        free_profile = bool(config.get("features.tts.free_policy_enabled", True))
        if not free_profile:
            self.tab_inara = ttk.Frame(self.main_nb)
            self.main_nb.add(self.tab_inara, text=ui.TAB_MAIN_INARA)
            ttk.Label(
                self.tab_inara,
                text="Moduł Inara - Wkrótce",
                font=("Arial", 14),
            ).pack(pady=50)

            self.tab_edtools = ttk.Frame(self.main_nb)
            self.main_nb.add(self.tab_edtools, text=ui.TAB_MAIN_EDTOOLS)
            ttk.Label(
                self.tab_edtools,
                text="Moduł EDTools - Wkrótce",
                font=("Arial", 14),
            ).pack(pady=50)

            self.tab_engi = engineer.EngineerTab(self.main_nb, self)
            self.main_nb.add(self.tab_engi, text=ui.TAB_MAIN_ENGINEER)

        # --- Dziennik ---
        from logic.logbook_manager import LogbookManager
        self.logbook_manager = LogbookManager()
        self.tab_journal = LogbookTab(self.main_nb, app=self, manager=self.logbook_manager)
        self.main_nb.add(self.tab_journal, text=ui.TAB_MAIN_JOURNAL)

        # Mapa kluczy -> zakładek (do obsługi menu "Nawigacja")
        self._tab_map = {
            "pulpit": self.tab_pulpit,
            "spansh": self.tab_spansh,
            "journal": self.tab_journal,
        }
        if self.tab_inara is not None:
            self._tab_map["inara"] = self.tab_inara
        if self.tab_edtools is not None:
            self._tab_map["edtools"] = self.tab_edtools
        if self.tab_engi is not None:
            self._tab_map["engineer"] = self.tab_engi

        # =========================
        # PASEK MENU
        # =========================
        self.menu_bar = RenataMenuBar(
            self.root,
            on_quit=self.root.quit,
            on_open_settings=self._open_settings_window,
            on_show_about=self._show_about_dialog,
            on_switch_tab=self._switch_tab,
            on_toggle_always_on_top=self.on_toggle_always_on_top,
            on_open_link=self.on_open_link,
            tab_labels={
                "pulpit": ui.TAB_MAIN_PULPIT,
                "spansh": ui.TAB_MAIN_SPANSH,
                "journal": ui.TAB_MAIN_JOURNAL,
                **({"engineer": ui.TAB_MAIN_ENGINEER} if self.tab_engi is not None else {}),
                **({"inara": ui.TAB_MAIN_INARA} if self.tab_inara is not None else {}),
                **({"edtools": ui.TAB_MAIN_EDTOOLS} if self.tab_edtools is not None else {}),
            },
        )
        self.root.config(menu=self.menu_bar)

        # --- OVERLAY / QUICK-VIEW ---
        self._init_overlay()
        self._init_debug_panel()

        # =========================
        # DANE NAUKOWE (S2-LOGIC-01)
        # =========================
        self.exobio_df = None
        self.carto_df = None
        self.science_data_loaded: bool = False
        self.modules_data_loaded: bool = False
        self.modules_data = None

        # próba wczytania danych przy starcie
        self._try_load_science_data()
        self._try_load_modules_data()

        # =========================
        # BINDY I PĘTLA KOLEJKI
        # =========================
        self.root.bind("<ButtonRelease-1>", self.check_focus, add="+")
        self.root.bind("<Configure>", self.on_window_move)
        self._init_window_resize_hitbox()
        self.root.after(100, self.check_queue)

    # ------------------------------------------------------------------ #
    #   Helpery do obsługi menu / nawigacji
    # ------------------------------------------------------------------ #

    def _on_tab_changed(self, _event):
        if hasattr(self.tab_spansh, "hide_suggestions"):
            self.tab_spansh.hide_suggestions()

    def _switch_tab(self, tab_key: str):
        tab = self._tab_map.get(tab_key)
        if tab is not None:
            self.main_nb.select(tab)

    def _show_about_dialog(self):
        import tkinter.messagebox as mbox

        release_url = "https://github.com/tyffanthc/RenataAI/releases/tag/v0.9.1-preview"
        text = (
            f"R.E.N.A.T.A. {config.APP_VERSION}\n"
            "Route, Exploration & Navigation Assistant for Trading & Analysis.\n\n"
            "Wersja FREE Preview:\n"
            "- Companion desktop do Elite Dangerous\n"
            "- Offline-first, bezpieczne fallbacki\n"
            "- Voice Pack Piper PL jest opcjonalny\n\n"
            f"Release: {release_url}\n\n"
            "Otworzyc strone release w przegladarce?"
        )
        if mbox.askyesno("O programie", text):
            try:
                webbrowser.open(release_url)
            except Exception as exc:
                _log_app_fallback("about.open_release", "failed to open release URL", exc)

    # ------------------------------------------------------------------ #
    #   Okno ustawień (Konfiguracja Systemów R.E.N.A.T.A.)
    # ------------------------------------------------------------------ #

    def _open_settings_window(self) -> None:
        """
        Otwiera nowe okno SettingsWindow jako modalne.
        Jeśli już jest otwarte – zamyka je (toggle).
        """
        existing = getattr(self, "_settings_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                try:
                    existing._on_close()
                except Exception as close_exc:
                    try:
                        existing.destroy()
                    except Exception as destroy_exc:
                        _log_app_fallback(
                            "settings.toggle.destroy",
                            "failed to destroy existing settings window",
                            destroy_exc,
                        )
                    _log_app_fallback(
                        "settings.toggle.close",
                        "settings window close callback failed; forced destroy fallback",
                        close_exc,
                    )
                return
        except Exception as exc:
            _log_app_fallback("settings.toggle.probe", "settings window probe failed", exc)
            self._settings_window = None

        self._settings_window = SettingsWindow(
            self.root,
            controller=self,
            on_close=self._on_settings_window_closed,
        )

        # dla kompatybilności z _try_load_science_data / update_science_status
        self.settings_tab = self._settings_window.settings_tab

    def _on_settings_window_closed(self) -> None:
        """Czyścimy referencję, gdy okno ustawień się zamknie."""
        self._settings_window = None
        self.settings_tab = None

    def _on_main_close(self) -> None:
        save_window_geometry(self.root, "main_window", include_size=True)
        try:
            self.root.quit()
        except Exception as quit_exc:
            _log_app_fallback("main_close.quit", "main window quit failed; trying destroy", quit_exc)
            try:
                self.root.destroy()
            except Exception as destroy_exc:
                _log_app_fallback("main_close.destroy", "main window destroy failed", destroy_exc)

    # ------------------------------------------------------------------ #
    #   Dane naukowe (Exobiology / Cartography)
    # ------------------------------------------------------------------ #

    def _science_data_path(self) -> str:
        return str(config.get("science_data_path", config.SCIENCE_EXCEL_PATH) or config.SCIENCE_EXCEL_PATH)

    def _try_load_science_data(self) -> None:
        """
        Próbuje wczytać arkusze naukowe z Excela.
        Utrzymuje prawdę o stanie w self.science_data_loaded
        i aktualizuje GUI (SettingsTab), jeśli to możliwe.
        """
        try:
            self.exobio_df, self.carto_df = load_science_data(self._science_data_path())
            self.science_data_loaded = True
            self.show_status("Dane naukowe załadowane poprawnie.")
        except Exception as exc:
            self.exobio_df = None
            self.carto_df = None
            self.science_data_loaded = False
            _log_app_fallback("science.load", "science data load failed", exc, path=self._science_data_path())
            # łagodny komunikat – szczegół błędu nie musi iść do usera
            self.show_status("Dane naukowe NIE są dostępne – wygeneruj arkusze.")
            # jeśli chcesz debug:
            # self.show_status(f"Szczegóły błędu danych naukowych: {e}")

        # powiadom GUI (Opcje), jeśli ma odpowiednią metodę
        if getattr(self, "settings_tab", None) is not None:
            if hasattr(self.settings_tab, "update_science_status"):
                try:
                    self.settings_tab.update_science_status(self.science_data_loaded)
                except Exception as exc:
                    _log_app_fallback(
                        "science.status_widget",
                        "settings science status refresh failed",
                        exc,
                    )
            if hasattr(self.settings_tab, "update_modules_status"):
                try:
                    self.settings_tab.update_modules_status(self.modules_data_loaded)
                except Exception as exc:
                    _log_app_fallback(
                        "modules.status_widget_from_science",
                        "settings modules status refresh failed",
                        exc,
                    )

    def _try_load_modules_data(self) -> None:
        """
        Próbuje wczytać dane modułów z pliku JSON.
        """
        if not config.get("modules_data_enabled", True):
            self.modules_data = None
            self.modules_data_loaded = False
            if getattr(self, "settings_tab", None) is not None:
                if hasattr(self.settings_tab, "update_modules_status"):
                    try:
                        self.settings_tab.update_modules_status(self.modules_data_loaded)
                    except Exception as exc:
                        _log_app_fallback(
                            "modules.status_widget_disabled",
                            "settings modules status refresh failed",
                            exc,
                        )
            return
        try:
            path = config.get("modules_data_path", "renata_modules_data.json")
        except Exception as exc:
            _log_app_fallback(
                "modules.path",
                "failed to resolve modules_data_path; using default",
                exc,
                interval_ms=30000,
            )
            path = "renata_modules_data.json"

        try:
            self.modules_data = load_modules_data(path)
            self.modules_data_loaded = True
            self.show_status("Dane modułów załadowane poprawnie.")
        except Exception as exc:
            self.modules_data = None
            _log_app_fallback("modules.load", "modules data load failed", exc, path=path)
            self.modules_data_loaded = False
            self.show_status("Brak danych modułów — wygeneruj plik.")

        try:
            app_state.modules_data = self.modules_data
            app_state.modules_data_loaded = self.modules_data_loaded
        except Exception as exc:
            _log_app_fallback("modules.state_sync", "failed to sync modules data to app_state", exc)

        if self.modules_data_loaded:
            try:
                app_state.ship_state.recompute_jump_range("loadout")
            except Exception as exc:
                _log_app_fallback(
                    "modules.recompute_jump_range",
                    "failed to recompute jump range after modules load",
                    exc,
                )

        if getattr(self, "settings_tab", None) is not None:
            if hasattr(self.settings_tab, "update_modules_status"):
                try:
                    self.settings_tab.update_modules_status(self.modules_data_loaded)
                except Exception as exc:
                    _log_app_fallback("modules.status_widget", "settings modules status refresh failed", exc)

    def is_science_data_available(self) -> bool:
        """
        Zwraca True, jeśli arkusze naukowe zostały poprawnie wczytane.
        """
        return bool(self.science_data_loaded)

    def is_modules_data_available(self) -> bool:
        return bool(self.modules_data_loaded)

    # ------------------------------------------------------------------ #
    #   Reszta Twojego kodu bez zmian
    # ------------------------------------------------------------------ #

    def _init_window_resize_hitbox(self) -> None:
        """
        Improves resize ergonomics by adding a custom in-window hitbox near
        the right/bottom edges. Native window frame stays enabled.
        """
        self._resize_hitbox_px = 8
        self._resize_hover_zone = None
        self._resize_drag_mode = None
        self._resize_drag_started = False
        self._resize_drag_origin = (0, 0)
        self._resize_start_size = (0, 0)

        self.root.bind_all("<Motion>", self._on_resize_motion, add="+")
        self.root.bind_all("<ButtonPress-1>", self._on_resize_press, add="+")
        self.root.bind_all("<B1-Motion>", self._on_resize_drag, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._on_resize_release, add="+")

    def _is_resize_allowed(self) -> bool:
        try:
            state = str(self.root.state()).lower()
        except Exception:
            state = "normal"
        if state in {"zoomed", "iconic"}:
            return False
        try:
            if bool(self.root.attributes("-fullscreen")):
                return False
        except Exception:
            pass
        return True

    def _is_pointer_over_main_window(self, x_root: int, y_root: int) -> bool:
        try:
            widget = self.root.winfo_containing(x_root, y_root)
        except Exception:
            return False
        if widget is None:
            return False
        try:
            return widget.winfo_toplevel() == self.root
        except Exception:
            return False

    def _detect_resize_zone(self, x_root: int, y_root: int):
        try:
            x = x_root - self.root.winfo_rootx()
            y = y_root - self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
        except Exception:
            return None

        margin = int(getattr(self, "_resize_hitbox_px", 8))
        if margin < 1 or w <= 0 or h <= 0:
            return None

        near_right = (w - margin) <= x <= w
        near_bottom = (h - margin) <= y <= h

        if near_right and near_bottom:
            return "se"
        if near_right:
            return "e"
        if near_bottom:
            return "s"
        return None

    @staticmethod
    def _cursor_for_resize_zone(zone):
        if zone == "e":
            return "sb_h_double_arrow"
        if zone == "s":
            return "sb_v_double_arrow"
        if zone == "se":
            return "size_nw_se"
        return ""

    def _set_resize_cursor(self, zone) -> None:
        cursor = self._cursor_for_resize_zone(zone)
        try:
            self.root.configure(cursor=cursor)
        except Exception:
            pass

    def _on_resize_motion(self, event):
        if getattr(self, "_resize_drag_mode", None):
            return
        if not self._is_resize_allowed():
            self._resize_hover_zone = None
            self._set_resize_cursor(None)
            return

        x_root = int(getattr(event, "x_root", self.root.winfo_pointerx()))
        y_root = int(getattr(event, "y_root", self.root.winfo_pointery()))

        if not self._is_pointer_over_main_window(x_root, y_root):
            if self._resize_hover_zone is not None:
                self._resize_hover_zone = None
                self._set_resize_cursor(None)
            return

        zone = self._detect_resize_zone(x_root, y_root)
        if zone != self._resize_hover_zone:
            self._resize_hover_zone = zone
            self._set_resize_cursor(zone)

    def _on_resize_press(self, event):
        if not self._is_resize_allowed():
            return

        x_root = int(getattr(event, "x_root", self.root.winfo_pointerx()))
        y_root = int(getattr(event, "y_root", self.root.winfo_pointery()))

        if not self._is_pointer_over_main_window(x_root, y_root):
            return

        zone = self._detect_resize_zone(x_root, y_root)
        if zone is None:
            return

        self._resize_drag_mode = zone
        self._resize_drag_started = True
        self._resize_drag_origin = (x_root, y_root)
        self._resize_start_size = (self.root.winfo_width(), self.root.winfo_height())
        self._set_resize_cursor(zone)
        return "break"

    def _on_resize_drag(self, event):
        mode = getattr(self, "_resize_drag_mode", None)
        if mode is None:
            return

        x_root = int(getattr(event, "x_root", self.root.winfo_pointerx()))
        y_root = int(getattr(event, "y_root", self.root.winfo_pointery()))

        start_x, start_y = self._resize_drag_origin
        start_w, start_h = self._resize_start_size
        dx = x_root - start_x
        dy = y_root - start_y

        min_w, min_h = self.root.minsize()
        if min_w < 1:
            min_w = 1
        if min_h < 1:
            min_h = 1

        new_w = start_w + dx if "e" in mode else start_w
        new_h = start_h + dy if "s" in mode else start_h

        if new_w < min_w:
            new_w = min_w
        if new_h < min_h:
            new_h = min_h

        try:
            self.root.geometry(f"{int(new_w)}x{int(new_h)}")
        except Exception as exc:
            _log_app_fallback("window.resize.drag", "window resize drag failed", exc, interval_ms=1000)
        return "break"

    def _on_resize_release(self, event):
        mode = getattr(self, "_resize_drag_mode", None)
        if mode is None:
            return

        self._resize_drag_mode = None
        self._resize_drag_started = False

        x_root = int(getattr(event, "x_root", self.root.winfo_pointerx()))
        y_root = int(getattr(event, "y_root", self.root.winfo_pointery()))
        zone = self._detect_resize_zone(x_root, y_root) if self._is_resize_allowed() else None
        self._resize_hover_zone = zone
        self._set_resize_cursor(zone)
        return "break"

    def check_focus(self, e):
        if getattr(self, "_resize_drag_started", False):
            self._resize_drag_started = False
            return
        if not hasattr(self.tab_spansh, 'hide_suggestions'):
            return
        w = None
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except Exception as exc:
            _log_app_fallback(
                "focus.winfo_containing",
                "failed to resolve clicked widget from coordinates",
                exc,
                interval_ms=15000,
            )
            w = e.widget
        if config.get("features.debug.input_trace", False):
            log_event(
                "APPDBG",
                "click widget",
                widget=str(w),
                widget_class=w.winfo_class() if w is not None else None,
            )
        try:
            from gui.common_autocomplete import AutocompleteController
            active_owner = AutocompleteController._active_owner
        except Exception as exc:
            _log_app_fallback(
                "autocomplete.owner",
                "failed to resolve autocomplete active owner",
                exc,
                interval_ms=15000,
            )
            active_owner = None
        is_listbox = isinstance(w, tk.Listbox) or getattr(w, "_renata_autocomplete", False)
        is_entry = isinstance(w, (tk.Entry, ttk.Entry))
        if is_listbox or (active_owner is not None and is_entry and w == active_owner.entry):
            if config.get("features.debug.input_trace", False):
                log_event("APPDBG", "ignore autocomplete click")
            return
        self.root.after_idle(self.tab_spansh.hide_suggestions)

    def on_window_move(self, event):
        if not hasattr(self.tab_spansh, 'hide_suggestions'):
            return
        try:
            from gui.common_autocomplete import AutocompleteController
            shared_listbox = AutocompleteController._shared_listbox
            active_owner = AutocompleteController._active_owner
        except Exception as exc:
            _log_app_fallback(
                "autocomplete.shared",
                "failed to resolve autocomplete shared state",
                exc,
                interval_ms=15000,
            )
            shared_listbox = None
            active_owner = None
        if active_owner is not None:
            return
        if shared_listbox is not None:
            try:
                if shared_listbox.winfo_ismapped():
                    return
            except tk.TclError:
                pass
        self.root.after_idle(self.tab_spansh.hide_suggestions)

    def check_queue(self):
        try:
            while True:
                msg_type, content = utils.MSG_QUEUE.get_nowait()

                if msg_type == "log":
                    self.tab_pulpit.log(content)

                elif msg_type == "status_neu":
                    txt, col = content
                    if hasattr(self.tab_spansh.tab_neutron, "set_status_text"):
                        self.tab_spansh.tab_neutron.set_status_text(txt, col)
                    else:
                        self.tab_spansh.tab_neutron.lbl_status.config(text=txt, foreground=col)
                elif msg_type == "list_nav":
                    common.wypelnij_liste(self.tab_spansh.tab_neutron.lst_nav, content)
                elif msg_type == "select_nav":
                    common.podswietl_cel(self.tab_spansh.tab_neutron.lst_nav, content)

                elif msg_type == "status_rtr":
                    txt, col = content
                    self.tab_spansh.tab_riches.lbl_status.config(text=txt, foreground=col)
                elif msg_type == "list_rtr":
                    common.wypelnij_liste(self.tab_spansh.tab_riches.lst_rtr, content)
                elif msg_type == "select_rtr":
                    common.podswietl_cel(self.tab_spansh.tab_riches.lst_rtr, content)

                elif msg_type == "status_amm":
                    txt, col = content
                    self.tab_spansh.tab_ammonia.lbl_status.config(text=txt, foreground=col)
                elif msg_type == "list_amm":
                    common.wypelnij_liste(self.tab_spansh.tab_ammonia.lst_amm, content)
                elif msg_type == "select_amm":
                    common.podswietl_cel(self.tab_spansh.tab_ammonia.lst_amm, content)

                elif msg_type == "status_trade":
                    txt, col = content
                    self.tab_spansh.tab_trade.lbl_status.config(text=txt, foreground=col)

                elif msg_type == "status_event":
                    self._overlay_set_status(content)

                elif msg_type == "ship_state":
                    try:
                        self.tab_pulpit.update_ship_state(content)
                    except Exception as exc:
                        _log_app_fallback(
                            "queue.ship_state.pulpit",
                            "failed to update pulpit ship state widget",
                            exc,
                            interval_ms=3000,
                        )
                    try:
                        self.tab_spansh.update_jump_range(content.get("jump_range_current_ly"))
                    except Exception as exc:
                        _log_app_fallback(
                            "queue.ship_state.spansh",
                            "failed to update spansh jump range widget",
                            exc,
                            interval_ms=3000,
                        )
                    self._overlay_update_jump_range(content)

                elif msg_type == "start_label":
                    live_ready = bool(getattr(app_state, "has_live_system_event", False))
                    # Prefill "Start" should also work after bootstrap replay.
                    # Live gating remains in places where true live-state is required.
                    self.tab_spansh.update_start_label(content)
                    try:
                        self.tab_pulpit.set_system_runtime_state(str(content), live_ready=live_ready)
                    except Exception as exc:
                        _log_app_fallback(
                            "queue.start_label.runtime_state",
                            "failed to update runtime state label",
                            exc,
                            interval_ms=3000,
                        )

        except queue.Empty:
            pass
        except Exception as exc:
            _log_app_fallback("queue.loop", "queue processing failed", exc, interval_ms=2000)
        finally:
            self.root.after(100, self.check_queue)

    def update_start_label(self, txt):
        utils.MSG_QUEUE.put(("start_label", txt))

    def update_status(self, msg, col="black", target="neu"):
        utils.MSG_QUEUE.put((f"status_{target}", (msg, col)))

    def show_status(self, msg: str):
        """
        Prosty helper do pokazywania komunikatów statusu.
        Na razie: log na Pulpit + fallback na print.
        """
        try:
            self.tab_pulpit.log(msg)
        except Exception as exc:
            _log_app_fallback(
                "show_status.log",
                "failed to write status to pulpit log",
                exc,
                interval_ms=2000,
                message=msg,
            )

    # ------------------------------------------------------------------ #
    #   Overlay / quick-view
    # ------------------------------------------------------------------ #

    def _init_overlay(self):
        self._overlay_hide_after_id = None
        self._overlay_visible = False

        self.overlay_frame = tk.Frame(
            self.root,
            bg=self._overlay_bg,
            bd=1,
            relief="solid",
        )

        self.overlay_status_label = tk.Label(
            self.overlay_frame,
            text="",
            bg=self._overlay_bg,
            fg=self._overlay_fg,
            font=("Arial", 9, "bold"),
        )
        self.overlay_status_label.pack(anchor="w", padx=8, pady=(6, 2))

        self.overlay_jr_label = tk.Label(
            self.overlay_frame,
            text="",
            bg=self._overlay_bg,
            fg=self._overlay_sec,
            font=("Arial", 9),
        )
        self.overlay_jr_label.pack(anchor="w", padx=8, pady=(0, 2))

        self.overlay_next_label = tk.Label(
            self.overlay_frame,
            text="Next: -",
            bg=self._overlay_bg,
            fg=self._overlay_sec,
            font=("Arial", 9),
        )
        self.overlay_next_label.pack(anchor="w", padx=8, pady=(0, 6))

        btn_row = tk.Frame(self.overlay_frame, bg=self._overlay_bg)
        btn_row.pack(fill="x", padx=6, pady=(0, 6))

        self.overlay_btn_copy = tk.Button(
            btn_row,
            text="Kopiuj",
            command=self._overlay_copy,
            bg=self._overlay_bg,
            fg=self._overlay_fg,
            relief="flat",
        )
        self.overlay_btn_copy.pack(side="left", padx=2)

        self.overlay_btn_next = tk.Button(
            btn_row,
            text="Copy next",
            command=self._overlay_copy_next,
            bg=self._overlay_bg,
            fg=self._overlay_fg,
            relief="flat",
        )
        self.overlay_btn_next.pack(side="left", padx=2)

        self.overlay_btn_details = tk.Button(
            btn_row,
            text="Pokaż szczegóły",
            command=self._overlay_show_details,
            bg=self._overlay_bg,
            fg=self._overlay_sec,
            relief="flat",
        )
        self.overlay_btn_details.pack(side="left", padx=2)

        self.overlay_btn_hide = tk.Button(
            btn_row,
            text="Ukryj",
            command=self._overlay_hide,
            bg=self._overlay_bg,
            fg=self._overlay_sec,
            relief="flat",
        )
        self.overlay_btn_hide.pack(side="right", padx=2)

        self._overlay_hide()

    def _init_debug_panel(self):
        self._debug_panel_enabled = bool(config.get("features.debug.panel", False))
        self._debug_panel_visible = False
        self._debug_panel_refresh_ms = 400
        self._debug_panel_last_text = None
        if not self._debug_panel_enabled:
            self.debug_frame = None
            self.debug_label = None
            return
        self.debug_frame = tk.Frame(
            self.root,
            bg=self._overlay_bg,
            bd=1,
            relief="solid",
        )
        self.debug_label = tk.Label(
            self.debug_frame,
            text="",
            bg=self._overlay_bg,
            fg=self._overlay_sec,
            font=("Consolas", 9),
            justify="left",
        )
        self.debug_label.pack(anchor="w", padx=8, pady=6)
        self._schedule_debug_panel_update()

    def _run_on_ui(self, fn):
        if threading.get_ident() == self._ui_thread_id:
            fn()
            return
        try:
            self.root.after(0, fn)
        except Exception as exc:
            _log_app_fallback("ui.dispatch", "failed to dispatch callback to UI thread", exc)

    def _schedule_debug_panel_update(self):
        if not self._debug_panel_enabled:
            return
        try:
            self.root.after(self._debug_panel_refresh_ms, self._update_debug_panel)
        except Exception as exc:
            _log_app_fallback("debug.schedule", "failed to schedule debug panel refresh", exc)

    def _build_debug_snapshot(self) -> dict:
        try:
            system = getattr(app_state, "current_system", None)
            docked = getattr(app_state, "is_docked", False)
            station = getattr(app_state, "current_station", None)
        except Exception as exc:
            _log_app_fallback("debug.snapshot", "failed to read app_state snapshot for debug panel", exc)
            system = None
            docked = False
            station = None

        with route_manager.lock:
            route_type = route_manager.route_type
            route_len = len(route_manager.route)
            route_index = route_manager.current_index

        next_hop_preview = common.get_active_route_next_system()
        if not next_hop_preview:
            text = common.get_last_route_text()
            if text.startswith("Route: "):
                next_hop_preview = text.splitlines()[0].strip()

        return {
            "current_system": system,
            "docked": docked,
            "station": station,
            "route_type": route_type,
            "route_len": route_len,
            "route_index": route_index,
            "next_hop_preview": next_hop_preview,
            "clipboard_mode": str(config.get("auto_clipboard_mode", "FULL_ROUTE")).strip().upper(),
            "next_hop_stepper_enabled": bool(
                config.get("features.clipboard.next_hop_stepper", True)
            ),
        }

    def _format_debug_text(self, snapshot: dict) -> str:
        def fmt(value) -> str:
            if value is None or value == "":
                return "—"
            return str(value)

        return (
            f"System: {fmt(snapshot.get('current_system'))}\n"
            f"Docked: {fmt(snapshot.get('docked'))}\n"
            f"Station: {fmt(snapshot.get('station'))}\n"
            f"Route: {fmt(snapshot.get('route_type'))} ({fmt(snapshot.get('route_len'))})\n"
            f"Route idx: {fmt(snapshot.get('route_index'))}\n"
            f"Next hop: {fmt(snapshot.get('next_hop_preview'))}\n"
            f"Clipboard: {fmt(snapshot.get('clipboard_mode'))}\n"
            f"Next hop stepper: {fmt(snapshot.get('next_hop_stepper_enabled'))}"
        )

    def _update_debug_panel(self):
        if threading.get_ident() != self._ui_thread_id:
            self._run_on_ui(self._update_debug_panel)
            return
        if not self._debug_panel_enabled or self.debug_frame is None:
            return
        if not config.get("features.debug.panel", False):
            if self._debug_panel_visible:
                self.debug_frame.place_forget()
                self._debug_panel_visible = False
            self._debug_panel_enabled = False
            return

        if not self._debug_panel_visible:
            self.debug_frame.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
            self._debug_panel_visible = True

        snapshot = self._build_debug_snapshot()
        text = self._format_debug_text(snapshot)
        if text != self._debug_panel_last_text:
            self.debug_label.config(text=text)
            self._debug_panel_last_text = text
        self._schedule_debug_panel_update()

    def _overlay_set_status(self, event):
        if not event:
            return
        level = event.get("level")
        code = event.get("code")
        msg = event.get("text") or ""
        sticky = bool(event.get("sticky"))
        if not msg:
            return
        color = self._overlay_fg
        if level == "WARN":
            color = "orange"
        elif level == "ERROR":
            color = "red"
        label = f"{level} {code}: {msg}" if level and code else msg
        self.overlay_status_label.config(text=label, fg=color)
        self._overlay_update_next()
        if sticky:
            self._overlay_show_for(None)
        else:
            self._overlay_show_for(4.0)

    def _overlay_update_jump_range(self, data: dict) -> None:
        if not config.get("ui_show_jump_range", True):
            self.overlay_jr_label.config(text="")
            return
        location = str(config.get("ui_jump_range_location", "overlay")).strip().lower()
        if location not in ("overlay", "both"):
            self.overlay_jr_label.config(text="")
            return
        jr = data.get("jump_range_current_ly")
        if jr is None:
            self.overlay_jr_label.config(text="JR: -")
            return
        try:
            jr_val = float(jr)
        except (TypeError, ValueError):
            self.overlay_jr_label.config(text="JR: -")
            return
        txt = f"JR: {jr_val:.2f} LY"
        if config.get("ui_jump_range_show_limit", True):
            limit = data.get("jump_range_limited_by")
            if limit in ("fuel", "mass"):
                txt += f" (limit: {limit})"
        if config.get("ui_jump_range_debug_details", False):
            fuel_needed = data.get("jump_range_fuel_needed_t")
            if fuel_needed is not None:
                try:
                    txt += f" fuel:{float(fuel_needed):.2f}t"
                except (TypeError, ValueError):
                    pass
        self.overlay_jr_label.config(text=txt)

    def _overlay_update_next(self):
        next_text = "Next: -"
        next_system = common.get_active_route_next_system()
        if next_system:
            next_text = f"Next: {next_system}"
        else:
            text = common.get_last_route_text()
            if text.startswith("Route: "):
                first_line = text.splitlines()[0].strip()
                next_text = first_line

        self.overlay_next_label.config(text=next_text)

        has_text = bool(common.get_last_route_text())
        state = tk.NORMAL if has_text else tk.DISABLED
        self.overlay_btn_copy.config(state=state)
        if not config.get("features.clipboard.next_hop_stepper", True):
            self.overlay_btn_next.config(state=tk.DISABLED)
        elif config.get("auto_clipboard_next_hop_allow_manual_advance", True):
            self.overlay_btn_next.config(state=tk.NORMAL if next_system else tk.DISABLED)
        else:
            self.overlay_btn_next.config(state=tk.DISABLED)

    def _overlay_show_for(self, seconds):
        if not self._overlay_visible:
            self.overlay_frame.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")
            self._overlay_visible = True
        if self._overlay_hide_after_id is not None:
            try:
                self.root.after_cancel(self._overlay_hide_after_id)
            except Exception as exc:
                _log_app_fallback("overlay.cancel_show", "failed to cancel overlay hide timer", exc)
        self._overlay_hide_after_id = None
        if seconds is not None:
            self._overlay_hide_after_id = self.root.after(
                int(seconds * 1000), self._overlay_hide
            )

    def _overlay_hide(self):
        if self._overlay_hide_after_id is not None:
            try:
                self.root.after_cancel(self._overlay_hide_after_id)
            except Exception as exc:
                _log_app_fallback("overlay.cancel_hide", "failed to cancel overlay hide timer", exc)
            self._overlay_hide_after_id = None
        self.overlay_frame.place_forget()
        self._overlay_visible = False

    def _overlay_copy(self):
        log_event("OVERLAY", "copy_click")
        text = common.get_last_route_text()
        if not text:
            log_event("OVERLAY", "copy_skip", reason="no_text")
            common.emit_status(
                "WARN",
                "CLIPBOARD_FAIL",
                source="overlay",
            )
            return
        result = common.try_copy_to_clipboard(text, context="overlay.full_route")
        if result.get("ok"):
            common.emit_status(
                "OK",
                "ROUTE_COPIED",
                source="overlay",
            )
        else:
            common.emit_status(
                "WARN",
                "CLIPBOARD_FAIL",
                source="overlay",
            )

    def _overlay_show_details(self):
        try:
            self.root.focus_force()
        except Exception as exc:
            _log_app_fallback("overlay.focus", "failed to focus main window from overlay", exc)

    def _overlay_copy_next(self):
        if not config.get("features.clipboard.next_hop_stepper", True):
            log_event("OVERLAY", "copy_next_skip", reason="feature_off")
            return
        log_event("OVERLAY", "copy_next_click")
        common.copy_next_hop_manual(source="overlay")
        self._overlay_update_next()

    def on_toggle_always_on_top(self, is_on: bool):
        try:
            self.root.wm_attributes("-topmost", is_on)
            self.show_status(
                "Tryb 'zawsze na wierzchu' włączony."
                if is_on else "Tryb 'zawsze na wierzchu' wyłączony."
            )
        except Exception as e:
            self.show_status(f"Błąd ustawiania trybu 'zawsze na wierzchu': {e}")

    def on_open_link(self, target: str):
        LINKS = {
            "inara": "https://inara.cz/",
            "spansh": "https://spansh.co.uk/",
            "coriolis": "https://coriolis.io/",
            "fuelrats": "https://fuelrats.com/",
        }

        url = LINKS.get(str(target).lower())
        if not url:
            self.show_status(f"Nieznany link: {target}")
            return

        try:
            webbrowser.open(url)
            self.show_status(f"Otworzono: {url}")
        except Exception as e:
            self.show_status(f"Błąd otwierania linku: {e}")

    def on_generate_science_excel(self):
        """
        Wywoływane z GUI (np. przycisk w Pulpicie/Settings):
        generuje arkusz Exobiology + Cartography, a potem
        próbuje ponownie wczytać dane i odświeżyć status w GUI.
        """
        self.show_status("Generuję dane naukowe (Exobiology + Cartography)...")

        def worker():
            error = None
            try:
                generate_science_excel(self._science_data_path())
            except Exception as e:
                error = str(e)

            def done():
                # reload danych
                self._try_load_science_data()

                # komunikat końcowy
                if error is None:
                    self.show_status(
                        f"Plik {os.path.basename(self._science_data_path())} wygenerowany poprawnie."
                    )
                else:
                    self.show_status(f"Błąd generowania danych naukowych: {error}")

            # wykonujemy done() w głównym wątku Tkintera
            try:
                self.root.after(0, done)
            except Exception as exc:
                _log_app_fallback(
                    "science.generate.callback",
                    "failed to schedule science generation callback on UI thread",
                    exc,
                )
                done()

        threading.Thread(target=worker, daemon=True).start()

    def on_generate_modules_data(self):
        """
        Wywolywane z GUI: generuje renata_modules_data.json i odswieza status.
        """
        if not config.get("modules_data_autogen_enabled", True):
            self.show_status("Generator danych modulow jest wylaczony w ustawieniach.")
            return
        self.show_status("Generuje dane modulow (FSD + booster)...")

        def worker():
            error = None
            try:
                error = generate_modules_data(
                    config.get("modules_data_path", "renata_modules_data.json"),
                    config.get("modules_data_sources", None),
                )
            except Exception as e:
                error = str(e)

            def done():
                self._try_load_modules_data()
                if error is None:
                    self.show_status("Plik renata_modules_data.json wygenerowany poprawnie.")
                else:
                    self.show_status(f"Blad generowania danych modulow: {error}")

            try:
                self.root.after(0, done)
            except Exception as exc:
                _log_app_fallback(
                    "modules.generate.callback",
                    "failed to schedule modules generation callback on UI thread",
                    exc,
                )
                done()

        threading.Thread(target=worker, daemon=True).start()

