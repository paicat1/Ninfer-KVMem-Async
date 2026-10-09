@echo off
rem ============================================================
rem  start-coder390-mtp.bat -- Coder390 + MTP speculative decoding (FINAL tuned profile)
rem
rem  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer
rem  Engine: engine\self-built-20261008\ninfer-serve.exe
rem  Port  : 8095
rem
rem  Launched THROUGH serve_tee.py: the console shows the SLIM view (engine
rem  diagnostic spam -- "[ring] budgets", "[ninfer] mask hidden", "[ninfer]
rem  demote-other short" -- is hidden), while the FULL log is still written to
rem  logs\serve-coder390-mtp.log for grep. Set SERVE_TEE_MODE=full before
rem  running to see everything in the console instead.
rem
rem  MEASURED (same model / same prompt / same params; only --spec mtp differs):
rem    bare decode 55.4 tok/s  ->  MTP  73.2 tok/s  (prose, accept 22.6%)
rem                                MTP 184.3 tok/s  (code,  accept 93.8%)
rem
rem  TUNED PARAMS (measured on RTX 5080 16GB / sm_120):
rem    --max-context 262144   logical ceiling (model native max)
rem    --kv-capacity 40960    40K device pool = the "full-speed" span
rem    --kv-dtype rk2v4-e8    cheapest KV format (2bit key + 4bit value)
rem    --prefill-chunk 512    smaller workspace than the 1024 default
rem    NINFER_KV_WINDOW=32768 the ring switch; ALSO what allows
rem                           kv-capacity < max-context
rem    => runtime 1.71 GiB | free 449.6 MiB
rem
rem  NO --vision : this artifact has no vision component (use
rem               start-coder390-vision.bat for the factory build).
rem  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
rem ============================================================
setlocal
set "ROOT=%~dp0"

if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"
if not exist "%MODEL%" goto no_model

set "ENGINE=%ROOT%engine\self-built-20261008\ninfer-serve.exe"
if not exist "%ENGINE%" goto no_engine

set "PY="
if exist "J:\miniconda3\python.exe" set "PY=J:\miniconda3\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY for %%P in (python.exe) do if not defined PY set "PY=%%~$PATH:P"
if not defined PY goto no_py

set "CUDA_BIN=%ROOT%engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"
set "NINFER_KV_WINDOW=32768"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
set "SERVE_TEE_MODE=slim"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [mode  ] MTP speculative decoding (--spec mtp --draft-tokens 4)
echo [tuned ] ctx 256K / pool 40K / rk2v4-e8 / prefill 512 / ring window 32K
echo [log   ] %ROOT%logs\serve-coder390-mtp.log   (console = slim view)
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup

"%PY%" "%ROOT%serve_tee.py" "%ROOT%logs\serve-coder390-mtp.log" ^
  "%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
exit /b 0

:no_model
echo REFUSE: model not found: "%MODEL%"
echo         Expected the P1b recoded container (.mtp-iq4nl.ninfer). Rebuild with:
echo           python scripts\recode_mtp.py --src ORIGINAL.ninfer --mtp-src Q8MTP.ninfer ^
echo             --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst THIS_PATH --verify
pause
exit /b 3

:no_engine
echo REFUSE: self-built engine missing: "%ENGINE%"
pause
exit /b 4

:no_py
echo REFUSE: python.exe not found (J:\miniconda3 / %%LOCALAPPDATA%%\Programs\Python\Python312 / PATH).
echo         serve_tee.py needs it for the slim console view + log file.
pause
exit /b 5
