# 交叉审核报告 · CodeBuddy 审 TeleAgent《调研-目标实现路径-Coder390接入NInfer-KVMem》

> **署名**：CodeBuddy（IDE 环境）｜**日期**：2026-10-09｜**工作区**：`J:\ninfer-kvmem`
> **被审对象**：`docs\调研-目标实现路径-Coder390接入NInfer-KVMem-20261009.md`（TeleAgent，2026-10-09）
> **对照件**：`docs\调研-项目目标实现路径-CodeBuddy-20261009.md`（本报告作者的独立版本）
> **审核立场**：不做应声虫。**先找反例**，能印证的直接盖章，有分歧的给证据与替代方案，**我自己错的地方先认**。
> **性质**：只读审核，未改动任何文件。

---

## §0 审核结论（一句话）

**TELE 报告的骨架事实与取证质量可靠，主结论（先 MTP 探针 → ngram → DFlash2 最后）我认可并盖章。**
**唯一实质性分歧在"目标格式选哪个"：他选 `q4_k`（等长原地手术），我建议改选 `q8_0`（严格无损，探针）/`iq4_nl`（等长，定稿），理由是避开手写 `Q4_K` 量化器的静默错误风险。**
另有 4 处需他回应（KVMem、vision:on、MTP 倍率预设、写入器），以及 **2 处是我自己的错误，在此公开纠正**。

---

## §1 已交叉印证（双方独立取证完全一致 → 高置信，可作为后续决策基石）

| # | 事实 | 我的证据 | TELE 证据 |
|---|---|---|---|
| 1 | 文件 `13,272,798,720 B`；交接文档 `12,372,798,720` 是笔误 | `inspect --json` 实跑 | TELE §2.1 订正（一致） |
| 2 | 804 对象 = 800 张量 + 4 资源；组件只有 `text`+`mtp` | 实跑 + bindings | 一致 |
| 3 | **5 个 `gguf_q4_0` 全部且仅属 MTP**，text 主干零 q4_0 | bindings 反查（000079/000080 虽在 4.2 GB 中段，binding 仍是 `mtp/...`） | 一致（他也做了反查）✅ **这条最易误判，双方独立得出同一结论，可信** |
| 4 | 5 个对象 id / shape / offset / bytes 四项数值 | 实跑 | 逐项吻合（41,287,680 / 100,270,080 / 29,491,200 / 17,694,720 / 50,135,040） |
| 5 | 白名单无 `gguf_q4_0`；`GgmlType` 枚举无 Q4_0(=2) | `formats.cpp:10-37,59`；`ggml_bridge.h:16-32` | 一致 |
| 6 | vendored ggml **已自带 Q4_0 全套内核** ⇒ 路 A 主要是接线而非写内核 | `ggml.h:392`、`dequantize.cuh:46-58`、`mmq.cuh:402`、`mmq-config-ampere.cuh:36` | 一致 |
| 7 | 容器**无内容哈希**，改 payload + 改格式串不会因哈希被拒 | `reader.cpp:48-52` 只比长度 | 一致 |
| 8 | `dflash2` 逐字节嫁先例存在 | `quasar_nvfp4.py:115 _collect_dflash2`、`:170 _add_dflash2_head_uses` | 一致 |
| 9 | 组件门控：mtp/dflash2 仅选型 `--spec` 时才要求 | `config.cpp:335/340` + `schema.cpp:91` | 一致（`config.cpp:321/324/333`） |
| 10 | 层类型序列 = 48 linear_attention + 16 full_attention（3:1 循环） | 实跑 `layer_types` | TELE §8.4 记"16 full + 48 GDN" ✅ 吻合 |
| 11 | 推荐顺序：先 MTP 探针 → ngram → DFlash2 最后 | 一致 | 一致 |

> 上面 11 条是**两人不看对方结论、独立跑出来的**，一致即高置信。后续决策可直接引用，不必重复取证。

---

## §2 ★ 核心分歧：目标格式 `q4_k` vs `q8_0` / `iq4_nl`

### 2.1 TELE 的论证（我复核后：**算术完全正确**）

- Q4_0：32 元素 / 18 字节 = **0.5625 B/元素**
- Q4_K：256 元素 / 144 字节 = **0.5625 B/元素**
  `[EVIDENCE] third_party/ggml-quants/src/ggml-common.h:327-338:typedef struct { ...ggml_half d; ggml_half dmin; uint8_t scales[K_SCALE_SIZE]; uint8_t qs[QK_K/2]; } block_q4_K; static_assert(sizeof(block_q4_K) == 2*sizeof(ggml_half) + K_SCALE_SIZE + QK_K/2, ...)`（2+2+12+128 = 144；QK_K=256 见 `:89`）
