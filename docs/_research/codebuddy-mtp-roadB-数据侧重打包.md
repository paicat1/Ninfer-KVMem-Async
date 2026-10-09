# 路 B 可行性调研：不重编引擎，数据侧把 MTP 的 5 个 `gguf_q4_0` 反量化重存并重打包 `.ninfer`

> 调研者：CodeBuddy（代码调研专家）｜日期：2026-10-09｜工作区：`J:\ninfer-kvmem`
> 性质：**只读调研**，未修改任何代码/模型文件。
> 结论摘要见 §0；每条结论都带 `[EVIDENCE] 相对路径:行号:原文摘录`。
> 路径约定：所有相对路径以 `J:\ninfer-kvmem` 为根；引擎源码树前缀记作 `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/`（下文简写 `…/fusion-engine-src/`）。

---

## §0 一句话结论（先看这个）

**路 B 完全可行，而且比预想的便宜得多：存在官方 Python 打包器 `tools/artifact/writer.py`（本地源码树里就有，已实测可 import），并且存在「体积零增长」的目标格式 —— `gguf_q4_k` 与 `gguf_iq4_nl` 与 `gguf_q4_0` 同为 4.5 bit/权重、每 32 元素 18 字节（iq4_nl）/每 256 元素 144 字节（q4_k），实测两者 Δbytes = 0。** 推荐的落地顺序：**先做 `gguf_iq4_nl`（块结构与 q4_0 逐字节同构、只需一张 16 项查找表 + 每 32 元素 absmax），其次 `gguf_q4_k`，最后才是 `bf16`（+582 MiB，需整包重写）**。

⚠️ **必须先纠正一个前提错误**：任务书里写的目标格式 `gguf_bf16` **在引擎里不存在**。引擎格式白名单里没有 `gguf_bf16`，也没有 `gguf_q4_0`。

- `[EVIDENCE] …/fusion-engine-src/src/artifact/formats.cpp:59:throw ArtifactError("unknown tensor format: " + std::string(name));`
- `[EVIDENCE] …/fusion-engine-src/docs/gguf.md:12-14:All fifteen block types llama.cpp writes for dense models: `Q8_0`, `Q2_K`, `Q3_K`, `Q4_K`, `Q5_K`,`Q6_K`, `IQ1_S`, `IQ1_M`, `IQ2_XXS`, `IQ2_XS`, `IQ2_S`, `IQ3_XXS`, `IQ3_S`, `IQ4_NL` and `IQ4_XS`,`
- 可接受的**确切拼写**只有：`bf16`（不带 `gguf_` 前缀）、`gguf_q4_k`、`gguf_iq4_nl`、`gguf_q8_0` 等（完整清单一字不差地贴在 §3.3）。

---

## §1 `.ninfer` 容器完整二进制格式（V3）

### 1.1 Header（32 字节，定长）

| 偏移 | 长度 | 含义 |
|---|---|---|
| 0..7 | 8 | entry magic `NINFER\x00\x03`（续卷是 `NINPRT\x00\x03`）；第 8 字节 `03` = 容器代际 |
| 8..15 | 8 | **目录 JSON 字节数** `json_bytes`，uint64 LE |
| 16..31 | 16 | **artifact id**（`uuid4().bytes`，**随机身份，不是内容哈希**） |

- `[EVIDENCE] …/fusion-engine-src/src/artifact/framing.h:9-19:inline constexpr std::array<std::byte, 8> kEntryMagic = {…'R', std::byte{0}, std::byte{3},};` / `inline constexpr std::size_t kHeaderBytes        = 32;` / `inline constexpr std::uint64_t kPayloadAlignment = 4096;` / `using ArtifactId = std::array<std::byte, 16>;`
- `[EVIDENCE] …/fusion-engine-src/tools/artifact/framing.py:5-8:MAGIC = b"NINFER\x00\x03"` / `PART_MAGIC = b"NINPRT\x00\x03"` / `HEADER = struct.Struct("<8sQ16s")` / `PAYLOAD_ALIGNMENT = 4096`
- artifact id 是随机的：`[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:141:self.artifact_id = uuid4().bytes`

### 1.2 目录 JSON 与 payload 对齐

- JSON 紧接 header 存放，长度 = `json_bytes`：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/reader.cpp:42-45:std::string text(static_cast<std::size_t>(json_bytes), '\0'); file->read_exact(kHeaderBytes, …); directory = parse_directory(parse_json(text, "artifact directory"), …);`
- **payload 起点 = align_up(32 + json_bytes, 4096)**：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/reader.cpp:46-47:entry_payload_start = align_up(checked_add(kHeaderBytes, json_bytes, "metadata end"), kPayloadAlignment, "entry payload start");`
- 目录 JSON **尾部用空格填充到对齐边界**（所以 JSON 内容小幅变化不必然改变 payload 起点）：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:43-46:reserve = (align_up(HEADER.size + len(encode_directory(value)), PAYLOAD_ALIGNMENT) - HEADER.size)`
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:83:return directory, encoded + b" " * (reserve - len(encoded)), entry_start`

### 1.3 artifact 表 / 文件段表（`files[]`）与 offset 语义

- 顶层目录 JSON 的必需成员：`components, objects, bindings, uses, files`（可选 `metadata, provenance`）：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:341:require_members(root, {"components", "objects", "bindings", "uses", "files"}, {"metadata", "provenance"}, "directory");`
- `files[0].path` 必须为 null，其后为 `.part-NNNN` 续卷；`payload_bytes` 为**该段承载的逻辑载荷字节数**：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:183-207:void parse_files(Directory& out, const Json& files, …)` / `:192:if (!value.at("path").is_null()) { throw ArtifactError("files[0].path must be null"); }` / `:201-204:file.payload_bytes = require_u64(value.at("payload_bytes"), …, true); file.logical_begin = out.payload_bytes;`
- **object 的 `offset` 是相对 payload 起点的逻辑偏移，不是文件绝对偏移**（这是历史上踩过的大坑）：
  `[EVIDENCE] refs/01-沈三殊-发放包/【必下1】文档与工具（人人要）/03-转换工具链.md:151:`objects[].offset` 是**相对 `payload_offset`** 的，不是文件绝对偏移 | 用 `payload_offset + offset` 取值`
