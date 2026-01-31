@echo off
title RenataAI – Smoke Tests T1 + T2
echo ================================================
echo   RenataAI – Smoke Tests (T1 + T2)
echo ================================================
echo.

REM --- ustal ścieżkę główną projektu ---
set ROOT=%~dp0

REM --- sprawdź dostępność py / python ---
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    set PYEXEC=py
) else (
    where python >nul 2>&1
    if %ERRORLEVEL%==0 (
        set PYEXEC=python
    ) else (
        echo !!!
        echo Nie znaleziono Python ani py.
        echo Zainstaluj Pythona lub dodaj go do PATH.
        echo !!!
        pause
        exit /b 1
    )
)

echo 🌐 Używany interpreter: %PYEXEC%
echo.

echo --------------------------------
echo 🔍 T1 – Smoke Test Backend
echo --------------------------------
%PYEXEC% tools/smoke_tests_beckendy.py
echo.

echo --------------------------------
echo 🔍 T2 – Smoke Test Journal
echo --------------------------------
%PYEXEC% tools/smoke_tests_journal.py
echo.

echo ================================================
echo ✔   Wszystkie testy wykonane.
echo ================================================
echo.
pause
