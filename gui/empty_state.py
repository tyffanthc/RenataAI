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


def _detect_treeview_header_height(tree: ttk.Treeview) -> int:
    try:
        tree.update_idletasks()
    except Exception:
        return 24
    try:
        height = int(tree.winfo_height())
    except Exception:
        return 24
    if height <= 1:
        return 24
    limit = max(1, min(96, height - 1))
    probe_x = 8
    for y in range(limit):
        try:
            region = tree.identify_region(probe_x, y)
        except Exception:
            region = ""
        if region and region != "heading":
            return max(1, y)
    return 24


def _place_overlay(target, overlay, display_mode: str) -> None:
    if isinstance(target, ttk.Treeview) and display_mode == "overlay_body":
        header_h = _detect_treeview_header_height(target)
        overlay.place(
            in_=target,
            x=0,
            y=header_h,
            relwidth=1,
            relheight=1,
            height=-header_h,
        )
    else:
        overlay.place(in_=target, x=0, y=0, relwidth=1, relheight=1)
    try:
        overlay.lift()
    except Exception:
        pass


def _refresh_overlay_geometry(target) -> None:
    if not bool(getattr(target, "_renata_state_visible", False)):
        return
    mode = getattr(target, "_renata_state_display_mode", None)
    if mode != "overlay_body":
        return
    overlay = getattr(target, "_renata_state_overlay", None)
    if overlay is None:
        return
    try:
        if not overlay.winfo_exists():
            return
    except Exception:
        return
    _place_overlay(target, overlay, mode)


def show_state(
    target,
    kind: str,
    title: str,
    message: str,
    *,
    display_mode: str = "replace",
) -> None:
    container = _resolve_container(target)
    if not title and not message:
        hide_state(target)
        return

    if display_mode == "overlay_body":
        overlay = getattr(target, "_renata_state_overlay", None)
        if overlay is None or not overlay.winfo_exists():
            overlay = ttk.Frame(target)
            title_label = ttk.Label(overlay, text="", font=("Arial", 10, "bold"))
            title_label.pack(anchor="center", pady=(16, 0))
            msg_label = ttk.Label(overlay, text="", font=("Arial", 9))
            msg_label.pack(anchor="center", pady=(2, 0))
            target._renata_state_overlay = overlay  # type: ignore[attr-defined]
            target._renata_state_title = title_label  # type: ignore[attr-defined]
            target._renata_state_message = msg_label  # type: ignore[attr-defined]
        else:
            title_label = getattr(target, "_renata_state_title", None)
            msg_label = getattr(target, "_renata_state_message", None)

        if title_label is not None:
            title_label.config(text=title)
        if msg_label is not None:
            msg_label.config(text=message or "")
            if message:
                msg_label.pack(anchor="center", pady=(2, 0))
            else:
                msg_label.pack_forget()

        _place_overlay(target, overlay, display_mode)
        if not bool(getattr(target, "_renata_state_overlay_bound", False)):
            target.bind(
                "<Configure>",
                lambda _ev, widget=target: _refresh_overlay_geometry(widget),
                add="+",
            )
            target._renata_state_overlay_bound = True  # type: ignore[attr-defined]

        target._renata_state_visible = True  # type: ignore[attr-defined]
        target._renata_state_kind = kind  # type: ignore[attr-defined]
        target._renata_state_display_mode = display_mode  # type: ignore[attr-defined]
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
    container._renata_state_display_mode = display_mode  # type: ignore[attr-defined]


def hide_state(target) -> None:
    mode = getattr(target, "_renata_state_display_mode", None)
    if mode == "overlay_body":
        overlay = getattr(target, "_renata_state_overlay", None)
        if overlay is not None:
            try:
                overlay.place_forget()
            except Exception:
                pass
        target._renata_state_visible = False  # type: ignore[attr-defined]
        return

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
