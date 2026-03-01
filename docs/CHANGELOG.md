# CHANGELOG.md

Ostatnia aktualizacja: 2026-03-01
Zakres: skondensowane zmiany release na podstawie `docs/internal/LAST_TICKET.MD`.

---

## v0.9.5 - changelog (domkniety)

### Added / Changed / Fixed (zbiorczo, commit history z LAST_TICKET od v0.9.4 do v0.9.5)

Added:
- System krotkich nazw TTS dla planet/cial (`System A 2` -> `A 2`) w calloutach exploration i DSS hintach (F35).
- Nowy flow komunikatow ExoBio: `Nowy wpis` -> `Kolejna probka` -> `Gatunek skompletowany` + finalna wycena 3/3 (F36).
- Pamiec boi nawigacyjnych (`visited_nav_beacons`) i suppress intro o pasywnym skanie w systemach juz odwiedzonych (F34).
- Smart Cash-In 2.0: collect-then-rank multi-provider, globalny dedupe/ranking, profile semantyczne, ship-size pad filter, auto-target do schowka, toggles w pulpicie (F32/F33).
- Rozszerzenia mapy i danych lokalnych gracza (PLAYERDB bridge/migrations, map metadata + quality gates) domkniete w paczkach F16/F20-F22/F31.
- Dziennik/Logbook v2: model `Entry`, mapowanie Journal -> Entry, akcje kontekstowe, integracja z nawigacja/chips i cache feedu po restarcie (F8/F9/F10/F19).
- Personal Galaxy Map w `Dziennik -> Mapa`: warstwy, filtry, legenda, PPM actions, Trade Compare v2, persistence view state, auto-center i auto-refresh po update PlayerDB (F20/F21/F22/F23/F31).

Changed:
- Eksploracja FSS liczy progres po realnych cialach (bez pasow asteroid/Belt), z poprawnym domykaniem 100% i poprawiona sekwencja milestone/fullscan (F30/F34/F35).
- Routing glosu dla krytycznych komunikatow exploration/exobio ma twardsze priorytety i bypass tam, gdzie wymagane sa callouty decyzji (F24/F35/F36).
- Cash-In profile i UI zostaly ujednolicone do nazw funkcjonalnych (`NEAREST/SECURE/EXPRESS/PLANETARY_VISTA`) z kompatybilnoscia aliasow legacy (F32/F33).
- PlayerDB rozszerzono od bazowego bridge do modelu map/exploration/cash-in (schema/migracje, ingest, provider, metadata gwiazd, visited nav-beacons) (F16/F31/F34).
- Runtime safety hardening dla dlugich sesji: lock-safe accessory `app_state`, bezpieczniejsze timery/queue GUI, watchdog lifecycle dla workerow i mniej ryzyka deadlockow/freeze (pakiety follow-up F23/F31/F36).

Fixed:
- Naprawiono blad mianownika w postepie FSS (pasy asteroid nie psuja procentu, brak falszywego 75% przy prostych systemach) (F30/F34/F35).
- Usunieto zbedny spam diagnostyczny paliwa z glownego widoku (`MSG_QUEUE`); startup fuel diagnostics trafiaja do debug/file log (F36).
- Naprawiono ucinanie waznych komunikatow przez matryce priorytetow i globalny cooldown TTS (w tym multi-body high-value oraz ExoBio 3/3) (F35/F36).
- Naprawiono startup fuel false-positive (`fuel startup uncertain`, `ambiguous_numeric_without_capacity`) przez potwierdzanie capacity, fallback last-known i bootstrap guards (F34/F36).
- Naprawiono powtarzanie "pasywnie z boi" oraz komunikaty zrodla danych w znanych/niezamieszkalych systemach (F34).
- Naprawiono trigger podsumowania eksploracji przy `StartJump`: flush pending exit summary tylko dla `JumpType=Hyperspace` (bez falszywego triggera na `Supercruise`).
- Naprawiono rozjazd runtime value po sprzedazy i po restarcie: domenowe resety po `SellExplorationData`/`SellOrganicData` + recovery respektuje eventy sprzedazy (`CASHIN-VALUE-INTEGRITY-SELL-RESET-01`).
- Naprawiono szereg regresji TTS/runtime: FIFO worker kolejki mowy, timeout guards (Piper/Winsound) i mniejsze ryzyko nakladania/ucinania komunikatow w dlugiej sesji.
- Naprawiono wydajnosc i odpornosc mapy przy duzych danych: debounce reloadow, batch lookup flag stacji (bez N+1), prefetch drilldown i stabilniejsze auto-refresh/reselection.
- Naprawiono niespojnosci polskich znakow (diakrytyki/mojibake) w templatekach TTS i wybranych tekstach UI, z normalizacja UTF-8 w calloutach.

