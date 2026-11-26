# 设计草案 · 三档驻留策略 + 动态 restore 预算 + 流式 prefill（M2）

> 2026-11-25 · 办公室侧（设计草案，**未施工、未验证**）
> **性质**：设计草案。文中的时间/收益均为**量级推算**，不得作为验收线；可引用的只有标「实测」的锚点。
> 内容基线：`origin/main = e49bad9`（11-24 23:54）；引擎源码 = `origin/engine-main = b9a9cc6`（11-14 快照，现役待钉）
> 硬件基线：RTX 5080 16 GB · PCIe 5.0 x16 · **DDR4-3200 双通道（已确认）**
> 同线文档：`预登记-刀6尾部必打与final重算-调研-CB-20261125.md`（ac41682）、`调研-预填充提速方向与L3收益重估-方向性试验-CB-20261125.md`

---

## 〇、五句结论

1. **物理前提先钉死**：`decode` 每 token 要读一遍「它看得见的全部 KV」，读 host 会掉到 **≤7 tok/s** ⇒ **decode 的可见集永远受显存池限制，"超池走内存全量"做不到**。
2. 16 GB 上 200K prompt 的真实处境是：池 1,920 页 = **122,880 token 可驻留**，剩余 **约 78K 必须被丢弃**——所以问题不是"要不要丢"，而是**"丢得聪不聪明"**。
3. 因此智能切换的收益是 **「选页更准 + prefill 更快」**，不是"不丢信息"。切档判据必须是 **`kept` 装不装得下**，不是"有没有超池"。
4. **最便宜的一步不是流式 kernel，而是「动态 restore 预算」**：`min(kept, avail)`，轻度超池即可全可见，约 1 天、零内核改动。
5. **`verification_status` 必须最先做**：`overflow > 0` 时现在的响应是「HTTP 200 + 看起来正常的答案」，这是产品级最危险的缺陷，比慢严重。

---

## 一、物理前提与量级（可引用）

| 项 | 值 | 性质 |
|---|---|---|
| 池容量 | 1,920 页 = 122,880 token | 实测（§245 交付口径） |
| 页大小 | ≈1.56 MB（由「512 页 ≈ 800 MB」反推） | 派生 |
| 每轮 restore 预算 | **1,024 页**（= min(`RETRIEVE` 65,536/64=1,024, 池 1,920×`SHARE` 60%=1,152)） | **实测**：`serve_20261125_074635.log.gz` 内 `[ring] budgets` **20,567 行全为 `evidence=1024 (pool 1920)`**，恒等式 80+1024+0+816=1,920 通过 |
| restore 每页税（C 步后） | **0.48–1.45 ms** | 实测（§241） |
| 每 chunk restore 成本 | ≈0.92 s（1,024 × ~0.9 ms） | 派生（原 0.45 s 基于过时的 512 页） |
| 读全历史（3 GB）@22 GB/s | **136 ms** | 派生（双通道 + pageable 折半） |
| decode 读全历史 | 136 ms/token ⇒ **≤7 tok/s** | 派生 |
| host 环 | 16 GiB ≈ **6,500 页** | 实测（配置） |

**⇒ 三条硬结论**：① decode 不能流式；② prefill 流式的带宽占用仅 ~9%（3 GB vs 1.45 s 计算）；③ 16 GB 上 200K 上下文必然丢弃 ~78K token，只能"丢得聪明"。

---

## 二、三档驻留策略

### 2.1 触发量（不是"是否超池"）

```
working_set  = n_blocks（当前请求的逻辑块数）
avail        = pool_pages − skeleton − recent − frontier_reserve
overflow     = working_set − avail
kept         = |select_retrieval_pages(...)|   ≤ min(SCORE_BUDGET/64, working_set)
```

### 2.2 四档行为

| 档 | 条件 | 行为 | 响应的 `verification_status` |
|---|---|---|---|
| **M0 全驻留** | `overflow ≤ 0` | 现状：不搬页；无压力不打分（刀5） | `verified` |
| **M1 页驻留（全可见）** | `overflow > 0` 且 `kept ≤ avail` | 搬 kept，全部可见 | `verified` |
| **M1′ 截断（现状默认）** | `kept > avail` | 截到 512 页；**部分被选中的页看不见** | **`unverified`** |
| **M2 流式 prefill** | `kept > avail` 且策略允许 | prefill 分块流读全历史；结束时按分数选 `avail` 页驻留 | `unverified`（丢得更少） |

**M2 的边界（必须写死在实现里）**：**只作用于 prefill**。decode 前必须把最终 `kept ∩ avail` 的页搬回显存；搬不下的部分按分数取前 `avail`，其余显式丢弃并标 `unverified`。

### 2.3 开关与降级

