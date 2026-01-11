# logic/science_data.py

import pandas as pd


def load_science_data(path: str = "renata_science_data.xlsx"):
    """
    Wczytuje dane naukowe wygenerowane przez generate_science_excel():
    - arkusz 'Exobiology'
    - arkusz 'Cartography'

    Zwraca:
        (exobio_df, carto_df) - dwa DataFrame'y pandas.

    Wyjątki (np. FileNotFoundError, ParserError) są przepuszczane dalej
    i powinny być obsłużone po stronie GUI / aplikacji.
    """
    exobio = pd.read_excel(path, sheet_name="Exobiology")
    carto = pd.read_excel(path, sheet_name="Cartography")
    return exobio, carto
