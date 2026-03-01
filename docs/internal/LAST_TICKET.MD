# LAST_TICKET.md

Ostatnia aktualizacja: 2026-02-28
Status: IN PROGRESS (FREE/PUB F12/F13/F14/F15/F16/F19/F20/F21/F22/F23/F24 domkniete; FSS milestone fix wdrozone; Mapa tryb renderowania Trasa/Mapa wdrozony (coords view z StarPos); F17 VOICE/UX backlog rozpisany; PRO STT layer deferred)
Cel: backlog feedbackowy + tracking wdrozenia FLOW (fazy 1-20) z podzialem FREE/PRO.

---

## FLOW snapshot (aktualny)

- Faza 1 (Backbone): DONE
- Faza 2 (Nawigacja i sprzedaz): DONE
- Faza 3 (Core eksploracji): DONE
- Faza 4 (Summary/Cash-In/Survival): DONE (FREE/PUB).
- Faza 5 (Combat + orkiestracja): DONE (FREE/PUB).
- Faza 6 (Granice PRO + hardening): DONE (FREE/PUB; PRO premium layer deferred).
- Faza 7 (Refaktor GUI + Mode System): DONE (FREE/PUB).
- Faza 8 (Dziennik / Logbook + Entry): DONE (FREE/PUB).
- Faza 9 (UX Dziennika): DONE (FREE/PUB).
- Faza 10 (Context Memory Persistence): DONE (FREE/PUB).
- Faza 11 (Cash-In Assistant hardening): DONE (FREE/PUB).
- Faza 12 (Cash-In cross-system nearest station): DONE (FREE/PUB).
- Faza 13 (Cash-In provider resilience): DONE (FREE/PUB).
- Faza 14 (Cash-In nearest real target fallback): DONE (FREE/PUB).
- Faza 15 (Cash-In dump -> offline index automation): DONE (FREE/PUB).
- Faza 16 (Player Local DB): DONE (FREE/PUB baseline: schema, ingest, query, provider, quality gates).
- Faza 17 (Voice UX + Clipboard gate): TODO (FREE/PUB planning).
- Faza 19 (Logbook Captain Feed v2): DONE (FREE/PUB).
- Faza 20 (Personal Galaxy Map MVP/Tkinter): DONE (FREE/PUB MVP mapy w `Dziennik -> Mapa`, F20-1..F20-7).
- Faza 21 (Personal Galaxy Map UX Polish): DONE (FREE/PUB; ergonomia, PPM, legenda, markery, Trade Compare v2).
- Faza 22 (Personal Galaxy Map follow-up fixes/UX): DONE (FREE/PUB; persist kontekstu mapy, center fix, Trade Compare modal usability + quality gates/smoke).
- Faza 23 (Runtime safety / stability fixes): DONE (FREE/PUB; paliwo false-positive, focus-safe GUI, auto-refresh mapy).
- Faza 24 (Exploration voice sequencing / callout hardening): DONE (FREE/PUB).
- Faza 25 (Exploration Value Integrity / DSS value accounting): DONE (FREE/PUB; DSS value upgrade + recovery).
- Faza 26 (High-G orbit trigger + gravity cache for approach): DONE (FREE/PUB; High-G przeniesione z `Scan` na approach/orbite, cache gravity in-memory).
- Faza 27 (Exploration cartography FSS value integrity): DONE (FREE/PUB; `PlanetClass` aliasy + hardening `NaN` fallback w `SystemValueEngine`).
- Faza 28 (Runtime audit follow-up: voice/text/cartography/recovery): DONE (FREE/PUB; diagnoza po audycie runtime + TTS).
- Faza 29 (PlayerDB test isolation / fixture contamination hygiene): DONE (FREE/PUB; test isolation + cleanup tools + docs/guardrails domkniete).
- Kolejny krok: follow-upy runtime UX/mapa/TTS wg testow w grze.
- Aktywny kierunek: follow-upy runtime/mapa/TTS wg diagnostyki z gameplayu.

---

## NOWY TICKET 0.9.5 (cash-in value integrity)

### CASHIN-VALUE-INTEGRITY-SELL-RESET-01 (P0)
Status: DONE (kod + testy regresyjne)

Problem (feedback gameplay):
- rozbieznosc miedzy estymacja Renaty (`cash_in_session_estimated`) a realnym wzrostem salda po sprzedazy,
- po sprzedazy (`SellExplorationData` / `SellOrganicData`) Renata potrafi nadal raportowac stare wartosci sesji,
- po restarcie aplikacji recovery moze odtworzyc wartosci, ktore zostaly juz sprzedane.

Zakres:
- runtime `SystemValueEngine` + router eventow sprzedazy + bootstrap recovery.
- bez zmiany historii finansowej PlayerDB (`cashin_history` zostaje source-of-truth dla historii).

#### Etap 1 - reset/clear w `SystemValueEngine`
Cel:
- dodac precyzyjne metody czyszczenia wartosci po sprzedazy z zachowaniem rozdzialu domen:
  - cartography (UC),
  - exobiology (Vista),
  - full reset (awaryjny/diagnostyczny).

Wymagania:
- poza licznikami wartosci czyscic tez kontenery deduplikacji i stan valuacji:
  - `seen_bodies`,
  - `cartography_bodies`,
  - `seen_species`,
  - `high_value_targets`,
  - discovery counters zalezne od domeny.
- metody musza byc deterministic i idempotent (podwojny reset nie zmienia stanu drugi raz).

#### Etap 2 - reakcja na eventy sprzedazy
Cel:
- dodac obsluge w runtime dla:
  - `SellExplorationData` -> clear domain `cartography`,
  - `SellOrganicData` -> clear domain `exobiology`,
  - (follow-up) `MultiSellExplorationData` -> clear domain `cartography`.

Wymagania:
- trigger resetu ma dzialac w `event_handler` po udanym przetworzeniu eventu,
- diagnostyka logowa ma pokazywac:
  - event,
  - domena resetu,
  - before/after totals (`carto/exobio/bonus/total`).

#### Etap 3 - hardening `WasMapped` w `analyze_scan_event`
Cel:
- ograniczyc zawyzanie estymacji DSS dla eventu `Scan`.

Wymagania:
- DSS value ma byc doliczane gdy:
  - mapowanie zostalo potwierdzone (`SAAScanComplete` upgrade), lub
  - `Scan` zawiera `WasMapped=True` i jest to pierwsza mapowana wycena danego body w tej sesji.
- ochrona przed wielokrotnym naliczeniem dla tych samych body (duplikaty/relog/recovery).
- utrzymac kompatybilnosc z obecnym upgradem `FSS -> DSS` na `SAAScanComplete`.

#### Etap 4 - synchronizacja z recovery
Cel:
- bootstrap recovery musi uwzgledniac eventy sprzedazy, aby nie odtwarzac juz sprzedanych wartosci.

Wymagania:
- rozszerzyc `_VALUE_EVENTS` w `exploration_value_recovery` o eventy sprzedazy i aplikowac reset domenowy,
- zachowac dotychczasowa diagnostyke `scan_counted/dss_upgrade_applied/...`,
- dodac nowe liczniki diagnostyczne `sale_reset_*`.

DoD:
- po `SellExplorationData` wartosc cartography/bonus sesji spada zgodnie z zakresem sprzedazy (w runtime),
- po `SellOrganicData` wartosc exobio sesji spada zgodnie z zakresem sprzedazy (w runtime),
- manual `Cash-in` po sprzedazy nie pokazuje stalego/starego payloadu z poprzedniego summary,
- po restarcie (bootstrap recovery) sprzedane dane nie wracaja do `cash_in_session_estimated`,
- testy regresyjne przechodza dla scenariuszy:
  - scan -> sell UC -> cash-in snapshot,
  - scan organic -> sell Vista -> cash-in snapshot,
  - scan -> sell -> restart -> recovery -> brak "odzyskanych" sprzedanych wartosci.

Wdrozenie (DONE):
- Etap 1 (`SystemValueEngine`):
  - dodane domenowe czyszczenie wartosci `clear_value_domain(...)` (`cartography` / `exobiology` / `all`),
  - reset obejmuje liczniki wartosci + kontenery deduplikacji i stanu valuacji.
  - commit: `c3a79df`
- Etap 2 (eventy sprzedazy):
  - `event_handler` wykonuje reset domeny po `SellExplorationData`/`SellOrganicData`,
  - dodana diagnostyka `VALUE cashin_sell_reset` (before/after `total/carto/exobio/bonus`).
  - commit: `0b1a0a0`
- Etap 3 (`WasMapped` hardening):
  - `analyze_scan_event` nie zawyza juz DSS przy `WasMapped=True` dla cial juz odkrytych,
  - upgrade DSS pozostaje potwierdzany przez `SAAScanComplete` lub bezpieczny warunek sesyjny.
  - commit: `a8f82ee`
- Etap 4 (recovery):
  - bootstrap recovery uwzglednia eventy sprzedazy:
    - `SellExplorationData`,
    - `MultiSellExplorationData`,
    - `SellOrganicData`,
  - dodane liczniki diagnostyczne `sale_reset_*`.
  - commit: `a8f82ee`

Testy:
- `py -m unittest tests.test_system_value_engine tests.test_f54_event_handler_sell_value_domain_reset tests.test_bootstrap_system_value_recovery -v` PASS

Uwagi:
- ten ticket nie zmienia historycznej tabeli `cashin_history` i raportowania rzeczywistych sprzedazy w PlayerDB,
- fokus ticketu to spojnosc runtime estymacji Renaty vs realny stan po eventach sprzedazy.

---

## FREE/PRO - status wdrozenia (snapshot)

### FREE (PUB) - WDROZONE

- Faza 1 (Backbone): DONE.
- Faza 2 (Nawigacja i sprzedaz): DONE.
- Faza 3 (Core eksploracji): DONE.
- Faza 4: `FLOW-F4-EXPLORATION-SUMMARY-BASE-01` - DONE.
- Faza 4: `FLOW-F4-CASH-IN-ASSISTANT-BASE-01` - DONE.
- Faza 4: `FLOW-F4-SURVIVAL-REBUY-AWARENESS-BASE-01` - DONE.
- Faza 4: `FLOW-F4-CROSS-MODULE-VOICE-PRIORITY-01` - DONE.
- Faza 4: `FLOW-F4-QUALITY-GATES-AND-SMOKE-01` - DONE.
- Faza 5: `FLOW-F5-COMBAT-AWARENESS-BASE-01` - DONE.
- Faza 5: `FLOW-F5-DISPATCHER-PRIORITY-MATRIX-01` - DONE.
- Faza 5: `FLOW-F5-VOICE-POLICY-WHY-WHEN-CONTRACT-01` - DONE.
- Faza 5: `FLOW-F5-ANTI-SPAM-REGRESSION-01` - DONE.
- Faza 5: `FLOW-F5-QUALITY-GATES-AND-SMOKE-01` - DONE.
- Faza 6: `FLOW-F6-FREE-PRO-CAPABILITY-AUDIT-01` - DONE.
- Faza 6: `FLOW-F6-VOICE-ETHICS-COMPLIANCE-01` - DONE.
- Faza 6: `FLOW-F6-DOCS-PRIVATE-PUBLIC-SYNC-01` - DONE.
- Faza 6: `FLOW-F6-RELEASE-HARDENING-AND-SMOKE-01` - DONE.
- Faza 7: `FLOW-F7-DASHBOARD-WIDGET-STRIP-BASE-01` - DONE.
- Faza 7: `FLOW-F7-CONSOLE-INTERACTION-SINGLE-SLOT-01` - DONE.
- Faza 7: `FLOW-F7-MODE-STATE-AUTO-DETECTOR-01` - DONE.
- Faza 7: `FLOW-F7-MODE-TTL-POLICY-01` - DONE.
- Faza 7: `FLOW-F7-MODE-MANUAL-OVERRIDE-AND-SAFETY-01` - DONE.
- Faza 7: `FLOW-F7-RISK-REBUY-WIDGET-CONTRACT-01` - DONE.
- Faza 7: `FLOW-F7-CARGO-VALUE-AT-RISK-ESTIMATOR-01` - DONE.
- Faza 7: `FLOW-F7-QUALITY-GATES-AND-SMOKE-01` - DONE.
- Faza 7: `TRADE-SELL-ASSIST-UI-REMOVAL-01` - DONE.
- Faza 8: `FLOW-F8-ENTRY-MODEL-AND-STORAGE-BASE-01` - DONE.
- Faza 8: `FLOW-F8-WPISY-UI-THREE-PANEL-01` - DONE.
- Faza 8: `FLOW-F8-LOGBOOK-JOURNAL-FEED-WHITELIST-01` - DONE.
- Faza 8: `FLOW-F8-JOURNAL-TO-ENTRY-MAPPING-ACTIONS-01` - DONE.
- Faza 8: `FLOW-F8-NAV-INTEGRATION-ENTRY-AND-CHIPS-01` - DONE.
- Faza 8: `FLOW-F8-PINBOARD-TEMPLATES-BASE-01` - DONE.
- Faza 8: `FLOW-F8-QUALITY-GATES-AND-SMOKE-01` - DONE.
- Faza 9: `FLOW-F9-ENTRY-CONTEXT-MENU-ACTIONS-AND-MOVE-01` - DONE.
- Faza 9: `FLOW-F9-ENTRY-MANUAL-METADATA-EDIT-01` - DONE.
- Faza 9: `FLOW-F9-FILTER-POPOVER-DATE-AND-MULTITAG-01` - DONE.
- Faza 9: `FLOW-F9-VOICE-COVERAGE-RUNTIME-GAPS-01` - DONE.

### FREE (PUB) - SNAPSHOT HISTORYCZNY (wymaga porzadkowania sekcji)

- FLOW-F10-CONTEXT-MEMORY-STATE-CONTRACT-01 (P0) - DONE.
- FLOW-F10-UI-STATE-PERSISTENCE-01 (P0) - DONE.
- FLOW-F10-PREFERENCES-PERSISTENCE-01 (P0) - DONE.
- FLOW-F10-DOMAIN-STATE-LAST-CONTEXT-01 (P1) - DONE.
- FLOW-F10-EXOBIO-SAMPLE-CONTINUITY-01 (P0) - DONE.
- FLOW-F10-ANTI-SPAM-PERSISTENCE-TTL-01 (P0) - DONE.
- FLOW-F10-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F11-CASH-IN-PAYOUT-POLICY-UC-VISTA-01 (P0) - DONE.
- FLOW-F11-STATION-CANDIDATE-CONTRACT-AND-PROVIDER-DETAILS-01 (P0) - DONE.
- FLOW-F11-CASH-IN-RANKING-PROFILES-SAFE-FAST-SECURE-01 (P0) - DONE.
- FLOW-F11-CASH-IN-ROUTE-HANDOFF-WITH-USER-CONSENT-01 (P1) - DONE.
- FLOW-F11-CASH-IN-STARTJUMP-CALLOUT-CONFIDENCE-01 (P1) - DONE.
- FLOW-F11-CASH-IN-UI-TRANSPARENCY-CONTRACT-01 (P1) - DONE.
- FLOW-F11-CASH-IN-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F11-CASH-IN-HOTKEY-TRIGGER-01 (P1) - DONE.
- FLOW-F11-CASH-IN-EDGE-CASE-FALLBACK-COMMS-01 (P0) - DONE.
- FLOW-F11-CASH-IN-ROUTE-PROFILE-STATE-PERSISTENCE-01 (P2) - DONE.
- FLOW-F12-CASH-IN-CROSS-SYSTEM-STATION-DISCOVERY-01 (P0) - DONE.
- FLOW-F12-CASH-IN-ROUTE-HANDOFF-REAL-TARGET-01 (P0) - DONE.
- FLOW-F12-CASH-IN-CROSS-SYSTEM-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F13-CASH-IN-PROVIDER-CIRCUIT-BREAKER-BACKOFF-01 (P0) - DONE.
- FLOW-F13-CASH-IN-STALE-CACHE-SWR-FALLBACK-01 (P0) - DONE.
- FLOW-F13-CASH-IN-FALLBACK-SOURCES-AND-UX-DEGRADATION-01 (P1) - DONE.
- FLOW-F13-CASH-IN-PROVIDER-RESILIENCE-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F14-CASH-IN-EDSM-RADIUS-CAP-AND-DIAGNOSTIC-01 (P0) - DONE.
- FLOW-F14-CASH-IN-SPANSH-DUMP-STATION-INDEX-FALLBACK-01 (P0) - DONE.
- FLOW-F14-CASH-IN-NEAREST-REAL-TARGET-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F15-CASH-IN-DUMP-DOWNLOAD-SETTINGS-UI-01 (P1) - DONE.
- FLOW-F15-CASH-IN-DUMP-TO-OFFLINE-INDEX-CONVERTER-AND-AUTO-WIRING-01 (P0) - DONE.
- FLOW-F15-CASH-IN-DUMP-TO-INDEX-END-TO-END-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.
- FLOW-F15-CASH-IN-USER-SUPPLIED-DATA-ATTRIBUTION-UI-01 (P1) - DONE.
- FLOW-F16-PLAYERDB-CONTRACT-AND-ORDER-BRIDGE-01 (P0) - DONE.
- FLOW-F16-PLAYERDB-SCHEMA-AND-MIGRATIONS-01 (P0) - DONE.
- FLOW-F16-PLAYERDB-INGEST-MARKET-DOCKED-JUMPS-01 (P0) - DONE.
- FLOW-F16-PLAYERDB-CASHIN-HISTORY-AND-QUERY-01 (P1) - DONE.
- FLOW-F16-PLAYERDB-PROVIDER-FOR-CASHIN-AND-MAP-01 (P0) - DONE.
- FLOW-F16-PLAYERDB-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE.

### PRO (private) - WDROZONE (infrastruktura/gates)

- Guard i routing publikacji (`PUB-PRO-ISOLATION-GATE-01`) - DONE.
- Warstwa capabilities FREE/PRO i smoke profile (z Fazy 1/2) - DONE.
- Commit routing `[PUB]`/`[PRO]` i checklisty release - DONE.

### PRO (private) - NIE WDROZONE (celowo deferred)

- Premium voice-first UX dla F4: `FLOW-F4-PRO-VOICE-UX-LAYER-01` - TODO (po domknieciu FREE F4).
- Premium voice-first UX dla F5: `FLOW-F5-PRO-VOICE-UX-LAYER-01` - TODO (po domknieciu FREE F5).
- Dodatkowe premium warstwy interakcji w nowych modulach (bez zmiany semantyki) - deferred.

---

## Szybka diagnoza (na podstawie kodu i testow manual)

1. `MSG.JUMPED_SYSTEM` to komunikat o biezacym systemie po skoku.
   - Dzisiaj brzmi jak "Skok. {system}."
   - Oczekiwane UX: "Aktualnie w {system}."

2. FSS progres i kolejnosc komunikatow potrafi sie rozjechac.
   - "75%" i "ostatnia planeta" potrafia wpasc za pozno.
   - "System w pelni przeskanowany" zalezy glownie od `FSSAllBodiesFound`.

3. Brakuje body-specific wskazowki DSS.
   - Jest wykrywanie ELW/WW/terraformable, ale bez tekstu typu:
     "Planeta X jest warta doglebnej analizy."

4. Exobio distance (realny prog) bywa nieslyszalne.
   - Watcher `Status.json` jest obecnie pollowany glownie przy nowych liniach Journal,
     co podczas chodzenia po planecie moze byc za rzadkie.

5. `WATCHER-STATUS` JSON/I/O to zwykle stan przejsciowy przy zapisie pliku przez gre.
   - Nie jest to krytyczny crash, ale UX loga musi byc spokojny i czytelny.

6. Bootstrap eventow po starcie appki moze odpalac TTS skokowy z historycznego wpisu Journal.
   - To daje efekt "dziwnego" komunikatu tuz po uruchomieniu.

---

### FLOW-F9-VOICE-COVERAGE-RUNTIME-GAPS-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Domknac luki pokrycia komunikatow Renaty w runtime FREE/PUB
  (policy map, renderer TTS, testy kontraktowe).

Zakres:
- `MSG.SMUGGLER_ILLEGAL_CARGO`:
  - dodane jawne policy TTS (bez fallbacku `silent`).
- `MSG.BODY_NO_PREV_DISCOVERY`:
  - dopiete do `ALLOWED_MESSAGES`,
  - dodany template rendera TTS.
- Dociagniete testy:
  - kontrakt policy + renderer,
  - smoke text-preprocessor.
- Aktualizacja dokumentacji:
  - `renata_mowa_logika_cooldown_detailed.md` (sekcja coverage runtime).

DoD:
- Brak `message_id` runtime, ktore wpadaja w `intent=silent` tylko przez brak wpisu policy.
- Komunikat `BODY_NO_PREV_DISCOVERY` jest realnie mowiony przez TTS.
- Pokrycie potwierdzone testami i smoke.

Wynik:
- `logic/event_insight_mapping.py`:
  - dodano `MSG.SMUGGLER_ILLEGAL_CARGO` do `TTS_POLICY_BY_MESSAGE_ID`
    (`intent=critical`, `category=alert`, `cooldown_policy=BYPASS_GLOBAL`).
- `logic/tts/text_preprocessor.py`:
  - `MSG.BODY_NO_PREV_DISCOVERY` dopiety do allowlisty i template.
- `tests/test_f5_voice_policy_contract.py`:
  - test policy smuggler + test rendera BODY_NO_PREV_DISCOVERY.
- `tests/test_f6_voice_ethics_compliance.py`:
  - rozszerzone sample voice o `BODY_NO_PREV_DISCOVERY` i `SMUGGLER_ILLEGAL_CARGO`.
- `tools/smoke_tests_beckendy.py`:
  - smoke dla obu komunikatow.
- `docs/Flow/private/docs/renata_mowa_logika_cooldown_detailed.md`:
  - dodana sekcja "Runtime coverage notes (FREE/PUB)".

---

## DONE (zrobione i domkniete)

- TTS-WIN-FOCUS-01
- NAV-NEXT-HOP-SEMANTICS-01
- NAV-NEXT-HOP-DUPLICATE-01
- WATCHER-STATUS-UX-01
- TTS-TUNING-01
- EXOBIO-GAP-01
- EXOBIO-RANGE-01
- EXOBIO-DISTANCE-REAL-01 (wersja bazowa)
- FSS-TTS-MESSAGE-ID-01
- EXIT-SUMMARY-WIRE-01
- SETTINGS-RUNTIME-CONTRACT-01
- ABOUT-DIALOG-REAL-01
- BRAND-NAMING-01
- JUMPED-SYSTEM-COPY-01

---

## NOWE TICKETY 0.9.2 (na bazie feedbacku)

### JUMPED-SYSTEM-COPY-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Zmienic komunikat `MSG.JUMPED_SYSTEM` na user-friendly:
  "Aktualnie w {system}."

Zakres:
- `logic/tts/text_preprocessor.py` (tylko microcopy).
- Bez zmian w eventach i routingu.

DoD:
- Po skoku / bootstrapie nie pada niezgrabny tekst typu "Skok...".
- Komunikat jest jednoznacznie "biezacy system".

Wynik:
- `logic/tts/text_preprocessor.py`: `MSG.JUMPED_SYSTEM` zmieniony z
  "Skok. {system}." na "Aktualnie w {system}."
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### FSS-COMPLETE-FALLBACK-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Ustabilizowac komunikaty FSS:
  - 25/50/75,
  - "ostatnia planeta",
  - "system w pelni przeskanowany".

Zakres:
- Dodac fallback "system w pelni przeskanowany" przy `Scan`,
  gdy `FSS_DISCOVERED >= FSS_TOTAL_BODIES`, nawet bez `FSSAllBodiesFound`.
- Zabezpieczyc kolejnosc: "ostatnia planeta" ma pasc przed "100%".
- Dedup/cooldown zostaje.

DoD:
- Brak sytuacji, gdzie "ostatnia planeta" pada po 100%.
- 100% jest mowione przewidywalnie.

Wynik:
- `logic/events/exploration_fss_events.py`:
  - dodany stan `FSS_FULL_WARNED`,
  - dodany helper `_maybe_speak_fss_full(...)`,
  - fallback 100% podlaczony do `handle_scan(...)`,
  - `handle_fss_all_bodies_found(...)` korzysta z tej samej sciezki.
- Kolejnosc wymuszona: jesli "ostatnia planeta" nie padla przed 100%,
  emituje sie tuz przed "system w pelni przeskanowany".
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### DSS-BODY-HINT-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Dodac komunikat body-specific dla wartosciowej planety podczas skanowania.

Zakres:
- Wysokowartosciowy trigger + nazwa ciala (`BodyName`) w komunikacie, np.:
  "Planeta {BodyName} jest warta doglebnej analizy DSS."
- Fallback do obecnej generycznej tresci, gdy brak nazwy.

DoD:
- Podczas FSS/Scan gracz dostaje jasny "co warto robic dalej".

Wynik:
- `logic/events/exploration_high_value_events.py`:
  - komunikaty ELW/WW/Terraformable sa body-specific, gdy jest `BodyName`,
  - tresc: `Planeta {BodyName} jest warta doglebnej analizy DSS.`,
  - fallback na generyczny komunikat, gdy nazwa ciala nie jest dostepna.
- `logic/tts/text_preprocessor.py`:
  - `MSG.ELW_DETECTED` dolaczony do sciezki `raw_text`, zeby nie tracic body-specific tresci.
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### BOOTSTRAP-TTS-GUARD-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Ograniczyc TTS na starcie appki dla historycznych eventow Journal.

Zakres:
- Rozroznienie `bootstrap replay` vs `live event`.
- Dla replay: bez komunikatow nawigacyjnych albo tylko neutralny status.

DoD:
- Po uruchomieniu Renata nie mowi mylacych komunikatow "next hop" z przeszlosci.

Wynik:
- `app/state.py`: dodana flaga runtime `bootstrap_replay`.
- `app/main_loop.py`: podczas `_bootstrap_state(...)` ustawiane jest `bootstrap_replay=True`,
  po zakonczeniu replay wraca `False`.
- `logic/events/navigation_events.py`: dla replay startupowego zablokowane TTS nawigacyjne
  (`MSG.NEXT_HOP`, `MSG.JUMPED_SYSTEM`, copy-confirm), przy zachowaniu aktualizacji stanu.
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### WATCHER-STATUS-MSG-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Dalsze uspokojenie komunikatow STATUS watcher, bez utraty diagnostyki.

Zakres:
- Komunikaty przejsciowe JSON/I/O trzymac jako techniczny warning,
  bez alarmowego tonu i bez TTS.
- Czytelny wording: "plik chwilowo niegotowy".

DoD:
- Brak "straszenia" usera na starcie.

Wynik:
- `app/status_watchers.py`:
  - wording status-watchera uproszczony i uspokojony (bez "blad", bez surowych wyjatkow),
  - komunikaty pozostaja techniczne i jednokrotne (`_log_once`),
  - nadal bez TTS (tylko log watcherow).
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### EXOBIO-STATUS-POLL-01 (P1)
Status: DONE (kod + smoke; manual verify pending)

Cel:
- Zapewnic stabilny odczyt pozycji dla exobio distance podczas marszu po planecie.

Zakres:
- Sprawdzic i ewentualnie odseparowac polling `StatusWatcher` od naplywu nowych linii Journal.
- Zachowac lekki polling i brak spamu CPU.

DoD:
- Komunikat o przekroczeniu progu dystansu pojawia sie przewidywalnie w realnej rozgrywce.

Uwagi:
- Ten ticket uruchamiamy po kolejnej sesji manualnych testow exobio na zywo.

Wynik:
- `app/main_loop.py`: watchery (`Status/Market/Cargo`) sa pollowane takze wtedy,
  gdy Journal chwilowo nie ma nowych linii (idle loop).
- To usuwa zaleznosc exobio-distance od naplywu eventow Journal podczas marszu po planecie.
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

## NOWE TICKETY (po kolejnym feedbacku graczy)

### SETTINGS-SCROLL-01 (P0)
Status: DONE

Cel:
- Zapewnic pelna przewijalnosc wszystkich zakladek w Settings (FREE i pelny widok).

Zakres:
- Osadzic zawartosc kazdej zakladki settings w `Canvas + Scrollbar`.
- Dodac obsluge `MouseWheel` oraz przewijania klawiatura.
- Zachowac obecny layout i style (bez przebudowy UX).

DoD:
- Przy malej wysokosci okna wszystkie opcje sa dostepne na kazdej zakladce.
- Brak "ucietych" pol ponizej dolnej krawedzi (zarowno FREE, jak i full settings).
- Brak regresji zapisu ustawien.

Test:
- Manual: zmniejszyc wysokosc okna Settings i przejsc przez wszystkie zakladki.
- Smoke: backend + journal PASS.
Wykonanie:
- Wszystkie zakladki Settings (FREE i pelne) sa osadzone w `Canvas + Scrollbar`.
- Dodano obsluge `MouseWheel`, `PageUp/PageDown`, `Ctrl+Home/Ctrl+End`.

Wynik testow:
- `py tools/smoke_tests_beckendy.py`: PASS 15/15.
- `py tools/smoke_tests_journal.py`: PASS 5/5.

---

### STARTUP-SYSTEM-STATE-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Uspokoic UX startupu, gdy `current_system` jest chwilowo nieznany.

Zakres:
- Dodac przejsciowy status startupowy:
  "Oczekiwanie na dane z gry (Location/FSDJump)".
- Nie emitowac mylacych komunikatow kontekstowych zanim pojawi sie pierwszy
  realny event systemowy z Journal.
- Po pierwszym eventcie od razu przelaczyc status na normalny.

DoD:
- User nie widzi "blednego" stanu przy zimnym starcie appki.
- Po pojawieniu sie eventu system ustawia sie przewidywalnie.
- Brak regresji bootstrapu i route/TTS.

Test:
- Manual: uruchom appke przed gra i po zaladowaniu do cockpit.
- Manual: scenariusz dwoch kont (Steam + Frontier login).

Wynik:
- Dodano runtime flage `app_state.has_live_system_event`, ustawiana dopiero po
  pierwszym realnym (nie-bootstrap) evencie `Location/FSDJump/CarrierJump`.
- Bootstrap replay nie ustawia juz "live" kontekstu UI (brak mylacego startu).
- Pulpit pokazuje przejsciowy status: `System: [Czekam na dane...]`.
- Dodano startupowy komunikat: `Oczekiwanie na dane z gry (Location/FSDJump).`
  gdy bootstrap nie ma realnego eventu systemowego.
- Prefill Trade i fallback sugestii stacji respektuja `has_live_system_event`.
- Smoke: backend 15/15 PASS, journal 5/5 PASS.

---

### TTS-FOCUS-REGRESSION-CHECK-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Potwierdzic brak focus-steal i brak czarnego okna konsoli podczas TTS.

Zakres:
- Utrzymanie sciezki uruchamiania Pipera w tle:
  `subprocess.STARTUPINFO + CREATE_NO_WINDOW`.
- Dodanie preflight runtime Pipera (DLL + `espeak-ng-data`) przed `subprocess.run`,
  zeby nie uruchamiac niekompletnego runtime i nie wywolywac popupow systemowych.
- Pozostawienie jednoznacznego logu wyboru engine i zrodla:
  `piper(settings|appdata)` / `pyttsx3(fallback)`.

DoD:
- Brak wyskakujacego terminala przy mowieniu Renaty.
- Brak "wyrzucania" gry na front przez probe uruchomienia niekompletnego Pipera.
- Fallback na `pyttsx3` gdy runtime Pipera nie jest kompletny.
- Log diagnostyczny jednoznacznie pokazuje aktywny engine.

Wynik:
- `logic/tts/piper_tts.py`:
  - dodany preflight kompletnego runtime (`piper_phonemize.dll`, `espeak-ng.dll`,
    `onnxruntime*.dll`, katalog `espeak-ng-data`),
  - selekcja `settings/appdata` akceptuje tylko kompletne runtime,
  - dodatkowy guard w `speak(...)` blokuje uruchomienie Pipera bez kompletu plikow.
- Smoke:
  - `py tools/smoke_tests_beckendy.py`: PASS 15/15
  - `py tools/smoke_tests_journal.py`: PASS 5/5

---

## Kolejnosc realizacji (proponowana)

1. SETTINGS-SCROLL-01 (P0)
2. STARTUP-SYSTEM-STATE-01 (P1)
3. Manual verify exobio distance cue in live gameplay

---

## Definicja "done" dla paczki 0.9.2

- Brak mylacego "next hop" po starcie.
- FSS komunikaty sa logiczne czasowo (last body przed 100%).
- Jest przynajmniej 1 body-specific hint DSS.
- Watcher status nie straszy usera.
- Exobio distance potwierdzone manualnie w terenie.

---

## EPIC: NAV-SYMBIOSIS-01 (Spansh + In-Game Route)

Cel:
- Symbioza dwoch warstw nawigacji:
  - Spansh = plan strategiczny (milestones, np. kolejne neutrony),
  - In-game NavRoute = nawigacja taktyczna "tu i teraz" (realne skoki do aktywnego celu).
- Wyeliminowanie falszywego `ROUTE_DESYNC` przy normalnym locie do pierwszego neutrona.

### NAVROUTE-INGEST-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Renata czyta trase ustawiona w grze (`NavRoute.json`) jako zrodlo taktyczne.

Zakres:
- Watcher `NavRoute.json` (load + refresh po zmianie pliku).
- Parser endpointu + listy systemow.
- Zapis do `app_state.nav_route` (osobno od trasy Spansha).

DoD:
- Po ustawieniu trasy w Galaxy Map Renata widzi endpoint i liczbe skokow.
- Brak crashy gdy `NavRoute.json` jest puste/chwilowo niegotowe.

Wynik:
- `app/state.py`: dodano runtime `nav_route` + API `set_nav_route(...)` i `clear_nav_route(...)`.
- `logic/events/navigation_events.py`: dodano `handle_navroute_update(...)` z parserem endpointu/listy systemow.
- `logic/event_handler.py`: podlaczone `on_navroute_update(...)` do glownego handlera.
- Commit: `e2af6f2`.

---

### MILESTONE-TRACKER-01 (P0)
Status: DONE (kod + test techniczny)

Cel:
- Trasa Spansh (neutron) dziala jako plan strategiczny z aktywnym milestone.

Zakres:
- Model `spansh_milestones` + indeks aktywnego milestone.
- Przejscie na kolejny milestone po osiagnieciu systemu celu.

DoD:
- Renata poprawnie trzyma aktywny punkt Spansha (bez skakania indeksu).
- Dziala dla odcinkow 10+ zwyklych skokow miedzy neutronami.

Wynik:
- Dodano model milestone'ow Spansha w `app_state`:
  - `spansh_milestones`,
  - `spansh_milestone_index`,
  - `spansh_milestone_mode`.
- Dodano API:
  - `set_spansh_milestones(...)`,
  - `clear_spansh_milestones(...)`,
  - `get_active_spansh_milestone()`,
  - `update_spansh_milestone_on_system(...)`.
- `NeutronTab` buduje milestone'y z punktow neutronowych + zawsze dodaje cel koncowy.
- Aktualizacja indeksu milestone jest podlaczona pod `Location/FSDJump/CarrierJump`.

---

### NEXT-HOP-SYMBIOSIS-01 (P0)
Status: DONE (kod + smoke)

Cel:
- `NEXT_HOP` korzysta z symbiozy (milestone + NavRoute) i nie spamuje desync.

Zakres:
- Brak `ROUTE_DESYNC`, gdy endpoint NavRoute zgadza sie z aktywnym milestone.
- `NEXT_HOP_COPIED` dalej dziala i wskazuje realny kolejny cel.

DoD:
- Neutron route: brak falszywego "poza trasa" po kazdym skoku.
- Clipboard/overlay bez regresji.

Wynik:
- `gui/common.py`: dodano guard `_is_navroute_aligned_with_active_milestone(...)`.
- Jesli endpoint `NavRoute` pokrywa aktywny milestone Spansha i biezacy system jest na `NavRoute`,
  Renata nie emituje `ROUTE_DESYNC`.
- Commit: `1388776`.

---

### DESYNC-GUARD-REAL-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Komunikat "poza trasa" tylko przy realnym odejsciu od planu.

Zakres:
- Twardy warunek desync: endpoint NavRoute != aktywny milestone przez N kolejnych skokow.
- Cooldown i dedup komunikatu desync.
- Reset po powrocie na poprawny kierunek.

DoD:
- Brak spamu desync.
- Ostrzezenie pojawia sie tylko przy realnej zmianie kierunku.

Wynik:
- `gui/common.py`: dodano licznik `_ACTIVE_ROUTE_DESYNC_STRIKES` + flage `_ACTIVE_ROUTE_DESYNC_ACTIVE`.
- `ROUTE_DESYNC` emituje sie dopiero po `auto_clipboard_next_hop_desync_confirm_jumps` (domyslnie `2`).
- Po powrocie na trase licznik i flaga sa resetowane.
- Commit: `4d9adc4`.

---

### PROGRESS-TO-MILESTONE-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Procentowy progres do aktywnego milestone na bazie in-game route.

Zakres:
- Progi: 25/50/75/100.
- Microcopy typu: "25%% drogi do pierwszego FSboosta."
- 1 komunikat na prog (dedup).

DoD:
- Gracz dostaje czytelny progres do kolejnego neutrona/celu.
- Brak dublowania tych samych progow.

Wynik:
- `gui/common.py`:
  - dodano tracker progresu do aktywnego milestone (`_ACTIVE_MILESTONE_*`),
  - progi 25/50/75/100 liczone sa na bazie pozycji na aktywnej trasie,
  - dedup per milestone (kazdy prog mowi sie raz), reset po zmianie milestone.
- `logic/tts/text_preprocessor.py`:
  - dodano `MSG.MILESTONE_PROGRESS`, `MSG.MILESTONE_REACHED`.
- `logic/utils/notify.py`:
  - nowe `message_id` dopiete do polityki TTS.
- Testy:
  - `py -m compileall gui/common.py logic/tts/text_preprocessor.py logic/utils/notify.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 15/15
  - `py tools/smoke_tests_journal.py` PASS 5/5

---

### UX-COPY-NAV-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Uporzadkowac microcopy statusow symbiozy.

Zakres:
- "Do boosta...", "Milestone osiagniety", "Przechodze do kolejnego celu".
- Bez technicznych terminow.

DoD:
- Krotkie, czytelne komunikaty zgodne z polityka TTS anti-spam.

Wynik:
- `logic/tts/text_preprocessor.py`:
  - `MSG.MILESTONE_REACHED` otrzymal czytelna mikrocopy przejscia:
    "Cel odcinka osiagniety ... Przechodze do kolejnego celu ..."
    (gdy znany jest kolejny milestone).
- `gui/common.py`:
  - dodany trigger "transition cue" przy osiagnieciu milestone,
    zanim zacznie sie liczenie kolejnego odcinka,
  - status techniczny uproszczony (bez terminow wewnetrznych).
- Efekt UX:
  - gracz dostaje jasny komunikat zamkniecia odcinka i przejscia dalej,
    zamiast "suchego" lub technicznego wordingu.
- Testy:
  - `py -m compileall gui/common.py logic/tts/text_preprocessor.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 15/15
  - `py tools/smoke_tests_journal.py` PASS 5/5

---

### TEST-NAV-SYMBIOSIS-01 (P0)
Status: DONE (test techniczny + smoke)

Cel:
- Potwierdzic stabilnosc przed releasem.

Scenariusz manual:
1. Neutron route z 10+ skokami do pierwszego neutrona.
2. Lot zgodnie z trasa: brak falszywego desync.
3. Zmiana kierunku przez gracza: desync pojawia sie po warunku N skokow.
4. Powrot na trase: desync znika, progres wraca.

DoD:
- Scenariusze 1-4 przechodza.
- Brak regresji w NEXT_HOP i clipboard.

Wynik:
- Dodano test techniczny do smoke:
  - `tools/smoke_tests_journal.py::test_nav_symbiosis_guard_and_desync`
  - pokrywa:
    1) aligned NavRoute + milestone -> brak falszywego `ROUTE_DESYNC`,
    2) real off-route -> `ROUTE_DESYNC`,
    3) powrot na trase -> reset stanu desync.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 15/15
  - `py tools/smoke_tests_journal.py` PASS 6/6
- Manualna walidacja lotu zostaje jako check release (zgodnie z runbookiem), ale
  krytyczna logika ma teraz staly test regresyjny.

---

## Kolejnosc realizacji (NAV-SYMBIOSIS-01)

1. (domkniete) UX-COPY-NAV-01
2. (domkniete) TEST-NAV-SYMBIOSIS-01

---

## NOWE TICKETY (feedback Cmdr Czuczik O7 - Spansh / Trade / Exobio)

### SPANSH-NEUTRON-PARITY-ALL-TABS-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Wymusic pelna spojnosc UX i zachowania wszystkich zakladek Spansh wzgledem wzorca Neutron.

Zakres:
- Neutron traktujemy jako baseline UX i zachowania (layout, interakcje, menu, akcje na wierszu, copy/export).
- Dociagamy do tego samego standardu: `ammonia`, `elw`, `hmc`, `exomastery`, `riches`, `trade`.
- Ujednolicamy komponenty wspolne, aby kolejne poprawki nie rozjezdzaly zakladek.
- Tworzymy matrix parity (zakladka x funkcja) i oznaczamy brakujace elementy jako blokery releasu.

DoD:
- Wszystkie zakladki Spansh maja ten sam standard obslugi co Neutron (poza jawnie uzasadnionymi roznicami domenowymi).
- Matrix parity ma kompletne PASS dla funkcji krytycznych (copy/export/row actions/statusy).
- Brak regresji po smoke i manual check per zakladka.

Wynik:
- `gui/tabs/spansh/planner_base.py`:
  - dodano wspolny mechanizm PPM dla plannerow opartych o base:
    - payload wyniku (`_get_results_payload`),
    - akcje kontekstowe (`_get_results_actions`),
    - wspolne podpiecie menu (`_attach_default_results_context_menu`),
    - reset i trzymanie `_results_rows` do akcji row-level.
- Podpiecie tego samego standardu PPM do zakladek:
  - `gui/tabs/spansh/ammonia.py`
  - `gui/tabs/spansh/elw.py`
  - `gui/tabs/spansh/hmc.py`
  - `gui/tabs/spansh/exomastery.py`
  - `gui/tabs/spansh/riches.py`
- Efekt:
  - zachowanie PPM i akcje "copy/export/row actions" sa spojne wzgledem wzorca Neutron
    na wszystkich plannerach opartych o `SpanshPlannerBase`.
- Testy:
  - `py -m compileall gui/tabs/spansh/planner_base.py gui/tabs/spansh/ammonia.py gui/tabs/spansh/elw.py gui/tabs/spansh/hmc.py gui/tabs/spansh/riches.py gui/tabs/spansh/exomastery.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 16/16
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### SPANSH-COPY-SYSTEM-COVERAGE-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Przywrocic kopiowanie nazw systemow we wszystkich zakladkach Spansh, nie tylko Neutron/Handel.

Zakres:
- Ujednolicic mapowanie "system field" dla schematow: ammonia/elw/hmc/exomastery/riches/neutron/trade.
- Upewnic sie, ze akcje kopiowania korzystaja z jednego helpera i jednej sciezki danych.
- Dodac fallback "brak nazwy systemu" zamiast kopiowania pustego stringa.

DoD:
- "Kopiuj system" dziala w kazdej zakladce Spansh.
- Brak pustego schowka dla poprawnych wynikow.
- Manual matrix per zakladka: PASS.

Wynik:
- Dodano centralny resolver systemu dla kopiowania:
  - `gui/common_tables.py::resolve_copy_system_value(...)`
  - mapowanie per schema: `ammonia/elw/hmc/exomastery/riches/neutron/trade`
  - fallback: `brak nazwy systemu` zamiast pustego schowka.
- Wszystkie zakladki Spansh korzystaja z jednej sciezki danych dla "Kopiuj system":
  - planner base: `gui/tabs/spansh/planner_base.py`
  - neutron: `gui/tabs/spansh/neutron.py`
  - trade: `gui/tabs/spansh/trade.py`
- Dodano test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_spansh_system_copy_mapping`
  - pokrywa mapowanie schema + fallback brakujacej nazwy.
- Testy:
  - `py -m compileall gui/common_tables.py gui/common.py gui/tabs/spansh/planner_base.py gui/tabs/spansh/neutron.py gui/tabs/spansh/trade.py tools/smoke_tests_beckendy.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 17/17
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### SPANSH-COPY-MODE-SELECTION-PARITY-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Ujednolicic i naprawic tryby kopiowania w calym Spansh (wzor: dzialanie docelowe z Neutron), aby nie bylo kopiowania tylko 1 wiersza.

Zakres:
- Poprawic rozroznienie trybow kopiowania: "jeden wiersz", "zaznaczone", "wszystkie" we wszystkich zakladkach Spansh.
- Dodac jawny mechanizm zaznaczania wierszy (checkbox/selection model) dla masowego kopiowania.
- Ujednolicic zachowanie menu kontekstowego i skrotow miedzy zakladkami.
- Tryby kopiowania maja byc osobnymi pozycjami PPM obok "Kopiuj system" (nie jako podmenu pod "Kopiuj system").

DoD:
- Kazdy tryb kopiowania zwraca poprawna liczbe wierszy we wszystkich zakladkach Spansh.
- Zaznaczenie kilku wierszy kopiuje tylko te pozycje, niezaleznie od zakladki.
- W PPM widoczne sa oddzielne akcje: "Kopiuj wiersz", "Kopiuj zaznaczone", "Kopiuj wszystkie", obok "Kopiuj system".
- Brak regresji "copy next hop".

Wynik:
- Dodano tryby kopiowania jako osobne pozycje PPM (bez podmenu pod "Kopiuj system"):
  - `Kopiuj wiersz`
  - `Kopiuj zaznaczone`
  - `Kopiuj wszystkie`
- Tryby sa wdrozone i spojne dla:
  - plannerow opartych o base (`gui/tabs/spansh/planner_base.py`)
  - `gui/tabs/spansh/neutron.py`
  - `gui/tabs/spansh/trade.py`
- Dodano selection model do masowego kopiowania:
  - `Listbox` i `Treeview` przelaczone na `selectmode=\"extended\"` (`gui/common_tables.py`)
  - PPM nie kasuje wielokrotnego zaznaczenia przy prawym kliknieciu.
- Dodano test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_spansh_copy_mode_actions`
  - sprawdza obecne akcje kopiowania i zabezpieczenia multi-select.
- Testy:
  - `py -m compileall gui/common_tables.py gui/tabs/spansh/planner_base.py gui/tabs/spansh/neutron.py gui/tabs/spansh/trade.py tools/smoke_tests_beckendy.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 18/18
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### SPANSH-EXPORT-CSV-EXCEL-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Naprawic eksport do arkusza (CSV/TSV) we wszystkich zakladkach Spansh, aby po wklejeniu do Excela dane byly czytelne.

Zakres:
- Dodac opcje kopiowania z naglowkami kolumn.
- Poprawic format CSV/TSV tak, aby nie powstawal output "same przecinki".
- Dodac w PPM podmenu eksportu (np. "Kopiuj jako"), z opcjami co najmniej: CSV i TSV.
- Dodac szybka akcje "Kopiuj do Excela (TSV + naglowki)".

DoD:
- Wklejenie do Excela daje kolumny z danymi (bez pustych przecinkow).
- Naglowki sa obecne w trybie "z naglowkami".
- PPM ma czytelny wybor formatu: "Kopiuj jako CSV" i "Kopiuj jako TSV" (podmenu eksportu).
- Pokrycie testem helperow formatowania.

Wynik:
- Dodano eksport z naglowkami i helpery formatowania:
  - `gui/common_tables.py`:
    - `format_header_delimited(...)`
    - `format_row_delimited_with_header(...)`
- Rozszerzono PPM o podmenu eksportu i szybka akcje Excel:
  - `Kopiuj do Excela (TSV + naglowki)`
  - `Kopiuj jako` ->
    - `Kopiuj jako CSV`
    - `Kopiuj jako CSV (naglowki)`
    - `Kopiuj jako TSV`
    - `Kopiuj jako TSV (naglowki)`
- Wsparcie podmenu w silniku menu kontekstowego:
  - `gui/common_tables.py::attach_results_context_menu(...)` (`children` -> submenu).
- Zmiany wdrozone spojnie dla:
  - planner base (`gui/tabs/spansh/planner_base.py`)
  - `gui/tabs/spansh/neutron.py`
  - `gui/tabs/spansh/trade.py`
- Dodano test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_spansh_export_actions_and_formats`
  - pokrywa akcje eksportu i format outputu (CSV/TSV + naglowki).
- Testy:
  - `py -m compileall gui/common_tables.py gui/common.py gui/tabs/spansh/planner_base.py gui/tabs/spansh/neutron.py gui/tabs/spansh/trade.py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_beckendy.py` PASS 19/19
- `py tools/smoke_tests_journal.py` PASS 6/6

---

### SPANSH-CHECKBOX-COPY-HEADERS-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Dodac jawne zaznaczanie wierszy checkboxami (ptaszek po lewej) w wynikach Spansh.
- Zapewnic, ze kopiowany fragment do Excela zawiera nazwy kolumn.

Zakres:
- Dodac kolumne checkbox po lewej stronie wierszy (Listbox/Treeview) dla zakladek Spansh.
- "Kopiuj zaznaczone" ma korzystac z checkboxow jako primary source wyboru.
- Dodac/ujednolicic akcje kopiowania zaznaczonych z naglowkami (TSV + naglowki pod Excel).
- Usunac calkowicie menu `Kopiuj CSV` z PPM.
- Zmienic nazwe menu `Kopiuj TSV` na `Kopiuj do Excela` (technicznie nadal TSV pod Excel).
- Dodac smoke-test regresyjny pokrywajacy:
  - checkbox selection -> kopiowanie tylko zaznaczonych,
  - obecne naglowki w kopiowanym fragmencie dla trybu Excel.

DoD:
- W kazdej zakladce Spansh widoczna jest kolumna checkbox po lewej.
- Gracz moze oznaczyc konkretne wiersze i skopiowac tylko je.
- Wklejenie do Excela daje pierwszy wiersz z naglowkami kolumn.
- W PPM nie ma pozycji `Kopiuj CSV`.
- W PPM jest pozycja `Kopiuj do Excela` (zamiast `Kopiuj TSV`).
- Brak regresji dla pozostalych trybow kopiowania.

---

Wynik:
- `gui/common_tables.py`:
  - dodano checkbox-mode dla wynikow (`Listbox` i `Treeview`) z wizualnym ptaszkiem po lewej,
  - dodano API:
    - `enable_results_checkboxes(...)`,
    - `clear_results_checkboxes(...)`,
    - `get_checked_internal_indices(...)`,
  - `Treeview` dostal lewa kolumne wyboru `__sel__` z toggle po kliknieciu.
- `gui/tabs/spansh/planner_base.py`, `gui/tabs/spansh/neutron.py`, `gui/tabs/spansh/trade.py`:
  - zaznaczenia checkbox sa primary source dla akcji `Kopiuj zaznaczone`,
  - usunieto menu `Kopiuj CSV`,
  - menu `Kopiuj TSV` zmieniono na `Kopiuj do Excela` (TSV pod Excel).
- `tools/smoke_tests_beckendy.py`:
  - zaktualizowano regresje menu/exportu pod nowy UX,
  - dodano asercje obecnosci warstwy checkbox.
- Testy:
  - `py -m compileall gui/common_tables.py gui/tabs/spansh/planner_base.py gui/tabs/spansh/neutron.py gui/tabs/spansh/trade.py tools/smoke_tests_beckendy.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS 26/26
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### TRADE-STATION-PICKER-UX-01 (P1)
Status: DONE (dialog + scrollbar + filter + UX contract)

Cel:
- Poprawic UX wyboru stacji w zakladce Handel.

Zakres:
- Dodac przewijanie (scrollbar) do listy stacji.
- Dodac wieksze okno/dialog wyboru stacji (z lista i filtrem), zamiast ciasnej listy inline.
- Zachowac obecny autocomplete jako szybka sciezke.

DoD:
- Uzytkownik moze wygodnie przewijac dlugie listy stacji.
- Dialog wyboru stacji dziala klawiatura i myszka.
- Brak regresji autocomplete.

Wdrozenie (2026-02-28):
- `gui/tabs/spansh/trade.py`:
  - picker stacji dziala jako osobne duze okno (`760x520`, `minsize 560x380`),
  - lista ma pionowy scrollbar + klawiature/mysz (`DoubleClick`, `Enter`, `Escape`),
  - dodany filtr live (`query_var.trace_add("write", _refresh_list)`),
  - autocomplete stacji pozostaje aktywny jako szybka sciezka.

Testy:
- `py -3 -m unittest tests.test_trade_station_picker_ux_contract tests.test_trade_station_picker_system_normalization -v` PASS

---

### TRADE-STATION-STATE-RESET-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Czyscic pole stacji po zmianie systemu startowego (aby nie zostawala stara stacja).

Zakres:
- Na zmiane `start_system`: reset `start_station`, ukrycie sugestii, odswiezenie hintow.
- Wyjatek: brak resetu, gdy system nie zmienil sie realnie (ten sam normalized key).

DoD:
- Zmiana systemu usuwa poprzednia stacje automatycznie.
- Uzytkownik nie musi recznie kasowac starej wartosci.

Wynik:
- `gui/tabs/spansh/trade.py`:
  - dodano trace handler `_on_start_system_changed(...)` dla `var_start_system`,
  - reset `start_station` nastepuje tylko przy realnej zmianie systemu
    (porownanie normalized key, bez false-positive),
  - po zmianie systemu ukrywane sa sugestie stacji i odswiezany hint.
- Test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_trade_station_state_reset_on_system_change`
  - pokrywa przypadki:
    1) brak resetu gdy system logicznie ten sam,
    2) reset przy realnej zmianie systemu,
    3) brak resetu na pierwszym trace po starcie.

---

### TRADE-ROUTE-STATION-NAMES-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Naprawic brak nazw stacji w wynikach trasy handlowej.

Zakres:
- Zweryfikowac mapowanie pol `station/from_station/to_station` w normalizacji wierszy.
- Ujednolicic render tabeli/listy i payload row-actions pod schema `trade`.
- Dodac fallback "UNKNOWN_STATION" tylko gdy rzeczywiscie brak danych.

DoD:
- Przy trasie 10+ pozycji nazwy stacji sa widoczne w UI.
- Kopiowanie wiersza/CSV zawiera nazwy stacji.
- Smoke scenariusz trade route: PASS.

Wynik:
- `logic/rows_normalizer.py`:
  - przebudowana normalizacja trade route dla wielu wariantow odpowiedzi API (flat + nested endpointy),
  - mapowanie `from_station` / `to_station` + fallback `UNKNOWN_STATION` tylko gdy brak danych,
  - row payload zawiera jawne pola stacji dla renderu i kopiowania.
- `gui/table_schemas.py` + `gui/strings.py`:
  - schema `trade` ma kolumny `Stacja Z` i `Stacja Do` (widoczne w UI i eksporcie).
- `gui/tabs/spansh/trade.py`:
  - payload PPM "Kopiuj stacje" sklada wartosc z obu stron trasy (`from -> to`) gdy dostepne,
  - fallback render (gdy schema off) pokazuje systemy razem ze stacjami.
- Test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_trade_station_name_normalization`
  - pokrywa mapowanie flat/nested + fallback `UNKNOWN_STATION`.

---

### TTS-POLISH-DIACRITICS-GLOBAL-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Przywrocic polskie znaki we wszystkich komunikatach TTS (nie tylko exobio).

Zakres:
- Zweryfikowac pelna sciezke od message_id do final TTS (preprocessor + engine input) dla glownych domen: nav/spansh/exploration/exobio/trade.
- Usunac normalizacje, ktora degraduje diakrytyke.
- Dodac test regresyjny na kluczowe komunikaty z wielu domen (nie tylko exobio).

DoD:
- TTS czyta polskie znaki poprawnie we wszystkich komunikatach user-facing.
- Brak regresji anti-spam i priorytetow dispatcher-a.

Wynik:
- `logic/tts/text_preprocessor.py`:
  - dodano centralny repair warstwy TTS (`_repair_polish_text`) dla typowych artefaktow mojibake,
  - poprawiono mikrocopy z polskimi znakami (`osiągnięty`, `przechodzę`, `startuję`),
  - sciezka `raw_text` przechodzi przez naprawe diakrytyki przed podaniem do TTS.
- `logic/events/exploration_high_value_events.py`:
  - fallbacki DSS i body-specific hinty maja poprawna polska diakrytyke.
- `logic/events/exploration_bio_events.py`:
  - komunikaty exobio (probki / gate dystansu) maja poprawna polska diakrytyke.
- Test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_tts_polish_diacritics_global`
  - pokrywa diakrytyke dla nav/explore/startup oraz naprawe `raw_text` z mojibake.

---

### EXOBIO-SAMPLE-PROGRESS-COPY-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Poprawic tresc, kolejnosc i warunki stopu komunikatow po kolejnych probkach exobio.

Zakres:
- Sekwencja po 1 probce:
  - komunikat progresu "pierwsza probka {gatunek} pobrana",
  - potem gate: "osiagnieto odpowiednia odleglosc, pobierz kolejna probke" (gdy warunek gate jest spelniony).
- Sekwencja po 2 probce:
  - komunikat progresu "druga probka pobrana",
  - potem gate jak wyzej, dopiero po realnym osiagnieciu progu.
- Sekwencja po 3 probce:
  - komunikat zakonczenia gatunku ("mamy wszystko"),
  - komunikat wartosci: wartosc pobranych probek liczona z `renata_science_data.xlsx` + bonusy (np. first footfall), jesli dane sa dostepne.
- Po komunikacie 3/3 nie emitowac dalszych komunikatow dla tego gatunku, dopoki gracz nie zacznie nowej rosliny/gatunku.
- Finalny wording zgodny z dokumentacja private (`ACTION_EXOBIOLOGY_HELPER.md`, polityki glosu).

DoD:
- Komunikaty probek sa semantycznie poprawne i w poprawnej kolejnosci (1/3 -> gate -> 2/3 -> gate -> 3/3 + wartosc).
- "Odleglosc osiagnieta" pojawia sie tylko po realnym osiagnieciu progu i nigdy nie zastepuje komunikatu progresu probki.
- Po 3/3 brak dalszych calloutow dla tego gatunku, az do nowej rosliny/gatunku.
- Brak dublowania i brak sprzecznych komunikatow w jednym kroku.

Wynik:
- `logic/events/exploration_bio_events.py`:
  - wdrozono sekwencje progresu probek:
    - `Pierwsza probka {gatunek} pobrana.`
    - `Druga probka {gatunek} pobrana.`
    - `Mamy wszystko dla {gatunek}. Szacowana wartosc pobranych probek: ...`
  - gate dystansu ma osobny komunikat po realnym osiagnieciu progu:
    - `Osiagnieto odpowiednia odleglosc. Pobierz kolejna probke.`
  - po 3/3 lock dla gatunku (`EXOBIO_SAMPLE_COMPLETE`) blokuje dalsze callouty
    do czasu nowej rosliny/gatunku.
  - usunieto fallback "udawanego gate" bez realnego progu z danych science.
  - dodano wycene 3/3 z `renata_science_data.xlsx` + opcjonalny bonus first footfall
    (gdy dane sa dostepne w evencie i arkuszu).
- Test regresyjny:
  - `tools/smoke_tests_beckendy.py::test_exobio_sample_progress_sequence`
  - pokrywa: `1/3 -> gate -> 2/3 -> gate -> 3/3 + wartosc` oraz brak dalszych komunikatow po domknieciu.

---

### SPANSH-FEEDBACK-SMOKE-PACK-01 (P0)
Status: DONE (test pack + smoke)

Cel:
- Dodac stale testy regresyjne dla nowych scenariuszy feedbackowych.

Zakres:
- Smoke/testy techniczne dla:
  - copy mode matrix (Neutron + pozostale zakladki),
  - trade route station names,
  - CSV/TSV export do Excela (naglowki + dane),
  - exobio sample progress/gate copy,
  - diakrytyka TTS dla kluczowych komunikatow z wielu domen.

DoD:
- Zestaw smoke przechodzi lokalnie.
- Krytyczne bugi z feedbacku maja stale pokrycie regresyjne.

Wynik:
- `tools/smoke_tests_beckendy.py`:
  - dodano test zbiorczy `test_spansh_feedback_smoke_pack_coverage`,
  - test sprawdza parity menu copy/export dla planner-base i dedykowanych zakladek
    (`neutron`, `trade`) oraz obecne pokrycie krytycznych testow regresyjnych.
- Pokryte scenariusze feedbackowe:
  - copy mode matrix (Neutron + pozostale zakladki przez `planner_base`),
  - trade route station names,
  - CSV/TSV export (naglowki + dane),
  - exobio sample progress/gate copy,
  - diakrytyka TTS.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 25/25
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

## Kolejnosc realizacji (feedback Cmdr Czuczik O7)

1. SPANSH-NEUTRON-PARITY-ALL-TABS-01 (P0)
2. SPANSH-COPY-SYSTEM-COVERAGE-01 (P0)
3. SPANSH-COPY-MODE-SELECTION-PARITY-01 (P0)
4. SPANSH-EXPORT-CSV-EXCEL-01 (P0)
5. TRADE-ROUTE-STATION-NAMES-01 (P0)
6. TTS-POLISH-DIACRITICS-GLOBAL-01 (P0)
7. EXOBIO-SAMPLE-PROGRESS-COPY-01 (P0)
8. TRADE-STATION-STATE-RESET-01 (P1)
9. TRADE-STATION-PICKER-UX-01 (P1)
10. SPANSH-FEEDBACK-SMOKE-PACK-01 (P0)
11. SPANSH-CHECKBOX-COPY-HEADERS-01 (P0)

---



## NOWE TICKETY 0.9.4 (feedback gameplay po v0.9.3) 
## Zmiany do dokumentacji w update v0.9.4!

### TRADE-COMMODITY-VISIBLE-01 (P0)
Plan rozszerzenia UX (po fixie P0):
- Potwierdzenie zachowania: powtarzajace sie legi sa akceptowalne, bo Spansh moze celowo zwracac petle.
- Etap 1: sticky `Summary bar` pod tabela Trade (bez merge komorek i bez przebudowy tabeli):
- Pokazuj `Cumulative Profit` tylko gdy istnieje w payloadzie (ostatnia wartosc na trasie).
- Gdy `cumulative_profit` nie istnieje: pokazuj `Total Profit = sum(total_profit)` i nie myl etykiet.
- Pokazuj `Total distance [ly] = suma distance_ly` po legach.
- Pokazuj `Skoki (szac.) = suma ceil(distance_ly / jump_range_effective)`.
- Dla legu bez `distance_ly` albo bez poprawnego jump range: wartosc `-` i pomijanie w sumie.
- Pokazuj `Updated` jako zakres: `newest ... oldest` (preferuj `updated_ago`, fallback `updated_at`).
- Etap 2: panel szczegolow dla zaznaczonego lega (rozpakowanie multi-commodity):
- Sekcja kontekstowa: `From/To`, `Updated`, `Cumulative Profit` (dla lega, jesli istnieje).
- Lista towarow: `commodity`, `amount`, `buy_price`, `sell_price`, `profit`, `total_profit`.
- Dla single-commodity panel nadal pokazuje 1 wiersz (spojny UX).
- Panel renderuje dane z kanonicznego modelu i nie wykonuje dodatkowej logiki biznesowej.
- Wymagane dane na wierszu: `commodities_raw`, `updated_ago`/`updated_at`, `cumulative_profit`.
- Etap 3 (opcjonalny): eksport Trade rozszerzony o sekcje `Summary` po pustej linii:
- `Cumulative Profit` albo `Total Profit`, `Total distance [ly]`, `Skoki (szac.)`, `Updated range`.

Status: DONE (kod + smoke)

Cel:
- Naprawic render towarow i metryk handlowych w zakladce Trade (towar/zysk/zysk-t nie moga byc puste, gdy Spansh zwraca dane).

Zakres:
- Zweryfikowac warianty odpowiedzi trade route ze Spansh (single commodity + multi commodity per leg).
- Rozszerzyc normalizacje wierszy tak, aby poprawnie mapowac:
  - `commodity` / `commodities`,
  - `amount`,
  - `buy_price`,
  - `sell_price`,
  - `profit`,
  - `total_profit`,
  - `updated_at` / `updated_ago`,
  - `cumulative_profit`.
- Obsluzyc aliasy nazw pol (`snake_case` / `camelCase`), m.in.:
  - `buy_price` / `buyPrice`,
  - `sell_price` / `sellPrice`,
  - `total_profit` / `totalProfit`,
  - `cumulative_profit` / `cumulativeProfit`,
  - `updated_at` / `updatedAt`.
- Zapewnic fallback:
  - "-" tylko gdy pole realnie nie istnieje w payloadzie.
- Dla wielu towarow w jednym legu:
  - pokazac czytelny agregat (np. "CommodityA +N"),
  - mapowac `total_profit` per-leg (sumowane z listy towarow, jesli brak top-level),
  - mapowac `profit` jako per-unit (wyliczone z `total_profit/amount`, gdy brak top-level),
  - mapowac `buy_price` / `sell_price` (preferuj top-level, fallback: srednia wazona po amount).
- Ustalic kanoniczne pola pod UI/eksport (brak rozjazdow):
  - `commodity_display`,
  - `amount`,
  - `buy_price`,
  - `sell_price`,
  - `profit`,
  - `total_profit`,
  - `cumulative_profit`,
  - `updated_ago`.
- Dla `cumulative_profit` ustalic priorytet zrodel:
  - 1) wartosc z payloadu lega/karty (jesli obecna),
  - 2) fallback opcjonalny: narastajaco z `total_profit` po trasie (gdy payload nie zwraca cumulative).
- Zsynchronizowac schema kolumn Trade z nowymi kluczami:
  - `Towar` -> `commodity_display`,
  - `Zysk [cr]` -> `total_profit`,
  - `Zysk/t [cr]` -> `profit`,
  - dodac/uzupelnic `Cumulative Profit` i `Updated`, jesli sa w payloadzie.

Pliki startowe:
- `logic/rows_normalizer.py`
- `gui/tabs/spansh/trade.py`
- `gui/table_schemas.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- Dla tras, gdzie Spansh zwraca towary, kolumny Trade nie sa puste.
- Dla tras z 2+ towarami na legu UI pokazuje poprawny agregat towaru i poprawne metryki zysku.
- `Cumulative Profit` jest poprawnie mapowany i widoczny (bez pustych pol, gdy API zwraca dane).
- Informacja o "updated" jest mapowana i widoczna (bez gubienia pola).
- Aliasy kluczy (`snake_case`/`camelCase`) sa obslugiwane i pokryte regresja.
- UI i eksport pokazuja te same wartosci (bez rozjazdu).
- Smoke ma regresje dla wariantu single + multi commodity + cumulative/updated.

Wynik:
- `logic/rows_normalizer.py`:
  - przebudowano normalizacje trade pod single + multi commodity,
  - dodano aliasy kluczy (`snake_case`/`camelCase`) dla cen/zyskow/cumulative/updated,
  - dodano agregacje dla multi-leg (`commodity_display`, `total_profit`, `profit`, wagi cen),
  - dodano mapowanie `updated_ago` i `cumulative_profit` (z payloadu + fallback narastajacy).
- `gui/table_schemas.py` + `gui/strings.py`:
  - schema Trade zostala zsynchronizowana z kanonicznymi danymi normalizera
    (mapowanie kolumn: `Towar` -> `commodity_display`,
    `Zysk [cr]` -> `total_profit`, `Zysk/t [cr]` -> `profit`),
  - dodano kolumny opcjonalne: `Cumulative Profit [cr]`, `Updated`.
- `tools/smoke_tests_beckendy.py`:
  - dodano regresje: `test_trade_multi_commodity_aliases_and_metrics`,
  - pokrycie: single + multi commodity, aliasy, `updated`, `cumulative_profit`,
    agregacja zyskow i srednie wazone.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 27/27
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### SPANSH-LAYOUT-PARITY-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Ujednolicic layout zakladek Spansh do wzorca Neutron (spojnosc wizualna i ergonomia bez zmiany logiki biznesowej).

Zasady (ustalone):
- Neutron jest wzorcem wygladu dla pozostalych zakladek Spansh.
- Kolejnosc sekcji ma byc spojna: `formularz -> akcje -> status -> tabela`.
- Wiersz akcji/statusu zostaje wspolny:
  - przyciski akcji pozostaja w tym samym wierszu,
  - przyciski sa wycentrowane poziomo,
  - status jest wycentrowany poziomo (w tym samym wierszu co akcje).
- Tabela i sekcja statusu startuja na porownywalnej wysokosci (bez duzych pustych "dziur" miedzy formularzem a wynikami).
- Spacing, marginesy, wysokosci kontrolek i rytm pionowy sa spojne miedzy zakladkami.
- Brak kopiowania widoku 1:1 ze Spansh web; zachowujemy obecny styl Renaty.

Zakres:
- Przejrzec i ujednolicic kontenery layoutu dla zakladek Spansh:
  - `Trade`,
  - planner-based tabs (`Riches/Ammonia/Earth-like/Rocky-HMC/Exo`) z zachowaniem ich specyfiki pol.
- Wspolne reguly geometrii wyniesc do warstwy wspolnej (tam gdzie to mozliwe), aby ograniczyc rozjazdy przy kolejnych zmianach.
- W Trade:
  - poprawic wiersz akcji/statusu tak, aby przyciski i status byly wycentrowane (ten sam wiersz).
- We wszystkich zakladkach Spansha:
  - zastosowac te sama zasade pozycjonowania wiersza akcji/statusu (bez wyjatkow per-tab).
- Nie zmieniac semantyki akcji i payloadow API (tylko layout/UX).

Pliki startowe:
- `gui/tabs/spansh/neutron.py`
- `gui/tabs/spansh/trade.py`
- `gui/tabs/spansh/planner_base.py`
- `gui/tabs/spansh/riches.py`
- `gui/tabs/spansh/ammonia.py`
- `gui/tabs/spansh/elw.py`
- `gui/tabs/spansh/hmc.py`
- `gui/tabs/spansh/exomastery.py`

DoD:
- Zakladki Spansh maja jednolity rytm layoutu zgodny z Neutron.
- W kazdej zakladce Spansha przyciski akcji i status sa wycentrowane w tym samym wierszu.
- Brak nadmiarowych pustych przestrzeni pomiedzy sekcjami.
- Brak regresji funkcjonalnych (wyznaczanie tras, kopiowanie, akcje PPM, render tabel).
- Smoke backend/journal przechodza.

Wynik:
- Dodano wspolny helper layoutu `akcje + status` w `gui/tabs/spansh/planner_base.py`
  i podlaczono go do zakladek plannerowych:
  - `gui/tabs/spansh/riches.py`
  - `gui/tabs/spansh/ammonia.py`
  - `gui/tabs/spansh/elw.py`
  - `gui/tabs/spansh/hmc.py`
  - `gui/tabs/spansh/exomastery.py`
- W `gui/tabs/spansh/neutron.py` i `gui/tabs/spansh/trade.py` przebudowano
  wiersz akcji/statusu na wspolny, wycentrowany uklad.
- Dla spojnosci osadzenia sekcji, listy/tabele w plannerach i Trade sa renderowane
  w glownym kontenerze zakladki (`fr`) razem z formularzem i akcjami.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 30/30
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### TRADE-UPDATED-BUY-SELL-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Uczytelnic swiezosc danych rynkowych w Trade oraz domknac kolumne `Skoki [szt]`,
  gdy API nie zwraca jawnego `jumps`.

Zakres:
- W normalizacji Trade mapowac oddzielnie swiezosc dla:
  - strony kupna (`source` / `from`),
  - strony sprzedazy (`destination` / `to`).
- Obsluzyc timestampy marketowe ze Spansh:
  - `market_updated_at` / `marketUpdatedAt` (+ fallbacki `updated_*`).
- Renderowac kolumne `Updated` w formacie kompaktowym:
  - `kupno / sprzedaz` (np. `10m / 2h`),
  - fallback do pojedynczej wartosci, gdy jedna strona jest niedostepna.
- W panelu `Szczegoly kroku` pokazywac ten sam model:
  - `Updated (kupno/sprzedaz): ...`.
- Dla `Skoki [szt]`:
  - jesli `jumps` przychodzi z API, uzywac tej wartosci,
  - jesli brak `jumps`, wyliczac fallback per leg:
    `ceil(distance_ly / jump_range_effective)` z aktualnego zasiegu statku/UI.
- Utrzymac spojność UI + export (jedno zrodlo danych wiersza).

Pliki startowe:
- `logic/rows_normalizer.py`
- `gui/tabs/spansh/trade.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- `Updated` w Trade nie jest puste, gdy payload ma dane freshness.
- Dla tras ze Spansh z polami `market_updated_at` kolumna pokazuje `kupno/sprzedaz`.
- `Skoki [szt]` nie zostaja puste przy braku `jumps` w payloadzie, jesli jest `distance_ly` i zasieg.
- Podsumowanie Trade nadal liczy zakres `Updated` i skoki bez regresji.
- Smoke backend/journal przechodzi.

Wynik:
- `logic/rows_normalizer.py`:
  - dodano mapowanie freshness per strona transakcji (`updated_buy_ago`, `updated_sell_ago`),
  - dodano obsluge `market_updated_at` / `marketUpdatedAt` + fallbacki `updated_*`,
  - dodano kompaktowanie age do formatu `m/h/d/w/y`,
  - `updated_ago` wiersza renderuje teraz pare `kupno / sprzedaz` (gdy obie strony sa dostepne).
- `gui/tabs/spansh/trade.py`:
  - `Updated` range w summary uwzglednia buy/sell age (oraz zapis z para `x / y`),
  - panel szczegolow pokazuje `Updated (kupno/sprzedaz): ...`,
  - dodano fallback wyliczania `jumps` per leg i podpiecie do wynikow przed renderem.
- `tools/smoke_tests_beckendy.py`:
  - rozszerzono regresje trade (`updated` + freshness pair + aliasy),
  - dodano test `test_trade_updated_buy_sell_pair_from_market_timestamps`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS
  - `py tools/smoke_tests_journal.py` PASS

---

### NEUTRON-EMPTY-STATE-SKELETON-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Uczytelnic stan pustej tabeli w Neutron:
  - kolumny maja byc widoczne zawsze (skeleton table),
  - komunikat empty-state ma byc overlayem tylko na body tabeli (bez zaslaniania naglowkow).

Zakres:
- Dla zakladki `Neutron` wymusic render kolumn tabeli rowniez przy `rows=[]`.
- Przebudowac empty-state tak, aby:
  - naglowki i struktura kolumn pozostaly widoczne,
  - overlay "Brak wynikow..." byl przypiety do obszaru danych (pod naglowkiem),
  - overlay chowal sie automatycznie po pojawieniu sie pierwszego wiersza.
- Zachowac obecna funkcjonalnosc:
  - sortowanie,
  - picker kolumn,
  - menu PPM,
  - checkboksy i kopiowanie.
- Nie zmieniac payloadow ani logiki wyznaczania trasy (tylko UX renderu pustego stanu).

Pliki startowe:
- `gui/tabs/spansh/neutron.py`
- `gui/common_tables.py`
- `gui/empty_state.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- W Neutron, bez wynikow, widoczne sa naglowki kolumn.
- Komunikat empty-state nie zaslania naglowkow (tylko obszar body).
- Po pojawieniu sie wynikow overlay znika, a tabela dziala jak dotad.
- Brak regresji w menu PPM / kopiowaniu / checkboxach.
- Smoke backend/journal przechodzi.

Wykonane:
- W `gui/tabs/spansh/neutron.py` dodano render skeleton table przy starcie:
  - `common.render_table_treeview(self.lst, "neutron", [])`.
- Wszystkie wywolania empty-state w Neutron przelaczono na tryb overlay:
  - `display_mode="overlay_body"`.
- W `gui/empty_state.py` dodano tryb `overlay_body`:
  - wykrywanie wysokosci naglowka Treeview,
  - overlay przycinany do obszaru body (ponizej naglowka),
  - automatyczne repozycjonowanie overlay po resize.
- Dodano regresje techniczna:
  - `test_neutron_empty_state_skeleton_overlay` w `tools/smoke_tests_beckendy.py`.
- Smoke po zmianie:
  - `py tools/smoke_tests_beckendy.py` PASS 31/31
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### FUEL-LOW-SCO-FALSE-POSITIVE-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Usunac jednorazowe falszywe ostrzezenie niskiego paliwa podczas sekwencji: start z planety -> supercruise -> SCO.

Zakres:
- Utwardzic confirmation guard dla low-fuel przy startup/transient probkach `Status.json`.
- Rozroznic "chwilowy glitch probki" od realnego low-fuel:
  - wymagane potwierdzenie przez kolejne probki i/lub krotki czas stabilizacji.
- Nie pogorszyc detekcji prawdziwego niskiego paliwa.

Pliki startowe:
- `logic/events/fuel_events.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- Brak falszywego "Paliwo krytyczne" w scenariuszu transient startup/SCO.
- Realny low-fuel nadal wywoluje alert.
- Regresja pokryta testem.

Wykonane:
- Rozszerzono guard potwierdzenia low-fuel o niepewne probki liczbowe bez wiarygodnej pojemnosci paliwa.
- Alert low-fuel wymaga potwierdzenia, gdy probka jest flag-only albo niepewna (startup/SCO transient).
- Dodano regresje: `test_low_fuel_transient_startup_sco_guard`.
- Smoke po zmianie: `py tools/smoke_tests_beckendy.py` PASS 30/30, `py tools/smoke_tests_journal.py` PASS 6/6.
- Commit: `10e2b57`.

---

### FSS-PROGRESS-PL-VOICE-01 (P2)
Status: DONE (kod + smoke)

Cel:
- Ujednolicic brzmienie progow FSS (25/50/75), bez obcego akcentu dla 25%.

Zakres:
- Zmienic copy dla FSS progress na formy slownie (PL), aby uniknac niejednoznacznej wymowy procentow:
  - "Dwadzieścia pięć procent systemu przeskanowane.",
  - "Połowa systemu przeskanowana.",
  - "Siedemdziesiąt pięć procent systemu przeskanowane."
- Zachowac obecny message_id i polityke anti-spam.

Pliki startowe:
- `logic/tts/text_preprocessor.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- Wszystkie progi FSS sa czytane stabilnie po polsku.
- Brak regresji kolejnosci i deduplikacji komunikatow.

---

### FSS-LAST-BODY-FULL-ORDER-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Naprawic kolejnosc i warunki komunikatow FSS:
  - "Ostatnia planeta do skanowania" tylko gdy zostaje 1 cialo (np. 9/10, 11/12),
  - "System w pelni przeskanowany" po faktycznym 100% (N/N).

Zakres:
- Usunac/ograniczyc fallback, ktory emituje "ostatnia planeta" dopiero przy 100%.
- Ustalic twarda logike:
  - `remaining == 1` -> last-body (once),
  - `discovered >= total` -> full-scan (once),
  - last-body nie moze zastapic full-scan i nie moze byc emitowany po nim.
- Dodac testy kolejnosci dla przypadkow:
  - 9/10 -> 10/10,
  - 11/12 -> 12/12,
  - bez eventu `FSSAllBodiesFound` (fallback po `Scan`).

Pliki startowe:
- `logic/events/exploration_fss_events.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- Komunikat "ostatnia planeta" pada tylko na N-1/N.
- Komunikat "100%" pada na N/N.
- Brak sytuacji, gdzie po zakonczeniu skanowania slyszyc tylko "ostatnia planeta".

---

### WINDOW-RESIZE-HITBOX-02 (P2)
Status: DONE (kod + smoke)

Cel:
- Poprawic ergonomie zmiany rozmiaru glownego okna (latwiejsze "zlapie" krawedzi niz domyslna cienka ramka systemowa).

Zakres:
- Wdrozyc opcje 2: wewnetrzna strefe resize (custom hitbox) o szerokosci 6-8 px:
  - prawa krawedz (E),
  - dolna krawedz (S),
  - prawy dolny rog (SE).
- Zostawic natywna ramke systemowa okna (bez `overrideredirect` i bez customowego titlebara).
- Dodac poprawny kursor dla stref:
  - `sb_h_double_arrow` / `sb_v_double_arrow` / `size_nw_se`.
- Podczas drag resize:
  - dynamicznie aktualizowac geometrie `WxH`,
  - respektowac minimalny rozmiar okna (i obecne ograniczenia runtime).
- Wylaczyc custom resize, gdy okno jest zmaksymalizowane/fullscreen.
- Upewnic sie, ze strefa nie blokuje interakcji z kontrolkami UI i nie koliduje z overlayami/debug panelem.

Pliki startowe:
- `gui/app.py`
- `gui/window_positions.py`
- `gui/empty_state.py` (check kolizji overlay po resize)
- `tools/smoke_tests_beckendy.py`

DoD:
- Uzytkownik moze wygodnie zmieniac rozmiar okna, "lapac" krawedz bez precyzyjnego trafiania w 1 px.
- Resize dziala plynnie na prawej, dolnej i rogu prawego-dolnego.
- Brak regresji dla:
  - zapisu/odtwarzania geometrii okna,
  - klikalnosci kontrolek przy krawedzi,
- overlayow i widgetow przypietych do dolu/prawej.
- Smoke backend/journal przechodzi.

Wynik:
- `gui/app.py`:
  - dodano customowy hitbox resize `8 px` dla krawedzi: prawa (E), dolna (S), prawy-dolny rog (SE),
  - dodano kursory: `sb_h_double_arrow`, `sb_v_double_arrow`, `size_nw_se`,
  - dodano drag-resize z respektowaniem `minsize` oraz guardami dla `zoomed/fullscreen`,
  - zachowano natywna ramke okna (bez `overrideredirect`).
- `tools/smoke_tests_beckendy.py`:
  - dodano regresje techniczna: `test_window_resize_hitbox_wiring`,
  - test dolaczony do smoke packa.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 33/33
- `py tools/smoke_tests_journal.py` PASS 6/6

---

### TRADE-LAYOUT-SPLIT-VIEW-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Ograniczyc przeladowanie informacyjne w zakladce Trade, zachowujac pelny kontekst danych.

Zakres:
- Wdrozyc uklad split-view dla Trade:
  - gorna sekcja: tabela trasy (`Trasa: Handel`),
  - dolna sekcja: `Szczegoly kroku`,
  - pomiedzy sekcjami: pionowy splitter (uzytkownik reguluje proporcje).
- Domyslnie zwinac sekcje `Szczegoly kroku` (compact start).
- Rozwijac `Szczegoly kroku` dopiero po zaznaczeniu wiersza trasy
  (lub po kliknieciu przycisku "Pokaz szczegoly").
- Scrollowanie lokalne, nie globalne:
  - pionowy i poziomy scrollbar tylko dla tabel,
  - brak "scrolla calej zakladki" jako domyslnego modelu.
- Zachowac summary bar pod glowna tabela:
  - Cumulative/Total Profit,
  - Dystans [ly],
  - Skoki (szac.),
  - Updated range.
- Tryb kompaktowy kolumn:
  - domyslnie ukryc najmniej krytyczne kolumny (`Updated`, `Cumulative Profit`),
  - pozostawic mozliwosc wlaczenia przez `Kolumny`.
- Nie zmieniac logiki payloadow i obliczen Trade (tylko layout/ergonomia).

Etapy wdrozenia:
- Etap 1: `PanedWindow` + splitter + poprawne minimalne wysokosci sekcji.
- Etap 2: mechanika zwijania/rozwijania `Szczegoly kroku`.
- Etap 3: poziome scrollbary i domyslny compact preset kolumn.

Pliki startowe:
- `gui/tabs/spansh/trade.py`
- `gui/common_tables.py`
- `gui/table_schemas.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- Trade po starcie nie przytlacza iloscia informacji (czytelny compact view).
- Uzytkownik moze recznie regulowac proporcje `Trasa` vs `Szczegoly kroku`.
- Sekcja szczegolow nie zabiera miejsca, dopoki nie jest potrzebna.
- Tabele maja lokalne scrollowanie (w tym poziome dla szerokich kolumn).
- Brak regresji dla:
  - zaznaczania i kopiowania wierszy,
  - PPM / eksportu,
- renderu empty-state i summary bar.
- Smoke backend/journal przechodzi.

Wynik:
- `gui/tabs/spansh/trade.py`:
  - wdrozono pionowy split-view (`ttk.PanedWindow`) dla sekcji:
    - `Trasa: Handel` (gora),
    - `Szczegoly kroku` (dol),
  - dodano toggle panelu szczegolow (`Pokaz/Ukryj szczegoly kroku`),
  - panel szczegolow startuje zwinięty (compact start) i rozwija sie po wyborze wiersza trasy,
  - podlaczono lokalne scrollowanie poziome:
    - glowna tabela trasy (Treeview),
    - tabela towarow w panelu szczegolow,
  - zachowano summary bar oraz dotychczasowa logike payloadow i obliczen.
- `tools/smoke_tests_beckendy.py`:
  - dodano regresje techniczna `test_trade_split_view_layout_wiring`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 36/36
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### TRADE-JUMPS-MARKET-AGE-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Domknac czytelnosc i wiarygodnosc danych Trade dla:
  - `Skoki [szt]` (z fallbackiem wyliczanym per leg),
  - `Wiek rynku K/S` (oddzielnie kupno/sprzedaz).

Zakres:
- Dla kolumny `Skoki [szt]`:
  - jesli API zwraca `jumps`, uzywamy tej wartosci bez zmian,
  - jesli `jumps` brak, wyliczamy fallback:
    - `ceil(distance_ly / jump_range_effective)` per leg,
    - `jump_range_effective` z aktualnego zasiegu statku/UI.
- Dla kolumny `Wiek rynku K/S`:
  - mapowanie freshness z endpointow source/target:
    - `market_updated_at` / `marketUpdatedAt`,
    - fallback do `updated_*` jesli potrzeba,
  - format kompaktowy `kupno / sprzedaz` (np. `49m / 13h`).
- Ujednolicenie opisu w panelu szczegolow:
  - `Wiek rynku (kupno/sprzedaz): ...`.
- Ujednolicenie etykiety kolumny:
  - `Updated` -> `Wiek rynku K/S`.
- Dla panelu `Szczegoly kroku`:
  - dopiac mapowanie cen `Kupno`/`Sprzedaz` tak, aby nie byly puste, gdy Spansh zwraca
    ceny w polach zagniezdzonych:
    - `source_commodity.buy_price`,
    - `destination_commodity.sell_price`.

Pliki startowe:
- `logic/rows_normalizer.py`
- `gui/tabs/spansh/trade.py`
- `gui/strings.py`
- `tools/smoke_tests_beckendy.py`

DoD:
- `Skoki [szt]` nie sa puste przy braku `jumps`, gdy `distance_ly` i zasieg sa dostepne.
- `Wiek rynku K/S` pokazuje pare kupno/sprzedaz tam, gdzie payload ma dane market update.
- Panel szczegolow pokazuje ten sam model K/S co tabela.
- `Kupno`/`Sprzedaz` w panelu szczegolow sa wypelnione, gdy ceny istnieja
  w zagniezdzonych strukturach commodity.
- Brak regresji summary i normalizacji Trade.
- Smoke backend/journal przechodzi.

Wynik:
- `logic/rows_normalizer.py`:
  - dodano mapowanie `updated_buy_ago` / `updated_sell_ago`,
  - dodano obsluge `market_updated_at` / `marketUpdatedAt` + fallbacki,
  - `updated_ago` renderuje pare `K/S` gdy dane sa dostepne.
  - dopieto mapowanie cen commodity z pol zagniezdzonych:
    - `source_commodity.buy_price`,
    - `destination_commodity.sell_price`.
- `gui/tabs/spansh/trade.py`:
  - summary `Wiek rynku` liczy zakres z par K/S,
  - panel szczegolow pokazuje `Wiek rynku (kupno/sprzedaz)`,
  - dodano fallback wyliczania `jumps` przed renderem tabeli.
- `gui/strings.py`:
  - etykieta kolumny zmieniona na `Wiek rynku K/S`.
- `tools/smoke_tests_beckendy.py`:
  - dodano regresje `test_trade_updated_buy_sell_pair_from_market_timestamps`.
  - dodano regresje `test_trade_nested_source_destination_prices_for_details`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 38/38
  - `py tools/smoke_tests_journal.py` PASS 6/6
- Commit:
  - `598cbfa`

---

### TRADE-FORM-COMPACT-LOWRES-01 (P1)
Status: DONE (kod)

Cel:
- Poprawic czytelnosc zakladki `Spansh/Trade` na nizszych rozdzielczosciach przez odchudzenie gornej sekcji formularza.

Zakres:
- Zmniejszyc wysokosc i szerokosc bloku formularza bez zmiany logiki Trade.
- Przeniesc checkboxy flag Trade do prawej, kompaktowej kolumny.
- Skrócic i osadzic suwak `Wiek rynku` inline przy polach formularza (zamiast pelnej szerokosci w osobnym wierszu).
- Przeniesc hint stacji pod pole stacji (z zawijaniem), aby nie rozpychal poziomo ukladu.

Pliki:
- `gui/tabs/spansh/trade.py`

Wynik:
- W `Trade` wdrozono nowy top-layout:
  - `top_form_wrap` z formularzem po lewej i `Filtry` po prawej,
  - checkboxy (`Large pad`, `Planetary`, `Player owned`, `Restricted`, `Prohibited`, `Avoid loops`, `Allow permits`) renderowane w kompaktowej siatce 2-kolumnowej po prawej.
- Dla pola stacji:
  - przycisk `Wybierz stacje...` osadzony inline w siatce formularza,
  - hint stacji renderowany pod polem (`wraplength`) zamiast w tym samym poziomym wierszu.
- `Wiek rynku`:
  - suwak przeniesiony do `f_form` jako sekcja inline,
  - suwak skrócony (stala dlugosc), bez zajmowania calej szerokosci kontenera.
- Dodatkowo zmniejszono szerokosc podstawowych pol `System`/`Stacja` dla lepszego wykorzystania miejsca w low-res.

Weryfikacja:
- `py -3 -m py_compile gui/tabs/spansh/trade.py logic/utils/renata_log.py` PASS
- `py -3 -m unittest tests.test_trade_station_picker_system_normalization tests.test_log_event_throttled_compat -v` PASS

Commit:
- `e7af95c`

---

### UI-GLOBAL-SCROLLBAR-WINDOW-COLOR-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Ujednolicic globalny styl scrollbarow w calej aplikacji i sprawdzic kolor okna/chrome
  pod branding Renaty.

Zakres:
- Wymusic globalny styl pionowego scrollbara (`Vertical.TScrollbar`) dla wszystkich miejsc,
  gdzie tworzony jest `ttk.Scrollbar`:
  - `background`: `#1f2833` (ciemny uchwyt),
  - `troughcolor`: `#0b0c10` (ciemne tlo toru),
  - `arrowcolor`: `#ff7100` (pomaranczowe strzalki),
  - `borderwidth`: `0` (plaski, bez ramki).
- Zweryfikowac, czy wszystkie scrollbary (Spansh, Settings, Logbook, dialogi) dziedzicza
  styl globalny, bez lokalnych rozjazdow.
- Dla okna glownego sprawdzic wariant koloru chrome/ramki `#ff7100`:
  - sprawdzic wsparcie natywne na Windows (titlebar/window frame),
  - jesli system nie wspiera, zostawic bezpieczny fallback i udokumentowac ograniczenie.

Pliki startowe:
- `gui/app.py`
- `gui/tabs/settings.py`
- `gui/common_tables.py`
- `gui/tabs/logbook.py`
- `gui/dialogs/*.py`
- `docs/internal/LAST_TICKET.MD`

DoD:
- Scrollbary pionowe maja spojny styl globalny we wszystkich glowych widokach aplikacji.
- Brak lokalnych override psujacych spojnosc (chyba ze jawnie uzasadnione).
- Zweryfikowany wynik dla koloru okna `#ff7100`:
  - dziala natywnie i jest stabilny, albo
  - zostaje fallback + notka techniczna o ograniczeniu platformy.
- Brak regresji czytelnosci i klikalnosci scrollbarow.

Uwagi:
- Kolor titlebara/ramki jest czesciowo zalezny od systemu i ustawien Windows,
  wiec ticket wymaga walidacji runtime na docelowej wersji OS.

Wynik:
- `gui/app.py`:
  - dopiety globalny styl scrollbarow:
    - `TScrollbar`, `Vertical.TScrollbar`, `Horizontal.TScrollbar`,
    - `background=#1f2833`, `troughcolor=#0b0c10`, `arrowcolor=#ff7100`, `borderwidth=0`,
    - mapowanie aktywnych/pressed stanow dla pion/poziom.
  - dopiete best-effort wywolanie chrome okna:
    - `apply_renata_orange_window_chrome(self.root)`.
- `gui/window_chrome.py` (nowy plik):
  - helper do natywnego ustawiania koloru ramki/caption/text na Windows (DWM):
    - border: `#ff7100`,
    - caption: `#ff7100`,
    - text: `#0b0c10`,
  - fallback bez crasha poza Windows lub przy braku wsparcia systemowego.
- Scrollbary z jawna aplikacja stylu pionowego (`style=\"Vertical.TScrollbar\"`):
  - `gui/common_tables.py`,
  - `gui/tabs/settings.py`,
  - `gui/tabs/spansh/trade.py`,
  - `gui/tabs/spansh/neutron.py`.
- Usuniete lokalne wymuszenia motywu, ktore mogly rozjezdzac globalny styl:
  - `gui/tabs/logbook.py` (`theme_use('clam')` usuniete),
  - `gui/dialogs/add_entry.py` (`theme_use('clam')` usuniete).
- Dodatkowo dopiete chrome okna dla popupow:
  - `gui/dialogs/add_entry.py`,
  - `gui/tabs/settings_window.py`.
- `tools/smoke_tests_beckendy.py`:
  - dodano regresje `test_global_scrollbar_style_and_window_chrome_wiring`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 39/39
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### SETTINGS-ADVANCED-SAVEBAR-LAYOUT-01 (P2)
Status: DONE (kod)

Cel:
- Poprawic uklad przyciskow `Przywroc domyslne` i `Zapisz ustawienia` w zakladce `Konfiguracja -> Zaawansowane`.

Zakres:
- Przeniesc pasek akcji pod sekcje `Debug`, aby nie renderowal sie w tym samym wierszu co ramka sekcji.

Pliki:
- `gui/tabs/settings.py`

Wynik:
- W `SettingsTab._build_tab_advanced()` pasek zapisu/resetu zostal przepiety na kolejny wiersz siatki:
  - `self._add_save_bar(parent, row=4)`.
- Efekt UX: przyciski sa pod sekcja `Debug`, a nie wewnatrz jej obszaru.
- Commit:
  - `03d5d22`

---

## Kolejnosc realizacji (feedback gameplay po v0.9.3)

1. TRADE-COMMODITY-VISIBLE-01 (P0)
2. FSS-LAST-BODY-FULL-ORDER-01 (P0)
3. SPANSH-LAYOUT-PARITY-01 (P1)
4. FUEL-LOW-SCO-FALSE-POSITIVE-01 (P1)
5. FSS-PROGRESS-PL-VOICE-01 (P2)
6. WINDOW-RESIZE-HITBOX-02 (P2)
7. TRADE-LAYOUT-SPLIT-VIEW-01 (P1)
8. UI-GLOBAL-SCROLLBAR-WINDOW-COLOR-01 (P1)

---
## Status Renaty na v0.9.5
## FLOW ROADMAP - Faza 1 (Backbone) - rozpiska wykonawcza

Status sekcji: DONE (archiwalna rozpiska wykonawcza; wszystkie tickety F1 oznaczone jako DONE).
Cel nadrzedny:
- Zbudowac wspolny fundament decyzyjny i emisyjny dla wszystkich akcji Renaty.
- Odciec lokalne, rozproszone decyzje TTS/UI na rzecz jednego kontraktu i jednego dispatcher-a.

Definicja DONE dla calej Fazy 1:
- Wszystkie akcje emituja przez `Action Dispatcher` i kontrakt `InsightEmitter`.
- Istnieje wspolna bramka decyzji `Risk + VaR + Trust`.
- Dziala model freshness (`cache + TTL + offline fallback + confidence/status`) i jest widoczny w outputach.
- Capabilities (FREE/PRO) sa warstwa uprawnien niezalezna od logiki akcji.

### FLOW-F1-CONTRACT-UNIFICATION-01 (P0)
Status: DONE (docs + smoke)

Cel:
- Ujednolicic kontrakty danych i emisji: priorytety, poziomy ryzyka, anty-spam, shape insightu.

Zakres:
- Ustalic i zamrozic kontrakt `Insight` (minimalne pola + metadata).
- Ustalic wspolny enum priorytetow TTS/UI.
- Ustalic wspolny model anti-spam (`message_id`, cooldown_scope, dedup_key).
- Ujednolicic slownictwo statusow (`risk_status`, `trust_status`, `confidence`).

Pliki startowe:
- `docs/Flow/private/docs/actions/EVENT_CONTRACT.md`
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`
- `docs/Flow/private/docs/policies/VOICE_CORE_RULES.md`
- `docs/Flow/private/docs/policies/GLOBAL_RISK_POLICY.md`
- `docs/Flow/private/docs/policies/GLOBAL_VALUE_AT_RISK.md`

Testy:
- Contract tests (shape + required fields).
- Regresja anti-spam dla powtarzalnych eventow.

Ryzyka:
- Rozjazd nazw pol miedzy modulami legacy.

DoD:
- Jeden spis kontraktow i enumow obowiazujacy wszystkie akcje.
- Brak nowych wpisow bez `message_id` i `source`.

Checklist PR-1:
- [x] Kontrakt `Insight` opisany i zamrozony (wymagane pola + metadata).
- [x] Uzgodniony enum priorytetow TTS/UI.
- [x] Uzgodniony kontrakt anti-spam (`message_id`, `dedup_key`, `cooldown_scope`, `cooldown_seconds`).
- [x] Ujednolicony slownik statusow (`risk_status`, `trust_status`, `confidence`).
- [x] Aktualizacja:
  - `docs/Flow/private/docs/actions/EVENT_CONTRACT.md`
  - `docs/Flow/private/docs/actions/PR_CHECKLIST.md`
  - `docs/Flow/private/FLOW.md`
- [x] Testy kontraktowe + regresja anti-spam.
- [x] Smoke backend/journal PASS.

Wynik:
- `docs/Flow/private/docs/actions/EVENT_CONTRACT.md`:
  - znormalizowany kontrakt event envelope,
  - dodany kanoniczny kontrakt Insight,
  - dodany model priorytetow TTS/UI,
  - dodany zamrozony kontrakt anti-spam.
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`:
  - dopiete twarde bramki kontraktowe (`source`, `message_id`, anti-spam metadata),
  - dopiety check canonical enumow (`priority`, `risk_status`, `trust_status`, `confidence`).
- `docs/Flow/private/FLOW.md`:
  - dodana sekcja `7.1. Faza 1 - zamrozone kontrakty (minimum)`.

Smoke:
- `py tools/smoke_tests_beckendy.py` PASS 39/39
- `py tools/smoke_tests_journal.py` PASS 6/6

---

### FLOW-F1-DISPATCHER-INSIGHT-EMITTER-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Wdrozyc centralny `Action Dispatcher` + kontrakt `InsightEmitter` jako jedyna sciezke emisji.

Zakres:
- Wydzielenie warstwy orchestracji:
  - `should_speak(...)`
  - `emit_insight(...)`
- Implementacja globalnych zasad:
  - priorytety,
  - cooldown globalny i per-message,
  - deduplikacja,
  - combat silence,
  - polityka "kto moze mowic teraz".
- Migracja akcji z lokalnych emitow na dispatcher.

Pliki startowe:
- `logic/*events*.py` (emitery akcji)
- `logic/tts/*`
- `app/main_loop.py`

Testy:
- Deterministyczny wybor komunikatu przy konflikcie 2+ akcji.
- Regresja: zero "dzikich emitow" poza dispatcherem.

Ryzyka:
- Dispatcher stanie sie "mozgiem domeny" (czego nie robimy).

DoD:
- 100% emisji TTS/UI przechodzi przez dispatcher/emitter.
- Lokalny direct-call TTS w akcjach usuniety lub zablokowany.

Checklist PR-2:
- [x] Zaprojektowac API `should_speak(...)` i `emit_insight(...)`.
- [x] Wydzielic centralny dispatcher jako single source emisji.
- [x] Podlaczyc priorytety i globalny cooldown.
- [x] Podlaczyc dedup i combat silence.
- [x] Przepiac minimum 2-3 akcje z lokalnych emitow na dispatcher.
- [x] Dodac test deterministycznego wyboru komunikatu przy konflikcie.
- [x] Dodac regresje na brak "dzikich emitow".
- [x] Zweryfikowac smoke backend/journal.

Wynik:
- Dodano nowy modul: `logic/insight_dispatcher.py`:
  - kontrakt `Insight`,
  - `should_speak(...)`,
  - `emit_insight(...)`,
  - `pick_insight_for_emit(...)`,
  - `emit_best_insight(...)`.
- Migracja emisji na dispatcher:
  - `logic/events/navigation_events.py`,
  - `logic/events/fuel_events.py`,
  - `logic/events/exploration_fss_events.py`.
- Regresje:
  - `test_insight_dispatcher_conflict_selection_deterministic`,
  - `test_no_wild_emits_in_migrated_event_modules`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 41/41
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### FLOW-F1-RISK-VAR-TRUST-GATE-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Spiac `Risk + VaR + Trust` w jedna bramke decyzyjna wspolna dla akcji.

Zakres:
- Dodanie wspolnego evaluatora decyzji, zwracajacego:
  - level ryzyka,
  - dopuszczalnosc emisji/rekomendacji,
  - confidence/trust status.
- Przepiecie akcji na wspolne API zamiast lokalnych warunkow.
- Zapewnienie spojnosc z politykami risk/var.

Pliki startowe:
- `docs/Flow/private/docs/policies/GLOBAL_RISK_POLICY.md`
- `docs/Flow/private/docs/policies/GLOBAL_VALUE_AT_RISK.md`
- `logic/*risk*`, `logic/*trust*` (jezeli istnieja)

Testy:
- Scenariusze low/medium/high risk.
- Konflikt trust-low vs risk-high.

Ryzyka:
- Podwojna logika (stara i nowa) w okresie migracji.

DoD:
- Akcje nie licza ryzyka lokalnie "po swojemu".
- Wynik bramki jest jedynym zrodlem decyzji risk/trust dla emisji.

Checklist PR-3:
- [x] Zaprojektowac wspolny wynik gate (`risk_status`, `trust_status`, `confidence`, `allow_emit`).
- [x] Uzgodnic mapowanie poziomow risk i trust na decyzje emisji.
- [x] Podlaczyc bramke do dispatcher-a jako pojedynczy punkt decyzji.
- [x] Przepiac minimum 2 akcje z lokalnych warunkow risk/trust.
- [x] Dodac regresje konfliktu: high-risk + low-trust.
- [x] Zweryfikowac smoke backend/journal.

Wynik:
- `logic/insight_dispatcher.py`:
  - dodany model `GateDecision`,
  - dodany `evaluate_risk_trust_gate(...)`,
  - normalizacja `risk_status`, `var_status`, `trust_status`, `confidence`,
  - jednolita decyzja `allow_emit` pod dispatcher.
- Akcje podlaczone pod gate context:
  - `logic/events/navigation_events.py`,
  - `logic/events/fuel_events.py`,
  - `logic/events/exploration_fss_events.py`.
- Regresje:
  - `test_risk_trust_gate_blocks_low_trust_low_confidence`,
  - `test_risk_trust_gate_allows_critical_override`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS 43/43
  - `py tools/smoke_tests_journal.py` PASS 6/6

---

### FLOW-F1-TRUST-FRESHNESS-MINIMUM-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Wdrozyc minimum implementacyjne trust/freshness dla zrodel external.

Zakres:
- Cache danych external + TTL.
- Fallback offline przy braku aktualizacji API.
- Widoczne pola pewnosci/freshness w outputach (UI + insight metadata):
  - `data_age`,
  - `confidence`,
  - `source_status`.

Pliki startowe:
- `docs/Flow/public/docs/data/DATA_TRUST_AND_FRESHNESS.md`
- `logic/providers/*`
- `logic/rows_normalizer.py` (jezeli bierze external data)

Testy:
- TTL hit/miss.
- Tryb offline z ostatnia znana wartoscia.
- UI pokazuje confidence/status.

Ryzyka:
- Niespojny fallback miedzy providerami.

DoD:
- Dla danych external zawsze wiadomo: "jak swieze" i "na ile pewne".

Wynik:
- `logic/cache_store.py`:
  - `get(..., allow_expired=True)` zwraca stale cache do fallbacku offline,
  - metadane cache zawieraja `data_age_seconds`, `ttl_seconds`, `stale`.
- `logic/spansh_client.py`:
  - route telemetry ma freshness: `source_status`, `confidence`, `confidence_score`, `data_age`,
  - dodany fallback offline na stale cache po bledzie API (`OFFLINE_CACHE_FALLBACK`),
  - dodane rozroznienie zrodel: `ONLINE_LIVE` / `CACHE_TTL_HIT` / `OFFLINE_CACHE_FALLBACK`.
- `logic/trade.py`:
  - przekazuje freshness metadata z klienta do normalizera.
- `logic/rows_normalizer.py`:
  - dopina `source_status`, `confidence`, `data_age` do kazdego wiersza trade.
- UI/Schema:
  - `gui/table_schemas.py` + `gui/strings.py`:
    - nowe kolumny trade (domyslnie ukryte): `Status zrodla`, `Pewnosc`, `Wiek danych`,
  - `gui/tabs/spansh/trade.py`:
    - summary i panel szczegolow pokazuja freshness obok metryk rynku.
- Regresje:
  - `tests/test_spansh_client.py`:
    - offline fallback z wygaslego cache,
    - freshness telemetry dla cache hit,
  - `tools/smoke_tests_beckendy.py`:
    - passthrough `source_status/confidence/data_age` w normalizerze trade.
- Testy:
  - `py tools/smoke_tests_beckendy.py` PASS 43/43
  - `py tools/smoke_tests_journal.py` PASS 6/6
  - `py -m unittest discover -s tests -p "test*.py"` PASS 39 (7 skipped)

---

### FLOW-F1-EVENT-INSIGHT-DECISION-MAPPING-01 (P1)
Status: DONE (kod + regresje + smoke)

Cel:
- Domknac mapowanie `event -> insight -> decision space`.

Zakres:
- Spis i standaryzacja mapowania eventow na klasy insightow.
- Powiazanie insightu z decyzja (co wolno powiedziec/pokazac i kiedy).
- Idempotentne `message_id` i dedup_key dla kazdej klasy.

Pliki startowe:
- `docs/Flow/private/docs/actions/EVENT_CONTRACT.md`
- `docs/Flow/private/FLOW.md`
- `logic/events/*.py`

Testy:
- Regresja mapowania dla kluczowych flow (nav/explo/trade/combat).

Ryzyka:
- Luki mapowania dla eventow rzadkich.

DoD:
- Kazdy krytyczny event ma jawna sciezke do insightu i decyzji.

Wynik:
- Dodano centralny rejestr mapowania:
  - `logic/event_insight_mapping.py`
  - kontrakt klasy insightu: `class_id`, `canonical_event`, `kind`, `decision_space`,
    domyslny `priority`, `cooldown_scope`, `cooldown_seconds`, `dedup_template`.
- Rejestr obejmuje kluczowe flow F1 (nav/fuel/fss):
  - `MSG.NEXT_HOP`, `MSG.JUMPED_SYSTEM`, `MSG.NEXT_HOP_COPIED`,
  - `MSG.DOCKED`, `MSG.UNDOCKED`,
  - `MSG.FUEL_CRITICAL`,
  - `MSG.FSS_PROGRESS_25/50/75`, `MSG.FSS_LAST_BODY`, `MSG.SYSTEM_FULLY_SCANNED`,
  - `MSG.FIRST_DISCOVERY`, `MSG.BODY_NO_PREV_DISCOVERY`.
- `logic/insight_dispatcher.py`:
  - `emit_insight(...)` korzysta z `resolve_emit_contract(...)`,
  - normalizuje metadane runtime (`canonical_event`, `insight_class`, `insight_kind`, `decision_space`),
  - domyslnie uzupelnia `priority`, `dedup_key`, cooldown z mapowania klasy.
- Eventy podlaczone do jawnych typow kanonicznych:
  - `logic/events/navigation_events.py` (`ROUTE_PROGRESS`, `JUMP_COMPLETED`),
  - `logic/events/fuel_events.py` (`SHIP_HEALTH_CHANGED`),
  - `logic/events/exploration_fss_events.py` (`SYSTEM_SCANNED`, `BODY_DISCOVERED`).
- Regresje:
  - `tests/test_event_insight_mapping.py`:
    - pokrycie mapowania message_id -> klasa,
    - pokrycie domyslnego resolve kontraktu emitowania.
  - `tools/smoke_tests_beckendy.py`:
    - `test_event_insight_mapping_core_contract`.
- Testy:
  - `py tools/smoke_tests_beckendy.py` PASS 44/44
  - `py tools/smoke_tests_journal.py` PASS 6/6
  - `py -m unittest discover -s tests -p "test*.py"` PASS 41 (7 skipped)

---

### FLOW-F1-CAPABILITIES-SEPARATION-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Wdrozyc warstwe capabilities FREE/PRO niezalezna od logiki akcji.

Zakres:
- Jeden kontrakt capabilities (np. `capabilities.voice_stt`).
- Bramka capability przed funkcja, nie w logice biznesowej akcji.
- Brak warunkow "czy user zaplacil" w action modules.

Pliki startowe:
- `docs/Flow/private/docs/policies/PRO_FEATURE_POLICY.md`
- `docs/Flow/private/FLOW.md`
- `app/config*`, `logic/capabilities*` (jezeli istnieja)

Testy:
- Smoke FREE profile.
- Smoke PRO profile.
- Audyt importow/warunkow planu.

Ryzyka:
- Capability creep (PRO zaczyna zmieniac jakosc decyzji zamiast kanal dostepu).

DoD:
- Capabilities sa osobna warstwa uprawnien i sa audytowalne.

Wynik:
- Dodano centralny kontrakt capabilities:
  - `logic/capabilities.py`
  - profile: `FREE` / `PRO`,
  - klucze capability:
    - `capabilities.voice_stt`,
    - `capabilities.ui_extended_tabs`,
    - `capabilities.settings_full`,
    - `capabilities.tts_advanced_policy`.
- Dodano kompatybilna migracje z legacy flagi:
  - `features.tts.free_policy_enabled` -> patch capability (`plan.profile` + capability flags).
- `config.py`:
  - dopiety `plan.profile`,
  - dopiete klucze capability (warstwa uprawnien audytowalna w configu).
- Bramka capability podlaczona przed funkcjami planowymi/UI:
  - `gui/app.py`: taby rozszerzone sa sterowane `capabilities.ui_extended_tabs`,
  - `gui/tabs/settings.py`: widok FREE/full sterowany `capabilities.settings_full`,
  - `logic/utils/notify.py`: polityka TTS sterowana `capabilities.tts_advanced_policy`.
- Action modules nie zawieraja warunkow planu:
  - dodany audyt regresyjny sprawdzajacy brak `features.tts.free_policy_enabled` / `plan.profile` w `logic/events/*`.
- Regresje:
  - `tests/test_capabilities.py`:
    - profile FREE/PRO,
    - override capability,
    - patch config z free-policy.
  - `tools/smoke_tests_beckendy.py`:
    - `test_capabilities_profile_contract`,
    - `test_no_plan_checks_in_action_modules`.
- Testy:
  - `py tools/smoke_tests_beckendy.py` PASS 46/46
  - `py tools/smoke_tests_journal.py` PASS 6/6
  - `py -m unittest discover -s tests -p "test*.py"` PASS 45 (7 skipped)

---

### FLOW-F1-QUALITY-GATES-AND-SMOKE-01 (P1)
Status: DONE (gate + regresje + smoke)

Cel:
- Dodac staly pakiet bramek jakosci pod Faze 1.

Zakres:
- Smoke FREE/PRO dla krytycznych flow.
- Invariant test: `combat state => zero TTS` (poza wyjatkami krytycznymi).
- Gate przeciw "dzikim emitom" i brakom kontraktu.
- Checklista PR wymuszajaca update FLOW przy zmianie architektury.

Pliki startowe:
- `tools/smoke_tests_beckendy.py`
- `tools/smoke_tests_journal.py`
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`
- `docs/Flow/private/FLOW.md`

Testy:
- Automatyczne w CI + manual smoke scenariusze krytyczne.

Ryzyka:
- Zielone smoke, ale realny rozjazd runtime bez scenariuszy edge-case.

DoD:
- Bramki odpalaja sie stale i blokuja regresje Fazy 1.

Wynik:
- Dodano twarde gate'y jakosci w smoke backend:
  - `test_combat_silence_invariant_zero_tts_except_critical`
    - invariant: `combat state => zero TTS` dla niekrytycznych,
    - wyjatek krytyczny (`P0_CRITICAL`) pozostaje dozwolony.
  - `test_emit_insight_contract_gate_in_event_modules`
    - AST-audyt `logic/events/*`:
      - kazde `emit_insight(...)` musi miec komplet kontraktu:
        `message_id`, `source`, `event_type`, `context`,
        `priority`, `dedup_key`, `cooldown_scope`, `cooldown_seconds`.
  - `test_runtime_free_pro_capabilities_smoke`
    - runtime smoke FREE/PRO na aktywnym configu:
      - capability patch FREE blokuje capability premium,
      - capability patch PRO odblokowuje capability premium.
- Utrzymane gate'y z poprzednich PR:
  - brak dzikich emitow w migrowanych event modules,
  - gate mapowania event->insight->decision space,
  - gate capabilities profile contract i brak warunkow planu w `logic/events/*`.
- Test hardening:
  - audyt AST czyta pliki `utf-8-sig`, co usuwa falszywe fail'e na BOM.
- Testy:
  - `py tools/smoke_tests_beckendy.py` PASS 49/49
  - `py tools/smoke_tests_journal.py` PASS 6/6
  - `py -m unittest discover -s tests -p "test*.py"` PASS 45 (7 skipped)

---

## Kolejnosc realizacji - FLOW Faza 1

1. FLOW-F1-CONTRACT-UNIFICATION-01
2. FLOW-F1-DISPATCHER-INSIGHT-EMITTER-01
3. FLOW-F1-RISK-VAR-TRUST-GATE-01
4. FLOW-F1-TRUST-FRESHNESS-MINIMUM-01
5. FLOW-F1-EVENT-INSIGHT-DECISION-MAPPING-01
6. FLOW-F1-CAPABILITIES-SEPARATION-01
7. FLOW-F1-QUALITY-GATES-AND-SMOKE-01

Uwagi wykonawcze:
- Nie robimy "big bang". Kazdy ticket domykamy z testami i aktualizacja docs.
- Po kazdym ticketcie aktualizujemy:
  - `docs/Flow/private/FLOW.md`,
  - `docs/Flow/private/ROADMAP.md` (jezeli zmienia sie zakres/kolejnosc),
  - status ticketu w tym pliku.

---

## FLOW ROADMAP - Faza 2 (Nawigacja i sprzedaz) - rozpiska wykonawcza

Status sekcji: DONE (archiwalna rozpiska wykonawcza; wszystkie tickety F2 oznaczone jako DONE).
Cel nadrzedny:
- Dowiezc MVP operacyjne: stabilny Route Awareness/Intent + Sell Assist (2-3 opcje, bez auto-gry).
- Domknac przekazanie wyboru sprzedazy do intentu nawigacyjnego.
- Utrzymac granice FREE/PRO przez capabilities (bez warunkow planu w logice akcji).

Definicja DONE dla calej Fazy 2:
- Route Planner stabilnie obsluguje `intent` i `off-route` bez spamu.
- Sell Assist zawsze prezentuje 2-3 opcje + `Pomijam` (bez narzucania "top 1").
- Wybor opcji sprzedazowej moze ustawic tylko intent (nigdy nie automatyzuje mapy gry).
- Funkcje glosowe sa podlaczone przez capabilities, a logika akcji pozostaje plan-agnostyczna.

Zasada podzialu commitow w Fazie 2:
- `FREE (PUB)` = kod i zachowania publikowane do public repo (release FREE).
- `PRO (PRO)` = tylko komfort/interakcja premium, realizowane w repo prywatnym.
- Jeden commit nie miesza zakresow `PUB` i `PRO`.

### FLOW-F2-ROUTE-AWARENESS-AND-INTENT-BASE-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Wdrozyc stabilny modul Route Awareness + Route Intent zgodnie z `ACTION_ROUTE_PLANNER.md`.

Zakres:
- Ujednolicic model stanu:
  - `route_mode` (`awareness | intent | idle`),
  - `route_target`,
  - `route_progress_percent`,
  - `next_system`,
  - `is_off_route`.
- Podlaczyc triggery:
  - route update, jump, progi 25/50/75/100, off-route.
- Utrzymac anti-spam:
  - 1 komunikat na prog,
  - dedup off-route,
  - respect global cooldown/combat silence.

Podzial FREE/PRO:
- FREE (PUB):
  - caly silnik route awareness/intent,
  - progi 25/50/75/100, off-route, anti-spam, UI status.
- PRO (PRO):
  - tylko dodatkowe wejscia glosowe do tych samych funkcji (bez zmiany logiki decyzji).

Commit routing:
- `[PUB]` dla core route/intent.
- `[PRO]` tylko dla premium voice convenience (bez naruszania core).

Pliki startowe:
- `logic/events/navigation_events.py`
- `logic/event_handler.py`
- `gui/common.py`
- `docs/Flow/private/docs/actions/ACTION_ROUTE_PLANNER.md`

Testy:
- regresja progow 25/50/75/100,
- regresja off-route (brak petli komunikatow),
- scenariusz restart appki w locie (odtworzenie intentu/local state).

Ryzyka:
- konflikt route-awareness z intent-only, gdy brak aktywnej trasy gry.

DoD:
- route status jest stabilny i czytelny (on-route/off-route/intent-only),
- brak per-hop narracji i brak spamu przy stalej sytuacji.

Checklist PR-F2-1:
- [x] Standaryzacja stanu route awareness/intent.
- [x] Podpiecie triggerow progowych i off-route.
- [x] Anty-spam dla progress + off-route.
- [x] Update docs:
  - `docs/Flow/private/FLOW.md`
  - `docs/Flow/private/docs/actions/ACTION_ROUTE_PLANNER.md`
- [x] Smoke backend/journal PASS.

Wynik:
- `app/state.py`:
  - dodany kanoniczny model runtime:
    - `route_mode`,
    - `route_target`,
    - `route_progress_percent`,
    - `next_system`,
    - `is_off_route`,
  - dodane API:
    - `get_route_awareness_snapshot()`,
    - `update_route_awareness(...)`,
    - `set_route_intent(...)`.
- `gui/common_route_progress.py`:
  - podpiecie sync stanu route awareness pod:
    - route ready,
    - jump progress,
    - route complete,
    - confirmed off-route,
    - powrot na trase.
- `gui/tabs/spansh/planner_base.py`:
  - intent ustawiany przy starcie liczenia trasy (gdy jest cel),
  - przejscie do awareness po znalezieniu trasy,
  - route empty -> intent-only albo idle (bez automatyzacji gry),
  - reset route state przy clear.
- `logic/events/navigation_events.py`:
  - `NavRoute` aktualizuje awareness state, gdy nie ma aktywnej trasy Spansh,
  - `NavRouteClear` / pusty `NavRoute` czysci awareness do `idle`.
- `gui/tabs/pulpit.py`:
  - status trasy pokazuje `on-route/off-route/intent-only`.
- Regresje:
  - nowy unit: `tests/test_route_awareness_state.py`,
  - rozszerzony smoke: `tools/smoke_tests_journal.py::test_nav_symbiosis_guard_and_desync`
    o asercje stanu awareness/off-route/progress.
- Testy:
  - `py -m unittest tests.test_route_awareness_state -v` PASS 3/3
  - `py tools/smoke_tests_journal.py` PASS 6/6
  - `py tools/smoke_tests_beckendy.py` PASS 49/49
  - `py -m unittest discover -s tests -p "test*.py"` PASS 48 (7 skipped)
  - `py -m compileall app gui logic tools` PASS

---

### FLOW-F2-SELL-ASSIST-RANKING-DECISION-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Wdrozyc Sell Assist jako decision space 2-3 opcji z trade-offami (`czas/zysk/ryzyko/trust`).

Zakres:
- Ujednolicic scoring:
  - `price_score`, `time_score`, `risk_score`, `trust_score`.
- Wymusic format wyniku:
  - zawsze 2-3 opcje (gdy dane sa dostepne),
  - zawsze przycisk `Pomijam`,
  - brak "jedynej slusznej" opcji.
- Pokazac reasoning:
  - zysk orientacyjny,
  - ETA/dystans,
  - ryzyko,
  - jakosc danych.

Podzial FREE/PRO:
- FREE (PUB):
  - scoring i ranking 2-3 opcji,
  - `Pomijam`,
  - decyzja na podstawie `czas/zysk/ryzyko/trust`,
  - fallbacki (offline/stale dane).
- PRO (PRO):
  - tylko forma interakcji (np. glosowe wywolanie panelu, szybkie voice navigation po opcjach).

Commit routing:
- `[PUB]` dla silnika rankingu i kart decyzji.
- `[PRO]` dla voice-first UX wokol tego samego rankingu.

Pliki startowe:
- `logic/trade.py`
- `logic/rows_normalizer.py`
- `gui/tabs/spansh/trade.py`
- `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`

Testy:
- ranking i fallback przy starych danych/offline,
- brak pustego decision space dla poprawnych danych wejscia,
- regresja: brak "top 1" bez alternatyw.

Ryzyka:
- rozjazd miedzy scoringiem runtime i tym, co pokazuje UI.

DoD:
- zawsze 2-3 opcje + `Pomijam`,
- kazda opcja ma czytelne trade-offy i status trust/freshness.

Checklist PR-F2-2:
- [x] Stabilny scoring 4-skladowy.
- [x] Decision cards 2-3 + `Pomijam`.
- [x] Fallback offline/stale data bez agresywnej rekomendacji.
- [x] Update docs:
  - `docs/Flow/private/FLOW.md`
  - `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`
- [x] Smoke + testy regresyjne PASS.

Wynik:
- `logic/trade.py`:
  - dodany silnik `build_sell_assist_decision_space(...)`,
  - scoring 4-skladowy:
    - `price_score`,
    - `time_score`,
    - `risk_score`,
    - `trust_score`,
  - strategie wyboru opcji:
    - `fastest`,
    - `highest_price`,
    - `safest`,
    - fallback `balanced`,
  - kontrakt outputu:
    - zawsze 2-3 opcje (gdy sa dane),
    - zawsze `skip_action=Pomijam`,
    - brak narzucanego `top1/recommended`,
  - tryb degradacji:
    - `advisory_only=true` dla stale/offline.
- `gui/tabs/spansh/trade.py`:
  - nowy panel `Sell Assist` nad tabela trasy,
  - render 2-3 kart opcji z trade-offami:
    - zysk orientacyjny,
    - ETA/dystans,
    - ryzyko,
    - trust/freshness,
  - staly przycisk `Pomijam`,
  - reset panelu przy `clear`, bledzie i braku wynikow.
- `tests/test_sell_assist_ranking.py`:
  - regresje:
    - 2-3 opcje + `Pomijam`,
    - fallback stale/offline (`advisory_only`),
    - brak wymuszania `top1` nawet dla pojedynczego lega.
- Docs:
  - `docs/Flow/private/FLOW.md`: nowa sekcja 7.3 (Sell Assist baseline),
  - `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`: dopisane zasady runtime F2-2.
  - `docs/Flow/private/ROADMAP.md`: odhaczone zadanie Sell Assist i DoD 2-3 + `Pomijam`.

Testy:
- `py -m unittest tests.test_sell_assist_ranking -v` PASS 3/3
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS
- `py -m unittest discover -s tests -p "test*.py"` PASS
- `py -m compileall app gui logic tools` PASS

---

### FLOW-F2-SELL-TO-ROUTE-INTENT-HANDOFF-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Domknac przekazanie wyboru z Sell Assist do Route Intent bez automatyzacji gry.

Zakres:
- Po wyborze opcji Sell Assist:
  - ustawiany jest tylko `route_intent` (target system/station),
  - brak zmian na mapie gry i brak auto-route.
- Dodac jasny UX:
  - "Ustaw intent",
  - "Pomijam",
  - komunikat potwierdzenia bez narzucania.

Podzial FREE/PRO:
- FREE (PUB):
  - handoff wyboru Sell Assist -> Route Intent,
  - twarda blokada auto-route/auto-gry.
- PRO (PRO):
  - glosowe potwierdzenie / glosowa akcja "ustaw intent" jako alternatywny kanal.

Commit routing:
- `[PUB]` dla kontraktu handoff i guardow anty-automatyzacji.
- `[PRO]` dla premium voice command wrapper.

Pliki startowe:
- `logic/events/navigation_events.py`
- `gui/tabs/spansh/trade.py`
- `gui/common.py`
- `docs/Flow/private/docs/actions/ACTION_ROUTE_PLANNER.md`
- `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`

Testy:
- wybor opcji ustawia intent i nic poza tym,
- brak side-effectu typu automatyczne ustawienie trasy,
- regresja "Pomijam" (brak ponawiania tej samej sugestii w petli).

Ryzyka:
- przypadkowe podpinki do starych helperow nawigacji, ktore modyfikuja route.

DoD:
- handoff = tylko zapis intentu + opcjonalny next-hop helper,
- zero auto-gry.

Checklist PR-F2-3:
- [x] Spiety kontrakt wyboru Sell Assist -> Route Intent.
- [x] Blokada automatyzacji mapy (twardy guard).
- [x] Potwierdzenie UX "intent set" + "Pomijam".
- [x] Update docs:
  - `docs/Flow/private/FLOW.md`
  - `docs/Flow/private/docs/actions/ACTION_ROUTE_PLANNER.md`
  - `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`
- [x] Smoke backend/journal PASS.

Wynik:
- `logic/trade.py`:
  - dodany kontrakt `handoff_sell_assist_to_route_intent(...)`,
  - twardy guard: `allow_auto_route=True` -> `AUTO_ROUTE_FORBIDDEN_SELL_ASSIST`,
  - handoff ustawia tylko intent przez callback `set_route_intent(...)`,
  - brak podpinek do route manager/mapy gry.
- `gui/tabs/spansh/trade.py`:
  - karty Sell Assist dostaly akcje `Ustaw intent`,
  - `Pomijam` daje jawne potwierdzenie UX bez side-effectow,
  - potwierdzenie `intent set` podkresla brak auto-route.
- `tests/test_sell_assist_intent_handoff.py`:
  - regresje:
    - wybor opcji ustawia intent i nic poza tym,
    - guard blokuje auto-route,
    - brak targetu nie ustawia intentu,
    - route manager pozostaje bez zmian po handoff.
- Docs:
  - `docs/Flow/private/FLOW.md`: sekcja 7.4 (handoff Sell -> Intent),
  - `docs/Flow/private/docs/actions/ACTION_ROUTE_PLANNER.md`: sekcja 10.1,
  - `docs/Flow/private/docs/actions/ACTION_SELL_ASSIST.md`: kontrakt handoff i UX.
  - `docs/Flow/private/ROADMAP.md`: odhaczone przekazanie wyboru do intent i DoD anti-auto-map.

Testy:
- `py -m unittest tests.test_sell_assist_intent_handoff -v` PASS 4/4
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS
- `py -m unittest discover -s tests -p "test*.py"` PASS
- `py -m compileall app gui logic tools` PASS

---

### FLOW-F2-VOICE-CAPABILITIES-WIRING-01 (P1)
Status: DONE (kod + regresje + smoke)

Cel:
- Podpiac capabilities do funkcji glosowych (np. STT) bez mieszania planow w logice akcji.

Zakres:
- Capability gate przed funkcja:
  - `capabilities.voice_stt` i pokrewne.
- Brak warunkow `plan.profile` / "czy user zaplacil" w modulach akcji.
- FREE fallback:
  - UI/hotkey dziala,
  - brak twardych errorow przy braku STT.

Podzial FREE/PRO:
- FREE (PUB):
  - capability gates i fallback (system stabilny bez STT),
  - brak plan-checkow w logice akcji.
- PRO (PRO):
  - faktyczne premium endpointy STT/voice-first (o ile wystepuja poza FREE).

Commit routing:
- `[PUB]` dla warstwy capabilities i guardow architektonicznych.
- `[PRO]` dla prywatnych integracji premium voice.

Pliki startowe:
- `logic/capabilities.py`
- `gui/tabs/settings.py`
- `logic/utils/notify.py`
- `logic/events/*.py` (audyt)
- `docs/Flow/private/docs/policies/PRO_FEATURE_POLICY.md`

Testy:
- smoke FREE profile,
- smoke PRO profile,
- AST/audyt: brak warunkow planu w `logic/events/*`.

Ryzyka:
- capability creep: PRO zacznie zmieniac jakosc decyzji zamiast kanal interakcji.

DoD:
- capabilities sa jedyna bramka uprawnien glosowych,
- logika akcji pozostaje plan-agnostyczna.

Checklist PR-F2-4:
- [x] Gate capability pod STT/voice actions.
- [x] Fallback FREE bez crashy i bez degradacji core awareness.
- [x] Audyt braku plan-checkow w action modules.
- [x] Update docs:
  - `docs/Flow/private/FLOW.md`
  - `docs/Flow/private/docs/policies/PRO_FEATURE_POLICY.md`
- [x] Smoke backend/journal PASS.

Wynik:
- `logic/capabilities.py`:
  - `capability_config_patch_from_free_policy(...)` obejmuje teraz tez `capabilities.voice_stt`,
  - dodany helper `is_voice_stt_enabled(...)` pod centralne gate'y.
- `logic/utils/notify.py`:
  - dodany centralny wrapper `execute_voice_stt_action(...)`,
  - FREE fallback: brak wyjatku, bezpieczny log "uzyj UI/hotkey",
  - PRO path: uruchamia akcje STT; awaria akcji jest soft-fail (bez crasha).
- `gui/tabs/settings.py`:
  - widoczny status capability STT w ustawieniach zaawansowanych (read-only),
  - dopisana informacja o fallbacku FREE (UI/hotkey bez crashy).
- Audyt:
  - utrzymany guard "brak plan-checkow" w `logic/events/*` (test smoke).
- Docs:
  - `docs/Flow/private/FLOW.md`: nowa sekcja 7.5 (Voice capabilities wiring),
  - `docs/Flow/private/docs/policies/PRO_FEATURE_POLICY.md`: kontrakt techniczny STT gate,
  - `docs/Flow/private/ROADMAP.md`: odhaczone zadanie F2 "capabilities -> voice/STT".

Testy:
- `py -m unittest tests.test_voice_capability_gate -v` PASS
- `py -m unittest tests.test_capabilities -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS
- `py -m unittest discover -s tests -p "test*.py"` PASS

---

### FLOW-F2-QUALITY-GATES-AND-SMOKE-01 (P1)
Status: DONE (kod + quality gates + smoke)

Cel:
- Dodac stale bramki jakosci dla Fazy 2 (route/sell/intent/capabilities).

Zakres:
- Test invariants:
  - route intent/off-route anti-spam,
  - sell decision space 2-3 + `Pomijam`,
  - handoff only-intent (no auto-route),
  - FREE/PRO voice capabilities smoke.
- Rozszerzyc smoke backend/journal o scenariusze F2.

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe gate'y dla route/sell/handoff i anty-spam.
- PRO (PRO):
  - dodatkowe smoke premium voice/capabilities (uruchamiane w prywatnym pipeline).

Commit routing:
- `[PUB]` dla gate'ow wymaganych do public release FREE.
- `[PRO]` dla dodatkowych testow/integracji premium.

Pliki startowe:
- `tools/smoke_tests_beckendy.py`
- `tools/smoke_tests_journal.py`
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`

Testy:
- automatyczne gate'y + manual sanity check z realnym payloadem Trade/Route.

Ryzyka:
- zielone testy jednostkowe bez pokrycia scenariuszy cross-module.

DoD:
- gate'y blokują regresje F2 przed releasem.

Checklist PR-F2-5:
- [x] Dodane testy invariantow F2.
- [x] Dodane scenariusze cross-module (sell -> intent -> route status).
- [x] Update checklisty PR pod wymagania F2.
- [x] Smoke backend/journal PASS.

Wynik:
- `tools/smoke_tests_beckendy.py`:
  - dodany gate `test_f2_sell_intent_route_cross_module`:
    - decyzja Sell Assist (2-3 + `Pomijam`),
    - handoff `sell -> intent`,
    - przejscie `intent -> awareness` po NavRoute bez off-route.
- `tests/test_f2_quality_gates.py`:
  - regresja cross-module pod runtime kontrakt F2 (sell -> intent -> awareness).
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`:
  - dopisane wymagane quality gates F2 (route/sell/handoff/voice/cross-module).

Testy:
- `py -m unittest tests.test_f2_quality_gates -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS
- `py -m unittest discover -s tests -p "test*.py"` PASS

---

## Kolejnosc realizacji - FLOW Faza 2

1. FLOW-F2-ROUTE-AWARENESS-AND-INTENT-BASE-01
2. FLOW-F2-SELL-ASSIST-RANKING-DECISION-01
3. FLOW-F2-SELL-TO-ROUTE-INTENT-HANDOFF-01
4. FLOW-F2-VOICE-CAPABILITIES-WIRING-01
5. FLOW-F2-QUALITY-GATES-AND-SMOKE-01

Uwagi wykonawcze:
- Pracujemy w rytmie: ticket -> commit -> update md -> raport.
- Kazdy ticket zamykamy dopiero po smoke i aktualizacji `FLOW.md`.
- Przy zmianie zakresu Fazy 2 aktualizujemy tez `docs/Flow/private/ROADMAP.md`.

---

### FLOW-F3-EXPLORATION-AWARENESS-STACK-01 (P0)
Status: DONE (kod + regresje + smoke)

Cel:
- Wdrozyc Exploration Awareness jako stabilny stack calloutow i podsumowan bez spamu.

Zakres:
- Normalizacja eventow eksploracyjnych pod jeden kontrakt insightow.
- Mechanika calloutow:
  - pojedynczy summary dla systemow mieszanych,
  - limity calloutow na system/sesje,
  - dedup i cooldown per `message_id`/`body`.
- Integracja z dispatcherem:
  - priorytety,
  - anti-spam,
  - combat silence.

Podzial FREE/PRO:
- FREE (PUB):
  - pelny awareness eksploracyjny (callouty + summary + anti-spam),
  - brak degradacji tresci insightow.
- PRO (PRO):
  - wygodniejszy kanal dostepu (voice-first/nawigacja po insightach),
  - bez zmiany logiki i jakosci insightow.

Commit routing:
- `[PUB]` dla logiki awareness/anti-spam i kontraktow insightow.
- `[PRO]` dla dodatkowych warstw interakcji premium.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `1c1b637`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

Pliki startowe:
- `logic/events/exploration_*`
- `logic/insight_dispatcher.py`
- `docs/Flow/private/docs/actions/ACTION_EXPLORATION_AWARENESS.md`
- `docs/Flow/private/FLOW.md`

Testy:
- regresja: system mieszany -> single summary,
- regresja: limity calloutow + dedup,
- smoke backend/journal dla payloadow eksploracyjnych.

Ryzyka:
- zbyt gadatliwy flow i powrot spamu po wlaczeniu nowych calloutow.

DoD:
- Exploration Awareness nie spamuje w systemach mieszanych.

Checklist PR-F3-1:
- [x] Callout stack z limitami i summary.
- [x] Integracja anti-spam i cooldown z dispatcherem.
- [x] Brak "dzikich" emitow poza InsightEmitter (dla calloutow awareness objetych tym ticketem).
- [x] Update docs workflow (ticket tracker + current task).
- [x] Smoke PASS.

Wynik:
- Dodany centralny stack awareness:
  - `logic/events/exploration_awareness.py`
  - limity per system/per sesja,
  - jednorazowy summary systemowy po przekroczeniu limitu,
  - snapshot stanu do regresji.
- Callouty exploration przepiete na stack + dispatcher:
  - `logic/events/exploration_high_value_events.py` (ELW/WW/Terraformable),
  - `logic/events/exploration_bio_events.py` (DSS bio signals),
  - `logic/events/exploration_misc_events.py` (first footfall przez dispatcher).
- Reset awareness podlaczony do resetu eksploracji:
  - `logic/events/exploration_fss_events.py`.
- Rozszerzony kontrakt mapowania i TTS:
  - `logic/event_insight_mapping.py`,
  - `logic/tts/text_preprocessor.py` (`MSG.EXPLORATION_SYSTEM_SUMMARY`).
- Dodane regresje:
  - `tests/test_exploration_awareness_stack.py`.

Testy:
- `py -m unittest tests.test_exploration_awareness_stack -v` PASS
- `py -m unittest tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (50/50)
- `py tools/smoke_tests_journal.py` PASS (6/6)

---

### FLOW-F3-FIRST-STATUS-CONTRACT-01 (P0)
Status: DONE

Cel:
- Domknac kontrakt first-statusow (okazja vs zdobycie) bez falszywych obietnic.

Zakres:
- Rozdzielenie semantyczne:
  - "first opportunity" (mozliwosc),
  - "first confirmed" (faktyczne zdobycie).
- Zakaz komunikatow sugerujacych pewnik przy niepelnych danych/trust.
- Jasny mapping `event -> insight kind -> decision space`.
- Dodanie confidence/trust do komunikatow first-status.

Podzial FREE/PRO:
- FREE (PUB):
  - pelna logika first-status i etyczna semantyka.
- PRO (PRO):
  - forma prezentacji i personalizacja, bez zmiany semantyki.

Commit routing:
- `[PUB]` dla kontraktu first-status i mapowan insightow.
- `[PRO]` tylko dla dodatkowego UX.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE.
- PRO: NIE WDROZONE.

Pliki startowe:
- `logic/event_insight_mapping.py`
- `logic/events/exploration_misc_events.py`
- `docs/Flow/private/docs/actions/ACTION_EXPLORATION_AWARENESS.md`
- `docs/Flow/private/docs/policies/VOICE_CORE_RULES.md`

Testy:
- regresja: opportunity != confirmed,
- regresja: brak falszywej obietnicy przy low trust/low confidence.

Ryzyka:
- mylenie "okazji" ze "zdobyciem" przy niepewnych danych.

DoD:
- First statusy sa rozroznione poprawnie i bez falszywych obietnic.

Checklist PR-F3-2:
- [x] Kontrakt statusow first z dwoma stanami semantycznymi.
- [x] Guardrails anti-overpromise przy niskim trust/confidence.
- [x] Regresje mapowania i tresci komunikatow.
- [x] Update docs (`ACTION_EXPLORATION_AWARENESS.md` + `VOICE_CORE_RULES.md`).
- [x] Smoke PASS.

Wdrozenie (FREE/PUB):
- Dodane rozdzielenie semantyki:
  - `MSG.FIRST_DISCOVERY_OPPORTUNITY` -> `first_opportunity`,
  - `MSG.FIRST_DISCOVERY` + `MSG.BODY_NO_PREV_DISCOVERY` -> `first_confirmed`.
- Kontekst emisji first-status zawiera:
  - `first_status_kind`,
  - `trust_status`,
  - `confidence`.
- Dodany guard anti-overpromise:
  - przy niepelnych danych (`WasDiscovered=None`) najpierw tylko "okazja".
- Rozszerzone mapowania:
  - `logic/event_insight_mapping.py`,
  - `logic/utils/notify.py`,
  - `logic/tts/text_preprocessor.py`.
- Dodane regresje:
  - `tests/test_f3_first_status_contract.py`,
  - update `tests/test_event_insight_mapping.py`.

Testy:
- `py -m unittest tests.test_f3_first_status_contract -v` PASS
- `py -m unittest tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (50/50)
- `py tools/smoke_tests_journal.py` PASS (6/6)

---

### FLOW-F3-DSS-HELPER-COMPLETION-01 (P1)
Status: DONE

Cel:
- Wdrozyc DSS Helper (wartosc mapowania + completion) zgodnie z polityka glosu.

Zakres:
- Heurystyka "warto mapowac / mozna pominac" oparta o risk/trust/value.
- Completion flow:
  - postep mapowania,
  - komunikat completion,
  - brak floodu przy wielu cialach.
- Integracja z combat silence + cooldowny globalne.

Podzial FREE/PRO:
- FREE (PUB):
  - pelna logika DSS helper i completion.
- PRO (PRO):
  - voice-first shortcuty/komendy do panelu DSS helper.

Commit routing:
- `[PUB]` dla logiki DSS i gate'ow anti-spam/combat silence.
- `[PRO]` dla premium sterowania interakcja.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE.
- PRO: NIE WDROZONE.

Pliki startowe:
- `logic/events/exploration_dss_events.py`
- `logic/event_handler.py`
- `logic/event_insight_mapping.py`
- `docs/Flow/private/docs/actions/ACTION_DSS_HELPER.md`

Testy:
- regresja completion,
- regresja combat silence (DSS nie przebija ciszy bojowej),
- smoke scenariuszy DSS.

Ryzyka:
- zbyt czeste komunikaty completion przy dynamicznych eventach skanu.

DoD:
- DSS respektuje combat silence oraz cooldowny globalne dispatcher-a.

Checklist PR-F3-3:
- [x] DSS value/completion flow wdrozony.
- [x] Dedup i cooldown pod completion.
- [x] Combat silence invariants zachowane.
- [x] Update docs (`ACTION_DSS_HELPER.md`).
- [x] Smoke PASS.

Wdrozenie (FREE/PUB):
- Dodany modul runtime DSS helper:
  - `logic/events/exploration_dss_events.py`.
- Dodany flow target hint:
  - heurystyka "warto mapowac" oparta o wartosc mapowania (`carto_df`) i prog.
- Dodany flow completion:
  - obsluga `SAAScanComplete`,
  - completion raz per `(system, body)`,
  - sparse progress milestone (1/3/5/co 5 cial) bez floodu.
- Dodane first mapped tylko przy potwierdzonych danych eventu.
- Integracja event routera:
  - `Scan` -> `handle_dss_target_hint`,
  - `SAAScanComplete` -> `handle_dss_scan_complete`.
- Rozszerzone kontrakty insight:
  - `MSG.DSS_TARGET_HINT`,
  - `MSG.DSS_COMPLETED`,
  - `MSG.DSS_PROGRESS`,
  - `MSG.FIRST_MAPPED`.
- Rozszerzone mapowanie TTS/notify + smoke gates.

Testy:
- `py -m unittest tests.test_f3_dss_helper_completion -v` PASS
- `py -m unittest tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (51/51)
- `py tools/smoke_tests_journal.py` PASS (6/6)

---

### FLOW-F3-EXOBIO-HELPER-PROGRESS-01 (P1)
Status: DONE

Cel:
- Wdrozyc Exobiology Helper (kandydaci + distance gates + progres) bez regresji glosu.

Zakres:
- Kandydaci exobio:
  - identyfikacja celow,
  - priorytety i limity calloutow.
- Distance gates + progress:
  - READY fire-once per cykl,
  - sample progress 1/2/3 zgodny z polityka komunikatow,
  - brak spamowania "tickami dystansu".
- Integracja z combat silence + global cooldown.

Podzial FREE/PRO:
- FREE (PUB):
  - pelny helper Exobio (READY/progress/kandydaci).
- PRO (PRO):
  - voice-first obsluga (np. odczyt statusu na zadanie), bez zmiany logiki.

Commit routing:
- `[PUB]` dla kontraktow Exobio i anti-spam.
- `[PRO]` dla rozszerzen interakcyjnych.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE.
- PRO: NIE WDROZONE.

Pliki startowe:
- `logic/events/exploration_bio_events.py`
- `logic/events/exploration_misc_events.py`
- `docs/Flow/private/docs/actions/ACTION_EXOBIOLOGY_HELPER.md`

Testy:
- regresja READY fire-once,
- regresja sekwencji 1/2/3 i komunikatu finalnego,
- smoke Exobio + combat silence.

Ryzyka:
- spam READY albo pomijanie istotnych komunikatow progresu.

DoD:
- Exobio respektuje combat silence oraz cooldowny globalne dispatcher-a.

Checklist PR-F3-4:
- [x] Kandydaci Exobio i distance gates wdrozone.
- [x] Progress 1/2/3 zgodny z kontraktem glosowym.
- [x] READY fire-once i dedup stabilne.
- [x] Update docs (`ACTION_EXOBIOLOGY_HELPER.md`).
- [x] Smoke PASS.

Wdrozenie (FREE/PUB):
- Exobio runtime przepiete na dispatcher (`emit_insight`) bez lokalnych `powiedz()`.
- Komunikaty Exobio objete kontraktem insight:
  - `MSG.EXOBIO_SAMPLE_LOGGED`,
  - `MSG.EXOBIO_RANGE_READY`,
  - `MSG.EXOBIO_NEW_ENTRY`.
- READY distance gate:
  - fire-once per cykl,
  - retry po suppression (np. combat silence), bez utraty sygnalu.
- Progress 1/2/3:
  - dedup per `(system, body, species, sample_no)`,
  - po 3/3 blokada dalszych calloutow dla tego cyklu.
- Codex entry:
  - dedup per `(system, species)`.
- Rozszerzone quality gates:
  - `tests/test_f3_exobio_helper_progress.py`,
  - smoke: brak wild-emit w `exploration_bio_events.py`,
  - mapowanie `event_insight_mapping` rozszerzone o Exobio IDs.

Testy:
- `py -m unittest tests.test_f3_exobio_helper_progress -v` PASS
- `py -m unittest tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (51/51)
- `py tools/smoke_tests_journal.py` PASS (6/6)

---

### FLOW-F3-QUALITY-GATES-AND-SMOKE-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Dodac stale quality gates Fazy 3 (Exploration Awareness + DSS + Exobio).

Zakres:
- Test invariants:
  - mixed systems -> single summary,
  - first opportunity vs first confirmed,
  - DSS completion bez spamu,
  - Exobio READY/progress bez floodu,
  - combat silence dla DSS/Exobio.
- Rozszerzenie smoke backend/journal o scenariusze eksploracyjne F3.

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe gate'y F3 pod public release.
- PRO (PRO):
  - dodatkowe smoke voice-first/personalizacji (prywatny pipeline).

Commit routing:
- `[PUB]` dla testow i gate'ow wymaganych do FREE release.
- `[PRO]` dla dodatkowych gate'ow premium UX.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE.
- PRO: NIE WDROZONE (celowo, osobny prywatny pipeline smoke voice/personalizacji).

Pliki startowe:
- `tools/smoke_tests_beckendy.py`
- `tools/smoke_tests_journal.py`
- `tests/test_f3_*.py`
- `docs/Flow/private/docs/actions/PR_CHECKLIST.md`

Testy:
- automatyczne gate'y + manual sanity na realnych payloadach eksploracji.

Ryzyka:
- "zielone" testy jednostkowe bez pokrycia przeplywu cross-module F3.

DoD:
- Gate'y blokuja regresje F3 przed releasem.

Checklist PR-F3-5:
- [x] Dodane testy invariantow F3.
- [x] Dodane scenariusze cross-module (awareness -> dss -> exobio).
- [x] Update checklisty PR pod wymagania F3.
- [x] Smoke backend/journal PASS.

Wynik:
- Dodane stale gate'y F3:
  - `tests/test_f3_quality_gates_and_smoke.py`:
    - mixed systems -> single summary (cross-module),
    - combat silence gate dla DSS/Exobio non-critical.
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py`:
    - `test_f3_exploration_cross_module_invariants`.
- Rozszerzony smoke journal:
  - `tools/smoke_tests_journal.py`:
    - `test_journal_f3_exobio_progress_no_flood`.
- Zaktualizowana checklista PR:
  - `docs/Flow/private/docs/actions/PR_CHECKLIST.md`:
    - nowa sekcja `7.2 Faza 3 quality gates`.

Testy:
- `py -m unittest tests.test_f3_quality_gates_and_smoke -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (52/52)
- `py tools/smoke_tests_journal.py` PASS (7/7)

---

## Kolejnosc realizacji - FLOW Faza 3

1. FLOW-F3-EXPLORATION-AWARENESS-STACK-01
2. FLOW-F3-FIRST-STATUS-CONTRACT-01
3. FLOW-F3-DSS-HELPER-COMPLETION-01
4. FLOW-F3-EXOBIO-HELPER-PROGRESS-01
5. FLOW-F3-QUALITY-GATES-AND-SMOKE-01

Uwagi wykonawcze:
- Pracujemy w rytmie: ticket -> commit -> update md -> raport.
- Kazdy ticket zamykamy dopiero po smoke i aktualizacji `FLOW.md`.
- Przy zmianie zakresu Fazy 3 aktualizujemy tez `docs/Flow/private/ROADMAP.md`.

---

### PUB-PRO-ISOLATION-GATE-01 (P0)
Status: DONE (guard + docs release)

Cel:
- Zablokowac przypadkowe wypchniecie kodu private/PRO do public push lub public build.

Zakres:
- Dodany twardy guard CLI:
  - `tools/public_repo_guard.py`
  - sprawdza tracked files, staged additions i opcjonalnie zawartosc ZIP.
- Aktualizacja dokumentacji release:
  - `docs/RELEASE_CHECKLIST.md`
  - `docs/RELEASE_SANITY_CHECK.md`
  - `docs/README_TRANSFER.md`

DoD:
- Przed pushem/buildem istnieje jednoznaczny PASS/FAIL gate (`PUBLIC_GUARD`).
- Release checklist i sanity check wymagaja przejscia guarda.
- Public release workflow ma wpisany FREE-only warunek.

---

## FLOW Faza 4 - Summary, Cash-In, Survival (NOWE TICKETY)

### FLOW-F4-EXPLORATION-SUMMARY-BASE-01 (P0)
Status: DONE

Cel:
- Wdrozyc Exploration Summary (system/session/cash-in view) bez przeciazenia TTS.

Zakres:
- Widok summary dla systemu i sesji:
  - highlights,
  - "co dalej",
  - sygnaly pod cash-in.
- TTS:
  - 1 zdanie max,
  - reszta szczegolow do UI.
- Trigger:
  - manual + kontrolowane auto (tylko gdy zmienia swiadomosc).

Podzial FREE/PRO:
- FREE (PUB):
  - pelny summary engine i UI.
- PRO (PRO):
  - dodatkowe voice-first wejscie do tego samego summary.

Commit routing:
- `[PUB]` dla summary logiki i UX bazowego.
- `[PRO]` tylko dla premium warstwy interakcji.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `8ae0892`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Summary pokazuje highlights + next step bez floodu TTS.
- Brak lokalnych emitow poza dispatcherem.

Checklist PR-F4-1:
- [x] Runtime summary engine.
- [x] Insight contract + mapping + TTS microcopy.
- [x] UI summary cards.
- [x] Testy jednostkowe + smoke PASS.
- [x] Update `docs/Flow/private/FLOW.md` i `docs/Flow/private/ROADMAP.md`.

Raport wykonania:
- Dodano runtime F4 summary: `logic/events/exploration_summary.py` (system/session/cash-in, highlights + next step).
- Auto trigger przepiety pod pelny skan FSS przez dispatcher:
  - `logic/events/exploration_fss_events.py`
  - `logic/event_handler.py` (najpierw analiza scan -> potem gate FSS, aby summary widzialo biezace dane).
- Dodano manual trigger z UI (`Pulpit`):
  - `gui/tabs/pulpit.py` (button + summary card),
  - `gui/app.py` (queue wiring + callback).
- Dodano przekazywanie structured summary payload przez sciezke insight:
  - `logic/utils/notify.py` (`exploration_summary` msg_queue event).
- Dopracowano TTS microcopy dla `MSG.EXPLORATION_SYSTEM_SUMMARY`:
  - `logic/tts/text_preprocessor.py`.
- Testy:
  - `py -m unittest tests.test_f4_exploration_summary_base -v` PASS
  - `py -m unittest tests.test_event_insight_mapping tests.test_f3_quality_gates_and_smoke -v` PASS
  - `py tools/smoke_tests_beckendy.py` PASS (53/53)
  - `py tools/smoke_tests_journal.py` PASS (7/7)
  - `py -m compileall app gui logic tests tools` PASS

---

### FLOW-F4-CASH-IN-ASSISTANT-BASE-01 (P0)
Status: DONE

Cel:
- Wdrozyc Cash-In Assistant z decyzjami "rozwaz" zamiast "wracaj teraz".

Zakres:
- Decision space:
  - 2-3 opcje + `Pomijam`.
- Ocena opcji:
  - czas / zysk / ryzyko / trust-freshness.
- Komunikacja:
  - neutralna, bez presji i bez narzucania.

Podzial FREE/PRO:
- FREE (PUB):
  - pelny model opcji i trade-offow.
- PRO (PRO):
  - szybsza interakcja (STT/voice-first) do tych samych opcji.

Commit routing:
- `[PUB]` dla logiki decyzji i anti-spam.
- `[PRO]` dla premium kanalu wejscia.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `101bc22`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Cash-In nie wymusza jednej decyzji.
- `Pomijam` nie powoduje spamu powrotnego.

Checklist PR-F4-2:
- [x] Ranking opcji cash-in.
- [x] Decision cards + UX "Pomijam".
- [x] Dedup/cooldown pod cash-in callouts.
- [x] Testy + smoke PASS.
- [x] Update docs akcji/polityk.

Raport wykonania:
- Dodano runtime Cash-In Assistant: `logic/events/cash_in_assistant.py`.
  - decision space: 2-3 opcje + `Pomijam`,
  - scoring opcji po osiach: czas / zysk / ryzyko / trust-confidence,
  - neutralna komunikacja (bez wymuszania "wracaj teraz"),
  - dedup/cooldown dla auto callouts + suppress po `Pomijam` dla tego samego podpisu kontekstu.
- Podpiecie auto pod F4 summary:
  - `logic/events/exploration_summary.py` wywoluje cash-in assistant po zbudowaniu summary.
- Podpiecie do dispatcher contract:
  - `logic/event_insight_mapping.py` -> `MSG.CASH_IN_ASSISTANT` (`CASH_IN_REVIEW`, `cash_in_decision`).
- Podpiecie TTS i queue:
  - `logic/tts/text_preprocessor.py` (microcopy/fallback),
  - `logic/utils/notify.py` (kolejka `cash_in_assistant`).
- Podpiecie UI (Pulpit):
  - `gui/tabs/pulpit.py`:
    - karta Cash-In Assistant,
    - render opcji (2-3) i note,
    - UX `Pomijam cash-in` + pobieranie biezacego podpisu kontekstu.
  - `gui/app.py`:
    - queue wiring `cash_in_assistant`,
    - callbacki `on_generate_cash_in_assistant` i `on_skip_cash_in_assistant`.
- Stan aplikacji:
  - `app/state.py`: `last_cash_in_signature`, `cash_in_skip_signature`.
- Testy:
  - `tests/test_f4_cash_in_assistant_base.py` (NOWY) PASS
  - `tests/test_f4_exploration_summary_base.py` PASS
  - `tests/test_event_insight_mapping.py` PASS
  - `py tools/smoke_tests_beckendy.py` PASS (54/54)
  - `py tools/smoke_tests_journal.py` PASS (7/7)
  - `py -m compileall app gui logic tests tools` PASS

---

### FLOW-F4-SURVIVAL-REBUY-AWARENESS-BASE-01 (P0)
Status: DONE

Cel:
- Wdrozyc Survival/Rebuy Awareness dla stanow krytycznych i konsekwencji.

Zakres:
- Detekcja:
  - rebuy-at-risk,
  - utrata wartosci (data/cargo),
  - stany krytyczne hull/combat context.
- Komunikaty:
  - konsekwencje i opcje, bez alarmizmu.
- Priorytety:
  - P0/P1 zgodnie z policy, combat silence i dispatcher.

Podzial FREE/PRO:
- FREE (PUB):
  - pelna logika survival/rebuy awareness.
- PRO (PRO):
  - dodatkowe voice UX, bez zmiany semantyki ryzyka.

Commit routing:
- `[PUB]` dla risk/survival contracts.
- `[PRO]` dla komfortowej warstwy interakcji.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` - runtime survival/rebuy baseline + testy regresyjne).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Krytyczne stany wykrywane poprawnie.
- Brak false-alarm spam i brak tonow moralizujacych.

Checklist PR-F4-3:
- [x] Runtime detekcja rebuy/survival.
- [x] Insighty + priorytety + dedup.
- [x] Regresje pod combat silence.
- [x] Smoke PASS.
- [x] Update docs.

Wdrozone (FREE/PUB):
- runtime moduł `logic/events/survival_rebuy_awareness.py`:
  - detekcja `no_rebuy`, `rebuy_borderline`, `combat+hull`, `VaR data/cargo`,
  - sygnatury stanu + dedup anty-spam,
  - priorytety:
    - `MSG.SURVIVAL_REBUY_CRITICAL` (P0),
    - `MSG.SURVIVAL_REBUY_HIGH` (P1).
- integracja z routerem eventow:
  - `logic/event_handler.py`:
    - `on_status_update` -> survival/rebuy handler,
    - `handle_event` -> ingest danych credits/rebuy z journala.
- UI Pulpit:
  - karta "Survival / Rebuy Awareness" z kontekstem i opcjami.
- mapowanie i TTS:
  - `logic/event_insight_mapping.py`,
  - `logic/tts/text_preprocessor.py`,
  - `logic/utils/notify.py` (kolejka payloadu `survival_rebuy`).
- testy:
  - `tests/test_f4_survival_rebuy_awareness_base.py` PASS,
  - `tests/test_event_insight_mapping.py` PASS,
  - `py tools/smoke_tests_beckendy.py` PASS (55/55),
  - `py tools/smoke_tests_journal.py` PASS (7/7),
  - `py -m compileall app gui logic tests tools` PASS.

---

### FLOW-F4-CROSS-MODULE-VOICE-PRIORITY-01 (P1)
Status: DONE

Cel:
- Domknac konflikty glosu miedzy Summary/Cash-In/Survival.

Zakres:
- Deterministyczna kolejnosc emisji na styku akcji F4.
- Wspolne reguly:
  - anti-spam,
  - cooldown scopes,
  - threshold exceptions.
- Brak "walki" komunikatow o kanal TTS.

Podzial FREE/PRO:
- FREE (PUB):
  - wspolna orkiestracja i priorytety.
- PRO (PRO):
  - brak zmian semantyki; tylko dodatkowe wejscia interakcyjne.

Commit routing:
- `[PUB]` dla dispatcher arbitration.
- `[PRO]` tylko dla premium UX triggerow.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `15efd00`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Brak konfliktow glosu miedzy akcjami F4.
- Powtarzalny wybor komunikatu dla tych samych warunkow.

Checklist PR-F4-4:
- [x] Wspolne reguly kolejkowania F4.
- [x] Dedup na styku modulow.
- [x] Testy cross-module PASS.
- [x] Smoke PASS.

Wdrozenie (FREE/PUB):
- `logic/insight_dispatcher.py`:
  - dodany cross-module arbitration dla F4 (`Summary/Cash-In/Survival`),
  - okno priorytetowe `dispatcher.f4_voice_priority_window_sec` (domyslnie 12s),
  - nizszy/equal priorytet jest tlumiony po niedawnym wyzszym,
  - wyzszy priorytet moze preemptowac nizszy (deterministycznie),
  - P0 critical ma twardy priorytet i nie jest tlumiony przez F4 gate.
- Dodane runtime metadane do context:
  - `voice_priority_reason`,
  - `voice_priority_forced` (gdy preemption wymusza TTS).
- Dodane testy jednostkowe:
  - `tests/test_f4_cross_module_voice_priority.py`.
- Dodane smoke F4:
  - `tools/smoke_tests_beckendy.py::test_f4_cross_module_voice_priority_baseline`.

Testy:
- `py -m unittest tests.test_f4_cross_module_voice_priority tests.test_f4_exploration_summary_base tests.test_f4_cash_in_assistant_base tests.test_f4_survival_rebuy_awareness_base tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (56/56)
- `py tools/smoke_tests_journal.py` PASS (7/7)

---

### FLOW-F4-QUALITY-GATES-AND-SMOKE-01 (P1)
Status: DONE

Cel:
- Dodac stale quality gates F4 i zablokowac regresje przed releasem.

Zakres:
- Test invariants:
  - summary bez floodu,
  - cash-in 2-3 + `Pomijam`,
  - survival/rebuy trigger correctness,
  - cross-module priority correctness.
- Rozszerzenie smoke backend/journal pod scenariusze F4.

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe gate'y release FREE.
- PRO (PRO):
  - prywatne smoke premium voice UX.

Commit routing:
- `[PUB]` dla gate'ow F4.
- `[PRO]` dla dodatkowych testow premium.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `5ffeaad`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Regressions F4 blokowane przez stale testy i smoke.

Checklist PR-F4-5:
- [x] Testy jednostkowe F4.
- [x] Testy cross-module F4.
- [x] Smoke backend/journal PASS.
- [x] Update `PR_CHECKLIST.md` o quality gates F4.

Wdrozenie (FREE/PUB):
- Dodane stale gate'y F4:
  - `tests/test_f4_quality_gates_and_smoke.py`
    - summary auto non-flood + cash-in signature alignment,
    - cash-in decision space contract (2-3 opcje + `Pomijam`),
    - survival no-rebuy critical + dedup,
    - cross-module priority determinism.
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f4_quality_gates_invariants`
    - paczka invariantow F4 end-to-end.
- Rozszerzony smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f4_survival_no_rebuy_nonflood`
    - non-flood i poprawny reason/level przez sciezke journala.

Testy:
- `py -m unittest tests.test_f4_quality_gates_and_smoke tests.test_f4_cross_module_voice_priority tests.test_f4_exploration_summary_base tests.test_f4_cash_in_assistant_base tests.test_f4_survival_rebuy_awareness_base tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (57/57)
- `py tools/smoke_tests_journal.py` PASS (8/8)

---

### FLOW-F4-PRO-VOICE-UX-LAYER-01 (P2)
Status: TODO (DEFERRED - po domknieciu FREE/PUB F4)

Cel:
- Dodac tylko premium warstwe komfortu voice-first dla modulow F4.

Zakres:
- STT/voice-first wejscia do istniejacych decyzji F4.
- Brak zmian modelu decyzji i brak zmian quality insightow.

Podzial FREE/PRO:
- FREE: bez zmian semantycznych.
- PRO: tylko kanal interakcji.

Commit routing:
- `[PRO]` only.

Status wdrozenia (FREE/PRO):
- FREE: NIE DOTYCZY.
- PRO: NIE WDROZONE (deferred do czasu domkniecia FREE F4).

DoD:
- Zero przewagi gameplayowej.
- Pelna zgodnosc z `PRO_FEATURE_POLICY.md`.

---

## Kolejnosc realizacji - FLOW Faza 4

1. FLOW-F4-EXPLORATION-SUMMARY-BASE-01
2. FLOW-F4-CASH-IN-ASSISTANT-BASE-01
3. FLOW-F4-SURVIVAL-REBUY-AWARENESS-BASE-01
4. FLOW-F4-CROSS-MODULE-VOICE-PRIORITY-01
5. FLOW-F4-QUALITY-GATES-AND-SMOKE-01
6. FLOW-F4-PRO-VOICE-UX-LAYER-01 (po domknieciu FREE)

Uwagi wykonawcze:
- Pracujemy w rytmie: ticket -> commit -> update md -> raport.
- Najpierw domykamy 5 ticketow `[PUB]`, potem opcjonalny `[PRO]`.
- Kazdy ticket zamykamy dopiero po smoke i update `FLOW.md` + `ROADMAP.md`.

---

## FLOW Faza 5 - Combat awareness i domkniecie orkiestracji (NOWE TICKETY)

### FLOW-F5-COMBAT-AWARENESS-BASE-01 (P0)
Status: DONE

Cel:
- Wdrozyc Combat Awareness (wzorce ryzykownych sytuacji, bez taktyki).

Zakres:
- Wykrywanie powtarzalnych wzorcow ryzyka w walce:
  - presja na kadlub/oslony,
  - niekorzystne okna wycofania,
  - eskalacja zagrozenia po czasie.
- Komunikaty neutralne i konsekwencyjne:
  - bez moralizowania,
  - bez narzucania "jedynej decyzji".
- Integracja przez dispatcher (brak lokalnych emitow).

Podzial FREE/PRO:
- FREE (PUB):
  - pelna detekcja wzorcow i komunikaty awareness.
- PRO (PRO):
  - dodatkowy kanal interakcji (voice-first/STT), ta sama semantyka.

Commit routing:
- `[PUB]` dla logiki combat-awareness i kontraktow insightow.
- `[PRO]` tylko dla premium warstwy interakcji.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `917877a`).
- PRO: NIE WDROZONE (deferred na etap premium UX).

DoD:
- Combat Awareness komunikuje tylko wzorce, bez taktyki i bez moralizowania.

Checklist PR-F5-1:
- [x] Runtime `combat_awareness` + sygnatury stanu.
- [x] Kontrakt insight + mapowanie `event_insight_mapping`.
- [x] TTS microcopy zgodne z polityka neutralnosci.
- [x] Testy jednostkowe + smoke PASS.

Wdrozenie (FREE/PUB):
- `logic/events/combat_awareness.py`:
  - nowy runtime Combat Awareness (wzorce ryzyka, bez taktyki),
  - wykrywanie: krytyczny kadlub, oslony-down exposure, niestabilne okno wyjscia, high-stake exposure,
  - sygnatury stanu + dedup/cooldown + non-flood,
  - emisja wylacznie przez dispatcher (`emit_insight`), bez lokalnych "dzikich" emitow.
- `logic/event_handler.py`:
  - podpiecie Combat Awareness do `on_status_update` i `handle_event`.
- `logic/event_insight_mapping.py`:
  - dodane kontrakty `MSG.COMBAT_AWARENESS_HIGH` i `MSG.COMBAT_AWARENESS_CRITICAL`.
- `logic/utils/notify.py` + `logic/tts/text_preprocessor.py`:
  - wiring nowych message_id do TTS/notify pipeline.
- `app/state.py` + `config.py`:
  - runtime pole sygnatury + flaga `combat_awareness_enabled`.
- testy:
  - `tests/test_f5_combat_awareness_base.py`,
  - rozszerzony `tests/test_event_insight_mapping.py`,
  - smoke: `tools/smoke_tests_beckendy.py`, `tools/smoke_tests_journal.py`.

Testy:
- `py -m unittest tests.test_f5_combat_awareness_base tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (58/58)
- `py tools/smoke_tests_journal.py` PASS (9/9)

---

### FLOW-F5-DISPATCHER-PRIORITY-MATRIX-01 (P0)
Status: DONE

Cel:
- Domknac priorytety miedzy akcjami na bazie dispatcher-a.

Zakres:
- Jedna deterministyczna macierz priorytetow dla modulow:
  - Navigation / Exploration / F4 / Combat.
- Jasne reguly:
  - combat silence,
  - deduplikacja cross-module,
  - cooldowny globalne i per-klasa,
  - kontrolowana eskalacja P2 -> P1/P0.
- Brak "walki" o kanal TTS przy jednoczesnych sygnalach.

Podzial FREE/PRO:
- FREE (PUB):
  - wspolna macierz i arbitraz dla calej aplikacji.
- PRO (PRO):
  - bez zmian semantyki; tylko dodatkowe trigger entrypoints.

Commit routing:
- `[PUB]` dla dispatcher arbitration matrix.
- `[PRO]` tylko dla premium UX.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `7036620`).
- PRO: NIE WDROZONE.

DoD:
- Brak konfliktow glosu miedzy akcjami (deterministyczny wybor komunikatu).

Checklist PR-F5-2:
- [x] Spisana i zaimplementowana macierz priorytetow.
- [x] Regresje cross-module na jednoczesne zdarzenia.
- [x] Smoke backend/journal PASS.

Wdrozenie (FREE/PUB):
- `logic/insight_dispatcher.py`:
  - wdrozona deterministyczna macierz cross-module (Navigation / Exploration / F4 / Combat),
  - utrzymane i domkniete reguly preemption/suppression + combat silence,
  - dodana kontrolowana eskalacja priorytetu (P2 -> P1 -> P0) dla powtarzanych sygnalow ryzyka,
  - dodany per-class cooldown gate (konfigurowalny przez `dispatcher.class_cooldown.*`),
  - rozszerzone metadane telemetryczne: `module_class`, `base_priority`, `effective_priority`, `priority_escalation_reason`, `voice_priority_reason`.
- `config.py`:
  - nowe ustawienia dispatcher matrix/escalation/class cooldown.
- testy:
  - nowy unit: `tests/test_f5_dispatcher_priority_matrix.py`,
  - smoke baseline: `tools/smoke_tests_beckendy.py::test_f5_dispatcher_priority_matrix_baseline`.

Testy:
- `py -m unittest tests.test_f5_dispatcher_priority_matrix tests.test_f4_cross_module_voice_priority tests.test_f5_combat_awareness_base tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (59/59)
- `py tools/smoke_tests_journal.py` PASS (9/9)

---

### FLOW-F5-VOICE-POLICY-WHY-WHEN-CONTRACT-01 (P1)
Status: DONE

Cel:
- Domknac wspolna logike "co, kiedy i dlaczego Renata mowi".

Zakres:
- Ujednolicenie kontraktu:
  - `message_id -> intent/kategoria -> warunki emisji`,
  - jasny `gate_reason` i telemetry context.
- Rozdzial semantyki vs stylu:
  - semantyka (czy mowic) niezalezna od wariantow tekstu.
- Spojnosc z:
  - `renata_mowa_logika_cooldown_detailed.md`,
  - `EXCEPTIONS_FLOW.md`,
  - `UX_TTS_POLICY.md`.

Podzial FREE/PRO:
- FREE (PUB):
  - wspolny kontrakt i reguly emisji.
- PRO (PRO):
  - profile komfortu/voice-first bez zmiany semantyki.

Commit routing:
- `[PUB]` dla policy contract.
- `[PRO]` tylko dla premium profili stylu.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `e19c8b3`).
- PRO: NIE WDROZONE.

DoD:
- Wspolna logika emisji jest jednoznaczna i audytowalna.

Checklist PR-F5-3:
- [x] Ujednolicenie kontraktow TTS intent/category.
- [x] Spojne `gate_reason` we wszystkich krytycznych modulach.
- [x] Update docs policy (private/public) + smoke PASS.

Wdrozenie (FREE/PUB):
- `logic/event_insight_mapping.py`:
  - dodany wspolny kontrakt TTS (`TTSPolicySpec` + `TTS_POLICY_BY_MESSAGE_ID`),
  - mapowanie `message_id -> tts_intent/tts_category/tts_cooldown_policy`,
  - `resolve_emit_contract` dopina policy metadata do runtime context.
- `logic/utils/notify.py`:
  - usunieta duplikacja lokalnych map intent/category,
  - notify korzysta z jednego kontraktu policy z event mappingu,
  - wdrozone `cooldown_policy` (`NORMAL`, `BYPASS_GLOBAL`, `ALWAYS_SAY`) w runtime gate.
- telemetry:
  - context emitow ma spójne pola policy (`tts_intent`, `tts_category`, `tts_cooldown_policy`),
  - zachowane audytowalne reason codes (`gate_reason`, `voice_priority_reason`).
- docs (public):
  - `docs/Flow/public/docs/ux/UX_TTS_POLICY.md` rozszerzony o runtime contract i telemetry.
- testy:
  - nowy unit `tests/test_f5_voice_policy_contract.py`,
  - smoke baseline `tools/smoke_tests_beckendy.py::test_f5_voice_policy_contract_baseline`.

Testy:
- `py -m unittest tests.test_f5_voice_policy_contract tests.test_f5_dispatcher_priority_matrix tests.test_f4_cross_module_voice_priority tests.test_f5_combat_awareness_base tests.test_event_insight_mapping -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (60/60)
- `py tools/smoke_tests_journal.py` PASS (9/9)

---

### FLOW-F5-ANTI-SPAM-REGRESSION-01 (P1)
Status: DONE

Cel:
- Zabezpieczyc brak regresji anti-spam po wlaczeniu combat-aware flow.

Zakres:
- Testy regresyjne na:
  - burst eventow combat,
  - przejscia combat <-> non-combat,
  - powtarzalne sygnatury i edge cooldown.
- Walidacja, ze wyjatki (READY/progi) nie flooduja i nie gubia krytycznych sygnalow.

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe regresje anti-spam.
- PRO (PRO):
  - dodatkowe regresje premium UX (private pipeline).

Commit routing:
- `[PUB]` dla gate'ow anty-regresyjnych.
- `[PRO]` dla dodatkowych gate'ow premium.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `TBD`).
- PRO: NIE WDROZONE.

DoD:
- Brak regresji anti-spam po wlaczeniu combat-aware flow.

Checklist PR-F5-4:
- [x] Test pack anti-spam (unit + integration).
- [x] Regresje dla wyjatkow cooldown (READY/progi/fuel).
- [x] Smoke PASS.

Wdrozenie (FREE/PUB):
- Dodano nowy pakiet unit regresji:
  - `tests/test_f5_anti_spam_regression.py`
    - burst combat signature non-flood,
    - READY recovery po combat silence + edge cooldown,
    - FSS threshold BYPASS_GLOBAL + anti-spam entity,
    - fuel critical not lost during combat burst.
- Rozszerzono smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f5_anti_spam_regression_baseline`
  - dodany do smoke pack coverage i runnera.
- Rozszerzono smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f5_anti_spam_transitions_and_exceptions`
  - scenariusz przez `event_handler` (combat transition + READY + fuel non-flood).
- Dodano reset runtime stanu dispatchera w smoke journal dla izolacji regresji
  (`reset_dispatcher_runtime_state`).

Testy:
- `py -m unittest tests.test_f5_anti_spam_regression -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (61/61)
- `py tools/smoke_tests_journal.py` PASS (10/10)

---

### FLOW-F5-QUALITY-GATES-AND-SMOKE-01 (P1)
Status: DONE

Cel:
- Dodac stale quality gates F5 i zablokowac regresje przed releasem.

Zakres:
- Test invariants F5:
  - combat awareness pattern-only (bez taktyki),
  - dispatcher priority determinism,
  - anti-spam stability w combat i poza combat,
  - brak konfliktow z F4 summary/cash-in/survival.
- Rozszerzenie smoke backend/journal o scenariusze F5.

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe gate'y pod release FREE.
- PRO (PRO):
  - prywatne smoke premium voice UX.

Commit routing:
- `[PUB]` dla gate'ow F5.
- `[PRO]` dla dodatkowych testow premium.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]` commit `f5f759f`).
- PRO: NIE WDROZONE.

DoD:
- Gate'y blokuja regresje F5 przed releasem.

Checklist PR-F5-5:
- [x] Testy jednostkowe F5.
- [x] Testy cross-module F5.
- [x] Smoke backend/journal PASS.
- [x] Update `PR_CHECKLIST.md` o quality gates F5.

Wdrozenie (FREE/PUB):
- Dodano nowy pakiet quality gate:
  - `tests/test_f5_quality_gates_and_smoke.py`
    - pattern-only i neutralnosc Combat Awareness,
    - determinizm matrix F4/F5,
    - stabilnosc anti-spam combat/non-combat,
    - brak konfliktu `survival` vs `combat critical`.
- Rozszerzono smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f5_quality_gates_invariants`
  - dodany do stalego runnera smoke.
- Rozszerzono smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f5_quality_gates_cross_module_nonflood`
  - scenariusz cross-module non-flood przez `event_handler`.
- Rozszerzono checklisty PR:
  - `docs/Flow/private/docs/actions/PR_CHECKLIST.md` sekcja `7.3 Faza 5 quality gates`.

Testy:
- `py -m unittest tests.test_f5_quality_gates_and_smoke -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (62/62)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F5-PRO-VOICE-UX-LAYER-01 (P2)
Status: TODO (DEFERRED - po domknieciu FREE/PUB F5)
Typ ticketu: WYLACZNIE PRO (private, bez wdrozenia do FREE/PUB).

Cel:
- Dodac tylko premium warstwe komfortu voice-first dla modulow F5.

Zakres:
- STT/voice-first wejscia do istniejacych decyzji F5.
- Brak zmian modelu ryzyka i brak zmian quality insightow.

Podzial FREE/PRO:
- FREE: bez zmian semantycznych.
- PRO: tylko kanal interakcji.

Commit routing:
- `[PRO]` only.
- `[PUB]` zabronione dla tego ticketu.

Status wdrozenia (FREE/PRO):
- FREE: NIE DOTYCZY.
- PRO: NIE WDROZONE.

DoD:
- Zero przewagi gameplayowej.
- Pelna zgodnosc z `PRO_FEATURE_POLICY.md`.

Wdrozenie (PRO/private):
- Deferred do etapu premium UX po domknieciu FREE F5.

---

## Kolejnosc realizacji - FLOW Faza 5

1. FLOW-F5-COMBAT-AWARENESS-BASE-01
2. FLOW-F5-DISPATCHER-PRIORITY-MATRIX-01
3. FLOW-F5-VOICE-POLICY-WHY-WHEN-CONTRACT-01
4. FLOW-F5-ANTI-SPAM-REGRESSION-01
5. FLOW-F5-QUALITY-GATES-AND-SMOKE-01
6. FLOW-F5-PRO-VOICE-UX-LAYER-01 (po domknieciu FREE)

Uwagi wykonawcze:
- Pracujemy w rytmie: ticket -> commit -> update md -> raport.
- Najpierw domykamy 5 ticketow `[PUB]`, potem opcjonalny `[PRO]`.
- Kazdy ticket zamykamy dopiero po smoke i update `FLOW.md` + `ROADMAP.md`.

---

## FLOW Faza 6 - Granice PRO i hardening wydaniowy (NOWE TICKETY)

Cel F6:
- domknac granice FREE vs PRO bez przeciekow,
- utwardzic release FREE,
- zsynchronizowac finalnie docs private/public.

### FLOW-F6-FREE-PRO-CAPABILITY-AUDIT-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Zweryfikowac i udokumentowac granice capabilities FREE/PRO.

Zakres:
- Audyt capability usage w runtime:
  - brak plan-checkow w logice akcji,
  - brak roznic semantyki insightow miedzy FREE i PRO.
- Audyt entrypointow PRO:
  - STT/voice-first tylko jako kanal interakcji,
  - brak "better analysis" i brak ukrytych bonusow.
- Dopiac stale testy i smoke profile `FREE`/`PRO`.

Podzial FREE/PRO:
- FREE (PUB):
  - testy i guardy potwierdzajace brak zaleznosci od PRO.
- PRO (PRO):
  - walidacja private capability map i premium entrypoints.

Commit routing:
- `[PUB]` dla audytu i gate'ow FREE.
- `[PRO]` dla private capability map/details.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Audyt capabilities potwierdza zgodnosc Free/Pro z polityka.
- Testy kontraktowe FREE/PRO przechodza bez regressji.

Checklist PR-F6-1:
- [x] Capability audit report (FREE/PRO).
- [x] Testy runtime capability profile PASS.
- [x] Smoke FREE/PRO PASS.
- [x] Brak plan-checkow w action modules.

Wdrozenie (FREE/PUB):
- `config.py`:
  - domyslny profil runtime ustawiony na `FREE`,
  - domyslne capabilities premium ustawione na `False`:
    - `capabilities.ui_extended_tabs`,
    - `capabilities.settings_full`,
    - `capabilities.tts_advanced_policy`,
    - `capabilities.voice_stt` (bez zmian: `False`).
- Dodany quality gate F6:
  - `tests/test_f6_free_pro_capability_audit.py`
    - domyslny kontrakt `DEFAULT_SETTINGS -> PROFILE_FREE`,
    - brak plan/capability checkow w `logic/events/*`,
    - niezmiennosc kontraktu emit (`resolve_emit_contract`) miedzy FREE/PRO,
    - runtime capability patch smoke (FREE/PRO).
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_default_profile_contract_is_free_pub`.

Wynik audytu:
- Plan-checki (`plan.profile`, `features.tts.free_policy_enabled`) pozostaja
  wylacznie w warstwie capability (`logic/capabilities.py`), poza modulami akcji.
- Moduly akcji (`logic/events/*`) nie sa sprzezone z planem FREE/PRO.
- Bramka STT pozostaje kanalowa (`logic/utils/notify.py`) i nie zmienia semantyki insightow.

Testy:
- `py -m unittest tests.test_f6_free_pro_capability_audit -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F6-VOICE-ETHICS-COMPLIANCE-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Potwierdzic zgodnosc implementacji glosu z polityka i etyka produktu.

Zakres:
- Audyt message_id/intent/category/cooldown_policy.
- Walidacja wyjatkow cooldown (READY/progi/fuel) pod anti-spam i combat silence.
- Walidacja tonu:
  - brak moralizowania,
  - brak wymuszania "top 1",
  - neutralny, informacyjny styl.

Podzial FREE/PRO:
- FREE (PUB):
  - wspolna semantyka emisji i kontrakt TTS.
- PRO (PRO):
  - dodatkowe profile komfortu bez zmiany semantyki.

Commit routing:
- `[PUB]` dla policy compliance i testow.
- `[PRO]` dla premium profili UX (jesli dotyczy).

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Implementacja glosu zgodna z polityka voice i etyka produktu.
- Brak regressji anti-spam/combat silence po audycie.

Checklist PR-F6-2:
- [x] Policy audit report.
- [x] Regresje TTS/dispatcher PASS.
- [x] Potwierdzenie zgodnosci z `EXCEPTIONS_FLOW.md` i `UX_TTS_POLICY.md`.

Wdrozenie (FREE/PUB):
- Dodany quality gate F6:
  - `tests/test_f6_voice_ethics_compliance.py`
    - audyt policy exception matrix (`message_id -> intent/category/cooldown_policy`),
    - audyt runtime kontraktu `resolve_emit_contract` (metadata policy w context),
    - walidacja wyjatkow cooldown (`BYPASS_GLOBAL` / `ALWAYS_SAY`) z zachowaniem anti-spam,
    - walidacja invariants combat silence (non-critical blokowany, critical niegubiony),
    - walidacja tonu (neutralny, informacyjny, bez wymuszania "top 1").
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f6_voice_ethics_compliance_baseline`
  - dodany do stalego runnera smoke.

Wynik audytu:
- Wyjatki cooldown dla FREE sa zgodne z polityka:
  - `MSG.EXOBIO_SAMPLE_LOGGED` -> `ALWAYS_SAY`,
  - `MSG.EXOBIO_RANGE_READY` + FSS thresholds (`25/50/75`, `LAST_BODY`, `FULLY_SCANNED`) -> `BYPASS_GLOBAL`,
  - `MSG.FUEL_CRITICAL` -> `ALWAYS_SAY`.
- Dispatcher utrzymuje anti-spam/combat silence:
  - `READY` blokowany w combat silence i odzyskiwany po wyjsciu z walki,
  - cooldown entity nadal blokuje flood dla wyjatkow cooldown.
- Tone-of-voice pozostaje neutralny i informacyjny (bez moralizowania i bez narzucania decyzji).
- Publiczny policy baseline zweryfikowany na `UX_TTS_POLICY.md`;
  `EXCEPTIONS_FLOW.md` nie wystepuje w aktualnym drzewie public docs, dlatego
  audyt wyjatkow oparto o runtime policy contract + smoke invariants.

Testy:
- `py -m unittest tests.test_f6_voice_ethics_compliance tests.test_f6_free_pro_capability_audit -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (64/64)
- `py tools/smoke_tests_journal.py` PASS (11/11)
- `py tools/public_repo_guard.py` PASS

---

### FLOW-F6-DOCS-PRIVATE-PUBLIC-SYNC-01 (P0)
Status: DONE (docs sync + cleanup)

Cel:
- Domknac finalna synchronizacje dokumentacji private/public.

Zakres:
- Porownanie zakresu i nazw:
  - `docs/Flow/private/FLOW.md`,
  - `docs/Flow/public/FLOW.md`,
  - `docs/Flow/public/README.md`.
- Usuniecie przeciekow private/pro z docs public.
- Ujednolicenie statusu faz i mapowania ticket -> roadmapa.

Podzial FREE/PRO:
- FREE (PUB):
  - finalne docs public gotowe do release.
- PRO (PRO):
  - private docs rozszerzone o premium backlog i deferred scope.

Commit routing:
- `[PUB]` dla zmian docs public/FREE.
- `[PRO]` dla private premium details.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Public i private docs sa zsynchronizowane na poziomie zakresu i nazw.
- Public docs nie zawieraja tresci private/pro.

Checklist PR-F6-3:
- [x] Diff docs private/public sprawdzony.
- [x] Public docs clean (no private leaks).
- [x] Flow/roadmap status finalnie zgodny.

Wdrozenie (FREE/PUB):
- `docs/Flow/public/FLOW.md`:
  - dodany aktualny snapshot faz FREE/PUB (stan na 2026-02-15),
  - rozszerzony high-level zakres funkcji o Exploration/Summary/Cash-In/Survival/Combat.
- `docs/Flow/public/README.md`:
  - dodany aktualny status faz FREE/PUB.
- `docs/Flow/public/docs/REFAKTOR_STATUS.md`:
  - zaktualizowany status faz i opis "co zrobiono / co dalej" pod F6.
- `docs/Flow/public/docs/actions/README.md`:
  - zakres public actions zsynchronizowany z aktualnym modelem FREE/PUB.

Wynik audytu docs:
- Public docs nie linkuja do dokumentacji private.
- Public docs nie zawieraja heurystyk/progow/checklist operacyjnych.
- Nazewnictwo i status faz sa zgodne z aktualnym snapshotem F6.

Walidacja:
- `rg -n "private|LAST_TICKET|ROADMAP|EXCEPTIONS_FLOW" docs/Flow/public` -> brak przeciekow linkow private.

---

### FLOW-F6-RELEASE-HARDENING-AND-SMOKE-01 (P0)
Status: DONE (smoke + public guard + sanity)

Cel:
- Utwardzic finalny proces release FREE.

Zakres:
- Stale gate'y release:
  - `tools/public_repo_guard.py` (repo + ZIP),
  - smoke backend/journal,
  - sanity/release checklist PASS.
- Finalny smoke krytycznych flow:
  - nawigacja,
  - eksploracja (F3/F4),
  - combat awareness (F5),
  - trade/sell assist.
- Weryfikacja artefaktow build (FREE only).

Podzial FREE/PRO:
- FREE (PUB):
  - obowiazkowe release gates i smoke.
- PRO (PRO):
  - osobny private pipeline build/test (bez publikacji).

Commit routing:
- `[PUB]` dla release gates FREE.
- `[PRO]` dla private pipeline PRO.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE WDROZONE.

DoD:
- Smoke scenariusze dla krytycznych flow przechodza po domknieciu faz.
- Build FREE nie zawiera kodu/sciezek PRO.

Checklist PR-F6-4:
- [x] `public_repo_guard` PASS (repo + zip).
- [x] backend smoke PASS.
- [x] journal smoke PASS.
- [x] release/sanity checklist PASS.

Wdrozenie (FREE/PUB):
- Bramka publiczna:
  - `py tools/public_repo_guard.py` -> `PUBLIC_GUARD=PASS`.
  - `py tools/public_repo_guard.py --zip "release\\Renata_v0.9.4-preview_win_x64.zip"` -> `PUBLIC_GUARD=PASS`.
- Smoke:
  - `py tools/smoke_tests_beckendy.py` PASS (65/65).
  - `py tools/smoke_tests_journal.py` PASS (11/11).
- Sanity release ZIP:
  - szybka walidacja zawartosci ZIP (brak `docs/internal`, `docs/Flow/private`, `pro`, runtime/user files) -> `ZIP_SANITY=PASS`.

Wynik:
- Finalny gate FREE dla F6 jest domkniety.
- Build/artefakty FREE pozostaja izolowane od sciezek private/PRO.

---

### FLOW-F6-PRO-PREMIUM-LAYER-CLOSURE-01 (P2)
Status: TODO (DEFERRED - private only)
Typ ticketu: WYLACZNIE PRO (private, bez wdrozenia do FREE/PUB).

Cel:
- Domknac deferred premium warstwy komfortu po stronie private.

Zakres:
- Dopiac:
  - `FLOW-F4-PRO-VOICE-UX-LAYER-01`,
  - `FLOW-F5-PRO-VOICE-UX-LAYER-01`.
- Potwierdzic, ze zmiany sa tylko UX/channel:
  - bez zmiany semantyki insightow,
  - bez przewagi gameplayowej.

Podzial FREE/PRO:
- FREE: NIE DOTYCZY.
- PRO: private premium UX only.

Commit routing:
- `[PRO]` only.
- `[PUB]` zabronione dla tego ticketu.

Status wdrozenia (FREE/PRO):
- FREE: NIE DOTYCZY.
- PRO: NIE WDROZONE.

DoD:
- Premium UX dziala prywatnie i nie zmienia logiki FREE.
- Zgodnosc z `PRO_FEATURE_POLICY.md`.

Checklist PR-F6-5:
- [ ] Private testy premium PASS.
- [ ] Brak zmian semantyki insightow.
- [ ] Brak przecieku do public branch/build.

---

## Kolejnosc realizacji - FLOW Faza 6

1. FLOW-F6-FREE-PRO-CAPABILITY-AUDIT-01
2. FLOW-F6-VOICE-ETHICS-COMPLIANCE-01 (DONE)
3. FLOW-F6-DOCS-PRIVATE-PUBLIC-SYNC-01 (DONE)
4. FLOW-F6-RELEASE-HARDENING-AND-SMOKE-01 (DONE)
5. FLOW-F6-PRO-PREMIUM-LAYER-CLOSURE-01 (private, po domknieciu FREE)

Uwagi wykonawcze:
- Cztery tickety `[PUB]` dla F6 sa domkniete (FREE gate zakonczony).
- Pozostaje opcjonalne domkniecie tylko private `[PRO]`.
- Rytm pracy bez zmian: ticket -> commit -> update md -> raport.

---

## NOWE TICKETY (FLOW Faza 7 - Refaktor GUI, priorytet: `docs/internal/Refaktor_GUI`)

Zrodla nadrzedne dla tej paczki:
- `docs/internal/Refaktor_GUI/UI_DASHBOARD_SPEC_v2.md`
- `docs/internal/Refaktor_GUI/WIDGET_TEXTS_SPEC.md`
- `docs/internal/Refaktor_GUI/UI_CONSOLE_INTERACTION_MODEL.md`
- `docs/internal/Refaktor_GUI/UI_MODE_SYSTEM_SPEC.md`
- `docs/internal/Refaktor_GUI/MODE_DETECTOR_RULESET.md`
- `docs/internal/Refaktor_GUI/MODE_TTL_POLICY.md`

### FLOW-F7-DASHBOARD-WIDGET-STRIP-BASE-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Wdrozyc docelowy dashboard Pulpitu (lekki status + widget strip), bez mnozenia kart.

Zakres:
- Layout wg `UI_DASHBOARD_SPEC_v2.md`:
  - Header (2 linie, status z MODE),
  - Mini status bar,
  - Widget strip,
  - Tool bar,
  - Console area (panel + log).
- Kontrakt widgetow wg `WIDGET_TEXTS_SPEC.md`:
  - stale: `MODE`, `RISK`, `CASH`, `ROUTE`,
  - kontekstowe: `SUM/FSS/EXO/MIN/TRD/XENO`.
- Brak nowych typow `MSG_QUEUE` (korzystamy z obecnych payloadow).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Dashboard nie jest przepelniony na 1080p i mniejszych oknach.
- Widoczne max 6-7 widgetow jednoczesnie.
- Widgety sa jednowierszowe i nie zawieraja list/decyzji inline.

Wynik:
- `gui/tabs/pulpit.py`:
  - przebudowa ukladu do modelu dashboard:
    - Header,
    - Mini status bar,
    - Widget strip (`MODE`, `RISK`, `CASH`, `ROUTE` + kontekstowe),
    - kompaktowy toolbar,
    - Console area z placeholderem panelu interakcji + log runtime.
  - usuniete duze karty F4 inline; payloady `exploration_summary`, `cash_in_assistant`,
    `survival_rebuy` mapuja sie na widgety.
  - dodane mapowanie `combat_awareness -> RISK`, zeby widget `RISK` uwzglednial takze combat.
- `gui/app.py`:
  - dopieta obsluga `msg_type == "combat_awareness"` w `check_queue()`
    do aktualizacji widgetu `RISK` na Pulpicie.

Testy:
- `py -m compileall gui/tabs/pulpit.py gui/app.py` PASS
- `py tools/smoke_tests_beckendy.py` PASS (64/64)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F7-CONSOLE-INTERACTION-SINGLE-SLOT-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Zrobic z konsoli centrum decyzji przez Single Panel Slot.

Zakres:
- Wdrozenie panelu wg `UI_CONSOLE_INTERACTION_MODEL.md`:
  - panel opcjonalny nad logiem,
  - max 30% wysokosci konsoli,
  - tryby: `Loading`, `Data`, `Confirm`, `Info-only`,
  - max 4 przyciski.
- Single slot policy:
  - klik widgetu/przycisku zastępuje panel,
  - payload tej samej domeny aktualizuje panel,
  - payload innej domeny aktualizuje tylko widget,
  - P0 alert moze nadpisac panel.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Brak stackowania historii paneli.
- Log runtime zawsze widoczny.
- Panel nie rozpycha layoutu Pulpitu.

Wynik:
- `gui/tabs/pulpit.py`:
  - odtworzona i przebudowana zakladka Pulpit z realnym panelem interakcji nad logiem,
  - wdrozony `Single Panel Slot`:
    - klik widgetu/przycisku zawsze zastępuje aktywny panel,
    - payload tej samej domeny odswieza otwarty panel,
    - payload innej domeny aktualizuje tylko widget,
    - alert `P0` (`RISK_CRITICAL`/`level=critical`) moze nadpisac panel,
  - panel ma tryby `Loading`, `Data`, `Confirm`, `Info-only`,
  - limit akcji panelu do max 4 przyciskow,
  - stale kontrolki panelu: `Zwin` / `Zamknij`,
  - wysokosc panelu ograniczona do max 30% wysokosci konsoli, log runtime zostaje stale widoczny.
- Zachowana kompatybilnosc API Pulpitu uzywanego przez `gui/app.py`:
  - `get_current_exploration_summary_payload`,
  - `get_current_cash_in_signature`,
  - `update_exploration_summary`, `update_cash_in_assistant`, `update_survival_rebuy`, `update_combat_awareness`.

Testy:
- `py -m compileall gui/tabs/pulpit.py gui/app.py` PASS
- `py tools/smoke_tests_beckendy.py` PASS (64/64)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F7-MODE-STATE-AUTO-DETECTOR-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Wdrozyc spojny system trybow AUTO dla GUI/TTS/overlay.

Zakres:
- `ModeState` wg `UI_MODE_SYSTEM_SPEC.md`:
  - `mode_id`, `mode_source`, `mode_confidence`, `mode_since`, `mode_ttl`.
- Priorytety AUTO wg `MODE_DETECTOR_RULESET.md`:
  - `COMBAT > DOCKED > EXPLORATION > MINING > NORMAL`.
- Integracja sygnalow z `Status.json`, Journal i runtime payloadow.
- Aktualizacja `Header Status` i widgetu `MODE`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Scenariusze AUTO przechodza: Docked, Undocked, FSS, Combat, Mining.
- Konflikty trybow rozstrzygane sa zawsze po priorytecie.
- Tryb jest wspolnym zrodlem prawdy dla dashboardu i overlay.

Wynik:
- `app/state.py`:
  - dodany centralny `ModeState`:
    - `mode_id`, `mode_source`, `mode_confidence`, `mode_since`, `mode_ttl`,
  - wdrozony AUTO detector z priorytetem:
    - `COMBAT > DOCKED > EXPLORATION > MINING > NORMAL`,
  - integracja sygnalow:
    - Status.json (`Docked`, `Flags`, `GuiFocus`, ring hints),
    - Journal (`Docked`, `Undocked`, eventy combat/exploration/mining, `Loadout`),
    - runtime payloady (`exploration_summary`, `survival_rebuy`, `combat_awareness`, `ship_state`),
  - publikacja snapshotu trybu do kolejki GUI: `MSG_QUEUE -> ("mode_state", snapshot)`.
- `logic/event_handler.py`:
  - dopiete przekazywanie sygnalow do mode detectora:
    - `on_status_update -> app_state.update_mode_signal_from_status(...)`,
    - `handle_event -> app_state.update_mode_signal_from_journal(...)`.
- `gui/app.py`:
  - `check_queue()` obsluguje `msg_type == "mode_state"` i aktualizuje:
    - Pulpit (`apply_mode_state`),
    - overlay (`_overlay_update_mode`),
  - runtime payloady aktualizuja detector trybu:
    - `exploration_summary`, `survival_rebuy`, `combat_awareness`, `ship_state`,
  - dodany tick `app_state.refresh_mode_state(source="queue.tick")`,
  - overlay dostal dedykowana etykiete `MODE: ...`.
- `gui/tabs/pulpit.py`:
  - dodane `apply_mode_state(...)`,
  - widget `MODE` + header status aktualizowane ze snapshotu centralnego `ModeState`,
  - usuniete lokalne wymuszanie `COMBAT` z widgetu `RISK` (single source of truth = `app_state`).
- Testy:
  - nowy test kontraktowy:
    - `tests/test_f7_mode_state_auto_detector.py`
      - Docked/Undocked,
      - FSS -> EXPLORATION,
      - Combat ma priorytet nad Docked,
      - Mining z loadout+ring,
      - priorytet EXPLORATION nad MINING.

Testy:
- `py -m compileall app/state.py logic/event_handler.py gui/app.py gui/tabs/pulpit.py tests/test_f7_mode_state_auto_detector.py` PASS
- `py -m unittest tests.test_f7_mode_state_auto_detector -v` PASS
- `py -m unittest tests.test_route_awareness_state -v` PASS
- `py -m unittest tests.test_gui_status_helpers -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (64/64)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F7-MODE-TTL-POLICY-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Ustabilizowac tryby przez TTL, bez "skakania" UI/TTS.

Zakres:
- TTL wg `MODE_TTL_POLICY.md`:
  - `COMBAT=45s`,
  - `EXPLORATION=120s`,
  - `MINING=90s`,
  - `DOCKED` bez TTL.
- Reset TTL na sygnal, wygaszanie po timeout.
- TTL konfigurowalny w `config` (MVP: wartosci domyslne + override).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Brak migania trybow przy chwilowych przerwach sygnalu.
- COMBAT wchodzi natychmiast i wygasa dopiero po TTL.
- Testy TTL dla COMBAT/EXPLORATION/MINING PASS.

Wynik:
- TTL mode policy wdrozona w `app/state.py`:
  - `COMBAT=45s`,
  - `EXPLORATION=120s`,
  - `MINING=90s`,
  - `DOCKED` bez TTL.
- Dodany quality gate:
  - `tests/test_f7_mode_ttl_policy.py`.

Testy:
- `py -m unittest tests.test_f7_mode_ttl_policy -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F7-MODE-MANUAL-OVERRIDE-AND-SAFETY-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Dodac manualny wybor trybu, bez utraty bezpieczenstwa.

Zakres:
- Panel `Tryby` (konsola) i manual override (`mode_source=MANUAL`).
- AUTO nie nadpisuje MANUAL, poza safety overlay dla COMBAT.
- Safety overlay moze narzucic combat-silence bez zmiany manual `mode_id`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Manual mode trzyma sie stabilnie do czasu zmiany przez usera.
- Safety overlay COMBAT dziala bez regresji anti-spam.
- UX panelu trybow jest spojny z widgetem `MODE`.

Wynik:
- `app/state.py`:
  - dodane API manual mode:
    - `set_mode_manual(...)`,
    - `set_mode_auto(...)`,
  - AUTO detector respektuje `mode_source=MANUAL` i nie nadpisuje `mode_id`,
  - dodany safety overlay:
    - `mode_overlay="COMBAT"` gdy AUTO wykrywa combat podczas MANUAL,
    - `mode_combat_silence=True` przy aktywnym safety overlay.
- `logic/insight_dispatcher.py`:
  - combat silence uwzglednia safety overlay z `ModeState`,
    bez wymuszania zmiany manual `mode_id`.
- `gui/tabs/pulpit.py`:
  - panel `MODE` ma akcje:
    - `AUTO`,
    - `MAN EXPL`,
    - `MAN MINING`,
    - `MAN COMBAT`,
  - widget/header/overlay pokazuja stan safety (`SAFE COMBAT`) gdy overlay aktywny.
- `gui/app.py`:
  - overlay `MODE` aktualizowany o source (`MAN`) i safety tag.
- Dodany quality gate:
  - `tests/test_f7_mode_manual_override_and_safety.py`
    - manual lock nie jest nadpisywany przez AUTO,
    - safety COMBAT overlay dziala bez zmiany manual `mode_id`,
    - po wygaszeniu sygnalu COMBAT overlay znika,
    - `set_mode_auto()` zwalnia manual lock,
    - dispatcher respektuje combat silence z safety overlay.

Testy:
- `py -m unittest tests.test_f7_mode_state_auto_detector tests.test_f7_mode_ttl_policy tests.test_f7_mode_manual_override_and_safety tests.test_f5_anti_spam_regression tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F7-RISK-REBUY-WIDGET-CONTRACT-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Ujednolicic kontrakt `RISK` w dashboardzie na jezyk decyzji gracza.

Zakres:
- Kontrakt tekstu widgetu wg `WIDGET_TEXTS_SPEC.md`:
  - `RISK: LOW | Rebuy OK`
  - `RISK: MED | Rebuy OK`
  - `RISK: HIGH | Rebuy OK`
  - `RISK: HIGH | REBUY LOW`
  - `RISK: CRIT | NO REBUY`
- Progi wartosci (feedback gameplay):
  - `LOW`: explo >= 50M lub exobio >= 100M,
  - `MED`: explo >= 100M lub exobio >= 250M,
  - `HIGH`: explo >= 150M lub exobio >= 500M,
  - `VERY_HIGH`: explo >= 200M lub exobio >= 750M,
  - `CRITICAL`: explo >= 250M lub exobio >= 1B.
- Warunki rebuy:
  - `NO REBUY` gdy `credits < rebuy_cost`,
  - `REBUY LOW` gdy `credits < 1.2 * rebuy_cost`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Mapa poziomow i etykiet RISK/REBUY jest deterministyczna.
- `NO REBUY` zawsze daje stan krytyczny.
- Brak regresji flow F4/F5.
- Możliwość zmiany progów w konfiguracji, na wzór "progi jackpotów". Zmieścić wszystko w jednym oknie zrobić podział na explo i exobio 2 tabele ze zmianą progów

Wdrozenie (FREE/PUB):
- `logic/risk_rebuy_contract.py`:
  - kontrakt widgetu `RISK` zdeterminowany dla etykiet:
    - `LOW/MED/HIGH/CRIT`,
    - `Rebuy OK/REBUY LOW/NO REBUY`,
  - wymuszenie:
    - `NO REBUY -> CRIT`,
    - `REBUY LOW -> minimum HIGH`.
- `gui/tabs/pulpit.py`:
  - widget `RISK` i panel korzystaja ze wspolnego kontraktu.
- `logic/events/survival_rebuy_awareness.py` i `logic/events/combat_awareness.py`:
  - payloady dopiete o `exploration_value_estimated` i `exobio_value_estimated`.
- `config.py`:
  - progi RISK explo/exobio przeniesione do konfiguracji:
    - `risk.threshold.exploration.*_cr`,
    - `risk.threshold.exobio.*_cr`.
- `tests/test_f7_risk_rebuy_widget_contract.py`:
  - quality gate dla mapowania risk/rebuy + override progow z config.

Commity:
- `5274ddb` `[PUB] FLOW-F7-RISK-REBUY-WIDGET-CONTRACT-01: unify deterministic risk/rebuy contract`
- `61a4d20` `[PUB] FLOW-F7-RISK-REBUY-WIDGET-CONTRACT-01: add configurable value thresholds`

Testy:
- `py -m unittest tests.test_f7_risk_rebuy_widget_contract -v` PASS
- `py -m unittest tests.test_f4_survival_rebuy_awareness_base tests.test_f5_combat_awareness_base tests.test_f5_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F7-CARGO-VALUE-AT-RISK-ESTIMATOR-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Przeliczac ryzyko cargo na walute, nie na sam tonaż.

Zakres:
- Estymacja:
  - `cargo_floor_cr` (do risk),
  - `cargo_expected_cr` (informacyjnie),
  - `confidence` (`HIGH/MED/LOW`).
- Kolejnosc zrodel cen:
  1. biezacy/target market,
  2. cache market,
  3. fallback statyczny.
- Integracja z `RISK` i panelem interakcji.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Risk nie bazuje juz tylko na `cargo_tons`.
- Fallback dziala stabilnie bez danych rynkowych.
- Confidence jest widoczny w UI/logu.

Wdrozenie (FREE/PUB):
- Dodany estimator VaR cargo:
  - `logic/cargo_value_estimator.py`:
    - estymacja:
      - `cargo_floor_cr` (do risk),
      - `cargo_expected_cr` (informacyjnie),
      - `confidence` (`HIGH/MED/LOW`),
    - kolejnosc zrodel:
      1. market biezacy,
      2. cache market,
      3. fallback statyczny,
    - fallback dla "unknown tons" po medianie market/cache i ostatecznie po cenie domyslnej.
- Integracja runtime:
  - `logic/event_handler.py`:
    - sync estymatora na `on_market_update`, `on_cargo_update` i na Journal `Cargo`.
  - `logic/events/survival_rebuy_awareness.py`:
    - `VAR` liczone z `cargo_floor_cr` (waluta), nie z samego tonażu,
    - payload dopiety o:
      - `cargo_floor_cr`,
      - `cargo_expected_cr`,
      - `cargo_value_confidence`,
      - `cargo_value_source`.
  - `logic/events/combat_awareness.py`:
    - ten sam kontrakt VaR cargo i integracja w payload.
- UI:
  - `gui/tabs/pulpit.py` panel `RISK` pokazuje:
    - `Cargo VaR: floor/expected`,
    - `Conf`,
    - `Src`.
- Konfiguracja:
  - `config.py`:
    - `risk.cargo.default_unit_price_cr`,
    - `risk.cargo.floor_factor.market/cache/fallback`,
    - `risk.cargo.fallback_prices`.

Testy:
- nowy quality gate:
  - `tests/test_f7_cargo_value_at_risk_estimator.py`
    - source order market -> cache -> fallback,
    - confidence mapping,
    - unknown tons median strategy.
- rozszerzone testy payload:
  - `tests/test_f4_survival_rebuy_awareness_base.py`,
  - `tests/test_f5_combat_awareness_base.py`.
- `py -m unittest tests.test_f7_cargo_value_at_risk_estimator tests.test_f7_risk_rebuy_widget_contract tests.test_f4_survival_rebuy_awareness_base tests.test_f5_combat_awareness_base tests.test_f5_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F7-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Domknac regresje i stabilnosc paczki F7.

Zakres:
- Testy i smoke:
  - widget visibility/order contract,
  - single panel slot lifecycle,
  - mode detector + TTL + manual override + safety,
  - risk/rebuy mapping,
  - cargo value estimator fallback/confidence.
- Public guard i release sanity PASS.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- `py tools/smoke_tests_beckendy.py` PASS.
- `py tools/smoke_tests_journal.py` PASS.
- `py tools/public_repo_guard.py` PASS.

Wdrozenie (FREE/PUB):
- Dodany quality gate F7:
  - `tests/test_f7_quality_gates_and_smoke.py`
    - widget visibility/order contract,
    - single panel slot lifecycle + P0 override,
    - mode detector + TTL + manual override + safety,
    - risk/rebuy mapping contract,
    - cargo value estimator fallback/confidence.
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f7_quality_gates_and_smoke_baseline`
    - baseline kontraktu F7 na runtime smoke.

Commit:
- `7b4e8ea` `[PUB] FLOW-F7-QUALITY-GATES-AND-SMOKE-01: add F7 quality gates and smoke baseline`

Testy:
- `py -m unittest tests.test_f7_quality_gates_and_smoke tests.test_f7_mode_state_auto_detector tests.test_f7_mode_ttl_policy tests.test_f7_mode_manual_override_and_safety tests.test_f7_risk_rebuy_widget_contract tests.test_f7_cargo_value_at_risk_estimator tests.test_f5_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (65/65)
- `py tools/smoke_tests_journal.py` PASS (11/11)
- `py tools/public_repo_guard.py` PASS

---

### TRADE-SELL-ASSIST-UI-REMOVAL-01 (P1)
Status: DONE (kod + smoke)

Cel:
- Odchudzic zakladke `Trade` przez usuniecie panelu `Sell Assist` z UI taba.

Zakres:
- `gui/tabs/spansh/trade.py`:
  - usuniety render panelu `Sell Assist` (w tym compact toggle i karty inline),
  - pozostawiona logika runtime Sell Assist (ranking/handoff) bez zmian kontraktu.
- `tools/smoke_tests_beckendy.py`:
  - usunieta regresja wiringu compact panelu UI (`test_trade_sell_assist_compact_wiring`).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Zakladka Trade nie renderuje panelu Sell Assist.
- Logika backendowa Sell Assist pozostaje aktywna (kontrakt decision space + handoff intent).
- Smoke backend PASS.

Wynik:
- Trade UI jest lzejsze i skupione na tabeli trasy + panelu szczegolow kroku.
- Kontrakt Sell Assist pozostaje w warstwie logiki:
  - 2-3 opcje (gdy sa dane),
  - `skip_action=Pomijam`,
  - handoff do `route_intent` bez auto-route.

Testy:
- `py -m compileall gui/tabs/spansh/trade.py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_beckendy.py` PASS (65/65)

---

## Kolejnosc realizacji (FLOW Faza 7 - Refaktor GUI)

1. FLOW-F7-DASHBOARD-WIDGET-STRIP-BASE-01 (P0) (DONE)
2. FLOW-F7-CONSOLE-INTERACTION-SINGLE-SLOT-01 (P0) (DONE)
3. FLOW-F7-MODE-STATE-AUTO-DETECTOR-01 (P0) (DONE)
4. FLOW-F7-MODE-TTL-POLICY-01 (P1) (DONE)
5. FLOW-F7-MODE-MANUAL-OVERRIDE-AND-SAFETY-01 (P1) (DONE)
6. FLOW-F7-RISK-REBUY-WIDGET-CONTRACT-01 (P0) (DONE)
7. FLOW-F7-CARGO-VALUE-AT-RISK-ESTIMATOR-01 (P1) (DONE)
8. FLOW-F7-QUALITY-GATES-AND-SMOKE-01 (P0) (DONE)
9. FLOW-F6-RELEASE-HARDENING-AND-SMOKE-01 (P0) (DONE)

Uwagi wykonawcze:
- Priorytet nadrzedny: specyfikacje z `docs/internal/Refaktor_GUI`.
- Wszystkie tickety F7 sa FREE/PUB (`[PUB]`) i nie dotykaja warstwy PRO.
- Porzadki docs robimy po domknieciu implementacji i quality gates.

---

## NOWE TICKETY (FLOW Faza 8 - Dziennik / Logbook + Entry, priorytet: `docs/Flow/private/journal_dev_md`)

Zrodla nadrzedne dla tej paczki:
- `docs/Flow/private/journal_dev_md/00_JOURNAL_SECTION_OVERVIEW.md`
- `docs/Flow/private/journal_dev_md/01_ENTRY_DATA_MODEL.md`
- `docs/Flow/private/journal_dev_md/02_UI_WIREFLOW.md`
- `docs/Flow/private/journal_dev_md/03_JOURNAL_TO_ENTRY_MAPPING.md`
- `docs/Flow/private/journal_dev_md/04_STORAGE_INDEXING_SYNC.md`
- `docs/Flow/private/journal_dev_md/05_TEMPLATES_PINBOARD_NAV.md`
- `docs/Flow/private/journal_dev_md/06_MVP_PLAN_AND_TASKS.md`
- `docs/Flow/private/journal_dev_md/11_BUILD_IN_JOURNAL.md`

### FLOW-F8-ENTRY-MODEL-AND-STORAGE-BASE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Wdrozyc wspolny model `Entry` oraz storage offline-first pod Dziennik/Wpisy.

Zakres:
- Schema + walidacja `Entry` (w tym `source.kind`, `location`, `tags`, `payload`).
- Repo danych: SQLite (preferowane) lub JSONL (MVP fallback).
- API: create/update/delete/list + filtry + sort + paging.
- Migracje: `schema_version` + bezpieczny fallback.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- CRUD `Entry` dziala i jest pokryty testami.
- Metadane system/stacja/body/koordy sa polami (nie tylko tekstem `body`).
- Filtry i sortowanie dzialaja stabilnie na MVP.

Wdrozenie (FREE/PUB):
- Dodano nowe repozytorium Entry:
  - `logic/entry_repository.py`
    - kontrakt `Entry` + walidacja (`EntryValidationError`),
    - storage JSONL (`user_entries.jsonl`) z atomowym zapisem,
    - API:
      - `create_entry`,
      - `update_entry`,
      - `delete_entry`,
      - `get_entry`,
      - `list_entries` (filtry + sort + paging),
      - helpery: `pin_entry`, `add_tags`, `remove_tags`,
      - bootstrap helper: `create_entry_from_journal`.
- Dodany quality gate F8:
  - `tests/test_f8_entry_model_and_storage_base.py`
    - walidacja kontraktu minimalnego i required fields,
    - update merge nested fields,
    - delete + persistence roundtrip JSONL,
    - filtry (`text`, `tags`, `source_kind`) i sort (`system_az`),
    - helpery pin/tag,
    - create-from-journal source/location contract.

Testy:
- `py -m unittest tests.test_f8_entry_model_and_storage_base -v` PASS (8/8)
- `py -m compileall logic/entry_repository.py tests/test_f8_entry_model_and_storage_base.py` PASS
- `py tools/smoke_tests_beckendy.py` PASS (65/65)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F8-WPISY-UI-THREE-PANEL-01 (P0)
Status: DONE (kod + smoke)

Cel:
- Wdrozyc nowy layout Dziennika zgodny z `journal_dev_md`:
  - 2 zakladki (`Wpisy`, `Logbook`),
  - 3 panele w `Wpisy` (Kategorie / Lista / Podglad).

Zakres:
- Widok drzewka kategorii i lista wpisow.
- Podglad + edycja wpisu.
- Filtry minimum: `tekst`, `tag`, `data`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Uklad 2-zakladkowy i 3-panelowy jest jednoznacznie wdrozony.
- Tworzenie i edycja wpisow dziala bez modalowego chaosu.
- UI zachowuje spojny styl i czytelnosc.

Wdrozenie (FREE/PUB):
- Przebudowana zakladka Dziennik:
  - `gui/tabs/logbook.py`
    - 2 sub-zakladki:
      - `Wpisy`,
      - `Logbook` (placeholder feed Journal pod kolejny ticket),
    - `Wpisy` jako layout 3-panelowy:
      - Kategorie,
      - Lista wpisow,
      - Podglad wpisu.
- Integracja z nowym repozytorium `EntryRepository`:
  - tworzenie, edycja, usuwanie wpisow,
  - filtrowanie po `tekst`, `tag`, `data od/do`,
  - sortowanie (`Najnowsze`, `Najstarsze`, `System A-Z`, `Tytul A-Z`),
  - podglad metadanych i tresci wpisu.
- Dodane akcje panelu podgladu:
  - `Ustaw cel` (route intent),
  - `Przypnij/Odepnij`,
  - `Kopiuj system`.
- Dodana obsluga kategorii usera:
  - lokalna lista kategorii w `user_entry_categories.json`.

Testy:
- `py -m compileall gui/tabs/logbook.py` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base -v` PASS (8/8)
- `py tools/smoke_tests_beckendy.py` PASS (65/65)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F8-LOGBOOK-JOURNAL-FEED-WHITELIST-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Utrzymac Logbook jako feed tylko logow kapitanskich (Journal), bez szumu technicznego.

Zakres:
- Whitelist eventow Journal dla Logbook feed.
- Wykluczenie logow technicznych aplikacji (`[APP]`, `[WARN]`, `[OK]`, `[STATE]`, `[CLIPBOARD]`).
- Logbook pozostaje read-only feedem; trwale dane tworzymy dopiero jako `Entry`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Feed pokazuje tylko eventy kapitanskie.
- Brak przecieku logow technicznych do zakladki Logbook.
- Zachowana wydajnosc i brak floodu.

Wdrozenie (FREE/PUB):
- Dodana warstwa whitelist + formatter feedu:
  - `logic/logbook_feed.py`
  - whitelist eventow Journal dla feedu Logbook (`MarketBuy`, `MarketSell`, `FSDJump`,
    `Docked`, `Undocked`, `Scan`, `SAAScanComplete`, `ProspectedAsteroid`, etc.).
- `logic/event_handler.py`:
  - enqueue feedu `MSG_QUEUE.put(("logbook_journal_feed", ...))` tylko po pozytywnej walidacji whitelist.
- `gui/app.py`:
  - obsluga nowego typu kolejki `logbook_journal_feed` w `check_queue`.
- `gui/tabs/logbook.py`:
  - zakladka `Logbook` przebudowana z placeholdera na realny feed (read-only),
  - tabela eventow: czas / event / system / miejsce / podsumowanie,
  - limit feedu (`250`) + przycisk `Wyczysc feed` (anti-flood).

Testy:
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F8-JOURNAL-TO-ENTRY-MAPPING-ACTIONS-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Wdrozyc mapowanie eventow Journal do chips i akcji tworzenia wpisow.

Zakres:
- Priorytetowe eventy MVP:
  - `MarketBuy`, `MarketSell`,
  - `Docked`, `Undocked`,
  - `FSDJump` (manual save),
  - `Scan`, `SAAScanComplete`,
  - `ProspectedAsteroid` (jesli aktywne).
- Akcje:
  - `Zapisz jako wpis`,
  - `Zapisz + edytuj`,
  - `Dodaj do istniejacego`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Event -> Entry mapowanie jest deterministyczne.
- Domyslne kategorie i payloady sa zgodne ze spec.
- Tworzenie wpisu z Logbook dziala w 2 kliknieciach.

Wdrozenie (FREE/PUB):
- Dodany deterministyczny mapper MVP eventow Journal -> Entry:
  - `logic/journal_entry_mapping.py`
  - mapowanie kategorii/payloadow dla:
    - `MarketBuy`, `MarketSell`,
    - `Docked`, `Undocked`,
    - `FSDJump`,
    - `Scan`, `SAAScanComplete`,
    - `ProspectedAsteroid`.
- Rozszerzony feed Logbook:
  - `logic/logbook_feed.py` przekazuje `default_category` i `raw_event`
    (podstawa pod akcje zapisu).
- Zakladka `Logbook`:
  - `gui/tabs/logbook.py`
  - dodane akcje:
    - `Zapisz jako wpis`,
    - `Zapisz + edytuj`,
    - `Dodaj do istniejacego`,
  - akcje dostepne z przyciskow i menu kontekstowego (PPM),
  - dopisanie eventu do istniejacego wpisu z merge tagow/location.

Testy:
- `py -m unittest tests.test_f8_journal_to_entry_mapping_actions -v` PASS
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist -v` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F8-NAV-INTEGRATION-ENTRY-AND-CHIPS-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Spiac Dziennik z nawigacja przez `Ustaw cel` z Entry i chipsow Logbook.

Zakres:
- `Ustaw cel` z fallbackiem: stacja -> body -> system.
- `Ustaw cel` z chipsow `SYSTEM`/`STATION` w Logbook.
- Integracja przez route intent/state, bez auto-route i bez automatyzacji gry.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Z Entry i chipsow da sie ustawic cel nawigacji.
- Status bar/komunikat UI potwierdza ustawienie celu.
- Brak side-effectow automatyzujacych gameplay.

Wdrozenie (FREE/PUB):
- Dodana warstwa helperow nawigacji Journal/Entry:
  - `logic/journal_navigation.py`
  - fallback targetu:
    - Entry: `station -> body -> system`,
    - Logbook event: `station -> body -> system`,
  - chips nawigacyjne ograniczone do `SYSTEM`/`STATION`.
- `gui/tabs/logbook.py`:
  - `Ustaw cel (event)` z feedu Logbook przez route intent (`journal.logbook.event`),
  - panel chips nawigacyjnych (SYSTEM/STATION) dla wybranego eventu,
  - `Ustaw cel (chip)` (`journal.logbook.chip`) + `Kopiuj chip`,
  - akcje nawigacyjne takze z menu kontekstowego (PPM),
  - status bar Logbook potwierdza ustawienie celu.
- Integracja pozostaje non-automation:
  - tylko `app_state.set_route_intent(...)`,
  - brak auto-route, brak automatyzacji gameplay.

Testy:
- `py -m unittest tests.test_f8_nav_integration_entry_and_chips -v` PASS
- `py -m unittest tests.test_f8_journal_to_entry_mapping_actions -v` PASS
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist -v` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F8-PINBOARD-TEMPLATES-BASE-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Dodac MVP pinboard i podstawowe szablony wpisow.

Zakres:
- Pin/unpin + filtr `Przypiete`.
- 1-2 szablony MVP:
  - `Mining Hotspot`,
  - `Trade Route`.
- Kontrakt `entry_type` + payload dla templatek.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Pinboard daje szybki dostep do najwazniejszych wpisow.
- Szablony tworza poprawne title/payload.
- Brak regresji nawigacji i filtrow.

Wdrozenie (FREE/PUB):
- Pinboard MVP:
  - `gui/tabs/logbook.py`
  - dodany filtr `Przypiete` w panelu filtrow,
  - dodany szybki toggle `Pinboard: ON/OFF` w toolbarze `Wpisy`,
  - status listy rozroznia tryb pinboard (`Pinboard: N wpisow przypietych`).
- Szablony MVP:
  - `logic/entry_templates.py`
  - dodane template builders:
    - `mining_hotspot`,
    - `trade_route`,
  - domyslne kategorie i kontrakt `entry_type + payload`:
    - `Gornictwo/Hotspoty`, `entry_type=mining_hotspot`,
    - `Handel/Trasy`, `entry_type=trade_route`.
- UI tworzenia z szablonu:
  - `gui/tabs/logbook.py`
  - przycisk `+ Szablon`,
  - prosty flow wyboru szablonu i zebrania pol,
  - tworzenie wpisu przez `build_template_entry(...)` + walidacja.

Testy:
- `py -m unittest tests.test_f8_pinboard_templates_base -v` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base -v` PASS
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist -v` PASS
- `py -m unittest tests.test_f8_journal_to_entry_mapping_actions -v` PASS
- `py -m unittest tests.test_f8_nav_integration_entry_and_chips -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F8-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality gate + smoke)

Cel:
- Domknac regresje i stabilnosc paczki F8.

Zakres:
- Quality gate tests:
  - `Entry` schema + CRUD + filter/sort,
  - Logbook source whitelist,
  - Journal -> Entry mapping actions,
  - nav integration from Entry/chips,
  - pinboard/templates.
- Smoke:
  - `tools/smoke_tests_beckendy.py`,
  - `tools/smoke_tests_journal.py`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Wszystkie quality gates F8 PASS.
- Smoke backend/journal PASS.
- Brak regresji F4/F5/F6/F7.

Wdrozenie (FREE/PUB):
- Dodany zbiorczy quality gate F8:
  - `tests/test_f8_quality_gates_and_smoke.py`
  - cross-check paczki F8:
    - event matrix + whitelist + mapowanie,
    - nawigacja Entry/chips,
    - pinboard i templates,
    - route intent contract bez auto-route.
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f8_quality_pack_baseline`
  - smoke obejmuje:
    - feed Logbook + chips,
    - Journal -> Entry draft,
    - templates,
    - pinboard filter,
    - route intent.

Testy:
- `py -m unittest tests.test_f8_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base tests.test_f8_logbook_journal_feed_whitelist tests.test_f8_journal_to_entry_mapping_actions tests.test_f8_nav_integration_entry_and_chips tests.test_f8_pinboard_templates_base -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (66/66)
- `py tools/smoke_tests_journal.py` PASS (11/11)

---

### FLOW-F8-PRO-STT-ENTRY-LAYER-01 (P2)
Status: TODO (DEFERRED - po domknieciu FREE/PUB F8)

Cel:
- Dodac voice-first tworzenie wpisow (STT) jako warstwe komfortu PRO.

Podzial FREE/PRO:
- FREE: NIE DOTYCZY.
- PRO: private premium UX only.

Commit routing:
- `[PRO]` only.

Status wdrozenia (FREE/PRO):
- FREE: NIE DOTYCZY.
- PRO: NIE WDROZONE.

DoD:
- STT tworzy wpisy bez zmiany semantyki i jakosci insightow FREE.
- Zgodnosc z `PRO_FEATURE_POLICY.md`.

---

## Kolejnosc realizacji (FLOW Faza 8 - Dziennik / Logbook + Entry)

1. FLOW-F8-ENTRY-MODEL-AND-STORAGE-BASE-01 (P0)
2. FLOW-F8-WPISY-UI-THREE-PANEL-01 (P0)
3. FLOW-F8-LOGBOOK-JOURNAL-FEED-WHITELIST-01 (P0)
4. FLOW-F8-JOURNAL-TO-ENTRY-MAPPING-ACTIONS-01 (P0)
5. FLOW-F8-NAV-INTEGRATION-ENTRY-AND-CHIPS-01 (P0)
6. FLOW-F8-PINBOARD-TEMPLATES-BASE-01 (P1)
7. FLOW-F8-QUALITY-GATES-AND-SMOKE-01 (P0)
8. FLOW-F8-PRO-STT-ENTRY-LAYER-01 (P2, deferred)

Uwagi wykonawcze:
- Priorytet nadrzedny: `journal_dev_md`.
- FREE/PUB first: najpierw 1-7, potem ewentualnie PRO.
- Brak automatyzacji gry; tylko wsparcie decyzji i szybki zapis wiedzy.

---

## NOWE TICKETY (Post F8 - Dziennik UX FREE/PUB)

### FLOW-F9-ENTRY-CONTEXT-MENU-ACTIONS-AND-MOVE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Rozszerzyc PPM wpisu o szybkie akcje i przenoszenie wpisu miedzy kategoriami usera.

Zakres:
- PPM na wpisie (lista + podglad):
  - `Ustaw cel`,
  - `Przypnij/Odepnij`,
  - `Kopiuj system`,
  - `Przenies do...` (lista aktualnych kategorii + mozliwosc nowej).
- Kontrakt nazewnictwa celu:
  - przycisk zostaje krotki: `Ustaw cel`,
  - status UI ma jawny typ targetu:
    - `Ustawiono cel [STATION]: ...`,
    - `Ustawiono cel [BODY]: ...`,
    - `Ustawiono cel [SYSTEM]: ...`.
- Fallback targetu bez zmian semantyki:
  - `station -> body -> system`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- PPM ma komplet akcji operacyjnych wpisu.
- `Przenies do...` dziala na kategoriach usera.
- Statusy celu sa czytelne (`[STATION]/[BODY]/[SYSTEM]`).

Wdrozenie (FREE/PUB):
- `gui/tabs/logbook.py`:
  - PPM wpisu dostepne z listy wpisow i panelu podgladu (`<Button-3>`),
  - akcje PPM: `Ustaw cel`, `Przypnij/Odepnij`, `Kopiuj system`, `Przenies do...`,
  - dynamiczne podmenu `Przenies do...` budowane z kategorii usera + kategorii z bazy,
  - opcja `Nowa kategoria...` i update `category_path` dla wybranego wpisu,
  - status `Ustaw cel` ma jawny typ targetu: `[STATION]/[BODY]/[SYSTEM]`.
- `logic/journal_navigation.py`:
  - dodane typed resolvery:
    - `resolve_entry_nav_target_typed(...)`,
    - `resolve_logbook_nav_target_typed(...)`,
  - zachowany kontrakt fallback `station -> body -> system` w resolverach legacy.
- Testy i smoke:
  - nowy test kontraktowy: `tests/test_f9_entry_context_menu_actions_and_move.py`,
  - rozszerzony smoke backend: `tools/smoke_tests_beckendy.py::test_f9_entry_context_menu_contract`.

Testy:
- `py -m unittest tests.test_f8_nav_integration_entry_and_chips tests.test_f9_entry_context_menu_actions_and_move -v` PASS
- `py -m unittest tests.test_f8_quality_gates_and_smoke -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (67/67)

---

### FLOW-F9-ENTRY-MANUAL-METADATA-EDIT-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Dac graczowi pelna, reczna kontrole metadanych wpisu (kategoria + tagi), bez utraty automatyki Renaty.

Zakres:
- Akcja PPM: `Edytuj metadane...`.
- Edycja kategorii wpisu (select/drzewo kategorii).
- Edycja tagow w oknie edycji wpisu:
  - lista checkboxow (tagi lokalne z bazy wpisow),
  - zachowanie auto-tagow jako punkt startowy,
  - mozliwosc dodania nowego taga recznie.
- Zapis zmian bez naruszenia kontraktu `entry_type/payload/source`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Gracz moze recznie zmienic kategorie i tagi dowolnego wpisu.
- Tagi checkbox dzialaja lokalnie (na bazie wpisow Dziennika).
- Brak regresji filtrow i listy kategorii.

Wdrozenie (FREE/PUB):
- `gui/tabs/logbook.py`:
  - PPM wpisu rozszerzone o akcje `Edytuj metadane...`,
  - dodane okno edycji metadanych wpisu:
    - zmiana `category_path` (lista lokalnych kategorii + mozliwosc wpisania nowej),
    - lista tagow lokalnych jako checkboxy,
    - reczne dodanie nowego taga (`Dodaj tag`) bez zamykania okna,
  - zapis metadanych przez `update_entry(...)` tylko dla `category_path` i `tags`,
  - bez zmian kontraktu `entry_type/payload/source`.
- Testy i smoke:
  - nowy test kontraktowy: `tests/test_f9_entry_manual_metadata_edit.py`,
  - rozszerzony smoke backend: `tools/smoke_tests_beckendy.py::test_f9_manual_metadata_edit_contract`.

Testy:
- `py -m unittest tests.test_f9_entry_context_menu_actions_and_move tests.test_f9_entry_manual_metadata_edit -v` PASS
- `py -m unittest tests.test_f8_quality_gates_and_smoke -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (68/68)

---

### FLOW-F9-FILTER-POPOVER-DATE-AND-MULTITAG-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Usprawnic filtrowanie wpisow przez lekkie popovery (inline, bez osobnych okien dialogowych).

Zakres:
- Popover daty po kliknieciu w pole daty:
  - inline (jak autocomplete), bez nowego okna modalnego,
  - zamykanie po kliknieciu poza popoverem / `Esc` / utracie fokusu.
- Semantyka dat:
  - `Od`: domyslnie `forever` (brak dolnej granicy),
  - `Do`: domyslnie `dzisiaj`,
  - godzina ignorowana (wybor dnia = caly dzien, do 23:59:59 lokalnego dnia).
- Multi-tag filter jako popover z checkboxami:
  - `Wszystkie` / `Wyczysc`,
  - tryb dopasowania `ALL` vs `ANY`.
- Tag autocomplete nie jest wymagane w tym tickecie.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

Status wdrozenia (FREE/PRO):
- FREE: WDROZONE (`[PUB]`).
- PRO: NIE DOTYCZY.

DoD:
- Filtr dat i tagow dziala przez popovery inline.
- Wybor daty jest calodzienny (bez znaczenia godziny).
- Multi-tag selection jest czytelny i nie wymaga wpisywania recznego.

Wdrozenie (FREE/PUB):
- `gui/tabs/logbook.py`:
  - filtry `Od`, `Do`, `Tagi` sa otwierane jako popovery inline (bez modali),
  - popovery zamykane przez klik poza, `Esc` i utrate fokusu,
  - semantyka dat:
    - `Od`: domyslnie `forever`,
    - `Do`: domyslnie `dzisiaj`,
    - zakres `Do` liczony do konca dnia (`23:59:59`),
  - multi-tag filter:
    - checkboxy lokalnych tagow z bazy wpisow,
    - akcje `Wszystkie` / `Wyczysc`,
    - tryb dopasowania `ALL` i `ANY`.
- `logic/entry_repository.py`:
  - rozszerzenie filtrow o `tags_mode` (`all`/`any`) przy `filters["tags"]`.
- Testy i smoke:
  - nowy test kontraktowy: `tests/test_f9_filter_popover_date_and_multitag.py`,
  - rozszerzony smoke backend:
    - `tools/smoke_tests_beckendy.py::test_f9_filter_popover_contract`.

Testy:
- `py -m unittest tests.test_f9_filter_popover_date_and_multitag tests.test_f9_entry_manual_metadata_edit tests.test_f9_entry_context_menu_actions_and_move -v` PASS
- `py -m unittest tests.test_f8_entry_model_and_storage_base tests.test_f8_quality_gates_and_smoke -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS (69/69)

---

## Kolejnosc realizacji (Post F8 - Dziennik UX FREE/PUB)

1. FLOW-F9-ENTRY-CONTEXT-MENU-ACTIONS-AND-MOVE-01 (P0) - DONE
2. FLOW-F9-ENTRY-MANUAL-METADATA-EDIT-01 (P0) - DONE
3. FLOW-F9-FILTER-POPOVER-DATE-AND-MULTITAG-01 (P1) - DONE

---

## NOWE TICKETY (F10 - Context Memory Persistence FREE/PUB)

Zrodlo: `docs/Flow/private/Features/11_CONTEXT_MEMORY_PERSISTENCE.md`

### FLOW-F10-CONTEXT-MEMORY-STATE-CONTRACT-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Wprowadzic stabilny kontrakt trwalego stanu aplikacji po restarcie,
  bez profilowania usera.

Zakres:
- Warstwy stanu:
  - `ui_state`,
  - `preferences`,
  - `domain_state`,
  - `anti_spam_state`.
- Kontrakt techniczny:
  - `schema_version`,
  - migracje wersji,
  - graceful fallback do defaults przy uszkodzonym/niezgodnym stanie.
- Guardrails:
  - brak danych osobowych,
  - brak retention pod ukryte profilowanie.
- Audyt "restart-loss":
  - lista stanow runtime, ktore dzis gubia sie po restarcie,
  - klasyfikacja: `persist` vs `session-only`.
  - kandydaci (min.):
    - exobio sample state (`sample_count`, `sample_complete`, `range_ready`),
    - FSS progress flags i first-discovery flags,
    - DSS/high-value/footfall callout flags,
    - route milestone progress cache (next-hop/milestones),
    - trade jackpot cache i smuggler warned targets,
    - dispatcher/debouncer okna anti-spam (wraz z decyzja co utrwalac),
    - combat/survival pattern runtime (jawnie ocenione jako session-only lub persist).

Podzial FREE/PRO:
- FREE (PUB): pelny kontrakt bazowy.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Stan laduje sie i zapisuje stabilnie miedzy sesjami.
- Niekompatybilny stan nie powoduje crashy.
- Contract i migracje sa pokryte testami.
- Istnieje jawny audit stanow restartowych (co zapisujemy, czego nie zapisujemy i dlaczego).

Wdrozenie (FREE/PUB):
- `logic/context_state_contract.py`:
  - kontrakt warstwowy `schema_version=1` (`ui_state/preferences/domain_state/anti_spam_state`),
  - migracja legacy-flat -> layered,
  - fallback przy niezgodnym/uszkodzonym payloadzie,
  - guardrails PII (blokada kluczy osobowych),
  - jawny audit restart-loss (`persist` vs `session-only`).
- `config.py`:
  - nowy `STATE_FILE` (`RENATA_STATE_PATH` override),
  - migracja legacy `app_state.json` do AppData,
  - `config.STATE` jako write-through persistent dict (bez zmiany API dla runtime),
  - API: `get_state_contract()`, `save_state_contract()`, `persist_runtime_state()`, `get_restart_loss_audit()`.

Testy:
- `py -m unittest tests.test_f10_context_memory_state_contract -v` PASS
- `py -m unittest tests.test_route_awareness_state -v` PASS
- `py -m unittest tests.test_f7_mode_state_auto_detector -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-UI-STATE-PERSISTENCE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Przywrocic po restarcie sensowny stan UI.

Zakres:
- Persist:
  - aktywna zakladka,
  - kluczowe checkboxy,
  - pinned cards.
- Odtworzenie stanu po starcie bez blokowania UI.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- UI wraca do ostatniego sensownego widoku.
- Brak regresji startupu i watchdogow.

Wdrozenie (FREE/PUB):
- `config.py`:
  - API UI state: `get_ui_state()`, `save_ui_state()`, `update_ui_state()` (deep-merge patchy).
- `gui/app.py`:
  - persist/restore aktywnej glownej zakladki (`main.active_tab_key`).
- `gui/tabs/spansh/__init__.py`:
  - persist/restore aktywnej sub-zakladki Spansh (`spansh.active_tab_key`).
- `gui/tabs/spansh/trade.py`:
  - persist/restore kluczowych checkboxow Trade (`spansh.trade.flags`):
    - `large_pad`, `planetary`, `player_owned`, `restricted`, `prohibited`, `avoid_loops`, `allow_permits`.
- `gui/tabs/logbook.py`:
  - persist/restore UI dziennika:
    - aktywna sub-zakladka (`journal.active_subtab_key`),
    - filtry (`text/date/tag_mode/tags/sort/pinned_only`),
    - wybrana kategoria.
  - pinboard (pinned cards) wraca po restarcie zgodnie ze stanem filtra.

Testy:
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_ui_state_persistence tests.test_route_awareness_state tests.test_f7_mode_state_auto_detector -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-PREFERENCES-PERSISTENCE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Trwale zapisywac preferencje, ktore wplywaja na zachowanie Renaty.

Zakres:
- Persist:
  - `verbosity`,
  - `trade_choice_bias`,
  - `tts_enabled`.
- Odczyt preferencji podczas bootstrapu runtime.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Preferencje sa zachowane miedzy restartami.
- Ustawienia nie wymagaja recznego "przeklikania" po starcie.

Wdrozenie (FREE/PUB):
- `config.py`:
  - preferences contract API:
    - `get_preferences()`,
    - `save_preferences()`,
    - `update_preferences()`.
  - persist i normalizacja preferencji:
    - `verbosity` (`low/normal/high`),
    - `trade_choice_bias` (`balanced/profit/safety/speed`),
    - `tts_enabled` (bool parser z robust fallback).
  - bootstrap runtime:
    - odczyt `preferences` z persisted state podczas startu,
    - mapowanie `tts_enabled -> voice_enabled` w runtime.
  - sync settings -> preferences:
    - `ConfigManager.save()` aktualizuje preference layer przy zmianach
      `voice_enabled/tts_enabled/verbosity/trade_choice_bias`.
- `logic/context_state_contract.py`:
  - utwardzony zapis kontraktu (unique tmp file + replace retry).

Testy:
- `py -m unittest tests.test_f10_preferences_persistence tests.test_f10_context_memory_state_contract tests.test_f10_ui_state_persistence -v` PASS
- `py -m unittest tests.test_route_awareness_state tests.test_f7_mode_state_auto_detector -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-DOMAIN-STATE-LAST-CONTEXT-01 (P1)
Status: DONE (kod + testy + smoke)

Cel:
- Zachowac minimalny kontekst domenowy potrzebny do szybkiego wznowienia pracy.

Zakres:
- Persist:
  - `last_route`,
  - `last_commodity`,
  - `last_plan_id`.
- Odtwarzanie kontekstu tylko jako wsparcie UX, bez zmiany semantyki insightow.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Po restarcie user moze wznowic ostatni kontekst bez recznego odtwarzania.
- Brak efektu "auto-akcji" bez decyzji usera.

Wynik:
- `logic/context_state_contract.py`:
  - rozszerzone defaults `domain_state` o:
    - `last_route`,
    - `last_commodity`,
    - `last_plan_id`.
- `config.py`:
  - dodane API warstwy domenowej:
    - `get_domain_state/save_domain_state/update_domain_state`,
    - `get_last_context/update_last_context`.
- `gui/common_route_progress.py`:
  - persist `last_route` + `last_plan_id` podczas `handle_route_ready_autoclipboard(...)`,
  - startup restore `last_route` przez `load_last_route_context_from_domain_state()`.
- `gui/tabs/spansh/trade.py`:
  - persist `last_commodity`:
    - po zaladowaniu wynikow trade,
    - po wyborze kroku trasy (selection details).
- Dodany quality gate:
  - `tests/test_f10_domain_state_last_context.py`.

Testy:
- `py -m unittest tests.test_f10_domain_state_last_context -v` PASS
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_ui_state_persistence tests.test_f10_preferences_persistence -v` PASS
- `py -m unittest tests.test_route_awareness_state tests.test_f7_mode_state_auto_detector -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-EXOBIO-SAMPLE-CONTINUITY-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Usunac blad numeracji probek exobio po restarcie aplikacji.

Zakres:
- Persist exobio progress:
  - `sample_count_by_key` (`system/body/species`),
  - `sample_complete_keys` (lock 3/3),
  - `range_ready_warned_keys`,
  - minimalny `range_trackers` state.
- Startup recovery:
  - odbudowa exobio progress z `ScanOrganic` (okno recovery),
  - fallback na neutralny wording, gdy stan jest niepewny.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Scenariusz:
  - 1/3 probki -> restart app/gry -> kolejna proba
  - daje poprawnie "2/3", nie "1/3".
- Brak regresji dla `EXOBIO_RANGE_READY` i locka 3/3.

Wynik:
- `config.py`:
  - dodane API warstwy anti-spam:
    - `get_anti_spam_state/save_anti_spam_state/update_anti_spam_state`.
- `logic/events/exploration_bio_events.py`:
  - persist exobio state do `anti_spam_state.exobio`:
    - `sample_count_by_key`,
    - `sample_complete_keys`,
    - `range_ready_warned_keys`,
    - `range_trackers`,
    - `last_status_pos`,
    - `uncertain_sequence_keys`.
  - startup restore exobio state:
    - `load_exobio_state_from_contract(...)`.
  - startup recovery z Journal:
    - `recover_exobio_from_journal_lines(...)`,
    - `bootstrap_exobio_state_from_journal_lines(...)`.
  - fallback wording przy niepewnym stanie:
    - neutralne `Kolejna próbka ...` zamiast blednej numeracji.
  - `reset_bio_flags(persist=True)` czyści i zapisuje stan exobio.
- `app/main_loop.py`:
  - `_bootstrap_state(...)` dopina exobio bootstrap recovery przed replay startupowym.
- Dodany quality gate:
  - `tests/test_f10_exobio_sample_continuity.py`.

Testy:
- `py -m unittest tests.test_f10_exobio_sample_continuity -v` PASS
- `py -m unittest tests.test_f3_exobio_helper_progress -v` PASS
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_domain_state_last_context tests.test_f10_ui_state_persistence tests.test_f10_preferences_persistence -v` PASS
- `py -m unittest tests.test_route_awareness_state tests.test_f7_mode_state_auto_detector -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-ANTI-SPAM-PERSISTENCE-TTL-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Utrzymac pamiec anti-spam miedzy sesjami tam, gdzie to potrzebne dla UX.

Zakres:
- Persist minimalnej pamieci dedup/cooldown:
  - FSS milestones,
  - Exobio READY + exobio sample continuity state,
  - landing callouts.
- Persist z krotkim TTL (zalezne od wyniku audytu restart-loss):
  - route milestone progress cache,
  - trade jackpot cache,
  - smuggler warned targets.
- TTL i limity rozmiaru dedup keys.
- Integracja tylko przez dispatcher (zakaz obchodzenia dispatcher-a).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Po restarcie brak floodu "starymi" calloutami.
- TTL dziala przewidywalnie, bez narastania stanu.
- Pokryte scenariusze restartowe dla exobio/FSS/route.

Wdrozenie (FREE/PUB):
- `config.py`:
  - dodane domyslne ustawienia TTL/limit dla anti-spam persistence:
    - `anti_spam.persist_min_interval_sec`,
    - `anti_spam.debouncer.ttl_sec`,
    - `anti_spam.debouncer.max_keys`,
    - `anti_spam.route_milestone.ttl_sec`,
    - `anti_spam.route_milestone.max_routes`,
    - `anti_spam.trade_jackpot.ttl_sec`,
    - `anti_spam.trade_jackpot.max_stations`,
    - `anti_spam.trade_jackpot.max_items`,
    - `anti_spam.smuggler_warned.ttl_sec`,
    - `anti_spam.smuggler_warned.max_targets`.
- `logic/utils/notify.py`:
  - `NotificationDebouncer` rozszerzony o:
    - load/persist stanu do `anti_spam_state.dispatcher_debouncer_windows`,
    - pruning po TTL + limit kluczy,
    - export/import snapshot stanu.
- `logic/events/trade_events.py`:
  - persisted cache `trade_jackpot_cache` z TTL i limitami.
- `logic/events/smuggler_events.py`:
  - persisted cache `smuggler_warned_targets` z TTL i limitami.
- `gui/common_route_progress.py`:
  - persisted cache `route_milestone_progress_cache`:
    - zapis progresu milestone (25/50/75/100),
    - restore po wznowieniu tej samej trasy.
- Dodany quality gate:
  - `tests/test_f10_anti_spam_persistence_ttl.py`.

Testy:
- `py -m unittest tests.test_f10_anti_spam_persistence_ttl -v` PASS
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_exobio_sample_continuity tests.test_route_awareness_state tests.test_f5_anti_spam_regression -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality gates + smoke)

Cel:
- Domknac jakosc i regresje dla calej paczki F10.

Zakres:
- Testy kontraktowe:
  - schema_version + migracje,
  - fallback przy uszkodzonym stanie,
  - brak danych osobowych w persisted state,
  - anti-spam TTL i limity,
  - exobio continuity (1/3 -> restart -> 2/3),
  - restart-loss audit policy (`persist` vs `session-only`).
- Smoke:
  - restart app -> odtworzenie `ui_state/preferences/domain_state`,
  - anti-spam persistence bez floodu.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Testy F10 PASS.
- Smoke backend/journal PASS bez regresji F4-F9.

Wdrozenie (FREE/PUB):
- Dodany quality gate pack:
  - `tests/test_f10_quality_gates_and_smoke.py`
    - fallback przy uszkodzonym state file (`load_state_contract_file` -> default contract),
    - policy audit restart-loss (`persist` vs `session-only`),
    - limit anti-spam dla debouncera (`anti_spam.debouncer.max_keys`),
    - restart smoke dla odtworzenia `ui_state/preferences/domain_state`,
    - restart smoke anty-spam bez floodu (trade jackpot + smuggler).
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f10_quality_gates_and_smoke_baseline`
    - kontrakt restartu warstw state,
    - anty-spam persistence po restarcie bez duplikatow.

Testy:
- `py -m unittest tests.test_f10_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_ui_state_persistence tests.test_f10_preferences_persistence tests.test_f10_domain_state_last_context tests.test_f10_exobio_sample_continuity tests.test_f10_anti_spam_persistence_ttl -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F10-PRO-ERGONOMIC-PRESETS-01 (P2)
Status: TODO (DEFERRED - po domknieciu FREE/PUB F10)

Cel:
- Dodac tylko ergonomiczne rozszerzenia PRO (np. wiecej presetow),
  bez zmiany jakosci analizy.

Podzial FREE/PRO:
- FREE (PUB): NIE DOTYCZY.
- PRO (PRO): private UX only.

Commit routing:
- `[PRO]` only.

DoD:
- Brak zmiany semantyki insightow FREE/PUB.
- Zgodnosc z polityka PRO.

---

## Kolejnosc realizacji (F10 - Context Memory Persistence FREE/PUB)

1. FLOW-F10-CONTEXT-MEMORY-STATE-CONTRACT-01 (P0) (DONE)
2. FLOW-F10-UI-STATE-PERSISTENCE-01 (P0) (DONE)
3. FLOW-F10-PREFERENCES-PERSISTENCE-01 (P0) (DONE)
4. FLOW-F10-DOMAIN-STATE-LAST-CONTEXT-01 (P1) (DONE)
5. FLOW-F10-EXOBIO-SAMPLE-CONTINUITY-01 (P0) (DONE)
6. FLOW-F10-ANTI-SPAM-PERSISTENCE-TTL-01 (P0) (DONE)
7. FLOW-F10-QUALITY-GATES-AND-SMOKE-01 (P0) (DONE)
8. FLOW-F10-PRO-ERGONOMIC-PRESETS-01 (P2, deferred)

---

## NOWE TICKETY (F11 - Cash-In Assistant Hardening FREE/PUB)

Zrodlo: `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md`

### FLOW-F11-CASH-IN-PAYOUT-POLICY-UC-VISTA-01 (P0)
Status: DONE (kod + testy)

Cel:
- Wdrozyc twardy kontrakt payout dla cash-in (UC/Vista) oraz jawne rozdzielenie `tariff %` vs fee serwisowe.

Zakres:
- Payout policy (MVP):
  - UC:
    - non-carrier -> 100%,
    - fleet carrier -> 75% (fixed fee 25%).
  - Vista:
    - non-carrier -> 100%,
    - fleet carrier -> `ASSUMED_100` (needs revalidation).
- Runtime fallback Vista:
  - `UNKNOWN` + domyslny fallback `ASSUMED_100`.
- `tariff %`:
  - tylko meta-info o carrierze,
  - bez wplywu na payout UC w modelu MVP.
- Kontrakt obliczen:
  - `brutto`, `fee`, `netto`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Dla UC payout na carrierze jest liczony fixed 25% fee.
- Dla Vista payout ma status assumption/unknown zgodny z trust-freshness.
- UI/runtime maja jawne pola `brutto/fee/netto`.

Checklist PR-F11-1:
- [x] Payout policy UC/Vista zaimplementowana.
- [x] `tariff %` tylko jako meta-info.
- [x] Kontrakt `brutto/fee/netto` dostepny w payloadach.
- [x] Testy jednostkowe payout PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - dodany runtime kontrakt payout `brutto/fee/netto` dla UC/Vista,
  - UC fleet carrier liczony fixed-policy (`75%`, fee `25%`),
  - Vista fleet carrier wspiera tryby `ASSUMED_100` i `UNKNOWN` z fallbackiem `ASSUMED_100`,
  - `tariff %` trzymana jako meta-info (`applies_to_payout=False`), bez wplywu na payout UC,
  - payload `cash_in_payload` zawiera `payout_contract` z mapa:
    - `uc_non_carrier`,
    - `uc_fleet_carrier`,
    - `vista_non_carrier`,
    - `vista_fleet_carrier`.
- `tests/test_f11_cash_in_payout_policy.py`:
  - test fixed fee UC 25% na fleet carrier,
  - test Vista `UNKNOWN` -> fallback `ASSUMED_100`,
  - test obecnosci kontraktu `brutto/fee/netto` w runtime payload.

Testy:
- `py -m unittest tests.test_f11_cash_in_payout_policy -v` PASS
- `py -m unittest tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F11-STATION-CANDIDATE-CONTRACT-AND-PROVIDER-DETAILS-01 (P0)
Status: DONE (kod + testy)

Cel:
- Przejsc z listy nazw stacji na kontrakt danych kandydata stacji do cash-in.

Zakres:
- Kontrakt `StationCandidate` (MVP):
  - `name`,
  - `system_name`,
  - `type` (`station|outpost|settlement|fleet_carrier`),
  - `services.has_uc`,
  - `services.has_vista`,
  - `distance_ly`,
  - `distance_ls`,
  - `source`,
  - `freshness_ts`.
- Integracja providerow:
  - EDSM/Spansh `details` (typ/uslugi/odleglosci/freshness),
  - unifikacja do jednego modelu runtime.
- Fallback:
  - brak danych szczegolowych -> tryb orientacyjny + confidence.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Cash-In Assistant operuje na `StationCandidate`, nie na samych nazwach.
- Dostepna jest usluga-aware filtracja (`has_uc`/`has_vista`).
- Dostepna jest informacja o freshness danych.

Checklist PR-F11-2:
- [x] Kontrakt `StationCandidate` w runtime.
- [x] Adaptery providerow EDSM/Spansh.
- [x] Fallback orientacyjny z confidence.
- [x] Testy kontraktowe provider->candidate PASS.

Wdrozenie (FREE/PUB):
- `logic/cash_in_station_candidates.py`:
  - dodany kontrakt `StationCandidate` (name/system/type/services/distance/source/freshness),
  - normalizacja i deduplikacja kandydatow z merge `source` oraz pokrycia uslug (`has_uc`/`has_vista`),
  - service-aware filtracja (`uc`/`vista`).
- `logic/spansh_client.py`:
  - dodany provider details: `stations_for_system_details(...)`.
- `logic/utils/edsm_client.py`:
  - dodany provider details: `fetch_system_stations_details(...)` + cache szczegolow.
- `logic/utils/http_edsm.py`:
  - dodany wrapper `edsm_station_details_for_system(...)`.
- `logic/events/cash_in_assistant.py`:
  - payload rozszerzony o `station_candidates` i `station_candidates_meta`,
  - runtime wspiera zrodla:
    - payload (`station_candidates`),
    - payload names (`station_names`),
    - provider lookup (flag),
    - local fallback (`current_station`).
- `config.py`:
  - `cash_in.station_candidates_lookup_enabled` (domyslnie `False`),
  - `cash_in.station_candidates_limit` (domyslnie `24`).

Testy:
- `py -m unittest tests.test_f11_station_candidate_contract tests.test_f11_station_provider_details -v` PASS
- `py -m unittest tests.test_f11_cash_in_payout_policy tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F11-CASH-IN-RANKING-PROFILES-SAFE-FAST-SECURE-01 (P0)
Status: DONE (kod + testy)

Cel:
- Wdrozyc ranking kandydatow i profile decyzji SAFE/FAST/SECURE.

Zakres:
- Twarde filtry:
  - exploration -> `has_uc`,
  - exobio -> `has_vista`.
- Sort domyslny:
  - rosnaco po `distance_ly`.
- Tie-break:
  - dla UC preferuj station nad fleet_carrier.
- Hutton guard:
  - dla ekstremalnego `distance_ls` kara score + warning UI (bez auto-odrzucenia).
- Profile:
  - `SAFE` (prefer non-carrier),
  - `FAST` (carrier OK, czas/odleglosc),
  - `SECURE` (docked + usluga -> cash-in now),
  - fallback `SECURE` -> `SAFE`, gdy uslugi brak.
- Preferencje gracza:
  - `avoid_carriers_for_uc`,
  - `carrier_ok_for_fast_mode`,
  - `show_tariff_meta`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Ranking kandydatow jest deterministyczny i profilowany przez SAFE/FAST/SECURE.
- Preferencje carrier sa respektowane.
- `distance_ls` guard redukuje puapki UX typu Hutton.

Checklist PR-F11-3:
- [x] Ranking SAFE/FAST/SECURE.
- [x] Tie-break station > carrier dla UC.
- [x] Hutton guard w score + warning.
- [x] Testy rankingowe i preferencji PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - dodany ranking profili `SAFE` / `FAST` / `SECURE`,
  - twarde filtry uslug:
    - `UC` -> `has_uc`,
    - `VISTA` -> `has_vista`,
  - tie-break dla UC preferuje `station` ponad `fleet_carrier` (SAFE),
  - `SECURE` preferuje biezaca stacje przy `Docked` + dostepnej usludze,
  - fallback `SECURE -> SAFE`, gdy uslugi brak,
  - Hutton guard (`distance_ls`) dodaje warning (`distance_ls_high`) i kare score, bez odrzucania kandydata,
  - opcje cash-in zawieraja profile z target/payout/reasoning/scores.
- `config.py`:
  - dodane preferencje rankingowe:
    - `cash_in.avoid_carriers_for_uc`,
    - `cash_in.carrier_ok_for_fast_mode`,
    - `cash_in.show_tariff_meta`,
    - `cash_in.hutton_guard_ls_threshold`,
    - `cash_in.hutton_guard_score_penalty`.
- `tests/test_f11_cash_in_ranking_profiles.py`:
  - ranking SAFE/FAST/SECURE,
  - preferencje carrier (`avoid` / `carrier_ok_for_fast_mode`),
  - Hutton guard warning,
  - `SECURE` dla docked i fallback `SECURE -> SAFE`.

Testy:
- `py -m unittest tests.test_f11_cash_in_ranking_profiles tests.test_f11_station_candidate_contract tests.test_f11_station_provider_details -v` PASS
- `py -m unittest tests.test_f11_cash_in_payout_policy tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F11-CASH-IN-ROUTE-HANDOFF-WITH-USER-CONSENT-01 (P1)
Status: DONE (kod + testy)

Cel:
- Domknac handoff cash-in -> route intent z twarda zasada zgody gracza.

Zakres:
- Akcje opcji cash-in:
  - `Ustaw trase`,
  - `Copy next hop`,
  - `Pomijam`.
- Integracja z route warstwa:
  - przekazanie profilu `SAFE` vs `FAST/NEUTRON`.
- Hard rule:
  - brak automatycznego generowania/ustawiania trasy bez akcji gracza.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Route handoff uruchamia sie tylko po jawnej akcji usera.
- Cash-in nie lamie inwariantu no-automation.

Checklist PR-F11-4:
- [x] Akcje `Ustaw trase` / `Copy next hop` dzialaja z cash-in.
- [x] Brak auto-route bez klikniecia.
- [x] Testy integracyjne route handoff PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - dodany kontrakt handoff:
    - `resolve_cash_in_option_target(...)`,
    - `handoff_cash_in_to_route_intent(...)`,
  - hard rule: `allow_auto_route=True` rzuca `AUTO_ROUTE_FORBIDDEN_CASH_IN`,
  - trigger cash-in nie modyfikuje route intent sam z siebie (no implicit route side-effects).
- `gui/tabs/pulpit.py`:
  - panel cash-in ma akcje:
    - `Intent` (wybor opcji),
    - `Ustaw trase`,
    - `Copy next hop`,
    - `Pomijam`,
  - handoff route/copy uruchamiany tylko po kliknieciu usera,
  - zachowany limit akcji panelu (`_PANEL_MAX_ACTIONS = 6`).
- `gui/app.py`:
  - dodany handler `on_cash_in_assistant_action(...)`,
  - `Ustaw trase` -> route intent przez `app_state.set_route_intent(...)`,
  - `Copy next hop` -> kopiowanie systemu celu do schowka,
  - brak auto-generowania pelnej trasy.
- `tests/test_f11_cash_in_route_handoff.py`:
  - handoff ustawia route intent z opcji cash-in,
  - blokada auto-route (`AUTO_ROUTE_FORBIDDEN_CASH_IN`),
  - brak mutacji `route_manager`,
  - trigger cash-in nie ustawia route intent automatycznie.

Testy:
- `py -m unittest tests.test_f11_cash_in_route_handoff tests.test_f11_cash_in_ranking_profiles tests.test_f11_station_candidate_contract tests.test_f11_station_provider_details -v` PASS
- `py -m unittest tests.test_f11_cash_in_payout_policy tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f6_voice_ethics_compliance tests.test_sell_assist_intent_handoff tests.test_route_awareness_state -v` PASS

---

### FLOW-F11-CASH-IN-STARTJUMP-CALLOUT-CONFIDENCE-01 (P1)
Status: DONE (kod + testy)

Cel:
- Dodac informacyjny callout cash-in przy wyjsciu z systemu (`StartJump`) z kontrola confidence.

Zakres:
- Trigger:
  - event `StartJump` (Hyperspace).
- Tresc:
  - `Twoje dane naukowe sa warte X Cr`,
  - `W ostatnim systemie zarobiles Y Cr`.
- Confidence gating:
  - `HIGH`: TTS moze podac konkretna kwote,
  - `MED`: TTS moze podac kwote orientacyjna,
  - `LOW`: bez kwoty, tylko tier (np. `VaR(Data): HIGH`).
- Anti-spam:
  - dedup/cooldown dla StartJump callout.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- StartJump callout dziala bez spamu i respektuje confidence.
- Przy `LOW` confidence nie pada mylaca kwota.

Checklist PR-F11-5:
- [x] StartJump trigger + template TTS.
- [x] Confidence policy HIGH/MED/LOW.
- [x] Dedup/cooldown.
- [x] Testy calloutu i anti-spam PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - dodany trigger `trigger_startjump_cash_in_callout(...)` dla `StartJump` (`Hyperspace`),
  - tresc calloutu zalezna od confidence:
    - `HIGH`: konkretne kwoty (`X Cr lacznie`, `Y Cr ostatni system`),
    - `MED`: kwoty orientacyjne (zaokraglone),
    - `LOW`: bez kwot, tylko tier `VaR(Data): ...`,
  - anti-spam:
    - dedup signature + cooldown (`cash_in.startjump_callout_cooldown_sec`),
  - callout ignorowany przy `bootstrap_replay` i dla `StartJump` innych niz `Hyperspace`.
- `logic/event_handler.py`:
  - router journala podpiety do cash-in StartJump callout.
- `logic/event_insight_mapping.py`:
  - nowy kontrakt `MSG.CASH_IN_STARTJUMP` (insight class + TTS policy).
- `logic/tts/text_preprocessor.py`:
  - dodany template/fallback dla `MSG.CASH_IN_STARTJUMP`.
- `config.py`:
  - `cash_in.startjump_callout_enabled`,
  - `cash_in.startjump_callout_cooldown_sec`.
- `tests/test_f11_cash_in_startjump_callout.py`:
  - trigger hyperspace,
  - confidence HIGH/MED/LOW,
  - anti-spam cooldown,
  - routing `EventHandler -> cash-in startjump`.
- `tests/test_event_insight_mapping.py`:
  - kontrakt mapowania rozszerzony o `MSG.CASH_IN_STARTJUMP`.

Testy:
- `py -m unittest tests.test_f11_cash_in_startjump_callout tests.test_event_insight_mapping tests.test_f11_cash_in_route_handoff tests.test_f11_cash_in_ranking_profiles tests.test_f11_station_candidate_contract tests.test_f11_station_provider_details tests.test_f11_cash_in_payout_policy tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F11-CASH-IN-UI-TRANSPARENCY-CONTRACT-01 (P1)
Status: DONE (kod + testy)

Cel:
- Ustandaryzowac kontrakt UI opcji cash-in i podniesc transparentnosc decyzji.

Zakres:
- Staly format opcji:
  - `Label` (`SAFE|FAST|SECURE`),
  - `Target` (stacja/carrier + system),
  - `Payout` (`brutto/fee/netto` lub `unknown`),
  - `ETA` (czas lub `unknown`),
  - `Risk` (tier + krotki reason),
  - `Actions` (`Ustaw trase` / `Copy next hop` / `Pomijam`).
- Oznaczenia:
  - `carrier` vs `non-carrier`,
  - meta `tariff %` (informacyjnie),
  - label `assumption` + `freshness` dla niepewnego payout Vista.
- Explainability:
  - `Dlaczego ta opcja?`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Wszystkie opcje cash-in sa renderowane w jednolitym kontrakcie UI.
- Gracz widzi jawnie koszty i poziom pewnosci.

Checklist PR-F11-6:
- [x] Kontrakt rendera opcji wdrozony.
- [x] Oznaczenia carrier/assumption/freshness.
- [x] Explainability.
- [x] Testy UI kontraktu PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - wdrozony staly kontrakt UI dla opcji cash-in:
    - `ui_contract_version = F11_UI_V1`,
    - `ui_contract.label`,
    - `ui_contract.target` (`display`, `kind`),
    - `ui_contract.payout` (`brutto/fee/netto/unknown/status/assumption/freshness/tariff_meta`),
    - `ui_contract.eta`,
    - `ui_contract.risk`,
    - `ui_contract.why`,
    - `ui_contract.actions` (`set_route`, `copy_next_hop`, `skip`),
  - kontrakt dopinany dla wszystkich opcji (ranking + fallback),
  - profile legacy sa normalizowane do `SAFE|FAST|SECURE`.
- `gui/tabs/pulpit.py`:
  - panel cash-in renderuje teraz szczegoly wybranej opcji w stalej strukturze:
    - wybrana opcja + selector opcji,
    - `Target` + `carrier/non-carrier`,
    - `Payout brutto/fee/netto` albo `unknown`,
    - label `assumption` + `freshness`,
    - `Tariff meta` (informacyjnie),
    - `ETA` + `Risk`,
    - `Dlaczego ta opcja: ...`.
- `tests/test_f11_cash_in_ranking_profiles.py`:
  - test kontraktu `F11_UI_V1`,
  - test `actions` i shape sekcji UI,
  - test `assumption + freshness` dla Vista na carrierze.

Testy:
- `py -m unittest tests.test_f11_cash_in_ranking_profiles tests.test_f11_cash_in_route_handoff tests.test_f11_cash_in_payout_policy tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py -m unittest tests.test_f11_cash_in_startjump_callout tests.test_event_insight_mapping tests.test_f11_station_candidate_contract tests.test_f11_station_provider_details -v` PASS

---

### FLOW-F11-CASH-IN-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality gates + smoke)

Cel:
- Domknac regresje calej paczki F11 (payout, candidates, ranking, route handoff, StartJump callout, UI contract).

Zakres:
- Quality gates:
  - payout policy UC/Vista + tariff-meta separation,
  - StationCandidate contract,
  - ranking SAFE/FAST/SECURE + Hutton guard,
  - route handoff tylko po akcji usera,
  - StartJump confidence policy + anti-spam,
  - UI transparency contract.
- Smoke:
  - backend + journal + cash-in scenariusze edge-case.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Testy F11 PASS.
- Smoke PASS bez regresji F4/F10.

Checklist PR-F11-7:
- [x] Testy jednostkowe F11.
- [x] Testy integracyjne F11.
- [x] Smoke backend/journal PASS.
- [x] Update checklist/docs po wdrozeniu.

Wdrozenie (FREE/PUB):
- Dodany quality gate pack:
  - `tests/test_f11_quality_gates_and_smoke.py`
    - kontrakt payload/UI (`F11_UI_V1`),
    - route handoff tylko po akcji usera (blokada auto-route),
    - StartJump confidence + anti-spam.
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f11_quality_gates_and_smoke_baseline`
    - cash-in payload z kontraktem UI,
    - route handoff bez side-effects na `route_manager.route`,
    - StartJump callout nonflood.
- Rozszerzony smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f11_startjump_cash_in_nonflood`
    - StartJump (Hyperspace) przez router journala,
    - anti-spam: drugi identyczny event stlumiony.

Testy:
- `py -m unittest tests.test_f11_quality_gates_and_smoke tests.test_f11_cash_in_payout_policy tests.test_f11_station_candidate_contract tests.test_f11_cash_in_ranking_profiles tests.test_f11_cash_in_route_handoff tests.test_f11_cash_in_startjump_callout tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

### FLOW-F11-CASH-IN-HOTKEY-TRIGGER-01 (P1)
Status: DONE (kod + testy)

Cel:
- Dodac szybki trigger cash-in z klawiatury (hotkey) bez zmiany semantyki decyzji.

Zakres:
- Wejscie:
  - globalny hotkey aplikacji (tylko gdy app aktywna),
  - mapowanie na trigger cash-in w trybie `manual_hotkey`.
- Zachowanie:
  - hotkey uruchamia ten sam pipeline co klik UI (`manual`),
  - respektuje dedup/cooldown/suppress (bez floodu panelu i TTS),
  - nie ustawia trasy i nie wykonuje auto-route.
- Konfiguracja:
  - `cash_in.hotkey_enabled` (bool),
  - `cash_in.hotkey_binding` (string, np. `Ctrl+Shift+C`).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Hotkey wywoluje cash-in zgodnie z pipeline `manual`.
- Brak regresji anty-spam i brak side-effectow route.

Checklist PR-F11-8:
- [x] Hotkey podlaczony do triggera cash-in.
- [x] Konfiguracja `enabled/binding` dodana.
- [x] Brak auto-route i brak zmian semantyki decyzji.
- [x] Testy jednostkowe/integracyjne hotkey PASS.

Wdrozenie (FREE/PUB):
- `config.py`:
  - dodane `cash_in.hotkey_enabled` (domyslnie `True`),
  - dodane `cash_in.hotkey_binding` (domyslnie `Ctrl+Shift+C`).
- `gui/app.py`:
  - dodany parser bindingu `_to_tk_hotkey_sequence(...)` (human-friendly -> Tk sequence),
  - dodane podpietcie skrótu `_bind_cash_in_hotkey()` podczas startupu GUI,
  - dodany handler `_on_cash_in_hotkey(...)` z guardem aktywnego okna aplikacji,
  - `on_generate_cash_in_assistant(...)` przyjmuje teraz `mode`, zeby hotkey mogl wywolac `manual_hotkey`.
- `logic/events/cash_in_assistant.py`:
  - `manual_hotkey` dziala jako alias manualnego triggera:
    - ten sam dedup namespace `cash_in_manual:*`,
    - ten sam cooldown (`0.0` jak manual UI),
    - bez side-effectow route.
- `tests/test_f11_cash_in_hotkey_trigger.py`:
  - parser bindingu hotkey -> Tk sequence,
  - trigger `manual_hotkey` -> dedup manual + cooldown `0.0`,
  - trigger `manual_hotkey` nie zmienia route state.

Testy:
- `py -m unittest tests.test_f11_cash_in_hotkey_trigger -v` PASS
- `py -m unittest tests.test_f11_cash_in_route_handoff tests.test_f11_quality_gates_and_smoke -v` PASS

---

### FLOW-F11-CASH-IN-EDGE-CASE-FALLBACK-COMMS-01 (P0)
Status: DONE (kod + testy)

Cel:
- Domknac komunikacje i fallbacki dla sytuacji granicznych cash-in (braki danych, brak non-carrier, offline).

Zakres:
- Edge-case: providers empty / brak danych stacyjnych:
  - fallback do trybu orientacyjnego,
  - jawny `confidence` i neutralny komunikat.
- Edge-case: brak kandydatow non-carrier:
  - komunikat UX o konsekwencji fee carriera (UC),
  - opcja kontynuacji z carrierem zamiast twardego bloku.
- Edge-case: offline/przerwane logi:
  - tylko bezpieczne komunikaty (bez twardych rekomendacji),
  - brak crashy i brak wymuszania decyzji.
- Spojnosc:
  - ten sam format komunikatow w panelu i TTS.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Kazdy edge-case ma jawny fallback i komunikat bezpieczny dla gracza.
- UI/TTS nie podaje mylacej pewnosci przy brakach danych.

Checklist PR-F11-9:
- [x] Fallback `providers_empty` i `no_station_data` ma jawny confidence.
- [x] Scenariusz `brak non-carrier` ma komunikat + opcje kontynuacji.
- [x] Offline/przerwane logi nie generuja twardych rekomendacji.
- [x] Testy edge-case PASS (w tym scenariusz `brak non-carrier + providers empty`).

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - dodane mapowanie edge-case -> `edge_case_meta` (`fallback_reasons`, `confidence`, `ui_hint`),
  - fallback confidence spinany z provider status (`providers_empty`, `no_station_data`, `offline`),
  - bezpieczne template TTS dla `providers_empty`, `no_non_carrier`, `offline`,
  - sygnatura cash-in rozszerzona o edge-reasons (stabilny dedup dla roznych fallbackow),
  - dopiete `provider_lookup_status` i liczniki kandydatow do `station_candidates_meta`.
- `gui/tabs/pulpit.py`:
  - czytelny render powodow fallbacku i poziomu pewnosci (`Fallback`, `Uwaga`).
- `tests/test_f11_cash_in_edge_cases.py`:
  - `providers_empty`,
  - `no_non_carrier`,
  - `offline/interrupted logs`,
  - `brak non-carrier + providers empty` (strict UX message).

Testy:
- `py -m unittest tests.test_f11_cash_in_edge_cases -v` PASS
- `py -m unittest discover -s tests -p "test_f11_*.py" -v` PASS
- `py -m unittest tests.test_f4_cash_in_assistant_base tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F11-CASH-IN-ROUTE-PROFILE-STATE-PERSISTENCE-01 (P2)
Status: DONE (kod + testy)

Cel:
- Opcjonalnie utrwalac profil cash-in (`SAFE|FAST|SECURE`) w route-state po akcji gracza.

Zakres:
- Persistence:
  - zapis `route_profile` do route-state przy `Ustaw trase` / `Copy next hop`,
  - brak zapisu przy samym triggerze cash-in bez akcji usera.
- Konfiguracja:
  - flaga runtime, np. `cash_in.persist_route_profile_to_route_state` (domyslnie `False`).
- Integracja:
  - route layer moze czytac profil jako hint (bez auto-planowania trasy),
  - zachowany hard rule no auto-route.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- `route_profile` utrwala sie tylko po jawnej akcji usera.
- Brak regresji route handoff i brak auto-route.

Checklist PR-F11-10:
- [x] Kontrakt route-state rozszerzony o `route_profile`.
- [x] Flaga konfiguracyjna persistence dodana.
- [x] Brak side-effectow przy triggerze bez akcji usera.
- [x] Testy persistence PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - `handoff_cash_in_to_route_intent(...)` wspiera `persist_route_profile` (opcja runtime),
  - handoff probuje przekazac `route_profile` do `set_route_intent` tylko przy wlaczonej fladze,
  - dodany helper `persist_cash_in_route_profile(...)` dla akcji `Copy next hop`.
- `app/state.py` lub route state:
  - `route_profile` dodany do route-state (`snapshot`, `update_route_awareness`, `set_route_intent`),
  - `route_profile` persystowany do `config.STATE` i odtwarzany przy starcie.
- `logic/context_state_contract.py`:
  - `route_profile` dodany do runtime defaults warstwy `domain_state`.
- `config.py`:
  - flaga `cash_in.persist_route_profile_to_route_state` (domyslnie `False`).
- `gui/app.py`:
  - akcja `set_route` przekazuje persistence flag do handoffu,
  - akcja `copy_next_hop` moze utrwalic `route_profile` jako hint route-state.
- `tests/test_f11_cash_in_route_profile_persistence.py`:
  - persistence tylko po akcji usera,
  - brak persistence przy auto triggerze,
  - brak regresji hard rule no auto-route.

Testy:
- `py -m unittest tests.test_f11_cash_in_route_profile_persistence tests.test_f11_cash_in_route_handoff tests.test_route_awareness_state tests.test_f11_quality_gates_and_smoke -v` PASS
- `py -m unittest discover -s tests -p "test_f11_*.py" -v` PASS
- `py -m unittest tests.test_f10_context_memory_state_contract tests.test_f10_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F11 - Cash-In Assistant Hardening FREE/PUB)

1. FLOW-F11-CASH-IN-PAYOUT-POLICY-UC-VISTA-01 (P0)
2. FLOW-F11-STATION-CANDIDATE-CONTRACT-AND-PROVIDER-DETAILS-01 (P0)
3. FLOW-F11-CASH-IN-RANKING-PROFILES-SAFE-FAST-SECURE-01 (P0)
4. FLOW-F11-CASH-IN-ROUTE-HANDOFF-WITH-USER-CONSENT-01 (P1)
5. FLOW-F11-CASH-IN-STARTJUMP-CALLOUT-CONFIDENCE-01 (P1)
6. FLOW-F11-CASH-IN-UI-TRANSPARENCY-CONTRACT-01 (P1)
7. FLOW-F11-CASH-IN-QUALITY-GATES-AND-SMOKE-01 (P0)
8. FLOW-F11-CASH-IN-HOTKEY-TRIGGER-01 (P1) (DONE)
9. FLOW-F11-CASH-IN-EDGE-CASE-FALLBACK-COMMS-01 (P0) (DONE)
10. FLOW-F11-CASH-IN-ROUTE-PROFILE-STATE-PERSISTENCE-01 (P2) (DONE)

---

## NOWE TICKETY (F12 - Cash-In Cross-System Nearest FREE/PUB)

Zrodlo: `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcje 17-18)

### FLOW-F12-CASH-IN-CROSS-SYSTEM-STATION-DISCOVERY-01 (P0)
Status: DONE (kod + testy)

Cel:
- Zapewnic realne wyszukiwanie najblizszych punktow sprzedazy danych poza biezacym systemem (expedition/deep-space case).

Zakres:
- Wejscie:
  - aktualny system gracza,
  - profil decyzji (`SAFE|FAST|SECURE`),
  - wymagana usluga (`UC|VISTA`).
- Discovery:
  - pobieranie kandydatow z systemow sasiednich (promien / budzet skokow),
  - twardy filtr uslug (`has_uc` / `has_vista`),
  - zachowanie kontraktu `StationCandidate` (`type/services/distance/source/freshness`),
  - confidence i fallbacki przy niepelnych danych.
- Wyjscie:
  - lista realnych kandydatow cross-system gotowych do rankingu.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Cash-in znajduje kandydatow z realnym targetem poza aktualnym systemem, gdy w biezacym systemie brak UC/Vista.
- Kontrakt candidate i confidence pozostaje spojny z F11.

Checklist PR-F12-1:
- [x] Cross-system discovery endpoint/pipeline wdrozony.
- [x] Filtracja UC/Vista i normalizacja do `StationCandidate`.
- [x] Ranking input otrzymuje realne cele cross-system.
- [x] Testy jednostkowe discovery PASS.

Wdrozenie (FREE/PUB):
- `logic/utils/edsm_client.py`:
  - dodane `fetch_nearby_systems(...)` (EDSM sphere-systems + cache odpowiedzi).
- `logic/utils/http_edsm.py`:
  - dodane `edsm_nearby_systems(...)` wrapper (debounce + log + safe fallback).
- `logic/cash_in_station_candidates.py`:
  - dodane `station_candidates_cross_system_from_providers(...)`:
    - pobiera systemy sasiednie,
    - zbiera station details per system,
    - filtruje `UC`/`VISTA`,
    - normalizuje i deduplikuje do kontraktu `StationCandidate`.
- `logic/events/cash_in_assistant.py`:
  - `_build_station_candidates_runtime(...)` wspiera cross-system discovery,
  - cross lookup uruchamiany tylko gdy lokalnie brak service-match (`UC`/`VISTA`),
  - `station_candidates_meta` rozszerzone o:
    - `cross_system_lookup_attempted`,
    - `cross_system_lookup_status`,
    - `cross_system_systems_requested`,
    - `cross_system_systems_with_candidates`.
- `config.py`:
  - dodane flagi runtime:
    - `cash_in.cross_system_discovery_enabled`,
    - `cash_in.cross_system_radius_ly`,
    - `cash_in.cross_system_max_systems`.
- Testy:
  - `tests/test_f12_station_provider_nearby.py`,
  - `tests/test_f12_cash_in_cross_system_discovery.py`.

Testy:
- `py -m unittest tests.test_f12_station_provider_nearby tests.test_f12_cash_in_cross_system_discovery -v` PASS
- `py -m unittest discover -s tests -p "test_f11_*.py" -v` PASS
- `py -m unittest tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F12-CASH-IN-ROUTE-HANDOFF-REAL-TARGET-01 (P0)
Status: DONE (kod + testy)

Cel:
- Zagwarantowac, ze `Ustaw trase` i `Copy next hop` dzialaja tylko na realnym celu (`system + station`) zamiast placeholdera.

Zakres:
- Handoff:
  - przekazywanie targetu z rankingu cross-system do route intent,
  - blokada handoffu przy braku realnego targetu (jasny komunikat UX),
  - brak "pozornego sukcesu" dla fallback `no_service_candidates`.
- UX:
  - panel rozroznia target orientacyjny vs realny,
  - komunikat przy braku celu: co brakuje i co zrobic dalej.
- Safety:
  - zachowany hard rule no auto-route bez akcji gracza.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Route intent powstaje tylko dla realnego targetu.
- Brak regresji no-auto-route i no-fake-target.

Checklist PR-F12-2:
- [x] Handoff waliduje realny target (`system_name + station_name`).
- [x] Placeholder target z fallbacku nie ustawia route intent.
- [x] Czytelny komunikat UX dla "brak realnego celu".
- [x] Testy integracyjne handoff PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - `resolve_cash_in_option_target(...)` zwraca:
    - `target_is_real`,
    - `target_quality`.
  - `handoff_cash_in_to_route_intent(...)` ma strict gate dla real target:
    - `target_missing_system`,
    - `target_missing_station`,
    - `target_not_real`.
  - dla scenariusza `no_service_candidates`:
    - wyciete podpinanie fallback placeholder targetu do opcji legacy.
- `gui/app.py`:
  - `set_route`: komunikat `brak realnego celu trasy (system+stacja)` przy walidacji negatywnej.
  - `copy_next_hop`: blokada i komunikat `brak realnego next hop (system+stacja)` dla targetu nie-realnego.
- Testy:
  - nowy: `tests/test_f12_cash_in_route_handoff_real_target.py`,
  - update: `tests/test_f11_cash_in_route_handoff.py` (brak placeholder attach dla fallback legacy).

Testy:
- `py -m unittest tests.test_f11_cash_in_route_handoff tests.test_f12_cash_in_route_handoff_real_target -v` PASS
- `py -m unittest discover -s tests -p "test_f11_*.py" -v` PASS
- `py -m unittest tests.test_f12_station_provider_nearby tests.test_f12_cash_in_cross_system_discovery tests.test_f12_cash_in_route_handoff_real_target tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F12-CASH-IN-CROSS-SYSTEM-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- Domknac jakosc i regresje dla cross-system cash-in (discovery + handoff + UX fallback).

Zakres:
- Quality gates:
  - discovery cross-system,
  - filtracja uslug UC/Vista,
  - ranking nearest dla celu w innym systemie,
  - handoff tylko dla realnego targetu.
- Smoke:
  - scenariusz wyprawowy:
    - brak stacji w aktualnym systemie,
    - stacja dostepna w systemie sasiednim,
    - `Ustaw trase` ustawia poprawny route intent.
  - scenariusz brak danych providerow:
    - komunikat orientacyjny,
    - brak route intent.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- Test pack F12 PASS.
- Smoke PASS bez regresji F11/F4.

Checklist PR-F12-3:
- [x] Testy jednostkowe F12.
- [x] Testy integracyjne F12.
- [x] Smoke backend/journal dla expedition case PASS.
- [x] Aktualizacja docs/checklist po wdrozeniu.

Wdrozenie (FREE/PUB):
- Dodany quality gate pack F12:
  - `tests/test_f12_quality_gates_and_smoke.py`
    - cross-system discovery + real target handoff,
    - fallback `no_service_candidates` blokuje route handoff,
    - placeholder target jest odrzucany (`target_not_real`).
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f12_quality_gates_and_smoke_baseline`
    - expedition case: brak lokalnego UC + remote target cross-system -> handoff PASS,
    - providers-empty case: fallback orientacyjny + handoff blocked.
- Rozszerzony smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f12_cross_system_cash_in_route_gate`
    - analogiczny gate dla przeplywu journal/runtime.

Testy:
- `py -m unittest tests.test_f12_quality_gates_and_smoke tests.test_f12_cash_in_cross_system_discovery tests.test_f12_cash_in_route_handoff_real_target tests.test_f12_station_provider_nearby -v` PASS
- `py -m unittest tests.test_f11_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

## Kolejnosc realizacji (F12 - Cash-In Cross-System Nearest FREE/PUB)

1. FLOW-F12-CASH-IN-CROSS-SYSTEM-STATION-DISCOVERY-01 (P0) (DONE)
2. FLOW-F12-CASH-IN-ROUTE-HANDOFF-REAL-TARGET-01 (P0) (DONE)
3. FLOW-F12-CASH-IN-CROSS-SYSTEM-QUALITY-GATES-AND-SMOKE-01 (P0) (DONE)

---

## NOWE TICKETY (F13 - Cash-In Provider Resilience FREE/PUB)

Zrodlo: `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcja 19)

### FLOW-F13-CASH-IN-PROVIDER-CIRCUIT-BREAKER-BACKOFF-01 (P0)
Status: DONE (kod + testy)

Cel:
- odseparowac chwilowe awarie providerow (`HTTP 503`) od logiki decyzji cash-in.

Zakres:
- circuit breaker per provider/endpoint:
  - osobno dla `edsm.station_details` i `edsm.nearby_systems`,
  - status `DOWN` z TTL (`5-15 min`, configowalne),
  - metryka: `provider_down_503_count`.
- exponential backoff + jitter:
  - retry `1s -> 2s -> 4s -> 8s`,
  - max `3-5` prob, potem `circuit_open`.
- telemetry:
  - `provider_lookup_status` rozroznia:
    - `providers_empty`,
    - `provider_down_503`,
    - `provider_circuit_open`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- brak floodowania endpointow w trakcie outage,
- czytelny status provider outage w payloadzie i logu.

Checklist PR-F13-1:
- [x] Circuit breaker per endpoint.
- [x] Backoff + jitter retry policy.
- [x] Telemetry status/metryki provider outage.
- [x] Testy outage/retry PASS.

Wdrozenie:
- `logic/utils/edsm_client.py`:
  - resilience per endpoint (`station_details`, `nearby_systems`),
  - circuit breaker (`DOWN` + TTL) z metrykami (`provider_down_503_count`),
  - retry policy z exponential backoff + jitter.
- `logic/utils/http_edsm.py`:
  - mapowanie i logowanie statusow `provider_down_503` / `provider_circuit_open`,
  - snapshot telemetry providera dla warstwy cash-in.
- `logic/events/cash_in_assistant.py`:
  - telemetry edge-case i `provider_lookup_status` rozroznia:
    - `providers_empty`,
    - `provider_down_503`,
    - `provider_circuit_open`,
  - komunikaty TTS/UI dla outage/circuit-open.
- `config.py`:
  - ustawienia resilience:
    - `providers.edsm.resilience.circuit_breaker_ttl_sec`,
    - `providers.edsm.resilience.retry.max_attempts`,
    - `providers.edsm.resilience.retry.base_delay_sec`,
    - `providers.edsm.resilience.retry.max_delay_sec`,
    - `providers.edsm.resilience.retry.jitter_sec`.
- Testy:
  - `tests/test_f13_cash_in_provider_resilience.py`,
  - rozszerzenie regresji edge-case: `tests/test_f11_cash_in_edge_cases.py`.

Testy:
- `py -m unittest tests.test_f13_cash_in_provider_resilience tests.test_f11_cash_in_edge_cases -v` PASS
- `py -m unittest tests.test_f12_cash_in_cross_system_discovery tests.test_f12_station_provider_nearby tests.test_f11_cash_in_route_handoff tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F13-CASH-IN-STALE-CACHE-SWR-FALLBACK-01 (P0)
Status: DONE (kod + testy)

Cel:
- zachowac operacyjnosc cash-in przy awariach providerow bez "martwego" panelu.

Zakres:
- stale-while-revalidate dla nearby/system candidates:
  - fallback do ostatniego poprawnego snapshotu,
  - status freshness: `FRESH` / `STALE` / `EXPIRED`,
  - confidence obnizone dla `STALE`.
- cache contract:
  - timestamp + source + service coverage + radius profile,
  - TTL + pruning.
- UX:
  - jawny label "wynik z cache (stale)".

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- przy outage provider panel cash-in uzywa stale cache (jesli istnieje),
- user widzi freshness i ograniczenia danych.

Checklist PR-F13-2:
- [x] SWR fallback dla nearby/provider candidates.
- [x] Freshness labels + confidence mapping.
- [x] Cache TTL/pruning.
- [x] Testy stale fallback PASS.

Wdrozenie:
- `logic/events/cash_in_assistant.py`:
  - SWR snapshot cache dla station candidates (`system+service+radius profile`),
  - fallback do ostatniego snapshotu przy provider empty/outage,
  - statusy freshness: `FRESH` / `STALE` / `EXPIRED`,
  - confidence downgrade dla `STALE`,
  - meta runtime:
    - `swr_cache_used`,
    - `swr_lookup_status`,
    - `swr_freshness`,
    - `swr_cache_age_sec`,
    - `swr_cache_source_status`,
    - `swr_saved_at_utc`.
- `config.py`:
  - `cash_in.swr_cache_enabled`,
  - `cash_in.swr_cache_fresh_ttl_sec`,
  - `cash_in.swr_cache_stale_ttl_sec`,
  - `cash_in.swr_cache_max_items`.
- `tests/test_f13_cash_in_provider_resilience.py`:
  - stale fallback (`STALE`) + confidence downgrade,
  - expired snapshot (`EXPIRED`) bez użycia cache.
- `tests/test_f11_cash_in_edge_cases.py`:
  - reset SWR cache między testami (deterministyczność).

Testy:
- `py -m unittest tests.test_f13_cash_in_provider_resilience tests.test_f11_cash_in_edge_cases -v` PASS
- `py -m unittest tests.test_f4_cash_in_assistant_base tests.test_f12_cash_in_cross_system_discovery tests.test_f12_station_provider_nearby tests.test_f11_cash_in_route_handoff tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F13-CASH-IN-FALLBACK-SOURCES-AND-UX-DEGRADATION-01 (P1)
Status: DONE (kod + testy)

Cel:
- ograniczyc single-point-of-failure na EDSM nearby endpoint.

Zakres:
- fallback source:
  - alternatywny provider (jesli dostepny kontraktowo),
  - lokalny known-systems/stations cache jako fallback LOW confidence.
- UX degradacji:
  - rozroznione komunikaty:
    - provider down (`HTTP 503`),
    - providers empty (`providers_empty`),
    - fallback stale/local.
  - komunikat operacyjny mowi:
    - skad sa dane,
    - jaka jest jakosc danych,
    - co user moze zrobic dalej.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- brak mylacego "brak danych stacyjnych" dla outage providera,
- user ma jasna informacje o trybie degradacji i confidence.

Checklist PR-F13-3:
- [x] Fallback source runtime.
- [x] UX message matrix outage vs empty vs stale.
- [x] Confidence LOW for degraded modes.
- [x] Testy komunikatow i fallback PASS.

Wdrozenie:
- `logic/events/cash_in_assistant.py`:
  - lokalny fallback source: cache znanych systemow/stacji (`local_known_fallback`),
  - zapis local-known po udanym provider lookup,
  - runtime fallback przy `providers_empty` / outage, gdy brak SWR candidates,
  - meta:
    - `local_known_fallback_used`,
    - `local_known_fallback_age_sec`,
    - `local_known_fallback_count`,
  - UX/TTS message matrix rozroznia:
    - `provider_down_503`,
    - `provider_circuit_open`,
    - `providers_empty`,
    - `stale_cache`,
    - `local_known_fallback`.
- `config.py`:
  - `cash_in.local_known_fallback_enabled`,
  - `cash_in.local_known_fallback_ttl_sec`,
  - `cash_in.local_known_fallback_max_items`.
- testy:
  - `tests/test_f13_cash_in_provider_resilience.py` (fallback local-known + message matrix),
  - resety cache w:
    - `tests/test_f11_cash_in_edge_cases.py`,
    - `tests/test_f4_cash_in_assistant_base.py`.

Testy:
- `py -m unittest tests.test_f13_cash_in_provider_resilience tests.test_f11_cash_in_edge_cases tests.test_f4_cash_in_assistant_base -v` PASS
- `py -m unittest tests.test_f12_cash_in_cross_system_discovery tests.test_f12_station_provider_nearby tests.test_f11_cash_in_route_handoff tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F13-CASH-IN-PROVIDER-RESILIENCE-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (kod + testy + smoke)

Cel:
- domknac regresje i potwierdzic odpornosc runtime dla outage providerow.

Zakres:
- quality gates:
  - circuit breaker open/close + TTL,
  - backoff behavior,
  - stale fallback + freshness/confidence labels,
  - UX matrix (`provider_down_503` vs `providers_empty` vs `stale_cache`).
- smoke:
  - outage EDSM nearby -> fallback stale/local -> brak crash/flood,
  - provider recovery -> powrot do `FRESH` i normalnego lookupu.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- quality pack F13 PASS,
- smoke PASS bez regresji F11/F12/F4/F6.

Checklist PR-F13-4:
- [x] Testy quality gate F13 PASS.
- [x] Smoke outage/recovery PASS.
- [x] Dokumentacja runtime zaktualizowana.
- [x] Brak regresji baseline PASS.

Wdrozenie (FREE/PUB):
- Dodany quality pack F13:
  - `tests/test_f13_quality_gates_and_smoke.py`
    - circuit breaker TTL open/close,
    - backoff profile (retry + jitter),
    - fallback stale cache (`STALE`) i confidence labels,
    - provider recovery (powrot do `source_status=providers`).
- Rozszerzony smoke backend:
  - `tools/smoke_tests_beckendy.py::test_f13_quality_gates_and_smoke_baseline`
    - outage `503` -> stale fallback,
    - providers empty -> local-known fallback,
    - recovery -> normal lookup.
- Rozszerzony smoke journal:
  - `tools/smoke_tests_journal.py::test_journal_f13_provider_resilience_fallback_matrix`
    - matrix reasonow/resilience dla runtime cash-in.
- Dopięta izolacja regresji F12/F13 smoke:
  - reset state resilience providera EDSM i cache fallback, aby testy nie dziedziczyly stanu.

Testy:
- `py -m unittest tests.test_f13_quality_gates_and_smoke tests.test_f13_cash_in_provider_resilience tests.test_f12_cash_in_cross_system_discovery tests.test_f12_station_provider_nearby tests.test_f11_cash_in_edge_cases tests.test_f11_cash_in_route_handoff tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_beckendy.py` PASS
- `py tools/smoke_tests_journal.py` PASS

---

## Kolejnosc realizacji (F13 - Cash-In Provider Resilience FREE/PUB)

1. FLOW-F13-CASH-IN-PROVIDER-CIRCUIT-BREAKER-BACKOFF-01 (P0)
2. FLOW-F13-CASH-IN-STALE-CACHE-SWR-FALLBACK-01 (P0)
3. FLOW-F13-CASH-IN-FALLBACK-SOURCES-AND-UX-DEGRADATION-01 (P1)
4. FLOW-F13-CASH-IN-PROVIDER-RESILIENCE-QUALITY-GATES-AND-SMOKE-01 (P0)

---

### FLOW-F14-CASH-IN-EDSM-RADIUS-CAP-AND-DIAGNOSTIC-01 (P0)
Status: DONE (kod + testy)

Powiazane dokumenty:
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcja 20.1)
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md`
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC.md`

Cel:
- usunac falszywe oczekiwanie radius > 100 LY dla EDSM `sphere-systems`.

Zakres:
- runtime clamp radius dla EDSM nearby:
  - `effective_radius = min(requested_radius, 100.0)`,
  - cap oznaczony jako `provider_cap` (limit API EDSM), nie klientowy hardcode bez kontekstu.
- diagnostyka providerowa:
  - pola: `requested_radius`, `effective_radius`, `provider_response_count`,
  - reason:
    - `provider_radius_cap`,
    - `provider_empty`.
- diagnostyka UI:
  - jawna informacja, gdy wpisano radius >100 i aktywny jest provider EDSM.
- explainability:
  - przy `requested>100` i `effective=100` confidence nearby obnizone,
    bez zmiany semantyki decyzji.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- brak scenariusza mylacego `radius=20000` bez informacji o limicie EDSM,
- user widzi radius faktycznie uzyty przez provider.
- scenariusz:
  - `requested>100 -> effective=100`,
  - panel pokazuje `EDSM limit 100 LY`,
  - i komunikat o kontynuacji fallbackiem (gdy 20.2 aktywne).

Checklist PR-F14-1:
- [x] Clamp radius EDSM <= 100 wdrozony.
- [x] Log diagnostyczny requested/effective radius wdrozony.
- [x] UI hint dla limitu providera wdrozony.
- [x] Reason codes `provider_radius_cap`/`provider_empty` wdrozone.
- [x] Testy regresji cash-in PASS.

Wdrozenie:
- `logic/utils/edsm_client.py`:
  - clamp nearby radius (`effective=min(requested, 100.0)`),
  - diagnostyka endpointu `nearby_systems`:
    - `last_requested_radius_ly`,
    - `last_effective_radius_ly`,
    - `last_provider_response_count`.
- `logic/utils/http_edsm.py`:
  - log nearby zawiera `radius` + `effective_radius` + `provider_response_count` + reason.
- `logic/cash_in_station_candidates.py`:
  - cross-system meta eksportuje nearby diagnostics i reason.
- `logic/events/cash_in_assistant.py`:
  - edge reasons rozszerzone o `provider_radius_cap` i `provider_empty`,
  - ui_hint pokazuje diagnostyke requested/effective.

Testy:
- `py -m unittest tests.test_f12_station_provider_nearby tests.test_f14_cash_in_edsm_radius_cap_and_diagnostic -v` PASS
- `py -m unittest tests.test_f13_cash_in_provider_resilience tests.test_f13_quality_gates_and_smoke tests.test_f11_cash_in_edge_cases tests.test_f11_cash_in_route_handoff tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke -v` PASS

---

### FLOW-F14-CASH-IN-SPANSH-DUMP-STATION-INDEX-FALLBACK-01 (P0)
Status: DONE (kod + testy)

Powiazane dokumenty:
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcja 20.2)
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md` (provider localny/offline index)
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC.md` (konsument tych samych danych)

Cel:
- zapewnic realny `system+stacja` dla cash-in, gdy online provider zwraca `empty/503`.

Zakres:
- fallback data source:
  - lokalny index stacji z dumpa Spansh (offline).
- warunek nearest:
  - index korzysta z mapy `system_name -> coords` (wbudowanej lub companion indexu).
- kontrakt bez zmian:
  - mapowanie do `StationCandidate` (`name/system/type/services/distance/source/freshness`).
- aktywacja fallbacku:
  - tylko gdy online path nie zwraca kandydatow z wymagana usluga (`UC`/`Vista`).
- policy bez prowizji (dla exploration):
  - preferencja/stosowanie non-carrier (`station|outpost|settlement`) z `has_uc=True`.
- FC policy (MVP):
  - fleet carriers ignorowane w fallback index (niestabilny nearest).
- quality danych uslug:
  - akceptowane tylko rekordy z pewnym `has_uc=True`,
  - rekordy `unknown services` odrzucane.
- freshness:
  - UI pokazuje `index_date` i `index_age_days`,
  - target source: `offline_index`.

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- w deep-space cash-in moze zwrocic realny target z dumpa mimo `providers_empty`,
- brak regresji dla obecnego flow online/route handoff.
- przy hit fallback:
  - `target_is_real=True`,
  - `target_source=offline_index`,
  - confidence jawne (`MED`/`LOW` zaleznie od wieku indexu).

Checklist PR-F14-2:
- [x] Loader/index dumpa Spansh wdrozony.
- [x] Fallback source podlaczony do cash-in runtime.
- [x] Kontrakt `StationCandidate` zachowany 1:1.
- [x] Mapa coords systemow dla nearest wdrozona.
- [x] FC ignorowane w fallback MVP.
- [x] Unknown services odrzucane (only has_uc=True).
- [x] Handoff route dziala z targetem dumpowym.

Wdrozenie (FREE/PUB):
- `logic/cash_in_station_candidates.py`:
  - dodany loader fallback `station_candidates_from_offline_index(...)`:
    - czyta lokalny JSON indexu (`stations` + optional `systems` coords map),
    - liczy nearest po `origin_coords` (3D distance LY),
    - mapuje 1:1 do kontraktu `StationCandidate`,
    - ignoruje FC w MVP (`non_carrier_only=True`),
    - odrzuca rekordy bez pewnej uslugi (`has_uc=True` / `has_vista=True`),
    - eksportuje meta: `index_date`, `index_age_days`, `rows_*`, `lookup_status`.
  - dodany cache pliku indexu (mtime-aware) + reset helper testowy.
- `logic/events/cash_in_assistant.py`:
  - fallback chain rozszerzony o `offline_index` (po provider/SWR/local-known, przed local fallback),
  - nowe meta runtime:
    - `offline_index_lookup_attempted`,
    - `offline_index_lookup_status`,
    - `offline_index_used`,
    - `offline_index_date`,
    - `offline_index_age_days`.
  - confidence dla `source_status=offline_index`:
    - `MED`/`LOW` zaleznie od wieku indexu (`cash_in.offline_index_confidence_med_age_days`).
  - edge-case reasons/UX/TTS:
    - `offline_index`,
    - `no_offline_index_hit`,
    - jawny hint z `index_date` i `index_age_days`.
- `config.py`:
  - nowe flagi:
    - `cash_in.offline_index_fallback_enabled`,
    - `cash_in.offline_index_path`,
    - `cash_in.offline_index_non_carrier_only`,
    - `cash_in.offline_index_confidence_med_age_days`.
- testy:
  - nowy: `tests/test_f14_cash_in_offline_index_fallback.py`
    - kontrakt i filtry offline indexu,
    - runtime fallback -> realny target -> handoff PASS,
    - miss indexu -> reason `no_offline_index_hit`.

Testy:
- `py -m unittest tests.test_f14_cash_in_offline_index_fallback tests.test_f14_cash_in_edsm_radius_cap_and_diagnostic tests.test_f13_cash_in_provider_resilience tests.test_f12_cash_in_cross_system_discovery tests.test_f12_cash_in_route_handoff_real_target tests.test_f11_cash_in_route_handoff tests.test_f4_cash_in_assistant_base tests.test_f4_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f13_quality_gates_and_smoke tests.test_f12_quality_gates_and_smoke tests.test_f11_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

---

### FLOW-F14-CASH-IN-NEAREST-REAL-TARGET-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (testy + smoke)

Powiazane dokumenty:
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcja 20.3)
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md`
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC.md`

Cel:
- domknac jakosc dla fixu nearest real target bez zmiany semantyki decyzji.

Zakres:
- quality gates:
  - clamp radius + diagnostyka,
  - fallback dump -> `target_is_real=True` -> handoff PASS,
  - brak dumpa/brak danych -> orientacyjny fallback jak obecnie.
  - online real target -> offline fallback nie nadpisuje wyniku.
  - online nearby `count>0`, ale `station_details=0` -> offline fallback daje real target.
  - offline miss -> reason `no_offline_index_hit`.
- smoke:
  - expedition case (`online empty + dump available`) -> realny target,
  - degraded case (`online empty + dump missing`) -> bez crash i z czytelnym komunikatem.
  - runtime no-internet -> offline index nadal zwraca target (gdy index dostepny).

Podzial FREE/PRO:
- FREE (PUB): pelny zakres.
- PRO (PRO): NIE DOTYCZY.

Commit routing:
- `[PUB]` only.

DoD:
- quality pack F14 PASS,
- smoke PASS bez regresji F11/F12/F13/F4/F6.

Checklist PR-F14-3:
- [x] Testy quality gate F14 PASS.
- [x] Smoke expedition/degraded PASS.
- [x] Test no-internet + offline index PASS.
- [x] Brak regresji baseline PASS.

Wdrozenie (FREE/PUB):
- `logic/events/cash_in_assistant.py`:
  - korekta statusu fallbacku: `offline_index_lookup_status=not_needed`, gdy online target juz istnieje
    (offline index nie nadpisuje online wyniku),
  - zachowany strict handoff `target_is_real`.
- quality pack:
  - nowy: `tests/test_f14_quality_gates_and_smoke.py`
    - online real target > offline index (brak nadpisania),
    - online nearby `count>0` + `station_details=0` -> offline index daje real target,
    - offline index miss -> `no_offline_index_hit` + orientational fallback,
    - runtime offline/no-internet -> offline index nadal daje target.
- smoke:
  - `tools/smoke_tests_journal.py::test_journal_f14_offline_index_nearest_real_target`
    - scenario online empty + offline index target + handoff PASS,
    - scenario runtime offline + offline index target PASS.

Testy:
- `py -m unittest tests.test_f14_quality_gates_and_smoke tests.test_f14_cash_in_offline_index_fallback tests.test_f14_cash_in_edsm_radius_cap_and_diagnostic tests.test_f13_quality_gates_and_smoke tests.test_f12_quality_gates_and_smoke tests.test_f11_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS
- `py tools/smoke_tests_journal.py` PASS

---

## Kolejnosc realizacji (F14 - Cash-In Nearest Real Target FREE/PUB)

1. FLOW-F14-CASH-IN-EDSM-RADIUS-CAP-AND-DIAGNOSTIC-01 (P0)
2. FLOW-F14-CASH-IN-SPANSH-DUMP-STATION-INDEX-FALLBACK-01 (P0)
3. FLOW-F14-CASH-IN-NEAREST-REAL-TARGET-QUALITY-GATES-AND-SMOKE-01 (P0)

---

### FLOW-F15-CASH-IN-DUMP-DOWNLOAD-SETTINGS-UI-01 (P1)
Status: DONE (kod + testy bazowe)

Cel:
- dac graczowi jawne sterowanie pobieraniem dumpa Spansh w konfiguracji Cash-In.

Zakres:
- nowe pola ustawien:
  - `cash_in.dump_download_url`,
  - `cash_in.dump_download_path`.
- UI:
  - przycisk pobierania `galaxy_stations.json.gz`,
  - pasek postepu,
  - status transferu i komunikaty bledow.

Wdrozenie:
- `gui/tabs/settings.py`:
  - sekcja Cash-In rozszerzona o downloader dumpa i progress/status.
- `config.py`:
  - dodane domyslne klucze URL/sciezki dumpa.

Uwagi:
- ten ticket nie domyka jeszcze konwersji dumpa do `offline_station_index.json`.

---

### FLOW-F15-CASH-IN-DUMP-TO-OFFLINE-INDEX-CONVERTER-AND-AUTO-WIRING-01 (P0)
Status: DONE (kod + testy)

Cel:
- usunac luke operacyjna: runtime cash-in czyta `offline_station_index.json`,
  a nie surowy `galaxy_stations.json.gz`.

Zakres:
- dodac konwerter dumpa:
  - wejscie: `galaxy_stations.json.gz`,
  - wyjscie: `offline_station_index.json` kompatybilny z fallback providerem.
- kontrakt wyjsciowy:
  - `stations` (z uslugami `has_uc`/`has_vista`),
  - `systems` lub `systems_rows` z coords,
  - `meta/index_date`.
- auto-wiring:
  - po udanej konwersji ustaw `cash_in.offline_index_path` na wygenerowany plik.
- UX:
  - czytelny status "masz dump, ale brak indexu JSON" oraz akcja naprawcza.

DoD:
- po `download + convert` cash-in zwraca realny target offline bez recznej ingerencji,
- `target_is_real=True` dla scenariusza expedition/offline (gdy dane indexu sa dostepne).

Checklist PR-F15-2:
- [x] Konwerter dump->index wdrozony.
- [x] Auto-wiring `cash_in.offline_index_path` wdrozony.
- [x] UX brak-indexu + akcja naprawcza wdrozone.
- [x] Regresja F11/F12/F13/F14 PASS.

Wdrozenie:
- `logic/cash_in_offline_index_builder.py`:
  - streaming konwersja `galaxy_stations.json.gz` -> `offline_station_index.json`,
  - output zgodny z fallback runtime:
    - `stations` (`has_uc`/`has_vista`),
    - `systems_rows` (coords),
    - `meta/index_date`.
- `gui/tabs/settings.py`:
  - nowy przycisk `Zbuduj offline index`,
  - oddzielny progress/status konwersji,
  - auto-podpiecie wygenerowanego pliku do `cash_in.offline_index_path`.
- testy:
  - `tests/test_f15_cash_in_dump_to_offline_index_converter.py`.

Testy:
- `py -m unittest tests.test_f15_cash_in_dump_to_offline_index_converter tests.test_f14_cash_in_offline_index_fallback tests.test_f14_quality_gates_and_smoke -v` PASS

---

### FLOW-F15-CASH-IN-DUMP-TO-INDEX-END-TO-END-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (testy quality gate + smoke-style e2e)

Cel:
- domknac jakosc i powtarzalnosc scenariusza e2e:
  `download dump -> build index -> cash-in real target`.

Zakres:
- quality gates:
  - poprawny format indexu i metadane freshness,
  - scenariusz braku coords/uslug -> jawny fallback reason,
  - scenariusz index stale -> confidence zgodne z polityka.
- smoke:
  - online outage + offline index hit -> route handoff PASS,
  - dump obecny, index brak -> komunikat naprawczy (bez pozornego sukcesu).

DoD:
- PASS quality pack F15,
- PASS smoke bez regresji F11/F12/F13/F14/F6.

Checklist PR-F15-3:
- [x] Testy F15 PASS.
- [x] Smoke e2e PASS.
- [x] Dokumentacja action/spec zaktualizowana.

Wdrozenie:
- `tests/test_f15_quality_gates_and_smoke.py`:
  - scenariusz `dump -> convert -> runtime offline_index -> handoff real target`,
  - scenariusz starego `index_date` -> confidence `LOW`.
- fix pod testy e2e:
  - `logic/cash_in_station_candidates.py::_safe_optional_float(...)`:
    - poprawka obslugi wartosci `0`/`0.0` (coords) dla fallback nearest.

Testy:
- `py -m unittest tests.test_f15_quality_gates_and_smoke tests.test_f15_cash_in_dump_to_offline_index_converter tests.test_f14_cash_in_offline_index_fallback tests.test_f14_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F15 - Cash-In Dump -> Offline Index FREE/PUB)

1. FLOW-F15-CASH-IN-DUMP-DOWNLOAD-SETTINGS-UI-01 (P1) - DONE
2. FLOW-F15-CASH-IN-DUMP-TO-OFFLINE-INDEX-CONVERTER-AND-AUTO-WIRING-01 (P0) - DONE
3. FLOW-F15-CASH-IN-DUMP-TO-INDEX-END-TO-END-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## NOWE TICKETY (F16 - PLAYER_LOCAL_DB FREE/PUB)

Zrodlo:
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md`
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md`

### FLOW-F15-CASH-IN-USER-SUPPLIED-DATA-ATTRIBUTION-UI-01 (P1)
Status: DONE (kod + docs)

Cel:
- dopiac model prawny dumpow Spansh w UI i dokumentacji.

Zakres:
- Settings -> Asystenci -> Cash-In:
  - komunikat `user-supplied data`,
  - atrybucja `Spansh (c) Gareth Harper`.
- dokumentacja Action:
  - jasny zapis, ze Renata nie hostuje ani nie dystrybuuje dumpow.

Wdrozenie:
- `gui/tabs/settings.py`:
  - dopisany blok informacyjny o modelu prawnym i atrybucji.
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md`:
  - sekcja `User-supplied data i atrybucja (MVP)`.

### FLOW-F16-PLAYERDB-CONTRACT-AND-ORDER-BRIDGE-01 (P0)
Status: DONE (kod + docs + testy)

Cel:
- utrzymac kolejnosc fallbacku dla cash-in:
  - local/player memory (bridge do PLAYER_LOCAL_DB),
  - dopiero potem offline index.

Zakres:
- runtime cash-in:
  - preferuj lokalne znane kandydaty przed `offline_index`,
  - zachowaj kontrakt `StationCandidate` bez zmiany semantyki decyzji.
- docs:
  - spisane jako bridge do docelowego provider `playerdb` (SQLite).

Wdrozenie:
- `logic/events/cash_in_assistant.py`:
  - fallback order ustawiony na `local_known_fallback` przed `offline_index`
    (zarowno dla trybu bez online lookup, jak i po nieudanym lookupu providerowym).
  - dopiete bridge labels pod przyszly provider `playerdb` (bez zmiany semantyki runtime):
    - `station_candidates_meta.source_status_bridge = playerdb_bridge`,
    - `station_candidates_meta.playerdb_bridge_used`,
    - `station_candidates_meta.source_order_contract`,
    - `edge_case_meta.source_status_bridge`,
    - reason alias `playerdb_bridge` obok `local_known_fallback`.
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md`:
  - nowy format statusow `[x]/[~]/[ ]`,
  - jawny roadmap `F16`.
  - decyzja lokalizacji DB:
    - glowna baza `player_local.db` -> `%APPDATA%/RenataAI/db/player_local.db`,
    - cache pomocniczy `playerdb` -> `%APPDATA%/RenataAI/cache/playerdb/*` (jesli potrzebny).
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md`:
  - dopisana kolejnosc zrodel i bridge do PLAYER_LOCAL_DB.

Testy:
- `py -m unittest tests.test_f16_playerdb_contract_and_order_bridge tests.test_f13_cash_in_provider_resilience tests.test_f14_quality_gates_and_smoke -v` PASS

### FLOW-F16-PLAYERDB-SCHEMA-AND-MIGRATIONS-01 (P0)
Status: DONE (kod + testy)

Cel:
- wdrozyc docelowa baze `player_local.db` (SQLite) z migracjami.

Zakres:
- tabele: `systems`, `stations`, `market_snapshots`, `trade_history`, `cashin_history`,
- wersjonowanie schematu + migracje,
- indeksy pod nearest/last-seen i retencje,
- coords systemow (`x,y,z`) w `systems` pod nearest query,
- stabilne klucze systemu:
  - `systems.system_address` (`SystemAddress`/`SystemId64` z Journal, jesli dostepne),
  - `stations.system_address` jako powiazanie/FK do systemu,
- klucz stacji pod snapshoty rynku:
  - `stations.market_id` (MarketID z Journal),
  - `market_snapshots.station_market_id` przypiete do tej samej stacji,
- freshness per warstwa:
  - system,
  - stacja/uslugi,
  - market snapshot,
- twardy kontrakt MVP `services_freshness_ts` w `stations` (last known services),
- `distance_ls` moze byc `unknown`; brak nie blokuje targetu (tylko confidence),
- schema snapshotow rynku pod pelny `Market.json` (lista wszystkich towarow na stacji + ceny/stock/demand).

Wdrozenie (FREE/PUB):
- `logic/player_local_db.py`:
  - dodano schema `v1` z `schema_migrations` i `PRAGMA user_version`,
  - `systems`: `system_address`, `system_id64`, coords `x/y/z`, indeksy nearest/last-seen,
  - `stations`: `system_address`, `market_id`, `services_freshness_ts`, `distance_ls_confidence`,
  - `market_snapshots`: `station_market_id`, `hash_sig`, indeks pod dedupe `(market_id, hash, snapshot_ts)`,
  - `market_snapshot_items` (row-per-commodity) + FK do snapshotu.
- `tests/test_f16_playerdb_schema_and_migrations.py`:
  - tworzenie schemy `v1`,
  - idempotentne migracje,
  - kontrakt kolumn i indeksow (`system_address`, `market_id`, snapshot `hash`).

Testy:
- `py -m unittest tests.test_f16_playerdb_schema_and_migrations tests.test_f16_playerdb_contract_and_order_bridge -v` PASS

### FLOW-F16-PLAYERDB-INGEST-MARKET-DOCKED-JUMPS-01 (P0)
Status: DONE (kod + testy)

Cel:
- zasilic `player_local.db` danymi observed-first z Journal i plikow gry.

Zakres:
- ingest `Docked/FSDJump/Location/Market.json`,
- upsert systemow/stacji,
- zapis `StarPos` z `Location/FSDJump` do `systems`,
- market snapshots + dedupe,
- zapis pelnego `Market.json`:
  - wszystkie towary,
  - `buy/sell price`,
  - `stock/supply`,
  - `demand`,
  - `snapshot_ts/freshness_ts`.

Wdrozenie (FREE/PUB):
- `logic/player_local_db.py`:
  - `ingest_journal_event(...)` dla `Location/FSDJump/CarrierJump/Docked`,
  - upsert `systems` (`StarPos`, `system_address`, `system_id64`),
  - upsert `stations` (`market_id`, `distance_ls`, `distance_ls_confidence`, `services_freshness_ts`),
  - `ingest_market_json(...)`:
    - snapshot `market_snapshots` + `market_snapshot_items`,
    - dedupe po `station_market_id + hash_sig`,
    - aktualizacja `freshness_ts` przy dedupe zamiast duplikowania snapshotu.
- `logic/event_handler.py`:
  - best-effort ingest playerdb z Journal i `Market.json` (bez zmiany semantyki runtime).

Testy:
- `py -m unittest tests.test_f16_playerdb_ingest_market_docked_jumps tests.test_f16_playerdb_schema_and_migrations tests.test_f16_playerdb_contract_and_order_bridge -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke -v` PASS

### FLOW-F16-PLAYERDB-CASHIN-HISTORY-AND-QUERY-01 (P1)
Status: DONE (kod + testy)

Cel:
- dopiac historie cash-in i query nearest/last-seen pod Cash-In i Personal Map.

Zakres (doprecyzowanie):
- query nearest oparte o coords systemow z `playerdb`,
- query zwraca jawne freshness/confidence dla danych stacyjnych i historii cash-in.

Wdrozenie (FREE/PUB):
- `logic/player_local_db.py`:
  - ingest `SellExplorationData`/`SellOrganicData` do `cashin_history`,
  - `query_cashin_history(...)` (UC/VISTA, last-seen),
  - `query_nearest_station_candidates(...)`:
    - nearest po `systems.x/y/z`,
    - fallback `last_seen` gdy brak coords,
    - filtr uslug `UC/Vista/Market`,
    - jawne `freshness_ts` i `confidence`.
- `logic/event_handler.py`:
  - best-effort ingest playerdb dla `SellExplorationData`/`SellOrganicData`.

Testy:
- `py -m unittest tests.test_f16_playerdb_cashin_history_and_query tests.test_f16_playerdb_ingest_market_docked_jumps tests.test_f16_playerdb_schema_and_migrations tests.test_f16_playerdb_contract_and_order_bridge -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke -v` PASS

### FLOW-F16-PLAYERDB-PROVIDER-FOR-CASHIN-AND-MAP-01 (P0)
Status: DONE (kod + testy)

Cel:
- uruchomic provider `source=playerdb` jako zrodlo #2 przed `offline_index`.

Zakres (doprecyzowanie):
- provider dla Cash-In i Personal Map zwraca:
  - nearest po coords (`x,y,z`),
  - kandydatow stacji z uslugami (`UC/Vista/Market`),
  - freshness/confidence per rekord,
  - source labels zgodne z polityka (`playerdb`, `offline_index`, `enriched`).

Wdrozenie (FREE/PUB):
- `logic/cash_in_station_candidates.py`:
  - shared provider `station_candidates_from_playerdb(...)` (Cash-In / future Map),
  - meta statusy `playerdb|playerdb_empty|playerdb_not_found|playerdb_error`.
- `logic/events/cash_in_assistant.py`:
  - realny provider `playerdb` wpiety przed `offline_index` i przed bridge `local_known_fallback`,
  - rozszerzone `station_candidates_meta` o pola `playerdb_*`,
  - `source_order_contract` zawiera `playerdb`.
- Kontrakt bridge z F16-1 zostaje zachowany (alias `playerdb_bridge` dla runtime cache), ale nie zastępuje juz realnego providera `playerdb`.

Testy:
- `py -m unittest tests.test_f16_playerdb_provider_for_cashin_and_map tests.test_f16_playerdb_cashin_history_and_query tests.test_f16_playerdb_ingest_market_docked_jumps tests.test_f16_playerdb_schema_and_migrations tests.test_f16_playerdb_contract_and_order_bridge -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke tests.test_f11_cash_in_payout_policy -v` PASS

### FLOW-F16-PLAYERDB-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (kod + testy)

Cel:
- potwierdzic brak regresji F11/F12/F13/F14/F15 oraz stabilny nearest target offline-first.

Zakres (doprecyzowanie):
- test ingestu `StarPos` -> coords w `systems`,
- test ingestu pelnego `Market.json` (wszystkie towary + ceny/stock/demand),
- test freshness labels/query dla `playerdb`,
- smoke cash-in + (future) map provider na danych observed-first.

Wdrozenie:
- `tests/test_f16_quality_gates_and_smoke.py`:
  - replay `Location/FSDJump/Docked/Market.json/SellExplorationData/SellOrganicData`,
  - smoke cash-in z `source=playerdb`,
  - nearest query fallback `last_seen`,
  - dedupe snapshotow `Market.json` przez `EventHandler.on_market_update(...)`.

Testy:
- `py -m unittest tests.test_f16_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f16_playerdb_provider_for_cashin_and_map tests.test_f16_playerdb_cashin_history_and_query tests.test_f16_playerdb_ingest_market_docked_jumps tests.test_f16_playerdb_schema_and_migrations tests.test_f16_playerdb_contract_and_order_bridge -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke tests.test_f11_cash_in_payout_policy -v` PASS

---

## Kolejnosc realizacji (F16 - PLAYER_LOCAL_DB FREE/PUB)

1. FLOW-F16-PLAYERDB-CONTRACT-AND-ORDER-BRIDGE-01 (P0) - DONE
2. FLOW-F16-PLAYERDB-SCHEMA-AND-MIGRATIONS-01 (P0) - DONE
3. FLOW-F16-PLAYERDB-INGEST-MARKET-DOCKED-JUMPS-01 (P0) - DONE
4. FLOW-F16-PLAYERDB-CASHIN-HISTORY-AND-QUERY-01 (P1) - DONE
5. FLOW-F16-PLAYERDB-PROVIDER-FOR-CASHIN-AND-MAP-01 (P0) - DONE
6. FLOW-F16-PLAYERDB-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## NOWE TICKETY (F17 - VOICE UX + CLIPBOARD GATE FREE/PUB)

Zrodlo:
- ustalenia produktowe (cash-in/tts/ppm) potwierdzone po testach runtime,
- `docs/Flow/private/docs/actions/ACTION_CASH_IN_ASSISTANT.md` (sekcja 23).

### FLOW-F17-CASH-IN-STATION-CLIPBOARD-GATE-BY-SYSTEM-01 (P0)
Status: DONE (kod + testy)

Cel:
- wymusic globalna zasade:
  - po `Ustaw trase` kopiujemy tylko system docelowy,
  - nazwe stacji kopiujemy dopiero po wejsciu do systemu docelowego.

Zakres:
- runtime:
  - blokada kopiowania stacji przed `current_system == target_system`,
  - auto-copy stacji po wejsciu do systemu celu.
- UX/TTS:
  - `Ustawiono cel trasy: {system}.`
  - `Stacja zostanie skopiowana po wejsciu do systemu docelowego.`
  - po wejsciu:
    - `Znalazlam cel stacyjny w {system}. Skopiowalam {stacja} do schowka.`

DoD:
- brak kopiowania stacji przed dotarciem do systemu celu,
- stacja kopiuje sie automatycznie po dotarciu,
- brak regresji `Copy next hop` i route intent.

Wdrozenie (FREE/PUB):
- `app/state.py`:
  - dodany kontrakt pending-copy stacji:
    - `set_pending_station_clipboard(...)`,
    - `get_pending_station_clipboard_snapshot()`,
    - `clear_pending_station_clipboard(...)`.
- `gui/app.py` (`on_cash_in_assistant_action`, `set_route`):
  - po `Ustaw trase` kopiowany jest system docelowy,
  - stacja:
    - kopiowana od razu tylko gdy gracz jest juz w systemie celu,
    - w innych przypadkach uzbrajana jako pending-copy na czas dolotu.
- `logic/events/navigation_events.py`:
  - gate `current_system == target_system` dla kopiowania stacji,
  - kopiowanie stacji przy dolocie + czyszczenie pending stanu.

Testy:
- `py -m unittest tests.test_f17_cash_in_station_clipboard_gate tests.test_f11_cash_in_route_handoff tests.test_f12_cash_in_route_handoff_real_target tests.test_route_awareness_state -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke tests.test_f15_quality_gates_and_smoke -v` PASS

### FLOW-F17-TTS-CLICK-EXPLORATION-SUMMARY-AND-CASH-IN-DECISION-01 (P1)
Status: DONE (kod + testy)

Cel:
- dodac brakujace potwierdzenia glosowe dla swiadomych akcji UI.

Zakres:
- klik `Podsumowanie eksploracji`:
  - `Podsumowanie gotowe. Dane warte {X} kredytow. {co_dalej}.`
- cash-in:
  - `Wybrano profil {SAFE|FAST|SECURE}.`
  - `Ustawiono cel trasy: {system}.`
  - `Skopiowalam nastepny hop: {system}.`
  - `Stacja zostanie skopiowana po wejsciu do systemu docelowego.`
- FAST/NEUTRON fallback:
  - `Nie znalazlam trasy neutronowej. Skopiowalam cel do schowka.`

DoD:
- kazda kluczowa akcja UI ma jasny, krotki komunikat TTS,
- brak floodu (cooldown/dedup respektowane).

Wdrozenie (FREE/PUB):
- `logic/events/exploration_summary.py`:
  - template TTS dla kliknietego podsumowania:
    - `Podsumowanie gotowe. Dane warte {X} Cr. {co_dalej}.`
- `gui/tabs/pulpit.py`:
  - wybor `SAFE/FAST/SECURE` wywoluje callback `set_intent`.
- `gui/app.py`:
  - dodane callouty TTS dla:
    - `set_intent` (`Wybrano profil ...`),
    - `set_route` (`Ustawiono cel...`, `Skopiowalam nastepny hop...`, `Stacja zostanie skopiowana...`),
    - `copy_next_hop` (`Skopiowalam nastepny hop...`).
  - FAST/NEUTRON fallback:
    - przy braku gotowej realnej trasy neutronowej:
      - `Nie znalazlam trasy neutronowej. Skopiowalam cel do schowka.`
  - anty-spam:
    - dedup per action/system + cooldown `1.5s`.
- Testy:
  - `tests/test_f17_tts_click_and_cash_in_decision.py`,
  - aktualizacja `tests/test_f4_exploration_summary_base.py`.

Testy:
- `py -m unittest tests.test_f17_tts_click_and_cash_in_decision tests.test_f4_exploration_summary_base -v` PASS
- `py -m unittest tests.test_f17_cash_in_station_clipboard_gate tests.test_f11_cash_in_route_handoff tests.test_f12_cash_in_route_handoff_real_target -v` PASS
- `py -m unittest tests.test_f14_quality_gates_and_smoke tests.test_f15_quality_gates_and_smoke -v` PASS

### FLOW-F17-TTS-HIGH-G-TRADE-FRESHNESS-PPM-RUNTIME-CRITICAL-01 (P1)
Status: DONE (kod + testy)

Cel:
- domknac brakujace komunikaty operacyjne Renaty.

Zakres:
- High-G:
  - komunikat:
    - `Wykryto wysokie przeciazenie grawitacyjne. Ogranicz opadanie.`
- Trade freshness:
  - dedykowany message_id stale/offline data:
    - `Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie.`
- PPM confirmations:
  - krotkie potwierdzenia dla:
    - `Ustaw cel`, `Przypnij`, `Kopiuj system`.
- Runtime critical:
  - krotkie komunikaty tylko dla zdarzen blokujacych (bez technicznego spamu).
- poza zakresem:
  - osobny TTS `wykryto log/brak logu` (deferred).

DoD:
- nowe message_id dopiete do policy map i renderer TTS,
- komunikaty sa zrozumiale i zgodne z polityka anti-spam.

Wdrozenie (FREE/PUB):
- `logic/events/high_g_warning.py`:
  - nowy handler high-g (journal + status),
  - prog `high_g_warning_threshold_g`,
  - komunikat:
    - `Wykryto wysokie przeciazenie grawitacyjne. Ogranicz opadanie.`
- `logic/event_handler.py`:
  - high-g handler podpiety do status/journal pipeline.
- `gui/tabs/spansh/trade.py`:
  - callout stale freshness przy `Sell Assist` advisory:
    - `Dane rynkowe sa nieswieze. Traktuj wynik orientacyjnie.`
- `gui/tabs/logbook.py`:
  - PPM confirmations:
    - `Ustaw cel`,
    - `Przypnij/Odepnij`,
    - `Kopiuj system`.
- `app/main_loop.py`:
  - runtime critical callout dla blokujacych problemow streamu journala.
- `logic/event_insight_mapping.py` + `logic/tts/text_preprocessor.py`:
  - dopiete message_id:
    - `MSG.HIGH_G_WARNING`,
    - `MSG.TRADE_DATA_STALE`,
    - `MSG.PPM_SET_TARGET`,
    - `MSG.PPM_PIN_ACTION`,
    - `MSG.PPM_COPY_SYSTEM`,
    - `MSG.RUNTIME_CRITICAL`.
- `config.py`:
  - dodane `high_g_warning_threshold_g` (domyslnie `2.0`).
- Testy:
  - `tests/test_f17_tts_operational_callouts.py`,
  - update `tests/test_event_insight_mapping.py`.

Testy:
- `py -m unittest tests.test_f17_tts_operational_callouts tests.test_event_insight_mapping tests.test_f6_voice_ethics_compliance tests.test_f17_tts_click_and_cash_in_decision tests.test_f17_cash_in_station_clipboard_gate -v` PASS
- `py -m unittest tests.test_f9_entry_context_menu_actions_and_move tests.test_sell_assist_ranking tests.test_sell_assist_intent_handoff -v` PASS

### FLOW-F17-VOICE-UX-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality gates + smoke)

Cel:
- domknac jakosc i regresje calego pakietu F17.

Zakres:
- quality gates:
  - clipboard gate (system-first, station-on-arrival),
  - UI click callouts (exploration summary + cash-in actions),
  - high-G + trade freshness + PPM + runtime-critical.
- smoke:
  - scenariusz ekspedycyjny:
    - `set route -> system copied -> station copied after arrival`.

DoD:
- PASS quality pack F17,
- PASS smoke bez regresji F11-F16/F5/F6.

Wdrozenie (FREE/PUB):
- dodany quality pack F17:
  - `tests/test_f17_quality_gates_and_smoke.py`
    - gate map/policy dla nowych `message_id` F17,
    - smoke e2e:
      - `set route -> system copied -> station copied after arrival`,
    - gate `High-G` + `runtime critical` (krotkie callouty operacyjne).

Testy:
- `py -m unittest tests.test_f17_quality_gates_and_smoke tests.test_f17_cash_in_station_clipboard_gate tests.test_f17_tts_click_and_cash_in_decision tests.test_f17_tts_operational_callouts tests.test_event_insight_mapping -v` PASS
- `py -m unittest tests.test_f15_quality_gates_and_smoke tests.test_f14_quality_gates_and_smoke tests.test_f13_quality_gates_and_smoke tests.test_f11_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance tests.test_f5_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F17 - VOICE UX + CLIPBOARD GATE FREE/PUB)

1. FLOW-F17-CASH-IN-STATION-CLIPBOARD-GATE-BY-SYSTEM-01 (P0) - DONE
2. FLOW-F17-TTS-CLICK-EXPLORATION-SUMMARY-AND-CASH-IN-DECISION-01 (P1) - DONE
3. FLOW-F17-TTS-HIGH-G-TRADE-FRESHNESS-PPM-RUNTIME-CRITICAL-01 (P1) - DONE
4. FLOW-F17-VOICE-UX-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## NOWE TICKETY (F18 - TTS UTF-8/PL DIACRITICS FREE/PUB)

### FLOW-F18-TTS-POLISH-DIACRITICS-AND-TEMPLATE-REGISTRY-01 (P0)
Status: DONE (kod + testy)

Cel:
- domknac jakosc polskich komunikatow TTS jako osobny pakiet:
  - centralny rejestr template'ow,
  - naprawa UTF-8/mojibake,
  - szybki audit diakrytykow.

Zakres:
- centralny rejestr template'ow TTS (single source of truth),
- normalizacja `raw_text`:
  - naprawa mojibake,
  - naprawa najczestszych form ASCII -> diakrytyki,
- audit testowy:
  - spojnosc registry <-> preprocessor,
  - kluczowe template'y z polskimi znakami,
  - szybki skan anty-mojibake dla glownych emiterow TTS.

Wdrozenie (FREE/PUB):
- dodany plik:
  - `logic/tts/message_templates.py`
    - centralny `TTS_TEMPLATE_REGISTRY`,
    - `allowed_message_ids()`,
    - `raw_text_first(...)`,
    - `template_for_message(...)`.
- `logic/tts/text_preprocessor.py`:
  - `ALLOWED_MESSAGES` pobierane z registry,
  - dodana warstwa `ASCII -> diakrytyki` dla najczestszych komunikatow,
  - fallback template'ow oparty o centralny rejestr.
- testy:
  - `tests/test_f18_tts_polish_templates_and_diacritics.py`,
  - update `tests/test_f17_tts_operational_callouts.py` (asercje odporne na diakrytyki).

Testy:
- `py -m unittest tests.test_f18_tts_polish_templates_and_diacritics tests.test_f17_tts_operational_callouts tests.test_f6_voice_ethics_compliance tests.test_f17_tts_click_and_cash_in_decision -v` PASS
- `py -m unittest tests.test_f17_quality_gates_and_smoke tests.test_event_insight_mapping tests.test_f5_voice_policy_contract tests.test_voice_capability_gate -v` PASS

---

## NOWE TICKETY (F19 - LOGBOOK CAPTAIN FEED V2 FREE/PUB)

Kontekst (uzgodnione zasady):
- Logbook feed ma cache w `%APPDATA%/RenataAI/cache/logbook`.
- `Wpisy` pozostaja osobno.
- Klasy zastepuja tagi w filtrach Logbooka.
- `Informacje` = tabela/panel szczegolow wybranego zdarzenia/grupy.
- `Podsumowanie` = agregaty dla aktualnego filtra.
- eventy `TECH` sa domyslnie ukryte, ale dostepne opcjonalnie.
- Pilnujemy czytelnosci zakladki Logbook (bez przeladowania UI trzema tabelami).

### FLOW-F19-LOGBOOK-FEED-CACHE-PERSISTENCE-AND-RESTORE-01 (P0)
Status: DONE (kod + testy)

Cel:
- zapewnic trwalosc Logbook feed po restarcie/crashu/utracie zasilania.

Zakres:
- cache feedu w `%APPDATA%/RenataAI/cache/logbook`,
- append-only zapis + limit/retencja,
- restore ostatnich N rekordow przy starcie Logbooka,
- brak zmiany semantyki `Wpisow`.

DoD:
- po restarcie Renaty feed Logbooka wraca (ostatnie N zdarzen),
- `Wpisy` i feed pozostaja osobnymi bytami.

Wdrozenie (FREE/PUB):
- dodany helper cache feedu:
  - `logic/logbook_feed_cache.py`
    - `append_logbook_feed_cache_item(...)`
    - `load_logbook_feed_cache(...)`
    - `clear_logbook_feed_cache(...)`
  - storage: `%APPDATA%/RenataAI/cache/logbook/feed.jsonl`
  - retencja po liczbie rekordow (tail do limitu feedu)
  - tolerancja uszkodzonej/urwanej linii JSONL po crashu
- `gui/tabs/logbook.py`:
  - restore feedu z cache przy starcie zakladki Logbook,
  - zapis cache przy doplywie eventu feedu,
  - czyszczenie cache po akcji `Wyczysc feed`.
- brak zmian semantyki `Wpisow` (Entry repository pozostaje osobno).

Testy:
- `py -m unittest tests.test_f19_logbook_feed_cache_persistence -v` PASS
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist tests.test_f8_quality_gates_and_smoke tests.test_f9_entry_context_menu_actions_and_move -v` PASS

### FLOW-F19-LOGBOOK-CAPTAIN-EVENT-COVERAGE-EXPANSION-01 (P0)
Status: DONE (kod + testy)

Cel:
- rozszerzyc coverage "logow kapitanskich" do realnego przebiegu sesji gry.

Zakres:
- rozszerzenie whitelist/mapowania eventow (minimum):
  - wejscie na orbite,
  - wejscie do pierscienia,
  - interdiction (proba + wynik ucieczki/niepowodzenia),
  - kolizje/spadek hull,
  - krotki przebieg starcia (combat),
  - exobio probki + zdarzenia sesji,
  - sprzedaz danych UC i Vista.
- fallback formattera:
  - event nie znika, dostaje minimalne `summary` + `raw_event`.

DoD:
- typowa sesja (skoki/ladowanie/exobio/sprzedaz/incydent/górnictwo) jest reprezentowana w Logbooku bez duzych luk,
- brak spamu technicznego w widoku domyslnym.

Wdrozenie (FREE/PUB):
- `logic/logbook_feed.py`:
  - rozszerzona whitelist eventow kapitanskich o:
    - `SupercruiseEntry`, `SupercruiseExit`, `ApproachBody`,
    - `Touchdown`, `Liftoff`,
    - `Interdicted`, `EscapeInterdiction`, `Interdiction`,
    - `UnderAttack`, `HullDamage`, `ShieldState`, `Died`.
  - rozszerzone summary formattery dla:
    - ladowanie/start/orbita/pierscien (best-effort przez `ApproachBody`),
    - interdiction (proba + ucieczka + wynik),
    - incydent/combat (atak, hull damage, tarcze, zgon),
    - sprzedaz danych UC/Vista z kwota `TotalEarnings` (jesli dostepna),
    - exobio `ScanOrganic` z rozroznieniem `ScanType` (best-effort).
  - rozszerzone chipsy feedu:
    - `INTERDICTOR`, `TARGET`, `CR`, `HULL`.
  - poprawka guardu TECH:
    - `ApproachBody` nie jest juz mylony z technicznym prefixem `APP`.
- fallback formattera zachowany:
  - eventy whitelisted bez pelnego formattera nadal tworza feed item z minimalnym `summary` + `raw_event`.

Testy:
- `py -m unittest tests.test_f19_logbook_captain_event_coverage -v` PASS
- `py -m unittest tests.test_f8_logbook_journal_feed_whitelist -v` PASS

### FLOW-F19-LOGBOOK-CLASSES-FILTER-AND-SORTABLE-FEED-01 (P1)
Status: DONE (kod + testy)

Cel:
- poprawic czytelnosc feedu Logbooka przy wiekszej liczbie eventow.

Zakres:
- filtry `Klasy` zamiast `Tagow` w Logbooku,
- klasy v1 (bez podklas):
  - `Nawigacja`, `Eksploracja`, `Exobio`, `Handel`, `Stacja`, `Incydent`, `Combat`, `TECH`,
- sortowanie tabeli feedu po naglowkach (jak w zakladkach Spansha),
- opcjonalny toggle `Pokaz TECH`.

DoD:
- user moze szybko odfiltrowac typ zdarzen i sortowac feed,
- `TECH` domyslnie ukryte.

Wdrozenie (FREE/PUB):
- `logic/logbook_feed.py`:
  - dodana klasyfikacja eventow feedu:
    - `classify_logbook_event(...)`,
  - `build_logbook_feed_item(...)` zwraca `event_class`.
- `gui/tabs/logbook.py` (zakladka `Logbook`):
  - dodany filtr `Klasy` (`Wszystkie (ALL)` + klasy v1),
  - dodany toggle `Pokaz TECH`,
  - tabela feedu rozszerzona o kolumne `Klasa`,
  - sortowanie po naglowkach tabeli:
    - `Czas`, `Klasa`, `Event`, `System`, `Miejsce`, `Podsumowanie`,
  - feed renderowany z listy rekordow (filter + sort), bez zmiany semantyki akcji PPM/chips,
  - status feedu pokazuje `visible/total`, klase i aktywny sort.

Testy:
- `py -m unittest tests.test_f19_logbook_classes_and_sort_contract -v` PASS
- `py -m unittest tests.test_f19_logbook_captain_event_coverage tests.test_f19_logbook_feed_cache_persistence tests.test_f8_logbook_journal_feed_whitelist tests.test_f8_quality_gates_and_smoke -v` PASS

### FLOW-F19-LOGBOOK-INFORMACJE-AND-PODSUMOWANIE-PANEL-01 (P0)
Status: DONE (kod + testy)

Cel:
- rozbudowac dolny panel Logbooka (obecne chipsy) bez psucia czytelnosci zakladki.

Zakres:
- `Informacje`:
  - szczegoly wybranego zdarzenia/grupy (czytelne wiersze opisowe),
- `Podsumowanie`:
  - agregaty dla aktualnego filtra (np. skoki/ladowania/kolizje/UC/Vista),
- integracja z obecnym panelem chips/nav helper (bez tworzenia 3 duzych tabel obok siebie).

DoD:
- jedno okno Logbook pozostaje czytelne,
- user widzi szczegoly i agregaty bez przechodzenia do innych zakladek.

Wdrozenie (FREE/PUB):
- `logic/logbook_feed.py`:
  - dodane helpery panelu:
    - `build_logbook_info_rows(feed_item)` (best-effort tabela `Informacje`),
    - `build_logbook_summary_snapshot(feed_items)` (agregaty `Podsumowanie` dla aktualnego filtra).
- `gui/tabs/logbook.py`:
  - dolny panel Logbooka rozbudowany o:
    - `Informacje (zdarzenie)` (tabela key/value),
    - `Podsumowanie (aktualny filtr)` (agregaty tekstowe),
    - zachowane `Chips nawigacyjne` jako lekki helper akcji.
  - `Informacje` odswiezane przy wyborze eventu i czyszczeniu feedu,
  - `Podsumowanie` odswiezane przy filtrach/sortowaniu/renderze feedu,
  - bez zmiany semantyki `Wpisow` i bez usuwania akcji PPM/chips.

Zakres agregatow (v1):
- liczba eventow (visible/filtered context),
- skoki, ladowania, dokowania,
- incydenty hull, interdiction + ucieczki,
- sprzedaz UC, sprzedaz Vista, suma laczna (best-effort po `TotalEarnings`/`Value`).

Testy:
- `py -m unittest tests.test_f19_logbook_info_and_summary_panel_contract -v` PASS
- `py -m unittest tests.test_f19_logbook_classes_and_sort_contract tests.test_f19_logbook_captain_event_coverage tests.test_f19_logbook_feed_cache_persistence tests.test_f8_logbook_journal_feed_whitelist tests.test_f8_quality_gates_and_smoke -v` PASS

### FLOW-F19-LOGBOOK-QUALITY-GATES-AND-JOURNAL-REPLAY-SMOKE-01 (P0)
Status: DONE (quality gates + smoke)

Cel:
- domknac jakosc i regresje pakietu F19.

Zakres:
- test restore cache feedu,
- testy klas/filter/sort,
- testy formatowania `summary` + `info_rows`,
- journal replay smoke:
  - skoki,
  - ladowanie,
  - exobio,
  - sprzedaz UC/Vista,
  - incydent/interdiction.

DoD:
- PASS quality pack F19,
- PASS replay smoke bez regresji F8/F9/F17.

Wdrozenie (FREE/PUB):
- dodany quality pack F19:
  - `tests/test_f19_quality_gates_and_smoke.py`
    - quality gate: kontrakt feed item (`event_class`, `summary`, `chips`, `raw_event`),
    - quality gate: helpery `Informacje` + `Podsumowanie`,
    - smoke: syntetyczny journal replay (`Location/FSDJump/Touchdown/ScanOrganic/HullDamage/Interdicted/EscapeInterdiction/Docked/SellExplorationData/SellOrganicData`)
      -> feed -> cache -> restore -> agregaty `Podsumowanie`.

Testy:
- `py -m unittest tests.test_f19_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f19_logbook_feed_cache_persistence tests.test_f19_logbook_captain_event_coverage tests.test_f19_logbook_classes_and_sort_contract tests.test_f19_logbook_info_and_summary_panel_contract tests.test_f8_logbook_journal_feed_whitelist tests.test_f8_quality_gates_and_smoke tests.test_f9_entry_context_menu_actions_and_move -v` PASS

### FLOW-F19-LOGBOOK-TABLE-UX-SPANSH-POLISH-01 (P1)
Status: DONE (kod + testy)

Cel:
- dopolerowac UX tabel Logbooka do stylu i zachowania zblizonego do zakladek Spansha,
  bez zmiany logiki feedu/filtra/agregatow.

Zakres:
- styl tabel feedu/informacji/chipsow jak w Spanshu (Treeview globalny),
- widoczny stan sortowania feedu (`^`/`v`) w naglowkach,
- wspolny helper tworzenia tabel Logbooka (spojnosc i mniej duplikacji).

DoD:
- feed Logbooka ma widoczny aktywny sort i kierunek,
- dolne tabele Logbooka maja styl zgodny z tabelami Spansha,
- brak regresji F19-3/F19-4/F19-5.

Wdrozenie (FREE/PUB):
- `gui/tabs/logbook.py`:
  - dodany helper `_create_spansh_like_treeview(...)` (wrapper `ttk.Treeview` z `style=\"Treeview\"`),
  - feed Logbooka przepiety na helper + globalny styl tabel,
  - `Informacje` i `Chips nawigacyjne` przepiete na helper + globalny styl tabel,
  - dodane `_logbook_feed_header_labels`,
  - dodane `_update_logbook_feed_sort_indicators()` z markerem `^` / `v`,
  - `_set_logbook_feed_sort(...)` aktualizuje naglowki sortu przed renderem.
- kontrakt testu F19-3 zaktualizowany pod nowy sposob renderowania naglowkow
  (helper + updater markerow zamiast twardych literalow `heading(\"time\", ...)`).

Testy:
- `py -m unittest tests.test_f19_logbook_classes_and_sort_contract tests.test_f19_logbook_info_and_summary_panel_contract tests.test_f19_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F19 - LOGBOOK CAPTAIN FEED V2 FREE/PUB)

1. FLOW-F19-LOGBOOK-FEED-CACHE-PERSISTENCE-AND-RESTORE-01 (P0) - DONE
2. FLOW-F19-LOGBOOK-CAPTAIN-EVENT-COVERAGE-EXPANSION-01 (P0) - DONE
3. FLOW-F19-LOGBOOK-CLASSES-FILTER-AND-SORTABLE-FEED-01 (P1) - DONE
4. FLOW-F19-LOGBOOK-INFORMACJE-AND-PODSUMOWANIE-PANEL-01 (P0) - DONE
5. FLOW-F19-LOGBOOK-QUALITY-GATES-AND-JOURNAL-REPLAY-SMOKE-01 (P0) - DONE
6. FLOW-F19-LOGBOOK-TABLE-UX-SPANSH-POLISH-01 (P1) - DONE

---

## NOWE TICKETY (F20 - PERSONAL GALAXY MAP MVP/TKINTER FREE/PUB)

Zrodlo:
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC.md`
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC_TKINTER_APPEND.md` (scalone do glownego speca)
- `docs/Flow/private/Features2/PLAYER_LOCAL_DB_PLAN.md` (F16 DONE)

Cel fazy:
- uruchomic pierwsze MVP mapy osobistej gracza (Tkinter), oparte o `playerdb`,
  bez naruszania semantyki Cash-In i bez ciezkiego 3D.

### FLOW-F20-MAP-CONTRACT-AND-DATA-PROVIDER-ADAPTERS-01 (P0)
Status: DONE (kod + testy)

Cel:
- zrobic warstwe adapterow danych dla mapy nad `playerdb` (bez SQL w UI).

Zakres:
- `MapDataProvider` (MVP) z metodami:
  - `get_system_nodes(time_range, source_filter)`,
  - `get_edges(time_range)`,
  - `get_stations_for_system(system_id/system_address)`,
  - `get_market_last_seen(market_id, limit)`,
  - `get_top_prices(commodity, mode, time_range, freshness_filter)`.
- kontrakt rekordow mapy:
  - `source/freshness/confidence` zgodne z PlayerDB/Cash-In.

DoD:
- UI mapy moze pobierac dane przez adapter, bez bezposrednich zapytan SQL.

Wdrozenie (FREE/PUB):
- dodany adapter `logic/personal_map_data_provider.py`:
  - `MapDataProvider.get_system_nodes(...)`,
  - `MapDataProvider.get_edges(...)` (best-effort kontrakt/meta; jawne `reason=playerdb_jumps_not_ingested` w baseline F20-1),
  - `MapDataProvider.get_stations_for_system(...)`,
  - `MapDataProvider.get_market_last_seen(...)`,
  - `MapDataProvider.get_top_prices(...)`.
- kontrakt rekordow mapy zwraca jawnie:
  - `source`,
  - `freshness_ts`,
  - `confidence`,
  - oraz meta zapytan (`time_range`, `source_filter`, `freshness_filter`, `query reason`).
- brak SQL w UI (adapter jest warstwa posrednia nad `playerdb_connection`).

Testy:
- `py -m unittest tests.test_f20_map_data_provider_adapters -v` PASS
- `py -m unittest tests.test_f16_playerdb_provider_for_cashin_and_map tests.test_f16_playerdb_cashin_history_and_query tests.test_f16_quality_gates_and_smoke -v` PASS

### FLOW-F20-MAP-TKINTER-SHELL-LAYOUT-AND-CANVAS-PAN-ZOOM-01 (P0)
Status: DONE (kod + testy)

Cel:
- postawic okno/zakladke mapy w ukladowi 3-panelowym z dzialajacym canvas pan+zoom.

Ustalenie UX:
- mapa jest podzakladka w `Dziennik`, obok `Logbook` (nie osobna glowna zakladka aplikacji).

Zakres:
- layout:
  - osadzenie w `Dziennik -> Mapa`,
  - `left_frame` (filtry),
  - `center_frame` (`Canvas` mapy),
  - `right_frame` (szczegoly),
- pan (`ButtonPress/B1-Motion/ButtonRelease`),
- zoom do kursora (`MouseWheel`, clamp skali),
- `Reset zoom`, `Center on current system` (stub/placeholder dopuszczalny na tym etapie).

DoD:
- mapa otwiera sie bez crasha, pan/zoom dzialaja plynnie na pustym i prostym zestawie danych.

Wdrozenie (FREE/PUB):
- dodany widget `gui/tabs/journal_map.py`:
  - `JournalMapTab` (shell 3-panelowy + `Canvas` mapy),
  - pan (`ButtonPress/B1-Motion/ButtonRelease`),
  - zoom do kursora (`MouseWheel`, clamp skali),
  - `Reset zoom`,
  - `Center on current system` (best-effort po `app_state.current_star_pos`, fallback status),
  - placeholder right-panel (`System details`, `Station details`, `Trade compare`) pod kolejne tickety F20.
- integracja z `Dziennik`:
  - `gui/tabs/logbook.py`:
    - dodana podzakladka `Mapa` obok `Wpisy` i `Logbook`,
    - zapis/przywracanie aktywnej podzakladki `entries|feed|map` w UI state.

Testy:
- `py -m unittest tests.test_f20_map_tkinter_shell_and_pan_zoom_contract -v` PASS
- `py -m unittest tests.test_f20_map_data_provider_adapters tests.test_f19_logbook_classes_and_sort_contract tests.test_f19_quality_gates_and_smoke -v` PASS
- Post-implement tweak:
  - zakres zoomu mapy rozszerzony do `0.10 .. 6.0` (commit `[PUB] Expand personal map zoom range to 0.10-6.0`).

### FLOW-F20-MAP-TRAVEL-NODES-AND-JUMPS-RENDERER-01 (P0)
Status: DONE (kod + testy)

Cel:
- pokazac pierwsza realna warstwe mapy: systemy odwiedzone + krawedzie skokow.

Zakres:
- renderer Canvas:
  - `create_line` dla jumps (edges),
  - `create_oval` dla systemow (nodes),
  - `create_text` dla etykiet przy odpowiednim zoomie,
- tagowanie Canvas:
  - `node:<id>`, `edge:<from>-<to>`,
- MVP layout:
  - `travel-path layout` (domyslny),
  - coords-view odlozony (later).

DoD:
- po danych z `playerdb` widac graf podrozy (systemy + skoki) i brak lagow przy typowym wolumenie MVP.

Wdrozenie (FREE/PUB):
- `gui/tabs/journal_map.py`:
  - `reload_from_playerdb()` laduje warstwe Travel przez `MapDataProvider`,
  - domyslny `travel-path layout` (uklad sekwencyjny / czytelny dla podrozy),
  - renderer Canvas rysuje:
    - nodes (`create_oval`) + label (przy zoom threshold),
    - edges (`create_line`),
    - tagi Canvas:
      - `map_node`, `node:<id>`,
      - `map_edge`, `edge:<from>-<to>`.
  - fallback krawedzi:
    - gdy provider `get_edges()` zwraca brak danych (baseline bez ingestu `jumps`),
    - renderer buduje krawedzie sekwencyjne po chronologii `last_seen/first_seen` (`sequential_fallback`).
  - `status` mapy jawnie komunikuje fallback krawedzi.
- cleanup runtime:
  - cancel pending `after(...)` callbackow w `destroy()` (brak szumu `invalid command name` w testach Tkinter).

Testy:
- `py -m unittest tests.test_f20_map_travel_nodes_and_jumps_renderer_contract -v` PASS
- `py -m unittest tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_data_provider_adapters -v` PASS
- `py -m unittest tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke -v` PASS

### FLOW-F20-MAP-SYSTEM-STATION-DRILLDOWN-PANELS-01 (P0)
Status: DONE

Cel:
- umozliwic drilldown: klik system -> lista stacji -> szczegoly stacji i last-seen market snapshots.

Zakres:
- click/double-click na node:
  - selekcja,
  - center on node (double-click),
- prawy panel:
  - `System details` (visit_count, last_seen),
  - lista stacji (`Treeview`),
  - `Station details` (UC/Vista/Market + freshness/confidence),
  - ostatnie snapshoty rynku (limit N).

DoD:
- user moze kliknac system i zobaczyc stacje + dane stacyjne/rynkowe z `playerdb`.
- Wdrozone (2026-02-22):
  - klik node na canvas (`map_node`) wybiera system i odswieza `System details`,
  - double-click node wybiera i centruje widok na systemie,
  - lista stacji w prawym panelu ladowana z `MapDataProvider.get_stations_for_system(...)`,
  - wybór stacji laduje `Station details` + ostatnie snapshoty rynku z `get_market_last_seen(...)`,
  - auto-select pierwszej stacji po wyborze systemu (czytelny drilldown bez dodatkowego klikniecia).
- Testy:
  - `py -m unittest tests.test_f20_map_system_station_drilldown_panels_contract -v` PASS
  - `py -m unittest tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_data_provider_adapters -v` PASS

### FLOW-F20-MAP-FILTERS-LAYERS-FRESHNESS-SOURCE-01 (P1)
Status: DONE

Cel:
- od razu utrzymac czytelnosc mapy przez filtry warstw i freshness.

Zakres:
- lewy panel:
  - warstwy `Travel/Stations/Trade/Cash-In`,
  - zakres czasu `7d/30d/all`,
  - freshness `<=6h/<=24h/<=7d/any`,
  - source `observed-only/include enriched`,
- redraw mapy po zmianie filtrow,
- `No data`/empty-state zamiast pustego/crashujacego UI.

DoD:
- filtry dzialaja i zmieniaja widok bez crasha, z czytelnym stanem pustym.
- Wdrozone (2026-02-22):
  - `freshness` filtr realnie filtruje systemy (`nodes`) i snapshoty rynku w drilldown,
  - warstwy `Stations/Trade/Cash-In` renderuja overlaye na node'ach mapy (`layer_stations`, `layer_trade`, `layer_cashin`),
  - status mapy pokazuje aktywne warstwy + filtry `time/freshness/source`,
  - empty-state i status po filtrach sa czytelne (`brak danych po filtrach`, `Travel wylaczona`),
  - right panel respektuje warstwe `Stations` (bez crasha, jawny komunikat).
- Testy:
  - `py -m unittest tests.test_f20_map_filters_layers_freshness_source_contract -v` PASS
  - `py -m unittest tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_data_provider_adapters -v` PASS
  - `py -m unittest tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke -v` PASS

### FLOW-F20-MAP-TRADE-COMPARE-ONE-COMMODITY-HIGHLIGHT-01 (P1)
Status: DONE

Cel:
- dostarczyc pierwsza realna funkcje decyzyjna mapy na danych lokalnych (`playerdb`).

Zakres:
- `Trade compare` w prawym panelu:
  - wybor commodity,
  - `Highlight`,
  - top buy/sell (last seen) + age/confidence,
- podswietlanie odpowiadajacych systemow na mapie (węzly systemow; stacje pozostaja w panelu).

DoD:
- dla 1 towaru mapa pokazuje top buy/sell na lokalnych snapshotach z freshness/confidence.
- Wdrozone (2026-02-22):
  - `Trade compare` korzysta z `playerdb` (`get_known_commodities`, `get_top_prices`),
  - combobox towarow uzupelniany lokalnymi commodity z `market_snapshot_items`,
  - `Highlight` wypelnia panel top `SELL/BUY` (last seen) z `age/confidence`,
  - odpowiadajace systemy sa podswietlane na mapie (`layer_trade_highlight`),
  - highlight respektuje warstwe `Trade` (dane sa liczone, ale overlay znika gdy warstwa off).
- Testy:
  - `py -m unittest tests.test_f20_map_trade_compare_one_commodity_highlight_contract -v` PASS
  - `py -m unittest tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_data_provider_adapters -v` PASS
  - `py -m unittest tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke -v` PASS

### FLOW-F20-MAP-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE

Cel:
- domknac MVP mapy testami kontraktu i smoke UI/data provider.

Zakres:
- testy adaptera `MapDataProvider`,
- smoke renderu nodes/edges na danych z `playerdb`,
- smoke click -> right panel details,
- smoke pan/zoom + filtry (bez crasha).

DoD:
- PASS quality pack F20 bez regresji F16 (playerdb) i F11/F14 (cash-in).
- Wdrozone (2026-02-22):
  - dedykowany pack `tests/test_f20_quality_gates_and_smoke.py`,
  - smoke UI mapy: render Travel -> drilldown -> filtry -> Trade compare/highlight,
  - quality gate providera mapy (`playerdb`) dla nodes/stations/market/commodity top.
- Dodatkowo (maintenance testow):
  - `tests/test_f14_quality_gates_and_smoke.py` odizolowany od `playerdb` mockiem, aby sprawdzal offline-index (zakres F14) po zmianie source-order w F16.
- Testy:
  - `py -m unittest tests.test_f20_quality_gates_and_smoke -v` PASS
  - `py -m unittest tests.test_f20_map_data_provider_adapters tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_trade_compare_one_commodity_highlight_contract -v` PASS
  - `py -m unittest tests.test_f19_quality_gates_and_smoke -v` PASS
  - `py -m unittest tests.test_f16_quality_gates_and_smoke tests.test_f11_cash_in_payout_policy tests.test_f14_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F20 - PERSONAL GALAXY MAP MVP/TKINTER FREE/PUB)

1. FLOW-F20-MAP-CONTRACT-AND-DATA-PROVIDER-ADAPTERS-01 (P0) - DONE
2. FLOW-F20-MAP-TKINTER-SHELL-LAYOUT-AND-CANVAS-PAN-ZOOM-01 (P0) - DONE
3. FLOW-F20-MAP-TRAVEL-NODES-AND-JUMPS-RENDERER-01 (P0) - DONE
4. FLOW-F20-MAP-SYSTEM-STATION-DRILLDOWN-PANELS-01 (P0) - DONE
5. FLOW-F20-MAP-FILTERS-LAYERS-FRESHNESS-SOURCE-01 (P1) - DONE
6. FLOW-F20-MAP-TRADE-COMPARE-ONE-COMMODITY-HIGHLIGHT-01 (P1) - DONE
7. FLOW-F20-MAP-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## Faza 21 (Personal Galaxy Map UX Polish - FREE/PUB, po F20 MVP)

Cel:
- poprawic ergonomie i czytelnosc mapy w `Dziennik -> Mapa` bez zmiany semantyki danych (`playerdb`) i bez rozbijania domknietego MVP F20.

Zasady:
- mapa pozostaje podzakladka `Dziennik -> Mapa`,
- PPM jest asystentem (akcje przygotowuja cel/trase, nie autopilot),
- na tym etapie odpuszczamy:
  - `Przypnij/Odepnij`,
  - `Odswiez dane systemu` (future dla online enrichment).

### FLOW-F21-MAP-CURSOR-AND-SELECTION-HIGHLIGHTS-01 (P0)
Status: DONE

Cel:
- poprawic podstawowy UX mapy: kursor, selekcje i aktualna pozycje gracza.

Zakres:
- kursor mapy:
  - domyslnie systemowy `arrow`,
  - podczas aktywnego pan (LPM drag) -> `fleur`/`hand2`,
  - po puszczeniu LPM -> powrot do `arrow`.
- highlight node:
  - wybrany system = biala otoczka (2-3 px, czytelny kontrast),
  - aktualny system gracza = zielona otoczka,
  - wspolistnienie obu stanow (selected + current).
- priorytet wizualny:
  1. selected
  2. current position
  3. badge warstw
  4. labels

DoD:
- domyslny kursor mapy to `arrow`,
- kursor pan jest widoczny tylko podczas drag,
- selected/current highlight sa czytelne i nie gryza sie wizualnie.
- Wdrozone (2026-02-23):
  - mapa uzywa kursora `arrow` domyslnie,
  - kursor `fleur` wlacza sie dopiero podczas `B1-Motion` (aktywny drag/pan),
  - release i klik/double-click node resetuja kursor do `arrow`,
  - selected node ma biala otoczke z kontrastowym cieniem,
  - current system gracza ma zielona otoczke,
  - selected + current moga wspolistniec na tym samym node.
- Testy:
  - `py -m unittest tests.test_f21_map_cursor_and_selection_highlights_contract -v` PASS
  - `py -m unittest tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract -v` PASS

### FLOW-F21-MAP-CONTEXT-MENU-PPM-ACTIONS-01 (P0)
Status: DONE

Cel:
- dodac menu PPM na node mapy z najwazniejszymi akcjami operatorskimi.

Zakres:
- PPM na system/node:
  - `Ustaw cel -> Trasa zwykla`
  - `Ustaw cel -> Trasa neutronowa`
  - `Kopiuj cel`
  - `Dodaj wpis -> [lista kategorii]`
  - `Dodaj wpis i edytuj`
  - `Wycentruj na tym systemie`
  - `Pokaz tylko ten system w panelu`
- `Trasa neutronowa`:
  - uruchamia neutron planner,
  - nie przelacza do zakladki Spansh/Neutron.
- disabled states:
  - wyszarzone opcje gdy brak sensu / brak danych,
  - krotki powod w statusie UI.

Poza zakresem (F21):
- `Przypnij/Odepnij`,
- `Odswiez dane systemu`.

DoD:
- PPM dziala na kliknieciu node,
- akcje respektuja model asystenta (bez autopilota),
- neutron route z PPM nie zmienia aktywnej zakladki Spansha.
- Wdrozone (2026-02-23):
  - PPM na node mapy z akcjami:
    - `Ustaw cel -> Trasa zwykla`
    - `Ustaw cel -> Trasa neutronowa`
    - `Kopiuj cel`
    - `Dodaj wpis` (submenu kategorii)
    - `Dodaj wpis i edytuj`
    - `Wycentruj na tym systemie`
    - `Pokaz tylko ten system w panelu`
  - `Trasa neutronowa` uruchamia planner bez przelaczania zakladki Spansh/Neutron,
  - disabled states dla brakujacego kontekstu / ownera wpisow / zajetego plannera.
- Wdrozone (spiecie z Logbook):
  - callbacki `map_get_available_entry_categories()` i `map_create_entry_for_system(...)` w `LogbookTab`.
- Testy:
  - `py -m unittest tests.test_f21_map_context_menu_ppm_actions_contract -v` PASS
  - `py -m unittest tests.test_f21_map_cursor_and_selection_highlights_contract -v` PASS
  - `py -m unittest tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_trade_compare_one_commodity_highlight_contract -v` PASS

### FLOW-F21-MAP-ACTION-BADGES-LAYERS-AND-LEGEND-01 (P1)
Status: DONE

Cel:
- zwiekszyc ilosc informacji na mapie bez efektu "choinki".

Zakres:
- markery akcji jako badge/doty/ikony (nie osobna otoczka per akcja),
- rozbudowa/ustabilizowanie warstw:
  - `Travel`, `Stations`, `Trade`, `Cash-In`,
  - `Exobio`, `Exploration`, `Incidents`, `Combat`,
  - opcjonalnie `Missions` (jesli dane sa dostepne).
- legenda w lewym panelu (dol):
  - opis otoczek i badge,
  - zwijana sekcja `Pokaz/Ukryj`,
  - aktualizacja pod aktywne warstwy (mniej szumu).
- zoom-gated czytelnosc:
  - przy malym zoom mniej etykiet/szczegolow,
  - przy wiekszym zoom wiecej badge/label.

DoD:
- legenda tlumaczy active overlays,
- markery akcji sa czytelne i nie psuja selekcji/current highlight,
- warstwy da sie wlaczac/wylaczac bez crasha i bez chaosu wizualnego.

Wdrozenie:
- rozszerzone warstwy mapy: `Exobio`, `Exploration`, `Incidents`, `Combat`,
- badge/doty akcji (bez dodatkowych otoczek) + zachowany priorytet `selected/current`,
- legenda w lewym panelu (sekcja zwijana `Pokaz/Ukryj`, opis tylko aktywnych warstw),
- zoom-gated badge/label readability (maly zoom = mniej badge/etykiet),
- `Exobio/Exploration` oparte o realny `playerdb/cashin_history` (Vista/UC),
- `Incidents/Combat` future-ready (warstwa + legenda, brak danych w obecnym schema PlayerDB).

Testy:
- `py -m unittest tests.test_f21_map_action_badges_layers_and_legend_contract -v` PASS
- `py -m unittest tests.test_f20_map_data_provider_adapters tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_trade_compare_one_commodity_highlight_contract tests.test_f21_map_cursor_and_selection_highlights_contract tests.test_f21_map_context_menu_ppm_actions_contract -v` PASS

### FLOW-F21-MAP-TRADE-COMPARE-V2-MULTISELECT-MODAL-01 (P1)
Status: DONE

Cel:
- zastapic surowy combobox towarow czytelniejszym wyborem wielopozycyjnym.

Zakres:
- przycisk `Wybierz towary...`,
- osobne okno/modal wyboru `commodities` (z `Market.json`, nie materials):
  - wyszukiwarka,
  - tabela w stylu Renaty/Spansh,
  - checkboxy,
  - `Zaznacz wszystkie` / `Wyczysc`,
  - `Akceptuj`.
- po akceptacji:
  - `Trade compare` pokazuje wybrane towary,
  - highlight mapy dziala dla aktywnego wiersza/wybranego towaru.

DoD:
- modal wyboru towarow jest czytelny i zgodny wizualnie z tabelami Renaty,
- wielowybor nie psuje obecnego `playerdb` provider flow,
- highlight pozostaje stabilny przy zmianie aktywnego wiersza.

Wdrozenie:
- przycisk `Wybierz towary...` otwiera modal (`Toplevel`) z:
  - wyszukiwarka,
  - tabela `Treeview` (styl Renaty/Spansh),
  - pseudo-checkboxy `[x]/[ ]`,
  - `Zaznacz wszystkie` / `Wyczysc` / `Akceptuj` / `Anuluj`.
- po akceptacji:
  - `Trade compare` renderuje wiele towarow w jednej tabeli (kolumna `Towar`),
  - zapamietywany jest koszyk wybranych towarow,
  - highlight mapy sterowany jest aktywnym wierszem (towar z zaznaczonego wiersza).
- zachowana kompatybilnosc F20:
  - `_run_trade_compare(<commodity>)` nadal dziala (single commodity),
  - ukryty combobox zostaje jako compatibility path.

Testy:
- `py -m unittest tests.test_f21_map_trade_compare_v2_multiselect_modal_contract -v` PASS
- `py -m unittest tests.test_f20_map_trade_compare_one_commodity_highlight_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f21_map_action_badges_layers_and_legend_contract tests.test_f21_map_context_menu_ppm_actions_contract tests.test_f21_map_cursor_and_selection_highlights_contract -v` PASS
- `py -m unittest tests.test_f20_map_data_provider_adapters tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract -v` PASS

### FLOW-F21-MAP-TOOLTIPS-AND-UX-QUALITY-GATES-01 (P1)
Status: DONE

Cel:
- domknac polish UX mapy testami i drobnymi zachowaniami czytelnosci.

Zakres:
- hover tooltip na node (krotki, bez spamu):
  - system,
  - `last seen`,
  - liczba stacji,
  - aktywne badge/warstwy.
- quality gates / smoke F21:
  - kursor pan vs `arrow`,
  - selected/current highlight coexist,
  - PPM enabled/disabled states,
  - legenda warstw,
  - Trade Compare v2 modal + highlight,
  - brak flicker / brak crasha przy hover+zoom.

DoD:
- PASS pack F21 bez regresji F20/F19/F16,
- UX mapy jest czytelny i przewidywalny przy normalnej pracy (klik, pan, hover, filtry).

Wdrozenie:
- hover tooltip na node (canvas overlay, bez osobnego okna):
  - `System`,
  - `Last seen`,
  - liczba stacji,
  - aktywne warstwy/badge dla node.
- tooltip ukrywa sie przy:
  - pan (`press/drag/release`),
  - zoom,
  - PPM,
  - redraw/leave canvas,
  aby uniknac "duchow" i szumu UX.
- quality/smoke pack F21:
  - hover + zoom,
  - PPM state setup,
  - Trade Compare v2 modal + highlight aktywnego wiersza.

Testy:
- `py -m unittest tests.test_f21_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f21_map_cursor_and_selection_highlights_contract tests.test_f21_map_context_menu_ppm_actions_contract tests.test_f21_map_action_badges_layers_and_legend_contract tests.test_f21_map_trade_compare_v2_multiselect_modal_contract tests.test_f20_map_data_provider_adapters tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f20_map_travel_nodes_and_jumps_renderer_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_trade_compare_one_commodity_highlight_contract -v` PASS
- `py -m unittest tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F21 - PERSONAL GALAXY MAP UX POLISH FREE/PUB)

1. FLOW-F21-MAP-CURSOR-AND-SELECTION-HIGHLIGHTS-01 (P0) - DONE
2. FLOW-F21-MAP-CONTEXT-MENU-PPM-ACTIONS-01 (P0) - DONE
3. FLOW-F21-MAP-ACTION-BADGES-LAYERS-AND-LEGEND-01 (P1) - DONE
4. FLOW-F21-MAP-TRADE-COMPARE-V2-MULTISELECT-MODAL-01 (P1) - DONE
5. FLOW-F21-MAP-TOOLTIPS-AND-UX-QUALITY-GATES-01 (P1) - DONE

---

## Faza 22 (Personal Galaxy Map follow-up fixes / usability - FREE/PUB, po F21)

Cel:
- domknac wykryte po F21 problemy ergonomii i stabilnosci mapy bez zmiany semantyki danych (`playerdb`) i bez przebudowy F20/F21 runtime.

Zakres:
- persystencja kontekstu mapy (warstwy/filtry/stan legendy),
- naprawa `Center on current system` dla aktualnego trybu renderu (`travel-path layout`),
- dopracowanie modala `Wybierz towary...` (scrollbar + filtr "Pokaż tylko dostępne na stacji"),
- quality gates / smoke dla nowych zachowan.

### FLOW-F22-MAP-VIEW-STATE-PERSISTENCE-01 (P0)
Status: DONE

Cel:
- zapamietywac kontekst `Dziennik -> Mapa` po restarcie programu.

Zakres:
- persystencja do UI state / config:
  - warstwy mapy (`Travel`, `Stations`, `Trade`, `Cash-In`, `Exobio`, `Exploration`, `Incidents`, `Combat`),
  - filtry mapy (`time_range`, `freshness`, `source`),
  - stan legendy (`Pokaz/Ukryj`).
- restore stanu po otwarciu `Dziennik -> Mapa` przed pierwszym `reload_from_playerdb()`.
- brak regresji dla zapamietywania aktywnej podzakladki `entries|feed|map`.

DoD:
- po restarcie Renaty warstwy i filtry mapy wracaja do ostatniego stanu,
- legenda wraca do poprzedniego stanu zwijania,
- brak crasha przy brakujacym/legacy state.

Wdrozenie (2026-02-23):
- `JournalMapTab` eksportuje i aplikuje stan UI mapy (`layers`, `filters`, `legend.collapsed`),
- `LogbookTab` zapisuje stan mapy do `ui_state.journal.map`,
- restore stanu mapy wykonywany po zbudowaniu zakladki `Mapa` i przed kolejnymi interakcjami użytkownika,
- zmiany warstw/filtrów/legendy notify ownera (`LogbookTab`) i triggerują persist UI state.

Testy:
- `py -m unittest tests.test_f22_map_view_state_persistence_contract -v` PASS
- `py -m unittest tests.test_f21_quality_gates_and_smoke tests.test_f20_map_tkinter_shell_and_pan_zoom_contract -v` PASS

### FLOW-F22-MAP-CENTER-ON-CURRENT-SYSTEM-TRAVEL-LAYOUT-FIX-01 (P0)
Status: DONE

Cel:
- naprawic `Center on current system`, aby centrowal na faktycznie wyrenderowanym node mapy.

Diagnoza:
- aktualna mapa (F20/F21) renderuje node w `travel-path layout` (syntetyczne XY),
- `Center on current system` uzywa realnych coords (`app_state.current_star_pos`),
- skutkiem jest centrowanie w niewlasciwe miejsce.

Zakres:
- jesli `current_system` istnieje w aktualnie wyrenderowanych node:
  - centruj po pozycji renderowanej node (canvas/world XY mapy), nie po `StarPos`.
- jesli current system nie jest na mapie:
  - pokaz krotki status UI (np. brak systemu w aktualnym filtrze).
- przygotowanie pod future:
  - rozdzielenie trybow centrowania `travel-layout` vs `coords-view` (bez wdrazania `coords-view` teraz).

DoD:
- `Center on current system` centruje na zielono oznaczonym node, jesli jest widoczny w aktualnym widoku danych,
- brak "wyrzucania mapy w pole",
- zachowany model asystenta i brak side effectow w warstwach/selektorach.

Wdrozenie (2026-02-23):
- `center_on_current_system()` najpierw szuka wyrenderowanego node aktualnego systemu i centruje po pozycji renderowanej (`travel-path layout`),
- gdy aktualny system nie jest widoczny w aktualnym widoku danych: jawny komunikat statusu UI zamiast centrowania "w pole",
- fallback `current StarPos` zostaje tylko jako shell fallback, gdy brak `current_system`.

Testy:
- `py -m unittest tests.test_f22_map_center_on_current_system_travel_layout_fix_contract -v` PASS
- `py -m unittest tests.test_f20_map_tkinter_shell_and_pan_zoom_contract tests.test_f21_quality_gates_and_smoke -v` PASS

### FLOW-F22-MAP-TRADE-COMPARE-MODAL-SCROLLBAR-AND-STATION-AVAILABLE-FILTER-01 (P1)
Status: DONE

Cel:
- dopracowac UX modala `Wybierz towary...` po F21-4.

Zakres:
- modal `Wybierz towary...`:
  - dodac czytelny scrollbar do listy towarow (`Treeview`) - pionowy (wymagany),
  - poziomy scrollbar (best-effort, jesli szerokosc kolumn tego wymaga).
- dodac checkbox:
  - `Pokaż tylko dostępne na stacji`
- semantyka checkboxa (twardy kontrakt):
  - filtruje liste towarow do pozycji obecnych w ostatnim znanym snapshotcie `Market.json`
    aktualnie wybranej stacji w prawym panelu mapy (`Station details` context),
  - jesli brak wybranej stacji lub brak snapshotu rynku:
    - checkbox jest `disabled` albo aktywny z pustym wynikiem + jawny komunikat (wybrac jeden model i trzymac konsekwentnie),
    - status/modul helper tlumaczy powod.
- zachowac:
  - wyszukiwarke,
  - multi-select checkboxy,
  - styl tabel Renaty/Spansh.

DoD:
- modal wygodnie obsluguje dlugie listy towarow (scrollbar dziala),
- checkbox `Pokaż tylko dostępne na stacji` robi dokladnie to, co opisuje nazwa,
- brak regresji `Trade compare` highlight i kompatybilnosci `_run_trade_compare(single commodity)`.

Wdrozenie (2026-02-23):
- modal `Wybierz towary...` ma scrollbar pionowy (wymagany) i poziomy (best-effort) dla `Treeview`,
- dodany checkbox `Pokaż tylko dostępne na stacji`,
- filtr checkboxa działa na podstawie ostatniego snapshotu `Market.json` aktualnie wybranej stacji w prawym panelu mapy,
- przy braku poprawnego kontekstu stacji checkbox jest wyszarzony i UI pokazuje krótki status filtra stacji,
- modal odświeża filtrowanie po zmianie wybranej stacji.

Testy:
- `py -m unittest tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract -v` PASS
- `py -m unittest tests.test_f21_map_trade_compare_v2_multiselect_modal_contract tests.test_f21_quality_gates_and_smoke -v` PASS

### FLOW-F22-MAP-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality gates + smoke)

Cel:
- domknac F22 testami i smoke bez regresji F21/F20.

Zakres:
- testy:
  - persist/restore stanu warstw/filtrów/legendy,
  - `Center on current system` dla `travel-path layout`,
  - modal `Wybierz towary...` ze scrollbar + filtrem stacji.
- smoke:
  - restart UI -> mapa wraca ze stanem,
  - selected station + checkbox `Pokaż tylko dostępne na stacji` -> lista commodity zaweza sie poprawnie.

DoD:
- PASS pack F22 + regresje F21/F20/F19/F16.

Wdrozenie (2026-02-28):
- domknieto quality gates/smoke F22 i potwierdzono brak regresji po zmianach follow-up mapy.

Testy:
- `py -3 -m unittest tests.test_f22_map_view_state_persistence_contract tests.test_f22_map_center_on_current_system_travel_layout_fix_contract tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract tests.test_f21_quality_gates_and_smoke tests.test_f20_quality_gates_and_smoke tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke tests.test_f14_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F22 - PERSONAL GALAXY MAP FOLLOW-UP FREE/PUB)

1. FLOW-F22-MAP-VIEW-STATE-PERSISTENCE-01 (P0) - DONE
2. FLOW-F22-MAP-CENTER-ON-CURRENT-SYSTEM-TRAVEL-LAYOUT-FIX-01 (P0) - DONE
3. FLOW-F22-MAP-TRADE-COMPARE-MODAL-SCROLLBAR-AND-STATION-AVAILABLE-FILTER-01 (P1) - DONE
4. FLOW-F22-MAP-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## Faza 23 (Runtime safety / stability fixes - FREE/PUB)

Cel:
- usunac ryzyka runtime wykryte w grze (powtarzajacy sie false alert paliwa, potencjalne przejmowanie fokusu okna, brak auto-refresh mapy po skoku) bez przebudowy logiki modulow.

Zakres:
- hardening alertu rezerwy paliwa pod transienty `Status.json`,
- polityka focus-safe GUI (brak wymuszania fokusu w runtime calloutach/overlay),
- auto-refresh `Dziennik -> Mapa` po update `playerdb` (z debounce i bez migotania),
- quality gates / smoke pod scenariusze w locie.

### FLOW-F23-FUEL-WARNING-TRANSIENT-HARDENING-01 (P0)
Status: DONE

Cel:
- wyeliminowac powtarzajace sie false-positive alerty niskiej rezerwy paliwa podczas przejsc stanu (start Renaty, start z planety, wejscie w nadswietlna / supercruise).

Diagnoza:
- logika alertu paliwa pracuje na czestych probkach `Status.json`,
- podczas przejsc stanu pola `Fuel.*` i/lub `FuelCapacity.*` bywaja chwilowo niepelne/niestabilne,
- transienty moga byc "promowane" do alertu po kilku probkach w krotkim oknie czasu,
- reset/re-arm po `Docked` moze powodowac ponowny alert po starcie/odlocie.

Zakres:
- zaostrzyc warunki potwierdzenia alertu przy probkach niepewnych (`FuelCapacity` brak/niejednoznaczne),
- oddzielic probki `certain` vs `uncertain` i nie traktowac `uncertain` jako rownowaznych do alarmu,
- dodac guard na przejscia stanu (start, launch, SC entry) aby ograniczyc false-positive,
- zachowac realny alert przy faktycznie niskim paliwie (bez oslabenia bezpieczenstwa),
- opcjonalny debug trace (gated) dla probek paliwa przy diagnostyce.

DoD:
- brak powtarzajacego sie alertu paliwa w scenariuszu: start Renaty -> start z planety -> wejscie w supercruise, jesli paliwo nie jest realnie niskie,
- realny alert nadal pojawia sie dla prawdziwej niskiej rezerwy,
- brak spamu TTS/logow.

Wdrozenie (2026-02-23):
- dodany twardy guard na niepewne probki liczbowe paliwa (`FuelMain` bez wiarygodnej pojemnosci i bez flagi `LowFuel` z gry):
  - nie moga budowac alertu,
  - nie moga uzbrajac pending-confirmation,
- pending confirm jest resetowany dla takich transientow, aby nie kumulowac false-positive miedzy startup/SCO/launch.

Testy:
- `py -m unittest tests.test_f23_fuel_warning_transient_hardening -v` PASS
- `py -m unittest tests.test_f5_anti_spam_regression tests.test_f5_quality_gates_and_smoke tests.test_f6_voice_ethics_compliance -v` PASS

### FLOW-F23-FOCUS-SAFE-WINDOW-POLICY-AND-TRACE-01 (P0)
Status: DONE

Cel:
- wyeliminowac ryzyko przejecia fokusu przez GUI Renaty podczas lotu (zwlaszcza przy skoku / wejsciu do systemu), aby nie minimalizowac gry.

Diagnoza:
- w kodzie istnieja sciezki `focus_force()/lift()/deiconify()` dla okien i modali,
- nawet pojedyncze przejecie fokusu w fullscreen moze zminimalizowac gre,
- user raportuje niebezpieczne "przeskoki" do GUI Renaty podczas skoku / ladowania systemu.

Zakres:
- audyt i klasyfikacja wszystkich wywolan `focus_force/lift/deiconify` (okna glowne + modale),
- usuniecie lub zmiękczenie wywolan wymuszajacych fokus tam, gdzie nie sa niezbedne (focus-safe policy),
- runtime callout/TTS/queue update nie moga prosic o foreground,
- dodac trace diagnostyczny (1-liniowy, gated), aby wiedziec kto i kiedy probowal podniesc fokus,
- zachowac dzialanie modali otwieranych swiadomie przez gracza (bez "martwych" okien).

DoD:
- brak focus-steal/minimalizacji gry w scenariuszu skok/wejscie do systemu przy normalnej pracy Renaty,
- modale i akcje GUI nadal dzialaja po swiadomym kliknieciu gracza,
- trace pozwala zdiagnozowac kolejne incydenty bez technicznego spamu.

Wdrozenie (2026-02-23):
- dodany helper `gui/window_focus.py` (focus-safe + trace gated przez `features.debug.focus_trace`),
- przepiete newralgiczne sciezki okien/modali (`overlay details`, modal mapy, dialogi ustawien, picker stacji Trade) na wspolny helper,
- usuniete agresywne `focus_force()` z `overlay.show_details` (zastapione bezpiecznym `lift` bez wymuszania fokusu).

Testy:
- `py -m unittest tests.test_f23_focus_safe_window_policy_and_trace -v` PASS
- `py -m unittest tests.test_f21_quality_gates_and_smoke tests.test_f20_map_trade_compare_one_commodity_highlight_contract -v` PASS

### FLOW-F23-MAP-AUTO-REFRESH-ON-PLAYERDB-UPDATES-01 (P0)
Status: DONE

Cel:
- mapa w `Dziennik -> Mapa` ma odswiezac sie automatycznie po skokach i innych zdarzeniach aktualizujacych `playerdb`, bez koniecznosci "ruszania" warstwa/filtrem.

Diagnoza:
- `playerdb` ingestuje `Location/FSDJump/CarrierJump/Docked` (i inne dane), ale mapa nie dostaje triggera reloadu,
- obecnie refresh nastepuje glownie po zmianie filtra/warstwy w zakladce mapy.

Zakres:
- dodac sygnal `map_dirty` / `map_refresh_needed` po zdarzeniach istotnych dla mapy (`Location`, `FSDJump`, `CarrierJump`, `Docked`, opcjonalnie `Sell*`, `Market.json`),
- debounce reloadu mapy (ochrona przed spamem redraw),
- refresh tylko gdy `Dziennik -> Mapa` jest aktywna lub bezpieczny deferred refresh przy kolejnym wejściu na mape,
- zachowac selekcje/stan mapy (warstwy, filtry, zoom/pan) podczas auto-refresh,
- jasny status UI przy refresh (bez migotania i bez utraty kontekstu).

DoD:
- po skoku nowy system/skok pojawia sie na mapie bez recznej zmiany warstwy/filtra,
- brak nadmiernego redraw/migotania,
- brak regresji F20/F21/F22 (drilldown, highlight, trade compare, warstwy).

Wdrozenie (2026-02-23):
- router eventow emituje sygnal kolejki GUI `playerdb_updated` po udanym ingest:
  - journal (`Location`, `FSDJump`, `CarrierJump`, `Docked`, `SellExplorationData`, `SellOrganicData`),
  - `Market.json`,
- `gui/app.py` obsluguje `playerdb_updated` i przekazuje sygnal do `LogbookTab`,
- `LogbookTab` deleguje notify do `JournalMapTab` oraz triggeruje deferred refresh po aktywacji podzakladki `Mapa`,
- `JournalMapTab` ma debounce + `dirty` state:
  - odswiezenie automatyczne po update `playerdb`,
  - deferred refresh gdy `Mapa` nie jest aktywna,
  - zachowanie selekcji systemu (best-effort) po auto-refresh.

Testy:
- `py -m unittest tests.test_f23_map_auto_refresh_on_playerdb_updates_contract -v` PASS
- `py -m unittest tests.test_f21_quality_gates_and_smoke tests.test_f20_quality_gates_and_smoke -v` PASS

### FLOW-F23-RUNTIME-STABILITY-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE

Cel:
- domknac F23 testami i smoke, aby poprawki runtime byly stabilne w warunkach zblizonych do gry.

Zakres:
- testy unit/integration:
  - transient fuel samples -> brak false alertu,
  - real low fuel -> alert nadal dziala,
  - focus-safe policy -> brak nieautoryzowanego `focus_force` w sciezkach runtime,
  - map auto-refresh po `playerdb` ingest (z debounce).
- smoke:
  - replay sekwencji `Location/FSDJump/Docked` -> mapa odswieza sie sama,
  - typowy flow eksploracyjny bez przejecia fokusu okna,
  - brak regresji F20/F21/F22 i F17/F4 (voice/callout gating).

DoD:
- PASS pack F23 + regresje F22/F21/F20/F19/F16/F14/F4.

Wdrozenie (2026-02-23):
- dodany pack `tests/test_f23_quality_gates_and_smoke.py` (focus-safe, playerdb->map auto-refresh signal, fuel transient guard vs real alert),
- pack F23 spina wdrozenia F23-1/F23-2/F23-3 w jednym smoke/runtime scenariuszu,
- uruchomione regresje F22/F21/F20/F19/F16/F14/F4.

Testy:
- `py -m unittest tests.test_f23_quality_gates_and_smoke tests.test_f23_focus_safe_window_policy_and_trace tests.test_f23_map_auto_refresh_on_playerdb_updates_contract tests.test_f23_fuel_warning_transient_hardening -v` PASS
- `py -m unittest tests.test_f22_map_view_state_persistence_contract tests.test_f22_map_center_on_current_system_travel_layout_fix_contract tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract tests.test_f21_quality_gates_and_smoke tests.test_f20_quality_gates_and_smoke tests.test_f19_quality_gates_and_smoke tests.test_f16_quality_gates_and_smoke tests.test_f14_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F23 - RUNTIME SAFETY / STABILITY FIXES FREE/PUB)

1. FLOW-F23-FOCUS-SAFE-WINDOW-POLICY-AND-TRACE-01 (P0) - DONE
2. FLOW-F23-MAP-AUTO-REFRESH-ON-PLAYERDB-UPDATES-01 (P0) - DONE
3. FLOW-F23-FUEL-WARNING-TRANSIENT-HARDENING-01 (P0) - DONE
4. FLOW-F23-RUNTIME-STABILITY-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## Faza 24 (Exploration voice sequencing / callout hardening - FREE/PUB)

Cel:
- uporzadkowac glosowy flow po pelnym skanowaniu systemu (FSS -> summary -> cash-in), aby komunikaty byly czytelne, nie wcinaly sie bez kontekstu i lepiej odzwierciedlaly wartosc eksploracyjna systemu.

Zakres:
- fix oczywistego blednego tekstu FSS full-scan (`pe?ni`),
- uzupelnienie calloutow eksploracyjnych o brakujace sygnaly exobio/ladowania (na poziomie planety/systemu),
- wyjecie wymaganych calloutow eksploracyjnych z limitera `exploration_awareness` (nie moga znikac przez anti-spam),
- "graceful sequencing" summary + cash-in (cash-in ma nie wchodzic agresywnie zaraz po summary; krotki komunikat jakosci systemu zamiast generycznego wciskania panelu),
- quality gates / smoke pod scenariusze FSS i exobio.

### FLOW-F24-EXPLORATION-FSS-FULL-SCAN-TEXT-FIX-01 (P0)
Status: DONE

Cel:
- naprawic bledny tekst `System w pe?ni przeskanowany.` wyswietlany w logu/GUI po pelnym FSS.

Diagnoza:
- literal w `logic/events/exploration_fss_events.py` zawiera `pe?ni`,
- to nie jest tylko problem konsoli/encodingu; tekst zly jest w source i trafia do `emit_insight(...)`.

Zakres:
- poprawic literal w `exploration_fss_events` (GUI/log/raw text),
- zachowac obecny wording `Ostatnia planeta do skanowania.` (bez zmiany semantyki / bez renamingu template),
- sprawdzic czy `MSG.SYSTEM_FULLY_SCANNED` pozostaje zgodny z template TTS i UI/logiem.

DoD:
- po pelnym FSS GUI/log pokazuje poprawny tekst `System w pelni przeskanowany.`,
- brak regresji triggera `exploration_summary` po full-scan.

Wdrozenie (2026-02-23):
- poprawiony literal full-scan w `logic/events/exploration_fss_events.py` (`pe?ni` -> `pełni`),
- dodany test regresji emitowanego tekstu i triggera summary.

Testy:
- `py -m unittest tests.test_f24_exploration_fss_full_scan_text_fix -v` PASS
- `py -m unittest tests.test_f3_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

### FLOW-F24-EXPLORATION-EXOBIO-LANDING-CALLOUTS-COVERAGE-01 (P0)
Status: DONE

Cel:
- uzupelnic komunikaty eksploracyjne tak, aby Renata sygnalizowala wartosc ladowania / exobio bardziej czytelnie podczas skanowania i po domknieciu systemu.

Diagnoza:
- high-value/DSS hinty (ELW/WW/HMC-T + DSS helper) sa w kodzie,
- exobio ma obecnie glownie callout `liczne sygnaly biologiczne` (`SAASignalsFound`, prog >= 3),
- brak pelniejszego, systemowego komunikatu typu `0 / malo / duzo obiektow badawczych`,
- brak spójnego calloutu "planeta X jest warta ..." dla exobio/ladowania (w granicach wiarygodnych danych).

Zakres:
- dopiac callouty exobio/ladowania tak, aby:
  - przy realnych sygnalach biologicznych planeta mogla dostac czytelny hint wartosci ladowania (best-effort, bez klamstw),
  - po domknieciu systemu summary moglo zaklasyfikowac system do prostego komunikatu:
    - `Tutaj nie ma nic wartosciowego` (0 / brak sensownych targetow),
    - `Malo obiektow badawczych` (1-3 targety / niski potencjal),
    - `Ten system wymaga doglebnej analizy` (wieksza liczba targetow / wysoki potencjal).
- zachowac istniejace high-value i DSS helper callouty (ELW/WW/HMC-T, DSS hint) jako osobna warstwa informacji.

DoD:
- Renata daje czytelniejszy sygnal o wartosci ladowania/exobio w typowym flow FSS + SAASignalsFound,
- po pelnym skanowaniu system dostaje krotki komunikat jakosciowy (0 / malo / duzo) zamiast wyłącznie generycznego calloutu cash-in.

Wdrozenie (2026-02-23):
- `SAASignalsFound` emituje teraz body-specific exobio/landing hinty takze dla malej liczby sygnalow biologicznych (nie tylko `>=3`):
  - niski count -> krotki hint rekonesans/ladowanie,
  - wysoki count (`>=3`) -> mocny hint wartosci ladowania,
- `exploration_summary` dostal heurystyke v1 klasyfikacji systemu po domknieciu FSS:
  - `Tutaj nie ma nic wartościowego`,
  - `Mało obiektów badawczych`,
  - `Ten system wymaga dogłębnej analizy`,
- klasyfikacja zasila `next_step` (dla auto/manual summary) bez ruszania logiki cash-in/rankingu.

Testy:
- `py -m unittest tests.test_f24_exploration_exobio_landing_callouts_coverage -v` PASS
- `py -m unittest tests.test_f3_quality_gates_and_smoke tests.test_f4_exploration_summary_base tests.test_f4_quality_gates_and_smoke -v` PASS

### FLOW-F24-EXPLORATION-REQUIRED-CALLOUTS-BYPASS-AWARENESS-LIMITS-01 (P0)
Status: DONE

Cel:
- wymagane komunikaty eksploracyjne nie moga byc ucinane przez limiter `exploration_awareness` per-system/per-session.

Diagnoza:
- `emit_callout_or_summary(...)` ma twarde limity calloutow i po limicie emituje summary/suppress,
- czesc kluczowych calloutow eksploracyjnych (high-value / DSS target / bio signals) moze zostac stlumiona mimo ze user oczekuje ich zawsze.

Zakres:
- zdefiniowac liste `required exploration callouts` (v1), ktore nie podlegaja limitowi awareness:
  - high-value bodies (ELW/WW/Terraformable HMC),
  - DSS target hint (gdy body przekracza prog wartosci),
  - exobio/landing signal (po wdrozeniu F24-2),
  - ewentualnie inne twarde callouty eksploracyjne uznane za krytyczne dla decyzji pilota.
- limiter awareness ma nadal dzialac dla calloutow "miekkich" / mniej istotnych.

DoD:
- required callouty eksploracyjne sa emitowane deterministycznie (nie znikaja przez cap awareness),
- anti-spam nadal chroni przed floodem dla calloutow niekrytycznych.

Wdrozenie (2026-02-23):
- `exploration_awareness.emit_callout_or_summary(...)` wspiera teraz required callouty eksploracyjne (v1) omijajace limiter per-system/per-session:
  - `MSG.ELW_DETECTED`
  - `MSG.WW_DETECTED`
  - `MSG.TERRAFORMABLE_DETECTED`
  - `MSG.DSS_TARGET_HINT`
  - `MSG.BIO_SIGNALS_HIGH`
- required callouty:
  - nadal respektuja dedupe po `callout_key`,
  - nie zuzywaja budzetu awareness (nie zjadaja limitu soft-calloutow),
  - nie sa zamieniane na summary/suppress przez awareness cap.
- testy awareness stack (legacy) zostaly przestawione na `soft` message IDs, aby dalej testowac limiter calloutow niekrytycznych.

Testy:
- `py -m unittest tests.test_f24_exploration_required_callouts_bypass_awareness_limits -v` PASS
- `py -m unittest tests.test_exploration_awareness_stack tests.test_f3_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

### FLOW-F24-EXPLORATION-SUMMARY-CASHIN-GRACEFUL-SEQUENCING-01 (P0)
Status: DONE

Cel:
- poprawic sekwencje glosu po pelnym FSS, aby `cash-in` nie "wjezdzal" zaraz po summary bez kontekstu.

Diagnoza:
- `trigger_exploration_summary(...)` bezwarunkowo wywoluje `trigger_cash_in_assistant(...)`,
- `MSG.EXPLORATION_SYSTEM_SUMMARY` ma `P3_LOW`, a `MSG.CASH_IN_ASSISTANT` ma `P2_NORMAL`, wiec cash-in naturalnie preemptuje/dochodzi zaraz po summary,
- aktualny TTS cash-in jest generyczny (`mam trzy opcje...`) i brzmi jak wcinka.

Zakres:
- dodac `graceful sequencing` miedzy `exploration_summary` a `cash-in` (np. warunek/okno/sekwencer zamiast natychmiastowej wcinki),
- dla auto-triggera po full-scan preferowac najpierw krotki komunikat jakosci systemu (z F24-2), a cash-in traktowac jako follow-up (panel / pozniej / warunkowo),
- zachowac manualny cash-in bez opozniania (klik usera ma miec priorytet),
- nie psuc logiki `cash-in` (ranking/opcje/route), zmieniamy tylko orchestration TTS i timing.

DoD:
- po pelnym FSS glos jest czytelny i nie brzmi jak "dwa moduly naraz",
- cash-in auto callout nie zaglusza eksploracyjnego summary/calloutu jakosci systemu,
- manualny trigger cash-in nadal reaguje natychmiast.

Wdrozenie:
- `trigger_exploration_summary(...)` przekazuje do auto cash-in `suppress_tts=True`,
- auto cash-in nadal buduje panel / stan / sygnature, ale bez glosowej wcinki po summary,
- manualny summary->cash-in zostaje bez `suppress_tts` (zachowany explicit UX po akcji gracza),
- dodany `voice_sequence_reason=after_exploration_summary` do kontekstu cash-in.

Testy:
- `py -m unittest tests.test_f24_exploration_summary_cashin_graceful_sequencing -v` PASS
- `py -m unittest tests.test_f4_quality_gates_and_smoke tests.test_f4_exploration_summary_base tests.test_f4_cash_in_assistant_base -v` PASS

### FLOW-F24-EXPLORATION-VOICE-SEQUENCING-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE

Cel:
- domknac F24 testami i smoke dla flow eksploracyjnego z calloutami i cash-in.

Zakres:
- testy:
  - fix tekstu full-scan (`pelni`),
  - required callouty nie wpadaja w awareness cap,
  - klasyfikacja systemu `0 / malo / duzo`,
  - sequencing `summary -> quality callout -> cash-in` (bez agresywnej wcinki).
- smoke:
  - FSS 75% -> last body -> full scan -> summary -> follow-up,
  - system z exobio sygnalami vs system bez wartosciowych targetow,
  - brak regresji F4/F11/F17/F23.

DoD:
- PASS pack F24 + regresje eksploracji/cash-in/voice.

Wdrozenie:
- dodany pack `tests/test_f24_quality_gates_and_smoke.py`,
- smoke spina:
  - fix tekstu full-scan (`System w pełni przeskanowany`),
  - required exobio callout poza awareness cap,
  - auto summary -> cash-in z `suppress_tts=True` (panel cash-in zostaje, bez glosowej wcinki).

Testy:
- `py -m unittest tests.test_f24_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f24_exploration_fss_full_scan_text_fix tests.test_f24_exploration_exobio_landing_callouts_coverage tests.test_f24_exploration_required_callouts_bypass_awareness_limits tests.test_f24_exploration_summary_cashin_graceful_sequencing tests.test_f3_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

---

## Kolejnosc realizacji (F24 - EXPLORATION VOICE SEQUENCING / CALLOUT HARDENING FREE/PUB)

1. FLOW-F24-EXPLORATION-FSS-FULL-SCAN-TEXT-FIX-01 (P0) - DONE
2. FLOW-F24-EXPLORATION-EXOBIO-LANDING-CALLOUTS-COVERAGE-01 (P0) - DONE
3. FLOW-F24-EXPLORATION-REQUIRED-CALLOUTS-BYPASS-AWARENESS-LIMITS-01 (P0) - DONE
4. FLOW-F24-EXPLORATION-SUMMARY-CASHIN-GRACEFUL-SEQUENCING-01 (P0) - DONE
5. FLOW-F24-EXPLORATION-VOICE-SEQUENCING-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## Faza 25 (Exploration Value Integrity / DSS value accounting): DONE

Cel:
- domknac wycene eksploracji tak, aby DSS (`SAAScanComplete`) realnie podbijal wartosc systemu w `SystemValueEngine` (runtime + bootstrap recovery), zamiast byc tylko meta-eventem.

### FLOW-F25-EXPLORATION-DSS-VALUE-ACCOUNTING-AND-RECOVERY-01 (P0)
Status: DONE

Diagnoza:
- `SAAScanComplete` trafial do helpera DSS + `analyze_discovery_meta_event(...)`,
- ale nie aktualizowal wartosci cartography w `SystemValueEngine`,
- przez to po wielu mapowaniach DSS summary moglo pokazywac `0 Cr` lub zbyt niskie wartosci,
- bootstrap recovery po starcie Renaty mial te sama luke.

Wdrozenie:
- `SystemValueEngine` zapamietuje zastosowana wycene per cialo (`cartography_bodies`) po evencie `Scan`,
- dodana metoda `analyze_dss_scan_complete_event(...)` robi upgrade FSS -> DSS (delta base + delta bonus discovery) i dedupe repeated `SAAScanComplete`,
- `EventHandler` wpina `SAAScanComplete` do nowej metody engine (runtime),
- `exploration_value_recovery` wpina `SAAScanComplete` do nowej metody engine (bootstrap/recovery).

DoD:
- DSS mapowanie podnosi wartosc systemu w runtime,
- ten sam efekt dziala po bootstrap recovery z journala,
- brak regresji `SystemValueEngine` i summary.

Testy:
- `py -m unittest tests.test_system_value_engine tests.test_bootstrap_system_value_recovery -v` PASS
- `py -m unittest tests.test_f4_exploration_summary_base tests.test_f24_quality_gates_and_smoke -v` PASS

---

## Faza 28 (Runtime audit follow-up: voice/text/cartography/recovery - FREE/PUB)

Cel:
- zamknac najwazniejsze problemy wykryte w audycie runtime/TTS, ktore jeszcze nie maja dedykowanych ticketow mimo wdrozen F24-F27.

Diagnoza (skrot):
- czesc komunikatow eksploracyjnych i UI ma zepsute polskie znaki / mojibake albo ASCII-PL (`Uzyj`, `Rozwaz`, `Le?`),
- TTS nie ma warstwy czytania liczb po polsku (szczegolnie dla `raw_text_first`), co brzmi nienaturalnie,
- kartografia nadal moze byc zanizona przy skanowaniu glownie gwiazd (`StarType` nie jest liczony w `SystemValueEngine`),
- recovery wartosci eksploracji ma stale okno (`max_lines`) i moze gubic `Scan` vs `SAAScanComplete`,
- komunikat postepu trasy mowi o procencie "trasy", ale faktycznie liczy milestone/odcinek.

### FLOW-F28-EXPLORATION-SUMMARY-RAW-TEXT-POLISH-REPAIR-01 (P0)
Status: DONE

Cel:
- usunac mojibake / zly zapis polskich znakow w runtime tekstach summary eksploracji.

Zakres:
- poprawic literalne teksty `next_step` / highlights / fallbacki w `logic/events/exploration_summary.py`,
- dopiac test regresji na konkretne teksty (`Dokoncz`, `Rozwaz`, `Lec` -> poprawny zapis po polsku),
- nie zmieniac semantyki decyzji summary (tylko warstwa tekstowa).

DoD:
- brak `?` / mojibake w komunikatach summary w logu/UI/TTS,
- test regresji potwierdza poprawne teksty.

Wdrozenie:
- `logic/events/exploration_summary.py`:
  - poprawione literalne teksty microcopy summary (`Dokończ`, `Rozważ`, `Leć`, `dokończenia`, `średni`),
  - poprawiona treść docstringa helpera `system_quality_hint` (czytelność kodu / brak mojibake).
- poprawki zapisane jako bezpieczne sekwencje `\\uXXXX` w źródle (runtime tekst poprawny niezależnie od kodowania konsoli).

Testy:
- `py -m unittest tests.test_f4_exploration_summary_base -v` PASS
- `py -m unittest tests.test_f24_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

### FLOW-F28-TTS-NUMBER-VERBALIZATION-AND-RAW-TEXT-FIRST-01 (P0)
Status: DONE

Cel:
- poprawic naturalnosc czytania liczb (Cr, %, LY) przez Piper i inne TTS.

Zakres:
- dodac warstwe verbalizacji liczb (PL) w `logic/tts/text_preprocessor.py`,
- objac nia rowniez sciezke `raw_text_first`,
- mapowania skrótów:
  - `Cr` -> `kredytow`,
  - `%` -> `procent`,
  - `LY` -> `lat swietlnych`,
- zachowac tryb bezpieczny (brak zmiany UI/raw logow; tylko TTS text).

DoD:
- duze liczby kredytow sa czytane bardziej naturalnie,
- brak regresji istniejących message templates / dedupe / cooldown.

Wdrozenie:
- `logic/tts/text_preprocessor.py`:
  - dodana warstwa verbalizacji liczb dla TTS (`Cr`, `%`, `LY`),
  - podpiecie verbalizacji do `_finalize_tts(...)`,
  - sciezka `raw_text_first` przechodzi teraz przez `_finalize_tts(...)` (naprawa ASCII-PL + liczby + finalizacja),
  - rozszerzony slownik `_PLAIN_POLISH_REPLACEMENTS` o czeste formy (`Rozwaz`, `domknieciu`, `pozniej`).
- verbalizacja dotyczy tylko tekstu TTS (nie zmienia UI/logow).

Testy:
- `py -m unittest tests.test_f28_tts_number_verbalization_and_raw_text_first -v` PASS
- `py -m unittest tests.test_f17_tts_operational_callouts tests.test_f18_tts_polish_templates_and_diacritics tests.test_f6_voice_ethics_compliance -v` PASS

### FLOW-F28-EXPLORATION-CARTOGRAPHY-STAR-TYPE-SUPPORT-01 (P0)
Status: DONE

Cel:
- doliczyc wartosc kartografii dla skanow gwiazd (`StarType`) w `SystemValueEngine`.

Diagnoza:
- obecny mapper cartography jest planet-centric (`PlanetClass`),
- przy sesjach "gwiazdowych" summary moze pokazywac `0 Cr` lub silne zanizenie.

Zakres:
- rozszerzyc `SystemValueEngine` o mapowanie `StarType -> cartography row/tier`,
- jawna diagnostyka `counted/skipped` dla `Scan` (best-effort, bez spamu),
- testy dla typowych gwiazd i case "brak mapowania".

DoD:
- skany gwiazd realnie podnosza `c_cartography`,
- brak regresji F25/F27.

### FLOW-F28-EXPLORATION-VALUE-RECOVERY-WINDOW-AND-DIAGNOSTICS-01 (P1)
Status: DONE

Cel:
- ograniczyc przypadki gubienia wyceny eksploracji po restarcie Renaty.

Zakres:
- poprawic strategie recovery (`max_lines`) lub dodac adaptacyjne/replay-safe podejscie,
- dodac krotkie logi diagnostyczne:
  - `Scan counted`,
  - `DSS upgrade applied`,
  - `DSS skipped (missing prior Scan)`.

DoD:
- mniejsze ryzyko zanizenia wyceny po restarcie przy dlugim journalu,
- diagnostyka pozwala szybko znalezc przyczyne `0 Cr`.

### FLOW-F28-ROUTE-PROGRESS-MILESTONE-WORDING-UX-01 (P1)
Status: DONE

Cel:
- doprecyzowac komunikaty postepu trasy, aby nie mylic milestone progress z postepem calej trasy.

Zakres:
- poprawic wording TTS/UI w `common_route_progress` (np. "do kolejnego etapu" / "odcinka"),
- zachowac obecna logike obliczen milestone (bez zmian semantyki route engine).

DoD:
- brak wrazenia "Renata pomylila procent trasy", gdy zmienia sie milestone.

### FLOW-F28-RUNTIME-PL-TEXT-AUDIT-ASCII-AND-MOJIBAKE-01 (P1)
Status: DONE

Cel:
- zrobic audit i cleanup runtime komunikatow bez polskich znakow / z mojibake.

Zakres:
- audit:
  - `logic/events/*`,
  - `gui/common_route_progress.py`,
  - `gui/strings.py`,
  - krytyczne komunikaty `cash-in`, route, exploration,
- poprawki tekstowe bez zmiany logiki.

DoD:
- brak oczywistych `Uzyj/Rozwaz/osiagniety` w krytycznych calloutach user-facing,
- brak mojibake w kluczowych komunikatach runtime.

Wdrozenie (DONE):
- cleanup krytycznych komunikatow runtime (cash-in, combat/survival, High-G, STT fallback, statusy GUI mapy/logbook/settings/pulpit),
- bez zmian logiki runtime (tylko warstwa tekstowa),
- dodany test-audit na regresje ASCII-PL w kluczowych plikach.

Testy:
- PASS `tests.test_f28_runtime_pl_text_audit_ascii_and_mojibake`
- PASS regresje `F28/F24/F17/F11/F14`

### FLOW-F28-RUNTIME-AUDIT-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE

Cel:
- domknac F28 testami/regresjami (voice/exploration/navigation UX).

Zakres:
- smoke dla:
  - summary eksploracji (tekst + liczby),
  - route progress wording,
  - cartography stars + recovery diagnostics,
- regresje F17/F24/F25/F27.

DoD:
- PASS pack F28 + regresje.

---

## Faza 29 (PlayerDB test isolation / fixture contamination hygiene - FREE/PUB)

Cel:
- zapobiec wyciekowi danych testowych (np. `F19_SMOKE_TARGET`, `F19_QG_SYS_A`) do realnego `player_local.db`, ktory zasila mape i Cash-In.

Diagnoza:
- testy smoke F19/F20/F21 korzystaja z `EventHandler.handle_event(...)`,
- `EventHandler` zapisuje eventy do `playerdb`,
- bez izolacji path test moze zapisac fixture data do `%APPDATA%/RenataAI/db/player_local.db`,
- mapa (`Personal Map`) i Cash-In czytaja `playerdb`, wiec testowe systemy/stacje pojawiaja sie w runtime.

### FLOW-F29-PLAYERDB-TEST-ISOLATION-F19-SMOKE-01 (P0)
Status: DONE

Cel:
- odizolowac testy F19 (i podobne smoke/replay) od realnego `playerdb`.

Zakres:
- testy `F19` przeniesc na temp DB (`TemporaryDirectory` + patch path),
- audit innych testow replay/smoke (F20/F21/F23/F24) pod zapisy do `EventHandler`/`playerdb`,
- helper testowy do tymczasowego `player_local.db`.

DoD:
- uruchomienie testow F19 nie wpisuje nic do realnego `%APPDATA%/RenataAI/db/player_local.db`,
- testy przechodza lokalnie bez regresji.

Wdrozenie:
- `tests/test_f19_quality_gates_and_smoke.py`:
  - test suite korzysta z temp DB (`TemporaryDirectory`) zamiast runtime `player_local.db`,
  - patch `logic.player_local_db.default_playerdb_path` w `setUp/tearDown`,
  - asercja guardrail: temp path != runtime path.

Testy:
- `py -m unittest tests.test_f19_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f19_logbook_feed_cache_persistence tests.test_f20_quality_gates_and_smoke -v` PASS

### FLOW-F29-PLAYERDB-FIXTURE-CONTAMINATION-CLEANUP-TOOLS-01 (P1)
Status: DONE

Cel:
- ulatwic cleanup testowych wpisow z lokalnego `playerdb` po przypadkowym uruchomieniu testow na runtime DB.

Zakres:
- best-effort helper/komenda cleanup fixture prefixes (np. `F19_`, `SMOKE_`, `QG_`) dla:
  - `systems`,
  - `stations`,
  - `cashin_history` / snapshotow powiazanych,
- dry-run + raport ile rekordow zostanie usunietych.

DoD:
- user/dev moze bezpiecznie usunac wpisy testowe z `playerdb` bez kasowania calej bazy.

Wdrozenie:
- helper `logic.player_local_db.cleanup_fixture_test_data(...)`:
  - dry-run (domyslnie) + apply,
  - raport licznikow (`systems`, `stations`, `market_snapshots`, `market_snapshot_items`, `cashin_history`, `trade_history`),
  - preview przykładowych systemow/stacji,
  - cleanup powiazanych snapshotow rynku po `station_market_id` i `(system_name, station_name)`.
- komenda CLI:
  - `python tools/playerdb_fixture_cleanup.py` (dry-run),
  - `python tools/playerdb_fixture_cleanup.py --apply` (faktyczne usuniecie),
  - `--prefix` (wlasne prefixy fixture).

Testy:
- PASS `tests.test_f29_playerdb_fixture_cleanup_tools`
- PASS regresje `F29/F16/F20`

### FLOW-F29-PLAYERDB-TEST-DATA-GUARDRAILS-AND-DOCS-01 (P1)
Status: DONE

Cel:
- dopisac guardrails dokumentacyjne i (opcjonalnie) runtime labels dla danych testowych.

Zakres:
- dokumentacja:
  - `PLAYER_LOCAL_DB_PLAN`,
  - `PERSONAL_GALAXY_MAP_SPEC`,
  - `journal_dev_md` (jesli dotyczy),
- opcjonalnie runtime meta/source flag dla fixture data w test harnessie (nie w normalnym runtime).

DoD:
- jasny kontrakt: testy zawsze uzywaja temp DB, a mapa/cash-in bazuja na `playerdb` jako source-of-truth.

Wdrozenie:
- dokumentacja guardrails dopieta w:
  - `PLAYER_LOCAL_DB_PLAN` (kontrakt test hygiene F29 + cleanup helper/CLI),
  - `PERSONAL_GALAXY_MAP_SPEC` (ryzyko fixture contamination + procedura cleanup),
  - `LAST_TICKET` (diagnoza, kolejność, statusy F29).
- decyzja jawna:
  - testy smoke/replay korzystajace z `EventHandler` + `playerdb` zawsze uruchamiane na temp DB,
  - runtime `playerdb` (`%APPDATA%/RenataAI/db/player_local.db`) pozostaje source-of-truth dla mapy i Cash-In,
  - cleanup fixture danych wykonywany wyłącznie narzędziem dry-run/apply (`tools/playerdb_fixture_cleanup.py`) po świadomej decyzji user/dev.

Testy / walidacja:
- weryfikacja dokumentacyjna + spójność z wdrożonymi F29-1 / F29-2 / F29-5.

### FLOW-F29-PLAYERDB-TEST-HYGIENE-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE

Cel:
- domknac F29 testami i smoke potwierdzajacymi brak zapisu do realnej bazy runtime.

Zakres:
- smoke: test replay przez `EventHandler` na temp DB,
- regresja: brak nowych wpisow w realnym path (mock/assert path usage),
- regresje F16/F19/F20/F21.

DoD:
- PASS pack F29 + brak side-effectow na runtime `player_local.db`.

---

## Kolejnosc realizacji (F28/F29 - runtime audit follow-up + playerdb test hygiene)

1. FLOW-F29-PLAYERDB-TEST-ISOLATION-F19-SMOKE-01 (P0) - DONE
2. FLOW-F28-EXPLORATION-SUMMARY-RAW-TEXT-POLISH-REPAIR-01 (P0) - DONE
3. FLOW-F28-TTS-NUMBER-VERBALIZATION-AND-RAW-TEXT-FIRST-01 (P0) - DONE
4. FLOW-F28-EXPLORATION-CARTOGRAPHY-STAR-TYPE-SUPPORT-01 (P0) - DONE
5. FLOW-F29-PLAYERDB-TEST-HYGIENE-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE
6. FLOW-F28-RUNTIME-AUDIT-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE
7. FLOW-F28-EXPLORATION-VALUE-RECOVERY-WINDOW-AND-DIAGNOSTICS-01 (P1) - DONE
8. FLOW-F28-ROUTE-PROGRESS-MILESTONE-WORDING-UX-01 (P1) - DONE
9. FLOW-F28-RUNTIME-PL-TEXT-AUDIT-ASCII-AND-MOJIBAKE-01 (P1) - DONE
10. FLOW-F29-PLAYERDB-FIXTURE-CONTAMINATION-CLEANUP-TOOLS-01 (P1) - DONE
11. FLOW-F29-PLAYERDB-TEST-DATA-GUARDRAILS-AND-DOCS-01 (P1) - DONE

---

## Faza 26 (High-G orbit trigger + gravity cache for approach - FREE/PUB)

Cel:
- przeniesc komunikat High-G z etapu skanowania (`Scan`) na etap zblizenia/orbity,
- zachowac bezpieczenstwo lotu (ostrzezenie blizej realnego ladowania),
- przygotowac dane grawitacji planety do reuse (mapa / logbook / przyszle helpery).

### FLOW-F26-HIGH-G-APPROACH-ORBIT-TRIGGER-AND-GRAVITY-CACHE-01 (P0)
Status: DONE

Diagnoza:
- aktualny high-g handler reaguje na `Scan`, `ApproachBody`, `Touchdown`, `Location` oraz `Status.json`,
- przez to komunikat moze pojawic sie za wczesnie (juz podczas skanowania planety),
- brak trwalego magazynu `gravity_g` per planeta (playerdb nie ma jeszcze tabeli bodies/system_bodies).

Zakres:
- High-G:
  - `Scan` przestaje emitowac TTS High-G,
  - `Scan` zapisuje / aktualizuje `gravity_g` planety (cache, a docelowo playerdb),
  - TTS High-G emitowany na:
    - `ApproachBody` (baseline),
    - wejscie na orbite / `OrbitalCruise` (rising-edge status flag) - preferowany trigger,
    - `Touchdown` jako fallback safety.
- Dane:
  - MVP cache `system+body -> gravity_g`,
  - opcjonalnie (jesli dopinamy od razu) tabela `playerdb.system_bodies`:
    - `system_address`, `system_name`, `body_id/body_name`, `surface_gravity_g`, `last_seen_ts`.
- Polityka:
  - dedupe/cooldown high-g pozostaje (bez spamu przy tej samej planecie).

DoD:
- brak calloutu High-G przy samym `Scan`,
- callout pojawia sie przy zblizeniu/orbicie dla planety > prog `high_g_warning_threshold_g`,
- brak regresji F17/F23 (TTS/policy/runtime safety),
- testy pokrywaja trigger orbit/approach i brak triggera na `Scan`.

Testy (plan):
- `tests/test_f26_high_g_orbit_trigger_and_gravity_cache.py`
- regresje:
  - `tests.test_f17_tts_operational_callouts`
  - `tests.test_f17_quality_gates_and_smoke`
  - `tests.test_f23_quality_gates_and_smoke`

Wdrozenie:
- `logic/events/high_g_warning.py`:
  - `Scan` nie emituje juz TTS High-G (tylko zapisuje `gravity_g` do cache `system+body`),
  - TTS High-G emituje na `ApproachBody` i `Touchdown`,
  - `Status.json` emituje tylko na rising-edge orbity/glide (best-effort po jawnych polach `OrbitalCruise` / `GlideMode`),
  - dedupe/cooldown pozostaje bez zmian.
- cache gravity:
  - MVP in-memory (`system+body -> gravity_g`) bez migracji `playerdb` na tym etapie.
- testy F17 dostosowane do nowej semantyki (`Scan` cache-only, `ApproachBody` trigger).

Testy:
- `py -m unittest tests.test_f26_high_g_orbit_trigger_and_gravity_cache tests.test_f17_tts_operational_callouts tests.test_f17_quality_gates_and_smoke -v` PASS
- `py -m unittest tests.test_f23_quality_gates_and_smoke -v` PASS

---

## Faza 27 (Exploration cartography FSS value integrity - FREE/PUB)

Cel:
- naprawic przypadki `0 Cr` w podsumowaniu eksploracji mimo skanow FSS cial planetarnych,
- uszczelnic `SystemValueEngine` na placeholder `Planet Type` z `NaN` w arkuszu Cartography,
- rozszerzyc mapowanie `PlanetClass` o popularne aliasy z journala.

### FLOW-F27-EXPLORATION-FSS-CARTOGRAPHY-NAN-FALLBACK-AND-PLANETCLASS-ALIASES-01 (P0)
Status: DONE

Diagnoza:
- fallback `_lookup_cartography_row()` moze zwrocic wiersz `Planet Type` z arkusza Cartography,
- w realnym `renata_science_data.xlsx` wiersz `Planet Type` ma `NaN` w polach wartosci,
- `float(NaN)` trafia do `c_cartography` i po sanitizacji summary daje `0 Cr` zamiast sensownej wyceny / diagnostyki,
- czesc realnych `PlanetClass` z journala nie wpada w obecne mapowanie aliasow (`PlanetClass -> Body_Type`).

Zakres:
- `SystemValueEngine`:
  - nie dopuszcza `NaN/non-finite` z wierszy cartography do `c_cartography` / `bonus_discovery`,
  - fallback `Planet Type` jest uzywany tylko gdy wiersz ma sensowne (finite, >0) wartosci,
  - rozszerzone aliasy `PlanetClass` (m.in. HMC/metal-rich/icy/rocky warianty `body/world/planet`).
- testy:
  - alias `High metal content body` liczy wartosc,
  - `Planet Type` z `NaN` nie zatruwa totals i nie powoduje falszywego `0 Cr` przez `NaN`.

DoD:
- brak `NaN` propagowanego do `SystemValueEngine` totals dla cartography,
- popularne `PlanetClass` aliasy sa liczone poprawnie,
- brak regresji summary/recovery.

Wdrozenie:
- `logic/system_value_engine.py`:
  - `FSS_Base_Value` / `DSS_Mapped_Value` / `First_Discovery_Mapped_Value` sa czytane jako finite-only (`NaN -> 0`),
  - fallback `_lookup_cartography_row()` ignoruje wiersz `Planet Type`, jesli ma niefinity/zerowe wartosci (jak w realnym arkuszu `renata_science_data.xlsx`),
  - rozszerzone aliasy `PlanetClass` (m.in. `High metal content body`, `metal-rich body/world`, `icy world/planet`, `rocky world/planet`).
- testy `SystemValueEngine` rozszerzone o:
  - alias HMC (`High metal content body`) -> poprawna wycena,
  - `Planet Type` z `NaN` nie zatruwa totals.

Testy:
- `py -m unittest tests.test_system_value_engine tests.test_bootstrap_system_value_recovery -v` PASS
- `py -m unittest tests.test_f4_exploration_summary_base tests.test_f24_quality_gates_and_smoke -v` PASS

---

## Faza 24 (Exploration voice sequencing / callout hardening - follow-up: FSS milestone regression fix - FREE/PUB)

Cel:
- naprawic regresje FSS: komunikaty 25%/50%/75%/Ostatnia planeta/System w pelni przeskanowany
  nie docieraly do TTS w malych systemach lub przy szybkim skanowaniu,
- przywrocic 5 progresywnych komunikatow progowych jako niezalezne, zawsze emitowane zdarzenia.

### FLOW-F24-FSS-MILESTONE-SEQUENCE-PRIORITY-MATRIX-BYPASS-01 (P0)
Status: DONE

Diagnoza:
- `_apply_priority_matrix` w `insight_dispatcher.py` tlumy kolejne komunikaty EXPLORATION P2_NORMAL
  jesli poprzedni komunikat tej samej klasy/priorytetu wyemitowano w ciagu ostatnich 10 sekund
  (`priority_matrix_window_sec = 10.0`),
- FSS 25% emituje -> `_remember_cross_module_voice` zapisuje `{EXPLORATION, P2_NORMAL, T0}`,
- FSS 50% przy szybkim skanowaniu (<10 sek) widzi ten sam `(EXPLORATION, P2_NORMAL)` -> SUPPRESSED,
- analogicznie 75%, "Ostatnia planeta" i "System w pelni przeskanowany",
- efekt: uzytkownik slyszal tylko 1-2 komunikaty zamiast 5 (czesto tylko "System w pelni przeskanowany"),
- szczegolnie objawia sie w malych systemach (2-4 ciala) i u doswiadczonych graczy skanujacych szybko.

Zakres:
- `logic/events/exploration_fss_events.py`:
  - `_fss_gate_context()` dostaje flage `"fss_milestone_sequence": True`,
  - flaga trafia do contextu wszystkich 5 FSS calloutow (25/50/75/ostatnia/pelne).
- `logic/insight_dispatcher.py`:
  - `_apply_priority_matrix()` sprawdza `context.get("fss_milestone_sequence")`,
  - jesli True -> bypass matrix suppression, insight przechodzi bez wzgledu na okno czasowe,
  - logika ogolna matrycy priorytetow pozostaje bez zmian.

Polityka:
- FSS milestone to sekwencja unikatowych zdarzen per system, nie spam - nie podlegaja matrix suppression.
- Dedupe w zakresie systemu pozostaje przez flagi `FSS_25_WARNED` itd. (modul-level guard).
- Pozostale gaty (risk/trust/cooldown per message_id/TTS_INTENT) dzialaja normalnie.
- Komunikaty COMBAT/F4 krytyczne dalej maja pierwszenstwo przez P0 / cross-module grupy.

DoD:
- wszystkie 5 FSS calloutow emitowane niezaleznie od predkosci skanowania,
- brak regresji F5 (combat silence, dispatcher priorytety),
- brak regresji F24 (exploration voice sequencing).

Wdrozenie:
- `logic/events/exploration_fss_events.py`:
  - `_fss_gate_context()`: dodano `"fss_milestone_sequence": True` do ctx dict.
- `logic/insight_dispatcher.py`:
  - `_apply_priority_matrix()`: wczesne wyjscie dla `fss_milestone_sequence` przed blokiem matrix suppression.

Testy:
- regresje: `py -m unittest tests.test_f24_fss_all_bodies_found_does_not_force_full_scan tests.test_f24_exploration_fss_full_scan_text_fix tests.test_f5_anti_spam_regression -v` PASS (oczekiwane).

---

## Faza 22 (Personal Galaxy Map follow-up - Tryb renderowania Trasa/Mapa - FREE/PUB)

Cel:
- wdrozyc wybor trybu renderowania mapy zgodnie ze specyfikacja (sekcja 14.5 B: Coords view),
- uzytkownik moze przelaczyc miedzy widokiem "Trasa" (syntetyczny grid serpentyna)
  a widokiem "Mapa" (rzeczywiste wspolrzedne StarPos x/z z playerdb),
- tryb renderowania persystuje miedzy sesjami.

### FLOW-F22-MAP-RENDER-MODE-COORDS-VIEW-TRASA-MAPA-01 (P1)
Status: DONE

Diagnoza:
- specyfikacja PERSONAL_GALAXY_MAP_SPEC.md sekcja 14.5 definiuje dwa tryby layoutu:
  A) Travel-path layout (wdrozony w F20-3 jako MVP domyslny),
  B) Coords view (zaplanowany jako "later") - mapowanie realnych x/z na 2D canvas,
- coords view nie byl wdrozony; dane x/y/z dostepne juz z `get_system_nodes()` w nodes_rows,
- brak kontrolki UI do przelaczania trybu renderowania.

Zakres:
- `gui/tabs/journal_map.py`:
  - `render_mode_var = tk.StringVar(value="Trasa")` - nowa zmienna stanu,
  - Combobox "Tryb renderowania: Trasa | Mapa" w sekcji Filtry (wiersz 3 w `filters_box`),
  - `_coords_layout_from_system_rows()` - nowa metoda layoutu wg coords:
    - pobiera `x`, `z` z rows (y = wysokosc, ignorowane - widok top-down),
    - skaluje do 160 jednostek canvas (uniform scale, najdluzsza os = 160 j.),
    - konwencja ED: x = galaktyczny E/W, z = N/S; galaktyczna polnoc u gory (z invertowane),
    - systemy bez coords -> pas awaryjny ponizej mapy (10 kol. x 12 j. krok),
    - fallback na travel layout gdy zadne cialo nie ma coords,
  - `reload_from_playerdb()`: if render_mode == "Mapa" -> coords layout, else -> travel layout,
  - status bar: "Mapa Trasa:" / "Mapa Mapa:" zamiast hardcoded "Mapa Travel:",
  - `export_persisted_ui_state()`: `"render_mode"` w sekcji `"filters"`,
  - `apply_persisted_ui_state()`: restore `render_mode_var` (walidacja: {"Trasa", "Mapa"}).

Polityka:
- tryb "Trasa" = travel-path layout (MVP domyslny), widok chronologicznej podrozy w serpentynie,
- tryb "Mapa" = widok galaktyczny top-down wg realnych wspolrzednych StarPos (x,z),
- zmiana trybu wyzwala `_on_filter_changed()` -> pelny reload i re-render mapy,
- krawedzie w obu trybach: sequential fallback lub provider jesli dostepny,
- `Center on current system` dziala w obu trybach (szuka renderowanego node po nazwie).

DoD:
- przelaczenie "Trasa" / "Mapa" zmienia layout na kanwie (widoczna roznica),
- w trybie "Mapa" systemy sa ulozzone wg realnych wspolrzednych galaktycznych,
- tryb persystuje po zamknieciu/otwarciu zakladki Mapa,
- brak regresji F20/F21/F22 (filtry, warstwy, trade compare, PPM, legenda, persystencja).

Wdrozenie:
- `gui/tabs/journal_map.py`:
  - `__init__`: `self.render_mode_var = tk.StringVar(value="Trasa")`,
  - `_build_ui` / `filters_box`: Label + Combobox "Tryb renderowania" na row=3,
  - nowa metoda `_coords_layout_from_system_rows()` po `_travel_layout_from_system_rows()`,
  - `reload_from_playerdb()`: dispatch na odpowiedni layout wg `render_mode`,
  - `export_persisted_ui_state()` + `apply_persisted_ui_state()`: persystencja `render_mode`.

Testy:
- brak nowych testow jednostkowych (deterministyczny layout, pokryty przez F20/F21 smoke),
- regresje: `py -m unittest tests.test_f20_map_data_provider tests.test_f22_map_view_state_persistence -v` PASS (oczekiwane).

---

## Kolejnosc realizacji (2026-02-24 - FSS milestone fix + Mapa tryb renderowania)

1. FLOW-F24-FSS-MILESTONE-SEQUENCE-PRIORITY-MATRIX-BYPASS-01 (P0) - DONE
2. FLOW-F22-MAP-RENDER-MODE-COORDS-VIEW-TRASA-MAPA-01 (P1) - DONE

---

---

## Faza 30 (Gameplay findings follow-up z testow w grze - runtime / exploration / mapa / cash-in)

Cel:
- domknac regresje i luki wykryte manualnie w gameplayu po ostatnich wdrozeniach F23/F24/F26/F28/F29,
- odroznic regresje od nowych zmian UX (copy/trigger policy),
- utrzymac stabilnosc runtime bez psucia flow eksploracji/cash-in/mapy.

### FLOW-F30-EXOBIO-POWERLOSS-STATE-RESTORE-AND-3OF3-SUMMARY-01 (P0)
Status: DONE (state restore + range gate + 3/3 completion regression pack)
Cel:
- naprawic odtwarzanie pelnego stanu exobio po power-loss/restart (distance gate + 1/3..3/3 + podsumowanie probek).

Wdrozenie (2026-02-28):
- dodany dedykowany test F30, ktory odtwarza scenariusz:
  - `1/3 -> restart -> range-ready -> 2/3 -> 3/3`.
- potwierdzona ciaglosc po restarcie dla:
  - `EXOBIO_SAMPLE_COUNT`,
  - `EXOBIO_RANGE_TRACKERS`,
  - komunikatu domkniecia gatunku (`Mamy wszystko ...`).

Testy:
- `py -3 -m unittest tests.test_f30_exobio_powerloss_state_restore_and_3of3_summary -v` PASS
- `py -3 -m unittest tests.test_f16_1_exobio_restart_state_continuity tests.test_f10_exobio_sample_continuity -v` PASS

### FLOW-F30-FSS-CATCHUP-MILESTONE-SEQUENCE-AND-FULLSCAN-REGRESSION-01 (P0)
Status: DONE (catch-up + dedupe + fullscan guard)
Cel:
- zdiagnozowac i naprawic catch-up flood progow FSS (25/50/75) w nietypowych systemach oraz sprawdzic regresje przedwczesnego full-scan.

Wdrozenie (2026-02-28):
- wdrozony pakiet F30 dla FSS catch-up/milestones:
  - emit tylko najwyzszego progu przy catch-up,
  - dedupe cial dla wariantow payload (`BodyID`/`BodyName`),
  - brak retro-floodu calloutow przy poznej synchronizacji bodycount.

Testy:
- `py -3 -m unittest tests.test_f30_fss_milestone_catchup_and_body_dedupe -v` PASS

### FLOW-F30-CASHIN-VOICE-PREFIX-COPY-POLISH-01 (P1)
Status: DONE (voice copy bez prefiksu "Cash-in")
Cel:
- usunac slowo "Cash-in" z glosowych komunikatow user-facing (bez zmiany logiki panelu i statusow technicznych).

Wdrozenie (2026-02-28):
- potwierdzony kontrakt copy:
  - TTS dla `MSG.CASH_IN_ASSISTANT` i `MSG.CASH_IN_STARTJUMP` usuwa prefiks "Cash-in" z `raw_text`,
  - statusy techniczne/UI pozostaja bez zmian (dotyczy tylko copy glosowego).

Testy:
- `py -3 -m unittest tests.test_f4_cash_in_assistant_base tests.test_f11_cash_in_startjump_callout -v` PASS

### FLOW-F30-EXPLORATION-SUMMARY-AUTO-CASHIN-VOICE-REGRESSION-01 (P0)
Status: DONE (summary->cash-in auto TTS suppression verified)
Cel:
- potwierdzic i naprawic sciezke, w ktorej po auto summary nadal czytany jest glosowy komunikat cash-in (np. offline index).

Wdrozenie (2026-02-28):
- potwierdzono runtime kontrakt:
  - auto `summary -> cash-in` buduje panel/stany, ale ma `suppress_tts=True`,
  - manualny trigger zachowuje glosowy callout cash-in.

Testy:
- `py -3 -m unittest tests.test_f24_exploration_summary_cashin_graceful_sequencing tests.test_f24_quality_gates_and_smoke tests.test_f4_quality_gates_and_smoke -v` PASS

### FLOW-F30-EXPLORATION-SUMMARY-JUMP-TRIGGER-FSS-ACTIVITY-GATE-01 (P1)
Status: DONE (jump trigger gated by real FSS activity)
Cel:
- dodac gate/cooldown: auto summary po jump tylko jesli od ostatniego summary byla aktywnosc FSS w systemie.

Wdrozenie (2026-02-28):
- wdrozony gate, ktory uzbraja pending summary tylko przy realnej aktywnosci FSS
  (bez false-positive po samym jump/discovery noise).

Testy:
- `py -3 -m unittest tests.test_f30_exploration_summary_after_jump_fss_gate -v` PASS

### FLOW-F30-MAP-TRADE-PICKER-STATION-ONLY-FILTER-LIVE-REGRESSION-01 (P0)
Status: DONE (station-only filter regression closed)
Wdrozenie (2026-02-28):
- potwierdzona stabilna sciezka filtra `Pokaz tylko dostepne na stacji` w modalu `Wybierz towary...`,
- kontrakt filtra trzyma powiazanie z aktywna stacja i snapshotem rynku bez regresji UX modala.

Testy:
- `py -3 -m unittest tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract tests.test_f22_map_view_state_persistence_contract tests.test_f22_map_center_on_current_system_travel_layout_fix_contract -v` PASS

Cel:
- zreprodukować i naprawic checkbox `Pokaz tylko dostepne na stacji` w modalu `Wybierz towary...` (live gameplay regression po F22-3).

### FLOW-F30-EXPLORATION-VALUE-VS-ACCOUNT-DELTA-RECONCILIATION-01 (P1)
Status: DONE (sell-domain reset + recovery reconciliation verified)
Cel:
- dokladnie zweryfikowac rozbieznosci `Cash-in system/session` vs realna zmiana kredytow po sprzedazy danych (instrumentacja + kontrakt).

Wdrozenie (2026-02-28):
- potwierdzony kontrakt wartosciowania:
  - domenowe resetowanie wartosci po `SellExplorationData`/`SellOrganicData`,
  - recovery respektuje eventy sprzedazy i nie odtwarza juz sprzedanych wartosci,
  - dedupe scan/FSS/DSS utrzymuje stabilne sumy sesji.

Follow-up (2026-02-28):
- domkniete wsparcie `MultiSellExplorationData` (UC) end-to-end:
  - `event_handler`: runtime sell-reset + snapshot + ingest do playerdb,
  - `player_local_db`: `ingest_journal_event` akceptuje `MultiSellExplorationData`,
  - `player_local_db`: `_cashin_service_for_event` mapuje `MultiSellExplorationData` -> `UC`.
- domkniete punkty P1 z audytu value-integrity:
  - `SystemValueEngine`: `high_value_targets` odswiezane po `SAAScanComplete` (DSS upgrade),
  - partial sell scope (MultiSell): reset cartography scoped do systemow z `Discovered`,
    z fallbackiem do global reset gdy payload nie niesie listy systemow,
  - ten sam kontrakt scoped resetu zastosowany w `exploration_value_recovery`.

Testy:
- `py -3 -m unittest tests.test_f54_event_handler_sell_value_domain_reset tests.test_bootstrap_system_value_recovery tests.test_system_value_engine -v` PASS
- `py -3 -m unittest tests.test_f54_event_handler_sell_value_domain_reset tests.test_f16_playerdb_cashin_history_and_query -v` PASS

### FLOW-F30-FOCUS-SAFE-REGRESSION-DURING-FSS-AND-DATA-SALE-01 (P0)
Status: DONE (focus-safe policy revalidated for runtime + TTS fallback)
Cel:
- zdiagnozowac i naprawic dalsze przypadki minimalizacji gry podczas FSS / sprzedazy danych mimo F23 focus-safe.

Wdrozenie (2026-02-28):
- potwierdzona polityka focus-safe:
  - runtime paths nie wymuszaja `focus_force` bez akcji usera,
  - fallback TTS `pyttsx3` jest domyslnie blokowany w trybach focus-risk i wymaga jawnego opt-in.

Testy:
- `py -3 -m unittest tests.test_f23_focus_safe_window_policy_and_trace tests.test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard -v` PASS

### FLOW-F30-MAP-ZOOM-RANGE-TO-10-00-01 (P1)
Status: DONE
Wdrozenie:
- maksymalna skala mapy podniesiona z `6.0` do `10.0` (Dziennik -> Mapa).

---

## NOWE TICKETY (F31 - Personal Galaxy Map Faza 17 backlog FREE/PUB)

Cel:
- wdrozyc backlog z `PERSONAL_GALAXY_MAP_SPEC.md` (pkt 17.1-17.4) bez regresji F20/F21/F22/F23,
- utrzymac czytelnosc mapy i stabilny runtime przy rosnacej liczbie informacji,
- domknac UX filtrow czasu/freshness i Trade Compare w scenariuszach gameplay.

### FLOW-F31-MAP-STAR-METADATA-PLAYERDB-SCHEMA-INGEST-01 (P0)
Status: DONE (schema v3 + ingest + provider contract)
Cel:
- dodac i utrzymac metadane gwiazdy na poziomie playerdb + ingest.

Zakres:
- migracja schematu `systems`:
  - `primary_star_type` TEXT,
  - `is_neutron` INTEGER NOT NULL DEFAULT 0,
  - `is_black_hole` INTEGER NOT NULL DEFAULT 0,
- ingest journala uzupelnia pola gwiazdy (best-effort, bez psucia obecnego kontraktu),
- provider mapy zwraca nowe pola w `get_system_nodes(...)`.

Akceptacja:
- brak regresji starych rekordow (NULL/0 fallback),
- nowe rekordy systemow maja metadane gwiazdy, jesli dane sa dostepne,
- SQL/providery dzialaja wstecznie kompatybilnie.

Wdrozenie (2026-02-28):
- schema `player_local_db` podniesiony do `v3`,
- tabela `systems` rozszerzona o:
  - `primary_star_type` (TEXT),
  - `is_neutron` (INTEGER, default 0),
  - `is_black_hole` (INTEGER, default 0),
- `ingest_journal_event(...)` obsluguje rowniez `Scan` dla aktualizacji metadanych gwiazdy,
- upsert systemu aktualizuje metadane gwiazdy only-when-provided (bez czyszczenia istniejacych danych),
- provider mapy `MapDataProvider.get_system_nodes(...)` zwraca nowe pola star metadata.

Follow-up / hotfix (2026-02-28):
- dodany punktowy ingest do backfillu metadanych gwiazd:
  - `player_local_db.ingest_star_metadata_event(...)` (tylko `Location/FSDJump/CarrierJump/Scan`),
- dodane narzedzie CLI:
  - `tools/playerdb_backfill_star_metadata.py`,
  - backfilluje `primary_star_type/is_neutron/is_black_hole` ze starych Journali bez replayu calej logiki runtime.

Testy:
- `py -3 -m unittest tests.test_f16_playerdb_schema_and_migrations tests.test_f20_map_data_provider_adapters -v` PASS
- `py -3 -m unittest tests.test_f16_playerdb_ingest_market_docked_jumps tests.test_f16_playerdb_provider_for_cashin_and_map tests.test_f20_quality_gates_and_smoke -v` PASS
- `py -3 -m unittest tests.test_f31_playerdb_star_metadata_backfill_tool -v` PASS
- `py -3 tools/playerdb_backfill_star_metadata.py` PASS (runtime backfill wykonany, bez bledow)

### FLOW-F31-MAP-STAR-VISUAL-CODING-TOOLTIP-DETAILS-01 (P1)
Status: DONE (star glyphs + tooltip/details enrichment)
Cel:
- pokazac rodzaj gwiazdy na mapie i w panelach bez utraty czytelnosci.

Zakres:
- kolor node zalezy od klasy gwiazdy,
- neutron i black hole odroznione od pozostalych gwiazd (glyph/obrys),
- tooltip node pokazuje typ gwiazdy,
- `System details` pokazuje typ gwiazdy,
- drobne zwiekszenie glyphu gwiazdy (+1 px).

Akceptacja:
- rozroznienie neutron/black hole dziala w renderze i tooltipie,
- mapa pozostaje klikalna przy ciasnych ukladach,
- brak regresji PPM/select/highlight.

Wdrozenie (2026-02-28):
- `MapNode` rozszerzony o:
  - `primary_star_type`,
  - `is_neutron`,
  - `is_black_hole`,
- renderer mapy:
  - lekko zwiekszony rozmiar glyphu gwiazdy (+1 px),
  - kolor glyphu oparty o klase gwiazdy,
  - odroznienie neutron/black hole przez osobny marker i outline,
- tooltip:
  - dodana linia `Gwiazda: ...`,
- `System details`:
  - dodana linia `Gwiazda: ...`.

Testy:
- `py -3 -m unittest tests.test_f31_map_star_visual_coding_contract tests.test_f31_map_time_filters_sliders_last_session_contract tests.test_f31_map_startup_autocenter_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f21_quality_gates_and_smoke tests.test_f22_map_view_state_persistence_contract -v` PASS

### FLOW-F31-MAP-AUTO-CENTER-ON-CURRENT-SYSTEM-STARTUP-01 (P0)
Status: DONE (one-shot startup center + user pan/zoom guard)
Cel:
- po starcie Renaty mapa domyslnie centruje widok na aktualny system gracza.

Zakres:
- jednorazowe auto-centrowanie po pierwszym zaladowaniu danych mapy,
- fallback na `current_star_pos` jesli aktualny system nie jest dostepny w node-ach,
- bez nadpisywania recznego pan/zoom po pierwszej interakcji usera.

Akceptacja:
- pierwsze otwarcie `Dziennik -> Mapa` centruje na aktualnym systemie,
- fallback nie psuje widoku i nie powoduje skokow po recznym przesunieciu mapy.

Wdrozenie (2026-02-28):
- dodany startup one-shot auto-center po pierwszym `reload_from_playerdb()`:
  - priorytet: aktualny system z renderowanych node,
  - fallback: `current_star_pos` (x/z),
- dodane guardrails przed nadpisaniem decyzji usera:
  - reczny pan/zoom przed pierwszym auto-center blokuje startup center (`user_blocked`),
  - blokada jest trwała dla tej instancji zakladki (brak skokow widoku po interakcji usera),
- wynik startup center jest raportowany w `reload_from_playerdb()` (`startup_center`).

Testy:
- `py -3 -m unittest tests.test_f31_map_startup_autocenter_contract tests.test_f22_map_center_on_current_system_travel_layout_fix_contract -v` PASS
- `py -3 -m unittest tests.test_f22_map_view_state_persistence_contract tests.test_f20_quality_gates_and_smoke tests.test_f21_quality_gates_and_smoke -v` PASS

### FLOW-F31-MAP-TIME-RANGE-FRESHNESS-SLIDERS-AND-LAST-SESSION-01 (P0)
Status: DONE (sliders + last-session gate + persisted state)
Cel:
- przebudowac filtry czasu/freshness na bardziej czytelne i szybkie w uzyciu.

Zakres:
- `time range` jako suwak pelnej szerokosci (`1d .. 365d .. forever`),
- osobny control dla `freshness` (pozostaje osobnym filtrem),
- etykieta wartosci nad suwakiem,
- checkbox `Ostatnia sesja`:
  - wylacza i wyszarza controls czasu/freshness,
  - filtruje dane tylko do okna ostatniej sesji,
  - po odznaczeniu przywraca poprzedni stan controls.

Akceptacja:
- filtry sa deterministyczne (brak niejasnosci one-slider-for-all),
- `time range` i `freshness` dzialaja niezaleznie,
- `Ostatnia sesja` ma czytelny i odwracalny efekt.

Wdrozenie (2026-02-28):
- filtry `Zakres czasu` i `Freshness` przebudowane na suwaki (UI mapy),
- dodany checkbox `Ostatnia sesja`:
  - wyszarza/disable oba suwaki,
  - przełącza mapowe filtrowanie na okno biezacej sesji runtime,
- utrzymana kompatybilnosc kontraktu:
  - `time_range_var` i `freshness_var` dalej istnieja i sa source-of-truth dla provider calls,
  - dochodzi warstwa `effective_*` dla `last_session_only`,
- persisted state mapy rozszerzony o `filters.last_session_only`.

Testy:
- `py -3 -m unittest tests.test_f31_map_time_filters_sliders_last_session_contract tests.test_f31_map_startup_autocenter_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_quality_gates_and_smoke tests.test_f22_map_view_state_persistence_contract -v` PASS

### FLOW-F31-MAP-LEGEND-ICONS-POPUP-AND-ZOOM-TEXT-CLEANUP-01 (P1)
Status: DONE (ikonowa legenda + popup gwiazd + cleanup zoom-info)
Cel:
- uproscic i uczytelnic legende mapy.

Zakres:
- zamiana tekstow "ring ..." na mini-ikony/swatch,
- dodanie przycisku obok `Ukryj` otwierajacego popup legendy gwiazd (kolor + opis),
- usuniecie sekcji informacyjnej o zoomie z legendy.

Akceptacja:
- legenda szybciej komunikuje znaczenie warstw,
- popup legendy nie zaslania krytycznie mapy i jest zamykalny bez side-effectow.

Wdrozenie (2026-02-28):
- legenda warstw przepisana na realne mini-ikony (te same ksztalty co na mapie: ring/square/diamond/badge), bez placeholderow tekstowych typu `[O]` / `[#]`,
- dodany przycisk `Gwiazdy` obok `Ukryj`:
  - pokazuje lekki popup overlay z kolorami/typami gwiazd,
  - popup jest stabilny i zamykalny kliknieciem (`Gwiazdy` / `x`),
- usunieta sekcja informacyjna o zoomie z tresci legendy,
- dodane cleanup popupu przy destroy zakladki.

Testy:
- `py -3 -m unittest tests.test_f31_map_legend_popup_contract tests.test_f21_map_action_badges_layers_and_legend_contract tests.test_f21_quality_gates_and_smoke -v` PASS

### FLOW-F31-MAP-TRADE-COMPARE-PROVENANCE-AND-CLEAR-01 (P1)
Status: DONE (provenance columns + clear action)
Cel:
- usunac mylenie kontekstu Trade Compare po zmianie systemu.

Zakres:
- rozszerzyc tabelke compare o pochodzenie danych (`System`, `Stacja`),
- dodac akcje `Wyczysc compare` obok `Odswiez`:
  - kasuje rows compare,
  - resetuje zaznaczone towary,
  - usuwa highlight z mapy,
- zachowac kompatybilnosc z modalem `Wybierz towary...`.

Akceptacja:
- user zawsze widzi zrodlo ceny,
- wyczyszczenie compare resetuje stan bez restartu zakladki,
- brak regresji F22 modal/station-only filter.

Wdrozenie (2026-02-28):
- rozszerzona tabela `Trade compare` o kolumny z pochodzeniem danych:
  - `System`,
  - `Stacja`,
- dodany przycisk `Wyczysc compare` obok `Odswiez`,
- dodany wspolny reset stanu compare:
  - kasuje rows compare,
  - resetuje wybrane towary + single commodity var,
  - czysci highlight mapy,
  - odswieza stan przyciskow i summary,
- zachowana kompatybilnosc z modalem `Wybierz towary...` (single/multi flow bez regresji).

Testy:
- `py -3 -m unittest tests.test_f31_map_trade_compare_provenance_and_clear_contract tests.test_f20_map_trade_compare_one_commodity_highlight_contract tests.test_f21_map_trade_compare_v2_multiselect_modal_contract tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract -v` PASS

### FLOW-F31-MAP-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: DONE (quality pack + smoke/regresje mapy)
Cel:
- domknac F31 testami, smoke i regresjami mapy/runtime.

Zakres:
- testy jednostkowe kontraktu provider/filter/map-state,
- smoke `Dziennik -> Mapa`:
  - selection/tooltip/details,
  - time-range/freshness/last-session,
  - trade compare provenance + clear,
- regresje F20/F21/F22/F23/F30.

Akceptacja:
- PASS pack F31 + regresje mapowe,
- brak regresji runtime safety i auto-refresh mapy.

Wdrozenie (2026-02-28):
- dodane quality gates F31:
  - `tests/test_f31_quality_gates_and_smoke.py`,
  - `tests/test_f31_map_legend_popup_contract.py`,
  - `tests/test_f31_map_trade_compare_provenance_and_clear_contract.py`,
- uruchomiony rozszerzony pack regresyjny F20/F21/F22/F31 (mapa, tooltip, legenda, compare, filtry, persistence) - PASS.

Testy:
- `py -3 -m unittest tests.test_f31_map_legend_popup_contract tests.test_f31_map_trade_compare_provenance_and_clear_contract tests.test_f31_quality_gates_and_smoke tests.test_f20_map_trade_compare_one_commodity_highlight_contract tests.test_f21_map_trade_compare_v2_multiselect_modal_contract tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract tests.test_f21_map_action_badges_layers_and_legend_contract tests.test_f21_quality_gates_and_smoke tests.test_f31_map_star_visual_coding_contract tests.test_f31_map_time_filters_sliders_last_session_contract tests.test_f31_map_startup_autocenter_contract tests.test_f20_map_filters_layers_freshness_source_contract tests.test_f20_map_system_station_drilldown_panels_contract tests.test_f22_map_view_state_persistence_contract tests.test_f20_quality_gates_and_smoke tests.test_f21_quality_gates_and_smoke -v` PASS

## Kolejnosc realizacji (F31 - Personal Galaxy Map Faza 17 backlog)

1. FLOW-F31-MAP-STAR-METADATA-PLAYERDB-SCHEMA-INGEST-01 (P0) - DONE
2. FLOW-F31-MAP-AUTO-CENTER-ON-CURRENT-SYSTEM-STARTUP-01 (P0) - DONE
3. FLOW-F31-MAP-TIME-RANGE-FRESHNESS-SLIDERS-AND-LAST-SESSION-01 (P0) - DONE
4. FLOW-F31-MAP-STAR-VISUAL-CODING-TOOLTIP-DETAILS-01 (P1) - DONE
5. FLOW-F31-MAP-LEGEND-ICONS-POPUP-AND-ZOOM-TEXT-CLEANUP-01 (P1) - DONE
6. FLOW-F31-MAP-TRADE-COMPARE-PROVENANCE-AND-CLEAR-01 (P1) - DONE
7. FLOW-F31-MAP-QUALITY-GATES-AND-SMOKE-01 (P0) - DONE

---

## NOWE TICKETY (F31 hotfix - mapa runtime po backfillu)

### FLOW-F31-MAP-COORDS-ONLY-RENDER-IN-MAPA-MODE-01 (P0)
Status: DONE
Cel:
- w trybie renderu `Mapa` pokazywac wyłącznie systemy z realnymi koordynatami (`x/z`), bez fallbackowego "pasa" wpisów bez coords.

Zakres:
- `JournalMapTab`:
  - w `render_mode=Mapa` odfiltrowac systemy bez coords,
  - usunac fallback strip (bez sztucznego ukladu dla `without_coords`),
  - krawedzie renderowac tylko dla widocznych node z coords,
  - status UI pokazuje licznik ukrytych rekordow bez coords.
- empty-state:
  - gdy po filtrach brak systemow z coords, pokazac jasny komunikat:
    `Brak systemow z koordynatami w tym zakresie`.

Akceptacja:
- tryb `Mapa` nie pokazuje "slupka"/ścieżki z rekordow bez coords,
- widok zawiera tylko realne dane koordynatowe,
- `Trasa` pozostaje bez zmian (może dalej używać path-layout).

Wdrozenie:
- `JournalMapTab._coords_layout_from_system_rows()` usuwa fallback strip i nie wraca do travel layout przy braku coords.
- `reload_from_playerdb()` raportuje `hidden_without_coords` i komunikat `Brak systemow z koordynatami w tym zakresie` dla pustego stanu trybu `Mapa`.

Testy:
- `py -3 -m unittest tests.test_f31_map_coords_only_render_mode_contract tests.test_f20_map_filters_layers_freshness_source_contract -v` PASS
### FLOW-F31-MAP-STARTUP-AUTOCENTER-RESTART-REGRESSION-01 (P0)
Status: DONE
Cel:
- naprawic regresje: po restarcie Renaty mapa nie centruje na aktualnym systemie gracza.

Zakres:
- przeanalizowac i poprawic warunek blokady startup-center (`_startup_autocenter_*`),
- zagwarantowac one-shot center po pierwszym `reload_from_playerdb()` po starcie aplikacji,
- nie gubic center przy restore stanu UI i po auto-refresh,
- zachowac guard: reczny pan/zoom usera po starcie blokuje kolejne auto-center.

Akceptacja:
- po czystym restarcie app pierwsze wejscie do `Dziennik -> Mapa` centruje na current system,
- brak "false block" bez interakcji usera,
- brak skokow widoku po recznym pan/zoom.

Wdrozenie:
- Startup auto-center dostal mechanizm `recenter_pending` dla sytuacji, gdy pierwszy center wykona sie przed finalnym rozmiarem canvasa.
- Przy pierwszym sensownym `CanvasConfigure` (>=32x32) widok dociaga center na aktualny system i kasuje pending.
- Reczny pan/zoom czysci `recenter_pending`, wiec nie ma "skoku zwrotnego" po interakcji usera.

Testy:
- `py -3 -m unittest tests.test_f31_map_startup_autocenter_contract tests.test_f31_map_coords_only_render_mode_contract tests.test_f20_map_filters_layers_freshness_source_contract -v` PASS
### FLOW-F31-MAP-LEGEND-STARS-POPUP-AND-SCROLLABLE-TEXT-01 (P1)
Status: DONE
Cel:
- domknac UX legendy: niezawodny popup `Gwiazdy` i przewijana sekcja tekstowa legendy bez ruszania przyciskow.

Zakres:
- `Gwiazdy`:
  - popup ma byc zawsze dostepny (klik), stabilny i czytelny,
  - poprawic ewentualne przypadki, gdy popup nie pojawia sie mimo akcji usera.
- legenda lewego panelu:
  - przyciski (`Gwiazdy`, `Ukryj`) pozostaja stale na gorze sekcji,
  - tylko obszar tekstu/opisow ma miec pionowy scroll,
  - brak zmiany semantyki warstw/ikon.

Akceptacja:
- popup `Gwiazdy` otwiera sie deterministycznie po kliknieciu i nie "znika od razu",
- dlugie opisy legendy sa przewijalne (tekst), przyciski sa stale widoczne,
- brak regresji zwijania legendy (`Pokaz/Ukryj`) i persisted state.

Wdrozenie:
- Legenda mapy ma scrollowany obszar tresci (`legend_body_canvas` + scrollbar), przyciski `Gwiazdy` i `Ukryj` pozostaja stale w naglowku.
- Popup `Gwiazdy` dziala deterministycznie po kliknieciu (toggle), bez zaleznosci od hover.
- Zwijanie legendy ukrywa tylko obszar tresci i nie rusza przyciskow.

Testy:
- `py -3 -m unittest tests.test_f31_map_legend_popup_contract tests.test_f31_map_startup_autocenter_contract tests.test_f31_map_coords_only_render_mode_contract tests.test_f20_map_filters_layers_freshness_source_contract -v` PASS
## Kolejnosc realizacji (F31 hotfix)

1. FLOW-F31-MAP-COORDS-ONLY-RENDER-IN-MAPA-MODE-01 (P0)
2. FLOW-F31-MAP-STARTUP-AUTOCENTER-RESTART-REGRESSION-01 (P0)
3. FLOW-F31-MAP-LEGEND-STARS-POPUP-AND-SCROLLABLE-TEXT-01 (P1)
4. FLOW-F31-MAP-TRADE-COMPARE-SCOPED-TO-SELECTED-SYSTEM-STATION-01 (P0) - DONE

### FLOW-F31-MAP-TRADE-COMPARE-SCOPED-TO-SELECTED-SYSTEM-STATION-01 (P0)
Status: DONE

Cel:
- przywrocic kompaktowy kontrakt tabeli `Trade compare` (bez kolumn `System`/`Stacja`),
- wymusic scope danych compare do aktualnie wybranego systemu/stacji w panelu `System details`.

Wdrozenie:
- `gui/tabs/journal_map.py`:
  - tabela `Trade compare`: kolumny `mode, commodity, price, age`,
  - dodano `_trade_compare_scope_from_selection()` i twardy gate scope,
  - compare (single/multi) bez scope nie odpytuje globalnego playerdb.
- `logic/personal_map_data_provider.py`:
  - `get_top_prices(...)` rozszerzone o filtry `system_name`, `station_market_id`, `station_name`.

Akceptacja:
- compare pokazuje dane tylko dla wybranego systemu/stacji,
- brak regresji clear/highlight/smoke.


## NOWE TICKETY (Runtime focus-safe / anti-minimize)

### FLOW-RUNTIME-FOCUS-SAFE-ZERO-MINIMIZE-01 (P0 BLOCKER)
Status: DONE (code+tests), manual smoke in ED required before release close

Zasada krytyczna:
- Renata NIE MOZE w zadnym wypadku doprowadzac do minimalizacji gry Elite Dangerous
  ani przejecia fokusa w trakcie rozgrywki (fullscreen/borderless), poza jawna akcja usera.

Cel:
- domknac runtime focus-safe tak, aby zdarzenia losowe (TTS/UI/dialogi/linki) nie mogly
  przerwac aktywnego okna gry.

Zakres:
- usunac lub zablokowac niejawne podnoszenie okna (`lift`/`deiconify`) poza sciezkami
  `user_initiated=True`,
- usunac `-topmost` z dialogow, ktore nie wymagaja hard-topmost do dzialania,
- utrzymac pyttsx3 jako opt-in risk-only (domyslnie OFF),
- dla linkow z UI: domyslnie clipboard/status zamiast automatycznego `webbrowser.open`,
- dodac twarde logowanie trace focus actions i korelacje z eventami runtime.

Akceptacja:
- 0 przypadkow minimalizacji gry wywolanych przez Renate podczas testu 60 min (loop:
  FSS, skoki, dock/undock, cash-in, mapa, ustawienia),
- brak wywolan focus-risk bez `user_initiated=True` (potwierdzone logiem `FOCUS`),
- brak regresji UX dla dialogow otwieranych recznie przez usera.

Definicja DONE:
- testy automatyczne + smoke manual PASS,
- wpisy diagnostyczne focus-safe dostepne w logach,
- ticket zamykany dopiero po potwierdzeniu na realnej sesji gry.

Wdrozenie (2026-02-28):
- `gui/window_focus.py`:
  - runtime/non-user sciezki sa twardo blokowane dla `focus_set/focus_force`,
  - runtime/non-user sciezki sa twardo blokowane dla `deiconify/lift`,
  - trace `FOCUS` raportuje blokady z `reason=not_user_initiated`.
- `gui/tabs/settings.py`:
  - usuniety `-topmost` z dialogu progow jackpot (`_edit_jackpot_thresholds`).
- `gui/tabs/journal_map.py`:
  - popup legendy gwiazd nie wykonuje `lift()` przy ponownym otwarciu,
  - jawnie ustawione `popup.attributes("-topmost", False)` (focus-safe).
- `gui/app.py`:
  - usuniete automatyczne otwieranie linkow w przegladarce (`webbrowser.open`),
  - dodany bezpieczny flow: kopiowanie URL do schowka + status w UI (`_safe_copy_external_url`),
  - dotyczy menu linkow i dialogu "O programie".

Testy:
- `py -3 -m unittest tests.test_f23_focus_safe_window_policy_and_trace tests.test_f23_quality_gates_and_smoke tests.test_f31_map_legend_popup_contract tests.test_f31_quality_gates_and_smoke tests.test_f31_map_star_visual_coding_contract tests.test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard -v` PASS

### FLOW-RUNTIME-BOOTSTRAP-TAIL-WINDOW-AND-UTF8-NOBOM-HYGIENE-01 (P1)
Status: DONE (code + verification)

Cel:
- zwiekszyc odpornosc bootstrapu na dlugie sesje journala (stary `Loadout` poza krotkim tail-window),
- usunac artefakty encodingu (`utf-8-sig` / BOM) z plikow runtime/UI/TTS.

Zakres:
- `app/main_loop.py`:
  - domyslny tail window bootstrapu podniesiony z `8000` do `50000` linii
    (`MainLoop._bootstrap_state(..., max_lines=50000)`),
- usuniety BOM (UTF-8 without BOM) z:
  - `app/main_loop.py`,
  - `app/status_watchers.py`,
  - `gui/tabs/pulpit.py`,
  - `gui/tabs/settings.py`,
  - `logic/tts/text_preprocessor.py`.

Akceptacja:
- bootstrap ma wieksza szanse odtworzyc `Loadout` w dlugich logach sesji,
- brak BOM i brak wewnetrznego `\ufeff` w ww. plikach,
- brak regresji parsera/journal runtime.

Wdrozenie (2026-02-28):
- wdrozone zgodnie z zakresem; hardening dotyczy kompletu danych bootstrap i higieny encodingu.

Weryfikacja:
- sprawdzenie binarne plikow: `file_bom=False` i `contains_ufeff=False` dla calej listy.



## NOWE TICKETY (FSS summary arming integrity / NavBeacon hardening)

### FLOW-F30-FSS-MANUAL-SCAN-TYPE-WHITELIST-NAVBEACON-EXCLUDE-01 (P0)
Status: DONE (code + tests)

Cel:
- usunac falszywe uzbrajanie auto-summary po skoku w systemach, gdzie nie bylo realnego FSS scanowania manualnego.

Root cause:
- `logic/events/exploration_fss_events.py::_is_manual_progress_scan(...)` traktuje kazdy `ScanType != "autoscan"` jako manual,
- `ScanType="NavBeaconDetail"` (oraz potencjalnie `Basic`) podnosi `FSS_HAD_MANUAL_PROGRESS_SCAN=True`, mimo ze to nie jest reczne FSS.

Zakres:
- zmienic logike `_is_manual_progress_scan` na whitelist:
  - domyslnie tylko `Detailed`,
  - ewentualne inne typy dopinac jawnie po potwierdzeniu gameplay.
- odrzucic `NavBeaconDetail` i `Basic` jako source manualnego FSS progress.
- dodac throttled diagnostic dla nieznanego `ScanType`, aby latwo wykryc nowe warianty eventow gry.
- utrzymac ten sam kontrakt dla bootstrap/recovery (ta sama funkcja klasyfikacji).

Akceptacja:
- sam `NavBeaconDetail` nie uzbraja `FSS_HAD_MANUAL_PROGRESS_SCAN`,
- system z `AutoScan + NavBeaconDetail` bez `Detailed` nie uzbraja pending auto-summary,
- scenariusz `FSSDiscoveryScan + Detailed + full` nadal uzbraja pending auto-summary.

Wdrozenie (2026-02-28):
- `logic/events/exploration_fss_events.py`:
  - `_is_manual_progress_scan(...)` zmienione z reguly `scan_type != autoscan` na whitelist manualnych typow (`Detailed`),
  - `NavBeaconDetail` i `Basic` oznaczone jako non-manual,
  - nieznane `ScanType` sa traktowane bezpiecznie jako non-manual + throttled diagnostic.
- klasyfikacja jest wspolna dla runtime i bootstrap (ta sama funkcja), wiec fix obejmuje oba flow.

Testy:
- `tests/test_f30_exploration_summary_after_jump_fss_gate.py`:
  - dodany regres: `NavBeaconDetail` nie podnosi manual gate,
  - potwierdzenie: `Detailed` podnosi manual gate.
- `tests/test_f60_bootstrap_fss_state_recovery.py`:
  - dodany regres: bootstrap z `NavBeaconDetail` nie przywraca manual gate.
- uruchomione:
  - `py -3 -m unittest tests.test_f30_exploration_summary_after_jump_fss_gate tests.test_f60_bootstrap_fss_state_recovery tests.test_f30_fss_milestone_catchup_and_body_dedupe` PASS

### FLOW-F30-EXPLORATION-SUMMARY-ARMING-HARD-GATE-DETAILED-SCAN-01 (P0)
Status: DONE (code + tests)

Cel:
- domknac twarda bramke uzbrajania `FSS_PENDING_EXIT_SUMMARY`, tak aby auto-summary odpalalo tylko po realnej aktywnosci FSS (honk + reczny scan).

Zakres:
- w `exploration_fss_events`:
  - utrzymac warunek `FSS_HAD_DISCOVERY_SCAN == True`,
  - zastapic obecna semantyke `FSS_HAD_MANUAL_PROGRESS_SCAN` semantyka "detailed/manual FSS only" (whitelist),
  - upewnic sie, ze armowanie przez `_wire_exit_summary_to_runtime()` nie przechodzi przez `NavBeaconDetail`.
- dodac jednoznaczny log armowania:
  - trigger source (`Scan` / `FSSAllBodiesFound`),
  - `scan_type_last`,
  - snapshot flag (`had_discovery`, `had_manual`, `discovered`, `total`).

Akceptacja:
- brak autopodsumowania przy tranzycie przez systemy "zamieszkale" skanowane tylko przez NavBeacon,
- autopodsumowanie odpala tylko po prawdziwym domknieciu FSS w danym systemie.

Wdrozenie (2026-02-28):
- `logic/events/exploration_fss_events.py`:
  - dodane metadane runtime:
    - `FSS_LAST_SCAN_TYPE`,
    - `FSS_LAST_MANUAL_SCAN_TYPE`,
  - `_wire_exit_summary_to_runtime(...)` dostal trigger metadata (`trigger_source`) i twardy gate:
    - `had_discovery=True`,
    - `had_manual=True`,
    - `last_manual_scan_type` nalezy do whitelist manual (`Detailed`),
  - dodane diagnostyczne logi:
    - `exit_summary_arm_blocked` (powod blokady + snapshot flag/licznikow),
    - `exit_summary_armed` (source + scan_type_last + snapshot),
  - source triggera przekazywany z:
    - `Scan`,
    - `FSSAllBodiesFound`.
- reset/bootstrap obejmuja i odtwarzaja `last scan type` metadata, aby gate i diagnostyka byly spójne po restarcie.

Testy:
- `tests/test_f30_exploration_summary_after_jump_fss_gate.py`:
  - dostosowane testy gate do `last_manual_scan_type`,
  - regres:
    - `NavBeaconDetail + full + FSSAllBodiesFound` nie uzbraja pending summary,
    - `FSSAllBodiesFound` uzbraja pending tylko gdy detailed-gate przechodzi.
- uruchomione:
  - `py -3 -m unittest tests.test_f30_exploration_summary_after_jump_fss_gate tests.test_f60_bootstrap_fss_state_recovery tests.test_f30_fss_milestone_catchup_and_body_dedupe tests.test_f24_fss_all_bodies_found_does_not_force_full_scan` PASS

### FLOW-F30-FSS-SUMMARY-REGRESSION-MATRIX-NAVBEACON-AND-BOOTSTRAP-01 (P0)
Status: DONE (tests + smoke-style matrix)

Cel:
- dodac testy regresyjne, ktore lapia wszystkie edge-case'y FSS summary arming.

Zakres testow:
- `NavBeaconDetail` only:
  - `FSSDiscoveryScan + NavBeaconDetail + full` -> pending summary NIE uzbrojone.
- `Detailed` path:
  - `FSSDiscoveryScan + Detailed + full` -> pending summary uzbrojone.
- `FSSAllBodiesFound`:
  - nie uzbraja pending, jesli manual gate nie jest spelniony.
- bootstrap:
  - odtwarzanie stanu z tail journala nie uzbraja pending tylko przez `NavBeaconDetail`.
- anti-regresja:
  - brak psucia `F30-EXPLORATION-SUMMARY-JUMP-TRIGGER-FSS-ACTIVITY-GATE-01`.

Akceptacja:
- PASS komplet testow matrix dla `ScanType` (`AutoScan`, `Detailed`, `NavBeaconDetail`, `Basic`),
- PASS smoke:
  - system bez `Detailed` -> brak autopodsumowania po skoku,
  - system z `Detailed` -> autopodsumowanie po skoku dziala.

Wdrozenie (2026-02-28):
- dodany pakiet matrix:
  - `tests/test_f30_fss_summary_scan_type_matrix.py`
    - runtime matrix gate (`AutoScan`, `NavBeaconDetail`, `Basic`, `Detailed`, `Analyse`, brak `ScanType`),
    - mixed path (`AutoScan` -> `Detailed`) z uzbrojeniem dopiero po manual detailed,
    - bootstrap matrix dla tych samych typow.
- test matrix potwierdza:
  - `NavBeaconDetail` i `Basic` nie uzbrajaja pending summary,
  - `Detailed` uzbraja pending summary,
  - nieznane `ScanType` sa domyslnie non-manual (safe).

Testy:
- `py -3 -m unittest tests.test_f30_fss_summary_scan_type_matrix tests.test_f30_exploration_summary_after_jump_fss_gate tests.test_f60_bootstrap_fss_state_recovery tests.test_f30_fss_milestone_catchup_and_body_dedupe tests.test_f24_fss_all_bodies_found_does_not_force_full_scan` PASS

## Kolejnosc realizacji (FSS summary arming integrity)

1. FLOW-F30-FSS-MANUAL-SCAN-TYPE-WHITELIST-NAVBEACON-EXCLUDE-01 (P0)
2. FLOW-F30-EXPLORATION-SUMMARY-ARMING-HARD-GATE-DETAILED-SCAN-01 (P0)
3. FLOW-F30-FSS-SUMMARY-REGRESSION-MATRIX-NAVBEACON-AND-BOOTSTRAP-01 (P0)

### FLOW-F30-FSS-LATE-BODYCOUNT-NMINUS1-LAST-BODY-AND-PROGRESS-CALLOUT-01 (P0)
Status: DONE (code + tests)

Cel:
- naprawic scenariusze late `FSSDiscoveryScan`, gdzie:
  - przy N-1 brakowalo calloutu `MSG.FSS_LAST_BODY`,
  - brakowalo feedbacku progresu po poznym `BodyCount`.

Root cause:
- w `handle_fss_discovery_scan(...)` sciezka `has_progress=True` robila tylko cichy sync licznikow/flag,
  bez uruchomienia progow FSS dla juz zeskanowanych cial.

Wdrozenie (2026-02-28):
- `logic/events/exploration_fss_events.py`:
  - w branchu late BodyCount (`previous_total <= 0` i `discovered_now > 0`) dodane:
    - `_check_fss_thresholds(gui_ref)` (catch-up callout dla aktualnego stanu),
    - `_sync_milestone_flags_after_late_body_count()` (utrzymanie anti-retro behavior).
  - efekt: N-1 dostaje `Ostatnia planeta do skanowania`, a scenariusze typu 5/8 dostaja callout progresu.
- `tests/test_f30_fss_milestone_catchup_and_body_dedupe.py`:
  - dodany regres: `test_late_bodycount_at_n_minus_1_emits_last_planet_callout`,
  - dodany regres: `test_late_bodycount_emits_current_progress_callout`,
  - zaktualizowany test sync, aby zachowac deterministyczny kontrakt po nowym catch-up flow.

Testy:
- `py -3 -m unittest tests.test_f30_fss_milestone_catchup_and_body_dedupe tests.test_f30_exploration_summary_after_jump_fss_gate tests.test_f30_fss_summary_scan_type_matrix tests.test_f24_fss_all_bodies_found_does_not_force_full_scan -v` PASS

### FLOW-F30-EXIT-SUMMARY-TRIGGER-SURFACE-HARDENING-AND-TRACE-01 (P0)
Status: DONE (code + tests)

Cel:
- ograniczyc false-positive "summary-like" komunikaty i rozdzielic trigger surface:
  - `StartJump cash-in` domyslnie OFF,
  - awareness summary z osobnym `message_id`,
  - twardy trace runtime dla kazdej emisji insight.

Wdrozenie (2026-02-28):
- `config.py`:
  - `cash_in.startjump_callout_enabled` domyslnie zmienione na `False`.
- `logic/events/exploration_awareness.py`:
  - summary fallback przestawiony na `MSG.EXPLORATION_AWARENESS_SUMMARY`,
  - w summary context dopinany `raw_text`,
  - dedup key rozdzielony: `exp_awareness_summary:{system}`.
- `logic/tts/message_templates.py`:
  - dodany `MSG.EXPLORATION_AWARENESS_SUMMARY`.
- `logic/event_insight_mapping.py`:
  - dodana klasa insight + TTS policy dla `MSG.EXPLORATION_AWARENESS_SUMMARY`.
- `logic/insight_dispatcher.py`:
  - dodany runtime trace `INSIGHT emit_decision` (message_id/source/event_type/allow_tts/reason/priority/dedup/system),
  - `MSG.EXPLORATION_AWARENESS_SUMMARY` sklasyfikowany jako `EXPLORATION` (nie F4), aby nie mieszac z exit summary.
- testy:
  - zaktualizowane asercje `tests/test_exploration_awareness_stack.py`,
  - zaktualizowana smoke asercja `tests/test_f3_quality_gates_and_smoke.py`.

Testy:
- `py -3 -m unittest tests.test_exploration_awareness_stack tests.test_f3_quality_gates_and_smoke tests.test_event_insight_mapping tests.test_f5_voice_policy_contract tests.test_f11_cash_in_startjump_callout tests.test_f11_quality_gates_and_smoke tests.test_f30_fss_milestone_catchup_and_body_dedupe tests.test_f30_exploration_summary_after_jump_fss_gate -v` PASS

### FLOW-F30-FSS-REAL-BODY-FILTER-BELT-CLUSTER-BARYCENTRE-01 (P0)
Status: DONE (code + tests)

Cel:
- zsynchronizowac milestone FSS z in-game `Bodies N/*` i usunac falszywy progres z obiektow niebedacych cialami niebieskimi.

Root cause:
- licznik `FSS_DISCOVERED` byl podbijany dla wpisow `Scan` typu:
  - `... Belt Cluster ...`,
  - `... Barycentre/Barycenter ...`,
- ten sam problem byl odtwarzany w bootstrapie (`bootstrap_fss_state_from_journal_lines`).

Wdrozenie:
- `logic/events/exploration_fss_events.py`:
  - dodano `_is_real_celestial_body(ev)` (filtr belt cluster/barycentre),
  - `handle_scan(...)`: guard filtrujacy przed naliczaniem progresu,
  - `bootstrap_fss_state_from_journal_lines(...)`: ta sama filtracja w recovery,
  - `_progress_count_for_thresholds()` ujednolicony do `FSS_DISCOVERED` (jeden licznik progow).

Akceptacja:
- brak naliczania progresu FSS dla belt-clusterow i barycentrow,
- po restarcie Renaty bootstrap nie przywraca zawyzonego progresu z tych wpisow,
- progi 25/50/75 sa liczone z jednego przefiltrowanego licznika.

Testy:
- `tests/test_f30_fss_milestone_catchup_and_body_dedupe.py`:
  - `test_handle_scan_ignores_belt_cluster_from_fss_progress`
- `tests/test_f60_bootstrap_fss_state_recovery.py`:
  - `test_bootstrap_ignores_belt_cluster_entries_in_discovered_counter`
- `py -3 -m unittest tests.test_f30_fss_milestone_catchup_and_body_dedupe tests.test_f60_bootstrap_fss_state_recovery tests.test_f30_exploration_summary_after_jump_fss_gate tests.test_f24_fss_all_bodies_found_does_not_force_full_scan -v` PASS (2026-03-01)


## NOWE TICKETY (Cash-In candidates: collect-then-rank + profile cleanup)

### FLOW-F32-CASH-IN-CANDIDATES-COLLECT-THEN-RANK-ORCHESTRATOR-01 (P0)
Status: TODO

Cel:
- usunac short-circuit providerow i przejsc na globalny model `collect -> rank`.

Zakres:
- `logic/cash_in_station_candidates.py`:
  - orchestrator zbiera kandydatow ze wszystkich providerow (offline index + local spansh dumps + edsm/playerdb bridge),
  - brak early-return po pierwszym trafionym zrodle,
  - normalize do wspolnego kontraktu rekordu.

Akceptacja:
- kandydaci sa zawsze agregowani wielozrodlowo,
- brak faworyzowania stalego offline tylko dlatego, ze byl pierwszy.

### FLOW-F32-CASH-IN-GLOBAL-DEDUPE-FRESHNESS-AND-RANKING-01 (P0)
Status: TODO

Cel:
- wybrac realnie najblizsza i najaktualniejsza stacje niezaleznie od zrodla.

Zakres:
- dedupe po `market_id` (fallback: `system_name + station_name`),
- preferencja rekordu:
  - nowszy `freshness_ts`,
  - przy remisie preferuj `SPANSH/EDSM` nad legacy offline,
- global sort:
  - `distance_ly ASC`,
  - `distance_ls ASC`.

Akceptacja:
- wynik top-1 odpowiada globalnie najblizszej stacji po dedupe/rankingu.

### FLOW-F32-CASH-IN-ROUTE-PROFILES-NAMED-SEMANTIC-01 (P1)
Status: TODO

Cel:
- usunac numerowane profile (`1/2/3`) i zastapic je semantycznymi nazwami.

Zakres:
- `logic/events/cash_in_assistant.py`,
- `logic/events/exploration_summary.py`,
- stale:
  - `NEAREST`,
  - `SECURE_PORT`,
  - `CARRIER_FRIENDLY`,
- migracja mapowania legacy (wsteczna zgodnosc ustawien runtime/persisted state).

Akceptacja:
- runtime, logi i UI uzywaja nazw profili (bez numerow tras).

### FLOW-F32-CASH-IN-PAYLOAD-TARGET-SYSTEM-CLIPBOARD-READINESS-01 (P1)
Status: TODO

Cel:
- przygotowac cash-in insight do natychmiastowego handoffu systemu celu.

Zakres:
- `CashInAssistantPayload`: dodac `target_system_name`,
- wiring do `MSG.CASH_IN_ASSISTANT` context,
- gwarancja, ze przy top kandydacie wartosc systemu docelowego jest jawnie dostepna.

Akceptacja:
- payload/callout zawiera `target_system_name` gotowe pod clipboard assist.

### FLOW-F32-CASH-IN-MIXED-SOURCE-QUALITY-GATES-AND-SMOKE-01 (P0)
Status: TODO

Cel:
- domknac regresje i udowodnic, ze ranking nie psuje fallbackow.

Zakres testow:
- mixed sources: offline + spansh local dump + edsm/playerdb,
- konflikt duplikatow (rozne freshness/source),
- sort tie-break (`ly`, potem `ls`),
- profile `NEAREST/SECURE_PORT/CARRIER_FRIENDLY`,
- payload `target_system_name`.

Akceptacja:
- PASS test pack + smoke runtime cash-in bez regresji F11/F14/F17.


