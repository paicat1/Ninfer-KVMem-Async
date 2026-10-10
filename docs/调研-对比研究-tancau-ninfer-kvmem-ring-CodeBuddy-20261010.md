# 调研：第三方项目 `tancau/ninfer-kvmem-ring` 对比研究

> 署名：**CodeBuddy**（H 盘讨论环境）｜日期：2026-10-10｜状态：**研究稿**（源码/文档逐字读取，clone 于 `refs/tancau-ninfer-kvmem-ring/`）
> 对象：https://github.com/tancau/ninfer-kvmem-ring （视频 BV1XMpu6MEDG 作者的项目）
> 用途：看他的思路、找与我们的异同/优劣/可借鉴点。全部结论带证据（文件:行 / 提交 hash）。

---

## 〇、一句话

NInfer 引擎**另一条血统**（`ashalliants/ninfer-3090`）上的 **KVMem ring 自移植**项目——他"造" ring，我们"用" ring；工程深度（引擎源码级）高于我们，但硬件与模型不同、速度低一个量级（硬件所限，非思路问题）。

---

## 一、项目概况

| 项 | 内容 | 证据 |
|---|---|---|
| 仓库 | `tancau/ninfer-kvmem-ring`（fork of `ashalliants/ninfer-3090`；亦提及 `iamwavecut/ninfer-3090` `franken/v0.11` 分支） | README-RING.md / BENCH-RESULTS.md §4.1 |
| 硬件 | **RTX 3060 12GB / sm_86 / Win10 LTSC / 32GB RAM** | README-RING.md:7 |
| 模型 | **Ternary-Bonsai-2-27B**（NInfer 三值 v3 件 **9,520,051,456 B**——与 Bonsai 线同件；对比阶段用 PTQ1_0.gguf 5.93GB） | README-RING.md:11 / BENCH-RESULTS.md §4.1 |
| 核心成果 | **96K device pool 服务 256K 逻辑上下文**（12G 卡）；dense 160K PPL 5.639521 **逐 bit 不变**（62/62 采样点 delta 0） | README-RING.md:7-9 |
| 生产配置 | **96K 池 / 262K 上下文 / 思考预算 8192** | 提交 `d24596d`："production launcher to 96K/8192" |
| 关键技术动作 | ① 自移植 KVMem ring（**拆 8 道约束锁**）② 自噬循环修复（3 行）③ 验证体系（L0–L7 + A/B/C 矩阵） | KVMEM-PORT-PLAN.md / `adf3ed4`/`9cd3993` |

---

## 二、他的思路（核心技术路线）

### 2.1 自移植 ring：拆 8 道约束锁（KVMEM-PORT-PLAN §"约束层清单"）

让"设备池 < 逻辑上下文"生效，需拆的 8 层（**同一约束出现在多个层，只改一处不够**）：

| # | 层 | 位置 | 处理 |
|---|---|---|---|
| 1 | 启动检查 | `serve_options.cpp` | 去掉 `kv_capacity >= max_context` |
| 2 | 规划器曲线 | `planning/startup.cpp`（两处） | `minimum_pages` 改为 concurrency |
| 3 | plan_cache | `state/decoder_state.cpp` | 去掉 `physical_page_groups < logical_pages` |
| 4 | 准入可行性 | `planning/pressure.cpp` | 逻辑页需求钳到池大小 |
| 5 | 峰值拟合 | `storage/context.cpp` | `physical_peak_fits` + deficit 钳位 |
| 6 | 物化预检 | `pressure.cpp` | 靠 #5 通过 |
| 7 | 页预留 | `storage/kv_store.h`（4 处） | 预留改为**逻辑承诺**（分离逻辑/物理） |
| 8 | 整段提示一次性映射 | `program/prefill.cpp` | 改为按 prefill 块增量映射 |

### 2.2 会计模型（他自称"最重要的一处认知"）

引擎不变式：**owner 独占设备 KV 页数 = entitlement（常驻+预留）**，与请求计划精确一致（`commit.cpp` 有断言）。
⇒ 不能把预留钳到池大小（断言必失败）；正确做法 = **分离逻辑承诺（reservation）与物理占用（allocated_pages_）**。

### 2.3 掩码时序（第二处关键认知）

回收发生在**映射时**；注意力在映射后、提交前 ⇒ 掩码必须在"**映射后、注意力前**"安装（原先在 commit 后 = 来不及，prefill 会读到已被覆盖的旧页）。

