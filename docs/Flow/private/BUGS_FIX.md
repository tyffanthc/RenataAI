# BUGS_FIX.md

## Nazwa
Audit bugow i poprawek (repo/runtime/docs)

## Typ
Dokument roboczy audytu technicznego (diagnostyka + plan napraw)

## Aktualizacja
2026-02-26

---

## Legenda statusu
- `[x]` sprawdzone / potwierdzone / naprawione
- `[~]` czesciowo sprawdzone / wymaga doprecyzowania
- `[ ]` do naprawy / do wdrozenia
- `N/D` nie dotyczy etapu

---

## 1. Najwazniejsze zdanie `[x]`
Etap 1 audytu potwierdza stabilny baseline runtime (kluczowe smoke-packi przechodza), ale wykrywa realne bugi UX/logiki oraz duzy dlug dokumentacyjny (mojibake/kodowanie), ktore trzeba domknac osobnymi ticketami.

---

## 2. Zakres audytu (Etap 1) `[x]`
Etap 1 obejmuje:
- szybki przeglad dokumentacji `docs` (skalowanie + skan problemow kodowania),
- automatyczny check skladni (`compileall`),
- uruchomienie kluczowych smoke/regresji (eksploracja/cash-in/mapa/playerdb/TTS/runtime safety),
- reczny audit krytycznych modulow pod katem bugow logicznych/wykonawczych/UX,
- przygotowanie listy potwierdzonych problemow i planu napraw.

Etap 1 nie obejmuje jeszcze:
- semantycznego przegladu wszystkich `*.md` linia-po-linii (121 plikow),
- pelnego przegladu wszystkich modulow GUI i helperow tabel (poza hotspotami),
- pelnego przegladu wszystkich `except/pass` w repo.

---

## 3. Co zostalo sprawdzone `[x]`
### 3.1 Dokumentacja (docs)
- policzono skale dokumentacji (`docs`: 121 plikow),
- sprawdzono wzorzec dokumentow statusowych (`ACTION_CASH_IN_ASSISTANT.md`),
- sprawdzono aktualny snapshot `docs/internal/LAST_TICKET.MD`,
- przeskanowano `docs/**/*.md` pod podejrzane wzorce mojibake (skrypt Python; wynik w sekcji 5.4),
- recznie sprawdzono kluczowe dokumenty runtime:
  - `docs/Flow/private/docs/actions/ACTION_EXPLORATION_SUMMARY.md`
  - `docs/Flow/private/docs/policies/VOICE_CORE_RULES.md`

### 3.2 Checki automatyczne
- `py -m compileall app gui logic tests` -> PASS
- kluczowe smoke packi -> PASS:
  - `F16`, `F19`, `F20`, `F21`, `F23`, `F24`, `F28`, `F29`

### 3.3 Przeglad hotspotow kodu
- eksploracja FSS / summary / recovery / wycena
- TTS preprocessor i template path
- cash-in -> neutron handoff
- tabela Neutron / Trade (render + szerokosci kolumn)
- mapa `Dziennik -> Mapa`

---

## 4. Wynik ogolny Etapu 1 `[~]`
- `[x]` Skladnia repo (Python) jest stabilna.
- `[x]` Kluczowe smoke-packi FREE/PUB przechodza.
- `[~]` Runtime ma jeszcze niespojnosci UX/logiki (zwlaszcza route/neutron i tabele Spansh).
- `[ ]` Dokumentacja ma powazny problem kodowania (mojibake) w wielu plikach.
- `[~]` TTS brzmi lepiej po F28, ale finalizacja interpunkcji nadal jest zbyt agresywna.

---

## 5. Potwierdzone problemy / ryzyka (Etap 1)

### 5.1 Neutron: niespojny status sukcesu vs fallback Cash-In `[x]`
Objaw:
- Po `Cash-in -> Ustaw trase (FAST)` Neutron potrafi pokazac zielony status `Znaleziono 2`,
- a Cash-In jednoczesnie traktuje wynik jako brak realnej trasy neutronowej (fallback).

Przyczyna (potwierdzona w kodzie):
- Cash-In uznaje `len(route) <= 2` za brak realnej neutronowki:
  - `gui/app.py:1885`
- Neutron tab emituje status sukcesu dla dowolnego `len(tr)`:
  - `gui/tabs/spansh/neutron.py:490`
  - `gui/tabs/spansh/neutron.py:491`

Skutek:
- mylacy UX / sprzeczne komunikaty miedzy modułami.

Proponowana naprawa:
1. Ujednolicic kryterium sukcesu (`len<=2` = status fallback, nie zielony sukces).
2. Rozdzielic "route returned by API" od "route operationally useful".

---

### 5.2 Tabele Spansh (Trade/Neutron): slaba responsywnosc i reflow `[x]`
Objaw:
- Tabele wygladaja jak "zepsute" po cash-in/neutron (duzo pustej przestrzeni, waskie kolumny).
- `Trade` jest szczegolnie podatny na zly layout przy zmianie rozmiaru okna.

Przyczyna (potwierdzona + hotspoty):
- renderer tabel opiera szerokosci o tresc (`content-based widths`):
  - `gui/common_tables.py:590`
  - `gui/common_tables.py:656`
- `Trade` dodatkowo wymusza tryb kompaktowy i ustawia `stretch=False` dla kolumn:
  - `gui/tabs/spansh/trade.py:765`
  - `gui/tabs/spansh/trade.py:776`

Skutek:
- slaba adaptacja do szerokosci okna,
- zla czytelnosc przy malych wynikach (np. Neutron 2 wiersze).

Proponowana naprawa:
1. Wspolny helper "responsive table columns" (fixed + elastic columns).
2. Reflow po aktywacji zakladki / po renderze w tle.
3. Audit `Trade` i `Trade Compare` jako pierwsze zakladki.

---

### 5.3 FSS progress milestones: ryzyko resetu progresu przy `FSSDiscoveryScan` `[~]`
Objaw (z gameplayu):
- mozliwe anomalie milestone (np. komunikat 25% przy stanie wygladajacym na >25%).

Stan:
- przedwczesne `System w pelni przeskanowany` przez `FSSAllBodiesFound` zostalo juz naprawione (F24/FSS hotfix),
- ale pozostaje ryzyko semantyczne resetu progresu FSS.

Hotspot:
- `handle_fss_discovery_scan()` resetuje caly stan progresu:
  - `logic/events/exploration_fss_events.py:351`
  - `logic/events/exploration_fss_events.py:361`

Uwagi:
- To moze byc poprawne przy wejsciu do nowego systemu,
- ale wymaga doprecyzowania warunkow resetu (czy event dotyczy tego samego systemu / re-entry do FSS).

Status:
- `[~]` Ryzyko logiczne potwierdzone w kodzie, ale wymaga odtworzenia z payloadem journala dla twardego reproduktora.

---

### 5.4 Dokumentacja: mojibake / kodowanie w wielu plikach `docs` `[~]`
Objaw:
- czesc dokumentow zawiera rozjechane znaki (`mojibake`), co psuje czytelnosc i utrudnia audit.

Pomiar (skrypt skanujacy `docs/**/*.md`, wzorce mojibake):
- `files_with_suspect_mojibake = 26`

Przykladowe hotspoty:
- `docs/Flow/private/docs/actions/ACTION_EXPLORATION_SUMMARY.md` (wysoki poziom)
- `docs/Flow/private/docs/policies/VOICE_CORE_RULES.md`
- `docs/Flow/private/Features2/PERSONAL_GALAXY_MAP_SPEC.md`
- `docs/internal/LAST_TICKET.MD`

Skutek:
- trudniejsza analiza i maintenance,
- ryzyko kopiowania uszkodzonych tekstow do runtime/TTS.

Proponowana naprawa:
1. "Encoding cleanup pass" per pakiet dokumentow (actions/policies -> features -> internal).
2. Po cleanupie: szybki audit statusow i linkow.

Status:
- `[~]` Wykonano cleanup pass dla kluczowych docs runtime (`ACTION_EXPLORATION_SUMMARY`, `VOICE_CORE_RULES`, `PERSONAL_GALAXY_MAP_SPEC`, `LAST_TICKET`) oraz lokalne poprawki statusow/numeracji.
- `[ ]` Nadal brak pelnego cleanupu calego `docs/**` i recznego review wszystkich plikow po konwersji.

---

### 5.5 "O programie": release URL przypiety do starego taga `[x]`
Objaw:
- link w `Pomoc -> O programie` nie prowadzi do najnowszego release.

Potwierdzenie:
- `gui/app.py:531`
- aktualnie: `.../releases/tag/v0.9.1-preview`

Wdrozone:
- zmieniono na `https://github.com/tyffanthc/RenataAI/releases/latest`.

---

### 5.6 TTS finalizacja: agresywna zamiana interpunkcji pogarsza naturalnosc mowy `[x]`
Objaw:
- mimo poprawionej verbalizacji liczb, czesc wypowiedzi brzmi sztucznie,
- przecinki sa zamieniane na kropki, co moze psuc rytm i czytanie liczb/list.

Potwierdzenie:
- `logic/tts/text_preprocessor.py` (`_finalize_tts`)
- linia z globalna zamiana:
  - `text = text.replace(\"?\", \".\").replace(\"!\", \".\").replace(\",\", \".\")`

Skutek:
- gorsza prozodia,
- mniej naturalne czytanie duzych liczb i list.

Wdrozone:
1. `_finalize_tts()` nie zamienia juz globalnie przecinkow na kropki.
2. Przecinki zostaja zachowane (lepsza prozodia list/klauzul, bez psucia verbalizacji liczb).

Follow-up (later):
- semantyczne pauzy TTS w wybranych template'ach zamiast surowych przecinkow.

---

### 5.7 Exploration value recovery: nadal heurystyczne okno odtwarzania `[~]`
Stan:
- okna recovery zostaly zwiekszone (F28 ticket 7):
  - `logic/events/exploration_value_recovery.py:29` / `:160` -> `12000`
  - `app/main_loop.py:95` -> bootstrap `8000`
- dodano diagnostyke recovery.

Ryzyko:
- bardzo dlugie sesje nadal moga wyjsc poza okno (zwlaszcza gdy `SAAScanComplete` i odpowiadajacy `Scan` sa daleko od siebie).

Status:
- `[~]` Znacznie poprawione, ale nie jest to jeszcze deterministyczny replay calej sesji.

Proponowana naprawa (later):
- checkpointing wartości eksploracji albo replay per-session marker zamiast stalego okna linii.

---

### 5.8 `except Exception: pass` - wysoki dlug diagnostyczny w GUI/runtime `[~]`
Objaw:
- repo ma duzo miejsc z bezglosnym tlumieniem wyjatkow.

Szybki skan:
- liczne hotspoty w `gui/tabs/journal_map.py`, `gui/common_tables.py`, `gui/tabs/spansh/*`, `logic/utils/notify.py`, `app/main_loop.py`.

Uwagi:
- czesc z nich jest uzasadniona (cleanup Tkinter, destroy race, optional UI),
- ale czesc maskuje realne bugi i utrudnia reprodukcje.

Status:
- `[~]` Problem potwierdzony, ale Etap 1 nie klasyfikuje jeszcze wszystkich `except/pass`.

Wdrozone (selektywny audit / krytyczne hotspoty):
- `logic/events/exploration_summary.py`:
  - cichy `except/pass` przy auto-triggerze Cash-In po summary -> throttlowany `WARN` log (`cash-in trigger failed`).
- `logic/insight_dispatcher.py`:
  - cichy `except/pass` przy odczycie snapshotu trybu dla combat-silence -> throttlowany `WARN` log.
- `gui/app.py`:
  - ciche `except/pass` przy programowym otwieraniu zakladki Spansh/Neutron -> throttlowany `APP` fallback log.

Status po poprawkach:
- `[x]` Najbardziej mylace ciche tlumienia w krytycznych flow (summary/cash-in, dispatcher combat silence, otwieranie Neutron) sa utwardzone diagnostycznie.
- `[x]` Selektywny audit objal glowny UI/runtime hot-path:
  - GUI/Tk helpery i zakladki: `common_tables`, `empty_state`, `ui_thread`, `window_positions`, `menu_bar`, `common_autocomplete`, `pulpit`, `logbook`, `journal_map`, `settings`, `settings_window`, `dialogs/add_entry`
  - Spansh: `planner_base`, `spansh/neutron.py`, `spansh/trade.py`, `spansh/__init__.py`
  - runtime/app: `gui/app.py`, `app/main_loop.py`, `app/state.py`, `app/route_manager.py`
  - cache/persist/state: `logic/cache_store.py`, `cash_in_offline_index_builder.py`, `entry_repository.py`, `context_state_contract.py`, `logbook_feed_cache.py`
  - playerdb/cash-in/mapa: `event_handler.py`, `cash_in_station_candidates.py`, `personal_map_data_provider.py`
  - eksploracja/exobio/FSS: `exploration_summary.py`, `exploration_fss_events.py`, `exploration_bio_events.py`, `exploration_dss_events.py`, `exploration_awareness.py`, `exploration_high_value_events.py`, `exploration_value_recovery.py`, `fuel_events.py`, `high_g_warning.py`
  - glos/TTS: `notify.py`, `piper_tts.py`
- `[~]` Zostaly glownie:
  - intencjonalne `pass`/fallbacki w `gui/app.py` (np. `queue.Empty`, `tk.TclError`, parse UI), ktore nalezy whitelistowac jako swiadome
  - szeroki line-by-line audit calego repo pod `except/pass` (poza selektywnym hot-path)
  - aktualizacja whitelisty i pokrycia w tym dokumencie po kolejnych etapach audytu

Proponowana naprawa (pozostale):
1. Zamknac whitelistę intencjonalnych `pass` (zwlaszcza `gui/app.py`: `queue.Empty`, `tk.TclError`, parse fallback UI).
2. Dalszy audit line-by-line tylko tam, gdzie nie ma jeszcze throttlowanej diagnostyki i fallback maskuje realny bug.

---

## 6. Co juz jest domkniete (zeby nie dublowac pracy) `[x]`
Etap 1 potwierdza, ze ponizsze klasy bugow byly niedawno naprawione i maja testy/smoke:
- przedwczesny full-scan FSS przez `FSSAllBodiesFound`,
- High-G trigger z `Scan` (przeniesiony na approach/orbite),
- DSS value upgrade i recovery,
- `NaN` fallback w kartografii (`Planet Type`),
- sekwencja glosu `exploration summary -> cash-in`,
- TTS verbalizacja liczb (Cr/%/LY) + `raw_text_first` finalizacja,
- izolacja testow `playerdb` i narzedzie cleanup fixture danych.

---

## 7. Proponowany podzial dalszego audytu (kolejne etapy) `[ ]`
### Etap 2 (P0/P1 runtime UX i spojnosc)
- Neutron/Cash-In status success/fallback (sekcja 5.1)
- responsywne tabele Spansh (`Trade`, `Neutron`, `Trade Compare`) (sekcja 5.2)
- `O programie` release URL latest (sekcja 5.5)

### Etap 3 (eksploracja / FSS semantics)
- reprodukcja i fix resetow milestone FSS (`FSSDiscoveryScan`) (sekcja 5.3)
- dopiecie diagnostyki `SAASignalsFound` per-body (jesli gameplay nadal raportuje braki calloutow)

### Etap 4 (docs + TTS polish debt)
- cleanup mojibake w `docs` (sekcja 5.4)
- poprawa finalizacji interpunkcji TTS (sekcja 5.6)
- selektywny audit `except/pass` (sekcja 5.8)

---

## 8. Test checklist audytu (Etap 1 wykonane) `[x]`
- `py -m compileall app gui logic tests` -> PASS
- smoke:
  - `F16`, `F19`, `F20`, `F21`, `F23`, `F24`, `F28`, `F29` -> PASS
- reczny przeglad hotspotow:
  - eksploracja FSS/summary/recovery
  - TTS preprocessor
  - cash-in -> neutron
  - common tables / Spansh tabs
  - mapa `Dziennik -> Mapa`

---

## 9. Zdanie ochronne `[x]`
Ten dokument jest audytem etapowym. Brak wpisu w Etapie 1 nie oznacza braku bledu w repo - oznacza tylko, ze dany obszar nie zostal jeszcze zbadany z wystarczajaca glebią.

---

## 10. Etap 2 - dodatkowe findings (docs/runtime UX/spojnosc) `[x]`
Etap 2 rozszerza audit o:
- spojnosc dokumentacji statusowej (`LAST_TICKET`, polityki/specy),
- dodatkowe problemy jakosciowe w kodzie (komentarze/docstringi z mojibake),
- potwierdzenie hotspotow UX z gameplayu (Neutron/Trade tabele, statusy).

### 10.1 `LAST_TICKET`: niespojny naglowek sekcji vs zawartosc `[x]`
Objaw:
- Sekcja `### FREE (PUB) - NIE WDROZONE` zawierala wiele pozycji oznaczonych jako `DONE`.

Potwierdzenie:
- naglowek sekcji: `docs/internal/LAST_TICKET.MD:86`
- przyklad wpisow `DONE` bezposrednio pod nim: `docs/internal/LAST_TICKET.MD:88+`

Skutek:
- mylacy status dla planowania prac,
- latwo przegapic realne TODO.

Wdrozone:
- lokalna korekta naglowka sekcji snapshotu na `FREE (PUB) - SNAPSHOT HISTORYCZNY (wymaga porzadkowania sekcji)`.
- usuwa to mylacy sygnal `NIE WDROZONE` dla listy zawierajacej pozycje `DONE`.

Follow-up (P2, opcjonalny):
- pelna przebudowa snapshotu na sekcje `WDROZONE / W TOKU / NIEWDROZONE / DEFERRED`.

---

### 10.2 `VOICE_CORE_RULES`: duplikacja numeracji sekcji `[x]`
Objaw:
- Dokument mial dwa naglowki `## 11` oraz duplikaty numeracji appendow.

Potwierdzenie:
- `docs/Flow/private/docs/policies/VOICE_CORE_RULES.md` (sekcje po follow-up F28 append)

Skutek:
- utrudnione linkowanie i odwolania z innych docs,
- nizsza wiarygodnosc dokumentu polityki.

Wdrozone:
- renumeracja sekcji po appendach F28 (bez zmiany tresci merytorycznej), w tym `11..16` i `16.1`.

---

### 10.3 Kod: mojibake w komentarzach/docstringach (jakosc utrzymania) `[~]`
Objaw:
- W czesci plikow `.py` wystepuja komentarze/docstringi z rozjechanym kodowaniem.

Przyklady potwierdzone:
- `gui/tabs/spansh/trade.py`:
  - komentarz autocomplete stacji (`D3b ...`) - okolice `:384`
  - docstring helpera stacji - okolice `:1734`
- `logic/events/exploration_fss_events.py`
  - komentarze/docstringi FSS z mojibake (np. opis `FSSDiscoveryScan`) - okolice `:353`

Skutek:
- runtime zwykle dziala poprawnie (to glownie komentarze/docstringi),
- ale utrudnia maintenance i audit,
- zwieksza ryzyko kopiowania uszkodzonych tekstow do komunikatow runtime.

Status:
- `[~]` Problem potwierdzony, ale Etap 2 nie robi jeszcze pelnego cleanupu kodowania `.py`.

Wdrozone (hotspoty, etapowy cleanup):
- `gui/tabs/spansh/trade.py` - poprawione komentarze/docstringi z mojibake (autocomplete / fallback / docstringi helperow).
- `logic/events/exploration_fss_events.py` - poprawione komentarze/docstringi FSS + oczywisty runtime log `[FSS] ... cial`.

Status po poprawkach:
- `[~]` Hotspoty potwierdzone w audycie sa oczyszczone, ale brak pelnego cleanupu komentarzy/docstringow we wszystkich `.py`.

---

### 10.4 `O programie`: stale odwolanie do konkretnego release tag `[x]`
Objaw:
- `Pomoc -> O programie` otwieral stary tag release zamiast aktualnego release.

Potwierdzenie (historyczne):
- `gui/app.py:531` -> `.../releases/tag/v0.9.1-preview`

Wdrozone:
- URL zmieniony na `.../releases/latest`.

---

### 10.5 Neutron/Cash-In + tabele Spansh: hotspot UX potwierdzony gameplayem `[x]`
Etap 1 wykryl problem statycznie. Etap 2 potwierdzil go praktycznie jako priorytet UX:
- Cash-In fallback (`len<=2`) vs zielony status Neutron `Znaleziono 2`
- tabela Neutron/Trade wyglada jak "zepsuta" przy malych wynikach i braku reflow

Ref (kod):
- `gui/app.py` (cash-in neutron fallback logic)
- `gui/tabs/spansh/neutron.py` (status + reflow)
- `gui/tabs/spansh/trade.py` (reflow)
- `gui/tabs/journal_map.py` (Trade Compare reflow)

Wdrozone (Etap 3):
- Neutron dla trasy 2-punktowej pokazuje fallback wording zamiast zielonego sukcesu.
- responsywny reflow tabel wdrozony dla `Neutron`, `Trade`, `Trade Compare` (mapa).

---

### 10.6 Test hygiene `playerdb`: Etap 2 potwierdza poprawe dla glownego flow `[x]`
Potwierdzenie (przeglad testow + smoke):
- `F19` smoke jest odizolowany od runtime DB (ticket F29-1),
- `F20/F21` smoke mapy i provider tests korzystaja z `TemporaryDirectory` / temp `player_local.db`,
- `F29` smoke dodatkowo pilnuje braku side-effectow na runtime DB.

Wniosek:
- glowne wektory skażenia `playerdb` przez testy sa domkniete.

---

## 11. Zaktualizowany plan kolejnych etapow audytu / napraw `[~]`
### Etap 3 (P0/P1 runtime UX i spojnosc) `[x]`
- `[x]` Neutron/Cash-In status success/fallback (sekcje 5.1 + 10.5) - Neutron dla trasy 2-punktowej pokazuje teraz fallback wording zamiast zielonego sukcesu.
- `[x]` responsywne tabele Spansh (`Trade`, `Neutron`, `Trade Compare`) (sekcje 5.2 + 10.5) - wdrozone lokalnie: `Neutron` (reflow `system_name`), `Trade` (elastyczne kolumny + reflow), `Trade Compare` (reflow kolumn `system/station/commodity`).
- `[x]` `O programie` release URL latest (sekcja 10.4)
- `[x]` porzadek snapshotu `LAST_TICKET` (sekcja 10.1) - lokalna korekta naglowka sekcji statusowej wykonana.