- 续卷头：magic + **u64 = 段序号** + 16 字节 artifact id；续卷 payload 起点固定 4096：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/reader.cpp:70-79:if (!std::equal(kPartMagic.begin(), kPartMagic.end(), header.begin()) || read_u64_le(header.data() + 8) != index || !std::equal(id.begin(), id.end(), header.begin() + 16)) { throw …": continuation header does not belong to this entry"; }` / `:76-77:if (input->bytes() != checked_add(kPayloadAlignment, record.payload_bytes, "part length"))`

### 1.4 本次实测的本机模型容器读数（强证据）

用现成脚本 + 直接解析目录 JSON 得到（未改动文件）：

```
file bytes            13272798720   (12.361 GiB)
magic                 b'NINFER\x00' version=3
manifest_len(json)    249824 B
artifact_id           f2e0f91359304bd9a7f34234f11cb742
entry_payload_start   249856  (= align_up(32+249824, 4096)，正好 61*4096)
files                 [{'path': None, 'payload_bytes': 13272548864}]   单文件
payload_bytes         13272548864
objects               804 个（4 个 resource + 800 个 tensor）
bindings              979（text/ 963 + mtp/ 16）
uses                  619
components            mtp, text
metadata              {"name": "qwen3.8-27b-coder390-Q2LynnStyle-Mtp"}
provenance            {"converter":"ninfer-v3","recipe":"qwen3_8_27b_gguf", sources: base+gguf}
```

- `[EVIDENCE] …/fusion-engine-src/tools/peek_container.py:19-29:head = fh.read(32) … (mlen,) = struct.unpack("<Q", head[8:16]) … aid = head[16:32].hex()`（本机实跑输出见上）
- ⚠️ **更正既有文档的数字笔误**：`docs/交接-工作区迁移-TeleAgent-20261009.md:72` 写 `12,372,798,720 B`，实际为 **`13,272,798,720 B`**（同为 ≈12.36 GiB，`Get-ChildItem` 实测）。
  `[EVIDENCE] docs/交接-工作区迁移-TeleAgent-20261009.md:72:- 大小：**12,372,798,720 B**（≈12.36 GiB）…`（与实测 13,272,798,720 不符，数字位序笔误）

### 1.5 有没有 C++ `writer.cpp` / packer？

**没有。** 引擎的 C++ 侧只有 reader，写容器是 **Python 独占**：

- `src/artifact/` 目录清单里没有 writer：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/` 目录内容 = `binder, file_io, formats, framing, layouts, materializer, permute_row_split, reader, schema, transcode, views`（无 writer / packer / build_artifact）
- 在 `src/` 全文搜 `Writer|write_object|plan_objects` 命中的 15 个文件全在 `serve/`、`core/disk_kv_bridge.h`、`models/qwen3_5/program/**`，**没有一个在 `src/artifact/`**：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/formats.cpp`（唯一出现在 artifact 目录下的命中，是 `write` 子串误命中，非 artifact writer）
- 官方白皮书也把转换/打包归到 Python 工具：
  `[EVIDENCE] …/fusion-engine-src/docs/weight-conversion.md:3-6:NInfer's converter creates `.ninfer` artifacts from local weights and a Python recipe.`

---

## §2 现成的打包 / 重打包工具：**有，且在本地**

### 2.1 官方 Python 打包器（最关键的发现）

`tools/artifact/` 是一套完整的、只依赖标准库的 v3 读写 SDK：

```
…/fusion-engine-src/tools/artifact/
  __init__.py  file_io.py  formats.py  framing.py  inspect.py
  layouts.py   reader.py   schema.py   tensor_output.py  writer.py  codecs/
```

**已在本机实测成功 import**（Python 3.12.10）：

```
MAGIC b'NINFER\x00\x03' PART b'NINPRT\x00\x03' ALIGN 4096 HEADER <8sQ16s 32
ArtifactWriter OK <class 'tools.artifact.writer.ArtifactWriter'>
Artifact 方法: ['__enter__','__exit__','__init__','_file','close','iter_object','iter_range','object','read_object','read_range']
```

- `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:109-110:class ArtifactWriter:` / `"Own temporary files and publish the entry after every declared byte is written."`
- 用法要点：`ArtifactWriter(path, specs, components=, bindings=, uses=, metadata=, provenance=)`；逐对象 `write_object(id, chunks)`；`finish()` 强制校验全覆盖：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:255-257:for obj in self.objects: if self._coverage[obj.id].ranges != [(0, obj.bytes)]: raise ArtifactError(f"{obj.id}: output coverage is incomplete")`
- 落盘用临时文件 + 原子 `os.link`，失败 `abort()` 清理，源文件绝不会被覆盖：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:266-274:os.close(self._fds.pop()) … os.link(self._temporary[index], target) …`
- 单文件上限默认 32,000,000,000 B（我们 13.27 GB 远低于此，不会分片）：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:27:DEFAULT_MAX_FILE_BYTES = 32_000_000_000`

### 2.2 现成的「重打包」范例脚本（可直接照抄改造）

`official-repo/ninfer-fusion-kvmem/tools/strip_components.py` 就是**一个已经跑通过的、用 reader+writer 重打包 .ninfer 的完整例子**（它做「删组件」，我们要做「换格式」，骨架完全一样）：

- `[EVIDENCE] official-repo/ninfer-fusion-kvmem/tools/strip_components.py:7-13:How (no re-implementation of the container): … * hand the surviving specs to the upstream ArtifactWriter, which recomputes the aligned object layout, writes the header + directory, and refuses to publish unless every declared object got its full coverage,`
- `[EVIDENCE] official-repo/ninfer-fusion-kvmem/tools/strip_components.py:175-189:writer = ArtifactWriter(args.dst, specs, components=kept_components, bindings=kept_bindings, uses=kept_uses, metadata=d.metadata, provenance=provenance,) … writer.write_object(obj.id, art.iter_object(obj.id)) … directory = writer.finish()`
- `[EVIDENCE] official-repo/ninfer-fusion-kvmem/tools/strip_components.py:200-203:check = Artifact(args.dst)  # re-open: validates header, length, directory, layout`

