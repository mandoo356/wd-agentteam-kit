@echo off
chcp 65001 >nul
cd /d "%~dp0"
where claude.cmd >nul 2>nul
if errorlevel 1 (
  echo [오류] Claude Code를 찾을 수 없습니다. 먼저 환경점검.bat 을 실행하세요.
  pause
  exit /b 1
)
echo 스타터킷 폴더에서 클로드를 시작합니다.
echo 현재 폴더: %CD%
echo.
echo 이 폴더에서 열어야 직원(.claude\agents)과 스킬(.claude\skills)이 붙고,
echo 자동저장과 삭제가드도 켜집니다.
echo 창을 그냥 열어 claude 를 치면 직원이 한 명도 안 뜹니다.
echo 다음부터는 이 파일을 더블클릭하세요.
echo.
call claude.cmd
if errorlevel 1 pause
