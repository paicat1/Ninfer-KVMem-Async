@echo off
rem ============================================================
rem  start-coder390.bat -- Coder390 BARE DECODE (no speculation) -- control arm
rem
rem  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer
rem          ^-- the ORIGINAL factory artifact: bare decode never touches the
rem              MTP head, so the q4_0 problem does not apply here, and using
rem              the untouched original keeps this arm a pure baseline.
rem  Engine: engine\self-built-20261008\ninfer-serve.exe
rem  Port  : 8091
rem
rem  Every other parameter is IDENTICAL to start-coder390-mtp.bat, so the only
rem  difference between the two arms is --spec mtp.
rem  Measured 2026-10-09 (same prompt as the MTP arm): 55.4 tok/s decode.
rem
rem  Launched THROUGH serve_tee.py (slim console view + full log to
rem  logs\serve-coder390.log). Set SERVE_TEE_MODE=full to see all.
rem
rem  NO --vision : the original artifact has no vision component.
rem  NO --spec   : bare decode IS the baseline.
rem  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
rem ============================================================
setlocal
set "ROOT=%~dp0"

if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"
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
echo [mode  ] BARE DECODE (no --spec, no --vision) -- baseline / control arm
echo [tuned ] ctx 256K / pool 40K / rk2v4-e8 / prefill 512 / ring window 32K
echo [note  ] content scorer defaults ON (set NINFER_TERNARY_KVMEM=0 to disable = negative control)
echo [log   ] %ROOT%logs\serve-coder390.log   (console = slim view)
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup

"%PY%" "%ROOT%serve_tee.py" "%ROOT%logs\serve-coder390.log" ^
  "%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8091 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 ^
  --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
exit /b 0

:no_model
echo REFUSE: model not found: "%MODEL%"
echo         Put it in %ROOT%models\ or run:  set MODEL=D:\path\to\model.ninfer  ^&^& %~nx0
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
