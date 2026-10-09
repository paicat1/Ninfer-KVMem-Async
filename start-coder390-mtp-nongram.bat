@echo off
rem ============================================================
rem  start-coder390-mtp-nongram.bat -- CONTROL ARM: copy-drafting (ngram) OFF
rem
rem  Identical to start-coder390-mtp.bat EXCEPT:
rem      + --ngram-draft-tokens 0    (turns copy drafting OFF)
rem      + port 8096 (vs 8095) and its own log file
rem
rem  WHY THIS ARM EXISTS
rem    speculative_options.h:32-41 -- "Copy drafting rides along with every
rem    drafter unless the command line sets its width":
rem        kDefaultNgramDraftTokens = 15;
rem        if (!width_explicit && backend != None) ngram_draft_tokens = 15;
rem    So a plain `--spec mtp` ALREADY drafts with ngram at width 15. The only
rem    way to measure what ngram contributes is to run this arm (width 0) and
rem    diff it against the standard arm:
rem
rem      python scripts\bench_spec.py --port 8095 ^
rem        --log logs\serve-coder390-mtp.log --label "MTP+ngram"
rem      python scripts\bench_spec.py --port 8096 ^
rem        --log logs\serve-coder390-mtp-nongram.log --label "MTP-only" ^
rem        --baseline bench_MTP+ngram.json
rem
rem  NOTE: both arms cannot run at once on a 16 GB card (weights alone are
rem  12.3 GiB) -- run one, stop it, then run the other.
rem
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
echo [mode  ] MTP K=4, copy-drafting OFF  (--spec mtp --draft-tokens 4 --ngram-draft-tokens 0)
echo [use   ] CONTROL ARM for the ngram A/B -- see the header comment
echo [tuned ] ctx 256K / pool 40K / rk2v4-e8 / prefill 512 / ring window 32K
echo [log   ] %ROOT%logs\serve-coder390-mtp-nongram.log   (console = slim view)
echo [warn  ] close other GPU apps first -- free VRAM swings ~250 MiB and decides startup

"%PY%" "%ROOT%serve_tee.py" "%ROOT%logs\serve-coder390-mtp-nongram.log" ^
  "%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8096 --model-id qwen3.8-27b-coder390-nongram ^
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384 ^
  --prefill-chunk 512 --spec mtp --draft-tokens 4 --ngram-draft-tokens 0 ^
  --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 ^
  --max-concurrency 1 --max-shared-prefixes 0 ^
  --kv-lease-growth --recover-invariant-failures ^
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20

echo.
echo [engine exited] errorlevel=%ERRORLEVEL%
pause
exit /b 0

:no_model
echo REFUSE: model not found: "%MODEL%"
pause
exit /b 3

:no_engine
echo REFUSE: self-built engine missing: "%ENGINE%"
pause
exit /b 4

:no_py
echo REFUSE: python.exe not found (J:\miniconda3 / %%LOCALAPPDATA%%\Programs\Python\Python312 / PATH).
pause
exit /b 5
