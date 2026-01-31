# RENATA_STATUS.md

Ostatnia aktualizacja: 2026-01-26  
Wlasciciel procesu: Patryk  
Tryb pracy: **1 post = 1 ticket** (asystent) -> raport -> weryfikacja -> nastepny ticket

---

## 0) Zasady stałe (obowiązujące)

1) **Każda nowa funkcja → feature flag / ustawienie + spójna obsługa w aplikacji**
- `config.py` (default + fallback)
- GUI Settings (jeśli user-facing)

2) Kod składamy w **VS Code z Codexem**.

3) Po każdym tickecie: raport
- co zmieniono
- pliki
- jak testować (komendy + manual)

4) Smoke testy wg `docs/RUNBOOK_SMOKE.md` + dopisany UX smoke (clipboard/overlay/tabele).

5) Preferencja: offline-first (online lookup tylko pod flagą).

---

## 1) Standard ticketu

- Cel + zakres + DoD  
- Flagi (jeśli dotyczy)  
- Testy (unit/contract/integration/manual)  
- Ryzyka/regresje  

---

## 2) Stan projektu (DONE)

### EPIC A — Core stabilizacja + Observability

#### A1 — D4.2c NEXT_HOP (P0)
- ✅ `features.clipboard.next_hop_stepper` + GUI checkbox + guarded logic (common/navigation_events/app)
- ✅ RUNBOOK: sekcja „Clipboard / NEXT_HOP — UX smoke”

#### A2 — Observability (P1/P2)
- ✅ `renata_log.py`: safe logging (`safe_repr` + limity + brak crashy) + format `[CATEGORY] message key=value`
- ✅ throttling logów + wpięcia w state/watchery (mniej spamu)
- ✅ debug panel: thread-safe UI update + throttled refresh + snapshot + gating flagą `features.debug.panel`
- ✅ testy: `tests/test_renata_log.py` (PASS)

### EPIC B — UX “pro” (P1)

#### B1a — UI-POLISH (wejścia + spójność)
- ✅ B1a: ujednolicone etykiety pól wejściowych, PL-first, centralizacja w `strings.py`
- ✅ B1a.1: spójne tab titles + stały układ opcji (checkbox order)
- ✅ B1a.3: wspólna siatka layoutu pól (ui_layout.py) + wyrównanie kolumn w plannerach
  - ✅ rozszerzenie: Trade przerobiony na wspólną siatkę (`ui_layout.py`)
- ✅ B1a.2: nagłówki tabel wyników po PL + spójne jednostki (`strings.py` + `table_schemas.py`)
- ✅ B1a.4: sticky header + autosize kolumn tabel (czytelne nagłówki, header zawsze widoczny)

#### B1b — Required fields (Trade)
- ✅ znacznik `Stacja*` + walidacja przed run (status “Uzupełnij pole: Stacja”, bez requestu)

#### B1c — Placeholder tabs (beta)
- ✅ spójne placeholdery “Wkrótce” + mikrocopy
- ✅ gating flagami w `config.py` (`features.ui.tabs.*`)
- ✅ TAB_DEFS: jedno miejsce wyboru (OFF→Wkrótce, ON+real→real, ON+brak→Beta aktywna)

#### B2 — TRADE-UI-AGE-01: Market Age jak na Spansh (DONE)
- Cel: kontrola wieku rynku jak w Spansh (data/czas + suwak presetów).
- Zakres: widget data/czas + slider presetów; dwukierunkowa synchronizacja; brak auto-odpalania.
- DoD: zmiana suwaka/pola aktualizuje drugie; brak requestu bez kliknięcia “Wyznacz”.
- Flagi: `features.trade.market_age_slider=true`.
- Testy: manual (Trade → zmiana suwaka/pola; brak auto-run), smoke standard.
- Ryzyka: rozjazd wartości czasu przy ręcznej edycji; niejednoznaczne strefy czasowe.

#### B3 - RESULTS-CONTEXT-MENU-01 (DONE)
- Prawy klik na wynikach: kopiuj/ustaw start/cel/dodaj via/CSV/TSV.
- Dziala w Neutron + Trade; wspolny mechanizm w `gui/common.py`.
- Flaga: `features.ui.results_context_menu=false` (Settings).

#### C1 - Column Picker (DONE)
- Potwierdzenie: fallback gdy wszystkie kolumny odznaczone -> default_visible_columns.
- Potwierdzenie: nieznane kolumny z ustawien sa filtrowane, brak crasha.
- Brak auto-run: zmiana tylko re-renderuje UI.

