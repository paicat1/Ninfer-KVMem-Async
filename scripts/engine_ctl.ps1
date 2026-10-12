# engine_ctl.ps1 -- start/stop/status/waitready for engine experiments (long-run harness).
# ASCII-only. v2 (2026-10-12): learned the hard way that a port LISTEN can belong to the OLD
# instance and that a start can fail on VRAM while the old one has not released memory.
#   * stop     : kill engine + tee, then WAIT until the process is gone and VRAM is back
#   * start    : refuse to start unless VRAM free looks sufficient; log goes logs\test_<tag>.log
#   * waitready: poll the LOG for "listening on" (success) or "FATAL"/"serve_tee end" (failure)
# Usage:
#   powershell -File tools\engine_ctl.ps1 -Action stop
#   powershell -File tools\engine_ctl.ps1 -Action start -Exe <exe> -Tag <tag> -Depth 2
#   powershell -File tools\engine_ctl.ps1 -Action waitready -Tag <tag> [-WaitSec 240]
#   powershell -File tools\engine_ctl.ps1 -Action status
param(
    [Parameter(Mandatory=$true)][ValidateSet('start','stop','status','waitready')][string]$Action,
    [string]$Exe = '',
    [string]$Tag = 'adhoc',
    [int]$Depth = 2,
    [int]$Port = 8094,
    [int]$WaitSec = 240,
    [int]$Score = -1,
    [int]$Pool = 65536,
    [int]$Draft = 4,

    [string]$Model = 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer'
)
$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root
$smi = 'J:\Bonsai\landing\cuda-13.3\bin\nvidia-smi.exe'
if (-not (Test-Path $smi)) { $smi = 'nvidia-smi' }

function Get-VramUsedMb {
    try {
        $out = & $smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        $parts = $out -split ','
        return @{ used = [int]$parts[0].Trim(); total = [int]$parts[1].Trim() }
    } catch { return $null }
}

if ($Action -eq 'status') {
    $p = Get-Process ninfer-serve -ErrorAction SilentlyContinue
    if ($p) { foreach ($proc in $p) { Write-Output ('engine pid=' + $proc.Id + ' ws_gb=' + [math]::Round($proc.WorkingSet64/1GB,2)) } }
    else { Write-Output 'engine STOPPED' }
    $vram = Get-VramUsedMb
    if ($vram) { Write-Output ('vram used=' + $vram.used + ' MiB / ' + $vram.total + ' MiB') }
    $listen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    Write-Output ('port ' + $Port + ' listening = ' + $listen.Count)
    exit 0
}

if ($Action -eq 'stop') {
    $p = Get-Process ninfer-serve -ErrorAction SilentlyContinue
    if ($p) { $p | Stop-Process -Force; Write-Output ('killed engine pid=' + (($p | ForEach-Object { $_.Id }) -join ',')) }
    else { Write-Output 'engine: not running' }
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*serve_tee.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output ('killed tee pid=' + $_.ProcessId) }
    Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*serve_tee.py*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output ('killed cmd pid=' + $_.ProcessId) }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 3
        $still = Get-Process ninfer-serve -ErrorAction SilentlyContinue
        $vram = Get-VramUsedMb
        if (-not $still -and $vram -and $vram.used -lt 1500) { Write-Output ('freed after ~' + (3 * ($i + 1)) + 's; vram used=' + $vram.used + ' MiB'); exit 0 }
        if (-not $still -and -not $vram) { Write-Output 'process gone (no nvidia-smi)'; exit 0 }
    }
    $vram = Get-VramUsedMb
    Write-Output ('WARN: still not free after 60s; vram used=' + ($vram.used) + ' MiB')
    exit 1
}

