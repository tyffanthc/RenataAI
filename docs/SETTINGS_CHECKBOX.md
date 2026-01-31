# SETTINGS_CHECKBOX.md

Cel: lista kontrolna widocznych/ukrytych checkboxow w Settings, zeby nic nie zginelo przy "FREE".
Aktualizowac przy kazdej zmianie widocznosci.

---

## Widoczne (aktualnie w UI)
- [x] Minimalny glos (polecane) / Tryb FREE (`features.tts.free_policy_enabled`)
- [x] Wlacz glos (`voice_enabled`)
- [x] Auto-schowek (`auto_clipboard`)
- [x] Auto-schowek trasy (dropdown) (`auto_clipboard_mode`)
- [x] Zezwol na dane online (master) (`features.providers.edsm_enabled` + lookup online)

---

## Ukryte (tylko flagi / dev)
- [x] Debug: panel, payloady, cache, dedup (`features.debug.*`, `debug_*`)
- [x] Tabele: column picker / treeview / persist sort / badges (`features.tables.*`)
- [x] Spansh: timeout/retries/debug payload (`spansh_*`, `features.spansh.*`)
- [x] Asystenci: FSS, high value, bio, FD/FF, smuggler, jackpot, high-g
- [x] Auto-clipboard: trigger, resync, allow manual, stepper
- [x] Provider flags szczegolowe (EDSM/system/trade lookup)
- [x] Inne: confirm_exit, motyw, log_dir, tryby dev

---

## Zasady
- Kazdy checkbox w Settings musi byc na liscie (Widoczne lub Ukryte).
- Jesli cos znika z UI (FREE), przenies do "Ukryte" i podaj powod.
- Jesli cos wraca do UI, przenies do "Widoczne".
- Nie trzymamy duplikatow.
