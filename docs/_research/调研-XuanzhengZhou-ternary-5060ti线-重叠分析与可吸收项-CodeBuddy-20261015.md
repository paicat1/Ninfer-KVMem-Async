# 调研：XuanzhengZhou「qwen3.8-27b-ternary-5060ti」线 —— 重叠分析与可吸收项

- 日期：2026-10-15 · 性质：**调研笔记**（上游支线跟踪 + 与我们树的文件级重叠 + 可吸收项分级）
- 作者：CodeBuddy（办公室侧）· 素材：`refs/xuanzheng-ternary-5060ti/`（clone @ 2026-10-15）+ `.temp/xz-hist/`（全量记录包解压，1410 条目）
- 一句话：**我们的"官方线"（paicat1/Bonsai-27B-NInfer）在 Linux/sm_120a/多路并发方向长出的兄弟工程——文件级重叠 ≥8 处，其中 3 处高价值；对谷的形态特异性提供了弱旁证；一批负结果与工艺可直接引；其仓内 `docs/linux-port/` 还是**面向我方的 Linux 迁移手册**（血统图/编译路线/已知坑总表/引擎能力面），`落地实施方案` 则是**为我方 5080 家机写的早期方案**。⚠️ 其全部质量测量基于 Ternary-Bonsai-2-27B（~1.72 bit/权重）——与我方 IQ3_S（3.62 bpw）模型前提不同，外推规则见 §2。**

---

## 1. 定位与血缘

| 项 | 内容 |
|---|---|
| 仓库 | `XuanzhengZhou/qwen3.8-27b-ternary-5060ti`（Apache-2.0） |
| **引擎基线** | **`paicat1/Bonsai-27B-NInfer` engine-main @ `f90e30c1`**（= 我方生态"官方线"引擎）+ 72 文件补丁 |
| 血缘链 | `Neroued/ninfer`（源头）→ `paicat1/Bonsai-27B-NInfer`（官方线）→ **本线** ∥ **XuanzhengZhou 线**（Linux + 多路） |
| 硬件 | RTX 5060 Ti 16G **sm_120a** · Ubuntu 24.04 · CUDA 13.3 · **120a 原生 SASS** |
| 模型/用途 | Ternary-Bonsai-2-27B（PQ2_0 + DFlash2）· **dsh 的 subagent 模型**（主模型 DeepSeek） |
| 工作量 | 143 轮（10-05→10-11）· 72 文件引擎补丁（覆盖即复现）· 全量逐轮记录 + 证据归档（17MB 打包） |
| 成果 | 并发上限 +67~106%（16K~256K：62/58/52/37/10 路）· 上限聚合 +176%（799 t/s）· C=16 每路解码 +234% · agent 首轮 TTFT 1.9s→0.13-0.40s · 质量总代价 ΔPPL +0.25% |

**构建目标共鸣**（其 r8 快照 CMakeLists 原文）："reference implementation is compiled for **sm_120a (RTX 5090)**"、"**128 SMs equals the RTX 5080**，120a 构建复用同一代码路径" ⇒ **我们与它同编译目标生态**。

**模型前提（重要）**：其权重为 **Ternary-Bonsai-2-27B（PQ2_0，~1.72 bit/权重，9.3× 压缩）**——与我方 **IQ3_S（3.62 bpw，11.3 GiB，2026-10-15 已实载成功）** 相差 **2.1 倍权重信息量**。其全部质量 / PPL / 逐字门数字都在"极限量化权重"前提上测得——**外推规则见 §2**。（tancau 线同为 ternary 前提，引用其数据时同样适用。）

**上游血统图（其 `docs/linux-port/docs/00`，全谱系首次被整理成图）**：

