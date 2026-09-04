# ============================================================
#  위드드림 AI 에이전트팀 스타터킷 — 한 줄 설치 (bootstrap)
#
#  수강생은 PowerShell 창에 아래 한 줄만 붙여넣습니다.
#    irm https://raw.githubusercontent.com/mandoo356/wd-agentteam-kit/main/install.ps1 | iex
#
#  하는 일
#    1) 깃허브에서 스타터킷(약 3MB, node_modules·비밀키 없음)을 받는다
#    2) C:\에이전트\01_KIT\starter-kit 에 표준 설치한다 (install_starterkit.ps1)
#       — 같이 만들어지는 C:\에이전트\내자료\ 에 수강생이 제안서·블로그·로고를 미리 넣는다
#    3) 환경점검(env_check.ps1)을 이어서 돌린다 — Node·Git·Claude Code 등은 여기서 명령어로 설치
#
#  테스트·강사용 환경변수 (선택)
#    $env:WD_KIT_ZIP      = 'C:\path\kit.zip'   깃허브 대신 로컬 ZIP 사용
#    $env:WD_INSTALL_ROOT = 'D:\에이전트'   설치 위치 변경
#    $env:WD_NO_ENVCHECK  = '1'                 환경점검 생략
#
#  이 파일은 UTF-8(BOM 없음)이며 raw.githubusercontent.com 이 charset=utf-8 로 내려준다.
# ============================================================

& {
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # PS 5.1 진행 막대는 다운로드를 수십 배 느리게 한다

try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
try { $null = & "$env:ComSpec" /c chcp 65001 } catch {}
try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding  = [Text.Encoding]::UTF8
} catch {}
try { $Host.UI.RawUI.WindowTitle = '위드드림 AI 에이전트팀 — 한 줄 설치' } catch {}

$Repo   = 'mandoo356/wd-agentteam-kit'
$Branch = 'main'
$ZipUrl = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

$Root = 'C:\에이전트'
if ($env:WD_INSTALL_ROOT) { $Root = $env:WD_INSTALL_ROOT }
$Root = [IO.Path]::GetFullPath($Root)
$Kit  = Join-Path $Root '01_KIT\starter-kit'

function Step([string]$t) { Write-Host ''; Write-Host "  ▶ $t" -ForegroundColor Magenta }
function Info([string]$t) { Write-Host "     $t" -ForegroundColor DarkGray }
function Fail([string]$t) {
    Write-Host ''
    Write-Host "  ❌ $t" -ForegroundColor Red
    Write-Host ''
    throw $t
}

# 아래 두 스크립트는 파일로 실행해야 하므로, 실행정책과 무관하게 돌도록 자식 powershell 로 띄운다.
# (같은 콘솔을 쓰므로 Y/n 질문·로그인 안내가 그대로 보인다)
function Run-Script([string]$Path, [string[]]$ScriptArgs) {
    $psExe = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $psExe)) { $psExe = 'powershell.exe' }
    # 자식 출력은 화면으로만 보내고(Out-Host), 함수의 반환값은 종료코드 하나만 남긴다
    & $psExe -NoProfile -ExecutionPolicy Bypass -File $Path @ScriptArgs | Out-Host
    return $LASTEXITCODE
}

$started = Get-Date
Write-Host ''
Write-Host '  위드드림 AI 에이전트팀 — 스타터킷 한 줄 설치' -ForegroundColor Magenta
Write-Host "  설치 위치: $Kit" -ForegroundColor DarkGray

if ($PSVersionTable.PSVersion.Major -lt 5) { Fail "PowerShell 5 이상이 필요합니다. 현재: $($PSVersionTable.PSVersion)" }

# ── 1. 작업 폴더 ─────────────────────────────────────────────
Step '작업 폴더 준비'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$tmp   = Join-Path $Root "90_TEMP\bootstrap-$stamp"
try {
    $null = New-Item -ItemType Directory -Path $tmp -Force
} catch {
    Fail "C: 드라이브에 폴더를 만들 수 없습니다. 기관 보안정책 또는 권한을 확인하세요. ($($_.Exception.Message))"
}
Info $tmp

