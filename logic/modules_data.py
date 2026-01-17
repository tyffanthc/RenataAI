from __future__ import annotations

import json
from typing import Any, Dict


def load_modules_data(path: str) -> Dict[str, Any]:
    """
    Laduje dane modulow z pliku JSON i waliduje podstawowa kompletosc.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("modules_data: niepoprawny format (nie dict)")

    if data.get("version") != "v1":
        raise ValueError("modules_data: nieznana wersja")

    fsd = data.get("fsd")
    booster = data.get("guardian_fsd_booster")
    if not isinstance(fsd, list) or not fsd:
        raise ValueError("modules_data: brak danych FSD")
    if not isinstance(booster, list) or not booster:
        raise ValueError("modules_data: brak danych booster")

    return data