### Etap 4 (eksploracja / FSS semantics)
- `[x]` reprodukcja i fix resetow milestone FSS (`FSSDiscoveryScan`) (sekcja 5.3)
- `[x]` diagnostyka `SAASignalsFound` per-body (log reasons/count, bez zmiany semantyki TTS)

### Etap 5 (docs + kodowanie + TTS polish debt) `[~]`
- `[~]` cleanup mojibake w `docs` (sekcje 5.4 + 10.2) - kluczowe docs runtime poprawione; brak pelnego cleanupu `docs/**`
- `[~]` cleanup mojibake w komentarzach/docstringach `.py` (sekcja 10.3) - hotspoty (`trade.py`, `exploration_fss_events.py`) poprawione, pelny cleanup nadal pending
- `[x]` poprawa finalizacji interpunkcji TTS (sekcja 5.6)
- `[~]` selektywny audit `except/pass` (sekcja 5.8) - krytyczne flow + routery (`event_handler.py`) + wybrane helpery GUI (`common_autocomplete`, `common_route_progress`, `common_tables`, `empty_state`, `settings`, `pulpit`) + `spansh/planner_base` + `spansh/neutron.py` + `notify.py` + eksploracja (`exploration_summary.py`, `exploration_fss_events.py`, `exploration_bio_events.py`, `exploration_dss_events.py`, `exploration_high_value_events.py`, `exploration_awareness.py`, `exploration_value_recovery.py`, `high_g_warning.py`) utwardzone diagnostycznie

---

## 12. Audit coverage (co sprawdzone / czego jeszcze nie) `[~]`
### 12.1 Pokrycie sprawdzone (Etap 1-3) `[x]`
- eksploracja:
  - FSS milestones / full-scan flow (hotspoty)
  - exploration summary / cash-in sequencing
  - exploration value recovery (okno + diagnostyka)
- TTS:
  - `text_preprocessor` (`raw_text_first`, verbalizacja liczb, finalizacja)
  - kluczowe message templates i ścieżki runtime
- cash-in:
  - handoff do route/neutron
  - statusy i TTS UI callouty (na poziomie smoke + hotspotów)
- mapa (`Dziennik -> Mapa`):
  - shell/render/drilldown/warstwy/tooltip/PPM (przez F20/F21/F22/F23 smoke)
- playerdb:
  - ingest/query/provider baseline + test isolation/hygiene
- runtime safety:
  - focus-safe policy
  - auto-refresh mapy po `playerdb_updated`
  - hardening low-fuel transient
- dokumentacja:
  - skan mojibake + hotspoty statusów/polityk

### 12.2 Pokrycie czesciowe `[~]`
- Spansh tabs UX/layout:
  - Neutron: hotspoty potwierdzone i poprawione (status + reflow)
  - Trade: hotspot responsywnosci poprawiony lokalnym reflow
  - Trade Compare: hotspot responsywnosci poprawiony lokalnym reflow
    - follow-up gameplay: usunieto kolumne `Stacja` w mapowym `Trade compare` (redundantna w tym widoku), zapewniono stale miejsce dla `Cena/Age` i reflow tylko przy zmianie szerokosci widgetu (bez walki z recznym resize kolumn).
- `except/pass`:
  - zidentyfikowany problem skali i hotspoty
  - brak klasyfikacji wszystkich miejsc (uzasadnione vs ryzykowne)
- dokumentacja:
  - skan + hotspoty potwierdzone
  - brak pelnego cleanupu kodowania

### 12.3 Pokrycie jeszcze nieobjete / niewystarczajace `[ ]`
- pelny audit obliczen handlowych (`Trade`) vs specy i dane wejscia
- pelny audit wydajnosci GUI przy duzych tabelach/payloadach
- pelny audit wszystkich providerow online (retry/backoff/circuit paths poza cash-in)
- pelny audit STT/voice-first (PRO/deferred)
- pelny line-by-line audit wszystkich dokumentow `docs`

---

## 13. Zasady triage i priorytetyzacji bugow `[x]`
### 13.1 Priorytet P0 (naprawiac najpierw)
- bug moze popsuc bezpieczenstwo lotu / fokus gry / sterowanie,
- bug daje falszywa decyzje operacyjna (cash-in/route/survival),
- bug niszczy dane lokalne (`playerdb`, logbook cache, user entries),
- bug daje jawnie sprzeczne komunikaty runtime (UI vs TTS vs status).

### 13.2 Priorytet P1
- bug mocno pogarsza czytelnosc/ergonomie (np. tabela wyglada jak zepsuta),
- bug utrudnia diagnostyke i maintenance (mojibake, ciche tlumienie wyjatkow),
- bug znieksztalca komunikaty TTS/UI bez psucia logiki.

### 13.3 Priorytet P2 / debt
- komentarze/docstringi/kodowanie bez wplywu na runtime,
- porzadki docs snapshotow i sekcji historycznych,
- refaktory wspolnych helperow bez aktualnego symptomu gameplay.

### 13.4 Regula wdrazania
- najpierw naprawa minimalna (stabilnosc/spojnosc),
- potem test regresji/smoke,
- dopiero potem refaktor/porzadki.

---

## 14. Kontrakt ticketow wynikajacych z BUGS_FIX `[x]`
Kazdy ticket wyjety z tego dokumentu powinien zawierac:
- `Objaw` (co widzi gracz / co psuje runtime),
- `Przyczyna` (potwierdzona w kodzie albo hipoteza z poziomem pewnosci),
- `Zakres` (co ruszamy i czego nie ruszamy),
- `DoD`,
- `Testy` (minimum: regresja + smoke dla dotknietego obszaru),
- `Ref` do sekcji `BUGS_FIX.md`.

To zabezpiecza przed "naprawami wszystkiego naraz" i regresjami w innych modulach.

---

## 15. Kryteria domkniecia audytu (wersja robocza) `[~]`
Audit mozna uznac za "domkniety operacyjnie" (nie absolutnie), gdy:
- `[x]` istnieje jawny backlog bugow/ryzyk z priorytetami (`BUGS_FIX.md`),
- `[~]` wszystkie pozycje P0/P1 z gameplay impact maja ticket albo sa naprawione,
- `[x]` cleanup mojibake w kluczowych docs runtime (`actions/policies/LAST_TICKET`) jest zrobiony,
- `[~]` audit `except/pass` ma sklasyfikowane i utwardzone najwazniejsze hotspoty krytyczne; pozostaje cleanup szerokiej grupy helperow GUI,
- `[x]` najwazniejsze tabele Spansh (`Trade`, `Trade Compare`, `Neutron`) maja spojna responsywnosc,
- `[ ]` dokument ma zaktualizowany status coverage po kolejnych etapach.

Uwagi:
- "pelny audit wszystkiego" jest celem ruchomym; celem praktycznym jest domkniecie ryzyk P0/P1 oraz utrzymanie stalego procesu (ticket -> fix -> test -> wpis w BUGS_FIX).

---

## 16. Gameplay findings z testow w grze (2026-02-25) `[~]`
Cel:
- porownac bledy z gameplayu z istniejacym backlogiem `BUGS_FIX.md`,
- dopisac brakujace regresje / follow-upy,
- odroznic: `naprawione`, `wymaga weryfikacji`, `nowy ticket`.

### 16.1 Exobio po utracie zasilania / restarcie gry `[x]`
Objaw (user):
- po restarcie Renata pamieta czesc kontekstu probek, ale nie odtwarza poprawnie dystansu / stanu 1/3,
- kolejne probki sa komunikowane jako "kolejna probka pobrana",
- przy 3/3 brak domkniecia podsumowania probek.

Ocena vs istniejace poprawki:
- `F10` domknal bazowy persist exobio, ale ten case byl regresja / luka w odtwarzaniu klucza po restarcie.

Root cause (potwierdzony w kodzie):
- `_apply_exobio_state_payload` przywracalo `last_status_pos["ts"]` ze stanu persisted,
- po restarcie trwajacym >120 s stary ts powodowal, ze `_canonical_body_for_key` odrzucalo
  nazwe ciala jako fallback dla numerycznych BodyID (np. `Body: 5`),
- klucz po restarcie to `("sol", "5", "bacteria")` zamiast `("sol", "sol 3", "bacteria")`,
- licznik nigdy nie dosiegnal 3 -> brak callout "Mamy wszystko" przy 3/3.

Wdrozone poprawki (`logic/events/exploration_bio_events.py`):
1. `_snapshot_exobio_state_payload` i `_apply_exobio_state_payload`:
   - `ts` NIE jest zapisywany / przywracany w `last_status_pos` (ts to wartosc runtime),
   - `ts` domyslnie wynosi 0.0 po zaladowaniu ze stanu.
2. `_canonical_body_for_key`:
   - `ts == 0.0` traktowane jako sentinel "pozycja z persisted state, brak freshness constraint",
   - nazwe ciala mozna uzyc do budowania klucza bez ograniczenia czasowego,
   - `_arm_range_tracker` nadal wymaga `ts <= 30 s` dla distance tracking (osobny warunek).
3. Logi diagnostyczne w `load_exobio_state_from_contract` i `_persist_exobio_state`:
   - jednorazowy dump kluczowych pol przy load/save (bez spamowania).

Testy regresji:
- `tests/test_f16_1_exobio_restart_state_continuity.py` (4 testy, PASS):
  - (a) numeryczne BodyID -> restart -> klucz stabilny, count 1->2->3, completion fires,
  - (b) kilka gatunkow -> restart -> zadna pozycja nie ginie / nie duplikuje sie,
  - (c) pusty stan persisted -> brak crasha, poprawne defaulty.

### 16.2 FSS milestones / catch-up sequence / przedwczesny full-scan `[~]`
Objaw (user):
- przy systemach typu `4 gwiazdy + 2 planety` Renata czyta progi 25/50/75 "po kolei" po wlocie (catch-up flood),
- sporadycznie nadal pojawia sie przedwczesny "System w pelni przeskanowany" przy ~17/18 lub ~18/19.

Ocena vs istniejace poprawki:
- czesc problemu byla naprawiona (`F24/F28`: `FSSAllBodiesFound`, resety `FSSDiscoveryScan`, matrix bypass milestones),
- catch-up flood naprawiony: `_check_fss_thresholds(...)` emituje tylko najwyzszy nowo-przekroczony prog (25/50/75),
- dodano dedupe `Scan` po aliasach `BodyID` + `BodyName`, aby ograniczyc podwojne liczenie cial przy mieszanych payloadach FSS.

Status:
- `[x]` fix catch-up sequence (najwyzszy prog zamiast sekwencji 25->50->75),
- `[x]` fix dedupe `Scan` (`BodyID`/`BodyName`) pod katem przedwczesnego full-scan,
- `[x]` wzmocnione testy regresyjne edge-case (`17/18`, `18/19` z aliasowym duplikatem skanu),
- `[~]` re-test runtime w grze (case `4/6`, `17/18`, `18/19`) nadal wymagany.

### 16.3 UX wording: usunac slowo "cash-in" z komunikatow glosowych `[x]`
Objaw (user):
- user chce uproszczenia komunikatow glosowych (bez prefiksu "Cash-in" w mowie).

Uwagi:
- to jest zmiana UX/copy, nie bug logiki.
- zakres wdrozenia: tylko TTS (`raw_text` w `cash_in_assistant.py` / `startjump`), bez zmian UI/log/status.

Wdrozone:
- usuniecie prefiksu `Cash-in` z glosowych `raw_text` dla:
  - `trigger_cash_in_assistant(...)`
  - `trigger_startjump_cash_in_callout(...)`
- regresje F4/F11/F24/F28 PASS.

### 16.4 Summary -> cash-in voice (regresja) `[x]`
Objaw (user):
- po `Podsumowanie gotowe...` nadal pojawia sie glosowy komunikat cash-in (np. offline index),
- user oczekuje: przy auto summary ma byc tylko summary.

Root cause (potwierdzony):
- `F24-4` ustawial `suppress_tts=True` dla auto `summary -> cash-in`, ale
  cross-module voice priority mogl nadpisac blokade, bo:
  - `_evaluate_should_speak(...)` zwracal `(False, "notify_policy")`,
  - `"notify_policy"` bylo uzywane zarowno dla blokad miekkich (cooldown/debounce),
    jak i semantycznej blokady `suppress_tts=True`,
  - cross-module override traktowal `allow_reason == "notify_policy"` jako kandydat do `force=True`.

Wdrozone poprawki:
- `F24-4` wprowadzil `suppress_tts=True` dla auto `summary -> cash-in`,
- `logic/insight_dispatcher.py`:
  - jawny zwrot `(False, "suppress_tts_explicit")` przy `context.suppress_tts=True`,
  - powod ten nie przechodzi przez override `notify_policy` (cross-module / matrix),
  - dodany log diagnostyczny `voice blocked: suppress_tts_explicit`.
- `logic/events/exploration_summary.py`:
  - trace runtime wokol przejscia `summary -> cash-in`:
    - `summary->cash-in: entry`
    - `summary->cash-in: exit OK`

Status:
- poprawka wdrozona i potwierdzona w kodzie.
- do runtime check (gameplay): oczekiwane logi:
  - `[VOICE] summary->cash-in: entry ... suppress_tts=True`
  - `[VOICE] summary->cash-in: exit OK ... suppress_tts=True`
  - `[VOICE] voice blocked: suppress_tts_explicit ... voice_sequence_reason=after_exploration_summary`

Adnotacja (manual vs auto):
- Obecna poprawka dotyczy tylko `mode=auto`.
- Przy `mode=manual` (klikniecie podsumowania przez gracza) `summary -> cash-in` nadal moze byc czytane glosowo:
  - trace runtime pokazuje wtedy `suppress_tts=False`.
- To nie jest regresja F24-4, tylko obecna semantyka.
- Jesli UX ma byc "tylko summary" rowniez dla manual triggera, potrzebny jest osobny follow-up:
  - ustawic `suppress_tts=True` dla kazdego `summary -> cash-in` (auto + manual),
  - albo dodac osobny toggle/policy dla manual summary.

### 16.5 Summary trigger po jump tylko po aktywnosci FSS `[~]`
Objaw (user):
- przy szybkim lataniu system->system auto summary jest irytujace,
- oczekiwany gate: summary po skoku tylko wtedy, gdy od ostatniego summary wykryto aktywnosc FSS w systemie.

Uwagi:
- to jest zmiana semantyki triggera UX (cooldown/gate po aktywnosci), nie bug parsera.

Wdrozone (kod + testy):
- `logic/events/exploration_fss_events.py`
  - auto summary po domknieciu FSS jest teraz **uzbrajane** (`pending`) zamiast emitowane natychmiast,
  - uzbrojenie nastepuje tylko po realnej aktywnosci FSS (`FSSDiscoveryScan`),
  - dodany `flush_pending_exit_summary_on_jump(...)`.
- `logic/events/navigation_events.py`
  - przy `FSDJump/CarrierJump` (non-bootstrap), przed resetem FSS stanu:
    - wykonywany jest `flush_pending_exit_summary_on_jump(...)`,
    - summary poprzedniego systemu emituje sie dopiero na nastepnym skoku.
- test regresji:
  - `tests/test_f30_exploration_summary_after_jump_fss_gate.py` (arming + flush + brak arming bez `FSSDiscoveryScan`)
- regresje PASS:
  - `F24`, `F28` smoke.

Status:
- `[x]` deferred auto-summary na nastepny jump po FSS-full,
- `[x]` gate po aktywnosci FSS (`FSSDiscoveryScan`),
- `[~]` re-test w grze (czy UX odpowiada oczekiwaniu przy realnej sesji skokow).

### 16.6 Mapa: checkbox "Pokaz tylko dostepne na stacji" nie filtruje `[~]`
Objaw (user):
- w modalu `Wybierz towary...` po wlaczeniu checkboxa nadal widoczne wszystkie towary.

Ocena vs istniejace poprawki:
- `F22-3` deklaruje wdrozenie filtra po ostatnim snapshotcie `Market.json`,
- obserwacja z gry wskazuje regresje lub niespelniony warunek kontekstu (wybor stacji / snapshot / MarketID).

Status:
- `[x]` wzmocniono UX/robustness:
  - fallback do pierwszej widocznej stacji, gdy selection znika po zmianie fokusu,
  - jawny status/licznik filtra (`towary: X/Y`) w modalu,
  - test regresji/kontrakt rozszerzony o scenariusz utraty zaznaczenia stacji.
- `[~]` wymagany re-test w grze (czy problem byl realnym bugiem kontekstu, czy "no-op" filtrem przy jednej stacji pokrywajacej caly zbior znanych towarow).

### 16.7 Wartosciowanie danych / rozbieznosci cash-in i sesji `[~]`
Objaw (user):
- rozbieznosci miedzy wartoscia sesji raportowana przez Renate a realna roznica kredytow po sprzedazy,
- po sprzedazy i po restarcie sesyjna wartosc potrafi sie zmienic.

Ocena vs istniejace poprawki:
- `F25/F27/F28` poprawily DSS/cartography/recovery i `StarType`,
- nadal potrzebna twarda weryfikacja kontraktu "session/system value" vs account delta i warunkow sprzedazy blisko miejsca zbioru.

Status:
- `[x]` dodano instrumentacje runtime dla eventow sprzedazy:
  - `VALUE cashin_sell_snapshot` przy `SellExplorationData` / `SellOrganicData`,
  - loguje: `sale_earnings`, `balance`, `current_system`,
    `estimate_system`, `estimate_session_total`, `estimate_carto`, `estimate_exobio`, `estimate_bonus`.
- `[x]` dodano lokalne narzedzie analizy logow `tools/cashin_value_snapshot_analyzer.py` do porownan
  `sale_earnings` vs `Balance delta` vs `estimate_session_total` podczas reprodukcji gameplay.
- `[x]` wdrozono pakiet runtime hardening (2026-02-27):
  - `SystemValueEngine`: domenowe czyszczenie wartosci po sprzedazy (`cartography`/`exobiology`/`all`) z czyszczeniem dedupe kontenerow
    (`seen_bodies`, `seen_species`, `cartography_bodies`, `high_value_targets`) i licznikow discovery zaleznych od domeny,
  - `event_handler`: automatyczny reset domeny po `SellExplorationData` / `SellOrganicData` + log diagnostyczny
    `VALUE cashin_sell_reset` (before/after: `total/carto/exobio/bonus`),
  - `SystemValueEngine.analyze_scan_event`: hardening `WasMapped` dla cial `WasDiscovered=True`
    (Scan nie dolicza od razu DSS; upgrade dopiero na `SAAScanComplete`),
  - `exploration_value_recovery`: bootstrap respektuje eventy sprzedazy
    (`SellExplorationData`, `MultiSellExplorationData`, `SellOrganicData`) i resetuje domeny podczas odtwarzania.
  - commity: `c3a79df`, `0b1a0a0`, `a8f82ee`.
- `[x]` pokrycie regresyjne:
  - `tests/test_system_value_engine.py` (clear domen, recount po czyszczeniu, `WasMapped` hardening),
  - `tests/test_f54_event_handler_sell_value_domain_reset.py` (reset po sell event + diagnostyka),
  - `tests/test_bootstrap_system_value_recovery.py` (sell-aware recovery po restarcie).
- `[~]` nadal wymagana reprodukcja w grze i porownanie:
  - roznica konta (`Balance delta`) vs `sale_earnings`,
  - `sale_earnings` vs `estimate_session_total`,
  - zachowanie po restarcie (bootstrap recovery vs sesja runtime),
  - sanity-check manualnego triggera `Cash-In` po sprzedazy (czy panel nie trzyma stalego payloadu z poprzedniego summary).

Checklist retestu gameplay (16.7):
1. Wejdz do systemu testowego, zbierz dane FSS/DSS + exobio, zapisz stan `Balance` przed sprzedaza.
2. Sprzedaj tylko UC (`SellExplorationData`) i porownaj:
   - `Balance delta`,
   - `VALUE cashin_sell_snapshot.sale_earnings`,
   - `VALUE cashin_sell_reset.after_*` (carto powinno spasc do zera domenowo).
3. Sprzedaj tylko Vista (`SellOrganicData`) i porownaj analogicznie (`exobio` powinno spasc domenowo).
4. Zrestartuj Renate po sprzedazy i sprawdz, czy bootstrap recovery nie przywraca sprzedanych wartosci.
5. Uzyj manualnego przycisku `Asystent cash-in` i potwierdz, ze wartosci sesji/systemu sa zgodne z nowym stanem po sprzedazy.

### 16.8 Fokus/minimalizacja gry podczas FSS / sprzedazy danych `[~]`
Objaw (user):
- gra potrafi zostac zminimalizowana podczas FSS lub sprzedazy danych.

Ocena vs istniejace poprawki:
- `F23` wprowadzil focus-safe policy i trace (guard na `focus_force` dla `user_initiated=False`),
- ale dwa nieobjete patche nadal powoduja focus-steal.

Potwierdzone hotspoty (analiza kodu):

**Hotspot A — `logic/route_clipboard.py:184` (POTWIERDZONY, NAPRAWIONY)**
- Stary kod tworzyl wtorny `tk.Tk()` jako fallback clipboard gdy pyperclip zawiodl.
- `tk.Tk()` + `root.update()` + `root.destroy()` z watku tla (MainLoop) rejestruje nowe okno Windows
  i moze minimalizowac gre fullscreen.
- Trigger: pyperclip fail + auto-clipboard (np. pending station clipboard przy Docked/sprzedazy).
- Naprawa: zastapiono `tk.Tk()` fallback przez ctypes `win32clipboard` (brak tworzenia okna, focus-safe).
- Ref: `logic/route_clipboard.py` (metoda `try_copy_to_clipboard`).

**Hotspot B — `logic/utils/notify.py:_speak_pyttsx3` (PODEJRZANY, TRACE DODANY)**
- `pyttsx3.init()` wywolywane PER kazde TTS tworzy obiekt COM/SAPI5 na Windows.
- SAPI5 wewnetrznie tworzy ukryte okno, co moze steal focus od gry fullscreen.
- Trigger: kazde powiadomienie TTS podczas FSS (milestones 25/50/75/100%) gdy piper niedostepny.
- Naprawa: dodano `log_event("TTS", "pyttsx3_invoke", ...)` — trace pomaga potwierdzic czy
  pyttsx3 aktywuje sie podczas incydentow fokus.
