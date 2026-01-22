from tkinter import ttk


class UIState:
    EMPTY = "empty"
    BUSY = "busy"
    ERROR = "error"
    INFO = "info"


MICROCOPY = {
    "pl": {
        "no_results": (
            "Brak wynikow dla obecnych ustawien.",
            "Sprobuj zmienic filtry lub zakres.",
        ),
        "filters_excluded": (
            "Filtry wykluczyly wszystkie wyniki.",
            "Poluzuj kryteria filtrowania.",
        ),
        "no_input": (
            "Brak danych wejsciowych.",
            "Wybierz punkt startowy i cel.",
        ),
        "busy_calculating": (
            "Obliczanie trasy...",
            "Prosze czekac.",
        ),
        "waiting_data": (
            "Oczekiwanie na dane...",
            "",
        ),
        "provider_off": (
            "Dane online sa wylaczone.",
            "Wlacz providera w ustawieniach.",
        ),
        "online_error": (
            "Nie udalo sie pobrac danych online.",
            "Sprawdz polaczenie lub sprobuj ponownie.",
        ),
        "route_empty": (
            "Trasa jest pusta.",
            "Brak punktow do wyswietlenia.",
        ),
        "route_completed": (
            "Trasa zakonczona.",
            "Brak kolejnych punktow.",
        ),
        "fallback": (
            "Wystapil problem, ale aplikacja dziala dalej.",
            "Sprawdz logi, jesli problem sie powtarza.",
        ),
    },
    "en": {
        "no_results": (
            "No results for the current settings.",
            "Try adjusting filters or range.",
        ),
        "filters_excluded": (
            "Filters excluded all results.",
            "Loosen filtering criteria.",
        ),
        "no_input": (
            "Missing input data.",
            "Select start and destination.",
        ),
        "busy_calculating": (
            "Calculating route...",
            "Please wait.",
        ),
        "waiting_data": (
            "Waiting for data...",
            "",
        ),
        "provider_off": (
            "Online data is disabled.",
            "Enable the provider in settings.",
        ),
        "online_error": (
            "Failed to fetch online data.",
            "Check your connection or try again.",
        ),
        "route_empty": (
            "Route is empty.",
            "No points to display.",
        ),
        "route_completed": (
            "Route completed.",
            "No further points.",
        ),
        "fallback": (
            "Something went wrong, but the app is still running.",
            "Check logs if the issue persists.",
        ),
    },
}


def get_copy(key: str, lang: str = "pl") -> tuple[str, str]:
    lang_map = MICROCOPY.get(lang) or MICROCOPY.get("pl", {})
    return lang_map.get(key, ("", ""))


def _resolve_container(target):
    return getattr(target, "_renata_state_container", None) or target


def show_state(target, kind: str, title: str, message: str) -> None:
    container = _resolve_container(target)
    if not title and not message:
        hide_state(target)
        return

    parent = container.master
    pack_info = getattr(container, "_renata_state_pack_info", None)
    if pack_info is None:
        try:
            pack_info = dict(container.pack_info())
            pack_info.pop("in", None)
            container._renata_state_pack_info = pack_info  # type: ignore[attr-defined]
        except Exception:
            pack_info = None

    frame = getattr(container, "_renata_state_frame", None)
    if frame is None or not frame.winfo_exists():
        frame = ttk.Frame(parent)
        title_label = ttk.Label(frame, text="", font=("Arial", 10, "bold"))
        title_label.pack(anchor="center")
        msg_label = ttk.Label(frame, text="", font=("Arial", 9))
        msg_label.pack(anchor="center", pady=(2, 0))
        container._renata_state_frame = frame  # type: ignore[attr-defined]
        container._renata_state_title = title_label  # type: ignore[attr-defined]
        container._renata_state_message = msg_label  # type: ignore[attr-defined]
    else:
        title_label = getattr(container, "_renata_state_title", None)
        msg_label = getattr(container, "_renata_state_message", None)

    if title_label is not None:
        title_label.config(text=title)
    if msg_label is not None:
        msg_label.config(text=message or "")
        if message:
            msg_label.pack(anchor="center", pady=(2, 0))
        else:
            msg_label.pack_forget()

    try:
        container.pack_forget()
    except Exception:
        pass

    try:
        if pack_info:
            frame.pack(**pack_info)
        else:
            frame.pack(fill="both", expand=True)
    except Exception:
        pass

    container._renata_state_visible = True  # type: ignore[attr-defined]
    container._renata_state_kind = kind  # type: ignore[attr-defined]


def hide_state(target) -> None:
    container = _resolve_container(target)
    frame = getattr(container, "_renata_state_frame", None)
    pack_info = getattr(container, "_renata_state_pack_info", None)
    if frame is not None:
        try:
            frame.pack_forget()
        except Exception:
            pass
    try:
        if pack_info:
            container.pack(**pack_info)
        else:
            container.pack(fill="both", expand=True)
    except Exception:
        pass
    container._renata_state_visible = False  # type: ignore[attr-defined]
