@echo off
rem ============================================================
rem  Evening blog - runs at 20:00 by Windows Task Scheduler.
rem  If today had a lecture, staff3 drafts a blog post and
rem  saves it as a Naver draft. Quiet on days with no lecture.
rem  (ASCII only on purpose: cmd.exe reads .bat files in CP949.)
rem ============================================================
chcp 65001 >nul
py -3 -X utf8 "%~dp0evening_blog.py"
exit /b %ERRORLEVEL%
