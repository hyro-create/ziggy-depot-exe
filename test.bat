@echo off
setlocal
cd /d "%~dp0"
title Ziggy - tests

if not exist ".venv\Scripts\python.exe" (
  echo [ERREUR] Environnement absent : lance d'abord install_dev.bat
  goto :fail
)
".venv\Scripts\python.exe" selfcheck.py
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pytest -v -rs
if errorlevel 1 goto :fail
echo.
echo [OK] Tous les tests sont passes. Les tests marques "skipped" ne sont pas executes ici : lis la raison indiquee.
if not defined ZIGGY_NOPAUSE pause
exit /b 0

:fail
echo.
echo [ECHEC] Des verifications ont echoue : Ziggy ne doit pas etre distribue.
if not defined ZIGGY_NOPAUSE pause
exit /b 1
