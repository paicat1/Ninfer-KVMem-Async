# 根因：67K 超池崩溃（0xC0000409 静默 abort）— 2026-10-12

> 承接 `docs/状态归档-20261012凌晨-v2.1与崩溃待续.md` 的第 3 节（"待办：67K 超池崩溃"）。
> 本文只记**已取证的事实**与**已做的修复**；未做的部分在最后一节，等裁决。

## 1. 一句话结论

超池请求（67,441 token > 65,536 池）走 `adopt host-backed` 准入时：

1. **发布阶段** `start_request → start_sequence → commit_activation` 抛
   `std::logic_error("KV activation has an unavailable Device page")`；
2. 该异常的 catch（`progress_materialization_transaction`，materialization.cpp:2355-2358）调
   `release_materialization_staging` → `abort_materialization_transfers`；
3. 中止路径对**已被消费/已失效的 activation** 再调 `page_reservation()`，抛
   `std::logic_error("KV activation reservation is stale")`；
4. 它撞上 `catch (...) { std::terminate(); }`（materialization.cpp:1421）→ `abort()`
   → **进程静默死亡**（exit `0xC0000409`，引擎日志**零行**）。

## 2. 证据链（每条都可复核）

| 环节 | 证据 |
|---|---|
| 退出码 | 日志 `===== serve_tee end (exit=3221226505) 2026-10-12 01:27:26 =====` |
| 系统记录 | 事件日志 01:27:22 Application Error + 01:27:25 WER 1001：`BEX64`、`c0000409`、`P9=0000000000000007`（FAST_FAIL_FATAL_APP_EXIT = abort）、故障模块 `ucrtbase.dll+0x7286e` |
| 转储 | `%LOCALAPPDATA%\CrashDumps\ninfer-serve.exe.16892.dmp`（259.9 MiB，01:27:25） |
| 符号化前提 | 用**同一批 .obj** 重链接并加 `/MAP`（`apps\ninfer-serve.mapcheck.*`）；新 exe 与原 exe 仅 PE 头 `0x100-0x200` 与 .rdata 一小段不同，**`.text` 逐字节相同** ⇒ map 的 RVA 对崩溃二进制有效 |
| 崩溃线程 | 自写 x64 unwind（`.pdata`/UNWIND_INFO）：`ucrtbase(abort)` ← `__catch$?release_materialization_staging@…$2`（与 `?catch$2@?0??abort_materialization_transfers@…` 被 **ICF 合并**到 0x1cd0edd）← `VCRUNTIME140_1` EH ← ntdll |
| 抛错点 A（中止路径） | 返回地址 `page_reservation+0x7c`（kv_store.h:1047-1052）→ 紧邻字面量 **`"KV activation reservation is stale"`**；其调用者帧 = `abort_materialization_transfers+0x1d8`（= materialization.cpp:1376/1386） |
| 抛错点 B（上游触发） | 返回地址 `commit_activation+0x821` → 紧邻字面量 **`"KV activation has an unavailable Device page"`**（kv_store.h:1101/1105）；调用者 `start_sequence+0xae5`（prefill.cpp:449/466） |
| 崩溃前日志序列 | `adopt host-backed: frontier=66814 need=1044 usable=1024 host_backed=37` → `demote-other short: freed=0 want=37 … noresident=1183 partial=1` → `demote-other short: freed=0 want=48 …` → 死亡 |

## 3. 为什么"超池"才崩（机制）

- 池 1024 页 < 采纳范围 1044 页 ⇒ 环必须**边映射边 demote**（日志里的 `demote-other short`、
  `demote profile: batch=8 submit`），pool 与 residency 全程在动。
- `judge_deferred_replicas`（materialization.cpp:822-837）用**瞬时快照** `missing > room`
  决定"是否延迟物化"；`prepare_activation`（kv_store.h:1014-1028）按那一刻的 residency 定预留量；
  `commit_activation`（kv_store.h:1076-1107）在**发布时**又用**新的** residency 去**断言**。