#### C2 - Treeview renderer + sort (DONE)
- Treeview dla wynikow Neutron + Trade (z column picker).
- Sort po kliknieciu naglowka, stabilny dla liczb/stringow/pustych.
- Flaga: features.tables.treeview_enabled.

#### C2.1 - Treeview UX polish (DONE)
- LP jako pierwsza kolumna; sort po LP resetuje kolejnosc.
- Wyrownania: LP prawa, System lewa, reszta srodek.
- Wskaznik sortu w naglowku.

#### C3 - Rollout Treeview na pozostale planery (DONE)
- Treeview podpiety do: Ammonia, ELW, HMC, Exomastery, Riches.
- LP dodane we wszystkich tabelach (tak jak w Neutron).
- Testy smoke: backend + journal PASS.

#### C4 - Treeview UX polish & decyzje wizualne (DONE)
- Separatory w naglowkach usuniete (mniej ciezaru wizualnego).
- Header i dane maja spojne wyrownania.
- Hover row dodany dla czytelnego feedbacku.
- Testy smoke: backend + journal PASS.

#### M-03 - Busy + blokada multi-clicka (DONE)
- Run blokowany na czas obliczen w kazdym plannerze.
- Przycisk Run jest disabled podczas pracy; status widoczny (label lub status bar).
- Busy zwalniany w success i error (finally).
- Testy smoke: backend + journal PASS.

#### D1 - EDSM helpery (online provider) (DONE)
- Opcjonalny provider EDSM (system lookup) pod flaga.
- Cache + throttling, brak crashy przy bledach/timeout.
- Flaga: `features.providers.edsm_enabled=false`.
- Testy smoke: backend + journal PASS.

#### D2 - EDSM rollout (DONE)
- D2a: flaga + zero requestow gdy OFF.
- D2b: klient HTTP (timeout + kontrolowane bledy).
- D2c: cache TTL (RAM).
- D2d: provider lookup_system (offline-first).
- D2e: pilot UI (AddEntry coords).
- D2f-1: autocomplete Start/Cel fallback do EDSM.

#### M-05 - Zapamietywanie sortu + ukladu kolumn (DONE)
- Sort (kolumna + kierunek) zapisywany per schema i odtwarzany po restarcie.
- Fallback gdy sortowana kolumna ukryta (LP lub pierwsza widoczna).
- Flaga: `features.tables.persist_sort_enabled=true`.
- Testy smoke: backend + journal PASS.

#### M-06 - Presety kolumn (Column Picker) (DONE)
- Presety: Minimal / Domyslny / Pro per schema (definicje w schemie).
- Zastosowanie presetu aktualizuje visible_columns i zapisuje ustawienie.
- Sort zachowuje fallback po zmianie presetu.
- Testy smoke: backend + journal PASS.

#### M-06.1 - Popup UX + bug Dystans (DONE)
- Dystans [ly] formatowany poprawnie (fallback tylko gdy brak danych).
- Popupy: toggle open/close + zapamietanie pozycji (Kolumny/Progi/Advanced).
- Testy smoke: backend + journal PASS.

#### M-07 - Persistencja pozycji i rozmiaru okien (DONE)
- Zapamietanie pozycji okien (main/settings/popupy) + bezpieczny fallback poza ekranem.
- Rozmiar zapisywany tam, gdzie ma sens (main/settings/kolumny).
- Dane w `window_positions` w user_settings.json.
- Testy smoke: backend + journal PASS.

#### M-04 - Panel bledow + ostatnie zapytanie SPANSH (DONE)
- Status SPANSH: sukces, brak wynikow, blad/timeout (czytelne komunikaty).
- Ostatnie zapytanie do Spansh jako sekcja zwijana (debug).
- Flaga: `features.debug.spansh_last_request=false`.
- Testy smoke: backend + journal PASS.

#### M-08 - Empty states + microcopy (DONE)
- Empty/busy/error w UI bez messageboxow; czytelne komunikaty PL/EN.
- Brak "martwych" tabel przy 0 wynikach.

#### M-09 - Presety kolumn v2 (per tab) (DONE)
- Presety per tab; zapis i odtworzenie po restarcie.
- Zmiana presetu aktualizuje widok bez crashy.


#### TTS-01 - Text Preprocessor (DONE)
- Message IDs + filtr TTS (mowi tylko kontrolowane komunikaty).
- Text preprocessor generuje krotkie, mowialne teksty PL.