### 2.4 自噬循环修复（视频里的"3 行改动"）

**问题**（提交 `adf3ed4`/`9cd3993` 逐字）：每个 decode 轮**重复恢复同样的锚页**（restore+install 186ms/轮）——因为 `demote_own` 在 decode 里没有 spare protection，turn-start restore 刚带回的页马上被"slack hunger"驱逐，下一轮又 restore。

**修复**：`ensure_sequence_kv_mapped` 加 `restore_preferred`（默认 true）；**三个 decode 调用点传 false**（decode.cpp 三处）；prefill/capture/commit 保持默认。decode 时不再 mid-turn restore（掩码仍跟随 residency；驱逐仍先 D2H 落盘，数据不丢）。

**效果**：强锚 decode **7.5–9.0 → 26.7–31.6 tok/s**（召回保持，prefill 不变）。

### 2.5 验证体系（高标准）

- **A 回归**：池==上下文时与原版**逐 bit 一致**（PPL 5.639521，62 采样点 delta 0）
- **B 证伪**：丢 50% 页必须显著变差（PPL ×1.266）——防"死代码"
- **C 功能 + C″ dense 对照**：32K 池 + 60K 提示 → 针**不可检索**（"文本里没有这个码"）；dense 池 → 答出针 ⇒ 判别力验证
- **L0–L7 分级**（residency 不变量 / 数值等价 / T>1 / PPL / 召回 / 负控 / 平坦性 / 有损性边界）

### 2.6 其他关键发现（他踩过的坑）

- **GDN 补偿洞察**："丢掉 50% 全注意力 KV，PPL 只涨 26.6%"——Qwen3.8 是混合注意力，GDN 层是循环状态、不受掩码影响、仍看全部历史
- **Windows WDDM 计费**：pinned 主机 KV 会被映射进 GPU 地址空间**按同一预算计费**；钳制 `budget = (free_device − 1 GiB) / 2`；解法 = 分页内存
- **复用深度公式**（维护者文档）：`depth = pool − working_set`；落袋（publish）要求 `[0, frontier)` 每页在设备，否则 `publish declined`——"**把池调大不是方案，它只是把悬崖挪到更高处**"
- **腾挪失败静默**：`demote_*` 短计数被调用方全部 `(void)` 丢弃——"ring 模式对 KV 容量既不检查、也不保证"（他指出的设计缺陷）
- **保险丝 bug**（视频提及）：`--reasoning-budget` 的判定"等号误写成大于等于"→ 计数器永不归零 → 熔断失灵
- **过度思考问题**（BENCH-RESULTS §三）：chat 模板 `reasoning_effort` 默认 **xhigh**；llama.cpp/KVMem 默认 `--reasoning-budget -1`（无限）；**"ninfer 默认开启 thinking；KVMem 默认 think=0（关闭）——这就是两者体验差异的主因"**；对策 = `--reasoning-effort medium` + `--reasoning-budget 2048`（**保险丝**）

---

## 三、与我们（本项目）的异同

| 维度 | 我们（ninfer-kvmem） | tancau | 说明 |
|---|---|---|---|
| **引擎血统** | `1314521gjy/ninfer-fusion-kvmem`（**官方融合版**） | `ashalliants/ninfer-3090` + **自移植 ring** | **两个不同 fork，同上游 `Neroued/ninfer`** |
| ring 来源 | 上游融合（`src/ops/kvmem/` 26 件 + qw3/10 件） | 自己移植（8 锁全拆） | 我们"用"，他"造" |
| 硬件 | RTX 5080 16G / **sm_120a** | RTX 3060 12G / sm_86 | 差一代半 |
| 模型 | Coder390（Qwen3.8-27B，Q2，12.37 GiB） | Ternary-Bonsai-2-27B（9.52 GB，三元） | |
| KV dtype | `rk2v4-e8` | `nvfp4`（ring）/ `rk8v4`（dense） | |
| 池 / 上下文 | 40K / 256K | 96K / 256K（生产） | |
| decode | **105 tok/s**（40K 池短答）；用户实测峰值 ~200 | 51.2（dense 60K）/ **26.7–31.6**（ring 修复后） | 硬件不同，**效率同量级**（3060→5080 约 2–3×） |
| MTP | K4（系统扫描过 4/7/12 + ngram 混合） | MTP3 + draft head | 我们调优更细 |
| 工程深度 | 配置级 + 编译补丁（3 类 MSVC） | **引擎源码级**（ring 移植 + 性能修复） | **他更深** |
| 验证 | 判活 + 探针 + A/B + STANDALONE 单测 | **PPL 逐 bit + NIAH 三针 + A/B/C 对照矩阵** | 他更系统 |
| 文档 | 构建史 + 复核台账（52 轮）+ 复现指南 | PORT-PLAN + BENCH + 维护者文档 | 各有侧重 |