Zakres release:
- v0.9.5 obejmuje domkniete paczki z `LAST_TICKET` od F11 do F36 (cash-in, playerdb, logbook, mapa, exploration, fuel, TTS, quality gates/smoke).

### FLOW-F11-CASH-IN-ASSISTANT-HARDENING (P0/P1)
- Domknieto paczke F11:
  - payout policy `UC/VISTA` (`brutto/fee/netto`),
  - kontrakt `StationCandidate` + provider details,
  - ranking `SAFE/FAST/SECURE`,
  - route handoff tylko na realnym celu (`system+stacja`),
  - startjump callouty z confidence policy,
  - quality gates i smoke.

### FLOW-F12-CASH-IN-CROSS-SYSTEM-NEAREST-STATION (P0)
- Dodano cross-system discovery kandydatow stacji pod Cash-In.
- Domknieto strict handoff:
  - brak placeholder targetu,
  - jasny komunikat blokady, gdy nie ma realnego celu.
- Quality pack F12 + smoke PASS.

### FLOW-F13-CASH-IN-PROVIDER-RESILIENCE (P0/P1)
- Wdrozono odpornosc providerow:
  - circuit breaker per endpoint,
  - retry/backoff,
  - stale cache (SWR),
  - fallback `local_known` + UX degradacji z reason codes.
- Quality pack F13 + smoke PASS.

### FLOW-F14-CASH-IN-NEAREST-REAL-TARGET-FIX (P0)
- Wdrozono limit diagnostyczny EDSM nearby (`requested` vs `effective radius` + reason).
- Dodano fallback `offline_index` (Spansh-derived) dla scenariuszy `providers_empty/503`.
- Domknieto quality gates:
  - online real target nie jest nadpisywany przez offline fallback,
  - offline/no-internet nadal moze zwrocic realny target (gdy index jest dostepny).

### FLOW-F15-CASH-IN-DUMP-TO-OFFLINE-INDEX (P0/P1)
- Settings Cash-In:
  - downloader `galaxy_stations.json.gz`,
  - builder `offline_station_index.json`,
  - progress/status i auto-wiring sciezki indexu.
- Domknieto quality gates F15 (dump -> index -> runtime real target).

### FLOW-F15-CASH-IN-USER-SUPPLIED-DATA-ATTRIBUTION-UI-01 (P1)
- Dla dump/index dodano jawny model prawny:
  - Renata nie hostuje ani nie dystrybuuje dumpow Spansh,
  - dump jest user-supplied (lokalny import),
  - atrybucja: `Spansh (c) Gareth Harper`.
- Zapis dopiety w UI i publicznych README.

### FLOW-F16-PLAYER_LOCAL_DB (bridge start)
- Rozpisano etap F16 (PLAYER_LOCAL_DB) w dokumentacji.
- Runtime bridge dla cash-in:
  - fallback order preferuje lokalne dane gracza (`local_known`) przed `offline_index`.

### FLOW-F8/F9/F10 - DZIENNIK, LOGBOOK, PERSISTENCJA (P0/P1)
- Domknieto fundament Dziennika:
  - model `Entry` + storage offline-first i migracje,
  - mapowanie `Journal -> Entry` + akcje "utworz wpis",
  - integracja nawigacji z chipsami system/station/body.
- Domknieto UX Dziennika:
  - context menu, move/edit metadata, filtry data + multitagi.
- Domknieto persistence i continuity:
  - kontrakt `app_state` (ui/preferences/domain/anti-spam),
  - restore kontekstu po restarcie (w tym continuity ExoBio z journala).

### FLOW-F19 - LOGBOOK CAPTAIN FEED V2 (P0/P1)
- Logbook feed z cache/restore po restarcie i po power-loss.
- Rozszerzone pokrycie eventow kapitanskich + klasy i sortowanie feedu.
- Rozbudowany panel informacyjny/podsumowania bez utraty czytelnosci.
- Journal replay smoke dla typowej sesji lotu (skoki, ladowanie, exobio, sprzedaz, incydenty).

