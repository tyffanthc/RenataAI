import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Dict, Any

from gui.tabs.settings import SettingsTab
from config import config  # <-- nowy manager konfiguracji


class SettingsWindow(tk.Toplevel):
    """
    Okno pop-up z ustawieniami Renaty.
    W środku używa istniejącego SettingsTab (scrollowalny kokpit opcji).

    Nowa logika:
    - domyślnie korzysta z ConfigManagera (config.get / config.save),
    - nadal pozwala wstrzyknąć własne get_config/save_config (np. do testów),
      ale jeśli nie podasz – bierze wartości z config.
    """

    def __init__(
        self,
        master: tk.Tk,
        *,
        controller: object,
        get_config: Optional[Callable[[], Dict[str, Any]]] = None,
        save_config: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)

        self.title("Konfiguracja Systemów R.E.N.A.T.A.")
        self.configure(bg="#0b0c10")

        self.on_close = on_close
        self._external_get_config = get_config
        self._external_save_config = save_config

        # --- zachowanie modalne + nad głównym oknem ---
        self.transient(master)
        self.grab_set()
        #self.wm_attributes("-topmost", False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # kontener dla SettingsTab
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        # SettingsTab dostaje callable, które czytają/zapisują JSON przez ConfigManagera
        self.settings_tab = SettingsTab(
            container,
            controller=controller,
            get_config=self._get_config_wrapper,
            save_config=self._save_config_wrapper,
        )
        self.settings_tab.pack(fill="both", expand=True)
        self._restore_popup_position("settings_window")
        self._bind_popup_position("settings_window")

    # ------------------------------------------------------------------ #
    #  Adaptery: SettingsTab -> ConfigManager
    # ------------------------------------------------------------------ #

    def _get_config_wrapper(self) -> Dict[str, Any]:
        """
        Funkcja przekazywana do SettingsTab jako get_config.
        - jeśli ktoś wstrzyknął własne get_config, używamy jego,
        - w przeciwnym razie zwracamy config.as_dict().
        """
        if self._external_get_config is not None:
            try:
                return self._external_get_config()
            except Exception:
                pass
        return config.as_dict()

    def _save_config_wrapper(self, data: Dict[str, Any]) -> None:
        """
        Funkcja przekazywana do SettingsTab jako save_config.
        Zapisuje ustawienia przez ConfigManagera + pokazuje messagebox „Zapisano”.
        Jeśli ktoś podał własne save_config – wywołujemy je dodatkowo.
        """
        # 1. Najpierw centralny zapis do JSON-a
        try:
            config.save(data)
        except Exception as e:
            messagebox.showerror(
                "R.E.N.A.T.A. – błąd zapisu",
                f"Nie udało się zapisać ustawień:\n{e}",
                parent=self,
            )
            return

        # 2. Opcjonalny callback zewnętrzny (np. do odświeżenia GUI)
        if self._external_save_config is not None:
            try:
                self._external_save_config(data)
            except Exception:
                # nie blokujemy usera, jeśli callback się wywali
                pass

        # 3. Potwierdzenie dla użytkownika
        messagebox.showinfo(
            "R.E.N.A.T.A.",
            "Zapisano ustawienia.",
            parent=self,
        )

    # ------------------------------------------------------------------ #

    def _on_close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass

        if self.on_close is not None:
            try:
                self.on_close()
            except Exception:
                pass

        self.destroy()

    def _get_popup_positions(self) -> Dict[str, Any]:
        cfg = config.get("ui.popup_positions", {})
        if not isinstance(cfg, dict):
            return {}
        return cfg

    def _save_popup_position(self, key: str, x: int, y: int) -> None:
        cfg = self._get_popup_positions()
        new_cfg = dict(cfg)
        new_cfg[key] = {"x": int(x), "y": int(y)}
        try:
            config.save({"ui.popup_positions": new_cfg})
        except Exception:
            pass

    def _restore_popup_position(self, key: str) -> None:
        cfg = self._get_popup_positions()
        pos = cfg.get(key)
        if not isinstance(pos, dict):
            return
        try:
            x = int(pos.get("x"))
            y = int(pos.get("y"))
        except Exception:
            return
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        if x < 0 or y < 0 or x > sw - 40 or y > sh - 40:
            return
        self.geometry(f"+{x}+{y}")

    def _bind_popup_position(self, key: str) -> None:
        def _on_configure(_event):
            try:
                x = self.winfo_x()
                y = self.winfo_y()
            except Exception:
                return
            self._save_popup_position(key, x, y)

        self.bind("<Configure>", _on_configure, add="+")
