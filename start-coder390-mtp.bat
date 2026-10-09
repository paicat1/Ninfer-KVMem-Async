@echo off
REM ============================================================
REM  start-coder390-mtp.bat  --  Coder390 + MTP speculative decoding
REM
REM  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer
REM  Engine: engine\self-built-20261008\ninfer-serve.exe  (SELF-BUILT, current)
REM  Port  : 8095
REM
REM  STATUS WARNING (2026-10-09, P0):
REM    The ORIGINAL artifact's MTP head is declared "gguf_q4_0", which the
REM    engine does NOT support -> this script will FAIL at load time with
REM      "weight/000789: unknown tensor format: gguf_q4_0"
REM    until P1 (data-side recode via scripts\recode_mtp.py) produced a
REM    container whose MTP head uses a supported format (target: gguf_q8_0).
REM    Point MODEL at that recoded container to use this script.
REM
REM  NO --vision : Coder390 has no "vision" component (would abort startup).
REM
REM  The env lines below are the whole KV configuration (KVMem ring).
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Put it in %ROOT%models\ or run:  set MODEL=D:\path\to\recoded-model.ninfer  ^&^& %~nx0
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
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [mode  ] MTP speculative decoding (--spec mtp --draft-tokens 4)
echo [warn  ] original artifact MTP head is gguf_q4_0 (unsupported) -- use the
echo [warn  ] P1-recoded container, otherwise load fails with unknown tensor format
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
