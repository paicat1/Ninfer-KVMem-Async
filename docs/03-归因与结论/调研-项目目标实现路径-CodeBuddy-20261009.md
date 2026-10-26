# 调研报告：ninfer-kvmem 项目目标的实现路径

> **署名**：CodeBuddy（IDE 环境）｜**日期**：2026-10-09｜**工作区**：`J:\ninfer-kvmem`
> **性质**：**只读调研**，未修改任何代码 / 模型 / 引擎文件。
> **用途**：回答"本项目目标到底怎么实现"，供用户裁决，并与 TeleAgent（TELE）的独立报告做**交叉审核**。
> **子报告（三路并行调研的原始取证）**：
> - `docs\_research\codebuddy-mtp-roadA-引擎侧补q4_0.md`
> - `docs\_research\codebuddy-mtp-roadB-数据侧重打包.md`
> - `docs\_research\codebuddy-dflash2-ngram-部署适配.md`
>
> **证据纪律**：每条关键结论后附 `[EVIDENCE] 路径:行号:原文`。凡本报告写"实测"，均为本机当场跑出来的原始输出，非转述。

---

## §0 一句话结论

**目标可达成，但三条投机的难度与确定性差异极大，必须按"先易后难、先验证后投入"排序：**

| 目标 | 我的判断 | 首期动作 |
|---|---|---|
| **MTP** | **高度可行**，且**不需要重编引擎** | 数据侧把 5 个 `gguf_q4_0` 重存为 `gguf_q8_0`（**逐位无损**），用本地官方 Python 打包器重排容器 → 当天可拿到"MTP 能否起 + 接受率"读数 |
| **DFlash2** | **能跑，但收益未知**；本模型有"同基座"这一重要利好，比 Bonsai 线的处境乐观 | 排在 MTP 之后；先用官方同基座权重做接受率实测，**不先投入自训** |
| **ngram** | 自身无独立障碍，**完全随 MTP 通而通** | 随 MTP 验收，不单列投入 |

**核心建议：暂不重编引擎（路 A）。** 数据侧方案（路 B）更便宜、可逆、当天见效；路 A 留作兜底。

---

## §1 目标拆解（把"跑起来"翻译成可判定的子目标）

用户原话目标 = NInfer 核心解码 + KVMem 长上下文 + 三种投机解码，落到 Coder390 上。拆成可验收的子项：

| # | 子目标 | 判定标准（客观、可跑出来） |
|---|---|---|
| G0 | 裸解码跑通 | ✅ 已完成，~52 tok/s（前序实测） |
| G1 | **MTP 投机生效** | `--spec mtp` 装得上 + `drafted/accepted tokens` 有读数 + tok/s 高于 G0 基线 |
| G2 | **DFlash2 投机生效** | `--spec dflash2` 装得上 + 接受率 ≥ 可接受阈值（建议 ≥60%，理由见 §4.3） |
| G3 | **ngram 生效** | `--ngram-draft-tokens` 有读数；`--lookup-ngram` A/B 有差异 |
| G4 | **KVMem 长上下文可用** | 长上下文不 OOM、`NINFER_KV_WINDOW` 生效、召回正常 |
| G5 | 部署/启动器适配完成 | 4 个 bat + 启动器 + profiles 全部指向 Coder390 与本工作区路径，默认参数不再触发"无 vision 组件"报错 |

---

## §2 现状取证（本机实测，含对既有文档的纠正）

### 2.1 容器真实读数（用官方 `tools/artifact/inspect.py` 当场跑出）

```
file_bytes        13,272,798,720   (12.36 GiB)
payload_bytes     13,272,548,864
json_bytes           249,824       → payload 起点 249,856 (= 61 × 4096)
artifact_id       f2e0f91359304bd9a7f34234f11cb742
components        text, mtp        (mtp: {"target":"text","config":{"architectures":["Qwen3_5MTP"]}})
objects           804  (800 tensor + 4 resource)
formats           bf16:360  fp32:96  gguf_iq2_s:21  gguf_iq3_s:144  gguf_iq3_xxs:26
                  gguf_iq4_xs:76  gguf_q2_k:2  gguf_q4_0:5  gguf_q4_k:67  gguf_q5_k:2  int32:1
layouts           contiguous_le_v1:457  gguf_blocks_v1:343
```

- `[EVIDENCE] 本机实跑输出（cd official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src; python -m tools.artifact.inspect <模型> --json）："file_bytes": 13272798720 / "objects": 804 / "tensors": 800 / "formats": {..., "gguf_q4_0": 5, ...}`

### 2.2 ⚠️ 纠正既有文档的一处数字笔误（请 TELE 交叉核对）

