@echo off
rem ============================================================
rem  Register the evening blog task (daily 20:00).
rem  Double-click once. No admin rights needed.
rem  (ASCII only on purpose: cmd.exe reads .bat files in CP949.)
rem ============================================================
chcp 65001 >nul
echo.
echo  Registering: EveningBlog  (every day at 20:00)
echo  Target: %~dp0evening_blog.bat
echo.
schtasks /Create /TN "EveningBlog" /TR "\"%~dp0evening_blog.bat\"" /SC DAILY /ST 20:00 /F
if errorlevel 1 (
  echo.
  echo  [!] Failed. Copy the message above and ask your teacher.
) else (
  echo.
  echo  [OK] Done. Check it:  schtasks /Query /TN "EveningBlog"
  echo       Run it now:      schtasks /Run   /TN "EveningBlog"
  echo       Remove it:       schtasks /Delete /TN "EveningBlog" /F
)
echo.
pause
