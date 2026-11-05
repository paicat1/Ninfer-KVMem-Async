# 调研：上游对照（Strata + KVMem v0.19）· prefill 基准修正 · DFlash2 可行性修正 · 本仓落地状态（CB · TELE · LUMMY）

- 日期：2026-11-03
- 对象：`Niko1221/Strata`（全库克隆，5,681 文件 / 87.4 MB，v0.2.10）
- **三方分工**：
  | 方 | 方法 | 产出 |
  |---|---|---|
  | **CB（本报告）** | 全库代码级精读（17 个模块）+ 引擎侧静态核查 | §二 18 个小节、§三 汇总、§八 收敛、§十 交叉核对 |
  | **TELE** | 文档级调研（9 篇 docs）+ 办公室侧静态核查（3 项） | `调研-STRATA-可借鉴点分析-TeleAgent-20261103.md`、三轮收敛意见 |
  | **LUMMY** | 跨项目对照（定位/成熟度/8 项增量） | `研究-Strata跨项目对照与借鉴清单-lummy-20261102.md` |
- 方式：tarball API 全量拉取（`refs/strata/`）→ 架构文档 → 核心头文件 → 关键实现

> ### ⚠ 家里智能体必读：先全量拉取 Strata 库，否则本报告无法复核
>
> 本报告的**全部代码引用**都在 `refs/strata/`（办公室本机克隆，**不入 git**，任何 pull 都拿不到）。
> **复核 §二 的 18 个小节之前，必须先拉取**：
>
> ```bash
> # 方式一：git clone（443 通畅时首选）
> git clone --depth 1 --single-branch https://github.com/Niko1221/Strata.git refs/strata
>
> # 方式二：tarball API（git 协议被墙时的替代——办公室就是这么拉的，clone 12 次全失败）
> curl -L -H "Authorization: token <TOKEN>" \
>   https://api.github.com/repos/Niko1221/Strata/tarball/main -o strata.tar.gz
> tar -xzf strata.tar.gz -C refs/ && mv refs/Niko1221-Strata-* refs/strata
> ```
>
> **验收**：`refs/strata` 下应有 **5,681 文件 / 87.4 MB**（v0.2.10，`main` @ 2026-11-02）。
>
> **不拉取也能读结论**（§八 收敛结论、§十 交叉核对是自足的），
> **但无法复核 §二 的 18 个小节**——那里的 `refs/strata/...:行号` 全部依赖该克隆。
- 证据等级：**代码级**（文件路径 + 行号 + 实测数字均来自其文档与注释）
- **收敛状态**：2026-11-03 三方收敛完成——**撤回 4 条 / 挂起 3 条 / 净可借 2 条 + 1 组方法论 + 1 条架构判断**（见 §八）

---

## 〇 一句话（两份合并）

**两个上游都读了，结论分三层：**

| 层 | 结论 |
|---|---|
| **基准** | **「我们 prefill 慢 2×」是错的**——那是拿 dense 27B 比 MoE。同 dense 27B：llama.cpp 197 tok/s、我们 **1,857**、qw3 融合 1,850 ⇒ **我们比 llama.cpp 快 9.4×，与 qw3 持平** |
| **可借（KVMem 上游，同谱系）** | **三层 KV（RAM↔SSD）**：RAM ±0.1%、SSD +2.5%（260K）；**DFlash2 集成已完成**（Qwen3.8-27B dense，1.14 GB，+14.6~33.7%） |
| **可借（Strata，同赛道）** | 自适应投机窗口 +7.88%（sm_120）· KV_PREFETCH prefill −4~5% · 方法论一组 |

**⇒ 上游 KVMem 更值得学（同谱系、同模型、同配置、有实测）；Strata 是镜子与补充。**

**❗ 第六层结论（§十四）**：**长前缀锚不是「提速 prefill」，是「让下一轮少做 prefill」**——门槛 = 锚页数 + 256 页工作集 + 余量 ≤ 池；收益线性（0.033 秒/页），最优 = 池允许的最深锚。**家里第一步零成本可做**：用 §206 的 63,989 prompt + 51,200 池，看现役件 `capture install` 是否 0→>0。

**❗ 本轮第五层结论（§十二）**：**DFlash2 的「无法加载」是 10 月算式错误**（把互斥的 MTP 加了进去）——引擎早已实现，Bonsai 线已有 `dflash2` 独立档（kvcap 17,920），Q4_K_M 转容器约 1.4~1.6 GiB，**可行**，缺的只是一次转码 + 一晚实测。

## 一 仓库概况

| 项 | 值 |
|---|---|
| `full_name` | `Niko1221/Strata` |
| stars / forks | **38,619 / 4,198** |
| 最新版本 | **v0.2.10（2026-11-02）** |
| 版本速度 | **20 个 release / 26 天**（v0.1.40.4 @10-08 → v0.2.10 @11-02） |
| 语言 | C++（556 cpp / 334 hpp / 118 cu / 981 py） |
| 后端 | CUDA / HIP / SYCL / Metal 四套 |
| 定位 | Qwen3.8-Flash-Next 一键安装（Win/Linux），OpenAI/Anthropic API on localhost |

**目录重心**：`apps/host`（934 文件）、`include/strata`（210）、`src/kernels`（181）、`src/split`（72）、`src/core`（67）、`src/prefill`（44）。

---

## 二 可参考技术（按对我们的价值排序）

### 2.1 KVA：长 prompt 的近似晚层读取（prefill +11~28%）

**文件**：`docs/KVA.md`（190 行）+ `include/strata/prefill/kva.hpp`（198 行）

**机制**（`kva.hpp:1-9` 原文）：

```
positions [0, n - suffix)   近似：后期层只跑 state-only
                            （GDN recurrence + conv history + K/V pages + indexer keys）
positions [n - suffix, n)   精确算（suffix，默认 2048 token）
```

**为什么能快**（`kva.hpp:3-6` 原文）：

> After layer `split` the prompt's late layers need only their recurrent state and their KV/indexer caches;
> **the attention output, the output projection, the MoE half and its expert transfers have no remaining consumer**
> for the approximate positions.

⇒ **跳过的是后期层的 MoE 半 + expert transfers**（Qwen3.8-Flash-Next 有 48 层 × 512 experts）。

**默认配置**（`kva.hpp:60-64`）：

```cpp
kKvaSuffixDefault = 2048;   // 精确尾
kKvaSplitDefault  = 36;     // 只近似 36-47 层（48 层中后 12 层）
```

**实测数字**（`docs/KVA.md`）：

| 平台 | 配置 | prompt 速度 | decode |
|---|---|---|---|
| Tesla P100 | IQ3_XXS | **+12% @14K / +20% @30K** | 噪声内 |
| Radeon R9700 | IQ3_S | **+28%**（2411→3086 tok/s） | **−11%**（94.7→84.3） |
| RTX 5070 | `--agent-long` 22 任务 | +11% @14K / +18% @30K | agent 6/10（exact 4 和 7） |

**质量代价（诚实记录）**：

- **split 24（初版，近似 24-47 层）质量崩**：长提取任务 4/6 通过（exact 6/6），270 条事实只找到 249；agent 循环 0/10 通过（exact 4 和 7）；30K 答案以"编造的行"开头
- **split 36（默认）**：agent 6/10、extraction 585/606（exact 585）⇒ 干净
- ⇒ **所以才默认关**（`STRATA_KVA=1` 才开）

**适用性判断**：

| 项 | 判断 |
|---|---|
| 直接照搬 | ❌ 要求 **48 层 + 512 experts**（Qwen3.8-Flash-Next 形状），我们是 27B Coder，形状不同 |
| **机制可借** | ⚠ **打折**：KVA 收益主要是"跳过 MoE 半 + expert transfers"（48×512 experts），**我们是稠密模型，没有 MoE 半** ⇒ 只能跳 `attention output` + `output projection`，收益远小于 +11~28% |
| 前置 | 需要确认我们的模型是否有 GDN/recurrent 层（`--gdn-state-fp16` 存在 ⇒ **有**） |

### 2.2 自适应投机窗口（我们固定 draft=4，他们是动态）

**文件**：`src/spec/draft_policy.cpp`（14,354 B）+ `src/spec/suffix_drafter.cpp`（3,512 B）

**两件事分开**：

**① lookup 型 drafter**（`suffix_drafter.cpp`）——不是神经网络，是 **3-token 哈希查表**：

```cpp
uint64_t key_at(size_t end) const {
    const uint64_t a = hist_[end - 2], b = hist_[end - 1], c = hist_[end];
    return mix(a * 0x9E3779B97F4A7C15ull ^ mix(b + 0x632BE59BD9B4E019ull) ^ (c << 1)) | 1ull;
}
SuffixDrafter(int min_match, int max_match, size_t capacity_tokens)
    : min_match_(std::max(3, min_match)), max_match_(std::max(min_match, max_match))
    // load factor <= 0.5
```

**② 窗口大小自适应策略**（`draft_policy.cpp`）——这才是可借的部分：

```cpp
kShape[]        = {0.0, 1.0, 1.35, 1.7, 2.05, 2.45, 2.85, 3.25, 3.6, 4.0, ...};  // 窗口大小的成本形状
kCostAlpha      = 0.1;     // 每轮实测耗时的 EMA 权重
kTokAlpha       = 0.05;    // MTP 窗口结果的 EMA 权重
kCalDecay       = 0.995;   // "MTP 概率→接受率" 校准表衰减
kDecay          = 0.97;    // lookup 计数衰减
kPriorQ[]       = {0.75, 0.88, 0.93, 0.96};  // 4 个 bucket 的先验
kPriorN         = 4.0;     // 先验等价 4 次观测
kProbes         = 3;       // 一个窗口大小试 3 次才允许成本否决
kStaleRounds    = 300.0;   // 300 轮没测过的大小会重试
```

**bucket 分级**（按 match 长度）：`<6 / <12 / <24 / ≥24` ⇒ 四档先验概率。

**v0.2.10 的实测收益**（release notes）：

> **DFlash2 against MTP, Qwen3.8 on one card.** Same engine and files, runs alternated:
> - Ryzen AI Max (Strix Halo) Windows: UD-Q4_K_XL **+12.0%** 短答 / **+8.8%** 长答；IQ3_S +8.4% / +4.0%
> - **RTX PRO 5000 (CUDA, sm_120)**，IQ3_S：**+7.88%** greedy / +6.23% 短采样 / **+1.38%** 长答（2K）

**RTX PRO 5000 是 sm_120**——与我们的 RTX 5080 **同架构**。

**适用性判断**：

| 项 | 判断 |
|---|---|
| **自适应窗口** | ✅ **可以直接借鉴**：纯调度层，不改模型、不改 kernel。我们 `--draft-tokens 4` 是固定值，他们的 EMA+校准表能"接受率高时用大窗口、低时用小" |
| lookup drafter | ⚠ 我们已有 MTP（91-99% 接受率），lookup 只适合"重复文本多"的场景（如 agent 反复引用同一段代码），**可作为补充**而非替代 |

### 2.3 expert_cache：MoE expert 驻留 VRAM（96% 暴露 → 部分隐藏）

**文件**：`include/strata/core/expert_cache.hpp`（20,651 B）+ `src/core/expert_cache.cpp`（39,829 B）

**问题定义**（`expert_cache.hpp:4-7` 原文，数字极有价值）：

> The CPU expert pool is the engine's **largest single cost**: measured, **663.6 MB of expert bytes per token at
> ~40 GB/s = 16.2 ms**, on a token of ~53 ms, and `test_expert_pool` says the pipeline hides **1.055 ms of 19.035**
> — **the CPU work is 96% exposed because the residual chain is strictly serial**.

**方案**：把 48×512 experts 的一部分放进 VRAM，GPU 算，CPU 只读 miss。

**设计依据（全部是实测，不是假设）**：

```
h_expert  = 4,105 slots，十倍留一交叉验证 0.6447 [0.6110, 0.6750]
VRAM      = 稳态实测 6414 MiB free，4105 slots 需 5413 MiB ⇒ 能放，余 ~1 GB
h_layer   = held-out 0.0456 ⇒ 只有 4.6% 的 (layer, token) 对十个专家全驻留
            ⇒ 不能按层分组，三段拆分不是优化而是必须
```

**适用性判断**：

| 项 | 判断 |
|---|---|
| 前提 | **模型必须是 MoE** |
| 我们的模型 | **Qwen3.8-27B-Coder390 = 稠密（dense）**（用户 2026-11-03 确认）⇒ **本路线关闭** |
| 若是 MoE | ⚠ 这是最大单项：16.2 ms/token 的 96% 暴露；但需要 `profile.bin` 静态规划 + VRAM 预算 |
| **若是 dense（我们）** | ❌ **不适用**——没有 expert 可 offload。这条数字（663.6 MB/token）只对 MoE 成立 |

### 2.4 conversation_cache：整会话 parking + pinned 前缀

**文件**：`include/strata/core/conversation_cache.hpp`（29,419 B）

**关键结构**：

```cpp
struct ConversationKv {
    int format, heads, head_dim, page_size, pooled_rows, idx_dim;
    ConversationBuffer k, v, k_scale, v_scale, pooled;   // 量化 + scale 分开存
    uint64_t dev_tag;                                     // STRATA_PARK_VRAM_MIB 的 VRAM slot 标签
};

bool pinned = false;   // 只读前缀，suffix 查询从它分支 ⇒ retention 永不 evict
struct PromptPlan { int64_t chunk, from, to, lend; double pipe; };  // prefill-pipe 的 chunk 计划
```

**三个可借的设计**：

| 设计 | 含义 | 对我们的意义 |
|---|---|---|
| **pinned 前缀** | suffix 查询的分支点，retention 永不驱逐 | 我们有 prefix cache（r2 命中 49.3%），但**没有"钉住"机制**——常用系统提示词可能被挤掉 |
| **整会话 parking** | KV + GDN + PLE + tails 整体存 host/VRAM，按需恢复 | 与我们的 KVMem 同层，但**粒度是"会话"而非"页"** |
| **k_scale / v_scale 独立存** | 量化值 + scale 分开 | 我们 rk8v4 的 scale 存哪？（需核） |

### 2.5 实验固化（本条来自本项目，用户已认可）

**建议原文**：

```
起服 → 先打印「件 sha / 全参数 / 补丁链指纹」
     → 缺任一项就拒绝起服
```

**为什么写在 Strata 报告里**：Strata 的 `bench/results/` 有 **2,185 个文件 / 21.9 MB**，按日期+配置分目录（如 `2026-09-29-layer-split-limits/data/norepeat-lim-kv-x2-coder-iq1_m.json`）——**他们每次实验都留下可回溯的记录**。