- Jesli trace pojawia sie podczas FSS focus-steal: wymusic piper (skonfigurowac `tts.engine=piper`).
- Ref: `logic/utils/notify.py:_speak_pyttsx3`.

Status:
- `[x]` Hotspot A (clipboard tk.Tk()) naprawiony; Hotspot B (pyttsx3 COM) domkniety follow-upami.
- `[x]` Focus-safe hardening:
  - `tts.engine=auto`: fallback do `pyttsx3` domyslnie zablokowany (`tts.auto_allow_pyttsx3_fallback=false`),
  - `tts.engine=pyttsx3`: od teraz rowniez blokowany domyslnie; wymaga jawnego opt-in
    `tts.pyttsx3_allow_focus_risk=true`.
- `[x]` Dodane regresje pod oba przypadki (auto + explicit) i sciezke opt-in.

### 16.9 Mapa: zoom max `6.00 -> 100.00` `[x]`
Wdrozone:
- zwiekszono maksymalna skale mapy w `Dziennik -> Mapa` z `6.0` do `100.0`,
- regresje mapy pan/zoom smoke PASS (`F20/F21`).

### 16.10 TTS (Piper): fonetyka dlugich kwot i slowa "nic" `[x]`
Objaw (user):
- Renata w podsumowaniu eksploracji potrafi "lamac jezyk" na dlugich kwotach,
- przy poprawnym zdaniu typu `Tutaj nie ma nic wartosciowego` Piper potrafi wymawiac `nic` jak `nic/nić` (fonetycznie zle).

Diagnoza (potwierdzona):
- `prepare_tts(...)` i verbalizacja liczb dzialaja poprawnie:
  - `Cr` jest zamieniane na slowa (`... kredyty/kredytow`),
  - test reczny w `cmd` zwraca poprawny tekst wyjsciowy dla `MSG.EXPLORATION_SYSTEM_SUMMARY`.
- problem nie jest bugiem regexu/verbalizacji `Cr`, tylko jakoscia fonetyki modelu Piper dla:
  - dlugich ciagow liczebnikow,
  - wybranych slow (np. `nic`) w konkretnym glosie/modelu.

Wazne:
- user potwierdzil, ze to na 100% Piper (nie fallback `pyttsx3`),
- parametry Piper (`length_scale`, `sentence_silence`) sa juz recznie dopracowane i nie chcemy ich ruszac.

Przelom / rozwiazanie (potwierdzone w probe, 2026-02-25):
- test w `tools/tts_random_numbers_probe.py` potwierdzil, ze najlepszy efekt daje NIE fonetyczne psucie slow
  (np. `piec set`, `tszy`), tylko standardowa verbalizacja + mikro-pauzy resetujace prozodie przez `;`,
- wariant `semi` (`Dane warte ; <grupa> ; <grupa> ; <grupa> ; kredytow.`) eliminuje seplenienie/kaleczenie
  liczb w kolejnych probach odsluchowych (user potwierdzil "ani razu nie sepleni"),
- kluczowe: dziala na poprawnej polszczyznie (`tts_base`) z dodanymi `;`, bez wprowadzania sztucznej fonetyki.

Wniosek:
- problem jest glownie prozodyczny (oddech/reset modelu), nie leksykalny,
- `;` dziala jako skuteczny "break/reset" dla Pipera przy dlugich sekwencjach liczebnikow.

Wdrozenie (prod, TTS-only) `[x]`:
1. Dodano globalny helper prosodyczny dla liczb (np. `;` jako mikro-pauzy) po verbalizacji liczb w
   `logic/tts/text_preprocessor.py` (TTS output only, bez zmian UI/logow).
2. Zastosowano ten sam styl dla wszystkich typow liczb:
   - `Cr` / `%` / `LY`,
   - gole liczby w komunikatach runtime,
   - liczby w nazwach systemow / targetow (np. `LHS 20`, `COL 285 ...`), z zachowaniem czytelnej prozodii.
3. Zachowano standardowa pisownie slow (bez fonetycznych podmian typu `tszy`, `piec set`) jako domyslna polityke.
4. Dodano testy regresyjne TTS pod nowy helper (duze `Cr`, procent, `LY`, nazwa systemu z cyframi).

Uwaga implementacyjna:
- proby z fonetycznymi podmianami slow (np. `piec set`, `tszy`) poprawialy czasem artykulacje, ale psuly
  naturalnosc i byly slyszalne jako "spacje w srodku slowa" - ten kierunek zostal odrzucony.
- proby z kompaktowym zaokraglaniem (`prawie 5 milionow`) pomagaja, ale to workaround wordingowy; docelowe
  rozwiazanie to standardowe liczby + `;` jako mikro-pauzy.

Adnotacja wdrozeniowa:
- Zgoda usera zostala uzyskana po probe odsluchowej wariantu `semi` (standardowa polszczyzna + `;`).

### 16.11 Exobio: spam logow zapisu kontekstu probek `[x]`
Objaw (user):
- podczas eksploracji Renata "wali logami" przy aktywnym exobio,
- chodzi o logi diagnostyczne zwiazane z zapisem kontekstu probek (continuity po restarcie), nie o TTS.

Diagnoza (potwierdzona):
- logika zapamietywania kontekstu probek jest poprawna i ma zostac bez zmian (`_persist_exobio_state`, `load_exobio_state_from_contract`),
- spam powoduje sukcesowy log `EXOBIO save_state: persisted exobio state`, emitowany przy czestych zapisach stanu podczas pobierania probek,
- log ten trafia do glownego strumienia logow Renaty przez `log_event(...)`.

Wdrozone:
- `logic/events/exploration_bio_events.py:_persist_exobio_state`
  - zachowano sam zapis stanu (`config.update_anti_spam_state(...)`) bez zmian semantyki,
  - sukcesowy log `save_state: persisted exobio state` ukryto za `debug_logging=True`,
  - logi bledow/fallbackow pozostaja widoczne.

Skutek:
- mniej spamu w normalnym gameplayu eksploracji,
- diagnostyka persist/load exobio nadal dostepna w sesjach debug.

### 16.12 Event router: izolacja wyjatkow FSS/bio/DSS (anti-loss) `[x]`
Objaw / ryzyko:
- wyjatek w pojedynczym handlerze FSS/bio/DSS (np. `FSSDiscoveryScan`, `Scan`, `SAAScanComplete`, exobio progress)
  byl lapany dopiero przez ogolny catch w `MainLoop`, co dawalo tylko `[EventHandler error] ...` bez kontekstu,
- sam tail-loop journala zwykle przezyl, ale konkretny event mogl zostac utracony (np. brak calloutu / rozjazd FSS).

Diagnoza:
- czesc wywolan w `logic/event_handler.py` byla "gola" (bez lokalnego `try/except`),
- przez to awaria jednego handlera mogla blokowac dalsze handlery tego samego eventu (`Scan`: FSS -> DSS hint).

Wdrozone:
- dodano lokalne `try/except + _log_router_fallback(...)` dla hotspotow:
  - `FSDJump` autoschowek,
  - `FSSDiscoveryScan`,
  - `FSSAllBodiesFound`,
  - `Scan` (`handle_scan` FSS + `DSS target hint` osobno, z izolacja per handler),
  - `SAASignalsFound`,
  - `SAAScanComplete`,
  - `ScanOrganic` / `CodexEntry` (exobio progress).
- globalny catch w `MainLoop` pozostaje jako ostatni bezpiecznik, a nie glowna diagnostyka tych flow.

Test regresyjny:
- awaria `exploration_fss_events.handle_scan(...)` nie blokuje `exploration_dss_events.handle_dss_target_hint(...)`,
- awaria `FSSDiscoveryScan` handlera nie propaguje wyjatku poza `EventHandler.handle_event(...)`.

### 16.13 Watchery Status/Market/Cargo/NavRoute: `mtime` po udanym parsie JSON `[x]`
Objaw / ryzyko:
- przy transient `JSONDecodeError` (plik jest w trakcie zapisu przez gre) watcher mogl oznaczyc `mtime`
  jako "juz przetworzone" PRZED udanym `json.load(...)`,
- kolejny poll z tym samym `mtime` pomijal ponowna probe odczytu i tracil jedno odswiezenie.

Diagnoza:
- `BaseWatcher._load_json_safely()` ustawial `self._last_mtime = mtime` przed parsowaniem JSON.

Wdrozone:
- `self._last_mtime = mtime` przeniesiono za udany `json.load(...)` (po successful parse),
- transient parse error nie znaczy juz wersji pliku jako "przetworzonej".

Test regresyjny:
- `tests/test_f33_status_watcher_mtime_after_json_parse.py`
  - pierwszy odczyt: `JSONDecodeError`,
  - drugi odczyt przy tym samym `mtime`: watcher ponawia parse i zwraca dane.

### 16.14 Watchery: naprawa `_log_dispatch_soft_failure` (bledna sygnatura `log_event_throttled`) `[x]`
Objaw / ryzyko:
- gdy handler watchera (`on_status_update`, `on_market_update`, itp.) rzucal wyjatek, sciezka soft-failure
  sama mogla rzucic `TypeError` przez zla kolejnosc argumentow `log_event_throttled(...)`,
- w praktyce psulo to diagnostyke i moglo eskalowac blad poza watcher.

Diagnoza:
- `_log_dispatch_soft_failure(...)` przekazywal argumenty jak do innej sygnatury (`WARN`, key, msg, cooldown_sec=...),
- poprawna sygnatura to: `log_event_throttled(key, interval_ms, category, msg, **fields)`.

Wdrozone:
- poprawiono wywolanie na poprawna kolejnosc argumentow,
- zachowano ten sam kontekst logowania (`watcher.<label>.dispatch:<kind>`).

Test regresyjny:
- `tests/test_f34_status_watcher_dispatch_soft_failure_logging.py`
  - `StatusWatcher.poll()` z handlerem rzucajacym wyjatek:
    - nie propaguje `TypeError`,
    - loguje `log_event_throttled(...)` z poprawnymi argumentami.

### 16.15 MainLoop: naprawa soft-failure logowania (`log_event_throttled`) `[x]`
Objaw / ryzyko:
- dwa error-pathy w `MainLoop` (`handler.log_dir` setup oraz fallback dla `_emit_runtime_critical`) mialy
  bledna kolejnosc argumentow `log_event_throttled(...)`,
- w razie wyjatku sciezka "soft-failure" sama mogla rzucic `TypeError`.

Diagnoza:
- ten sam wzorzec co w watcherach: przekazywanie argumentow jak do innej sygnatury.

Wdrozone:
- poprawiono oba wywolania na sygnature:
  `log_event_throttled(key, interval_ms, category, msg, **fields)`.

Test regresyjny:
- `tests/test_f35_main_loop_soft_failure_throttled_logging.py`
  - blad przy `handler.log_dir` setup -> poprawny throttled log (bez `TypeError`),
  - blad `emit_insight(...)` w `_emit_runtime_critical` -> poprawny throttled log fallback.

### 16.16 Dispatcher: combat silence failsafe na bledzie snapshotu `[x]`
Objaw / ryzyko:
- gdy odczyt `app_state.get_mode_state_snapshot()` rzucal wyjatek, dispatcher logowal warning, ale
  wracal do `return False` (czyli combat silence NIEAKTYWNE),
- w rzadkim edge-case moglo to przepuscic TTS eksploracyjne podczas walki.

Wdrozone:
- `logic/insight_dispatcher.py:_is_combat_silence_active(...)`
  - po zlogowaniu bledu snapshotu zwraca teraz konserwatywnie `True` (milcz).

Test regresyjny:
- `tests/test_f36_combat_silence_failsafe_on_snapshot_error.py`
  - wyjatek `get_mode_state_snapshot()` -> helper zwraca `True`.

### 16.17 Dispatcher: reuse `evaluate_risk_trust_gate` bez podwojnej ewaluacji `[x]`
Objaw / ryzyko:
- `emit_insight(...)` liczyl `evaluate_risk_trust_gate(...)` dwa razy nawet wtedy, gdy priorytet
  NIE ulegl eskalacji (brak zmiany `effective_insight`),
- to nie psulo logiki, ale dodawalo zbedna prace i utrudnialo czytelna diagnostyke (duplikat tej samej ewaluacji).

Diagnoza:
- `initial_gate` bylo liczone na poczatku, ale pozniej kod i tak wykonywal ponownie
  `evaluate_risk_trust_gate(effective_insight)` niezaleznie od tego, czy `effective_insight is insight`.

Wdrozone:
- gdy priorytet nie zmienil sie (czyli `effective_insight is insight`), dispatcher reuzywa `initial_gate`,
- ponowna ewaluacja gate zostaje tylko wtedy, gdy faktycznie powstaje nowy `effective_insight`
  po eskalacji priorytetu.

Test regresyjny:
- `tests/test_f37_dispatcher_gate_evaluation_reuse.py`
  - brak eskalacji -> `evaluate_risk_trust_gate(...)` wywolane 1 raz,
  - eskalacja priorytetu -> `evaluate_risk_trust_gate(...)` wywolane 2 razy.

### 16.18 MainLoop bootstrap: bez `readlines()` calego journala do RAM `[x]`
Objaw / ryzyko:
- bootstrap journala w `MainLoop._bootstrap_state(...)` robil `f.readlines()[-max_lines:]`,
  co najpierw ladowalo CALY plik journala do pamieci,
- przy dlugich sesjach ED (duze `Journal.*.log`) powodowalo zbedny peak RAM przy starcie/restarcie Renaty.

Diagnoza:
- slicing `[-max_lines:]` ograniczal liczbe linii dopiero PO pelnym odczycie pliku.

Wdrozone:
- odczyt taila journala przez `deque(f, maxlen=max_lines)` (staly bufor),
- zachowana ta sama logika bootstrapu (exobio recovery / value recovery / replay taila).

Test regresyjny:
- `tests/test_f38_main_loop_bootstrap_tail_lines_memory_safe.py`
  - bootstrap nie uzywa `readlines()`,
  - do recovery przekazywane sa ostatnie `max_lines` linii.

### 16.19 TTS: generic fallback dla template-only `message_id` w `prepare_tts` `[x]`
Objaw / ryzyko:
- czesc komunikatow TTS miala template w `message_templates.py`, ale brak dedykowanej galezi
  w `prepare_tts(...)`,
- funkcja spadala do `return None`, co dawalo calkowity brak calloutu TTS mimo poprawnej definicji template.

Dotkniete (przyklad):
- `MSG.BIO_SIGNALS_HIGH`, `MSG.DSS_TARGET_HINT`, `MSG.DSS_COMPLETED`, `MSG.DSS_PROGRESS`,
- `MSG.EXOBIO_*` (czesc), `MSG.FIRST_MAPPED`, `MSG.SMUGGLER_ILLEGAL_CARGO`,
- `MSG.TERRAFORMABLE_DETECTED`, `MSG.TRADE_JACKPOT`, `MSG.WW_DETECTED`.

Wdrozone:
- na koncu `prepare_tts(...)` dodano generic fallback:
  - `fallback = _render_template(message_id)`
  - jesli template istnieje -> `_finalize_tts(fallback)`
- nie zmienia zachowania galezi z dedykowana logika (normalizacja systemu/stacji, specjalne komunikaty).

Test regresyjny:
- `tests/test_f39_tts_generic_template_fallback_for_unhandled_messages.py`
  - lista template-only `message_id` zwraca niepusty tekst TTS zamiast `None`.

### 16.20 TTS (pyttsx3 fallback): preferuj polski glos SAPI5 `[x]`
Objaw / ryzyko:
- fallback `pyttsx3` wybieral zawsze pierwszy glos z `eng.getProperty("voices")`,
- na Windows z wieloma glosami (EN/DE/PL) moglo to skutkowac czytaniem polskiego tekstu glosami
  niepolskimi (niska zrozumialosc calloutow).

Wdrozone:
- dodano helper wyboru glosu `pyttsx3`, ktory preferuje wpisy pasujace po:
  - `voice.name` (`polish`, `polski`)
  - `voice.languages` (`pl-PL`, `pl_PL`, `pl`)
- gdy brak dopasowania: fallback do pierwszego glosu (zachowanie bezpieczne wstecznie).

Test regresyjny:
- `tests/test_f40_pyttsx3_polish_voice_selection.py`
  - wybor po nazwie (`Polish`)
  - wybor po `voice.languages` (`pl-PL`)
  - fallback do pierwszego glosu
  - obsluga pustej listy glosow

### 16.21 TTS: auto fallback blokowany (focus-safe) daje user-facing diagnostyke `[x]`
Objaw / ryzyko:
- gdy `tts.engine=auto`, Piper byl niedostepny/zepsuty, a `tts.auto_allow_pyttsx3_fallback=false`,
  Renata mogla po prostu zamilknac (blokada fallbacku byla logowana technicznie, ale bez czytelnej informacji
  dla uzytkownika w standardowym strumieniu soft-failure).

Wdrozone:
- w sciezce `auto` + fallback pyttsx3 zablokowany dodano `_log_notify_soft_failure(...)`
  z czytelnym komunikatem:
  - Piper niedostepny lub blad
  - pyttsx3 fallback zablokowany (focus-safe)

Efekt:
- brak "cichego" braku TTS w tej sciezce; uzytkownik dostaje jasna diagnoze w logu Renaty.

Test regresyjny:
- `tests/test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard.py`
  - przy `auto` + brak Pipera + fallback blocked:
    - `pyttsx3` nie jest wywolywany,
    - pojawia sie user-facing soft-failure diagnostic.

### 16.22 PlayerDB ingest: odrzucenie `Docked/Location(docked)` bez `system_name` (bez `UNKNOWN_SYSTEM`) `[x]`
Objaw / ryzyko:
- `ingest_journal_event(...)` mogl zapisac stacje pod sztucznym `system_name="UNKNOWN_SYSTEM"`,
  gdy event `Docked` (lub `Location` z `Docked=True`) mial `StationName`, ale brakowalo `StarSystem`
  i nie bylo `fallback_system_name`,
- tworzylo to "ghost" stacje zanieczyszczajace `stations` i wyniki routingu/candidate query.

Wdrozone:
- dodano wczesny guard przed otwarciem DB:
  - `Docked/Location(docked)` + `StationName` + brak `system_name` -> zwrot
    `{"ok": False, "reason": "missing_system_name", ...}`
- brak insertu do `stations` i brak fallbacku na `"UNKNOWN_SYSTEM"`.

Test regresyjny:
- `tests/test_f16_playerdb_ingest_market_docked_jumps.py`
  - `Docked` bez `StarSystem` i bez fallbacku -> `ok=False`, `reason=missing_system_name`
  - brak rekordu stacji / brak `UNKNOWN_SYSTEM` w DB (lub DB nie powstaje wcale, co tez jest OK)

### 16.23 PlayerDB cash-in ingest: brak `TotalEarnings` nie zapisuje fałszywego `0` `[x]`
Objaw / ryzyko:
- `SellExplorationData` / `SellOrganicData` bez pola zarobku (`TotalEarnings`/`Earnings`/`Value`/`Total`)
  byly zapisywane do `cashin_history` z `total_earnings=0`,
- to zanieczyszczalo analityke cash-in i moglo znieksztalcac sumy/raporty sesji.

Wdrozone:
- `ingest_journal_event(...)` dla eventow cash-in:
  - gdy brak wartosci zarobku -> zwrot
    `{"ok": False, "reason": "missing_earnings_value", ...}`
  - brak insertu do `cashin_history` (zamiast wpisu `0`)

Test regresyjny:
- `tests/test_f16_playerdb_cashin_history_and_query.py`
  - `SellExplorationData` bez `TotalEarnings` -> `ok=False`, `reason=missing_earnings_value`
  - brak wpisu w `cashin_history` (nie powstaje fałszywe `0`)

### 16.24 Exobio state crash-recovery: tuple-klucze sa JSON-safe (potwierdzenie + regression test) `[x]`
Objaw / ryzyko (z audytu Claude):
- podejrzenie crasha `_persist_exobio_state()` przy `json.dumps(...)`, bo exobio trzyma runtime dicty z kluczami-tuple
  (`(system, body, species)`), a JSON nie obsluguje tuple-kluczy.

Weryfikacja:
- aktualny kod juz serializuje klucze przez `_encode_exobio_key(...)` i helpery:
  - `_serialize_exobio_sample_count()`
  - `_serialize_exobio_trackers()`
  - `_serialize_exobio_key_set(...)`
- payload ze `_snapshot_exobio_state_payload()` jest JSON-serializable i poprawnie wraca przez
  `_apply_exobio_state_payload(...)` do kluczy tuple.

Wdrozone:
- brak zmian runtime (zachowanie bylo juz poprawne),
- dodano dedykowany test regresyjny JSON round-trip, zeby nie cofnac tego przy przyszlych zmianach.

Test regresyjny:
- `tests/test_f41_exobio_state_tuple_key_json_roundtrip.py`
  - payload snapshotu jest `json.dumps(...)`-safe,
  - tuple-klucze wracaja po `_apply_exobio_state_payload(...)`,
  - `ts` nie jest persistowane w `last_status_pos`,
  - trackery dla complete key sa czyszczone przy restore (zgodnie z logika).

### 16.25 PlayerDB market snapshots: dedupe race hardening (`UNIQUE` + `INSERT OR IGNORE`) `[x]`
Objaw / ryzyko:
- `ingest_market_json()` robil dedupe przez `SELECT ... WHERE hash_sig` przed insertem, ale bez `UNIQUE`
  constraint na `market_snapshots`,
- przy concurrent poll (dwa identyczne Market.json blisko siebie) oba inserty mogly przejsc i zapisac duplikaty.

Wdrozone:
- schema/migracje:
  - podniesiono PlayerDB schema do `v2`
  - dodano migracje deduplikujaca istniejace `market_snapshots` (zachowuje najnowszy wpis per klucz)
  - dodano partial `UNIQUE` indexes:
    - `(station_market_id, hash_sig)` dla wpisow z `market_id`
    - `(system_name, station_name, hash_sig)` gdy `market_id` brak