```
模型侧：Qwen3.8-27B 底座（阿里）+ unsloth NVFP4 + z-lab DFlash（草稿头）+ prism-ml Bonsai-2-27B（PTQ1_0 / PQ2_0 GGUF）
引擎侧：Neroued/ninfer（引擎本体）→ UDPSendToFailed/ninfer-4090（E8 lattice = rk4v4-e8 / rk2v4-e8 的发明者；WDDM bypass）
        → CraneBW/ninfer-ternary-bonsai-ada（三元内核 mma）→ Ambolio/ninfer-4090-windows @6eb70a07（v1.0.8 多 fork 融合；已转私有）
        → shensanshu/ninfer-ada-ternary（三元补丁 + pack.py；ModelScope 作者链）→ paicat1/Bonsai-27B-NInfer（我方官方线）
```

- **rk2v4-e8 的发明来源首次明确 = `UDPSendToFailed/ninfer-4090` 的 E8 lattice**；
- 作者（沈三殊）三元补丁的基线 = Ambolio v1.0.8（**已私有**）——复刻作者原路需找存档 fork；
- 补充线索（其标注"未核实"）：**Inferno（16GB 5060 Ti fork of NInfer）**、`mr-september/ninfer-2080ti-22g` / `stonelab/ninfer-2080ti-22g`（Gitee，**带 Dockerfile** = Linux/Docker 构建先例）、`zheteng-v/ninfer-4090`。

**面向我方的材料（重要）**：`docs/linux-port/` 是一套**为用户（paicat1）编写的 Linux 重建手册**（00 血统与依赖 / 01 编译路线 / 02 权重获取 / 03 验收判据 / 04 已知坑总表 / 05 引擎能力面参考 / 06 Windows→Linux 迁移对照 / 07 里程碑）；`docs/落地实施方案-Bonsai27B-NInfer-20260921.md`（v1.2）则是**为我方 5080 家机（Windows）写的早期落地方案**（含"弹性 KV 池"论证与 M0-M5 阶段规划）——即**对方主动为我方准备的迁移/落地知识包**，未来若走 Linux 或多机部署，直接从这里起步。

**其质量门三档哈希（v140 认证）**：`k8v4 = 8.755896` ｜ `nvfp4 = 8.766253`（Δ≈+0.088%）— 与 tancau 六格式表、我方精算三方互证**。

---

## 2. 适用边界：模型前提与外推规则（ternary ≠ 我们的 IQ3_S）

**前提差异**：本线（与 tancau 线）的模型均为 **Ternary-Bonsai-2-27B（PQ2_0，~1.72 bit/权重）**——权重已被推到"极限量化"的临界；我方 **IQ3_S（3.62 bpw）** 权重信息量是它的 **2.1 倍**。KV 量化是"在权重误差之上的增量误差"——两者叠加后的输出分歧阈值，在两种权重前提上不同。

**外推规则表**：

| 其结论 | 可用性 | 理由 |
|---|---|---|
| KV 量化损伤**排序**（int8≈无损 > rk8v4/fp8 > k8v4 > nvfp4） | 🟢 大概率保持 | 物理不变（K/V 位宽越低越伤）；tancau 亦自注"ranking 跨模型可携带、绝对值不可" |
| PPL **相对代价量级**（+0.05~0.36%） | 🟡 预计同量级或更低，须实测 | 权重余量更大 ⇒ KV 边际损伤通常更小（方向性推断） |
| PPL **绝对值**（4.34 / 8.75 量级） | 🔴 不可用 | 模型 / 语料 / 工具均不同 |
| **逐字一致门数字**（rk8v4 5/8、rk4v4-e8 3/8） | 🔴 **必须重测**（最优先） | 在 1.72bpw 脆弱分布上测得；IQ3_S 的分歧阈值预计显著更高 |
| **"4-bit KV = agent 红线"判决** | 🟡 强度下降，不自动解除 | ① IQ3_S 更稳健；② 我方域更严（DSH 工具链一个字符错 = 事故）——红线位置要在 IQ3_S + DSH 域上重标 |
| "生产留 8bit（int8）"运营线 | 🟡 参考不照搬 | 三元模型下的保守解 |

