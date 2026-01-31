# RenataAI od A do Z

Dokument oparty o analizę kodu w `c:\Users\Patryk\Desktop\RenataAI` (bez uruchamiania GUI i bez połączeń sieciowych).

## Update 2026-01-21 (recent changes)
- Results tables: Treeview renderer + sort + LP + column picker (flags).
- Treeview rollout to all Spansh planners with table results.
- Results context menu (copy/start/goal/CSV/TSV) under flag.
- Trade Market Age slider + datetime (flagged).


## A) Executive summary

### Co Renata robi (10–15 punktów)
- Czyta Journal ED oraz pliki Status/Market/Cargo i aktualizuje stan gry (AppState) w tle `app/main_loop.py`, `app/status_watchers.py`, `logic/event_handler.py`.
- Aktualizuje pozycję gracza, stację i status zadokowania na podstawie eventów `Location/FSDJump/Docked` w `logic/events/navigation_events.py`.
- Wylicza trasy SPANSH: Neutron, R2R, Ammonia, ELW, HMC, Exomastery oraz Trade w `logic/*` i `gui/tabs/spansh/*`.
- Wspiera autouzupełnianie systemów i stacji przez SPANSH w `logic/spansh_client.py` i `gui/common_autocomplete.py`.
- Zarządza trasą i auto‑schowkiem (FULL_ROUTE/NEXT_HOP) wraz z markerem [SKOPIOWANO] w `gui/common.py`, `logic/route_clipboard.py`.
- Pokazuje overlay „quick view” (status + Next Hop + kopiowanie) w `gui/app.py`.
- Pulpit: log zdarzeń i szybkie przyciski generowania danych naukowych / modułów w `gui/tabs/pulpit.py`.
- Generuje i ładuje arkusze naukowe (Exobiology + Cartography) w `logic/generate_renata_science_data.py`, `logic/science_data.py`.
- Liczy wartość naukową systemu (System Value Engine + Exit Summary) w `logic/system_value_engine.py`, `logic/exit_summary.py`.
- Liczy bieżący zasięg skoku (Jump Range Engine) na podstawie Loadout/Status w `logic/ship_state.py`, `logic/jump_range_engine.py`.
- Prowadzi prosty logbook (foldery/wpisy) w `logic/logbook_manager.py`, `gui/tabs/logbook.py`.
- Inżynier: sprawdza braki w recepturze na podstawie `config.RECEPTURY` w `logic/engineer.py`.
- Cache + deduplikacja zapytań do SPANSH w `logic/cache_store.py`, `logic/request_dedup.py`.

### Największe mocne strony (3–5)
- Centralny ConfigManager i spójny `config.get()` ułatwiają flagowanie funkcji (`config.py`).
- Modularny routing eventów journala (osobne pliki `logic/events/*`) ułatwia utrzymanie.
- SpanshClient z cache/dedupe ogranicza spam i poprawia UX (`logic/spansh_client.py`).
- Normalizatory wierszy + schematy tabel umożliwiają czytelne listy wyników (`logic/rows_normalizer.py`, `gui/table_schemas.py`).
- Rozdzielenie warstw: UI ↔ logika ↔ providerzy (Spansh) jest już widoczne.

### Największe problemy/ryzyka (3–5)
- Spójność UI jest niska: mieszane fonty, języki i etykiety w niemal każdej zakładce (`gui/app.py`, `gui/tabs/spansh/*`).
- Wiele funkcji jest „stubem” lub placeholderem (Inara/EDTools, beta taby w Spansh) bez jasnego statusu (`gui/app.py`, `gui/tabs/spansh/__init__.py`).
- Część flag konfiguracyjnych nie jest podłączona do logiki (np. `fss_assistant`, `bio_assistant`, `high_value_planets`, `smuggler_alert`) – ryzyko niespójnych oczekiwań (`config.py`, `logic/events/*`).
- Brak testów GUI i testów dla Settings/Logbook/Overlay – duże ryzyko regresji UX.
- Uzależnienie od SPANSH i zewnętrznych źródeł danych bez trybu offline.

