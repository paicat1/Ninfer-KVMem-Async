@echo off
REM ============================================================
REM  start-coder390.bat  --  Coder390 BARE DECODE (no speculation)
REM
REM  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer
REM          ^-- the ORIGINAL factory artifact: bare decode does not touch the
REM              MTP head, so the q4_0 problem does not apply here. Using the
REM              untouched original keeps this arm a pure baseline.
REM  Engine: engine\self-built-20261008\ninfer-serve.exe  (SELF-BUILT, current)
REM  Port  : 8091
REM
REM  Purpose: the CONTROL ARM for every A/B test (MTP / ngram / DFlash2).
REM    Measured 2026-10-09 (same prompt as the MTP arm): 55.4 tok/s decode.
REM
REM  TUNED PARAMS -- kept IDENTICAL to start-coder390-mtp.bat so that the only
REM  difference between the two scripts is --spec mtp:
REM    --max-context 262144 / --kv-capacity 40960 / --kv-dtype rk2v4-e8
REM    --prefill-chunk 512 / NINFER_KV_WINDOW=32768 / --host-kv-mib 16384
REM
REM  NO --vision : the Coder390 artifact has no "vision" component; passing
REM                it aborts startup with "missing component vision".
REM  NO --spec   : bare decode IS the baseline.
REM
REM  The env lines below are the whole KV configuration (KVMem ring).
REM  The content scorer defaults ON whenever NINFER_KV_WINDOW is set.
REM  Setting NINFER_TERNARY_KVMEM=0 would be the NEGATIVE CONTROL, not a knob.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Put it in %ROOT%models\ or run:  set MODEL=D:\path\to\model.ninfer  ^&^& %~nx0
  pause
  exit /b 3
)
set "ENGINE=%ROOT%engine\self-built-20261008\ninfer-serve.exe"
if not exist "%ENGINE%" (
  echo REFUSE: self-built engine missing: "%ENGINE%"
  pause
  exit /b 4
)
set "CUDA_BIN=%ROOT%engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"
set "NINFER_KV_WINDOW=32768"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [mode  ] BARE DECODE (no --spec, no --vision) -- baseline / control arm
echo [tuned ] ctx 256K / pool 40K / rk2v4-e8 / prefill 512 / ring window 32K
echo [note  ] content scorer defaults ON (set NINFER_TERNARY_KVMEM=0 to disable = negative control)
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8091 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
