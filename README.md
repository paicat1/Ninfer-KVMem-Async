# Ninfer-KVMem-Async

**在两代前序工程跑通的架构上，部署更大的模型（Qwen3.8-27B-Coder390，27B）。**

## 这个仓是做什么的（30 秒版）

在 **16 GB 消费显卡**上跑 **27B 模型**做**长上下文 Agent 会话**——原生放不下（百万 token 的 KV ≈ 32 GiB），靠 **KVMem 虚拟化**（KV 分层存放 + 按需召回）"装得下"；本仓的核心增量是**异步页流水（Async Page Pipeline）**：页搬运与解码计算**流水并行**（搬运不等解码、解码不等页），让"超池"不等于"减速"，并配齐正确性工程（池内 vs 超池输出逐字无损）与全套实测标定（池 / KV 精度档 / 投机档）。

- **怎么来的**：三代工程接力——Bonsai-27B-NInfer（引擎与量化）→ Bonsai-27B-NInfer-kvmem（KVMem 环）→ 本仓（异步页流水），详见下方三代演进表；
- **当前状态**：**限定场景（单路长上下文、显存独占、PCIe Gen4）生产可用**；两个已知未决课题 = ① 时段性慢态（"死亡谷"：触发三条件已钉死=Gen5+外压≥400MiB+贴边，行号级根因待解）② **C12 空闲后首请求可能永久挂死**（未复现）——另：**"卡死"已归因闭合=符号链接缺失**（带符号构建免疫，见 ★2026-10-18/19）；
- **怎么读这个仓**：下面先看关键节点与全部战役（精选）；逐轮完整过程（含每次决策的证据链）见[项目构建史](docs/ninfer-kvmem-项目构建史.md)。

> English condensed edition → [README.en.md](README.en.md)


三代演进：