### Co poprawić “na już” (top 10 quick wins UX/UI)
Note: several items below are already done (labels, required fields, placeholders, tables).
1) Ujednolicić nazwy i język etykiet w Spansh (PL lub EN, ale konsekwentnie) – `gui/tabs/spansh/*.py`.
2) Dodać wizualny znacznik pól wymaganych (np. Trade: Station) – `gui/tabs/spansh/trade.py`.
3) Usunąć / ukryć placeholdery tabów albo oznaczyć je jako „nieaktywne” – `gui/tabs/spansh/__init__.py`, `gui/app.py`.
4) Dodać prosty stan „liczę…” podczas zapytań SPANSH (status label + disable button) – `app/route_manager.py`, `gui/tabs/spansh/*`.
5) Znormalizować odstępy i szerokości pól w formularzach – `gui/tabs/spansh/*`, `gui/tabs/pulpit.py`.
6) Związać ustawienia asystentów z logiką (fss/bio/high_value/smuggler) – `logic/events/*`.
7) Dodać skrót Enter do uruchamiania kalkulacji w każdej zakładce – `gui/tabs/spansh/*`.
8) Zmniejszyć „debug printy” w konsoli lub przenieść pod flagę debug – `gui/app.py`, `gui/tabs/spansh/trade.py`.
9) Ujednolicić nazwy i opisy pól typu „Max DTA/Max Dist” – `gui/tabs/spansh/*`.
10) Wyrównać listy wyników do schematów tabel (włączyć domyślnie i bez fallbacków) – `gui/common.py`, `gui/table_schemas.py`.

### Co poprawić “w następnym etapie” (top 10 zmian większych)
1) Jednolity layout „workspace” dla wszystkich plannerów (siatka + sekcje + spójne komponenty) – `gui/tabs/spansh/*`.
2) Zastąpić `Listbox` tabelą `Treeview` z nagłówkami i sortowaniem – `gui/common.py`, `gui/table_schemas.py`.
3) Dodać panel „błędy / logi zapytań” w każdej zakładce SPANSH – `gui/tabs/spansh/*`.
4) Dodać „column picker” dla tabel (flaga istnieje, brak UI) – `gui/common.py`, `gui/tabs/settings.py`.
5) Wprowadzić stan „busy” globalny (blokady i kolejka) dla wszystkich plannerów – `app/route_manager.py`.
6) Zapisać i odtwarzać układ okna oraz ostatnią zakładkę – `gui/app.py`, `config.py`.
7) Ograniczyć lub przepisać „placeholder” tabs (Inara/EDTools) – `gui/app.py`.
8) Ujednolicić obsługę walidacji pól numerycznych i błędów API – `gui/tabs/spansh/*`.
9) Rozbudować Logbook o wyszukiwanie i filtrowanie – `gui/tabs/logbook.py`, `logic/logbook_manager.py`.
10) Ujednolicić system powiadomień (status bar/overlay/log) – `gui/app.py`, `gui/common.py`, `logic/utils/notify.py`.

## B) Opis produktu (user view)

### Zakładki top‑level

#### Pulpit
- Do czego służy: status dashboard + log zdarzeń + akcje generowania danych (`gui/tabs/pulpit.py`).
- Workflow: start app → status systemu/ship state → log w ScrolledText → opcjonalnie generuj arkusze naukowe i dane modułów.
- Wejście: `app_state` (system/ship), kliknięcia w przyciski.
- Wyjście: log tekstowy, statusy, pliki `renata_science_data.xlsx` i `renata_modules_data.json`.
- Typowe błędy: brak `pandas/lxml` przy generowaniu arkuszy (`logic/generate_renata_science_data.py`), brak danych modułów (`logic/modules_data.py`).

#### Spansh (moduł planowania)
- Do czego służy: wszystkie planery tras SPANSH w sub‑zakładkach (`gui/tabs/spansh/__init__.py`).
- Workflow: wybierz sub‑zakładkę → uzupełnij parametry → klik „Wyznacz/Calculate” → lista wyników → auto‑schowek / overlay.
- Wejście: parametry formularzy + (opcjonalnie) aktualny system/ship jump range z `app_state`.
- Wyjście: lista wyników (Listbox) + opcjonalne skopiowanie trasy do schowka.
- Typowe błędy: brak systemu startowego, brak wyników SPANSH, brak stacji w Trade.

