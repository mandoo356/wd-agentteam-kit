# ============================================================
#  위드드림 AI 에이전트팀 스타터킷 — 엔진 업데이트 (이미 설치한 수강생용)
#
#  PowerShell 창에 아래 한 줄만 붙여넣습니다. (CMD 창이면 아래 두 번째 줄)
#    irm https://raw.githubusercontent.com/mandoo356/wd-agentteam-kit/main/update.ps1 | iex
#    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/mandoo356/wd-agentteam-kit/main/update.ps1 | iex"
#
#  하는 일 (2026-09-08)
#    1) 켜져 있는 슬랙 서버(server.py)를 끈다
#    2) 엔진 파일만 새 판으로 바꾼다 — server.py · claude_bridge.py · roster.py(신설) · 점검.py · 카드·README
#       ※ 내가 만든 것(직원 .claude/agents · 스킬 · personas.py · agent_channels.py · .env · workspace)은 건드리지 않는다
#    3) 바꾸기 전 파일은 starter-kit\backup\update-날짜\ 에 남긴다
#    4) 어제 대화(.agent_session.json)를 지워 새 대화로 시작한다 — 잘못 기억한 이름이 여기서 끊긴다
#    5) 강사 이름이 내 설정 파일에 들어가 있는지 살펴보고 알려준다 (지우지는 않는다)
#    6) py 점검.py 4 로 확인하고, 서버를 새 창에서 다시 켠다
#
#  고치는 증상: ① 직원이 나를 남(강사) 이름으로 부름  ② 팀장만 대답하고 나머지 직원이 안 나옴
#              ③ 이모지·캐릭터(인사말)가 안 생김
#
#  선택 환경변수:  $env:WD_INSTALL_ROOT = 'D:\Agent'   (설치 위치를 바꿨을 때)
#  이 파일은 UTF-8(BOM 없음)이며 raw.githubusercontent.com 이 charset=utf-8 로 내려준다.
# ============================================================

& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
try { $null = & "$env:ComSpec" /c chcp 65001 } catch {}
try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding  = [Text.Encoding]::UTF8
} catch {}
try { $Host.UI.RawUI.WindowTitle = '위드드림 AI 에이전트팀 — 엔진 업데이트' } catch {}

$Repo    = 'mandoo356/wd-agentteam-kit'
$Branch  = 'main'
$RawBase = "https://raw.githubusercontent.com/$Repo/$Branch/starter-kit"

$Root = 'C:\Agent'
if ($env:WD_INSTALL_ROOT) { $Root = $env:WD_INSTALL_ROOT }
$Root = [IO.Path]::GetFullPath($Root)
$Kit  = Join-Path $Root '01_KIT\starter-kit'
$Srv  = Join-Path $Kit 'slack-server'

function Step([string]$t) { Write-Host ''; Write-Host "  ▶ $t" -ForegroundColor Magenta }
function Info([string]$t) { Write-Host "     $t" -ForegroundColor DarkGray }
function Warn([string]$t) { Write-Host "     ⚠️  $t" -ForegroundColor Yellow }
function Fail([string]$t) { Write-Host ''; Write-Host "  ❌ $t" -ForegroundColor Red; Write-Host ''; throw $t }

Write-Host ''
Write-Host '  위드드림 AI 에이전트팀 — 엔진 업데이트 (2026-09-08 판)' -ForegroundColor Magenta
Write-Host "  대상: $Kit" -ForegroundColor DarkGray

if (-not (Test-Path -LiteralPath (Join-Path $Srv 'server.py'))) {
    Fail "설치된 스타터킷을 못 찾았습니다: $Kit`n     처음 설치라면 대신 이 한 줄:  irm https://raw.githubusercontent.com/$Repo/$Branch/install.ps1 | iex"
}

