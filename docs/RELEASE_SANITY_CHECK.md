# Release Sanity Check (ZIP clean)

Before upload, verify the ZIP does NOT contain any of these runtime files:
- user_settings.json
- user_logbook.json
- config.json
- log.txt / *.log

Expected ZIP contents (example):
- RenataAI.exe
- README.txt
- CHANGELOG.txt
- user_settings.example.json
- THIRD_PARTY_NOTICES.txt
- start_renata_portable.bat
- PORTABLE_MODE.txt

PASS/FAIL:
- [ ] PASS — ZIP is clean (none of the files above are present)
- [ ] FAIL — ZIP contains runtime data (do not upload)

Quick PowerShell check (optional):
Get-ChildItem -Recurse -Filter *.zip | ForEach-Object { $_.FullName }
# Extract ZIP to a temp folder and search:
# Get-ChildItem -Recurse | Where-Object { $_.Name -in @('user_settings.json','user_logbook.json','config.json','log.txt') -or $_.Extension -eq '.log' }