##### Neutron Plotter
- Cel: trasa neutronowa między systemami (`gui/tabs/spansh/neutron.py`, `logic/neutron.py`).
- Workflow: Start/Cel → Max range + Eff → Charge → opcjonalnie Via → „Wyznacz trasę” → lista skoków.
- Wejścia: Start, Cel, Range, Efficiency, Supercharge, Via.
- Wyjścia: lista skoków (z tabelą schema `neutron`).
- Błędy: puste Start/Cel, niepoprawne Via (walidator `logic/neutron_via.py`).
- Dodatki: „Reverse” (zamiana Start/Cel), lista Via w trybie „compact” (chipy) lub Listbox.

##### Road to Riches
- Cel: trasa R2R po ciałach o wysokiej wartości (`gui/tabs/spansh/riches.py`, `logic/riches.py`).
- Workflow: Start/Cel → Range/Radius/Max Sys/Max Dist/Min Scan → opcje Loop/Use Map/Avoid → „Wyznacz Riches”.
- Wejścia: parametry R2R.
- Wyjścia: lista systemów i ciał (schema `riches`).
- Błędy: brak Start, brak wyników SPANSH.

##### Ammonia Worlds
- Cel: trasa po światach amoniakowych (`gui/tabs/spansh/ammonia.py`, `logic/ammonia.py`).
- Wejścia: Start/Cel + parametry R2R + Loop/Avoid.
- Wyjścia: lista systemów/ciał (schema `ammonia`).
- Błędy: brak Start, brak wyników.

##### Earth‑like Route (ELW)
- Cel: trasa po planetach Earth‑like (`gui/tabs/spansh/elw.py`, `logic/elw_route.py`).
- Wejścia: Start/Cel + parametry R2R + Loop/Avoid.
- Wyjścia: lista systemów/ciał (schema `elw`).
- Błędy: brak Start, brak wyników.

##### Rocky/HMC Route
- Cel: trasa po Rocky/HMC (`gui/tabs/spansh/hmc.py`, `logic/hmc_route.py`).
- Wejścia: Start/Cel + parametry R2R + Loop/Avoid.
- Wyjścia: lista systemów/ciał (schema `hmc`).
- Błędy: brak Start, brak wyników.

##### Exomastery
- Cel: trasa po systemach z bio (exobiology) (`gui/tabs/spansh/exomastery.py`, `logic/exomastery.py`).
- Wejścia: Start/Cel + min landmark value + Loop/Avoid.
- Wyjścia: lista systemów/ciał (schema `exomastery`).
- Błędy: brak Start, brak wyników.

##### Trade Planner
- Cel: trasa handlowa SPANSH (`gui/tabs/spansh/trade.py`, `logic/trade.py`).
- Wejścia: System + Stacja, Kapitał, Max hop, Cargo, Max hops, Max DTA, Max age, flagi (Large pad itd.).
- Wyjścia: lista hopów (schema `trade`), auto‑schowek trasy.
- Błędy: brak Systemu, brak Stacji (wymagane przez SPANSH Trade).

##### Placeholdery (beta)
- Tourist Router, Fleet Carrier Router, Colonisation Plotter, Galaxy Plotter – taby z komunikatem „wkrótce” (`gui/tabs/spansh/__init__.py`).

#### Inara / EDTools
- Aktualnie stuby z etykietą „Wkrótce” (`gui/app.py`).

#### Inżynier
- Cel: sprawdzenie braków materiałów do receptur (`gui/tabs/engineer.py`, `logic/engineer.py`).
- Workflow: wybierz recepturę → „Sprawdź Braki” → komunikat głosowy/log.
- Wejścia: receptura z `config.RECEPTURY`.
- Wyjścia: komunikat o brakach / komplecie.
- Błędy: brak inventory w `config.STATE`.

#### Dziennik (Logbook)
- Cel: notatki w drzewie folderów (`gui/tabs/logbook.py`, `logic/logbook_manager.py`).
- Workflow: wybór folderu → dodaj wpis / folder → zapis do `user_logbook.json`.
- Wejścia: tytuł, treść, system, ciało, współrzędne.
- Wyjścia: drzewo Treeview + plik JSON.
- Błędy: brak pliku logbook (tworzy się domyślnie), opcjonalny brak `pyperclip`.

