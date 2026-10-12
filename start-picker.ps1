# start-picker.ps1 -- interactive launcher with a live VRAM account.
# ASCII-only on purpose (BOM-less .ps1 is read as ANSI by Windows PowerShell).
#   * every choice immediately re-computes the VRAM requirement (weights + pool + runtime + graph)
#   * the margin is measured live with nvidia-smi (the available budget moves ~0.6 GiB with the
#     desktop/WDDM state -- calibrated from this host's logs, see tools\vram_model.py --calibrate)
#   * the valley-burden hint follows 精算 §7.4: burden ~ (context - pool) x bytes/token
# Usage:
#   powershell -File start-picker.ps1            # interactive menu
#   powershell -File start-picker.ps1 -Show      # just print the account for the current config
#   powershell -File start-picker.ps1 -Pool 32768 -Dtype rk4v4-e8 -Launch
param(
    [int]$Pool = 65536,
    [string]$Dtype = 'rk2v4-e8',
    [int]$Graph = 64,
    [int]$HostKv = 16384,
    [int]$Context = 262144,
    [switch]$Launch,
    [switch]$Show
)
$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root
$exe = Join-Path $root 'engine\self-built-20261008\ninfer-serve.exe'
$model = Join-Path $root 'models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer'
$smi = 'C:\Windows\System32\nvidia-smi.exe'
if (-not (Test-Path $smi)) { $smi = 'nvidia-smi' }

$POOLS = @(65536, 55296, 51200, 40960, 32768, 28672)
$DTYPES = @('rk2v4-e8', 'rk4v4-e8', 'k8v4', 'int8', 'bf16')
$GRAPHS = @(64, 128, 0)
$HOSTKVS = @(16384, 8192, 32768)

function Get-Vram {
    try {
        $out = & $smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        $p = $out -split ','
        $used = [int]$p[0].Trim()
        $total = [int]$p[1].Trim()
        # WDDM does NOT expose per-process VRAM (--query-compute-apps returns nothing on Windows).
        # So: detect the engine process and use the measured desktop baseline instead.
        # Baseline measured on this host with the engine stopped: 904-990 MiB (6 samples) => 950 MiB.
        $running = $false
        $p = Get-Process ninfer-serve -ErrorAction SilentlyContinue
        if ($p) { $running = $true }
        return @{ used = $used; total = $total; running = $running; desktop = 950 }
    } catch { return $null }
}

function Show-Account {
    $vram = Get-Vram
    $vargs = @('build\vram_model.py', '--pool', [string]$Pool, '--dtype', $Dtype, '--graph', [string]$Graph, '--context', [string]$Context)
    $note = ''
    if ($vram) {
        if ($vram.running) {
            # after stopping the engine only the desktop baseline is still in use
            $vargs += @('--used-mib', [string]$vram.desktop, '--total-mib', [string]$vram.total)
            $note = ('  note: an engine is RUNNING now (GPU used ' + $vram.used + ' MiB of ' + $vram.total +
                     '). The account assumes you stop it first (then ~' + $vram.desktop + ' MiB desktop remains).')
        } else {
            $vargs += @('--used-mib', [string]$vram.used, '--total-mib', [string]$vram.total)
        }
    }
    Write-Output ''
    Write-Output ('  config : pool=' + $Pool + ' tok   kv-dtype=' + $Dtype + '   graph=' + $Graph + ' MiB   host-kv=' + $HostKv + ' MiB   ctx=' + $Context)
    if ($note -ne '') { Write-Output $note }
    python @vargs | ForEach-Object { Write-Output ('  ' + $_) }
    Write-Output ''
}

