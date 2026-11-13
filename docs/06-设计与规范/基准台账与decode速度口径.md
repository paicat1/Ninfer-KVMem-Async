# 基准台账与 decode 速度口径规范

> 2026-11-13 立。依据：`docs/03-归因与结论/调研-上游对照-Strata与KVMem-v0.19-与prefill基准修正-CB-TELE-LUMMY-20261103.md` §十六（Basalt 台账）、§十七（成熟度）、§十八（decode 口径）。
> 目的：终结"8 个实测全对、但无一可比"的局面。

---

## 0. 病症：现有 8 个 decode 数字为何互相矛盾

| 数字（tok/s） | 出处 | 实际口径 | 不可比的原因 |
|---|---|---|---|
| 748.6 | 仓二峰值 | 请求级 · 短输出 | 不同模型/不同仓 |
| 463.9 | 10-13 峰值 | **5s 窗口峰值** | 峰值 ≠ 均值 |
| 388 | §178 | 请求级 · 短请求 | **独显通道** |
| 239 | §206 | **5s 窗口峰值** · 64K 上下文 | 峰值 |
| 182.1 | §206 | 请求级 · 38K 输出 · 59.5% 接受率 | 长输出 + 混合投机 |
| 154.9 / 186.0 / 202.6 | §220 | 请求级 · **384 tok 输出** · 核显通道 | 短输出 + 核显 |
| 580 | 用户观察 | 口径不明（未复现） | 未复现 |
| 3 | 页漂移现场 | 请求级 · 超池 + 漂移 | 病态态 |

**六个不可比维度**，任一不同即不可比：

```
① 请求级 vs 5s 窗口（均值 vs 峰值）
② prompt 长度（384 / 32K / 64K / 199K）
③ 生成长度（384 / 38K）
④ 显示通道（igpu / dgpu，差 19–60%）
⑤ 并发数（1 / N）
⑥ 采样方式（greedy / temperature）
```

---

## 1. 强制规范：六字段必标

**任何对外给出或写入文档的速度数字，必须同时标注以下六项：**

| # | 字段 | 取值示例 |
|---|---|---|
| ① | `prompt_tokens` | 66 / 512 / 32768 / 199000 |
| ② | `output_tokens` | 234 / 384 / 38000 |
| ③ | `concurrency` | 1 / 4 |
| ④ | `quant` + `kv` | `iq3_s系` / `rk8v4` |
| ⑤ | `channel` | `igpu` / `dgpu` |
| ⑥ | `sampling` | `greedy` / `t=0.7 top_p=0.9 top_k=20` |

**缺任一字段 → 必须在数字旁标注「未标口径，不可横向比较」。**

### 为什么这条最重要

现有的 §220 表格（`143.1 / 172.5 / 152.7 / 202.6`）只标了「件 / 头 / 池」，**六字段里缺 ③③④⑥**（并发、量化档、采样）。
按本规范，这些数字**只能用于同表内部横比**（因为六字段在表内一致），**不能与 §206 的 182.1 或 §178 的 388 直接比**。

---

## 2. 三层基准（成本从低到高）

### 第一层：短基准（llama-bench 兼容，~5 分钟）

```
prompt : 512 token（固定文本，全仓共用一份）
output : 128 token
采样   : greedy
重复   : 3 次
报告   : tg128 = mean ± std
```

**价值**：可与 llama.cpp / vLLM 的数字**同口径直接对比**。

### 第二层：长基准（TTFT + TPOT，~10 分钟）

```
prompt : 32,768 token（正好一个锚的 frontier）
output : 512 token
采样   : greedy
重复   : 3 次
报告   : TTFT (s) + TPOT (ms/token) + P90
```

**价值**：测出「池内 vs 超池」「核显 vs 独显」「接受率高低」的差异。

### 第三层：分负载（conv / struct / prose，~30 分钟）

```
三类各 3 次，分别记录：
  decode_tps + accept_pct + draft_len
```

**价值**：回答「这个档适合什么任务」——这是「选头」与「选模型」的唯一依据。

> ⚠ 第三层是**当前最大的空白**：现有全部数字都来自单一代码题（struct 类），conv 与 prose 从未测过。

---

## 3. 台账字段（采自 Basalt，可直接抄）

### A. 吞吐分项（按负载类型拆）

| 字段 | 含义 |
|---|---|
| `decode_tps` | 三类 fixture 的 tokens 总和 ÷ 时间总和（**token 加权，不是三者均值**） |
| `decode_conv_tps` | 对话类 |
| `decode_struct_tps` | 结构化类（代码 / JSON） |
| `decode_prose_tps` | 散文类 |

> 原文强调：`decode_tps` 是三类 tokens 之和 ÷ 三类 decode 时间之和，**不是三者均值**。
> 这治的正是我们「拿单一 384 tok 请求代表全部」的毛病。

### B. 投机分项（按负载拆）

| 字段 | 含义 |
|---|---|
| `accept_conv_pct` / `accept_struct_pct` / `accept_prose_pct` | 接受的 draft ÷ 提供的 draft（%） |
| `draft_len_conv` / `draft_len_struct` / `draft_len_prose` | 每轮平均提供几个 draft |