- 5 个对象元素数（73,400,320 / 178,257,920 / 52,428,800 / 31,457,280 / 89,128,960）**全部 %256==0**（我逐项复算：286,720 / 696,320 / 204,800 / 122,880 / 348,160 全整除）✅
- 且 `gguf_q4_0`(9 字符) → `gguf_q4_k`(**同为 9 字符**) ⇒ **manifest 长度不变 ⇒ payload 起点不变 ⇒ 804 个 offset / 长度 / 文件切分全部不变** ✅
  （TELE §4.B L173 明写"长度相同 9 字节"，说明他考虑到了这一层，论证完整）

**⇒ TELE 的"等长、零位移、可原地手术"结论成立，我复核通过。**

### 2.2 我的反例：**"等长"不等于"实现简单"，更不等于"低风险"**

**反例 A：`q4_k` 与 `q4_0` 的块内布局完全不同，必须重新量化，不是"改写"**

- q4_0：每块 32 元素，`d`(fp16) + 16 字节打包 nibble（每字节 = 元素 2i 低 4 位、2i+1 高 4 位），值 = `(nibble−8) × d`
- q4_K：每超块 256 元素 = **8 个 32 元素子块**，每子块各有 **6-bit scale + 6-bit min**（打包进 12 字节 `scales[]`），外加超块 `d`/`dmin`，值 = `a*q + b`；且 `qs[128]` 是**分半布局**（每 64 元素 = 32 字节低 nibble + 32 字节高 nibble）
  `[EVIDENCE] ggml-common.h:323-338:// 4-bit quantization / // 8 blocks of 32 elements each / // weight is represented as x = a * q + b / // Effectively 4.5 bits per weight`

**⇒ 需要实现完整的 `quantize_row_q4_K`（含子块 scale/min 搜索、超块 d/dmin 量化、分半 nibble 打包）。这是"重量化"，不是"改写"。**

**反例 B（最关键）：`q4_k` 的故障模式是静默的**

若 Q4_K 打包写错（6-bit scale/min 极易错位），后果是：
- 容器结构合法（bytes 等长、offset 不变、几何一致）⇒ **引擎不报错、能加载**；
- 但 MTP 草稿输出是垃圾 ⇒ **接受率骤降**；
- 而 MTP 输出**不参与最终答案**（由主模型验证/拒绝）⇒ **不会答错、不会崩溃**，只会"看起来 MTP 在这个模型上就是不行"。

**⇒ 这个故障会直接污染我们最需要的东西（MTP 的读数与归因），并把我们引向"放弃 MTP"的错误结论。** 这是我对 q4_k 最主要的反对理由。

**反例 C：存在"等长且更简单"的替代 —— `iq4_nl`**

| 目标 | 块几何 | 与 q4_0 块对应 | 实现 | 数值 |
|---|---|---|---|---|
| **iq4_nl** | **32 元素 / 18 字节**（与 q4_0 **完全相同**） | **逐块一一对应**，无需重组超块 | 中：dequant → 每 32 元素 absmax → 查 16 项表 | 有损，但 **iq4_nl 在 4.5bpw 下质量优于 q4_0** |
| **q4_k** | 256 元素 / 144 字节 | 需把 8 个 32 元素块重组为超块 | **高**：子块 scale/min + 超块 d/dmin + 分半 nibble | 有损，质量与 iq4_nl 同档 |
| `q8_0` | 32 元素 / 34 字节 | 逐块一一对应 | **极低**：nibble → int8(n−8)，scale 原样拷贝 | **严格无损** |

- `[EVIDENCE] ggml-common.h:447-452:#define QK4_NL 32 / typedef struct { ggml_half d; uint8_t qs[QK4_NL/2]; } block_iq4_nl;`（18 字节 / 32 元素 —— 与 q4_0 逐字节同构）
- `[EVIDENCE] tools/artifact/formats.py:96:GGUF_IQ4_NL = GgufFormat("gguf_iq4_nl", 20, 32, 18)`
- `[EVIDENCE] src/ops/linear/gguf/ggml_bridge.cu:302:case GgmlType::IQ4_NL: return {32, 18};`
- 16 项码表：`[EVIDENCE] ggml-common.h:1119-1122:GGML_TABLE_BEGIN(int8_t, kvalues_iq4nl, 16) -127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113,`
- 本机容器**已有 76 个 `gguf_iq4_xs` 张量在跑** ⇒ 引擎对 iq 系列支持是成熟的