- ingest:
  - `INSERT OR IGNORE` do `market_snapshots`
  - przy ignore (race) -> re-select istniejacego snapshotu + `freshness_ts` update + `deduped=True`

Efekt:
- race na dedupe nie tworzy juz duplikatow snapshotow dla tego samego `hash_sig`.

Testy:
- `tests/test_f16_playerdb_schema_and_migrations.py`
  - schema `v2`, 2 migracje, obecne nowe `UNIQUE` indeksy dla `market_snapshots`
- `tests/test_f16_playerdb_ingest_market_docked_jumps.py`
  - istniejący test dedupe by `marketid+hash` nadal przechodzi (kontrakt zachowany)

### 16.26 Exobio range tracker: cleanup uszkodzonego baseline GPS zamiast cichego `continue` `[x]`
Objaw / ryzyko:
- uszkodzony tracker dystansu exobio (brak `lat`/`lon`/`radius_m`/`threshold_m` w trackerze) byl cicho pomijany
  w `handle_exobio_status_position(...)`,
- taki tracker zostawal w `EXOBIO_RANGE_TRACKERS` i juz nigdy nie mogl dojsc do calloutu "range ready".

Wdrozone:
- dla nie-`pending` trackerow z brakujacym baseline/threshold:
  - usuniecie z `EXOBIO_RANGE_TRACKERS`
  - cleanup z `EXOBIO_RANGE_READY_WARNED`
  - throttled log diagnostyczny (`RANGE_TRACKER_INVALID`)
- stan jest persistowany normalnym flow (`state_changed=True`)

Efekt:
- broken tracker nie "wisi" bez konca; runtime samooczyszcza stan i zostawia czytelny slad w logach.

Test regresyjny:
- `tests/test_f42_exobio_invalid_range_tracker_cleanup.py`
  - invalid non-pending tracker (`lat=None`) jest usuwany
  - nie emituje `MSG.EXOBIO_RANGE_READY`
  - loguje `RANGE_TRACKER_INVALID`

### 16.27 FSS: odrzucenie niespójnego `FSSDiscoveryScan` (`BodyCount < FSS_DISCOVERED`) `[x]`
Objaw / ryzyko:
- gdy `FSSDiscoveryScan` przychodzil z `BodyCount` mniejszym niz juz zebrany progres (`FSS_DISCOVERED`),
  kod podnosil `FSS_TOTAL_BODIES = max(BodyCount, FSS_DISCOVERED)`,
- to moglo sztucznie wytworzyc `N/N` i wywolac falszywe milestone/full-scan (np. 3/3 po `BodyCount=2`).

Wdrozone:
- w `handle_fss_discovery_scan(...)` dodano walidacje:
  - jesli jest progres i `BodyCount < FSS_DISCOVERED` -> throttled log + `return` (ignoruj event)
- brak zmiany `FSS_TOTAL_BODIES`, brak zmiany flag milestone przy niespójnym evencie.

Efekt:
- uszkodzony/spozniony `FSSDiscoveryScan` nie psuje stanu procentow FSS i nie produkuje falszywych calloutow.

Test regresyjny:
- `tests/test_f28_fss_discovery_scan_does_not_reset_progress.py`
  - `FSS_DISCOVERED=5`, `BodyCount=2` -> event odrzucony
  - `FSS_TOTAL_BODIES` pozostaje bez zmian
  - logowany jest `body_count_inconsistent`

### 16.28 PlayerDB market ingest: walidacja zakresu cen (`BuyPrice`/`SellPrice`/`MeanPrice`) `[x]`
Objaw / ryzyko:
- `ingest_market_json()` zapisywal ceny bez walidacji zakresu,
- wartosci ujemne / zerowe / absurdalnie duze mogly trafic do `market_snapshot_items` i psuc downstream
  (sortowanie profitu, rankingi ofert, diagnostyka).

Wdrozone:
- dodano sanitizacje cen rynkowych (`_sanitize_market_price(...)`) dla:
  - `BuyPrice`
  - `SellPrice`
  - `MeanPrice`
- wartosci poza zakresem ( `< 1` lub `> 9_999_999` ) zapisywane jako `NULL`
- sanitizacja stosowana:
  - przy budowie hash dedupe (`_normalized_market_items_hash`)
  - przy insercie do `market_snapshot_items`

Efekt:
- garbage price values nie zatruwaja DB i nie wpływaja na downstream query/ranking.

Test regresyjny:
- `tests/test_f16_playerdb_ingest_market_docked_jumps.py`
  - `BuyPrice=-5000`, `SellPrice=99_999_999`, `MeanPrice=0` -> zapisane jako `NULL`

### 16.29 TTS `raw_text_first` bez `raw_text`: fallback do template (regression coverage) `[x]`
Kontekst:
- problem byl zidentyfikowany w `BUGS_FINDE` jako ryzyko "milczenia", gdy `raw_text_first=True`, ale emitter nie poda `raw_text`,
- fix logiczny jest juz wdrozony generic fallbackiem `prepare_tts()` (`BUGS_FIX 16.19`, commit `4429aa0`),
- brakowalo dedykowanego testu regresyjnego dla tego konkretnego scenariusza.

Wdrozone:
- dodano dedykowany test regresyjny dla `MSG.ELW_DETECTED` (message z `raw_text_first=True`) wywolanego bez `raw_text`,
- test potwierdza fallback do template (`prepare_tts(...)` zwraca tekst zamiast `None`).

Efekt:
- scenariusz `raw_text_first` bez `raw_text` jest jawnie zabezpieczony testem i nie powinien wrócic jako cicha regresja.

Test regresyjny:
- `tests/test_f39_tts_generic_template_fallback_for_unhandled_messages.py`
  - `prepare_tts("MSG.ELW_DETECTED", {})` -> zwraca niepusty tekst zakonczony kropka

### 16.30 TTS nazwy systemow z cyframi (`LHS 20`, `HIP 63523`): werbalizacja jest celowa (regression coverage) `[x]`
Kontekst:
- finding z `BUGS_FINDE` zakladal, ze `_STANDALONE_NUMBER_RE` "psuje" nazwy systemow, bo werbalizuje cyfry,
- po wdrozeniu prozodii `;` dla liczb (TTS/Piper) decyzja produktowa jest odwrotna:
  - liczby maja byc czytane wszedzie, takze w nazwach systemow, z mikro-pauzami `;`.

Decyzja / status:
- oznaczone jako `false positive` wzgledem obecnego zachowania (to jest intencjonalny efekt, nie regresja),
- domkniete dodatkowym testem regresyjnym dla duzej liczby w nazwie systemu.

Wdrozone:
- dodano test `prepare_tts("MSG.JUMPED_SYSTEM", {"system": "HIP 63523"})`
  - oczekuje werbalizacji liczby (brak surowego `63523`)
  - oczekuje prosody breaks `;`

Efekt:
- zachowanie "cyfry w nazwach systemow sa werbalizowane" jest jawnie potwierdzone testami i nie bedzie wracalo jako przypadkowy rollback.

Test regresyjny:
- `tests/test_f28_tts_number_verbalization_and_raw_text_first.py`
  - `LHS 20` + `HIP 63523` -> werbalizacja liczb + `;`

### 16.31 TTS `_percent_sub`: usuniecie martwego warunku (`procent` / `procent`) `[x]`
Objaw / ryzyko:
- w `_percent_sub` byl martwy warunek:
  - `unit = "procent" if ... else "procent"`
- obie galezie zwracaly to samo, co utrudnialo czytanie kodu i moglo mylnie sugerowac dzialajaca logike odmiany.

Wdrozone:
- uproszczono `_percent_sub` do jednej stalej galezi:
  - `unit="procent"`
- brak zmiany semantyki runtime (cleanup kodu / utrzymanie).

Efekt:
- czytelniejsza implementacja i brak martwego warunku w hotspotcie TTS.

Weryfikacja:
- istniejące testy TTS (w tym `%` i `LY`) przechodza bez zmian.

### 16.32 TTS mojibake repair: idempotencja `_repair_polish_text` (regression coverage) `[x]`
Kontekst:
- w `BUGS_FINDE` bylo podejrzenie, ze `_repair_polish_text(...)` moze nadpisac poprawne polskie znaki przy ponownym przejsciu przez preprocessor,
- szczegolnie istotne przy wielokrotnym przechodzeniu tekstu przez pipeline TTS.

Wdrozone:
- dodano dedykowany regression test idempotencji `_repair_polish_text(...)` dla juz poprawnych tekstow:
  - pojedynczy znak `ł`
  - zdanie z polskimi znakami
  - krotki komunikat runtime
- test sprawdza:
  - 1x repair == oryginal
  - 2x repair == oryginal

Efekt:
- potwierdzone, ze naprawa mojibake jest idempotentna dla poprawnych polskich znakow (brak regresji przy ponownym przetworzeniu).

Test regresyjny:
- `tests/test_f18_tts_polish_templates_and_diacritics.py`
  - `test_repair_polish_text_is_idempotent_for_already_correct_diacritics`

### 16.33 TTS decimal dot (`100.5`) rozcinany przez normalizacje kropki `[x]`
Objaw / ryzyko:
- teksty z liczba dziesietna zapisana kropka (np. `100.5,`) byly rozcinane w `_finalize_tts()` do postaci `100. 5,`,
- powodowalo to znieksztalcony tekst TTS i potencjalnie nienaturalne czytanie.

Diagnoza:
- podejrzenie w `BUGS_FINDE` wskazywalo regex `_STANDALONE_NUMBER_RE`,
- faktyczny root cause byl w `_finalize_tts()`:
  - globalna normalizacja kropek (`re.sub(r"\\s*\\.\\s*", ". ", ...)`) traktowala kropke dziesietna jak separator zdan.

Wdrozone:
- dodano ochrone kropek dziesietnych (`(?<=\\d)\\.(?=\\d)`) przed normalizacja kropki,
- po normalizacji zdaniowej kropki dziesietne sa przywracane.

Efekt:
- `100.5` nie jest juz rozcinane na `100. 5`,
- zachowana normalizacja kropek konczacych zdania.

Test regresyjny:
- `tests/test_f28_tts_number_verbalization_and_raw_text_first.py`
  - `Cena 100.5, test` -> brak `100. 5`
  - `Cena 100,5. test` -> forma z przecinkiem nadal poprawna

### 16.34 TTS: `semicolon + standalone` interaction (regression coverage) `[x]`
Kontekst:
- w `BUGS_FINDE` bylo podejrzenie, ze sekwencja regexow w `_verbalize_tts_numbers()` moze robic double-processing,
- szczegolnie po wdrozeniu prozodii `;` dla liczb (`_credits_sub`) i pozniejszym `standalone` regexie.

Wynik weryfikacji:
- nie potwierdzono bledu runtime,
- mieszany tekst `Cr + ; + standalone` jest przetwarzany poprawnie (kazda liczba raz).

Wdrozone:
- dodano regression test dla scenariusza:
  - `Dane warte 100,000 Cr ; 200.`
- test sprawdza:
  - verbalizacje kwoty i standalone `200`
  - brak surowych cyfr w wyniku
  - brak duplikacji fraz (`sto tysiecy`, `dwiescie` liczone po 1x)

Efekt:
- podejrzenie double-processing zostalo domkniete testem i nie powinno wracac jako niepewny hotspot.

Test regresyjny:
- `tests/test_f28_tts_number_verbalization_and_raw_text_first.py`
  - `test_semicolon_and_standalone_number_interaction_does_not_double_process`

### 16.35 TTS `MSG.MILESTONE_PROGRESS`: brak podwojnego "procent" (regression coverage / false positive) `[x]`
Kontekst:
- w `BUGS_FINDE` byl finding (oznaczony finalnie jako `[fp]`) o rzekomym podwojnym "procent" w `MSG.MILESTONE_PROGRESS`,
- runtime weryfikacja pokazala poprawny output, ale brakowalo testu, ktory by to stabilizowal.

Wdrozone:
- dodano dedykowany regression test dla:
  - `prepare_tts("MSG.MILESTONE_PROGRESS", {"percent": 25})`
- test sprawdza:
  - obecność `dwadzieścia pięć`
  - `procent drogi`
  - dokładnie jedno wystąpienie słowa `procent`
  - obecność prozodii `;`

Efekt:
- false positive jest teraz domkniete nie tylko ręczną weryfikacją, ale też testem automatycznym.

Test regresyjny:
- `tests/test_f28_tts_number_verbalization_and_raw_text_first.py`
  - `test_milestone_progress_percent_is_not_double_processed`

### 16.36 TTS pyttsx3 fallback: integracyjny test wyboru polskiego glosu `[x]`
Kontekst:
- `BUGS_FINDE` mial brak testu dla rzeczywistej sciezki fallbacku pyttsx3 (`_speak_pyttsx3`),
- helper `_select_pyttsx3_voice_id(...)` byl juz testowany, ale brakowalo potwierdzenia w integracji z obiektem engine.

Wdrozone:
- dodano test integracyjny `_speak_pyttsx3(...)` z fake engine (multi-language voice list),
- test potwierdza, ze sciezka runtime:
  - wybiera glos `pl_voice`,
  - ustawia `rate` i `volume`,
  - przekazuje tekst do `say(...)`.

Efekt:
- potwierdzone, ze preferencja polskiego glosu dziala nie tylko w helperze, ale tez w faktycznym fallback path pyttsx3.

Test regresyjny:
- `tests/test_f40_pyttsx3_polish_voice_selection.py`
  - `test_speak_pyttsx3_applies_polish_voice_in_engine_path`

### 16.37 TTS `piper fail + fallback blocked`: regression test diagnostycznego logu `[x]`
Kontekst:
- fix funkcjonalny (`BUGS_FIX 16.21`) dodal user-facing diagnostyke przy `engine=auto`, gdy Piper jest niedostepny, a fallback pyttsx3 jest zablokowany,
- w `BUGS_FINDE` zostal brak testu dla tej sciezki (z naciskiem na czytelny log).

Wdrozone:
- rozszerzono test `F31` o asercje dla tej sciezki:
  - user-facing `_log_notify_soft_failure` zawiera czytelny komunikat o zablokowanym fallbacku,
  - `log_event_throttled(...)` dostaje wpis `TTS` z kluczem `tts:auto_pyttsx3_fallback_blocked`,
  - przekazywany jest jawny `reason=tts.auto_allow_pyttsx3_fallback=false`.

Uwaga:
- aktualna sciezka `_queue_log_line` nie modeluje formalnych poziomow `ERROR/WARN`,
- dlatego test domyka "czytelnosc + diagnostyke" zamiast literalnie sprawdzac severity level.

Efekt:
- fallback-blocked path jest jawnie zabezpieczony testem regresyjnym (user-facing + log diagnostyczny).

Test regresyjny:
- `tests/test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard.py`
  - `test_auto_mode_blocked_fallback_logs_user_facing_diagnostic`

### 16.38 TTS system names (`RS-T d3-94`, `b5`, `d0`): alfanumeryczne suffixy (regression coverage) `[x]`
Kontekst:
- w `BUGS_FINDE` zostal brak testu dla `_standalone_sub` na nazwach systemow z alfanumerycznymi suffixami,
- po decyzji produktowej z `16.30` (werbalizacja cyfr w nazwach systemow jest celowa) brakowalo testu dla trudniejszych wzorcow katalogowych (`d3-94`, `b5-2`, `d0`).

Wdrozone:
- dodano regression test dla reprezentatywnego przypadku:
  - `MSG.JUMPED_SYSTEM` z systemem `Eol Prou RS-T d3-94`
- test potwierdza biezace zachowanie:
  - cyfry sa werbalizowane (`trzy`, `dziewiecdziesiat cztery`)
  - zachowane sa prosody breaks `;`
  - surowe fragmenty `d3` / `94` nie zostaja w wyjsciu TTS

Efekt:
- zachowanie dla alfanumerycznych suffixow systemow jest teraz jawnie pokryte testem i nie wróci jako przypadkowa zmiana regex/TTS.

Test regresyjny:
- `tests/test_f28_tts_number_verbalization_and_raw_text_first.py`
  - `test_alphanumeric_system_suffix_digits_are_verbalized_consistently`

### 16.39 Watchers `_log_dispatch_soft_failure`: direct helper regression test `[x]`
Kontekst:
- fix `log_event_throttled(...)` sygnatury w watcherach byl juz wdrozony (`BUGS_FIX 16.14`),
- mielismy test poll-level (`StatusWatcher.poll()`), ale w `BUGS_FINDE` zostal jeszcze brak bezposredniego testu helpera `_log_dispatch_soft_failure(...)`
  pod katem dawnego TypeError (brak `msg` argumentu).

Wdrozone:
- dodano direct regression test helpera `_log_dispatch_soft_failure("status_update")`,
- test sprawdza poprawna sygnature wywolania `log_event_throttled(...)`:
  - key
  - interval
  - severity (`WARN`)
  - `msg` (czyli brak dawnego TypeError)
  - `context`

Efekt:
- helper error-path jest jawnie pokryty testem i nie polegamy tylko na posrednim scenariuszu `poll()`.

Test regresyjny:
- `tests/test_f34_status_watcher_dispatch_soft_failure_logging.py`
  - `test_dispatch_soft_failure_helper_logs_with_valid_signature`

### 16.40 TTS spawning: hard cap `1` aktywny watek (mitigacja overlap/spawn storm) `[~]`
Objaw / ryzyko:
- kazde `powiedz()` z TTS uruchamialo nowy `threading.Thread(_watek_mowy)`,
- przy burstach (FSS / kaskady insightow) prowadziło to do wielu równoległych wątków TTS, overlapu audio i spiętrzenia opóźnień.

Wdrozone (mitigacja):
- dodano hard cap `1` aktywny watek TTS w `logic/utils/notify.py`:
  - nowy start TTS jest blokowany, gdy poprzedni watek nadal mówi,
  - logowany jest throttled wpis diagnostyczny `tts:thread_busy_drop`,
  - slot TTS jest zwalniany w `finally` w `_watek_mowy(...)` (także po wyjątku),
  - start wątku TTS ustawiony jako `daemon=True`.

Efekt:
- brak lawinowego spawnienia watkow TTS i brak overlapu wynikajacego z równoległych startów,
- koszt uboczny (na razie): nowe komunikaty w czasie aktywnej syntezy sa pomijane (brak kolejki FIFO).

Status:
- mitigacja wdrozona i przetestowana,
- follow-up FIFO worker zostal domkniety w `16.54` (status punktu problemowego: `[x]`).

Testy regresyjne:
- `tests/test_f43_tts_thread_spawning_limit.py`
  - `test_powiedz_limits_tts_to_single_active_thread_and_drops_overlap`
  - `test_watek_mowy_releases_active_slot_even_when_speak_raises`
### 16.41 Bootstrap replay: reset flagi po wyjatku handlera (regression coverage) `[x]`
Kontekst:
- w `BUGS_FINDE` byl false positive, ze `app_state.bootstrap_replay` moze zostac `True`,
- brakowalo jednak dedykowanego testu regresyjnego na edge-case: wyjatek w `handler.handle_event(...)` podczas bootstrap replay (`Location` / `FSDJump`).

Wdrozone:
- dodano regression test do `F38`, ktory wymusza wyjatek w `handler.handle_event(...)` podczas bootstrap,
- test potwierdza, ze `MainLoop._bootstrap_state(...)` resetuje `app_state.bootstrap_replay` do `False` mimo wyjatku.

Efekt:
- false positive z `BUGS_FINDE` jest domkniety nie tylko analiza kodu, ale tez testem regresyjnym,
- future refactor bootstrapu nie cofnie gwarancji resetu flagi po bledzie handlera.

Test regresyjny:
- `tests/test_f38_main_loop_bootstrap_tail_lines_memory_safe.py`
  - `test_bootstrap_resets_bootstrap_replay_even_when_handler_raises_on_location`

### 16.42 Piper TTS: timeout procesu syntezy (`subprocess.run`) + regression test `[x]`
Kontekst:
- w `BUGS_FINDE` byl potwierdzony SEV-1: `logic/tts/piper_tts.py` uruchamial `subprocess.run(piper.exe, ...)` bez `timeout`,
- zawieszony/crashujacy `piper.exe` mogl blokowac watek TTS na nieokreslony czas (a potem jeszcze synchroniczne odtworzenie WAV).

Wdrozone:
- dodano hard timeout `15.0s` do `subprocess.run(...)` w `logic/tts/piper_tts.py`,
- istniejacy error-path (`except Exception`) nadal loguje blad i zwraca `False`,
- dodano regression test symulujacy zawieszony/ubity Piper przez `subprocess.TimeoutExpired`.

Efekt:
- pipeline Pipera nie moze juz wisiec bez limitu czasu na etapie syntezy subprocessu,
- timeout-path jest jawnie pokryty testem (cleanup tymczasowego WAV + log + `False`).

Test regresyjny:
- `tests/test_f44_piper_tts_timeout_and_cleanup.py`
  - `test_speak_applies_timeout_and_cleans_up_when_piper_hangs`

### 16.43 Exobio restart: `EXOBIO_RECOVERY_UNCERTAIN_KEYS` nie blokuje calloutow (false positive + regression coverage) `[x]`
Kontekst:
- w `BUGS_FINDE` bylo podejrzenie, ze po restarcie przywrocone `EXOBIO_RECOVERY_UNCERTAIN_KEYS` moga blokowac callouty egzobiologii (`2/3`, `3/3`),
- analiza kodu sugerowala, ze `uncertain` steruje tylko wordingiem ("Kolejna probka"), ale brakowalo dedykowanego testu bootstrapu z persisted state (`source=state`).

Wdrozone:
- dodano regression test w `F16.1`:
  - buduje stan z `event_uncertain=True` (numeric `BodyID`, brak `StarSystem`),
  - persistuje stan do kontraktu,
  - symuluje restart + `bootstrap_exobio_state_from_journal_lines([], ...)` (`source=state`),
  - sprawdza przywrocenie `EXOBIO_RECOVERY_UNCERTAIN_KEYS`,
  - potwierdza, ze po restarcie nadal leci callout `2/3` ("Kolejna probka") i `3/3` completion ("Mamy wszystko").

Efekt:
- podejrzenie z `BUGS_FINDE` domkniete jako false positive,
- mamy twarde regression coverage dla scenariusza restart + persisted uncertain sequence.

