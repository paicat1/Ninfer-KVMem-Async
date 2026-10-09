# 调研报告 · 让 Coder390 在 NInfer + KVMem 上跑满三种投机（目标实现路径）

> **署名**：TeleAgent（星辰超级智能体）
> **日期**：2026-10-09
> **对象**：本线 `ninfer-kvmem`（`J:\ninfer-kvmem`）
> **用途**：本项目"目标如何实现"的技术路线调研；**供与 CodeBuddy 交叉审核**（对侧将独立出一份，交叉纠错）。
> **审计基准**：
> - 代码基线：`J:\ninfer-kvmem @ 99c7233`
> - 引擎源码：`official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src`
> - 模型：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`
> - 参照契约：`refs\01-沈三殊-发放包\新\急速档\src-tree\ninfer-4090w-ternary\docs\maintainer\qwen3.8-27b-{artifact,dflash2}.md`
> **声明**：本文所有"事实"均带证据（`[EVIDENCE]` 或命令输出摘要）；未能证实者明确标注【待证】/【待补】。不同结论的交叉验证留给对侧。

---

## 0. 一句话结论

**本项目的目标（Coder390 + NInfer 核心解码 + KVMem + MTP/DFlash2/ngram 三投机）在技术上可达，但要拆成三件独立的事**：

1. **MTP**：卡点是"模型 MTP 头用了引擎不支持的 `gguf_q4_0`"。**两条可行路**——**(A) 引擎补 Q4_0**（内核已在 vendored ggml 里现成，主要是接线 + 重编）；**(B) 数据侧把 5 个 q4_0 张量"等长"重写为 `gguf_q4_k`**（不改偏移、不改长度、不重编，外科手术式探针）。**推荐先做 B 探针拿读数，再决定是否上 A 做成通用能力。**
2. **DFlash2**：本模型**包内没有 dflash2 组件**，且 DFlash2 是**独立训练的草稿模型**（`z-lab/Qwen3.8-27B-DFlash2`），不是"打开开关"就有。**必须先拿到/转换一份与 Coder390 几何兼容的 DFlash2 草稿并注入**——本机引擎自带转换器里有 dflash2 配方与"逐字节嫁接"先例，路径存在，但**是三项里最重、最不确定的一项**。
3. **ngram**：引擎已内置 ngram（`--ngram-draft-tokens` 依赖 `--spec`，`--lookup-ngram` 独立）；**只要 MTP 或 DFlash2 任一条通，ngram 就可落地**；其增量是"修剪式"（参考实测 +3%~13%），**不是翻倍开关**。

**并附"方案 0"**：什么都不改——裸解码已通（~52 tok/s），先只做集成（KVMem/启动器/复现材料），不碰投机。这是必须摆上桌的第一选项（见 §7）。

---

## 1. 目标与口径

**目标（用户原话口径）**：把新模型 `Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer` 搬进 **NInfer + KVMem** 架构跑起来，并把前序线（`J:\Bonsai-Official`）**全部能力**尽量适配到它身上：

> **NInfer 核心解码（最快）＋ KVMem 长上下文（KV 卸主机内存、腾显存）＋ 三种投机解码（MTP / DFlash2 / ngram）**

**纪律**：三条投机"**试到确认做不到为止**"，每条都要有**原文输出 + 读数 + 证据**。

**记法约定**：形状用 `[N,K]=[输出行,输入列]`；`[EVIDENCE] 文件:行:原文`。

---

## 2. 已取证事实（骨架）

### 2.1 模型容器（直读本机文件，非文档推断）

用脚本直读 `.ninfer` 头 + 目录 JSON（magic 8B + u64 长度@8 + artifact id 16B@16 + JSON@32；payload 对齐 4096）：

| 项 | 值 |
|---|---|
| magic | `NINFER\0\3`（v3） |
| artifact_id | `f2e0f91359304bd9a7f34234f11cb742` |
| manifest（目录 JSON） | 249,824 B |
| 文件 | **单文件**；`payload_bytes=13,272,548,864`；**文件总长 13,272,798,720 B（12.36 GiB）** |
| 对象 | **800 张量 + 4 资源 = 804** |
| 组件 | **只有 `text` 与 `mtp`**（无 vision / dflash / dflash2） |
| metadata.name | `qwen3.8-27b-coder390-Q2LynnStyle-Mtp` |
| provenance | converter=`ninfer-v3`；recipe=`qwen3_8_27b_gguf`；source.gguf=`/opt/coder390/Q2LynnStyle/…-MTP.gguf` |
| text 配置 | `Qwen3_5ForCausalLM`，hidden 5120 / 64 层 / vocab 248320 / max_pos 262144 |
| mtp 配置 | `Qwen3_5MTP`，target=text |

**格式分布（800 张量）**：`bf16 360｜fp32 96｜int32 1｜gguf_q4_k 67｜gguf_q5_k 2｜gguf_q2_k 2｜gguf_iq3_s 144｜gguf_iq3_xxs 26｜gguf_iq4_xs 76｜gguf_iq2_s 21` **`+ gguf_q4_0 5`**。

> **订正（T-EVIDENCE）**：交接文档 §4.1 记文件大小 `12,372,798,720 B`，**实际为 `13,272,798,720 B`**（13 被误写为 12；"≈12.36 GiB"的换算本身正确）。
> **【待补】** 交接文档给的 SHA256 `CDD82B69…6921` 本次未复算，标记待补。

**5 个 `gguf_q4_0` 对象（关键）**——由 bindings 反查，**全部且仅属于 MTP**：

| 对象 id | 形状 | offset | bytes | 归属（binding） |
|---|---|---:|---:|---|
| `weight/000079` | `[14336,5120]` | 4,220,248,576 | 41,287,680 | `mtp/layers/0/attention/{query,key,gate,value}`（一个父张量切 4 段） |
| `weight/000080` | `[34816,5120]` | 4,261,536,256 | 100,270,080 | `mtp/layers/0/mlp/{gate,up}`（一个父张量切 2 段） |
| `weight/000789` | `[5120,10240]` | 13,175,151,104 | 29,491,200 | `mtp/input_projection` |
| `weight/000796` | `[5120,6144]` | 13,204,684,288 | 17,694,720 | `mtp/layers/0/attention/output` |
| `weight/000798` | `[5120,17408]` | 13,222,389,248 | 50,135,040 | `mtp/layers/0/mlp/down` |

> 注：`weight/000079/000080` 物理位置在中段（4.2 GB）——转换器把 MTP 的 qkv/gate_up 与 text 主干交错落盘，但**逻辑归属仍是 MTP**（bindings 全部 `mtp/...`）。**text 主干零 q4_0**这句因此成立。

### 2.2 引擎格式与内核

- **格式白名单**（`parse_format` 的唯一来源）**无 q4_0**：
  `[EVIDENCE] src/artifact/formats.cpp:22: std::pair{QType::GGUF_Q8_0, std::string_view{"gguf_q8_0"}},`（同表含 q2_k/q3_k/q4_k/q5_k/q6_k/iq*，**无 gguf_q4_0**）
  `[EVIDENCE] src/artifact/formats.cpp:59: throw ArtifactError("unknown tensor format: " + std::string(name));`（即报错原文来源）
- **GGUF 桥枚举无 Q4_0**：
  `[EVIDENCE] src/ops/linear/gguf/ggml_bridge.h:16: enum class GgmlType : int {`（成员 Q8_0=8…IQ1_M=29，**无 Q4_0=2**）
- **但 vendored ggml 内核已自带 Q4_0**（决定路 A 工作量）：
  `[EVIDENCE] third_party/ggml-quants/include/ggml.h:392: GGML_TYPE_Q4_0    = 2,`
  `[EVIDENCE] third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:46: static __device__ … void dequantize_q4_0(const void * vx, …)`
  `[EVIDENCE] third_party/ggml-quants/src/ggml-cuda/mmq-config-ampere.cuh:36: CASE(GGML_TYPE_Q4_0, 256, 1, 128,   8, …)`（ampere/blackwell/cdna/gcn 均有配置）
- **引擎源码全树 `q4_0` 命中数 = 0**（`Select-String` 计数 0）⇒ 引擎侧从未支持过 Q4_0。

### 2.3 组件与投机门控

- 组件必需 `text`：`[EVIDENCE] src/artifact/schema.cpp:251: void parse_components(…) { if (!values.is_object() || !values.contains("text")) {`；缺组件报错源在 `schema.cpp:91`。
- **mtp / dflash2 仅在选中对应 `--spec` 时才要求**：
  `[EVIDENCE] src/models/qwen3_5/config.cpp:321: out.mtp  = options.speculative == SpeculativeBackend::Mtp;`
  `[EVIDENCE] src/models/qwen3_5/config.cpp:324: if (out.mtp) { const auto& config = companion(directory, "mtp").config;`
  `[EVIDENCE] src/models/qwen3_5/config.cpp:333: if (options.speculative == SpeculativeBackend::DFlash ||`（335 行取 `companion(directory, options.speculative_component())`）
- **MTP 绑定按"名字 + 形状"，与格式无关**：
  `[EVIDENCE] src/models/qwen3_5/load/mtp.cpp:8: out.input_projection = b.parameter("mtp/input_projection", {h, 2ULL * h}, {"mtp/stem_input"});`
- **DFlash2 绑定强依赖组件配置中的卷积/选择器几何**：
  `[EVIDENCE] src/models/qwen3_5/load/dflash2.cpp:7: const auto& extra = config.dflash2.value();`（随后按 `conv_kernel_size/conv_group_size/selector_rank/vocab_size` 取张量）⇒ **不能从别的模型随手拿一份 dflash2 灌注**。
- **CLI 选项**：
  `[EVIDENCE] src/serve/serve_options.cpp:260: --spec mtp|dflash|dflash2     speculative decoding backend`
  `[EVIDENCE] src/serve/serve_options.cpp:270: --ngram-draft-tokens N        copy up to N tokens … verified alongside --spec;`
  `[EVIDENCE] src/serve/serve_options.cpp:283: --lookup-ngram N              context-lookup drafting alongside --spec:`

### 2.4 容器可重写性

- 读取器**无内容哈希校验**，只校验 magic / JSON 长度 / artifact id / payload 长度：
  `[EVIDENCE] src/artifact/reader.cpp:50: if (expected != file->bytes()) {`（仅长度；无 hash / 无 checksum）
  `[EVIDENCE] src/artifact/reader.cpp:36: const auto json_bytes = read_u64_le(header.data() + 8);`（长度上限检查）
  ⇒ **改 payload 内容 + 改 JSON 里的格式串是安全的**（不会因哈希失配被拒）。
- **重打包有先例工具**：`official-repo\infer-fusion-kvmem\tools\strip_components.py`（抬头："repack a NInfer v3 artifact with some components removed"，字节流式、不覆盖源）。

### 2.5 转换器（本机引擎自带）

- `[EVIDENCE] src-tree/fusion-engine-src/tools/convert/gguf_blocks.py:475: RECIPES = {"qwen3_8_27b_gguf": qwen3_8_27b_gguf}`
- `[EVIDENCE] …/gguf_blocks.py:434: encoded, direct = text_sources(gguf, mtp=mtp)`
- `[EVIDENCE] …/gguf_blocks.py:439: recipe.assign(name, format=format, method=import_encoded, source=source, activation_policy="AllowA8")` ⇒ **artifact 的块格式 = 源 GGUF 的块格式，逐字导入**（这就是 MTP 落成 q4_0 的直接原因：源 GGUF 的 MTP 头是 Q4_0）。
- CLI 支持 `--source mtp|dflash|dflash2|quantized` 与 `--components text,vision,mtp,dflash,dflash2`（`__main__.py:131/136`）。
- **dflash2 "逐字节嫁接"先例**：
  `[EVIDENCE] …/quasar_nvfp4.py:115: def _collect_dflash2(official: Artifact) -> dict:`（"Collect the dflash2 objects, bindings, uses and component for a byte-copy graft."）
  `[EVIDENCE] …/quasar_nvfp4.py:170: def _add_dflash2_head_uses(recipe, params) -> None:`（补 `text/output_head@dflash2/final_hidden`，否则 planning 报 missing Use）

### 2.6 参照 artifact 契约（Qwen3.8-27B）

- DFlash2 是**独立来源**、作为 **66 对象后缀**注入：
  `[EVIDENCE] refs\…\qwen3.8-27b-artifact.md:536: The DFlash2 source is z-lab/Qwen3.8-27B-DFlash2 revision 50307d4c…`
  `[EVIDENCE] …:368: The DFlash2 suffix starts after all 1118 base tensors.`
- DFlash2 几何（与 Coder390 **几何一致**）：`L_d=5 / H=5120 / target 特征层 [5,19,33,47,61] / mask_token_id=248070 / sliding=2048 / conv taps=2 group=16 / selector rank=256 top-16 / RoPE theta=1e7`。
  `[EVIDENCE] …qwen3.8-27b-dflash2.md:46: | target feature layers |  | [5,19,33,47,61] |`
- 参照 artifact 的 **MTP 用 `W8G32_F16S`**（引擎已支持），本线用 `gguf_q4_0`（不支持）：
  `[EVIDENCE] …qwen3.8-27b-artifact.md:120: | MTP matrices | MTP | W8G32_F16S | row-split-k128-v1 | encode official BF16 source |`

### 2.7 ngram 现状（引用既有审计）

`docs\BONSAI_ngram_audit_report.md`（源码级审计）结论：ngram 是引擎侧特征、与 MTP/DFlash 互补（命中时优先）、**非独立翻倍**（参考实测 MTP+ngram 相对 MTP-only **+3%~13%**）。

---

## 3. 卡点定性（一句话）

**"模型能被引擎认识"缺少两样东西**：
1. MTP 头声明的**块格式 `gguf_q4_0` 不在引擎白名单**里（§2.2）→ 加载即抛 `unknown tensor format`。
2. **DFlash2 组件根本不在包里**（§2.1），而它**必须**由一份专用草稿模型转换而来（§2.3、§2.6）。

KVMem 与 NInfer 解码路径**不构成卡点**（裸解码已通，KVMem 是引擎级、与模型权重格式无关）。

---

## 4. MTP：三条路径

> 前置已确认：MTP 绑定按名/形状取张量（§2.3），**格式换掉不影响绑定**；只要换成"引擎支持的块格式"即可。

### 4.A 引擎补 Q4_0（重编）

**做什么**：给引擎加 `Q4_0` 支持——`QType` 枚举 + `kFormats` 增 `gguf_q4_0` + `GgmlType::Q4_0=2` + `block_shape(Q4_0)`（32 元素/18 字节）+ 在 gguf 桥的分派里接上 Q4_0 的 `dequantize_rows`/`vector_product`/`matrix_product`（内核**已在 vendored ggml 现成**，§2.2）。
**成本**：C++/CUDA 接线改动（量级：数处小改）+ **一次 clean 重编**（自编链已有，`build\`；红线：一架构一空目录，禁用增量构建）。
**收益**：**一劳永逸**——本模型按原样加载，且引擎今后能吃任何 Q4_0 的 GGUF 系 `.ninfer`；符合"NInfer 引擎最强"的产品方向。
**风险**：重编耗时；Q4_0 路径在本机 sm_120a 上**未经实测**（需自测）；需同步给转换器补 `block_format` 映射，否则重转仍产出 q4_0（可接受，因为引擎已能读）。

### 4.B 数据侧"等长重写"：q4_0 → q4_k（不重编，探针）

**关键算术事实（本报告核心发现）**：

| 块格式 | 块 | 字节 | 字节/元素 |
|---|---|---|---|
| Q4_0 | 32 元素 | 2(d)+16 = **18** | **0.5625** |
| Q4_K | 256 元素 | 144 | **0.5625** |

5 个 MTP 对象的元素数（5120 / 6144 / 10240 / 14336 / 17408 × 对应维）**全部被 256 整除**，且二者字节/元素相同 ⇒ **同样元素数下 q4_k 与 q4_0 的字节数逐字节相等**（已按 §2.1 表逐对象核验：41,287,680 / 100,270,080 / 29,491,200 / 17,694,720 / 50,135,040 均吻合）。

**因此可以做到**：
1. 对这 5 段 payload **原地重写**（读 q4_0 → 反量化 fp32 → 按标准 `quantize_row_q4_K` 重编码 → 写回**同样长度**的字节）；
2. 把目录 JSON 里 5 处 `"gguf_q4_0"` 就地替换为 `"gguf_q4_k"`（**长度相同 9 字节** ⇒ manifest 长度不变 ⇒ **所有 offset/长度/文件切分全部不变**）。

**成本**：一个 Python 外科脚本（读头 → 定位 5 段 → 重编码回写 → 就地改 5 个格式串），**不需重编、不需上游 Python 写入器**。
**收益**：**最快拿到 MTP 读数**（验证 MTP 投机在 Coder390 上的接受率/吞吐）。
**风险**：① q4_0→q4_k 属"4bit→4bit 重量化"，有微小数值损失（对草稿头可接受）；② 必须**先备份原模型**（T-BACKUP / T-PROTECT-ASSET：`models\` 是 `.gitignore` 排除的 >1G 资产，改动前必须留副本或确认可从源重下）；③ 该产物是"改写版"，与原厂件不再逐字节一致（需在构建史登记 provenance）。

### 4.C 请上游/重转（最省我方工程量，最不可控）

- 请模型作者（Merkyor）用**引擎支持的 MTP 格式**（如参照件的 `W8G32_F16S`，或 `gguf_q4_k/q8_0`）重导；或
- 用本机转换器**重跑** `qwen3_8_27b_gguf`，但**必须拿到源 GGUF**（本机只有 `.ninfer`，源 GGUF 在 `/opt/coder390/...`），且需指定一份**已支持格式的 MTP 源**（`--source mtp=`）。

**风险**：依赖外部/依赖大文件下载；不可控。

---

## 5. DFlash2：唯一硬门是"草稿件从哪来"

**事实**：本模型**没有** dflash2 组件（§2.1）；DFlash2 是**独立训练**的草稿模型（`z-lab/Qwen3.8-27B-DFlash2`，§2.6），绑定强依赖组件配置里的卷积/选择器几何（§2.3）⇒ **不是开关，是"另装一个件"**。

**可行路径**（按优先级）：

### 5.A 转换注入（推荐先评估）
用本机转换器 `--recipe qwen3_8_27b_gguf --source dflash2=<z-lab DFlash2> --components text,mtp,dflash2`（或对已有 `.ninfer` 做"嫁接"）。本机转换器**同时具备** dflash2 配方与逐字节嫁接先例（§2.5）。
**前提**：① 能拿到 `z-lab/Qwen3.8-27B-DFlash2`（BF16 safetensors，81 张量）；② 转换器需要 CUDA 设备与 base 源；③ **需确认 Coder390 与 Qwen3.8-27B 的几何/层号完全一致**（本模型 hidden/layer/vocab 与参照一致，**强迹象但不等于证明**——DFlash2 条件是 target 隐藏态，微调模型上草稿质量**未经验证**）。

### 5.B 从参照 artifact 嫁接
若手上有带 dflash2 的参照 v3 artifact，可照 `quasar_nvfp4.py` 的 `_collect_dflash2` 逐字节嫁接（含补 Use）。**成本**=下载/持有参照 artifact（~12 GB 级）。

### 5.C 放弃 DFlash2（把它当"做不到"结案）
理由：DFlash2 草稿是为 **Qwen3.8-27B 原版**训练的；Coder390 是衍生微调，草稿质量**先天不确定**；而 MTP 已足够强（参照实测 MTP≈2.3–2.5×）。若 MTP 跑通，DFlash2 的边际价值需用**同口径 A/B** 证明后才值得投入。

---

## 6. ngram / KVMem / 集成

- **ngram**：引擎内置（`src/models/qwen3_5/ngram.cpp` + `lookup_draft.h` 等）。`--ngram-draft-tokens` **依赖 `--spec`**（§2.3）⇒ **MTP 通即自然可用**；`--lookup-ngram` 独立。**预期收益**：MTP-only 之上 **+3%~13%**，不是翻倍（引 §2.7）。**务必同口径 A/B 复测**，勿把"翻倍"归因给 ngram。
- **KVMem**：引擎级、与权重格式无关；本模型裸解码已通，KVMem 应可直接生效。**待做**：在真实请求下确认 `kvmem_score: SELECT`（检索判活）与显存卸载行为。
- **集成（启动器/日志/复现材料）**：`start-*.bat` / `ninfer_launcher.py` 仍是 Bonsai 名与旧路径，需适配 Coder390；属工程收口，非技术卡点。

---

## 7. 方案对比与推荐（**先摆方案 0**）

### 方案 0（什么都不做）
保持裸解码（~52 tok/s）+ 只做集成收口，**不做任何投机适配**。
- 改动量：0 引擎改动、0 重编、0 模型改写。
- 收益：**今天就能用**（KVMem 长上下文 + 最快核心解码已在）。
- 代价：无 MTP/ngram/DFlash2 加速（但裸解码本身已是 NInfer 的强项）。
- **适用**：若近期需求是"稳定可用"，方案 0 是合理的默认。

### 方案对比

| 方案 | 覆盖目标 | 改动量 | 重编 | 风险 | 建议 |
|---|---|---|---|---|---|
| 0 只集成 | 无投机 | 极小 | 否 | 极低 | 立即可行 |
| **B：MTP 等长重写 q4_k** | **MTP** | 小（1 脚本） | **否** | 低~中（数值/需备份） | **先做（探针）** |
| A：引擎补 Q4_0 | MTP（通用） | 中 | **是** | 中（未实测路径） | B 通后评估 |
| C：重转/上游重导 | MTP | 小（我方） | 否 | 中（依赖外部/大件） | 备选 |
| 5.A/B：注入 DFlash2 | DFlash2 | 大 | 否 | **高**（件来源+质量） | 最后做 |
| ngram | ngram | 小（随 spec） | 否 | 低 | MTP 通后即启 |

### 推荐顺序（务实，逐条取证）
1. **先方案 B**：对 5 个 MTP q4_0 做等长重写为 q4_k（**先备份原模型**），起 `--spec mtp`，**拿原文日志 + 接受率 + 吞吐读数**。
2. **B 若不稳/不满意 → 方案 A**：引擎补 Q4_0（含转换器 `block_format` 映射），重编后按原样加载，做成通用能力。
3. **MTP 稳后 → 启 ngram**（`--ngram-draft-tokens`），**同口径 A/B** 量化 ngram 真实增益。
4. **最后评估 DFlash2**：先算"是否值得"——需要 `z-lab DFlash2` + 转换 + 几何证明 + 质量实测；若 MTP+ngram 已满足需求，可**按"做不到/不划算"结案并留证据**。

---

## 8. 风险与前置验证（做前必查）

1. **资产保护（T-PROTECT-ASSET）**：`models\` 是 `.gitignore` 排除的 >1G 唯一副本——**任何改写前必须先备份到 `_safety_backups\` 或确认可重下**；本报告与脚本都不得在 `models\` 同树做删除/移动。
2. **数值正确性**：q4_0→q4_k 重编码必须与引擎解码端**同一 block_q4_K 布局**；落地前用**独立 oracle**（解回 fp32 比对）验证逐块误差。
3. **MTP 门槛**：MTP 还需 `mtp` 组件 `architectures == "Qwen3_5MTP"`（本模型满足，§2.1）+ 目标 text 几何匹配（满足）。
4. **DFlash2 几何/层号一致性**：需**证明** Coder390 与 Qwen3.8-27B 的层类型序列（16 full + 48 GDN）与 RoPE/norm 语义一致，才谈得上嫁接 DFlash2。
5. **同口径复测纪律**：任何加速结论必须**同语料、同参数、关思考**、以引擎日志 `req#N done` 行为权威读数；合成材料接受率**不可作决策依据**。
6. **不接受"看起来正常"**：KVMem 必须看到 `kvmem_score: SELECT`；MTP 必须看到草稿/接受计数；否则视为未生效。

---

## 9. 待决事项（请用户裁决）

1. **MTP 走 B（快）还是 A（通用）**？（建议：先 B 探针，A 作为后续）
2. **是否允许改写 `models\` 里的 `.ninfer`**？（方案 B 需要；需你确认备份策略）
3. **DFlash2 优先级**：现在就投入（需下载 z-lab DFlash2 + 转换），还是 MTP/ngram 之后再评估？
4. **是否允许重编引擎**（方案 A 前提；自编链见 `build\`，红线=一架构一空目录 clean build）。

---

## 附录 A · 证据索引

| # | 结论 | 证据 |
|---|---|---|
| E1 | 格式白名单无 q4_0 | `src/artifact/formats.cpp:22,26,59` |
| E2 | ggml 桥枚举无 Q4_0 | `src/ops/linear/gguf/ggml_bridge.h:16-32` |
| E3 | vendored ggml 已有 Q4_0 内核 | `third_party/ggml-quants/include/ggml.h:392`；`…/dequantize.cuh:46`；`…/mmq-config-ampere.cuh:36` |
| E4 | 引擎源码零 q4_0 | Select-String 计数 0 |
| E5 | 容器无内容哈希 | `src/artifact/reader.cpp:36,50` |
| E6 | 组件门控（mtp/dflash2 随 --spec） | `src/models/qwen3_5/config.cpp:321,324,333` |
| E7 | MTP 按名/形状绑定 | `src/models/qwen3_5/load/mtp.cpp:8` |
| E8 | DFlash2 绑定依赖组件几何 | `src/models/qwen3_5/load/dflash2.cpp:7` |
| E9 | CLI：--spec / --ngram-draft-tokens / --lookup-ngram | `src/serve/serve_options.cpp:260,270,283` |
| E10 | 本模型目录解析（804 对象 / 5×q4_0 / 组件 text+mtp） | `peek_ninfer*.py` 输出（本报告 §2.1） |
| E11 | gguf 配方逐字导入源块格式 | `tools/convert/gguf_blocks.py:416,434,439,475` |
| E12 | dflash2 逐字节嫁接先例 | `tools/convert/quasar_nvfp4.py:115,170` |
| E13 | DFlash2 独立来源 + 66 对象后缀 | `refs\…\qwen3.8-27b-artifact.md:368,536` |
| E14 | DFlash2 几何 | `refs\…\qwen3.8-27b-dflash2.md:46-56` |
| E15 | 重打包先例工具 | `official-repo\infer-fusion-kvmem\tools\strip_components.py` |
| E16 | ngram 增益量级与共生机理 | `docs\BONSAI_ngram_audit_report.md` §3/§5 |

## 附录 B · 术语

- **`.ninfer`**：NInfer 的 v3 容器（magic `NINFER\0\3`），目录 JSON + 对齐 payload。
- **组件（component）**：`text`（必须有）/`mtp`/`vision`/`dflash`/`dflash2`/`proposal`。
- **块格式**：`gguf_*`（q2_k…q8_0、iq*）为 GGUF 系块量化；`bf16/fp32/int32` 为直接张量。
- **等长重写**：不改 offset/长度、只改 payload 字节与同长格式串的原地改写。

---

> **本报告为 TeleAgent 独立产出，请与 CodeBuddy 的版本交叉审核。**
> 交叉审核纪律：不做应声虫——**默认先找反例**；重点互查：① q4_0/q4_k 字节等价性推导；② 等长重写是否遗漏对齐/切分；③ DFlash2 几何一致性的证明链；④ 是否有第三条更优路径被漏掉。
