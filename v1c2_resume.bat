@echo off
title ninfer-serve V1c2 resume (vision 64K, no growth, graph32)
cd /d J:\ninfer-kvmem
set NINFER_KV_WINDOW=32768
set NINFER_KV_SINK=5120
set NINFER_KV_RETRIEVE=8192
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
python serve_tee.py logs\serve_20261011_v1c2_resume.log ^
  "J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve.exe" ^
  "J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer" ^
  --host 127.0.0.1 --port 8094 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 65536 --kv-dtype rk2v4-e8 --host-kv-mib 16384 --cuda-graph-allowance-mib 32 ^
  --prefill-chunk 512 --spec mtp --draft-tokens 4 --vision-cpu ^
  --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 ^
  --max-concurrency 1 --max-shared-prefixes 0 --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 ^
  --recover-invariant-failures
echo.
echo [exit] ninfer-serve exited. press any key to close.
pause >nul