Test regresyjny:
- `tests/test_f16_1_exobio_restart_state_continuity.py`
  - `test_e_uncertain_sequence_key_survives_bootstrap_and_does_not_block_callouts`

### 16.44 GUI `check_queue()`: limit wiadomosci na tick + backlog reschedule `[x]`
Kontekst:
- w `BUGS_FINDE` byl potwierdzony SEV-2: `gui/app.py::check_queue()` przetwarzal `MSG_QUEUE` w petli `while True` bez limitu (`get_nowait()`),
- przy burstach (np. FSS/event storm) jeden tick Tkinter mogl spędzać zbyt dużo czasu na drenowaniu kolejki, co powodowalo lag UI.

Wdrozone:
- dodano limit przetwarzania kolejki GUI na tick: `20` wiadomosci,
- gdy tick dochodzi do limitu i kolejka nadal ma backlog, kolejny tick planowany jest przez `after(0)` (natychmiast),
- gdy kolejka zostanie opróżniona w limicie, zostaje standardowy interwał `after(100)`.

Efekt:
- pojedynczy tick GUI nie monopolizuje pętli Tkinter podczas event storm,
- backlog nadal jest szybko drenowany (agresywny re-schedule `after(0)`), ale z zachowaniem punktów oddechu między tickami.

Test regresyjny:
- `tests/test_f45_gui_check_queue_tick_limit.py`
  - `test_check_queue_limits_items_per_tick_and_reschedules_immediately_when_backlog_exists`
  - `test_check_queue_uses_idle_delay_when_queue_fully_drained_within_tick`

### 16.45 MainLoop `run()`: global exception guard + restart petli journala `[x]`
Kontekst:
- w `BUGS_FINDE` byl potwierdzony SEV-2: `MainLoop.run()` nie mial outer `try/except`,
- nieobsluzony wyjatek z `_find_latest_file()`, `_bootstrap_state()` albo `_tail_file()` mogl zakonczyc daemon thread bez czytelnego sygnalu dla uzytkownika (silent crash czytnika journala).

Wdrozone:
- dodano outer `try/except` wokol pojedynczej iteracji `while True` w `MainLoop.run()`,
- na nieobsluzonym wyjatku:
  - log przez `_log_error(...)` (`[BŁĄD MainLoop/run] ...`),
  - callout diagnostyczny przez `_emit_runtime_critical(...)`,
  - krotki backoff (`sleep(1)`) i retry petli.

Efekt:
- daemon thread czytnika journala nie umiera po pojedynczym nieobsluzonym wyjatku,
- runtime ma czytelny sygnal diagnostyczny i automatycznie probuje wznowic prace.

Test regresyjny:
- `tests/test_f46_main_loop_run_restart_on_unhandled_exception.py`
  - `test_run_restarts_loop_after_unhandled_tail_exception`

### 16.46 TTS/Winsound: "GUI freeze" jako false positive (worker-thread isolation) `[x]`
Kontekst:
- w `BUGS_FINDE` byl finding o `winsound.PlaySound(...)` jako przyczynie freeze GUI,
- po weryfikacji sciezki runtime okazalo sie, ze Piper/Winsound dziala w dedykowanym watku TTS (`powiedz()` -> `_start_tts_thread()` -> `_watek_mowy()`), a nie na watku GUI/Tkinter.

Wdrozone:
- dodano regression test izolacji worker-thread:
  - symuluje zablokowane `_speak_tts(...)`,
  - potwierdza, ze `powiedz()` wraca szybko (nie blokuje wywolujacego),
  - slot TTS pozostaje aktywny podczas pracy workera i zwalnia sie po zakonczeniu.

Efekt:
- finding "GUI freeze przez `winsound.PlaySound`" domkniety jako false positive,
- osobny temat blokowania samego watku TTS / braku timeout playbacku pozostaje otwarty (to inny problem niz freeze GUI).

Test regresyjny:
- `tests/test_f47_tts_powiedz_nonblocking_worker_isolation.py`
  - `test_powiedz_returns_while_tts_worker_is_blocked`

### 16.47 Piper/Winsound: timeout playbacku w watku TTS (mitigacja hangu) `[~]`
Kontekst:
- po domknieciu `16.46` jako false positive (GUI), zostawal realny problem: `winsound.PlaySound(...)` mogl zablokowac sam watek TTS bez timeoutu,
- przy aktywnym guardzie `16.40` (`1` aktywny watek TTS) taki hang mogl skutkowac dluga cisza / dropami kolejnych komunikatow.

Wdrozone (mitigacja):
- w `logic/tts/piper_tts.py` dodano helper `_play_wav_with_timeout(...)`:
  - odtwarza WAV w pomocniczym daemon-thread,
  - czeka `join(timeout)` (domyslnie `45s`),
  - przy timeout wykonuje best-effort `winsound.PlaySound(None, SND_PURGE)`,
  - loguje throttled `piper_winsound_playback_timeout`,
  - zwraca `False` (pipeline TTS konczy sie kontrolowanie zamiast wisiec bez limitu).
- `piper_tts.speak(...)` uzywa helpera zamiast bezposredniego blokujacego `winsound.PlaySound(...)`.

Efekt:
- zawieszony playback `winsound` nie trzyma bez limitu calego pipeline Pipera/TTS,
- runtime dostaje diagnostyke timeoutu i moze przejsc dalej.

Status:
- mitigacja wdrozona,
- follow-up guard dla powtornego hangu workerow domkniety w `16.55` (status findingu runtime: `[x]`),
- nie jest to pelne rozwiazanie scheduler/playback manager (zachowanie `SND_PURGE` zalezy od drivera / winsound).

Test regresyjny:
- `tests/test_f48_piper_winsound_playback_timeout.py`
  - `test_play_wav_with_timeout_returns_false_and_purges_when_playback_hangs`

### 16.48 PlayerDB: cache `ensure_schema` per DB path/session (redukcja overhead ingestu) `[x]`
Kontekst:
- w `BUGS_FINDE` byl finding, ze `playerdb_connection(..., ensure_schema=True)` uruchamial `ensure_playerdb_schema()` przy kazdym ingest/journal event,
- powodowalo to powtarzalny overhead SQLite (PRAGMA / schema checks / migrations table) mimo braku zmian schematu.

Wdrozone:
- dodano process/session cache "schema ensured" per DB path w `logic/player_local_db.py`,
- `playerdb_connection(...)`:
  - przy `ensure_schema=True` sprawdza cache dla danego path,
  - uruchamia `ensure_playerdb_schema(...)` tylko przy pierwszym uzyciu pathu (lub gdy plik zniknal),
  - kolejne polaczenia dla tego samego DB path omijaja redundantne schema-checki,
- explicit `ensure_playerdb_schema(...)` zachowuje dotychczasowa semantyke (nie zostal "zcacheowany"), ale po sukcesie oznacza path jako ensured.

Efekt:
- redukcja overheadu DB w goracych sciezkach ingestu (`Location`, `Docked`, cash-in, `Market.json`) dla tego samego pliku playerdb,
- brak zmiany kontraktu migracji/schema dla jawnych wywolan `ensure_playerdb_schema(...)`.

Test regresyjny:
- `tests/test_f16_playerdb_schema_and_migrations.py`
  - `test_playerdb_connection_caches_schema_ensure_per_db_path`

### 16.49 `app_state`: lock-safe accessors dla hotspotow runtime (mitigacja race/dirty-read) `[~]`
Kontekst:
- w `BUGS_FINDE` byl finding o lockless read/write pol `app_state` (`bootstrap_replay`, `current_system`, `has_live_system_event`) pomiedzy watkiem journala, GUI i sciezkami calloutow,
- najwieksze hotspoty byly w `MainLoop` (bootstrap replay), GUI (`check_queue` / snapshoty) oraz sciezkach navigation/cash-in uzywajacych bezposrednich `getattr(app_state, ...)`.

Wdrozone:
- dodano lock-safe helpery w `app/state.py`:
  - `set_bootstrap_replay(...)`
  - `is_bootstrap_replay()`
  - `get_current_system_name()`
  - `has_live_system_event_flag()`
- podmieniono hotspot call-site'y na helpery w:
  - `app/main_loop.py` (set/reset `bootstrap_replay`, `runtime_critical` context `system`)
  - `gui/app.py` (`check_queue` start-label gate, debug snapshot, wybrane akcje route/cash-in)
  - `logic/events/navigation_events.py` (`bootstrap_replay`, `current_system`)
  - `logic/events/cash_in_assistant.py` (`bootstrap_replay`, `has_live_system_event`, `current_system`)
- dodano regression test `F49`:
  - round-trip helperow `AppState`,
  - uzycie helperow w `_detect_offline_or_interrupted(...)`,
  - guard bootstrap replay w `trigger_startjump_cash_in_callout(...)`.

Efekt:
- mniejsza szansa na dirty-read/stale context dla kluczowych pol `app_state` w najczestszych sciezkach runtime,
- ujednolicone API odczytu/zapisu tych pol (mniej bezposrednich `getattr(...)` / assignmentow w hotspotach).

Status:
- mitigacja hotspotow (`[~]`) dla pierwotnego zakresu,
- follow-upy domykajace finding dla tych pol: `16.51` (stress test) + `16.56` (remaining call-site sweep).

Commit:
- `b0453ff` - `[PUB] Add lock-safe app_state accessors for runtime hotspots`

Testy:
- `tests.test_f49_app_state_runtime_lock_accessors_and_hotspots`
- `tests.test_f11_cash_in_startjump_callout`
- `tests.test_f17_cash_in_station_clipboard_gate`
- `tests.test_f38_main_loop_bootstrap_tail_lines_memory_safe`
- `tests.test_f45_gui_check_queue_tick_limit`
- `tests.test_f46_main_loop_run_restart_on_unhandled_exception`

### 16.50 NotificationDebouncer: deferred persist kontraktu poza caller-path `can_send()` (mitigacja janku) `[~]`
Kontekst:
- w `BUGS_FINDE` byl finding, ze `NotificationDebouncer.can_send()` moze wykonywac synchroniczny zapis kontraktu (`config.update_anti_spam_state`) na sciezce wywolania (potencjalnie z watku UI/Tkinter),
- `load_from_contract()` jest po pierwszym razie cache'owany, ale persist stanu debouncera nadal mogl wpasc na caller-path co min. `anti_spam.persist_min_interval_sec` i powodowac mikro-freezy/jank na wolniejszym dysku.

Wdrozone:
- `logic/utils/notify.py` (`NotificationDebouncer`):
  - dodano write-behind scheduler dla persistu (`threading.Timer`) i sekwencje zmian/flush (`_persist_change_seq`, `_persist_flushed_seq`),
  - `can_send()` po zmianie stanu wywoluje `_request_persist_after_change()` zamiast bezposredniego `persist_to_contract()`,
  - pierwszy persist po starcie/reset pozostaje synchroniczny (zachowanie restart/durability),
  - kolejne persysty sa deferowane poza caller-path (timer callback -> `persist_to_contract()`),
  - `reset()` anuluje pending timer, zeby nie zostawiac background write po testach/resecie runtime.
- dodano regression test `F50`:
  - pierwszy persist jest sync,
  - kolejna zmiana jest deferowana przez timer,
  - callback timera flushuje pending persist.

Efekt:
- mniejszy jank na caller-path `can_send()` (szczegolnie UI/Tkinter) przy czestszych emitach insightow/voice gate,
- zachowane cooldowny i restartowa semantyka pierwszego zapisu.

Status:
- mitigacja (`[~]`) - brak pelnej kolejki async dla wszystkich I/O kontraktu (benchmark caller-path dla `50x can_send()` domkniety follow-upem `16.53`).

Commit:
- `aa9ef31` - `[PUB] Defer debouncer contract writes off caller path`

Testy:
- `tests.test_f50_notify_debouncer_deferred_persist`
- `tests.test_f10_anti_spam_persistence_ttl`
- `tests.test_f5_anti_spam_regression`

### 16.54 TTS spawning (`16.40`): FIFO worker queue zamiast drop overlap `[x]`
Kontekst:
- `16.40` wprowadzilo mitigacje (hard cap `1` aktywny watek TTS), ale kosztem dropowania nowych komunikatow podczas aktywnej syntezy (`thread_busy_drop`),
- w `BUGS_FINDE` punkt `Unbounded TTS thread spawning` pozostawal `[~]` do czasu wdrozenia prawdziwej kolejki FIFO/worker.

Wdrozone:
- `logic/utils/notify.py`:
  - dodano kolejke mowienia `_TTS_SPEECH_QUEUE`,
  - `_start_tts_thread(...)`:
    - zawsze enqueue tekst TTS,
    - uruchamia worker tylko gdy brak aktywnego workera,
  - dodano `_tts_worker_loop()`:
    - pojedynczy worker serializuje synteze (FIFO),
    - bez tworzenia nowego watku na kazdy komunikat,
  - `powiedz()` nie dropuje juz overlapu przy aktywnym TTS (brak `tts:thread_busy_drop` na normalnej sciezce),
  - `_watek_mowy(...)` dostal `release_slot` (domyslnie `True`) dla kompatybilnosci testow/manual call.

Efekt:
- brak nakladania i brak gubienia komunikatow z powodu aktywnego TTS,
- brak lawinowego spawnienia watkow TTS,
- zachowany non-blocking caller-path `powiedz()` (worker dziala asynchronicznie).

Testy regresyjne:
- `tests/test_f43_tts_thread_spawning_limit.py`
  - aktualizacja pod semantyke queue (1 worker + queued overlap, bez drop),
- `tests/test_f47_tts_powiedz_nonblocking_worker_isolation.py`
  - izolacja workera i szybki powrot `powiedz()`,
- `tests/test_f51_tts_fifo_worker_queue.py` (nowy)
  - potwierdzenie FIFO i braku dropow dla 3 komunikatow.

Commit:
- `87b05b1` - `[PUB] Add FIFO TTS worker queue to avoid overlap drops`

### 16.55 Piper/Winsound (`16.47`): guard na powtorne hungi playback workerow `[x]`
Kontekst:
- po `16.47` mielismy timeout + `SND_PURGE`, ale przy niektorych driverach `winsound` moglem nadal zostac wiszacy worker playbacku,
- kolejne wywolania mogly wtedy uruchamiac nastepne helper-thready playbacku, co kumulowalo "zombie" workerow w tle.

Wdrozone:
- `logic/tts/piper_tts.py`:
  - dodano guard globalny dla playbacku `winsound`:
    - `_WINSOUND_PLAYBACK_GUARD_LOCK`
    - `_WINSOUND_HUNG_WORKER`
  - `_play_wav_with_timeout(...)`:
    - przed startem nowego playbacku sprawdza, czy poprzedni hung-worker nadal zyje,
    - jesli tak: pomija nowe odtwarzanie i loguje throttled `piper_winsound_playback_still_hung`,
    - po timeoutie zapamietuje wiszacy worker jako active hung,
    - po poprawnym zakonczeniu czysci guard.
- rozszerzono regression `F48`:
  - `test_play_wav_with_timeout_skips_new_playback_while_previous_hung_worker_is_alive`
    - potwierdza, ze drugie wywolanie nie uruchamia nowego playbacku podczas trwajacego hangu.

Efekt:
- brak kaskadowego spawnienia kolejnych wiszacych workerow winsound przy powtarzalnym hangu drivera,
- bardziej przewidywalny fail-safe w TTS (skip + log) zamiast narastajacego problemu watkow.

Status:
- punkt `winsound blokuje TTS worker` domkniety jako `[x]` dla obecnego zakresu runtime guardow,
- ograniczenie techniczne pozostaje: `SND_PURGE` jest best-effort zalezny od sterownika audio.

Commit:
- `e7c3d1c` - `[PUB] Guard repeated winsound hangs from spawning new playback`

Testy:
- `tests.test_f48_piper_winsound_playback_timeout`
- `tests.test_f44_piper_tts_timeout_and_cleanup`
- `tests.test_f51_tts_fifo_worker_queue`
- `tests.test_f43_tts_thread_spawning_limit`
- `tests.test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard`

### 16.56 `app_state` (`16.49`): remaining runtime call-site sweep domkniety `[x]`
Kontekst:
- po `16.49` i `16.51` finding dla pol `bootstrap_replay/current_system/has_live_system_event` byl blisko domkniecia, ale zostawaly pojedyncze runtime odczyty bez helperow lock-safe.

Wdrozone:
- podmieniono remaining runtime call-site odczytow `current_system` na helpery:
  - `logic/events/exploration_fss_events.py`
  - `logic/events/trade_events.py`
  - `gui/tabs/spansh/trade.py` (fallback station suggest; kompatybilny fallback dla starszego `app_state`)
- sweep `rg` dla runtime (`app/logic/gui`) nie zwraca juz bezposrednich odczytow/zapisow tych trzech pol (poza komentarzami/docs).

Efekt:
- finding `app_state.bootstrap_replay/current_system/has_live_system_event` z `BUGS_FINDE` jest domkniety dla deklarowanego zakresu tych pol,
- runtime korzysta ze spojnego API helperow lock-safe w glownych sciezkach gameplay/UI.

Commit:
- `7a8dbe3` - `[PUB] Replace remaining app_state field reads with lock-safe helpers`

Testy:
- `tests.test_f24_fss_all_bodies_found_does_not_force_full_scan`
- `tests.test_f30_fss_milestone_catchup_and_body_dedupe`
- `tests.test_f17_tts_operational_callouts`
- `tests.test_f5_anti_spam_regression`
- `tests.test_f10_anti_spam_persistence_ttl`

### 16.57 Bug 16.8 (pyttsx3 focus steal): hard block także dla explicit engine + opt-in only `[x]`
Kontekst:
- po `cc6ac77` auto fallback do pyttsx3 byl domyslnie blokowany, ale explicit `tts.engine=pyttsx3` nadal mogl aktywowac SAPI5/COM i kraść focus z gry.

Wdrozone:
- `config.py`:
  - dodano nowa flage `tts.pyttsx3_allow_focus_risk` (domyslnie `False`),
- `logic/utils/notify.py`:
  - dodano focus-safe hard guard przed `_speak_pyttsx3(...)`,
  - guard dziala dla obu sciezek:
    - auto fallback (`engine=auto` + fallback allowed),
    - explicit `engine=pyttsx3`,
  - gdy guard aktywny:
    - throttled log `tts:pyttsx3_focus_risk_blocked`,
    - user-facing soft diagnostic o blokadzie pyttsx3.
- `tests/test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard.py`:
  - zaktualizowano/regresje:
    - explicit pyttsx3 by default blocked,
    - explicit pyttsx3 allowed przy `tts.pyttsx3_allow_focus_risk=true`,
    - auto fallback opt-in bez focus-risk opt-in nadal blocked,
    - auto fallback + focus-risk opt-in -> allowed.

Efekt:
- pyttsx3/SAPI5 nie uruchamia sie juz "przypadkiem" w runtime gameplay,
- ryzyko focus steal z `pyttsx3` jest domyslnie odciete (opt-in only).

Commit:
- `9c72df3` - `[PUB] Block pyttsx3 by default unless focus-risk opt-in is set`

Testy:
- `tests.test_f31_tts_auto_pyttsx3_fallback_focus_safe_guard`
- `tests.test_f40_pyttsx3_polish_voice_selection`
- `tests.test_f17_tts_operational_callouts`
- `tests.test_f43_tts_thread_spawning_limit`
- `tests.test_f51_tts_fifo_worker_queue`

### 16.58 Mapa (`F6-01`): eliminacja N+1 SQLite przy wyliczaniu warstw stacji `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-01`, SEV-2) mapa wykonywala N+1 zapytan SQLite przy kazdym reloadzie (`_compute_layer_flags_for_nodes` wywolywal `get_stations_for_system(...)` osobno dla kazdego noda),
- powodowalo to kosztowny reload mapy przy wiekszych zbiorach systemow i szybkim przelaczaniu filtrow.

Wdrozone:
- `logic/personal_map_data_provider.py`:
  - dodano batched API `get_station_layer_flags_for_systems(...)`,
  - pojedyncza kwerenda SQL (z `ROW_NUMBER() OVER (...)`) zwraca per-system:
    - `stations_count`,
    - `has_market`,
    - `has_cashin`,
  - zachowano limit `200` rekordow per system (zgodny z poprzednia semantyka call-site).
- `gui/tabs/journal_map.py`:
  - `_compute_layer_flags_for_nodes(...)` preferuje nowe API batch,
  - zachowany fallback do starej sciezki `get_stations_for_system(...)` gdy batch API nie istnieje albo zwroci blad.
- `tests/test_f20_map_filters_layers_freshness_source_contract.py`:
  - dodano regression:
    - `test_layer_flags_use_batched_station_lookup_when_available`,
    - asercje: `batch_calls == 1`, `single_calls == 0`, poprawne flagi warstw.

Efekt:
- reload mapy nie wykonuje juz N osobnych zapytan stacji dla N nodow, gdy provider wspiera batch API,
- zachowana kompatybilnosc wsteczna i bezpieczny fallback.

Commit:
- `f29e0a2` - `[PUB] Batch station-layer flag lookup to remove map N+1 reload queries`

Testy:
- `tests.test_f20_map_filters_layers_freshness_source_contract`
- `tests.test_f20_map_data_provider_adapters`
- `tests.test_f20_quality_gates_and_smoke`

### 16.59 Mapa (`F6-02`): auto-refresh reselect race i utrata selekcji po reloadzie `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-02`, SEV-2) po auto-refresh mapa mogla stracic selekcje systemu bez czytelnego sygnalu dla uzytkownika,
- dodatkowo reselekcja byla oparta tylko o stary `node_key`; gdy klucz noda zmienial sie po reloadzie (przy tej samej nazwie systemu), selekcja nie byla odtwarzana.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - `_run_debounced_auto_refresh(...)`:
    - zapamietuje `selected_system_name` przed `reload_from_playerdb()`,
    - po reloadzie probuje reselekcji:
      - najpierw po starym `selected_key`,
      - fallback po nazwie systemu (`system_name`) gdy klucz ulegl zmianie,
    - gdy reselekcja sie nie powiedzie:
      - czyści selekcje,
      - ustawia jawny status: `utracono selekcje (system poza filtrami)`.
  - dodano helper `_find_node_key_by_system_name(...)`.
