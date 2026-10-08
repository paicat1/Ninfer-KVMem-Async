@echo off
REM ============================================================
REM  a4-arm-C.bat -- A4 hang A/B arm C: SELF-BUILT 20261008 + our patches
REM  Our migration deliverable (branch s6-20261008 tip 3b9dc83).
REM  Same on-site A4 args as arm A. Visible console; close = stop.
REM  ASCII-only on purpose (cmd OEM/ANSI codepage).
REM ============================================================
setlocal
set "ROOT=%~dp0.."
set "PY=J:\miniconda3\python.exe"
set "MODEL=%ROOT%\models\Ternary-Bonsai-2-27B-ninfer-v3.ninfer"
set "ENGINE=%ROOT%\engine\self-built-20261008\ninfer-serve.exe"
set "LOG=%ROOT%\logs\a4_armC.log"
set "CUDA_BIN=%ROOT%\engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
if not exist "%MODEL%" ( echo REFUSE: model missing: %MODEL% & pause & exit /b 3 )
if not exist "%ENGINE%" ( echo REFUSE: engine missing: %ENGINE% & pause & exit /b 4 )
echo [arm   ] C (self-built 20261008 + patches)
echo [engine] %ENGINE%
echo [port  ] 8097
echo [log   ] %LOG%
"%PY%" "%ROOT%\serve_tee.py" "%LOG%" "%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8097 --model-id qwen3.8-27b ^
  --max-context 163840 --kv-capacity 163840 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec dflash2 --draft-tokens 7 --lm-head-draft --vision ^
  --default-max-tokens 32768 --default-reasoning-effort medium --default-thinking-budget 16000 ^
  --max-concurrency 1 --preserve-thinking --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 ^
  --kv-lease-growth --recover-invariant-failures
echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause >nul