`docs\05-交接与值守\交接-工作区迁移-TeleAgent-20261009.md:72` 写 `12,372,798,720 B`，**实际为 `13,272,798,720 B`**（数字位序笔误；两者都 ≈12.36 GiB，故不影响后续结论，但引用时应更正）。

- `[EVIDENCE] docs/05-交接与值守/交接-工作区迁移-TeleAgent-20261009.md:72:- 大小：**12,372,798,720 B**（≈12.36 GiB）`

### 2.3 5 个 `gguf_q4_0` 张量：全部属于 mtp，text 侧零 q4_0

**这是本次调研我特意去证伪的一点**：它们的 offset 分成两簇（2 个在 4.2 GB 处、3 个在 13.17 GB 处），看起来像"text 里也有 q4_0"。查 bindings 后确认**全部归属 mtp**：

```
weight/000079  [14336, 5120]   41,287,680 B  offset  4,220,248,576
weight/000080  [34816, 5120]  100,270,080 B  offset  4,261,536,256
weight/000789  [ 5120,10240]   29,491,200 B  offset 13,175,151,104
weight/000796  [ 5120, 6144]   17,694,720 B  offset 13,204,684,288
weight/000798  [ 5120,17408]   50,135,040 B  offset 13,222,389,248
合计 238,878,720 B（227.8 MiB）／424,673,280 个权重 ＝ 全模型 payload 的 1.80%
```

- `[EVIDENCE] 本机 bindings 实测：mtp/input_projection {"object": "weight/000789"}`
- `[EVIDENCE] 本机 bindings 实测：mtp/layers/0/attention/query {"parts": [{"object": "weight/000079", "range": [0, 31457280]}]}`（key/gate/value 另三段，合起来覆盖整个 000079）
- `[EVIDENCE] 本机 bindings 实测：mtp/layers/0/mlp/gate {"parts": [{"object": "weight/000080", "range": [0, 89128960]}]}`（up 段 [89128960,178257920]）
- `[EVIDENCE] 本机 bindings 实测：mtp/layers/0/attention/output → 000796、mtp/layers/0/mlp/down → 000798`

**归纳**：MTP 只有 1 层（`layers/0`），5 个张量覆盖 input_projection / attention（q,k,v,gate,output）/ mlp（gate,up,down）。

**⚠️ 改动面精确表述（2026-10-09 二轮修订，采纳 TELE 的独立发现）**：
- **改 5 个**：上述 5 个 `gguf_q4_0`
- **原样搬运 799 个**：794 个其他 tensor + **1 个 `auxiliary/000000`** + 4 个 resource
- **`auxiliary/000000` 不是 resource，是 800 tensor 之一**，重打包**必须保留**：
  `[EVIDENCE] inspect --objects 实测：13272524288  24576  tensor  int32/contiguous_le_v1 [6144]  auxiliary/000000`
  （24,576 B = 6144 × 4 B。**2026-10-09 二轮修订 · 归因更正**：6144 的正确来源是 **GDN：`linear_num_value_heads 48 × linear_value_head_dim 128`**，不是我首轮写的"24 heads × 256 head_dim"（那是**注意力**的 `num_attention_heads 24 × head_dim 256`，两者**巧合同为 6144**，但归因错误）。
  `[EVIDENCE] 本容器 config 实测：'linear_num_value_heads': 48, 'linear_value_head_dim': 128`（48×128 = 6144）
  `[EVIDENCE] tools/convert/ternary.py:48-51:GDN_VALUE_HEADS = 48 / GDN_HEAD_DIM = 128 / GDN_VALUE_DIM = GDN_VALUE_HEADS * GDN_HEAD_DIM`（TELE 指出，复核成立）
  它位于 payload 最末，offset 13,272,524,288。）
- 范例脚本也强制保留 auxiliary：`[EVIDENCE] tools/strip_components.py:133-134:elif obj.id.startswith("auxiliary/"): keep_ids.add(obj.id)  # tiny constants the engine may name by convention`

### 2.4 一个重要的既有结论需要"精确化"

交接文档说"`reader.cpp` 无内容校验 ⇒ 数据侧重打包安全"——**结论成立，但表述需要收紧**：容器确实**没有内容哈希/校验和**，但存在 8 项结构性校验（文件长度 = payload 起点 + payload_bytes、`bytes` 必须等于几何算出的值、`offset` 必须 **256** 字节对齐、对象递增不重叠不越界、`components` 必须含 `text`、JSON 不允许重复成员…）。**任何一项不满足都会拒载**，所以"随便改字节"是不行的，必须走正规 writer。

