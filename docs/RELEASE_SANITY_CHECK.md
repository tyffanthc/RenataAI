# Release Sanity Check (ZIP clean)

Before upload, verify ZIP does NOT contain runtime/user files:
- `user_settings.json`
- `user_logbook.json`
- `config.json`
- `log.txt` / `*.log`
- `tmp/` cache/output folders

Expected ZIP contents (example):
- `RenataAI.exe`
- `README.txt`
- `CHANGELOG.txt`
- `user_settings.example.json`
- `THIRD_PARTY_NOTICES.txt`
- `start_renata_portable.bat`
- `PORTABLE_MODE.txt`

PASS/FAIL gate:
- [ ] PASS - ZIP is clean (none of the forbidden files above)
- [ ] FAIL - ZIP contains runtime data (do not upload)

Quick PowerShell check (optional):
```powershell
$zip = "release\\Renata_vX.Y.Z-preview_win_x64.zip"
$tmp = Join-Path $env:TEMP "renata_zip_check"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $tmp -Force

Get-ChildItem -Recurse $tmp | Where-Object {
  $_.Name -in @("user_settings.json","user_logbook.json","config.json","log.txt") -or
  $_.Extension -eq ".log" -or
  $_.FullName -match "\\tmp\\"
}
```
