# 研判：PDL —— 谷的第一嫌疑（研究与关闭影响评估）

- 日期：2026-10-15 · 性质：**研判报告**（证据链汇总 + 因果评估 + 关闭影响量化 + 修法候选）
- 作者：CodeBuddy（办公室侧汇总）· 证据链 = 家里 CB 的 S6→S12 值守产出 + 构建史 §44/§45 + 夜间值守报告（2026-10-15）
- 结论状态：**方向强指 PDL，因果未闭合**（缺"谷窗内完整 ON-OFF-ON"；S12 同窗发生率对照在跑，预计 ~15:40 出统计判决）
- **⚠️ 更正记录（2026-10-16）**：本报告的"PDL 第一嫌疑"**已被后续实测推翻**——10-16 凌晨家里线完成两项决定性实验：① **谷已"按需复现"**（外部进程占约 1.2 GiB 显存 ⇒ 施加即入谷 7/7、释放即恢复、两轮可重复）；② **机制定位到 host 侧提交在驱动里被阻塞**（`submit ≈ wall`、`wait = sync = 0`；自然谷 3286 条 + 按需谷 6 条），并以 **ON/OFF 回切反例正式宣告 PDL 出局**（ON 健康 161 / OFF 深谷 27.6）。本报告正文保留原样（其数据、方法学与"关闭影响"评估仍有历史价值）；PDL 相关表述请以本更正与同仓 `研判-驱动提交阻塞-最小复现与可行动项-20261016.md`、`夜报-20261016-按需复现与驱动提交机制.md` 为准。

---

## 0. 摘要（一页速览）

1. **PDL 是谷的第一嫌疑**：指纹级吻合（纯轮询等待 = 满频 100%/功耗仅 63-98W/显存 4-19%/并行核被饿死 8×）+ 路径级吻合（MTP off 杀谷，谷在 verify(target) 路径内）+ 因果半张判决（01:11：ON 臂慢 7.4×、OFF 臂健康、输出逐字相同）。
2. **关闭 PDL 的收益损失 ≈ 0**：健康窗内 **PDL-ON ≡ PDL-OFF**（5 臂 × 7 探针 = 35 读数全落同一健康带 155-162，输出逐字相同；E1 烟测差异 ≤1.2%）。
3. **关闭操作零成本**：`NINFER_PDL_OFF=1`（捕获期生效，一次重启）；S10 运行期 flag 已实证**对已捕获的图无效**（图回放不再执行开关判断）。
4. **但先别急着定论**：还有一条强备选嫌疑 = **GDN gating 常驻**（sm_120a 真实每 SM 3 CTA、代码写死 2；上游已用运行时 occupancy 查询修复，我方补丁已备待建）。S12 判决正是这两条路的分叉点。
5. 若 S12 两窗相当（PDL 出局）⇒ 转 GDN gating 常驻；若 ON 窗谷率显著高 ⇒ PDL 因果成立 ⇒ 先关 PDL（零代价）再谈修法。

---

## 1. PDL 是什么（原理与本引擎形态）

### 1.1 技术原理

**Programmatic Dependent Launch**（Hopper+ 特性，CUDA 11.8+）：

- 传统串行 kernel：B 必须等 A **完全退出**（grid drain + 内存 flush + launch latency ~2-5µs/对）才能启动；
- PDL：A 调 `trigger_dependents()` 宣布"数据已对后继可见"；B 可**提前启动**，先跑不依赖 A 的前导部分（常量加载、smem 初始化、独立计算），在真正需要 A 数据处调 `wait_for_dependencies()` 握手；
- **收益来源**：隐藏 kernel 间 launch latency + 隐藏 grid-drain 尾部（A 未完时 B 已在预热）。
- **代价形态**：wait 是**纯轮询**实现；且消费核在重叠期只拿剩余 SM（引擎注释自陈 "runs up to half as fast"）。

### 1.2 本引擎形态（关键事实）

| 项 | 值 | 出处 |
|---|---|---|
| 封装 | `src/core/pdl.cuh`：`launch_consumer()`（图捕获期把内核挂成 programmatic dependent）/ `enter()` / `wait_for_dependencies()` / `trigger_dependents()` | 构建史 §44 |
| 调用点 | **131 处**：`launch_consumer`×57 / `enter`×29 / `trigger_dependents`×20 / `wait_for_dependencies`×14 / `enter_streaming`×若干 | P1-d 静态分析 |
| 构建实况 | `CMAKE_CUDA_ARCHITECTURES=120a` + `NINFER_SM120_NATIVE=ON` ⇒ 不定义 `SM8X_COMPAT` ⇒ **PDL 恒开** | 构建史 §44 |
| 上游对照 | 上游白皮书把 **120a 标"未验"**；上游引擎走 SM8X 兼容路（**PDL = no-op**）⇒ **PDL 激活是我线首开**，且**"粘性慢态"上游无先例**（本仓 GitHub 上 PDL 相关 issue/PR = 0） | P1-c 取证 |

