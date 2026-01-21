# RenataAI UX/UI Backlog

## Done (recent)
- C1: Column Picker (flagged, persistence).
- C2: Treeview renderer + sort (Neutron + Trade).
- C2.1: Treeview UX polish (LP, alignment, sort indicator).
- C3: Treeview rollout (Ammonia/ELW/HMC/Exomastery/Riches) + LP everywhere.
- C4: Treeview UX polish (no separators, header alignment, hover row).
- B2: Trade Market Age slider + datetime (flagged).
- B3: Results context menu (flagged).


Każda pozycja: opis, pliki, ryzyko, test, flaga.

## Quick wins (1–2h)
- QW-01 (P1): Ujednolicić język i nazewnictwo etykiet w Spansh; Files: `gui/tabs/spansh/neutron.py`, `gui/tabs/spansh/riches.py`, `gui/tabs/spansh/ammonia.py`, `gui/tabs/spansh/elw.py`, `gui/tabs/spansh/hmc.py`, `gui/tabs/spansh/exomastery.py`; Risk: low; Test: manualne przejście po tabach; Flag: no.
- QW-02 (P1): Dodać wizualne oznaczenie pól wymaganych (np. Station w Trade); Files: `gui/tabs/spansh/trade.py`; Risk: low; Test: sprawdź walidację i komunikaty; Flag: no.
- QW-03 (P1): Wyłączyć/ukryć placeholdery tabów lub dodać “disabled” + opis; Files: `gui/tabs/spansh/__init__.py`, `gui/app.py`; Risk: low; Test: sprawdź listę zakładek; Flag: no.
- QW-04 (P2): Dodać prosty status „Liczenie…” + disable button w każdej zakładce; Files: `app/route_manager.py`, `gui/tabs/spansh/*`; Risk: low; Test: klik „Wyznacz” i obserwuj UI; Flag: no.
- QW-05 (P2): Ujednolicić padding i szerokości pól formularzy; Files: `gui/tabs/spansh/*`, `gui/tabs/pulpit.py`; Risk: low; Test: wizualny przegląd UI; Flag: no.
- QW-06 (P2): Dodać Enter jako skrót uruchomienia obliczeń w tabach; Files: `gui/tabs/spansh/*`; Risk: low; Test: Enter w polu wejściowym; Flag: no.
- QW-07 (P2): Usunąć „debug printy” z UI lub związać z flagą; Files: `gui/app.py`, `gui/tabs/spansh/trade.py`; Risk: low; Test: uruchomienie GUI bez spamowania konsoli; Flag: `debug_ui` (nowa).
- QW-08 (P2): Dodać krótki opis pól (tooltip/label hint) dla DTA/Radius/Max hops; Files: `gui/tabs/spansh/*`; Risk: low; Test: sprawdź opis w UI; Flag: no.
- QW-09 (P2): Ujednolicić nazwy i format jednostek (LY/ls) w labelach; Files: `gui/tabs/spansh/*`; Risk: low; Test: przegląd etykiet; Flag: no.
- QW-10 (P3): Wymusić schemat tabel (i ukryć fallback list) gdy `features.tables.*` włączone; Files: `gui/common.py`; Risk: low; Test: wyniki w tabelach; Flag: no.
- QW-11 (P3): Dodać przycisk „Kopiuj trasę” obok listy wyników; Files: `gui/common.py`, `gui/tabs/spansh/*`; Risk: low; Test: ręczne kopiowanie; Flag: no.
- QW-12 (P3): Dodać krótkie „empty state” w listach wyników; Files: `gui/common.py`; Risk: low; Test: brak wyników; Flag: no.
- QW-13 (P3): Ujednolicić style dla tk.Listbox i tk.Button (kolory, font); Files: `gui/app.py`, `gui/common.py`, `gui/tabs/logbook.py`; Risk: low; Test: wizualny przegląd; Flag: no.
- QW-14 (P3): Dodać ostrzeżenie o braku pliku `renata_science_data.xlsx` na Pulpicie; Files: `gui/tabs/pulpit.py`, `gui/app.py`; Risk: low; Test: bez pliku; Flag: no.
- QW-15 (P3): Wpiąć flagi asystentów do logiki (fss/bio/high_value/smuggler); Files: `logic/events/exploration_fss_events.py`, `logic/events/exploration_bio_events.py`, `logic/events/exploration_high_value_events.py`, `logic/events/smuggler_events.py`; Risk: low; Test: smoke tests + manual; Flag: no.

