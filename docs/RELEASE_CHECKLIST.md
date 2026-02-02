# Release Checklist - RenataAI

## Scope confirmation
- Confirm target version and included tickets.
- Freeze feature flags for release (default ON/OFF decisions).
- Verify `user_settings.json` is not tracked.

## Build and smoke
- `py tools/smoke_tests_beckendy.py`
- `py tools/smoke_tests_journal.py`
- TTS autodetect: voice pack w APPDATA -> log "selected=piper source=appdata".

## Core UI/UX (manual)
- Start app: `py main.py`
- Spansh tabs open and render (Neutron, Riches, Ammonia, ELW, HMC, Exo, Trade).
- FREE tabs: w FREE widoczne tylko Pulpit/Spansh/Dziennik/Settings, brak Inara/EDTools/Inzynier.
- Treeview tables: headers visible, sort by header works, LP column present.
- Column Picker: toggle columns, presets apply, restart keeps layout.
- Context menu on results (if enabled): copy, set Start/Cel, CSV/TSV.
- Trade: required field "Stacja*" validation, no request when empty.
- Trade: "Alerty jackpotow" widoczne w Settings + przycisk progow.
- Market Age slider (if enabled): slider <-> datetime sync, no auto-run.

## Autocomplete and providers
- Autocomplete Start/Cel works (offline cache).
- With EDSM ON: fallback accepts unknown system names (no UI errors).
- With EDSM OFF: no online requests, behavior unchanged.

## Empty state microcopy (PL/EN)
- no_results: "Brak wynikow dla obecnych ustawien." / "Sprobuj zmienic filtry lub zakres."
- filters_excluded: "Filtry wykluczyly wszystkie wyniki." / "Poluzuj kryteria filtrowania."
- no_input: "Brak danych wejsciowych." / "Wybierz punkt startowy i cel."
- busy_calculating: "Obliczanie trasy..." / "Prosze czekac."
- waiting_data: "Oczekiwanie na dane..." / ""
- provider_off: "Dane online sa wylaczone." / "Wlacz providera w ustawieniach."
- online_error: "Nie udalo sie pobrac danych online." / "Sprawdz polaczenie lub sprobuj ponownie."
- route_empty: "Trasa jest pusta." / "Brak punktow do wyswietlenia."
- route_completed: "Trasa zakonczona." / "Brak kolejnych punktow."
- fallback: "Wystapil problem, ale aplikacja dziala dalej." / "Sprawdz logi, jesli problem sie powtarza."

## Exploration voice (manual, if journal available)
- First discovery: "Gratulacje..." and "To cialo nie ma wczesniejszego odkrywcy."
- First footfall: "Zanotowano pierwszy ludzki krok..."
- FSS milestones: 25/50/75/100% messages.
- Bio signals: "Potwierdzono liczne sygnaly biologiczne..."

## Debug / observability
- Logging does not crash app on odd fields.
- Debug panel (if enabled) updates without errors and no spam.
- SPANSH last request panel (if enabled) shows payload.

## Cache / performance sanity
- Repeat same Neutron request -> cache HIT (if `debug_cache=true`).
- EDSM ON does not slow Neutron routes (no per-hop lookups).

## Release artifacts
- Verify README/RENATA_STATUS are up to date.
- Tag build and archive logs if needed.
- Voice Pack installer: payload present + ISCC build.
- Voice Pack installer EXE jest osobnym assetem (nie w ZIP).