### Auto‑range / override / fallback
- Mechanizm używa `app_state.ship_state.jump_range_current_ly` i przełącza się na fallback z `planner_fallback_range_ly` jeśli brak danych (`gui/tabs/spansh/*`, `logic/spansh_client.py`).
- „Manual override” działa per‑tab (zmiana wartości Range ustawia flagę `_range_user_overridden`).

### Via / reverse / table wyniki / [SKOPIOWANO]
- Via: walidacja duplikatów i długości w `logic/neutron_via.py`, UI w `gui/tabs/spansh/neutron.py`.
- Reverse: tylko w Neutron (zamiana Start/Cel + odwrócenie Via).
- Wyniki: renderowane jako Treeview (pod flagami) lub proste listy tekstowe.
- [SKOPIOWANO]: marker kopii wiersza i w overlay (auto‑schowek) w `gui/common.py`.

## C) Architektura i przepływ danych (dev view)

### Entrypointy
- `main.py` – główne uruchomienie GUI i pętli journala.
- `debug_run.py` – diagnostyka importów i startu GUI.
- `tools/journal_replay.py` – odtwarzanie journala.
- `tools/smoke_tests_*.py` – smoke‑testy backendu i journala.

### Biblioteka GUI
- Tkinter + ttk (`gui/app.py`, `gui/tabs/*`).

### Mapa modułów (skrót)
- `app/` – pętla i stan aplikacji: `app/main_loop.py`, `app/state.py`, `app/route_manager.py`, `app/status_watchers.py`.
- `gui/` – UI: `gui/app.py`, `gui/menu_bar.py`, `gui/tabs/*`, `gui/common.py`, `gui/common_autocomplete.py`, `gui/table_schemas.py`.
- `logic/` – logika domenowa: planery (`logic/neutron.py`, `logic/riches.py`, `logic/ammonia.py`, `logic/elw_route.py`, `logic/hmc_route.py`, `logic/exomastery.py`, `logic/trade.py`), klienci (`logic/spansh_client.py`, `logic/spansh_payloads.py`), normalizacja (`logic/rows_normalizer.py`), system state (`logic/ship_state.py`, `logic/jump_range_engine.py`, `logic/fit_resolver.py`), eksploracja (`logic/system_value_engine.py`, `logic/exit_summary.py`), logbook (`logic/logbook_manager.py`), cache/dedup (`logic/cache_store.py`, `logic/request_dedup.py`).
- `logic/events/*` – routery eventów journala (fuel, fss, bio, navigation, trade, smuggler, materials).
- `tools/` – narzędzia CLI do smoke testów.
- `tests/` – unit/integration testy payloadów i via.

### Przepływ danych (high level)
1) Journal + Status/Market/Cargo
- `app/main_loop.py` tailluje `Journal.*.log` i przekazuje linie do `logic/event_handler.py`.
- `app/status_watchers.py` polluje `Status.json`, `Market.json`, `Cargo.json` i wywołuje `EventHandler.on_*`.

2) Eventy → AppState
- `logic/event_handler.py` deleguje eventy do `logic/events/*`.
- `logic/events/navigation_events.py` aktualizuje `app_state` i auto‑schowek (Next Hop).
- `logic/ship_state.py` aktualizuje masę/fuel/cargo i wylicza Jump Range.

3) Planery → SPANSH
- UI wywołuje `route_manager.start_route_thread()` → `logic/*` → `logic/spansh_client.py`.
- Payloady powstają w `logic/spansh_payloads.py`.
- Wyniki parsowane są przez `logic/rows_normalizer.py`.
- Render tabel przez `gui/common.py` + `gui/table_schemas.py`.

4) Auto‑clipboard / NEXT_HOP
- `gui/common.py` + `logic/route_clipboard.py` utrzymują „aktywną trasę”, kopiują FULL_ROUTE lub NEXT_HOP.
- Trigger NEXT_HOP jest wywoływany z `logic/events/navigation_events.py` i overlay (GUI).

