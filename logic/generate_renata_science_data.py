try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None  # pozwoli nam obsłużyć błąd łagodnie niżej w funkcjach

import requests
from .utils import HEADERS
from io import StringIO

EXOBIO_URL = "https://elite-dangerous.fandom.com/wiki/Exobiologist"
EXPLORER_URL = "https://elite-dangerous.fandom.com/wiki/Explorer"
OUTPUT_FILE = "renata_science_data.xlsx"


def _fetch_html(url: str) -> str:
    """
    Pobiera HTML strony, używając naszego standardowego HEADERS,
    ale dostosowanego do stron WWW (Fandom).
    """
    if HEADERS is not None:
        headers = HEADERS.copy()
    else:
        headers = {}

    # Dostosowanie pod HTML, nie JSON
    headers["Accept"] = (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    )
    # Content-Type przy GET do strony HTML jest zbędny (i bywa mylący)
    headers.pop("Content-Type", None)

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text


def build_exobiology_sheet() -> "pd.DataFrame":
    """
    Pobiera z Fandoma pełną tabelę exobiologii (Genus/Species/Value/CCR)
    i przygotowuje arkusz:
    Species_Name, Base_Value, First_Discovery_Bonus, Total_First_Footfall, Minimum_Distance.
    """
    if pd is None:
        raise RuntimeError(
            "Brak biblioteki 'pandas'. "
            "Zainstaluj: pip install pandas"
        )

    try:
        html = _fetch_html(EXOBIO_URL)
    except Exception as e:
        raise RuntimeError(f"Nie udało się pobrać strony Exobiologist: {e}") from e

    try:
        tables = pd.read_html(StringIO(html))
    except ImportError as e:
        # Tu wpada 'Missing optional dependency lxml'
        raise RuntimeError(
            "Brak parsera HTML 'lxml' dla pandas.read_html. "
            "Zainstaluj: pip install lxml"
        ) from e

    exo_table = None
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if "genus" in cols and "species" in cols and "value (cr)" in cols:
            exo_table = t.copy()
            break

    if exo_table is None:
        raise RuntimeError(
            "Nie udało się znaleźć tabeli exobiologii na stronie Exobiologist."
        )

    # Mapowanie nazw kolumn
    col_map: dict = {}
    for c in exo_table.columns:
        lc = str(c).strip().lower()
        if "genus" == lc:
            col_map[c] = "Genus"
        elif "species" == lc:
            col_map[c] = "Species"
        elif "value" in lc and "(cr" in lc:
            col_map[c] = "Value (CR)"
        elif lc in ("ccr", "clonal colony range", "colony range"):
            col_map[c] = "CCR"
    exo_table = exo_table.rename(columns=col_map)

    required_cols = {"Genus", "Species", "Value (CR)", "CCR"}
    if not required_cols.issubset(set(exo_table.columns)):
        raise RuntimeError(
            f"Tabela exobiologii nie ma wymaganych kolumn: {required_cols}"
        )

    exo = exo_table.copy()

    # Parsowanie wartości kredytowej
    val_str = (
        exo["Value (CR)"]
        .astype(str)
        .str.replace(r"\[.*?\]", "", regex=True)   # usuń przypisy [1]
        .str.replace(r"[^\d]", "", regex=True)    # wszystko poza cyframi
    )
    exo["Base_Value"] = pd.to_numeric(val_str, errors="coerce")

    # Parsowanie CCR -> minimum distance
    ccr_str = (
        exo["CCR"]
        .astype(str)
        .str.replace(r"\[.*?\]", "", regex=True)
    )
    exo["Minimum_Distance"] = (
        ccr_str
        .str.extract(r"(\d+)", expand=False)
        .pipe(pd.to_numeric, errors="coerce")
    )

    # Budowa pełnej nazwy gatunku
    def _species_name(row):
        genus = str(row["Genus"]).strip()
        species = str(row["Species"]).strip()
        if species.lower() in ("", "n/a", "na", "–", "-", "nan"):
            return genus
        return f"{genus} {species}"

    exo["Species_Name"] = exo.apply(_species_name, axis=1)

    # Obliczenia bonusów
    exo["First_Discovery_Bonus"] = exo["Base_Value"] * 4
    exo["Total_First_Footfall"] = exo["Base_Value"] * 5

    exo = exo[exo["Base_Value"].notna()].copy()

    exo["Base_Value"] = exo["Base_Value"].astype(int)
    exo["First_Discovery_Bonus"] = exo["First_Discovery_Bonus"].astype(int)
    exo["Total_First_Footfall"] = exo["Total_First_Footfall"].astype(int)

    exo_sheet = exo[[
        "Species_Name",
        "Base_Value",
        "First_Discovery_Bonus",
        "Total_First_Footfall",
        "Minimum_Distance",
    ]].sort_values("Species_Name")

    return exo_sheet