# ── 1. 켜져 있는 서버 끄기 ──────────────────────────────────
Step '켜져 있는 슬랙 서버 끄기'
$killed = 0
if ($env:WD_NO_KILL) {
    Info '서버 끄기는 건너뜁니다 (WD_NO_KILL). 켜져 있으면 그 창에서 Ctrl+C.'
} else {
    try {
        $all = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $all | Where-Object {
            $_.Name -match '^python' -and $_.CommandLine -and $_.CommandLine -match 'server\.py'
        } | ForEach-Object {
            # 감시기(supervisor)가 띄운 다른 서버(강사 홈서버 등)는 건드리지 않는다 — 수강생 킷의 서버만
            $ppid = $_.ParentProcessId
            $par = $all | Where-Object { $_.ProcessId -eq $ppid } | Select-Object -First 1
            if ($par -and $par.CommandLine -and $par.CommandLine -match 'supervisor|withdream-agent-server') { return }
            try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $killed++ } catch {}
        }
    } catch {}
    if ($killed -gt 0) { Info "서버 $killed 개를 껐습니다. 옛 서버 창은 닫아도 됩니다." } else { Info '켜져 있는 서버가 없습니다.' }
}

# ── 2. 받을 파일 ─────────────────────────────────────────────
#   내가 고치는 파일(personas.py · agent_channels.py · .env · 직원 · 스킬)은 이 목록에 없다.
$files = @(
    'slack-server/server.py',
    'slack-server/claude_bridge.py',
    'slack-server/roster.py',
    'slack-server/README.md',
    '점검.py',
    '프롬프트카드.md',
    'README.md'
)
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bak   = Join-Path $Kit "backup\update-$stamp"
$tmp   = Join-Path $Root "90_TEMP\update-$stamp"
$null  = New-Item -ItemType Directory -Path $tmp -Force

