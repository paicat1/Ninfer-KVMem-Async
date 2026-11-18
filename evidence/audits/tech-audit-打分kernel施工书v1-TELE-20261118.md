# 技术审核 · 打分 kernel 优化施工书 v1（C7 步）

- 审核人：TELE · 2026-11-18
- 审核对象：`docs\03-归因与结论\施工-打分kernel优化-施工书-CB-20261118.md`（90 行九节）
- 证据源：`engine-src\src-tree\fusion-engine-src\src\ops\kvmem\kvmem_retrieve_launch.cu`（304 行全文）、`kvmem_score.h`（L1-80 / L380-489）、§242（`docs\ninfer-kvmem-项目构建史.md:7464` 起）
- **总判定：退回重做**（4 项阻断 + 4 项须补；方向与证据基础确认成立）

## 一、已证实项（施工书与源码/数据吻合）

| 施工书声称 | 实测 | 证据 |
|---|---|---|
| 两趟点积、2x dominant term | ✓ phase1 与 phase2 各一次 `dot_q_sum`；头注释自陈 "two dot products per (block, head) … 2x cost on the dominant term" | kvmem_retrieve_launch.cu:20-23,179,239 |
| 2,432 = 152 chunk × 16 层 per-layer launch | ✓ 调用侧 `cfg.n_layers=1` 逐层；**全树唯一调用点 = kvmem_score.h:446**（kvmem_retrieve.cpp 仅薄包装） | kvmem_score.h:424,446 |
| head_w=1/(总层×H) 补偿 16 次累加 | ✓ 用 `n_layers_total` 归一，注释与实现一致 | kvmem_retrieve_launch.cu:271-277 |
| grid_x = layers × q_tokens 公式现成 | ✓ kernel 已支持多层 grid | kvmem_retrieve_launch.cu:267-268 |
| 现役无 logits 共享缓存 | ✓ 现役 dynamic shmem = 2×4×24 = **192 B**（仅 stats）；"64KiB opt-in"只是头注释假想上界 | kvmem_retrieve_launch.cu:278;15-18 |
| mask/incl 早退是正确性特性 | ✓ | kvmem_retrieve_launch.cu:262-266 |
| 打分是产品路径成本（非纯仪器） | ✓ `kvmem_score_enabled()` 三态：`NINFER_KV_WINDOW>0` 即默认开；语义档装窗依赖该 score | kvmem_score.h:58-80,472-474 |
| §一证据表数字 | ✓ 455.5s/2432=187.3ms；0.48 TFLOPS=90 MFLOP/187ms；4096×4B=16KB | 构建史:7464 |

## 二、阻断缺陷（退回理由）

### B1 刀1 的 `s_logits[n_blocks]` 结构算术不成立（缺 head 维度）
- phase2 按 (block, head) 逐对重算点积（kvmem_retrieve_launch.cu:228-241）。要"第二趟不再重算"，缓存必须覆盖本块处理的**全部 (b,h) 对**：容量 = n_blocks × n_heads × 4B = 4096×24×4B = **384 KiB**（施工书 §四.1 写"容量=n_blocks"→16KB，**少乘 heads=24**）。
- 48KB 默认上限装不下，消费卡 opt-in（~99-132KB/块）也装不下 ⇒ 照施工书施工 = launch 直接失败或静默退化。
- 可行变体：①**per-head 内层一趟**（每 head 缓存 logit[b]，16KB 可行）——但 phase2 现设计"每 (b,layer,token) 1 次 atomicAdd"（:219-221 有意为之，省 24× atomic）会膨胀 24×（~3.67M → ~88M/launch）；②**分组缓存**（48KB→G=3 heads / opt-in→G=6），atomic 膨胀 ⌈24/G⌉ 倍。
- ⇒ 两个变体都有 atomic 膨胀代价，可能吃掉点积节省。**结构定案+微基准实测（点积占比、atomic 开销）之前，"收益 ≈ -40%"与"召回风险为零"（禁定性词，且 N6 的存在本身承认数值顺序可动 top-k 边界）均不可给。**
- 附：dot 实现为逐元素标量循环（:78-103，无 float4/bf16x2 向量化、无多累加器 ILP）——187ms 对 ~50M MAC/launch 是深延迟束缚形态；**"向量化/ILP 改造（不动两趟结构、零语义变化）"可能比一趟化收益更大且召回风险真为零**，施工书完全未评估，应作为微基准阶段的第一对比臂。

### B2 判据与选型预期互相矛盾（阶段验收必挂）
- N1 ≤228s ⇔ 单次 93.7ms ⇔ **-50.0% 整**（455.5→228，零裕度）。刀1 理论上限 = -50%（两趟对称且 dot=100% 时间占比），现实 -40~45%。
- 施工书 §三 自预期刀1 ≈ -40%（→112ms/273s），§八 阶段1 验收却用 N1/N3 ⇒ **按自家预期必挂**。N1/N2/N3 是"两刀叠加最佳情况"的线，不是刀1 单独的线。
- 预注册判据测前必须自洽，否则验收时"判据失败但工程成功"或被迫中途改判据，两者都违反预注册纪律。

