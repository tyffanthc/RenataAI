# FLOW_MASTER.md
## Renata — Spójna Architektura (Zasady + Akcje + Cykle)

> Ten dokument jest **jednym źródłem prawdy** dla produktu Renata.
> Łączy filozofię, polityki globalne i akcje w spójny system, gotowy do implementacji i review PR.

---


## Spis treści
- [Renata — Spójna Architektura (Zasady + Akcje + Cykle)](#renata-spójna-architektura-zasady-akcje-cykle)
- [1. Filozofia (Idea Renaty)](#1-filozofia-idea-renaty)
- [2. Warstwy systemu (od dołu do góry)](#2-warstwy-systemu-od-dołu-do-góry)
  - [2.1 Dane](#21-dane)
  - [2.2 Analiza i heurystyki](#22-analiza-i-heurystyki)
  - [2.3 Wnioski (Insights)](#23-wnioski-insights)
  - [2.4 Decyzje (Decision Space)](#24-decyzje-decision-space)
  - [2.5 Ryzyko (Risk + VaR)](#25-ryzyko-risk-var)
- [3. Anti-spam (globalnie)](#3-anti-spam-globalnie)
- [4. Akcje (Actions) — katalog i rola](#4-akcje-actions-katalog-i-rola)
  - [4.1 Route Awareness & Route Intent](#41-route-awareness-route-intent)
  - [4.2 Sell Assist](#42-sell-assist)
- [5. Eksploracja — pełny lifecycle (end-to-end)](#5-eksploracja-pełny-lifecycle-end-to-end)
- [6. Przetrwanie i walka (bez taktyki)](#6-przetrwanie-i-walka-bez-taktyki)
- [7. Zasada końcowa](#7-zasada-końcowa)

---



## Mapa dokumentów
- [Polityka: Trust & Freshness](docs/data/DATA_TRUST_AND_FRESHNESS.md)
- [UX: TTS Policy](docs/ux/UX_TTS_POLICY.md)
- [UX: Insight Alerts](docs/ux/UX_INSIGHT_ALERTS.md)
- [UX: Decision Cards](docs/ux/UX_DECISION_CARDS.md)
- [Polityka: Global Risk Policy](docs/policies/GLOBAL_RISK_POLICY.md)
- [Polityka: VaR (Value at Risk)](docs/policies/GLOBAL_VALUE_AT_RISK.md)
- [Status: Refaktor](docs/REFAKTOR_STATUS.md)

- [Akcje](docs/actions)

---


## 1. Filozofia (Idea Renaty)
- Renata **nie gra za pilota** i **nie automatyzuje gry**.
- Renata **interpretuje** dane i zamienia je w **wnioski**.
- Renata tworzy **Decision Space** (2–3 sensowne opcje), a nie „Top 1”.
- Milczenie jest funkcją: **Renata mówi tylko wtedy, gdy cisza byłaby gorsza**.

**Granice:**
- brak makr i „autopilota”,
- brak rozkazów,
- brak obietnic (np. „na pewno będziesz pierwszy”), jeśli nie ma 100% danych.

---

## 2. Warstwy systemu (od dołu do góry)

### 2.1 Dane
- **Local (PRIMARY):** logi gry — prawda operacyjna.
- **External (SECONDARY):** EDSM / Inara — zmysły (opcjonalne, starzeją się).
- **Reference (TERTIARY):** wiki, `science_data.xml` — model świata (statyczny).

Wszystko przechodzi przez:
- `docs/data/DATA_TRUST_AND_FRESHNESS.md`

### 2.2 Analiza i heurystyki
- klasyfikacja wartości (tiers),
- wykrywanie okazji (bio, jackpot, first opportunities),
- liczenie distance gates (exobio).

### 2.3 Wnioski (Insights)
- **Insight Alerts:** interpretacja, nie powtórzenie HUD.
- **Planet Insight Callouts:** jednorazowe wskazanie konkretnej planety/obiektu.

Reguły mowy i spamu:
- `docs/ux/UX_TTS_POLICY.md`
- `docs/ux/UX_INSIGHT_ALERTS.md`

### 2.4 Decyzje (Decision Space)
- minimalne Decision Cards:
  - 1 pytanie, max 3 opcje, zawsze „Pomijam”

### 2.5 Ryzyko (Risk + VaR)

Ryzyko = prawdopodobieństwo straty.
VaR = waga straty.
Renata nie straszy: **informuje o konsekwencjach**.

---

## 3. Anti-spam (globalnie)
- max 1 komunikat na obiekt (per-body once),
- cooldowny globalne,
- agregacja zamiast list,
- brak powtórek po „Pomijam”,
- Combat Silence zawsze ma pierwszeństwo (poza krytycznymi stanami).

---

## 4. Akcje (Actions) — katalog i rola

### 4.1 Route Awareness & Route Intent

### 4.2 Sell Assist

## 5. Eksploracja — pełny lifecycle (end-to-end)

## 6. Przetrwanie i walka (bez taktyki)

## 7. Zasada końcowa
> **Renata nie robi z Ciebie pasażera.
> Robi z Ciebie pilota, który mniej rzeczy przegapia.**
