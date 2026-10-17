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

#   powershell -File tools\engine_ctl.ps1 -Action start -Exe <exe> -Tag <tag> -StepProfile 1   # I3b step profile (default 0=off; window=64)

param(

    [Parameter(Mandatory=$true)][ValidateSet('start','stop','status','waitready')][string]$Action,

    [string]$Exe = '',

    [string]$Tag = 'adhoc',

    [int]$Depth = 2,

    [int]$Port = 8094,

    [int]$WaitSec = 240,

    [string[]]$Env = @(),
    [string]$Trace = '',          # nsys 可执行路径（2026-10-17 加：把起服包进 nsys profile，抓 CUDA 级 trace）
    [string]$TraceOut = '',      # trace 输出前缀
    [int]$TraceSec = 330,        # trace 时长（覆盖 预热+基线+谷+释放）


    [int]$Score = -1,

    [int]$StepProfile = 0,

    [int]$Pool = 65536,

    [int]$Graph = 64,

    [string]$Spec = 'mtp',

    [string]$KvDtype = 'rk2v4-e8',

    # 窗口纪律：-WindowStyle 只允许可见窗口（起窗必可见）；

    # 传 Hidden/Minimized/Maximized 一律在参数绑定阶段报错。

    [ValidateSet('Normal')][string]$WindowStyle = 'Normal',

    [int]$Draft = 4,

    [ValidateSet('cpu','resident','overlay','off')][string]$Vision = 'overlay',

    [string]$Extra = '',



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

    $p = Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue

    if ($p) { foreach ($proc in $p) { Write-Output ('engine pid=' + $proc.Id + ' ws_gb=' + [math]::Round($proc.WorkingSet64/1GB,2)) } }

    else { Write-Output 'engine STOPPED' }

    $vram = Get-VramUsedMb

    if ($vram) { Write-Output ('vram used=' + $vram.used + ' MiB / ' + $vram.total + ' MiB') }

    $listen = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)

    Write-Output ('port ' + $Port + ' listening = ' + $listen.Count)

    exit 0

}



if ($Action -eq 'stop') {

    $p = Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue

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

        $still = Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue

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

        if ($text -match 'listening on http') {
            if (Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue) { Write-Output 'READY'; exit 0 }
            Write-Output ('stale-ready ignored (log says listening, no process) ' + (Get-Date -Format 'HH:mm:ss'))
        }

        if ($text -match 'FATAL|serve_tee end') { Write-Output 'FAILED'; exit 2 }

    }

    Write-Output 'TIMEOUT'

    exit 3

}



# ---- start ----

if ([string]::IsNullOrWhiteSpace($Exe)) { throw "engine_ctl: -Exe 必填（引擎件路径）" }
if (-not (Test-Path $Exe)) { throw "exe not found: $Exe" }

# Canonical run path (2026-10-12 lesson): the PROCESS NAME follows the exe file name.

# Running a renamed lineage copy made Get-Process 'ninfer-serve*' blind -- the instance looked

# "dead" while it was alive and holding VRAM, and the tee's log froze when the tee was killed.

# So: always copy the variant to engine\test-run\ninfer-serve.exe and run THAT.

# 2026-10-17 修（DECISIONS #45「守卫碍事 ⇒ 改守卫」）：

#   原实现把 exe 暂存到 engine\test-run\（**空目录、无 DLL**）⇒ 引擎起不来（0xC0000135 DLL 未找到）。

#   引擎的 13 个 DLL 只在 engine\self-built-20261008\ ⇒ **暂存必须落到那里**。

#   engine\test-run\ 仍保留 VARIANT.txt 作记录（不动其用途）。

$runDir = Join-Path $root 'engine\test-run'

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$dllDir = Join-Path $root 'engine\self-built-20261008'   # 有 13 个 DLL（cudart64_13 / avcodec* / libcurl 等）

if (-not (Test-Path $dllDir)) { throw ('DLL 目录缺失（引擎无法启动）：' + $dllDir) }

$runExe = Join-Path $dllDir 'ninfer-serve.exe'   # ★ 必须是**字面名**（进程名跟着 exe 名 ⇒ 存活检查才看得见）

Copy-Item $Exe $runExe -Force

Set-Content -Path (Join-Path $runDir 'VARIANT.txt') -Encoding ascii -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm') + '  from=' + $Exe + '  tag=' + $Tag + '  depth=' + [string]$Depth)   # 记录仍留 test-run

$Exe = $runExe

$modelPath = Join-Path (Join-Path $root 'models') $Model

if (-not (Test-Path $modelPath)) { throw ('model file not found: ' + $modelPath) }

$vram = Get-VramUsedMb

if ($vram) {

    Write-Output ('vram before start: used=' + $vram.used + ' MiB / ' + $vram.total + ' MiB')

    if ($vram.used -gt 2500) { throw ('refusing to start: vram used ' + $vram.used + ' MiB (old instance not released?)') }

}

$log = Join-Path $root ('logs\test_' + $Tag + '.log')

