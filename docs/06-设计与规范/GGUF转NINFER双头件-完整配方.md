# 普通 GGUF → NINFER 双头件：完整配方

> 2026-11-08 首次全流程打通（unsloth UD-Q3_K_XL → ud_q3kxl_mtp.ninfer），本文记录**实测可行**的路径、
> 判断方法、失败模式与根因。所有数字来自本机实测，不是估计。

---

## 0. 结论速查

| 要做的事 | 一句话 |
|---|---|
| 判断一个 GGUF 能不能转 | 跑 `tools.convert.gguf_blocks.validate()`，报 `tensor set mismatch` 或 `X is Y (shape)` 就是不能 |
| 转换主权重 | `python -m tools.convert --recipe qwen3_8_27b_gguf --source gguf=... --components text,vision` |
| 补 MTP 头 | `scripts/experimental/graft_mtp_from_gguf.py`（本仓自写，2026-11-08） |
| 补 DFlash2 头 | `scripts/experimental/graft_dflash2.py`（既有） |
| 选哪个 GGUF | **优先选保留 norm/alpha 为 F32/BF16 的**（ISTA-DASLab GSQ-RCO）；unsloth UD 系需打补丁 |
| 用哪个投机头 / 深度 | **DFlash2 + d5**（197.5 tok/s）；要更大池才退 MTP + d3（152.7）。d6/d7 更慢，不要用 |

---

## 1. 前置条件：什么文件、在哪找

### 1.1 主权重 GGUF

| 来源 | 本机位置 | 说明 |
|---|---|---|
| unsloth Dynamic 3.0 | `models/Qwen3.8-27B-UD-Q3_K_XL.gguf`（12.24 GB） | 需打兼容补丁（见 §5.1） |
| ISTA-DASLab GSQ-RCO | `J:\KVMem-GSQ\models\Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf`（11.29 GB） | **原生通过校验，且自带 MTP 头** |
| SWIFT 版 | `J:\KVMem-GSQ\models\Swift-1.5-...-IQ3_S-mtp.gguf` | 现有 SWIFT 件的源 |

### 1.2 HF 元数据（`--model` 必需）

**位置：`J:\Bonsai\landing\weights\Qwen3.8-27B\`**（本机已有全套）

必需文件：
```
config.json                    ← recipe 读架构
tokenizer.json                 ← 运行时校验 Split pattern，GGUF 自带的不够
tokenizer_config.json
generation_config.json
preprocessor_config.json       ← 视觉需要
video_preprocessor_config.json ← 视觉需要
chat_template.jinja            ← 可用 tools/chat_templates/qwen3_8.jinja 覆盖
```

**坑：GGUF 里虽然带 `tokenizer.ggml.tokens`（248,320 个）和 `chat_template`，但结构与 HF 的
`tokenizer.json` 不同，运行时会对 Split pattern 做精确校验，不能用 GGUF 的替代。**

### 1.3 视觉塔（mmproj）

**位置：`J:\KVMem-GSQ\models\`**

```
mmproj-Qwen3.8-27B-BF16.gguf      0.87 GB
mmproj-Qwen3.8-27B-Q5_K-MIX.gguf  0.32 GB
```

转换后视觉塔固化成 **282 MiB**（441 个绑定，q4_g64/q5_g64/q8_g32 混合），**运行时不需要 mmproj 文件**。

### 1.4 MTP 头（单独文件时）

unsloth 的 `MTP/mtp-Qwen3.8-27B-Q4_0.gguf` **1.37 GB**，其中：
- `token_embd` 546 MB + `output` 546 MB = **80% 是副本，不要**
- `blk.64.*` 15 个张量 **266 MB** = 真正要的

### 1.5 DFlash2 头

**位置：`models/dflash2/`**
```
Qwen3.8-27B-DFlash2-Q4_K_M.gguf   1.06 GB   ← 用这个
Qwen3.8-27B-DFlash2-BF16.gguf     0.04 GB   ← codebook 参考
```

### 1.6 运行环境

| 项 | 要求 | 本机实测 |
|---|---|---|
| Python | 文档说 3.11，**实际 3.13.5 可用** | `J:\miniconda3\python.exe` |
| torch | 必需 | **2.10.0+cu130 已装** |
| numpy | 必需 | 2.3.2 已装 |
| `gguf` 包 | **必需**（`pip install gguf`） | 已装 |

⚠ `C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe` **没有 torch**，别用它。

---

## 2. 判断流程：一个 GGUF 能不能转

### 2.1 三步判定

```python
import sys
sys.path.insert(0, r'J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src')
from tools.convert.sources.gguf import GGUFFile
from tools.convert.gguf_blocks import validate, has_mtp