### Warstwy
- UI: `gui/*`.
- Logika plannerów: `logic/*.py`.
- Providerzy: `logic/spansh_client.py`, `logic/utils/http_spansh.py`.
- Storage/cache: `config.py` (user_settings.json), `logic/cache_store.py` (AppData cache), `logic/logbook_manager.py` (user_logbook.json).
- Config/flags: `config.py` + `gui/tabs/settings.py`.
- Testy: `tests/*`, `tools/*`, `docs/RUNBOOK_SMOKE.md`.

## D) Konfiguracja i feature flags

### Gdzie jest konfiguracja
- `user_settings.json` zarządzany przez `ConfigManager` w `config.py`.
- `config.json` (exit summary) zarządzany przez `logic/config.py` (obecnie tylko w `app/state.py`).

### Pełna lista ustawień + defaulty (user_settings.json)

**Ścieżki i pliki**
- `log_dir` = `_default_log_dir()` → `main.py`, `app/main_loop.py`, `logic/events/files.py`, `tools/journal_replay.py`.
- `modules_data_enabled` = True → `gui/app.py` (load), `logic/ship_state.py`.
- `modules_data_path` = `renata_modules_data.json` → `gui/app.py`, `logic/modules_data.py`.
- `modules_data_autogen_enabled` = True → `gui/app.py`, `gui/tabs/pulpit.py`.
- `modules_data_debug` = False → (flaga nieużywana w kodzie).
- `modules_data_sources` = {fsd_url, booster_url, fallback_urls} → `logic/generate_renata_modules_data.py`.
- `status_poll_interval` = 0.5 (domyślny fallback) → `app/status_watchers.py`.
- `market_poll_interval` = 1.0 (domyślny fallback) → `app/status_watchers.py`.

**UI i zachowanie**
- `language` = pl → `gui/tabs/settings.py`.
- `theme` = dark → `gui/tabs/settings.py`.
- `use_system_theme` = True → `gui/tabs/settings.py`.
- `confirm_exit` = True → `gui/tabs/settings.py` (brak logiki zamykania w GUI).
- `ui_show_jump_range` = True → `gui/app.py`, `gui/tabs/pulpit.py`.
- `ui_jump_range_location` = both → `gui/app.py`, `gui/tabs/pulpit.py`.
- `ui_jump_range_show_limit` = True → `gui/app.py`, `gui/tabs/pulpit.py`.
- `ui_jump_range_debug_details` = False → `gui/app.py`, `gui/tabs/pulpit.py`.

**Głos / asystenci / alerty**
- `voice_enabled` = True → `logic/utils/notify.py`.
- `landing_pad_speech` = True → (flaga zdefiniowana, brak użycia w logice).
- `route_progress_speech` = True → (flaga zdefiniowana, brak użycia w logice).
- `fuel_warning` = True → `logic/events/fuel_events.py`.
- `fuel_warning_threshold_pct` = 15 → `logic/events/fuel_events.py`.
- `high_g_warning` = True → (flaga zdefiniowana, brak użycia w logice).
- `fss_assistant` = True → (flaga zdefiniowana, brak użycia w logice).
- `high_value_planets` = True → (flaga zdefiniowana, brak użycia w logice).
- `bio_assistant` = True → (flaga zdefiniowana, brak użycia w logice).
- `trade_jackpot_speech` = True → `logic/events/trade_events.py`.
- `smuggler_alert` = True → (flaga zdefiniowana, brak użycia w logice).
- `read_system_after_jump` = True → (flaga zdefiniowana, brak użycia w logice).

**Auto‑schowek / clipboard**
- `auto_clipboard` = True → `gui/common.py`.
- `auto_clipboard_mode` = FULL_ROUTE → `gui/common.py`.
- `auto_clipboard_next_hop_trigger` = fsdjump → `gui/common.py`.
- `auto_clipboard_next_hop_copy_on_route_ready` = False → `gui/common.py`.
- `auto_clipboard_next_hop_resync_policy` = nearest_forward → `gui/common.py`.
- `auto_clipboard_next_hop_allow_manual_advance` = True → `gui/common.py`, `gui/app.py`.
- `debug_next_hop` = False → `gui/common.py`.