- `tests/test_f23_map_auto_refresh_on_playerdb_updates_contract.py`:
  - `test_auto_refresh_reselects_by_system_name_when_node_key_changes`,
  - `test_auto_refresh_reports_selection_lost_when_selected_node_disappears`.

Efekt:
- stabilniejsze odtwarzanie selekcji po auto-refresh mapy,
- brak „cichej” utraty selekcji bez informacji; uzytkownik dostaje jednoznaczny status.

Commit:
- `c083649` - `[PUB] Harden map auto-refresh reselection for key-change/lost-selection cases`

Testy:
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f20_map_filters_layers_freshness_source_contract`

### 16.60 Mapa (`F6-04`): usuniecie sync SQLite z click drilldown (cache prefetched stacji) `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-04`, SEV-2) `select_system_node(...)` wykonywal synchroniczne `get_stations_for_system(...)` na click path,
- przy wolniejszym dysku / ingest-collision moglo to chwilowo przycinac UI podczas klikniecia noda.

Wdrozone:
- `logic/personal_map_data_provider.py`:
  - dodano batch API `get_stations_for_systems(...)` (stacje per system, limitowane `ROW_NUMBER() OVER (...)`).
- `gui/tabs/journal_map.py`:
  - dodano prefetch cache stacji dla aktualnych nodow przy `reload_from_playerdb()`:
    - `_prime_prefetched_system_stations(...)`,
    - `_prefetched_stations_for_node(...)`,
  - `select_system_node(...)` uzywa najpierw prefetched cache zamiast on-demand query,
  - zostawiono fallback do `get_stations_for_system(...)` dla kompatybilnosci/starszych providerow.
- `tests/test_f20_map_system_station_drilldown_panels_contract.py`:
  - dodano regression:
    - `test_map_drilldown_uses_prefetched_batch_stations_instead_of_single_query`
    - asercje: click drilldown korzysta z batch cache, `single_calls == 0`.

Efekt:
- klikniecie noda na mapie nie wykonuje juz synchronicznego pojedynczego query stacji (przy dostepnym prefetch cache),
- mniejszy risk UI hitch przy drilldown i aktywnym runtime.

Commit:
- `2a4f5ee` - `[PUB] Prefetch map drilldown stations to avoid sync single-query on click`

Testy:
- `tests.test_f20_map_system_station_drilldown_panels_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f20_map_filters_layers_freshness_source_contract`
- `tests.test_f20_map_data_provider_adapters`

### 16.61 Mapa (`F6-03`): stale tooltip badges po zmianie warstw (cache invalidation) `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-03`, SEV-2) tooltip mapy mogl utrzymac nieaktualny tekst/badge po zmianie warstw/filtra bez ruchu kursora.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - `_on_filter_changed()` wykonuje teraz natychmiastowe `_hide_map_tooltip()` przed reloadem,
  - gwarantowane wyczyszczenie:
    - `map_tooltip` na canvasie,
    - `_tooltip_text_cache`,
    - `_tooltip_node_key` / `_tooltip_last_pos`.
- `tests/test_f20_map_filters_layers_freshness_source_contract.py`:
  - dodano regression:
    - `test_filter_change_hides_tooltip_to_avoid_stale_layer_badges`.

Efekt:
- po zmianie warstw/filtra nie ma ryzyka pozostania stalego tooltipu z poprzednimi badge,
- brak zaleznosci od ruchu myszy, zeby wymusic odswiezenie tooltipu.

Commit:
- `2644f17` - `[PUB] Invalidate map tooltip cache immediately on filter changes`

Testy:
- `tests.test_f20_map_filters_layers_freshness_source_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`

### 16.62 Mapa (`F6-05`): debounce `_on_filter_changed` (redukcja reload storm) `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-05`, SEV-3) szybkie klikanie checkboxow warstw triggerowalo wiele kolejnych `reload_from_playerdb()` bez debounce.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - dodano debounce dla reloadu filtrow:
    - `_filter_reload_debounce_ms` (domyslnie `90ms`),
    - `_filter_reload_after_id`,
    - `_cancel_filter_reload_debounce()`,
    - `_schedule_filter_reload_debounce()`,
    - `_run_debounced_filter_reload()`,
  - `_on_filter_changed()`:
    - nadal robi natychmiastowe `_hide_map_tooltip()` + persist UI state,
    - reload mapy uruchamiany przez debounce (zamiast natychmiast).
  - `destroy()`:
    - anuluje pending debounce reloadu filtrow.
- `tests/test_f20_map_filters_layers_freshness_source_contract.py`:
  - dodano regression:
    - `test_filter_changes_are_debounced_into_single_reload`
    - szybkie 3 wywolania `_on_filter_changed()` => pojedynczy reload po timeout.

Efekt:
- mniejszy jitter/UI load przy szybkim przelaczaniu warstw/filtrow,
- brak kaskadowych reloadow mapy na kazde pojedyncze klikniecie.

Commit:
- `b39e969` - `[PUB] Debounce map filter-change reloads to avoid UI reload storms`

Testy:
- `tests.test_f20_map_filters_layers_freshness_source_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`

### 16.63 Mapa (`F6-06`): clear stale trade highlight przy `Trade=OFF` i reloadzie `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-06`, SEV-3) highlighty trade compare mogly zostawac w stanie i wracac po ponownym wlaczeniu warstwy Trade po reloadach.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - `_refresh_trade_compare_if_needed()`:
    - gdy `layer_trade_var=False`, czyści `_trade_highlight_node_keys`,
    - wykonuje `_redraw_scene()` tylko gdy highlight byl aktywny (unikamy zbednego redraw).
- `tests/test_f20_map_trade_compare_one_commodity_highlight_contract.py`:
  - dodano regression:
    - `test_trade_highlight_is_cleared_on_reload_when_trade_layer_disabled`
    - scenariusz: `Trade ON` + compare -> `Trade OFF` + reload -> highlight empty -> `Trade ON` + reload -> highlight odtwarzany swiezo.

Efekt:
- brak stalego highlightu po reloadach, gdy warstwa Trade jest tymczasowo wylaczona,
- powrot warstwy Trade odtwarza highlight z aktualnych danych, nie ze starego stanu.

Commit:
- `f2b9fa3` - `[PUB] Clear stale trade highlights when trade layer is disabled on reload`

Testy:
- `tests.test_f20_map_trade_compare_one_commodity_highlight_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f21_map_trade_compare_v2_multiselect_modal_contract`

### 16.64 Mapa (`F6-07`): casefold-spojnosc selekcji trade pickera `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-07`, SEV-3, podejrzenie) trade picker porownywal selekcje case-sensitive, co moglo rozjezdzac checkbox state/toggle dla wariantow typu `gold` vs `Gold`.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - dodano helpery case-insensitive dla `_trade_picker_selected`:
    - `_trade_picker_selection_contains(...)`,
    - `_trade_picker_selection_add(...)`,
    - `_trade_picker_selection_remove(...)`,
  - `_trade_picker_refresh_rows()` i `_trade_picker_toggle_row_iid()` korzystaja z helperow,
  - `_trade_picker_accept()` deduplikuje finalna liste po `casefold`.
- `tests/test_f21_map_trade_compare_v2_multiselect_modal_contract.py`:
  - dodano regression:
    - `test_trade_picker_selection_is_casefold_consistent`
    - scenariusz: selekcja `{"gold"}` poprawnie zaznacza wiersz `Gold`, toggle usuwa/dodaje case-insensitive.

Efekt:
- spojny stan checkboxow i toggle niezaleznie od wariantu wielkosci liter commodity,
- brak duplikatow case-variantow przy akceptacji pickera.

Commit:
- `025fe39` - `[PUB] Make map trade-picker selection case-insensitive`

Testy:
- `tests.test_f21_map_trade_compare_v2_multiselect_modal_contract`
- `tests.test_f22_map_trade_compare_modal_scrollbar_and_station_available_filter_contract`
- `tests.test_f20_map_trade_compare_one_commodity_highlight_contract`

### 16.65 Mapa (`F6-10`): notify map activation przy powrocie na `Dziennik` `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-10`, SEV-3) mapa mogla nie dostac sygnalu aktywacji po powrocie na glowna zakladke `Dziennik`, gdy subtab `Mapa` byl juz aktywny.

Wdrozone:
- `gui/app.py`:
  - `RenataApp._on_tab_changed(...)`:
    - po zmianie main taba sprawdza aktywny key,
    - gdy aktywny `journal`, wywoluje `tab_journal.on_parent_main_tab_activated()` (best-effort, z fallback logiem przy bledzie).
- `gui/tabs/logbook.py`:
  - wydzielono helper `_notify_map_parent_activation()` (reuzywany),
  - `_on_subtab_changed()` korzysta z helpera,
  - dodano `on_parent_main_tab_activated()` dla callbacku z `RenataApp`.
- `tests/test_f23_map_auto_refresh_on_playerdb_updates_contract.py`:
  - dodano regresje:
    - `test_app_tab_changed_notifies_journal_when_main_tab_is_journal`,
    - `test_app_tab_changed_skips_journal_activation_for_other_tabs`.

Efekt:
- powrot na `Dziennik` nie pomija juz aktywacji mapy, gdy `Mapa` jest aktywnym subtabem,
- deferred auto-refresh mapy moze zostac uruchomiony od razu po powrocie na glowny tab Journal.

Commit:
- `e546dbe` - `[PUB] Bridge main-tab Journal activation to map subtab refresh path`

Testy:
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f21_quality_gates_and_smoke`

### 16.66 Mapa (`F6-08`): auto-refresh tylko gdy `Dziennik/Mapa` jest runtime-visible `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-08`, SEV-3) mapa mogla wykonywac auto-refresh i query nawet gdy glowny tab nie byl `Dziennik` (np. uzytkownik byl na `Spansh`), o ile aktywny pozostawal subtab `Mapa`.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - dodano `_is_journal_main_tab_active()` (resolver przez `app._resolve_active_main_tab_key`),
  - `_is_map_runtime_visible_for_auto_refresh()` wymaga teraz:
    - aktywnego subtaba `map`,
    - aktywnego main taba `journal` (gdy resolver jest dostepny; fallback kompatybilny przy braku resolvera).
- `tests/test_f23_map_auto_refresh_on_playerdb_updates_contract.py`:
  - dodano regression:
    - `test_journal_map_auto_refresh_is_deferred_when_main_tab_not_journal`
    - asercje: update przy `main=spansh` jest deferred (`scheduled=False`), po powrocie na `journal` następuje reload.

Efekt:
- brak niepotrzebnych reloadow mapy, gdy uzytkownik pracuje na innej glownej zakladce,
- zachowany bezpieczny resume deferred refresh po powrocie do `Dziennik` (mostek z `16.65`).

Commit:
- `79aba21` - `[PUB] Gate map auto-refresh by Journal main tab visibility (F6-08)`

Testy:
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f21_quality_gates_and_smoke`

### 16.67 Mapa (`F6-09`): pre-filter non-renderable nodes przed flagami/prefetch/render `[x]`
Kontekst:
- w `BUGS_FINDE` (`F6-09`, SEV-3) znaleziono niespojnosc pipeline: node mogl byc odrzucony dopiero w `set_graph_data()` (`x/y=None`), ale warstwy i prefetch potrafily byc liczone wczesniej dla tego rekordu.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - dodano `JournalMapTab._prepare_renderable_nodes(...)` (walidacja: `key` + float `x/y`),
  - `reload_from_playerdb()` uzywa teraz jednej, oczyszczonej listy `render_nodes` dla:
    - `_compute_layer_flags_for_nodes(...)`,
    - `_prime_prefetched_system_stations(...)`,
    - `set_graph_data(...)`,
  - fallback edges (`sequential_fallback`) budowane sa z `render_nodes`,
  - wynik reloadu raportuje `dropped_nodes`, a status mapy dopisuje liczbe pominietych nodow.
- `tests/test_f20_map_filters_layers_freshness_source_contract.py`:
  - dodano regresje `test_reload_skips_non_renderable_nodes_before_flags_compute`,
  - asercje: `_compute_layer_flags_for_nodes` dostaje tylko renderowalne nody, `dropped_nodes=1`, mapa renderuje wyłącznie `NODE_OK`.

Efekt:
- brak marnowania zapytan warstwowych dla rekordow, ktore i tak nie trafia na canvas,
- spojny pipeline danych (ta sama lista nodow dla flags/prefetch/render),
- czytelniejsza diagnostyka (`dropped_nodes`) dla edge-case danych historycznych/uszkodzonych.

Commit:
- `b6def5f` - `[PUB] Pre-filter non-renderable map nodes before flags and render (F6-09)`

Testy:
- `tests.test_f20_map_filters_layers_freshness_source_contract`
- `tests.test_f21_quality_gates_and_smoke`
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`

### 16.69 GUI (`SEV-3`): lifecycle timerow `.after()` (queue/debug) bez duplikacji i cleanup on close `[x]`
Kontekst:
- w `BUGS_FINDE` otwarty byl problem timerow `.after()` w GUI (`check_queue` / debug panel): brak trackingu callback id mogl prowadzic do duplikacji schedule i orphaned callbackow w dlugiej sesji.

Wdrozone:
- `gui/app.py`:
  - dodano tracking queue timera: `self._queue_check_after_id`,
  - dodano helpery `_schedule_queue_check(...)` i `_cancel_queue_check()` (cancel-before-reschedule),
  - init petli kolejki przechodzi przez `_schedule_queue_check(100)` zamiast surowego `root.after(...)`,
  - `check_queue()` czyści aktywny id i reschedule robi przez wspolny scheduler,
  - dodano tracking debug timera: `self._debug_panel_after_id`,
  - dodano `_cancel_debug_panel_update()` + cancel-before-reschedule w `_schedule_debug_panel_update()`,
  - `_on_main_close()` anuluje timery `debug` i `queue` przed `quit()`.
- `tests/test_f52_gui_after_timer_lifecycle_contract.py`:
  - `test_debug_panel_schedule_cancels_previous_timer`,
  - `test_queue_schedule_cancels_previous_timer`,
  - `test_main_close_cancels_timers_before_quit`.

Efekt:
- brak narastania duplikatow callbackow `.after()` dla debug panelu i loopa kolejki,
- jawny cleanup timerow przy zamykaniu okna,
- mniejsze ryzyko długosesyjnego memory leak/janku od orphaned callbackow.

Commit:
- `aa754b9` - `[PUB] Harden GUI after-timer lifecycle for queue and debug panel`

Testy:
- `tests.test_f52_gui_after_timer_lifecycle_contract`
- `tests.test_f45_gui_check_queue_tick_limit`

### 16.71 NotificationDebouncer (`SEV-2`): pełne zdjęcie persist I/O z caller-path (`can_send`) `[x]`
Kontekst:
- w `BUGS_FINDE` punkt `Config I/O jank` był częściowo domknięty (`16.50/16.52/16.53`), ale pierwszy write w `can_send()` nadal mógł wejść synchronicznie w caller-path.

Wdrozone:
- `logic/utils/notify.py`:
  - `can_send()` nie wykonuje już żadnego sync persistu przez `_request_persist_after_change()` (również dla pierwszego write),
  - persist idzie zawsze przez deferred timer path (`_ensure_persist_timer(...)`),
  - dodano `_ensure_async_persist_fallback()` na wypadek błędu startu timera (fallback worker thread zamiast sync I/O w caller-path),
  - `reset()` flushuje pending state przed czyszczeniem (stabilna trwałość stanu przy szybkim resecie/restarcie testowym),
  - dodano flagę `_persist_fallback_active` (guard przed duplikacją fallback workerów).
- `tests/test_f50_notify_debouncer_deferred_persist.py`:
  - aktualizacja kontraktu na fully-async caller-path:
    - first write jest deferred,
    - burst nie robi sync write,
    - wall-clock test wymusza szybki first call (bez slow I/O na caller-path),
    - stale-timer/reset nadal poprawnie izoluje callbacki.

Efekt:
- `can_send()` pozostaje responsywny także na pierwszym zapisie,
- brak sync `config.update_anti_spam_state(...)` w caller-path,
- zachowana trwałość stanu przy szybkim `reset()` (flush pending before clear).

Commit:
- `9d51aa2` - `[PUB] Make NotificationDebouncer persist fully async on caller path`

Testy:
- `tests.test_f50_notify_debouncer_deferred_persist`
- `tests.test_f10_anti_spam_persistence_ttl`
- `tests.test_f5_anti_spam_regression`

### 16.70 Startup (`SEV-3`): bezpieczne odsłanianie okna po init (eliminacja race `after(0)`) `[x]`
Kontekst:
- w `BUGS_FINDE` otwarty byl punkt o potencjalnym race przy startupie: `root.after(0, _show_main_window)` moglo odpalic reveal okna zbyt wczesnie na wolnych maszynach.

Wdrozone:
- `main.py`:
  - wydzielono `run()` (czytelniejszy i testowalny startup flow),
  - dodano helper `_show_main_window_safe(root)` z oddzielnymi `try/except` dla `update_idletasks` i `deiconify`,
  - wprowadzono `MAIN_WINDOW_SHOW_DELAY_MS = 300`,
  - reveal okna jest teraz schedulowany przez `root.after(MAIN_WINDOW_SHOW_DELAY_MS, ...)`.
- `tests/test_f53_main_window_startup_show_delay_contract.py`:
  - `test_run_schedules_window_show_with_nonzero_delay`,
  - `test_show_main_window_safe_still_deiconifies_when_update_fails`,
  - `test_show_main_window_safe_swallow_exceptions`.

Efekt:
- mniejsze ryzyko black-screen race podczas startupu na wolniejszych hostach,
- zachowany fail-safe startup (brak crashu na błędzie `update_idletasks`/`deiconify`),
- startup ma teraz kontrakt testowy (delay > 0 i odporność helpera).

Commit:
- `8d4a2ce` - `[PUB] Harden startup window reveal scheduling and safety`

Testy:
- `tests.test_f53_main_window_startup_show_delay_contract`
- `tests.test_f17_quality_gates_and_smoke`

### 16.68 Route manager (`SEV-2`): worker lifecycle hardening (busy gate + timeout watchdog) `[x]`
Kontekst:
- w `BUGS_FINDE` pozostawal otwarty problem lifecycle workerow tras (`route_manager`): brak atomowego guardu startu oraz brak timeoutu na wiszacy job mogly zostawic planner stale w stanie `busy`.

Wdrozone:
- `app/route_manager.py`:
  - `RouteManager.__init__` przyjmuje `route_job_timeout_s` (domyslnie `120s`),
  - `start_route_thread(...)` zwraca `bool` i ma atomowy guard `self._busy` (reject konkurencyjnego startu + throttled log),
  - dodano `job token` (`_active_job_token`) i token-safe finalize, aby stary/timed-out worker nie nadpisal stanu nowego joba,
  - dodano watchdog `_start_route_job_watchdog(...)`: po przekroczeniu timeoutu odczepia `busy/current_mode` dla wiszacego workera i loguje `route_job_timeout`,
  - dodano soft logging wyjatkow workera (`route_job_worker_exception`) bez wycieku stanu.
- `tests/test_f51_route_manager_worker_lifecycle_contract.py`:
  - `test_start_route_thread_rejects_second_start_while_busy`,
  - `test_timeout_watchdog_releases_busy_state_for_hung_job`,
  - `test_timed_out_old_job_completion_does_not_clobber_new_busy_state`.

Efekt:
- brak race startu dwoch jobow tras naraz na poziomie `RouteManager`,
- wiszacy worker nie blokuje stale planera (auto-detach po timeout),
- stary worker po timeoutie nie moze juz nadpisac stanu aktywnego, nowszego joba.

Commit:
- `65ce69b` - `[PUB] Harden RouteManager worker lifecycle with timeout watchdog and token-safe finalize`

Testy:
- `tests.test_f51_route_manager_worker_lifecycle_contract`
- `tests.test_f11_cash_in_route_handoff`
- `tests.test_route_awareness_state`
- `tests.test_f17_quality_gates_and_smoke`

### 16.53 NotificationDebouncer (`16.50`): wall-clock regression dla burst `50x can_send()` na caller-path `[x]`
Kontekst:
- w `BUGS_FINDE` pozostawal otwarty test-gap wydajnosciowy dla `can_send()` (`50x` wywolan) po wdrozeniu deferred persistu,
- mielismy testy strukturalne (koalescencja/pending timer), ale brakowalo sprawdzenia czasowego caller-path pod symulowanym wolnym I/O.

Wdrozone:
- rozszerzono `tests/test_f50_notify_debouncer_deferred_persist.py` o:
  - `test_burst_can_send_after_first_write_stays_fast_under_slow_persist_io`
    - `config.update_anti_spam_state` symulowane jako wolne I/O (`sleep(0.03)`),
    - pierwszy `can_send()` zawiera sync write (oczekiwane),
    - kolejne `49` wywolan burst pozostaje szybkie na caller-path (deferred persist, bez kolejnych sync write).

Assercje testu:
- pierwszy call obejmuje koszt wolnego persistu (`>= 25 ms`),
- burst `49` kolejnych calli miesci sie w bezpiecznym budzecie (`< 350 ms`) na caller-path,
- liczba sync write na caller-path zostaje `1`,
- burst koalescuje do pojedynczego pending timera deferred persist.

Efekt:
- mamy wall-clock regression potwierdzajacy praktyczny efekt `16.50` (zdjecie dyskowego I/O z caller-path po pierwszym zapisie).

Commit:
- `a28361b` - `[PUB] Add can_send burst caller-path latency regression test`

Testy:
- `tests.test_f50_notify_debouncer_deferred_persist`
- `tests.test_f10_anti_spam_persistence_ttl`
- `tests.test_f5_anti_spam_regression`

### 16.51 `app_state` race (16.49): 2-thread stress regression test dla helperow/accessorow `[x]`
Kontekst:
- po wdrozeniu `16.49` (`lock-safe accessors` + migracja hotspotow) w `BUGS_FINDE` zostawal otwarty brakujacy test concurrency:
  - `Concurrent read/write app_state.bootstrap_replay`.

