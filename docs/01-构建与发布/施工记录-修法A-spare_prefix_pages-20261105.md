# 施工记录：修法 A `spare_prefix_pages`（2026-11-05）

> 用户令：「全部同意」（含 ① 源码施工 ② 编译窗口 ③ 转现役 + #68/#70/#67/#76）。
> 挂账 #64。参考实现 `refs\community\tancau-ninfer-kvmem-ring`，取值口径与语义按其 `program_impl.h:1219-1229` / `context.cpp:1551-1563` / `docs\maintainer\ring-reuse-depth-and-failure-brief.md` §7。
> **本文件记录的是「当前生效二进制」与其源码改动集的反溯关系**：`engine-src` 是独立未跟踪子仓，改动不提交（保持 HEAD 不变以免打断 asset-dual 树的同一性检查），故以本记录 + 备份 + binary sha 三者共同锚定。

## 1. 改了什么（2 文件，`+31/-9`）

| 文件 | 改动 | 行数 |
|---|---|---|
| `program_impl.h` | `ensure_ring_room` / `demote_kv_pages_to_host` 两个声明各加 `std::uint32_t spare_prefix_pages = 0U`；补语义注释 | `+5` |
| `context.cpp` | 两处定义加同名参数；`is_preferred` 加 `page < spare_prefix_pages \|\|` 短路；`ensure_ring_room` 内两处 `demote_kv_pages_to_host` 转发该参数；`ensure_sequence_kv_mapped` 新增取值点并把值传给 Main / Backend 两次 `ensure_ring_room` | `+17/-9` |

**语义**：`spare_prefix_pages` 让第一遍降级跳过逻辑页 `[0, N)`；第二遍仍会让出，所以调用方的「必须腾出的页数」保证不变。作用是把「即将发布 capture 的前缀」从 oldest-first 的第一遍降级里保留下来——capture 只有在 frontier 以下每页都 Device-resident 时才能落袋。

`[EVIDENCE] git -C engine-src diff --stat: program_impl.h | 9 +++-- ;; storage/context.cpp | 31 +++++++++++++----- ;; 2 files changed, 31 insertions(+), 9 deletions(-)`

## 2. 取值口径（为什么不取 `total_tokens`、为什么不含 `shared_candidates`）

取值点（`context.cpp` `ensure_sequence_kv_mapped`，`ring_profile_mark(1)` 之后）：

```cpp
std::uint32_t spare_prefix_pages = 0U;
if (sequence.lane < max_concurrency && requests[sequence.lane].prefill &&
    !requests[sequence.lane].prefill->capture_groups.empty()) {
    spare_prefix_pages = kv_pages_for_frontier(
        requests[sequence.lane].prefill->capture_groups.back().frontier);
}
```

- 与参考实现同源：`requests[sequence.lane].prefill->capture_groups.back().frontier`（参考文档 §7 原文）。
- **不取 `total_tokens`**：那是本步要映射的 frontier，decode 阶段会等于当前序列长度（可达 100K+），会把几乎所有页都列入保护、使第一遍永远空跑，等于把降级退化成纯 oldest-first 的第二遍。
- **不含 `shared_candidates`**：本仓 `RequestControl::Prefill`（`program_impl.h:532`）只保留 `capture_groups`；`shared_candidates` 属 plan 期结构（`RequestBasePlanImpl:213` / `AdmissionCandidateImpl:271`），`PreparedPromptData`（`frontend\prepared_prompt.h:158`）也不持有。运行期发布走 `capture_groups`，故按参考实现口径即可，没有漏项可加。
- 无 pending capture 时恒为 `0`，decode 不付任何代价。

## 3. 备份（T-BACKUP）

