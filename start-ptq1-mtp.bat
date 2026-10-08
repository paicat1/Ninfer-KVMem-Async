@echo off
REM ============================================================
REM  start-ptq1-mtp.bat  --  tier launcher for the sm_120a engine pack
REM
REM  Model : models\bonsai2_27b_ternary_ptq1_native_mtp.ninfer   (put the model file in .\models\ next to this script,
REM          or set MODEL=... on the command line to point somewhere else)
REM  Port  : 8095
REM
REM  The six env lines below are the whole KV configuration. Since 2026-10-02 the
REM  content scorer defaults ON whenever NINFER_KV_WINDOW is set (no KVMEM_* variable
REM  is needed, and none is set here on purpose: the default IS the fixed behaviour).
REM  Setting NINFER_TERNARY_KVMEM=0 would be the NEGATIVE CONTROL, not a tuning knob.
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if not defined MODEL set "MODEL=%ROOT%models\\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Put it in %ROOT%models\\ or run:  set MODEL=D:\path\to\bonsai2_27b_ternary_ptq1_native_mtp.ninfer  ^&^& start-ptq1-mtp.bat
  pause
  exit /b 3
)
set "CUDA_BIN=%ROOT%engine"
set "PATH=%CUDA_BIN%;%CUDA_BIN%\x64;%PATH%"
set "NINFER_KV_WINDOW=16384"
set "NINFER_KV_RETRIEVE=8192"
set "NINFER_KV_RING=1"
set "NINFER_HOST_PAGEABLE=1"
set "NINFER_KV_REUSE_HOSTBACKED=1"
set "NINFER_TERNARY_PTQ1_FAST=1"

if not exist "%ROOT%engine\ninfer-serve-120a.exe" (
  echo REFUSE: engine\ninfer-serve-120a.exe is missing from this pack
  pause
  exit /b 4
)
set "ENGINE=%ROOT%engine\ninfer-serve-120a.exe"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [note  ] content scorer defaults ON (set NINFER_TERNARY_KVMEM=0 to disable = negative control)
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause