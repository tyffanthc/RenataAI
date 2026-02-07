# RenataAI - Features (v0.9.1-preview)

This file is a concise, code-based overview of what RenataAI currently does.
It reflects the current repository state and default behavior.

## Core runtime
- Desktop companion app (Tkinter) for Elite Dangerous.
- Reads Journal logs (offline-first).
- Maintains game state (system/body/station, ship state, route, inventory).
- Route manager with next-hop logic and progress state.

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

## Results tables (Treeview UX)
- Header sort
- LP row index column
- Column picker
- Presets per schema
- Persisted sort/visible columns
- Hover highlight
- Context menu (copy/set Start-Cel-Via/export), when enabled

## Trade capabilities
- Required station validation (`Stacja*`)
- Station suggestions by system
- EDSM-backed station list on focus (when online provider is enabled)
- Spansh fallback autocomplete on typed query
- Market Age controls (flagged)
- Jackpot thresholds and jackpot voice alerts

## Voice (TTS)
- Message-ID based preprocessor
- FREE voice policy (critical/context/silent)
- Category cooldowns and dedup
- Engine auto-select:
  - Piper (if available)
  - pyttsx3/SAPI5 fallback
- Optional Voice Pack autodetected from APPDATA

## Exploration/event logic
- Fuel warning threshold
- First discovery and first footfall messages
- FSS milestone messages (25/50/75/100)
- High-value world detection (ELW/WW/terraformable)
- Exobio cues including distance-ready flow
- Smuggler alert (illegal cargo)

## Providers and networking
- Centralized Spansh client
- Optional EDSM provider (flag-gated)
- Request timeout/retry/cache/dedup safeguards

## Settings and storage
- Effective settings path: `%APPDATA%\\RenataAI\\user_settings.json`
- Defaults in `config.py`
- FREE profile exposes only a reduced, safe subset of settings

## Settings runtime contract
- Runtime-active toggles affect behavior immediately.
- Toggles marked `w przygotowaniu` are UI placeholders (saved, but not runtime-wired yet).
- Current placeholders include:
  - `landing_pad_speech`
  - `route_progress_speech`
  - `high_g_warning`
  - `fss_assistant` toggle
  - `high_value_planets` toggle
  - `preflight_limpets`
  - `fdff_notifications`
  - `read_system_after_jump`
  - `mining_accountant`
  - `bounty_hunter`

## Tooling
- Backend smoke tests
- Journal smoke tests
- TTS preview tool
- Release sanity checklist for ZIP contents
