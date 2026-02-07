# main.py (v90 - OPERACJA KABEL)

import tkinter as tk
import threading

from config import config        # <- bierzemy instancję ConfigManagera
from gui import RenataApp
from app.main_loop import MainLoop
from logic.utils import powiedz


if __name__ == "__main__":
    root = tk.Tk()
    app = RenataApp(root)

    powiedz("R.E.N.A.T.A. v90: startuję pętlę Journal...", app)

    # Ścieżka logów z JSON-a (user_settings.json)
    log_dir = config.get("log_dir")

    th = threading.Thread(
        target=MainLoop(app, log_dir).run,
        daemon=True,
    )
    th.start()

    root.mainloop()