**同**：池<上下文思路、`NINFER_KV_*` 环境变量族、Windows、Qwen3.8-27B 系模型、MTP 投机、KVMem 式 ring 机制（block-sparse working-set）。

---

## 四、他比我们好的地方

1. **引擎源码级改造能力**：8 道锁、会计模型（逻辑/物理分离）、掩码时序、CUDA Graph 掩码指针固化问题——我们只到"用引擎 + 编译补丁"层面。
2. **性能诊断深度**：自噬循环定位（计时器三级点名 setup/submit+sync/post；拆分 ensure 为 score/demote/map/restore+install）。
3. **验证方法学**：逐 bit 回归 + 证伪测试（B）+ 对照矩阵（C/C″）——比我们的"判活+探针"更系统。
4. **有损性量化**：主动测出"窗口<上下文丢什么"（L7）+ GDN 补偿洞察。
5. **"过度思考"对策**（reasoning-effort/预算保险丝）——**与我们的撞墙问题同源**。
6. **WDDM 主机 KV 计费处理**（钳制公式 + 分页内存）。

## 五、我们比他好的地方

1. **ring 实现更成熟**（血统优势）：我们的融合版是"五拍体 + preferred 保护 + lease 机制（kv_lease_growth）+ B32 检索预算默认开（2026-10-07）+ 可审计预算行（`[ring] budgets: skeleton/evidence/recent/free`）"——`context.cpp:2389+` 逐字证据；他的版本有"腾挪失败静默"缺陷 + 复用深度受限（`publish declined`）。
2. **硬件与模型**：5080（sm_120a）vs 3060（sm_86）；Coder390（新）vs Bonsai（三元，能力受损——用户已否）。
3. **速度**：同量级效率下，绝对速度高 2–4 倍。
4. **MTP 调优**：K 扫描（4/7/12 系统扫）+ ngram 混合实测（他是 MTP3 固定档）。
5. **工程管理**：双智能体 + 52 轮复核台账 + 证据纪律——流程严谨度。
6. **生态位**：我们跟随"官方融合线"（上游持续维护）；他维护自造 fork（8 锁的长期维护成本）。

---

## 六、可借鉴清单（优先级排序）

| # | 借鉴点 | 优先级 | 可行性/动作 |
|---|---|---|---|
| 1 | **"保险丝"经验**（reasoning-effort/预算对策；"ninfer 默认开 thinking vs KVMem 默认 think=0"） | ★★★ | **直接关联 DSH 撞墙讨论**——见 §七 |
| 2 | **自噬循环自查**：我们的 decode 三处调用点（decode.cpp:479/677/931）**也执行 restore 拍**（ensure 五拍第 4 拍），需验证有没有同款 churn | ★★★ | 回家实测：decode 时间分布 / 日志 restore 计数 |
| 3 | **性能诊断方法**（计时器三级点名） | ★★ | 需要时移植思路（不改引擎，先测） |
| 4 | **验证方法学**（A/A′ 逐 bit 回归、B 证伪、C/C″ 对照） | ★★ | 补进我们的验证体系文档 |
| 5 | **8 锁清单**（对照检查融合版对应约束层） | ★ | 认知价值（上游已处理，防回归时有用） |
| 6 | **WDDM 计费公式**（`budget=(free−1GiB)/2`） | ★ | 对照 Bonsai 线 16G 主机 KV 配置 |
| 7 | **复用深度公式**（`depth = pool − working_set`） | ★ | 理解 `--max-shared-prefixes` / capture/publish 领域 |

---

## 七、⭐ 与当前 DSH 撞墙讨论的交叉发现（重要）

tancau 的项目与我们在讨论的问题**高度交叉**，提供独立佐证：