**SPANSH / sieć**
- `spansh_timeout` = 20 → `logic/spansh_client.py`.
- `spansh_retries` = 3 → `logic/spansh_client.py`.
- `features.spansh.debug_payload` = False → `logic/exomastery.py`, `logic/trade.py`.
- `features.spansh.form_urlencoded_enabled` = True → `logic/spansh_client.py`.
- `features.spansh.neutron_via_enabled` = True → `logic/spansh_payloads.py`.
- `features.spansh.neutron_overcharge_enabled` = True → `logic/spansh_payloads.py`.
- `features.spansh.trade_market_age_enabled` = True → `logic/spansh_payloads.py`.
- `spansh_base_url` = https://spansh.co.uk/api (fallback) → `logic/spansh_client.py`.

**Ship State / JR**
- `ship_state_enabled` = True → `logic/event_handler.py`.
- `ship_state_use_status_json` = True → `logic/event_handler.py`, `logic/ship_state.py`.
- `ship_state_use_cargo_json` = True → `logic/event_handler.py`, `logic/ship_state.py`.
- `ship_state_debug` = False → `logic/ship_state.py`.

**Fit Resolver / Jump Range Engine**
- `fit_resolver_enabled` = True → `logic/ship_state.py`.
- `fit_resolver_debug` = False → `logic/fit_resolver.py`.
- `fit_resolver_fail_on_missing` = False → `logic/fit_resolver.py`, `logic/event_handler.py`.
- `jump_range_engine_enabled` = True → `logic/ship_state.py`.
- `jump_range_engine_debug` = False → `logic/jump_range_engine.py`.
- `jump_range_rounding` = 2 → `logic/jump_range_engine.py`.
- `jump_range_include_reservoir_mass` = True → `logic/jump_range_engine.py`.
- `jump_range_compute_on` = both → `logic/ship_state.py`.
- `jump_range_engineering_enabled` = True → `logic/jump_range_engine.py`.
- `jump_range_engineering_debug` = False → `logic/ship_state.py`.
- `jump_range_validate_enabled` = False → `logic/ship_state.py`.
- `jump_range_validate_debug` = False → `logic/ship_state.py`.
- `jump_range_validate_tolerance_ly` = 0.05 → `logic/ship_state.py`.
- `jump_range_validate_log_only` = True → `logic/ship_state.py`.

**Plannery**
- `planner_auto_use_ship_jump_range` = True → `logic/spansh_client.py`, `gui/tabs/spansh/*`.
- `planner_allow_manual_range_override` = True → `gui/tabs/spansh/*`.
- `planner_fallback_range_ly` = 30.0 → `logic/spansh_client.py`, `gui/tabs/spansh/*`.

**Tabela / schema**
- `features.tables.spansh_schema_enabled` = True → `gui/common.py`, `gui/table_schemas.py`.
- `features.tables.normalized_rows_enabled` = True → `gui/tabs/spansh/*`.
- `features.tables.schema_renderer_enabled` = True → `gui/common.py`.
- `features.tables.column_picker_enabled` = True → (flaga istnieje, brak UI).
- `features.tables.ui_badges_enabled` = True → `gui/common.py`.
- `tables_visible_columns` = {} → `gui/common.py`.

**Autocomplete / UI features**
- `features.ui.neutron_via_compact` = True → `gui/tabs/spansh/neutron.py`.
- `features.ui.neutron_via_autocomplete` = True → `gui/tabs/spansh/neutron.py`.
- `features.providers.system_lookup_online` = False → `gui/tabs/spansh/neutron.py`.
- `features.trade.station_autocomplete_by_system` = True → `gui/tabs/spansh/trade.py`.
- `features.trade.station_lookup_online` = False → `gui/tabs/spansh/trade.py`.

**Debug**
- `debug_autocomplete` = False → `gui/common_autocomplete.py`.
- `debug_cache` = False → `logic/cache_store.py`.
- `debug_dedup` = False → `logic/request_dedup.py`.

**Progi Maklera PRO**
- `jackpot_thresholds` = `DEFAULT_JACKPOT_THRESHOLDS` → `logic/events/trade_events.py`.

