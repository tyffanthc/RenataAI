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

## Uninstall
Standard Windows Apps list (per-user)