1. **"过度思考"同款现象**：B站用户反馈（4070TiS 16G）"bonsai2 过度思考离谱……调一堆无关工具、任务 12 分半"——与我们讨论的"思考停不下来/撞墙"同类。
2. **他的对策与我们的讨论同向**：`reasoning-effort medium` + **`reasoning-budget 2048`（保险丝）**——正是我们讨论的"降 tb / 对齐输出预算"思路。
3. **⭐ 双环境行为差异的独立佐证**：他明确写 **"ninfer 默认开启 thinking；KVMem 默认 think=0（关闭）——这就是两者体验差异的主因"**——与用户观察（纯 KVMem"行为正常" vs NInfer"老撞墙"）**方向一致**：**思考配置/处理的差异**很可能就是两个环境行为差异的关键变量（对应我们候选 1★）。
4. **保险丝 bug 教训**：思考预算的实现有细节坑（`==` 写成 `>=` → 永久失灵）——提醒：思考预算类机制要验证"真的会熔断"。

---

## 八、结论

- **他的项目**：引擎级深度的"自造 ring"（8 锁 + 自噬循环修复 + 高标准验证），把 12G 卡推到 256K；代价是速度受硬件限制（26.7–51.2 tok/s）与自维护 fork 成本。
- **我们的项目**：用成熟融合版（五拍 + lease + preferred 保护）+ 更强硬件 + 更细调优，速度高 2–4 倍；工程管理更严（双智能体+台账）。
- **最大可借鉴三件事**：① **保险丝经验**（直接用于撞墙问题）② **自噬循环自查**（我们可能有同款 decode churn，待实测）③ **诊断/验证方法学**（计时器三级点名 + 逐 bit 回归）。

---

## 十、第二轮核对：tancau 引擎级修复 vs 我们的引擎（2026-10-10 追加）

> 起因：外部报告（另一环境）指出 tancau 有三条引擎级修复、建议核对血缘后搬运。本环境用**两边本地源码**逐条核对（我们的 = `engine-main` @ Bonsai clone；他的 = `refs/tancau-ninfer-kvmem-ring`）。

### 10.1 核对结果总表

| # | tancau 的修复 | 提交 | 我们引擎的对应状态 | 结论 |
|---|---|---|---|---|
| 1 | 自噬循环：decode 跳过 mid-ensure restore | `adf3ed4`/`9cd3993` | 无 `restore_preferred`；我们的融合版是"五拍体 + preferred 保护 + hysteresis" | ⚪ 机制不同，**churn 与否需实测** |
| 2 | **保险丝失灵**：`==` 应改 `>=` | `24c8ea5` | **`output_session.cpp:581` 正是 `==`** | 🔴 **同款 bug，我们中** |
| 3 | **超预算 throw** → OutputLimit | `24c8ea5` | **`output_session.cpp:524` `> budget` → `throw`** | 🔴 **同款，我们中** |
| 4 | **control 交接被拒 throw** → OutputLimit | `15abab8` | **`output_session.cpp:653/656` 同款 `throw`** | 🔴 **同款，我们中** |
| 5 | progress 保活（不受 `return_progress` 门控） | `202f098` | **同样被门控**（`openai_chat.h:30` 默认 false；`openai_chat_http.cpp:54` 条件） | 🔴 **同款，我们中** |

### 10.2 关键证据（逐字）

**tancau `24c8ea5`（保险丝本体）**：
> "The control handoff tested `model_thinking_tokens == budget`, so once the counter went past the budget -- exactly what the overshoot path sees -- the fuse could never fire again and the model was free to think indefinitely. That is the runaway: 16,037 thinking tokens observed against a 24,576 budget, with the fuse that should have stopped it silently disarmed. It now tests `>=`."

**tancau `15abab8`（交接拒绝）**：
> "…an untyped throw that no transaction-layer handler catches, so it reached the Engine's catch(...) and failed every in-flight request. A run that merely ran out of thinking budget therefore ended the whole conversation. … The request log shows the control path firing twice in 198 requests"
> "**Lowering --default-thinking-budget is only safe once this lands**; before it, a smaller budget made the refusal more likely and killed the conversation when it happened."

**tancau `202f098`（保活）**：
> "DSH dsh-llm-pi-ai kills streams after 300 s idle, rearmed only by yielded parsed events, and a 173K root prefill is silent for 15+ min. The engine already had per-chunk progress events but gated them on a client return_progress flag no agent client sends, so the watchdog always won."

**我们的对应代码（`engine-main`，逐字）**：
- `output_session.cpp:581`：`… model_thinking_tokens == *impl_->preview_semantic.budget) { … control_pending = true; … ApplyTargetControl; }` ← **`==`**
- `output_session.cpp:524`：`… model_thinking_tokens > *impl_->preview_semantic.budget) { throw std::logic_error("model output exceeded the licensed thinking budget"); }`
- `output_session.cpp:653/656`：`throw std::logic_error("canonical thinking control did not close the thinking phase");` / `…reasoning channel…`
- `openai_chat.h:30`：`bool return_progress = false;`；`openai_chat_http.cpp:54`：`.prompt_progress = request.stream && request.return_progress,`

