# BONSAI 仓库 ngram 投机解码审计 + 在 Qwen3.8-27B-Coder390 上加 ngram 的可行性报告

> 审计对象：`paicat1/Bonsai-27B-NInfer-kvmem`（`engine-main` 分支）
> 目标模型：`Merkyor/Qwen3.8-27B-Coder390-EfficientThink-...-GGUF-NInfer`（qwen35 架构，内嵌 MTP、支持 DFLASH，用户称"无 ngram"）
> 审计方式：GitHub MCP 直接读取仓库源码（非文档推断）
> 生成日期：2026-10-08

---

## 1. 结论速览（先给判断）

| 问题 | 结论 | 可信度 |
|---|---|---|
| ngram 能不能加到这个模型上？ | **能**。ngram 是引擎侧特征，不需要模型权重改动；"模型没有 ngram"不构成障碍。 | 源码证实 |
| ngram 能否与 MTP / DFLASH 共存？ | **能共存**。ngram 与 MTP/DFLASH 处在同一投机子系统的不同层，源码明确"优先用 ngram 命中覆盖草稿头"。 | 源码证实 |
| 加上 ngram 解码速度是否翻番？ | **需修正预期**：在本模型同族（Qwen3.8-27B）上，ngram 叠加 MTP 仅 **+3%~13%**（仓库自带 2026-09-19 实测）；你观察到的"翻番"几乎可确定是 **MTP 本身的贡献**（MTP≈2.3–2.5× vs 无投机，与目标模型文档的 2.5× 一致）。 | 源码实测 + 目标文档交叉印证 |
| ngram 最大价值在哪？ | 输出"重复输入"的场景（摘要/编辑/RAG 作答/复用名字与结构的代码），以及 MTP 草稿窗口受限（高 K）时。 | 源码注释 |

**一句话**：ngram 可加、可与 MTP/DFLASH 配合，但它是对 MTP 的"修剪式"增强（+几个百分点），不是独立的翻倍开关。把"翻番"归因给 ngram 是测量混淆，应隔离 MTP-only vs MTP+ngram 复测确认。

---

## 2. ngram 在 BONSAI 中的实现事实（源码取证）

### 2.1 两类 ngram 结构
- **引擎级存档** `src/models/qwen3_5/ngram.cpp`（sha `751bdbdca32ad13b4eccf21c58c6bb26f46575d4`）+ `ngram.h`（`8212b226...`）
  - `NgramArchive`：引擎拥有的 CPU 存储，按会话 key 建立 n-gram 索引（宽度 `{16,8,4}`），用 blocked-Bloom 过滤加速随机访问。
  - `NgramSnapshot::propose(history, maximum, minimum_match=12)`：要求历史尾部 **≥12 token 精确匹配**才提议续写，纯 CPU 哈希查找，**零设备开销**。
  - 来源分四种 `NgramSourceKind::{Reasoning, Text, Generated, Tool}`，淘汰时优先保留 Tool/代码（`weakest()` 比较 kind 优先级）。
  - 预算：`NgramArchiveLimits{session_bytes=128MB, total_bytes=512MB, sessions=32, sources=1024}`。
  - `[EVIDENCE] ngram.h: "class NgramArchive { ... begin(key, input, boundaries, parent, parent_generation) ... publish(request, output)"`
- **请求级提议器** `src/models/qwen3_5/program/ngram_proposer.h`（`57a75098...`）
  - `NgramProposer::propose_for_round(history, maximum, neural_drafts, min_match=12)` —— **关键参数 `neural_drafts` 就是 MTP/DFLASH 已产出的草稿数**，ngram 在其之上"补充"草稿。
  - `[EVIDENCE] ngram_proposer.h: "if (available < maximum + 2 && drafts <= neural_drafts) { return {}; }"`

### 2.2 接入投机管线
- `src/models/qwen3_5/program/speculative/` 目录并存：
  - `mtp.cpp`（`7e2d63cf...`，神经式草稿头）
  - `mtp_adaptive.h`、`mtp_alignment.h`
  - **`lookup_draft.h`（`0597f8df...`，ngram 式上下文查表草稿）**
  - `target_verification.cpp`（统一验证 drafted token）
- `[EVIDENCE] lookup_draft.h 头部注释: "A draft model guesses what comes next from weights; this guesses it from the text already in front of it, which costs no device work at all."`

---

## 3. ngram 与 MTP / DFLASH 能否共存 —— 已证实