### Jak dodać nową flagę (zasada globalna)
1) Dodaj klucz i default w `config.py` w `DEFAULT_SETTINGS`.
2) Odczytuj flagę przez `config.get()` w odpowiednich modułach.
3) Jeśli flaga ma UI: dodaj do `gui/tabs/settings.py` (zmienna, UI i zapis w `_collect_config`).
4) Upewnij się, że nie łamiesz kompatybilności (stare klucze pozostają).

### config.json (RenataConfig)
- `exit_summary_enabled` = True, `voice_exit_summary` = True → `logic/config.py`, tylko inicjalizacja w `app/state.py`.

## E) Testy i jakość

### Co jest testowane
- Unit: payloady SPANSH (`tests/test_spansh_payloads.py`).
- Unit: walidacja Via (`tests/test_neutron_via.py`).
- Integration (opcjonalnie): SPANSH (`tests/test_spansh_integration.py`).
- Smoke: backend i journal (`tools/smoke_tests_beckendy.py`, `tools/smoke_tests_journal.py`).

### Jak odpalić wszystkie testy (copy/paste)
- `python tools/smoke_tests_beckendy.py`
- `python tools/smoke_tests_journal.py`
- Opcjonalnie: `python -m unittest` (dla tests/)

### Braki testowe (ryzyka)
- Brak testów GUI (taby, ustawienia, overlay).
- Brak testów logbook (CRUD, drag/move).
- Brak testów Jump Range Engine (in/out data + edge cases).
- Brak testów cache/dedup (TTL, concurrency).
- Brak testów ustawień (save/load + walidacja).

### Minimalny test plan dla release’a (manual)
- Uruchomienie GUI: `python main.py`.
- Pulpit: logi pojawiają się po odczycie journala.
- Spansh: wyznaczenie trasy w każdej sub‑zakładce (Neutron/R2R/Ammonia/ELW/HMC/Exo/Trade).
- Auto‑schowek: FULL_ROUTE i NEXT_HOP (kopiowanie do schowka).
- Overlay: pojawia się przy statusie, działa Copy / Copy next.
- Logbook: dodaj/edytuj/usuń wpis oraz folder.
- Settings: zapisz/odczytaj ustawienia (user_settings.json aktualizowany).

## F) Audyt UI/UX (min. 30 obserwacji)

### Spójność UI
1) Mieszanie fontów (Eurostile/Arial/Consolas) w różnych tabach (`gui/app.py`, `gui/tabs/*`, `gui/common.py`).
2) Mieszanie języka PL/EN w etykietach („Range/Max range/Max DTA”) (`gui/tabs/spansh/*`).
3) Różne nazwy akcji „Wyznacz/Calculate/Wyczyść” bez konsekwencji (`gui/tabs/spansh/*`).
4) Część widgetów to tk.*, część ttk.* bez spójnego stylu (`gui/app.py`, `gui/tabs/logbook.py`).
5) Logbook używa własnych kolorów i stylu Treeview niezależnych od globalnego theme (`gui/tabs/logbook.py`).
6) Różna gęstość i padding pól między tabami (np. neutron vs riches) (`gui/tabs/spansh/*`).

### Czytelność
7) Małe rozmiary fontu w overlay i statusach utrudniają szybki odczyt (`gui/app.py`).
8) Listy wyników to Listbox z długimi liniami – brak łamania i sortowania (`gui/common.py`).
9) Nagłówek tabeli to pierwszy wiersz listy – łatwo „zgubić” kolumny (`gui/common.py`).
10) [SKOPIOWANO] dopisywane do wiersza zaburza wyrównanie kolumn (`gui/common.py`).
11) Brak wizualnego wyróżnienia błędów w samych tabach (poza status label) (`gui/tabs/spansh/*`).
12) Placeholdery „wkrótce” wyglądają jak błąd lub niedziałająca funkcja (`gui/tabs/spansh/__init__.py`).

### Ergonomia
13) Brak domyślnych skrótów (Enter/Esc) w większości tabów (tylko Via ma Return) (`gui/tabs/spansh/*`).
14) Brak wskazania wymaganych pól (np. Trade Station) (`gui/tabs/spansh/trade.py`).
15) Brak prostej akcji „kopiuj trasę” obok listy wyników (tylko auto‑clipboard) (`gui/common.py`).
16) Brak wyszukiwarki w Settings (dużo opcji) (`gui/tabs/settings.py`).
17) Brak wyszukiwarki/filtrów w Logbook (`gui/tabs/logbook.py`).
18) Brak zapamiętywania rozmiaru/położenia okna (`gui/app.py`).