**反向提醒（防乐观过头）**：
- 权重越接近无损，KV 量化误差在**总误差预算里的占比**反而可能更大（相对更可见）——"IQ3_S 下 nvfp4 一定更安全"不成立，以数据说话；
- 我方逐字门可能要**比 tancau 更严**：他的域 = 开放式散文改写率，我们的域 = **agent 工具调用正确性**（路径/shell/JSON 一个字符错即事故）。

**与之配套的三件"在 IQ3_S 上重做"实验（工具已就绪）**：
1. **逐字一致门重标**（`verbatim_gate.py` 已交付）：先跑 IQ3_S 噪声地板（期望 8/8）→ 再跑 IQ3_S 内跨 KV 对照（rk2v4 vs nvfp4 vs rk8v4）——**判据不用其 ≥7/8**，先看我们的分布再定红线；提示集要含 DSH 真实域（代码 diff、JSON 工具调用、长引用）；
2. **PPL 网格**：其编译产物含 **`ninfer-perplexity`**（同血统引擎大概率可 build）——固定语料 × {rk2v4, nvfp4, k8v4/rk8v4, Q8} 全网格，一次拿到"我们模型上的真实汇率"；
3. **DSH 任务 A/B**（精算文档 §8 清单）——最终裁决层。

---

## 3. 文件级重叠矩阵（我方 19 补丁 16 文件 vs 其 72 文件）

| # | 我方补丁（触及文件） | 其改动（轮次） | 重叠性质 |
|---|---|---|---|
| 1 | `models/qwen3_5/program/program_impl.h`（ledger42 v2 异步流水 + ledger46 v2.1） | **`targets/qwen3_6/impl/runtime/program_impl.h`（r42：verify 宽度自适应表 + dflash_impl 别名助手）** | 🟡 **同文件，（版本树 targets 结构不同），两套改动可互为参考/合并需注意** |
| 2 | `runtime/engine/engine_core.h`（ledger42 取消检查点） | r33（其 materialization 报告亦行号级剖析 `engine_core.h:1925/2035/2044`） | 🟡 同文件 |
| 3 | `ops/launcher/speculative_round.cu`（s6/s7/s9 段戳） | `ops/wrapper/speculative_round.cpp`（r36） | 🟡 同族（wrapper vs launcher） |
| 4 | **S11 第一嫌疑：`ops/context_kv_materialize/materialize.cu:411/459`（PDL wait）** | **`ops/context_kv_materialize/context_kv_materialize.cpp`（r8）** + 其「物化串行化解剖报告」 | 🔴 **同族（物化路径），高价值** |
| 5 | 13 等待点之一 `gated_delta_net/recurrent.cuh:744` | **r41 全套**（recurrent.cu/cuh、state_passing、replay、chunked/launch） | 🔴 **同族（GDN），高价值** |
| 6 | s11 `gdn_gating_proj/bf16/…kernels.cu`（常驻常量 2→运行时查询） | `gdn_input_proj/*`（r8）+ `core/linear_attention_state.*`（r33/41）+ `core/gdn_replay_records.cpp`（r36）（**状态镜像 FP16/FP8**） | 🔴 **同域（GDN 状态），高价值** |
| 7 | `program/transactions/materialization.cpp`（ledger47 超池中止静默死） | 其物化报告直指 `materializing_`/`ContextTransaction` 单槽 + `scheduler.h:233-238` | 🟡 同域（物化事务） |
| 8 | `serve/openai_chat_http.cpp`（ledger42v2/W1-4） | `serve/http_server.cpp`/`serve_options.cpp`/`generation_service.h`（r8/r9） | 🟡 同域（服务层） |

其余大块（我方独有）：v2 异步页流水全链（context.cpp/program.cpp/program_impl.h）、MTP 仪表链（mtp.cpp/step_graph_profile.h）、pdl.cuh（S7-S10）。**其独有**：三元内核全套（PQ2_0 专用，对我们 Q2Lynn 不适用）、dflash_impl、多路预填批处理、前缀缓存服务层。