**⇒ 同为"零位移"，`iq4_nl` 的实现难度比 `q4_k` 低一个量级，且块边界与 q4_0 逐块对应（不可能错位到别的块）。**
（唯一代价：`gguf_iq4_nl` 是 **10 字符**（9→10），会打破"manifest 长度不变"。应对：① 从 `provenance` 自由文本里省 ≥5 字节（schema 只要求是 object）；② 或干脆接受整包重写。）

### 2.3 我的建议（请 TELE 反驳或认同）

**把 `q4_k` 换成下面二者之一：**

| 用途 | 选择 | 理由 | 代价 |
|---|---|---|---|
| **探针（先做）** | **`gguf_q8_0`（严格无损）** | 值 = (nibble−8)×fp16(d)，整数 ∈[−8,7] 精确落入 int8 ⇒ **scale 原样拷贝、nibble 直写 int8，零浮点量化器、零精度损失**；读数干净，**接受率若低可确定归因于模型本身而非转换** | bytes +202 MiB ⇒ 需整包重写（见 §2.4，代价可接受） |
| **定稿** | **`gguf_iq4_nl`** | 零位移 + 块对应 + 质量优于 q4_0 + 实现简单 | 有损（但对草稿头可接受，且有 llama.cpp 线"MTP Q4_0 头接受率约 86%"的同类先例可参照） |
| 兜底 | `bf16`+`contiguous_le_v1` | 实现最简（dequant→bf16），但 d 由 fp16→bf16 会掉 ~0.4% 精度，**非严格无损** | +582 MiB |

> 补充一个支持 8-bit 方向的旁证（来自 TELE 自己的取证）：**参照 artifact 的官方 MTP 头就是用 `W8G32_F16S`（8-bit）存的**（TELE §2.6 E：`qwen3.8-27b-artifact.md:120:| MTP matrices | MTP | W8G32_F16S |`）；本机 `quasar_nvfp4.py:272` 也记 `"grouped_absmax q8_g32_fp16 for MTP head"`。
> **⇒ 上游官方就是用 8-bit 存 MTP 头，这直接支持"8-bit 存 MTP 是可接受的正统做法"。**

### 2.4 对"整包重写 13 GB"的顾虑 —— 实测不成立

TELE 选择原地手术的隐含动机是"避免重写 13 GB"。但：
- **本机自带官方 Python 写入器**：`src-tree/fusion-engine-src/tools/artifact/writer.py`（我实测 import 成功，`ArtifactWriter` 类可用；临时文件 + `os.link` 原子发布，**不会覆盖源文件**）
  `[EVIDENCE] tools/artifact/writer.py:255-257:for obj in self.objects: if self._coverage[obj.id].ranges != [(0, obj.bytes)]: raise ArtifactError(f"{obj.id}: output coverage is incomplete")`
  `[EVIDENCE] tools/artifact/writer.py:266-274:os.link(self._temporary[index], target)`
- **J 盘余量实测 235 GB**（`Get-PSDrive J`），写 13 GB 无压力
- ⇒ "整包重写"的成本 = 一次顺序拷贝（几分钟），**远低于调试一个 Q4_K 量化器的成本**

---

## §3 其余 4 处分歧（请 TELE 回应）

### 3.1 分歧：KVMem 是否"应可直接生效"

- TELE §6：**"KVMem：引擎级、与权重格式无关；本模型裸解码已通，KVMem 应可直接生效。"**
- **我的反例（源码级）**：本线 KVMem 是**纯环境变量驱动**，`NINFER_KV_WINDOW` 是环的**唯一真值**；**`NINFER_KV_RING` 已空转**（源码无 getenv 引用）；**`--kvmem-*` CLI 在本树未接线**；长上下文还必需 `--max-concurrency 1` + Legacy Host KV + 检索常开。
  `[EVIDENCE] src/serve/startup.cpp:48-52` + `src/serve/serve_options.cpp:1124-1132`（`NINFER_KV_WINDOW`）
- ⇒ "可直接生效"是**未验证的假设**，且若按 CLI 开关去找会**找不到**（未接线）。**请 TELE 核对其证据来源**：是有实测日志，还是推理？若是推理，应降级为【待证】。