我们的对应物是 `build.info`（P0-6，草案已写但未实施）。

### 2.6 显存分配 granule 圆整（⚠ **本节假设已在 §2.18① 被否定，保留仅作记录**）

**文件**：`src/core/native_dense.cpp:24-36`

**原文（含实测）**：

```cpp
// `load` makes one cudaMalloc per projection matrix, and the driver backs each call with 2 MiB granules
// (measured on the RTX 5060: 300 buffers of 6.73 MiB asked 2019 MiB and cost 2400).  So a stage's real
// footprint is the granule-rounded sum, not the payload sum.
constexpr uint64_t kAllocGranule = 2ull << 20;   // 2 MiB
constexpr uint64_t kSmallAlloc   = 1ull << 20;   // <1 MiB 的走 payload，不圆整
uint64_t alloc_bytes(uint64_t bytes) {
    return bytes < kSmallAlloc ? bytes : (bytes + kAllocGranule - 1) / kAllocGranule * kAllocGranule;
}
```

**数字**：

```
300 个 6.73 MiB 的 buffer
  申请总和 = 2,019 MiB
  实际占用 = 2,400 MiB     ← 多 381 MiB（+19%）
```

**为什么对我们重要**：如果我们的引擎也是"每个投影一次 cudaMalloc"，那 **KV 池上限的估算会系统性低估显存占用**——每层每投影多出来的 granule 碎片，可能正是"池上限上不去"的一部分原因。

**可做的验证（一条命令，零成本）**：`nvidia-smi` 在起服后看 `used` 与"纸面计算值"的差；差值 ÷ 2 MiB 就是碎片个数。

### 2.7 `STRATA_HC_Q8`：hyper-connection 投影的 Q8 量化

**文件**：`src/core/native_dense.cpp:44-56`

**原文**：