def build_cartography_sheet() -> "pd.DataFrame":
    """
    Pobiera z Fandoma tabelę skanów (Scan Values) i buduje arkusz Cartography:
    Body_Type, Terraformable, FSS_Base_Value, DSS_Mapped_Value, First_Discovery_Mapped_Value.
    """
    if pd is None:
        raise RuntimeError(
            "Brak biblioteki 'pandas'. "
            "Zainstaluj: pip install pandas"
        )

    try:
        html = _fetch_html(EXPLORER_URL)
    except Exception as e:
        raise RuntimeError(f"Nie udało się pobrać strony Explorer: {e}") from e

    try:
        tables = pd.read_html(StringIO(html))
    except ImportError as e:
        raise RuntimeError(
            "Brak parsera HTML 'lxml' dla pandas.read_html. "
            "Zainstaluj: pip install lxml"
        ) from e

    scan_table = None
    for t in tables:
        cols = [str(c).strip().lower() for c in t.columns]
        if "planet type" in cols and "fss" in cols:
            scan_table = t.copy()
            break

    if scan_table is None:
        raise RuntimeError(
            "Nie udało się znaleźć tabeli Scan Values na stronie Explorer."
        )

    col_map: dict = {}
    for c in scan_table.columns:
        lc = str(c).strip().lower()
        if "planet type" in lc:
            col_map[c] = "Planet Type"
        elif "terraformable" in lc:
            col_map[c] = "Terraformable?"
        elif lc == "fss":
            col_map[c] = "FSS"
        elif "fss+dss" in lc and "fd" not in lc:
            col_map[c] = "FSS+DSS"
        elif "fss+fd+dss" in lc:
            col_map[c] = "FSS+FD+DSS"

    scan_table = scan_table.rename(columns=col_map)

    needed = {"Planet Type", "Terraformable?", "FSS", "FSS+DSS", "FSS+FD+DSS"}
    if not needed.issubset(set(scan_table.columns)):
        raise RuntimeError(
            f"Tabela Scan Values nie ma wymaganych kolumn: {needed}"
        )

    carto = scan_table.copy()

    # czasem tabela jest powielona (nagłówek na dole) – wywalamy wiersze bez FSS
    carto = carto[carto["FSS"].notna()].copy()

    # Czyścimy wartości (usuwamy znaki nienumeryczne)
    for col in ["FSS", "FSS+DSS", "FSS+FD+DSS"]:
        carto[col] = (
            carto[col]
            .astype(str)
            .str.replace(r"\[.*?\]", "", regex=True)
            .str.replace(r"[^\d]", "", regex=True)
        )
        carto[col] = pd.to_numeric(carto[col], errors="coerce")

    carto_sheet = pd.DataFrame({
        "Body_Type": carto["Planet Type"],
        "Terraformable": carto["Terraformable?"],
        "FSS_Base_Value": carto["FSS"].astype("Int64"),
        "DSS_Mapped_Value": carto["FSS+DSS"].astype("Int64"),
        "First_Discovery_Mapped_Value": carto["FSS+FD+DSS"].astype("Int64"),
    })

    carto_sheet = carto_sheet[carto_sheet["Body_Type"].notna()].reset_index(drop=True)
    return carto_sheet


def generate_science_excel(path: str = OUTPUT_FILE) -> str | None:
    """
    Generuje plik Excela z dwoma arkuszami: Exobiology i Cartography.
    Zwraca:
        None – jeśli wszystko poszło OK
        str  – jeśli nastąpił błąd (komunikat do Pulpitu)
    """
    if pd is None:
        return (
            "[SCIENCE_DATA] Brak biblioteki 'pandas'. "
            "Zainstaluj pakiety: pip install pandas xlsxwriter"
        )

    try:
        exobio_df = build_exobiology_sheet()
        carto_df = build_cartography_sheet()

        with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
            exobio_df.to_excel(writer, index=False, sheet_name="Exobiology")
            carto_df.to_excel(writer, index=False, sheet_name="Cartography")

        return None

    except Exception as e:
        return f"[SCIENCE_DATA] Błąd przy generowaniu pliku {path}: {e}"