### 3.2 分歧：启动器 `vision:on` 的定性

- TELE §6：把启动器适配归为"**工程收口，非技术卡点**"
- **我的反例**：`ninfer_launcher.py:193` **默认 `vision:on`**，而 Coder390 **无 vision 组件** ⇒ 启动即抛 `missing component vision`（`schema.cpp:91`）。
  ⇒ 这不是"收口"，是**启动器在 Coder390 上开箱即用的硬阻塞**。**建议提级为 P0 必改项**，与"MTP 探针"并列，而不是放到最后。

### 3.3 分歧：`MTP ≈ 2.3–2.5×` 不能作为 DFlash2 的决策依据

- TELE §5.C 以"MTP 已足够强（参照实测 MTP≈2.3–2.5×）"作为"DFlash2 边际价值低、可结案"的论据之一
- **我的反例**：该数字来自**参照模型 Qwen3.8-27B**，不能直接套到 Coder390 —— 本模型 MTP **只有 1 层**（`mtp/layers/0`）、是 **linear_attention 混合架构**、且 MTP 头被量化到 4-bit（还要再重存一次）。**三条都会压低接受率。**
- ⇒ 建议改为：**MTP 的收益在 Coder390 上完全未知，必须先实测**；DFlash2 的取舍等 MTP 实测后再定（这一点 TELE 自己也写了"需同口径 A/B 证明"，我建议把它提为硬前置，而不是附带说明）。

### 3.4 分歧：写入器"不在本机"

- TELE 记录："外部 `E:\infer-build` 上游 Python 写入器**不在本机**" —— **这句对**（该外部路径确实不存在）
- 但 TELE §4.B 写"**不需上游 Python 写入器**"，容易被读成"本机没有写入器、只能手写原地手术"
- **补充**：**本机 src-tree 里就自带官方写入器** `tools/artifact/writer.py`（已实测可用）。⇒ 整包重写不需要任何外部资源。

---

## §4 ★ 我的自我纠正（2 条，先认错）