## Średnie (0.5–2 dni)
- M-01 [DONE] (P1): Dodać UI do wyboru kolumn tabel (column picker); Files: `gui/common.py`, `gui/tabs/settings.py`, `gui/table_schemas.py`; Risk: medium; Test: wybór kolumn i rendering; Flag: `features.tables.column_picker_enabled`.
- M-02 [DONE] (P1): Zastąpić Listbox na Treeview z sortowaniem dla wyników tras; Files: `gui/common.py`, `gui/tabs/spansh/*`, `gui/table_schemas.py`; Risk: medium; Test: sortowanie i copy; Flag: `features.tables.treeview_enabled`.
- M-03 [DONE] (P1): Centralny wskaźnik „busy” + blokada wielokrotnego clicka; Files: `app/route_manager.py`, `gui/app.py`, `gui/tabs/spansh/*`; Risk: medium; Test: szybkie kliknięcia; Flag: no.
- M-04 (P2): Dodać panel błędów i ostatniego zapytania SPANSH (HTTP status/job id); Files: `logic/spansh_client.py`, `gui/tabs/spansh/*`; Risk: medium; Test: celowe błędy; Flag: no.
- M-05 (P2): Przepisanie layoutów Spansh do jednolitej siatki (grid/columns); Files: `gui/tabs/spansh/*`; Risk: medium; Test: porównanie layoutów; Flag: no.
- M-06 (P2): Zapisywanie rozmiaru okna + ostatniej zakładki w config; Files: `gui/app.py`, `config.py`; Risk: medium; Test: restart app; Flag: no.
- M-07 (P2): Auto‑detekcja log_dir w Settings (obecnie disabled); Files: `gui/tabs/settings.py`, `config.py`; Risk: medium; Test: ustawienie ścieżki; Flag: no.
- M-08 (P3): Dodanie wyszukiwarki w Settings; Files: `gui/tabs/settings.py`; Risk: medium; Test: filtr opcji; Flag: no.
- M-09 (P3): Dodanie wyszukiwarki/filtru w Logbook; Files: `gui/tabs/logbook.py`, `logic/logbook_manager.py`; Risk: medium; Test: filtr wpisów; Flag: no.
- M-10 (P3): Lepsza obsługa „rate limit” w autocomplete (cancel old requests); Files: `gui/common_autocomplete.py`, `logic/spansh_client.py`; Risk: medium; Test: szybkie wpisywanie; Flag: no.

## Duże (refaktor / nowy layout)
- L-01 (P1): Spójny redesign UI „cockpit”, ujednolicone fonty i style; Files: `gui/app.py`, `gui/tabs/*`, `gui/common.py`; Risk: high; Test: pełny smoke + manual; Flag: `features.ui.new_theme`.
- L-02 (P1): Nowy „Route Workspace” z tabelą, filtrami i panelami szczegółów; Files: `gui/common.py`, `gui/tabs/spansh/*`, `gui/table_schemas.py`; Risk: high; Test: wszystkie trasy; Flag: `features.ui.route_workspace`.
- L-03 (P2): Refaktor AppState/RouteManager (oddzielenie UI state od config.STATE); Files: `app/state.py`, `app/route_manager.py`, `config.py`, `gui/app.py`; Risk: high; Test: smoke + regression; Flag: no.
- L-04 (P2): Ujednolicenie źródeł danych i providerów (Spansh/EDSM/Inara); Files: `logic/spansh_client.py`, `logic/utils/http_spansh.py`, nowe moduły providerów; Risk: high; Test: integracyjne; Flag: `features.providers.multi`.
- L-05 (P3): Implementacja Inara/EDTools lub usunięcie stubów + flow w menu; Files: `gui/app.py`, `gui/menu_bar.py`; Risk: high; Test: manual; Flag: no.