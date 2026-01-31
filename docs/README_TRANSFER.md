# RenataAI - Transfer Summary

This file is a compact handoff for moving the project to another ChatGPT account.
It complements existing docs (RENATA_STATUS.md, RUNBOOK_SMOKE.md, docs/*).

## What this project is
Desktop assistant for Elite Dangerous with Spansh planners, route tools, and UX-focused UI.

## How to run
- GUI: `py main.py`
- Smoke (backend): `python tools/smoke_tests_beckendy.py`
- Smoke (journal): `python tools/smoke_tests_journal.py`

## Key docs (source of truth)
- `RENATA_STATUS.md` - current status, flags, workflow
- `RUNBOOK_SMOKE.md` - smoke procedures
- `docs/RENATA_OVERVIEW.md` - product overview
- `docs/RENATA_UX_BACKLOG.md` - UX backlog
- `docs/RENATA_ARCH.mmd` - architecture sketch

## Recent updates (C1-C3)
- Column Picker for result tables (flagged).
- Treeview renderer + sort + LP + header indicators (flagged).
- Treeview rollout to Ammonia/ELW/HMC/Exomastery/Riches.

## Where to look in code
- UI tabs: `gui/tabs/*`
- Spansh planners: `gui/tabs/spansh/*`, `logic/spansh_payloads.py`
- Settings: `gui/tabs/settings.py`
- Config: `config.py` (user settings in `user_settings.json` - do not commit; copy from `user_settings.example.json`)

## Flags and settings
Feature flags live in `config.py` and are surfaced in Settings when user-facing.
Follow rule: new feature => flag + default OFF + Settings (if user-facing).
Key flags:
- `features.tables.column_picker_enabled`
- `features.tables.treeview_enabled`
- `features.ui.results_context_menu`

## Gotchas
- Use `py` on Windows if `python` is not available.
- `user_settings.json` is local-only; do not commit. If missing, copy `user_settings.example.json` -> `user_settings.json`.

## TTS (Piper, Windows-only)
- Default engine: `tts.engine=auto` (Piper if available, else pyttsx3).
- Configure paths in `user_settings.json`:
  - `tts.piper_bin` (e.g. `tools/piper/piper.exe` or a PATH bin)
  - `tts.piper_model_path` (e.g. `models/piper/pl_pl.onnx`)
  - `tts.piper_config_path` (e.g. `models/piper/pl_pl.json`)
- `tools/piper/` and `models/piper/` are local-only and gitignored.
- Download model/config (example):
  - `py tools/download_piper_model.py --model-url <URL.onnx> --config-url <URL.json> --out-dir models/piper`