⚠️ **但该脚本本机直接跑不起来**：它硬编码了上游仓库绝对路径。
- `[EVIDENCE] official-repo/ninfer-fusion-kvmem/tools/strip_components.py:25:UPSTREAM = r"E:\infer-build\refs\infer-all-full\ninfer-all-master"`
- 实测 `Test-Path 'E:\infer-build'` → **False**（E: 存在但该目录不存在）。
- **处置**：把 `UPSTREAM` 换成 `J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` 即可（上面已验证该树里 `tools.artifact` 可 import）。

### 2.3 参考文档里提到的转换/打包工具链

| 工具 | 能力 | 证据 |
|---|---|---|
| `python3 -m tools.convert --recipe …` | 从 safetensors / GGUF 源**从头转换** | `[EVIDENCE] refs/…/03-转换工具链.md:58-66:python3 -m tools.convert \ --model … --recipe qwen3_6_27b …` |
| `tools/upgrade_ninfer_v2_to_v3.py` | 容器代际升级（v2→v3） | `[EVIDENCE] refs/…/03-转换工具链.md:105:python3 tools/upgrade_ninfer_v2_to_v3.py <v2.ninfer> <v3输出.ninfer>` |
| `python3 -m tools.artifact.inspect` | L0 结构校验（**重打包后必跑**） | `[EVIDENCE] …/fusion-engine-src/docs/weight-conversion.md:605:python3 -m tools.artifact.inspect models/my_qwen.ninfer --objects --bindings` |
| 三元线 `pack.py` | GGUF→ninfer（**只认三元私有 type**） | `[EVIDENCE] refs/…/03-转换工具链.md:92-93:python <三元线>\tools\pack.py check --gguf … / … build <新名>.ninfer …` |

**有没有 python/脚本能写 `.ninfer`？→ 有，就是 `tools/artifact/writer.py`（已在本地，实测可用）。**

### 2.4 上游对「GGUF 反量化再进 ninfer」的态度（重要反例，需正面回应）

- `[EVIDENCE] refs/…/03-转换工具链.md:199:4. **"langchain 式"第三方反量化再进 ninfer**（llama.cpp GGUF → safetensors → .ninfer）：**未证实**，且反量化会引入重量化损失，**不建议作为路径**。`
- `[EVIDENCE] refs/…/09-转换判别与推荐名单.md:44:| **"先把 GGUF 反量化回 safetensors 再转"** | ⚠️ **未证实且不推荐** | —— | 会引入重量化损失，且未实测 |`
- `[EVIDENCE] refs/…/09-转换判别与推荐名单.md:78:| "先反量化 GGUF 再转" | **未证实**，且引入损失；走这条路不如直接用 llama.cpp |`
- `[EVIDENCE] refs/…/10-兜底方案（最后手段）.md:30:| 手上只有普通 GGUF 且必须用 ninfer | 引擎无 GGUF 读取器 | 只有一条例外：**三元 GGUF** 可经魔搭的 `pack.py` 打包…；其余请用 llama.cpp |`

**反驳/边界（质疑精神）**：这些条目针对的是「**整模型**从普通 GGUF 反量化再重量化」——那确实会全盘掉精度。而**本路的差别是**：(a) 只动 5 个张量、占全模型 **1.8%**（238.9 MB / 13.27 GB）；(b) 有 **iq4_nl / q4_k 这类「同码率、零体积变化」的目标格式**，不是「反量化到 fp16 再重量化到更低比特」；(c) 而且这 5 个张量是 **MTP 草稿头**（只影响 draft 命中率，**不影响主模型输出分布**——投机解码是「验证后丢弃」的，接受/拒绝由主模型裁决）。因此上游这句「不推荐」**不构成对路 B 的否决**，但需要按 §6 的验收判据做数值与端到端验证。

---

## §3 张量格式字段在哪里决定？改格式要同步改什么？

### 3.1 format 写在 **JSON 目录**里，不在二进制头里

- tensor 对象的必需字段（**白名单式，多一个字段都报错**）：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:219-221:require_members(value, {"id", "kind", "shape", "format", "layout", "offset", "bytes"}, {"divisors"}, "tensor");`
- `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:241-243:out.objects.emplace_back(TensorObject{ id, parse_shape(value.at("shape"), id), require_id(value.at("format"), id), require_id(value.at("layout"), id), offset, bytes, divisors});`
- Python 侧同构：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/schema.py:209-210:if kind == "tensor": members(value, common | {"shape", "format", "layout"}, {"divisors"}, "tensor")`
- 所以：**`format` 就是 JSON 里的一个字符串；二进制头里没有任何格式信息。**

### 3.2 改格式必须同步改哪些字段

顺序依赖链：`format` → `bytes`（由 layout 几何算出）→ `offset`（前一个对象末尾向上对齐 256）→ `files[].payload_bytes`（= 最后一个对象 end）→ 文件长度 → 若 `json_bytes` 变化则 `payload 起点`可能整体平移。

1) **`bytes` 必须等于 `encoded_size(layout, format, shape, divisors)`**：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/layouts.cpp:12-14:if (geometry.bytes != object.bytes || object.offset % geometry.alignment) { throw ArtifactError("encoded size or object alignment differs from layout"); }`
   `[EVIDENCE] …/fusion-engine-src/tools/artifact/schema.py:163-167:if obj.bytes != size or obj.offset % alignment: raise ArtifactError(f"{obj.id}: expected {size} encoded bytes and {alignment}-byte alignment, got bytes={obj.bytes}, offset={obj.offset}")`

2) **`offset` 必须 256 字节对齐**（不是 4096；4096 只约束 payload 起点）：
   `[EVIDENCE] …/fusion-engine-src/src/core/weight_view.h:39:std::uint64_t alignment           = 256;`（WeightGeometry 默认，weight_geometry 全程未改写）
   `[EVIDENCE] …/fusion-engine-src/tools/artifact/layouts.py:28:PLANE_ALIGNMENT = 256`（且 5 个 Layout 的 alignment 全是 256，见 `:92` `:95` `:102` `:107` `:111`）
   实测本机 5 个 q4_0 的 offset 全部 256/4096 对齐（4220248576 = 4096×1030334，余同）。

3) **`offset` 必须严格递增、不重叠、不越界**：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:231-233:if (offset < previous_end || end > out.payload_bytes) { throw ArtifactError(id + ": object overlaps, is out of order or exceeds payload"); }`