| 开关 | 值 | 语义 |
|---|---|---|
| `NINFER_KV_RESIDENCY_POLICY` | `adaptive`（默认） | 按 2.2 自动选档 |
| | `stream` | 强制 M2（A/B 与极端长文） |
| | `paged` | 强制 M1/M1′（当前行为，兜底） |
| **降级规则** | M2 任一步失败（partials 分配失败 / kernel 不可用 / 显存不足） | **fail-closed → 回 M1′ + `unverified`**，绝不静默走"半流式" |

---

## 三、动态 restore 预算（建议先行，约 1 天）

### 3.1 问题

现在的预算是 `min(RETRIEVE/64, 池×SHARE%)`（`context.cpp:3030-3032`）。交付口径（池 1,920 页、`RETRIEVE`=65,536、`SHARE`=60，后者自 2026-11-15 起进启动器 `L930/L1625`）= `min(1,024, 1,152)` = **1,024 页**，实测常量（见 §1 表）。
但**池还有空槽时，这 1,024 仍是浪费**——明明能装 1,500 页，却只搬 1,024。

### 3.2 改法

```cpp
// 现状（示意，context.cpp:3030-3032）：env 与池份额取小
const std::int32_t budget = std::min(retrieve_pages, pool * share_pct / 100);   // 交付口径 = 1,024

// 改为：取「kept 需求」与「实际可用槽」的较小者
const std::int32_t avail  = pool_pages - skeleton - recent - in_flight - frontier_reserve;
const std::int32_t budget = std::min<std::int32_t>(kept_wanted, avail);
```

### 3.3 效果与边界

| 场景 | 现状 | 动态预算 |
|---|---|---|
| 池内（M0） | 不打分不搬 | 不变 |
| 轻度超池（kept ≈ 1,500） | 截到 1,024（丢 476 页可见性） | **全可见** |
| 重度超池（kept ≈ 3,000） | 截到 1,024 | 仍受 avail 限制（约 1,500） |
| 池贴顶（avail ≈ 0） | 1,024 | 回落到与现状相同 |

**风险**：`frontier_reserve` 必须留够，否则重演 §233「提检索 = 抢 frontier 的页 ⇒ prefill 2.2–25.6 tok/s」。

---

## 四、M2（流式 prefill）设计要点

### 4.1 数据通路

```
prefill 第 N 个 chunk
  ↓ attention 按 tile（如 256 页 = 16K token）遍历历史
  ↓ 每 tile：host → pinned 中转环（双缓冲，≤64 MB）→ 计算
  ↓ online softmax 的 (m, l, acc) 跨 tile 传递（partials 落显存，约 12.7 MB 级）
  ↓ 算完即释放，池不需要装下历史
```

### 4.2 为什么可行（源码层）

- `ContextAttentionPolicy` 已是**页寻址**：`PageMapped = true`、`block_table`、`context_tile(kv_head, key0, physical_page)`（11-14 快照）；
- `selected_blocks` 位图已存在（原注释：「KVMem-style host-offload prototype」）；
- 打分 kernel 的 phase1 已是 **online softmax**（running max + rescale）⇒ 分段合并的写法在本仓有先例。

### 4.3 工程风险（三条，按严重度）

| # | 风险 | 说明 |
|---|---|---|
| 1 | **event/stream 生命周期** | 上游 `Neroued/ninfer#357` 在 host-tier restore 上 `cudaStreamWaitEvent` 无效句柄 → `0xC0000409` / 驱动侧 AV。合并/流式改造必须保证 **event 不跨请求复用** |
| 2 | **跨 tile softmax 数值** | partials 顺序改变 ⇒ 与现役非 bitwise 相同；需精度门（vs 现役 ≤1e-5，vs FP64 参考不劣于现役×1.5） |
| 3 | **decode 边界** | 流式只允许在 prefill；decode 若误用 ⇒ ≤7 tok/s。需运行期断言（`phase == prefill`） |

---

## 五、`verification_status`（最先做，几天）

### 5.1 为什么

**已经有一条告警通道，不是从零开始。** `GenerationService::warn_on_prompt_over_pool`（`generation_service.cpp:299-338`）在 prompt 超过驻留池时写 console 警告，文案逐字包含 "HTTP 200 and a plausible wrong answer … Treat every answer to this request as unverified against its context"，并自述 "a MISSING line is never evidence that a request was safe"。

它的三个缺陷正是本方案要补的：
1. **只在 console**，客户端拿不到（HTTP 响应无字段）；
2. **30 秒节流**（`kOverPoolInterval`），连续超池请求会被抑制成一行；
3. **无量化**：只说"unverified"，不告诉客户端丢了多少 token。

⇒ 本节不是新造机制，而是把已有告警升级为**结构化响应字段**（并去掉节流对可见性的影响）。

### 5.2 定义

```
response.verification_status ∈ { "verified", "unverified" }

verified   ⇔ overflow ≤ 0            （全驻留，无丢弃）
           ∨ (kept ≤ avail)           （全可见）
unverified ⇔ kept > avail             （有丢弃；M1′ 与 M2 同）
```

