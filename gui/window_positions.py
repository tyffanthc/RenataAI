import config


def _get_positions() -> dict:
    cfg = config.get("window_positions", {})
    if not isinstance(cfg, dict):
        cfg = {}
    legacy = config.get("ui.popup_positions", {})
    if isinstance(legacy, dict):
        for key, val in legacy.items():
            if key not in cfg and isinstance(val, dict):
                cfg[key] = val
    return cfg


def _save_positions(data: dict) -> None:
    try:
        config.save({"window_positions": data})
    except Exception:
        pass


def _center_window(window, width: int, height: int) -> None:
    try:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
    except Exception:
        return
    x = max(0, int((sw - width) / 2))
    y = max(0, int((sh - height) / 2))
    window.geometry(f"+{x}+{y}")


def restore_window_geometry(window, key: str, *, include_size: bool = False) -> None:
    cfg = _get_positions()
    pos = cfg.get(key)
    if not isinstance(pos, dict):
        return
    try:
        x = int(pos.get("x"))
        y = int(pos.get("y"))
    except Exception:
        return

    window.update_idletasks()
    try:
        sw = window.winfo_screenwidth()
        sh = window.winfo_screenheight()
        cur_w = window.winfo_width()
        cur_h = window.winfo_height()
    except Exception:
        return

    w = cur_w
    h = cur_h
    if include_size:
        try:
            w = int(pos.get("w"))
            h = int(pos.get("h"))
        except Exception:
            w = cur_w
            h = cur_h

    if x < 0 or y < 0 or x > sw - 40 or y > sh - 40:
        _center_window(window, w, h)
        return

    if include_size and w and h:
        window.geometry(f"{w}x{h}+{x}+{y}")
    else:
        window.geometry(f"+{x}+{y}")


def save_window_geometry(window, key: str, *, include_size: bool = False) -> None:
    try:
        x = int(window.winfo_x())
        y = int(window.winfo_y())
        w = int(window.winfo_width())
        h = int(window.winfo_height())
    except Exception:
        return
    data = _get_positions()
    entry = {"x": x, "y": y}
    if include_size:
        entry["w"] = w
        entry["h"] = h
    data[key] = entry
    _save_positions(data)


def bind_window_geometry(window, key: str, *, include_size: bool = False, delay_ms: int = 300) -> None:
    def _schedule(_event=None):
        job = getattr(window, "_renata_geo_job", None)
        if job:
            try:
                window.after_cancel(job)
            except Exception:
                pass
        window._renata_geo_job = window.after(  # type: ignore[attr-defined]
            delay_ms,
            lambda: save_window_geometry(window, key, include_size=include_size),
        )

    window.bind("<Configure>", _schedule, add="+")
