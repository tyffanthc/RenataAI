# main.py (v0.9.3 - FEEDBACK LOOP)

import threading
import tkinter as tk

from app.main_loop import MainLoop
from config import APP_VERSION, config
from gui import RenataApp
from logic.utils import powiedz


if __name__ == "__main__":
    root = tk.Tk()
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

    root.mainloop()