**附加字段（建议）**：`context_dropped_tokens`（估算丢弃量 = (working_set − avail) × 64），让客户端能判断"丢了多少"。

### 5.3 客户端语义

agent 侧应按 `unverified` 决定是否采信、是否降级（例如改为分块提问），而不是把标记当装饰。

---

## 六、判据（预注册，写死再跑）

| # | 判据 | 门槛 | 状态 |
|---|---|---|---|
| **①** | 三针 **155 / 937 / 1797** 在 120K / 200K 超池下**全部出现在最终驻留集合** | 硬门 | 未测 |
| **②** | `recall@resident`：M2 / 动态预算 相对 M1′ 的提升 | **≥ +20 百分点**才值得做 M2 | 未测 |
| **③** | prefill 时间：M2 不比 M1′ 慢 | ≤ +10% | 未测 |
| **④** | 精度：M2 的答案与"把上下文降到池内"的理想情况一致率 | ≥95% | 未测 |
| **⑤** | 回退：M2 任一步失败 ⇒ fail-closed 到 M1′ + `unverified` | 必须 | — |
| **⑥** | 显存：pinned 中转环 ≤64 MB，池尺寸不变 | 必须 | — |

**⇒ 判据 ② 是"要不要做 M2"的总闸**：如果现在三针本来就都在驻留集合里（即 `recall@resident` 已接近 100%），那 M2 只剩 +7~11% 的速度，**不值得投两周**。

---

## 七、执行顺序

| 顺位 | 动作 | 成本 | 依赖 |
|---|---|---|---|
| **1** | `verification_status` + `context_dropped_tokens` 贯通 | 几天 | 无 |
| **2** | **量 `recall@resident`**（日志：`KEPT` 行 + `ring retrieve` 的 `first/last`） | 0 | 无 |
| **3** | **动态 restore 预算**（`min(kept, avail)`） | 1 天 | 需 `frontier_reserve` 定值 |
| 4 | 刀6′（尾部必打 + final） | 3–5 天 | 需两次复测基线 |
| 5 | M2 流式 prefill | 2 周 | 仅当 ② 显示有缺口 |

---

## 八、与既有结论的关系

| 既有结论 | 本草案的关系 |
|---|---|
| §241 C 步（每页税 4.1–7.5 → 0.48–1.45 ms） | **已把 M2 的速度红利吃掉大半** ⇒ M2 只剩 +7~11%（见 §4） |
| §233「池贴顶提检索 = 抢 frontier」 | 动态预算必须留 `frontier_reserve`，否则重演 |
| §245 刀5 懒打分（无压力零打分） | M0 档保持不动 |
| §245 刀6 退役（压力区恒等必打） | M1/M1′ 沿用；刀6′ 是独立优化 |
| §249 A/B 定裁（2026-11-26） | B 件 `EFB3F69B` 405.7 s vs 在役件 `8E437B71`@`PERIOD=1` 397.9 s（+2%）⇒ **代码非回归**；恒等必打的池满代价 **+241 s**（对撞口径 397.9−156.7）+242 s（三次中位 398.7−156.7），**+154%**；满池尾部 **76.8 tok/s**（384 tok/5 s，每 chunk 一次全量打分） |
| §241「超池答案一律 unverified」 | 本草案把它**结构化**为 API 字段（§5） |

---

## 九、不确定性清单

| 项 | 状态 |
|---|---|
| `recall@resident` 现值 | **未测**（决定 M2 生死） |
| `frontier_reserve` 合理值 | **未定**（动态预算的安全边界） |
| M2 的 partials 尺寸与位置 | **未定**（估计 12.7 MB 级，需按 (token × head × 256) 实算） |
| 512 页截断点、`kept` 二次截断 | 来自 11-14 快照（`context.cpp` L1754-1755 / L1779），**11-24 现役待钉** |
| 动态预算对池碎片的影响 | **未测**（`avail` 是瞬时值，可能抖动） |

---

## 十、引用

- 构建史：§233（提检索净负）、§241（C 步实测 + 超池 unverified 注记）、§242（打分 kernel 86.5%）、§245（刀5/刀6 三口径、口径状态总表 L8009）、§247（刀6 退役与构建不可复现）
- 源码（11-14 快照，现役待钉）：`kvmem_score.h` L286/L458-506、`kvmem_select.h` L61-92、`context.cpp` L1631-1632 / L1754-1755 / L1779 / L3058、`ops/kernel/paged_kv_address.cuh` L14-22、`ops/softmax_attention/dense/context/kernel.cuh` L7-27
- 同线文档：`预登记-刀6尾部必打与final重算-调研-CB-20261125.md`、`调研-预填充提速方向与L3收益重估-方向性试验-CB-20261125.md`
- 上游：`Neroued/ninfer#357`（host-tier restore 崩溃，open）、`#415`（热路径驱逐，open）、`ashalliants/ninfer-3090#208`（同族慢态，open）
