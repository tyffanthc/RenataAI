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

## 3) T3 – UX/GUI smoke (5 minut)
Wymaga uruchomionego GUI.

- [ ] Spójność UI: fonty/rozmiary pól są spójne w całym module Spansh (Start/Cel/Range itd.)
- [ ] Focus/Enter: Start → Tab → Cel → Tab → Range → Tab → Calculate działa sensownie
- [ ] Enter w polach nie robi “dziwnych rzeczy” (np. nie dodaje Via, jeśli dropdown otwarty)
- [ ] Stany: po kliknięciu “Wyznacz trasę” widać czytelny stan “busy” i potem wynik/komunikat
- [ ] Empty state: brak wynikow -> widoczny komunikat + podpowiedz co zrobic
- [ ] Lista Via: chipsy nie rozpychają layoutu, usuwanie działa i Reverse odwraca kolejność
- [ ] Tabele wyników: nagłówki widoczne, przewijanie OK, [SKOPIOWANO] nie rozwala szerokości
- [ ] Treeview: sort po kliknieciu naglowka, LP widoczne, column picker zmienia widoczne kolumny (pod flagami)

## 3.1) Clipboard / NEXT_HOP — UX smoke
Pre-conditions:
- [ ] `python main.py` uruchomiony, Renata widzi journal (zdarzenia lecą).

Flow: route → skok → next hop
- [ ] Wyznacz trasę (np. Neutron / R2R) z min. 3 hopami.
- [ ] Upewnij się, że auto-clipboard jest ustawiony na tryb `NEXT_HOP`.
- [ ] Wykonaj skok (symulacja eventem albo realnie).
- [ ] Do schowka trafia następny punkt (nie bieżący).
- [ ] Na bieżącym hopie jest marker [SKOPIOWANO].
- [ ] Overlay pokazuje "Copy next" i po skoku aktualizuje się spójnie.

Edge cases:
- [ ] Route empty → brak błędów, brak kopiowania.
- [ ] Route finished → brak kopiowania, czytelny status.
- [ ] Route changed (nowa trasa) → resync index, brak "skakania" po starych hopach.

## 4) T4 – Spansh parity (manual, szybka)
Wymaga dostępu do sieci (SPANSH).

- [ ] Neutron: Normal/Overcharge faktycznie zmienia zachowanie (mnożnik 4/6)
- [ ] Riches: Minimum Scan Value działa (zmiana wartości zmienia wynik)
- [ ] Exomastery: Minimum Landmark Value działa (zmiana wartości zmienia wynik)
- [ ] Trade: Maximum Market Age aktywne i wpływa na wyniki
## 5) Journal replay (manual)
- [ ] `python tools/journal_replay.py "tools/journal test.txt"`
- [ ] Brak crashy w trakcie odtwarzania

## 6) SPANSH non-trade route (manual, GUI)
Wymaga dostępu do sieci (SPANSH).

- [ ] Odpal Renatę: `python main.py` (albo Twój standardowy sposób uruchamiania GUI)
- [ ] Wejdź w zakładkę SPANSH (np. `Riches` / `ELW` / `HMC` / `Ammonia`)
- [ ] Uruchom wyliczenie trasy
- [ ] Sprawdź lifecycle w UI: start → „busy” → wynik trasy → brak crashy

## 7) RouteManager lifecycle (obserwacja)
- [ ] Wybrany tryb trasy ustawia `current_mode`/`busy` i po zakończeniu wraca do stanu spoczynku
- [ ] Przełączenie zakładek/trybów nie powoduje wyjątków w logu/konsoli