g = GGUFFile(r'<待测.gguf>')
try:
    validate(g)
    print('PASS  mtp =', has_mtp(g))
except Exception as e:
    print('FAIL ', e)
```

| 结果 | 含义 | 怎么办 |
|---|---|---|
| `PASS` + `mtp=True` | 完美，转换即带 MTP | 直接用 |
| `PASS` + `mtp=False` | 主权重可用，缺 MTP | 转换后 graft MTP（§4） |
| `FAIL ... is Q8_0 (48, 5120)` | GDN 的 ssm_alpha/beta 被量化 | 打 §5.1 补丁 |
| `FAIL ... tensor set mismatch` | 张量名/数量不符 | **放弃**，不是 Qwen3.8-27B 结构 |

### 2.2 支持的块类型（15 种，硬边界）

```
8 Q8_0    10 Q2_K   11 Q3_K   12 Q4_K   13 Q5_K   14 Q6_K
16 IQ2_XXS  17 IQ2_XS  18 IQ3_XXS  19 IQ1_S
20 IQ4_NL   21 IQ3_S   22 IQ2_S    23 IQ4_XS   29 IQ1_M
```

**不支持**：`Q4_0`(2)、`Q4_1`(3)、`Q8_K`(15)、`F32`(0)/`BF16`(30) 作为量化块出现。

### 2.3 recipe 的张量期望分类

```
blocks 402 个  ← 必须是上述 15 种之一
F32    353 个  ← 必须精确 F32
BF16    96 个  ← 必须精确 BF16（就是 ssm_alpha/beta 各 48）
```

**校验规则（`gguf_blocks.py:157-163`）：非 blocks 张量格式必须精确相等，不做 dequant 回退。**

---

## 3. 转换主权重

```powershell
$env:PYTHONUTF8='1'
Set-Location 'J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src'

& 'J:\miniconda3\python.exe' -X utf8 -m tools.convert `
  --model 'J:\Bonsai\landing\weights\Qwen3.8-27B' `
  --recipe qwen3_8_27b_gguf `
  --source 'gguf=<主权重.gguf>' `
  --source 'vision=J:\KVMem-GSQ\models\mmproj-Qwen3.8-27B-BF16.gguf' `
  --components 'text,vision' `
  --resource 'chat_template.jinja=tools/chat_templates/qwen3_8.jinja' `
  --proposal `
  --name '<公开名>' `
  --out 'J:\ninfer-kvmem\models\<输出>.ninfer'
```

**关键参数说明**

| 参数 | 作用 | 坑 |
|---|---|---|
| `--components` | `text,vision,mtp,dflash,dflash2` 子集 | **GGUF 无 `blk.64.nextn` 时不能写 `mtp`**，否则 `ValueError: the MTP component needs an -mtp GGUF` |
| `--proposal` | 生成 131,072 行的 proposal head（约 461 MB） | 不用投机可以省掉 |
| `--source vision` | mmproj GGUF | 不给就无视觉 |
| `--out` | 必须是不存在的路径 | 已存在会拒绝 |

**实测耗时**：1151 个对象，约 5 分钟（GPU 转换）。

**产物大小**：`UD-Q3_K_XL`(12.24 GB) → `ud_q3kxl.ninfer` 12.64 GiB（含 vision 282 MiB + proposal 461 MB）。

---

## 4. 嫁接 MTP 头

### 4.1 工具

