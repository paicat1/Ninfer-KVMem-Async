@echo off
REM ============================================================
REM  start-pq2-dflash-designc.bat  --  Design C control launcher
REM  SELF-BUILT engine (sm_120a, MSVC-compiled, Design C patch)
REM  Ternary Bonsai 2-27B v3 (full)
REM
REM  MODEL : models\Ternary-Bonsai-2-27B-ninfer-v3.ninfer
REM  ENGINE: engine\self-built-20261008\ninfer-serve.exe  (SELF-BUILT, current)
REM  PORT  : 8095  (avoids official 8094, both can run side-by-side)
REM
REM  === WHAT DESIGN C FIXES ===
REM  Official engine: when the model stops mid "thinking" phase the answer
REM  can be EMPTY (thinking never closed). Design C forces the target-
REM  control path so thinking closes and the model continues in the
REM  answer region.  (output_session.cpp L553-571)
REM
REM  === THINKING BUDGET (optional) ===
REM  --default-thinking-budget N caps model-origin thinking at N tokens,
REM  then forces the answer body with the remaining output budget.
REM  PURPOSE: stop the "xhigh thinking wall" ? thinking burns the whole
REM  output and produces zero body.  This is a SERVER-LEVEL (argv)
REM  setting because the OpenAI chat endpoint does NOT parse a request
REM  thinking_budget field (only Anthropic's thinking.budget_tokens does).
REM  Uncomment the line below to enable, e.g. N=16000.
REM  --default-thinking-budget 16000
REM
REM   ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "MODEL=%ROOT%models\\Ternary-Bonsai-2-27B-ninfer-v3.ninfer"
set "ENGINE=%ROOT%engine\\self-built-20261008\\ninfer-serve.exe"

if not exist "%MODEL%" (
  echo REFUSE: model not found: "%MODEL%"
  pause
  exit /b 3
)
if not exist "%ENGINE%" (
  echo REFUSE: self-built ninfer-serve.exe missing (need engine\self-built-20261008)
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
echo [note  ] Design C control: thinking-close must force body output
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b ^
  --max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --spec dflash2 --draft-tokens 12 --lm-head-draft --vision ^
  --default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1 ^
  --max-shared-prefixes 0 ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause >nul