#### TTS-02 - Strojenie glosu (DONE)
- Parametry: tempo i pauzy (Piper) + wolniejsze pyttsx3.
- Twarde reguly ciszy: cooldown globalny i per-kategoria.

#### TTS-02b - Pokladowe microcopy PL (DONE)
- Pokladowe, krotkie komunikaty bez emocji i bez wykrzyknikow.
- Spojne pauzy (kropki) + segmenty kontekstowe.

#### TTS-02c - UTF-8 + mikro-polish (DONE)
- Naprawione kodowanie UTF-8 w text_preprocessor.
- Dwie poprawki tekstu: ROUTE_DESYNC + FIRST_DISCOVERY.

#### BUG-SETTINGS-LOGDIR-01 (DONE)
- Naprawa zapisu log_dir (strip() + pusty => None).
- Smoke: backend + journal PASS.

#### BUG-ROUTE-TRANSIT-01 (DONE)
- Po route_end czyszczenie trasy (koniec trybu przelotowego).
- Smoke: backend + journal PASS.

#### TTS-03 - Scenariusze FREE (DONE)
- Polityka FREE: critical/context/silent + reguly ciszy.
- Flaga: `features.tts.free_policy_enabled=true`.

#### UX-SETTINGS-01 - FREE Settings Profile (DONE)
- Ustawienia uproszczone (5?7 opcji) + ukrycie dev/advanced.
- Checkbox: "Minimalny glos (polecane)" (policy FREE).

#### BUG-TTS-PL-01 - UTF-8 w Piper (DONE)
- Wymuszone UTF-8 w piper_tts, pelne polskie znaki.
- Testowa linia w `tools/tts_preview.py` (Zazolc gesla jazn).

#### TTS-TOOLS - Preview (DONE)
- `tools/tts_preview.py` z trybem `--force` i `--pause` do strojenia TTS.

---

## 3) Aktualny UX stan (skrót)

- Wejścia w plannerach: spójne labelki + jednostki, spójny układ opcji, wspólna siatka layoutu.
- Tabele: nagłówki PL + jednostki; sticky header + autosize kolumn.
- Tabele (Treeview): sort, LP i column picker pod flagami.
- Wyniki: menu kontekstowe (prawy klik) pod flaga `features.ui.results_context_menu`.
- Trade: walidacja “Stacja wymagana”; autocomplete stacji działa offline z cache (bez gry cache może być puste), online lookup opcjonalny pod flagą.
- Debug: debug panel i logger utwardzone, throttling ogranicza spam.

---

## 4) Flagi kluczowe (obecne)

- Clipboard:
  - `features.clipboard.next_hop_stepper`
- Debug:
  - `features.debug.panel`
  - `features.debug.autocomplete` (jeśli istnieje: powinno być default OFF)
  - `features.debug.spansh_last_request`
- UI Tabs (beta):
  - `features.ui.tabs.tourist_enabled`
  - `features.ui.tabs.fleet_carrier_enabled`
  - `features.ui.tabs.colonisation_enabled`
  - `features.ui.tabs.galaxy_enabled`
- UI (wyniki):
  - `features.ui.results_context_menu`
- Tabele:
  - `features.tables.column_picker_enabled`
  - `features.tables.treeview_enabled`
  - `features.tables.persist_sort_enabled`
- Providerzy (online):
  - `features.providers.edsm_enabled`
- Trade (online lookup):
  - `features.trade.station_lookup_online` / `features.providers.system_lookup_online` (wg realnych kluczy w config)

---

## 5) Testy / komendy (minimum)

### Unit / contract
- `python -m unittest tests.test_spansh_payloads`
- `py -m unittest tests/test_renata_log.py`

### Smoke
- `python tools/smoke_tests_beckendy.py`
- `python tools/smoke_tests_journal.py`

**Ostatni wynik smoke:** 2026-01-26 ? backend 15/15 OK, journal 5/5 OK

### Manual (GUI)
- `py main.py`
- UX smoke: NEXT_HOP (clipboard + overlay), tabele (naglowki, sticky, autosize), Trade required field, menu kontekstowe wynikow.

---

## 6) Known gotchas / zasady repo

### user_settings.json
- `user_settings.json` to lokalny plik ustawien dev-a.
- Nie commitowac.
- Jest ignorowany przez git (`.gitignore`).
- Start: skopiuj `user_settings.example.json` -> `user_settings.json`.
- Jesli kiedys byl trackowany: `git rm --cached user_settings.json` + commit.

---