`scripts/experimental/graft_mtp_from_gguf.py`（2026-11-08 新写）

```powershell
& python -X utf8 'scripts\experimental\graft_mtp_from_gguf.py' `
  --base 'models\ud_q3kxl.ninfer' `
  --gguf 'models\mtp-Qwen3.8-27B-Q4_0.gguf' `
  --out  'models\ud_q3kxl_mtp.ninfer' `
  --dry-run      # 先跑这个，确认 unbound new names = []
```

**实测**：112.8s，产物 +266 MB（12.64 → 12.89 GiB）。

### 4.2 15 个张量 → 16 个绑定的映射表

| MTP GGUF 张量 | NINFER 绑定 | 处理 |
|---|---|---|
| `blk.64.attn_q` `[12288,5120]` | `attention/query` | **拆前 6144 行** |
| 同上 | `attention/gate` | **拆后 6144 行** |
| `blk.64.attn_k` `[1024,5120]` | `attention/key` | 直传 |
| `blk.64.attn_v` `[1024,5120]` | `attention/value` | 直传 |
| `blk.64.attn_output` `[5120,6144]` | `attention/output` | 直传 |
| `blk.64.attn_q_norm` `[256]` | `attention/query_norm` | F32→bf16 |
| `blk.64.attn_k_norm` `[256]` | `attention/key_norm` | F32→bf16 |
| `blk.64.attn_norm` `[5120]` | `layers/0/input_norm` | F32→bf16 |
| `blk.64.post_attention_norm` `[5120]` | `layers/0/post_attention_norm` | F32→bf16 |
| `blk.64.ffn_gate` `[17408,5120]` | `mlp/gate` | 直传 |
| `blk.64.ffn_up` `[17408,5120]` | `mlp/up` | 直传 |
| `blk.64.ffn_down` `[5120,17408]` | `mlp/down` | 直传 |
| `blk.64.nextn.eh_proj` `[5120,10240]` | `input_projection` | 直传 |
| `blk.64.nextn.enorm` `[5120]` | `embedding_norm` | F32→bf16 |
| `blk.64.nextn.hnorm` `[5120]` | `hidden_norm` | F32→bf16 |
| `blk.64.nextn.shared_head_norm` `[5120]` | `final_norm` | F32→bf16 |

### 4.3 三件必须做的事（漏一件就起不来）

1. **`components` 加 `"mtp": {"config": {"architectures": ["Qwen3_5MTP"]}, "target": "text"}`**
2. **9 条 `uses`**（全部 `activation_policy: AllowA8`）：
   ```
   mtp/input_projection            ← mtp/stem_input
   mtp/layers/0/attention/query    ← mtp/layers/0/mixer_input
   mtp/layers/0/attention/gate     ← mtp/layers/0/mixer_input
   mtp/layers/0/attention/key      ← mtp/layers/0/mixer_input
   mtp/layers/0/attention/value    ← mtp/layers/0/mixer_input
   mtp/layers/0/attention/output   ← mtp/layers/0/attention/gated_output
   mtp/layers/0/mlp/gate           ← mtp/layers/0/ffn_input
   mtp/layers/0/mlp/up             ← mtp/layers/0/ffn_input
   mtp/layers/0/mlp/down           ← mtp/layers/0/mlp/product
   ```
3. **多加一条 `text/output_head ← mtp/final_hidden`**
   （MTP 复用主模型输出头；缺这条会 `FATAL: missing Use text/output_head@mtp/final_hidden`）

### 4.4 格式不必转换

unsloth 文件名叫 `Q4_0`，实际内部是 **q6_k（attn）+ q4_k（ffn）+ F32（norm）**，
全部受支持，**按原块字节直传即可，不需要 recode 成 q8_0**。

> `scripts/recode_mtp.py` 只在**源是真正 Q4_0** 时才需要（Coder390 原件就是那种，
> Q4_0→Q8_0 位精确无损，但体积 +89%）。优先用 `--target-format gguf_iq4_nl` 保持体积。

---

## 5. 失败模式与根因（今天踩过的全部坑）