### FLOW-F20/F21/F22/F23/F31 - PERSONAL GALAXY MAP (P0/P1)
- Mapa osadzona jako podzakladka `Dziennik -> Mapa` (MVP + UX polish).
- Render trasy i wezlow podrozy, drilldown system/station, warstwy i legenda.
- PPM actions, tooltipy, akcje map->entry, Trade Compare v2 (multiselect/modal/usability).
- Persistence stanu mapy: center/zoom/warstwy/filtry + restore po restarcie.
- Auto-refresh mapy po update PlayerDB (deferred refresh + debounce).
- Rozszerzenia F31:
  - metadata gwiazd (schema + ingest + provider),
  - visual coding + tooltip details,
  - auto-center na current system na starcie,
  - tryb renderowania `Trasa/Mapa` z coords view.

### CASHIN-VALUE-INTEGRITY-SELL-RESET-01 (P0)
- Runtime `SystemValueEngine` dostal domenowe resety wartosci:
  - `cartography`,
  - `exobiology`,
  - `all`.
- Eventy `SellExplorationData` / `SellOrganicData` (oraz `MultiSellExplorationData`) resetuja odpowiednia domene wartosci sesji.
- Bootstrap recovery uwzglednia eventy sprzedazy i nie odtwarza juz sprzedanych wartosci do `cash_in_session_estimated`.

### FLOW-F6-RELEASE-HARDENING-AND-SMOKE-01 (P0)
- Domknieto finalny gate FREE/PUB dla F6:
  - `py tools/public_repo_guard.py` PASS,
  - `py tools/public_repo_guard.py --zip release\\Renata_v0.9.4-preview_win_x64.zip` PASS,
  - `py tools/smoke_tests_beckendy.py` PASS,
  - `py tools/smoke_tests_journal.py` PASS.
- Potwierdzono sanity ZIP (brak sciezek private/PRO i runtime/user files) -> `ZIP_SANITY=PASS`.
- Zaktualizowano publiczne statusy faz F6:
  - `docs/Flow/public/FLOW.md`,
  - `docs/Flow/public/README.md`,
  - `docs/Flow/public/docs/REFAKTOR_STATUS.md`.

### TRADE-SELL-ASSIST-UI-REMOVAL-01 (P1)
- Usunieto panel `Sell Assist` z zakladki `Trade` (odchudzenie UI i mniej przeladowania informacji).
- Pozostawiono backendowy kontrakt Sell Assist:
  - ranking 2-3 opcji,
  - `skip_action=Pomijam`,
  - handoff `route_intent` bez auto-route.
- Usunieto smoke wiring dla compact panelu UI, pozostawiajac testy logiki runtime.

---

## v0.9.4 - changelog

### TRADE-COMMODITY-VISIBLE-01 (P0)
- Przebudowano normalizacje Trade pod oba warianty payloadu:
  - `commodity` (single),
  - `commodities[]` (multi).
- Dodano aliasy kluczy `snake_case` i `camelCase` dla cen, zyskow, cumulative i updated.
- Dla multi-commodity dodano agregacje:
  - `commodity_display` (`Towar +N`),
  - `total_profit`,
  - `profit`,
  - fallbacki na podstawie srednich wazonych.
- Zsynchronizowano schema tabeli Trade z danymi normalizera:
  - `Towar` -> `commodity_display`,
  - `Zysk [cr]` -> `total_profit`,
  - `Zysk/t [cr]` -> `profit`.
- Dodano pokrycie regresyjne dla single/multi, aliasow, updated i cumulative.

### SPANSH-LAYOUT-PARITY-01 (P1)
- Ujednolicono layout i rytm sekcji Spansh wzgledem wzorca Neutron.
- Dodano wspolny helper ukladu `akcje + status` w planner base.
- Zakladki plannerowe (`Riches`, `Ammonia`, `ELW`, `HMC`, `Exo`) dostaly wspolny model osadzenia i akcji.
- W `Neutron` i `Trade` przebudowano wiersz akcji/statusu na wspolny, wycentrowany uklad.

### TRADE-UPDATED-BUY-SELL-01 (P1)
- Dodano model freshness per strona transakcji:
  - `updated_buy_ago`,
  - `updated_sell_ago`.
- Obsluzono `market_updated_at` / `marketUpdatedAt` z fallbackami.
- `Updated` w tabeli i summary pokazuje pare `kupno / sprzedaz`.
- Dodano fallback wyliczania `jumps` per leg, gdy API nie zwraca `jumps`.
- Panel szczegolow pokazuje `Updated (kupno/sprzedaz)`.

