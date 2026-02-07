# R.E.N.A.T.A. (RenataAI) - Transfer Summary

This file is a compact handoff for moving the project to another ChatGPT account.
It complements existing docs in docs/.
R.E.N.A.T.A. = Route, Exploration & Navigation Assistant for Trading & Analysis.

## What this project is
Desktop companion for Elite Dangerous with Spansh planners, route tools, and UX-focused UI.

## Attribution / Trademarks
RenataAI uses third-party services/APIs (Spansh, EDSM, Inara, EDTools) and the Elite Dangerous Journal format.
All trademarks and brand names belong to their respective owners.

## How to run
- GUI: `py main.py`
- Smoke (backend): `python tools/smoke_tests_beckendy.py`
- Smoke (journal): `python tools/smoke_tests_journal.py`

## Key docs (source of truth)
- `docs/README.md` - what docs/ contains and what it is not
- `docs/RELEASE_CHECKLIST.md` - release checklist (manual + smoke)
- `docs/RELEASE_SANITY_CHECK.md` - ZIP clean gate
- `docs/COMPLIANCE_CHECKLIST.md` - compliance + licenses
- `docs/README_TRANSFER.md` - handoff summary (this file)

## Recent updates (0.9.2-preview)
- Route/nav symbiosis improved: milestone progress 25/50/75/100 per active segment.
- Desync warnings now use confirmation guard to reduce false positives.
- NEXT_HOP semantics corrected (real next target instead of current system).
- FSS flow improved: policy-wired progress messages and full-scan ordering.
- Exobio flow expanded with real distance checks from `Status.json`.
- Startup reliability fixes:
  - restored Start prefill after bootstrap,
  - calmer watcher JSON/I/O wording,
  - low-fuel startup transient guards.
- Piper TTS preflight on Windows to prevent focus-stealing popup.
- Portable mode starter remains available in ZIP (`start_renata_portable.bat` + `PORTABLE_MODE.txt`).

## Where to look in code
- UI tabs: `gui/tabs/*`
- Spansh planners: `gui/tabs/spansh/*`, `logic/spansh_payloads.py`
- Settings: `gui/tabs/settings.py`
- Config: `config.py` (defaults).
- Renata stores all user settings in `%APPDATA%\\RenataAI\\user_settings.json`.
- Local config files next to the application are ignored unless `RENATA_SETTINGS_PATH` override is used.

## Flags and settings
Feature flags live in `config.py` and are surfaced in Settings when user-facing.
Follow rule: new feature => flag + default OFF + Settings (if user-facing).
Key flags:
- `features.tables.column_picker_enabled`
- `features.tables.treeview_enabled`
- `features.ui.results_context_menu`

## Settings runtime contract
- Settings marked as `w przygotowaniu` are UI placeholders only (saved in config, not runtime-active yet).
- Runtime-active toggles have immediate effect and are used directly by event/planner logic.

## FREE Settings Profile
Settings in FREE mode show a short, safe list of options (5-7 max). Advanced/dev options are hidden.

## Gotchas
- Use `py` on Windows if `python` is not available.
- `user_settings.json` is local-only; do not commit.

## TTS (Piper, Windows-only)
- Default engine: `tts.engine=auto` (Piper if available, else pyttsx3).
- Optional Voice Pack in APPDATA is auto-detected when `tts.engine=auto`.
- If manual paths are used, they live in `user_settings.json`:
  - `tts.piper_bin`, `tts.piper_model_path`, `tts.piper_config_path`

### Licencje (TTS / Voice Pack)
- Piper TTS engine: MIT License (repozytorium rhasspy/piper).
- Model glosu PL: `pl_PL-gosia-medium.onnx` — licencja CC0 (public domain).
- Voice Pack (Piper + model) jest opcjonalny i dystrybuowany oddzielnie od glownego release.

