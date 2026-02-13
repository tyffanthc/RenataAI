# Release Checklist - R.E.N.A.T.A. (RenataAI)

## Scope confirmation
- Confirm target version and included tickets.
- Freeze feature flags for release (default ON/OFF decisions).
- Verify `user_settings.json` is not tracked.

## Build and smoke
- `py tools/smoke_tests_beckendy.py`
- `py tools/smoke_tests_journal.py`
- `py -3 -m py_compile main.py config.py gui/common.py logic/events/*.py`
- TTS autodetect:
  - voice pack in APPDATA -> `selected=piper source=appdata`
  - no voice pack -> `selected=pyttsx3 reason=piper_not_found`

## Core UI/UX (manual)
- Start app: `py main.py`
- Spansh tabs open and render (Neutron, Riches, Ammonia, ELW, HMC, Exo, Trade).
- FREE tabs: in FREE mode visible only Pulpit/Spansh/Dziennik/Settings.
- Treeview tables: headers visible, sort by header works, LP column present.
- Column Picker: toggle columns, presets apply, restart keeps layout.
- Context menu on results (if enabled): copy, set Start/Cel/Via, export options per current UI.
- Trade: required field `Stacja*` validation, no request when empty.
- Trade: station suggestions on focus:
  - EDSM ON -> list appears after load
  - EDSM OFF -> clear hint text shown
- Trade: verify split-view behavior:
  - details panel opens after row selection,
  - details panel can be hidden/shown without breaking main table.
- Trade: verify columns render values (no empty placeholders when payload contains data):
  - `Towar`
  - `Zysk [cr]`
  - `Zysk/t [cr]`
  - `Cumulative Profit [cr]`
  - `Wiek rynku K/S`

## Navigation / route behavior (manual)
- Plan Neutron route with long in-game segment before first neutron.
- Following in-game route should NOT spam `poza trasa`.
- Milestone progress should speak 25/50/75/100 for active segment.
- On milestone reached:
  - segment-complete line is spoken once
  - next target is copied once
- NEXT_HOP line must refer to real next target.

## Exploration and event flow (manual)
- FSS progress 25/50/75/100 works and ordering is sensible.
- Last-body cue is spoken before full-scan completion, not after.
- Full scan completion line appears once.
- High-value DSS hints appear for eligible bodies.
- Exobio:
  - second sample cue appears,
  - real distance readiness cue appears after threshold is passed.

## Fuel warning sanity (manual)
- On startup with normal fuel, no false `Fuel reserves critical`.
- Real low-fuel still triggers warning.
- Docking or refuel clears warning state.

## Windows focus behavior (manual)
- While TTS speaks (Piper), no extra console steals focus from game.

## Debug / observability
- Logging does not crash app on odd fields.
- Debug panel (if enabled) updates without spam.
- Watcher startup errors are non-critical and concise.

## Release artifacts
- Verify `docs/README_TRANSFER.md`, `docs/COMPLIANCE_CHECKLIST.md`, `docs/RELEASE_SANITY_CHECK.md` are up to date.
- Voice Pack installer is a separate asset (not inside app ZIP).
- ZIP should contain:
  - `RenataAI.exe`
  - `README.txt`
  - `CHANGELOG.txt`
  - `user_settings.example.json`
  - `THIRD_PARTY_NOTICES.txt`
  - `start_renata_portable.bat`
  - `PORTABLE_MODE.txt`

## Release notes must include
- Voice Pack (Piper PL) is optional.
- Without Voice Pack, system Windows voice fallback is used.
- If TTS defaults changed, note possible `user_settings.json` refresh requirement.