4) **`divisors`**：非 NVFP4 只能是 1（我们这 5 个都不是 NVFP4，写 1 或省略）：
   `[EVIDENCE] …/fusion-engine-src/src/core/weight_view.cpp:81-82:if (divisors == 0 || (divisors != 1 && format != QType::NVFP4)) { throw std::invalid_argument("only an NVFP4 plane carries more than one divisor"); }`

5) **`shape`**：保持不动。gguf 块格式要求 `K % block_elements == 0`：
   `[EVIDENCE] …/fusion-engine-src/src/core/weight_view.cpp:123-125:if (!is_gguf(format) || k % std::uint64_t(block.elements)) { throw std::invalid_argument("GgufBlocks requires a ggml block format over whole blocks"); }`
   本机 5 个张量的 K = 5120 / 10240 / 6144 / 17408，**全部被 32、256、512 整除** ⇒ iq4_nl(32) / q4_k(256) / q8_0(32) 都合法。

6) **`bindings` 的 `parts.range` 不用改**（range 是父对象的**逻辑元素下标**，与存储格式无关；但父对象元素总数不能变）：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:174-175:if (begin >= end || end > weight_element_count(directory.tensor(handle).shape)) { throw ArtifactError(label + ": Part exceeds source logical elements"); }`
   `[EVIDENCE] …/fusion-engine-src/src/artifact/transcode.h:17-18:Logical element addressing (row * columns + column) is the same before and after, so bindings over parts of a transcoded object stay valid.`

7) **引擎 Op 侧的额外几何约束**（GGUF 矩阵乘路径要求 K 是 512 的倍数）：
   `[EVIDENCE] …/fusion-engine-src/src/ops/linear/gguf/gguf_linear.cpp:112:… || w.k % block.elements != 0 || w.k % 512 != 0) {`
   本机 K ∈ {5120, 10240, 6144, 17408} ⇒ 全部 %512==0 ✅

### 3.3 `formats.cpp` 合法格式名清单（**一字不差的原文**）

`[EVIDENCE] …/fusion-engine-src/src/artifact/formats.cpp:10-37:`

```cpp
constexpr std::array kFormats = {
    std::pair{QType::BF16, std::string_view{"bf16"}},
    std::pair{QType::FP32, std::string_view{"fp32"}},
    std::pair{QType::INT32, std::string_view{"int32"}},
    std::pair{QType::Q4_G64_FP16, std::string_view{"q4_g64_fp16"}},
    std::pair{QType::Q5_G64_FP16, std::string_view{"q5_g64_fp16"}},
    std::pair{QType::Q6_G64_FP16, std::string_view{"q6_g64_fp16"}},
    std::pair{QType::Q8_G32_FP16, std::string_view{"q8_g32_fp16"}},
    std::pair{QType::T2_G128_FP16, std::string_view{"t2_g128_fp16"}},
    std::pair{QType::PTQ1_G128_FP16, std::string_view{"ptq1_g128_fp16"}},
    std::pair{QType::NVFP4, std::string_view{"nvfp4"}},
    std::pair{QType::FP8_E4M3FN_ROW_BF16, std::string_view{"fp8_e4m3fn_row_bf16"}},
    std::pair{QType::GGUF_Q8_0, std::string_view{"gguf_q8_0"}},
    std::pair{QType::GGUF_Q2_K, std::string_view{"gguf_q2_k"}},
    std::pair{QType::GGUF_Q3_K, std::string_view{"gguf_q3_k"}},
    std::pair{QType::GGUF_Q4_K, std::string_view{"gguf_q4_k"}},
    std::pair{QType::GGUF_Q5_K, std::string_view{"gguf_q5_k"}},
    std::pair{QType::GGUF_Q6_K, std::string_view{"gguf_q6_k"}},
    std::pair{QType::GGUF_IQ2_XXS, std::string_view{"gguf_iq2_xxs"}},
    std::pair{QType::GGUF_IQ2_XS, std::string_view{"gguf_iq2_xs"}},
    std::pair{QType::GGUF_IQ2_S, std::string_view{"gguf_iq2_s"}},
    std::pair{QType::GGUF_IQ3_XXS, std::string_view{"gguf_iq3_xxs"}},
    std::pair{QType::GGUF_IQ3_S, std::string_view{"gguf_iq3_s"}},
    std::pair{QType::GGUF_IQ1_S, std::string_view{"gguf_iq1_s"}},
    std::pair{QType::GGUF_IQ1_M, std::string_view{"gguf_iq1_m"}},
    std::pair{QType::GGUF_IQ4_NL, std::string_view{"gguf_iq4_nl"}},
    std::pair{QType::GGUF_IQ4_XS, std::string_view{"gguf_iq4_xs"}},
};
```

合法 layout 名（`[EVIDENCE] …/fusion-engine-src/src/artifact/formats.cpp:38-44`）：
`contiguous_le_v1`、`row_split_k128_v1`、`row_scale_v1`、`block_scale_k16_m128x4_v1`、`gguf_blocks_v1`。
（另有 `row_split_panel4_v1` 只存在于设备侧，容器**不得声明**：`[EVIDENCE] formats.cpp:46-51:a `.ninfer` claiming one would be describing bytes the writer could not have produced.`）

**结论：`gguf_bf16` 不存在；`gguf_q4_0` 不存在。可用目标是 `bf16` + `contiguous_le_v1`，或 `gguf_q4_k` / `gguf_iq4_nl` / `gguf_q8_0` + `gguf_blocks_v1`。**

Python 侧注册完全一致（供交叉验证）：
`[EVIDENCE] …/fusion-engine-src/tools/artifact/formats.py:96:GGUF_IQ4_NL = GgufFormat("gguf_iq4_nl", 20, 32, 18)`
`[EVIDENCE] …/fusion-engine-src/tools/artifact/formats.py:89:GGUF_Q4_K = GgufFormat("gguf_q4_k", 12, 256, 144)`
`[EVIDENCE] …/fusion-engine-src/tools/artifact/formats.py:101:GGUF_Q8_0 = GgufFormat("gguf_q8_0", 8, 32, 34)`
`[EVIDENCE] …/fusion-engine-src/tools/artifact/formats.py:65:BF16 = DirectFormat("bf16", 2)`

### 3.4 本机 5 个 `gguf_q4_0` 张量的真实字段（实测）

```
{"id": "weight/000079", "shape": [14336, 5120], "format": "gguf_q4_0", "layout": "gguf_blocks_v1", "offset":  4220248576, "bytes":  41287680, "kind": "tensor"}
{"id": "weight/000080", "shape": [34816, 5120], "format": "gguf_q4_0", "layout": "gguf_blocks_v1", "offset":  4261536256, "bytes": 100270080, "kind": "tensor"}
{"id": "weight/000789", "shape": [ 5120,10240], "format": "gguf_q4_0", "layout": "gguf_blocks_v1", "offset": 13175151104, "bytes":  29491200, "kind": "tensor"}
{"id": "weight/000796", "shape": [ 5120, 6144], "format": "gguf_q4_0", "layout": "gguf_blocks_v1", "offset": 13204684288, "bytes":  17694720, "kind": "tensor"}
{"id": "weight/000798", "shape": [ 5120,17408], "format": "gguf_q4_0", "layout": "gguf_blocks_v1", "offset": 13222389248, "bytes":  50135040, "kind": "tensor"}
```

它们**全部属于 mtp 组件**（text 的 787 个引用里不含 000079/000080，实测 `text refs 000079? False  000080? False`，`n text ids 787`）：

- `[EVIDENCE] 容器 bindings（实测）：mtp/input_projection {"object": "weight/000789"}`
- `[EVIDENCE] 容器 bindings（实测）：mtp/layers/0/attention/query {"parts": [{"object": "weight/000079", "range": [0, 31457280]}]}`（key/gate/value 另三段，合起来正好覆盖 0..73400320 = 14336×5120，即整个父张量）
- `[EVIDENCE] 容器 bindings（实测）：mtp/layers/0/mlp/gate {"parts": [{"object": "weight/000080", "range": [0, 89128960]}]}`（up 段 [89128960, 178257920]，合起来覆盖整个父张量）
- `[EVIDENCE] 容器 bindings（实测）：mtp/layers/0/attention/output {"object": "weight/000796"}`、`mtp/layers/0/mlp/down {"object": "weight/000798"}`
- `[EVIDENCE] 容器 components（实测）：{"config": {"architectures": ["Qwen3_5MTP"]}, "target": "text"}`

**交叉验证（关键）**：5 个张量的 `bytes` 都精确等于 `prod(shape)/32*18`，与 ggml `block_q4_0` 定义完全吻合 ⇒ 容器里存的就是**裸 ggml q4_0 块、行主序、无 padding、scale 在块首**：
73,400,320/32×18 = 41,287,680 ✅；178,257,920/32×18 = 100,270,080 ✅；52,428,800/32×18 = 29,491,200 ✅；31,457,280/32×18 = 17,694,720 ✅；89,128,960/32×18 = 50,135,040 ✅（5/5 全中）

---

## §4 q4_0 的块结构、现有反量化实现、工作量估算

### 4.1 q4_0 块结构的确切定义（引擎内第三方 ggml 代码）

`[EVIDENCE] …/fusion-engine-src/third_party/ggml-quants/src/ggml-common.h:194-199:`

```c
#define QK4_0 32
typedef struct {
    ggml_half d;           // delta
    uint8_t qs[QK4_0 / 2]; // nibbles / quants
} block_q4_0;
static_assert(sizeof(block_q4_0) == sizeof(ggml_half) + QK4_0 / 2, "wrong q4_0 block size/padding");
```

⇒ **block_size = 32 元素 / 18 字节；scale `d` 是 fp16，位于块首 2 字节；随后 16 字节 = 32 个 4-bit 码。**

反量化公式（低 nibble 在前，减 8 居中）：
`[EVIDENCE] …/fusion-engine-src/third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:46-58:`

```c
static __device__ __forceinline__ void dequantize_q4_0(const void * vx, const int64_t ib, const int iqs, float2 & v){
    const block_q4_0 * x = (const block_q4_0 *) vx;
    const float d = x[ib].d;
    const int vui = x[ib].qs[iqs];
    v.x = vui & 0xF;
    v.y = vui >> 4;
    v.x = (v.x - 8.0f) * d;
    v.y = (v.y - 8.0f) * d;
}
```

⇒ **value = (nibble − 8) × fp16(d)**，nibble 顺序：字节 `qs[i]` 的低 4 位 = 元素 2i，高 4 位 = 元素 2i+1。

### 4.2 「同构」的目标格式：`gguf_iq4_nl`（块结构与 q4_0 逐字节相同）

`[EVIDENCE] …/fusion-engine-src/third_party/ggml-quants/src/ggml-common.h:447-452:`

```c
#define QK4_NL 32
typedef struct {
    ggml_half d;
    uint8_t qs[QK4_NL/2];
} block_iq4_nl;
static_assert(sizeof(block_iq4_nl) == sizeof(ggml_half) + QK4_NL/2, "wrong iq4_nl block size/padding");
```

码表（16 项非线性表）：
`[EVIDENCE] …/fusion-engine-src/third_party/ggml-quants/src/ggml-common.h:1119-1122:`

```c
// TODO: fix name to kvalues_iq4_nl
GGML_TABLE_BEGIN(int8_t, kvalues_iq4nl, 16)
    -127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113,
GGML_TABLE_END()
```

引擎桥确认块形参与内核可用性：
`[EVIDENCE] …/fusion-engine-src/src/ops/linear/gguf/ggml_bridge.cu:302:case GgmlType::IQ4_NL: return {32, 18};`
`[EVIDENCE] …/fusion-engine-src/src/ops/linear/gguf/ggml_bridge.cu:311:bool has_matrix_kernel(GgmlType type) { return type != GgmlType::IQ1_M; }`（⇒ IQ4_NL 有矩阵核）

⇒ **q4_0 → iq4_nl = 「dequant 到 float，然后每 32 元素取 absmax/127 作新 d（fp16），每个值查 16 项表取最近索引」。块字节数、块数、行字节数全部不变，payload 长度一字不差。**

### 4.3 仓库里有没有现成的反量化函数可复用？

| 位置 | 能否复用 | 证据 |
|---|---|---|
| `tools/convert/gguf_blocks.py::_dequantize` | **能，但需 `gguf` 包 + torch** | `[EVIDENCE] …/fusion-engine-src/tools/convert/gguf_blocks.py:173-187:def _dequantize(gguf, tensor, first, last): try: from gguf import GGMLQuantizationType; from gguf.quants import dequantize … values = dequantize(np.ascontiguousarray(blocks), kind)` |
| `tools/convert/sources/gguf_source.py` | 同上，依赖 `gguf` 包 | `[EVIDENCE] …/fusion-engine-src/docs/weight-conversion.md:409-412:`tools/convert/sources/gguf_source.py` reads the GGUF file (via the `gguf` package --`pip install gguf`; it performs the actual block dequantization …` |
| 引擎侧 gguf 反量化 | **不能**：`GgmlType` 枚举里**没有 Q4_0** | `[EVIDENCE] …/fusion-engine-src/src/ops/linear/gguf/ggml_bridge.h:16-32:enum class GgmlType : int { Q8_0 = 8, Q2_K = 10, Q3_K = 11, Q4_K = 12, Q5_K = 13, Q6_K = 14, IQ2_XXS = 16, IQ2_XS = 17, IQ3_XXS = 18, IQ1_S = 19, IQ4_NL = 20, IQ3_S = 21, IQ2_S = 22, IQ4_XS = 23, IQ1_M = 29, };`（**无 Q4_0 = 2**） |
| 引擎侧 q4_0 CUDA 反量化 | 有，但只在 `dequantize.cuh`，是 `__device__` CUDA 代码，离线用不了 | `[EVIDENCE] …/third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:46:static __device__ __forceinline__ void dequantize_q4_0(...)` |
| 加载时转码（transcode） | **不能**：只支持 q8_g32_fp16 → q4/q6 g64 | `[EVIDENCE] …/fusion-engine-src/src/artifact/transcode.h:16-18:The only supported source is Q8_G32_FP16 in the row-split layout; targets are Q4_G64_FP16 and Q6_G64_FP16 in the same layout.` |

**本机 Python 环境实测**：`numpy` ✅ 已装；`torch` ❌ 未装；`gguf` ❌ 未装。
⇒ **最省事的实现路径 = 纯 numpy 手写 q4_0 解码（约 20 行）+ 目标格式编码**，无需装任何包。

### 4.4 数据量与实现难度

| 目标格式 | 每权重比特 | 5 个张量新字节数 | 相比 q4_0 增量 | 实现难度 | 引擎支持 |
|---|---|---|---|---|---|
| **当前 `gguf_q4_0`** | 4.5 | 238,878,720（227.8 MiB） | — | — | ❌ 不支持 |
| **`gguf_iq4_nl`** | 4.5 | 238,878,720 | **0 B** | **低**：16 项查表 + 每 32 absmax | ✅ `formats.cpp:35` |
| **`gguf_q4_k`** | 4.5 | 238,878,720 | **0 B** | **中高**：256 元素超块、8×6bit scale/min 打包、nibble 高低位分区 | ✅ `formats.cpp:25` |
| `gguf_q8_0` | 8.5 | 451,215,360 | **+212,336,640 B（+202.5 MiB / 0.198 GiB）** | 低（每 32 absmax + 8bit 码） | ✅ `formats.cpp:22` |
| **`bf16`** | 16 | 849,346,560 | **+610,467,840 B（+582.1 MiB / 0.569 GiB）** | 最低（fp32→bf16 截断） | ✅ `formats.cpp:11` |

（上表字节数由 `tools/artifact/layouts.py::encoded_size` 对本机 5 个 shape 实算得出：
`[EVIDENCE] …/fusion-engine-src/tools/artifact/layouts.py:348-351:if layout_spec is GGUF_BLOCKS_V1: … return gguf_blocks_geometry(numeric_spec, shape).payload_bytes`
`[EVIDENCE] …/fusion-engine-src/tools/artifact/layouts.py:329-335:if layout_spec is CONTIGUOUS_LE_V1: … return prod(dims) * numeric_spec.word_bytes`）

参数量：5 个张量合计 **424,673,280 个权重**（4.25 亿），占全模型 payload 的 **1.80%**（238,878,720 / 13,272,548,864）。
⇒ 纯 numpy 按 32 元素块向量化处理（np.frombuffer → uint8 → 拆 nibble → 查表），**秒级到十秒级**即可完成，内存占用可控（单张量最大 100 MB，可分块）。

---

## §5 重打包的风险点

### 5.1 体积变化（已量化，见 §4.4）

- 选 `gguf_iq4_nl` / `gguf_q4_k`：**Δ = 0**，文件仍 13,272,798,720 B。
- 选 `bf16`：文件 ≈ 13,883,266,560 B（+0.569 GiB），仍 **< 32,000,000,000 B 单文件上限**，不会触发分片：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:27:DEFAULT_MAX_FILE_BYTES = 32_000_000_000`

### 5.2 ⚠️ 最大的隐藏风险：**JSON 长度变化会平移整个 payload**

本机 `json_bytes = 249,824`，`32 + 249,824 = 249,856 = 61 × 4096`，**正好卡在对齐边界上**（没有余量）。

- 改格式名 `gguf_q4_0`(9 字符) → `gguf_iq4_nl`(10 字符)：JSON **+5 字节** ⇒ `align_up(32 + 249,829, 4096) = 253,952` ⇒ **payload 起点从 249,856 移到 253,952（+4,096）** ⇒ **全部 804 个对象的 offset 都要 +4096，整包 13.27 GB 必须重写**（不能再做「原地打 5 个补丁」）。
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:84:reserve = align_up(HEADER.size + len(encoded), PAYLOAD_ALIGNMENT) - HEADER.size`
- 改格式名 → `gguf_q4_k`(9 字符)：JSON **长度不变** ⇒ payload 起点不变 ⇒ **对象 offset 全部不变**，理论上可「原地覆写 5 段 payload + 改 5 个字符串」。
- 或者用 `gguf_iq4_nl` 时**在别处省掉 ≥5 个 JSON 字节**（例如裁剪 `provenance.sources.*.path`，那是自由文本，引擎只要求是 object）：
  `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:354-358:if (root.contains("metadata")) { out.metadata = root.at("metadata"); } … if (!out.metadata.is_object() || !out.provenance.is_object()) { throw ArtifactError("metadata and provenance must be objects"); }`
- **推荐做法**：直接用 `ArtifactWriter` 全量重排（它会自动重算 offset/对齐/payload/files，并做全覆盖校验），**不要手算 offset**。这是最稳的，代价只是一次 13 GB 级顺序拷贝。

### 5.3 对齐 / padding 是否要重算？

- 对象对齐 **256**（不是 4096）由 `plan_objects` 自动处理：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/schema.py:182:start = align_up(offset, get_layout(spec.layout).alignment)`
- payload 起点 4096 对齐、目录 JSON 尾部空格填充，由 `layout_directory` 自动处理：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:47-84:while True: entry_start = integer(HEADER.size + reserve, …) … if len(encoded) <= reserve: … return directory, encoded + b" " * (reserve - len(encoded)), entry_start`
- ⇒ **用 writer 就不需要手算任何对齐**；只有「原地打补丁」方案才需要自己保证。

### 5.4 有没有 magic 之外的隐式校验？

**有，以下几处（都不是哈希，但都会拒载）：**

1. 入口文件长度必须等于 `payload 起点 + files[0].payload_bytes`：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/reader.cpp:48-52:const auto expected = checked_add(entry_payload_start, directory.files[0].payload_bytes, "entry length"); if (expected != file->bytes()) { throw ArtifactError(entry.string() + ": entry length differs from directory"); }`
2. 每个张量 `bytes` 必须等于几何算出的值、`offset` 必须 256 对齐（§3.2）。
3. 对象必须递增不重叠、不越界（§3.2）。
4. 续卷（若有）的 magic + 序号 + artifact id 三重校验（§1.3）。
5. 目录 JSON 不允许重复成员、不允许非有限数：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:103-104:if (!member_stack.back().insert(key).second) { throw ArtifactError(std::string(label) + ": duplicate JSON member " + key); }`
6. `components` 必须含 `text`：`[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:252-254:if (!values.is_object() || !values.contains("text")) { throw ArtifactError("components must contain text"); }`
7. `uses` 的 `parameter` 必须能在 `bindings` 里找到：
   `[EVIDENCE] …/fusion-engine-src/src/artifact/schema.cpp:306-308:if (!out.bindings.contains(use.parameter)) { throw ArtifactError(label + ": missing parameter"); }`
8. **没有内容哈希/校验和**：`reader.cpp` 全文只有 magic、`json_bytes` 上界、文件长度、几何一致性检查；`artifact_id` 是 `uuid4().bytes`：
   `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:141:self.artifact_id = uuid4().bytes`
   ⇒ **印证了既有判断「数据侧重打包安全」**（`docs/协作-给CodeBuddy-20261009.md:50`）。

### 5.5 `text` 组件 787 个权重要不要动？

**不要动，也不需要重编码。** 只改 5 个 mtp 张量，其余 795 个 tensor + 4 个 resource 原样拷贝字节：

- `binding` 前缀统计实测：`text/` 963 条、`mtp/` 16 条；text 引用到的对象恰好 787 个，且不含 000079/000080/000789/000796/000798。
- `[EVIDENCE] …/fusion-engine-src/tools/artifact/writer.py:241-247:def write_object(self, object_id, chunks): … for chunk in chunks: self.write_region(object_id, offset, chunk)`——逐对象流式写入，天然支持「大部分原样搬运」。
- ⚠️ **实现陷阱**：不要对 q4_0 对象调 `Artifact.iter_object()` / `.object()`，因为 Python reader 会做 `validate_encoding`，而 `gguf_q4_0` 不在注册表里会直接抛错：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/reader.py:165-167:if object_id not in self._validated: validate_encoding(obj);`
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/schema.py:157-161:size = encoded_size(obj.layout, obj.format, obj.shape, obj.divisors) … raise ArtifactError(f"{obj.id}: {error}")`
  ⇒ 读这 5 个对象要用 `art.iter_range(obj.offset, obj.bytes)`（绕过校验）：
  `[EVIDENCE] …/fusion-engine-src/tools/artifact/reader.py:128-130:def iter_range(self, offset: int, length: int, *, chunk_bytes: int = READ_CHUNK_BYTES)`
  （注意：这正好也是 `strip_components.py:187` 的一个坑——它对 kept 对象统一调 `iter_object`，照抄时必须改成 `iter_range`。）

### 5.6 其它风险

- **MTP 是草稿头，精度损失不影响主模型输出分布**（投机解码由主模型验证/拒绝），但会**降低接受率** ⇒ 必须用 `--spec mtp` 实测 `acceptance rate` / `tok/round` 与基线对比。
  `[EVIDENCE] …/fusion-engine-src/apps/cli/main.cpp:245-248:print_metric(backend + " drafted tokens", …); print_metric(backend + " accepted tokens", …);`
- **重打包后必须重跑 L0 结构校验**：`python3 -m tools.artifact.inspect <out>.ninfer --objects --bindings`
  `[EVIDENCE] …/fusion-engine-src/docs/weight-conversion.md:605:python3 -m tools.artifact.inspect models/my_qwen.ninfer --objects --bindings`
- 上游明确警告「文件合法 ≠ 引擎能跑该 Op 组合」：
  `[EVIDENCE] refs/…/03-转换工具链.md:162:| 12 | 装载失败 `artifact object was not consumed by the selected target` | Binder 要求**每个对象都被消费**…`
  `[EVIDENCE] refs/…/09-转换判别与推荐名单.md:115:3. **"自写 recipe 能覆盖到什么程度"**：…**但不能替你补上引擎没实现的内核**——"文件合法 ≠ 引擎能跑这个组合"。`
  ⇒ 我们保留全部对象与绑定，理论上不会被「未消费」拒载，但仍需 `--spec mtp` 冒烟。
- **磁盘**：产物需另开 ~13.3 GB（iq4_nl/q4_k）或 ~13.9 GB（bf16）；`models/` 是 >1G 受保护资产，**禁止覆盖/删除原件**（T-PROTECT-ASSET，`docs/协作-给CodeBuddy-20261009.md:61`）。

---

## §6 有没有第三条更省事的路？

### 6.1 引擎启动时忽略/跳过 mtp 组件？—— **没有专门的开关**

- 投机后端只有这一个总开关：
  `[EVIDENCE] …/fusion-engine-src/src/serve/serve_options.cpp:260:"  --spec mtp|dflash|dflash2     speculative decoding backend\n"`
- MTP 相关只有两个**与 q4_0 无关**的开关：
  `[EVIDENCE] …/fusion-engine-src/src/serve/serve_options.cpp:138-139:"  --mtp-experts-q4              Qwen3.6-35B-A3B: store the MTP layer's routed\n" "                                experts in the text layers' formats\n"`（MoE 专用，我们是 dense，不适用）
  `[EVIDENCE] …/fusion-engine-src/src/serve/serve_options.cpp:266-268:"  --mtp-attention-window N      the MTP draft head attends to its first 64 keys\n" …`（只改注意力窗口，不解决格式）
- 没有任何 `--transcode` / 环境变量级别的容器转码开关（在 `serve_options.cpp` 全文搜 `transcode` → **0 命中**）。
- 加载时转码机制存在但**不支持 q4_0**：`[EVIDENCE] …/fusion-engine-src/src/artifact/transcode.h:16-18`（见 §4.3）。
- **结论：不存在「不重编、不重打包」的第三路。** 唯一「跳过」就是**不加 `--spec mtp`**——这正是当前裸解码能跑通的原因。

### 6.2 为什么裸解码不受影响（可用于判断改动面）

张量格式校验是**惰性**的，只在对象被物化时才做：
- `[EVIDENCE] …/fusion-engine-src/src/artifact/reader.cpp:113-119:void Reader::validate_object(ObjectHandle handle) const { … (void)geometry(handle); … }`
- `[EVIDENCE] …/fusion-engine-src/src/artifact/materializer.cpp:236:reader.validate_object(placement.object);`
- `[EVIDENCE] …/fusion-engine-src/src/artifact/binder.cpp:143:reader_.validate_object(object);`

⇒ 只有 `--spec mtp` 才会去物化 MTP 的 5 个 q4_0 并在 `formats.cpp:59` 抛出 `unknown tensor format: gguf_q4_0`：
`[EVIDENCE] …/fusion-engine-src/src/artifact/formats.cpp:55-60:QType parse_format(std::string_view name) { for (const auto& [format, spelling] : kFormats) { if (spelling == name) { return format; } } throw ArtifactError("unknown tensor format: " + std::string(name)); }`
`[EVIDENCE] docs/协作-给CodeBuddy-20261009.md:42:| MTP 投机 | ❌ | `weight/000789: unknown tensor format: gguf_q4_0`…`

### 6.3 另一条（比路 B 更"正统"但需要外部资源）的路：路 C

- 上游作者用支持格式重导 MTP 头。本机容器的 `provenance` 记录了**源 GGUF 路径**，但那是生产机上的绝对路径，本地没有：
  `[EVIDENCE] 容器 provenance（实测）：{"converter": "ninfer-v3", "recipe": "qwen3_8_27b_gguf", "sources": {"base": {"path": "/opt/coder390/Qwen3.8-27B-Coder390-EfficientThink/model"}, "gguf": {"path": "/opt/coder390/Q2LynnStyle/Qwen3.8-27B-Coder390-Q2LynnStyle-MTP.gguf"}}}`
- 有趣/可疑的一点：**当前源码树的 `qwen3_8_27b_gguf` recipe 会拒绝含 q4_0 的 GGUF**，但本机这个制品却带 q4_0：
  `[EVIDENCE] …/fusion-engine-src/tools/convert/gguf_blocks.py:158-163:stored = info.type_id in GGUF_FORMATS_BY_TYPE; if info.shape != shape or (kind == "blocks") != stored or … raise ValueError(f"{gguf.path}: {name} is {info.type_name} {info.shape}")`
  ⇒ 说明**产出本制品的那套转换器的格式注册表当时包含 Q4_0（type id 2），当前树已移除**。若能从上游拿到那份源 GGUF/转换器，路 C 可能零损失；否则只能走路 B。

---

## §7 建议的落地步骤（供主对话决策，本调研不改任何文件）

1. **（推荐主选）`gguf_q4_0` → `gguf_iq4_nl`**，用本地 `tools/artifact/{reader,writer}.py` 全量重排：
   - 纯 numpy：`value = (nibble − 8) * fp16(d)` → 每 32 元素 `d' = max|v| / 127`（fp16）→ 码 = 距 `v/d'` 最近的 `kvalues_iq4nl` 索引（表见 `ggml-common.h:1121`）。
   - Δbytes = 0，shape/offset 不变；仅 JSON 里 5 个 `format` 字符串变化（+5 字节 → 会让 payload 起点 +4096，交给 writer 自动处理）。
2. **（零位移变体）若想「原地打补丁」**：改用 `gguf_q4_k`（9 字符，JSON 长度不变），但需实现 Q4_K 超块量化（难度中高）。
3. **（最省实现、接受膨胀）`bf16` + `contiguous_le_v1`**：+582 MiB，实现最简单，可先做**探针**验证「MTP 能起来、能拿到读数」，再回头做 iq4_nl 的精修版。
4. **验收**（照抄上游分级判据）：
   - L0：`python3 -m tools.artifact.inspect <out>.ninfer --objects --bindings` 无异常；
   - L4：引擎 `--spec mtp` 装得上、单条 prompt smoke 正常；
   - L5/端到端：对比 `--spec mtp` 的 `drafted/accepted tokens` 与 `tok/round`，并与裸解码 tok/s 做 A/B；
   - L9 负控：故意写错 `bytes`/错格式名，确认被拒（`refs/…/03-转换工具链.md:181-182` L8/L9）。
5. **纪律**：产物落正式目录（如 `models\`），**不覆盖原件**（T-PROTECT-ASSET）；报告落 `docs\`。
