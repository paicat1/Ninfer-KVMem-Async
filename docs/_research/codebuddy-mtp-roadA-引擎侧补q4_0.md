# 路 A 可行性调研：给 NInfer 引擎补 `gguf_q4_0` 支持

> 调研日期：当前会话 · 只读调研，未改动任何代码。
> 目标：为「MTP 5 个张量是 `gguf_q4_0`，引擎报 `weight/000789: unknown tensor format: gguf_q4_0`」这条改造路线，给出**行级证据**与**最小改动集合**。
>
> **路径基准（下文 `[EVIDENCE]` 均相对此基准）**
> - `ENG/` = `J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src\`
> - `WS/`  = `J:\ninfer-kvmem\`

---

## 0. 结论速览（TL;DR）

| # | 问题 | 结论 |
|---|---|---|
| 1 | 白名单在哪 / 报错哪行 | `ENG/src/artifact/formats.cpp:10-37`（`kFormats`，26 项，无 q4_0）；解析函数 `parse_format` 在 `formats.cpp:55-60`，**`formats.cpp:59` 抛出 `unknown tensor format: …`**；再由 `ENG/src/artifact/layouts.cpp:16` 加上 `weight/000789: ` 前缀 |
| 2 | `GgmlType` 枚举 / 映射 | 枚举在 `ENG/src/ops/linear/gguf/ggml_bridge.h:16-32`（15 项，无 Q4_0）；**格式名→GgmlType 的映射在 `ENG/src/ops/linear/gguf/gguf_linear.cpp:87-107` 的 `gguf_type(QType)`**，不在 `ggml_bridge.h` |
| 3 | 引擎已有 q4_0 代码吗 | **引擎 `src/` 内 0 处**；但 **vendored `third_party/ggml-quants` 里 Q4_0 全家桶齐全**（`GGML_TYPE_Q4_0=2`、`block_q4_0`、`QK4_0=32`、`dequantize_q4_0`、`vec_dot_q4_0_q8_1`、mmq 的 DP4A/MMA 两条路）→ 可直接复用 |
| 4 | 有无 "dequant→bf16 再走通用路径" | **有，且是现成通路**：`dequantized_product`（`ggml_bridge.h:111-117` / `ggml_bridge.cu:470-495`），先例是 `IQ1_M`（`has_matrix_kernel` 对它返回 false，`ggml_bridge.cu:311`）。**不需要写 CUDA GEMM 内核**，只需补「反量化 + 向量核 Decoder」 |
| 5 | 重编代价 | 工具链（vcvars / cmake / ninja / CUDA 13.3 / vcpkg 缓存）**本机全部健在**；红线是「一个架构一个空目录 clean build」；脚本里写死的旧机器绝对路径 `J:\Bonsai-Official\...` **已失效需改**（旧 SRC 路径实测已不存在） |
| 6 | 副作用 | `kFormats` / `parse_format` 是**全局**白名单（不分组件），加一个名字对所有组件生效；`QType` 枚举受 `is_gguf()` 区间测试约束，**不能重编号**，只能追加 |

---

## 1. `formats.cpp` 白名单与报错点

### 1.1 `kFormats` 完整内容（26 项）

`[EVIDENCE] ENG/src/artifact/formats.cpp:10-37:constexpr std::array kFormats = {`

| 行 | QType | 字符串 |
|---|---|---|
| 11 | BF16 | `bf16` |
| 12 | FP32 | `fp32` |
| 13 | INT32 | `int32` |
| 14 | Q4_G64_FP16 | `q4_g64_fp16` |
| 15 | Q5_G64_FP16 | `q5_g64_fp16` |
| 16 | Q6_G64_FP16 | `q6_g64_fp16` |
| 17 | Q8_G32_FP16 | `q8_g32_fp16` |
| 18 | T2_G128_FP16 | `t2_g128_fp16` |
| 19 | PTQ1_G128_FP16 | `ptq1_g128_fp16` |
| 20 | NVFP4 | `nvfp4` |
| 21 | FP8_E4M3FN_ROW_BF16 | `fp8_e4m3fn_row_bf16` |
| 22 | GGUF_Q8_0 | `gguf_q8_0` |
| 23 | GGUF_Q2_K | `gguf_q2_k` |
| 24 | GGUF_Q3_K | `gguf_q3_k` |
| 25 | GGUF_Q4_K | `gguf_q4_k` |
| 26 | GGUF_Q5_K | `gguf_q5_k` |
| 27 | GGUF_Q6_K | `gguf_q6_k` |
| 28 | GGUF_IQ2_XXS | `gguf_iq2_xxs` |
| 29 | GGUF_IQ2_XS | `gguf_iq2_xs` |
| 30 | GGUF_IQ2_S | `gguf_iq2_s` |
| 31 | GGUF_IQ3_XXS | `gguf_iq3_xxs` |
| 32 | GGUF_IQ3_S | `gguf_iq3_s` |
| 33 | GGUF_IQ1_S | `gguf_iq1_s` |
| 34 | GGUF_IQ1_M | `gguf_iq1_m` |
| 35 | GGUF_IQ4_NL | `gguf_iq4_nl` |
| 36 | GGUF_IQ4_XS | `gguf_iq4_xs` |

`[EVIDENCE] ENG/src/artifact/formats.cpp:22-27:std::pair{QType::GGUF_Q8_0, std::string_view{"gguf_q8_0"}},` … `std::pair{QType::GGUF_Q6_K, std::string_view{"gguf_q6_k"}},`

**`gguf_blocks_v1` 到底接受哪些格式字符串？**
关键点：**layout 只负责 "行 = 整块 ggml 块" 这一几何约定，它不做格式过滤**。真正的格式过滤 100% 来自 `kFormats` 这一张表（26 个名字）。

`[EVIDENCE] ENG/src/artifact/formats.cpp:38-44:constexpr std::array kLayouts = { … std::pair{QuantLayout::GgufBlocks, std::string_view{"gguf_blocks_v1"}}, };`

`[EVIDENCE] ENG/src/artifact/formats.cpp:46-48:// Layouts a device may hold but an artifact may never declare. … `parse_layout` deliberately does not see them`

也就是说：`gguf_blocks_v1` **接受且仅接受**上表中 15 个 `gguf_*` 名字（q8_0 / q2_k / q3_k / q4_k / q5_k / q6_k / iq2_xxs / iq2_xs / iq2_s / iq3_xxs / iq3_s / iq1_s / iq1_m / iq4_nl / iq4_xs）。**`gguf_q4_0` 不在表内 → 报错。**

### 1.2 解析格式字符串的函数

`[EVIDENCE] ENG/src/artifact/formats.cpp:55-60:QType parse_format(std::string_view name) { for (const auto& [format, spelling] : kFormats) { if (spelling == name) { return format; } } throw ArtifactError("unknown tensor format: " + std::string(name)); }`

### 1.3 "unknown tensor format" 由哪一行产生

- **抛出点**：`[EVIDENCE] ENG/src/artifact/formats.cpp:59:    throw ArtifactError("unknown tensor format: " + std::string(name));`
- **唯一调用点**：`[EVIDENCE] ENG/src/artifact/layouts.cpp:10:        auto geometry = weight_geometry(parse_format(object.format), parse_layout(object.layout),`
- **张量名前缀 `weight/000789: ` 的来源**：`[EVIDENCE] ENG/src/artifact/layouts.cpp:16:    } catch (const std::exception& error) { throw ArtifactError(object.id + ": " + error.what()); }`
- **再往上一层**：`[EVIDENCE] ENG/src/artifact/reader.cpp:109:    if (!result) { result = describe_tensor(tensor); }`（`Reader::geometry`，惰性逐张量解析）

> ⇒ 完整报错链：`reader.cpp:109` → `layouts.cpp:10` → `formats.cpp:55` → `formats.cpp:59` throw → `layouts.cpp:16` 加 `weight/000789: ` 前缀。
> 全仓检索 `"unknown tensor format"` 只有 1 个命中文件（`ENG/src/artifact/formats.cpp`），确认无第二处白名单。

---

## 2. `ggml_bridge.h` 的 `GgmlType` 与映射表

### 2.1 `GgmlType` 枚举完整列表（15 项）

`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.h:16-32:enum class GgmlType : int { Q8_0 = 8, Q2_K = 10, Q3_K = 11, Q4_K = 12, Q5_K = 13, Q6_K = 14, IQ2_XXS = 16, IQ2_XS = 17, IQ3_XXS = 18, IQ1_S = 19, IQ4_NL = 20, IQ3_S = 21, IQ2_S = 22, IQ4_XS = 23, IQ1_M = 29, };`

注释明确其值 = GGUF 张量目录里的 `ggml_type` id：
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.h:15:// The block type's id in a GGUF tensor directory (ggml_type).`

### 2.2 格式名 → GgmlType 的映射表在哪

**不在 `ggml_bridge.h`，而在 `gguf_linear.cpp`：**

`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:87-107:gguf::GgmlType gguf_type(QType format) { switch (format) { case QType::GGUF_Q8_0: return gguf::GgmlType::Q8_0; … case QType::GGUF_IQ4_XS: return gguf::GgmlType::IQ4_XS; default: break; } throw std::invalid_argument("gguf: not a GGUF block format"); }`

声明：`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.h:21:[[nodiscard]] gguf::GgmlType gguf_type(QType format);`

### 2.3 加 Q4_0 需要改的常量（block size / blck_size / type_size）

一共 **4 处**与「块几何」相关的常量表：

| # | 位置 | 内容 | Q4_0 应填 |
|---|---|---|---|
| A | `ENG/src/ops/linear/gguf/ggml_bridge.h:16-32` | `enum class GgmlType` | **`Q4_0 = 2`**（ggml 官方 id） |
| B | `ENG/src/core/weight.h:106-125` `gguf_block_shape(QType)` | `QType → {elements, bytes}`（这是**真正被 `row_bytes()` 用的**） | **`{32, 18}`** |
| C | `ENG/src/ops/linear/gguf/ggml_bridge.cu:290-309` `block_shape(GgmlType)` | `GgmlType → BlockShape` | **`{32, 18}`** |
| D | `ENG/src/ops/linear/gguf/ggml_vec_*.cuh` `Decoder<T>::kBlockElems/kBlockBytes` | 向量核块几何 | **`32 / 18`** |

关于 C：实测 `gguf::block_shape(GgmlType)` **在 `src/` 与 `tests/` 内均无调用者**（全树检索 `gguf::block_shape` → 0 命中；`src/` 里 `row_bytes()` 用的是 `core/weight.h` 的 `gguf_block_shape(QType)`，见 `gguf_linear.cpp:22`），但它遇到未知类型会 throw（`ggml_bridge.cu:308`），仍应同步补齐以免留坑。

Q4_0 块几何的权威来源（vendored ggml）：
`[EVIDENCE] ENG/third_party/ggml-quants/src/ggml-common.h:194-199:#define QK4_0 32 / typedef struct { ggml_half d; uint8_t qs[QK4_0 / 2]; } block_q4_0; / static_assert(sizeof(block_q4_0) == sizeof(ggml_half) + QK4_0 / 2, "wrong q4_0 block size/padding");`
⇒ 32 元素 / 18 字节 / **4.50 bits per weight**。

ggml 官方 id：`[EVIDENCE] ENG/third_party/ggml-quants/include/ggml.h:392:        GGML_TYPE_Q4_0    = 2,`

CUDA traits 也已存在：`[EVIDENCE] ENG/third_party/ggml-quants/src/ggml-cuda/common.cuh:998-1004:struct ggml_cuda_type_traits<GGML_TYPE_Q4_0> { static constexpr int qk = QK4_0; … static constexpr int bs = sizeof(block_q4_0); };`

---

## 3. 引擎里是否已有 q4_0 代码 / 有没有可复用的 vendored 实现

### 3.1 引擎自身 `src/`：**零**

模式 `q4_0|Q4_0|QK4_0` 在 `ENG/` 全树检索共 **17 个文件命中，全部位于 `third_party/ggml-quants/`**，`src/` 一次都没有。
`src/` 内检索 `GGUF_Q4_K|GGUF_IQ4_NL|GgmlType::` 只有 4 个文件：`core/weight.h`、`artifact/formats.cpp`、`ops/linear/gguf/gguf_linear.cpp`、`ops/linear/gguf/ggml_bridge.cu` — 均**无 Q4_0 分支**。

### 3.2 vendored ggml-quants：**Q4_0 全链路齐备，可直接复用**

| 能力 | 证据 |
|---|---|
| 类型 id | `ENG/third_party/ggml-quants/include/ggml.h:392: GGML_TYPE_Q4_0 = 2,` |
| 块结构 / QK | `ENG/third_party/ggml-quants/src/ggml-common.h:194-199`（`QK4_0 32`、`block_q4_0`） |
| CUDA traits | `ENG/third_party/ggml-quants/src/ggml-cuda/common.cuh:998-1004` |
| **反量化（2 值 pair 形式）** | `ENG/third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:46-58:static __device__ __forceinline__ void dequantize_q4_0(const void * vx, const int64_t ib, const int iqs, float2 & v){ … v.x = (v.x - 8.0f) * d; v.y = (v.y - 8.0f) * d; }` |
| 反量化（整行形式，**IQ4_NL 可作模板**） | `ENG/third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:407-421:static __device__ __forceinline__ void dequantize_iq4_nl(const void * vx, const int64_t ibs, dst_t * yy, const int tid) { const block_iq4_nl * x = … + ibs*(QK_K/QK4_NL); … }` |
| **向量点积（含 -8 修正）** | `ENG/third_party/ggml-quants/src/ggml-cuda/vecdotq.cuh:135-136:    // second part effectively subtracts 8 from each quant value` / `:136:    return d4 * (sumi * ds8f.x - (8*vdr/QI4_0) * ds8f.y);` |
| 向量点积入口 | `ENG/third_party/ggml-quants/src/ggml-cuda/vecdotq.cuh:774-790:static __device__ __forceinline__ float vec_dot_q4_0_q8_1(…)` |
| **MMQ（整数张量核 GEMM）DP4A 路** | `ENG/third_party/ggml-quants/src/ggml-cuda/mmq.cuh:560-565:            case GGML_TYPE_Q4_0: return ggml_cuda_mmq_util_funcs(VDR_Q4_0_Q8_1_MMQ, ggml_cuda_mmq_load_tiles_q4_0<…>, ggml_cuda_mmq_vec_dot_q4_0_q8_1_dp4a<…>, …);` |
| **MMQ MMA 路** | `ENG/third_party/ggml-quants/src/ggml-cuda/mmq.cuh:730-735:        case GGML_TYPE_Q4_0: return ggml_cuda_mmq_util_funcs(-1, ggml_cuda_mmq_load_tiles_q4_0<…>, ggml_cuda_mmq_vec_dot_q8_0_q8_1_mma<…, MMQ_Q8_1_DS_LAYOUT_DS4>, …);` |
| MMQ 激活布局 | `ENG/third_party/ggml-quants/src/ggml-cuda/mmq.cuh:65-67:        case GGML_TYPE_Q4_0: case GGML_TYPE_Q4_1: return MMQ_Q8_1_DS_LAYOUT_DS4;` |
| MMQ case 声明 | `ENG/third_party/ggml-quants/src/ggml-cuda/mmq.cuh:1588:extern DECL_MMQ_CASE(GGML_TYPE_Q4_0);` |

vendored 来源与授权：`[EVIDENCE] ENG/third_party/ggml-quants/README.ninfer.md:3-5:These files are copied unmodified from llama.cpp, commit a25c9865…, under the MIT license`

> **结论**：`dequantize`、`vecdot`、甚至 `mul_mat_q` 三条路在 vendored 侧都已存在，**引擎侧不需要新写 CUDA GEMM 内核**，只需在 bridge 层做「接线 + 一个 Decoder + 一个行反量化分支」。

---

## 4. 最小改动集合（最关键一节）

### 4.1 先回答核心问题：线性层调用链里 q4_k/q2_k 是怎么被消费的？有没有统一 dequant→bf16 的 fallback？

**有。调用链如下（全部在 `ENG/src/ops/linear/gguf/gguf_linear.cpp`）：**

入口分派（按 `is_gguf(qtype)` 走 GGUF 路）：
`[EVIDENCE] ENG/src/ops/linear/linear.cpp:80-85:    if (is_gguf(w.qtype)) { if (workspace == nullptr) { throw … } detail::gguf_linear(x, w, out, *workspace, stream); return; }`
（`linear_add` / `linear_swiglu` / `embedding` / `attn_input_proj` / `gdn_input_proj` / `linear_topk` 各有同样的 `is_gguf` 分派，见 `ENG/src/ops/wrapper/*.cpp` 与 `ENG/src/ops/linear_topk/linear_topk.cpp:62-65`）

中央调度器 `gguf_project`（`gguf_linear.cpp:173-269`）**三条分支**：

| 分支 | 条件 | 走什么 |
|---|---|---|
| ① 向量核（decode / MTP verify / 小批） | `t <= 8` | `gguf::vector_product(...)` — `gguf_linear.cpp:183-203`，**对任何类型无条件执行，不问 `has_matrix_kernel`** |
| ② 整数张量核 GEMM（长 prefill） | `t > 8` 且 `has_matrix_kernel(type)` | `gguf::matrix_product(...)` — `gguf_linear.cpp:234-246` |
| ③-a 循环向量核 | `t > 8`、`!has_matrix_kernel`、`t <= 64` | 每 8 列一批调 `vector_product` — `gguf_linear.cpp:247-255` |
| ③-b **dequant→BF16→cuBLAS** | `t > 8`、`!has_matrix_kernel`、`t > 64` | `gguf::dequantized_product(...)` — `gguf_linear.cpp:256-266` |

`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:234:        if (gguf::has_matrix_kernel(type)) {`
`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:247:        } else if (t <= kDequantizedVectorColumns) {`
`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:264:            gguf::dequantized_product(type, w.qdata, row_bytes(w), w.n, k, source, t, out, stride, scratch, kDequantizedScratchBytes, stream);`

**fallback 通路的实现（现成，无需新写）：**
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.h:111-117:// The same product as matrix_product for a type without an integer kernel: each pass dequantizes up to dequantized_rows_per_pass rows into `scratch` (BF16) and runs a cuBLAS BF16 GEMM with an FP32 accumulator.`
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.cu:470-495:void dequantized_product(...) { … dequantize_rows(type, …, rows_bf16, k, stream); cublasGemmEx(blas, CUBLAS_OP_T, CUBLAS_OP_N, count, columns, k, &alpha, rows_bf16, CUDA_R_16BF, k, x, CUDA_R_16BF, k, &beta, out + first, CUDA_R_32F, …); }`

**先例类型 = `IQ1_M`**（它正是「没有整数核，宽乘积反量化后走 BF16 GEMM」的那个类型）：
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.cu:311:bool has_matrix_kernel(GgmlType type) { return type != GgmlType::IQ1_M; }`
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.h:44-45:// Whether the integer tensor-core prefill kernel exists for the type. IQ1_M has none (nor does it in llama.cpp); its wide products dequantize and take a BF16 GEMM.`
`[EVIDENCE] ENG/docs/gguf.md:31-32:  More columns (prompts) take llama.cpp's integer tensor-core kernel (`mul_mat_q`, vendored unmodified in `third_party/ggml-quants` …). `IQ1_M` has no such kernel; its wide products dequantize to BF16 and run cuBLAS.`

> ⇒ **路 A 完全可以"只加反量化、不写 CUDA GEMM"**：把 `has_matrix_kernel(Q4_0)` 置为 false，Q4_0 就自动复刻 IQ1_M 的全部通路。

### 4.2 但有一个硬约束：向量核 Decoder 是**必需**的（逃不掉）

分支 ①（`t <= 8`）与 ③-a（`9..64`）都调用 `vector_product` → `vector_launch` → **`vec::Decoder<T>`**：

`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.cu:71-90:VectorLaunch vector_launch(GgmlType type) { switch (type) { case GgmlType::Q8_0: return vec_launch<GGML_TYPE_Q8_0>; … } throw std::invalid_argument("gguf vector product: unsupported block type"); }`
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge_vec.cuh:601-603:template <ggml_type type> void vec_launch(...) { using D = vec::Decoder<type>;`
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge_vec.cuh:89-90:template <ggml_type type> struct Decoder;`

**MTP 恰恰跑在 decode / verify 这种小 `t` 上**，所以 Decoder 必须补。好消息：Q4_0 的块几何（32 元素 / 18 字节）与 **IQ4_NL 完全相同**，Decoder 可以几乎照抄：
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge_vec.cuh:107-124:struct Decoder<GGML_TYPE_IQ4_NL> { static constexpr int kBlockElems = 32, kBlockBytes = 18, kTableWords = 0; … s.f[0] = half_at(b); for (int j = 0; j < 4; ++j) { const int2 v = get_int_from_table_16(int(u32_a2(b + 2 + 4 * j)), kvalues_iq4nl); … } };`
`dot` 的 `-8 * sum` 修正可参照同文件 Q4_K 的写法（`sum` 形参 = 该 32 值切片的未量化激活之和）：
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge_vec.cuh:169-170:    __device__ __forceinline__ static float dot(const Slice& s, const int* a, float d, float sum) { return s.f[0] * d * float(dot4(s.w + 4, a + 4, dot4(s.w, a, 0))) - s.f[1] * sum; }`
（ggml 侧语义佐证：`ENG/third_party/ggml-quants/src/ggml-cuda/vecdotq.cuh:135-136`）

### 4.3 最小改动清单（按文件）

| # | 文件（相对 `ENG/`） | 位置 | 要做什么 |
|---|---|---|---|
| 1 | `src/artifact/formats.cpp` | `kFormats`（`:10-37`） | 加一行 `std::pair{QType::GGUF_Q4_0, std::string_view{"gguf_q4_0"}},`。**这是消掉报错的唯一必需项** |
| 2 | `src/core/weight.h` | `enum class QType`（`:9-45`） | 追加 `GGUF_Q4_0 = 26`（**不要重编号**，见 §6.2）。放在 `PTQ1_G128_FP16 = 25` 之后 |
| 3 | `src/core/weight.h` | `is_gguf()`（`:47-49`） | 区间测试 `>=GGUF_Q8_0 && <=GGUF_IQ4_XS` 覆盖不到 26，须改为 `(f >= GGUF_Q8_0 && f <= GGUF_IQ4_XS) \|\| f == GGUF_Q4_0`。**绝不能简单把上界放宽到 26**，否则 `PTQ1_G128_FP16(25)` 会被误判为 gguf（有 `static_assert(!is_gguf(QType::PTQ1_G128_FP16))` 在 `:54` 兜底） |
| 4 | `src/core/weight.h` | `gguf_block_shape()`（`:106-125`） | 加 `case QType::GGUF_Q4_0: return {32, 18};` |
| 5 | `src/ops/linear/gguf/ggml_bridge.h` | `enum class GgmlType`（`:16-32`） | 加 `Q4_0 = 2,` |
| 6 | `src/ops/linear/gguf/gguf_linear.cpp` | `gguf_type()`（`:87-107`） | 加 `case QType::GGUF_Q4_0: return gguf::GgmlType::Q4_0;` |
| 7 | `src/ops/linear/gguf/ggml_bridge.cu` | `block_shape()`（`:290-309`） | 加 `case GgmlType::Q4_0: return {32, 18};`（无调用者，防留坑） |
| 8 | `src/ops/linear/gguf/ggml_bridge.cu` | `has_matrix_kernel()`（`:311`） | 改为 `return type != GgmlType::IQ1_M && type != GgmlType::Q4_0;` ⇒ **走 dequant→BF16→cuBLAS，不写 GEMM** |
| 9 | `src/ops/linear/gguf/ggml_bridge.cu` | `dequantize_rows_kernel`（`:206-249`） | 加 `else if constexpr (type == GGML_TYPE_Q4_0)` 分支；可仿同函数里 Q8_0 的自带循环写法（`:214-219`），按 `blockIdx.x * (QK_K / QK4_0)` 取块（QK4_0=32，即每网格 8 个块），`y[i] = d * ((qs[i/2] 低/高 4 位) - 8)` |
| 10 | `src/ops/linear/gguf/ggml_bridge.cu` | `dispatch_dequantize()`（`:263-285`） | 加 `case GgmlType::Q4_0: return launch_dequantize<GGML_TYPE_Q4_0, 32>(...);` |
| 11 | `src/ops/linear/gguf/ggml_bridge.cu` | `vector_launch()`（`:71-90`） | 加 `case GgmlType::Q4_0: return vec_launch<GGML_TYPE_Q4_0>;` |
| 12 | `src/ops/linear/gguf/ggml_bridge_vec.cuh` | `Decoder<>`（`:89-90` 起） | 新增 `template <> struct Decoder<GGML_TYPE_Q4_0>`：`kBlockElems=32, kBlockBytes=18, kTableWords=0`；`decode`：8 个 `u32_a4(b+2+4i)` 拆 nibble 成 int8 字；`dot`：`s.f[0] * (d * dot8 - 8 * sum)` |
| 13 | `src/ops/linear/gguf/ggml_vec_q4_0.cu` | **新建** | 内容一行：`#include "ggml_bridge_vec.cuh"` + `NINFER_GGUF_VECTOR_INSTANCE(GGML_TYPE_Q4_0);`（照抄 `ggml_vec_iq4_nl.cu:1-4`） |
| 14 | `src/ops/linear/gguf/sources.cmake` | `:4-34` 的 `add_library(ninfer_ggml_quants STATIC …)` | 把 `ggml_vec_q4_0.cu` 加进源列表 |

**可选 / 一致性项（不影响 MTP 跑通，但建议）：**

| # | 文件 | 说明 |
|---|---|---|
| 15 | `tools/artifact/formats.py:87-101` 与 `:120-141` | Python 侧格式注册表（写侧）。加 `GGUF_Q4_0 = GgufFormat("gguf_q4_0", 2, 32, 18)` 并加进 `GGUF_FORMATS`。**不加以不影响读**，但保持两侧一致 |
| 16 | `tests/ops/linear/test_gguf.cpp:40-58` | `cases()` 加一行 `{QType::GGUF_Q4_0, "q4_0", {0}}`（`half_fields` = 块内 binary16 乘数字节偏移 → q4_0 只有偏移 0 的 `d`） |
| 17 | `docs/gguf.md:12-13`、`docs/maintainer/tensor-formats.md:46-62`、`docs/weight-conversion.md:167-169` | 文档里"十五种"的表述与表格需同步 |

### 4.4 走 mmq（整数张量核 GEMM）的可选加强项 —— **建议本次不做**

如果想让长 prefill 也走核（而非 dequant+cuBLAS），需额外：
- 新建 `src/ops/linear/gguf/ggml_mmq_q4_0.cu`（`NINFER_GGUF_MATRIX_INSTANCE(GGML_TYPE_Q4_0)`，照抄 `ggml_mmq_q4_k.cu:1-5`）
- `ggml_bridge.cu:413-442` 的 `matrix_product` 加 `NINFER_GGUF_MATRIX_CASE(Q4_0);`
- `ggml_bridge.cu:392-411` 的 `matrix_fixup_bytes` 加 `case GgmlType::Q4_0:`
- `has_matrix_kernel` 保持 true

**风险（为什么建议不做）**：`matrix_product_impl` 有硬几何门槛 ——
`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge_mmq.cuh:118:    if (k % 256 != 0 || rows % 128 != 0 || row_bytes % block_bytes != 0 ||`
MTP 那 5 个张量的 `rows` 未必是 128 的倍数（例如 attention 的 head 拼接维度），一旦不满足就 **throw**，比 dequant 通路风险高得多；而 MTP 头本身很小，dequant+cuBLAS 的性能完全够。

---

## 5. 重编代价

### 5.1 构建脚本清单（`WS/build/`）

| 脚本 | 用途 |
|---|---|
| `s6_1208a.bat` | **现役主脚本**：`cmake` configure + `ninja -k 0 -j 16` 全图构建 |
| `s6_configure.bat` / `s6_build.bat` / `s6_build_runtime.bat` | 旧基线（20261003）分步 |
| `s6_1208a_test.ps1` | STANDALONE 前端单测（53 项断言） |
| `a4-arm-A/C/D.bat`、`a4_load.py` | A4 压测三臂（与本次无关） |
| `designc_*.ps1`、`s6_k0_*.ps1` | legacy |
| `产物清单.md` | 各引擎件 SHA256 锚点 |
| `patches/` | `0001-fix-engine-…MSVC-C2326-C3495-C2026.patch`、`0002-feat-frontend-Design-C….patch`、`0003-build-tests-frontend_test-STANDALONE-exe-bundle.patch` + `README.md` |

### 5.2 构建流程

`[EVIDENCE] WS/build/README.md:29:3. **新基线全图构建**：`cmd /c s6_1208a.bat` → 产物 `<BUILD>\apps\ninfer-serve.exe`（+ 同目录 DLL）。`
`[EVIDENCE] WS/build/README.md:31:4. **可选验证**：`s6_1208a_test.ps1`（STANDALONE 前端单测，53 项断言，成功静默、退出码 0）。`
`[EVIDENCE] WS/build/README.md:32:5. **产物落位**：拷到正式目录（本机 = `engine\self-built-20261008\`）；**不要**把成品留在构建中间目录`

实际命令：
`[EVIDENCE] WS/build/s6_1208a.bat:18:"%CMAKE%" -S "%SRC%" -B "%BUILD%" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=120a -DCMAKE_CUDA_COMPILER=…/nvcc.exe -DNINFER_SM120_NATIVE=ON -DCMAKE_TOOLCHAIN_FILE=J:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows -DVCPKG_INSTALLED_DIR=…/build-120a/vcpkg_installed -DNINFER_BUILD_APPS=ON -DBUILD_TESTING=OFF -DNINFER_BUILD_BENCHMARKS=OFF`
`[EVIDENCE] WS/build/s6_1208a.bat:23:"%CMAKE%" --build "%BUILD%" -- -k 0 -j 16`

### 5.3 是否必须 clean build —— **是（红线）**

`[EVIDENCE] WS/docs/交接-工作区迁移-TeleAgent-20261009.md:104:- **红线（前序教训）**：**一个架构一个空目录 clean build**——增量构建会产出"启动即崩"的二进制。`
`[EVIDENCE] WS/docs/交接-工作区迁移-TeleAgent-20261009.md:105:- 产物落**正式目录**，**不要留 `.temp\`**（T-NO-TEMP-WORK）。`

⇒ 改完源码后**新建一个空 BUILD 目录**重配重编，不要复用 `build-1208a`。

### 5.4 已知的坑

1. **必须先 init `vcvars64.bat`**：`[EVIDENCE] WS/build/README.md:80:- **必须先 init `vcvars64.bat`**，否则 MSVC 报 `c1083 cstddef`（环境问题，非代码问题）。`
   更细：`[EVIDENCE] ENG/AGENTS.md:196:(`fatal error C1083: Cannot open include file: 'cstdint'`), because `INCLUDE` and `LIB` come from vcvars too.` —— 只把编译器 `bin` 加 PATH 不够。
2. **`.bat` 注释必须 ASCII-only**：`[EVIDENCE] WS/build/README.md:82:- `.bat` 注释一律 **ASCII-only**（cmd 按 OEM/ANSI 码页解析，中文注释会乱码炸构建——本项目踩过）。`
3. **不要"重新 configure 修缓存"**：`[EVIDENCE] ENG/AGENTS.md:227-228:… those caches are live and correct. Reconfiguring is the one thing that actually breaks the build here.`（指旧基线目录，与红线 5.3 一致：要干净目录而不是重配旧目录）
4. **脚本里写死的旧机器绝对路径已失效**（本次实测，`2026` 会话）：
   - `WS/build/s6_1208a.bat:13` 的 `SRC=J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` —— 该路径**实测仍存在**（`CMakeLists.txt` = True），但它是**旧工作区**的源码树；本次要编的是**本工作区**的树，须改为 **`J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src`**（实测 `CMakeLists.txt` 存在，git 分支 `s6-20261008`、`git status` 干净 0 行）。
     ⚠️ 核对过：两处 `src-tree` 下都有 `fusion-engine-src/`，改路径时**别改错到旧仓**——建议改完先 `type "%SRC%\VERSION"` 或 `git -C %SRC% rev-parse --abbrev-ref HEAD` 确认落在 `J:\ninfer-kvmem` 这棵。
   - `WS/build/s6_1208a.bat:11` 的 `CMAKE=…\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` —— **实测不存在**；本机实际在 **`J:\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe`**（实测存在；`ninja.exe` 同样在 BuildTools 下存在）。
   - `WS/build/s6_1208a.bat:14` 的 `BUILD=J:\Bonsai-Official\.temp\build-1208a` —— 按红线应换成**新的空目录**（例如 `J:\ninfer-kvmem\.temp\build-q40`，注意 5.3 又要求产物不留 `.temp` ⇒ 编完立即拷到正式目录）。

### 5.5 工具链 / 环境变量（**本机实测全部健在**）

| 项 | 脚本里的值 | 实测 |
|---|---|---|
| MSVC `vcvars64.bat` | `j:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat` | ✅ 存在 |
| CMake | `…\2022\Community\…\CMake\bin\cmake.exe` | ❌ 不存在（本机无 VS Community）；✅ `J:\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` |
| Ninja | 同上 Community 路径 | ❌ 不存在；✅ BuildTools 同期路径下 `ninja.exe`（注：`s6_1208a_test.ps1`/`s6_k0_*.ps1` 另有 `J:\Microsoft Visual Studio\2022\BuildTools\Common7\…` 的写法，随主脚本一并核对） |
| CUDA 13.3 | `J:\Bonsai\landing\cuda-13.3\bin` | ✅ 存在（`where nvcc` 首选即 `J:\Bonsai\landing\cuda-13.3\bin\nvcc.exe`） |
| vcpkg toolchain | `J:/vcpkg/scripts/buildsystems/vcpkg.cmake` | ✅ `J:\vcpkg` 存在 |
| vcpkg 已装依赖 | `J:/Bonsai-Official/.temp/build-120a/vcpkg_installed` | ✅ 存在（含 `x64-windows`）⇒ **无需重新拉 vcpkg 依赖，省一大截时间** |
| GPU arch | `-DCMAKE_CUDA_ARCHITECTURES=120a -DNINFER_SM120_NATIVE=ON` | RTX 5080 / sm_120a |
| 源码树分支 | — | ✅ `git rev-parse --abbrev-ref HEAD` = **`s6-20261008`**（= README 所说"已含全部补丁"的新基线）；`git status --porcelain` = **0 行**（干净） |

依赖表：`[EVIDENCE] WS/build/README.md:7-15`（CUDA 13.3 / vcpkg x64-windows / VS2022 BuildTools / CMake+Ninja / sm_120a）。

### 5.6 编译量级估计

- 本次改动触碰 `src/core/weight.h`（**头文件，被 `ninfer_ops`/`ninfer_runtime`/几乎所有目标依赖**）⇒ 即使不 clean build 也会触发大面积重编；叠加红线 5.3，**应按"全图 clean build"预留时间**。
- 新增 1 个 `.cu`（`ggml_vec_q4_0.cu`）= 1 个向量核实例化（比 mmq 实例化便宜得多；`ggml_bridge_mmq.cuh:148-152` 的矩阵实例化才是重量级）。
- 参考：`s6_1208a.bat:23` 用 `ninja -k 0 -j 16` 全图构建。

---

## 6. 风险与副作用

### 6.1 白名单是全局的，不是按组件

`parse_format` / `kFormats` 是**全引擎唯一**的格式注册表，由 `describe_tensor` 对**每一个**张量调用（`reader.cpp:109`），没有任何"按 `text` / `mtp` / `dflash2` 组件分别配置"的机制。

`[EVIDENCE] ENG/src/artifact/layouts.cpp:10:        auto geometry = weight_geometry(parse_format(object.format), parse_layout(object.layout),`
`[EVIDENCE] ENG/src/artifact/reader.cpp:109:    if (!result) { result = describe_tensor(tensor); }`

**正面影响**：加一个名字后，`text` / `mtp` / 任何组件的 `gguf_q4_0` 张量都能解析，无需组件级改动（MTP 走的也是 `is_gguf → gguf_linear` 这条通用路）。
**负面影响**：白名单一旦放开，任何来源的 q4_0 权重都会被接受；若某个 q4_0 张量几何不合规（`k % 512 != 0` 等），错误会从"解析期白名单拒绝"推迟到 `require_gguf` 运行时抛出：
`[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:111-115:    if (!is_gguf(w.qtype) || w.layout != QuantLayout::GgufBlocks || w.qdata == nullptr || w.n <= 0 || w.k <= 0 || w.k % block.elements != 0 || w.k % 512 != 0) { throw std::invalid_argument(…": expected a resident GGUF matrix over 512-column groups"); }`

### 6.2 `QType` 枚举不能重编号（最需要小心的改动点）

`is_gguf()` 是**区间测试**，且 PTQ1 被"故意放在最后"：

`[EVIDENCE] ENG/src/core/weight.h:47-49:[[nodiscard]] constexpr bool is_gguf(QType format) { return format >= QType::GGUF_Q8_0 && format <= QType::GGUF_IQ4_XS; }`
`[EVIDENCE] ENG/src/core/weight.h:39-43:    // Row-split only. Appended LAST on purpose: `is_gguf()` below is a range test over GGUF_Q8_0..GGUF_IQ4_XS, so a new value must land outside that range, and the wire format carries the name rather than the number, so nothing may be renumbered.`
`[EVIDENCE] ENG/src/core/weight.h:51-54:// The range test above only stays correct while the ggml block types remain the contiguous top of the enum. Pin it … / static_assert(!is_gguf(QType::T2_G128_FP16)); / static_assert(!is_gguf(QType::PTQ1_G128_FP16));`

⇒ **只能追加 `GGUF_Q4_0 = 26`**（在 `PTQ1_G128_FP16 = 25` 之后），并**同步改 `is_gguf()` 为带显式排除/或运算的形式**，使 `PTQ1(25)` 仍返回 false，否则 `weight.h:54` 的 `static_assert` 会编译失败（这正是作者留的护栏，改动会被立刻抓住）。

### 6.3 走 dequant 通路的两个副作用

1. **workspace 变大**：只要任一 product 无整数核，`gguf_project_workspace_bytes` 就会多申请 16 MiB 反量化 scratch + 一份向量激活：
   `[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:139-141:        } else { dequantized = true; }`
   `[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:160-163:        if (dequantized) { (void)layout.alloc_bytes(gguf::vector_activation_bytes(k, gguf::kMaxVectorColumns)); (void)layout.alloc_bytes(kDequantizedScratchBytes); }`
   `[EVIDENCE] ENG/src/ops/linear/gguf/gguf_linear.cpp:14:constexpr std::size_t kDequantizedScratchBytes = std::size_t{16} << 20;`
   影响面仅限含 Q4_0 的那一组 product（MTP 头），`text` 组件（全 q4_k 等）不受影响。
2. **prefill 慢**：`t > 64` 时 Q4_0 走 "dequant 到 BF16 + cuBLAS"，比整数张量核慢；但 MTP 头张量小、且 MTP 主要跑在小 `t`，实际影响有限。

### 6.4 q4_0 的精度/速度特性，与"作者为什么没支持"

**引擎内没有任何注释/文档明说"不支持 q4_0 的原因"**。唯一可考的口径是"覆盖 llama.cpp 为 dense 模型写的全部 15 种块类型"：

`[EVIDENCE] ENG/docs/gguf.md:12-13:All fifteen block types llama.cpp writes for dense models: `Q8_0`, `Q2_K`, `Q3_K`, `Q4_K`, `Q5_K`, `Q6_K`, `IQ1_S`, `IQ1_M`, `IQ2_XXS`, `IQ2_XS`, `IQ2_S`, `IQ3_XXS`, `IQ3_S`, `IQ4_NL` and `IQ4_XS`,`
`[EVIDENCE] ENG/docs/weight-conversion.md:167-169:All fifteen block types llama.cpp writes for dense models are supported: Q8_0, Q2_K to Q6_K, IQ1_S, IQ1_M, IQ2_XXS, IQ2_XS, IQ2_S, IQ3_XXS, IQ3_S, IQ4_NL and IQ4_XS.`

即：**Q4_0 属于 ggml 的 legacy 类型（id 2，见 `ggml.h:392`），llama.cpp 现代量化器不为 dense 模型产出它**，所以 NInfer 的"15 种"清单天生不含它 —— 这次的 `.ninfer` 是第三方导出器给 MTP 头选了 Q4_0，撞到了清单外。

**精度/速度**（由块结构与 ggml 语义推导，非文档原文）：
- **同为 4.50 bits/weight**（32 值/18 B，见 `ggml-common.h:194-199`），与 `q4_k`（256 值/144 B，见 `gguf_block_shape` `ENG/src/core/weight.h:111`）**每权重位数完全相同**。
- 但 **q4_0 每 32 个值只有 1 个 fp16 比例尺**（`block_q4_0 { ggml_half d; uint8_t qs[16]; }`），而 q4_k 有 6-bit 子块尺度 + 超块 fp16 尺度 ⇒ **同样 4.5 bpw 下 q4_0 的量化误差明显大于 q4_k**。
- 速度：块更小（32 vs 256）意味着同样的 K 有 8 倍数量的块头，仅就"读字节数"而言与 q4_k 持平；若走 dequant 通路则还要额外付出 BF16 展开 + cuBLAS 的开销。
- 对本次场景（MTP 投机草稿头）**精度不敏感**：MTP 只负责产草稿 token，由主模型 verify，草稿分布偏一点不影响最终输出分布 —— 这也是"路 B（数据侧重存为 bf16/q4_k）"同样成立的原因。

### 6.5 其他需注意的点

- `dequantize_rows_kernel` 要求 `k % QK_K(256) == 0`（网格是 `k/256`）：`[EVIDENCE] ENG/src/ops/linear/gguf/ggml_bridge.cu:255-258:    if (k % QK_K != 0 || rows <= 0) { throw …"gguf dequantize: K must be whole 256-value blocks"; } dequantize_rows_kernel<type, threads, dst_t><<<dim3(k / QK_K, rows, 1), threads, 0, stream>>>(…)`
  ⇒ Q4_0 分支必须按"每个 `blockIdx.x` 覆盖 256 个值 = 8 个 q4_0 块"来写（与 `dequantize_iq4_nl` 用 `ibs*(QK_K/QK4_NL)` 的写法一致，`dequantize.cuh:410`）。
- `require_gguf` 另要求 `k % 512 == 0`（`gguf_linear.cpp:112`）。K=5120（hidden）满足；但**建议在动手前先从容器里 dump 这 5 个张量的实际 shape / layout 字符串**确认一次（`weight/000789` 应是其中之一）。
- 向量核几何自检：`vec_launch` 会校验 `args.row_bytes % D::kBlockBytes == 0`（`ggml_bridge_vec.cuh:604`）；`row_bytes = (k/32)*18`，k=5120 ⇒ 2880，2880 % 18 == 0 ✅。
- 反量化 scratch 每次处理行数：`dequantized_rows_per_pass`（`ggml_bridge.cu:465-468`），k=5120 时 16 MiB 可放 ~1536 行，足够。

---

## 7. 一句话判断

**路 A 可行，且比预期轻**：引擎已经有现成的「无整数核类型 → 反量化到 BF16 → cuBLAS」通路（先例 `IQ1_M`），vendored ggml 里 Q4_0 的反量化/向量点积/MMQ 实现一应俱全，**引擎侧只需 ~14 处小改 + 1 个新 `.cu`，不需要写任何 CUDA GEMM 内核**；真正的成本在**重编**（头文件 `core/weight.h` 改动触发全图重建 + 红线要求新空目录 clean build + 脚本里 3 处旧机器绝对路径已失效需修）。

相对地，路 B（数据侧把 5 个 q4_0 张量重存为 bf16/q4_k、不重编）依旧是**更轻**的选项 —— 本调研不改变该判断，只是把路 A 的"重"量化成了"约 14 处小改 + 一次 clean build"。