- 环模式下 prepare → commit 之间 demote/restore 必然改变 residency ⇒ 断言被打穿，
  且**打穿之后的清理路径**再撞上同一个失效状态 ⇒ 静默 abort。
- 附带事实：req#54（50,648 token，未超池）正常完成 ⇒ 崩溃条件与"prompt ≥ pool"一致，
  与引擎自己的超池警告文案（"measured: prompt >= pool is the condition that reproduces it"）吻合。

## 4. 本次修复（已增量编译验证，**未部署**）

改动文件：`src/models/qwen3_5/program/transactions/materialization.cpp`（**仅 .cpp**，
增量编译 `BUILD-EXIT=0`，新 exe `1317263872` B，02:30:00，已确认新日志字符串在二进制内）。

1. 新增匿名命名空间 helper `terminate_with_reason(site, std::exception_ptr)`：
   先 `fprintf` 原因 + `fflush(stderr)`，再 `std::terminate()`。
   **5 处**裸 `catch (...) { std::terminate(); }` 全部改为带原因：
   `release_materialization_staging`（两处 fence 同步）、`abort_materialization_transfers`、
   `publish_pressure_work`、`abort_pressure_work`。
2. `abort_materialization_transfers`：activation 回滚改走 `abort_restores` lambda ——
   `page_reservation` 抛错（activation 已被 publish 阶段消费，或它所在的地址已释放）时，
   打印 `[ninfer] abort_materialization_transfers: <which> activation already consumed (…)`，
   **跳过回滚**；`restores` 为空也直接返回（无事可回滚）。

**语义依据**：失效 activation 意味着这些页已归序列所有（或随地址一起释放），
`abort_device_replica` 再动它们反而会误伤活数据 —— 跳过才是正确的中止语义。

**备份/回滚锚**：`J:\Bonsai-Official\_backups\materialization.cpp.bak_20261012_pre_abortfix`
（sha256 前缀 `DF7EE2EBA5B7946A`，133700 B）；引擎源码仓 `s6-20261008` @ `4c4dcfa`，
该文件改动前是干净状态（`git checkout --` 亦可回滚）。

## 5. 仍未解决（需裁决）

修复后：**引擎不再崩**，但超池请求仍会**失败**（HTTP 500），且现在会留下可读日志。
根因（快照断言 vs 环模式移动靶）仍在，彻底修法需要 **kv_store.h（头文件 → 全量编译）**：

- 建议①（.cpp 可做）：`judge_deferred_replicas` 在环模式恒 `defer`（只要范围内有非驻留页），
  避免"按快照承诺全驻留、发布时被打穿"。
- 建议②（头文件）：`commit_activation` 的预留量检查由 **assert** 改为 **reconcile**
  （按当前 residency 调整预留量；池满时抛可读错误而不是断言失败）。
- 建议③：`deferred_missing`/`missing_replicas` 的口径统一（现在一个按 `address.page_count`、
  一个按 `pages_for_tokens(activation_frontier)`）。

## 6. 本次新增的取证工具（`j:/ninfer-kvmem/tools/`，均被 .gitignore 排除，不入库）

| 工具 | 用途 |
|---|---|
| `dump_stack.py` | 手写 minidump 解析（线程/模块/内存/异常流）+ 栈扫描 |
| `unwind.py` | x64 真回溯：读各模块 `.pdata`+UNWIND_INFO 逐帧展开 |
| `sym_resolve.py` | map 符号化；`--verify/--diff/--diff-range/--sections` 校验镜像一致性与差异定位 |
| `find_exception.py` | 在转储内存里找异常对象（按 vtable）+ 读出 `what()` |
| `find_throw_string.py` | 从"抛出点返回地址"反查它引用的字符串字面量（= 哪条不变式） |
| `range_check.py` | 转储内存区间构成与地址包含判断 |

崩溃取证标准流程（可复用）：WER 取异常码/P9 → CrashDumps 取转储 → 同批 .obj 重链接 `/MAP`
（先验 `.text` 逐字节一致）→ `unwind.py` 拿真调用链 → `find_throw_string.py` 定不变式原文。