1. **我错：`tools/strip_components.py` "未证实"是错的。**
   我在自己报告 §7.6 写"该脚本在本工作区不存在（搜索 0 命中）"——**我的搜索范围是 `src-tree/fusion-engine-src`，没覆盖 `official-repo\ninfer-fusion-kvmem\tools\`。**
   **实测：文件确实存在**，在 `official-repo\ninfer-fusion-kvmem\tools\strip_components.py`（8.13 KB，抬头 "repack a NInfer v3 artifact with some components removed"）。
   `[EVIDENCE] search_file *strip_components* → official-repo/ninfer-fusion-kvmem/tools/strip_components.py`
   ⇒ **TELE 的 E15 是对的，我的质疑不成立，撤回。**（教训：`.gitignore` 排除的目录 glob 不进去，跨子树取证必须用 PowerShell 全盘搜。）

2. **我错（表述过宽）："工作区内没有任何 DFlash 相关工具"。**
   准确说法是：**没有任何 dflash2 权重/草稿件**（需下载），但**工具与文档齐备**：
   - `refs\01-沈三殊-发放包\新\急速档\src-tree\ninfer-4090w-ternary\docs\maintainer\qwen3.8-27b-dflash2.md`（26.47 KB，另有 2 处副本）
   - `…\tools\convert\qwen3_8_27b\dflash2_inventory.py`（2.67 KB）、`dflash2_recipe.py`（14.45 KB）
   - `…\tests\convert\qwen3_8_27b\test_dflash2_recipe.py`、`…\tests\targets\qwen3_6_27b\test_engine_dflash2_real.cpp`
   `[EVIDENCE] search_file *dflash2* (refs) → 32 命中`

---

## §5 TELE 独有的、我认可并采纳的发现（3 条，补我的空白）

1. **MTP 落成 q4_0 的根因**（我没有）：`tools/convert/gguf_blocks.py:439` 用 `import_encoded` **逐字导入源 GGUF 的块格式** ⇒ 源 GGUF 的 MTP 头是 Q4_0，artifact 就必然是 q4_0。
   `[EVIDENCE] TELE §2.5 E11: gguf_blocks.py:416,434,439,475`
   ⇒ 这解释了我报告中"当前 recipe 会拒绝 q4_0 但本制品却带 q4_0"的疑问：**产出本制品的那版转换器注册过 Q4_0，当前树已移除**。
2. **参照 artifact 的官方 MTP 用 `W8G32_F16S`（8-bit）** —— 支持我的 8-bit 方向（见 §2.3 末）。
3. **参照 DFlash2 的完整几何契约**：`L_d=5` / `H=5120` / target 特征层 `[5,19,33,47,61]` / `mask_token_id=248070` / sliding 2048 / conv taps=2 group=16 / selector rank=256 top-16 / RoPE theta=1e7 —— 这是后续做 DFlash2 几何一致性证明时必须对齐的清单。

---

## §6 双方都还没证实的（继续取证清单，按重要性）

1. **【最高】MTP 在 Coder390 上的真实收益**：无人测过。必须 `--spec mtp` 实跑 A/B（同语料、同参数），拿 drafted/accepted 与 tok/s。
2. **【高】Coder390 与 Qwen3.8-27B 的层类型序列是否逐层一致**（DFlash2 嫁接的前置）。
   → **可立即做的静态检查**：本模型 `layer_types` 实测为 `index%4==3 → full_attention`；参照契约的 target 特征层 `[5,19,33,47,61]` 落在本模型上分别是 **5→linear、19→full、33→linear、47→full、61→linear**（**跨越两种层类型**）。⇒ 必须确认参照模型在 `[5,19,33,47,61]` 上的层类型**与本模型逐位一致**，否则 DFlash2 特征层语义错位。请对照 `refs\…\qwen3.8-27b-dflash2.md` 核这 5 层的类型。
3. **【中】`NINFER_KV_WINDOW` 的实际生效行为**（长上下文实测 + `kvmem_score: SELECT`）。
4. **【中】重存后 MTP 的数值正确性**：需要"独立 oracle"（解回 fp32 与原 q4_0 逐块比对误差），q8_0 应得 **误差 = 0**（这是它相对 q4_k/iq4_nl 的天然优势：可自证）。
5. **【低】交接文档的 SHA256 `CDD82B69…6921` 未复算**（TELE 已标【待补】，我认同保留该标记）。

---

## §7 合成后的单一建议（给用户裁决，两侧差异已收敛）

| 优先级 | 动作 | 关键选择 |
|---|---|---|
| **P0** | 部署适配（含 **`vision:on` 必须关**） | 硬阻塞，先做 |
| **P1** | **MTP 探针** | **建议 `gguf_q8_0` 严格无损**；产物**写新文件**到 `models\`（原件不动，T-PROTECT-ASSET），用本机 `writer.py` 整包重写 |
| **P2** | 拿读数 A/B（MTP 真实收益） | 决定后续是否值得继续投入 |
| **P3** | 定稿格式 | 依 P2 结果选 `iq4_nl`（零位移）或维持 `q8_0`；**不建议 `q4_k`** |
| **P4** | ngram 随 MTP 启 | 同口径 A/B，勿预设"翻倍" |
| **P5** | DFlash2 | 先做 §6.2 的层类型逐位核对（**零成本**）再决定是否下载 z-lab 权重 |
| 兜底 | 路 A（引擎补 Q4_0） | 仅在 P1/P3 出现不可解问题时启用；vendored ggml 已有内核，主要是接线 |

**我对用户 4 个待决的建议**：① MTP 走**数据侧（B）**、探针格式用 **q8_0**；② **允许**在 `models\` 下**新增**改写版（**不覆盖/不移动原件**）；③ DFlash2 **延后**（先做零成本的几何核对）；④ **暂不重编引擎**。

---

## §8 关于 TELE 的提交审批包（附带意见，我不擅自 commit）

- 两份文档（`docs\调研-目标实现路径-…md`、`docs\ninfer-kvmem-项目构建史.md`）按工具三分法属 **②项目文档**，定性正确，可入库。
- **建议**：**先完成本轮交叉审核、把 §2 的格式分歧与 §4 的自我纠正收敛后再提交**，避免"报告已入库但结论已被修订"的不一致状态。收敛后我支持一次提交。
- 另：TELE 提到 `.temp\` 下的解析脚本是临时中间物、不入库 —— 同意；按 T-NO-TEMP-WORK，若该脚本有复用价值，建议**转正**到 `tools\` 下而非留在 `.temp\`。

---

**署名**：CodeBuddy ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`
**审核姿态**：印证 11 条 / 提出分歧 5 处 / 自我纠正 2 处 / 采纳对方 3 条 / 列出待证 5 项。
**给 TELE 的回应请求**：重点回 §2.3（格式选择）与 §3.1（KVMem 证据来源）两条。
