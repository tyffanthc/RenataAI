import tkinter as tk
from tkinter import ttk, messagebox
import config
from logic import utils
from gui import common
from gui.tabs import pulpit, engineer
from gui.tabs import spansh
from gui.menu_bar import RenataMenuBar
from gui.tabs.settings_window import SettingsWindow
from gui.tabs.logbook import LogbookTab
import webbrowser
from logic.generate_renata_science_data import generate_science_excel
from app.state import app_state
from app.route_manager import route_manager
import threading
from logic.science_data import load_science_data


class RenataApp:
    def __init__(self, root):  # <--- ZAUWAŻ WCIĘCIE (TAB)
        self.root = root
        self.root.title("R.E.N.A.T.A.")
        self.root.geometry("1100x700")

        # ==========================================================
        # 🎨 RENATA "BLACKOUT" PROTOCOL - STYLIZACJA TOTALNA
        # ==========================================================
        
        # 1. Definicja Palety (Żeby łatwo zmieniać)
        C_BG = "#0b0c10"       # Głęboka czerń (Tło)
        C_FG = "#ff7100"       # Elite Orange (Tekst)
        C_SEC = "#c5c6c7"      # Szary (Tekst pomocniczy)
        C_ACC = "#1f2833"      # Ciemnoszary (Belki, tła inputów)

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
        except:
            pass

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

        # Scrollbary (Paski przewijania)
        style.configure("Vertical.TScrollbar", background=C_ACC, troughcolor=C_BG, borderwidth=0, arrowcolor=C_FG)
        style.configure("Horizontal.TScrollbar", background=C_ACC, troughcolor=C_BG, borderwidth=0, arrowcolor=C_FG)

        # ==========================================================
        # KONIEC PROTOKOŁU BLACKOUT
        # ==========================================================

        # =========================
        # GŁÓWNY NOTEBOOK
        # =========================
        self.main_nb = ttk.Notebook(self.root)
        self.main_nb.pack(fill="both", expand=1)
        self.main_nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # --- Pulpit ---
        self.tab_pulpit = pulpit.PulpitTab(
            self.main_nb,
            on_generate_science_excel=self.on_generate_science_excel,
            app_state=app_state,
            route_manager=route_manager,
        )
        self.main_nb.add(self.tab_pulpit, text="Pulpit")

        # --- SPANSH ---
        self.tab_spansh = spansh.SpanshTab(self.main_nb, self.root)
        self.main_nb.add(self.tab_spansh, text="Spansh")

        # --- Inara (stub) ---
        self.tab_inara = ttk.Frame(self.main_nb)
        self.main_nb.add(self.tab_inara, text="Inara")
        ttk.Label(
            self.tab_inara,
            text="Moduł Inara - Wkrótce",
            font=("Arial", 14),
        ).pack(pady=50)

        # --- EDTools (stub) ---
        self.tab_edtools = ttk.Frame(self.main_nb)
        self.main_nb.add(self.tab_edtools, text="EDTools")
        ttk.Label(
            self.tab_edtools,
            text="Moduł EDTools - Wkrótce",
            font=("Arial", 14),
        ).pack(pady=50)

        # --- Inżynier ---
        self.tab_engi = engineer.EngineerTab(self.main_nb, self)
        self.main_nb.add(self.tab_engi, text="Inżynier")

        # --- Dziennik ---
        from logic.logbook_manager import LogbookManager
        self.logbook_manager = LogbookManager()
        self.tab_journal = LogbookTab(self.main_nb, app=self, manager=self.logbook_manager)
        self.main_nb.add(self.tab_journal, text="Dziennik")

        # Mapa kluczy -> zakładek (do obsługi menu "Nawigacja")
        self._tab_map = {
            "pulpit": self.tab_pulpit,
            "spansh": self.tab_spansh,
            "inara": self.tab_inara,
            "edtools": self.tab_edtools,
            "engineer": self.tab_engi,
            "journal": self.tab_journal,
        }

        # =========================
        # PASEK MENU
        # =========================
        self.menu_bar = RenataMenuBar(
            self.root,
            on_quit=self.root.quit,
            on_open_settings=self._open_settings_window,
            on_show_about=self._show_about_stub,
            on_switch_tab=self._switch_tab,
            on_toggle_always_on_top=self.on_toggle_always_on_top,
            on_open_link=self.on_open_link,
            tab_labels={
                "pulpit": "Pulpit",
                "spansh": "Spansh",
                "engineer": "Inżynier",
                "inara": "Inara",
                "edtools": "EDTools",
                "journal": "Dziennik",
            },
        )
        self.root.config(menu=self.menu_bar)

        # =========================
        # DANE NAUKOWE (S2-LOGIC-01)
        # =========================
        self.exobio_df = None
        self.carto_df = None
        self.science_data_loaded: bool = False

        # próba wczytania danych przy starcie
        self._try_load_science_data()

        # =========================
        # BINDY I PĘTLA KOLEJKI
        # =========================
        self.root.bind("<Button-1>", self.check_focus)
        self.root.bind("<Configure>", self.on_window_move)
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

    def _show_about_stub(self):
        import tkinter.messagebox as mbox
        mbox.showinfo(
            "O programie",
            "R.E.N.A.T.A. AI v90\nFrontend cockpit edition.\n"
            "Ten dialog to tylko placeholder – backend sobie go kiedyś dopieści. :)"
        )

    # ------------------------------------------------------------------ #
    #   Okno ustawień (Konfiguracja Systemów R.E.N.A.T.A.)
    # ------------------------------------------------------------------ #

    def _open_settings_window(self) -> None:
        """
        Otwiera nowe okno SettingsWindow jako modalne.
        Jeśli już jest otwarte – tylko je podnosi.
        """
        existing = getattr(self, "_settings_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_set()
                return
        except Exception:
            # jeśli coś poszło nie tak – traktujemy jakby okna nie było
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

    # ------------------------------------------------------------------ #
    #   Dane naukowe (Exobiology / Cartography)
    # ------------------------------------------------------------------ #

    def _try_load_science_data(self) -> None:
        """
        Próbuje wczytać arkusze naukowe z Excela.
        Utrzymuje prawdę o stanie w self.science_data_loaded
        i aktualizuje GUI (SettingsTab), jeśli to możliwe.
        """
        try:
            self.exobio_df, self.carto_df = load_science_data("renata_science_data.xlsx")
            self.science_data_loaded = True
            self.show_status("Dane naukowe załadowane poprawnie.")
        except Exception:
            self.exobio_df = None
            self.carto_df = None
            self.science_data_loaded = False
            # łagodny komunikat – szczegół błędu nie musi iść do usera
            self.show_status("Dane naukowe NIE są dostępne – wygeneruj arkusze.")
            # jeśli chcesz debug:
            # self.show_status(f"Szczegóły błędu danych naukowych: {e}")

        # powiadom GUI (Opcje), jeśli ma odpowiednią metodę
        if getattr(self, "settings_tab", None) is not None:
            if hasattr(self.settings_tab, "update_science_status"):
                try:
                    self.settings_tab.update_science_status(self.science_data_loaded)
                except Exception:
                    pass

    def is_science_data_available(self) -> bool:
        """
        Zwraca True, jeśli arkusze naukowe zostały poprawnie wczytane.
        """
        return bool(self.science_data_loaded)

    # ------------------------------------------------------------------ #
    #   Reszta Twojego kodu bez zmian
    # ------------------------------------------------------------------ #

    def check_focus(self, e):
        if hasattr(self.tab_spansh, 'hide_suggestions'):
            w = e.widget
            if "listbox" not in str(w).lower() and "entry" not in str(w).lower():
                self.tab_spansh.hide_suggestions()

    def on_window_move(self, event):
        if hasattr(self.tab_spansh, 'hide_suggestions'):
            self.tab_spansh.hide_suggestions()

    def check_queue(self):
        try:
            while True:
                msg_type, content = utils.MSG_QUEUE.get_nowait()

                if msg_type == "log":
                    self.tab_pulpit.log(content)

                elif msg_type == "status_neu":
                    txt, col = content
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

                elif msg_type == "start_label":
                    self.tab_spansh.update_start_label(content)

        except Exception:
            pass
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
        except Exception:
            print(msg)

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
                generate_science_excel("renata_science_data.xlsx")
            except Exception as e:
                error = str(e)

            def done():
                # reload danych
                self._try_load_science_data()

                # komunikat końcowy
                if error is None:
                    self.show_status("Plik renata_science_data.xlsx wygenerowany poprawnie.")
                else:
                    self.show_status(f"Błąd generowania danych naukowych: {error}")

            # wykonujemy done() w głównym wątku Tkintera
            try:
                self.root.after(0, done)
            except Exception:
                done()

        threading.Thread(target=worker, daemon=True).start()
