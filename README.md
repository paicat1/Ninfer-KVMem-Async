# Qwen38-27B-NInfer-kvmem

**在两代前序工程跑通的架构上，部署更大的模型（Qwen3.8-27B-Coder390，27B）。**

三代演进：

| 代 | 仓 | 验证了什么 |
|---|---|---|
| 一 | [**paicat1/Bonsai-27B-NInfer**](https://github.com/paicat1/Bonsai-27B-NInfer)（main=项目层 / engine-main=引擎层） | **Bonsai 2 跑上 NInfer 引擎**——三元量化（2.125bit）+ MTP 投机，**快**（decode 100+ tok/s） |
| 二 | [**paicat1/Bonsai-27B-NInfer-kvmem**](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem) | **NInfer × KVMem 结合**——灵活配置；有限显存下把 KV 下放内存（16 GiB host 环），**架构跑通** |
| 三 | [**paicat1/Qwen38-27B-NInfer-kvmem**](https://github.com/paicat1/Qwen38-27B-NInfer-kvmem)（本仓） | 架构验证完成后，**部署 Qwen3.8-27B 系 NInfer 容器**——256K 逻辑上下文、自转 MTP 头、思考预算熔断、视觉塔嫁接，全部工程结论从踩坑到定稿；**并作为 Qwen 4 27B（Bonsai/NInfer 格式）的着陆预备** |

> 硬件基线：RTX 5080 16 GB + 128 GB RAM，Windows，全部结论为实测（非推测）。

---

## 从两仓成果到今天：继承、堵点、压榨、成绩

### 继承：前两仓留下的三件武器

| 武器 | 来自 | 在本仓的作用 |
|---|---|---|
| **MTP 投机解码** | 仓一（Bonsai on NInfer） | decode 105 → 233 tok/s 的来源 |
| **KVMem 环** | 仓二（NInfer×KVMem 融合） | KV 大挪移：显存装不下的页自动下沉 16 GiB 内存——256K 深度的根基 |
| **工具链 + GUI 配置能力** | 两仓沉淀 | 量化/转换/校验脚本与启动器全部复用，本仓只做增量 |

### 第一关：让 27B 大模型上车

Bonsai 线跑的是小模型，本仓要上 **Qwen3.8-27B-Coder390**（27B、256K 原生上下文、自带视觉组件）。第一堵点：**引擎没有现成的 MTP 头**。

- 第一次尝试（q8 重打包，头 451 MB，13.49 GB）：**起不来**——显存装不下；
- 第二次（`recode_mtp.py` 抽层自转头，iq4_nl 量化，头 239 MB）：**成功**——比官方头小 212 MB，省下的空间后来全转给了 KV 池。

### 第二关：撞墙——思考 30 秒被砍

上车后真实使用立刻撞墙：**agentic 任务思考 30-40 秒就被砍断**（`finish=length`），客户端显示"已达到输出 token 上限"并不停要"继续"——Bonsai 时代的短任务没暴露，27B 的长思考把这颗雷踩响了。

三方取证（引擎日志 + 源码 + 官方 README）定案：`--kv-lease-growth` 在"池 ≪ 逻辑上下文"的深超池构型下，把输出砍在 ~4,096 token 的租约窗口上（bounded completion）。**修复三件套**：定稿移除 growth + 引擎层修掉思考熔断三连缺陷（W1-W4，patch 84 行）+ 客户端保活。

**修复后**：两轮真实 agentic 实测零截断——单请求连续输出 **16,143 token**（旧墙的 4 倍）。

### 第三关：视觉——282 MiB 视觉塔整体嫁接

27B 容器原本没有视觉。做法不是重转模型，而是**逐字节嫁接**：官方视觉塔 333 个对象（282 MiB，q4/q5/q8/bf16 混合精度）原样搬进自转头容器——`graft_vision.py` 全程格式校验。识图实测 **26.9 秒**（CPU 编码，零设备显存）。

### 压榨：每个参数都标定过

| 参数 | 起点 | 终点 | 方法 |
|---|---|---|---|
| KV 池 | 40,960 | **51,200**（55K 贴边不可复现、56K 缺 17-50 MiB 实测弃案） | 逐档起服，以启动预约字节数精确定档 |
| 逻辑上下文 | 128K | **256K** | 模型原生上限，池外 KV 下放 16 GiB 内存环 |
| decode | ~100 tok/s | **105-233 tok/s** | MTP 接受率（混合投机） |
| prefill | — | 1.5-2.2k tok/s | 超池召回被流水化吸收（开销仅 8-23%，零截尾） |
| 显存 | — | 16 GB 卡跑 27B + 视觉 + 51K 池，free 490 MiB | 池/权重/工作区逐项对账 |

### 成绩单

| 项 | 修复前（Bonsai 线同场景） | 本线今天 |
|---|---|---|
| agentic 编程任务 | 思考 30 s 被砍、无限"继续" | **飞机游戏 4m33s 完整跑通（829 行，可直接玩）**、雾铃镇 3D 小镇 **1m39s** |
| 单请求连续输出 | ~4,096（租约窗口砍断） | **16,143 token** |
| 逻辑上下文 | 128K | **256K** |
| KV 池 | 40,960 | **51,200 稳定**（标定上限 55,296） |
| decode 速度 | ~100 tok/s | **105-233 tok/s** |
| 视觉 | 无 | **识图 26.9 s**（CPU 编码零显存） |

---

## 当前定稿（2026-10-11）

| 项 | 值 |
|---|---|
| 引擎 | `self-built-20261008`（官方源码 s6-20261008 @ `3b9dc83` + W1-W4 修复 patch） |
| 池 | **51,200 token（800 页）**——当前桌面负载下可复现的稳定档 |
| 上下文 | 256K 逻辑（262,144，模型原生上限）；池外 KV 自动下沉 16 GiB host 环 |
| 投机 | MTP K4（自转头，iq4_nl 量化，239 MB） |
| 思考 | medium/high + `--default-thinking-budget 16000` |
| 止血 | `--recover-invariant-failures`，**无 `--kv-lease-growth`**（撞墙根因，见下） |
| 视觉 | 嫁接件 `mtp-iq4nl.vision.ninfer` + `--vision-cpu`（零设备显存） |
| 并发 | **1**（KVMem 环硬约束，见已知限制） |

## 快速开始（已有引擎与模型时）

```
启动器.bat            # GUI 唯一入口，8 个预设
```

选预设 **★定稿 51200稳定（无growth）** → 起服 → `http://127.0.0.1:8094/v1`（OpenAI 兼容）。

命令行等价（⚠️ **KV_ENV 五开关缺一不可**：缺 `NINFER_KV_WINDOW` 引擎拒启，缺其余"起得来但静默答错"）：

```bat
set NINFER_KV_WINDOW=32768
set NINFER_KV_RETRIEVE=8192
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
engine\self-built-20261008\ninfer-serve.exe models\...mtp-iq4nl.ninfer ^
  --host 127.0.0.1 --port 8094 --max-context 262144 --kv-capacity 51200 ^
  --kv-dtype rk2v4-e8 --host-kv-mib 16384 --prefill-chunk 512 ^
  --spec mtp --draft-tokens 4 --default-max-tokens 32768 ^
  --default-reasoning-effort high --default-thinking-budget 16000 ^
  --max-concurrency 1 --recover-invariant-failures
```

客户端：任何 OpenAI 兼容工具；DSH 接入见 `docs/`（provider 配置示例含 `streamIdleTimeoutMs`）。

## 仓库结构（诚实的 overlay 定位）

本库**不是**自包含的引擎发行包，而是"**官方引擎源码 + 本线全部工作产物**"的工作区叠加层：

| 路径 | 内容 | 在库内 |
|---|---|---|
| `docs/` | **构建史（v1-v32 完整历程）**、8 份交叉审核报告、4 份调研、教程 | ✅ |
| `build/` | 引擎构建脚本（`s6_1208a.bat` 等）+ 3 份引擎补丁 + 产物清单 | ✅ |
| `scripts/` | 模型加工（`recode_mtp.py` 自转 MTP 头、`graft_vision.py` 视觉嫁接）+ 探针（`test_ab_arm1.py`/`probe_recall*.py`） | ✅ |
| `patches/` | **W1-W4 引擎修复**（84 行，含四重验收） | ✅ |
| `ninfer_launcher.py` | GUI 唯一入口（8 预设、校验告警、KV_ENV 注入） | ✅ |
| `serve_tee.py`、`start-coder390*.bat` | 起服工具 | ✅ |
| `official-repo/` | **引擎源码**（嵌套 clone，s6-20261008） | ❌ 未跟踪（来源见复现指南） |
| `engine/` | 构建产物二进制（~6.5 GB） | ❌ 本地构建 |
| `models/` | 模型三件套（~40 GB，见下） | ❌ 外部下载+本库脚本加工 |
| `refs/` | 发放包与 Bonsai 线参考材料 | ❌ |

### models/ 三件套（一条进化链）

**本线原件下载地址（实测来源，ModelScope）**：
[`Merkyor/Qwen3.8-27B-Coder390-EfficientThink-...-RLOO-GGUF-NInfer/tree/master/GGUF-NInfer`](https://modelscope.cn/models/Merkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-GGUF-NInfer/tree/master/GGUF-NInfer)
（HuggingFace 上游参考：[nerkyor 同名系](https://huggingface.co/nerkyor)，Apache-2.0；"Q2LynnStyle" 为 Lynn 式 q2 混合精度的量化风格标签）

```
MTP.ninfer（orig 原件，13.27 GB，上表下载件的 NInfer 容器，无头无视觉）
  └─ recode_mtp.py 抽层自转 MTP 头（iq4_nl，239 MB）
       → mtp-iq4nl.ninfer（13.27 GB，文本主力）
            └─ graft_vision.py 逐字节嫁接官方视觉塔（333 对象，282 MiB）
                 → mtp-iq4nl.vision.ninfer（13.57 GB，视觉主力）
```

## 从零复现指南

**前置**：Windows · RTX 5080 16 GB（或同档）· 128 GB RAM · VS2022 BuildTools（C++20、CMake、Ninja）· CUDA 13.3 · Python 3.12。

1. **引擎源码（公开 GitHub 仓库）**：
   ```bat
   git clone https://github.com/1314521gjy/ninfer-fusion-kvmem.git
   cd ninfer-fusion-kvmem
   git checkout s6-20261008        # 3b9dc83 —— 本线基线
   ```
   放置为 `official-repo/ninfer-fusion-kvmem/`。
   **免构建替代**：发放包（沈三殊分发，`refs/01-沈三殊-发放包/00-先读我-总纲.md` 有完整说明）提供**预编译引擎 exe**（按显卡取一个，~1.1 GB）——不写代码只想跑的话直接用它；模型从同层 `01-模型下载清单（推荐链接）.md` 下载（含地址/体积/sha256/加速法）；
2. **应用修复**：`git apply patches/W1-W4_engine_fix.patch`（W1-W4：思考预算熔断 `==`→`>=`、越界不再 abort、control 强制闭合、prompt-progress 门控放宽——四处均已实测验收）；
3. **构建**：`build/s6_1208a.bat`（或 VS 环境 + `cmake --build <dir> --target ninfer-serve`；构建要点见 `build/README.md` 与 `build/patches/`）；产物部署到 `engine/self-built-20261008/`；
4. **模型加工**：下载原件（Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle）→ `python scripts/recode_mtp.py --src ORIGINAL.ninfer --mtp-src Q8MTP.ninfer --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst ...mtp-iq4nl.ninfer --verify` → `python scripts/graft_vision.py`（嫁接视觉塔）；
5. **起服验证**：上面的命令行（或 launcher）→ `curl 127.0.0.1:8094/v1/models` → `python scripts/test_ab_arm1.py`（健康探针）。

**复现难度自评：中偏低。** 引擎源码公开（GitHub）、发放包有预编译 exe（免构建路径）、模型下载含 sha256 清单、构建脚本/参数/验收探针全在本库——途径全部明确，主要工作是 CUDA 环境 + 模型下载 + 按 `docs/教程-KVMem与短测-给agent与使用者.md` 起服。唯一非公开件是发放包本身（找作者沈三殊拿，或用 GitHub 源码自构建绕开）。

## 关键工程结论（全部实测，踩坑沉淀）

- **`--kv-lease-growth` 是撞墙根因**：深超池构型（池 49-55K ≪ 逻辑 256K）下租约窗口（~4,096 tok）无法扩充时输出被砍（bounded completion，`finish_reason=length`）——超池构型要保住输出**不要开它**（官方 README:218 同口径）。已从定稿移除，撞墙清零（两轮 DSH agentic 实测：16,143/11,782 tok 连续输出零截断）。
- **池标定**：57,344 ✗（缺 17-50 MiB 随桌面负载波动）/ 55,296 贴边不可复现 / **51,200 稳定**。贴边池的余量以"启动瞬间的 WDDM 可驱逐量"为准，逐日波动。
- **挂账 39**：视觉请求 + 无 growth → `scatter.cpp:18` 断言（HTTP 500；`--recover-invariant-failures` 兜住引擎）。**视觉场景保持 growth ON**（视觉输出短，碰不到 4,096 墙）。
- **KVMem 环 = 单并发**：环无法回收另一 lane 的设备页，`--max-concurrency >1` 启动即拒——**并发与 256K 深度/检索互斥**。
- **W1-W4 已修**（思考预算熔断三连缺陷 + 流式保活），patch 与四重验收见 `patches/`。
- **超池口径（B28）**：超池 prompt 的中段答案按"未核实"对待——`NINFER_KV_RETRIEVE` 检索开关是保命符。
- **召回开销已实测**：超池 prefill 被流水化吸收（~8-23%，60K 场景往返 ≈4-8 s），零截尾。
- **push 教训**：推送成功以 `git status -sb` 的 ahead 0 为唯一判据。

## 模型支持边界与演进方向

| 状态 | 模型 | 说明 |
|---|---|---|
| ✅ **已验证** | Qwen3.8-27B 系（`Coder390-EfficientThink` Q2LynnStyle 量化的 NInfer 容器） | 本仓全部实测（A 臂两轮 DSH agentic、召回探针、视觉识图）都跑在它上面 |
| 🔶 **理论可装，未验证** | **其他 Qwen 3.8 27B 的 NInfer 容器**（如发放包清单的 `neroued/Qwen3.8-27B-NInfer` 官方转换件） | 引擎吃 `.ninfer` 容器，同构容器应可加载；MTP 头/视觉需按模型重新加工（脚本可复用）——**未跑过，不做承诺** |
| 🔶 **理论可装，未验证** | Qwen 其他系列（如 Qwen3.6-27B/35B 的 NInfer 转换件） | 同上，架构参数（KV 层布局/head_dim）不同构时需先验证 |
| 🎯 **设计目标** | **Qwen 4 27B 的 Bonsai 格式与 NInfer 格式** | 本仓的池/环/检索/加工链就是为下一代模型着陆预备的：容器一到，重跑加工脚本即可上车 |

> 加工链与容器解耦：换任何 NInfer 容器，只需重跑 `recode_mtp.py`（MTP 头自转）与 `graft_vision.py`（视觉嫁接）两个脚本——参数与验收探针全部现成。

## 已知限制

- 单并发（KVMem 环架构约束）；
- 256K 为模型原生上限——512K 属外推区，不可用（长文场景由 KVMem 检索兜底）；
- 视觉 CPU 编码 ~20 s/图（GPU 编码需视觉塔常驻 1.4 GiB 显存，须降池至 ~20K）；
- 超池中段正确性依赖检索开关（B28）。

## 文档索引

- **`docs/ninfer-kvmem-项目构建史.md`** —— v1-v32 完整历程（每个决策的证据链），**先读这个**；
- `docs/教程-KVMem与短测-给agent与使用者.md` —— 使用教程；
- `docs/审核-*.md` ×8 —— TeleAgent 与 CodeBuddy 双向交叉审核记录；
- `docs/调研-*.md` ×4 —— tancau 同源引擎对比、撞墙机制、目标路径；
- `build/README.md`、`build/产物清单.md` —— 引擎构建细节。

## 致谢

- **[tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring)** —— 本线今天解决的核心问题全部以其同源引擎的公开修复与实测为参照：思考预算熔断三连缺陷（W1-W3）的修法来源、KV 租约撞墙（bounded completion）的对照定案、`ensure_sequence_kv_mapped` 调用点与语义的核对基准。没有这份先行工作，W1-W4 的修复与撞墙定位不会有这么快的收敛。
- **沈三殊（shensanshu）** —— 引擎发放包、三元量化工具链与模型转换链（ModelScope `shensanshu/ninfer-ada-ternary`）。
- **Neroued / 1314521gjy / nerkyor（ModelScope: Merkyor）** —— NInfer 引擎、融合引擎与模型上游。

## License 与上游

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer 引擎 | [Neroued/ninfer](https://github.com/Neroued/ninfer) | Apache-2.0 |
| 融合引擎（KVMem 环 + host-backed） | [1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem) | Apache-2.0 |
| 模型（Coder390-EfficientThink 系） | [nerkyor @ HuggingFace](https://huggingface.co/nerkyor) | Apache-2.0 |
| 三元量化工具链 / 转换 / 校验 | 沈三殊（shensanshu）· ModelScope `shensanshu/ninfer-ada-ternary` | 见其发布页 |

本仓为上游衍生的部署/验证工程（非官方发布方）；详见 `LICENSE`（Apache-2.0）与 `NOTICE.md`。
