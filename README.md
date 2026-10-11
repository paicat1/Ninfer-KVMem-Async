# Qwen38-27B-NInfer-kvmem

**在两代前序工程跑通的架构上，部署更大的模型（Qwen3.8-27B-Coder390，27B）。**

三代演进：

| 代 | 仓 | 沉淀 |
|---|---|---|
| 一 | [**paicat1/Bonsai-27B-NInfer**](https://github.com/paicat1/Bonsai-27B-NInfer)（main=项目层 / engine-main=引擎层，两分支一体） | **Bonsai-2-27B 三元量化（2.125 bit，9.81 GiB）跑上 NInfer**：Ambolio 移植 + CraneBW 内核、改 CMake `89\|120a`、自产 v2 制品；Device/Host **双层 KV**（被动容量）；MTP / DFlash2 投机。极值：prefill 2,850 / decode 396.9 tok/s |
| 二 | [**paicat1/Bonsai-27B-NInfer-kvmem**](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem) | **KVMem 环（主动检索）**：显存小池 + 主机卸载、`--kv-capacity` 可小于上下文、内容打分 SELECT、五开关；**混合投机**：dflash2（K1-15）+ MTP（K1-5）+ ngram，**K=7 甜点**（K≥10 崩塌）、接受率语料效应（数数字 91% vs 散文 3.7-13.4%）；自编整套引擎（MSVC 补丁 ×7 + Design C 治"思考区 stop 空正文"）+ 双引擎对照；GUI 启动器与 serve_tee 日志工具自建。极值：**prefill 3,820 / decode 748.6 tok/s**（真实负载 19 请求，接受率 35.7-94.4%） |
| 三 | [**paicat1/Qwen38-27B-NInfer-kvmem**](https://github.com/paicat1/Qwen38-27B-NInfer-kvmem)（本仓） | 换大模型：**Qwen3.8-27B-Coder390-EfficientThink**——自转 MTP 头（iq4_nl）、思考熔断三连缺陷修复（W1-W4）、growth 定案、池标定 51,200、视觉塔嫁接、256K 逻辑上下文；**并作为 Qwen 4 27B（Bonsai/NInfer 格式）的着陆预备** |

> 硬件基线：RTX 5080 16 GB + 128 GB RAM，Windows，全部结论为实测（非推测）。

---

## 从两仓成果到今天：继承、堵点、压榨、成绩

### 继承：前两仓留下的武器库

| 武器 | 来自 | 在本仓的作用 |
|---|---|---|
| **混合投机（dflash2 + MTP + ngram）与调参方法论** | 仓二：K=7 甜点、K≥10 崩塌、**接受率是强语料依赖指标**（不能用合成文本测）、真实负载 748.6 峰值 | 本仓的 MTP K4 + ngram 档位、`test_ab_arm1.py` 的接受率/速度统计方法，全部照此模式验收 |
| **KVMem 环（主动检索式 KV 卸载）** | 仓二：显存小池 + 主机卸载、内容打分 SELECT、五开关（缺一静默答错）、埋针判活方法论（问句独立回合、MAXQ=256） | 256K 深度的根基；本仓的召回探针（`probe_recall*.py`）与 KV_ENV 注入直接继承 |
| **自编引擎方法论** | 仓一+仓二：MSVC 编译兼容补丁、双分支（项目层/引擎层）、产物 hash 台账、复现指南 | 本仓 W1-W4 patch 与构建部署照此模式（`patches/` + 产物对账 + `.bak` 回滚锚） |
| **思考预算（Design C）** | 仓二：自编 serve 的 `--default-thinking-budget` 生效 vs 发放包预编译成品 exe 不解析该字段 | 本线 tb 熔断的前身——W1-W4 修的正是它的三连缺陷（`==` 失灵/越界 abort/交接拒绝） |
| **GUI 启动器 + serve_tee** | 仓二自建（作者分发包只有 bat） | 本仓扩展到 8 预设 + 校验告警 + KV_ENV 注入 |

### 第一关：让 27B 大模型上车

Bonsai 线的 Bonsai-2-27B 任务短、无视觉，这颗雷没机会暴露；本仓要上 **Qwen3.8-27B-Coder390**（27B、256K 原生上下文、模型作者已把视觉组件打进容器），长思考一上来就把它踩响了。第一堵点：**引擎没有现成的 MTP 头**。

- 第一次尝试（q8 重打包，头 451 MB，13.49 GB）：**起不来**——显存装不下；
- 第二次（`recode_mtp.py` 抽层自转头，iq4_nl 量化，头 239 MB）：**成功**——比下载件（Merkyor 打包）里的头小 212 MB，省下的显存让更大的高速池成为可能。

### 第二关：撞墙——思考 30 秒被砍

上车后真实使用立刻撞墙：**agentic 任务思考 30-40 秒就被砍断**（`finish=length`），客户端显示"已达到输出 token 上限"并不停要"继续"——Bonsai 时代的短任务没暴露，27B 的长思考把这颗雷踩响了。

三方取证（引擎日志 + 源码 + 融合引擎上游的 README）定案：`--kv-lease-growth` 在"高速池 ≪ 逻辑上下文"的深超池构型下，把输出砍在 ~4,096 token 的租约窗口上（bounded completion）。**修复三件套**：定稿移除 growth + 引擎层修掉思考熔断三连缺陷（W1-W4，patch 84 行）+ 客户端保活。

**修复后**：两轮真实 agentic 实测零截断——单请求连续输出 **16,143 token**（旧墙的 4 倍）。

### 第三关：视觉——282 MiB 视觉塔整体嫁接

自转头的 27B 容器原本没有视觉。做法不是重转模型，而是**逐字节嫁接**：模型作者（Merkyor）容器里内置的视觉塔，333 个对象（282 MiB，q4/q5/q8/bf16 混合精度）原样搬进自转头容器——`graft_vision.py` 全程格式校验。识图实测 **26.9 秒**（CPU 编码，零设备显存）。

### 压榨：每个参数都标定过

| 参数 | 起点 | 终点 | 方法 |
|---|---|---|---|
| 高速池（显存） | 40,960 | **51,200**（55K 贴边不可复现、56K 缺 17-50 MiB 实测弃案） | 逐档起服，以启动预约字节数精确定档 |
| 逻辑上下文 | 128K | **256K** | 模型原生上限；池外 KV 下放 16 GiB 内存 host 环 |
| decode | ~100 tok/s | **105-233 tok/s** | MTP 接受率（混合投机） |
| prefill | — | 1.5-2.2k tok/s | 超池召回被流水化吸收（开销仅 8-23%，零截尾） |
| 显存总账 | — | 16 GB 卡：权重 12.3 GiB + 高速池/工作区 1.9 GiB + 视觉，free 490 MiB | 权重/池/工作区逐项对账 |

### 成绩单

| 项 | 修复前（Bonsai 线同场景） | 本线今天 |
|---|---|---|
| agentic 编程任务 | 思考 30 s 被砍、无限"继续" | **飞机游戏 4m33s 完整跑通（829 行，可直接玩）**、雾铃镇 3D 小镇 **1m39s** |
| 单请求连续输出 | ~4,096（租约窗口砍断） | **16,143 token** |
| 逻辑上下文 | 128K | **256K** |
| 高速池（显存热 KV） | 40,960 | **51,200 稳定**（标定上限 55,296；全量 KV = 高速池 + 16 GiB host 环，两级承载 256K） |
| decode 速度 | ~100 tok/s | **105-233 tok/s** |
| 视觉 | 无 | **识图 26.9 s**（CPU 编码零显存） |

---

## 当前定稿（2026-10-11）

| 项 | 值 |
|---|---|
| 引擎 | `self-built-20261008`（上游融合引擎源码，分支 s6-20261008 @ `3b9dc83` + W1-W4 修复 patch） |
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

客户端：任何 OpenAI 兼容工具；DSH 接入示例见 `docs/教程-KVMem与短测-给agent与使用者.md` 与构建史（provider 配置含 `streamIdleTimeoutMs: 3600000`）。

## 仓库结构（诚实的 overlay 定位）

本库**不是**自包含的引擎发行包，而是"**上游引擎源码 + 本线全部工作产物**"的工作区叠加层：

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
MTP.ninfer（orig 原件，13.27 GB，即上方 ModelScope 下载件的 NInfer 容器，无头无视觉）
  └─ recode_mtp.py 抽层自转 MTP 头（iq4_nl，239 MB）
       → mtp-iq4nl.ninfer（13.27 GB，文本主力）
            └─ graft_vision.py 逐字节嫁接模型作者容器内置的视觉塔（333 对象，282 MiB）
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
4. **模型加工**：从上表 ModelScope 地址下载 GGUF-NInfer 容器（即 `--mtp-src`，其内置 q8_0 MTP 头与视觉塔）与原件 → `python scripts/recode_mtp.py --src <原件>.ninfer --mtp-src <下载件>.ninfer --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst ...mtp-iq4nl.ninfer --verify` → `python scripts/graft_vision.py`（从同一下载件嫁接视觉塔）；
5. **起服验证**：上面的命令行（或 launcher）→ `curl 127.0.0.1:8094/v1/models` → `python scripts/test_ab_arm1.py`（健康探针）。

**复现难度自评：中偏低。** 引擎源码公开（GitHub）、发放包有预编译 exe（免构建路径）、模型下载含 sha256 清单、构建脚本/参数/验收探针全在本库——途径全部明确，主要工作是 CUDA 环境 + 模型下载 + 按 `docs/教程-KVMem与短测-给agent与使用者.md` 起服。唯一非公开件是发放包本身（找作者沈三殊拿，或用 GitHub 源码自构建绕开）。

## 关键工程结论（全部实测，踩坑沉淀）

- **`--kv-lease-growth` 是撞墙根因**：深超池构型（高速池 49-55K ≪ 逻辑 256K）下租约窗口（~4,096 tok）无法扩充时输出被砍（bounded completion，`finish_reason=length`）——超池构型要保住输出**不要开它**（融合引擎上游 README 第 218 行同口径）。已从定稿移除，撞墙清零（两轮 DSH agentic 实测：16,143/11,782 tok 连续输出零截断）。
- **池标定**：57,344 ✗（缺 17-50 MiB 随桌面负载波动）/ 55,296 贴边不可复现 / **51,200 稳定**。贴边池的余量以"启动瞬间的 WDDM 可驱逐量"为准，逐日波动。
- **挂账 39（已销案，2026-10-11）**：视觉请求 + 无 growth 曾触发 `scatter.cpp:18` 断言（HTTP 500）——现役引擎已不复现（V1b/V1c 实测）；视觉统一 hemostat=on（无 growth），growth 已退出所有路径。
- **KVMem 环 = 单并发**：环无法回收另一 lane 的设备页，`--max-concurrency >1` 启动即拒——**并发与 256K 深度/检索互斥**。
- **W1-W4 已修**（思考预算熔断三连缺陷 + 流式保活），patch 与四重验收见 `patches/`。
- **超池口径（B28）**：超池 prompt 的中段答案按"未核实"对待——`NINFER_KV_RETRIEVE` 检索开关是保命符。
- **召回开销已实测**：超池 prefill 被流水化吸收（~8-23%，60K 场景往返 ≈4-8 s），零截尾。
- **push 教训**：推送成功以 `git status -sb` 的 ahead 0 为唯一判据。

## 模型支持边界与演进方向

| 状态 | 模型 | 说明 |
|---|---|---|
| ✅ **已验证** | Qwen3.8-27B 系（`Coder390-EfficientThink` Q2LynnStyle 量化的 NInfer 容器） | 本仓全部实测（A 臂两轮 DSH agentic、召回探针、视觉识图）都跑在它上面 |
| 🔶 **理论可装，未验证** | **其他 Qwen 3.8 27B 的 NInfer 容器**（如发放包清单的 `neroued/Qwen3.8-27B-NInfer` 上游转换件） | 引擎吃 `.ninfer` 容器，同构容器应可加载；MTP 头/视觉需按模型重新加工（脚本可复用）——**未跑过，不做承诺** |
| 🔶 **理论可装，未验证** | Qwen 其他系列（如 Qwen3.6-27B/35B 的 NInfer 转换件） | 同上，架构参数（KV 层布局/head_dim）不同构时需先验证 |
| 🎯 **设计目标** | **Qwen 4 27B 的 Bonsai 格式与 NInfer 格式** | 本仓的池/环/检索/加工链就是为下一代模型着陆预备的：容器一到，重跑加工脚本即可上车 |

> 加工链与容器解耦：换任何 NInfer 容器，只需重跑 `recode_mtp.py`（MTP 头自转）与 `graft_vision.py`（视觉嫁接）两个脚本——参数与验收探针全部现成。

## 已解决问题档案（按时间序）

> 每行都是一次真实踩坑的完整闭环：问题 → 现象 → 根因 → 解决 → 验证。证据链详见 `docs/ninfer-kvmem-项目构建史.md`。

| # | 问题 | 现象 | 根因 | 解决方案 | 测试与验证 |
|---|---|---|---|---|---|
| 1 | 27B 大模型上车 | MTP 头格式引擎不兼容，无法加载 | 官方容器 MTP 头为 gguf_q4_0（引擎不支持） | `recode_mtp.py` 自转 MTP 头为 iq4_nl（小 202 MB） | decode 105 tok/s；SHA-256 骨架 804 对象零不匹配 |
| 2 | 视觉塔缺位 | 基础件无视觉能力 | 视觉塔未随容器发放 | `graft_vision.py` 整体嫁接 282 MiB 视觉塔（q4/q5 混合，CPU 编码最优配比） | 真实识图成功（"条纹渐变+同心圆环"）；modalities.vision=true |
| 3 | worker 崩溃不自愈（B01） | 超池+大输出请求 → worker 崩/进程静默退出，后续请求全挂 | 租约预留失败路径无兜底 | `--recover-invariant-failures`：出问题只废当前请求 | 深超池探针引擎存活、请求级失败 |
| 4 | E5 growth 止血旗反杀（**DSH 撞墙**） | 输出总在 ~4,037-4,071 被砍（"30 秒墙"），DSH 显示"已达输出上限"+"继续"死循环 | `--kv-lease-growth` 深超池下租约窗口（~4,096）无法扩充 → bounded completion（finish=length）——**是截断不是限速**，与 max_tokens/tb 均无关 | **去 growth**（官方 README:218 同口径）；A/B 实测定案 | 撞墙清零：两轮 DSH agentic 16,143/11,782 tok 零截断；22 次墙位截断 → 0 |
| 5 | 思考墙死循环 | xhigh 思考烧光输出预算 → 空正文 | 思考 token 计入输出预算（包含关系） | `--default-thinking-budget 16000`；引擎 S3 起 OpenAI 端点解析 per-request `thinking_budget`（请求值优先） | 中档思考正常收尾；探针 medium 2-4K 自然 stop |
| 6 | W1-W4 保险丝/保活缺陷 | 越预算 throw、熔断 `==` 永不触发、交接拒绝、progress 被门控（DSH watchdog 误杀风险） | 引擎防御路径三连缺陷 + 流式空 choice | patch 修复（`patches/W1-W4_engine_fix.patch`，W2/W3 先于 W1 验收） | 四重验收（构建史施工批） |
| 7 | 视觉塔闪退循环 | 开视觉起服 → `missing component vision` 四连拒启 | 模型件（iq4nl）无 vision 组件，与视觉开关配对错误 | launcher 联动：开视觉自动切 iq4nlvis 嫁接件 | 联动后起服成功；validate 告警防手改 |
| 8 | KV 五开关缺一静默答错 | 缺任何一个：起得来、缓存命中率高、**中段答错、零报错** | KVMem 环/检索/window 开关缺一即静默退化 | launcher 固定注入 `KV_ENV` 五开关（含 `NINFER_KV_WINDOW`——缺它直接拒启） | 20,203 tok 超池 prompt 检索答案正确（restored=128） |
| 9 | 挂账 39：视觉 × 无 growth | 视觉请求 HTTP 500（`scatter.cpp:18` 断言） | 引擎旧版 scatter 路径缺陷 | 引擎更新后不复现；launcher 三处联动撤除（视觉统一 on） | V1b/V1c 起服 + decode 108.2 功能验证，销案 |
| 10 | 池标定与 64K 起服 | 65,536 池差 213 MiB 拒启；腾显存后仍差 149（WDDM 归还不即时，滴流 ~36 MiB/30s） | runtime 预留（CUDA Graph 驱动态）按 profile 自动算偏大 | `--cuda-graph-allowance-mib 128` 压 graph 预算补缺口 | 64K 起服 25s；decode 101.1（基线 101-104，**零代价**）；launcher 64k 档已绑该参数 |
| 11 | DSH maxTokens 全额预留 | 单请求 prompt+输出全额预留，65,536 输出上限放大超池面 | 思考计入输出 + DSH 默认 65,536 | DSH `maxTokens` → 24,000（单轮封顶；prompt ≤41,536 时 decode 期永不超池） | 生效验证：实机 started 行 `max output 24,000` |
| 12 | 长会话"页漂移"降速 | 34-39 轮 agentic 会话后 decode 从 122 → 3 tok/s，host 占用 98-110% | cache replay 逐轮重映射历史页，**最早页被逐渐挤出设备池**（34 轮后 ~330 页滞留 host → decode 每 token host 往返）——是**轮数**触发，与超池深度无关（三组对照：81K/72K/72K 全不掉速 134/126/134） | 缓解：定期新开会话（机制必需）+ 池扩容（28→~38 轮才触发）+ maxTokens 封顶；根治 = 引擎早期页 pin/预取（挂账 42，待修） | 机理两次独立实证（hidden 页判别：不掉速 ≤17 vs 掉速 329-334） |
| 13 | stream 挂起（挂账 41，**待修**） | 客户端停止读/断开 → 引擎请求永占并发槽（max-concurrency 1 = 服务不可用直到重启） | decode 线程阻塞在同步 send：无超时 + 无断开检测取消 | 已定性可复现（`scripts/test_stream_stall.py`）；修复方向 = send timeout + 断开取消 | 判据签名齐备：CPU delta=0 / GPU idle / TCP Established / 日志静默 |

> **未解决事项**（与上表闭环对照）：挂账 41（stream 挂起引擎侧修复）、挂账 42（页漂移引擎侧根治）、超池中段正确性依赖检索开关（下节"已知限制"）、W5（KV 池自噬，待实测）。

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
| 模型（Coder390-EfficientThink 系） | ModelScope [Merkyor/...-RLOO-GGUF-NInfer](https://modelscope.cn/models/Merkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-GGUF-NInfer)（实测下载）；HF `nerkyor` 同名系 | Apache-2.0 |
| 三元量化工具链 / 转换 / 校验 | 沈三殊（shensanshu）· ModelScope `shensanshu/ninfer-ada-ternary` | 见其发布页 |

本仓为上游衍生的部署/验证工程（非官方发布方）；详见 `LICENSE`（Apache-2.0）与 `NOTICE.md`。