### 1.3 上游生态知识（P1-c 30 分钟取证）

| 来源 | 关键知识 |
|---|---|
| **PyTorch #199166**（high priority · silent correctness） | `cudaGridDependencySynchronize` **只等"直接前驱"**；中间 store-only 核不等待 ⇒ 后续核提前起并读旧数据；且"**生产者必须给依赖核留 SM**，2048 行以上就全过了" |
| **vLLM #59467** | PDL **省的是核间 gap**（0.96 → 0.27 µs）；链上**非 PDL 核造成更长 gap** |
| **FlashInfer #6449** | **trigger 提前**（移到依赖 wait 后立即 trigger）⇒ **−1.7% 延迟** |
| **vLLM #59737** | 标准用法：消费核提前起、**读数据前再等** |

---

## 2. 为什么是谷的第一嫌疑（证据链）

### 2.1 证据一：机制指纹级吻合（最强的一类）

PDL 等待 = **纯轮询**（busy-wait）——与谷的 GPU 侧指纹逐项吻合：

```
谷期 util 99.8-100% + SM 满频 2910 MHz + pmon 锁定 ninfer-serve（87-99%）
但显存控制器仅 2.6-9%、功耗仅 63-98 W（健康 129-217 W/64%）
且并发普通 kernel 被饿死 8×（3.24ms、推导 0.33GHz vs 健康 0.39-0.42ms）
```

这是教科书级的"死转等待"签名——**在等待，不在工作**。

### 2.2 证据二：路径级吻合（MTP off 杀谷）

```
44.2s/25.4 → 9.3s/55.8 → 44.6s/25.8   （A-B-A 三明治，无自愈伪影）
```

MTP 关闭后谷消失 ⇒ attention/pool/ring/demote 路径全部排除 ⇒ **目标收敛到 MTP verify(target)/draft kernels**（S35）。
链定位：`text.cpp:751 → run_layers(Phase::Verify)`。

### 2.3 证据三：段级吻合（S6 设备侧时间戳）

`%globaltimer` 段戳（1-thread kernel / 段，1107→1112 节点）：首次慢带读数把自旋定位到 **TARGET 段**（120-134 of ~170ms/轮；draft 42-61；ingress/egress 0）。

### 2.4 证据四：因果"半张判决"（01:11）

| 臂 | 引擎自报 | decode | wall | 输出 sha |
|---|---|---|---|---|
| 1 | **ENABLED（ON）** | **20.9**（谷） | 55.4 s | f1626c59 |
| 2 | **DISABLED（OFF）** | **154.6**（健康） | 7.3 s | **f1626c59（逐字同）** |

**ON 慢 7.4× / OFF 快 / 输出逐字相同** ⇒ 方向强指 PDL；**唯缺 ON3 反转臂**（排除"自然自愈"），故仍不作为定论。

### 2.5 证据五：链上第一打点对象（S11）

`ops/context_kv_materialize/materialize.cu:411 / :459`（`enter_streaming()` / `enter()`）——**每轮都在关键路径上**（即便搬运字节为 0，映射/记账 kernel 仍跑并 `wait_for_dependencies()`）；是 **C5（搬运）× C1（PDL）的交点**。

### 2.6 反证与边界（诚实清单）

| 项 | 结论 | 证据 |
|---|---|---|
| C5 环搬运竞争 | **否**（对本谷） | 干净谷窗（22:19-22:26）搬运 = 0 页/0 s；全时段 36× 差是**负载混淆**（深负载同时导致搬运与低 decode） |
| C7 页/映射风暴 | **稳定否定** | 全时段 `materialization = {}` 为空 |
| C3 宿主侧等待 | 早已被数据削弱 | 文本路径不在链上 |
| C6 时钟/降频 | 弱 | 慢窗实测满频 2917 MHz |
| C8 图调度 | 弱未排 | 待图内 vs eager 对比 |
| 02:13 深谷捕获 | **不构成证据** | verify 212.67ms 深谷后五臂全健康（ON 7.1% vs OFF 0%，n=14） |
| S12 早期数据 | **待判** | 4.5h/775 探针纯空转零谷（说明谷是负载诱发）；负载+发生率对照在跑 |

### 2.7 方法学门槛（为什么"再抓 10 次也全是废数据"）

两条硬事实合起来把常规实验方法全部排除：

1. **谷是长跑进程内的状态，重启即重置**（3/3 捕获验证）；且**谷可 5 秒内自愈**（01:21:18 谷 → 01:21:23 已 159.3）；
2. **PDL 属性在"图捕获时"烘焙**——S10 运行期 flag 实测**对已捕获的图无效**（01:20-01:21 五相切换，引擎全程未打印 `runtime switch` 行；代码级根因：`launch_consumer` 的条件 `graph_dependent(launch.stream) && !pdl_kill_switch()` 只在捕获期为真）。

