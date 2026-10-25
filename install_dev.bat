@echo off
setlocal
cd /d "%~dp0"
title Ziggy - installation de l'environnement de developpement

where python >nul 2>nul
if errorlevel 1 goto :nopython
if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement Python...
  python -m venv .venv
  if errorlevel 1 goto :fail
)
echo Installation des dependances, patiente un instant...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements-build.txt
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" selfcheck.py
if errorlevel 1 goto :fail
echo.
echo [OK] Environnement pret. Tu peux lancer test.bat, lancer.bat ou build.bat.
if not defined ZIGGY_NOPAUSE pause
exit /b 0

:nopython
echo [ERREUR] Python est introuvable. Installe Python 3.11 ou plus recent depuis https://www.python.org/downloads/
echo en cochant "Add Python to PATH", puis relance ce script.
:fail
echo.
echo [ECHEC] Installation interrompue. Lis le message ci-dessus.
if not defined ZIGGY_NOPAUSE pause
exit /b 1
