<#
  install_starterkit.ps1

  더블클릭 설치용 본체.
  - C:\Agent 표준 구조를 만든다.
  - MyData\Proposal·Blog·Logo·Profile(제안서·블로그·로고·프로필) 폴더를 만들어 수강생이 미리 자료를 넣을 자리를 준다.
  - 현재 스타터킷을 01_KIT\starter-kit 으로 복사한다.
  - 이동을 느리게 하는 node_modules 및 재생성 파일은 복사하지 않는다.
  - 실제 비밀키와 로그인 상태는 복사하지 않는다.
  - 기존 설치가 있으면 덮어쓰지 않는다.
  - 끝나면 묻지 않고 환경점검(env_check.ps1)으로 넘어간다 — 프로그램·파이썬 3.14·꾸러미·슬랙 열쇠까지 자동.
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\Agent',
    [switch]$NoOpen,
    [switch]$SkipEnvironmentCheck
)

$ErrorActionPreference = 'Stop'
try {
    $null = & "$env:ComSpec" /c chcp 65001
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding = [Text.Encoding]::UTF8
} catch {}

try { $Host.UI.RawUI.WindowTitle = '위드드림 AI 에이전트팀 — 폴더 생성 및 설치' } catch {}
# 파워셸 창에서 claude 한 단어로 부를 수 있게 사용자 범위 실행 정책을 풀어 둔다 (회사 정책이면 조용히 실패)
try { if ((Get-ExecutionPolicy -Scope CurrentUser) -notin 'RemoteSigned','Unrestricted','Bypass') { Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force -ErrorAction Stop } } catch {}

$sourceKit = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetRoot = [IO.Path]::GetFullPath($InstallRoot)
$targetKit = Join-Path $targetRoot '01_KIT\starter-kit'
$marker = Join-Path $targetKit '환경점검.bat'
$logFile = Join-Path $targetRoot '설치결과.txt'

function Write-Step([string]$Text) {
    Write-Host ''
    Write-Host "  ▶ $Text" -ForegroundColor Magenta
}

function Write-Info([string]$Text) {
    Write-Host "     $Text" -ForegroundColor DarkGray
}

function Stop-WithMessage([string]$Text) {
    Write-Host ''
    Write-Host "  ❌ $Text" -ForegroundColor Red
    Write-Host ''
    $null = Read-Host '  이 창을 닫으려면 Enter'
    exit 1
}

Write-Host ''
Write-Host '  위드드림 AI 에이전트팀 — 폴더 생성 및 설치' -ForegroundColor Magenta
Write-Host "  설치 위치: $targetRoot" -ForegroundColor DarkGray

# ZIP 내부에서는 옆 파일을 안정적으로 읽지 못하므로 먼저 압축을 풀게 한다.
if (-not (Test-Path -LiteralPath (Join-Path $sourceKit 'env_check.ps1'))) {
    Stop-WithMessage '스타터킷이 완전히 풀리지 않았습니다. ZIP에서 모두 압축 풀기 후 다시 실행하세요.'
}

Write-Step '표준 폴더 만들기'
$folders = @(
    '00_README',
    '01_KIT',
    '02_INSTALLERS\Node22',
    '02_INSTALLERS\Python',
    '02_INSTALLERS\Git',
    '03_OFFLINE_PACKAGES',
    '04_LEARNER_BACKUP',
    '05_EXPORT\html',
    '05_EXPORT\pdf',
    '90_TEMP',
    'MyData\Proposal',
    'MyData\Blog',
    'MyData\Logo',
    'MyData\Profile'
)

try {
    foreach ($relative in $folders) {
        $path = Join-Path $targetRoot $relative
        $null = New-Item -ItemType Directory -Path $path -Force
    }
} catch {
    Stop-WithMessage "C: 드라이브에 폴더를 만들 수 없습니다. 기관 보안정책 또는 권한을 확인하세요. ($($_.Exception.Message))"
}
Write-Info "$($folders.Count)개 표준 폴더 확인"

# MyData 안내문 — 수강생이 수업 전에 뭘 어디에 넣을지
$guide = Join-Path $targetRoot 'MyData\여기에_넣으세요.txt'
if (-not (Test-Path -LiteralPath $guide)) {
    @(
        '내 자료 폴더 — 수업 전에 미리 넣어 두세요',
        '',
        '  Proposal\  제안서 — 내가 실제로 보낸 제안서 3개 (pptx·pdf·docx·hwp)',
        '  Blog\      블로그 — 내가 쓴 블로그 글 3개 (txt·docx·pdf, 또는 글 주소를 적은 txt)',
        '  Logo\      로고 — 회사 로고 1개 (png·jpg·svg). 명함·홈페이지 캡처도 됩니다',
        '  Profile\   프로필 — (선택) 강사 프로필·이력서 3개',
        '',
        '폴더 이름이 영문인 이유: 프로그램이 한글 경로에서 드물게 막히는 일을 없애기 위해서입니다.',
        '직원(AI)은 이 폴더를 읽기만 하고 원본을 고치지 않습니다.',
        '없는 것은 비워 두어도 수업은 진행됩니다. 모듈 3.5(내 자료) 전까지만 채우면 됩니다.'
    ) | Set-Content -LiteralPath $guide -Encoding UTF8
}
Write-Info "MyData 안내문: $guide"

