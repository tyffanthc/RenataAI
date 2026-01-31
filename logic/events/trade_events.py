from __future__ import annotations

from typing import Any

import config
from logic.utils import powiedz
from logic import utils
from app.state import app_state

# --- MAKLER PRO (S2-LOGIC-06) ---
JACKPOT_WARNED_STATIONS = set()
JACKPOT_DEFAULT = {}
JACKPOT_CACHE = set()


def handle_market_data(data: dict, gui_ref=None):
    """
    CZYSTA FUNKCJA GAMEPLAY (Etap B1)
    ---------------------------------
    Przyjmuje dict `data` (odpowiednik Market.json).
    Zero I/O. Zero wczytywania plików.

    Logika 1:1 z handle_market (bez I/O).
    """

    if not config.get("trade_jackpot_speech", True):
        return

    if not isinstance(data, dict):
        return

    items = data.get("Items") or data.get("items") or []
    if not isinstance(items, list):
        return

    station_name = (
        data.get("StationName")
        or data.get("stationName")
        or data.get("Name")
        or "UNKNOWN_STATION"
    )

    system_name = app_state.current_system or data.get("StarSystem") or "UNKNOWN_SYSTEM"

    global JACKPOT_WARNED_STATIONS, JACKPOT_DEFAULT, JACKPOT_CACHE

    jackpot_cfg = config.get("jackpot_thresholds", JACKPOT_DEFAULT)

    thresholds = {
        str(name).lower(): int(val)
        for name, val in jackpot_cfg.items()
        if isinstance(val, (int, float))
    }

    if not thresholds:
        return

    station_key = (system_name, station_name)
    if station_key in JACKPOT_WARNED_STATIONS:
        return

    # SZUKAMY JACKPOTU
    for item in items:
        if not isinstance(item, dict):
            continue

        raw_name = item.get("Name_Localised") or item.get("Name") or ""
        if not raw_name:
            continue

        name_clean = str(raw_name).strip()
        key = name_clean.lower()

        if key not in thresholds:
            continue

        # Realna obecność towaru
        try:
            stock_val = int(item.get("Stock") or 0)
        except Exception:
            stock_val = 0

        if stock_val <= 0:
            continue

        try:
            buy_price_val = int(item.get("BuyPrice") or 0)
        except Exception:
            buy_price_val = 0

        if buy_price_val <= 0:
            continue

        jackpot_threshold = thresholds[key]

        # Czy mamy jackpot?
        if buy_price_val < jackpot_threshold:
            jackpot_key = (system_name, station_name, key, buy_price_val)

            # Antyspam (cache)
            if jackpot_key in JACKPOT_CACHE:
                continue

            JACKPOT_CACHE.add(jackpot_key)
            JACKPOT_WARNED_STATIONS.add(station_key)

            msg = (
                f"Komandorze, {name_clean} jest tu wyjątkowo tanie. "
                f"To świetna okazja. Cena: {buy_price_val} kredytów."
            )
            powiedz(
                msg,
                gui_ref,
                message_id="MSG.TRADE_JACKPOT",
                context={"raw_text": msg},
            )

            try:
                utils.MSG_QUEUE.put(
                    (
                        "log",
                        f"[MAKLER PRO] JACKPOT na stacji {station_name}: "
                        f"{name_clean} @ {buy_price_val} Cr",
                    )
                )
            except Exception:
                pass

            break
