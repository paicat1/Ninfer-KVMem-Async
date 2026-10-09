@echo off
rem ============================================================
rem  start-coder390-vision.bat -- Coder390 with VISION on CPU threads
rem
rem  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer
rem          ^-- the FACTORY build. It is the ONLY artifact on this line that
rem              carries a "vision" component: our .mtp-iq4nl.ninfer and the
rem              original both have none, so any --vision* flag aborts startup
rem              with "Qwen3.8 config: missing component vision".
rem  Engine: engine\self-built-20261008\ninfer-serve.exe
rem  Port  : 8097
rem
rem  WHY --vision-cpu (source: serve_options.cpp:291-297, measured 2026-10-10):
rem    "cpu runs it on CPU threads with NO device Vision memory"
rem    => vision costs ZERO device VRAM. Measured: weights 12.3 -> 12.5 GiB,
rem       runtime 1.44 GiB, free 663.4 MiB, engine ready in 13.3s.
rem    COST: images are capped at 256 merged tokens (~512x512 pixels) and CPU
rem    encoding takes "one to a few seconds" per image.
rem
rem  POOL REDUCED TO 20K ON PURPOSE: the factory MTP head is q8_0 (451 MB)
rem  instead of our iq4_nl head (239 MB), so the 40K pool does not fit.
rem  Measured with 20K: free 663.4 MiB.
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

if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer"
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
  --default-max-tokens 8192 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
exit /b 0

:no_model
echo REFUSE: factory Q8MTP model not found: "%MODEL%"
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
