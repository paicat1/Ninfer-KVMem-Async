# 违规记录：窗口不可见/被最小化/无窗口（T-WINDOW）

- 审计时刻：2026-10-17 17:29:00
- 审计器：`scripts\audit_windows.py`（独立层，非 CB 自报）
- 判据：有窗口 ⇒ 必须可见且非最小化；无窗口 ⇒ 亦违规

| pid | 进程 | 有窗口 | 最小化 | 可见 | 标题 |
|---|---|---|---|---|---|
| 14796 | cmd.exe | False |  |  |  |
| 13424 | python.exe | False |  |  |  |
| 23816 | python.exe | False |  |  |  |
| 17716 | ninfer-serve-I3b322a.exe | False |  |  |  |
| 18276 | powershell.exe | False |  |  |  |
| 25796 | python.exe | False |  |  |  |
| 15064 | python.exe | False |  |  |  |
| 11564 | powershell.exe | False |  |  |  |

**处置**：立即恢复可见并说明；本文件为独立证据，不得删除。
