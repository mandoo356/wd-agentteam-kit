# 위드드림 에이전트팀 - 슬랙 서버 감시 루프 (스타터킷판)
# server.py 를 창 없이 띄우고, 꺼지면 10초 뒤 자동으로 다시 켠다.
# launcher.vbs 가 이 파일을 창 없이 실행하고,
# 자동시작_켜기.bat 이 HKCU Run 에 등록해 로그온 때마다 저절로 뜬다.
#
# ⚠ 남의 python 을 건드리지 않는다. 이름이 server.py 인 파이썬은 이 PC 에 여럿 있을 수 있어
#   (대표 홈서버 withdream-agent-server 등), 이름으로 골라 끄면 엉뚱한 서버가 죽는다.
#   그래서 이 감시기가 띄운 자식의 PID 를 logs\server.pid 에 적어두고, 끌 때는 그 PID 만 본다.

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $dir 'logs'
if (-not (Test-Path -LiteralPath $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$log = Join-Path $logDir 'launcher.log'
$pidFile = Join-Path $logDir 'server.pid'

function Write-Log([string]$msg) {
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $log -Value "[$ts] $msg" -Encoding utf8
}

# 감시기가 두 벌 돌면 서버도 두 벌이 되어 슬랙이 같은 말을 두 번 한다. 한 벌만 허용한다.
$mutex = New-Object System.Threading.Mutex($false, 'Global\WithdreamStarterkitSupervisor')
if (-not $mutex.WaitOne(0)) {
    Write-Log '감시기가 이미 돌고 있어 이번 실행은 그냥 끝냅니다.'
    exit 0
}

# 이 토큰을 자식에게 물리면 claude.ai 계정 커넥터(구글 캘린더·지메일)가 통째로 사라진다.
Remove-Item Env:CLAUDE_CODE_OAUTH_TOKEN -ErrorAction SilentlyContinue

# 파이썬 3.14 찾기: 표준 설치 경로 -> py 런처 순.
$py = $null
$useLauncher = $false
foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python314\python.exe", "$env:ProgramFiles\Python314\python.exe")) {
    if (Test-Path -LiteralPath $c) { $py = $c; break }
}
if (-not $py) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { $py = $launcher.Source; $useLauncher = $true }
}
if (-not $py) {
    Write-Log '파이썬 3.14 를 찾지 못했습니다. 환경점검.bat 을 먼저 돌려주세요.'
    exit 1
}
Write-Log "python: $py (launcher=$useLauncher)"

$argList = if ($useLauncher) { @('-3.14','-X','utf8','server.py') } else { @('-X','utf8','server.py') }

# 감시기 자신의 PID 도 남긴다 — 끌 때 이 감시기만 정확히 내리기 위해서.
Set-Content -Path (Join-Path $logDir 'supervisor.pid') -Value $PID -Encoding ascii

# 2026-10-05: 예전에는 여기서 10초마다 조용히 영원히 다시 띄웠다. 열쇠가 틀리면
#   하루 종일 돌면서 아무도 모른다 — 수강생 눈에는 "PC 를 껐다 켜니 슬랙이 죽었다" 로 보인다.
#   그래서 ① 바로 꺼지는 게 3번 연속이면 안내 창을 한 번 띄우고 ② 재시도 간격을 60초로 늘린다.
#   한 번이라도 20초 넘게 버티면 정상으로 보고 카운터를 되돌린다.
$fails = 0
$notified = $false
while ($true) {
    Write-Log 'starting server.py (supervisor)'
    $t0 = Get-Date
    try {
        $proc = Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $dir -WindowStyle Hidden -PassThru
        Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
        Write-Log "server.py pid $($proc.Id)"
        Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
    } catch {
        Write-Log "start error: $($_.Exception.Message)"
    }
    Remove-Item -LiteralPath $pidFile -ErrorAction SilentlyContinue
    $lived = [int]((Get-Date) - $t0).TotalSeconds
    if ($lived -lt 20) { $fails++ } else { $fails = 0; $notified = $false }

    if ($fails -ge 3) {
        $help = Join-Path $dir 'logs\서버가_안뜹니다.txt'
        @(
            '슬랙 서버가 떴다가 바로 꺼지는 것이 반복되고 있습니다.',
            '',
            "마지막 확인: $(Get-Date -Format 'yyyy-MM-dd HH:mm')   연속 실패 $fails 회",
            '',
            '거의 모든 경우 원인은 슬랙 열쇠 3개입니다.',
            '  1) 스타터킷 폴더의 환경점검.bat 을 다시 누르세요',
            '  2) 열쇠 3개를 다시 붙여넣으세요 (xoxb- / xapp- / 내 슬랙 아이디)',
            '  3) 끝나면 이 파일은 지워도 됩니다',
            '',
            '자세한 기록: slack-server\logs\launcher.log'
        ) | Set-Content -LiteralPath $help -Encoding UTF8
        if (-not $notified) {
            Write-Log "연속 $fails 회 실패 — 안내 창을 띄우고 재시도 간격을 60초로 늘립니다."
            $notice = Join-Path $dir 'notice.vbs'
            if (Test-Path -LiteralPath $notice) {
                try { Start-Process -FilePath 'wscript.exe' -ArgumentList ('"{0}"' -f $notice) -WindowStyle Hidden } catch {}
            }
            $notified = $true
        }
        Write-Log 'server.py exited - restart in 60s'
        Start-Sleep -Seconds 60
    } else {
        Write-Log 'server.py exited - restart in 10s'
        Start-Sleep -Seconds 10
    }
}