Wdrozone:
- rozszerzono `tests/test_f49_app_state_runtime_lock_accessors_and_hotspots.py` o 2-thread stress smoke:
  - writer: intensywne `set_bootstrap_replay(...)` + aktualizacja `current_system` / `has_live_system_event` pod `app_state.lock`,
  - reader: rownolegle odczyty helperami `is_bootstrap_replay()`, `get_current_system_name()`, `has_live_system_event_flag()`.

Assercje testu:
- oba watki koncza prace (brak hangu/deadlocka),
- brak wyjatkow w writer/reader,
- odczyty zwracaja poprawne typy (`bool` / `str`) pod obciazeniem.

Status:
- regression coverage dodane (`[x]`) dla brakujacego testu z `BUGS_FINDE`,
- nie zmienia statusu `16.49` (tam nadal `[~]`, bo to mitigacja hotspotow, nie pelny globalny audit wszystkich pol `app_state`).

Commit:
- `b75870b` - `[PUB] Add app_state accessor thread stress regression test`

Testy:
- `tests.test_f49_app_state_runtime_lock_accessors_and_hotspots`
- `tests.test_f11_cash_in_startjump_callout`
- `tests.test_f45_gui_check_queue_tick_limit`
- `tests.test_f38_main_loop_bootstrap_tail_lines_memory_safe`

### 16.52 NotificationDebouncer deferred persist: hardening timera po `reset()` + burst `50x can_send()` regression `[x]`
Kontekst:
- po `16.50` (deferred persist write-behind przez `Timer`) test strukturalny `F50` ujawnil edge-case:
  - stary callback timera mogl wejsc po `reset()` (np. w testach lub szybkim restarcie runtime) i wykonac stalego persysta / namieszac w stanie scheduler'a.

Wdrozone:
- `logic/utils/notify.py` (`NotificationDebouncer`):
  - dodano guard generacji callbackow timera (`_persist_epoch`) oraz identyfikatory timera (`_persist_timer_seq`, aktywny `seq/epoch`),
  - callback deferred persistu ignoruje stale wywolania po `reset()` / po zastapieniu timera nowym,
  - stale callback nie czysci juz referencji do nowego aktywnego timera (porownanie `seq + epoch`).
- rozszerzono `tests/test_f50_notify_debouncer_deferred_persist.py`:
  - `50x can_send()` burst coalescing (1 sync write na caller-path + 1 pending timer + deferred flush),
  - `stale_timer_callback_after_reset_is_ignored` (regresja na race po `reset()`).

Efekt:
- stabilniejszy scheduler deferred persistu debouncera (bez wyciekajacych/stalych callbackow po resecie),
- domkniete regression coverage dla strukturalnego scenariusza `50x can_send()` (koalescencja zapisow poza caller-path).

Status:
- hardening wdrozony (`[x]`) dla scheduler/timer race po `16.50`,
- wall-clock benchmark/profiling caller-path dla `50x can_send()` domkniety follow-upem `16.53`.

Commit:
- `78ac719` - `[PUB] Harden debouncer deferred persist timer reset race`

Testy:
- `tests.test_f50_notify_debouncer_deferred_persist`
- `tests.test_f10_anti_spam_persistence_ttl`
- `tests.test_f5_anti_spam_regression`

### 16.72 Mapa: precyzyjny hitbox klikniecia systemu (bez etykiet tekstowych) `[x]`
Kontekst:
- gameplay report: przy ciasno ulozonych gwiazdach klik czesto lapal zly system, bo aktywny obszar klikniecia byl wiekszy niz sama "gwiazda" (nakladaly sie etykiety).

Wdrozone:
- `gui/tabs/journal_map.py`:
  - aktywny tag klikowy `map_node` zostal ograniczony do glyphu gwiazdy (`create_oval`),
  - etykieta tekstowa node ma osobny tag (`map_node_label`) i nie przechwytuje juz klikow selekcji node.
- efekt: hitbox selekcji odpowiada rozmiarowi gwiazdy, a nie szerokosci nazwy systemu.

Testy:
- `tests.test_f20_map_travel_nodes_and_jumps_renderer_contract`
  - nowa regresja: elementy z tagiem `map_node` nie zawieraja typu `text`.
- `tests.test_f20_quality_gates_and_smoke`
- `tests.test_f21_quality_gates_and_smoke`
- `tests.test_f23_map_auto_refresh_on_playerdb_updates_contract`

Commit:
- `9c0bc39` - `[PUB] Tighten map node click hitbox to star glyph only`

---

### 16.73 Trade station picker: normalizacja nazwy systemu i hardening UX `[x]`
Objaw / ryzyko:
- gdy uzytkownik wpisal w polu systemu format `"System / Stacja"` lub `"System, Stacja"`,
  zapytanie EDSM do pobierania stacji bylo kierowane do calego napisu zamiast samej nazwy systemu,
- brak early return dla pustego pola systemu przed otwarciem pickera (prowadzil do bledow UX),
- przyciski pickera w trybie Spansh Trade nie respektowaly dark-theme aplikacji (niskie kontrast),
- refresh listy stacji nie mial oslonienie przed wyjatkami.

Wdrozone:
- `gui/tabs/spansh/trade.py`:
  - dodano `_system_name_for_station_lookup(value: str) -> str` (static helper):
    wydziela nazwe systemu ze stringow `"System / Stacja"` i `"System, Stacja"`;
  - `_load_station_candidates(system)` i `_open_station_picker_dialog()` uzywaja helpera
    zamiast inline slice logiki;
  - `_open_station_picker_dialog()`: early return z hintem gdy pole systemu puste;
  - explicit dark-theme palette dla przyciskow pickera (`tk.Button` + `bg/fg` kolory);
  - refresh listy stacji owinieto `try/except` z `log_event_throttled`.
- `logic/utils/renata_log.py`:
  - `log_event_throttled` dostalo backward-compat shim dla legacy sygnatury
    `(category, code, msg, cooldown_sec=..., context=...)` uzytej w Trade picker error paths.

Testy regresyjne:
- `tests/test_trade_station_picker_system_normalization.py` (2 testy):
  - `_system_name_for_station_lookup` strips inline station,
  - `_load_station_candidates` queries EDSM with normalized system.
- `tests/test_log_event_throttled_compat.py` (2 testy):
  - nowa sygnatura dziala bez zmian,
  - legacy sygnatura (`category, code, msg, cooldown_sec=...`) obslugiwana.

Commit:
- `b6fcff7` - `[PUB] Trade station picker: normalize system name + log_event_throttled compat shim`

---

### 16.74 Release hygiene / security: path leak sanitization + config write hardening `[x]`
Kontekst:
- w `BUGS_FINDE` (Sesja 8, release hygiene) pozostawaly otwarte punkty pre-release:
  - `SEV-1`: pelne sciezki systemowe w logach (`piper_tts`, `cache_store`),
  - `SEV-2`: cichy `except` przy `renata_user_home_dir()` i nieatomowy zapis `user_settings.json`.

Wdrozone:
- `logic/tts/piper_tts.py`:
  - sanitizacja danych w logach do samej nazwy pliku/katalogu (bez pelnej sciezki):
    - `piper_appdata_models_scan`: `base=os.path.basename(base)`,
    - `piper_wav_cleanup`: `path=os.path.basename(wav_path)`.
- `logic/cache_store.py`:
  - dodano helper `_safe_log_path_name(path)` i podmieniono pola logow:
    - `src`, `dst`, `path` raportowane jako basename,
    - dotyczy m.in. `cache.migrate.move_file`, `cache.prune.rmdir.*`,
      `cache.get.remove_corrupt`, `cache.delete`.
- `config.py`:
  - usunieto silent swallow w `renata_user_home_dir()`:
    - przy bledzie `os.makedirs(...)` logowany jest warning przez `_log_config_warning(...)`,
    - bez wycieku pelnej sciezki (`directory=os.path.basename(path)`).
  - utwardzono zapis ustawien (`ConfigManager._write_file`):
    - atomowy write: `tempfile.mkstemp(...)` + `json.dump(...)` + `os.replace(...)`,
    - cleanup pliku tymczasowego przy wyjatku.

Efekt:
- logi nie ujawniaja pelnych lokalnych sciezek typu `C:\Users\<user>\...`,
- mniejsze ryzyko uszkodzenia `user_settings.json` przy crashu w trakcie zapisu,
- brak cichego maskowania bledu tworzenia katalogu user-home.

Testy regresyjne:
- `tests/test_f60_release_hygiene_security_regressions.py`:
  - `test_piper_cleanup_log_uses_filename_only`,
  - `test_cache_logs_do_not_expose_full_paths`,
  - `test_renata_user_home_dir_logs_mkdir_failure_without_full_path`,
  - `test_config_write_is_atomic_and_preserves_previous_file_on_dump_failure`.
- smoke/regresje zalezne:
  - `tests/test_f44_piper_tts_timeout_and_cleanup`,
  - `tests/test_f10_preferences_persistence`,
  - `tests/test_spansh_client`.

Commit:
- (pending)

---

### T7-01 TTS: poprawna odmiana polska dla `n % 10 == 1` poza zakresem 11-19 `[x]`
Objaw / ryzyko:
- `_plural_form_pl(21, "kredyt", "kredyty", "kredytów")` zwracal `"kredytów"` (genityw) zamiast `"kredyt"` (singularis),
- analogicznie dla 31, 41, ..., 91, 101, 121 etc. - wszystkich liczb konczacych sie cyfra 1,
  ale NIE bedacych w zakresie specjalnym 11-19 jezyka polskiego,
- skutek: "dwadziescia jeden kredytow" zamiast poprawnego "dwadziescia jeden kredyt".

Root cause:
- `_plural_form_pl` miala sprawdzenie dla `n == 1` i dla `10 <= n%100 <= 19`,
  ale nie miala warunku dla `n % 10 == 1` (poza specjalnym zakresem 11-19).

Wdrozone:
- `logic/tts/text_preprocessor.py`:
  - dodano galez `if n % 10 == 1: return one` przed sprawdzeniem `2 <= n%10 <= 4`,
  - dotyczy wszystkich wywolan `_plural_form_pl` (jednostki Cr, %, LY, grupy tysiac/milion),
  - liczby 11, 111, 1011 (ktore sa w zakresie 10-19 modulo 100) pozostaja poprawnie w genitywum.

Testy regresyjne:
- `tests/test_f28_tts_number_verbalization_edge_cases_pl_forms.py` (18 testow, PASS):
  - 14 unit testow `_plural_form_pl`: 1, 2, 5, 11, 12, 20, 21, 22, 31, 91, 101, 111, 121, 1011,
  - 4 integration testow via `prepare_tts` raw_text: 1 Cr, 11 Cr, 21 Cr, 111 Cr.
- Istniejace testy TTS (20 testow): PASS bez regresji.

Commit:
- `75fd8d1` - `[PUB] Fix Polish plural form for n%10==1 credits and add edge-case tests`

---

### 16.75 Audyt: exploration summary / cash-in value integrity (logic) `[x]`
Kontekst:
- po gameplay raportach o rozjazdach (`realny zysk` vs `cash_in_session_estimated`) wykonano pelny audit przeplywu:
  - Journal -> `EventHandler` -> `SystemValueEngine` -> `exploration_summary` -> `cash_in_assistant`,
  - oraz recovery/bootstrap (`exploration_value_recovery`, `bootstrap_fss_state_from_journal_lines`).

Najwazniejsze znalezione bledy:

1) KRYTYCZNE - `Scan` belt/ring liczony jak planeta (`Planet Type`) i zawyza wartosci
- plik: `logic/system_value_engine.py` (`_extract_cartography_type`, fallback `Planet Type`)
- gdy event `Scan` nie ma ani `PlanetClass`, ani `StarType` (typowo `Belt Cluster` / ring), kod wpada do fallbacku planetarnego i nalicza wartosc cartography.
- efekt: sztuczne pompowanie `c_cartography` i `total` (a wiec tez summary/session cash-in).
- obserwacja z tail journali: duza liczba `Scan` bez `PlanetClass`/`StarType`, praktycznie wszystko belt-like.

2) KRYTYCZNE - runtime sell reset nie obejmuje `MultiSellExplorationData` `[x]`
- plik: `logic/event_handler.py`
  - mapper domen (`_sell_value_domain_for_event`) zna `MultiSellExplorationData`,
  - ale glowny warunek wywolania resetu (`if typ in {...}`) nie zawiera `MultiSellExplorationData`.
- efekt: po MultiSell UC wartosci sesyjne zostaja "stare" (brak resetu cartography), co daje rozjazd po sprzedazy.
- wdrozenie (2026-02-28):
  - `logic/event_handler.py`: sell runtime hook rozszerzony o `MultiSellExplorationData`,
  - reset domeny i snapshot diagnostyczny dzialaja teraz tak samo jak dla `SellExplorationData`.

3) WYSOKIE - playerdb ingest/cashin history nie obejmuje `MultiSellExplorationData` `[x]`
- pliki:
  - `logic/event_handler.py` (whitelist ingest Journal -> playerdb),
  - `logic/player_local_db.py` (`ingest_journal_event`, `_cashin_service_for_event`).
- efekt:
  - brak wpisu cash-in UC dla MultiSell w local DB,
  - niespojnosc telemetryczna miedzy runtime valuation a historia playerdb/mapy.
- wdrozenie (2026-02-28):
  - `logic/event_handler.py`: journal->playerdb whitelist zawiera `MultiSellExplorationData`,
  - `logic/player_local_db.py`: `_cashin_service_for_event` mapuje `MultiSellExplorationData` -> `UC`,
  - `logic/player_local_db.py`: `ingest_journal_event` akceptuje `MultiSellExplorationData`.

4) SREDNIE - high-value breakdown w summary moze byc nieaktualny po DSS upgrade `[x]`
- plik: `logic/system_value_engine.py`
  - `analyze_dss_scan_complete_event(...)` poprawia `c_cartography` / bonus,
  - ale nie aktualizuje wpisu `high_value_targets` dla ciala.
- efekt:
  - total systemu po DSS jest poprawiony,
  - ale breakdown ELW/WW/HMC w summary moze zostac na starej wartosci.
- wdrozenie (2026-02-28):
  - `logic/system_value_engine.py`:
    - `high_value_targets` zmienione na `upsert` po `Scan` (brak duplikatow),
    - `analyze_dss_scan_complete_event(...)` odswieza `estimated_value` targetu po upgrade FSS->DSS.

5) SREDNIE - reset po sprzedazy jest globalny po domenie, nie scoped do systemow z eventu `[x]`
- plik: `logic/event_handler.py` + `logic/system_value_engine.py`
  - `clear_value_domain(domain=...)` wywolywany bez `system_name` -> czysci cala domene runtime.
- efekt:
  - w scenariuszach czesciowej sprzedazy mozliwe zanizenie pozostalej wartosci (nadmierny reset).
  - uwaga: to kompromis "safe reset" vs precyzyjne mapowanie systemow sprzedanych.
- decyzja i wdrozenie (2026-02-28):
  - strategia hybrydowa:
    - dla `MultiSellExplorationData` z lista `Discovered` resetujemy runtime cartography tylko dla wskazanych systemow,
    - gdy lista jest pusta/niekompletna -> fallback do global reset (zachowanie bezpieczne jak dotad),
  - wdrozone zarowno w runtime (`logic/event_handler.py`), jak i w recovery (`logic/events/exploration_value_recovery.py`).

6) NISKIE - diagnostyka sell snapshot pomija `MultiSellExplorationData` `[x]`
- plik: `logic/event_handler.py` (`_log_sell_value_snapshot`)
- brak wpisu diagnostycznego dla MultiSell utrudnia szybka analize rozjazdu "przed/po sell".
- wdrozenie (2026-02-28):
  - `_log_sell_value_snapshot` rozszerzony o `MultiSellExplorationData`.

Dodatkowe obserwacje z audytu:
- gate FSS dla auto summary (arming/flush) jest logicznie uszczelniony wzgledem `AutoScan/NavBeaconDetail` i unknown `ScanType` (safe default non-manual).
- glowne zrodla rozjazdu kwot to nie gate FSS, tylko valuation + sell reset/ingest.

Priorytet napraw (kolejnosc wdrozenia):
1. P0 `[x]`: odciecie belt/ring od valuation planetarnego (`Scan` bez `PlanetClass`/`StarType` nie moze wpasc do `Planet Type`).
2. P0 `[x]`: runtime reset dla `MultiSellExplorationData` (tak jak `SellExplorationData`).
3. P0 `[x]`: playerdb ingest + cashin history dla `MultiSellExplorationData`.
4. P1 `[x]`: aktualizacja `high_value_targets` po DSS upgrade.
5. P1 `[x]`: decyzja produktowa dla partial sell scope (global reset vs reset tylko listy `Discovered` z MultiSell).
6. P2 `[x]`: rozszerzenie snapshot/diag logow o `MultiSellExplorationData`.

Checklist retestu po fixach:
1. Zrob skany FSS/DSS + exobio w kilku systemach, zanotuj saldo przed sprzedaza.
2. Sprzedaj przez `MultiSellExplorationData` (UC) i `SellOrganicData` (Vista).
3. Zweryfikuj:
   - runtime `system_value_engine.calculate_totals()` po sprzedazy,
   - summary/cash-in payload (`cash_in_system_estimated`, `cash_in_session_estimated`),
   - wpisy `cashin_history` w playerdb.
4. Potwierdz brak naliczania belt/ring jako planet (`Scan` bez klasy nie podnosi cartography).

Status:
- audit wykonany, findings potwierdzone kodem i danymi z Journal,
- wszystkie punkty 1-6 wdrozone (runtime + recovery + testy regresyjne),
- 16.75 zamkniete.

---

### 16.76 Safe patch: `fuel startup false-positive` + `FSS summary trace hardening` `[~]`
Cel:
- naprawic dwa realne problemy bez dokladania nowego globalnego stanu w `event_handler`:
  1) sporadyczne falszywe alerty `MSG.FUEL_CRITICAL` przy starcie/niestabilnej probce `Status.json`,
  2) trudna diagnostyka, dlaczego i kiedy auto `exploration summary` zostaje uzbrojone/wyemitowane.

Zakres patcha (bez zmian ryzykownych):
- NIE dodajemy globalnej flagi `_scanned_in_current_system` w `logic/event_handler.py`.
- NIE warunkujemy flusha summary nowym polem `_renata_scanned_in_system` w `navigation_events`.
- NIE duplikujemy `flush_pending_exit_summary_on_jump(...)` w `navigation_events`.

#### A) Fuel: startup/transient guard (warstwa `logic/events/fuel_events.py`) `[x]`
Problem:
- przy niestabilnym starcie (`FuelMain` chwilowo 0 / brak pojemnosci / niejednoznaczna probka) moze pasc alert krytyczny mimo braku realnego low-fuel.

Bezpieczny fix:
1. wzmocnic "no-decision" dla probek niejednoznacznych:
   - gdy `low_fuel_flag == False` i jednoczesnie:
     - brak wiarygodnej pojemnosci (`FuelCapacity.Main <= 0` lub brak),
     - oraz `FuelMain` nie daje pewnej interpretacji (None / 0 startup / semantycznie niejednoznaczne),
   => reset pending i `return` (bez alertu).
2. utrzymac/utwardzic dwu-probkowe potwierdzenie dla przypadkow flag-only i uncertain.
3. dodac throttlowany diag log dla odrzuconej probki startup:
   - `fuel_startup_uncertain_sample_ignored`.

Akceptacja:
- brak `MSG.FUEL_CRITICAL` przy losowych startup probkach bez pewnych danych,
- alert pojawia sie nadal przy realnym low fuel (2 spójne probki lub pewna flaga gry).

Wdrozone:
- `logic/events/fuel_events.py`:
  - dodano centralny reset pending confirm (`_reset_low_fuel_pending_confirmation`),
  - dodano throttled diagnostyke ignorowanych probek startup (`fuel_startup_uncertain_sample_ignored:*`),
  - dodano no-decision early return dla `FuelMain=None` + brak pojemnosci + brak flagi low-fuel,
  - startup transient `FuelMain==0` bez pojemnosci teraz jawnie resetuje pending i loguje powod.
- `tests/test_f23_fuel_warning_transient_hardening.py`:
  - nowy regresyjny test `missing_fuel_and_capacity...` (brak alertu + reset stalego pending).

#### B) FSS summary + milestone progress hardening (warstwa `exploration_fss_events` + `event_handler` + `navigation_events`) `[x]`
Problem:
- core gate jest poprawny (`FSS_PENDING_EXIT_SUMMARY`), ale przy incydentach trudno odtworzyc przyczyne uzbrojenia/flusha.
- komunikat `exit summary` pojawiał się po dolocie (na `FSDJump`), a oczekiwany timing to przed skokiem (`StartJump`).
- progi FSS (25/50/75) potrafiły zbyt wcześnie "eskalować" przez postęp niemanuany/auto-feed.

Wdrożone:
1. Utrzymana bramka armingu summary:
   - wymagane: `FSSDiscoveryScan` + co najmniej jeden manualny scan (`ScanType=detailed`) + full closure (`FSS_DISCOVERED >= FSS_TOTAL_BODIES`).
2. Timing summary przeniesiony na `StartJump`:
   - `logic/event_handler.py`: `StartJump` flushuje uzbrojony pending summary przed skokiem.
   - `logic/events/navigation_events.py`: usunięty fallback flush na `FSDJump/CarrierJump` (żeby nie mówić po dolocie).
3. Hardening progów FSS:
   - dodany licznik `FSS_DISCOVERED_MANUAL`,
   - milestone 25/50/75 i "ostatnia planeta" liczone z progresu manualnego (preferowany), z fallbackiem kompatybilnym dla istniejących scenariuszy/testów.
4. Rozszerzona diagnostyka armingu:
   - `exit_summary_armed` zawiera również `discovered_manual`.

Akceptacja:
- `exit summary` pojawia się na `StartJump` (przed skokiem), nie po dolocie.
- brak fałszywych progów 75% przy niskim manualnym postępie.
- brak regresji gate’ów F30/F24/F60.

#### D) StartJump cash-in: wygaszenie auto-calloutu (warstwa `event_handler`) `[x]`
Cel:
- wyłączyć automatyczny `MSG.CASH_IN_STARTJUMP` podczas skoku i zostawić auto-voice tylko dla `exit summary`.

Wdrożone:
- `logic/event_handler.py`:
  - pozostawiony tylko `flush_pending_exit_summary_on_jump(...)` na `StartJump`,
  - usunięty routing `StartJump -> trigger_startjump_cash_in_callout(...)`.
