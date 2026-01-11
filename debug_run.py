import os
import sys
import time
import traceback

print("=== DIAGNOSTYKA SYSTEMU RENATA v71+ (REF U1–U2 zgodna) ===")
print(f"Katalog roboczy: {os.getcwd()}")

def sprawdz_plik(sciezka):
    if os.path.exists(sciezka):
        print(f"[OK] Znaleziono: {sciezka}")
        return True
    else:
        print(f"[BŁĄD] BRAKUJE PLIKU: {sciezka}")
        return False

# ------------------------------------------------------------
# 1. SPRAWDZANIE STRUKTURY PLIKÓW
# ------------------------------------------------------------
print("\n--- 1. Weryfikacja plików ---")

# UWAGA: logic/utils.py usunięto po refaktorze → nie sprawdzamy go już!
wymagane = [
    "main.py",
    "gui.py",
    "config.py",
    "logic/__init__.py",
    "logic/neutron.py",
    "logic/riches.py",
    "logic/engineer.py"
]

bledy = 0
for plik in wymagane:
    if not sprawdz_plik(plik):
        bledy += 1

if bledy > 0:
    print(f"\nFATALNY BŁĄD: Brakuje {bledy} plików!")
    print("Upewnij się, że masz folder 'logic' i w nim plik '__init__.py'.")
    input("\nWciśnij ENTER aby zamknąć...")
    sys.exit()

# ------------------------------------------------------------
# 2. SPRAWDZANIE IMPORTÓW
# ------------------------------------------------------------
print("\n--- 2. Test Importów (Ładowanie modułów) ---")
try:
    print("Importowanie config...", end=" ")
    import config
    print("OK")

    print("Importowanie logic.utils (pakiet)...", end=" ")
    import logic.utils as utils_pkg
    print("OK")

    # Test kluczowych symboli z pakietu utils
    print("Weryfikacja symboli logic.utils...", end=" ")
    _ = utils_pkg.powiedz
    _ = utils_pkg.MSG_QUEUE
    _ = utils_pkg.HEADERS
    _ = utils_pkg.pobierz_sugestie
    print("OK")

    print("Importowanie logic.neutron...", end=" ")
    from logic import neutron
    print("OK")

    print("Importowanie logic.riches...", end=" ")
    from logic import riches
    print("OK")
    
    print("Importowanie logic.engineer...", end=" ")
    from logic import engineer
    print("OK")

    print("Importowanie gui...", end=" ")
    import gui
    print("OK")

except Exception as e:
    print("\n!!! BŁĄD KRYTYCZNY PODCZAS IMPORTOWANIA !!!")
    print("Program wywala się, bo jeden z modułów nie ładuje się poprawnie.")
    print("-" * 30)
    traceback.print_exc()
    print("-" * 30)
    input("\nWciśnij ENTER aby zamknąć...")
    sys.exit()

# ------------------------------------------------------------
# 3. PRÓBA URUCHOMIENIA GUI
# ------------------------------------------------------------
print("\n--- 3. Próba startu GUI ---")
try:
    import tkinter as tk
    root = tk.Tk()
    print("Główne okno TK stworzone.")
    app = gui.RenataApp(root)
    print("Klasa RenataApp załadowana poprawnie.")
    print("\nSUKCES! Wszystko wygląda dobrze.")
    print("Zamykam test. Spróbuj uruchomić main.py.")
    root.destroy()
except Exception as e:
    print(f"\nBŁĄD GUI: {e}")
    traceback.print_exc()

input("\nDIAGNOSTYKA ZAKOŃCZONA. Wciśnij ENTER...")