⇒ **重启式 A-B-A 在物理上测不到谷；运行期开关切不了已捕获的图——两扇门都关了。**
⇒ 正解 = **S12 同窗口发生率对照**（`scripts\valley_load_incidence.ps1`）：不重启、每窗起服（ON/OFF 自报核验）+ 持续深负载（60KB×8 轮，15K→120K 跨 65,536 池）+ 每循环浅探针；**ON 窗谷率/深谷次数显著高于 OFF 窗（跨 6 对）⇒ 因果成立**；相当 ⇒ PDL 出局。

---

## 3. 关闭 PDL 的影响评估（量化）

### 3.1 收益损失：≈ 0（两项独立标定）

| 标定 | 设计 | 结果 |
|---|---|---|
| **E1 烟测**（S7 后） | PDL-on/off 单对比 | 浅 144.4→142.9（−1%）、深 137.1→135.4（−1.2%）；**输出 sha 逐字相同** |
| **S10 null 基线**（01:22-01:36） | 5 臂（ON/OFF/ON/OFF/ON）× 7 探针 × 120s（多探针分布法） | **35 读数全部落在 155-162 健康带**，所有臂输出逐字相同（f1626c59） |

### 3.2 为什么可能榨不出收益（机制解释）

1. **graph 重放形态**：每轮整图一次提交（1107 节点一个 graph launch）——PDL 主要省的是 eager 串行下的 kernel 间空泡，而 graph 执行器本身已把启动开销摊平；
2. **执行时间主导**：1107 节点 ÷ 27-32ms ≈ **24µs/节点**——执行时间主导的形态；即使每对 kernel 有 1-3µs 缝隙，全图理论上限也只有 ~1-3ms（~10%），实测 <1% 说明缝隙本已被压得很小；
3. **设计取舍**：`enter()` 注释自陈的"依赖核只拿剩余 SM ⇒ 半速"——收益与代价并存，本工作负载下两者都接近不可测。

### 3.3 风险消除（若因果坐实）

谷（或至少"PDL-ON 专属的谷"）消失——按 §2 的指纹，等待点在 PDL 依赖自旋，off 后该自旋路径不存在。

### 3.4 操作方式与注意事项

```
NINFER_PDL_OFF=1       ← 环境变量，捕获期生效（生产起服直接加）
NINFER_PDL_FLAG_FILE   ← S10 运行期 flag（.temp\pdl_off.flag，每秒查一次）
                           ⚠️ 只影响"新捕获的形状"；已捕获的图不受影响（实测）
NINFER_PDL_OFF（启动语义）优先于 flag 文件
```

- 120a-native 构建**默认恒开**——关闭必须显式设置；
- 关闭成本 = **一次重启**（启动语义不变，S8 自报保留）。

### 3.5 收益损失的诚实边界

- "零收益"结论来自**健康窗 + 短探针**的 35 读数与 2 组烟测——**长稳态、长 prefill、高并发 batch** 等形态尚未分场景标定；
- 如果未来某场景确实需要 PDL 的核间重叠（例如极短核密集的形态），可回退研究"保留 PDL 的修法"（见 §4）。

---

## 4. 修法候选（如果"保留 PDL"的第三条路值得走）

前提：S12 判 PDL 因果成立。按上游经验四条路：

| # | 修法 | 依据 | 备注 |
|---|---|---|---|
| ① | **trigger 提前**（移到依赖 wait 后立即 trigger） | FlashInfer #6449（−1.7%） | 改动小，先试 |
| ② | **减少链上 store-only/短核**（或给它们补 trigger） | PyTorch #199166（"只等直接前驱"陷阱） | 需先盘点链上的 store-only 核 |
| ③ | **逐点确认消费核"等的确实是它要的数据"**（13 个等待点清单见 §5） | PyTorch/ vLLM 标准用法 | 13 点逐一过，工作量大但彻底 |
| ④ | **对特定段禁用 PDL**（S7 开关粒度化 / 按 kernel 白名单） | 本线自研 | 折中：保留收益区、切掉病理区 |

**若 PDL 出局** ⇒ 转 **GDN gating 常驻**（已备补丁）：

