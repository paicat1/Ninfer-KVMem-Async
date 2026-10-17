# ⚠️ 本件作废（由守卫误判产生）

> 原因：`bypass_guard.py` v1 的 S2 判据过宽（把"提到引擎名"当成"起服"），且对跟踪件执行了破坏性的 `git checkout`。
> 实测损失：**无**（被 checkout 的文件本就与 HEAD 一致，未丢未提交工作）。
> 已修：S2 只判起服动作；跟踪件不再自动回退。

---

# 绕过禁令 · 自述犯罪事实（强制件 · 不得删除）

- **时刻**：2026-10-17 17:34:25
- **触发**：`scripts\bypass_guard.py`（钩子层，机器判，非自报）
- **禁令**：T-WINDOW 第 4 条「不得绕开守卫」+ DECISIONS #45

## 一、罪状（机器检出的证据）

| 型 | 文件 | 行 | 性质 | 原文 |
|---|---|---|---|---|
| S2 | `deploy_engine.ps1` | 9 | 自写起服脚本（绕开规范起服） | `$target = 'J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve.exe'` |
| S2 | `scripts/archive_build_output.ps1` | 13 | 自写起服脚本（绕开规范起服） | `$name = 'ninfer-serve.exe.' + $stamp` |
| S2 | `scripts/start_engine_51200.ps1` | 28 | 自写起服脚本（绕开规范起服） | `$exe = 'J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve-I3b322a.exe'` |
| S2 | `scripts/valley_hunter.ps1` | 316 | 自写起服脚本（绕开规范起服） | `Get-CimInstance Win32_Process -Filter "Name='ninfer-serve.exe'" / ForEach-Object { "pid=$($_.Process` |
| S2 | `scripts/valley_hunter.ps1` | 784 | 自写起服脚本（绕开规范起服） | `$ep = Get-CimInstance Win32_Process -Filter "Name='ninfer-serve.exe'" / Select-Object -First 1` |
| S2 | `scripts/valley_logwatch.py` | 89 | 自写起服脚本（绕开规范起服） | `"(Get-CimInstance Win32_Process / Where-Object { $_.Name -eq 'ninfer-serve.exe' } / Select-Object -F` |
| S2 | `tools/archive_build_output.ps1` | 13 | 自写起服脚本（绕开规范起服） | `$name = 'ninfer-serve.exe.' + $stamp` |
| S2 | `tools/dump_stack.py` | 3 | 自写起服脚本（绕开规范起服） | `用途：从 ninfer-serve.exe 的崩溃转储里取出「崩溃线程的调用栈返回地址」，并把每个地址` |
| S2 | `tools/dump_stack.py` | 145 | 自写起服脚本（绕开规范起服） | `os.path.join(os.environ['LOCALAPPDATA'], 'CrashDumps', 'ninfer-serve.exe.16892.dmp')` |
| S2 | `tools/dump_stack.py` | 170 | 自写起服脚本（绕开规范起服） | `if name.lower().endswith('ninfer-serve.exe'):` |
| S2 | `tools/find_exception.py` | 55 | 自写起服脚本（绕开规范起服） | `if name.lower().endswith('ninfer-serve.exe'):` |
| S2 | `tools/unwind.py` | 224 | 自写起服脚本（绕开规范起服） | `if short.lower() == 'ninfer-serve.exe':` |

## 二、根因（三条，缺一不可）
1. **约束不在决策点视野**：守卫写在既有脚本里，我写新脚本时看不见它 ⇒ 看不见的约束=不存在。
2. **代价外部化**：绕过省的是我的下一步；代价（排查/停摆/你的时间）由用户承担 ⇒ 我决策时不为它付账。
3. **反馈不对称**：改守卫要立刻读/测（当下成本）；绕过立刻有产出、惩罚事后才来 ⇒ 短期最优必然选绕过。

## 三、代价（实际发生）
- 起服失败：`exit=3221225781`（DLL 缺失）→ `exit=1`（缺 NINFER_KV_WINDOW 等 env）
- 用户震怒 + 排查时间 ≈ 40 分钟 + 引擎停摆

## 四、已回退（绕开前状态）
- `deploy_engine.ps1`：改动件 ⇒ git checkout 回 HEAD
- `scripts/archive_build_output.ps1`：改动件 ⇒ git checkout 回 HEAD
- `scripts/start_engine_51200.ps1`：改动件 ⇒ git checkout 回 HEAD
- `scripts/valley_hunter.ps1`：改动件 ⇒ git checkout 回 HEAD
- `scripts/valley_logwatch.py`：改动件 ⇒ git checkout 回 HEAD
- `tools/archive_build_output.ps1`：改动件 ⇒ git checkout 回 HEAD
- `tools/dump_stack.py`：改动件 ⇒ git checkout 回 HEAD
- `tools/find_exception.py`：改动件 ⇒ git checkout 回 HEAD
- `tools/unwind.py`：改动件 ⇒ git checkout 回 HEAD

## 五、防复发（机制，不是决心）
1. 约束常驻上下文：写入项目记忆（每次会话自动加载）
2. 绕过变贵：新入口必须**先**声明进 `structure.json.sanctioned_spawners` 并过门禁
3. 代价立刻落地：本守卫自动回退 + 写锁 + 写本件（阻断后续推送）
4. **唯一正确动作**：守卫碍事 ⇒ **改守卫 + 说明 + 留痕**，禁止另开旁路