### 3.1 三处源码证据
1. **`neural_drafts` 形参**（ngram_proposer.h）：ngram 提议器在构造时**已知**神经草稿数量，并只在能"补充/超越"时才提议（`drafts <= neural_drafts` 则退让）。说明两者被设计为**同一 draft round 的协作方**。
2. **`lookup_draft.h` 注释明确**（原文）：
   > "Those are the cases a draft head is weakest on, which is why the two are **complements rather than alternatives**."
   > "**lookup preferred over the head's proposal whenever it matches**"
   —— 即同一 round 内，ngram 命中时**优先采用 ngram 提议**，覆盖 MTP 草稿头的提议。这是共存的直接证实。
3. **同一 `speculative/` 子系统**内 `mtp.cpp` 与 `lookup_draft.h` 并列，由 `target_verification.cpp` 统一验证；二者产出合并进同一草稿窗口，一次 target 前向即验证完。

### 3.2 组合规则（基于源码与目标模型文档）
| 组合 | 是否可行 | 说明 |
|---|---|---|
| ngram 单独 | ✅ | 无神经投机时，ngram 独立提供草稿 |
| MTP + ngram | ✅ | **推荐组合**，ngram 补齐 MTP 弱项 |
| DFLASH + ngram | ✅ | 同理，ngram 叠加外挂草稿 |
| MTP + DFLASH | ❌ | 二者互斥（单一 `--spec` 选择，目标文档明说） |
| ngram + MTP + DFLASH | ❌ | 因 MTP/DFLASH 互斥 |

> 注意：互斥的是 **MTP 与 DFLASH**（都是"模型式"投机，单选），**ngram 是独立的"数据式"投机层，不与二者中任何一个冲突**。用户"ngram 可以和 MTP/DFLASH 配合"的判断**正确**。

---

## 4. 在目标模型上加 ngram 的可行性 & 实操

### 4.1 为什么"模型没有 ngram"不是障碍
ngram 不依赖任何模型权重或特殊头（不像 MTP 需要 blk.64 的 `nextn` 头、DFLASH 需要外挂草稿模型）。它纯粹**重放引擎已观测到的 token 历史 + 存档来源**。因此：
- 目标模型即使"无 ngram 头"，只要用**带 ngram 的引擎**加载，就能获得 ngram 投机。
- 这对 qwen35 架构模型天然适用（BONSAI 的 `qwen3_5` 前端 + `speculative/` 子系统已为该架构实现完整 ngram 链路）。

### 4.2 实操步骤
1. **用 BONSAI 的 NInfer 构建加载目标模型的 `.ninfer` 包**（非姊妹仓、非 stock ninfer-all）。理由：ngram 代码（`ngram.cpp` / `ngram_proposer.h` / `lookup_draft.h` / `speculative/lookup_draft.h`）只存在于 BONSAI 仓库——你提到的"姊妹仓投机没有 ngram"与此一致。
2. **启用 ngram 配置**：前端侧 `ngram_sources_enabled` / `ngram_archive_enabled`（在 `frontend.cpp` 中已存在开关），并为会话提供种子存档（session key + 输入来源）。
3. **冷启动即有收益**：`NgramArchive::begin` 用 prompt / 工具结果做种子来源；`ngram_sources.h` 会从工具输出里抽取"连续编号行"作为高质量来源（对 agent/代码场景极友好）。
4. **多轮回填收益复利**：请求完成时 `publish()` 把生成输出登记为新来源；子会话可经 `parent`/`parent_generation` 继承父存档，越跑命中越高。

### 4.3 前置验证项（前次审计遗留，仍待确认）
- BONSAI 的 NInfer 基底是否读 `gguf_blocks_v1`（目标 `.ninfer` 包格式）。若否，需格式转换或换基底。
- 目标模型视觉塔（`vision-bf16.safetensors`）是否需要在 ngram 场景一并启用（ngram 本身与视觉无关，但若用多模态则照常加载）。

---

## 5. 速度预期修正（诚实告知，防误导）

### 5.1 仓库自带实测（lookup_draft.h，2026-09-19，Qwen3.8-27B @ 单卡 3090，MTP + 优化草稿头，lookup 命中时优先）
```
n-gram    2      3      4      6      8     16     off
decode  135.6  148.9  143.5  145.2  148.7  148.5  144.9 tok/s
accept   0.87   1.00   0.96   0.97   1.00   1.00   0.964
```
- **n-gram=8 起每次命中都正确（accept=1.00）**，decode 较 off 仅 **+2.6%**（148.7 vs 144.9）。
- 注释原文关键句：
  > "**The gain is small because there was little to win.** The draft head already accepts 95-96% on this model, so a perfect drafter is worth +5.5% at K=3 and +13% at K=5 and no more."