- 事实：27B 几何的 GDN gating kernel 在 sm_120a 构建上 **REG=72（sm_86 调优值 65）+ 40 KiB 动态共享 ⇒ 真实每 SM 常驻 3 CTAs，而代码 `constexpr` 写死 2**（`ops/gdn_gating_proj/bf16/bf16_gdn_gating_proj_kernels.cu:261`，注释 "Measured on the sm_86 build"）⇒ RTX 50 卡上 cooperative 网格少 1/3 并行度；
- 上游已于 10-14 用运行时 occupancy 查询修复同类问题（`iamwavecut/ninfer-all` `ec26e64`）；
- 我方补丁已备：`patches\i3b_s11_gdn_residency_occupancy.patch`（3,851 B，运行时 `cudaOccupancyMaxActiveBlocksPerMultiprocessor` 查询 + 失败回退调优表）——**待构建**（排在 S12 窗间隙，避免抢 CPU 污染发生率对照）。

---

## 5. 附录 A：verify 链上 13 个 PDL 等待点（修法清单）

| 优先级 | 等待点 | 形态 | 理由 |
|---|---|---|---|
| ⭐⭐⭐ | `ops/context_kv_materialize/materialize.cu:411 / :459` | `enter_streaming()` / `enter()` | **每轮都在链上**；C5×C1 交点 |
| ⭐⭐ | `ops/softmax_attention/sliding_window/kernel.cuh:47 / :72` | `enter_streaming()` / `enter()` | 每层注意力，forward 主计算 |
| ⭐⭐ | `ops/linear_attention/gated_delta_net/recurrent.cuh:744` | `enter_streaming()` | 每层 GDN，forward 主计算 |
| ⭐ | `ops/kernel/speculative_round.cuh:27 / 48 / 562 / 641 / 962` | `enter()` ×5 | 轮级入口核 |
| （降级） | `ops/candidate_selector/bf16/candidate_selector_path.cu:94 / 120 / 135` | `enter()` ×3 | 在接受路径（S9 实测 accept ≈ 0.01 ms ⇒ 非瓶颈） |

## 6. 附录 B：证据出处与工具索引

**证据出处**：
- 构建史 `docs\ninfer-kvmem-项目构建史.md` §44（PDL 机制确认）/ §45（S7 开关注入）/ S10（基线、半张判决、运行期局限）/ S35（MTP off 杀谷）
- 夜间值守报告 `docs\05-交接与值守\谷攻关-夜间值守报告-20261015.md`（§8.1 半张判决 / §8.2 运行期局限 / §9 null 基线 / §12 相关性+链定位 / §14 深谷捕获 / §15 负载诱发+S12）
- 静态分析（P1-d）：131 调用点分类 + 13 等待点行号（本报告 §5）

**工具**：
- `scripts\pdl_aba.ps1`（重启式 on/off/on 三臂 + 浅/深探针）
- `scripts\pdl_aba_rt.ps1`（运行期 5 相 A-B-A——**受限于"图捕获烘焙"已证无效**）
- `scripts\valley_load_incidence.ps1`（**S12 同窗发生率对照——当前正解**，台账 `.temp\loadinc_*.txt`）
- `scripts\valley_trigger_aba.ps1`（谷窗自动触发）
- 引擎自报：`logs\test_valleywatch.log` 的 `PDL: programmatic`（每窗起服核对 ON/OFF）；`spin-stamp / target-split / verify-split` 打点

**关键台账**：`.temp\pdl_aba_night0110.txt`（半张判决）/ `.temp\pdl_rt_night0120.txt`（运行期无效实证）/ `.temp\incidence_20261015_0227.txt`（4.5h null）/ `.temp\loadinc_20261015_0713.txt`（S12 在跑）

---

## 7. 结论与行动

**三句话**：
1. PDL 凭"纯轮询指纹 + MTP 路径收敛 + 半张因果判决"三项，是谷的最强单一嫌疑，但**因果未闭合**（缺谷窗内完整 ON-OFF-ON）；
2. **关闭 PDL 的收益损失实测 ≈ 0、操作成本 = 一次重启**——所以"若因果坐实，先关 PDL"是零风险决策；
3. S12 同窗发生率对照（~15:40 出判决）是分叉点：**PDL 成立 ⇒ 关 + 修法（§4 ①②③④）；PDL 出局 ⇒ 转 GDN gating 常驻（补丁已备）**。

**行动清单**：
- [ ] 等 S12 完整统计（`.temp\loadinc_20261015_0713.txt` 的 WINDOW 行；ON/OFF 跨 6 对）
- [ ] 若 PDL 因果成立：生产起服脚本加 `NINFER_PDL_OFF=1`（或先做 S12 后的确认单跑）＋ 按 §4 ①②③④ 研究修法
- [ ] 若 PDL 出局：窗间隙构建 `patches\i3b_s11_gdn_residency_occupancy.patch` → 同窗复测
- [ ] 长稳态补测（如某段时间需要 PDL 收益的精确账）：`pdl_aba.ps1` 现成
- [ ] S12 若 8 小时内两臂都抓不到谷 → 改用更长窗（如 2 小时/对）重跑（已列入自迭代触发条件）
