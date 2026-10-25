@echo off
setlocal
cd /d "%~dp0"
title Ziggy - construction

where python >nul 2>nul
if errorlevel 1 goto :nopython

if not exist ".venv\Scripts\python.exe" (
  echo [1/6] Creation de l'environnement Python...
  python -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [1/6] Environnement Python existant.
)
set "PY=.venv\Scripts\python.exe"

echo [2/6] Installation des dependances et de PyInstaller...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements-build.txt
if errorlevel 1 goto :fail

echo [3/6] Verification des dependances...
"%PY%" selfcheck.py
if errorlevel 1 goto :fail

echo [4/6] Tests...
"%PY%" -m pytest -q
if errorlevel 1 goto :fail

echo [5/6] Compilation PyInstaller, quelques minutes...
"%PY%" -m PyInstaller --noconfirm --clean ziggy.spec
if errorlevel 1 goto :fail
if not exist "dist\Ziggy\Ziggy.exe" goto :fail

echo [6/6] Verification de l'application compilee...
"dist\Ziggy\Ziggy-diagnostic.exe" --check
if errorlevel 1 goto :fail
"%PY%" tools\smoke_test_build.py "dist\Ziggy"
if errorlevel 1 goto :fail

echo.
echo ================================================================
echo  Termine : dist\Ziggy\Ziggy.exe
echo  Etape suivante : installer.bat  pour creer Ziggy-Setup.exe
echo  Tes donnees (%LOCALAPPDATA%\Ziggy) n'ont pas ete touchees.
echo ================================================================
if not defined ZIGGY_NOPAUSE pause
exit /b 0

:nopython
echo [ERREUR] Python est introuvable. Installe Python 3.11 ou plus recent depuis https://www.python.org/downloads/
:fail
echo.
echo [ECHEC] La construction a echoue : aucun fichier n'est a utiliser. Lis le message ci-dessus.
if not defined ZIGGY_NOPAUSE pause
exit /b 1