- `[EVIDENCE] official-repo/.../src/artifact/reader.cpp:48-52:if (expected != file->bytes()) { throw ArtifactError(entry.string() + ": entry length differs from directory"); }`
- `[EVIDENCE] official-repo/.../src/artifact/layouts.cpp:12:if (geometry.bytes != object.bytes || object.offset % geometry.alignment) { throw ArtifactError("encoded size or object alignment differs from layout"); }`（**对齐的执行点在此**。2026-10-09 二轮修订：TELE 指出我原引 `weight_view.h:39` 只是 `WeightGeometry::alignment` 的**默认值定义**、非执行点——结论不变，引用归属已更正）
- `[EVIDENCE] official-repo/.../src/artifact/schema.cpp:252-254:if (!values.contains("text")) { throw ArtifactError("components must contain text"); }`

---

## §3 MTP：三条路线的对比与推荐

### 3.1 卡点根因（已由我复核确认）

- `[EVIDENCE] official-repo/.../src/artifact/formats.cpp:55-60:QType parse_format(...) { for (...) if (spelling == name) return format; } throw ArtifactError("unknown tensor format: " + std::string(name)); }`
- `[EVIDENCE] official-repo/.../src/artifact/formats.cpp:10-37:` 白名单 26 项，**含 `gguf_q4_k`(L25)、`gguf_iq4_nl`(L35)、`gguf_q8_0`(L22)、`bf16`(L11)，但无 `gguf_q4_0`，也无 `gguf_bf16`**
- 校验是**惰性**的（只在对象被物化时做）⇒ 不加 `--spec mtp` 时 MTP 权重永不被解析，这就是**裸解码不受影响**的原因：
  `[EVIDENCE] official-repo/.../src/artifact/reader.cpp:113-119:void Reader::validate_object(ObjectHandle handle) const { ... (void)geometry(handle); ... }`
  `[EVIDENCE] official-repo/.../src/artifact/materializer.cpp:236:reader.validate_object(placement.object);`

> ⚠️ **拼写陷阱（请 TELE 注意）**：目标格式的正确拼写是 **`bf16`**（不带 `gguf_` 前缀）、`gguf_q8_0`、`gguf_iq4_nl`、`gguf_q4_k`。交接文档 §3.2 写的"重存为 bf16 / q4_k"若落成 `gguf_bf16` 会直接被拒。

### 3.2 三条路线对比

| | **路 B（数据侧重存重打包）** | **路 A（引擎补 q4_0 重编）** | **路 C（请上游重导）** |
|---|---|---|---|
| 是否需要重编引擎 | **否** | 是（MSVC+CUDA13.3+clean build，小时级） | 否 |
| 本机是否有现成工具 | **有**：`tools/artifact/{reader,writer}.py`（官方，只依赖标准库，实测可 import） | 需手写补丁 | 依赖外部人 |
| 数值损失 | 取决于目标格式（见 §3.3） | 无 | 无 |
| 可逆性 | **高**（原件不动，出新版） | 中（引擎补丁可回退） | — |
| 阻塞项 | 需 ~13.3 GB 磁盘（**实测 J 盘余 235 GB ✅**） | 工具链路径要改（脚本写死本机路径） | 需拿到源 GGUF（本机 provenance 指向 `/opt/coder390/...`，**本地没有**） |
| 主要风险 | 重排 13 GB 文件的 IO 与实现细节 | 重编失败 / 增量构建产崩二进制 | 不可控 |

### 3.3 ★ 我的独立判断：目标格式应选 **`gguf_q8_0`（无损）做探针**，而非子报告推荐的 `iq4_nl`

子报告推荐 `gguf_iq4_nl`（Δbytes = 0）。我认为**探针阶段应改选 `gguf_q8_0`**，理由如下（这是本报告最重要的判断）：

**q4_0 → q8_0 是逐位无损的**（不是"反量化再重量化"）：

- q4_0 块 = `fp16 d` + 32 个 4-bit 码，**值 = (nibble − 8) × fp16(d)**，nibble∈[0,15] ⇒ 整数值 ∈ **[−8, 7]**
  `[EVIDENCE] official-repo/.../third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:46-58:v.x = vui & 0xF; ... v.x = (v.x - 8.0f) * d;`
  `[EVIDENCE] official-repo/.../third_party/ggml-quants/src/ggml-common.h:194-199:#define QK4_0 32 / ggml_half d; uint8_t qs[QK4_0 / 2];`
- q8_0 块 = `fp16 d` + 32 个 int8，**同为 32 元素/块**
  `[EVIDENCE] official-repo/.../tools/artifact/formats.py:101:GGUF_Q8_0 = GgufFormat("gguf_q8_0", 8, 32, 34)`
