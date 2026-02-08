from logic.spansh_client import HEADERS, client as spansh_client
from logic.utils.http_edsm import edsm_systems_suggest, is_edsm_enabled


def pobierz_sugestie(tekst: str):
    """
    Kompatybilne API autocomplete systemow.

    Od Fazy 2.3 jedynym zrodlem zapytan HTTP SPANSH jest SpanshClient.
    """
    q = (tekst or "").strip()
    if q.startswith("-"):
        q = q[1:].strip()
    if len(q) < 2:
        return []

    try:
        names = spansh_client.systems_suggest(q)
        if names:
            return names
        if is_edsm_enabled():
            return edsm_systems_suggest(q)
        return []
    except Exception as e:  # noqa: BLE001
        print(f"[Spansh] System suggest exception ({q!r}): {e}")
        if is_edsm_enabled():
            return edsm_systems_suggest(q)
        return []


def pobierz_sugestie_stacji(system: str, tekst: str):
    """
    Kompatybilne API autocomplete stacji.
    """
    sys_name = (system or "").strip()
    q = (tekst or "").strip()
    if not sys_name:
        return []
    if len(q) < 1:
        return []

    try:
        return spansh_client.stations_for_system(sys_name, q)
    except Exception as e:  # noqa: BLE001
        print(f"[Spansh] Station suggest exception ({sys_name!r}, {q!r}): {e}")
        return []
