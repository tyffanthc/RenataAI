import tkinter as tk
from tkinter import ttk
import threading

from logic.utils import pobierz_sugestie
from gui.window_positions import restore_window_geometry, bind_window_geometry, save_window_geometry

COLOR_BG     = '#0b0c10'
COLOR_FG     = '#ff7100'
COLOR_SEC    = '#c5c6c7'
COLOR_ACCENT = '#1f2833'


class AddEntryDialog(tk.Toplevel):
    def __init__(self, parent, system=None, body=None, coords=None):
        super().__init__(parent)
        self.title("Dodaj wpis")
        self.configure(bg=COLOR_BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # kontekst z gry
        self.system = system
        self.body = body
        self.coords = coords

        # wynik po Zapisz
        self.result_data = None

        # stan do podpowiedzi Spansh
        self._last_query = ""
        self._suggest_lock = threading.Lock()
        self._coords_last_system = ""

        self._create_widgets()
        restore_window_geometry(self, "add_entry_dialog", include_size=True)
        bind_window_geometry(self, "add_entry_dialog", include_size=True)
        self._maybe_fetch_coords()

    def _create_widgets(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)

        # --- Tytuł ---
        lbl_title = tk.Label(self, text="Tytuł", bg=COLOR_BG, fg=COLOR_FG)
        lbl_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.entry_title = tk.Entry(
            self,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        self.entry_title.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10)

        # --- Treść ---
        lbl_content = tk.Label(self, text="Treść", bg=COLOR_BG, fg=COLOR_FG)
        lbl_content.grid(row=2, column=0, sticky="w", padx=10, pady=(10, 0))

        self.text_content = tk.Text(
            self,
            height=8,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        self.text_content.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=10)
        self.rowconfigure(3, weight=1)

        # --- Sekcja lokalizacji ---
        lbl_loc = tk.Label(self, text="Lokalizacja", bg=COLOR_BG, fg=COLOR_SEC)
        lbl_loc.grid(row=4, column=0, sticky="w", padx=10, pady=(10, 0))

        # System (z podpowiedziami Spansh)
        lbl_sys = tk.Label(self, text="System:", bg=COLOR_BG, fg=COLOR_FG)
        lbl_sys.grid(row=5, column=0, sticky="w", padx=10)

        # Combobox, styl i readonly
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("Orange.TCombobox",
                        fieldbackground=COLOR_ACCENT,
                        background=COLOR_ACCENT,
                        foreground=COLOR_FG)
        self.entry_system = ttk.Combobox(self, state="readonly")
        self.entry_system.configure(style="Orange.TCombobox")
        self.entry_system.grid(row=5, column=1, sticky="ew", padx=10)
        self.entry_system.set(self.system or "")

        # bind do Spansh-autocomplete
        self.entry_system.bind("<KeyRelease>", self._on_system_key)
        self.entry_system.bind("<<ComboboxSelected>>", self._on_system_selected)

        # Ciało
        lbl_body = tk.Label(self, text="Ciało:", bg=COLOR_BG, fg=COLOR_FG)
        lbl_body.grid(row=6, column=0, sticky="w", padx=10)

        self.entry_body = tk.Entry(
            self,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        self.entry_body.grid(row=6, column=1, sticky="ew", padx=10)
        self.entry_body.insert(0, self.body or "")

        # Współrzędne
        lbl_coords = tk.Label(self, text="Współrzędne:", bg=COLOR_BG, fg=COLOR_FG)
        lbl_coords.grid(row=7, column=0, sticky="w", padx=10)

        self.entry_coords = tk.Entry(
            self,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            insertbackground=COLOR_FG,
            relief="flat",
        )
        self.entry_coords.grid(row=7, column=1, sticky="ew", padx=10)
        self.entry_coords.insert(0, self.coords or "")

        self.lbl_coords_status = tk.Label(self, text="", bg=COLOR_BG, fg=COLOR_SEC)
        self.lbl_coords_status.grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 0))

        # --- Przyciski ---
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.grid(row=9, column=0, columnspan=2, pady=10)

        btn_save = tk.Button(
            btn_frame,
            text="Zapisz",
            command=self._on_save,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            activebackground=COLOR_FG,
            activeforeground=COLOR_BG,
            relief="flat",
            padx=10,
        )
        btn_save.pack(side="left", padx=(0, 10))

        btn_cancel = tk.Button(
            btn_frame,
            text="Anuluj",
            command=self._on_cancel,
            bg=COLOR_ACCENT,
            fg=COLOR_FG,
            activebackground=COLOR_FG,
            activeforeground=COLOR_BG,
            relief="flat",
            padx=10,
        )
        btn_cancel.pack(side="left")

    # --------------------------------------------------
    #  Spansh autocomplete dla pola "System"
    # --------------------------------------------------
    def _on_system_key(self, event=None):
        """
        Wołane przy każdej zmianie tekstu w polu System.
        Dla krótkich stringów nic nie robi, dla dłuższych odpala
        zapytanie do Spansh w osobnym wątku.
        """
        text = self.entry_system.get().strip()
        if len(text) < 2:
            return

        # prosta histereza: jeśli tekst się nie zmienił – nie spamujemy API
        with self._suggest_lock:
            if text == self._last_query:
                return
            self._last_query = text

        threading.Thread(
            target=self._fetch_spansh_suggestions, args=(text,), daemon=True
        ).start()

    def _fetch_spansh_suggestions(self, query: str):
        try:
            raw = pobierz_sugestie(query)
        except Exception:
            return

        names = raw if isinstance(raw, list) else []
        if not names:
            return

        # aktualizacja GUI musi być w wątku głównym
        self.after(0, self._apply_suggestions, names)

    def _apply_suggestions(self, names: list[str]):
        try:
            self.entry_system['values'] = names
            if names:
                self.entry_system.configure(state="readonly")
        except:
            pass

    # --------------------------------------------------
    #  EDSM fallback dla wspolrzednych
    # --------------------------------------------------
    def _set_coords_status(self, text: str, error: bool = False) -> None:
        try:
            color = "#ff5555" if error else COLOR_SEC
            self.lbl_coords_status.config(text=text, fg=color)
        except Exception:
            pass

    def _on_system_selected(self, event=None):
        self._maybe_fetch_coords()

    def _maybe_fetch_coords(self):
        system = self.entry_system.get().strip()
        coords = self.entry_coords.get().strip()
        if not system or (coords and coords != "-"):
            return
        if system == self._coords_last_system:
            return
        try:
            from logic.utils.http_edsm import is_edsm_enabled
        except Exception:
            return
        if not is_edsm_enabled():
            return

        self._coords_last_system = system
        self._set_coords_status("Pobieranie danych z EDSM...")
        threading.Thread(target=self._fetch_coords, args=(system,), daemon=True).start()

    def _fetch_coords(self, system: str):
        try:
            from logic.utils.edsm_provider import lookup_system, get_last_reason
        except Exception:
            return
        info = lookup_system(system)
        if info:
            coords = f"X: {info.x:.2f}, Y: {info.y:.2f}, Z: {info.z:.2f}"
            self.after(0, self._apply_coords, coords)
            return

        reason = get_last_reason()
        if reason in ("edsm_timeout", "edsm_unavailable", "edsm_bad_response", "edsm_error"):
            self.after(0, self._set_coords_status, "Nie udalo sie pobrac danych online.", True)
        elif reason == "edsm_not_found":
            self.after(0, self._set_coords_status, "Brak danych systemu w EDSM.", False)
        else:
            self.after(0, self._set_coords_status, "", False)

    def _apply_coords(self, coords: str):
        try:
            self.entry_coords.delete(0, "end")
            self.entry_coords.insert(0, coords)
            self._set_coords_status("Wspolrzedne uzupelnione z EDSM.", False)
        except Exception:
            pass

    # --------------------------------------------------
    #  Obsługa przycisków
    # --------------------------------------------------
    def _on_save(self):
        title = self.entry_title.get().strip()
        content = self.text_content.get("1.0", "end").strip()

        system = self.entry_system.get().strip()
        body = self.entry_body.get().strip()
        coords = self.entry_coords.get().strip()

        self.result_data = {
            "title": title,
            "content": content,
            "system": system,
            "body": body,
            "coords": coords,
        }
        save_window_geometry(self, "add_entry_dialog", include_size=True)
        self.destroy()

    def _on_cancel(self):
        self.result_data = None
        save_window_geometry(self, "add_entry_dialog", include_size=True)
        self.destroy()
