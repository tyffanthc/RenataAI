# logic/events/files.py

import os
import config


def get_log_dir() -> str:
    """
    Zwraca aktualny katalog logów Journala na podstawie ConfigManagera.
    """
    return config.get("log_dir")


def status_path() -> str:
    """
    Ścieżka do Status.json w katalogu journala.
    """
    return os.path.join(get_log_dir(), "Status.json")


def market_path() -> str:
    """
    Ścieżka do Market.json w katalogu journala.
    """
    return os.path.join(get_log_dir(), "Market.json")
