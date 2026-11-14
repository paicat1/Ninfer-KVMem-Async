# 违规记录：窗口不可见/被最小化/无窗口（T-WINDOW）

- 审计时刻：2026-10-19 01:09:46
- 审计器：`scripts\audit_windows.py`（独立层，非 CB 自报）
- 判据：有窗口 ⇒ 必须可见且非最小化；无窗口 ⇒ 亦违规

| pid | 进程 | 有窗口 | 最小化 | 可见 | 标题 |
|---|---|---|---|---|---|
| 16048 | powershell.exe | True | True | True | 选择 HANG-CATCH batch r7-r10 (auto-close when done) |

**处置**：立即恢复可见并说明；本文件为独立证据，不得删除。
