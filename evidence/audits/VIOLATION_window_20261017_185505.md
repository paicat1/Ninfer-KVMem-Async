# 违规记录：窗口不可见/被最小化/无窗口（T-WINDOW）

- 审计时刻：2026-10-17 18:55:05
- 审计器：`scripts\audit_windows.py`（独立层，非 CB 自报）
- 判据：有窗口 ⇒ 必须可见且非最小化；无窗口 ⇒ 亦违规

| pid | 进程 | 有窗口 | 最小化 | 可见 | 标题 |
|---|---|---|---|---|---|
| 15236 | powershell.exe | True | True | True | VALLEY-LOGWATCH [running] -- engine-log channel; tiers <60 valley / <6 deep / <1.5 vdeep; close = stop |
| 22092 | powershell.exe | True | True | True | HUNTER-WATCHDOG [running] -- alert if hunter ledger silent > 420s; close window = stop |
| 15060 | powershell.exe | True | True | True | E1-PASSIVE-WATCH [running] -- 1 sample/min; close = stop |
| 22780 | cmd.exe | True | True | True | C:\Windows\system32\cmd.exe - C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe  serve_tee.py J:\ninfer-kvmem\logs\test_valleywatch.log J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve.exe J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer --host 127.0.0.1 --port 8094 --model-id qwen3.8-27b-coder390 --max-context 262144 --kv-capacity 49152 --cuda-graph-allowance-mib 64 --kv-dtype rk2v4-e8 --host-kv-mib 16384 --prefill-chunk 512 --spec mtp --draft-tokens 4 --vision --vision-residency overlay --request-log-jsonl evidence\reqlogs\reqlog_watch.jsonl --request-log-max-mib 128 --request-log-keep 2 --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 --max-concurrency 1 --max-shared-prefixes 0 --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20 --recover-invariant-failures  |
| 10480 | powershell.exe | True | True | True | VALLEY-HUNTER [running] -- 1 probe/min, case on decode<60+verify>=100 x2; auto-stop after $MaxHours h or log cap $LogCapMB MB |

**处置**：立即恢复可见并说明；本文件为独立证据，不得删除。