> 某个 fixture 未发生投机时，对应字段留空（不是填 0）。
> 这治的正是「§205 只记 d7=99.2 没记接受率」那个坑。

### C. 硬件实测（不是抄规格书）

| 字段 | 测法 |
|---|---|
| `cpu` | 「型号 + 物理核数」，如 `"AMD Ryzen 9 9950X, 16 cores"` |
| `ram_gbps` | 每物理核一线程流式读 2 GiB 缓冲，多次取最好 |
| `pcie` | 驱动报告的链路，如 `"5.0 x16"`（**最大代际 + 当前宽度**，空闲时会降代） |
| `h2d_gbps` | pinned host→device，多次 256 MiB 拷贝取最好 |

> 这治的正是「带宽参数靠猜（1024 GB/s）」那个坑。

### D. 起服参数

| 字段 | 限制 |
|---|---|
| `engine_args` | 预设传给引擎的参数（**不含模型路径，≤300 字符**） |

> 这治的正是「忘了打什么补丁 / 用了哪个件」那个坑。

---

## 4. 去重规则（一行一 setup）

- **一个 setup 一行**：同件同头同池同通道的一次完整测量 = 一行
- **不同 setup 不合并**：改任一维度（池/头/通道/采样）都是新行
- **同一 setup 的重复 3 次只留统计量**：记 `mean` / `std` / `n=3`，不逐条列

---

## 5. JSONL 台账模板

文件：`evidence/ledgers/<YYYY-MM-DD>-<tag>.jsonl`，一行一个 JSON 对象。字段取自调研 §16.5 的本仓适配版（比自创格式更完整）。

> 目录选择说明：`structure.json` 把 `evidence/` 定义为「实验证据：cases/ ledgers/ samples/ reqlogs/ baselines/（只增不改）」，台账天然属于 `ledgers/`。根目录白名单不含 `bench/`，而 `structure.json` 在治理基线内（改动需 rebuild），故不在根目录新建 `bench/`。

```json
{
  "date": "2026-11-13",
  "operator": "cb",
  "model": "gsq_iq3s_dual.ninfer",
  "model_sha": "e9b0ebf",
  "spec": "mtp",
  "draft_tokens": 3,
  "kv_dtype": "rk8v4",
  "pool_tokens": 65536,
  "engine_exe": "ninfer-serve.exe",
  "engine_sha": "496D6070",
  "engine_args": "--kv-capacity 65536 --kv-dtype rk8v4 --cuda-graph-allowance-mib 64 --wddm-budget-arithmetic-only --spec mtp --draft-tokens 3 ...",
  "gpu": "RTX 5080 16GB",
  "gpu_used_mib": 15690,
  "channel": "dgpu",
  "graph_allowance_mib": 64,
  "host_kv_mib": 16384,
  "prompt_tokens": 66,
  "output_tokens": 234,
  "ttft_s": 0.330,
  "prefill_tps": 200.6,
  "decode_tps": 143.1,
  "decode_conv_tps": null,
  "decode_struct_tps": null,
  "decode_prose_tps": null,
  "accept_pct": 64.3,
  "accept_conv_pct": null,
  "accept_struct_pct": null,
  "accept_prose_pct": null,
  "note": "单实例；物理余 288 MiB；81,920 反而降到 134.0"
}
```

### 字段必填性

| 级别 | 字段 |
|---|---|
| **必填**（缺一即「未标口径」） | `date` / `model` / `spec` / `pool_tokens` / `kv_dtype` / `channel` / `engine_sha` / `prompt_tokens` / `output_tokens` / `decode_tps` |
| 宜填 | `draft_tokens` / `engine_args` / `gpu` / `gpu_used_mib` / `graph_allowance_mib` / `accept_pct` / `ttft_s` / `prefill_tps` / `model_sha` |
| 按负载填 | `decode_conv/struct/prose_tps` / `accept_conv/struct/prose_pct`（未发生则留 `null`，不填 0） |
| 可选 | `note` / `operator` / `host_kv_mib` |

### 与六字段的映射

| §18.5 必标字段 | 台账字段 |
|---|---|
| ① prompt 长度 | `prompt_tokens` |
| ② 生成长度 | `output_tokens` |
| ③ 并发数 | 单路为默认；多路需加 `concurrency` |
| ④ 量化档 | `model` + `kv_dtype` |
| ⑤ 显示通道 | `channel` |
| ⑥ 采样方式 | 记录在 `engine_args`（含 temperature / top_p / top_k） |

---

## 6. 落地约束

1. **新数字必须带六字段**，缺字段即视为「未标口径」；
2. **历史数字不追改**（append-only），但在引用时必须补一句口径说明；
3. **跨件横比前，先核对六字段是否一致**——不一致的只能定性描述，不能给差值百分比；
4. 台账文件按日一文件，一行一 setup，**不手工改历史行**。

---

## 7. 待补的三项空白

| 空白 | 影响 | 成本 |
|---|---|---|
| 分负载基准（conv / prose） | 「选头」缺依据，全部数字只代表 struct | 第三层，约 30 分钟 |
| 长基准（TTFT + TPOT + P90） | 不知道长上下文下的真实手感 | 第二层，约 10 分钟 |
| `ram_gbps` / `h2d_gbps` 实测 | 带宽参数仍是猜的 | 一次性，约 20 分钟 |
