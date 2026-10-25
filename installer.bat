@echo off
setlocal
cd /d "%~dp0"
title Ziggy - creation de l'installateur

if not exist "dist\Ziggy\Ziggy.exe" (
  echo [ERREUR] dist\Ziggy\Ziggy.exe est absent : lance d'abord build.bat
  goto :fail
)
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" ( echo [ERREUR] Environnement absent : lance d'abord install_dev.bat & goto :fail )
set "VER="
for /f "delims=" %%v in ('"%PY%" -c "from version import APP_VERSION; print(APP_VERSION)"') do set "VER=%%v"
if not defined VER ( echo [ERREUR] Version introuvable dans version.py & goto :fail )

set "ISCC="
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%p set "ISCC=%%~p"
if not defined ISCC for /f "delims=" %%i in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%i"
if not defined ISCC goto :noiscc

echo Compilation de l'installateur, version %VER%...
if exist "installer_output\Ziggy-Setup.exe" del "installer_output\Ziggy-Setup.exe"
"%ISCC%" /Qp "/DMyAppVersion=%VER%" "installer\ziggy.iss"
if errorlevel 1 goto :fail
if not exist "installer_output\Ziggy-Setup.exe" goto :fail

echo.
echo ================================================================
echo  Termine : installer_output\Ziggy-Setup.exe  (version %VER%)
echo ================================================================
if not defined ZIGGY_NOPAUSE pause
exit /b 0

:noiscc
echo [ERREUR] Inno Setup 6 est introuvable.
echo Installe-le une seule fois (gratuit) : https://jrsoftware.org/isdl.php  - version 6.3 ou plus recente.
echo Puis relance installer.bat.
:fail
echo.
echo [ECHEC] L'installateur n'a pas ete cree.
if not defined ZIGGY_NOPAUSE pause
exit /b 1
