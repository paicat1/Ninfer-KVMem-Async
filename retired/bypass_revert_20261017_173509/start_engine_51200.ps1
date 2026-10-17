# start_engine_51200.ps1 -- E-C 起服（池 51200）· 2026-10-17 CB
#   关键：**必须带 engine_ctl.ps1 的那套 KV 环境变量**（NINFER_KV_WINDOW 是"池 < 上下文"的唯一开关）
#         且 **PATH 前置 engine 与 engine\self-built-20261008**（DLL 靠它解析）
#   用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_engine_51200.ps1
$host.UI.RawUI.WindowTitle = 'ENGINE-51200 [running] -- pool 51200; close = stop engine'
Set-Location 'J:\ninfer-kvmem'

# —— 环境（照抄 scripts\engine_ctl.ps1 L126-136）——
$env:NINFER_KV_WINDOW = '32768'
$env:NINFER_KV_SINK = '5120'
$env:NINFER_KV_RETRIEVE = '8192'
$env:NINFER_KV_RING = '1'
$env:NINFER_HOST_PAGEABLE = '1'
$env:NINFER_KV_REUSE_HOSTBACKED = '1'
$env:NINFER_ASYNC_DEMOTE_DEPTH = '2'
$env:NINFER_DEMOTE_PROFILE = '1'
$env:CUDA_PATH = 'J:\Bonsai\landing\cuda-13.3'
$env:PATH = 'J:\ninfer-kvmem\engine;J:\ninfer-kvmem\engine\self-built-20261008;' + $env:PATH

$PyExe = $null
foreach ($c in @('python', 'py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $PyExe = $c; break } }
if (-not $PyExe) {
    $f = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    if ($f.Count -gt 0) { $PyExe = $f[0] }
}
if (-not $PyExe) { Write-Host 'FATAL: no python' -ForegroundColor Red; exit 1 }

$exe = 'J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve-I3b322a.exe'
$model = 'J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer'
$log = 'J:\ninfer-kvmem\logs\test_valleywatch.log'

if (-not (Test-Path $exe)) { Write-Host ("FATAL: exe missing: " + $exe) -ForegroundColor Red; exit 1 }
if (-not (Test-Path $model)) { Write-Host ("FATAL: model missing: " + $model) -ForegroundColor Red; exit 1 }

Write-Host ("interpreter = " + $PyExe)
Write-Host ("engine exe  = " + $exe)
Write-Host ("pool        = 51200   KV_WINDOW=32768")
Write-Host ("reqlog      = evidence\reqlogs\reqlog_watch.jsonl")

& $PyExe serve_tee.py $log $exe $model `
    --host 127.0.0.1 --port 8094 --model-id qwen3.8-27b-coder390 `
    --max-context 262144 --kv-capacity 51200 --cuda-graph-allowance-mib 64 `
    --kv-dtype rk2v4-e8 --host-kv-mib 16384 --prefill-chunk 512 `
    --spec mtp --draft-tokens 4 --vision --vision-residency overlay `
    --request-log-jsonl evidence\reqlogs\reqlog_watch.jsonl --request-log-max-mib 128 --request-log-keep 2 `
    --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 `
    --max-concurrency 1 --max-shared-prefixes 0 --presence-penalty 0 `
    --temperature 0.7 --top-p 0.9 --top-k 20 --recover-invariant-failures