### 5.2 为什么你看到"翻番"几乎确定是 MTP 而非 ngram
- 目标模型文档实测：NInfer+MTP 单请求 ≈ llama.cpp 无投机 **2.5×**（131.9 vs 53.4 tok/s），与"翻番/翻倍"量级吻合。
- 而 ngram 叠加 MTP 在该同族模型上仅 +3%~13%（见 5.1）。
- **归因建议（T0 诚实）**：你测到的"翻倍"= MTP 基线效应。要把 ngram 的真实贡献量化，请**隔离复测**：
  - A 组：`--spec mtp`（关 ngram）
  - B 组：`--spec mtp` + 开 ngram
  - 同负载、同 K，B/A 之比才是 ngram 真实增益（预期 1.03–1.13，非 2.0）。

### 5.3 ngram 真正能"大赢"的前提
- **负载高度重复**（代码复用名字/结构、RAG 把检索段落照抄作答、编辑/摘要重排输入）——lookup_draft.h 注释称这些正是"草稿头最弱、二者互补"的场景。
- **MTP 草稿窗口受限**（高 K）时：注释指出 MTP 停在 K=5 时 ngram 把 182.7→191.0 tok/s；窗口放到 15 后，长匹配可在单 round 内推更远。
- 对照：**弱草稿模型**下 lookup drafting 可"transformative"（注释原话），但本目标模型 MTP 已 95-96% 接受，故 ngram 只是"修剪"。

---

## 6. 风险与注意
1. **内存预算**：`NgramArchive` 默认 512MB 总量 / 128MB 单会话 / 32 会话 / 1024 来源；海量长生成会触发淘汰（优先保 Tool/代码来源）。一般负载可忽略。
2. **冷启动收益低**：首个无重复模式的请求 ngram 几乎不贡献；收益随会话/来源积累上升。
3. **不要误以为 ngram 替代 MTP**：二者是正交增强。关掉 MTP 只开 ngram，在自由生成文本上接近纯解码（ngram 注释："worthless on free-form prose"）。
4. **格式兼容仍是落地前提**：目标 `.ninfer` 包需 BONSAI 引擎能读 `gguf_blocks_v1`（见 4.3）。
5. **姊妹仓无 ngram**：确认 ngram 代码仅 BONSAI 有；若目标当前由姊妹仓/stock ninfer-all 加载，则根本没有 ngram 可"开"，必须先切到 BONSAI 构建。

---

## 7. 证据索引（文件 : sha）
- `src/models/qwen3_5/ngram.h` : `8212b226179ef6fd8dcdc1ada60d1622a38e7589`
- `src/models/qwen3_5/ngram.cpp` : `751bdbdca32ad13b4eccf21c58c6bb26f46575d4`
- `src/models/qwen3_5/frontend/ngram_sources.h` : `b5b2973b380f31e576c7f6d41faab82542819e62`
- `src/models/qwen3_5/program/ngram_proposer.h` : `57a75098dc3888e027612180ab25218b251e9c8f`
- `src/models/qwen3_5/program/speculative/lookup_draft.h` : `0597f8df49cebdc27ee43d82174f96016548b1e6`
- `src/models/qwen3_5/program/speculative/mtp.cpp` : `7e2d63cf1bbbde9ca482b82be1f8a046444160c8`
- `src/models/qwen3_5/frontend/output_session.cpp`(Design C) : `f9084d5f8ecc6ac2b99142bda34c58b3e2054e43`

## 8. 给用户的下一步建议
1. **切到 BONSAI 的 NInfer 构建**加载目标模型 `.ninfer` 包，确认 `gguf_blocks_v1` 可读（落地的唯一硬前提）。
2. 开启前端 ngram 开关 + 会话种子存档，跑一轮 agent/代码负载看实际命中。
3. **隔离复测** MTP-only vs MTP+ngram（同 K、同负载），用 B/A 之比确认 ngram 真实增益，修正"翻番"归因。
4. 若目标是"再压延迟"：优先调大 MTP 草稿窗口 K（让 ngram 长匹配在单 round 内推更远），这比单纯开 ngram 收益更大。
