# COMPLIANCE_CHECKLIST.md

Purpose: Quick audit to reduce copyright and policy risks before release.
Scope: Code, docs, UI text, and third-party services used by RenataAI.

## A) Third-party services and trademarks
- [ ] All third-party names are used only for identification (Spansh, EDSM, Inara, EDTools, Elite Dangerous).
- [ ] Attribution/trademark note present in `docs/README_TRANSFER.md`.
- [ ] No third-party logos/icons included without permission.

## B) Content ownership
- [ ] No copied text from websites or docs included in code or UI.
- [ ] Any external references are paraphrased and minimal.
- [ ] No embedded media from third parties (images, audio, videos) without license.

## C) API usage and terms
- [ ] Providers are optional (offline-first). All online providers are gated by flags and OFF by default.
- [ ] No hidden online requests when flags are OFF.
- [ ] UI/UX does not claim official affiliation with any provider.

## D) User data and privacy
- [ ] User data stays local by default (settings, logs, logbook).
- [ ] Upload is opt-in only and clearly labeled (if ever enabled).
- [ ] No personal data in example files or docs.

## E) Release hygiene
- [ ] `user_settings.json` is not tracked or committed.
- [ ] `user_settings.example.json` exists and is minimal.
- [ ] `tools/piper/` and `models/piper/` are gitignored.

## F) Quick documentation pointers
- [ ] `docs/RENATA_STATUS.md` reflects current DONE/NEXT/FUTURE.
- [ ] `docs/SETTINGS_CHECKBOX.md` lists visible/hidden settings for FREE.
- [ ] `docs/UI_VISIBILITY.md` lists visible/hidden tabs for FREE.

## G) TTS / Voice Pack (Piper)
- [x] Piper TTS engine pochodzi z repozytorium rhasspy/piper i jest licencjonowany na MIT License.
- [x] Do dystrybucji NIE jest uzywany fork GPL (piper1-gpl).
- [x] Model glosu `pl_PL-gosia-medium.onnx` posiada licencje CC0 (public domain).
- [x] Voice Pack (Piper + model) jest opcjonalny i dystrybuowany oddzielnie od glownego EXE/ZIP.
- [x] Informacja o licencjach TTS jest udokumentowana w README_TRANSFER.md.

Notes:
- If any item fails, fix before release.