- ⇒ **scale 原样拷贝，nibble 直接写成 int8(nibble − 8)**，值域 [−8,7] 完全落在 int8 内，**零浮点运算、零舍入、零精度损失**。

**为什么"无损"在探针阶段比"零体积"更重要**：
探针的目的是**消除不确定性**。若用有损的 iq4_nl，一旦接受率偏低，我们将**无法归因**——分不清是"MTP 本身在这个模型上收益小"还是"转换损失打死了接受率"。无损的 q8_0 让读数干净，一次实验定生死。

| 目标格式 | 5 张量新体积 | 增量 | 数值 | 实现难度 | 建议用途 |
|---|---|---|---|---|---|
| **`gguf_q8_0`** | 451,215,360 B | **+202.5 MiB（占全模型 1.5%）** | **逐位无损** | 低（nibble→int8，~10 行 numpy，无需浮点） | **★ 探针首选** |
| `gguf_iq4_nl` | 238,878,720 B | **0 B** | 有损（absmax 重标定 + 16 项非线性表查表），但 iq4_nl 在 4.5bpw 下**质量本身优于 q4_0** | 中（查表） | **定稿优选**（拿到读数后再做） |
| `gguf_q4_k` | 238,878,720 B | 0 B | 有损 | **中高**（256 元素超块、6bit scale/min 打包） | 不推荐 |
| `bf16`+`contiguous_le_v1` | 849,346,560 B | +582.1 MiB | 无损（fp32→bf16 截断） | 最低 | 兜底 |

（体积由 `tools/artifact/layouts.py::encoded_size` 对本机 5 个 shape 实算；K = 5120/10240/6144/17408 **全部 %32==0 且 %512==0**，满足 gguf 块格式与 Op 侧几何约束
`[EVIDENCE] official-repo/.../src/core/weight_view.cpp:123-125:if (!is_gguf(format) || k % std::uint64_t(block.elements)) { throw ... "GgufBlocks requires a ggml block format over whole blocks"; }`
`[EVIDENCE] official-repo/.../src/ops/linear/gguf/gguf_linear.cpp:112:... || w.k % block.elements != 0 || w.k % 512 != 0) {`）

### 3.4 路 B 的具体落地路径（已验证工具链）

1. **读**：`Artifact(...)` 打开原件；**对这 5 个 q4_0 对象必须用 `iter_range(offset, bytes)`，不能用 `iter_object()`**——Python reader 会做 `validate_encoding`，而 `gguf_q4_0` 不在注册表里会直接抛错：
   `[EVIDENCE] official-repo/.../tools/artifact/reader.py:165-167:if object_id not in self._validated: validate_encoding(obj);`
   `[EVIDENCE] official-repo/.../tools/artifact/reader.py:128-130:def iter_range(self, offset: int, length: int, ...)`
2. **转**：numpy 拆 nibble（`qs[i]` 低 4 位 = 元素 2i，高 4 位 = 2i+1）→ int8(n−8)，scale 原样拷贝。无需装 torch/gguf（**本机实测 numpy ✅ 已装，torch ❌，gguf ❌**）。
3. **写**：`ArtifactWriter(dst, specs, components=, bindings=, uses=, metadata=, provenance=)`，其余 795 个 tensor + 4 个 resource 用 `write_object(id, art.iter_object(id))` 原样流式搬运，`finish()` 强制全覆盖校验：
   `[EVIDENCE] official-repo/.../tools/artifact/writer.py:255-257:for obj in self.objects: if self._coverage[obj.id].ranges != [(0, obj.bytes)]: raise ArtifactError(f"{obj.id}: output coverage is incomplete")`
   `[EVIDENCE] official-repo/.../tools/artifact/writer.py:266-274:os.link(self._temporary[index], target)`（临时文件 + 原子发布，**源文件不会被覆盖**，符合 T-PROTECT-ASSET）
4. **改字段**：只改 5 个对象的 `format` 字符串；`shape`、`bindings.parts.range` **都不用改**（range 是逻辑元素下标，与存储格式无关）：
   `[EVIDENCE] official-repo/.../src/artifact/transcode.h:17-18:Logical element addressing (row * columns + column) is the same before and after, so bindings over parts of a transcoded object stay valid.`

**⚠️ 实现陷阱（必须交给 writer 处理）**：本机 `json_bytes = 249,824`，`32+249,824 = 249,856 = 61×4096` **正好卡在对齐边界**。`gguf_q4_0`(9 字符)→`gguf_q8_0`(9 字符) **长度不变**，payload 起点不变；但 →`gguf_iq4_nl`(10 字符) 会 +5 字节 ⇒ payload 起点 +4096 ⇒ **全部 804 个对象 offset 要平移，必须整包重写**。**结论：不要手算 offset、不要"原地打补丁"，一律用 `ArtifactWriter` 全量重排。**

