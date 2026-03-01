# FLOW.md

Publiczny opis produktu Renata. Ten plik zawiera tylko informacje przeznaczone
do publikacji.

## Status faz (FREE/PUB)
- Ostatnia aktualizacja: 2026-03-01
- Faza 1: DONE
- Faza 2: DONE
- Faza 3: DONE
- Faza 4: DONE
- Faza 5: DONE
- Faza 6: DONE (FREE release hardening + smoke)
- Post-F6 (v0.9.5): DONE (hardening runtime, TTS i exploration bez zmiany publicznych granic produktu).

## Granica publikacji
- `docs/Flow/public` zawiera filozofie produktu, zasady UX i polityki wysokiego poziomu.
- `docs/Flow/public` nie zawiera heurystyk wewnetrznych, progow, kontraktow technicznych,
  checklist PR, planow wydaniowych PRO ani szczegolow implementacji.
- Szczegoly operacyjne sa trzymane w dokumentacji wewnetrznej i nie sa linkowane z public.

## Mapa dokumentow publicznych
- [README](README.md)
- [Data Trust and Freshness](docs/data/DATA_TRUST_AND_FRESHNESS.md)
- [UX TTS Policy](docs/ux/UX_TTS_POLICY.md)
- [UX Insight Alerts](docs/ux/UX_INSIGHT_ALERTS.md)
- [UX Decision Cards](docs/ux/UX_DECISION_CARDS.md)
- [Global Risk Policy](docs/policies/GLOBAL_RISK_POLICY.md)
- [Global Value at Risk](docs/policies/GLOBAL_VALUE_AT_RISK.md)
- [Actions (public scope)](docs/actions/README.md)
- [Refaktor Status (public)](docs/REFAKTOR_STATUS.md)

## Filozofia
- Renata nie gra za pilota i nie automatyzuje gry.
- Renata interpretuje dane i podaje wnioski, a nie rozkazy.
- Renata pokazuje Decision Space (sensowne opcje), a nie "jedyna sluszna decyzje".
- Renata mowi tylko wtedy, gdy cisza bylaby gorsza.

## Publiczny zakres funkcji
- Nawigacja i wsparcie decyzji trasy.
- Wsparcie decyzji sprzedazowych.
- Exploration awareness i komunikaty postepu eksploracji.
- Podsumowanie eksploracji oraz cash-in/survival awareness.
- Combat awareness (wzorce ryzyka, bez taktyki).
- Komunikaty insightowe i karty decyzji zgodne z politykami UX.
- Komunikacja ryzyka i VaR na poziomie zrozumialym dla pilota.

## Publiczne granice produktu
- Brak makr i brak autopilota.
- Brak sterowania statkiem przez Renate.
- Brak obietnic bez pelnych danych.
- Brak przewagi gameplayowej wynikajacej z planu PRO.