### 5.1 `X is Q8_0 (48, 5120)` —— unsloth UD 系不兼容

**根因**：unsloth Dynamic 量化为了省 12 MB，把 GDN 门控参数 `ssm_alpha/beta`（各 48 个）
从 BF16 压成 Q8_0。recipe 要求这两个是 BF16，且**没有通用 dequant 回退路径**。

**解法**（已写入本仓，两处改动，只影响转换工具）：

| 文件 | 改动 |
|---|---|
| `tools/convert/sources/gguf.py` | `read_bf16_words` 增加 Q8_0 分支：`block = fp16_scale × int8`，反量化后按 bf16 返回；并补 `TYPE_Q8_0 = 8` |
| `tools/convert/gguf_blocks.py` | `validate` 对 `ssm_alpha/beta` 放宽（`tolerated` 时只校验 shape）；定义 `USABLE_Q8 = frozenset((8,))` |

**注意**：`validate` 里 `stored` 对 Q8_0 为真，而 `kind` 是 "BF16"，所以 `(kind=="blocks") != stored`
会先成立 —— 只把 `tolerated` 加在第三个条件上是**无效的**，必须整条短路。

### 5.2 `ImportError: reading a .gguf source requires the 'gguf' package`

```powershell
& 'J:\miniconda3\python.exe' -m pip install gguf -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 5.3 `FATAL: missing Use text/output_head@mtp/final_hidden`

见 §4.3 第 3 条。

### 5.4 `ArtifactError: weight/900000: expected nonempty string without NUL`

`TensorSpec` 第三个参数要**格式名字符串**（`fmt.name`），不是格式对象。

### 5.5 起服 FATAL 但瓦工没报错

**先查通道**：`nvidia-smi --query-gpu=memory.used`。
- `used ≈ 60 MiB` → 核显通道，预算 ~4,217 MiB（arith）
- `used ≥ 1,100 MiB` → 独显通道，桌面（explorer/NVIDIA Overlay）占 1–2 GB，可用空间直接少 2 GB

**2026-11-08 实测**：独显通道下 `used 2,086 MiB`（explorer + **NVIDIA Overlay ×2** + 开始菜单），
`ud_q3kxl_mtp` 的 86,016 池直接 FATAL，降到 32,768 才起。

### 5.6 `T-WINDOW VIOLATION` 但记录写着"可见=True"

**不一定是窗口真的不可见**。引擎 FATAL 立即退出时，tee 宿主的窗口随之消失，
窗口门在检查时点抓不到窗口 → 判违规。**先看是否 FATAL，再怀疑窗口纪律。**

---

## 6. 实测数据汇总（本机 5080 / 16,303 MiB）

### 6.1 各件权重与池

| 件 | weights | 池上限（核显 / 独显） |
|---|---|---|
| CODER390 双头（MTP 头） | 12.3 GiB | 86,016 / 58,368 |
| CODER390 双头（DFlash2 头） | 13.5 GiB | 40,960 / 32,768 |
| SWIFT15 双头（MTP 头） | 11.3 GiB | 126,976 / 98,304 |
| SWIFT15 双头（DFlash2 头） | 12.3 GiB | 90,112 / 51,200 |
| **GSQ IQ3_S 双头（MTP 头）** | **11.3 GiB** | **126,976 / 98,304**（131,072 FATAL：need 4245.3 > avail 4217.1） |
| **GSQ IQ3_S 双头（DFlash2 头）** | **12.3 GiB** | **90,112 / 51,200**（94,208 FATAL：need 3222.1 > avail 3133.9） |
| ~~ud_q3kxl（裸）~~ | ~~11.9 GiB~~ | 已删除（接受率不可用） |
| ~~ud_q3kxl_mtp~~ | ~~12.2 GiB~~ | 已删除（接受率 13.7%） |

### 6.2 速度

| 件 | 投机 | decode | 接受率 |
|---|---|---|---|
| CODER390 | MTP k3 | **130.3** | 56.4% |
| CODER390 | DFlash2 k5 | 134.8 | 39.8% |
| SWIFT15 | MTP k3 | 114.3 | 44.3% |
| SWIFT15 | DFlash2 k5 | 116.0 | 28.8% |
| ~~ud_q3kxl（裸）~~ | ~~无~~ | ~~58.4~~ | 已删除 |
| ~~ud_q3kxl_mtp~~ | ~~MTP d1~~ | ~~66.2~~ | ~~26.9%~~ 已删除 |
| ~~ud_q3kxl_mtp~~ | ~~MTP d3~~ | ~~63.0~~ | ~~13.7%~~ 已删除 |
| ~~ud_q3kxl_mtp~~ | ~~MTP d5~~ | ~~43.1~~ | ~~3.9%~~ 已删除 |

**⚠ 旧口径：66-token 单题（2026-11-14 核显复测，仅供历史；同口径六臂见 §6.2e）**

| 件 | 头 | 池 | decode | 接受率 |
|---|---|---|---|---|
| CODER390 | MTP k3 | 86,016 | 154.9 | 64.2% |
| CODER390 | DF2 k5 | 40,960 | 194.4 | 62.1% |
| SWIFT15 | MTP k3 | 126,976 | 138.1 | 56.6% |
| SWIFT15 | DF2 k5 | 90,112 | 186.0 | 57.6% |
| **GSQ** | **MTP k3** | 126,976 | **152.7** | **64.3%** |
| **GSQ** | **DF2 k5** | 90,112 | **202.6** | 59.3% |

> 独显通道的旧数据（130.3 / 134.8 / 114.3 / 116.0）已被核显通道整体推翻：**同件同池，核显快 19–60%**，DFlash2 受益最大（权重多 1.2 GiB，独显通道页出最严重）。

### 6.2b DFlash2 深度扫描（GSQ 双头，池 90,112，核显，每档重启 + 单请求）

| draft | decode | 接受率 | 相对 d5 |
|---|---|---|---|
| d3 | 160.9 | 64.4% | −18.6% |
| d4 | **190.7 ± 0.0**（3 轮钉实） | **69.8%** | −3.6% |
| **d5** | **197.5 ± 0.1**（3 轮钉实） | 59.3% | **峰值** |
| d6 | 180.3 | 50.3% | −8.8% |
| d7 | 163.3 | 45.3% | −17.4% |

**结论**：
- **d5 是速度甜点**，d4 紧随（−3.6%），**d6/d7 明确变慢**（验证成本增长快于接受收益）。
- 接受率 d4 最高（69.8%），但速度不如 d5；追求低延迟优先接受率才选 d4。
- 曲线形状与旧件（§205：d4=36.2% → d5=32.2% → d6=26.3%）**完全不同**：GSQ 深位接受率高 20–30 个百分点，说明草稿头质量高一个档次 —— **但依然没有 d6+ 的收益，瓶颈从"草稿质量"转成了"验证算力"**。

### 6.2c 负载类型对速度的影响（GSQ MTP @ 126,976，prompt 508–516 token，cache 0）

| 负载 | decode（3 次均值） | 接受率 |
|---|---|---|
| **struct（代码 / JSON）** | **141.6** | 59–63% |
| short-struct（128 out） | 141.0 | 51–69% |
| prose（散文） | 125.5 | 43–55% |
| **conv（对话）** | **110.2** | 40–42% |

**MTP 收益与「输出可预测性」正相关，与提示长度无关**：代码/JSON 可预测 → 60%；对话/散文自由 → 40%。

### 6.2e 六臂同口径（512-token / 四负载 / cache 0）—— **唯一可用于横比的表**

口径：prompt 508–516 token（服务端 `usage` 校准）、output 128/256、greedy、每格 3 次、核显通道、graph64+arith、**每次请求带唯一 `user` 保证 cache=0**。

| 臂 | short-struct | struct | prose | conv |
|---|---|---|---|---|
| GSQ MTP d3 @126,976 | 141.0 / 63% | 141.6 / 61% | 125.5 / 50% | 110.2 / 41% |
| GSQ DF2 d5 @90,112 | 159.1 / 51% | 183.7 / 57% | 137.7 / — | 131.5 / 38% |
| CODE MTP d3 @86,016 | 150.3 / 68% | 149.5 / 65% | 110.3 / 45% | 114.2 / 47% |
| CODE DF2 d5 @40,960 | 136.7 / 55% | 140.6 / 58% | 94.7 / — | 102.0 / — |
| SWIFT MTP d3 @126,976 | 129.1 / 52% | 161.4 / **73%** | 121.6 / 48% | 118.2 / 46% |
| **SWIFT DF2 d5 @90,112** | **172.6** / 53% | **196.7** / — | **142.7** / 41% | **129.1** / — |

（单元格 = decode tok/s / 接受率）

**排名与 66-token 旧口径完全相反**：

| 头 | 旧（66-token） | **新（512-token struct）** |
|---|---|---|
| DF2 | GSQ 202.6 > CODE 194.4 > SWIFT 186.0 | **SWIFT 196.7 > GSQ 183.7 > CODE 140.6** |
| MTP | CODE 154.9 > GSQ 152.7 > SWIFT 138.1 | **SWIFT 161.4 > CODE 149.5 > GSQ 141.6** |

**注意**：CODE 双头权重 14.02 GiB，DFlash2 池只有 40,960（别件 45%），它的 140.6 是池的代价，不是头差。同池可比对只有 GSQ vs SWIFT（都 90,112）：**SWIFT 快 7.1%**。

### 6.2d 长上下文（32,758 token prompt，池 126,976）

| 指标 | 值 |
|---|---|
| prefill | 852–867 tok/s |
| **TTFT** | **165.7 s** |
| decode | 112.2 / 127.1 / 144.2 |
| TPOT | 21.0 ms/chunk（P90 22.0），归一化 ≈8.8 ms/token |

**长上下文的瓶颈是 prefill 不是 decode**：32k prompt 要 2 分 45 秒才出第一个字，而 decode 仍有 110+。

### 6.3 结构性开销（决定池大小）

| 组件 | 大小 | 折合池 token（0.0355 MiB/token） |
|---|---|---|
| 视觉塔 | 282 MiB | ~7,950 |
| MTP 头（iq4_nl / q6_k） | 228–266 MiB | ~6,400–7,500 |
| DFlash2 头 | 1.38 GiB | **~38,000** |
| proposal head | 461 MB | 仅投机用，是否上卡待查 |

---

## 7. 风险清单

| 风险 | 后果 | 规避 |
|---|---|---|
| **MTP 头与主权重非同源** | 接受率崩（实测 13.7%，正常应 >40%） | 用同一发布方的 MTP；或接受低接受率 |
| **unsloth 量化 ssm_alpha/beta** | GDN 门控精度已损，MTP 依赖 hidden，误差放大 | 优选 ISTA-DASLab GSQ-RCO 系 |
| **DFlash2 头 1.38 GiB** | 吃掉 ~38k token 池，16 GB 卡不划算 | 只在需要 DFlash2 速度时加 |
| **独显通道** | 可用空间少 1–2 GB，高池必 FATAL | `nvidia-smi` 先查 `used` |
| **磁盘** | 转换 + 嫁接每个件约 13 GiB，中间产物要清 | `.tmp` 与中间件用完即删 |
| **`--components mtp` 对无 MTP 的 GGUF** | 直接 `ValueError` | 先 `has_mtp()` 判断 |
| **recipe 校验不做 dequant 回退** | 任何被量化的 norm/alpha 都会整件拒绝 | 先 `validate()` 探路 |
| **测试脚本在请求之间读 tee 日志** | `Get-Content` 独占打开日志 → tee 写失败退出 → 引擎随管道断开而死 → **表现为「第二个请求连接被拒」，极易误判成池不够**（2026-11-14 我据此错误结论「90,112 只能服务 1 个请求」，实为脚本 bug；用不读日志的脚本复测，90,112 与 126,976 都能连续服务 5 个真实请求） | 压测脚本**只在全部请求结束后读一次日志**；或读日志前先 `Copy-Item` 到临时文件再读 |
| **用采样/贴边池做多轮基准** | 每档单独重启引擎才等价；同实例连发会因首请求占用 KV 导致后续请求行为变化 | 基准测量一律「一档一重启」，且每次请求带唯一 `user`（否则引擎按 turn closure 复用 97% 前缀缓存，实测把 struct 从 141.6 夸大到 237.8） |
| **只看 `capacity` 行的 `free` 判可用性** | `free 0 B` 是 arith 纸面余量，不代表物理；`slack 13.6 MiB` 仍可能连续服务 5 个真实请求 | 判可用性用「连续 5 个真实请求是否全成功」，不用单看 free |

---

## 8. 最小可复现流程（复制即用）

```powershell
$env:PYTHONUTF8='1'
$ENG = 'J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src'
$PY  = 'J:\miniconda3\python.exe'
Set-Location $ENG