### 10.3 对"降 tb 方案"的影响（重要）

原方案（降 tb 到 DSH max_tokens 之下）新增**三个前置条件**：
1. 修 L653/656 throw（否则"模型拒绝交接"→ 终结对话；他实测 198 请求中 2 次）
2. 修 L581 `==` → `>=`（否则 **MTP/overshoot 场景下保险丝失灵 → 无限思考**——可能是"思考停不下来"的机制来源）
3. 修 L524 throw → OutputLimit（否则超预算 → 终结对话）

**tancau 逐字警告：修复落地前降 tb 不安全。** 修复前替代路径 = DSH 侧调大 `streamIdleTimeoutMs`（零成本）+ 保持现状观察。

**另**：tancau 后来把默认 tb 从 8192 **提高到 24576**（`3c7b6bc`："8192 cut legitimate creative work"）——降 tb 有质量代价的实践证据。

### 10.4 更正外部报告一处表述

外部报告写"保险丝 bug：= 误写成 >="——**方向相反**。以 tancau 提交为准：修复前 `==`、修复后 `>=`（`==` 在计数器越过后永不成立 = 失灵）。**结论仍成立**（这条正对着我们的坑），机制表述应为"**`==` 应为 `>=`**"。

### 10.5 更新后的动作清单

| # | 动作 | 类型 | 成本 |
|---|---|---|---|
| 1 | DSH 侧：查 `streamIdleTimeoutMs` 并调大（他设 3600000） | 配置 | 零 |
| 2 | 引擎补丁：throw×2 → OutputLimit + `==` → `>=`（照 tancau diff 移植） | 引擎改动 | 小（~60 行） |
| 3 | 引擎补丁：progress 保活（照 `202f098`） | 引擎改动 | 小（~10 行） |
| 4 | 自噬循环自查（decode restore churn） | 实测 | 低 |
| 5 | 降 tb（**前置 = 动作 2 完成后**） | 配置 | 零 |

---

## 十一、施工单 · 本项目源码精确核对版（供龙猫施工单填充，2026-10-10）

> 用途：龙猫报告第六部分（W1–W5 施工单草案）的【待核对】处，本环境用**本地源码逐字核对**补全。
> 口径：每条给"**改前**（本项目逐字原文）+ **改后**（照 tancau 实际修复模式）+ 验收判据"。**"改前"全部逐字取自 `engine-main`**（`git show`），非推断。

### 11.1 W1 · 保险丝判定（`==` → `>=`）

**改前**（`src/models/qwen3_5/frontend/output_session.cpp:580-584`，逐字）：

```cpp
    if (impl_->preview_semantic.in_reasoning && impl_->preview_semantic.budget &&
        impl_->preview_semantic.model_thinking_tokens == *impl_->preview_semantic.budget) {
        impl_->preview_semantic.control_pending = true;
        return complete(count, FinishReason::None, runtime::ContinuationAction::ApplyTargetControl);
    }
```

**改后**（照 tancau `24c8ea5` 实际 diff）：`==` → `>=`（**改动量 1 字符**）。
tancau 修复前后结构与本项目**逐字同构**（已比对）。

### 11.2 W2 · 超预算 throw → OutputLimit（**注意：不是"类型化"**）

**改前**（`output_session.cpp:523-526`，逐字）：

```cpp
            if (impl_->preview_semantic.budget &&
                impl_->preview_semantic.model_thinking_tokens > *impl_->preview_semantic.budget) {
                throw std::logic_error("model output exceeded the licensed thinking budget");
            }
```

**改后**（照 tancau `24c8ea5` 实际方案）——**不是"类型化异常"，是"消除 throw"**：
- 打诊断日志（`[ninfer] thinking budget exceeded: budget=%u produced=%u`）；
- **以 OutputLimit 结束本回合**，保留已产出（tancau 逐字："A budget is a limit: reaching it ends THIS turn"）。

> ⚠️ **更正**：龙猫施工单 §6.4 写"改为类型化异常（使事务层能按类型 catch）"——**tancau 没走这条路**；他的实践是"**该路径根本不该抛错**"（预算 = limit，不是错误）。取舍：类型化 = 保留异常语义但要求事务层配合（改动面更大）；消除 = 语义正确且改动最小（tancau 已验证）。**建议照 tancau**。