### B3 刀2 的 -10~20% 无机制，且缺数据布局方案
- §一自家证据："kernel 总时 526.4s ≈ 填充墙钟 ⇒ 无大段 GPU 空闲"——**GPU 无空闲时，launch 合并（省 15 次 launch/调度 ≈ 百 μs 级）省不出墙钟时间**；-10~20% 无从产生。
- 数据布局：逐层 launch 发生在各层 forward 内部，q 是逐层覆盖的暂存张量（.cu:26-27 "only one qn is alive at a time"）；合并到 chunk 末需缓存 16 层 q（896tok×24h×256d×2B×16 ≈ **176MB VRAM**+拷贝）或改变 issue 时序——施工书未提。
- ⇒ 刀2 应降级为"待论证项"（给出定量机制）或从本步剔除。

### B4 标语"8min→3.3min"超物理上限
- fill ≈ 非打分 GPU 时 70.9s（526.4−455.5）+ 打分总时 X（GPU busy≈wall，§一自证）。
- X=228s（N1 过线）⇒ fill ≈ **299s ≈ 5.0min**；X 按"90-110ms×2432"⇒ fill 290-338s（4.8-5.6min）。
- 198s（3.3min）需 X≈127s（单次 52ms，-72%）——刀1+刀2 达不到，那是刀3（剪枝）/刀4（增量）的量级。标语必须改与 N2 自洽。

## 三、须补项

- **B5（高）数值 oracle 判据缺失**：两趟结构本身是 verifier 分离统计/累加的手段（:26-27 自陈，两个 mean-K bug 靠它发现）；消掉它必须补独立 oracle 判据（FP64 参考/逐元素相对误差线）。N6 只是排序重合代理。源码树 AGENTS.md 数值变更契约（CUDA mathematics → independent oracle）同此要求。
- **B6（高）路径未钉死**：仓内同名副本 ≥3 处（`official-repo\ninfer-fusion-kvmem`、`work\publish-wt-20261114_093158`、`refs\01-沈三殊-发放包`×2，grep 命中）；施工书通篇裸文件名。必须绝对路径钉死在役树 `J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src\src\ops\kvmem\` 并显式禁触其余副本；九节 Scope"2 文件"与 §三 3 文件不符（实际触及 = launch.cu + kvmem_score.h；retrieve.cpp 可不动）。
- **B7（中）参考出处悬空**：`qwen_executor.cpp:23750-23753` 与 `kernels_cuda.cu:5340-5435` **全仓不存在**（glob 证实，上游树引用）；one-dot 只能按头注释描述自写，v2 应改引注并声明。
- **B8（中）执行细节**：N6 取证工具未定义（新旧 kernel top-k 集合抓取与固定输入钉法）；回滚备份清单缺 kvmem_score.h；微基准的 GPU 占用与在役引擎共存/服务窗口纪律未写。

## 四、亮点确认

- 靶子选对：打分 kernel 占 GPU busy 86.5% 是 nsys 实测；两趟 2x 是源码自陈事实。
- 证据表九行与源码/数据逐条吻合（§一表）。
- 禁则七条方向正确（不改候选集/head_w/mask、不硬编码 16384、单刀验收——与源码自述的坑一一对应）。
- 回滚链三层（backup_file 台账 + 双副本二进制 + 单 commit revert）设计合格。
- J4 召回硬门槛前置。

## 五、v2 重做清单（退回条件）

1. 刀1 结构定案（per-head/分组一趟 + atomic 膨胀权衡表），微基准第一臂先测"向量化/ILP（不动两趟）"，用实测数据定判据线。
2. 判据分刀拆线：阶段线（刀1 solo）与终线（合并）各自自洽；N2 只保留为终线。
3. 标语改"~5min 量级（刀1+刀2 达满上限时）；3.3min 需刀3/刀4"。
4. 绝对路径钉死 + Scope 文件清单改准 + 显式禁触其余副本。
5. 补 N6b 数值 oracle 判据。
6. 备份清单对齐实际触及集；微基准窗口纪律写入执行方案。

## 附录：关键证据行号

- 两趟点积：kvmem_retrieve_launch.cu:20-23（自陈）、:179（phase1 dot）、:239（phase2 dot）
- deliberate trade 与 mean-K bug 史：:24-31
- single-atomic 设计：:219-221（注释）、:242-243（实现）
- head_w 归一：:271-277；grid 公式：:267-268；现役 shmem：:278
- mask 早退：:262-266；标量 dot 循环：:78-103
- 调用侧：kvmem_score.h:424（n_layers=1）、:441-454（segment 循环）、:446（唯一调用点）
- 三态开关与产品路径：kvmem_score.h:56-80；语义档依赖：:472-474
- §242 数字基线：docs\ninfer-kvmem-项目构建史.md:7464
