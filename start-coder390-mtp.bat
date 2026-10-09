@echo off
REM ============================================================
REM  start-coder390-mtp.bat  --  Coder390 + MTP speculative decoding
REM
REM  Model : models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer
REM  Engine: engine\self-built-20261008\ninfer-serve.exe  (SELF-BUILT, current)
REM  Port  : 8095
REM
REM  STATUS (2026-10-09, P1b): WORKING -- this is the FINAL tuned profile.
REM    The factory artifact's MTP head is declared "gguf_q4_0", which the engine
REM    does NOT support. The .mtp-iq4nl.ninfer container carries the same head
REM    recoded to "gguf_iq4_nl" (same byte length, full-block L1 verification
REM    passed; head data taken from the official Q8MTP build, a higher-precision
REM    source than the original q4_0 head).
REM
REM  MEASURED (same model / same prompt / same params; only --spec mtp differs):
REM    bare decode 55.4 tok/s  ->  MTP  73.2 tok/s  (prose, accept 22.6%)
REM                                MTP 184.3 tok/s  (code,  accept 93.8%)
REM    outputs semantically identical, no degradation.
REM
REM  TUNED PARAMS (all measured on this box: RTX 5080 16GB / sm_120):
REM    --max-context 262144    logical ceiling (model native max)
REM    --kv-capacity 40960     40K device pool = the "full-speed" span
REM    --kv-dtype rk2v4-e8     cheapest KV format (2bit key + 4bit value)
REM    --prefill-chunk 512     smaller workspace than the 1024 default
REM    NINFER_KV_WINDOW=32768  the ring switch; ALSO the thing that allows
REM                            kv-capacity < max-context (without it the engine
REM                            refuses to start: "--kv-capacity must be at least
REM                            --max-context")
REM    => runtime 1.71 GiB | free 449.6 MiB
REM
REM  NO --vision : Coder390 has no "vision" component (would abort startup).
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
if not defined MODEL set "MODEL=%ROOT%models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Expected the P1b recoded container. Rebuild it with:
  echo           python scripts\recode_mtp.py --src ORIGINAL.ninfer --mtp-src Q8MTP.ninfer ^
  echo             --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst THIS_PATH --verify
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
echo [mode  ] MTP speculative decoding (--spec mtp --draft-tokens 4)
echo [tuned ] ctx 256K / pool 40K / rk2v4-e8 / prefill 512 / ring window 32K
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b-coder390 ^
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