---

## 4. 可吸收项（分级）

### A 级（直接读、直接引）

1. **物化串行链解剖**（`ninfer_materialization_report.md`）：16 路 TTFT 尾 ~0.6s/路的根因 = **三个"单槽"资源被串行**：
   - `materializing_`（只能 1 个，`engine_core.h:2044`）
   - `prefill_lane_`（只能 1 个，`scheduler.h:363`）
   - `ContextTransaction context_transaction_`（物化 OR 收尾捕获，只能 1 个，`program.h:949`/`resource_manager.h:3376`）
   - 门控 `scheduler.h:233-238 should_attempt_admission()` 要求三者全空 → 严格串行流水线；每步同一线程同一把 `execution_mutex_`（`engine_core.h:2035`）
   - → 其 v20 修复（入场门控根治：16 路真并发 TTFT 710→47ms）
   ——我方单路场景影响小，但**这是同血统物化路径的行号级地图**（家里树可直接按行号对照）
2. **负结果/证伪清单**（CHANGELOG + GOAL.md §6）：与我们直接相关的——
   - **`PDL_off = −1.1%`**（llama.cpp 基线扫描；与我方 ninfer 上 ≤1.2% 独立互证 → **PDL 收益 ~1% 量级共识**）
   - **FP8 KV：−4.9%（smem 墙）**（与 tancau"坏交易"、我方不推荐 fp8 三方一致）
   - "f16 累加注意力 −4.45%"、"提高每 SM warp 数"、"CUDA Graph 消除 launch"、"提高每 SM warp 数"、"字粒度 LUT"、"192-tile 寄存器文件边界"、"host 26% 可争取"、"稳态退化≠会话身份/目录容量/host KV 池"
   - **探针观察者效应 ×3.71**：`NINFER_PREFILL_STEP_PROBE=1` 把入场阶梯 2.424s → 8.993s（+6.57s，TTFT p90 +158%）⇒ **探针本身可能改写被测系统**（我方 I3b 探针已有"零行为门"挡过——此为方法论旁证）
3. **CUDA graph 量化**（v112）：**仅 C≤8 划算（+6.9%/+5.9%），图池代价 2.5-3 GB**（C≥16 关图因图池起不来）——我方单路开图决策的旁证。
4. **运维纪律四件**（可直接照抄进我方规程）：**永不 kill -9**（曾触发 Xid 62 / GPU Reset）、显存 256 MiB 硬地板、systemd 三单元自愈、Xid 监控（`journalctl -k | grep -ci Xid`）。
5. **【新·高价值】已知坑总表**（`docs/linux-port/docs/04`，"两边踩过的坑合并、按代价排序"）——与我方直接相关：
   - 💀 **超池 ⇒ 中段内容静默丢失**（HTTP 200、`finish_reason=stop`、**日志零报错**）——**"大佬包"（我方同源 Windows 发行版）也有此问题、根因至今未定位** ⇒ 与 tancau"silently unreadable"、我方页漂移**三方共证此缺陷是 KVMem 族共性**；处置只有"超池告警 ⇒ 该答案不可用 + 池 ≥ 题面"
   - 💀 **客户端 `max_tokens` > 池 token 数 ⇒ 打崩 worker 且不自愈**（此后全 503，`/v1/models` 仍 200）——我方挂账 47/54 同族；处置：客户端 max_tokens ≤ 池容量
   - 💀 **五个 ring 开关缺一不可**：只设 WINDOW+REUSE ⇒ **99.9% 缓存命中但长题面答错**（中段看不见）、零报错——"RETRIEVE 是把中段找回来的那个" ⇒ 与我方 KV_ENV 五开关认知合流
   - 💀 **PTQ1 fast-rung 没开 ⇒ 慢 50× 无报错**（"看起来像模型就是慢"）；容器代际不匹配；**PTX-only 构建性能崩**（⇒ 我方"120a 原生 SASS"纪律再证）
   - ⚠️ **合成数据选投机档 ⇒ 结论反转**（接受率差 2.5×，必须真实负载）——与 tancau"勿引用合成 41%"、我方合成语料纪律**三方共识**
   - ⚠️ **DFlash2 K≥10 断崖崩塌**（比不开还慢 70%+，"禁用区"）——"K 值有禁用区"概念
   - ⚠️ **`--recover-invariant-failures` 默认关**（"崩实例⇒拒绝并继续服务"现成开关）——**查我方引擎有没有**（与挂账 41/42 直接相关）
   - ⚠️ `--max-context 262144` + `--host-kv-mib 16384` 拒启（`host_pages + pool_pages ≥ max-context 页数`守卫；"自测先用 65536"）；长上下文 >200K 质量下降（200K 前压缩）；ECC 交税（6.25% 容量 + 12% 带宽）；显存"拆账本"看（权重+logits+旋转/prefill+KV+GDN+staging/context）