Step '새 엔진 파일 받기'
$got = @()
foreach ($rel in $files) {
    $segs = @(($rel -split '/') | ForEach-Object { [uri]::EscapeDataString($_) })
    $url  = $RawBase + '/' + ($segs -join '/')
    $dst = Join-Path $tmp ($rel -replace '/', '\')
    $null = New-Item -ItemType Directory -Path (Split-Path $dst) -Force
    try {
        Invoke-WebRequest -Uri $url -OutFile $dst -UseBasicParsing
        $len = (Get-Item -LiteralPath $dst).Length
        if ($len -lt 200) { throw "받은 파일이 너무 작습니다 ($len bytes)" }
        $got += $rel
        Info ("{0}  ({1:N0} bytes)" -f $rel, $len)
    } catch {
        Fail "다운로드 실패: $rel`n     인터넷 연결 또는 기관 방화벽(github.com)을 확인하세요. ($($_.Exception.Message))"
    }
}
# 새 server.py 가 정말 새 판인지 (roster 를 쓰는지) 확인 — 캐시된 옛 파일이면 여기서 멈춘다
$srvText = Get-Content -LiteralPath (Join-Path $tmp 'slack-server\server.py') -Raw -Encoding UTF8
if ($srvText -notmatch 'from roster import') { Fail '받은 server.py 가 새 판이 아닙니다. 잠시 후 다시 실행해 보세요.' }

# ── 3. 백업하고 바꿔 넣기 ────────────────────────────────────
Step "바꾸기 전 파일 백업 → $bak"
foreach ($rel in $got) {
    $cur = Join-Path $Kit ($rel -replace '/', '\')
    if (Test-Path -LiteralPath $cur) {
        $b = Join-Path $bak ($rel -replace '/', '\')
        $null = New-Item -ItemType Directory -Path (Split-Path $b) -Force
        Copy-Item -LiteralPath $cur -Destination $b -Force
    }
}
Step '엔진 파일 교체'
foreach ($rel in $got) {
    $src = Join-Path $tmp ($rel -replace '/', '\')
    $dst = Join-Path $Kit ($rel -replace '/', '\')
    $null = New-Item -ItemType Directory -Path (Split-Path $dst) -Force
    Copy-Item -LiteralPath $src -Destination $dst -Force
}
Info ("{0}개 교체. personas.py · agent_channels.py · .env · 직원 · 스킬은 그대로입니다." -f $got.Count)
try { Remove-Item -LiteralPath (Join-Path $Srv '__pycache__') -Recurse -Force -ErrorAction SilentlyContinue } catch {}
try { Remove-Item -LiteralPath $tmp -Recurse -Force } catch {}

# ── 4. 어제 대화 끊기 ────────────────────────────────────────
Step '어제 대화 지우기 (새 대화로 시작)'
$sess = Join-Path $Srv '.agent_session.json'
if (Test-Path -LiteralPath $sess) { Remove-Item -LiteralPath $sess -Force; Info '저장된 대화를 지웠습니다. 잘못 기억한 이름·옛 요청이 여기서 끊깁니다.' }
else { Info '저장된 대화가 없습니다.' }

# ── 5. 강사 이름이 내 설정에 들어가 있는지 ──────────────────
Step '내 설정 파일에 강사 이름이 섞여 있는지 살펴보기'
$instructor = '김민주'
$suspects = @()
$cands = @(
    (Join-Path $env:USERPROFILE '.claude\CLAUDE.md'),
    (Join-Path $Kit 'CLAUDE.md'),
    (Join-Path $Kit 'workspace\memory\facts.md')
)
$memDir = Join-Path $env:USERPROFILE '.claude\projects'
if (Test-Path -LiteralPath $memDir) {
    $cands += @(Get-ChildItem -LiteralPath $memDir -Recurse -File -Include '*.md' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
}
$agentsDir = Join-Path $Kit '.claude\agents'
if (Test-Path -LiteralPath $agentsDir) {
    $cands += @(Get-ChildItem -LiteralPath $agentsDir -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
}
foreach ($f in $cands) {
    if ($f -and (Test-Path -LiteralPath $f)) {
        try {
            $t = Get-Content -LiteralPath $f -Raw -Encoding UTF8 -ErrorAction Stop
            if ($t -and $t.Contains($instructor)) { $suspects += $f }
        } catch {}
    }
}
if ($suspects.Count -gt 0) {
    Warn "아래 파일에 강사 이름($instructor)이 들어 있습니다. 내 이름이 맞는지 열어서 고치세요 (지우지는 않았습니다):"
    foreach ($f in $suspects) { Warn "  $f" }
} else { Info '없습니다.' }
$facts = Join-Path $Kit 'workspace\memory\facts.md'
if (-not (Test-Path -LiteralPath $facts)) {
    Warn 'workspace\memory\facts.md 가 없습니다 — 카드 P1 을 먼저 하세요. 이 파일의 "이름:" 줄로 직원이 나를 알아봅니다.'
}

# ── 6. 확인 ──────────────────────────────────────────────────
Step '확인 — py 점검.py 4'
Push-Location $Kit
try { & py -3 '점검.py' '4' | Out-Host } catch { Warn "점검을 못 돌렸습니다: $($_.Exception.Message)" }
Pop-Location

# ── 7. 서버 다시 켜기 ────────────────────────────────────────
Step '슬랙 서버를 새 창에서 켭니다'
if ($env:WD_NO_SERVER) {
    Info '서버 자동 기동은 건너뜁니다 (WD_NO_SERVER). slack-server 폴더에서 직접:  py -3 server.py'
} else {
    try {
        Start-Process -FilePath "$env:ComSpec" -ArgumentList '/k', 'chcp 65001 >nul & py -3 server.py' -WorkingDirectory $Srv
        Info '새 검은 창에 "✅ 준비 완료" 가 뜨면 됩니다. 그 창은 닫지 마세요.'
    } catch { Warn "서버를 자동으로 못 켰습니다. slack-server 폴더에서 직접:  py -3 server.py" }
}

Write-Host ''
Write-Host '  ✅ 업데이트 끝. 이제 이렇게 하세요' -ForegroundColor Green
Info '1) 슬랙 DM에  새 대화  라고 치세요 → "새 대화로 시작합니다. ○○ 대표님" 에 내 이름이 나오면 성공'
Info '2) 직원을 찍어 부르려면 문장 맨 앞에 이름:  교안담당 불러서 ○○ 해줘  /  @팀장 …'
Info '3) 이름·아이콘·인사말을 아직 안 정했으면 클로드에서 카드 P11(새 판)을 한 번 더 붙여넣으세요'
Info '   → 점검 결과에 ❌ 인사말 빈칸 이 떴다면 이게 그 처방입니다'
Info "백업: $bak"
Write-Host ''
Write-Host '  이 창은 닫아도 됩니다.' -ForegroundColor DarkGray
}
