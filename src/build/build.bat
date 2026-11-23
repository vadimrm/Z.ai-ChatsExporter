@echo off
rem === Build the AutoClaw.Z.ai-ExportChat package: ONE exe (round 19) ===
rem Run from anywhere: build\build.bat
rem NOTE: ASCII-only on purpose - cmd parses .bat files in the OEM codepage,
rem and UTF-8 Cyrillic text broke execution (the 2026-11-07 build failure).
setlocal
set ROOT=%~dp0..
set VENV=%~dp0venv
set DIST=%~dp0dist
set WORK=%~dp0work
set RELEASE=%ROOT%\release

if not exist "%VENV%\Scripts\python.exe" (
  echo [1/3] Creating the build venv ^(python -m venv^)...
  python -m venv "%VENV%"
)

echo [2/3] Installing PyInstaller into the build venv...
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-warn-script-location -q pyinstaller
if errorlevel 1 goto :fail

echo [3/3] Building ExportChat.exe (GUI + chat adapters in one process)...
rem --paths backend: the adapter modules are imported in-process by
rem frontend\job_runner.py (round 19 - no more engine subprocess/exe);
rem --hidden-import is belt-and-braces insurance for the lazy imports.
rem round 84 (ver 2.00): exe file icon = the Tk quill feather (same as the
rem title bar default), extracted from tk86t.dll into ExportChat.ico
"%VENV%\Scripts\pyinstaller.exe" --noconfirm --onefile --noconsole --name ExportChat --icon "%~dp0ExportChat.ico" --paths "%ROOT%\backend" --hidden-import adapter --hidden-import export_chat --hidden-import zcode_export --distpath "%DIST%" --workpath "%WORK%" --specpath "%~dp0." "%ROOT%\frontend\main.py"
if errorlevel 1 goto :fail

if not exist "%RELEASE%" mkdir "%RELEASE%"
copy /Y "%DIST%\ExportChat.exe" "%RELEASE%\" >nul
copy /Y "%ROOT%\db_profiles.cfg" "%ROOT%\exe for test\" >nul
copy /Y "%ROOT%\build\ExportChat.factory.cfg" "%ROOT%\exe for test\ExportChat.cfg" >nul
rem --- db_profiles.cfg ships WITH the package (owner decision, round 19):
rem the exe reads it at startup; the user edits it as plain text ---
copy /Y "%ROOT%\db_profiles.cfg" "%RELEASE%\" >nul
rem --- language files ship WITH the package (round 23): editable texts,
rem loaded at startup and on every language switch ---
copy /Y "%ROOT%\lang_ru.cfg" "%RELEASE%\" >nul
copy /Y "%ROOT%\lang_en.cfg" "%RELEASE%\" >nul
copy /Y "%ROOT%\lang_zh.cfg" "%RELEASE%\" >nul

rem --- p70: BOTH fresh configs go into release (owner:
rem latest formats of BOTH configs; ExportChat.cfg = factory v6) ---
copy /Y "%ROOT%\build\ExportChat.factory.cfg" "%RELEASE%\ExportChat.cfg" >nul

rem --- "exe for test" (owner renamed from "for tests", p70):
rem self-contained folder for checking on another computer;
rem exe is gitignored, README.txt and lang files live in git;
rem BOTH configs are refreshed on each build ---
if not exist "%ROOT%\exe for test" mkdir "%ROOT%\exe for test"
copy /Y "%DIST%\ExportChat.exe" "%ROOT%\exe for test\" >nul
copy /Y "%ROOT%\db_profiles.cfg" "%ROOT%\exe for test\" >nul
copy /Y "%ROOT%\build\ExportChat.factory.cfg" "%ROOT%\exe for test\ExportChat.cfg" >nul
copy /Y "%ROOT%\lang_ru.cfg" "%ROOT%\exe for test\" >nul
copy /Y "%ROOT%\lang_en.cfg" "%ROOT%\exe for test\" >nul
copy /Y "%ROOT%\lang_zh.cfg" "%ROOT%\exe for test\" >nul

echo.
echo Done. Package: %RELEASE%
dir /b "%RELEASE%"
exit /b 0

:fail
echo BUILD FAILED.
exit /b 1
