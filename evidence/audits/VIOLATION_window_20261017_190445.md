# 违规记录：窗口不可见/被最小化/无窗口（T-WINDOW）

- 审计时刻：2026-10-17 19:04:45
- 审计器：`scripts\audit_windows.py`（独立层，非 CB 自报）
- 判据：有窗口 ⇒ 必须可见且非最小化；无窗口 ⇒ 亦违规

| pid | 进程 | 有窗口 | 最小化 | 可见 | 标题 |
|---|---|---|---|---|---|
| 15236 | powershell.exe | True | True | True | VALLEY-LOGWATCH [running] -- engine-log channel; tiers <60 valley / <6 deep / <1.5 vdeep; close = stop |
| 22092 | powershell.exe | True | True | True | HUNTER-WATCHDOG [running] -- alert if hunter ledger silent > 420s; close window = stop |
| 15060 | powershell.exe | True | True | True | E1-PASSIVE-WATCH [running] -- 1 sample/min; close = stop |
| 10480 | powershell.exe | True | True | True | VALLEY-HUNTER [running] -- 1 probe/min, case on decode<60+verify>=100 x2; auto-stop after $MaxHours h or log cap $LogCapMB MB |

**处置**：立即恢复可见并说明；本文件为独立证据，不得删除。
