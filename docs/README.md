# R.E.N.A.T.A. (RenataAI)

Route, Exploration & Navigation Assistant for Trading & Analysis.
Desktopowy companion dla Elite Dangerous, ktory czyta dane z gry i pomaga podejmowac decyzje bez automatyzowania rozgrywki.

## Czym jest Renata
Renata to asystent decyzyjny, nie autopilot.

- interpretuje dane z Journal/Status/Market/Cargo,
- wspiera planowanie tras (Spansh), eksploracje i handel,
- podaje krotsze, kontekstowe komunikaty TTS,
- ogranicza spam i dba o czytelnosc informacji.

## Co Renata robi dzisiaj (v0.9.2)
- Zakladki Spansh: `Neutron`, `Riches`, `Ammonia`, `ELW`, `HMC`, `Exomastery`, `Trade`.
- Route workflow z auto-clipboard i wskazaniem kolejnego celu.
- Trade helper z walidacja danych i wynikami tabelarycznymi.
- Exploration callouty (FSS, high-value hints, exobio sample flow).
- Globalny pipeline TTS (Piper/pyttsx3) z polityka anti-spam.
- Konfigurowalne UI tabel (Treeview, kolumny, sort, copy/export).

## Jak Renata dziala (high-level)
1. Main loop czyta pliki gry (Journal + watchery pomocnicze).
2. Event handler aktualizuje `app_state` i uruchamia logike domenowa.
3. Moduly logiczne wyliczaja insighty/route i przygotowuja payloady (np. Spansh).
4. GUI renderuje wynik i udostepnia akcje (copy, export, ustaw Start/Cel).
5. TTS wypowiada tylko komunikaty o wartosci decyzyjnej.

## Wymagania
- Windows (projekt jest rozwijany i testowany glownie na Windows).
- Python 3.10+ (zalecany launcher `py`).
- Elite Dangerous Journal w domyslnej sciezce Saved Games albo wlasny `log_dir`.

## Szybki start (dev)
Uruchom GUI:

```powershell
py main.py
```

Smoke testy:

```powershell
py tools/smoke_tests_beckendy.py
py tools/smoke_tests_journal.py
```

Wybrane testy jednostkowe:

```powershell
py -m unittest tests.test_spansh_payloads
```

## Konfiguracja i ustawienia
- Renata trzyma ustawienia usera w `%APPDATA%\\RenataAI\\user_settings.json`.
- Lokalny plik obok aplikacji nie jest source-of-truth, chyba ze ustawisz `RENATA_SETTINGS_PATH`.
- Przydatny startowy szablon: `user_settings.example.json`.

### TTS
- Domyslnie: `tts.engine=auto`.
- `auto` wybiera Piper (jesli dostepny), inaczej fallback na `pyttsx3`.
- Voice Pack Piper jest opcjonalny i instalowany osobno.
- Szczegoly instalatora: `tools/voicepack_installer/README.md`.

## Struktura repo (najwazniejsze katalogi)
- `app/` - petla glowna, state, route manager.
- `gui/` - UI (zakladki, wspolne komponenty, tabele, clipboard).
- `logic/` - logika domenowa, eventy, TTS, klient Spansh, payloady.
- `tests/` - testy jednostkowe.
- `tools/` - smoke testy i narzedzia pomocnicze.
- `docs/` - dokumentacja projektu.

## Dokumentacja
- Publiczny opis produktu i granic: `docs/Flow/public/`.
- Status release i quality gate: `docs/RELEASE_CHECKLIST.md`.
- Szybki handoff: `docs/README_TRANSFER.md`.
- Backlog wykonawczy i refaktor: `docs/internal/`.

## Model FREE/PRO (high-level)
- Jeden codebase i wspolny core.
- Rozdzial planow przez capabilities, nie przez duplikacje logiki.
- Brak przewagi gameplayowej dla PRO.

## Non-goals
- Brak makr i automatyzacji gry.
- Brak sterowania statkiem/mapa gry przez Renate.
- Brak "jedynej slusznej decyzji" narzucanej pilotowi.

## Troubleshooting (krotko)
- Brak danych z gry: sprawdz `log_dir` i czy Elite zapisuje Journal.
- Brak glosu Piper: zostaw `tts.engine=auto` albo sprawdz instalacje voice packa.
- Problemy z testami: uruchamiaj komendy przez `py` z katalogu repo.

## Trademarks / attribution
Projekt korzysta z danych/uslug stron trzecich (m.in. Spansh, EDSM, Inara, EDTools) oraz formatu Elite Dangerous Journal.
Wszystkie znaki towarowe naleza do ich wlascicieli.
