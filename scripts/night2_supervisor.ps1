# night2_supervisor.ps1 -- 看门狗：主脚本死了/卡死则自动重启（断点续跑）
param(
    [int]$MaxHours = 4,
    [int]$StaleSec = 300,
    [int]$CheckSec = 60
)
$root = 'J:\ninfer-kvmem'
Set-Location $root
$dir = Join-Path $root '.temp\night2'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$supLog = Join-Path $dir 'supervisor.log'
$stateF = Join-Path $dir 'state.json'
$hbF = Join-Path $dir 'heartbeat.txt'

function Say([string]$m) {
    $l = (Get-Date -Format 'MM-dd HH:mm:ss') + '  [SUP] ' + $m
    Add-Content -LiteralPath $supLog -Value $l -Encoding UTF8
}

function MainAlive {
    $p = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'night2_run\.ps1' }
    return [bool]$p
}

Say ('supervisor start, maxHours=' + $MaxHours + ' staleSec=' + $StaleSec)
$deadline = (Get-Date).AddHours($MaxHours)

while ((Get-Date) -lt $deadline) {
    $phase = ''
    if (Test-Path $stateF) { try { $phase = (Get-Content $stateF -Raw -Encoding UTF8 | ConvertFrom-Json).phase } catch {} }
    if ($phase -eq 'DONE') { Say 'phase=DONE, supervisor exit'; break }

    $alive = MainAlive
    $hbAge = 99999
    if (Test-Path $hbF) { $hbAge = ((Get-Date) - (Get-Item $hbF).LastWriteTime).TotalSeconds }

    if (-not $alive) {
        Say ('main not running (phase=' + $phase + ') -> restart')
        Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','J:\ninfer-kvmem\scripts\night2_run.ps1' -WorkingDirectory $root -WindowStyle Normal | Out-Null
        Start-Sleep -Seconds 30
    }
    elseif ($hbAge -gt $StaleSec) {
        Say ('main alive but stale (' + [math]::Round($hbAge, 0) + 's) -> kill & restart')
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match 'night2_run\.ps1' } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Get-Process 'ninfer-serve' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 5
        Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','J:\ninfer-kvmem\scripts\night2_run.ps1' -WorkingDirectory $root -WindowStyle Normal | Out-Null
        Start-Sleep -Seconds 30
    }
    else {
        Say ('ok phase=' + $phase + ' hbAge=' + [math]::Round($hbAge, 0) + 's')
    }
    Start-Sleep -Seconds $CheckSec
}
Say 'supervisor exit'