# ① 判定
& $PY -X utf8 -c "import sys;sys.path.insert(0,r'$ENG');from tools.convert.sources.gguf import GGUFFile;from tools.convert.gguf_blocks import validate,has_mtp;g=GGUFFile(r'<src.gguf>');validate(g);print('PASS mtp=',has_mtp(g))"

# ② 转换（无 MTP 的 GGUF）
& $PY -X utf8 -m tools.convert --model 'J:\Bonsai\landing\weights\Qwen3.8-27B' `
  --recipe qwen3_8_27b_gguf --source 'gguf=<src.gguf>' `
  --source 'vision=J:\KVMem-GSQ\models\mmproj-Qwen3.8-27B-BF16.gguf' `
  --components text,vision `
  --resource 'chat_template.jinja=tools/chat_templates/qwen3_8.jinja' `
  --proposal --name '<name>' --out 'J:\ninfer-kvmem\models\<out>.ninfer'

# ③ 嫁 MTP（dry-run 先看 unbound=[]）
& python -X utf8 'J:\ninfer-kvmem\scripts\experimental\graft_mtp_from_gguf.py' `
  --base 'models\<out>.ninfer' --gguf 'models\mtp-Qwen3.8-27B-Q4_0.gguf' `
  --out 'models\<out>_mtp.ninfer' --dry-run
& python -X utf8 'J:\ninfer-kvmem\scripts\experimental\graft_mtp_from_gguf.py' `
  --base 'models\<out>.ninfer' --gguf 'models\mtp-Qwen3.8-27B-Q4_0.gguf' `
  --out 'models\<out>_mtp.ninfer'

# ④ 嫁 DFlash2（可选）
& python -X utf8 'J:\ninfer-kvmem\scripts\experimental\graft_dflash2.py' `
  --base 'models\<out>_mtp.ninfer' --gguf 'models\dflash2\Qwen3.8-27B-DFlash2-Q4_K_M.gguf' `
  --out 'models\<out>_dual.ninfer'
```

---

## 9. 尚未验证 / 已知空白

- ~~`ud_q3kxl` 与 `ud_q3kxl_mtp` 的池上限从未扫过~~ → **该两件已删除**（接受率 13.7%，无实用价值）。
- ~~MTP 接受率低（13.7%）的根因未定位~~ → **已定位为同源性**：同源件 GSQ 一次转出即 64.3%，unsloth 独立 MTP 文件只有 13.7%（4.7 倍差）。GDN 门控被打包方量化也有影响，但非主因。
- **d6/d7 变慢的算力拆解未做**：目前只知道「验证成本增长快于接受收益」，具体是 verify 前向、KV 写入还是 draft 生成本身，未做 profile。
- `swift_dflash2` bundle 的 `graph=192` 与 16K 池组合未重测（若跑到 88K 必须降到 64）。
- proposal head 461 MB 是否常驻显存未确认（若常驻，未开投机时应能省下）。
- **多轮长会话未压测**：所有测量都是单请求或 5 个独立请求，没有做「同一会话持续增长 100k token」的场景。
- **DP 对比只做了 3 题**：GSQ / CODER390 / SWIFT 在代码与推理上打平，但样本量不足以区分能力上限。