6. **【新·高价值】稳态退化族（v29-v33）——与谷同族的另一条慢态，且他们根治了**：
   - 现象：持续混合负载后退化（n16 TTFT 中位 **47 ms → 3.9 s**、聚合 254 → 162 t/s）
   - v29 触发变量消融 ⇒ **不是会话身份，是累计请求量（KV 池饱和）**；v30 根治 = `--host-state-slots 16→48`（"状态镜像槽位耗尽后逐路串行驱逐"，代码定位 `types.h:869 RuntimeStats`）；v33 抓到**真正热点 = `engine_commit_output`（输出提交主机相）从 1.5 ms/窗口爆到最高 1004 ms/窗口**（30 窗口 2941 ms vs 干净档）；认证：**1125 轮长稳 0 退化 0 Xid**、n16 TTFT 3851.9 → 47.3 ms
   - ⇒ 与谷的关系：其慢态在**主机侧（提交相爆炸）**、机制是**槽耗尽→驱逐**；我方在 **GPU 侧（自旋）**——两家族互不替代，但**"提交相"是可交叉检查的观察量**（我方 I3b 仪表含提交五分——谷期提请对一次）；"槽耗尽"机制查我方 state-slots 配置
7. **引擎能力面清单**（`05`，对"成熟发行版引擎二进制"的静态拆解——**当查漏表用**，可 grep 源码核对子系统名）：
   - 125 CLI 参数 / 34 env / **KV 9 档**（bf16,int8,fp8,rk8v4,rk4v4,rk4v4-e8,rk2v4-e8,nvfp4,k8v4）/ 投机 3 套（MTP + DFlash2 + **n-gram 查表**）
   - KV 策略层名：`value-aware-demote`、`recency-eviction`、`cache-tap-ladder`、**`long-anchors`（"锚"机制名）**、`auto-prefix-grid`；准入租约：`thorough-admission-search`、`kv-lease-growth`、`kv-headroom-mib`；自愈：`recover-invariant-failures`
   - **GGUF 桥**（IQ1_S…IQ4_XS / Q2_K…Q8_0）= 我方换模型（IQ3_S）的技术底座；服务端三套 API（OpenAI chat / **Responses** / **Anthropic**）+ `count_tokens`/**`compact`** + 内置 WebUI + **MCP 代理** + Prometheus `/metrics`
   - 平台分支：`--devices`（Linux 多卡）、WDDM evictable-budget、DirectStorage（Windows）
8. **显卡故障处置规程**（`docs/00-必读`）：kill -9 禁令的**完整处置流程**（SIGTERM → 宽限期——释放 57 GiB 很慢 → 最长等 60 s → 查 D 态）+ 故障取证报告模板（状态快照/持卡进程/CUDA context/内核日志/Xid 时间线/责任判定：10-06 Xid 13/43 = 应用层 bug、10-07 Xid 62 = 驱动关闭挂死）——**直接可用**。

### B 级（工艺参考）

5. **GDN 状态镜像工艺**（v78/v108）：FP16 存储（寄存器仍 FP32）省 ~75 MiB/路、PPL Δ+0.000554；FP8 e4m3 省 35.5 MiB/路、Δ+0.0028；**纪律**：改变逐字节哈希 ⇒ 必须立"独立哈希档"（text 一致但 thinking 哈希变了：723 chars vs 752）
6. **入场门控/物化互斥的 fail-stop 案**（v76）："捕获 offer 队列挂起时推进预填" → `prefill cannot advance while a capture offer is pending` → 整机 503 ⇒ 修复后复用 4/16→16/16 ——**与我方挂账 42 领域（capture/落袋）同族状态机缺陷**
7. **服务层/DSH 工艺**：前缀缓存 L1-L4（新会话首轮 cache 98.9-99.1%、TTFT 0.13-0.40s）、工具轮连接层分帧（5.011→0.240s）、tool_choice 4 种 400 形态翻译、**maxTokens 结论（v145）：dsh 单轮输出上限只由引擎档位 `--ctx` 决定（无 clamp）**
8. **env 开关命名体系**（可交叉检查我方引擎）：`NINFER_TERNARY_S8` / `NINFER_STATE_RECURRENT_FP8/FP16` / `NINFER_VERIFY_WIDTH_ADAPT` / `NINFER_PREFILL_STEP_PROBE` / `--device-state-slots`
9. **DSH 适配器四层全解**（`server/dsh_adapter.py` 38.9 KB，头部注释即设计文档）：
   - **根因发现**：dsh 新会话布局 `[system, user(任务), user(声明), user(16K 环境快照)]`——任务在第 1 条 ⇒ **前缀 ~600 token 就分叉、每任务冷预填**；修法 = 任务挪末尾 + 占位串 + 断点标记；
   - **画像先行**：v135 埋点抓到"裁剪档真实形态 = 3 消息/2 user ⇒ 旧规则 `len(users)>=3` 从不生效"——**先测真实流量形态再写规则**（方法论）；
   - L2 精确回放（sha256 键、只对首轮/内部请求、TTL 300 s、**逐字节回放零质量风险**）；L3 前缀落盘 + L4 启动预热；水位监控**只观测绝不压缩**（80% 告警）
10. **GOAL §3/§4 的物化根治全案**：P0 根因（v8）="**materialization 事务一次一个 + 收尾捕获 ~2.3 s 单飞**"（涉及 `program_impl.h` / `text_context_impl.h` / `context_kv_materialize.cpp` / `engine.cpp`——"串行性藏在事务/资源管理器结构里，没有简单 mutex"）；方案 A（多槽）/ B（增量入场）/ C（错峰+批量收尾）⇒ 最终 C + 门控撤除 + SRPT 交付（v20）。**"收尾捕获 2.3 s 单飞" = 我方 capture 路径的对照数字**
11. **混合上下文计划 + 基线数字**（10-10）：256K 档 C=10 服务 70:20:10 混流 ⇒ 32K TTFT 中位 **105 s**、每路解码被预填挤到 **1.83-2.71 t/s**（同请求纯 32K 档 75 t/s）——**"长预填阻塞短请求"的实测**；其"按使用量自动分配上下文"的痛点表（换档=重启=丢缓存 / 静态预留浪费）**正是我方异步页流水已部分解决的**——可对照宣讲。附 `bench8.py`（可配流量比例/到达模式/冷热比例的混合流基准）

### C 级（只读记录，不吸收）

- 三元内核全套（PQ2_0 专用）、多路预填批处理、自适应 verify 宽度（其判为"性能负"默认关）、Linux 移植成分

---

## 5. 对当前战斗的三个重要发现

1. **谷的形态特异性：弱旁证（重要）**
   其同为 sm_120a 原始构（其 CMake 目标闭集明确 `120a|89`）+ 官方线血统 + 1h 连续 agent 作业 0 Xid 0 重启——**其报告体系（143 轮 + GOAL 主日志）中无任何"谷/自旋/粘性慢态"记录**（关键词检索 spin/valley/自旋/谷 仅命中 v76 的 capture 队列——非 GPU 自旋）。
   ⇒ 提高"谷 = 我方特定形态触发（单路深堆积长会话 + 贴边池 + overlay + 65K-81K 池域）"假设的权重——而非"120a+PDL 普适病"。
   ⚠️ 但不能反推 PDL 无罪：其形态（32K 浅上下文、16 路短会话）未进入我方谷的高发域。
2. **verify 宽度 vs GDN replay 记录平面（墙）**
   其 r42（自适应 verify 宽度）**默认关**的阻塞 = 变窄宽度撞 `GdnReplayRecordSpec.width = plan.draft_window + 1`（`layouts_impl.h:181`，稠密视图）→ `gdn_input_proj_conv_record` 宽度不匹配 → fail-stop。
   ⇒ **我方若未来调 MTP/verify 宽度（谷的 MTP 嫌疑相关方向），此墙先记**（记录平面按最大宽度规划 + 带步长视图是修法方向）。
3. **物化路径 = 我方 PDL 第一嫌疑区**
   其 r8 触及 `context_kv_materialize` + 出局解剖了物化事务全链（含 `device.synchronize()` 在事务内被拉进串行链）。
   ⇒ 我方 S11 的 `materialize.cu:411/459` PDL wait 分析可借其行号级地图（家里树对照）。

---

## 6. 待办

- [ ] 精读 GOAL.md §6 完整负结果清单（137.8 KB 主日志；本文档已摘相关条）
- [ ] 其 r41 快照（GDN 全套）与家里树逐文件对照（我方 S11 区域 vs 其 r41 区域不同，但同域）
- [ ] `证据归档-20261009-20261010.tar.xz`（16MB，ncu/nsys 原始）——选择性抽看 GDN/graph 相关
- [ ] **登记进 `docs/上游谱系与跟踪纪律-20261011.md`**（新增支线：官方线 → XuanzhengZhou Linux/sm_120a 多路线）
- [ ] 家里树侧：按 §3 矩阵逐文件对照（办公室无引擎源码树）
- [ ] 若采纳：kill-9 禁令/显存地板/Xid 监控 进我方运维规程
- [ ] **在 IQ3_S 上重标三件**（逐字门噪声地板 + 跨 KV 对照 / PPL 网格 / DSH A/B——见 §2 末）；落定前，凡引用本线（及 tancau 线）的判据数字均标注"**三元权重前提**"
- [ ] **交叉检查我方引擎三件**：**state-slots 配置**（对照其"槽耗尽→驱逐"机制）/ **`--recover-invariant-failures` 是否可用**（挂账 41/42 的"现成开关"）/ **谷期"提交相"指标**（我方 I3b 提交五分 vs 其 `engine_commit_output` 爆炸）
- [ ] 通读其 `docs/linux-port/` 全集 + `落地实施方案`（若未来走 Linux/多机部署——**这是对方给我们的现成知识包**）

## 7. 素材位置

- 参考仓：`refs/xuanzheng-ternary-5060ti/`（README.zh-CN、CHANGELOG、engine-patches/{README,_filelist,src}、history/）
- 全量记录解压：`.temp/xz-hist/改进过程/`（GOAL.md、优化报告-全历史/ ~130 篇、引擎补丁-分轮快照/ r7-r42、PPL配置/、基准脚本/）
- 关键单篇：`优化报告-全历史/ninfer_materialization_report.md`（物化解剖）、`优化报告v2/v81/v76/v78/v105/v112`（PDL-llama 扫描/观察者效应/捕获队列/GDN 状态/graph 量化）