### 3.5 路 A 的兜底预案（若将来必须支持原生 q4_0）

子报告已探明**不需要写 CUDA GEMM 内核**——引擎有现成 fallback：

- `[EVIDENCE] official-repo/.../src/ops/linear/gguf/ggml_bridge.h:111-117:// The same product as matrix_product for a type without an integer kernel: each pass dequantizes ... into scratch (BF16) and runs a cuBLAS BF16 GEMM`
- 先例：`IQ1_M` 就是走这条路（`has_matrix_kernel` 对它返回 false）：
  `[EVIDENCE] official-repo/.../src/ops/linear/gguf/ggml_bridge.cu:311:bool has_matrix_kernel(GgmlType type) { return type != GgmlType::IQ1_M; }`
- Q4_0 与 IQ4_NL 块几何相同（32 元素 / 18 字节），`Decoder` 可照抄：
  `[EVIDENCE] official-repo/.../src/ops/linear/gguf/ggml_bridge_vec.cuh:107-109:struct Decoder<GGML_TYPE_IQ4_NL> { static constexpr int kBlockElems = 32, kBlockBytes = 18, ...`
- 第三方 ggml 里 Q4_0 全链路齐备（`GGML_TYPE_Q4_0=2`、`block_q4_0`、mmq DP4A/MMA）：`[EVIDENCE] .../third_party/ggml-quants/src/ggml-cuda/mmq.cuh:402:case GGML_TYPE_Q4_0: return MMQ_DP4A_TXS_Q4_0;`
- **两个坑**：① `QType` 不能重编号（有 static_assert 护栏），只能追加并同步改 `is_gguf()`；② 重编必须 **clean build**（增量构建会产出"启动即崩"的二进制），且构建脚本里 CMake/Ninja 的 Community 路径本机不存在（在 BuildTools 下）、SRC 需改到本工作区。

### 3.6 一个值得注意的反向线索

本机容器的 `provenance` 记录了源 GGUF 路径，且**当前源码树的 `qwen3_8_27b_gguf` recipe 会拒绝含 q4_0 的 GGUF，但本机这个制品却带 q4_0** ⇒ 说明**产出本制品的那套转换器当时注册了 Q4_0（type id 2），当前树已移除**。若能向上游拿到那份源 GGUF 或转换器，路 C 可做到零损失。

- `[EVIDENCE] 容器 provenance 实测：{"converter":"ninfer-v3","recipe":"qwen3_8_27b_gguf","sources":{"base":{"path":"/opt/coder390/Qwen3.8-27B-Coder390-EfficientThink/model"},"gguf":{"path":"/opt/coder390/Q2LynnStyle/Qwen3.8-27B-Coder390-Q2LynnStyle-MTP.gguf"}}}`

---

## §4 DFlash2：能跑 ≠ 有正收益

### 4.1 卡点与报错链

- `[EVIDENCE] official-repo/.../src/artifact/schema.cpp:88-94:const Component& Directory::component(std::string_view name) const { ... throw ArtifactError("missing component " + std::string(name)); }`
- 触发链：`config.cpp:335` → `companion()`(`:48-54`) → 用 `load_options.h:95` 返回的 `"dflash2"` 查目录；被 `config.cpp:340` 加前缀成 `Qwen3.5 config: …`
- 引擎用到的组件名：`text`（必需）/ `vision` / `mtp` / `dflash` / `dflash2`；**Coder390 只有 `text`+`mtp`**

### 4.2 需要什么（注入清单）

- config 12 字段 + `dflash_config`（`target_layer_ids` / `mask_token_id` / `conv_kernel_size` / `conv_group_size` / `selector_rank` / `selector_top_k`）
- 权重见 `load/dflash.cpp:12-42`、`load/dflash2.cpp:5-29`；**embedding / output_head 直接复用 target**，codebook 形状 `[vocab, rank]` ⇒ **注入的权重增量很小**
- 工作区内实测**没有任何 `*DFlash*` 目录**（`DFlash2-FP8/` 不存在，子报告已确认）

### 4.3 ★ 我的独立判断：本模型有"同基座"利好，比 Bonsai 线乐观，但必须实测接受率