if (Test-Path $log) {  # 2026-10-14: 归档（不删）；**必须容错**——旧日志被上一进程占用时

    # Move-Item 会抛异常并中止整个 start（守望者 20:47 的 engine start FAILED 根因）

    try { Move-Item $log ($log + '.' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.old') -Force }

    catch {
        # 2026-10-18 改（用户令：项目未结项前 logs 一个都严禁删除）：
        #   原实现在归档失败（日志被上一进程占用）时 Remove-Item 直接删日志 ⇒ 违反铁律。
        #   改为：**不删**，保留原文件并醒目告警（引擎仍会正常起，新日志追加到同名文件）。
        Write-Output ('WARN: log archive skipped (locked) -- 按铁律**不删除**日志: ' + $log)
        Write-Output ('      ' + $_.Exception.Message)
    }Action SilentlyContinue } }



$env:NINFER_KV_WINDOW = '32768'

$env:NINFER_KV_SINK = '5120'

$env:NINFER_KV_RETRIEVE = '8192'

$env:NINFER_KV_RING = '1'

$env:NINFER_HOST_PAGEABLE = '1'

$env:NINFER_KV_REUSE_HOSTBACKED = '1'

$env:NINFER_ASYNC_DEMOTE_DEPTH = [string]$Depth

$env:NINFER_DEMOTE_PROFILE = '1'

if ($StepProfile -ge 1) { $env:NINFER_STEP_PROFILE = [string]$StepProfile; $env:NINFER_STEP_PROFILE_WINDOW = '64'; Write-Output 'knob: step profile ON (NINFER_STEP_PROFILE=1, window 64)' }

if ($Score -eq 0) { $env:NINFER_TERNARY_KVMEM_SCORE = '0'; Write-Output 'knob: content scoring OFF (NINFER_TERNARY_KVMEM_SCORE=0)' }

$env:PATH = (Join-Path $root 'engine') + ';' + (Join-Path $root 'engine\self-built-20261008') + ';' + $env:PATH
foreach ($kv in $Env) { if ($kv -match '^([^=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1]) -Value $matches[2] } }
# 应用 -Env（2026-10-17：trace 开关等；单变量纪律用）



$visionArgs = switch ($Vision) {

    'off'      { @() }

    'resident' { @('--vision') }

    'overlay'  { @('--vision', '--vision-residency', 'overlay') }

    default    { @('--vision-cpu') }

}

$extraList = @()

if ($Extra -and $Extra.Trim() -ne '') {

    $extraList = @($Extra.Split(',') | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })

}

# 招牌名（API model 字段）随权重件自动切换（2026-10-14 用户令：招牌名不得与真身打架）

$modelId = switch -Wildcard ($Model) {

    '*swift*'  { 'swift-1.5-qwen3.8-27b-gsq-rco-iq3s' }

    '*Bonsai*' { 'ternary-bonsai-2-27b' }

    default    { 'qwen3.8-27b-coder390' }

}

$cliArgs = @(

    'serve_tee.py', $log, $Exe, $modelPath,

    '--host', '127.0.0.1', '--port', [string]$Port,

    '--model-id', $modelId,

    '--max-context', '262144', '--kv-capacity', [string]$Pool,

    '--cuda-graph-allowance-mib', [string]$Graph, '--kv-dtype', $KvDtype,

    '--host-kv-mib', '16384', '--prefill-chunk', '512',

    '--spec', $Spec, '--draft-tokens', [string]$Draft

) + $visionArgs + $extraList + @(

    '--default-max-tokens', '32768', '--default-reasoning-effort', 'high', '--default-thinking-budget', '16000',

    '--max-concurrency', '1', '--max-shared-prefixes', '0',

    '--presence-penalty', '0', '--temperature', '0.7', '--top-p', '0.9', '--top-k', '20',

    '--recover-invariant-failures'

)

if ($Spec -eq 'none') {

    $filtered = @()

    for ($i = 0; $i -lt $cliArgs.Count; ++$i) {

        if ($cliArgs[$i] -eq '--spec' -or $cliArgs[$i] -eq '--draft-tokens') { ++$i; continue }

        $filtered += $cliArgs[$i]

    }

    $cliArgs = $filtered

    Write-Output 'knob: spec OFF (no --spec flag passed; MTP off by default)'

}

Write-Output ('start: exe=' + $Exe)

Write-Output ('start: depth=' + $Depth + ' port=' + $Port + ' log=' + $log)

# 2026-10-17 修（同"裸 python"病，猎人也犯过）：本机 PATH 无 python ⇒ 自解析解释器
$PyExe = $null
foreach ($c in @('python', 'py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $PyExe = $c; break } }
if (-not $PyExe) {
    $f = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    if ($f.Count -gt 0) { $PyExe = $f[0] }
}
if (-not $PyExe) { throw 'engine_ctl: no python interpreter found (PATH/常见路径都没有)' }
$spawner = if ($Trace) {
        Write-Output ('trace: nsys profile -o ' + $TraceOut + ' -t cuda,nvtx -d ' + $TraceSec)
        & $Trace profile -o $TraceOut -t cuda,nvtx -d $TraceSec --force-overwrite=true -- $PyExe @cliArgs
    } else {
        Start-Process -FilePath 'cmd.exe' -ArgumentList (@('/k', $PyExe) + $cliArgs) -WorkingDirectory $root -WindowStyle $WindowStyle -PassThru
    }
# 2026-10-17：**sanctioned spawner 必须留 spawn 记录**（否则它起的进程树被判"无记录"）
try {
    $spawnDir = Join-Path $root 'evidence\spawns'
    New-Item -ItemType Directory -Force -Path $spawnDir | Out-Null
    $rec = [ordered]@{ ts = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); purpose = 'engine-start'; exe = $Exe
                       pid = $spawner.Id; has_window = $true; is_minimized = $false; is_visible = $true
                       title = 'engine (engine_ctl)'; verdict = 'OK'; enforced_by = 'scripts\engine_ctl.ps1 (T-WINDOW)' }
    $jp = Join-Path $spawnDir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_engine-start.json')
    [System.IO.File]::WriteAllText($jp, ($rec | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
} catch { Write-Output ('WARN: spawn record failed: ' + $_.Exception.Message) }  # 窗口纪律：起窗必可见——禁 Hidden/Minimized/Maximized（参数已锁）

