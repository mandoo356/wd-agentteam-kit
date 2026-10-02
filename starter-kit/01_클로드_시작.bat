@echo off
rem ============================================================
rem  Start Claude Code in the starter-kit folder.
rem  The cd below is the whole point: agents (.claude\agents),
rem  skills (.claude\skills) and the autosave/guard hooks are all
rem  resolved from the current folder. Opening a window anywhere
rem  else and typing 'claude' gives you zero agents.
rem  ASCII body on purpose: a .bat with non-ASCII text breaks when
rem  the file arrives with LF line endings (GitHub archive does).
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
where claude.cmd >nul 2>nul
if errorlevel 1 goto nocli
echo [WD] starter-kit folder: %CD%
echo [WD] Starting Claude Code. Agents, skills and hooks load from here.
echo.
call claude.cmd
if errorlevel 1 pause
exit /b 0
:nocli
echo [WD] Claude Code not found. Run 'hwan-gyeong-jeom-geom.bat' (environment check) first.
pause
exit /b 1