- efekt runtime:
  - `startjump + uzbrojony FSS pending summary` -> tylko summary przed skokiem,
  - brak auto `MSG.CASH_IN_STARTJUMP` podczas normalnego skoku.

#### C) MainLoop/handler.log_dir (out-of-scope fix) `[x]`
Ocena:
- przenoszenie `handler.log_dir` przed watchery nie adresuje root cause `fuel critical`,
- watchery korzystaja z `status_path()/market_path()` i nie zależą od `handler.log_dir`.

Decyzja:
- nie wdrażac jako fix paliwa.

Testy regresyjne do dodania:
1. `tests/test_fuel_startup_uncertain_samples_do_not_trigger_critical.py`
   - startup sample uncertain -> brak alertu,
   - dwa pewne low-fuel sample -> alert.
2. `tests/test_fss_exit_summary_flush_trace_contract.py`
   - pending False -> flush skipped + trace,
   - pending True -> single emit + clear pending + trace.
3. `tests/test_fss_non_scan_events_do_not_arm_summary.py`
   - `ScanOrganic`/`CodexEntry`/`SAAScanComplete` bez FSS gate -> brak arming.

Status:
- patch wdrożony kodowo (A/B/D),
- testy regresyjne F30/F24/F60/F11: PASS.

### 16.77 Stabilizacja release: `StartJump exit-summary only` + `mojibake hygiene` `[ ]`
Kontekst:
- obecnie runtime nadal potrafi emitować `MSG.CASH_IN_STARTJUMP` przy skokach bez realnego FSS workflow,
- po kolejnych zmianach wracają krzaki diakrytyczne (mojibake) w części komunikatów,
- cel release: jeden spójny mechanizm auto-podsumowania na `StartJump`, bez duplikatów i bez regresji.

Decyzje funkcjonalne (zamrożenie zakresu):
- auto-podsumowanie w locie ma być tylko jedno: `exit summary`,
- trigger auto-podsumowania: tylko `StartJump`,
- `cash-in` zostaje wyłącznie do ręcznego użycia z panelu (`Pulpit`), bez auto-calloutu na `StartJump`.

DoD:
- `exit summary` uzbraja się tylko gdy spełnione są oba warunki:
  - `FSSDiscoveryScan` w bieżącym systemie,
  - minimum jeden manualny scan (`ScanType=detailed`) w bieżącym systemie.
- auto-emisja podsumowania występuje tylko na `StartJump` i tylko raz na uzbrojenie.
- `MSG.CASH_IN_STARTJUMP` nie emituje się automatycznie podczas skoku.
- liczenie progresu FSS i progów 25/50/75 opiera się o realny licznik ciał gry (`Bodies N/*`) i manualnie zaliczone ciała:
  - progres ma działać poprawnie dla małych i dużych systemów,
  - brak wpływu `Signals Detected` na milestone body-progress.
- teksty TTS mają poprawne polskie znaki (brak `sÄ…`, `zarobiĹ‚eĹ›`, `Ĺ‚Ä…cznie` itp.).
- brak regresji na pozostałych funkcjach (navigation/fuel/map/trade).

Zakres kodu do przeglądu i zmian:
- `logic/events/exploration_fss_events.py`
- `logic/event_handler.py`
- `logic/events/navigation_events.py`
- `logic/events/exploration_summary.py`
- `logic/events/cash_in_assistant.py`
- `logic/tts/text_preprocessor.py`

Plan wykonania (bez „łatania na ślepo”):
- krok 1: usunięcie auto `MSG.CASH_IN_STARTJUMP` z routera i potwierdzenie, że manualny cash-in w panelu działa,
- krok 2: finalne spięcie `exit summary` tylko na `StartJump` z jednym źródłem uzbrojenia,
- krok 3: twarda korekta mojibake w źródłowych stringach + testy regresyjne diakrytyki,
- krok 4: testy kontraktowe FSS (matryca ScanType + body-count) i smoke pod release.

Status wdrożenia:
- krok 1: `[x]` auto `MSG.CASH_IN_STARTJUMP` usunięty z routera `StartJump`,
- krok 3 (zakres `cash_in_assistant`): `[x]` poprawione źródłowe stringi mojibake dla runtime TTS cash-in/startjump,
- testy: `[x]` F11/F28/F30/F32 PASS po zmianach.

### 16.77 Mapa: Trade compare tylko dla wybranego systemu/stacji + kompakt kolumn `[x]`
Problem:
- po zmianach F31 do `Trade compare` wrocily kolumny `System`/`Stacja`,
- compare pobieral globalny top z calego playerdb (wiele systemow), zamiast scope z panelu `System details`.

Wdrozone:
- `gui/tabs/journal_map.py`:
  - usuniete kolumny `System` i `Stacja` z tabeli `Trade compare`,
  - nowa bramka `_trade_compare_scope_from_selection()`:
    - scope pobierany z aktualnie wybranej stacji/systemu w panelu `System details`,
  - `_run_trade_compare(...)` i `_run_trade_compare_multi(...)`:
    - zapytania idą tylko w scope wybranego systemu/stacji,
    - bez wybranego scope compare zwraca czytelny komunikat i nie pobiera globalnych danych.
- `logic/personal_map_data_provider.py`:
  - `get_top_prices(...)` dostal filtry:
    - `system_name`,
    - `station_market_id`,
    - `station_name` (fallback gdy brak market id).

Testy:
- zaktualizowane quality gates:
  - `tests/test_f31_map_trade_compare_provenance_and_clear_contract.py`,
  - `tests/test_f31_quality_gates_and_smoke.py`.

Efekt:
- `Trade compare` pokazuje ceny tylko dla stacji/systemu wybranego w panelu po prawej,
- tabela jest znowu kompaktowa (bez redundantnych kolumn).

### 16.78 FSS milestones: filtracja `Belt Cluster`/`Barycentre` + spójny licznik progów `[x]`
Problem:
- progi FSS 25/50/75 potrafiły wyzwalać się zbyt wcześnie względem in-game `Bodies N/*`,
- do licznika progresu wpadały również wpisy `Scan` dla `... Belt Cluster ...` (pas asteroid),
- po restarcie Renaty bootstrap mógł odtworzyć zawyżony progres z tych samych wpisów.

Root cause:
- `handle_scan(...)` podbijał `FSS_DISCOVERED` dla każdego nowego `BodyName/BodyID`,
- `bootstrap_fss_state_from_journal_lines(...)` odtwarzał licznik analogicznie, bez filtracji artefaktów,
- milestone używały ścieżki z preferencją licznika manualnego, co utrudniało spójność z HUD `Bodies`.

Wdrożone:
1. `logic/events/exploration_fss_events.py`
   - dodana funkcja `_is_real_celestial_body(ev)`:
     - odrzuca `Belt Cluster`,
     - odrzuca `Barycentre/Barycenter`.
2. Runtime FSS:
   - `handle_scan(...)` dostaje wczesny guard:
     - jeśli obiekt nie jest realnym ciałem niebieskim -> event nie podbija progresu FSS.
3. Bootstrap FSS:
   - `bootstrap_fss_state_from_journal_lines(...)` używa tej samej filtracji,
   - po restarcie nie wraca zawyżony licznik z belt-clusterów.
4. Milestones:
   - `_progress_count_for_thresholds()` ujednolicony do `FSS_DISCOVERED`,
   - progi 25/50/75 opierają się o jeden, przefiltrowany licznik względem `FSS_TOTAL_BODIES`.

Testy:
- `tests/test_f30_fss_milestone_catchup_and_body_dedupe.py`
  - nowy regres: `test_handle_scan_ignores_belt_cluster_from_fss_progress`.
- `tests/test_f60_bootstrap_fss_state_recovery.py`
  - nowy regres: `test_bootstrap_ignores_belt_cluster_entries_in_discovered_counter`.

Efekt:
- milestone FSS są bliżej semantyki in-game `Bodies N/*`,
- brak sztucznego przyrostu progresu przez pasy asteroid i barycentra,
- runtime + bootstrap mają spójną regułę liczenia.
- weryfikacja regresji (2026-03-01): `test_f30_*`, `test_f60_*`, `test_f24_*` PASS.

### 16.79 FSS: Nav Beacon / pasywny skan / nowe komunikaty `[~]`
Cel:
- dodać czytelne komunikaty dla scenariusza pasywnego skanowania (`NavBeaconDetail` / `AutoScan`) bez naruszania gate’u `exit summary`.

Zakres docelowy:
1. Nav Beacon + AutoScan:
   - Renata nie milczy, gdy system „wpada” pasywnie.
2. FSSDiscoveryScan late catch-up:
   - utrzymanie spójnej synchronizacji bez spamu.
3. FSSAllBodiesFound:
   - soft-sygnał, bez przedwczesnego full-scan.
4. Filtr belt/barycentre:
   - już wdrożony w 16.78 (runtime + bootstrap).
5. High-value DSS:
   - per body, niezależnie od wcześniejszego odkrycia.
6. Exit summary:
   - auto tylko na `StartJump`.

Etap 1 (wdrożony):
- `logic/events/exploration_fss_events.py`:
  - dodana ścieżka pasywna:
    - `_is_passive_progress_scan(...)`,
    - `_maybe_emit_passive_scan_callouts(...)`,
  - nowe flagi runtime:
    - `FSS_PASSIVE_DATA_WARNED`,
    - `FSS_PASSIVE_FULL_WARNED`,
  - reset flag w `reset_fss_progress(...)`,
  - przy `Scan` niemanuanym:
    - emit `MSG.FSS_PASSIVE_DATA_INGESTED`,
    - emit `MSG.FSS_PASSIVE_SYSTEM_COMPLETE` gdy pasywne pokrycie dojdzie do `N/N`.
- `logic/tts/message_templates.py`:
  - dodane template’y:
    - `MSG.FSS_PASSIVE_DATA_INGESTED`,
    - `MSG.FSS_PASSIVE_SYSTEM_COMPLETE`.
- `logic/event_insight_mapping.py`:
  - dodane klasy insight + polityka TTS dla ww. message_id.

Ważne:
- gate auto `exit summary` nie został poluzowany:
  - nadal wymagane `FSSDiscoveryScan + min. 1 manual Detailed + full closure`.

Etap 2 (wdrożony):
- `logic/events/exploration_fss_events.py`:
  - late `FSSDiscoveryScan` (`previous_total <= 0` i `discovered_now > 0`) emituje nowy komunikat synchronizacji:
    - `MSG.FSS_BODYCOUNT_SYNCED`.
- `logic/tts/message_templates.py`:
  - dodany template `MSG.FSS_BODYCOUNT_SYNCED`.
- `logic/event_insight_mapping.py`:
  - dodana klasa insight + TTS policy dla `MSG.FSS_BODYCOUNT_SYNCED`.
- testy:
  - `tests/test_f30_fss_milestone_catchup_and_body_dedupe.py`:
    - `test_late_bodycount_emits_sync_callout`.

Etap 3 (wdrożony):
- `logic/events/exploration_fss_events.py`:
  - `FSSAllBodiesFound` dla częściowego postępu nie emituje full-scan,
  - dodany soft-komunikat:
    - `MSG.FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY`
      („sygnały FSS kompletne, ale brak jeszcze pełnych danych części ciał”),
  - brak uzbrojenia `exit summary` w tym scenariuszu.
- `logic/tts/message_templates.py`:
  - dodany template `MSG.FSS_SIGNALS_COMPLETE_PENDING_CLASSIFY`.
- `logic/event_insight_mapping.py`:
  - dodana klasa insight + TTS policy dla ww. komunikatu.
- testy:
  - `tests/test_f24_fss_all_bodies_found_does_not_force_full_scan.py`:
    - scenariusze partial teraz oczekują `pending classify` zamiast ciszy,
    - nowy regres: `test_all_bodies_found_partial_emits_pending_only_once`.

Etap 4 (wdrożony):
- `logic/events/exploration_fss_events.py`:
  - `check_high_value_planet(...)` przeniesiony przed deduplikację `already_counted`,
  - high-value hint może zadziałać także na follow-up `Detailed` dla ciała, które wcześniej wpadło pasywnie (`AutoScan`/`NavBeaconDetail`).
- testy:
  - `tests/test_f30_fss_milestone_catchup_and_body_dedupe.py`:
    - nowy regres: `test_handle_scan_runs_high_value_check_for_followup_detailed_on_same_body`.

### 16.80 UX/Runtime hardening: `FSS gate passive`, `fuel init`, `high-value per body`, `nav fallback`, `FSS TTL` `[x]`
Cel:
- domknąć błędy responsywności i spójności runtime bez rozszerzania zakresu funkcjonalnego.

Zakres:
1. FSS/Summary Gate (passive full):
   - poluzowanie gate `FSS_PENDING_EXIT_SUMMARY`,
   - jeśli `FSS_DISCOVERED == FSS_TOTAL_BODIES` przez passive ingest, arming summary dozwolony także bez manual `Detailed`.
2. Fuel initialization:
   - usunięcie 8s okna potwierdzenia (`LOW_FUEL_FLAG_CONFIRM_WINDOW_SEC`),
   - ignorowanie próbek `FuelMain=0.0` tylko do momentu pierwszej poprawnej próbki `FuelMain > 0` po starcie/resecie,
   - po inicjalizacji reakcja natychmiastowa (bez wielosekundowego pending).
3. High-value dedupe:
   - odejście od globalnych flag per typ (`HV_*_WARNED`),
   - dedupe po unikalnym ciele (`BodyID` / fallback `BodyName`) w obrębie sesji,
   - runtime hint DSS jako `MSG.HIGH_VALUE_DSS_HINT`.
4. Navigation fallback:
   - usunięcie twardego wyjścia przy aktywnej trasie Spansha,
   - równoległy fallback awareness z `NavRoute` gdy Spansh jest niekompletny albo oznaczony off-route.
5. Message TTL:
   - milestone FSS 25/50/75 dostają TTL kolejki TTS = 20s,
   - przeterminowane milestone nie są odczytywane (uniknięcie starych progów przy szybkim skanowaniu).

Wdrożone:
- `logic/events/exploration_fss_events.py`
  - gate `exit summary` dopuszcza passive full ingest (`FSS_PASSIVE_FULL_WARNED`) przy `N/N`,
  - passive full path uzbraja pending summary (`trigger_source=passive_ingest`),
  - milestone 25/50/75 przekazują do TTS `tts_max_queue_age_sec=20.0`.
- `logic/events/fuel_events.py`
  - usunięta logika 8s confirm-window,
  - dodany runtime state `_FUEL_SEEN_VALID_SAMPLE`,
  - `FuelMain=0.0` bez capacity jest ignorowane tylko do pierwszej poprawnej próbki `>0`,
  - po inicjalizacji alert low-fuel działa natychmiast.
- `logic/events/exploration_high_value_events.py`
  - usunięte globalne flagi `HV_*_WARNED`,
  - dedupe per body (`HV_SCANNED_BODIES`),
  - unified komunikat runtime: `MSG.HIGH_VALUE_DSS_HINT`.
- `logic/events/navigation_events.py`
  - brak twardego short-circuit przy aktywnym Spanshu,
  - fallback awareness z NavRoute działa, gdy Spansh jest niekompletny lub off-route.
- `logic/utils/notify.py`
  - kolejka TTS wspiera TTL per-item (`max_queue_age_sec` + `enqueued_monotonic`),
  - worker odrzuca przeterminowane wpisy.
- `logic/event_insight_mapping.py`
  - dodana klasyfikacja + policy dla `MSG.HIGH_VALUE_DSS_HINT`.
- `logic/tts/message_templates.py`
  - dodany template `MSG.HIGH_VALUE_DSS_HINT`.
- `logic/events/exploration_awareness.py`
  - `MSG.HIGH_VALUE_DSS_HINT` dodany do required exploration callouts.

Regresja (PASS):
- `tests.test_f30_exploration_summary_after_jump_fss_gate`
- `tests.test_f30_fss_summary_scan_type_matrix`
- `tests.test_f30_fss_milestone_catchup_and_body_dedupe`
- `tests.test_f24_fss_all_bodies_found_does_not_force_full_scan`
- `tests.test_f23_fuel_warning_transient_hardening`
- `tests.test_f23_quality_gates_and_smoke`
- `tests.test_route_awareness_state`
- `tests.test_f62_tts_fss_priority_and_coalescing`
- `tests.test_f3_quality_gates_and_smoke`
- `tests.test_event_insight_mapping`
- `tests.test_f30_high_value_dedupe_per_body` (nowy)

### 16.81 UC/VISTA precision model: `MassEM formula`, `First Logged 5x`, `summary split` `[~]`
Cel:
- zmniejszyć rozjazd pomiedzy estymata Renaty a wyplata w grze,
- przejsc z tabel statycznych na runtime formula tam, gdzie Journal daje dane (MassEM),
- wyraznie oddzielic "Estimated Value" od "Potential First Logged Bonus".

Wdrozone:
1. `logic/system_value_engine.py`
   - dodana dynamiczna formula UC:
     - `V = k + (k * q * m**0.2)`,
     - stale dla glownych klas: `ELW`, `WW`, `AW`, `HMC`, `Rocky`,
   - mnozniki:
     - first discovery `x2.6`,
     - first mapped `x3.7`,
     - efficiency `x1.25` gdy `ProbesUsed <= EfficiencyTarget`,
   - fallback:
     - gdy brak `MassEM` lub brak parametrow klasy -> stara sciezka z arkusza `Cartography`,
   - exobio first logged:
     - `SystemStats.has_first_footfall_opportunity`,
     - `SystemStats.potential_first_logged_bonus`,
     - per-body multipliers (`exobio_body_multipliers`) i first-footfall tracking.
2. `logic/exit_summary.py`
   - `ExitSummaryData` rozszerzony o:
     - `potential_first_logged_bonus`,
     - `has_first_footfall_opportunity`.
3. `logic/events/exploration_summary.py`
   - payload zawiera `potential_first_logged_bonus_estimated`,
   - TTS summary rozdziela:
     - "Szacowana wartość"
     - "Potencjalny bonus first logged" (gdy > 0).
4. `logic/events/exploration_bio_events.py`
   - nowy callout runtime `MSG.HIGH_VALUE_FIRST_LOGGED_ALERT` (dedupe per `(system, body)`).
5. `logic/event_insight_mapping.py` + `logic/tts/message_templates.py` + `logic/events/exploration_awareness.py`
   - dodane mapowanie/policy/template/required-callout dla `MSG.HIGH_VALUE_FIRST_LOGGED_ALERT`.
6. `logic/generate_renata_science_data.py`
   - arkusz `Cartography` oznaczony jako fallback (`Runtime_Priority=fallback_wiki`),
   - dopisane kolumny informacyjne `Formula_k`, `Formula_q`.

Regresja/testy do uruchomienia po wdrozeniu:
- `tests.test_system_value_engine`
- `tests.test_f4_exploration_summary_base`
- `tests.test_event_insight_mapping`
- `tests.test_f30_exploration_summary_after_jump_fss_gate`

Status:
- `[~]` implementacja kodu gotowa,
- `[ ]` finalne strojenie stalej mapy `k/q` pod walidacje gameplay (target <=1% rozjazdu).

### 16.82 Cash-In station candidates: `Collect then Rank` + profile cleanup `[ ]`
Cel:
- usunac blad logiczny, w ktorym pierwsze trafione zrodlo (offline DB) blokuje lepsze/swiezsze kandydaty,
- przejsc na model globalnego rankingu: najpierw zbierz wszystko, potem deduplikuj i sortuj,
- przygotowac payload pod clipboard assist (system celu gotowy do przekazania).

Diagnoza:
- obecny flow w cash-in potrafi faworyzowac `offline_station_index` tylko dlatego, ze zwrocil wynik jako pierwszy,
- lokalne dane Spansha/EDSM nie zawsze sa rankowane razem z offline/provider bridge,
- profile tras numerowane (`1/2/3`) utrudniaja semantyke runtime i utrzymanie.

Zakres zmian:
1. `logic/cash_in_station_candidates.py`
   - przebudowa orchestratora do modelu `collect -> normalize -> dedupe -> rank`,
   - bez short-circuit po pierwszym providerze,
   - agregacja kandydatow z:
     - `station_candidates_from_offline_index(...)`,
     - lokalnych dumpow Spansh (`.json` user supplied),
     - EDSM/playerdb provider bridge (wg dostepnosci runtime),
   - wspolny kontrakt rekordu:
     - `system_name`, `station_name`, `distance_ly`, `distance_ls`, `services`, `source`, `freshness_ts`.
2. Globalne dedupe i ranking:
   - dedupe po kluczu stacji (`system_name + station_name` lub `market_id` gdy dostepny),
   - preferencja rekordu:
     - nowszy `freshness_ts`,
     - przy remisie: `SPANSH/EDSM` nad starym offline,
   - finalne sortowanie:
     - `distance_ly ASC`, potem `distance_ls ASC`.
3. Profile routing (czytelne nazwy):
   - zastapienie modelu `1/2/3` staly mi profilami:
     - `NEAREST`,
     - `SECURE_PORT`,
     - `CARRIER_FRIENDLY`,
   - migracja uzyc w:
     - `logic/events/cash_in_assistant.py`,
     - `logic/events/exploration_summary.py`.
4. Clipboard readiness:
   - rozszerzenie `CashInAssistantPayload` o `target_system_name`,
   - zapewnienie, ze `MSG.CASH_IN_ASSISTANT` ma gotowy `target_system_name` w context (pod handoff do schowka/next-hop).

Akceptacja / DoD:
- Renata wybiera realnie najblizsza stacje po rankingu globalnym, niezaleznie od zrodla danych.
- Brak regresji fallbacku offline (dziala tylko gdy nic lepszego nie istnieje).
- Runtime i UI nie pokazuja numerow profili, tylko nazwy funkcjonalne.
- Payload/callout ma jawne `target_system_name` do integracji clipboard assist.

Plan wdrozenia:
- Etap A: orchestrator collect-then-rank + dedupe/rank.
- Etap B: profile naming migration (`1/2/3` -> stale semantyczne).
- Etap C: payload `target_system_name` + wiring insight context.
- Etap D: testy regresyjne + smoke scenariuszy mixed-source (offline + spansh + edsm).
