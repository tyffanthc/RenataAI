# RenataAI — Features (v0.9.1-preview)

This file is a concise, code-based overview of what RenataAI currently does.
It reflects the current repository state and defaults.

**Core runtime**
- Desktop app (Tkinter) for Elite Dangerous companion workflows.
- Reads Elite Dangerous Journal logs (offline-first).
- Maintains game state (current system/body/station, ship state, inventory).
- Route management (active route list, next hop, route progress).

**Main tabs (UI)**
- **Pulpit (Dashboard):** current system/status, ship state, route summary, log output.
- **Spansh:** planners + results tables + route tools.
- **Logbook (Dziennik):** local logbook with folders/entries, context menu actions.
- **Engineer (Inżynier):** recipe inventory check (hidden in FREE profile).
- **Inara / EDTools:** hidden in FREE profile (placeholder only).

**Spansh planners (GUI + logic)**
- Neutron route planner.
- Riches / R2R.
- Ammonia.
- ELW.
- HMC.
- Exomastery.
- Trade route planner.
- Common behavior: request → results table → status feedback.

**Results tables (Treeview UX)**
- Real columns with PL headers and units.
- Sort by header click.
- LP (row index) column.
- Column picker with presets (per tab).
- Persisted column visibility + sort state.
- Sticky header + autosize widths.
- Hover row highlight.
- Context menu (copy/csv/tsv/set Start/Cel/Via) when enabled.

**Trade planner (extras)**
- Required Station field validation (no request when empty).
- Market Age (slider + datetime) under flag.
- Station suggestions by system:
  - Focus/open list via EDSM (if enabled).
  - Fallback hint when EDSM is OFF.
- Jackpot thresholds and alerts (voice).

**Route & clipboard tools**
- Auto‑clipboard: full route or NEXT_HOP.
- Next‑hop stepper with FSDJump/Location triggers.
- Manual “copy next hop” action.
- Route signature + dedup to avoid spam.

**Exploration / journal‑driven logic**
- Fuel warnings (low fuel).
- First discovery & first footfall announcements.
- FSS progress milestones (25/50/75/100%).
- High‑value worlds detection (ELW / WW / terraformable / HMC).
- Bio signals alerts (DSS bio).
- Smuggler alert (illegal cargo).
- Trade jackpot alerts (market data).

**TTS system**
- Message‑ID based TTS via Text Preprocessor.
- Free policy gating (critical vs context vs silent).
- Cooldowns per category (nav/route/explore/alert/info).
- Engines:
  - Piper (if available).
  - Fallback pyttsx3/SAPI5.
- Optional Voice Pack auto‑detected in APPDATA.

**Providers & online data (offline‑first)**
- Spansh HTTP client (centralized), retries/timeout, cached requests, dedup.
- EDSM optional:
  - system lookup (coords).
  - stations-in-system (Trade suggestions).
- Online calls are gated by flags and OFF by design when disabled.

**Data & calculations**
- Jump range engine (from ship modules + cargo/fuel).
- Modules data loader + generator (renata_modules_data.json).
- Science data loader + generator (renata_science_data.xlsx).

**Settings & storage**
- Settings stored in `%APPDATA%\\RenataAI\\user_settings.json`.
- Defaults live in `config.py`.
- FREE profile: short, safe settings list (advanced hidden).

**Debug & observability**
- Safe logging (no crashes on bad fields).
- Throttled logs.
- Optional debug panel.
- Last Spansh request snapshot (optional).

**Tools & tests**
- Smoke tests (backend + journal).
- Journal replay tool.
- TTS preview tool.

**Notes**
- Some tabs/features are hidden in FREE profile but exist in code.
- Voice Pack is optional; app runs without it (system voice fallback).
