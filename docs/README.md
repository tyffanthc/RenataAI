# R.E.N.A.T.A. (RenataAI)

Route, Exploration & Navigation Assistant for Trading & Analysis.
Desktopowy companion dla Elite Dangerous, ktory czyta dane z gry i pomaga podejmowac decyzje bez automatyzowania rozgrywki.

## Czym jest Renata
Renata to asystent decyzyjny, nie autopilot.

- interpretuje dane z Journal/Status/Market/Cargo,
- wspiera planowanie tras (Spansh), eksploracje i handel,
- podaje krotsze, kontekstowe komunikaty TTS,
- ogranicza spam i dba o czytelnosc informacji.

## Co Renata robi dzisiaj (v0.9.5)
- Zakladki Spansh: `Neutron`, `Riches`, `Ammonia`, `ELW`, `HMC`, `Exomastery`, `Trade`.
- Route workflow z auto-clipboard i wskazaniem kolejnego celu.
- Trade helper z walidacja danych, split-view i panelem szczegolow kroku.
- Trade pokazuje `Wiek rynku K/S`, `Cumulative Profit` i fallback wyliczania `Skoki [szt]`.
- Cash-In smart navigation: collect-then-rank multi-source, global dedupe/ranking, profile semantyczne i auto-target do schowka.
- Cash-In ship awareness: filtr stacji pod rozmiar statku (`needs_large_pad`) + runtime toggles (`SHIP/EXP/CAR`) w pulpicie.
- Exploration callouty (FSS, high-value hints, ExoBio sample flow).
- Eksploracja FSS: inteligentne liczenie cial (filtr pasow asteroid/Belt), poprawny progres i domkniecie 100% przy pelnym skanie.
- Eksploracja ExoBio: pelna asysta probek 1/2/3 (`nowy wpis` -> `kolejna probka` -> `gatunek kompletny`) z koncowa wycena i wysokim priorytetem mowy dla finalu.
- Nawigacja: pamiec boi nawigacyjnych per system (visited nav beacons), bez powtarzania intro o pasywnym skanie w znanych ukladach.
- UX/TTS: krotkie, human-friendly nazwy cial niebieskich w komunikatach glosowych (bez twardego prefiksu nazwy systemu).
- Stabilnosc paliwa na starcie: potwierdzanie `fuel_capacity`, fallback last-known i guards bootstrap bez falszywych alertow krytycznych.
- Globalny pipeline TTS (Piper/pyttsx3) z polityka anti-spam.
- Konfigurowalne UI tabel (Treeview, kolumny, sort, copy/export) + spojny globalny styl scrollbarow.

## Najwazniejsze zmiany od v0.9.4 do v0.9.5 (wg LAST_TICKET)
- Cash-In (F11-F17, F32-F33): pelny pipeline kandydatow stacji, profile semantyczne, ship-size constraints, clipboard auto-target i quality gates.
- Player Local DB (F16 + F34): rozszerzone migracje/schema, bridge danych runtime, pamiec visited nav beacons.
- Mapa i UI (F20-F22, F31): rozbudowany widok mapy, warstwy, legendy, filtry, persistence i regresje startup/center.
- Eksploracja (F24-F31, F34-F36): stabilniejsze sekwencje FSS/DSS/ExoBio, lepsze callouty i odporna persystencja po restarcie.
- Fuel runtime (F23, F34, F36): hardening low-fuel/startup path, mniej spamu, bardziej przewidywalne alerty krytyczne.
- TTS/Voice UX (F17-F19, F35-F36): lepsze priorytety i kolejkowanie dla krytycznych komunikatow oraz krotsze nazwy cial.

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

## User-supplied data (Cash-In / offline)
- Renata nie dostarcza ani nie hostuje dumpow danych Spansh.
- Uzytkownik pobiera dump samodzielnie ze zrodla Spansh i importuje go lokalnie.
- Zrodlo danych: Spansh (c) Gareth Harper.