### Feedback/stany
19) Brak globalnego stanu „busy” podczas wyliczeń SPANSH (`app/route_manager.py`).
20) Brak spinnera/progressu dla zapytań sieciowych (pola wyglądają jak „zamrożone”) (`logic/spansh_client.py`).
21) Błędy SPANSH lądują w logu i statusie, ale nie mają kontekstu w UI (`gui/common.py`).
22) Brak jasnego „empty state” gdy brak wyników (Listbox po prostu pusty) (`gui/common.py`).
23) Brak feedbacku „zapisano ustawienia” poza MessageBox (brak logu) (`gui/tabs/settings.py`).
24) Debug printy w konsoli (np. kliknięcia) wyglądają jak „błędy” (`gui/app.py`).

### Przewidywalność
25) Trade akceptuje „System / Station” w jednym polu, ale nie komunikuje tego w UI (`gui/tabs/spansh/trade.py`).
26) Reverse dostępny tylko w Neutron, brak analogii w innych trasach (`gui/tabs/spansh/neutron.py`).
27) Różne nazwy dla tych samych parametrów (Range vs Max range) (`gui/tabs/spansh/*`).
28) Różne skróty i formaty jednostek (DTA/Dist/Distance) (`gui/tabs/spansh/*`).
29) Placeholdery tabs są „klikalne” mimo braku funkcji – brak jasnego „disabled” (`gui/tabs/spansh/__init__.py`).
30) Autocomplete znika przy ruchu okna (watcher), bez wyjaśnienia (`gui/app.py`, `gui/common_autocomplete.py`).

### Friendliness / „pro‑tool”
31) Brak jednoznacznych ikon/kolorów statusów na listach (wrażenie „surowego” UI).
32) Brak spójnego nagłówka sekcji w każdej zakładce (nie wiadomo „gdzie jestem”).
33) Listboxy wyglądają jak kontrolki developerskie (brak sortowania, brak headerów) (`gui/common.py`).
34) Inara/EDTools wyglądają jak błędne zakładki („Wkrótce” bez opisu) (`gui/app.py`).
35) Ustawienia są długie i płaskie – brak „kontekstu” co wpływa na co (`gui/tabs/settings.py`).
36) Brak ekranów pomocy/FAQ z opisem pól i workflow.

## F.1) Checklist „ładność i ergonomia” (wymagania)
- [ ] Hierarchia: najważniejsze akcje są wyraźne (Calculate/Wyznacz trasę), a reszta nie krzyczy
- [ ] Odstępy: nie ma „przyklejonych” kontrolek, layout oddycha
- [ ] Kontrast: tekst jest czytelny na ciemnym tle
- [ ] Nazewnictwo: wszędzie konsekwentnie „Start/Cel/Range/Radius/Max systems” (bez miksu)
- [ ] Błędy: jak coś nie działa (sieć, zły system), komunikat jest konkretny i po polsku
## G) Plan usprawnień (skrót)
- Pełny backlog: `docs/RENATA_UX_BACKLOG.md`.
- Diagramy: `docs/RENATA_ARCH.mmd`.

## H) Checklisty manualne (przed release)

- [ ] Start aplikacji `python main.py` bez błędów.
- [ ] Spansh: Neutron/R2R/Ammonia/ELW/HMC/Exo/Trade – każda zakładka zwraca listę wyników.
- [ ] Auto‑clipboard działa w trybie FULL_ROUTE i NEXT_HOP.
- [ ] Overlay pokazuje status i Next Hop, Copy działa.
- [ ] Logbook: dodaj/edytuj/usuń wpis, zapisz `user_logbook.json`.
- [ ] Ustawienia zapisują się do `user_settings.json` i odczytują po restarcie.
- [ ] Smoke tests: `python tools/smoke_tests_beckendy.py` oraz `python tools/smoke_tests_journal.py`.
