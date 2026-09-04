<#
  env_check.ps1 — 「에이전트팀 만들기 과정」 출발선 자동 점검

  무엇을 하나
    1) 필요한 프로그램(Node·Python·Git·Claude Code…)이 깔렸는지, 버전이 맞는지 본다
    2) 빠진 것은 winget / npm / pip 으로 자동 설치한다 (묻고 진행)
    3) 로그인이 필요한 것(Claude Code·슬랙 열쇠·Google Flow·네이버)은 그 화면을 바로 띄운다
    4) 결과 체크리스트를 검은 창과 HTML(환경점검_결과.html)로 보여준다

  실행
    환경점검.bat 더블클릭  ← 이게 전부입니다
    (직접)  powershell -NoProfile -ExecutionPolicy Bypass -File env_check.ps1

  옵션 (강사·테스트용)
    -SkipInstall      자동 설치 안 함
    -SkipLogin        로그인 창 안 띄움
    -NoBrowser        HTML·안내 페이지 안 열음
    -NoPause          끝나고 Enter 대기 안 함
    -Yes              모든 질문에 Y
    -PretendMissing   테스트용 — 특정 항목을 "없는 것"으로 가정
                      예) -PretendMissing node,git,claude-login

  🔒 이 파일은 .env 의 열쇠 값을 절대 읽어 화면에 찍지 않습니다. 키 이름과 모양만 봅니다.
  🔒 로그인은 항상 사람이 직접 합니다. 비밀번호를 대신 입력하지 않습니다.
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipLogin,
    [switch]$NoBrowser,
    [switch]$NoPause,
    [switch]$Yes,
    [string[]]$PretendMissing = @()
)

# ── 0. 콘솔 준비 ──────────────────────────────────────────────
$ErrorActionPreference = 'Continue'
# -File 로 넘어오면 "node,git" 이 한 덩어리로 들어오므로 콤마를 잘라 준다
$PretendMissing = @($PretendMissing | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
try { $null = & "$env:ComSpec" /c chcp 65001 } catch {}
try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    [Console]::InputEncoding  = [Text.Encoding]::UTF8
} catch {}
try { $Host.UI.RawUI.WindowTitle = '에이전트팀 만들기 — 환경 점검' } catch {}

$KIT    = Split-Path -Parent $MyInvocation.MyCommand.Path
$COURSE = Split-Path -Parent $KIT
$USERHOME = $env:USERPROFILE
$REPORT = Join-Path $KIT '환경점검_결과.html'
$STARTED = Get-Date

$OKM = [char]0x2705   # ✅
$NOM = [char]0x274C   # ❌
$WRN = [char]0x26A0   # ⚠

# ── 1. 도우미 ────────────────────────────────────────────────
function Write-Step([string]$t) { Write-Host ''; Write-Host "  ▶ $t" -ForegroundColor Magenta }
function Write-Info([string]$t) { Write-Host "     $t" -ForegroundColor DarkGray }
function Write-Warn([string]$t) { Write-Host "     $WRN $t" -ForegroundColor Yellow }

function Ask-YesNo([string]$q, [bool]$default = $true) {
    if ($Yes) { return $true }
    $hint = '[y/N]'; if ($default) { $hint = '[Y/n]' }
    $a = Read-Host "  ? $q $hint"
    if ([string]::IsNullOrWhiteSpace($a)) { return $default }
    return $a.Trim().ToLower().StartsWith('y')
}

function Wait-Enter([string]$msg) {
    if ($Yes) { return }
    $null = Read-Host "  ⏎ $msg (Enter)"
}

