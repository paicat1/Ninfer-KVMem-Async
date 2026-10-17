@echo off
rem ============================================================
rem  start-coder390-vision.bat -- Coder390 with VISION on CPU threads
rem
rem  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer
rem          ^-- the GRAFTED build (2026-10-10): our .mtp-iq4nl line + the factory
rem              vision tower copied byte-identical (333 objects, 282.0 MiB).
rem              It replaced the factory Q8MTP artifact (deleted 2026-10-11): the
rem              grafted head is iq4_nl (239 MB) vs factory q8_0 (451 MB) => the
rem              pool fits MUCH larger (55K+vision measured, free 490.4 MiB).
rem  Engine: engine\self-built-20261008\ninfer-serve.exe
rem  Port  : 8097
rem
rem  WHY --vision-cpu (source: serve_options.cpp:291-297, measured 2026-10-10):
rem    "cpu runs it on CPU threads with NO device Vision memory"
rem    => vision costs ZERO device VRAM. Measured (grafted build, 55K pool):
rem       free 490.4 MiB; DSH image recognition succeeded in 26.9s (TTFT 19.8s
rem       = CPU encoding). COST: images are capped at 256 merged tokens
rem       (~512x512 pixels) and CPU encoding takes tens of seconds per image.
rem
rem  POOL: this bat keeps the conservative 20K (guaranteed start on a dirty
rem  desktop); the grafted build measured fine at 40K and 55,296 with vision.
rem  ⚠ hemostat: vision + no-growth hits a scatter assertion (issue 39,
rem  2026-10-11) => this bat keeps --kv-lease-growth ON (short vision outputs
rem  never reach the 4,096 wall).
rem
rem  NOT --vision-residency resident: that keeps the tower resident in device
rem  memory (~1.4 GB) -- the exact opposite of what this script is for.
rem
rem  Launched THROUGH serve_tee.py (slim console view + full log to
rem  logs\serve-coder390-vision.log). Set SERVE_TEE_MODE=full to see all.
rem  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
rem ============================================================
setlocal
set "ROOT=%~dp0"

if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer"
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
echo [mode  ] MTP + VISION on CPU threads (--vision-cpu: zero device vision VRAM)
echo [tuned ] ctx 256K / pool 20K (reduced: factory q8_0 head is 451 MB) / rk2v4-e8
echo [note  ] images capped at 256 merged tokens (~512x512); CPU encode = a few seconds
echo [log   ] %ROOT%logs\serve-coder390-vision.log   (console = slim view)
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup

"%PY%" "%ROOT%serve_tee.py" "%ROOT%logs\serve-coder390-vision.log" ^
  "%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8097 --model-id qwen3.8-27b-coder390-vision ^
  --max-context 262144 --kv-capacity 20480 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 --spec mtp --draft-tokens 4 --vision-cpu ^
  --default-max-tokens 8192 --default-reasoning-effort high --default-thinking-budget 16000 --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
exit /b 0

:no_model
echo REFUSE: grafted vision model not found: "%MODEL%"
echo         That file is the ONLY artifact here carrying a vision component.
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
