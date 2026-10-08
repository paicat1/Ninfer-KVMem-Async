@echo off
REM ============================================================
REM  start-pq2-dflash.bat  --  Official engine launcher (dflash tier)
REM  NInfer sm_120a official pack | Ternary Bonsai 2-27B v3 (full)
REM
REM  MODEL : models\Ternary-Bonsai-2-27B-ninfer-v3.ninfer  (full Q12 + lm-head)
REM  ENGINE: engine\ninfer-serve-120a.exe  (official, NO Design C patch)
REM  PORT  : 8094
REM
REM  === TERM GLOSSARY (what each arg means) ===
REM  --spec dflash2      speculative-decoding backend = "dual-flash" draft
REM                       head. drafts 12 tokens/round, then verify; the
REM                       verified tokens are reused so decode is faster.
REM  --draft-tokens 12  how many tokens the draft head guesses per round.
REM  --lm-head-draft    use the optimized output-head as the draft model
REM                       (the one saved with the artifact).
REM  --kv-dtype k8v4    KV cache dtype: k8v4 = 8-bit weights + 4-bit values
REM                       (the delivery tier; ~half the memory of bf16 KV).
REM  --kv-capacity 17920  KV token pool size this launch reserves.
REM  --max-context 262144  context window upper bound (KV ring headroom).
REM  --host-kv-mib 16384   host (system RAM) KV mirror size, MB.
REM  --prefill-chunk 1024  prefill chunk granularity.
REM  --default-max-tokens 32768  cap on a request's total output.
REM  --default-reasoning-effort none  thinking OFF by default (clients may
REM                       enable per request; keeps it deterministic/fast).
REM  --max-concurrency 1  one request at a time (deterministic A/B runs).
REM  --max-shared-prefixes 0  no cross-request KV prefix sharing.
REM  --temperature/--top-p/--top-k  sampler defaults (clients may override).
REM
REM  === KV MEMORY RING (KVMem) ===
REM  The six NINFER_* env lines configure the KV ring so long context can
REM  span device+host. Defaults below are the fixed production behaviour:
REM    NINFER_KV_WINDOW=16384   the retained KV window size.
REM    NINFER_KV_RETRIEVE=8192   retrieve budget per query.
REM    NINFER_KV_RING=1         enable the KV ring (retention across turns).
REM    NINFER_HOST_PAGEABLE=1   host KV pages are pageable (reclaimable).
REM    NINFER_KV_REUSE_HOSTBACKED=1  reuse host-backed KV on new requests.
REM    (The content scorer defaults ON whenever the ring is set. Setting
REM     NINFER_TERNARY_KVMEM=0 would be the NEGATIVE CONTROL, not a knob.)
REM
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "MODEL=%ROOT%models\\Ternary-Bonsai-2-27B-ninfer-v3.ninfer"
if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  echo         Put it in %ROOT%models\\ or run:  set MODEL=D:\path\to\model.ninfer  ^&^& %~nx0
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

if not exist "%ROOT%engine\ninfer-serve-120a.exe" (
  echo REFUSE: engine\ninfer-serve-120a.exe is missing
  pause
  exit /b 4
)
set "ENGINE=%ROOT%engine\ninfer-serve-120a.exe"

echo [engine] %ENGINE%
echo [model ] %MODEL%
echo [note  ] content scorer defaults ON (set NINFER_TERNARY_KVMEM=0 to disable)
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8094 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec dflash2 --draft-tokens 12 --lm-head-draft --vision ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause >nul