- **利好证据**：容器 provenance 显示 base = `Qwen3.8-27B-Coder390-EfficientThink`，recipe = `qwen3_8_27b_gguf`；而官方 DFlash2 权重是 `z-lab/Qwen3.8-27B-DFlash2`（**同基座 Qwen3.8-27B**）。
- **反面证据（Bonsai 教训）**：Bonsai 线的"自造注入件"用的是在该基座上**重训**的 `ProCreations/Ternary-Bonsai-2-27B-DFlash2`；非同源训练的头接受率崩（B18 实测 22% / 47% vs 同源 91.5–100%）。根因是**草稿头吃的是 target 残差**，换 target 就失配。
- **我的综合判断**：
  - Coder390 是 Qwen3.8-27B 的**微调**产物（非三元重训），与基座的距离远小于 Bonsai ⇒ **同基座 DFlash2 的可用性显著高于 Bonsai 场景，值得一试**；
  - 但 Coder390 被量化到 Q2LynnStyle（iq2_s/iq3_s/iq4_xs 等低比特），**量化后的残差 ≠ 原 bf16 残差**，DFlash2 头是在原精度上训练的 ⇒ 接受率必然打折；
  - 另外本模型是 **linear_attention ×3 + full_attention ×1 的混合层结构**（`layer_types` 实测），草稿头必须匹配该结构。
- **结论**：**先做 MTP（确定有收益、成本低），再拿官方同基座权重做 DFlash2 接受率实测；若接受率 <60% 则放弃或转"自训"（成本高，需另议）。绝不先投入自训。**

### 4.4 关于"自造注入件"的参考做法

`refs\01-沈三殊-发放包\新\急速档V2\` 里的做法 = `tools.convert --source dflash2=PATH --components text,vision,mtp,dflash2`（从源权重整包重导）。**这条路对我们不成立**——我们没有 Coder390 的源 safetensors/GGUF（provenance 指向 `/opt/...`，本地无）。⇒ 若走 DFlash2，只能**在容器层面注入组件**（用 §3.4 那套 reader+writer，往 components/bindings/objects 里加 dflash2 条目）。

---

## §5 ngram：没有独立障碍，随 MTP 通而通

- `--ngram-draft-tokens` 的校验：`speculative_options.h:50-58`，**必须配 `--spec`**；实现在 `decode.cpp:232-298` ⇒ **MTP 一通，ngram 立即可用**
- `--lookup-ngram`：**只挂在 MTP 分支**（`prefill.cpp:997/1013`），配 dflash2 时是死代码、且**无 backend 校验** ⇒ 这正好解释了前序实测的"**启动了但空转、52.9 vs 51.9 无差异**"——MTP 没通，它无从生效
- ⇒ **ngram 不单列投入，作为 MTP 的验收项之一**

---

## §6 非投机部分：KVMem 与部署适配（都是"必改"，不是"选做"）

### 6.1 KVMem：**纯环境变量驱动，CLI 未接线**（2026-10-09 二轮修订：措辞收紧）

- **是一族环境变量，不是"唯一真值"**（我原表述过窄，TELE 指出后我复核成立并进一步精确化）：
  - 环开关：`NINFER_KV_WINDOW`
    `[EVIDENCE] src/serve/serve_options.cpp:1125:const char* text = std::getenv("NINFER_KV_WINDOW");`
  - 另有 `NINFER_KV_RETRIEVE(_AUTO)` / `NINFER_KV_NEIGHBOR_PAGES` / `NINFER_KV_REUSE_HOSTBACKED` / `NINFER_KV_SINK` / `NINFER_HOST_PAGEABLE`，以及一族诊断开关 `NINFER_TERNARY_KVMEM*`（`raw_k_*`、`WINDOW_ASSEMBLY`、`SEMANTIC`、`RAWK_ARENA` 等，多为 opt-in）
    `[EVIDENCE] src/ops/kvmem/kvmem_window_plan.h:42-50:const char* value = std::getenv("NINFER_TERNARY_KVMEM_WINDOW_ASSEMBLY"); const char* ring = std::getenv("NINFER_KV_WINDOW"); ... "ring precedence: NINFER_KV_WINDOW is set -> Z-side window assembly yields"`
- **`NINFER_KV_RING` 的正确定性**（我原写"已空转"，不精确）：它是**被废弃的旧名**——该 gate 曾读它，2026-10-07 的 B30 修复把它改为读 `NINFER_KV_WINDOW`：
  `[EVIDENCE] src/serve/serve_options.cpp:1118-1122:// B30 (fixed 2026-10-07): this gate used to read NINFER_KV_RING, while the engine-side gate (models/qwen3_5/program/planning/startup.cpp, ring_requested()) reads NINFER_KV_WINDOW. The engine's own advice therefore named the WRONG variable: setting only NINFER_KV_RING passed here ...`