if ($Action -eq 'waitready') {
    $log = Join-Path $root ('logs\test_' + $Tag + '.log')
    for ($i = 0; $i -lt [int]($WaitSec / 5); $i++) {
        Start-Sleep -Seconds 5
        if (-not (Test-Path $log)) { continue }
        # the tee holds the log open: read a snapshot copy, never the file itself
        $snap = Join-Path $root '.temp\waitready_snap.txt'
        try { Copy-Item $log $snap -Force -ErrorAction Stop } catch { continue }
        $text = [IO.File]::ReadAllText($snap)
        if ($text -match 'listening on http') { Write-Output 'READY'; exit 0 }
        if ($text -match 'FATAL|serve_tee end') { Write-Output 'FAILED'; exit 2 }
    }
    Write-Output 'TIMEOUT'
    exit 3
}

# ---- start ----
if (-not (Test-Path $Exe)) { throw "exe not found: $Exe" }
# Canonical run path (2026-10-12 lesson): the PROCESS NAME follows the exe file name.
# Running a renamed lineage copy made Get-Process ninfer-serve blind -- the instance looked
# "dead" while it was alive and holding VRAM, and the tee's log froze when the tee was killed.
# So: always copy the variant to engine\test-run\ninfer-serve.exe and run THAT.
$runDir = Join-Path $root 'engine\test-run'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$runExe = Join-Path $runDir 'ninfer-serve.exe'
Copy-Item $Exe $runExe -Force
Set-Content -Path (Join-Path $runDir 'VARIANT.txt') -Encoding ascii -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm') + '  from=' + $Exe + '  tag=' + $Tag + '  depth=' + [string]$Depth)
$Exe = $runExe
$modelPath = Join-Path (Join-Path $root 'models') $Model
if (-not (Test-Path $modelPath)) { throw ('model file not found: ' + $modelPath) }
$vram = Get-VramUsedMb
if ($vram) {
    Write-Output ('vram before start: used=' + $vram.used + ' MiB / ' + $vram.total + ' MiB')
    if ($vram.used -gt 2500) { throw ('refusing to start: vram used ' + $vram.used + ' MiB (old instance not released?)') }
}
$log = Join-Path $root ('logs\test_' + $Tag + '.log')
if (Test-Path $log) { Remove-Item $log -Force }

$env:NINFER_KV_WINDOW = '32768'
$env:NINFER_KV_SINK = '5120'
$env:NINFER_KV_RETRIEVE = '8192'
$env:NINFER_KV_RING = '1'
$env:NINFER_HOST_PAGEABLE = '1'
$env:NINFER_KV_REUSE_HOSTBACKED = '1'
$env:NINFER_ASYNC_DEMOTE_DEPTH = [string]$Depth
$env:NINFER_DEMOTE_PROFILE = '1'
if ($Score -eq 0) { $env:NINFER_TERNARY_KVMEM_SCORE = '0'; Write-Output 'knob: content scoring OFF (NINFER_TERNARY_KVMEM_SCORE=0)' }
$env:PATH = (Join-Path $root 'engine') + ';' + (Join-Path $root 'engine\self-built-20261008') + ';' + $env:PATH

$cliArgs = @(
    'serve_tee.py', $log, $Exe, $modelPath,
    '--host', '127.0.0.1', '--port', [string]$Port,
    '--model-id', 'qwen3.8-27b-coder390',
    '--max-context', '262144', '--kv-capacity', [string]$Pool,
    '--cuda-graph-allowance-mib', '64', '--kv-dtype', 'rk2v4-e8',
    '--host-kv-mib', '16384', '--prefill-chunk', '512',
    '--spec', 'mtp', '--draft-tokens', [string]$Draft, '--vision-cpu',
    '--default-max-tokens', '32768', '--default-reasoning-effort', 'high', '--default-thinking-budget', '16000',
    '--max-concurrency', '1', '--max-shared-prefixes', '0',
    '--presence-penalty', '0', '--temperature', '0.7', '--top-p', '0.9', '--top-k', '20',
    '--recover-invariant-failures'
)
Write-Output ('start: exe=' + $Exe)
Write-Output ('start: depth=' + $Depth + ' port=' + $Port + ' log=' + $log)
Start-Process -FilePath 'cmd.exe' -ArgumentList (@('/k', 'python') + $cliArgs) -WorkingDirectory $root -WindowStyle Maximized
Write-Output 'started (visible window); now run -Action waitready'