function Invoke-Cmd {
    # cmd.exe 로 한 줄을 실행해 출력·종료코드를 돌려준다. 멈추면 시간 초과로 끊는다.
    param([string]$Line, [int]$TimeoutSec = 30)
    $tmp = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $env:ComSpec -ArgumentList "/d /s /c `"$Line 2>&1`"" `
                -RedirectStandardOutput $tmp -NoNewWindow -PassThru
        # PowerShell 5.1 함정: Handle 을 먼저 읽어두지 않으면 ExitCode 가 $null 로 나온다.
        $null = $p.Handle
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            try { $p.Kill() } catch {}
            return @{ ok = $false; code = -2; out = '(시간 초과)' }
        }
        $out = ''
        try { $out = [IO.File]::ReadAllText($tmp, [Text.Encoding]::UTF8).Trim() } catch {}
        $code = $p.ExitCode
        if ($code -eq $null) {
            # 그래도 비면 출력으로 판정 (cmd 의 "인식되지 않습니다" 메시지가 없으면 성공으로 본다)
            $code = 1
            if ($out -and $out -notmatch 'is not recognized|인식되지 않|not found|찾을 수 없') { $code = 0 }
        }
        return @{ ok = ($code -eq 0); code = $code; out = $out }
    } catch {
        return @{ ok = $false; code = -1; out = "$_" }
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

function First-Line([string]$s) { if (-not $s) { return '' }; return ($s -split "`r?`n")[0].Trim() }

function Get-Ver([string]$text) {
    if ($text -match '(\d+)\.(\d+)(?:\.(\d+))?') {
        $patch = 0; if ($Matches[3]) { $patch = $Matches[3] }
        return [version]('{0}.{1}.{2}' -f $Matches[1], $Matches[2], $patch)
    }
    return $null
}

function Has-Cmd([string]$name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    return $null
}

function Refresh-Path {
    $m = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $u = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$m;$u"
}

function Open-Url([string]$url) {
    if ($NoBrowser) { Write-Info "(브라우저 생략) $url"; return }
    try { Start-Process $url } catch { Write-Warn "열 수 없음: $url" }
}

function Open-NewWindow([string]$title, [string]$cmdline, [string]$workdir = $KIT) {
    # 사람이 직접 조작해야 하는 명령(로그인 등)은 별도 검은 창에 띄운다.
    if ($SkipLogin) { Write-Info "(로그인 창 생략) $cmdline"; return }
    try {
        Start-Process -FilePath $env:ComSpec -ArgumentList "/k title $title && $cmdline" -WorkingDirectory $workdir
    } catch { Write-Warn "창을 열 수 없음: $_" }
}

# ── 2. 결과 저장소 ───────────────────────────────────────────
$script:Results = New-Object System.Collections.ArrayList

function Set-Result {
    param([string]$Id, [string]$Name, [string]$Group, [bool]$Ok, [string]$Detail,
          [string]$Fix = '', [string]$Url = '')
    if ($PretendMissing -contains $Id) { $Ok = $false; $Detail = "(테스트) 없는 것으로 가정 — $Detail" }
    $row = [pscustomobject]@{ Id=$Id; Name=$Name; Group=$Group; Ok=$Ok; Detail=$Detail; Fix=$Fix; Url=$Url }
    $i = -1
    for ($k = 0; $k -lt $script:Results.Count; $k++) { if ($script:Results[$k].Id -eq $Id) { $i = $k } }
    if ($i -ge 0) { $script:Results[$i] = $row } else { $null = $script:Results.Add($row) }
    $mark = $NOM; $color = 'Red'
    if ($Ok) { $mark = $OKM; $color = 'Green' }
    Write-Host ("  {0}  {1}" -f $mark, $Name) -ForegroundColor $color
    if ($Detail) { Write-Host ("        └ {0}" -f $Detail) -ForegroundColor DarkGray }
    return $Ok
}
function Get-Result([string]$Id) { foreach ($r in $script:Results) { if ($r.Id -eq $Id) { return $r } }; return $null }
function Is-Ok([string]$Id) { $r = Get-Result $Id; return ($r -and $r.Ok) }

# ── 3. 개별 검사 ─────────────────────────────────────────────
function Check-Internet {
    foreach ($h in 'claude.ai', 'nodejs.org', 'www.google.com') {
        try {
            $c = New-Object Net.Sockets.TcpClient
            $ar = $c.BeginConnect($h, 443, $null, $null)
            $done = $ar.AsyncWaitHandle.WaitOne(3000)
            if ($done -and $c.Connected) { $c.Close(); return (Set-Result 'internet' '인터넷 연결' '기본' $true "$h 연결됨") }
            $c.Close()
        } catch {}
    }
    Set-Result 'internet' '인터넷 연결' '기본' $false 'Wi-Fi/랜선을 확인하세요 — 설치와 로그인 모두 인터넷이 필요합니다'
}

function Check-Disk {
    try {
        $drive = Get-PSDrive -Name $KIT.Substring(0, 1) -ErrorAction Stop
        $gb = [math]::Round($drive.Free / 1GB, 1)
        Set-Result 'disk' '디스크 여유 3GB 이상' '기본' ($gb -ge 3) "$($drive.Name): 드라이브 여유 ${gb}GB (설치 1.6GB + 스타터킷 0.7GB)"
    } catch { Set-Result 'disk' '디스크 여유 3GB 이상' '기본' $true '확인 불가 — 건너뜁니다' }
}

function Check-Node {
    $r = Invoke-Cmd 'node -v'
    if (-not $r.ok -or -not $r.out) {
        return (Set-Result 'node' 'Node.js 22 이상' '필수' $false '설치 안 됨' 'nodejs.org 에서 LTS 설치' 'https://nodejs.org/ko/download')
    }
    $v = Get-Ver $r.out
    $ok = ($v -ne $null -and $v.Major -ge 22)
    $d = (First-Line $r.out); if (-not $ok) { $d += ' → 22 이상 필요. nodejs.org 에서 LTS 를 덮어 설치' }
    Set-Result 'node' 'Node.js 22 이상' '필수' $ok $d 'nodejs.org 에서 LTS 설치' 'https://nodejs.org/ko/download'
}

function Check-Npm {
    $r = Invoke-Cmd 'npm -v'
    $ok = ($r.ok -and $r.out -and (Get-Ver $r.out) -ne $null)
    $d = 'Node.js 를 깔면 같이 들어옵니다'; if ($ok) { $d = 'npm ' + (First-Line $r.out) }
    Set-Result 'npm' 'npm (Claude Code 설치용)' '필수' $ok $d 'Node.js 다시 설치' 'https://nodejs.org/ko/download'
}

function Check-Python {
    $r = Invoke-Cmd 'py -3 -V'
    $launcher = 'py -3'
    if (-not $r.ok -or $r.out -notmatch 'Python') { $r = Invoke-Cmd 'python -V'; $launcher = 'python' }
    if (-not $r.ok -or $r.out -notmatch 'Python') {
        return (Set-Result 'python' 'Python 3.11 이상' '필수' $false '설치 안 됨 (또는 PATH 미체크)' '설치 시 "Add python.exe to PATH" 체크' 'https://www.python.org/downloads/windows/')
    }
    $v = Get-Ver $r.out
    $ok = ($v -ne $null -and (($v.Major -gt 3) -or ($v.Major -eq 3 -and $v.Minor -ge 11)))
    $d = "$(First-Line $r.out) ($launcher)"
    if (-not $ok) { $d += ' → 3.11 이상 필요' }
    # py -3 와 python 이 다른 버전을 가리키면 알려만 준다 (수업은 py -3 기준)
    if ($launcher -eq 'py -3') {
        $r2 = Invoke-Cmd 'python -V'
        if ($r2.ok -and $r2.out -match 'Python' -and (First-Line $r2.out) -ne (First-Line $r.out)) {
            $d += " / 참고: 'python' 은 $(First-Line $r2.out) — 수업은 py -3 로 통일"
        }
    }
    $script:PY = $launcher
    Set-Result 'python' 'Python 3.11 이상' '필수' $ok $d '설치 시 "Add python.exe to PATH" 체크' 'https://www.python.org/downloads/windows/'
}

function Check-Pip {
    if (-not $script:PY) { return (Set-Result 'pip' 'pip (파이썬 꾸러미 설치 도구)' '필수' $false 'Python 먼저') }
    $r = Invoke-Cmd "$($script:PY) -m pip --version"
    $ok = ($r.ok -and $r.out -match 'pip')
    $d = 'pip 이 없습니다 → Python 재설치'; if ($ok) { $d = First-Line $r.out }
    Set-Result 'pip' 'pip (파이썬 꾸러미 설치 도구)' '필수' $ok $d
}

function Check-Git {
    $r = Invoke-Cmd 'git --version'
    $ok = ($r.ok -and $r.out -match 'git version')
    $d = '설치 안 됨'; if ($ok) { $d = First-Line $r.out }
    Set-Result 'git' 'Git' '필수' $ok $d 'git-scm.com 에서 설치 (기본값으로 Next 만)' 'https://git-scm.com/download/win'
}

function Check-Claude {
    $exe = Has-Cmd 'claude'
    if (-not $exe) { $exe = Has-Cmd 'claude.cmd' }
    if ($exe) {
        $r = Invoke-Cmd 'claude --version' 40
        $d = First-Line $r.out; if (-not $d) { $d = $exe }
        return (Set-Result 'claude' 'Claude Code 설치' '필수' $true $d)
    }
    $codex = Has-Cmd 'codex'
    if ($codex) { return (Set-Result 'claude' 'Claude Code 설치' '필수' $true "codex 로 대체 확인 ($codex) — 수업은 Claude Code 기준") }
    Set-Result 'claude' 'Claude Code 설치' '필수' $false '설치 안 됨' 'npm install -g @anthropic-ai/claude-code' 'https://docs.claude.com/en/docs/claude-code/setup'
}

function Check-ClaudeLogin([switch]$Quiet) {
    if (-not (Is-Ok 'claude')) {
        if ($Quiet) { return $false }
        return (Set-Result 'claude-login' 'Claude Code 로그인 (claude.ai 유료 계정)' '필수' $false 'Claude Code 먼저 설치' '' 'https://claude.ai/')
    }
    $r = Invoke-Cmd 'claude auth status' 40
    $logged = $false; $d = '로그인 안 됨'
    try {
        $j = $r.out | ConvertFrom-Json
        if ($j.loggedIn -eq $true) {
            $logged = $true
            $d = "로그인됨"
            if ($j.email) { $d += " — $($j.email)" }
            if ($j.subscriptionType) { $d += " ($($j.subscriptionType))" }
        }
    } catch {
        if ($r.out -match '"loggedIn"\s*:\s*true') { $logged = $true; $d = '로그인됨' }
    }
    if ($Quiet) { return $logged }
    Set-Result 'claude-login' 'Claude Code 로그인 (claude.ai 유료 계정)' '필수' $logged $d 'claude auth login' 'https://claude.ai/'
}

function Check-PyPackages {
    $req = @('slack_bolt', 'slack_sdk', 'aiohttp', 'dotenv', 'claude_agent_sdk')
    if (-not (Is-Ok 'python')) {
        Set-Result 'pypkg' '파이썬 꾸러미 5개 (slack-bolt·slack-sdk·aiohttp·python-dotenv·claude-agent-sdk)' '필수' $false 'Python 먼저'
        Set-Result 'playwright' 'playwright 패키지 (블로그·이미지 스킬용)' '선택' $false 'Python 먼저'
        return
    }
    $tmp = Join-Path $env:TEMP 'wd_envcheck_mods.py'
    @'
import importlib.util as u
mods = ["slack_bolt","slack_sdk","aiohttp","dotenv","claude_agent_sdk","playwright"]
print(" ".join(m + "=" + ("O" if u.find_spec(m) else "X") for m in mods))
'@ | Set-Content -Path $tmp -Encoding ASCII
    $r = Invoke-Cmd "$($script:PY) `"$tmp`"" 40
    Remove-Item $tmp -ErrorAction SilentlyContinue
    $missing = @(); $have = @{}
    foreach ($tok in ($r.out -split '\s+')) {
        if ($tok -match '^(\w+)=(O|X)$') { $have[$Matches[1]] = ($Matches[2] -eq 'O') }
    }
    foreach ($m in $req) { if (-not $have[$m]) { $missing += $m } }
    if ($have.Count -eq 0) {
        Set-Result 'pypkg' '파이썬 꾸러미 5개 (slack-bolt·slack-sdk·aiohttp·python-dotenv·claude-agent-sdk)' '필수' $false "확인 실패: $(First-Line $r.out)"
        Set-Result 'playwright' 'playwright 패키지 (블로그·이미지 스킬용)' '선택' $false '확인 실패'
        return
    }
    $d = '5개 모두 설치됨'; if ($missing.Count) { $d = '빠짐: ' + ($missing -join ', ') }
    Set-Result 'pypkg' '파이썬 꾸러미 5개 (slack-bolt·slack-sdk·aiohttp·python-dotenv·claude-agent-sdk)' '필수' ($missing.Count -eq 0) $d "py -3 -m pip install -r slack-server\requirements.txt"
    $pd = 'pip install playwright'; if ($have['playwright']) { $pd = '설치됨' }
    Set-Result 'playwright' 'playwright 패키지 (블로그·이미지 스킬용)' '선택' ([bool]$have['playwright']) $pd 'py -3 -m pip install playwright'
}

function Check-Folders {
    $need = @('.claude\agents', '.claude\skills', 'workspace\inbox', 'workspace\memory', 'slack-server\server.py', '점검.py')
    $missing = @($need | Where-Object { -not (Test-Path (Join-Path $KIT $_)) })
    $d = "정상 — $KIT"; if ($missing.Count) { $d = '없음: ' + ($missing -join ', ') + ' — 스타터킷 압축을 다시 푸세요' }
    Set-Result 'folders' '스타터킷 폴더 구조' '필수' ($missing.Count -eq 0) $d
}

function Check-MyData {
    # 표준 설치(C:\에이전트\01_KIT\starter-kit)면 두 단계 위가 회사 건물 — 그 안의 내자료\ 를 센다
    $root = Split-Path -Parent $COURSE
    $base = Join-Path $root '내자료'
    if ((Split-Path -Leaf $COURSE) -ne '01_KIT' -or -not (Test-Path $base)) {
        Set-Result 'mydata' '내 자료 (제안서 3·블로그 3·로고 1)' '선택' $false '내자료 폴더 없음 — 표준 설치가 아니면 건너뜁니다'
        return
    }
    $n = @{}
    foreach ($k in '제안서','블로그','로고','프로필') {
        $n[$k] = @(Get-ChildItem -LiteralPath (Join-Path $base $k) -File -ErrorAction SilentlyContinue).Count
    }
    $ok = ($n['제안서'] -ge 3) -and ($n['블로그'] -ge 3) -and ($n['로고'] -ge 1)
    $d = "제안서 $($n['제안서'])개 · 블로그 $($n['블로그'])개 · 로고 $($n['로고'])개 · 프로필 $($n['프로필'])개 — $base"
    Set-Result 'mydata' '내 자료 (제안서 3·블로그 3·로고 1)' '선택' $ok $d "$base 에 파일을 넣으세요 (모듈 3.5 전까지)"
}

function Check-SlackEnv {
    # 🔒 값은 절대 화면에 찍지 않는다. 키 이름과 앞머리(xoxb-/xapp-)만 본다.
    $env_ = Join-Path $KIT 'slack-server\.env'
    $fix = '04_슬랙앱_안내문 대로 앱을 만들고 .env 에 열쇠 2개를 넣습니다 (모듈 4 전까지)'
    $url = 'https://api.slack.com/apps'
    if (-not (Test-Path $env_)) {
        $stray = @(Get-ChildItem (Join-Path $KIT 'slack-server') -Filter '.env.*' -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -ne '.env.example' })
        $d = '.env 파일이 아직 없습니다'
        if ($stray.Count) { $d = ".env 대신 $($stray[0].Name) 로 저장돼 있습니다 — 확장자를 지우세요" }
        return (Set-Result 'slack' '슬랙 열쇠 2개 (.env) — 모듈 4 전까지' '필수' $false $d $fix $url)
    }
    $vals = @{}
    foreach ($line in (Get-Content $env_ -Encoding UTF8 -ErrorAction SilentlyContinue)) {
        $l = $line -replace '^﻿', ''
        if ($l.Trim().StartsWith('#') -or $l -notmatch '=') { continue }
        $k, $v = $l -split '=', 2
        $vals[$k.Trim().ToUpper()] = $v
    }
    $problems = @()
    foreach ($pair in @(@('SLACK_BOT_TOKEN', 'xoxb-'), @('SLACK_APP_TOKEN', 'xapp-'))) {
        $key = $pair[0]; $head = $pair[1]
        if (-not $vals.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($vals[$key])) { $problems += "$key 비어 있음"; continue }
        $raw = $vals[$key]; $v = $raw.Trim()
        if ($v.StartsWith('"') -or $v.StartsWith("'") -or $v.EndsWith('"') -or $v.EndsWith("'")) { $problems += "$key 따옴표 지우세요"; continue }
        if ($raw -ne $v) { $problems += "$key 앞뒤 공백 지우세요"; continue }
        if (-not $v.StartsWith($head)) {
            $other = 'xoxb-'; if ($head -eq 'xoxb-') { $other = 'xapp-' }
            if ($v.StartsWith($other)) { $problems += "$key 자리에 $other 가 들어갔습니다 (둘이 바뀜)" } else { $problems += "$key 는 $head 로 시작해야 합니다" }
        }
    }
    $d = '열쇠 2개 모양 정상 (값은 확인하지 않습니다)'; if ($problems.Count) { $d = $problems -join ' / ' }
    Set-Result 'slack' '슬랙 열쇠 2개 (.env) — 모듈 4 전까지' '필수' ($problems.Count -eq 0) $d $fix $url
}

function Check-VSCode {
    $p = Has-Cmd 'code'
    if (-not $p) { foreach ($c in @("$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe", "$env:ProgramFiles\Microsoft VS Code\Code.exe")) { if (Test-Path $c) { $p = $c } } }
    $d = '없어도 실습됩니다 (약 350MB)'; if ($p) { $d = $p }
    Set-Result 'vscode' 'VS Code' '선택' ([bool]$p) $d 'code.visualstudio.com' 'https://code.visualstudio.com/'
}

function Check-Chrome {
    $p = $null
    foreach ($c in @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")) { if (Test-Path $c) { $p = $c } }
    $d = '네이버 블로그·Google Flow 스킬이 실제 Chrome 을 씁니다'; if ($p) { $d = $p }
    Set-Result 'chrome' 'Google Chrome (블로그·이미지 스킬용)' '선택' ([bool]$p) $d 'google.com/chrome' 'https://www.google.com/chrome/'
}

function Check-FlowLogin {
    $prof = Join-Path $USERHOME '.claude\.image-flow-profile'
    $ok = (Test-Path $prof) -and (@(Get-ChildItem $prof -Force -ErrorAction SilentlyContinue).Count -gt 0)
    $d = '아직 로그인 안 함 (Gemini 구독 계정 필요, 세션 약 8시간)'; if ($ok) { $d = "로그인 기록 있음 — $prof" }
    Set-Result 'flow-login' 'Google Flow 로그인 (이미지 스킬)' '선택' $ok $d 'py -3 flow-image-JJ\scripts\flow_login.py' 'https://labs.google/fx/tools/flow'
}

function Check-NaverLogin {
    $state = Join-Path $KIT 'naver-blog\.naver-state.json'
    $ok = Test-Path $state
    $d = '아직 로그인 안 함'; if ($ok) { $d = '세션 파일 있음 (.naver-state.json)' }
    Set-Result 'naver-login' '네이버 블로그 로그인 (블로그 스킬)' '선택' $ok $d 'py -3 naver-blog\naver_draft.py login --blog-id 내아이디' 'https://blog.naver.com/'
}

# ── 4. 고치기 (설치·로그인) ───────────────────────────────────
function Install-WithWinget([string]$id, [string]$label, [string]$override = '') {
    Write-Info "winget 으로 $label 설치 중… (몇 분 걸립니다)"
    $wargs = @('install', '--exact', '--id', $id, '--accept-package-agreements', '--accept-source-agreements', '--silent')
    if ($override) { $wargs += @('--override', $override) }
    try { & winget @wargs } catch { Write-Warn "winget 실패: $_" }
    Refresh-Path
}

function Fix-Programs {
    $todo = @()
    if (-not (Is-Ok 'node'))   { $todo += @{ id = 'OpenJS.NodeJS.LTS';  label = 'Node.js LTS'; ov = '' } }
    if (-not (Is-Ok 'python')) { $todo += @{ id = 'Python.Python.3.13'; label = 'Python 3.13'; ov = '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1' } }
    if (-not (Is-Ok 'git'))    { $todo += @{ id = 'Git.Git';            label = 'Git';         ov = '' } }
    if ($todo.Count -eq 0) { return }

    Write-Step "빠진 프로그램 $($todo.Count)개: $(($todo | ForEach-Object { $_.label }) -join ', ')"
    $winget = Has-Cmd 'winget'
    if ($SkipInstall) { Write-Info '(-SkipInstall) 자동 설치 생략'; return }
    if ($winget -and (Ask-YesNo '지금 자동으로 설치할까요? (winget 사용, 몇 분 소요)')) {
        foreach ($t in $todo) { Install-WithWinget $t.id $t.label $t.ov }
        Write-Info '설치 후 다시 확인합니다'
        if (-not (Is-Ok 'node'))   { Check-Node | Out-Null; Check-Npm | Out-Null }
        if (-not (Is-Ok 'python')) { Check-Python | Out-Null; Check-Pip | Out-Null }
        if (-not (Is-Ok 'git'))    { Check-Git | Out-Null }
    } else {
        if (-not $winget) { Write-Warn 'winget 이 없어 자동 설치가 안 됩니다. 다운로드 페이지를 엽니다.' }
        foreach ($t in $todo) {
            $r = $null
            switch ($t.label) { 'Node.js LTS' { $r = Get-Result 'node' } 'Python 3.13' { $r = Get-Result 'python' } 'Git' { $r = Get-Result 'git' } }
            if ($r -and $r.Url) { Open-Url $r.Url }
        }
        Write-Info '설치가 끝나면 이 프로그램을 다시 실행하세요 (검은 창을 새로 여는 효과가 있습니다).'
    }
}

function Fix-Claude {
    if (Is-Ok 'claude') { return }
    if (-not (Is-Ok 'npm')) { Write-Warn 'npm 이 없어 Claude Code 를 설치할 수 없습니다. Node.js 부터.'; return }
    if ($SkipInstall) { Write-Info '(-SkipInstall) Claude Code 설치 생략'; return }
    Write-Step 'Claude Code 설치'
    if (Ask-YesNo 'npm install -g @anthropic-ai/claude-code 를 지금 실행할까요? (약 610MB)') {
        try { & npm install -g @anthropic-ai/claude-code } catch { Write-Warn "npm 실패: $_" }
        Refresh-Path
        Check-Claude | Out-Null
    }
}

function Fix-ClaudeLogin {
    if ((Is-Ok 'claude-login') -or -not (Is-Ok 'claude')) { return }
    if ($SkipLogin) { Write-Info '(-SkipLogin) 로그인 생략'; return }
    Write-Step 'Claude Code 로그인 — 새 창과 브라우저가 열립니다'
    Write-Info '브라우저에서 claude.ai 계정(유료 구독)으로 로그인하고, 코드가 나오면 검은 창에 붙여넣으세요.'
    Write-Info '이 창은 로그인이 끝나는 걸 자동으로 감지합니다 (최대 10분).'
    Open-NewWindow 'Claude-Code-로그인' 'claude auth login'
    $deadline = (Get-Date).AddMinutes(10)
    $logged = $false
    while ((Get-Date) -lt $deadline) {
        if (Check-ClaudeLogin -Quiet) { $logged = $true; break }
        Write-Host -NoNewline '.' -ForegroundColor DarkGray
        Start-Sleep -Seconds 5
    }
    Write-Host ''
    if (-not $logged) { Write-Warn '10분 안에 로그인이 확인되지 않았습니다. 로그인 후 다시 실행하세요.' }
    Check-ClaudeLogin | Out-Null
}

function Fix-PyPackages {
    if ((Is-Ok 'pypkg') -or -not (Is-Ok 'pip')) { return }
    if ($SkipInstall) { Write-Info '(-SkipInstall) 꾸러미 설치 생략'; return }
    $req = Join-Path $KIT 'slack-server\requirements.txt'
    if (-not (Test-Path $req)) { Write-Warn "requirements.txt 가 없습니다: $req"; return }
    Write-Step '파이썬 꾸러미 5개 설치'
    if (Ask-YesNo "$($script:PY) -m pip install -r slack-server\requirements.txt 를 지금 실행할까요?") {
        $parts = @($script:PY -split ' ')
        $pyArgs = @(); if ($parts.Count -gt 1) { $pyArgs = @($parts[1..($parts.Count - 1)]) }
        try { & $parts[0] @pyArgs -m pip install -r $req } catch { Write-Warn "pip 실패: $_" }
        Check-PyPackages | Out-Null
    }
}

function Fix-Slack {
    if (Is-Ok 'slack') { return }
    if ($SkipLogin) { Write-Info '(-SkipLogin) 슬랙 설정 생략'; return }
    Write-Step '슬랙 열쇠 넣기 — 안내문과 .env 를 엽니다'
    $srv = Join-Path $KIT 'slack-server'
    $envf = Join-Path $srv '.env'
    $example = Join-Path $srv '.env.example'
    if (-not (Test-Path $envf) -and (Test-Path $example)) { Copy-Item $example $envf; Write-Info '.env.example 을 복사해 .env 를 만들었습니다' }
    $guide = Get-ChildItem $COURSE -Filter '04_슬랙앱_안내문*_WD.html' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $guide) { $guide = Get-ChildItem $COURSE -Filter '04_슬랙앱_안내문*.html' -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if ($guide) { Open-Url $guide.FullName } else { Write-Info '안내문 HTML 이 근처에 없어 슬랙 앱 페이지만 엽니다' }
    Open-Url 'https://api.slack.com/apps'
    if (-not $NoBrowser -and (Test-Path $envf)) { try { Start-Process notepad.exe $envf } catch {} }
    Write-Info '① 슬랙 워크스페이스는 회사 것 말고 본인 것으로 새로 만듭니다 (slack.com/get-started)'
    Write-Info '② 안내문대로 앱을 만들어 xoxb- 와 xapp- 열쇠를 받습니다'
    Write-Info '③ 메모장에 열린 .env 의 SLACK_BOT_TOKEN= / SLACK_APP_TOKEN= 뒤에 붙이고 저장(Ctrl+S)'
    if ($Yes) { Check-SlackEnv | Out-Null; return }
    while ($true) {
        $a = Read-Host '  ⏎ 열쇠를 넣고 저장했으면 Enter, 나중에 하려면 S 를 치고 Enter'
        if ($a.Trim().ToLower() -eq 's') { Write-Info '슬랙은 모듈 4 전까지만 준비하면 됩니다.'; break }
        if (Check-SlackEnv) { break }
    }
}

function Fix-OptionalLogins {
    if ($SkipLogin) { return }
    if (-not ((Is-Ok 'python') -and (Is-Ok 'playwright') -and (Is-Ok 'chrome'))) { return }
    if (-not (Is-Ok 'flow-login')) {
        $script_ = Join-Path $KIT 'flow-image-JJ\scripts\flow_login.py'
        if ((Test-Path $script_) -and (Ask-YesNo 'Google Flow(이미지 스킬) 로그인 창을 지금 띄울까요? (Gemini 구독 계정 필요)' $false)) {
            Open-NewWindow 'Google-Flow-로그인' "$($script:PY) `"$script_`"" (Split-Path $script_)
            Wait-Enter '크롬 창에서 Google 로그인을 마치고 "[OK] 로그인 완료" 가 뜨면'
            Check-FlowLogin | Out-Null
        }
    }
    if (-not (Is-Ok 'naver-login')) {
        $script_ = Join-Path $KIT 'naver-blog\naver_draft.py'
        if ((Test-Path $script_) -and (Ask-YesNo '네이버 블로그(블로그 스킬) 로그인 창을 지금 띄울까요?' $false)) {
            $bid = Read-Host '  ? 네이버 블로그 아이디 (blog.naver.com/뒤에 오는 것, 비우면 건너뜀)'
            if (-not [string]::IsNullOrWhiteSpace($bid)) {
                Open-NewWindow 'Naver-Blog-로그인' "$($script:PY) `"$script_`" login --blog-id $($bid.Trim())" (Split-Path $script_)
                Wait-Enter '크롬 창에서 네이버 로그인을 마치고 "[OK]" 가 뜨면'
                Check-NaverLogin | Out-Null
            }
        }
    }
}

# ── 5. 결과 HTML ─────────────────────────────────────────────
$WD_SYMBOL_B64 = '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'

function Html([string]$s) { return [System.Net.WebUtility]::HtmlEncode($s) }

function Write-Report {
    $req = @($script:Results | Where-Object { $_.Group -ne '선택' })
    $opt = @($script:Results | Where-Object { $_.Group -eq '선택' })
    $reqOk = @($req | Where-Object { $_.Ok }).Count
    $optOk = @($opt | Where-Object { $_.Ok }).Count
    $allOk = ($reqOk -eq $req.Count)
    $verdict = '아직 준비가 덜 됐습니다 — ❌ 줄만 고치면 됩니다'
    $verdictClass = 'bad'
    if ($allOk) { $verdict = '출발 준비 완료! 강의 당일 바로 시작할 수 있습니다'; $verdictClass = 'good' }

    $sb = New-Object System.Text.StringBuilder
    $null = $sb.Append(@"
<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>환경 점검 결과 — 에이전트팀 만들기</title>
<style>
:root{--p:#7B2D8E;--deep:#3D1249;--dark:#5A1E6B;--band:#F8F5FA;--line:#E8DEF0;--ok:#1E9E5A;--no:#E84393;--gold:#F5A623;--ink:#1f1a24}
*{box-sizing:border-box}
body{margin:0;background:#fff;color:var(--ink);font-family:"Noto Sans KR","Noto Sans Korean","Noto Sans CJK KR","NotoSansKR","Malgun Gothic","맑은 고딕",sans-serif;line-height:1.55}
code,pre{font-family:"Noto Sans KR","Noto Sans Korean","Noto Sans CJK KR","NotoSansKR","Malgun Gothic","맑은 고딕",sans-serif}
.nav{display:flex;align-items:center;gap:12px;padding:14px 32px;border-bottom:1px solid var(--line)}
.nav img{height:38px;width:auto}
.nav .t{font-weight:700;color:var(--deep)}
.nav .s{color:#6b6470;font-size:13px;margin-left:auto}
.wrap{max-width:960px;margin:0 auto;padding:48px 24px 80px}
h1{margin:0 0 8px;font-size:30px;color:var(--deep);letter-spacing:-.01em}
.lede{margin:0 0 28px;color:#5c5661}
.verdict{border-radius:16px;padding:22px 26px;margin:0 0 36px;font-size:19px;font-weight:700;display:flex;align-items:center;gap:14px}
.verdict.good{background:#eaf7ef;color:#155c36;border:1px solid #bfe6cf}
.verdict.bad{background:#fdeef5;color:#8a1e4f;border:1px solid #f6c6dc}
.verdict .n{font-size:14px;font-weight:500;margin-left:auto;opacity:.8}
h2{font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:var(--p);margin:36px 0 12px}
table{width:100%;border-collapse:collapse;border:1px solid var(--line);border-radius:16px;overflow:hidden}
th{background:var(--dark);color:#fff;text-align:left;font-weight:600;font-size:13px;padding:10px 14px}
td{padding:12px 14px;border-top:1px solid var(--line);vertical-align:top;font-size:14px}
tr:nth-child(even) td{background:var(--band)}
td.m{width:44px;text-align:center;font-size:18px}
td.name{font-weight:600;width:34%}
.detail{color:#5c5661}
.fix{color:var(--deep);margin-top:4px;font-size:13px}
.fix a{color:var(--p);font-weight:600;text-decoration:none}
.fix a:hover{text-decoration:underline}
.slab{margin-top:56px;background:var(--deep);color:#eadff0;border-radius:16px;padding:28px 30px}
.slab b{color:#A855F7}
.slab ol{margin:8px 0 0 18px;padding:0}
.foot{margin-top:18px;font-size:12px;color:#8a8390}
@media print{.nav{border:0}.slab{background:#fff;color:#000;border:1px solid #ccc}}
</style></head><body>
<div class="nav"><img alt="WITH DREAM" src="data:image/png;base64,$WD_SYMBOL_B64"><span class="t">에이전트팀 만들기 과정</span><span class="s">환경 점검 · $($STARTED.ToString('yyyy-MM-dd HH:mm'))</span></div>
<div class="wrap">
<h1>출발선 점검 결과</h1>
<p class="lede">$(Html $env:COMPUTERNAME) · $(Html $KIT)</p>
<div class="verdict $verdictClass"><span>$(if($allOk){'🎉'}else{'🛠'})</span><span>$verdict</span><span class="n">필수 $reqOk/$($req.Count) · 선택 $optOk/$($opt.Count)</span></div>
"@)

    foreach ($grp in @(@('필수 — 이게 다 ✅ 여야 수업을 시작할 수 있습니다', $req), @('선택 — 없어도 실습되지만, 집에서 스킬을 쓰려면 필요합니다', $opt))) {
        $null = $sb.Append("<h2>$($grp[0])</h2><table><tr><th></th><th>항목</th><th>확인 결과</th></tr>")
        foreach ($r in $grp[1]) {
            $m = '❌'; if ($r.Ok) { $m = '✅' }
            $fix = ''
            if (-not $r.Ok -and ($r.Fix -or $r.Url)) {
                $fix = '<div class="fix">→ ' + (Html $r.Fix)
                if ($r.Url) { $fix += " <a href=`"$($r.Url)`" target=`"_blank`" rel=`"noopener`">$(Html $r.Url)</a>" }
                $fix += '</div>'
            }
            $null = $sb.Append("<tr><td class=`"m`">$m</td><td class=`"name`">$(Html $r.Name)</td><td><div class=`"detail`">$(Html $r.Detail)</div>$fix</td></tr>")
        }
        $null = $sb.Append('</table>')
    }

    $null = $sb.Append(@"
<div class="slab"><b>다음 할 일</b>
<ol>
<li>❌ 가 있으면 그 줄의 안내대로 고치고 <b>환경점검.bat</b> 을 다시 더블클릭합니다.</li>
<li>전부 ✅ 면 검은 창에서 <b>py -3 점검.py 0</b> 으로 한 번 더 확인하고, 프롬프트카드.md 의 모듈 0 부터 시작합니다.</li>
<li>슬랙 열쇠는 <b>모듈 4 전까지</b>만 준비되면 됩니다. Google Flow·네이버 로그인은 집에서 스킬을 쓸 때 하면 됩니다.</li>
</ol>
<div class="foot">이 점검은 열쇠 값을 읽거나 저장하지 않으며, 로그인은 항상 본인이 직접 합니다. · 위드드림컨설팅</div>
</div>
</div></body></html>
"@)
    [IO.File]::WriteAllText($REPORT, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
}

# ── 6. 실행 ──────────────────────────────────────────────────
Write-Host ''
Write-Host '  ┌──────────────────────────────────────────────────┐' -ForegroundColor Magenta
Write-Host '  │   에이전트팀 만들기 과정 — 출발선 자동 점검      │' -ForegroundColor Magenta
Write-Host '  └──────────────────────────────────────────────────┘' -ForegroundColor Magenta
Write-Info "스타터킷: $KIT"
if ($PretendMissing.Count) { Write-Warn "테스트 모드 — 없는 것으로 가정: $($PretendMissing -join ', ')" }

$script:PY = $null

Write-Step '1/6 기본 확인'
Check-Internet | Out-Null
Check-Disk | Out-Null

Write-Step '2/6 프로그램 확인'
Check-Node | Out-Null
Check-Npm | Out-Null
Check-Python | Out-Null
Check-Pip | Out-Null
Check-Git | Out-Null
Check-Claude | Out-Null
Check-VSCode | Out-Null
Check-Chrome | Out-Null
Fix-Programs
Fix-Claude

Write-Step '3/6 Claude Code 로그인'
Check-ClaudeLogin | Out-Null
Fix-ClaudeLogin

Write-Step '4/6 파이썬 꾸러미'
Check-PyPackages | Out-Null
Fix-PyPackages

Write-Step '5/6 스타터킷 · 슬랙'
Check-Folders | Out-Null
Check-MyData | Out-Null
Check-SlackEnv | Out-Null
Fix-Slack

Write-Step '6/6 선택 항목 (스킬용 로그인)'
Check-FlowLogin | Out-Null
Check-NaverLogin | Out-Null
Fix-OptionalLogins

# ── 7. 최종 체크리스트 ───────────────────────────────────────
Write-Host ''
Write-Host '  ══════════════════ 체크리스트 ══════════════════' -ForegroundColor Magenta
$req = @($script:Results | Where-Object { $_.Group -ne '선택' })
$opt = @($script:Results | Where-Object { $_.Group -eq '선택' })
Write-Host '  [필수]' -ForegroundColor White
foreach ($r in $req) { $m = $NOM; $c = 'Red'; if ($r.Ok) { $m = $OKM; $c = 'Green' }; Write-Host "  $m $($r.Name)" -ForegroundColor $c; if (-not $r.Ok) { Write-Host "        └ $($r.Detail)" -ForegroundColor DarkGray; if ($r.Fix) { Write-Host "        └ 고치기: $($r.Fix)" -ForegroundColor Yellow } } }
Write-Host '  [선택]' -ForegroundColor White
foreach ($r in $opt) { $m = $NOM; $c = 'Red'; if ($r.Ok) { $m = $OKM; $c = 'Green' }; Write-Host "  $m $($r.Name)" -ForegroundColor $c }
$reqOk = @($req | Where-Object { $_.Ok }).Count
$optOk = @($opt | Where-Object { $_.Ok }).Count
Write-Host '  ─────────────────────────────────────────────────' -ForegroundColor Magenta
if ($reqOk -eq $req.Count) {
    Write-Host "  🎉 필수 $reqOk/$($req.Count) 전부 통과 · 선택 $optOk/$($opt.Count) — 출발 준비 완료!" -ForegroundColor Green
} else {
    Write-Host "  필수 $reqOk/$($req.Count) 통과 · 선택 $optOk/$($opt.Count) — ❌ 표시된 것만 고치고 다시 실행하세요." -ForegroundColor Yellow
}

try { Write-Report; Write-Info "결과 파일: $REPORT"; if (-not $NoBrowser) { Start-Process $REPORT } } catch { Write-Warn "HTML 저장 실패: $_" }
Write-Info ("소요 {0:n0}초" -f ((Get-Date) - $STARTED).TotalSeconds)

if (-not $NoPause) { $null = Read-Host '  창을 닫으려면 Enter' }
if ($reqOk -eq $req.Count) { exit 0 } else { exit 1 }