> `STRATA_HC_Q8`: 1 = on (the GGUF's own Q8_0 projections, or — a bf16 pack — a Q8_0 copy quantized at load); 0 = off;
> unset / auto = on for gfx12 (RDNA4: the R9700 **decode +2.5 to +4%**, KL 0.0003-0.0010 over its noise floor) unless
> `STRATA_GFX12_DEFAULTS=0`; also on for gfx1151 (Strix Halo, `STRATA_HC_Q8=0` turns it off), **decode +9.5%,
> json/code/tool/chat/agent +7.9..+10.7%**

**含义**：hyper-connection（多流残差）的投影层从 bf16 降到 Q8_0，**decode +2.5~9.5%**，质量代价 KL 0.0003~0.0010（噪声级）。

**对我们的意义**：这是**第二个"量化换速度"的有效案例**（第一个是 rk8v4 比 rk2v4 快 20%），而且方向一致——**8 位在速度与质量上都优于更低比特**。

### 2.8 DFlash2 生产实现（`src/core/dflash2.cpp`，59,518 B）

**不是离线工具**（`tools/dflash2/` 才是评测工具），这里是真的 drafter：

```cpp
Dflash2Drafter::~Dflash2Drafter() {
    for (cudaGraphExec_t& e : exec_) if (e) cudaGraphExecDestroy(e);   // ← cudaGraph 执行
    for (int l = 0; l < 8; ++l) { fr(kring_[l]); fr(vring_[l]); }      // ← 8 层 K/V ring
    ... cs_ / cs2_ 双 stream + ev_fork_/ev_join_ 事件
}
// STRATA_DF2_PROFILE=1 (measurement only): the round runs without its graph and an event follows every stage;
// the per-stage averages print at exit
```

**三个可借的实现要点**：

| 要点 | 含义 |
|---|---|
| **cudaGraph 执行** | drafter 的整轮编成图，减少 launch 开销 |
| **双 stream + fork/join 事件** | drafter 与 target 的搬运/计算重叠 |
| **8 层 K/V ring** | drafter 只保留 8 层 K/V（不是全部层）⇒ 显存小、可常驻 |

**注意**：它需要 `native_head` + `native_mmvq`（量化矩阵向量乘）——**能为任意 target 构建 drafter**，不限定 MoE。

### 2.9 `pinned.cu`：pinned host arena（**不是** KV 前缀钉住，两个概念）

**文件**：`src/core/pinned.cu`（67,537 B）

**先澄清**：`conversation_cache.hpp` 里的 `bool pinned` 指"KV 前缀不被驱逐"；`pinned.cu` 指 **pinned（锁页）host 内存 arena**——两个不同的东西。

**可借的工程细节**：

```cpp
constexpr uint64_t kSharedArenaHeaderBytes = 4096;
constexpr char kSharedArenaMagic[16] = "STRATA-ARENA-V1";   // 共享 arena 带 magic + version

// Loader fix: `fseek`/`ftell` are 32-bit on Windows by default (and the pack is 42.9 GB),
// and the 64-bit spelling is not the same on the two platforms.
#ifdef _WIN32
#define STRATA_FSEEK64(f, o) _fseeki64((f), (long long)(o), SEEK_SET)
#else
#define STRATA_FSEEK64(f, o) fseeko((f), (off_t)(o), SEEK_SET)
#endif

// Linux: 2 MB 大页
#ifndef MAP_HUGE_2MB
#define MAP_HUGE_2MB (21 << 26)
#endif
```

**三条可借**：

| 细节 | 为什么值得借 |
|---|---|
| **`_fseeki64`** | Windows 默认 `fseek` 是 32 位，>2 GB 的 pack 会静默错位 |
| **`MAP_HUGE_2MB`** | Linux 用 2 MB 大页，减少 TLB miss（我们 Windows 为主，但可查 `largePageSizeInBytes`） |
| **SharedArenaHeader（magic+version）** | 多进程/多实例共享同一 arena，避免重复加载权重 |

### 2.10 `kv_q8.cu`：KV Q8 量化内核

**文件**：`src/kernels/cuda/kv_q8.cu`（12,867 B）

```cpp
// One block = one 64-value group of one KV head of K (blockIdx.z = 0) or V (1); 64 threads, one value each.
// MULTI (S26 STRATA_LFUSE): blockIdx.z = 2 * token + (K / V); token j reads step + j * step_stride ...
template <bool MULTI = false>
__global__ void kv_append_q8_kernel(int8_t* k_q, int8_t* v_q,
                                    uint16_t* k_scale, uint16_t* v_scale,
                                    const int32_t* table, const int32_t* step,
                                    const float* kcur, const float* vcur, int kv_heads,
                                    int head_dim, int page_size, KvHostPools host,
                                    int step_stride = 0, int cur_stride = 0)
```

**四点设计**：

| 设计 | 值 | 含义 |
|---|---|---|
| **量化粒度** | **64 值一组**（`KV_Q8_GROUP`） | 每 64 个值一个 scale（不是 per-tensor） |
| **K/V 分离存储** | `k_q`/`v_q` + `k_scale`/`v_scale` | 各自独立量化 |
| **scale 类型** | `uint16_t`（fp16） | scale 本身用半精度 |
| **`MULTI` 模板（STRATA_LFUSE）** | 一次 launch 处理多个 token | **融合多 token append**，减少 launch 次数 |

**对我们的意义**：我们的 `rk8v4` 是 rank-8/vector-4 的复合格式，比"64 值一组 + fp16 scale"复杂；**但 `MULTI`（多 token 一次 launch）是可借的**——超池场景每步 append 一个 token，launch 开销累积可观。

### 2.11 `mtp.hpp`：MTP draft 层的完整结构（**对我们直接相关**）

**文件**：`include/strata/core/mtp.hpp`（25,938 B）+ `src/core/mtp.cpp`（109,505 B）

**原文（结构与实测接受率）**：

```cpp
// The model ships one multi-token-prediction layer (vLLM 0.30.0 `qwen4_exp` MTP; transcribed and validated in
// `tools/mtp_probe.py`, where it accepts 0.89 / 0.86 / 0.85 of greedy drafts at steps 1-3).
//
//   e = fc_embedding(rms(embed(tok)) * (1+w))      h = fc_hidden per stream(rms_10240(R) * (1+w))
//   R = h + e  ->  attention hyper-connection  ->  QSA attention (own K/V)  ->  MLP hyper-connection
//      ->  MoE (512 experts, top-10, shared expert)  ->  R += y * 2 sigmoid(inject / hc)  ->  final mixer  ->  head
//
// Runtime choices (only affect DRAFT quality, never the output):
//   * the large projections run as Q8_0 through the multi-column MMVQ (tools/mtp_rt.py quantizes them);
//   * the attention is DENSE over every cell the layer has seen - identical to the model's sparse selection
//     below 2,051 cells - so speculative cells never touch indexer state and are simply overwritten;
//   * all 512 routed experts live in VRAM (708 MB) and run through the grouped hit kernels.
```

**四个关键数字**：

| 项 | 值 | 对我们的意义 |
|---|---|---|
| MTP 接受率（step 1–3） | **0.89 / 0.86 / 0.85** | 递减但都很高；说明 draft 层值得投入 |
| **MTP 层显存** | **~0.9 GB**（`load()` 注释） | **我们的 MTP 层占多少？** 若也是 0.9 GB，是池上限的一个大项 |
| 512 experts 驻留 VRAM | **708 MB** | 与 expert_cache 同思想，但只对 MTP 层（必须） |
| attention 走 DENSE（<2051 cells） | — | 投机细胞不碰 indexer state，位置重复处理时直接覆盖 |

**三个可借**：

| 借什么 | 怎么做 |
|---|---|
| **MTP 大投影 Q8_0** | 我们的 MTP 是否也量化了？若还是 bf16，0.9 GB 里有大头可压 |
| **MTP 独立 K/V** | 他们 MTP 有 `own K/V`（不与主模型共享）⇒ 主模型的 KV 池不被 MTP 污染 |
| **DENSE attention over seen cells** | 短线（<2051 cells）不用稀疏索引 ⇒ 省一套 indexer 状态 |

### 2.12 `prefill.cpp`：主干是 MoE 专用（**dense 借不到**）

**文件**：`src/prefill/prefill.cpp`（**7,763 行 / 510 KB / 230 个函数**）

**函数名分布**（前 40 个抽样）：

```
ple_batch_enabled / Context::run
gather_native / gather_native_group / gather_strata_q2      ← expert gather
swiglu / swiglu_quant / swiglu_scaled / down_row_scales     ← MoE FFN
tab_built / tab_fits / overread_bytes / whole_tiles         ← MMQ 表格
prep_group / experts / experts_native / quantize_act_native ← MoE 分组计算
```

**⇒ 大半是 MoE 的 fused kernel**（`moe_fused.cu` 126 KB、`moe_ws_gu_iq2.cu` 52 KB、`moe_mmq.cu` 37 KB）。**稠密模型没有这些路径。**

### 2.13 GEMM 走厂商库（**dense 的红海**）

**文件**：`src/prefill/gemm.cu`（78,659 B）

```cpp
#include <cublas_v2.h>
#if defined(__HIPCC__) && defined(STRATA_HIPBLASLT_AVAILABLE)
#include "hipblaslt_tuning.hpp"
#endif
```

⇒ **NVIDIA 走 cuBLAS、AMD 走 hipBLASLt**——不自研 dense GEMM。

**对我们（RTX 5080 / sm_120）的结论**：**我们的 prefill GEMM 也在 cuBLAS 里，没有自研空间**——这坐实了"dense prefill 是红海"的判断。

### 2.14 `wmma_gemm.cu` 的一条工程教训（**优化可能静默没跑**）

**文件**：`src/prefill/wmma_gemm.cu`（37,873 B，仅 RDNA3/gfx1100）

**原文（编译期宏陷阱）**：

> `STRATA_WMMA_GFX11` is defined by the BUILD (CMakeLists.txt, from CMAKE_HIP_ARCHITECTURES), **not inferred from
> compiler macros**: measured on this toolchain the HOST pass of a HIP compile does not define `__gfx1100__` but does
> define `__HIP_DEVICE_COMPILE__`, so a compiler-macro guard here **silently selected the "return false" stub** at the
> bottom of this file for the very symbol the engine links — **the WMMA path then never ran**, while the same file
> compiled with hipcc (as the probes do) took the real branch.

**⇒ 教训**：`#ifdef` 守卫选错分支 ⇒ **优化路径静默不生效，编译通过、运行正确、只是慢**。

**对我们的意义**：我们 23 个补丁里，有没有"编译期守卫选错导致优化没跑"的？**这是一个可查的方向**（比追 2.0 s 便宜）。

### 2.15 `KV_PREFETCH.md`：prefill 内逐层上传重叠（**prefill 4.1~5.3%**）

**文件**：`docs/KV_PREFETCH.md`（2,713 B）

**问题**（原文）：

> When long-context KV lives partly in system RAM, prefill uploads each attention layer's cached prefix.
> **Waiting for every upload on the compute stream leaves the GPU idle.**

**方案**：`STRATA_KV_PREFETCH=1`——**下一层的上传在独立 stream 上，当前层继续计算**；复用现有 staging pool，不新分配 KV buffer。

**实测（ABBA，两臂各 2 次观测，20 个 JSON 检查全过）**：

| Cold input | Serial prefill | Overlapped prefill | 改善 |
|---|---|---|---|
| 8K | 5.013 s | 5.025 s | 无 |
| **32K** | 16.989 s | **16.082 s** | **−5.3%** |
| **64K** | 32.604 s | **31.259 s** | **−4.1%** |

Profiling：**939 ms / 1,553 ms 的 serial KV-stage wait 移出关键路径**（copies 仍在执行，没消除）。decode 无加速。

**对我们的意义（重要）**：

```
我们的 restore 97% 在 prefill（§179）
我们的异步 demote 解决的是"挤出"侧的阻塞
KV_PREFETCH 解决的是"逐层上传"侧的阻塞 —— 不同层次
```

⇒ **如果我们的 restore 在 prefill 期间是"一层等一层"，这里能拿 4~5%**；如果已经是流水，收益为 0。**需读码确认**。

**它的诚实标注值得学**（原文）：

> - **The historical timings are NOT a measured speedup of this pure-upstream port.**
> - No claim of a pure-upstream GPU speedup or bitwise numerical parity yet.
> - **Keep draft** until pure-upstream long-context, cancellation, and image-history tests pass.

### 2.16 第三方对我们的实测（`bench/results/2026-10-04-community-4090-agents-vs-dense-27b/`）

**这是外部评测者（T-Crypt）在 RTX 4090 上对"Strata vs 我们的 NInfer 27B"的对比**，2026-10-04。

**双方配置**：

```
Strata : --max-context 262144 --kv q4_0 --resident-experts --expert-cache auto --prefill auto
         --spec 4 --spec-min-p 0.5 --pcie-frac 0.20 --mtp, conversation_cache_mib=0
NInfer : --max-context 262144 --kv-dtype rk4v4-e8 --spec mtp --draft-tokens 3
         --default-thinking-budget 4096 --max-concurrency 1
```

#### ① Recall（3 facts @ 10/50/90% 深度）—— **我们的 prefill 慢 2 倍**

| tokens | Strata（found / prompt tok/s / 秒） | **NInfer（我们）** |
|---|---|---|
| 55,586 | 3/3 / 3,494 / 17.3 s | 3/3 / **3,037** / 23.3 s |
| 117,153 | 3/3 / 3,904 / 31.3 s | 3/3 / **2,391** / **51.2 s** |
| **~199,500** | 3/3 / **3,833** / **53.7 s** | 3/3 / **1,857** / **110.2 s** |

**⇒ 199.5K token 的 prompt 速度：我们 1,857 vs 他们 3,833（差 2.06×）；TTFT 110.2 s vs 53.7 s**

**这是我们的最大短板，且有外部实测。**

#### ② 真实任务（3 个 ticket，Claude Code subagent，rubric 预先固定）

| task | Strata IQ2_XS | **NInfer 27B** |
|---|---|---|
| T1 Python config renderer | 42 | 35 |
| T2 Quickshell QML | **0（150 min 无编辑）** | 34 |
| T3 evidence write-up | 44（120 min） | 43（**62 min**） |
| **total /150** | **86** | **112** |
| 时限内完成 | 1/3 | **2/3** |

**⇒ 总分我们赢（112 vs 86），完成度也赢（2/3 vs 1/3）。**

#### ③ Prefix reuse—— **我们的最大优势**

| | Strata | **NInfer（我们）** |
|---|---|---|
| prompt tokens from cache | 17.5M / 54.0M（**32.4%**），938 req | **11.8M / 13.3M（88.5%）**，last 101 req |
| 一个日志轮 | `prompt 109780 = 2559 reused + 107221 read in 27966 ms` | 172,578 tokens，**172,343 from state cache**，first token **524 ms** |

**评测者结论（原文）**：

> Strata's decode and prompt speed were higher than NInfer's in every measurement here;
> **prefix reuse decided the elapsed time.**

**⇒ 这解释了为什么我们 decode 更慢（140 vs 173）但 wall time 快一倍（2m11s vs 5m21s）：我们复用 88.5%，他们每轮重读 70–110K token。**

**⚠ 口径注记（TELE 第二轮核实补正，必读——否则上表会被读重）**：

| # | 口径 | 含义 |
|---|---|---|
| ① | **recall 三档是全新 prompt 的冷读速率**（needle 零复用） | "2.06×" 与 P3-20 **同象限**（都是冷 prefill），是**外部印证靶点**，不是新方向 |
| ② | **复用率 88.5% vs 32.4% 被配置混杂** | Strata 侧 `conversation_cache_mib=0`（32 GB RAM 顶格**被迫关闭**）；样本量亦不同（**938 请求 / 54.0M** vs **101 请求 / 13.3M**）⇒ **等缓存条件下对方原始速率仍更高**；我方"首 token 524 ms @172K"是 10-04 时点实测成绩 |
| ③ | **任务总分 112 vs 86 的构成** | T2 对手 agent **150 分钟 0 edits**（34:0，不是我方能力优势）；共用任务质量 **78 vs 86 对方占优**；我方硬优势 = **T3 用时 62 vs 120 分钟** + **完成度 2/3 vs 1/3** |

**⇒ 结论修正**：这张镜子证明的是"**我们的 prefill 值得优化**"（②的等缓存条件下对方仍更快），
**不是**"我们已经赢了"（③的构成里有偶然性）。

#### ④ 三条可行动结论

| # | 结论 | 依据 |
|---|---|---|
| 1 | **我们的 prefill 是外部公认的短板**（199K 差 2 倍） | 3,833 vs 1,857 tok/s |
| 2 | **我们的 prefix reuse 是外部公认的优势**（88.5% vs 32.4%） | 同一报告 |
| 3 | **"复用率决定 wall time，decode 速度只决定体感"** | 评测者原话 |

⇒ **优化方向应该从"decode 提速"转向"prefill 提速"**（因为 prefill 差 2 倍，而我们 decode 已被 prefix reuse 补偿）。

### 2.17 同源关系：Strata 明确致谢 ninfer

**`docs/HOW_IT_WORKS.md:67-69`** 与 **`docs/DETAILS.md:1380`** 原文：

> Built with parts of llama.cpp / ggml (MIT). **Ideas from**
> [Splash](https://github.com/incoai/splash), **[ninfer](https://github.com/Neroued/ninfer)** and
> [HyperQwen](https://github.com/syv-ai/HyperQwen).

**⇒ Strata 公开承认借鉴 ninfer 系思路**（`Neroued/ninfer` 是上游本线谱系中的节点）。

**注意区分**：这里的 `ninfer` 指上游 `Neroued/ninfer`，**不是我们的 `paicat1/Ninfer-KVMem-Async`**。同源指的是"同一个上游谱系"，不是"借鉴我们"。

**另外**：`src/program/generate.cpp:10061` 有 `STRATA_VOLTA_BUILD backport (see docs/ and ninfer-flash-next-v100-backport)` —— 说明他们还从 ninfer 系 backport 过 V100 支持。

### 2.18 三项"我们这边是否踩坑"的静态核查（CB 独立取证，2026-11-03 补）

TELE 做了办公室侧静态核查，本报告独立复验，**两成立、一推翻**。

#### ① granule 圆整假设 —— **本报告 §2.6 撤回**（我方不存在该问题）

**抽样**（`refs/tancau-ninfer-kvmem-ring`，引擎源码真身，1,871 文件）：

```
cudaMalloc 全库：20 个文件 / 65 次调用
  其中 tools/*.cu 探针：        44 次（非生产路径）
       tests/*.cu：              5 次
       src/core/arena.cu：       2 次
       src/models/.../decoder_state.cpp：1 次
       src/ops/.../causal_cache/launch.h：1 次
  ⇒ src/ 生产路径仅 4 处
```

**且 arena 是既有设计**：

```
src/core/arena.cu       19,788 B
src/core/arena.h         6,655 B
src/core/host_kv_arena.cpp 30,605 B
src/core/host_kv_arena.h   10,528 B
```

⇒ **"每投影一次 cudaMalloc ⇒ 多占 19%"在我们引擎结构性不存在。**
**§2.6 的"改 arena"建议作废**（arena 已是在位设计）。

**残余**：granule 风险收窄到 **KV 池 bundle 预留 + workspace 分配**两处，且不是逐投影。

#### ② MTP 权重精度 —— **TELE 的判断被推翻，我们 10-09 就做完了**

**TELE 的依据**：`mtp.cpp L21/35/53` 出现 `DType::BF16` ⇒ "MTP 投影权重全 BF16"。

**实际读码**：

```cpp
// mtp.cpp:21  ← 这是 workspace 分配，不是权重
(void)layout.alloc(DType::BF16, {w.n, last});

// mtp.cpp:53  ← 这是中间结果 buffer，不是权重
Tensor packed = workspace.alloc(DType::BF16, {p.weight.n, columns});
```

**权重的真实类型是 `Weight::qtype`**（`src/core/weight.h`）：

```cpp
struct Weight {
    QType qtype = QType::Q4_G64_FP16;   // 默认 Q4，不是 BF16
    ...
};
```

**而 MTP 权重的实际 qtype，`scripts/recode_mtp.py` 头部写死了答案**：

> `recode_mtp.py -- recode an MTP head's **gguf_q4_0** tensors to **gguf_q8_0 (BIT-EXACT)** inside a NInfer v3 artifact.
>
> WHY：The Coder390 artifact declares its MTP head as `gguf_q4_0`, which the engine's format whitelist does
> not accept, so `--spec mtp` cannot load. **`gguf_q8_0` IS supported.**
>
> WHY IT IS BIT-EXACT：q4_0 block = fp16 `d` + 32 nibbles，value = (nibble − 8) × d；
> `(nibble − 8)` ∈ [−8, 7] 恰好落在 int8 范围 ⇒ 复制 scale 字节 + 存 int8 ⇒ **解码值逐位相同，零浮点运算**。

**⇒ 我们的 MTP 权重：`gguf_q4_0` → 已无损转 `gguf_q8_0`（2026-10-09，`scripts/recode_mtp.py` 519 行）。**

**所以"Q8 化空间成立"不成立**——已经 Q8 了。而且方向是反的：

```
Q8_0 → BF16 = +582 MiB（本仓 docs/_research/codebuddy-mtp-roadB-数据侧重打包.md:16 已算过）
```

**⇒ 这条与 embq4 同类：都是"没查已有工作，把已完成项当新机会"。**

#### ③ 编译期宏守卫陷阱 —— **干净负结果，此问关闭**

22 个补丁零 `#if` 引入 ⇒ `wmma_gemm` 式"优化静默没跑"结构性不可能。

**但保留一条通用纪律**：任何"优化开关"若靠 `#ifdef` 选分支，须有一条运行时日志证明该分支真的走到了。

---

## 三 技术的适用性汇总（我们是**稠密 27B**，按这个前提重排）

| # | 技术 | Strata 收益 | 对我们 | 理由 | 工作量 |
|---|---|---|---|---|---|
| 1 | **自适应投机窗口** | +7.88%（sm_120 greedy） | ✅ **可直接借** | 纯调度层，与模型无关 | 几十行 |
| 2 | ~~显存 granule 圆整~~ | — | ❌ **假设被否定（§2.18①）** | 我们走 DeviceArena（`src/core/arena.cu`），src 下 cudaMalloc 仅 4 处 | — |
| 3 | `STRATA_HC_Q8` | decode +2.5~9.5% | ✅ **可借（需确认我们有 hyper-connection）** | 8 位投影 → 更快且质量噪声级 | 中 |
| 4 | **pinned 前缀** | 常用前缀不驱逐 | ✅ **设计可借** | 我们有 prefix cache 但无钉住 | 中 |
| 5 | **实验固化** | bench 2,185 文件可回溯 | ✅ **已认可** | — | 1 天 |
| 6 | **DFlash2 实现要点** | +7.88% | ⚠ **机制可借** | cudaGraph + 双 stream + 8 层 K/V ring；但需 native drafter 头 | 大 |
| 7 | **KVA 晚层跳过** | prefill +11~28% | ⚠ **收益打折** | 收益主要在跳 MoE 半，**稠密无 MoE** | 大 |
| 8 | **expert_cache** | 16.2 ms/token 的 96% 暴露 | ❌ **不适用** | **稠密模型没有 expert** | — |
| 9 | ~~MTP 层 Q8 化~~ | — | ❌ **已做过（§2.18②）** | 我们 MTP 权重 10-09 已是 `gguf_q8_0`（`recode_mtp.py` 无损转码）；Q8→BF16 反而 +582 MiB | — |
| 10 | **KV Q8 的 MULTI 融合** | 多 token 一次 launch | ⚠ **可借** | 我们每步 append 一个 token，launch 开销累积 | 中 |
| 11 | `_fseeki64` / `MAP_HUGE_2MB` | Windows 32 位 fseek 陷阱 | ✅ **可查可借** | >2 GB pack 会静默错位 | 小 |
| 12 | ~~编译期守卫陷阱~~ | — | ❌ **负结果（§2.18③）** | 22 补丁零 `#if`，结构性不可能 | — |
| 13 | `prefill.cpp` MoE 主干 | — | ❌ **不适用** | 230 函数大半是 MoE fused kernel | — |
| 14 | `gemm.cu` | — | ❌ **无空间** | 走 cuBLAS/hipBLASLt，不自研 dense GEMM | — |
| 15 | **`KV_PREFETCH`（逐层上传重叠）** | **prefill −4.1~5.3% @32K/64K** | ✅ **可借（需读码确认我们是否已流水）** | 我们 restore 97% 在 prefill，与 demote 异步不同层次 | 中 |
| 16 | **第三方实测（2.16）** | — | ⚠ **这是镜子不是技术** | **我们 prefill 慢 2×（1,857 vs 3,833 @199K）；prefix reuse 赢（88.5% vs 32.4%）** | — |
| 17 | 同源关系（致谢 ninfer） | — | 📌 **谱系事实** | 上游 `Neroued/ninfer`，非本仓；同源不同实现 | — |

## 四 建议（**2026-11-03 收敛版，与 §八 一致**）

> **⚠ 本节已按 §2.18 的独立取证重排**：原"第一优先 granule 圆整核查"**已撤回**——
> 我们引擎走 `DeviceArena`（`src/core/arena.cu`），`src/` 下 `cudaMalloc` 仅 4 处，
> "逐投影 malloc 吃 19%"结构性不存在。

### 第一优先：自适应投机窗口（+7.88%，sm_120 同架构实测）

```
现状：--draft-tokens 4（固定值）
借鉴：EMA 成本（kCostAlpha=0.1）+ 接受率校准表（kCalDecay=0.995）
     + 4 桶先验（kPriorQ={0.75,0.88,0.93,0.96}，按 match <6/<12/<24/≥24 分级）
     + stale 重测（kStaleRounds=300）
成本：纯调度层，不改 kernel、不改模型
```

**为什么排第一**：这是**唯一有 sm_120 实测数字的代码级可借项**（+7.88% greedy），而我们 `--draft-tokens` 是固定值。

### 第二优先：`KV_PREFETCH` 的读码确认（不是直接抄）

```
先回答一个问题：我们的 restore 在 prefill 期间是否"一层等一层"？
  是  ⇒ 可拿 prefill −4~5%（Strata 实测 −5.3% @32K / −4.1% @64K）
  否  ⇒ 已是流水，收益为 0，此项关闭
成本：读码 0（家里）
```

**注意**：这与我们的异步 demote **不同层次**——demote 异步解决"挤出侧"，KV_PREFETCH 解决"逐层上传侧"。

### 第三优先：`STRATA_HC_Q8` 式投影量化（+2.5~9.5%）

前提：确认我们的模型是否有 hyper-connection / 多流残差结构（**未查**）。

### 第四优先：pinned 前缀 + 实验固化

### 已撤出（勿再排期）

| 项 | 原因 |
|---|---|
| ~~granule 圆整核查~~ | §2.18① 假设否定：arena 是在位设计 |
| ~~MTP 层 Q8 化~~ | §2.18② 已做过：权重 10-09 已 q8_0 |
| ~~编译期宏守卫排查~~ | §2.18③ 22 补丁零 `#if` |

### 明确不做

- **expert_cache**：稠密模型无 expert
- **KVA**：收益依赖跳 MoE 半，稠密下打折严重；但**记录其洞察**（近似位置的后层 output 没有消费者）

## 五 边界（本次未覆盖）

| 项 | 状态 |
|---|---|
| `src/kernels/kv_q4.cu` / `kv_q8.cu` | 未读（KV 量化内核，118 个 cu 文件） |
| `src/split/` | 只有 CMakeLists（11 KB），源码在别处（层拆分实现未定位） |
| `apps/host`（934 文件） | 未读（host 侧调度） |
| Metal / SYCL 后端 | 未读 |
| `tools/dflash2/` | 已读 README（**离线评测工具**，非生产实现；生产集成在 app 层） |
| KVA 的 `h_expert` 计算 | 只读了结论，未读 `tools/routing_kfold.py` |

---

## 六 引用

- 全库：`refs/strata/`（5,681 文件 / 87.4 MB，tarball API 拉取，`main` @ v0.2.10）
- `refs/strata/docs/KVA.md`（190 行，KVA 架构与实测）
- `refs/strata/include/strata/prefill/kva.hpp:1-64`（KVA 实现常量）
- `refs/strata/include/strata/core/expert_cache.hpp:4-28`（MoE offload 数字依据）
- `refs/strata/include/strata/core/conversation_cache.hpp`（pinned / parking / ConversationKv）
- `refs/strata/src/spec/draft_policy.cpp:1-30`（自适应窗口常量）
- `refs/strata/src/spec/suffix_drafter.cpp:1-40`（3-token 哈希 lookup）
- release notes v0.2.10（DFlash2 默认 + 实测 +7.88% @sm_120）

---

## 七 补读记录（每次续读追加）

| 日期 | 补读内容 | 结论 |
|---|---|---|
| 2026-11-03 #1 | `docs/KVA.md` + `kva.hpp` | KVA 机制：近似晚层 + 2048 尾；收益主要为跳 MoE 半 |
| 2026-11-03 #2 | `expert_cache.hpp` | MoE offload；663.6 MB/token、96% 暴露；**稠密不适用** |
| 2026-11-03 #3 | `conversation_cache.hpp` | pinned 前缀 / 整会话 parking / k_scale 独立存 |
| 2026-11-03 #4 | `draft_policy.cpp` + `suffix_drafter.cpp` | 自适应窗口（EMA+校准表+4 桶）；3-token 哈希 lookup |
| 2026-11-03 #5 | `native_dense.cpp` | **2 MiB granule 圆整（+19%）** + `STRATA_HC_Q8`（+2.5~9.5%） |
| 2026-11-03 #6 | `dflash2.cpp` | cudaGraph + 双 stream fork/join + 8 层 K/V ring |
| 2026-11-03 #7 | `pinned.cu` | **pinned host arena**（非 KV 前缀钉住）；`_fseeki64` / `MAP_HUGE_2MB` / SharedArena |
| 2026-11-03 #8 | `kv_q8.cu` | 64 值一组 + K/V 分离 + fp16 scale + `MULTI`（多 token 一次 launch） |
| 2026-11-03 #9 | `mtp.hpp` + `mtp.cpp` | MTP 接受率 0.89/0.86/0.85；**层占 ~0.9 GB**；大投影 Q8_0；独立 K/V；DENSE<2051 |
| 2026-11-03 #10 | `prefill.cpp`（7,763 行） | 230 函数大半是 MoE fused kernel；**稠密借不到** |
| 2026-11-03 #11 | `gemm.cu` + `wmma_gemm.cu` | NVIDIA 走 cuBLAS（无自研空间）+ **编译期守卫致优化静默没跑的教训** |

---

## 八 总结论（**以 §十 为准**；本节为 2026-11-03 三方收敛版）

> **⚠ 自洽性说明**：本节此前含 4 条"可借项"，其中 granule 圆整、MTP Q8 化、编译期守卫排查三条
> 已被 §2.18 的独立取证推翻/关闭，衰减计数第三臂被 §10.3 判定对象不同。
> **本节已按 §十 重写；旧表不再保留，避免"新旧结论并存"。**

### 8.1 净可借清单（2 条代码级 + 1 组方法论 + 1 条架构判断）

| # | 项 | 收益 | 状态 |
|---|---|---|---|
| **1** | **自适应投机窗口**（`draft_policy.cpp`：EMA 成本 + 接受率校准表 + 4 桶先验 + stale 重测） | **+7.88%**（RTX PRO 5000 / sm_120 greedy） | ✅ **唯一无争议的代码级可借项**；我们 `--draft-tokens 4` 是固定值 |
| **2** | **`KV_PREFETCH`（prefill 内逐层上传重叠）** | **prefill −5.3% @32K / −4.1% @64K** | ⚠ 需读码确认我们是否已是流水；若是，收益为 0 |
| **3** | **测量与文档基础设施**（冻结语料 / 量化标尺 / KL 噪声底 / 实测后否决目录 / AGENTS.md 对外闸 / 实验固化） | 不直接提速 | ✅ 与架构无关，可直接并入 P3-20 执行细则 |
| **4** | **架构判断：评分子系统是稠密模型的必需件** | — | ✅ **本轮最重要的产出**（见 §10.2） |

### 8.2 已撤回 / 已关闭（4 条，**勿再引用**）

| 项 | 结论 | 依据 |
|---|---|---|
| ~~granule 圆整（每投影 malloc 多占 19%）~~ | **假设否定**：我们走 `DeviceArena`，`src/` 下 `cudaMalloc` 仅 4 处 | §2.18① |
| ~~MTP 层 Q8 化空间~~ | **已做过**：MTP 权重 2026-10-09 已由 `gguf_q4_0` 无损转 `gguf_q8_0`；Q8→BF16 反而 **+582 MiB** | §2.18②（`scripts/recode_mtp.py`） |
| ~~编译期宏守卫陷阱~~ | **干净负结果**：22 个补丁零 `#if`，结构性不可能 | §2.18③ |
| ~~衰减计数评分第三臂~~ | **对象不同**：他数 MoE expert，我们数 KV 页 | §10.3 |

### 8.3 显式挂起（3 条，**前置未满足，不排期**）

| 项 | 挂起理由（前置条件） |
|---|---|
| **CUDA 13 双 API**（`cudaMemcpyBatchAsync` / `cudaMemcpyFlagPreferOverlapWithCompute`） | **前置 = 我们自己的「提交 vs 传输」占比 profile**。Strata 实测：提交段 **−82.7%**（0.0936→0.0162 ms），但**端到端总传输只 −1.3%**、生成速度 30.3 vs 30.0 无增益；作者原文 *"This evidence does not justify changing the default"*。⇒ 只救"提交占比大"的负载，我们的占比未测 |
| **SSD 第三层**（device → RAM → SSD） | **前置 = 页访问频率分布剂量学**（可零机时离线算，与 A3 离线 trace 回放合流）；SSD ~7 GB/s vs DDR5 ~90 GB/s 差 12×，只适合真冷页 |
| **精度梯度实验**（Q2/IQ2 × 评分失真） | **前置 = 容器量化档可用性**——P1-1 教训：`--embedding-q4` 被容器格式干净拒绝；档位不可用则实验无对象 |

### 8.4 借不到的（架构差异，非"没想到"）

```
KVA 晚层跳过       收益主要来自跳 MoE 半 —— 稠密没有
expert_cache       663.6 MB/token —— 稠密没有 expert
prefill.cpp 主干   230 函数大半是 MoE fused kernel
gemm.cu            走 cuBLAS / hipBLASLt，dense GEMM 无自研空间
```

### 8.5 一个必须承认的事实

> **Strata 的 38,619 stars 与 26 天 20 个版本，主要建立在「MoE + 多卡 + 跨平台」这三件事上。**
> **我们是「稠密 27B + 单卡 16 GB + Windows」，这三件事都不在它的优化射程内。**

**⇒ 继续深挖 Strata 的边际收益已接近零**（核心模块全部读完：KVA / expert_cache / conversation_cache / MTP / prefill / gemm / spec / dflash2）。


## 九 与 TELE 报告（`调研-STRATA-可借鉴点分析-TeleAgent-20261103.md`）的交叉印证

TELE 读文档、本报告读代码，两者互补。

### 9.1 一致确认（三条）

| 项 | TELE | 本报告（代码级） |
|---|---|---|
| **同源关系**：Strata 致谢 ninfer | ✅ 发现（HOW_IT_WORKS L67-68） | ✅ **核实为真**，并补：`DETAILS.md:1380` 同款；指**上游 `Neroued/ninfer`**，非本仓 |
| **KV 分层驻留**（`--kv-streaming` / `--kv-resident` / `--kv-grow`） | ✅ 文档读到 | ✅ 代码侧对应 `conversation_cache.hpp` 的 `ConversationKv` + `pinned` + parking |
| **制度化基础设施**（冻结语料 / 12 条检查 / 量化标尺 / 否决目录） | ✅ 详细列出 | ✅ 印证：`bench/results/` **2,185 文件 / 21.9 MB**，按日期+配置分目录 |

### 9.2 本报告补充（TELE 未覆盖的四条）

| # | 补充 | 为什么重要 |
|---|---|---|
| 1 | **`KV_PREFETCH.md`**：prefill 逐层上传重叠，实测 −5.3% @32K | TELE 未提；这是**唯一直接针对 prefill 的现成方案** |
| 2 | **第三方对我们的实测**（2.16） | **外部视角：我们 prefill 慢 2×、prefix reuse 赢 88.5%**——比任何内部讨论都硬 |
| 3 | ~~`native_dense.cpp` 的 granule 圆整~~ | **已撤回**（§2.18① 我们走 DeviceArena） |
| 4 | **`mtp.hpp`：MTP 层占 ~0.9 GB + Q8_0 投影** | 我们的 MTP 若未量化，有大头可压 |

### 9.3 本报告修正（一条）

| TELE 的判断 | 修正 |
|---|---|
| "驻留评分器（衰减路由计数）是我们 SCORE=0/1 之外的天然第三对照臂" | ⚠ **需区分**：他们的评分器是 **MoE 路由计数**（哪个 expert 热），我们的 SCORE 是 **KV 页内容评分**——**不同对象**，不能直接当第三臂 |

### 9.4 联合结论

> **两个报告合起来，Strata 对我们的价值从"技术借鉴"变成"一面镜子"：**
>
> **技术层面**：净可借 2 条（自适应窗口 +7.88% / KV_PREFETCH −4~5%），都不是大提速。
>
> **镜子层面（更重要）**：第三方实测告诉我们——**我们的 decode 不慢（有 prefix reuse 补偿），prefill 才是短板（差 2 倍）**。
> 这一个月我们一直在追 decode 侧的 2.0 s，而外部数据显示真正该修的是 prefill。
| 2026-11-03 #12 | `HOW_IT_WORKS.md:67-69` + `DETAILS.md:1380` | **致谢 ninfer 系**（同源关系实锤，指上游 Neroued/ninfer） |
| 2026-11-03 #13 | `KV_PREFETCH.md` | **prefill 内逐层上传重叠：−5.3% @32K / −4.1% @64K**；诚实的"未在纯上游验证"标注 |
| 2026-11-03 #14 | `bench/results/2026-10-04-community-4090-agents-vs-dense-27b/` | **第三方对我们的实测：prefill 慢 2×（1,857 vs 3,833 @199K），prefix reuse 赢（88.5% vs 32.4%），总分 112 vs 86** |
| 2026-11-03 #15 | `refs/tancau-ninfer-kvmem-ring`（引擎真身）+ `src/core/arena.cu` | **granule 假设否定**：src 下 cudaMalloc 仅 4 处，arena 是既有设计 ⇒ §2.6 撤回 |
| 2026-11-03 #16 | `mtp.cpp` + `weight.h` + `scripts/recode_mtp.py` | **MTP 权重是 `gguf_q8_0`（10-09 由 q4_0 无损转码）**，不是 BF16 ⇒ TELE 的"Q8 化空间"推翻；Q8→BF16 反而 +582 MiB |
| 2026-11-03 #17 | 22 个补丁 `#if` 扫描 | 零命中 ⇒ 宏守卫陷阱关闭 |

---

## 十 与 TELE 联合攻关文档的交叉核对（2026-11-03 第二轮）

### 10.1 TELE 三条静态核查的复验结果

| 项 | TELE 判定 | CB 复验 | 差异 |
|---|---|---|---|
| ① granule 圆整 | 假设否定（走 DeviceArena） | ✅ **成立**（独立计数：src 下 4 处 cudaMalloc） | — |
| ② MTP 权重 | 实锤 BF16，Q8 化空间成立 | ❌ **推翻**：`DType::BF16` 是 workspace；权重 `qtype` 已是 `gguf_q8_0` | **误读 1 处** |
| ③ 宏守卫陷阱 | 干净负结果 | ✅ 成立 | — |

### 10.2 TELE 最有价值的一条：**稠密模型评分子系统是结构性必需**

原文（TELE）：

> STRATA 不需要引擎侧内容评分，是因为其模型原生 **QSA indexer** 在做选择。
> **稠密模型没有 indexer，选择必须由引擎合成——这正是 Ninfer-KVMem 评分子系统存在的结构性理由。**

**这条极重要，本报告完全采纳并建议记入构建史**：

```
MoE 模型（Strata）  → attention 里有 indexer，稀疏选择是模型自带的
稠密模型（我们）     → 没有 indexer，KV 页选择必须由引擎侧合成
                    ⇒ 评分子系统不是"可选优化"，是"没有它就没有选择"
```

**推论**：P3-20 的"评分要不要留"这个问题问错了——**评分必须留，要问的是"用什么信号、花多少预算"**。

### 10.3 TELE 的自我修正（B2 撤回）—— 也成立

他说撤回"衰减计数评分第三臂"：**稠密模型 resident 页每步无条件被读，无可计数之物**。

⇒ 这条与 10.2 一致：Strata 的"路由计数"是给 MoE expert 用的，我们的"页评分"是给 KV 页用的，**对象与触发条件都不同**。

### 10.4 两报告合并后的最终可借清单（3 条，不是 4 条）

| # | 项 | 收益 | 状态 |
|---|---|---|---|
| 1 | **自适应投机窗口** | +7.88%（sm_120 实测） | ✅ 唯一无争议的代码级可借项 |
| 2 | **KV_PREFETCH（逐层上传重叠）** | prefill −4.1~5.3% | ✅ 需读码确认我们是否已流水 |
| 3 | **pinned 前缀 / 实验固化 / 冻结语料 / 量化标尺** | 测量与文档基础设施 | ✅ 与架构无关，可直接并入 P3-20 |

**撤回的两条**：granule 圆整（不存在）、MTP Q8 化（已做过）。

### 10.5 一句判断

> **两轮交叉核查（先我读代码、后 TELE 读文档+静态核查）之后，Strata 对我们的净技术价值收敛到 2 条代码级 + 1 组方法论。**
>
> **但最有价值的产出不是技术，是 10.2 那条架构判断：评分子系统是稠密模型的必需件，不是可选项。**


---

## 十一 上游 KVMem v0.19 对照（同谱系，优先于 Strata）

> 本节为本轮新增，原为独立报告 `调研-KVMem上游v0.19与prefill基准修正-CB-20261103.md`，现并入本文。
> 克隆位置：`refs/kvmem-kvmem-main/`（821 文件 / 17.1 MB，`master` @ 2026-11-03）。

### 11.0 版本差

| 项 | 我们谱系文档（10-29） | 上游现状 |
|---|---|---|
| 版本 | 0.18.0 / 0.18.1 RC1 | **v0.19.1（10-31）** |
| release | — | v0.19.poly1（10-30，PolyStrata · RTX 50）<br>v0.19.0-rc1（10-27，NInfer · RTX 20/30/40/50 · V100） |
| 今日提交 | — | `17a19ee` **native FP8 prefill optimization**（PR #250）<br>`1e4b50` **arbitrate NInfer ngram copy yield**（PR #254） |

**活跃分支里有 NInfer 专项**：

```
feat/ninfer-dflash2-layer-pipeline
feat/ninfer-dflash2-quantized-heads
feat/ninfer-cross-owner-checkpoints
feat/selective-kv-refresh
codex/ninfer-low-precision-patches-20261102
```

### 11.1 **prefill 基准修正（本轮最重要）**

### 2.1 三个基准放在一起

| 实现 | 模型 | 上下文 | prefill | 出处 |
|---|---|---|---|---|
| **llama.cpp + KVMem（ISTA）** | **dense 27B IQ3_S** | 260,012 | **197 tok/s** | `prefill-harvest-optimization.md:23` |
| **我们（NInfer 27B）** | **dense 27B** | 199,500 | **1,857 tok/s** | 第三方实测（RTX 4090，10-04） |
| **qw3 FP8 融合实现** | dense 27B | — | **1,849.77 tok/s** | `kvmem_qw3/docs/kvmem_fp8_performance_benchmark_20260725.md`（上游引用） |
| Strata | **MoE** Qwen3.8-Flash-Next IQ2_XS | 199,500 | **3,833 tok/s** | Strata `bench/results/…dense-27b/` |

### 2.2 结论

```
我们 1,857  vs  llama.cpp 197   = 9.4×（同 dense 27B，同属 KVMem 谱系）
我们 1,857  vs  qw3 融合 1,850  = 1.004×（持平）
Strata 3,833 是 MoE 架构优势（激活参数少），不是引擎优势
```

**⇒ 撤回「我们 prefill 慢 2×」**：那是拿 dense 27B 比 MoE，架构不同，不可比。

**⇒ 我们的 prefill 在 dense 27B 上已接近该谱系的极限**（与 qw3 的 FP8 融合实现持平）。

### 2.3 上游对"prefill 2×"的诊断（llama.cpp 侧，不适用我们）

`prefill-harvest-optimization.md:23-30` 原文：

> That profile is **host idle plus thousands of tiny ggml launches**, not FlashAttention saturating HBM over a 60k window.
>
> The KVMem-local bottleneck is harvest: `process_ubatch` launches the graph asynchronously, then
> `llama_kvmem_harvest_ubatch` **host-syncs the capture backend**, D2D-snapshots with a **host snap wait**,
> converts F16→F32→F16, and issues **~256 synchronous 64 KiB `pwrite`s plus `drop_page_cache` on the compute thread**.

**⇒ 这是 llama.cpp 的 harvest 路径 host-wait 阻塞 ubatch overlap，与我们的引擎无关。**

**但有一条通用教训值得记**：**"host 端等待"会让 ubatch 之间无法 overlap**——若我们的 restore/demote 在 prefill 里有类似 host-wait，同样会阻塞。

---

### 11.2 三层 KV 分层（**容量天花板的终极解**）

### 3.1 三个参数（两后端统一）

```text
--kvmem-host-mib H --kvmem-disk-path PATH --kvmem-disk-mib D
```

### 3.2 八个机制（`active-kv-tiering.md`）

| 机制 | 内容 |
|---|---|
| **单一所有权** | 同一份原生 KV 只有一套记录；活动→闲置移动所有权，保留 RAM/SSD 位置 |
| **增量恢复** | 恢复只读实际选中的内容，**不再生成全量 KV 冷快照** |
| **配额先于写入** | 先取得目的配额，**完成后才发布新副本、释放旧副本** |
| **读租约** | 读租约保留内容及配额，即使原会话已删除 |
| **失败不丢副本** | 磁盘满/读失败/取消都不能提前丢弃唯一有效副本 |
| **碎片显式拒绝** | 连续记录无法分配时明确拒绝，**不超配** |
| **小记录打包** | 按 **256 KiB / 64 条**打包，相邻区间合并写入 |
| **存储 worker 不碰 GPU** | 不执行 GPU API、不拥有需 CUDA 析构的对象 |

**边界（原文）**：完整 K/V（含**量化 scale 和 MTP KV**）都可离开 RAM；**活跃 mean-K 留在 RAM**；H/D 都**不是**进程 RSS 限制（OS 文件缓存另计）。

### 3.3 验证数据（RTX 5060 Ti，逐对交替 + 95% 单侧上界）

| 对照 | 配对数 | 中位数 | 95% 上界 |
|---|---|---|---|
| ninfer 原引擎 → 累计 RAM（short-0） | 7 | **−0.101%** | +0.569% |
| ninfer 原引擎 → 累计 RAM（continue-0） | 7 | **−0.159%** | +0.934% |
| **llama 260K 长上下文 → 最终 RAM** | 7 | **+2.476%** | +4.150% |

**⇒ RAM 层几乎零成本（±0.1%）；SSD 层在 260K 下 +2.5%。**

**且验证覆盖我们的配置**：原文 *"ninfer 覆盖 C1/C2/C8、RK8V4/MTP3/CUDA Graph"*。

---

### 11.3 与 Strata 对比：哪个更值得学

| 维度 | **kvmem/kvmem（上游）** | Niko1221/Strata |
|---|---|---|
| 谱系 | **同一套代码（我们的上游）** | 同赛道竞品（借鉴过 ninfer 思路） |
| 模型 | **dense 27B（和我们一样）** | MoE Qwen3.8-Flash-Next |
| 配置 | **RK8V4 / MTP3 / CUDA Graph（和我们一样）** | 自研 QSA |
| KV 分层 | **三层（GPU↔RAM↔SSD），已验证** | 两层 + SSD 文档 |
| prefill 优化 | **有专项 68 KB 文档 + 5 stage** | KVA（MoE 专用） |
| 验证方法学 | **95% 单侧上界 + 逐对交替** | ABBA |
| 可借鉴 | **SSD 第三层 / 所有权机制 / 打包策略** | 自适应窗口 / KV_PREFETCH |

**⇒ 上游更值得学：同谱系、同模型、同配置、有实测。**

---

### 11.4 可借鉴清单

| # | 项 | 收益 | 前置 |
|---|---|---|---|
| **1** | **三层 KV（RAM↔SSD）** | 容量天花板解，代价 **+2.5%**（260K） | 需实现 `HostKvStorage` + 租约 + 配额 |
| **2** | **小记录打包（256 KiB / 64 条）** | 减少 SSD 随机写 | 零（策略） |
| **3** | **单一所有权 + 增量恢复** | 避免全量冷快照 | 设计层 |
| 4 | **prefill host-wait 检查** | 若有类似阻塞，可拿 overlap | 读码（零） |
| 5 | 上游 v0.19.1 的 FP8 prefill | 未知（今日刚合） | 需读 PR #250 |

---

### 11.5 边界

- 192 篇 docs 只精读 4 篇（tiering / validation / prefill / retrieval-stagein）
- v0.19.1 的 FP8 prefill（PR #250）尚未读实现
- 三层 KV 的代码未读（只有文档 + 验证记录）
- 未在实机验证任何数字

---

### 11.6 引用

- `refs/kvmem-kvmem-main/docs/active-kv-tiering.md`（82 行）
- `refs/kvmem-kvmem-main/docs/active-kv-tiering-validation-20261010.md`（167 行）
- `refs/kvmem-kvmem-main/docs/prefill-harvest-optimization.md:23-30`（prefill 诊断）
- `refs/kvmem-kvmem-main/docs/retrieval-stagein-optimization.md`（247 行，PR 0–3 landed）
- `refs/kvmem-kvmem-main/docs/dflash2-kvmem-integration.md`（177 行，含 16 GB profile）
- GitHub API：v0.19.1 / PR #250 / PR #254 / 分支列表

---

## 十二 DFlash2 可行性修正（**推翻 10 月「无法加载」的结论**）

> 2026-11-03 追加。本节推翻构建史 §184.5 L4466 的结论，并给出可执行的验证路径。

### 12.1 10 月的算式错在哪

构建史 §184.5 L4466 原文：

> DFlash2 头：**无该件**。按 `dflash2_inventory.py` 逐张量算得 **2,118,708,560 B ≈1.97 GiB**
> （比 MTP iq4_nl 多 1.75 GiB）⇒ 推算池上限为负（**12.6 + 1.97 = 14.6 GiB** 已超可用），**无法加载**。

**错误**：`12.6` 是「**MTP 配置下**的总占用」。而 MTP 与 DFlash2 **互斥**（见 12.2），
不该把 MTP 的占用加到 DFlash2 头上。

```
错误算式：12.6 + 1.97 = 14.6        ← MTP 与 DFlash2 并存
正确算式：12.6 − 0.9（MTP）+ 1.97 = 13.67
```

**⇒ 10 月多算了 0.9 GiB，很可能因此误判为「无法加载」。**

### 12.2 互斥是引擎文档明写的

`origin/engine-main:src-tree/fusion-engine-src/docs/maintainer/dflash.md:3-7` 原文：

> NInfer implements DFlash and DFlash2 as **optional components** of the Qwen3.5 model.
> Their private config and bindings select the stored weights;
> **startup chooses one backend, draft width and proposal head.**

**⇒ 「startup chooses one backend」= 运行时只选一个，不并存。**

**Bonsai 线的实证**（`paicat1/Bonsai-27B-NInfer-kvmem` 的 `ninfer_launcher_profiles.json`）：

| 档名 | spec | kv | ctx | **kvcap** |
|---|---|---|---|---|
| **起服-dflash档** | **dflash2** | k8v4 | 256k | **17,920** |
| **备用-MTP档** | **mtp** | k8v4 | 256k | **17,920** |
| 省显存-无视觉 | dflash2 | k8v4 | 256k | 17,920 |
| 180k k8v4 关视觉 | d7 | k8v4 | 180k | 180k |

⇒ **`dflash2` 与 `mtp` 是两个独立档**；**两者的 kvcap 都是 17,920**（不是 58,368）。

**⇒ 池不必是 58,368——Bonsai 线本来就是「小池 17,920 + host 16 GiB 镜像」的配置。**

### 12.3 引擎实现早已存在

`origin/engine-main` 的 DFlash2 实现（完整，非空缺）：

```
src/models/qwen3_5/load/dflash.cpp + dflash2.cpp
src/models/qwen3_5/execution/draft.cpp（44 KB）
src/models/qwen3_5/program/storage/draft_context.cpp
src/ops/attn_input_proj/q8/q8_dflash2_attn_input.cu (+_unified)
src/ops/linear_swiglu/q8/q8_dflash2_linear_swiglu.cu (+_unified)
src/ops/common/dflash_rope.cuh
tests/.../test_engine_dflash2_real.cpp
docs/maintainer/dflash.md（317 行完整规格）
```

**27B DFlash2 几何**（`dflash.md` 表）：

```
Hidden width H    5120        Draft layers     5
Intermediate      17408       Target block IDs [5,19,33,47,61]
Sliding window    2048        Selector         Top-16, rank 256
Conv              Two taps, group width 16
```

**⇒ 引擎侧无需改动；缺的只是容器内的 `dflash2/` 组件。**

### 12.4 头体积：三个口径必须分清

| 口径 | 值 | 说明 |
|---|---|---|
| HF 的 GGUF `Q4_K_M` | **1.065 GB**（1,143,006,816 B） | 只有 3 档：BF16 3.595 / Q8_0 1.915 / Q4_K_M 1.065 |
| 构建史算的「Q8 容器」 | **1.97 GiB**（2,118,708,560 B） | 按 `dflash2_inventory.py` 逐张量累计 |
| **Q4_K_M 转容器后的估算** | **约 1.4~1.6 GiB** | 待 `dflash2_inventory.py` 实测确认 |

**MoE 版（Strata 用的）更小，但我们不能用**：

```
Qwen3.8-Flash-Next-DFlash2-Q4_K_M.gguf   0.337 GB
Qwen3.8-Flash-Next-DFlash2-Q8_0.gguf     0.607 GB   ← 用户看到的「0.7 G」接近这档
```

`docs/TERMINAL_LAUNCH.md:98`：**「`dflash2` is for Qwen3.8-Flash-Next only」** ⇒ 绑定 MoE，不适用 dense 27B。

### 12.5 可行性判断

| 配置 | 池 | DFlash2 头 | MTP | 判定 |
|---|---|---|---|---|
| 10 月假设 | 58,368 | 1.97 + 12.6（含 MTP） | 加载 | ❌ 14.6 GiB，超 |
| **修正后（Q4_K_M）** | **17,920** | **1.4~1.6** | **不加载** | ✅ **可能装下** |
| 修正后（Q8） | 17,920 | 1.97 | 不加载 | ⚠ 需算 |

**⇒ 「Q8 换 Q4_K_M」可行，前提是：**

```
① 池降到 17,920（Bonsai 的「起服-dflash档」配置）
② 确认引擎用 dflash2 时不加载 MTP（dflash.md 已写，NInfer 侧待实测）
③ 容器转码：Q4_K_M GGUF → .ninfer 的 dflash2/ 组件
```

### 12.6 收益预期（上游实测，非外推）

`refs/kvmem-kvmem-main/docs/dflash2-kvmem-integration.md`（RTX 5060 Ti，16 GB）：

| 阶段 | MTP3 | DFlash2-5 |
|---|---|---|
| 长文本 | 54.69 | **73.09（+33.7%）** |
| 图像 | 63.23 | **81.63（+29.1%）** |
| 代码+thinking | 72.50 | **83.07（+14.6%）** |

**显存代价**：MTP3 13,327 MiB → DFlash2-3 14,669 MiB（**+1.31 GiB**，该实测是「MTP objects unchanged」的配置）。

**⚠ 边界**：上游 Task 1 是 **13K token 负载**（远小于 36,864 池），**未触发换页** ⇒ 长上下文场景的外推**未验证**。

### 12.7 下一步（三条，全在 mac 上可做）

| # | 动作 | 机时 | 产出 |
|---|---|---|---|
| **1** | 跑 `dflash2_inventory.py` 算 **Q4_K_M 转容器后**的体积 | 0 | 决定「装不装得下」 |
| 2 | 若 ≤1.6 GiB ⇒ 按 Bonsai「起服-dflash档」（kvcap 17,920 / host 16 GiB）起一次 | 1 晚 | 实测 decode |
| 3 | 判据：**长上下文（>100K）decode 是否仍净收益**（换页成本要算进去） | 同晚 | 分场景结论 |

### 12.8 一句话

> **DFlash2 从来不是「装不下」，是「按错的池算 + 加了不该加的 MTP」。**
>
> **引擎已实现、容器可转码、Bonsai 线已有可用配置；缺的只是一次 Q4_K_M 转码 + 一晚实测。**

---

## 十三 本仓对上游建议的落地状态 + pinned 前缀分析（2026-11-04 追加）

### 13.1 六条建议的实际处理

| # | 建议 | 本仓动作 | 状态 |
|---|---|---|---|
| 1 | 自适应投机窗口 +7.88% | **早已实现**（`mtp_adaptive.h`，`kAdaptiveMtpMaximumDrafts=15`）；**§205 实测判死**：准入预算要 5.06–5.29 GiB，16 GB 卡给不出（avail 3.6） | ❌ 关闭 |
| 2 | KV_PREFETCH（逐层重叠） | 核验确认**已是逐层事件流水**（`execution/text.cpp:1223` `cudaStreamWaitEvent(stream, layer_ready_[layer], 0)`） | ⚠ 未测剩余收益 |
| 3 | DFlash2 容器转码 | **§203 已落地**：SWIFT-1.5 + z-lab Q4_K_M 起服成功，接受率 17–20%，2.2× | ✅ 完成 |
| 4 | pinned 前缀 | 构建史仅有 `pinned` **host arena**（非 KV 前缀钉住）；核验文档明写「未见钉住保留策略」 | ⚠ 未做（见 13.2） |
| 5 | 三层 KV（RAM↔SSD） | 未推进（128 GB 内存，SSD 层无收益且伤盘） | ⛔ 主动放弃 |
| 6 | 实验固化（件 sha + 全参数 + 补丁链） | **无机制**，且已出事故：§200 `RestoreExe` 默认值陷阱把现役件错置成 RC6（35D9E6B1），生产件应为 RC2（9453FFC6） | ⚠ 缺口 |

**附加**：B 线预登记文档（286 行）已被本仓（§201）判定「修订完成前不得直接作为实验底稿」——
其 6.1 通道拆分与行动 #2 矩阵写于甲-0b 步级判读之前，且信号层修复①已被源码否定（D2）。

### 13.2 pinned 前缀：作用、本仓现状、收益条件

#### ① Strata 的定义（`conversation_cache.hpp` 原文）

> `pinned` … **the read-only prefix many suffix queries branch from, so retention never evicts it**
> (conv_cache.hpp) and a parked conversation holding it stays parked.
> A run-time mark only: it is not in the session file.

**⇒ 标记「只读共享前缀」，retention 永不驱逐。**

#### ② 解决的问题

多轮会话每轮的新请求都是「旧前缀 + 新内容」：

```
第 1 轮： [系统提示 2.5K] + [用户1] + [助手1]
第 2 轮： [同一前缀] + [用户2]
第 3 轮： [同一前缀] + [用户3]
```

**池压力把前缀驱逐 ⇒ 下一轮要从头 prefill 整条历史。**

#### ③ 本仓已有半个机制：`NINFER_KV_SINK`

§184.4 报错原文：

```
NINFER_KV_SINK pin leaves no working room: pin needs 80 page(s),
the ring needs at least 4 page(s) beyond it, so the pool must hold at least 84 page(s)
```

**⇒ sink 默认钉住开头 80 页。** 按 §184.4 换算（84 页 = 5,376 token）：

```
1 页 ≈ 64 token
80 页 ≈ 5,120 token
```

#### ④ 差异在「钉什么」，不在「钉多少」

| | 本仓 `KV_SINK` | Strata `pinned` |
|---|---|---|
| 钉的对象 | **开头固定 80 页**（静态） | **被复用过的任意前缀**（动态标记） |
| 覆盖量 | ≈5,120 token | 可钉任意长度、可多段 |
| 触发 | 起服时固定 | 运行时按「谁被复用」标记 |

**⇒ 我们是「保开头」，他们是「保命中过的」。**

#### ⑤ 收益条件（关键）—— 但实测数据已经否定了这一项

**构建史 L1314 的实测：多轮会话的 cache replay 命中率 = 99.9%。**

```
命中率 99.9% ⇒ 离上限不到 0.1%
pinned 最多能到 100%
⇒ 收益上限 0.1% ⇒ 不值得做
```

**⇒ 13.2 的结论：pinned 在本仓无收益，建议关闭。**

**真正的问题不是命中率，是 §13.4 的页漂移。**

#### ⑤-旧 收益条件的理论推算（已被实测否定，保留作记录）

```
系统提示 + 前几轮历史 < 5,120 token  ⇒ sink 已保住，pinned 无用
                     > 5,120 token  ⇒ 超出部分会被驱逐，pinned 有价值
```

| 场景 | 前缀长度 | 现状 |
|---|---|---|
| 简单问答 | ~3K | ✅ sink 保得住 |
| **长 agent 会话（Claude Code 类）** | **20K–80K** | ❌ **保不住，每轮重 prefill** |
| 多文件代码审查 | 30K+ | ❌ 保不住 |

**粗算**（3,000 tok/s）：30K token 重 prefill ≈ 10 s/轮，20 轮 ≈ **200 s/会话**。

#### ⑥ 但先要确认一件事

本仓 `§205` 记录 retention 用 **LRFU**——**高频访问的前缀本来就留得住**。

```
若 LRFU 已把共享前缀保住 ⇒ pinned 的真实收益远小于 200 s
若 LRFU 只看近期、前缀被新内容挤出 ⇒ pinned 有价值
```

**⇒ 判据：看驱逐日志里有没有「每轮都被访问、却被驱逐」的页。有 ⇒ pinned 有价值；没有 ⇒ 不必做。**

### 13.3 建议（三件，均不与 DFlash 冲突）

| 序 | 项 | 为什么 | 机时 |
|---|---|---|---|
| 1 | **查 LRFU 下共享前缀的实际驱逐行为** | 决定 pinned 值不值得做（0 机时读日志） | 0 |
| 2 | **实验固化的最小形态**（起服前打印件 sha + 全参数，缺一拒启） | §200 已出事故；不提速但防「又用错件」 | 半天 |
| 3 | KV_PREFETCH 剩余收益测算（读现成 profile 日志） | 决定要不要做 | 0 |
| — | ~~pinned 实现~~ | 先等 #1 的结论 | — |

### 13.4 页漂移：真实残留与已找到的解法（2026-11-04 核实）

#### ① 现象（构建史 L1306-1314，四对照实验）

| 对照 | 配置 | 超池深度 | decode |
|---|---|---|---|
| 单轮深超池 | 标准件 + 64K 池 | 246 页（81,264 tok） | **134.5** ✓ |
| 多轮 + cache replay | 标准件 + 64K 池 | 101 页（72K） | **125.8** ✓ |
| V1a 完全复刻 | vision + 51,200 + growth | 327 页（72K） | **134.0** ✓ |
| **掉速现场（req#34，34 轮）** | 同上 | ~150–330 页 | **3 tok/s** ✗ |

**判别特征（原文）**：

> decode 期 `mask hidden` 页数——不掉速组 hidden ≤ 17；掉速组**稳定 329-334 页**
> ⇒ **每步 attend 需 330 页在 host ⇒ 每 token host 往返 ⇒ host 98-101%**

#### ② 机理（与容量、与算法都无关）

> 每轮 cache replay（99.9% 命中）重新映射历史页，把**最早的页逐渐挤出设备池**；34 轮后 ~330 页早期上下文滞留 host。
> **不是「prompt > 池」触发（V1a 超池更深却正常），是「会话轮数」触发**

**⇒ 命中率 99.9% 也无法避免——那 0.1% 恰好是「每步 attend 都要用的开头」。**

**tancau（环作者）的独立结论（`ring-reuse-depth-and-failure-brief.md`）**：

> **结论一：复用深度由降级顺序决定，不由池大小决定**——「把池调大不是方案，只是把悬崖挪到更高处」
>
> **结论二：会话>池时「落袋」与「降级」互斥**——落袋要求 `[0,frontier)` 全设备驻留（`capture.cpp:63-115`），
> 服务超池会话必须降级同区间 ⇒ 两者不可兼得 ⇒ **超池会话存不下新锚**

#### ③ 三个修法（tancau 10-06 施工书）

| 修法 | 内容 | 本仓状态 |
|---|---|---|
| **C** | `HostKVExtentStore::publish` 把「陈旧 host 副本挂不上」判死刑（`std::terminate`）+ 调用方 `(void)` 丢返回值 ⇒ 九次静默死亡。改为可失败（`std::nullopt` + declined 日志） | ✅ **已修**（tancau `618cf7b`），本线 s6 树**含 C** |
| **A** | `demote_kv_pages_to_host` 新增 **`spare_prefix_pages`**——第一遍降级**跳过 `[0, 最深待发布 capture)`** | ✅ **已合入并转现役**（2026-11-05，`008cca2`，现役件 `F814B07A2B71ED4E`） |
| **B** | **host-backed anchor**——checkpoints **引用** ring 已有的 host 页而不拷贝 | ❌ **未做**（引擎深度改动，= 挂账 42 蓝图） |

#### ④ 修法 A 的实际代码（tancau 克隆 `refs/tancau-ninfer-kvmem-ring`）

`src/models/qwen3_5/program/program_impl.h:1551`：

```cpp
std::uint32_t ProgramImpl::demote_kv_pages_to_host(
    KVAddressSpaceStore& addresses, LogicalKVPageStore& pages,
    const KVAddressSpaceHandle& address,
    std::uint32_t sink_pages, std::uint32_t target_free,
    std::span<const std::uint32_t> preferred,
    std::uint32_t spare_prefix_pages)          // ← 新增参数
{
    const auto is_preferred = [&](std::uint32_t page) {
        return page < spare_prefix_pages ||    // ← 前缀页豁免（第一遍）
               (!preferred.empty() && std::binary_search(preferred.begin(), preferred.end(), page));
    };
    // Oldest first, skipping the attention sink and (in the first pass) the pages retrieval
    // wants to keep. If that is not enough the second pass gives up the retrieved pages too,
    // so the caller is guaranteed to get the room it asked for whenever the Device can supply it at all.
}
```

**两遍降级**：

```
第一遍：跳过 [0, spare_prefix_pages) + preferred（检索想要的）
不够   ⇒ 第二遍：连 preferred 也让出（保证调用方一定拿到空间）
```

**⇒ 这就是页漂移的直接解法：给前缀页一个「第一遍豁免」。**

#### ⑤ 合并工作量（三处）

| # | 改动 | 难点 |
|---|---|---|
| 1 | `program_impl.h` 加参数 + `is_preferred` 加一个判断 | 无 |
| 2 | `program_impl.h/.cpp` 两处调用点传值 | 无 |
| 3 | **决定 `spare_prefix_pages` 的取值** | **难点**：必须等于「最深待发布 capture」，不能拍脑袋 |

**tancau 注释写明了语义**：`[0, 最深待发布 capture)`。


#### ⑥ 本仓已按此实现（2026-11-05，commit `008cca2`）

**改动**：2 文件 `+31 / −9`

| 文件 | 改动 |
|---|---|
| `program_impl.h` | `ensure_ring_room` / `demote_kv_pages_to_host` 各加 `std::uint32_t spare_prefix_pages = 0U`；补语义注释（+5） |
| `context.cpp` | 两处定义加参数；`is_preferred` 加 `page < spare_prefix_pages \|\|` 短路；`ensure_ring_room` 内两处转发；`ensure_sequence_kv_mapped` 新增取值点并传给 Main / Backend 两次调用（+17/−9） |

**取值口径**（`施工记录-修法A-spare_prefix_pages-20261105.md` §2）：

```cpp
std::uint32_t spare_prefix_pages = 0U;
if (sequence.lane < max_concurrency && requests[sequence.lane].prefill &&
    !requests[sequence.lane].prefill->capture_groups.empty()) {
    spare_prefix_pages = kv_pages_for_frontier(
        requests[sequence.lane].prefill->capture_groups.back().frontier);
}
```

**两个「不取」的理由（原文）**：

| 不取 | 理由 |
|---|---|
| `total_tokens` | 那是本步要映射的 frontier，decode 阶段可达 100K+ ⇒ **会把几乎所有页列入保护、第一遍永远空跑**，退化成纯 oldest-first 的第二遍 |
| `shared_candidates` | 本仓 `RequestControl::Prefill` 只保留 `capture_groups`；运行期发布走它，无漏项可加 |

**无 pending capture 时恒为 0** ⇒ **decode 不付任何代价。**

**编译与门**：增量 24 秒（`BUILD-EXIT=0`）、ARCH-GATE `384/384 sm_120a / 0 sm_86 / 0 PTX`、DEPLOY-DLLS 16 件。

#### ⑦ 效果验证：方案就绪，**未点火**

`方案-修法A效果验证与受控序列复验-20261105.md` 原文：

> 状态：**未点火、零请求、零数据**。本文只做「回来即可照着跑」的方案与阻断点盘点。

**三个阻断点**：

| # | 阻断点 | 后果 |
|---|---|---|
| 1 | `bench_night.py` 末尾 `taskkill /IM ninfer-serve.exe /F` | **会连带杀掉不是它起的引擎** |
| 2 | 两个引擎不能并存（各 12.3 GiB，16 GB 装不下） | 跑基准前必须先 `engine_ctl -Action stop`，跑完再起现役 |
| 3 | **`bench_prompt.json` 只有 384 tok** | **触发不了 ring demote** ⇒ 修法 A 在这个 prompt 上与旧件**零差异** |

**⇒ 第 3 条是设计缺陷**：验证修法 A 必须用「长 prompt（≥池容量）」或「缩小池（`-Kvcap 16384` + ≥20K tok prompt）」。

**实验设计（原方案）**：

```
臂 A = F814B07A2B71ED4E（修法 A，现役）
臂 B = engine\lineage\ninfer-serve-RC8.exe（B93B1791，无修法 A）
其余全同：Coder390 件 / --spec mtp --draft-tokens 4 / --kv-capacity 16384
          / rk8v4 / host-kv-mib 16384 / prefill-chunk 512 / greedy / 同长 prompt
序列 A B A B（每臂 ≥2 次）
先算全同配置重复离散；>±1.5% 不许比 A/B
指标：publish declined 次数 / capture install 落袋深度 / hit / prompt exceeds
```

### 13.5 核实纠正（本报告此前两处错误）

| 此前的说法 | 核实结果 |
|---|---|
| 「本仓 retention 用 LRFU」（§13.2⑤-旧、以及对话中的表述） | ❌ **`lrfu`/`LRFU` 在 `origin/engine-main` 全树 0 命中**。LRFU 是 **kvmem 上游 16GB profile 的参数**（`dflash2-kvmem-integration.md` 的 `LRFU lambda 0.5`），不是本仓实现 |
| 「理论上限 = 池容量 / 会话长度 = 40%」 | ❌ **该公式只适用于「单次长 prompt、无历史」**；多轮对话实测命中 99.9%，与此公式无关 |

**本仓实际的降级策略**（`program_impl.h:1215-1218` 原文注释）：

> LOCAL PROTOTYPE (KVMem-style ring): **demote the oldest Device-resident pages**
> (skipping the attention sink and, on the first pass, `preferred`) until at least `target_free` Device pages
> have been released, or nothing more can be demoted.

**⇒ 策略 = 「最旧优先（按逻辑页号）+ 跳过 sink + （tancau 版）第一遍跳过 preferred」——接近 FIFO，不是 LRU。**

**⇒ 与 tancau 作者的判断一致：「环的实际策略 = 无脑 FIFO + sink」。**

**但注意**：本仓连 `spare_prefix_pages` 都没有，所以**我们可能连「第一遍跳过 preferred」都不完整**——这一条待家里读实际调用点确认。


### 13.6 修正后的建议序

| 序 | 项 | 依据 | 机时 |
|---|---|---|---|
| **1** | **点火修法 A + 锚落袋验证**（§14.8 第一步：§206 现成场景 63,989 prompt + 51,200 池，看 `capture install` 0→>0） | 零构造零改码，用现役件 `F814B07A`（已合入修法 A 但未测过）；旧件 `B93B1791` 同场景对照 | **1 小时** |
| **2** | **源码资产化：`patches/24_fixA` + `patches/25_conv_draft_startup`** | §13.7：改动只在机器里，23 个 patch 都有主仓，唯修法 A 漏了 | **10 分钟** |
| 3 | 实验固化最小形态（件 sha + 全参数） | §200 已出事故 | 半天 |
| 4 | KV_PREFETCH 剩余收益测算 | 读现成 profile | 0 |
| — | ~~合并修法 A~~ | ✅ **已完成**（`008cca2`，2026-11-05） | — |
| — | ~~pinned 前缀~~ | 命中率 99.9%，无收益 | **关闭** |
| — | ~~修法 B（host-backed anchor）~~ | 引擎深度改动，需单独立项 | 暂缓 |


### 13.7 源码资产化缺口：`engine-src` 的改动**只在机器里**（2026-11-05 核实）

#### ① 现状：三样东西锚定，缺了最关键的第四样

`施工记录-修法A-spare_prefix_pages-20261105.md:4` 原文：

> **本文件记录的是「当前生效二进制」与其源码改动集的反溯关系**：
> `engine-src` 是**独立未跟踪子仓**，改动不提交（**保持 HEAD 不变以免打断 asset-dual 树的同一性检查**），
> 故以**本记录 + 备份 + binary sha** 三者共同锚定。

**⇒ 现在锚定修法 A 的只有：**

| # | 载体 | 内容 |
|---|---|---|
| ① | 施工记录（文字） | `+31/−9`、改哪两个函数、取值口径 |
| ② | `_safety_backups\20261105_pre_fixA\` | **改动前**备份（4 文件） |
| ③ | binary sha | `F814B07A2B71ED4E` |
| **④** | **改动后源码** | ❌ **不在任何版本控制里** |

#### ② 理由成立，但只解决了「不能提交到 engine-main」

`asset-dual` 检查的逻辑：引擎源码 HEAD ↔ 编译产物 sha，**HEAD 一变就判不匹配**。

**⇒ 不能随便给 `engine-main` 加提交。**

**但这不等于「源码必须不上库」——两种做法都能保住 HEAD：**

| 做法 | 改 HEAD | 能上库 |
|---|---|---|
| commit 到 `engine-main` | ✅ | ❌ 会打断 asset-dual |
| **导出 patch 存进主仓 `patches/`** | ❌ | ✅ **可以** |
| 建临时分支 `fixA-20261105` | ❌ | ✅ 可以 |

#### ③ 项目本来就有这个惯例，唯独修法 A 没跟上

```
patches/  23 个 .patch，合计 0.2 MB
  ledger42_v2_async_demote.patch（39,958 B）
  i3b_s12v3_fourlayer.patch（16,062 B）
  …
```

**⇒ 23 个补丁全部以 `.patch` 形式在主仓里，只有修法 A 漏了。**

**⇒ 而且 §204 还记着：`engine-src` 另有 6 个文件未提交**（conv/draft/startup 扩展）——**也没有 patch**。

#### ④ 风险：一旦机器上的 `engine-src` 丢失

```
丢/误 reset/换机器 ⇒ 只能靠施工记录的文字重写一遍
⇒ 这正是"源码树被删了再重建"的同型事故
```

#### ⑤ 建议（两条命令，不动 HEAD）

```powershell
# 修法 A
cd engine-src
git diff -- program_impl.h storage/context.cpp > ..\patches\24_fixA_spare_prefix_pages.patch

# §204 的 6 文件扩展
git diff -- <6 files> > ..\patches\25_conv_draft_startup_ext.patch
```

**判据**：patch 能否干净应用（`git apply --check`）——能 ⇒ 源码资产化完成。

### 13.8 分支完整度核实（2026-11-05）

**核实方法**：GitHub API 列全部仓库分支 + 与本地 `git branch -r` 对比。

| 仓库 | 分支数 | 分支 | 最近推送 |
|---|---|---|---|
| **`Ninfer-KVMem-Async`**（主仓） | **2** | `engine-main` / `main` | 2026-11-04 23:34 |
| `Bonsai-27B-NInfer-kvmem`（旧仓） | **3** | `engine-main` / `main` / **`port-20261020`** | 2026-10-20（停更） |
| `Bonsai-27B-NInfer`（旧仓） | 2 | `engine-main` / `main` | 2026-10-06（停更） |
| `Ninfer-KVMem` | 2 | `engine-main` / `main` | 2026-11-04 23:34（**与主仓同 sha**） |

**结论**：

```
主仓 Ninfer-KVMem-Async：2 分支，本地齐全，无遗漏、无残留
「第三分支 port-20261020」属旧仓 Bonsai-27B-NInfer-kvmem，10-20 遗留，非新增
Ninfer-KVMem 与 Ninfer-KVMem-Async 的 sha 完全相同 ⇒ 同一仓库的旧名重定向，不是两个仓
```

**⇒ 分支结构干净；真正的缺口是 13.7 的「源码改动未资产化」，不是分支数。**

---

## 十四 长前缀锚（PrivateLongAnchor）：机制、门槛与落地指导

> 2026-11-05 追加。本节把「多轮讨论 + TELE 六轮交叉复核」综合成可直接执行的形态。
> 与 §13.4（页漂移 + 修法 A/B）的关系：§13.4 讲「为什么需要」，本节讲「怎么用、什么时候能用、能省多少」。

### 14.1 一句话

**长前缀锚 = 把「prompt 第 N 个 token 处」的 KV 状态标成「值得保留」，下一轮若前缀匹配就跳过那 N 个 token 的 prefill。**

**它不加速 prefill，它是「让下一轮少做 prefill」。收益 = 省下的 token 数 ÷ prefill 速度。**

---

### 14.2 它到底是什么（先破除三个误解）

### 误解 1：「锚是一个程序」

**不是。锚是一个位置标记 + 那一段 KV 被保留。**

```cpp
// frontend.cpp:575-582
if (full_prompt_frontier >= 32768) {
    for (std::uint32_t frontier = 32768; frontier < full_prompt_frontier; frontier += 32768) {
        add_opportunity(PromptCacheMarkerKind::PrivateLongAnchor, ..., frontier, ...);
    }
}
```

**⇒ 它只是在「32K、64K、96K…」这些位置各提一个「这里值得存一份」的机会。**

### 误解 2：「锚是保留提示词文本」

**不是。保留的是那 N 个 token 算出来的 KV。**

```
1 页 = 64 token（构建史 L812）
1 页 ≈ 1.66 MB（rk8v4，由「2 倍 rk2v4」推断；L4831 增量实测支撑 1.56 MB/页）
⇒ 每 token ≈ 26 KB
⇒ 32K token = 512 页 × 1.66 MB ≈ 850 MB
```

**⚠ 注意**：按 64 层 × 8 KV heads × 128 dim × 0.75 B（**示例参数，未逐层核实**）直算会得 96 KB/token，比实测大 3.7 倍——因为 Qwen3.5 是 **hybrid 架构，只有部分层是 attention**（GDN 层只存 state，不存 KV）。**估算必须用「页 × 页大小」，不能用「层数 × 头数」直算。**

### 误解 3：「锚是显存预留」

**不是。它不预分配，只在「落袋那一刻」检查「能不能装下」。装不下就 decline + 打日志，什么都不发生。**

```cpp
// capture.cpp:120-126
if (publish_scan_pages + work > usable) {
    fprintf(stderr, "anchor publish declined: frontier=%u needs=%u+workset=%u usable=%u ...");
    publish_private = false; publish_shared = false;
}
```

---

### 14.3 参数与开关（现成的，不用改代码）

| 参数 | 含义 | 默认 | 位置 |
|---|---|---|---|
| **`--max-long-anchors-per-continuation N`** | 每个会话最多几个锚；**0 = 完全关闭** | **2** | `serve_options.cpp:288-292` |
| `--auto-prefix-grid` | 另一套机制：**共享**前缀候选（`SharedStablePrefix`），**不是长锚的可调步长版** | 关 | `L363`，与 `--no-prefix-reuse` 互斥（L437） |
| `NINFER_KV_HOST_ANCHORS=1` | **修法 B**：允许「前缀含 host 页」的锚落袋（按引用） | 关 | `capture.cpp:27-33` |

**⇒ 长锚本身的开关就是第一个参数，不需要改代码。**

### 步长是硬编码的，但可以解锁

```cpp
// frontend.cpp:576
for (frontier = 32768; frontier < full_prompt_frontier; frontier += 32768) {
//                 ↑ 这两个 32768 就是"锚的大小"
```

**⇒ 改成 8192 就是 8K 锚。** 建议 env 化（`NINFER_ANCHOR_STRIDE`）一次编译扫全矩阵。

**作者为什么选 32K（`frontend.cpp:569-574` 注释原文）：**

```
32K stride bounds the extra chunk splits (~8 max). Gated to long prompts only.
```

**⇒ 两条都是工程取舍，不是原理约束：**
1. 限制 chunk split 数量（每个锚会让 prefill 在那切一刀）
2. 只对长 prompt 生效（避免短会话浪费）

---

### 14.4 门槛公式（唯一必须记住的东西）

```
锚页数 + 工作集 256 页 + decode 余量 ≤ 池页数
```

**工作集 256 页的构成**（`capture.cpp:35-39` 原文推导）：

```
NINFER_KV_RETRIEVE = 12288 tokens = 192 pages
--prefill-chunk    = 1024 tokens  =  16 pages
ring slack                         =   8 pages
tail COW                           =   1 page
─────────────────────────────────────────
217 → rounded 256 pages
```

**换算：**

```
1 页 = 64 token              （构建史 L812：KV 20,480 tokens | pages 320/4,096）
1 页 ≈ 1.66 MB（rk8v4）      （L4831：KV 51,200 tokens | pages 800/4,096 | runtime 2.23 GiB）
1 页 ≈ 0.83 MB（rk2v4-e8）   （L633-636 实证）
```

**⇒ 锚 token 数 × 64 → 锚页数；再 + 256 + 余量 ≤ 池页数。**

---

### 14.5 各池档的判定（统一判据，余量 > 0 才算可用）

| 池（token） | 页数 | **可用最深锚** | 锚页数 | 门槛（锚+256） | 余量 | 每轮省（1.92k tok/s） |
|---|---|---|---|---|---|---|
| **32,000** | 500 | **8K** | 128 | 384 | 116 | **4.2 秒** |
| **32,768** | 512 | **8K** | 128 | 384 | 128 | **4.2 秒** |
| 40,960 | 640 | 16K | 256 | 512 | 128 | 8.5 秒 |
| **51,200**（SWIFT+DFlash 实测） | 800 | **32K** | 512 | 768 | **32** | **17.1 秒** |
| **57,344**（Coder390 实测） | 896 | **32K** | 512 | 768 | 128 | **17.1 秒** |
| 65,536 | 1,024 | 32K | 512 | 768 | 256 | 17.1 秒 |
| **80,000**（SWIFT+MTP 已测） | 1,250 | **32K**（64K 差 30 页） | 512 | 768 | 482 | **17.1 秒** |
| 89,600 | 1,400 | **64K** | 1,024 | 1,280 | 120 | 34.1 秒 |
| 98,304 | 1,536 | 64K | 1,024 | 1,280 | 256 | 34.1 秒 |
| **262,144**（Bonsai） | 4,096 | **192K** | 3,072 | 3,328 | 768 | **102 秒** |

### 三个必须注意的边界

**① 贴线 = 不可用**

```
81,920 池（1,280 页）+ 64K 锚（1,024）+ 工作集（256）= 1,280 ⇒ 余 0
⇒ 看似"刚好装下"，实际 decode 没有任何调度空间
⇒ 实用门槛 ≈ 89,600 token（1,400 页）
```

**② 80,000 与 81,920 之间没有阶跃**

```
两档都只能建 32K 锚
真正阶跃在 ~89.6K 以上（64K 锚）
```

**③ 32K 池只有 8K 锚可用**

```
16K 锚 + 256 = 512 页 = 池 32,768 ⇒ 余 0 ⇒ 不可用
⇒ 32K 池统一按 8K 锚算
```

---

### 14.6 收益模型：为什么是「角点解」不是「内点最优」

```
单位页收益 = 64 token ÷ 1,920 tok/s = 0.0333 秒/页（恒定，与步长无关）
⇒ 锚越大总收益越大，单位收益不变
⇒ 没有中间最优点，最优 = 池允许的最深锚
⇒ 扫描不是为了找最优，是为了验证"线性假设是否成立"
```

### 唯一的二阶因素：深锚的机会成本

```
锚越深 ⇒ 锁住的页越多 ⇒ decode 可调度页越少
⇒ 降级/restore 流量越大
⇒ 最深锚未必最舒服
```

**实践选择：在「能建的最深锚」和「留够 decode 余量」之间取平衡，余量建议 ≥ 200 页。**

**⚠ 与 §14.5 表的衔接**：表中 89,600 档（64K 锚 + 256 工作集）余 120 页，**可用但低于建议余量** ⇒ 实践推荐 **94,720 以上**（98,304 档余 256 页，符合 200 页建议）。

---

### 14.7 与异步页流水的关系：互补，且下锚后更需要异步

| | 长前缀锚 | 异步页流水 |
|---|---|---|
| **层** | 决策层（留什么） | 执行层（怎么搬） |
| 时机 | prefill（保护） | decode（降级/恢复重叠） |
| 解决 | 「该留的页被踢了」 | 「搬运时 GPU 空转」 |

### 下锚后，三个方向让异步更重要

```
① 可用池变小：锚锁 512 页 ⇒ 可调度页少 ⇒ 换页更频繁
② 复用要 restore：512 页 ≈ 850 MB，按 25 GB/s ≈ 34 ms（**25 GB/s 是 PCIe 4.0 x16 量级假设，本机未实测**）
③ 落袋要腾空间：锚落袋前必须先降级别处
```

**⇒ 一句话：锚让「该留的留下」，异步让「该搬的搬得不疼」。**

---

### 14.8 家里的执行序（三步，按顺序）

### 第一步：验证「现役件能不能落袋」（零成本，最优先）

**用 §206 的现成场景，不要构造新 prompt：**

```
场景（L4832 实证）：prompt 63,989 token + 池 51,200
三条件全满足：
  ① 池 800 页 ≥ 768（门槛）✓
  ② prompt 63,989 ≥ 32,768（有锚）✓
  ③ prompt 63,989 > 池 51,200（触发降级）✓

旧件（B93B1791，无修法 A）⇒ capture install 必为 0
新件（F814B07A，含修法 A）⇒ 应 > 0
```

**判据：**

```powershell
# 臂 A（现役件，含修法 A）——必须用 §206 同款模型件
scripts\engine_ctl.ps1 -Action start -Tag fixA -Depth 2 -Pool 51200 -Experimental
#   模型件：models\swift15_dflash2.ninfer（§206 同款）

# 跑 §206 的 63,989 prompt，先看一眼真实日志里 install 行长什么样
Select-String -Path <log> -Pattern "capture install|anchor publish|KEPT"

# 臂 B（旧件，无修法 A）——用 lineage 里的 RC8 同场景补跑
#   engine\lineage\ninfer-serve-RC8.exe（B93B1791）
#   ⚠ 两个件不能并存（各 12.3 GiB）⇒ 必须先 stop 再起
```

**⚠ 关键**：臂 B（旧件 `B93B1791`）**必须真的跑一次**。
"旧件 install 必为 0" 目前只是**推断**（122K 会话的类比），§206 原始日志只有 `WARN: prompt exceeds...` 行，
**没有 `install=0` 的直接证据** ⇒ 补跑一次（+30 分钟）才构成 A/B 双证据。

**结果解读：**

| install 计数 | 含义 |
|---|---|
| **> 0** | ✅ 修法 A 起效，锚能落袋 |
| **= 0** | ❌ 修法 A 无效，或条件未满足（看 `anchor publish declined` 的数字） |

### 第二步：扫描各池档的最深可用锚（如果第一步通过）

**需要先做一件事：把步长 env 化**（改 `frontend.cpp` 两处字面量 + 重编译，一次编译扫全矩阵）。

```powershell
# 矩阵
池 ∈ {32768, 40960, 51200, 57344, 65536, 80000}
步长 ∈ {8192, 16384, 32768}
锚数固定 = 1（--max-long-anchors-per-continuation 1）
prompt = 池 × 1.2（确保超池）
每臂 2 次，ABBA
```

**必须记录的三个量：**

```
① capture install 实际落袋的 frontier（日志有 frontier + ordinal）
② prefill 总耗时（判 chunk split 成本）
③ TTFT
```

**判据（绝对量，不用百分比）：**

```
8K 档 split 成本预算 = 4.2 秒 ÷ 7 切点 ≈ 0.6 秒/切点
净收益 = TTFT 改善 − prefill 增量
净收益 > 0 ⇒ 该步长可用
```

### 第三步：如果小步长有隐藏成本，再决定是否立项

**唯一未测的变量是 chunk split 成本。作者选 32K 的唯一实质理由就在这。**

```
若 8K 步长的 prefill 增量 < 4.2 秒 ⇒ 可用
若 > 4.2 秒 ⇒ 小步长不划算，回到 32K
```

---

### 14.9 家里的三个先决条件（必须先确认）

| # | 待确认 | 怎么查 |
|---|---|---|
| 1 | **32K 池档的实际 `--kv-capacity`** 是 32,000 还是 32,768 | 起服日志 `capacity \| KV xx,xxx tokens` 行 |
| 2 | 本仓 `serve_options` 是否同构 tancau | `git grep -n "max-long-anchors-per-continuation"` |
| 3 | 本仓 `frontend.cpp` 的锚步长是否也是 32768 硬编码 | `git grep -n "frontier += 32768"` |

**⇒ 三条都是零机时，先查完再谈实验。**

---

### 14.10 本轮讨论中我犯的错（避免家里重复）

| # | 错误 | 正确 |
|---|---|---|
| 1 | 页大小说成 26.1 KB / 6.1 MB | **0.83 MB（rk2v4）/ 1.66 MB（rk8v4）** |
| 2 | 门槛加了 evidence 128（重复计 retrieve） | **工作集 256 页已含 retrieve 192，不重复加** |
| 3 | "50K 是上下文" | **是池；上下文天生 256K** |
| 4 | "rk8v4 上限 20,480" | **51,200**（完整旗标实测，L4831） |
| 5 | **"80K 池能建 64K 锚"——连续三轮** | **80,000 = 1,250 页 < 1,280 ⇒ 只能 32K 锚** |
| 6 | 32K 池口径漂移（500 vs 512 页） | **统一 8K 锚** |
| 7 | 81,920 贴线标"可建"，却给 32,768 贴线标"不可用" | **同构场景同判据：贴线不可用** |
| 8 | `--auto-prefix-grid` 说成"长锚的可调步长版" | **是另一套机制（`SharedStablePrefix` 共享前缀）** |

**⇒ 根因都是一个：没有每次重新代入「工作集 256 页」和「池的实际页数」。**

---

### 14.11 一句给家里的总结

> **长前缀锚不是「提速 prefill」，是「让下一轮少做 prefill」。**
>
> **它能建的前提是：锚页数 + 256 页工作集 + 余量 ≤ 池页数。**
>
> **它的收益是线性的（0.033 秒/页），所以最优永远是「池允许的最深锚」，扫描只为验证小步长的 chunk split 成本。**
>
> **现在能做的第一步，是用 §206 的 63,989 prompt + 51,200 池，看现役件 F814B07A 的 `capture install` 是否从 0 变成 > 0——这一步零构造、零改码。**

---


### 14.13 自动适配锚大小（按池自动选步长）——设计草案

**目标**：启动时按 `--kv-capacity` 自动算出该池能撑的最深锚，不需要人工设步长。

#### ① 公式法（启动时算，10–20 行）

```cpp
std::uint32_t anchor_stride_for_pool(std::uint32_t pool_tokens) {
    constexpr std::uint32_t kWorkingSet = 16384;  // 256 页（capture.cpp:35-39 实证）
    constexpr std::uint32_t kMinReserve = 12800;  // 200 页 decode 余量（可调）
    constexpr std::uint32_t kMinStride  = 8192;   // 最小锚

    if (pool_tokens <= kWorkingSet + kMinReserve + kMinStride) { return 0; }  // 池太小 ⇒ 不锚

    const std::uint32_t budget = pool_tokens - kWorkingSet - kMinReserve;

    std::uint32_t stride = kMinStride;
    while (stride * 2 <= budget) { stride *= 2; }   // 取不超过 budget 的最大 2 的幂
    return stride;
}
```

**验算（三档余量）：**

| 池（token） | **保守**（余 200 页） | **平衡**（余 64 页） | **激进**（余 0） |
|---|---|---|---|
| 32,768 | 0（不锚） | 8K | 8K |
| 40,960 | 8K | 16K | 16K |
| **51,200** | **16K** | **16K** | **32K**（余 32 页） |
| 57,344 | 16K | **32K** | 32K |
| 65,536 | 32K | 32K | 32K |
| 80,000 | 32K | 32K | 32K（64K 需 81,920） |
| 98,304 | 64K | 64K | 64K |
| 262,144 | 128K | 128K | 192K |

**⇒ 关键结论：51,200 档没有「既安全又最优」的中间解——**

```
32K 锚（省 17.1 秒）⇔ 余量仅 32 页（decode 几乎无调度空间）
16K 锚（省 8.5 秒）⇔ 余量充足
```

**⇒ 自动适配只能选一种取舍，不能两全。**

#### ② 查表法（实测后写死，更准）

```cpp
struct AnchorProfile { std::uint32_t pool_min, pool_max, stride; };

// 需实机扫描后填（示例值，未验证）
static constexpr AnchorProfile kAnchorTable[] = {
    {  32768,  40959,  8192 },
    {  40960,  57343, 16384 },
    {  57344,  94207, 32768 },
    {  94208, 131071, 65536 },
    { 131072, 262144, 98304 },
};
```

**⇒ 推荐：查表优先 + 公式兜底**

```cpp
std::uint32_t stride = lookup_anchor_table(pool_tokens);
if (stride == 0) { stride = anchor_stride_for_pool(pool_tokens); }
```

#### ③ 三档策略做成参数

```cpp
enum class AnchorPolicy { Conservative, Balanced, Aggressive };
// Conservative: kMinReserve = 12800（200 页）
// Balanced:     kMinReserve =  4096（ 64 页）
// Aggressive:   kMinReserve =     0（贴线，不推荐生产）
```

**⇒ 对应 CLI：`--anchor-policy conservative|balanced|aggressive`**

#### ④ 落地路径（顺序不能跳）

| 步 | 动作 | 前提 |
|---|---|---|
| **1** | 不改代码，用 §14.8 的 A/B 验证锚能落袋 | 现役件 `F814B07A` + §206 场景 |
| **2** | env 化步长（`NINFER_ANCHOR_STRIDE`），手工扫出各池档的实际甜点 | 步 1 通过 |
| **3** | 把实测结果写进查表 + 加 `--anchor-policy` | 步 2 有数据 |
| **4** | 启动时自动查表，不需要人工设 | 步 3 稳定 |

**⇒ 跳过步 1、2 直接写公式，就是拿未验证的假设做自动化——等于把错误固化。**

#### ⑤ 与 §14.6 角点解的关系

```
单位页收益恒定（0.033 秒/页）⇒ 最优永远是"池允许的最深锚"
⇒ 自动适配的本质 = "算出这个边界"
⇒ 但边界受"decode 余量"约束 ⇒ 余量策略是唯一的自由度
```


### 14.12 引用

| 内容 | 出处 |
|---|---|
| 锚生成（32K 步长 + 两条取舍理由） | `refs/tancau-ninfer-kvmem-ring/src/models/qwen3_5/frontend/frontend.cpp:569-582` |
| 落袋容量门 + decline 日志 | `.../program/transactions/capture.cpp:104-128` |
| 工作集 256 页推导（含"不要用结果反推"的教训） | `capture.cpp:35-44` |
| 修法 B 开关 `NINFER_KV_HOST_ANCHORS` | `capture.cpp:22-33` |
| 满员替换（非自动 LRU） | `capture.cpp:700-723` |
| 修法 A `spare_prefix_pages` | `program_impl.h:1219-1229`（声明与语义注释）+ `storage/context.cpp:1551-1563`（`demote_kv_pages_to_host` 实现，`is_preferred` 在 1560-1563） |
| 锚数量默认 2 | `runtime/engine/model_instance.cpp:118` |
| CLI 参数 | `serve/serve_options.cpp:288-292`（锚数）、`L363`（auto-prefix-grid）
| 工作集 256 页推导（retrieve 192 + prefill 16 + slack 8 + COW 1） | `capture.cpp:35-44` | |
| token/页 = 64 | 构建史 L812（`KV 20,480 tokens \| pages 320/4,096`） |
| 页大小 0.83 MB（rk2v4） | 构建史 L633-636 |
| 页大小 1.56 MB（rk8v4，**增量实测**：25 MiB / 1024 tok） | 构建史 L4831 |
| 页大小 1.66 MB（rk8v4，**推断**：2 倍 rk2v4） | 本报告 §14.4 换算，非实测 |
| rk8v4 池上限 51,200 | 构建史 L4831（`pages 800/4,096 \| runtime 2.23 GiB`） |
| SWIFT+MTP 80,000 未探顶 | 构建史 L4464（**注：属 §184.5「每格 1 轮不得作强证据」节，引用需带限定**） |
| Coder390 57,344（65,536 不可用） | 构建史 L5199 / L5212 |
| §206 现成场景（63,989 prompt + 51,200 池） | 构建史 L4832 |
| prefill 1.92k tok/s | 构建史 L4832 |
