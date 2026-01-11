# RenataAI — Smoke pack (runbook)

Cel: szybka, powtarzalna weryfikacja „czy Renata żyje” po świeżym klonie albo większej zmianie.

Zasady:
- Uruchamiaj komendy z katalogu repo (root).
- Smoke testy nie powinny pisać do `user_settings.json` (wyłączają głos tylko w pamięci).
- Brak destrukcyjnej automatyzacji: to jest checklist, nie skrypt czyszczący.

## 0) Repo hygiene (weryfikacja)
- [ ] `git status` nie pokazuje `__pycache__/` ani `*.pyc` (artefakty są ignorowane przez `.gitignore`)

## 1) T1 — Backend smoke
- [ ] `python tools/smoke_tests_beckendy.py`
- [ ] Brak `Traceback` i brak `AssertionError`

Alternatywa (Windows): `Run_Renata_tests.bat` (uruchamia T1 + T2).

## 2) T2 — Journal/AppState smoke
- [ ] `python tools/smoke_tests_journal.py`
- [ ] Brak `Traceback` i brak `AssertionError`

Minimum (DoD):
- [ ] system aktualizuje się po `FSDJump`
- [ ] stacja aktualizuje się po `Docked`
- [ ] `is_docked` reaguje poprawnie (Docked/Undocked)
- [ ] DEBOUNCER działa (brak floodu)

## 3) Journal replay (manual)
- [ ] `python tools/journal_replay.py "tools/journal test.txt"`
- [ ] Brak crashy w trakcie odtwarzania

## 4) SPANSH non-trade route (manual, GUI)
Wymaga dostępu do sieci (SPANSH).

- [ ] Odpal Renatę: `python main.py` (albo Twój standardowy sposób uruchamiania GUI)
- [ ] Wejdź w zakładkę SPANSH (np. `Riches` / `ELW` / `HMC` / `Ammonia`)
- [ ] Uruchom wyliczenie trasy
- [ ] Sprawdź lifecycle w UI: start → „busy” → wynik trasy → brak crashy

## 5) RouteManager lifecycle (obserwacja)
- [ ] Wybrany tryb trasy ustawia `current_mode`/`busy` i po zakończeniu wraca do stanu spoczynku
- [ ] Przełączenie zakładek/trybów nie powoduje wyjątków w logu/konsoli
