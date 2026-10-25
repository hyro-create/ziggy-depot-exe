@echo off
setlocal
cd /d "%~dp0"
title Ziggy
if not exist ".venv\Scripts\python.exe" (
  echo Environnement absent : installation...
  call install_dev.bat
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" ziggy.py
if errorlevel 1 (
  echo.
  echo [ERREUR] Ziggy s'est arrete. Details : %LOCALAPPDATA%\Ziggy\logs\ziggy.log
  pause
)
