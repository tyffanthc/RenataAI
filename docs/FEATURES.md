# R.E.N.A.T.A. (RenataAI) - Features (v0.9.4-preview)

R.E.N.A.T.A. = Route, Exploration & Navigation Assistant for Trading & Analysis.

This file is a concise, code-based overview of current behavior.

## Core runtime
- Desktop companion app (Tkinter) for Elite Dangerous.
- Reads Journal logs (offline-first).
- Polls `Status.json`, `Cargo.json`, `Market.json`, and `NavRoute.json`.
- Maintains game state (system/body/station, ship state, route, inventory).

## Main UI tabs
- Dashboard (`Pulpit`)
- Spansh planners (`Spansh`)
- Logbook (`Dziennik`)
- Settings
- Hidden in FREE profile: Inara, EDTools, Inzynier

## Spansh planners
- Neutron
- Riches (R2R)
- Ammonia
- ELW
- HMC
- Exomastery
- Trade

Common flow: request -> normalize -> render -> status update.

## Navigation and route symbiosis
- Active route from Spansh with next-hop management.
- In-game route (`NavRoute.json`) is ingested and used for route alignment.
- Milestone progress voice for route segments: 25/50/75/100.
- Milestones are tracked per segment (for example: to next neutron boost).
- Desync warning has confirmation guard (no immediate false positives).
- NEXT_HOP semantics fixed: "next" means real next target, not current system.

## Results tables (Treeview UX)
- Header sort.
- LP row index column.
- Column picker.
- Presets per schema.
- Persisted sort/visible columns.
- Hover highlight.
- Context menu (copy/set Start-Cel-Via/export), when enabled.

## Trade capabilities
- Required station validation (`Stacja*`).
- Station suggestions by system.
- EDSM-backed station list on focus (when online provider is enabled).
- Spansh fallback autocomplete on typed query.
- Trade row normalization for single/multi-commodity legs.
- Cumulative profit mapping and detail panel per selected leg.
- Market age pair for buy/sell side (`Wiek rynku K/S`).
- Fallback jumps calculation per leg when API omits jump count.
- Split-view layout (route table + details panel).
- Jackpot thresholds and jackpot voice alerts.

## Voice (TTS)
- Message-ID based text preprocessor.
- FREE voice policy (critical/context/silent).
- Category cooldowns and dedup.
- Engine auto-select:
  - Piper (if available)
  - pyttsx3/SAPI5 fallback
- Optional Voice Pack autodetected from APPDATA.
- Piper preflight on Windows to avoid focus-stealing popup behavior.

## Exploration/event logic
- Fuel warning threshold with startup/transient guards.
- First discovery and first footfall messages.
- FSS milestone messages (25/50/75/100) through message_id policy.
- Full-scan handling with ordered last-body behavior.
- High-value world detection (ELW/WW/terraformable + DSS hint flow).
- Exobio cues:
  - high bio signals,
  - range-ready cue after second sample,
  - real distance check from `Status.json` with species threshold.
- Smuggler alert (illegal cargo).

## Startup and reliability
- Startup bootstrap avoids replay navigation spam.
- Start field prefill is restored after bootstrap.
- Status watcher JSON/I/O logs are calmer and non-critical.
- Fuel low warning hardened against startup/SCO transient samples.

## Providers and networking
- Centralized Spansh client.
- Optional EDSM provider (flag-gated).
- Request timeout/retry/cache/dedup safeguards.

## Settings and storage
- Effective settings path: `%APPDATA%\\RenataAI\\user_settings.json`.
- Defaults in `config.py`.
- FREE profile exposes only a reduced, safe subset of settings.
- Optional portable launcher can override settings path via `RENATA_SETTINGS_PATH`.

## Tooling
- Backend smoke tests.
- Journal smoke tests.
- TTS preview tool.
- Release sanity checklist for ZIP contents.