### 11.3 W3 · 交接被拒 throw → OutputLimit

**改前**（`output_session.cpp:652-657`，逐字）：

```cpp
    if (impl_->preview_semantic.in_reasoning) {
        throw std::logic_error("canonical thinking control did not close the thinking phase");
    }
    if (impl_->split_reasoning && impl_->preview_state.in_reasoning) {
        throw std::logic_error("canonical thinking control did not close the reasoning channel");
    }
```

**改后**（照 tancau `15abab8`，逐字模式）：两处均改为——打诊断（`[ninfer] thinking control refused: …`）+ `control_pending = false; applied = true; terminalize(...)` + `finish_reason = OutputLimit`（保留已产出）。
tancau 实测触发频率：**198 请求中 2 次**（每次都终结对话——修复前）。

### 11.4 W4 · progress 保活（3 处改动）

**改动 1**（`src/serve/openai_chat_http.cpp:53-54`，逐字）：

```cpp
            .prompt_progress = request.stream && request.return_progress,
```

→ `.prompt_progress = request.stream,`（照 `202f098`）

**改动 2**（`src/serve/openai_chat_http.cpp:117`，逐字）：

```cpp
        const bool return_progress   = request.return_progress;
```

→ `const bool return_progress   = true;`（照 `202f098`："return_progress gates the wire format only"）

**改动 3**（`src/serve/openai_chat_response.cpp:363 与 :386`，逐字，**两处相同**）：

```cpp
    payload["choices"]        = Json::array({stream_choice(Json::object())});
```

→ `payload["choices"]        = Json::array({stream_choice(Json{{"reasoning_content", "\n"}})});`（照 `7f52a22`）

**为什么改动 3 必需**：pi-ai 只对**非空 reasoning 字段**产生 `thinking_delta` 事件（**空 delta 不产生事件 → watchdog 不被重置 → 300s 照掐**）。换行对答案与工具解析不可见，约 1 token。
**本环境核对**：本项目两处 progress 构造**均为空 delta**（L363/L386 逐字核对）→ 改动 3 必需。

### 11.5 W5 · 自噬循环（本项目机制细节，供实测设计）

- 本项目 `ensure_sequence_kv_mapped`（`context.cpp:2389+`）= **五拍体**：① `ensure_sequence_kv_lease`（lease 机制，本项目独有）② 打分排 preferred ③ 降级（preferred 最后放弃）④ **restore preferred 回 device（H2D）** ⑤ 安装掩码。
- tancau 修的是**第 ④ 拍在 decode 每轮重复**；本项目**第 ④ 拍同样存在于 decode 三个调用点**（`decode.cpp:479/677/931`，均未传"跳过"参数）。
- **但**：本项目有 preferred 保护 + 评分 hysteresis（逐字："Scoring runs only when the mapped page count changed"）——**churn 程度待实测**。
- 实测判据（与龙猫 §6.6 一致）：decode 每轮 restore 计数 / 时间分布（是否有固定开销随轮次增长）。
- **若无 churn → 不动**；若有 → 参照 `9cd3993` 模式（加 `restore_preferred` 参数，decode 三处传 false；**注意本项目函数签名为三参数**（`program_impl.h:1602`），加参数需同步声明与**全部 9 个调用点**）。

### 11.6 参照提交清单（本环境已全部读取，可提供逐字 diff）

| 提交 | 内容 | 状态 |
|---|---|---|
| `24c8ea5` | W1（`==`→`>=`）+ W2（超预算 throw→OutputLimit）+ 另两条 family 修复 | ✅ 已读全文 |
| `15abab8` | W3（交接拒绝 throw→OutputLimit） | ✅ 已读全文 |
| `202f098` | W4 改动 1/2（progress 去门控） | ✅ 已读全文 |
| `7f52a22` | W4 改动 3（delta 带 reasoning 换行） | ✅ 已读全文 |
| `9cd3993` / `adf3ed4` | W5（`restore_preferred`） | ✅ 已读全文 |

---

*本稿为调研记录（非施工文档）；源码引用基于 clone 于 `refs/tancau-ninfer-kvmem-ring/` 与 `engine-main`（Bonsai clone）的仓库逐字读取（提交 `adf3ed4`/`9cd3993`/`15abab8`/`24c8ea5`/`202f098`/`7f52a22` 等），命令均为 `git log/show/grep`。*