| 代 | 仓 | 沉淀 |
|---|---|---|
| 一 | [**paicat1/Bonsai-27B-NInfer**](https://github.com/paicat1/Bonsai-27B-NInfer)（main=项目层 / engine-main=引擎层，两分支一体） | **Bonsai-2-27B 三元量化（2.125 bit，9.81 GiB）跑上 NInfer**：Ambolio 移植 + CraneBW 内核、改 CMake `89\|120a`、自产 v2 制品；Device/Host **双层 KV**（被动容量）；MTP / DFlash2 投机。极值：prefill 2,850 / decode 396.9 tok/s |
| 二 | [**paicat1/Bonsai-27B-NInfer-kvmem**](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem) | **KVMem 环（主动检索）**：显存小池 + 主机卸载、`--kv-capacity` 可小于上下文、内容打分 SELECT、五开关（本仓增至六）；**混合投机**：dflash2（K1-15）+ MTP（K1-5）+ ngram，**K=7 甜点**（K≥10 崩塌）、接受率语料效应（数数字 91% vs 散文 3.7-13.4%）；自编整套引擎（MSVC 补丁 ×7 + Design C 治"思考区 stop 空正文"）+ 双引擎对照；GUI 启动器与 serve_tee 日志工具自建。极值：**prefill 3,820 / decode 748.6 tok/s**（真实负载 19 请求，接受率 35.7-94.4%） |
| 三 | [**paicat1/Ninfer-KVMem-Async**](https://github.com/paicat1/Ninfer-KVMem-Async)（本仓；2026-10-13 由 Qwen38-27B-NInfer-kvmem 改名） | 换大模型：**Qwen3.8-27B-Coder390-EfficientThink**——自转 MTP 头（iq4_nl）、思考熔断三连缺陷修复（W1-W4）、growth 定案、池标定 51,200、视觉塔嫁接、256K 逻辑上下文；**并作为 Qwen 4 27B（Bonsai/NInfer 格式）的着陆预备**。2026-10-18/19 收官三件套：arch 误编根因闭合、**卡死元凶判决（符号链接缺失）**、谷触发三条件钉死 |

> 硬件基线：RTX 5080 16 GB + 128 GB RAM，Windows，全部结论为实测（非推测）。

---

## 从两仓成果到今天：继承与全部战役

### 继承：前两仓留下的武器库

| 武器 | 来自 | 在本仓的作用 |
|---|---|---|
| **混合投机（dflash2 + MTP + ngram）与调参方法论** | 仓二：K=7 甜点、K≥10 崩塌、**接受率是强语料依赖指标**（不能用合成文本测）、真实负载 748.6 峰值 | 本仓的 MTP K4 + ngram 档位、`test_ab_arm1.py` 的接受率/速度统计方法，全部照此模式验收 |
| **KVMem 环（主动检索式 KV 卸载）** | 仓二：显存小池 + 主机卸载、内容打分 SELECT、五开关（本仓增 sink 至六开关；缺一静默答错）、埋针判活方法论（问句独立回合、MAXQ=256） | 256K 深度的根基；本仓的召回探针（`probe_recall*.py`）与 KV_ENV 注入直接继承 |
| **自编引擎方法论** | 仓一+仓二：MSVC 编译兼容补丁、双分支（项目层/引擎层）、产物 hash 台账、复现指南 | 本仓 W1-W4 patch 与构建部署照此模式（`patches/` + 产物对账 + `.bak` 回滚锚） |
| **思考预算（Design C）** | 仓二：自编 serve 的 `--default-thinking-budget` 生效 vs 发放包预编译成品 exe 不解析该字段 | 本线 tb 熔断的前身——W1-W4 修的正是它的三连缺陷（`==` 失灵/越界 abort/交接拒绝） |
| **GUI 启动器 + serve_tee** | 仓二自建（作者分发包只有 bat） | 本仓简化为 **4 预设（2 模式 × 2 模型）** + 校验告警 + KV_ENV 注入 |


### 关键节点（精选）

> ## ★ 2026-10-18/19 · 卡死归因收官 + 死亡谷触发条件钉死 + arch 事故根因闭合（三件矩阵判决实验）
>
> **① 卡死元凶判决（构建史 §136）**：同条件（Gen5 + 外压 400 MiB + 池贴边）三件二进制对照——**S13 生产件（无符号）= decode 0、5/5 探针 30 s 超时取消（卡死不返回）**；**sym3 / offi（带符号构建）= 41 / 44.5 tok/s 深谷但 6/6 全部完成**。三件跨两个编译器版本（14.43/14.44）全"谷但完成"，唯一无符号件卡死 ⇒ **卡死元凶 = 符号链接缺失**（/Zi+/DEBUG 改变链接产物布局本身，不是"符号让我们看见卡死"，是"加符号这个动作治了卡死"）。**"挂死"与"谷"自此分为两个问题**：卡死=构建问题（已定位、可复现制造/回避）；谷=负载×环境现象（未闭合）。
>
> **② 死亡谷触发条件钉死（§135，六批全矩阵）**：**AND 三条件**——Gen5 PCIe 下 + 外部显存压力 ≥400 MiB + 自由显存贴边（<400 MB），缺一不触发（零外压×两件×两代 8 例全健康；Gen4 下贴边+400 MiB 两件 0/68 入谷）。WHEA 风暴（峰值 1857/min）逐拍对齐后确认**与谷无因果**（并发现象）。已撤回"68 探 0 谷=承诺失效"的中间错误结论（真相=Gen4 环境抑制+零外压双重不在域）；当前诚实表述：**"在已声明适用域内存在可稳定触发的剂量（3/3，n=3），非任意条件必触发"**。
>
> **③ arch 误编根因闭合（§128/T#0056）**：sym 件"启动挂死"实为构建缺 `-DCMAKE_CUDA_ARCHITECTURES=120a` ⇒ CMake 默认 sm_86 ⇒ RTX 5080（sm_120a）无法直载 ⇒ PTX JIT 长征假死（357 kernel）。sym3 照配方重编（`cuobjdump` 验收 **384 cubin 全 sm_120a、0 sm_86**）。教训已机器化：**任何 CUDA 构建必须显式传 arch 并以产物级 cuobjdump 验收**。
>
> **④ 异步 DEPTH 三档浅载对照（§137）**：D2（默认）187.1 > D0（同步）183.6 > D1 182.6 tok/s——**浅载下异步页流水没有活干**（差异在噪声级），与 10-16 深轮重载对照（异步净收益 ~20%、最深段 ≈2×）合并出的口径 = **异步价值随工作集深度上升而显现**；深度档 3/4 深载未实测，默认保持 D2。
>
> **⑤ 启动器整治与引擎分线（§130-139/用户令）**：引擎下拉=**现役三件**（S13 生产件 322A972D / offi 官方链+符号 3543AD18 / sym3 新构建链+符号 9453FFC6）+ 归档五件；模型维度=**六档**（q2lynn / swift / bonsai / iq4nl / iq4nlvis / orig）；异步页流水 = A/B 开关 × 深度（1/2/3/4 批在飞）两个独立维度；场景预设=4 个（2 模式 × 2 模型），与引擎下拉正交（引擎=跑哪个二进制，场景=用什么参数跑）。
>
> **⑥ 环境事件（同级事实）**：BIOS 已由 PCIe **Gen5 降 Gen4**（WHEA 风暴止血：6h 12,305 条 AER → 0）；跨分界数据必须显式标注代数。**Gen5 属已知高风险运行态**——见"已知限制"。

> ## ★ 2026-10-16 · 异步页流水拿到同条件对照铁证 + 死亡谷攻关里程碑（连续 120 小时不间断压测）
>
> **① 深轮重载 ON/OFF 对照**（多轮递进 + 部分缓存复用 + 长输出，2.3-3.5× 超池，2026-10-16）：
> - 拆掉异步（同步回退）**decode 拖慢约 20%**（深段 median 188.1 vs 234.9，**r=0.80**）；**最深段（3.5× 超池）差 ≈ 2.0 倍**（119.4 vs 235.6）；ring STALL **33 → 2**（≈16×）；
> - 浅载对照：单发超池打平（r=1.13）⇒ 口径：**异步的价值随工作集深度上升而显现**（它正是为深载设计的）；
> - 诚实边界：n=3/臂、单机、健康期；**触发需同时满足自由显存贴边（<400 MB）**（"在已声明适用域内存在可稳定触发剂量，非任意条件必触发"）；同步臂未"死"（历史"多轮必死"的更强主张未复现——观测为"可用但慢"）。
>
> **② 死亡谷（时段性慢态）攻关里程碑**：
> - **可按需复现**：外部显存压力（约 1.2 GiB）⇒ 施加即入谷（速度降至 1/25）、释放即恢复、两轮可重复——不再"等窗口"；
> - **机制定位**：谷期时间**全在 host 侧提交调用**（`submit ≈ wall`、`wait = sync ≈ 0`）⇒ 卡点在引擎自身的提交路径（驱动内部阻塞）；**PDL（原最大嫌疑）以开关回切反例出局**；宿主路径 / 页档位 / 池大小 / 节流逐项实测排除；
> - **深档（≈1/100）也已造出，且受"机器态时窗"支配**（全晚 12 发长持：**窗内 4/4 命中、窗外 8/8 谷档**——"重启即复现"配方被证伪；时窗开合条件解析中）；
> - 剩余：把提交路径上的具体阻塞点钉到行号级——**约 2 分钟最小复现协议已备**（供社区 / 上游 / 驱动侧研判）。
>
> **③ 此间（10-14~15）其他进展**：Swift-1.5（IQ3_S）换底座与 KV 档 A/B（rk8v4 快且稳）；v2 转正为日常基线（127 轮连跑 0×500、峰值 403.7）；S12 发生率对照 12 窗全 0 ⇒ 发现"活跃窗口"结构；S11 GDN 常驻修复（字节相同输出）。详见[构建史](docs/ninfer-kvmem-项目构建史.md) §50-73。
>
> **📄 演示材料**：[`异步页流水-技术说明.pptx`（18 页）](docs/异步页流水-技术说明.pptx) · [**English 版**](docs/Async-Page-Pipeline-Technical-Brief.pptx) · [公开说明（MD）](docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md)

> ## ★ 2026-10-13 07:15 · 新峰 463.9（H1 基线 · agentic 首战）
>
> 晨间首场 **agentic 会话**（tools 30 / 28 轮；引擎 `build 35173e0` = 基线 `H1_54fix_20261013`，64K 池 / draft4 / depth1）：
> - **decode 峰值 463.9 tok/s，连续 ≥6 窗保持 451–464**（07:15:47–07:16:12：463.9/459.7/461.8/457.5/451.0/451.8，随后 245.0；host ~98%）；
>   **req#2：题面 8,303 → 输出 23,869 tok，TTFT 5.1 s，prefill 2.23k，req 级 decode 258.2（混合投机）**；
> - 中段多轮：**cache 99.3–100%（private endpoint）**，TTFT 311 ms–1.1 s（req#3–#26）；**4 次超池零故障**（`unavailable Device page` / `recovery` / HTTP 500 全 0 ✓）；
> - **同会话后段 07:25:32 起进入谷且长时不爬**（滚动记录）：**第二轮（07:26–07:30）40 窗中 23 窗 <20（min 0.2、max 144、均 34.7）**、两次 cache=0 全量重填（TTFT 35–42 s）；**第三轮（07:32:24 起）prefill 正常、decode 深谷 0.2–7.2（90 s 盯守未爬出，截至 07:36:26）**——挂账 46 现场版（谷底 0.2 = 迄今最低）；
> 现场日志 `logs\test_54fix1d.log`（07:15:24 会话起）。
>
> ## ★ 2026-10-11 20:39-21:18 · 重大突破：异步页流水（Async Page Pipeline）首战
>
> **超池解码从"个位数深谷"到"稳定高位"**——v2 引擎 20:39 起服、20:43 首战、21:04 多轮：
> - **峰值 decode 333.0 tok/s（20:48:58，host 98.2%）；连续 40 秒破 300**（20:48:53-20:49:33，10 样本 296-333）；
> - **首战 130 样本中位数 100.5 tok/s**（同指标：挂账 42 前凌晨版 **5.6**——**18 倍**；批量版 103.6 持平——但峰值能力 333 vs 155 翻倍）；
> - **74.4K 深超池（host 99%）decode 仍 114.4**（req#57）；**16K 输出长任务 decode 251.1**（req#7）；**prefill 极值 991.4**（req#58）；
> - **多轮对话可用（核心突破——v2 前多轮必死：第二轮即掉个位数）**：5-6 轮正常推进；深谷（页操作风暴，decode 1-6 tok/s）**可自愈爬出**（req#61 实例：谷 100s → 峰 60s → 深谷 155s → 峰 → 16K 输出全部完成，6m0.3s）；自动压缩后仍 100-157。
>
> **机制**：demote/restore 页搬运与 decode kernel **流水并行**——批量攒页（8 页/批）+
> transfer stream 异步提交 + 下一步收割（等待被上一步 kernel 时间覆盖）→ **decode 永不等页**。
> 挂账 42 全链（取消检查点前移 → 批量 demote → 异步 demote）+ 挂账 44 profile 定案，
> 源码增量 `patches/ledger42_v2_async_demote.patch`（基线 s6-20261008@3b9dc83）。
>
> **与 KVMem 的关系（两层架构）**：KVMem = **数据层**（KV 页放哪 + 按需召回——"放得下"）；
> v2 = **搬运层**（页搬运与解码解耦流水——"搬得起"）。OS 类比：KVMem = 虚拟内存 + 按需调页；
> v2 = 异步 I/O（脏页后台回写 / 预读）——**页自由流动，解码永不停顿**。
>
> **📄 完整技术解析** → [`docs/技术解析-异步页流水-v2-20261011.md`](docs/技术解析-异步页流水-v2-20261011.md)
> （问题背景 / 机理 / v2 实现与正确性契约 / **与 KVMem 逐项对照 + 常见误解澄清** / 实机验证 /
> 死亡谷分析 / 施工档案与回滚锚）；工程记录详见[构建史](docs/ninfer-kvmem-项目构建史.md) §三·十九。

### 全部战役（按 [构建史](docs/ninfer-kvmem-项目构建史.md) 逐节对应）

| # | 战役 | 结果 | 构建史 |
|---|---|---|---|
| 0 | 建线与 git 基线；首轮技术调研；三轮交叉审核收敛 | 方向与分工定案 | §一/二/三 |
| 1 | P0 启动层适配 Coder390 + 引擎统一 self-built + 裸解码基线（17 tok/s 成因确定） | 部署链打通 | §三·六 |
| 2 | P1 MTP 数据侧重打包（q4_0 → q8_0 位级无损，三档验收） | MTP 头可换 | §三·七 |
| 3 | **MTP 跑通**：官方 Q8MTP 两度显存失败 → 自转 iq4_nl（省 212 MB）→ 起服 A/B；ctx 扫描；三量澄清（max-context / WINDOW / kv-capacity）；256K + 40K 压榨 | **decode 105 → 256K 上下文** | §三·八 |
| 4 | 启动器定稿（P1b 参数重写，8→10 预设） | 一键起服 | §三·九 |
| 5 | 视觉可行性 + 定稿参数"闪退"根因（模型容器缺 vision 组件） | 闪退根修（launcher 联动） | §三·十 |
| 6 | 两处定稿纠错（用户裁决）+ 思考预算占显存取证 + 视觉嫁接挂账 | 参数口径修正 | §三·十一/十二 |
| 7 | **视觉塔嫁接**：282 MiB（333 对象，q4/q5/q8/bf16 混合）逐字节并入自转头容器；识图 26.9 s | 视觉可用 | §三·十二 + 开篇第三关 |
| 8 | ngram 实测（两臂对照：+2.7%，无统计显著性） | 保持默认 | §三·十三 |
| 9 | **DSH 撞墙定案**：`--kv-lease-growth` 深超池 bounded completion（上游 B35 同问题）——三轮交叉审核收敛 | **去 growth，撞墙清零** | §三·十四/十五 |
| 10 | **W1-W4 引擎施工**（思考熔断三连缺陷，patch 84 行）+ 四重验收 | 潜在缺陷清除 | §三·十七 |
| 11 | **A 臂闭环**：两轮 DSH agentic 零截断（16,143/11,782 tok）；池上限标定；视觉三合一 | 挂账 38 销账 | §三·十六 |
| 12 | **自主实验夜**：64K 池标定（graph-allowance）+ **页漂移定案**（多轮 replay 挤出早期页 → decode 3 tok/s）+ **stream 挂起双重缺陷**（挂账 41）+ 挂账 39 销案 | 三类新形态定性 | §三·十七 |
| 13 | 上游 23 提交逐条评审（无重复；B34/B35/B37 对应）+ sink=5120 实施（skeleton 4→80 页）+ KVMem 源头侦察（issue #114 / tancau brief / 挂账 42 蓝图） | 缓解落地 + 施工设计待审 | §12/§13 |
| 14 | DSH 联调：自动压缩触发调参（ctx 229,376）+ maxTokens 24,000 封顶 | 长会话工作流闭环 | §三·十七 §8 |
| 15 | **v2 转正**：独立交叉审核（2×40 轮深压）+ 实况 127 轮连跑 0×500、峰值 403.7 | 异步流水成为日常运行档 | §三·十九~二十九 / 40-47 |
| 16 | **换底座**：Swift-1.5 IQ3_S 实载（11.3 GiB / 9.4 s）+ KV 档 A/B（rk8v4 速度与接受率双优）+ 请求线实测（中位 56,440 / 最大 96,430） | 生产切 IQ3_S + rk8v4 @ 65,536 | §36-39 |
| 17 | **谷（时段性慢态）攻关 S1-S13**：四区段仪表化 → 路径收敛 → 逐项排除（PDL / 页中转 / 宿主路径 / 页档位 / 池大小 / 节流）→ **可按需复现（谷档 1/25）** → **机制定位 = host 侧提交阻塞（驱动内部）** → **深档受机器态时窗支配（窗内 4/4、窗外 8/8）** | 可控（指纹可检 / 分钟级自愈 / 回避手段已确证）；时窗开合与行号级根因待解 | §48-73 + 夜研-1/2/3 + 深档搜索 |
| 18 | **异步贡献判决实验**：深轮重载 ON/OFF 同条件对照——拆掉异步 decode 拖慢约 20%（r=0.80），最深段差约 2.0 倍 | 异步价值主张获对照铁证 | 夜研-1/2/3 |
| 19 | **公开材料**：双语 README + 双语 18 页 PPT + 公开技术说明 | 面向社区 / 上游协同 | docs/ |
| 20 | **sym "挂死"根因闭合**：构建缺 arch ⇒ sm_86 ⇒ JIT 长征假死；sym3 重编 cuobjdump 验收 384×sm_120a | 事故根因闭合 + 产物验收门 | §128 / T#0056 |
| 21 | **谷触发条件判决**（Gen5×外压×贴边六批矩阵）：AND 三条件钉死；零外压从不触发；WHEA 与谷无因果 | "可按需复现"补全适用域 | §134-135 |
| 22 | **卡死元凶判决收官**：三件矩阵（S13 无符号卡死 vs sym3/offi 带符号"谷但完成"）⇒ 元凶=符号链接缺失 | 卡死定位为构建问题、可制造可回避 | §136 / #0069 |
| 23 | **异步 DEPTH 三档浅载对照 + 启动器整治**（现役三引擎/六档模型/异步×深度/场景引擎正交） | 异步价值口径收口到"深载" | §137-139 |

> 以上为主要战役**精选**；**逐轮完整过程**（每次决策的证据链、失败与回归记录）见 **[项目构建史](docs/ninfer-kvmem-项目构建史.md)**（§1–§140，含挂账台账与仪表链）。

### 压榨：每个参数都标定过

| 参数 | 起点 | 终点 | 方法 |
|---|---|---|---|
| 高速池（显存） | 40,960 | **51,200 稳定**（55K 贴边不可复现、56K 缺 17-50 MiB 弃案；**64K 实测成功**——需 `--cuda-graph-allowance-mib 64/128` + 净 GPU，2026-10-11） | 逐档起服，以启动预约字节数精确定档 |
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
| 高速池（显存热 KV） | 40,960 | **51,200 稳定**（标定 55,296 贴边 / **64K 实测成功**；全量 KV = 高速池 + 16 GiB host 环，两级承载 256K） |
| decode 速度 | ~100 tok/s | **105-233 tok/s** |
| 视觉 | 无 | **识图 26.9 s**（CPU 编码零显存） |

---

## 当前定稿（2026-10-19 更新）：**六档模型 × 三现役引擎 × 4 场景预设**

启动器"模型"维度现为**六档**（换模型自动带整套参数，`MODEL_BUNDLES`：KV / 池 / CUDA-Graph 预算 / 视觉一并切换）；"引擎"维度为**独立正交**下拉（跑哪个二进制，与场景参数解耦）= **现役三件**；场景预设 = **4 个**（2 模式 × 2 模型：生产 / 压力）。参数逐项解释见 **[`docs/引擎启动参数与配置档-20261014.md`](docs/引擎启动参数与配置档-20261014.md)**。

| 现役引擎件 | 身份 | 一句话性质 |
|---|---|---|
| **S13 · 生产件**（`engine\self-built-20261008\ninfer-serve.exe`，sha `322A972D`） | 官方链 14.44、**无符号** | 日常生产件；**Gen5+外压 400 = 卡死不返回**（已知短板，避开该组合） |
| **offi · 官方链 14.44 + 符号**（`engine\variants\ninfer-serve-sym-official.exe`，sha `3543AD18`） | D 项判决件 | Gen5+外压 400 = **44.5 谷但完成**——卡死未复现 |
| **sym3 · 新构建链 + 符号**（`engine\variants\ninfer-serve-sym.exe`，sha `9453FFC6`） | 同参重编判决件 | Gen5+外压 400 = **41 谷但完成** |

> **卡死元凶判决（§136）**：三件唯一变量差 = 符号链接——**生产/外压场景建议直接选用带符号件**（offi/sym3），卡死形态不再复现；谷（慢但走得完）仍存在于全部三件，属负载×环境现象，见"已知限制"。

| 档 | 模型件 | KV | 池 | Graph | 关键实测 |
|---|---|---|---|---|---|
| **SWIFT 1.5（现行生产）** | `swift15_iq3s_mtp.ninfer`（11.3 GiB 上卡） | **`rk8v4`**（实机定档） | **65,536**（池≥工作集硬纪律）/ int8 上限 57,344–61,440 | **192**（硬要求，64 会告警） | 深 60K decode 143.7 tok/s / 接受 64%；载入 ~9 s；65,536@rk8v4 free 727.9 MiB |
| **Q2LYNN（定稿基线）** | `…Q2LynnStyle-MTP.mtp-iq4nl.ninfer`（+`…vision` 嫁接件） | `rk2v4-e8` | 51,200（稳定）/ 65,536（实测） | 64 | 历史全部实测都在它上面；基准**冻结**于 [`baselines/q2lynn/`](baselines/q2lynn/) |
| BONSAI | 前序线件（**未下载**） | — | — | — | 仅登记待测试（启动器选它会提示） |
| iq4nl / iq4nlvis / orig | 自转 MTP 头（无视觉）+ 视觉嫁接件 / 纯基线原件 | — | — | — | 内部加工链三态，见下方 models 三件套说明 |

- 引擎件：**三现役**（见上方现役引擎表）——生产件 = `engine\lineage\I3b_step13_fourlayer_20261015.exe`（sha256 `322A972D…`；= 上游融合引擎 + I3b 全链补丁（p2/s2–s11）+ ledger42×3/44/46×2/47 + W1-W4；仪器门 `NINFER_STEP_PROFILE` 默认关，零行为）；符号判决件在 `engine\variants\`。**2026-10-19 新增结论：Gen5+外压场景生产件卡死、带符号件"谷但完成" ⇒ 该场景选 offi/sym3**（§136 三件矩阵）。
- 上下文 256K 逻辑（262,144）；池外 KV 自动下沉 16 GiB host 环；投机 **MTP K4**；思考 high + 预算 16000；止血 `--recover-invariant-failures`（**无 growth**）；视觉 overlay/off；并发 **1**（环硬约束）
- **池 ≥ 工作集是硬纪律**（超池 ⇒ 检索子集介入 ⇒ 内容可能变化，见"关键工程结论"）
- 每档基准与实测数据存 `baselines/<档>/`（冻结集只增不改；golden SHA 只在同档内可比）

## 快速开始（已有引擎与模型时）

```
启动器.bat            # GUI 唯一入口，4 个场景预设（2 模式 × 2 模型）
```

选预设 **★定稿 51200稳定（无growth）** → 起服 → `http://127.0.0.1:8094/v1`（OpenAI 兼容）。

命令行等价（⚠️ **KV_ENV 六开关缺一不可**：缺 `NINFER_KV_WINDOW` 引擎拒启，缺其余"起得来但静默答错"；`NINFER_KV_SINK=5120` = attention-sink 骨架页，2026-10-11 官方 D-01 对标新增，banner `skeleton=80` 为生效判据）：

```bat
set NINFER_KV_WINDOW=32768
set NINFER_KV_SINK=5120
set NINFER_KV_RETRIEVE=8192
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
> 启动器（`ninfer_launcher.py`）已内置上述六开关 + 异步页流水 **A/B 开关 × 深度档（1/2/3/4 批在飞，默认 2）**（`NINFER_ASYNC_DEMOTE` / `NINFER_ASYNC_DEMOTE_DEPTH`）——实测依据：单发超池 r=1.13（打平）、深轮重载 r=0.801（净收益成立，最深段 ≈2×）；浅载三档对照 D2 187.1>D0 183.6>D1 182.6 ⇒ 异步价值随工作集深度上升而显现。做 A/B 只切这一项、其余不动，改档需重启 serve。
engine\lineage\I3b_step13_fourlayer_20261015.exe models\swift15_iq3s_mtp.ninfer ^
  --host 127.0.0.1 --port 8094 --model-id swift-1.5-qwen3.8-27b-gsq-rco-iq3s ^
  --max-context 262144 --kv-capacity 65536 --cuda-graph-allowance-mib 192 --kv-dtype rk8v4 ^
  --host-kv-mib 16384 --prefill-chunk 512 --spec mtp --draft-tokens 4 ^
  --default-max-tokens 32768 --default-reasoning-effort high --default-thinking-budget 16000 ^
  --max-concurrency 1 --recover-invariant-failures
```

> `--model-id` 是**服务招牌名**（API `model` 字段），与权重真身名可不同：`engine_ctl` 现按权重件自动切（swift / Bonsai / 默认 coder390），工具侧从 `/v1/models` 读（`scripts/_modelid.py`）——**不用手改**。Q2LYNN 档把 KV 换回 `rk2v4-e8`、池 51,200、Graph 64 即可（或直接用启动器预设）。

客户端：任何 OpenAI 兼容工具；DSH 接入示例见 `docs/教程-KVMem与短测-给agent与使用者.md` 与构建史（provider 配置含 `streamIdleTimeoutMs: 3600000`）。

## 仓库结构

本库**不是**自包含的引擎发行包，而是"**上游引擎源码 + 本线全部工作产物**"的工作区叠加层：

| 路径 | 内容 | 在库内 |
|---|---|---|
| `docs/` | **构建史（§1–§140 完整历程）**、交叉审核报告、调研、教程 + **`引擎启动参数与配置档-20261014.md`**（参数全表/两档配置）、`KV档A-B-*`（KV 精度 A/B）、`深上下文池收益与A2适用域-20261014.md`、`Swift换底座-三臂结果与int8预算-20261014.md` | ✅ |
| `build/` | 引擎构建脚本（`s6_1208a.bat` 等）+ 3 份基线补丁（`build/patches/0001-0003`）+ 产物清单 | ✅ |
| `scripts/` | 模型加工（`recode_mtp.py` / `graft_vision.py`）+ 探针（`test_ab_arm1.py` / `probe_recall*.py`）+ 谷测量（`valley_bench.py` / `valley_history.py`）+ **新工具**：`verbatim_gate.py`（逐字一致门，8 提示）、`bisect_env.ps1`（环境二分）、`gpu_probe.cu`（机器级健康探针）、`_modelid.py`（招牌名解析）、`valley_watch.ps1` + `watch_launch.ps1`（守望者 `Ninfer-KVMem-Async守望者`）、`pdl_aba.ps1` + `valley_trigger_aba.ps1`（PDL on/off A-B-A）+ **谷攻关分析件（随仓发布）**：`audit_selfinduce.py` / `audit_dims.py`（自诱导混淆审计：条件概率对照 + 维度拆分）、`freemem_vs_valley.py`（宿主内存 × 谷：撤回旧"无内存信号"负结果的那把尺）、`timeline_deep.py`（深谷窗 1 分钟分辨率对齐）、`memhold.py`（宿主内存压力施加器，A 组阳性对照执行件） | ✅ |
| `tools/` | **诊断仪器源码 + 工程工具箱（随仓发布，可复现性）**：仪器 = `concur_bench.cu`（跨进程：GPU 核延迟 / 宿主页读延迟 / 宿主页读带宽三测）· `pageable_bench.cu`（pageable vs pinned 拷贝对照）· `vram_hold.cu`（**按需触发谷**：外部占显存）· `submit_load.cu`（提交洪泛）· `gpu_probe.cu`（机器级健康探针）+ 各自 `build_*.bat` + **5 个预编译 exe（~880 KiB，免 CUDA 工具链即可用）**；工具箱 = `dump_stack.py` / `sym_resolve.py` / `unwind.py`（崩溃栈回溯与符号解析）· `find_exception.py` / `find_throw_string.py` · `gate_check.ps1` / `merge_verify.ps1`（交付闸门与合并校验）· `vram_model.py` / `bench_analyze.py` / `range_check.py` · `archive_build_output.ps1` / `retire_dir.ps1` / `backup_file.py` / `daily_append.py` / `sda_trap.py` / `commit_msg_denylist.txt` 等 | ✅ |
| `patches/` | **19 个引擎补丁**：I3b 链（`i3b_p2/s2/s3b/s3b_fix/s4/s6/s7/s8/s9/s10/s11`——step-profile / submit 拆分 / sticky 修复 / 图内事件 / **S6 段级打点** / **S7 PDL 开关 + target 三分** / **S8 PDL 自报** / **S9 verify 细分** / **S10 运行期 PDL** / **S11 GDN 常驻**）+ W1-W4 修复 + ledger42×3 / 44 / 46×2 / 47 | ✅ |
| `baselines/` | **每模型一套基准**（2026-10-14 立）：`q2lynn/`（**冻结**：逐字门噪声地板 8/8、KV A/B 台账、深上下文台账、容量表）+ `swift15_iq3s/`（现行：四臂逐字件、容量表）+ `README.md` 纪律 | ✅ |
| `repro/` | **源码树 bundle 快照**（分支 `line-coder390` @ `79457af`，2026-10-12 打）+ 版本台账副本 `MANIFEST.txt` | ✅ |
| `ninfer_launcher.py` | GUI 唯一入口（**三品牌模型选择**、场景预设、校验告警、KV_ENV 六开关注入、`MODEL_BUNDLES` 换档联动） | ✅ |
| `serve_tee.py`、`start-coder390*.bat` | 起服工具 | ✅ |
| `engine-src/` | **引擎源码树工作副本**（构建实际读取 `engine-src\src-tree\fusion-engine-src`；根含 `PROVENANCE.md` 与完整 git 历史） | ❌ 未跟踪（入库快照 = `repro/*.bundle`） |
| `official-repo/` | 公开上游对照 clone（**本线构建不读它** —— 构建读 `engine-src/`） | ❌ 未跟踪 |
| `engine/` | 构建产物二进制（~6.5 GB） | ❌ 本地构建 |
| `models/` | 模型三件套（~40 GB，见下） | ❌ 外部下载+本库脚本加工 |
| `refs/` | 发放包与 Bonsai 线参考材料（**未入库** → 外发复现者拿不到，见复现指南） | ❌ |

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

## 上游仓库

```
【我方家族】GitHub 用户 paicat1，三仓逐代迭代（README 开篇三仓表）
  仓一 [paicat1/Bonsai-27B-NInfer](https://github.com/paicat1/Bonsai-27B-NInfer)
       （main=项目层 / engine-main=引擎层，两分支一体）
       Bonsai-2-27B 三元量化（2.125 bit，9.81 GiB）跑上 NInfer：Ambolio 移植 +
       CraneBW 内核、改 CMake、自产 v2 制品；Device/Host 双层 KV（被动容量）；
       MTP/DFlash2 投机。极值：prefill 2,850 / decode 396.9 tok/s；89|120a
    └─ 仓二 [paicat1/Bonsai-27B-NInfer-kvmem](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem)
         KVMem 环（主动检索）：显存小池 + 主机卸载、可小于上下文、内容打分
         SELECT、六开关；混合投机 dflash2(K1-15)+MTP(K1-5)+ngram，K=7 甜点
         （K≥10 崩塌）、接受率语料效应（数数字 91% vs 散文 3.7-13.4%）；
         自编整套引擎（MSVC 补丁 ×7 + Design C 治"思考停止空正文"）+ 双引擎对照；
         GUI 启动器与 serve_tee 自建。极值：prefill 3,820 / decode 748.6 tok/s
         （本机部署/工作副本 = J:\KVMem-GSQ）
       └─ 仓三 [paicat1/Ninfer-KVMem-Async](https://github.com/paicat1/Ninfer-KVMem-Async)【★本仓，origin 即指向它★，2026-10-13 由 Qwen38-27B-NInfer-kvmem 改名】
            换大模型 Qwen3.8-27B-Coder390-EfficientThink：自转 MTP 头（iq4nl）、
            思考熔断三连缺陷修复（W1-W4）、growth 定案、池标定 51,200、
            视觉塔嫁接、256K 逻辑上下文；Qwen 4 27B（Bonsai/NInfer 格式）着陆预备

【上游】
  [1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem)（引擎源码出处；本线 s6-20261008 @3b9dc837
  → 自编 self-built-20261008；落后其 main 23 提交）
  [tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring)（环算法）＋ [kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3)（策略层）→ 已并入该仓
  NInfer 基座：[Neroued/ninfer](https://github.com/Neroued/ninfer) → [ashalliants/ninfer-3090](https://github.com/ashalliants/ninfer-3090)（0.11.0-rtx3090）→ [iamwavecut/ninfer-all](https://github.com/iamwavecut/ninfer-all)
  官方上游：**[kvmem/kvmem](https://github.com/kvmem/kvmem)**（双后端 llama.cpp + NInfer；原 `kvmem/kvmem-llama.cpp` **已声明停用、迁入本仓**；RC2 线 = iamwavecut/ninfer-all + KVMem 整合包）
```

- 上游 23 个新提交已逐条评审（构建史 §12）：无引擎行为级变更；B34=页漂移、B35=撞墙、B37=压缩摘要截断已各自对应本线修复或规避；吸收走 cherry-pick（详见 `docs/上游谱系与跟踪纪律-20261011.md`）。

## 从零复现指南

**前置**：Windows · RTX 5080 16 GB（或同档）· 128 GB RAM · VS2022 BuildTools（C++20、CMake、Ninja）· vcpkg（本机 `J:\vcpkg`）· CUDA 13.3 · Python 3.12 · **PCIe 插槽建议运行在 Gen4**（Gen5 + 显存争用场景实测触发 WHEA 风暴，本机 BIOS 已降 Gen4；跨代数数据不可直接对比）。

1. **引擎源码**——源码必须落在 **`engine-src\src-tree\fusion-engine-src\`**（`build\s6_1208a.bat` 第 34 行的 `SRC` 读这里）。两选一：

   **A0. 本仓 `engine-main` 分支（最直接 · 与前两仓同构；转公开后无需权限、可直接克隆）**：本仓 = **双分支一体**（`main`=项目层 / **`engine-main`**=引擎层；tag **`engine-20261013`**）：
   ```bat
   git clone -b engine-main https://github.com/paicat1/Ninfer-KVMem-Async.git engine-src
   ```

   **A. 本库快照 bundle（离线备选 · 含完整 git 历史）**：`repro/` 带一份自持源码树 bundle：
   ```bat
   git clone repro\qwenline_line-coder390_20261013_r2.bundle engine-src
   cd engine-src && git checkout line-coder390 && cd ..
   ```
   快照 = 分支 `line-coder390` @ `da5a710`（**2026-10-13 打 · 当前基线**，tag `H1_20261013_baseline`；含挂账 54 修复 `35173e0`，iterate-1 `c800106` 已 revert）；
   sha256 = `9BF92C8C565F4289EC0417604A060E9E3B9C7BC9C3BBF09E954183248256E9EE`（**含 `refs/tags/H1_20261013_baseline`**）；仓库根含 `PROVENANCE.md`（血缘/分叉记录）与 `patches/`。
   *（已实测：`git bundle verify` 通过 + 真克隆一次核对 `src-tree` / `PROVENANCE.md` / `patches/` 均在。）*
   *（旧快照仍在库中保留：`repro\qwenline_line-coder390_20261012.bundle` @ `79457af`；以及首切版 `…_20261013.bundle`（不带 tag，sha `B25CD543…`）。）*

   **B. 从公开上游自建（可溯源）**：`git clone https://github.com/1314521gjy/ninfer-fusion-kvmem.git` →
   `git checkout engine-v0.11.0-kvmem-20261008`（**`2852f6f`**，上游 tag，已核对存在于 `official-repo/ninfer-fusion-kvmem`）→ 放到 `engine-src\src-tree\fusion-engine-src\` →
   依序应用 `build/patches/0001-0003`（= 基线上 3 个本地提交：`5b07bc1` MSVC 修正 / `a25012b` Design C / `3b9dc83` 测试 STANDALONE，**已整理入库**）+ `patches/` 下 **19 个补丁**（本线 I3b 链 p2→s11 + ledger 系列 + W1-W4 按序应用即得现行引擎：段级打点 + 四层 op 组打点 + PDL 运行期开关）。
   ⚠️ *B 为**未逐步实测**路径，以 A 为准。*

   **免构建替代**：发放包（沈三殊分发）提供**预编译引擎 exe**（按显卡取一个，~1.1 GB）——不写代码只想跑的话直接用它；
   总纲 `refs/01-沈三殊-发放包/00-先读我-总纲（必下与选下）.md`、下载清单 `…\01-模型下载清单（推荐链接）.md`（含地址/体积/sha256/加速法）；
   ⚠️ **`refs/` 未入库**，需自己取得（找作者沈三殊拿）。

2. **应用修复**：`git apply patches/W1-W4_engine_fix.patch`（W1-W4：思考预算熔断 `==`→`>=`、越界不再 abort、control 强制闭合、prompt-progress 门控放宽——四处均已实测验收）；其余补丁按需（非 I3b 的 8 个：ledger42×3 / ledger44 / ledger46×2 / ledger47 / W1-W4）。

3. **构建**：`build\s6_1208a.bat`（或 VS 环境 + `cmake --build <dir> --target ninfer-serve`；要点见 `build/README.md` 与 `build/patches/`）；产物部署到 `engine/self-built-20261008/`。
   ⚠️ **两条 2026-10-18/19 新增硬纪律**（代价：66 分钟冷编报废 + 一整个判决实验夜）：
   - **必须显式传 `-DCMAKE_CUDA_ARCHITECTURES=120a -DNINFER_SM120_NATIVE=ON`**——CMake 默认值会落到 sm_86，本机（sm_120a）无法直载 ⇒ PTX JIT 长征表现为"启动挂死"（§128 根因）；
   - **产物验收必须 `cuobjdump --list-elf` 核对 arch**（384 cubin 全 sm_120a、0 sm_86 才算过门）；
   - **若构建件用于 Gen5 / 外压长跑：注入符号链接**（env `/Zi` + `LINK=/DEBUG`，即 offi 配方）——三件矩阵判决显示**无符号构建在该场景下卡死不返回，带符号件"谷但完成"**（§136；日常 Gen4 生产不受影响）。

4. **模型加工**：从上表 ModelScope 地址下载 GGUF-NInfer 容器（即 `--mtp-src`，其内置 q8_0 MTP 头与视觉塔）与原件 →
   `python scripts/recode_mtp.py --src <原件>.ninfer --mtp-src <下载件>.ninfer --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst ...mtp-iq4nl.ninfer --verify` →
   `python scripts/graft_vision.py`（从同一下载件嫁接视觉塔）。

5. **起服验证**：上面的命令行（或 launcher）→ `curl 127.0.0.1:8094/v1/models` → `python scripts/test_ab_arm1.py`（健康探针）。

**换机/换目录必改的绝对路径**（本库 34 个文件写死 `J:\`；主要集中处）：`build\s6_1208a.bat`（`SRC` / `VCPKG_ROOT` / CUDA 13.3 —— 本机在 `J:\Bonsai\landing\cuda-13.3`，**外部线目录·只读引用**）、`build\*.ps1` 与 `build\s6*.bat`、`deploy_engine.ps1`、`start-*.bat`、`ninfer_launcher.py`、`scripts\*.py`。

**复现难度自评：中偏低（A 路全程实测）。** 引擎源码两路可得（本库 bundle 快照已实测可克隆 / 公开上游 + 补丁为未验证路径）、发放包有预编译 exe（免构建路径）、模型下载含 sha256 清单、构建脚本/参数/验收探针全在本库——途径全部明确，主要工作是 CUDA 环境 + 模型下载 + 按 `docs/教程-KVMem与短测-给agent与使用者.md` 起服。唯一非公开件是发放包本身（找作者沈三殊拿，或用源码自建绕开）。

## 关键工程结论（全部实测，踩坑沉淀）

- **`--kv-lease-growth` 是撞墙根因**：深超池构型（高速池 49-55K ≪ 逻辑 256K）下租约窗口（~4,096 tok）无法扩充时输出被砍（bounded completion，`finish_reason=length`）——超池构型要保住输出**不要开它**（融合引擎上游 README 第 218 行同口径）。已从定稿移除，撞墙清零（两轮 DSH agentic 实测：16,143/11,782 tok 连续输出零截断）。
- **池标定**：57,344 ✗（缺 17-50 MiB 随桌面负载波动）/ 55,296 贴边不可复现 / **51,200 稳定**；**65,536 实测成功**（2026-10-11，需 `--cuda-graph-allowance-mib 64~128` + 桌面 ≤~1.0 GiB——WDDM 归还不即时，逐日波动）。
- **挂账 39（已销案，2026-10-11）**：视觉请求 + 无 growth 曾触发 `scatter.cpp:18` 断言（HTTP 500）——现役引擎已不复现（V1b/V1c 实测）；视觉统一 hemostat=on（无 growth），growth 已退出所有路径。
- **KVMem 环 = 单并发**：环无法回收另一 lane 的设备页，`--max-concurrency >1` 启动即拒——**并发与 256K 深度/检索互斥**。
- **W1-W4 已修**（思考预算熔断三连缺陷 + 流式保活），patch 与四重验收见 `patches/`。
- **超池口径（B28）**：超池 prompt 的中段答案按"未核实"对待——`NINFER_KV_RETRIEVE` 检索开关是保命符。
- **召回开销已实测**：超池 prefill 被流水化吸收（~8-23%，60K 场景往返 ≈4-8 s），零截尾。
- **push 教训**：推送成功以 `git status -sb` 的 ahead 0 为唯一判据。

- **SWIFT 换底座实测（2026-10-14）**：`rk8v4` 在 Swift 上最快且接受率最高（深 60K 37.3 s / decode 143.7 / 64%），与 `rk2v4-e8` 输出**逐字相同**；`nvfp4` = "免费档"（速度≈现状）；**int8 上限 61,440**（65,536 差 35 MB 拒启）；换底座首次解锁"池 81,920 + 高精度 KV"。
- **池 ≥ 上下文（不只是速度，是可比性）**：超池 ⇒ 检索/选页介入 ⇒ 模型看到的是"选出的子集" ⇒ **输出会变**（同格式只差池大小的实测：`78bcb798` vs `8b3a141f`）；一切内容对比（逐字门 / golden SHA）**必须在池 ≥ 上下文下跑**。
- **谷（慢态）攻关进展（2026-10-19 更新）**：**触发三条件已钉死**（§135 六批矩阵）——**AND**（Gen5 PCIe + 外部显存压力 ≥400 MiB + 自由显存贴边 <400 MB），缺一不触发（零外压 8 例全健康；Gen4 下 68 探针 0 入谷）；**机制仍收敛在 host 侧提交调用**（`submit ≈ wall`、`wait = sync ≈ 0`，驱动内部阻塞），**PDL 以 ON/OFF 回切反例出局**；宿主路径 / 页档位 / 池大小 / 节流逐项实测排除；**WHEA 风暴逐拍对齐确认与谷无因果**（并发现象）；**"卡死"与"谷"二分**——无符号构建在 Gen5+外压下卡死不返回（元凶=符号链接缺失，§136），带符号件同条件"慢但走得完"；约 2 分钟最小复现协议已备（供社区/上游研判）。详见 ★ 2026-10-18/19 记录与[公开说明](docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md) §5.1。
- **招牌名 ≠ 真身名**：`--model-id` 按权重件自动切、工具从 `/v1/models` 读；含中文的 `.ps1` 必须存 **UTF-8 with BOM**（PS 5.1 按 GBK 解会解析崩）。

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
| 8 | KV 六开关缺一静默答错 | 缺任何一个：起得来、缓存命中率高、**中段答错、零报错** | KVMem 环/检索/window 开关缺一即静默退化（第六个 `NINFER_KV_SINK=5120` = 10-11 官方 D-01 对标新增） | launcher 固定注入 `KV_ENV` 六开关（含 `NINFER_KV_WINDOW`——缺它直接拒启） | 20,203 tok 超池 prompt 检索答案正确（restored=128） |
| 9 | 挂账 39：视觉 × 无 growth | 视觉请求 HTTP 500（`scatter.cpp:18` 断言） | 引擎旧版 scatter 路径缺陷 | 引擎更新后不复现；launcher 三处联动撤除（视觉统一 on） | V1b/V1c 起服 + decode 108.2 功能验证，销案 |
| 10 | 池标定与 64K 起服 | 65,536 池差 213 MiB 拒启；腾显存后仍差 149（WDDM 归还不即时，滴流 ~36 MiB/30s） | runtime 预留（CUDA Graph 驱动态）按 profile 自动算偏大 | `--cuda-graph-allowance-mib 128` 压 graph 预算补缺口 | 64K 起服 25s；decode 101.1（基线 101-104，**零代价**）；launcher 64k 档已绑该参数 |
| 11 | DSH maxTokens 全额预留 | 单请求 prompt+输出全额预留，65,536 输出上限放大超池面 | 思考计入输出 + DSH 默认 65,536 | DSH `maxTokens` → 24,000（单轮封顶；prompt ≤41,536 时 decode 期永不超池） | 生效验证：实机 started 行 `max output 24,000` |
| 12 | 长会话"页漂移"降速 | 34-39 轮 agentic 会话后 decode 从 122 → 3 tok/s，host 占用 98-110% | cache replay 逐轮重映射历史页，**最早页被逐渐挤出设备池**（34 轮后 ~330 页滞留 host → decode 每 token host 往返）——是**轮数**触发，与超池深度无关（三组对照：81K/72K/72K 全不掉速 134/126/134） | 缓解：定期新开会话（机制必需）+ 池扩容（28→~38 轮才触发）+ maxTokens 封顶；**根治 = 挂账 42 全链**（取消检查点前移 + 批量 demote + **v2 异步 demote**）＝ 已部署 + 实机验证 ✓（超池多轮 103-195 tok/s、10+ 轮零降速，见 §三·十九；v2.1 多批 in-flight 已施工 ✓ §三·二十四） | 机理两次独立实证（hidden 页判别：不掉速 ≤17 vs 掉速 329-334） |
| 13 | stream 挂起（原挂账 41） | 引擎请求 started 后永不 done：日志静默 + CPU 0 / GPU idle + TCP Established，重启才恢复（req#4 现场，DSH"思维断链"） | 🔀 **已并入挂账 42**（第三次复现定案，v3 规模修正版证伪"send 阻塞"）：根因唯一收敛 = **页漂移极端态下页操作深处同步点冻结**（§14.1） | 无"取消信号"死锁形态另立 **挂账 43**（步级看门狗，待设计 ✗）；挂账 42 全链部署后未再复现（待长跑观察） | 第三次复现定案：16K output / 270KB 载荷 / 20s 真停读（v3 规模修正版）✓ |
| 14 | 谷（慢态）范围收敛 | decode 25–28（偶发 11–12）、SM 100% 满频但功耗仅 63–98 W、几乎不碰显存、并行核**未**被饿死（2026-10-16 外部进程实测 6–8 µs；旧"饿死 8×"表述因**查无原始测量记录**已撤回） | 排除机器/驱动/降频/带宽、全部配置旋钮（二分清白）、KV/ring/demote 主链（裸解码满速）后，锁定 **MTP 图内 target 段** | S6 `%globaltimer` 段级打点（图 1107→1112 节点，capture 安全）；关 MTP 即愈 | 谷窗内三明治 A-B-A（44.2 s→9.3 s→44.6 s，非自愈）；**10-19 判决：触发三条件 AND（Gen5+外压≥400MiB+贴边）；卡死/谷二分（元凶=符号链接缺失，带符号件不再卡死）；机制仍在 host 提交路径（行号级待解）** |
| 15 | 启动器"两个模型"混淆 | 命令行同时出现 `swift15_iq3s_mtp.ninfer` 与 `--model-id qwen3.8-27b-coder390` | 招牌名硬编码旧线名，换件未同步 | `engine_ctl` 按件自动切 + `scripts/_modelid.py` 从 `/v1/models` 读 | 实测 `/v1/models` 只报真身名；工具端自动解析（a2gate 单轮正常） |
| 16 | 含中文 `.ps1` 秒退 | 守望者脚本起不来：`Unexpected token '}'` | PS 5.1 对**无 BOM 的 UTF-8** 按 GBK 解码，中文字符串被解错 | 5 个脚本统一存为 UTF-8 with BOM | 5/5 `PS-SYNTAX-OK`

> **未解决事项**（权威台账 = [构建史 §四·挂账表](docs/ninfer-kvmem-项目构建史.md) 1–28 行，下列为当前头部项）：**谷行号级根因**（host 提交路径具体阻塞点，dump 路线已关闭，改活体观测：谷态 nsys 栈采样 / spin-stamp 分段）；**Gen5 回切复测**（预登记已立：`docs\实验-Gen5回切复测-预登记-CB-20261019.md`，WHEA 复发即停）；**深载长跑异步 ON/OFF 对照**（异步的决胜局，浅载已证无差异）；**SWIFT1.5 目验**（model-id 修复后的用户侧重起目检）；**挂账表 §60–§139 逐节回填**（表体更新滞后，防旧状态与新结论矛盾）。历史小号挂账（43/46/48/49/54/55/W5 等）多数已并入上述或关闭，逐条状态以台账为准。

## 已知限制

- **谷（慢态）未闭合**（触发源=三条件 AND 已钉死，行号级根因待解）：**Gen5 PCIe + 外部显存压力 ≥400 MiB + 自由显存贴边（<400 MB）**三者同时满足才触发（缺一不触发）；期间 decode 掉到 25–28（偶发 11–12）而机器本身健康；机制收敛在 host 侧提交阻塞（驱动内部阻塞）、PDL 出局；**唯一确证缓解 = 避免与引擎争抢显存 +（本机已降 Gen4）**；期间可用裸解码（不传 `--spec`，~56 tok/s）规避；守望者自动记录谷窗证据；触发条件适用域内为"存在可稳定触发剂量（3/3，n=3，单机）"，**不是任意条件必触发**——复现前请先核对三条件；
- **C12：空闲后首请求挂死（2026-10-16 首次观测，未复现）**——引擎长时间空闲后，首个请求**可能永久不返回**：stderr 零输出（连打点都不出）、GPU 近空转（util ~2%、功耗 ~26 W）、请求日志有 start 无完成，**26 分钟不自愈、只能重启恢复**。已做主动复现（空闲 5 / 25 分钟 × 显存压力，2×2 四格）**全部正常应答** ⇒ **触发条件未知**。**遇到时重启引擎即可恢复**。与"谷"不同：谷是"慢但可自愈"，此条是"挂死"。**2026-10-19 更新线索**：三件矩阵判决确认"无符号构建 × Gen5+外压 ⇒ 卡死不返回"同形态，C12 与符号链接/Gen5 关联性待按该线索回判（**换用带符号件 offi/sym3 或保持 Gen4 可大幅降低风险**）。**欢迎反馈可复现线索**；

- 单并发（KVMem 环架构约束）；
- 256K 为模型原生上限——512K 属外推区，不可用（长文场景由 KVMem 检索兜底）；
- 视觉 CPU 编码 ~20 s/图（GPU 编码需视觉塔常驻 1.4 GiB 显存，须降池至 ~20K）；
- 超池中段正确性依赖检索开关（B28）；**且"超池"本身有风险面**：`prompt > 池` ⇒ 中段隐藏 + 页账风险（32K 池跑 40-49K prompt 实测触发 device page 不变式失败（§三·二十二）；64K 池跑 72.7K 亦约 11% 升级为请求级 500（§三·二十五））⇒ **池必须 ≥ 预期最大 prompt**。

## 文档索引

- **`docs/异步页流水-技术说明.pptx`**（18 页演示，另有英文版 `Async-Page-Pipeline-Technical-Brief.pptx`）/ **`docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md`**（公开版科普说明）——对外介绍与原理；
- **`docs/ninfer-kvmem-项目构建史.md`** —— §1–§140 完整历程（每个决策的证据链 + 挂账台账），**先读这个**；
- **`docs/引擎启动参数与配置档-20261014.md`** —— 启动参数逐项解释 + 两档配置（SWIFT 现行 / Coder390 定稿）+ 环境变量六开关；
- `docs/教程-KVMem与短测-给agent与使用者.md` —— 使用教程；
- `docs/KV档A-B-*` / `docs/深上下文池收益与A2适用域-20261014.md` / `docs/Swift换底座-三臂结果与int8预算-20261014.md` —— 精度-池-底座三组实测；
- `docs/审核-*.md` ×19（另 `交叉审核-*` ×2）—— TeleAgent 与 CodeBuddy 双向交叉审核记录；
- **`docs/FAQ-死亡谷-20261016.md`** —— **谷 FAQ**（怎么判断/会不会答错/怎么恢复/怎么预防/已排除什么）；

- **`docs/Minimal-Reproduction-Valley-On-Demand-20261016.md`**（EN）+ `docs/研判-驱动提交阻塞-最小复现与可行动项-20261016.md`（中文）—— **≈2 分钟最小复现协议**（一条命令：`scripts\valley_minrepro.ps1`），供社区/上游/驱动侧研判；

- **`docs/工程史-死亡谷根因排查与确定-CB-20261017.md`** —— 死亡谷根因排查工程史（120h 压测的完整排查链：触发/机制/排除矩阵；"卡死 vs 谷"的变量分离结论以构建史 §136 为准）。

- `docs/调研-*.md` ×3 —— tancau 同源引擎对比、撞墙机制、目标路径；
- `build/README.md`、`build/产物清单.md` —— 引擎构建细节。

## 致谢

**贡献归属（详见构建史）**：

- **[Neroued/ninfer](https://github.com/Neroued/ninfer)** —— NInfer 引擎基座（本仓引擎的始祖）。
- **[1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem)** —— 融合引擎源码（本线引擎 `self-built-20261008` 的直接出处）；KVMem 环 + host-backed checkpoint 的引擎层实现（含 `ensure_sequence_kv_mapped` 等核心机制）；Bug 手册 B33-B39 病历与 docs/13/14 修法库。
- **[tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring)** —— KVMem 环算法的原始实现（并入融合引擎）；**本线 W1-W4 修复的 diff 参照**（思考熔断三连缺陷的修法样板）；环复用深度/召回边界/decode 墙的作者级结论（brief，本线页漂移定位的重要参照）。
- **[kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3)（Di Chai）** —— 检索策略层算法（并入融合引擎）。
- **[kvmem/kvmem](https://github.com/kvmem/kvmem)（Leye Wang / wangleye 等）** —— KVMem **官方双后端仓**（llama.cpp + NInfer）：调优默认值对照（D-01..D-08 的来源）、[issue #114](https://github.com/kvmem/kvmem-llama.cpp/issues/114) 修法线索（issue 提于更名前的 `kvmem/kvmem-llama.cpp`；作者已声明该仓停用、统一到 `kvmem/kvmem`）。
- **沈三殊（shensanshu）** —— 引擎发放包、三元量化工具链与模型转换链（ModelScope `shensanshu/ninfer-ada-ternary`）。
- **Merkyor / nerkyor** —— 模型权重（Coder390-EfficientThink 系 NInfer 容器，含内置视觉塔）。

**本线自有工作**（构建史 §一至§十七）：Qwen3.8-27B 上车路径（自转 MTP 头 + 视觉嫁接）、W1-W4 patch 施工与四重验收、growth 撞墙取证与定案、页漂移/sequence 重建风暴/stream 挂起三类形态的发现与实测、**异步页流水（v2 搬运层）施工与首战 333 tok/s**（上游全材料审计未发现同款实现，见 `docs/上游谱系与跟踪纪律-20261011.md` §6.5）、池标定（51,200/64K/graph64）、DSH 联调（压缩触发调参、maxTokens 封顶）、A/B 方法论与探针脚本。前两仓血缘见开篇三仓表。

## License 与上游

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer 引擎基座 | [Neroued/ninfer](https://github.com/Neroued/ninfer)（基线 [ashalliants/ninfer-3090](https://github.com/ashalliants/ninfer-3090)，0.11.0-rtx3090） | Apache-2.0 |
| KVMem 环（并入融合引擎） | [tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring) | Apache-2.0 |
| 检索策略层（并入融合引擎） | [kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3)（Di Chai） | Apache-2.0 |
| 融合引擎（KVMem 环 + host-backed） | [1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem) | Apache-2.0 |
| KVMem 官方仓（上游对照，未并入） | [kvmem/kvmem](https://github.com/kvmem/kvmem)（双后端；原 kvmem-llama.cpp 停用迁入） | 见其仓 |
| 模型（Coder390-EfficientThink 系） | ModelScope [Merkyor/...-RLOO-GGUF-NInfer](https://modelscope.cn/models/Merkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-GGUF-NInfer)（实测下载）；HF `nerkyor` 同名系 | Apache-2.0 |
| 三元量化工具链 / 转换 / 校验 | 沈三殊（shensanshu）· ModelScope `shensanshu/ninfer-ada-ternary` | 见其发布页 |

本仓为上游衍生的部署/验证工程（非官方发布方）；详见 `LICENSE`（Apache-2.0）与 `NOTICE.md`。
