from __future__ import annotations

from typing import Dict, Set


# Centralny rejestr template'ów TTS.
# `raw_text_first=True` oznacza: jeśli context ma `raw_text`, preprocessor
# powinien preferować ten tekst (po naprawie kodowania/diakrytyków).
TTS_TEMPLATE_REGISTRY: Dict[str, dict[str, object]] = {
    "MSG.NEXT_HOP": {"template": "Następny skok. {system}.", "raw_text_first": False},
    "MSG.JUMPED_SYSTEM": {"template": "Aktualnie w {system}.", "raw_text_first": False},
    "MSG.NEXT_HOP_COPIED": {"template": "Cel skopiowany. {system}.", "raw_text_first": False},
    "MSG.ROUTE_COMPLETE": {"template": "Trasa zakończona.", "raw_text_first": False},
    "MSG.ROUTE_DESYNC": {"template": "Poza trasą. Nawigacja wstrzymana.", "raw_text_first": False},
    "MSG.FUEL_CRITICAL": {"template": "Uwaga. Paliwo krytyczne.", "raw_text_first": False},
    "MSG.DOCKED": {"template": "Zadokowano. {station}.", "raw_text_first": False},
    "MSG.UNDOCKED": {"template": "Odlot potwierdzony.", "raw_text_first": False},
    "MSG.FIRST_DISCOVERY": {"template": "Pierwsze odkrycie. Układ potwierdzony.", "raw_text_first": False},
    "MSG.FIRST_DISCOVERY_OPPORTUNITY": {
        "template": "Wygląda na okazję pierwszego odkrycia. Czekam na potwierdzenie.",
        "raw_text_first": False,
    },
    "MSG.BODY_NO_PREV_DISCOVERY": {
        "template": "Potwierdzono. To ciało nie ma wcześniejszego odkrywcy.",
        "raw_text_first": False,
    },
    "MSG.SYSTEM_FULLY_SCANNED": {"template": "Skan systemu zakończony.", "raw_text_first": False},
    "MSG.ELW_DETECTED": {"template": "Wykryto planetę ziemiopodobną. Wysoka wartość.", "raw_text_first": True},
    "MSG.FOOTFALL": {"template": "Pierwszy krok zarejestrowany.", "raw_text_first": False},
    "MSG.ROUTE_FOUND": {"template": "Trasa wyznaczona.", "raw_text_first": False},
    "MSG.SMUGGLER_ILLEGAL_CARGO": {
        "template": "Uwaga. Nielegalny ładunek na pokładzie.",
        "raw_text_first": True,
    },
    "MSG.WW_DETECTED": {"template": "Wykryto świat wodny. Wysoka wartość.", "raw_text_first": True},
    "MSG.TERRAFORMABLE_DETECTED": {
        "template": "Wykryto planetę terraformowalną. Wysoka wartość.",
        "raw_text_first": True,
    },
    "MSG.BIO_SIGNALS_HIGH": {"template": "Wykryto wiele sygnałów biologicznych.", "raw_text_first": True},
    "MSG.DSS_TARGET_HINT": {"template": "Cel jest wart mapowania DSS.", "raw_text_first": True},
    "MSG.DSS_COMPLETED": {"template": "Mapowanie DSS zakończone.", "raw_text_first": True},
    "MSG.DSS_PROGRESS": {"template": "Postęp mapowania DSS zaktualizowany.", "raw_text_first": True},
    "MSG.FIRST_MAPPED": {"template": "Pierwsze mapowanie potwierdzone.", "raw_text_first": True},
    "MSG.TRADE_JACKPOT": {"template": "Wykryto silny sygnał handlowy.", "raw_text_first": True},
    "MSG.EXOBIO_SAMPLE_LOGGED": {"template": "Próbka biologiczna zapisana.", "raw_text_first": True},
    "MSG.EXOBIO_NEW_ENTRY": {"template": "Nowy wpis biologiczny dodany.", "raw_text_first": True},
    "MSG.EXOBIO_RANGE_READY": {"template": "Dystans do kolejnej próbki gotowy.", "raw_text_first": True},
    "MSG.FSS_PROGRESS_25": {"template": "Dwadzieścia pięć procent systemu przeskanowane.", "raw_text_first": False},
    "MSG.FSS_PROGRESS_50": {"template": "Połowa systemu przeskanowana.", "raw_text_first": False},
    "MSG.FSS_PROGRESS_75": {"template": "Siedemdziesiąt pięć procent systemu przeskanowane.", "raw_text_first": False},
    "MSG.FSS_LAST_BODY": {"template": "Ostatnia planeta do skanowania.", "raw_text_first": False},
    "MSG.EXPLORATION_SYSTEM_SUMMARY": {"template": "Podsumowanie eksploracji gotowe.", "raw_text_first": True},
    "MSG.EXPLORATION_AWARENESS_SUMMARY": {"template": "Podsumowanie uwag eksploracyjnych gotowe.", "raw_text_first": True},
    "MSG.CASH_IN_ASSISTANT": {"template": "Cash-in. Sprawdź decyzje w panelu.", "raw_text_first": True},
    "MSG.CASH_IN_STARTJUMP": {"template": "Cash-in. Punkt kontrolny danych gotowy.", "raw_text_first": True},
    "MSG.SURVIVAL_REBUY_HIGH": {
        "template": "Ryzyko przetrwania wzrosło. Sprawdź opcje w panelu.",
        "raw_text_first": True,
    },
    "MSG.SURVIVAL_REBUY_CRITICAL": {
        "template": "Brak rebuy albo krytyczne ryzyko utraty postępu.",
        "raw_text_first": True,
    },
    "MSG.COMBAT_AWARENESS_HIGH": {"template": "Wzorzec ryzyka bojowego jest aktywny.", "raw_text_first": True},
    "MSG.COMBAT_AWARENESS_CRITICAL": {"template": "Wzorzec ryzyka bojowego jest krytyczny.", "raw_text_first": True},
    "MSG.HIGH_G_WARNING": {
        "template": "Wykryto wysokie przeciążenie grawitacyjne. Ogranicz opadanie.",
        "raw_text_first": True,
    },
    "MSG.TRADE_DATA_STALE": {
        "template": "Dane rynkowe są nieświeże. Traktuj wynik orientacyjnie.",
        "raw_text_first": True,
    },
    "MSG.PPM_SET_TARGET": {"template": "Ustawiono cel.", "raw_text_first": True},
    "MSG.PPM_PIN_ACTION": {"template": "Zmieniono przypięcie wpisu.", "raw_text_first": True},
    "MSG.PPM_COPY_SYSTEM": {"template": "Skopiowano system.", "raw_text_first": True},
    "MSG.RUNTIME_CRITICAL": {
        "template": "Wykryto błąd krytyczny runtime. Sprawdź panel statusu.",
        "raw_text_first": True,
    },
    "MSG.MILESTONE_PROGRESS": {"template": "Trwa lot do kolejnego odcinka trasy.", "raw_text_first": False},
    "MSG.MILESTONE_REACHED": {"template": "Cel odcinka osiągnięty.", "raw_text_first": False},
    "MSG.STARTUP_SYSTEMS": {"template": "Renata. Startuję wszystkie systemy.", "raw_text_first": False},
}


def allowed_message_ids() -> Set[str]:
    return set(TTS_TEMPLATE_REGISTRY.keys())


def raw_text_first(message_id: str) -> bool:
    row = TTS_TEMPLATE_REGISTRY.get(str(message_id or ""))
    if not isinstance(row, dict):
        return False
    return bool(row.get("raw_text_first"))


def template_for_message(message_id: str) -> str:
    row = TTS_TEMPLATE_REGISTRY.get(str(message_id or ""))
    if not isinstance(row, dict):
        return ""
    return str(row.get("template") or "")