# ── 2. 스타터킷 받기 ─────────────────────────────────────────
Step '스타터킷 받기'
$zip = Join-Path $tmp 'kit.zip'
if ($env:WD_KIT_ZIP) {
    if (-not (Test-Path -LiteralPath $env:WD_KIT_ZIP)) { Fail "WD_KIT_ZIP 파일이 없습니다: $env:WD_KIT_ZIP" }
    Copy-Item -LiteralPath $env:WD_KIT_ZIP -Destination $zip
    Info "로컬 ZIP 사용: $env:WD_KIT_ZIP"
} else {
    Info $ZipUrl
    try {
        Invoke-WebRequest -Uri $ZipUrl -OutFile $zip -UseBasicParsing
    } catch {
        Fail "다운로드에 실패했습니다. 인터넷 연결 또는 기관 방화벽(github.com)을 확인하세요. ($($_.Exception.Message))"
    }
}
$zipMB = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 2)
Info "받은 크기: ${zipMB}MB"

# ── 3. 압축 풀기 ─────────────────────────────────────────────
Step '압축 풀기'
$ext = Join-Path $tmp 'x'
try {
    Expand-Archive -LiteralPath $zip -DestinationPath $ext -Force
} catch {
    Fail "압축을 풀지 못했습니다. 백신이 막았거나 파일이 손상됐을 수 있습니다. ($($_.Exception.Message))"
}
$installer = Get-ChildItem -LiteralPath $ext -Recurse -File -Filter 'install_starterkit.ps1' | Select-Object -First 1
if (-not $installer) { Fail '받은 파일 안에 install_starterkit.ps1 이 없습니다. 원본이 바뀌었는지 강사에게 알려주세요.' }
$srcKit = $installer.DirectoryName
$srcCount = (Get-ChildItem -LiteralPath $srcKit -File -Force -Recurse | Measure-Object).Count
Info "스타터킷 파일 $srcCount 개 확인"

# ── 4. 표준 위치에 설치 ─────────────────────────────────────
Step 'C:\에이전트 표준 폴더 만들고 스타터킷 설치'
$code = Run-Script $installer.FullName @('-InstallRoot', $Root, '-NoOpen', '-SkipEnvironmentCheck')
if ($code -ne 0) { Fail "설치 스크립트가 실패했습니다 (종료코드 $code)." }
if (-not (Test-Path -LiteralPath (Join-Path $Kit '환경점검.bat'))) { Fail "설치 후 $Kit 에 환경점검.bat 이 없습니다." }
$dstCount = (Get-ChildItem -LiteralPath $Kit -File -Force -Recurse | Measure-Object).Count
Info "설치된 파일 $dstCount 개"

# ── 5. 정리 ──────────────────────────────────────────────────
try { Remove-Item -LiteralPath $tmp -Recurse -Force } catch {}

$elapsed = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
Write-Host ''
Write-Host "  ✅ 스타터킷 설치 완료 ($elapsed 초)" -ForegroundColor Green
Info "위치: $Kit"
Info "다음: 환경점검 → 카드 P0 부터"
Info "내 자료: $Root\내자료 에 제안서 3·블로그 3·로고 1 을 수업 전에 넣어 두세요"

# ── 6. 환경점검 이어서 ───────────────────────────────────────
if ($env:WD_NO_ENVCHECK) {
    Info '환경점검은 건너뜁니다 (WD_NO_ENVCHECK).'
} else {
    Step '환경점검 시작 — Node·Git·Claude Code 가 없으면 명령어로 설치합니다 (Y 만 누르세요)'
    $null = Run-Script (Join-Path $Kit 'env_check.ps1') @()
}

Write-Host ''
Write-Host '  이 창은 닫아도 됩니다.' -ForegroundColor DarkGray
}
