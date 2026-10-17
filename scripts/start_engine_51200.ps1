$host.UI.RawUI.WindowTitle = 'ENGINE-51200 [running] -- pool 51200; close = stop engine'
Set-Location 'J:\ninfer-kvmem'
$env:CUDA_PATH = 'J:\Bonsai\landing\cuda-13.3'
$env:CUDA_PATH_V13_3 = 'J:\Bonsai\landing\cuda-13.3'
$PyExe = $null
foreach ($c in @('python','py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $PyExe = $c; break } }
if (-not $PyExe) { $f = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName); if ($f.Count -gt 0) { $PyExe = $f[0] } }
if (-not $PyExe) { Write-Host 'FATAL: no python' -ForegroundColor Red; exit 1 }
$exe = 'J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve-I3b322a.exe'
$model = 'J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer'
if (-not (Test-Path $exe)) { Write-Host ("FATAL: exe missing: " + $exe) -ForegroundColor Red; exit 1 }
Write-Host ("engine exe = " + $exe)
Write-Host ("cwd        = " + (Get-Location).Path)
Write-Host ("pool       = 51200")
& $PyExe serve_tee.py 'J:\ninfer-kvmem\logs\test_valleywatch.log' $exe $model --host 127.0.0.1 --port 8094 --model-id qwen3.8-27b-coder390 --max-context 262144 --kv-capacity 51200 --cuda-graph-allowance-mib 64 --kv-dtype rk2v4-e8 --host-kv-mib 16384 --prefill-chunk 512 --spec mtp --draft-tokens 4 --vision --vision-residency overlay --request-log-jsonl .temp\reqlog_watch.jsonl --request-log-max-mib 128 --request-log-keep 2 --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 --max-concurrency 1 --max-shared-prefixes 0 --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 --recover-invariant-failures
