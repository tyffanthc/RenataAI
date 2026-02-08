# Voice Pack Installer (Piper PL)

Folder: tools/voicepack_installer/

## Build prerequisites
- Inno Setup installed (ISCC in PATH)
- Payload files present in tools/voicepack_installer/payload/:
  - piper_runtime/ (full contents of tools/piper/)
  - models/pl_PL-gosia-medium.onnx
  - models/pl_PL-gosia-medium.json
  - voicepack.json
  - VOICEPACK_LICENSES.txt

## Build (Inno Setup)
ISCC.exe voicepack.iss

Output: Renata-VoicePack-Piper-PL-Installer-0.9.0-pl1.exe

## Install target
%APPDATA%\RenataAI\voice\piper\

Default path is APPDATA.
Installer allows selecting another folder (for portable/onedir use).

## Detection model (Renata side)
- APPDATA install: auto-detected by `tts.engine=auto`.
- Portable install: install next to `RenataAI.exe` using:
  - `voice\piper\piper.exe`
  - `voice\piper\models\pl_PL-gosia-medium.onnx`
  - `voice\piper\models\pl_PL-gosia-medium.json`
- Keep Piper runtime files (DLL + `espeak-ng-data`) next to `piper.exe`.

## User message shown in installer
`payload/INSTALL_INFO.txt` is shown before install and copied with the pack,
so users see APPDATA vs portable guidance during setup.

## Uninstall
Standard Windows Apps list (per-user)