- **`--kvmem-*` CLI 在本树未接线**（此点双方一致）
- **启动器已固定注入 5 个开关**（新增，重要）：`ninfer_launcher.py:54-60` 的 `KV_ENV` = `NINFER_KV_WINDOW=16384` / `KV_RETRIEVE=8192` / `KV_RING=1` / `HOST_PAGEABLE=1` / `KV_REUSE_HOSTBACKED=1`，且 `:291 env.update(KV_ENV)`。
  `[EVIDENCE] ninfer_launcher.py:53:# KVMem 五开关：缺一 = 起得来但静默答错（缓存命中率高、中段答错、零报错）。GUI 内固定注入。`
  ⇒ **KVMem 不需要我方额外配置**（启动器已注入），但**必须判活**：注释明示"缺一 = 起得来但**静默答错**、零报错" ⇒ 长上下文验收必须看到 `kvmem_score: SELECT`，**不能凭"能起来"判定生效**。

### 6.2 部署适配必改清单（实测行号）

| 位置 | 现状 | 必改 |
|---|---|---|
| `ninfer_launcher.py:40` | 模型名仍是 Bonsai | → Coder390 文件名 |
| `ninfer_launcher.py:193` | 默认 `vision:on` | → **off**（Coder390 无 vision 组件，会直接抛 `missing component vision`） |
| `ninfer_launcher.py:270` | `--model-id qwen3.8-27b` | 核对是否需改为 coder390 口径 |
| `start-pq2.bat` / `start-pq2-dflash.bat` / `start-pq2-dflash-designc.bat` / `start-ptq1-mtp.bat` | MODEL 变量、`--vision`、`--spec dflash2` 均为旧口径 | 逐个改为 Coder390 + 本工作区路径 |
| `启动器.bat:7` | 写死 `D:\Python311` | 改为本机实际解释器路径 |
| `ninfer_launcher_profiles.json` | 旧档位 | 同上 |

⚠️ **`vision:on` 这条尤其重要**：它是"启动器在 Coder390 上开箱即用"的硬阻塞，而不是优化项。

---

## §7 风险与未知（诚实列出，不粉饰）

