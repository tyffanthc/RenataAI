# main.py (v0.9.5 - FEEDBACK LOOP)

import threading
import tkinter as tk

from app.main_loop import MainLoop
from config import APP_VERSION, config
from gui import RenataApp
from logic.utils import powiedz

MAIN_WINDOW_SHOW_DELAY_MS = 300


def _show_main_window_safe(root: tk.Tk) -> None:
    try:
        root.update_idletasks()
    except Exception:
        pass
    try:
        root.deiconify()
    except Exception:
        pass


def run() -> None:
    root = tk.Tk()
    # Avoid startup flicker while all tabs/widgets are being built.
    root.withdraw()
    app = RenataApp(root)

    startup_text = f"Renata {APP_VERSION}: startuje wszystkie systemy."
    powiedz(
        startup_text,
        app,
        message_id="MSG.STARTUP_SYSTEMS",
        context={"version": APP_VERSION},
        force=True,
    )

    # Sciezka logow z JSON-a (user_settings.json)
    log_dir = config.get("log_dir")

    th = threading.Thread(
        target=MainLoop(app, log_dir).run,
        daemon=True,
    )
    th.start()

    root.after(MAIN_WINDOW_SHOW_DELAY_MS, lambda: _show_main_window_safe(root))
    root.mainloop()


if __name__ == "__main__":
    run()
