import requests
import config
from logic.spansh_client import client as spansh_client
from logic.utils.http_edsm import edsm_systems_suggest


HEADERS = {
    "User-Agent": (
        "RENATA/1.0 "
        "(R.E.N.A.T.A. - Route Engine & Navigation Automated Trade Assistant; "
        "contact: tyffanthc@gmail.com)"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "From": "tyffanthc@gmail.com",
}


def pobierz_sugestie(tekst: str):
    """
    Zwraca listę nazw systemów na podstawie API Spansh.
    ZAWSZE zwraca list[str] i NICZEGO w środku nie mutuje.
    Obsługuje zarówno odpowiedzi typu dict, jak i list.
    """
    q = (tekst or "").strip()
    # w niektórych miejscach użytkownik wpisuje z prefiksem '-', to ignorujemy
    if q.startswith("-"):
        q = q[1:].strip()

    print(f"[Spansh] '{q}' → zapytanie")

    # dla bardzo krótkich zapytań nie spamujemy API
    if len(q) < 2:
        return []

    try:
        url = "https://spansh.co.uk/api/systems"
        headers = {
            "User-Agent": "RenataAssistant/2.0",
            "Referer": "https://spansh.co.uk",
            "Accept": "application/json",
        }
        res = requests.get(url, params={"q": q}, headers=headers, timeout=4)
        if res.status_code != 200:
            print(f"[Spansh] HTTP {res.status_code} dla '{q}'")
            return []

        data = res.json()
        items = []

        # Spansh bywa kapryśny, obsłuż oba formaty
        if isinstance(data, dict):
            # popularne pola: "systems" albo "results"
            items = data.get("systems") or data.get("results") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []

        names: list[str] = []

        for item in items:
            name = None
            if isinstance(item, str):
                # jeśli API od razu zwróci listę stringów
                name = item
            elif isinstance(item, dict):
                # typowa odpowiedź: {"name": "Colonia", ...}
                name = (
                    item.get("name")
                    or item.get("system")
                    or item.get("Name")
                    or item.get("system_name")
                )
            else:
                # nieobsługiwany typ – pomijamy
                continue

            if not name:
                continue

            if name not in names:
                names.append(str(name))

        print(f"[Spansh] '{q}' → {len(names)} wyników")
        if names:
            return names
        return edsm_systems_suggest(q)

    except Exception as e:
        print(f"[DEBUG] API Wyjątek: {e}")
        return edsm_systems_suggest(q)


def pobierz_sugestie_stacji(system: str, tekst: str):
    """
    Zwraca listę nazw STACJI w podanym systemie, korzystając z klienta SPANSH.

    Uwaga:
    - używa SpanshClient.stations_for_system(...) (z debouncerem),
    - dla bezpieczeństwa zawsze zwraca list[str],
    - w razie błędu/logiki po naszej stronie -> [] + print do konsoli.
    """
    sys_name = (system or "").strip()
    q = (tekst or "").strip()

    if not sys_name:
        return []

    # dla bardzo krótkich prefiksów nie ma sensu odpalać zapytania
    if len(q) < 1:
        return []

    try:
        return spansh_client.stations_for_system(sys_name, q)
    except Exception as e:
        print(f"[Spansh] Station suggest exception ({sys_name!r}, {q!r}): {e}")
        return []