1. **MTP 的真实收益未知**：本模型 MTP 只有 1 层，且是 linear_attention 混合架构，MTP 能带来多少加速**没有任何本机证据**，必须实测（建议 A/B：裸解码 vs `--spec mtp` 的 tok/s 与 accepted/drafted）。
2. **重排 13.27 GB 容器**：IO 与耗时；**产物必须另存新文件，严禁覆盖原件**（T-PROTECT-ASSET）。J 盘余量实测 **235 GB ✅ 充足**。
3. **"文件合法 ≠ 引擎能跑"**：上游明确警告过"自写 recipe 能覆盖到什么程度"有限，`artifact object was not consumed by the selected target` 类拒载仍可能出现 ⇒ 重排后必须跑 L0 结构校验 + 引擎冒烟。
4. **上游对"反量化再进 ninfer"的公开态度是"不推荐"**——但该结论针对的是**整模型**反量化重量化；我们只动 1.8% 的权重、且是 MTP 草稿头（输出由主模型验证/拒绝，**不影响主模型输出分布**），因此不构成否决，但必须做数值与端到端验证。
5. **DFlash2 的接受率风险**（§4.3），且工作区内**没有任何可用草稿件**。
6. ~~**子报告中有一处未证实**：`tools/strip_components.py` 不存在~~
   **【2026-10-09 二轮修订 · 撤回】** 该"未证实"是**我自己的搜索范围错误**：我只在 `src-tree/fusion-engine-src` 下搜，没覆盖 `official-repo\ninfer-fusion-kvmem\tools\`。
   **实测文件存在**：`official-repo\ninfer-fusion-kvmem\tools\strip_components.py`（8.13 KB，抬头 "repack a NInfer v3 artifact with some components removed"）。
   `[EVIDENCE] official-repo/ninfer-fusion-kvmem/tools/strip_components.py:1:strip_components.py -- repack a NInfer v3 artifact with some components removed.`
   唯一真问题：`:25:UPSTREAM = r"E:\infer-build\refs\infer-all-full\ninfer-all-master"` 是外部路径，本机不存在 ⇒ 使用前改为本机 `src-tree\fusion-engine-src` 即可。
   **教训（写入纪律）**：`official-repo/` 被 `.gitignore` 排除，glob 类检索**不进入**该目录 ⇒ 跨子树取证一律用 PowerShell，否则产生假阴性。

---

## §8 落地路线图（建议）

| 阶段 | 动作 | 产出 | 验收判据 |
|---|---|---|---|
| **P0（当天）** | 部署适配：4 bat + 启动器 + profiles 改 Coder390/本区路径，vision 关掉，解释器路径修正 | 可启动、可裸解码 | 启动器起得来、52 tok/s 基线复现 |
| **P1（探针）** | q4_0 → **q8_0 无损**重存 + `ArtifactWriter` 全量重排（**新文件，不覆盖原件**） | `models\Coder390-...-mtp-q8.ninfer` | L0：`inspect --objects --bindings` 无异常；L4：`--spec mtp` 装得上 |
| **P2（读数）** | A/B：裸解码 vs `--spec mtp` | tok/s、drafted/accepted、tok/round | **有加速且接受率合理**才继续投入 |
| **P3（精修）** | 换成 `iq4_nl` 定稿（Δ0，4.5bpw 下质量优于 q4_0） | 定稿容器 | 与 P2 读数对比不劣化 |
| **P4（ngram）** | `--ngram-draft-tokens` + `--lookup-ngram` A/B | 读数 | 有差异才算生效；无差异则记录为"不可用"并停止 |
| **P5（DFlash2）** | 取官方同基座权重 → 容器层注入 → 接受率实测 | 报告 | 接受率 ≥60% 才保留 |
| **P6（KVMem）** | 用 `NINFER_KV_WINDOW` 环境变量配置，长上下文实测 | 长上下文不 OOM + 召回正常 | 与 G4 判据对齐 |
| 兜底 | 仅当 P1/P3 出现对齐/语义不可解问题 → 走路 A（补 q4_0 + 重编） | 引擎补丁 | clean build + 冒烟 |

> **纪律**：每阶段产物落正式目录（`models\` / `docs\`），不留 `.temp\`；每个结论带证据落盘；commit 前按 T-COMMIT-APPROVAL 完整展示并停等批准。

---

## §9 请用户裁决的事项

1. **是否批准 P1 的数据侧重打包**（会在 `models\` 下新增一个 ~13.5 GB 文件，原件不动）。
2. **是否现在就跑去上游（沈三殊）问两件事**：① 能否用支持格式重导 MTP 头（路 C）；② 有无适配 Qwen3.8-27B 的 DFlash2 权重（P5 前置）。这两问零成本但能省掉大量试错。
3. **是否暂缓路 A（重编引擎）**——我的建议是暂缓。
4. **DFlash2 的投入门槛**：接受率阈值定在多少才继续（我建议 60%）。

---

## §10 给 TELE 的交叉审核对照点（请逐条核对或反驳）

| # | 我的结论 | 需要 TELE 核对/反驳的点 |
|---|---|---|
| 1 | 模型实际 `13,272,798,720 B`，交接文档写 `12,372,798,720` 是笔误 | 请确认并更正文档 |
| 2 | 5 个 q4_0 **全部属于 mtp**（offset 分两簇容易误判） | 你的判断是否一致？有无证据推翻？ |
| 3 | 目标格式拼写是 **`bf16`** 而非 `gguf_bf16`；`gguf_q4_0` 不存在 | 你文档 §3.2 的"bf16 / q4_k"是否落成了错误拼写？ |
| 4 | **探针应选 q8_0（逐位无损）而非 iq4_nl（Δ0 但有损）** | 这条可能与你的推荐相反，请给反驳或认同 |
| 5 | 对象对齐是 **256**，payload 起点才是 4096；`json_bytes` 正好卡边界 | 与你掌握的容器格式描述是否一致？ |
| 6 | **KVMem 只走 `NINFER_KV_WINDOW` 环境变量，`--kvmem-*` 未接线、`NINFER_KV_RING` 已空转** | 请核对，这条影响长上下文怎么配 |
| 7 | `ninfer_launcher.py:193` 默认 `vision:on` 是 Coder390 的**硬阻塞** | 你那边是否也定位到？ |
| 8 | ~~`tools/strip_components.py` **在本工作区不存在**~~ → **【2026-10-09 二轮修订 · 本人撤回并证伪自己】** 该文件**确实存在**于 `official-repo\ninfer-fusion-kvmem\tools\strip_components.py`（8.13 KB）。我首轮判"不存在"是**我自己的检索范围错误**（只搜 `src-tree` 子树，`official-repo/` 被 `.gitignore` 排除、glob 不进入）。TELE 的 E15 正确，我的质疑不成立。详见 §7.6 | （无需 TELE 回答；改为请 TELE 确认我的撤回已到位） |
| 9 | DFlash2：**同基座利好，但量化残差失配，接受率必须实测** | 你是否认同"先 MTP、后 DFlash2、不先自训"的排序？ |

> 两侧结论不一致时按纪律**停止操作并报告差异**，同步须经用户授权。本报告只做只读调研，未改动任何文件。

---

**署名**：CodeBuddy ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`
**证据可复现**：本报告所有"实测"均可用 `cd official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` 后 `python -m tools.artifact.inspect <模型> [--objects|--bindings|--json]` 复跑验证。