function Launch-Engine {
    $vram = Get-Vram
    $tag = 'pick_' + $Pool + '_' + ($Dtype -replace '-', '')
    $log = Join-Path $root ('logs\serve_' + $tag + '.log')
    Write-Output ('launching: exe=' + $exe)
    Write-Output ('           log=' + $log)
    $env:NINFER_KV_WINDOW = '32768'
    $env:NINFER_KV_SINK = '5120'
    $env:NINFER_KV_RETRIEVE = '8192'
    $env:NINFER_KV_RING = '1'
    $env:NINFER_HOST_PAGEABLE = '1'
    $env:NINFER_KV_REUSE_HOSTBACKED = '1'
    $cliArgs = @(
        'serve_tee.py', $log, $exe, $model,
        '--host', '127.0.0.1', '--port', '8094',
        '--model-id', 'qwen3.8-27b-coder390',
        '--max-context', [string]$Context, '--kv-capacity', [string]$Pool,
        '--cuda-graph-allowance-mib', [string]$Graph, '--kv-dtype', $Dtype,
        '--host-kv-mib', [string]$HostKv, '--prefill-chunk', '512',
        '--spec', 'mtp', '--draft-tokens', '4', '--vision-cpu',
        '--default-max-tokens', '32768', '--default-reasoning-effort', 'high', '--default-thinking-budget', '16000',
        '--max-concurrency', '1', '--max-shared-prefixes', '0',
        '--presence-penalty', '0', '--temperature', '0.7', '--top-p', '0.9', '--top-k', '20',
        '--recover-invariant-failures'
    )
    Start-Process -FilePath 'cmd.exe' -ArgumentList (@('/k', 'python') + $cliArgs) -WorkingDirectory $root -WindowStyle Maximized
    Write-Output 'started (visible window). Watch the log for "listening on http".'
}

if ($Show) {
    Show-Account
    exit 0
}
if ($Launch) {
    Show-Account
    Launch-Engine
    exit 0
}

# ---- interactive ----
while ($true) {
    Write-Output '================ ninfer-serve launcher (VRAM account) ================'
    Write-Output ('  model  : Qwen3.8-27B-Coder390-...-MTP...vision.ninfer   (weights 12.30 GiB on card)')
    Write-Output ('  exe    : engine\self-built-20261008\ninfer-serve.exe')
    Write-Output ''
    for ($i = 0; $i -lt $POOLS.Count; $i++) {
        $mark = '  '
        if ($POOLS[$i] -eq $Pool) { $mark = ' *' }
        Write-Output ('   [' + ($i + 1) + '] pool ' + $POOLS[$i] + ' tok' + $mark)
    }
    Write-Output ('   [c] custom pool')
    Write-Output ''
    for ($i = 0; $i -lt $DTYPES.Count; $i++) {
        $mark = '  '
        if ($DTYPES[$i] -eq $Dtype) { $mark = ' *' }
        Write-Output ('   [d' + ($i + 1) + '] kv-dtype ' + $DTYPES[$i] + $mark)
    }
    Write-Output ''
    for ($i = 0; $i -lt $GRAPHS.Count; $i++) {
        $mark = '  '
        if ($GRAPHS[$i] -eq $Graph) { $mark = ' *' }
        Write-Output ('   [g' + ($i + 1) + '] cuda-graph ' + $GRAPHS[$i] + ' MiB' + $mark)
    }
    Write-Output ''
    for ($i = 0; $i -lt $HOSTKVS.Count; $i++) {
        $mark = '  '
        if ($HOSTKVS[$i] -eq $HostKv) { $mark = ' *' }
        Write-Output ('   [h' + ($i + 1) + '] host-kv ' + $HOSTKVS[$i] + ' MiB (host RAM, not VRAM)' + $mark)
    }
    Write-Output ''
    Show-Account
    Write-Output '   [enter] launch   [q] quit   (choose 1-6 / c / d1-5 / g1-3 / h1-3)'
    $choice = Read-Host '  choice'
    if ($choice -eq 'q') { exit 0 }
    if ($choice -eq '') { Launch-Engine; exit 0 }
    if ($choice -match '^[1-6]$') { $Pool = $POOLS[[int]$choice - 1]; continue }
    if ($choice -eq 'c') {
        $custom = Read-Host '  pool tokens (multiple of 64)'
        $value = 0
        if ([int]::TryParse($custom, [ref]$value) -and $value -ge 4096 -and $value -le 262144) { $Pool = $value }
        continue
    }
    if ($choice -match '^d([1-5])$') { $Dtype = $DTYPES[[int]$Matches[1] - 1]; continue }
    if ($choice -match '^g([1-3])$') { $Graph = $GRAPHS[[int]$Matches[1] - 1]; continue }
    if ($choice -match '^h([1-3])$') { $HostKv = $HOSTKVS[[int]$Matches[1] - 1]; continue }
}