`_safety_backups\20261105_pre_fixA\`：`context.cpp 174982 / 325AAE3EE7276FFD`、`program_impl.h 114471 / CAA4DCA16CED34F6`、`decode.cpp 74233 / C60BB6EDAACBC1F1`、`program_impl.cpp 47041 / 8070DB82833BC9ED`。

源码行尾基线：`context.cpp crlf=0 bare_lf=3201`、`program_impl.h crlf=0 bare_lf=2055` —— **纯 LF**，改动按 LF 写入，改后 `bare_lf` 分别 `3218` / `2060`，`crlf` 仍为 0。

## 4. 编译（唯一入口 `build\s6_1208a.bat`）

| 项 | 结果 |
|---|---|
| 单目标预检 | `context.cpp.obj` 编译 `PRECHECK_EXIT=0 elapsed_s=6.2` |
| 全量 | `[20/20] Linking CXX executable apps\ninfer-serve.exe`、`[18/20] Linking ... apps\ninfer-serve.exe`、`BUILD-EXIT=0 2026/11/05 7:22:39.90` |
| 耗时 | **24 秒**（`CMakeCache` 在 + 仅 2 文件受影响，增量 20 目标；非冷编 55–66 min） |
| 亲和性 | `affinity=OK 0x0FFF`（启动脚本 `work\data\start_build_fixA.ps1` 钉 P 核） |
| 窗口 | 标题 `ninfer FIX-A build sm_120a - auto-closes when build exits`，`Normal` 可见，跑完自关 |

`[EVIDENCE] build-out\build_engine.log: BUILD-EXIT=0 2026/11/05 7:22:39.90`

## 5. 两道机器门

- **ARCH-GATE**：`exe=ninfer-serve.exe ELF=384 sm_120a=384 sm_86=0 ptx=0` → `ARCH-GATE: OK`
- **DEPLOY-DLLS**：`DEPLOY-DLLS: OK files=16`（显式重跑，`deploy_exit=0`）

`[EVIDENCE] 命令输出: ARCH-GATE: OK ;; DEPLOY-DLLS: OK files=16`

## 6. 产物、封存与转现役

- 产物：`build-out\build-1208a\apps\ninfer-serve.exe`，`1333993472 B`，`sha16=F814B07A2B71ED4E`，mtime `2026-11-05 07:22:32`。
- 封存：`engine_assets.ps1 adopt -Label FIXA-20261105` → `engine\lineage\ninfer-serve-FIXA-20261105.exe`（同 sha），`MANIFEST.md` 已追加一行（原代号列 `-`，用途待补）。
- 转现役：`engine_ctl.ps1 -Action start -Exe <lineage 新件> -Tag fixA -Depth 2 -Pool 57344 -Experimental`
  - 不加 `-Experimental` 时被 T#0059 拦下：`[GATE T#0059] refuse to overwrite live engine ... (pass -Experimental to acknowledge; backup kept)`。
  - 加 `-Experimental` 后：`T#0059: backup skipped (identical hash in lineage MANIFEST)`（现役 RC8 的 sha 在台账，故不再生成重复备份）→ **现役位 `engine\self-built-20261008\ninfer-serve.exe` 已换成 `F814B07A2B71ED4E`**，进程 `pid=23220` 用的即该件。
- **回滚锚点**：旧现役 `B93B179176A0DC23` 在 `engine\lineage\ninfer-serve-RC8.exe`（只读），新件亦在 lineage（`F814B07A`）——两侧都可 `Copy-Item` 秒级还原。
- **DLL 对账**：现役位 16 件 vs `build-out\build-1208a\apps` 16 件，逐件 SHA256 `dll_sha_diff=0`（本次未改依赖，无需同步）。

`[EVIDENCE] 命令输出: live size=1333993472 mtime=07:22:32 sha16=F814B07A2B71ED4E ;; pid=23220 path=...\self-built-20261008\ninfer-serve.exe`
`[EVIDENCE] 命令输出: live_dll=16 build_dll=16 ;; dll_sha_diff=0`

## 7. 起服与冒烟

| 项 | 结果 |
|---|---|
| 起服参数 | `--kv-capacity 57344`（**不是默认 65536**）、`--spec mtp --draft-tokens 4`、`--vision --vision-residency overlay`、`--host-kv-mib 16384`、`--cuda-graph-allowance-mib 64`、`--max-context 262144`、`--max-concurrency 1` |
| VRAM | `vram before start: used=58 MiB / 16303 MiB` |
| 就绪 | `warmup complete | 381 ms`、`listening on http://127.0.0.1:8094 | model qwen3.8-27b-coder390` |
| 接口 | `/v1/models` → **200**，`context_window=262144` |
| 推理 | `POST /v1/chat/completions` → `HTTP OK 0.8s`，`content=2`，`completion_tokens=26`（reasoning 24） |
| ring | `[ring] budgets: skeleton=80, evidence=128, recent=0, free=688 (pool 896)`、`ensure profile ... free=896` |

`[EVIDENCE] logs\test_fixA.log: 2026-11-05 07:24:46.168 INFO warmup complete | 381 ms ;; listening on http://127.0.0.1:8094 | model qwen3.8-27b-coder390`
`[EVIDENCE] 命令输出: models_status=200 ;; HTTP OK elapsed_s=0.8 ;; content=2`

## 8. 未验证项（如实列出，不冒充）

修法 A 的**效果**验证需要池压力下的长序列，本轮只做了「不崩 + 服务可用」冒烟。以下仍待 #68 受控序列复验（多小时长跑，需固定提示词 + 每档 ≥2 次）：

- 页漂移三特征（hidden 高 + host 98–101% + decode≈3 tok/s）共现复测
- 34 轮 cache replay 对照
- 超池 `prompt exceeds` 行为
- MTP / DFlash / DFlash2 三后端冒烟
- `mask hidden` 分布对比
- `publish declined` / `capture install` 深度 / `hit` 是否提升（修法 A 的直接收益指标）

**不得**把本轮冒烟结论表述为「修法 A 已生效并提升命中」——那只证明件能编译、能起、能出 token。
