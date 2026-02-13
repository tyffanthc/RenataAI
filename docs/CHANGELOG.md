# CHANGELOG.md

Ostatnia aktualizacja: 2026-02-13
Zakres: zmiany z sekcji `## Zmiany do dokumentacji w update v0.9.4!`
w `docs/internal/LAST_TICKET.MD`.

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
