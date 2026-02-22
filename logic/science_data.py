# logic/science_data.py

import pandas as pd
import config


def load_science_data(path: str | None = None):
    """
    Wczytuje dane naukowe wygenerowane przez generate_science_excel():
    - arkusz 'Exobiology'
    - arkusz 'Cartography'

    Zwraca:
        (exobio_df, carto_df) - dwa DataFrame'y pandas.

    Wyjątki (np. FileNotFoundError, ParserError) są przepuszczane dalej
    i powinny być obsłużone po stronie GUI / aplikacji.
    """
    resolved_path = str(path or config.get("science_data_path", config.SCIENCE_EXCEL_PATH))
    exobio = pd.read_excel(resolved_path, sheet_name="Exobiology")
    carto = pd.read_excel(resolved_path, sheet_name="Cartography")
    return exobio, carto