### NEUTRON-EMPTY-STATE-SKELETON-01 (P1)
- W Neutron wymuszono skeleton table przy pustych wynikach (naglowki zawsze widoczne).
- Empty state dziala jako overlay tylko na body tabeli, bez zaslaniania naglowkow.
- Overlay automatycznie znika po pojawieniu sie wynikow.
- Dodano test regresyjny dla skeleton + overlay.

### FUEL-LOW-SCO-FALSE-POSITIVE-01 (P1)
- Utwardzono logike low-fuel pod transient startup/SCO.
- Alert niskiego paliwa wymaga potwierdzenia przy probkach niepewnych/flag-only.
- Ograniczono falszywe ostrzezenia bez utraty detekcji realnego low-fuel.
- Dodano test regresyjny pod ten scenariusz.

### FSS-PROGRESS-PL-VOICE-01 (P2)
- Ujednolicono polskie brzmienie progow FSS (25/50/75) pod TTS.
- Komunikaty progresu dostosowano do form czytelnych glosowo.
- Zachowano dedup i anty-spam polityki message_id.

### FSS-LAST-BODY-FULL-ORDER-01 (P0)
- Uporzadkowano kolejnosc FSS:
  - "Ostatnia planeta do skanowania" tylko dla `N-1/N`,
  - "System w pelni przeskanowany" dla `N/N`.
- Usunieto przypadki, gdzie "ostatnia planeta" zastapowala 100% lub padala po 100%.
- Dodano regresje dla scenariuszy 9/10->10/10 i 11/12->12/12.

### WINDOW-RESIZE-HITBOX-02 (P2)
- Dodano custom hitbox resize `8 px` dla:
  - prawej krawedzi,
  - dolnej krawedzi,
  - prawego dolnego rogu.
- Dodano odpowiednie kursory resize i guardy dla fullscreen/zoomed.
- Zachowano natywna ramke systemowa (bez `overrideredirect`).
- Dodano test techniczny wiringu resize.

### TRADE-LAYOUT-SPLIT-VIEW-01 (P1)
- Wdrozono split-view w Trade (`PanedWindow`):
  - gora: `Trasa: Handel`,
  - dol: `Szczegoly kroku`.
- Dodano toggle panelu szczegolow (`Pokaz/Ukryj szczegoly kroku`).
- Panel szczegolow startuje jako zwinity i aktywuje sie po wyborze kroku.
- Podlaczono lokalne scrollowanie poziome dla obu tabel Trade.
- Zachowano summary bar i logike payloadow/obliczen.

### TRADE-JUMPS-MARKET-AGE-01 (P1)
- Domknieto model `Wiek rynku K/S` (kupno/sprzedaz) i jego render.
- Zmieniono etykiete kolumny na `Wiek rynku K/S`.
- Dodano fallback wyliczania `Skoki [szt]`:
  - `ceil(distance_ly / jump_range_effective)` per leg.
- W panelu szczegolow dopieto mapowanie cen z pol zagniezdzonych:
  - `source_commodity.buy_price`,
  - `destination_commodity.sell_price`.
- Dodano regresje dla rynku K/S i cen zagniezdzonych.

### UI-GLOBAL-SCROLLBAR-WINDOW-COLOR-01 (P1)
- Ujednolicono globalny styl scrollbarow:
  - `TScrollbar`, `Vertical.TScrollbar`, `Horizontal.TScrollbar`.
- Podlaczono style do glownych widokow i tabel (`Spansh`, `Settings`, `Logbook`, dialogi).
- Dodano helper `gui/window_chrome.py` (best-effort DWM) dla koloru ramki/caption na Windows.
- Usunieto lokalne wymuszenia motywu, ktore psuly globalna spojnosc.
- Dodano regresje techniczna pod styl scrollbar/chrome wiring.

### SETTINGS-ADVANCED-SAVEBAR-LAYOUT-01 (P2)
- Poprawiono layout w `Konfiguracja -> Zaawansowane`.
- Pasek `Przywroc domyslne` / `Zapisz ustawienia` przeniesiono pod sekcje `Debug`
  (do kolejnego wiersza siatki), zamiast renderu w tym samym obszarze.

---

## Podsumowanie techniczne

- Zakres v0.9.4 domknal:
  - stabilnosc i czytelnosc Trade,
  - porzadek komunikatow FSS/fuel,
  - parity layoutu Spansh,
  - spojnosc stylu UI (scrollbary/chrome),
  - ergonomie okna i pustych stanow tabel.
- Testy smoke w trakcie tej paczki byly utrzymane na zielono, a kolejne regresje
  dopisano do `tools/smoke_tests_beckendy.py`.