## FREE RELEASE — BLOCKERS (P0)

- TTS-01 - Text preprocessor (glos Renaty) (DONE)
- TTS-02 - Parametry glosu (tempo, pauzy) (DONE)
- TTS-03 - Scenariusze FREE (co Renata mowi / czego nie) (DONE)
- UX-SETTINGS-01 - FREE Settings Profile (ukrycie opcji) (DONE)
  - Dodac checkbox: "Minimalny glos (polecane)" / "Tryb FREE" (kontrola policy)
- FREE release nie wychodzi, dopoki powyzsze nie sa DONE.
- FREE = tylko PL (EN po FREE).

---

## 7) NEXT (priorytety)

### P0
- (puste)

### P1
- Jezyk EN (po FREE)

### P2
- (puste)

### FUTURE / VISION (kierunki zatwierdzone)
- External Data Helpers (offline-first): helpery jako klasy funkcji (nie zakladki): EDSM (coords/bodies/hotspoty), EDTools/EDMining (mining), Inara (rynek/inventory) pozniej; zawsze pod flagami, OFF domyslnie.
- D2f-2/D2f-3 — dalszy rollout EDSM (po FREE).
- Jezyk EN = P2 / po FREE (nie blocker).
- Mining Helpers (bez zakladek): Hotspot Helper (najblizsze hotspoty + krokowy clipboard), Mining Sell Assist (ranking zysk/cena/t/dystans/popyt/wiek rynku, doprecyzowanie dialogowe).
- Route Awareness + Cockpit HUD: milestony 25/50/75/100, status utraty/zakonczenia trasy; minimalistyczny HUD (fake-3D) + TTS, bez per-hop spamu.
- Pro Actions + Decision Panels: akcje zalezne od typu danych (system/stacja/body) + lekkie panele decyzji (ostrzezenia, "dlaczego").
- Session Memory & Resume: pamiec ostatniego planner/parametry/route/hop + opcjonalne wznowienie po przerwie; bez auto-run.
- Captain's Log (voice-assisted): glosowe tworzenie wpisow, notatki i lokalizacje; dane lokalne, prywatne.
- Instructor Mode (opt-in): kontekstowe podpowiedzi dla nowych graczy; OFF domyslnie; fundament pod przyszla monetyzacje.
- Symbioza danych (2-way helpers): opt-in upload do EDSM/EDTools; etapy: manual -> auto w tle; brak globalnej bazy Renaty.
### Roadmapa - Cel Renaty (glos i UX)
- Cel: pokladowy asystent Elite Dangerous (journal events, akcje w GUI, spojny glos, brak spamu i cooldowny).
- TTS: edge-tts (jakosc/komplikacja) + kolejka, krotkie wypowiedzi, retry/backoff.
- TTS jest blockerem FREE i definiuje tozsamosc Renaty.
- STT pojawia sie po FREE, po feedbacku uzytkownikow (nie blocker).
- Speech Manager: kolejka + priorytety (ALERT>ACK>STATUS>LORE), cancel lore na alert, anti-repeat/cooldown.
- Policy layer: tryb minimalny w stresie, lore opt-in, brak recytowania parametrow trasy.
- Content/Lore DB: warianty wypowiedzi + cooldowny; lore po FSDJump: pytanie 'chcesz ciekawostke?'.
- Sterowanie glosem: push-to-talk na start, mute STT gdy TTS mowi; wake word pozniej.
- MVP: SpeechManager, Content DB + selector, STT offline + PTT, Intent router, TTS Edge + SSML presets, LoreDB hook po FSDJump.
- Online helpery moga poprawiac precyzje UX (np. dystanse Neutron z coords), ale zawsze pod flaga i nie wymagane.
- Helpery danych sa "opcjonalne narzedzia", nie zaleznosci; offline-first zawsze wygrywa.
- Mining helpers bez zakladek: hotspoty + sprzedaz jako prowadzenie krokowe, bez automatyzacji sterowania gra.
- Cockpit HUD to minimalny status (route milestones), nie nowa "scena UI"; TTS ma wspierac, nie narrac.
- Session memory, Captain's Log i Instructor Mode to tryby opt-in, bez spamu i bez auto-wykonan.

---

## 8) Tryb pracy w nowym czacie (procedura)
1) Wybieramy 1 ticket (max 1–3 dopiero później).
2) Codex implementuje pod flagą + raport.
3) Patryk robi smoke wg runbook + UX smoke.
4) Jeśli OK → merge → następny ticket.