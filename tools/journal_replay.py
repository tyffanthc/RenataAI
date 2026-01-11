import os
import sys
import time
import json

import config
from logic.event_handler import handler
from logic.events.files import status_path, market_path


def replay_journal(path: str) -> None:
    """Odtwarza plik Journal.*.log linia po linii.

    Dla każdego eventu:
    - jeśli jest typu Status, zapisuje go do Status.json (status_path()),
    - jeśli jest typu Market, zapisuje go do Market.json (market_path()),
    - przekazuje surową linię do EventHandlera (handler.handle_event).

    Narzędzie pomocnicze do debugowania / testów bez odpalania gry.
    """
    if not os.path.exists(path):
        print(f"[ERROR] Brak pliku: {path}")
        return

    # Na wszelki wypadek wyłącz głos (nie chcemy TTS przy testach)
    # Zachowujemy kompatybilność ze starą strukturą config.SETTINGS,
    # jeśli nadal istnieje.
    try:
        if hasattr(config, "SETTINGS"):
            config.SETTINGS["VOICE"] = False
    except Exception:
        pass

    # Upewnij się, że katalog logów istnieje (na potrzeby Status/Market.json)
    log_dir = config.get("log_dir")
    os.makedirs(log_dir, exist_ok=True)

    print("=== RENATA - JOURNAL REPLAY ===")
    print(f"Plik: {path}")
    print("-" * 40)

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                print(f"[WARN] Nieprawidłowy JSON: {line}")
                continue

            # Symulacja zapisania Status/Market jeśli event ich dotyczy
            if ev.get("event") == "Status":
                try:
                    with open(status_path(), "w", encoding="utf-8") as sf:
                        json.dump(ev, sf, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"[WARN] Nie udało się zapisać Status.json: {e}")

            if ev.get("event") == "Market":
                try:
                    with open(market_path(), "w", encoding="utf-8") as mf:
                        json.dump(ev, mf, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"[WARN] Nie udało się zapisać Market.json: {e}")

            # --- PRZEKAZANIE EVENTU DO HANDLERA ---
            handler.handle_event(line, gui_ref=None)

            # Minimalne opóźnienie dla czytelności logu
            time.sleep(0.01)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python -m tools.journal_replay C:\\ścieżka\\do\\Journal.log")
        sys.exit(1)

    replay_journal(sys.argv[1])
