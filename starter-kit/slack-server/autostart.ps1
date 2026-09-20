<#
  autostart.ps1 - 슬랙 서버 자동시작 켜기/끄기

  켜기: 로그온할 때마다 슬랙 서버가 저절로 뜨고, 꺼져도 10초 뒤 다시 켜진다.
        더 이상 터미널에서 py -3 -X utf8 server.py 를 칠 일이 없다.
  끄기: 등록을 지우고, 이 킷이 띄운 감시기·서버만 정확히 내린다.

  ⚠ 이름이 server.py 인 파이썬을 싸잡아 끄지 않는다. 이 PC 에는 다른 서버가 함께 돌 수 있고
    (대표 홈서버 withdream-agent-server), 이름으로 고르면 그쪽이 죽는다.
    감시기가 logs\server.pid / logs\supervisor.pid 에 적어둔 PID 만 본다.
#>
# -Quiet : 환경점검이 부를 때. 마지막에 Enter 를 기다리지 않는다.
param([switch]$Enable, [switch]$Disable, [switch]$Quiet)

try {
    $null = & "$env:ComSpec" /c chcp 65001
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
} catch {}

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $dir 'launcher.vbs'
$logDir = Join-Path $dir 'logs'
$pidFile = Join-Path $logDir 'server.pid'
$supPidFile = Join-Path $logDir 'supervisor.pid'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runName = 'WithdreamStarterkitServer'

function Say([string]$t, [string]$c = 'Gray') { Write-Host "  $t" -ForegroundColor $c }
function Pause-IfInteractive { if (-not $Quiet) { $null = Read-Host '  이 창을 닫으려면 Enter' } }

function Stop-ByPidFile([string]$file, [string]$name, [string]$expectName) {
    if (-not (Test-Path -LiteralPath $file)) { return }
    $id = (Get-Content -LiteralPath $file -ErrorAction SilentlyContinue | Select-Object -First 1) -as [int]
    if ($id) {
        $p = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($p -and $p.ProcessName -eq $expectName) {
            Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
            Say "✔ $name 종료 (PID $id)" 'Green'
        }
    }
    Remove-Item -LiteralPath $file -ErrorAction SilentlyContinue
}

Write-Host ''
if ($Disable) {
    Say '슬랙 서버 자동시작 — 끄기' 'Magenta'
    Write-Host ''
    try { Remove-ItemProperty -Path $runKey -Name $runName -ErrorAction Stop; Say '✔ 로그온 자동시작 등록을 지웠습니다.' 'Green' }
    catch { Say '· 자동시작 등록이 원래 없었습니다.' 'DarkGray' }

    # 감시기를 먼저 내린다. 서버부터 내리면 감시기가 10초 뒤 되살린다.
    Stop-ByPidFile $supPidFile '감시기' 'powershell'
    Start-Sleep -Milliseconds 500
    Stop-ByPidFile $pidFile '슬랙 서버' 'python'

    Write-Host ''
    Say '이제 슬랙에 말을 걸어도 직원들이 답하지 않습니다. 다시 켜려면 자동시작_켜기.bat 을 누르세요.' 'DarkGray'
    Write-Host ''
    Pause-IfInteractive
    exit 0
}

Say '슬랙 서버 자동시작 — 켜기' 'Magenta'
Write-Host ''

if (-not (Test-Path -LiteralPath $vbs)) {
    Say "❌ launcher.vbs 가 없습니다: $vbs" 'Red'
    Write-Host ''; Pause-IfInteractive; exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $dir '.env'))) {
    Say '❌ slack-server\.env 가 없습니다. 환경점검.bat 으로 슬랙 열쇠부터 넣어주세요.' 'Red'
    Write-Host ''; Pause-IfInteractive; exit 1
}

Say '※ 터미널(검은 창)에서 직접 켜 둔 서버가 있다면, 그 창에서 Ctrl+C 로 먼저 꺼주세요.' 'DarkGray'
Say '   두 벌이 돌면 슬랙에서 직원이 같은 말을 두 번 합니다.' 'DarkGray'
Write-Host ''

# 이 킷이 앞서 띄워둔 것이 있으면 정리하고 새로 시작한다.
Stop-ByPidFile $supPidFile '먼저 돌던 감시기' 'powershell'
Start-Sleep -Milliseconds 500
Stop-ByPidFile $pidFile '먼저 돌던 서버' 'python'

$cmd = "wscript.exe `"$vbs`""
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $runName -Value $cmd
Say '✔ 로그온할 때마다 저절로 켜지도록 등록했습니다.' 'Green'
Say "  등록 내용: $cmd" 'DarkGray'

Start-Process -FilePath 'wscript.exe' -ArgumentList "`"$vbs`"" -WindowStyle Hidden
Say '· 지금 바로 켜는 중입니다...' 'DarkGray'

$ok = $false; $serverPid = $null
foreach ($i in 1..25) {
    Start-Sleep -Seconds 1
    if (Test-Path -LiteralPath $pidFile) {
        $id = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1) -as [int]
        if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) { $ok = $true; $serverPid = $id; break }
    }
}

Write-Host ''
if ($ok) {
    Say "✔ 슬랙 서버가 켜졌습니다 (PID $serverPid). 검은 창은 뜨지 않습니다." 'Green'
    Say '  이제 PC를 껐다 켜도 저절로 뜹니다. 슬랙에서 직원을 불러 확인해 보세요.' 'Green'
} else {
    Say '⚠ 25초 안에 서버가 올라오지 않았습니다. logs\launcher.log 와 logs\server.log 를 확인해 주세요.' 'Yellow'
}
Write-Host ''
Pause-IfInteractive
