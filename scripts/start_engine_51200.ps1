# 起服脚本（B2 完整版）：环境变量 + serve_tee 日志包装 + 参数（由启动器函数生成，逐字一致）
$host.UI.RawUI.WindowTitle = 'ENGINE 51200-pool [running] -- close window = stop'
Set-Location J:\ninfer-kvmem

$env:NINFER_ASYNC_DEMOTE = '1'
$env:NINFER_HOST_PAGEABLE = '1'
$env:NINFER_KV_RETRIEVE = '8192'
$env:NINFER_KV_REUSE_HOSTBACKED = '1'
$env:NINFER_KV_RING = '1'
$env:NINFER_KV_SINK = '5120'
$env:NINFER_KV_WINDOW = '32768'
$env:SERVE_TEE_MODE = 'slim'

$log = Join-Path 'logs' ("serve_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")
& python -X utf8 serve_tee.py $log "J:\ninfer-kvmem\engine\lineage\I3b_step13_fourlayer_20261015.exe" `
    "J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer" `
    "--host" `
    "127.0.0.1" `
    "--port" `
    "8094" `
    "--model-id" `
    "qwen3.8-27b-coder390" `
    "--max-context" `
    "262144" `
    "--kv-capacity" `
    "51200" `
    "--cuda-graph-allowance-mib" `
    "64" `
    "--kv-dtype" `
    "rk2v4-e8" `
    "--host-kv-mib" `
    "16384" `
    "--prefill-chunk" `
    "512" `
    "--spec" `
    "mtp" `
    "--draft-tokens" `
    "4" `
    "--vision" `
    "--vision-residency" `
    "overlay" `
    "--default-max-tokens" `
    "32768" `
    "--default-reasoning-effort" `
    "high" `
    "--default-thinking-budget" `
    "16000" `
    "--max-concurrency" `
    "1" `
    "--max-shared-prefixes" `
    "0" `
    "--presence-penalty" `
    "0" `
    "--temperature" `
    "0.7" `
    "--top-p" `
    "0.9" `
    "--top-k" `
    "20" `
    "--recover-invariant-failures" 