Write-Step '가벼운 스타터킷 설치'
if (Test-Path -LiteralPath $marker) {
    Write-Host '  ⚠ 기존 스타터킷이 있어 덮어쓰지 않았습니다.' -ForegroundColor Yellow
    Write-Info $targetKit
} else {
    $excludedDirs = @(
        (Join-Path $sourceKit 'office\node_modules'),
        (Join-Path $sourceKit 'office\dist'),
        (Join-Path $sourceKit 'office\.wrangler'),
        (Join-Path $sourceKit '__pycache__'),
        (Join-Path $sourceKit 'slack-server\__pycache__'),
        (Join-Path $sourceKit 'slack-server\logs'),
        (Join-Path $sourceKit 'naver-blog\logs'),
        (Join-Path $sourceKit 'naver-blog\.naver-profile'),
        (Join-Path $sourceKit '.image-flow-profile'),
        (Join-Path $sourceKit 'backup')
    )

    $copyArgs = @(
        $sourceKit,
        $targetKit,
        '/E',
        '/R:1',
        '/W:1',
        '/XJ',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/NP',
        '/XD'
    ) + $excludedDirs + @(
        '/XF',
        '.env',
        '.agent_session.json',
        '.naver-state.json',
        '환경점검_결과.html',
        '*.pyc'
    )

    & robocopy @copyArgs | Out-Null
    $copyCode = $LASTEXITCODE
    if ($copyCode -gt 7) {
        Stop-WithMessage "스타터킷 복사에 실패했습니다. robocopy 종료코드: $copyCode"
    }
    if (-not (Test-Path -LiteralPath $marker)) {
        Stop-WithMessage '복사가 끝났지만 환경점검.bat을 찾지 못했습니다. 원본 ZIP을 다시 받으세요.'
    }

    $installedFiles = Get-ChildItem -LiteralPath $targetKit -File -Force -Recurse
    $installedBytes = ($installedFiles | Measure-Object Length -Sum).Sum
    Write-Host '  ✅ 스타터킷 복사 성공' -ForegroundColor Green
    Write-Info ("{0}개 파일 / {1:N1}MB" -f $installedFiles.Count, ($installedBytes / 1MB))
}

$readmeSource = Join-Path $targetKit 'README.md'
$readmeTarget = Join-Path $targetRoot '00_README\스타터킷_README.md'
if ((Test-Path -LiteralPath $readmeSource) -and -not (Test-Path -LiteralPath $readmeTarget)) {
    Copy-Item -LiteralPath $readmeSource -Destination $readmeTarget
}

$logLines = @(
    "설치일시=$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))",
    "원본=$sourceKit",
    "설치위치=$targetKit",
    '제외=node_modules, dist, .wrangler, cache, logs, .env, login profiles',
    '다음단계=01_KIT\starter-kit\환경점검.bat'
)
$logLines | Set-Content -LiteralPath $logFile -Encoding UTF8

Write-Step '설치 결과'
Write-Host "  ✅ 표준 폴더와 스타터킷 준비됨" -ForegroundColor Green
Write-Info "스타터킷: $targetKit"
Write-Info "기록: $logFile"
Write-Info "내 자료: $(Join-Path $targetRoot 'MyData') — 제안서 3·블로그 3·로고 1 을 수업 전에 넣어 두세요"
Write-Host ''
Write-Host '  node_modules는 이동 속도와 PC 호환성 문제 때문에 제외했습니다 (모듈 5에서 npm install).' -ForegroundColor Yellow

if (-not $NoOpen) {
    try { Start-Process explorer.exe -ArgumentList "`"$targetRoot`"" } catch {}
}

# 2026-09-07: 묻지 않고 바로 환경점검으로 넘어간다. 프로그램 설치·파이썬 3.14·꾸러미·슬랙 열쇠까지 거기서 끝낸다.
if (-not $SkipEnvironmentCheck) {
    Write-Step '이어서 환경점검·자동 설치를 시작합니다 (묻지 않습니다)'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $targetKit 'env_check.ps1') | Out-Host
}

Write-Host ''
Write-Host '  이 창은 닫아도 됩니다.' -ForegroundColor DarkGray
