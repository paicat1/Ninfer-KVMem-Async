# 判定：异步 OFF 臂输出退化分叉源头 + XTier 节奏器天花板算术（TELE，2026-10-26）

> 执行者：TeleAgent（零机时读码 + 台账数字，无任何新实验、无引擎点火）
> 判定对象：挂账 #53（分叉源头）、#54（适用域，部分）、#56（天花板算术）；#57 被 log_verify 门拦住（见 §五）
> 证据基线：engine-src\src-tree\fusion-engine-src\ 源码 + `.temp\async_abab_20261025_202705.txt` 台账（§164 已入库数字）+ ledger44 结论

---

## 一、#53 判定结论（分叉源头）

**总体结论：OFF 臂输出退化的"KV 数据损坏"解释未找到任何机制支撑；全部证据一致指向"FP 求和序/调度差异"家族（良性——两臂各自计算正确，只是调度不同导致归约序不同，文本从首个分叉 token 起分流）；OFF 臂的死循环复读 = 分叉后文本落入贪婪解码复读盆地（长上下文贪婪解码的吸引子效应），不是数据损坏的直接证据。**

### 1.1 已实锤：三道守卫 + 同步拷贝语义（数据损坏候选逐一定性排除）

**守卫①：陈旧 host 副本不可 drop（epoch 守卫）**
- [EVIDENCE] kv_store.h:577-583: `can_drop_device_replica` 要求 `host_replica_current(handle)`（host 副本 `content_epoch` 与 `committed_columns` 与当前页完全一致）才允许 drop
- [EVIDENCE] context.cpp:2392-2397: "Already preserved on the Host (demoted before and then retrieved): no transfer needed" 快速路径在 `host_replica_current` 为假时 `continue`（宁可不 demote 也不丢数据）
- ⇒ "host 副本过期仍被当成最新" 这条损坏路被构造性堵死

**守卫②：同步臂 D2H 无"在途拷贝 vs 槽位复用"竞态窗口**
- sync 路径 D2H 落在计算流：[EVIDENCE] context.cpp:2321-2323: "// Copy on the compute stream so the D2H is ordered after the kernels that wrote it." + `copy_to_host(sources, ..., device.stream)`（context.cpp:2322-2323）
- 宿主侧是可分页 staged 拷贝：[EVIDENCE] paged_kv_cache.cpp:758-759: `cudaMemcpy2DAsync(host_ptr, host_pitch, device_ptr, device_pitch, width, count, cudaMemcpyDeviceToHost, stream)`；[EVIDENCE] arena.cu:632: "so it is charged to system RAM only. The cost is that cudaMemcpy to and from it is staged"
- CUDA 语义：async API 对可分页宿主内存退化为阻塞式 staged 拷贝；实测印证——[EVIDENCE] test_abab_off_c1.log demote profile 行: "copy=2.68 publish=0.00 tail=0.00"（宿主线程在 copy_to_host 内等待 2.68ms；若为纯异步入队该值应≈微秒）
- ⇒ copy 返回时传输已完成，publish/drop 之前数据已落地；retrieve（H2D）虽走 transfer_streams（[EVIDENCE] materialization.cpp:1149-1152），但目标槽位释放时源数据已无在途读取者，跨流竞态不成立

**守卫③：两臂均为纯字节拷贝，无数值变换**
- sync：[EVIDENCE] context.cpp:2320-2344（device_sources → copy_to_host → publish → drop_device_replica，无格式/精度变换）
- async：[EVIDENCE] context.cpp:2289-2318（同一拷贝，仅改 transfer_streams + 环形槽位，retire 在 fence 完成后才 publish/drop：context.cpp:2148-2174）
- restore 发布同样受 epoch 守卫：[EVIDENCE] kv_store.h:541-551（`publish_device_replica` 要求 host 副本 epoch/列数匹配，否则 throw）

### 1.2 判定成立的机制（FP/调度家族）

两臂唯一差异 = demote 的流与时机（sync=计算流内联阻塞 vs async=传输流+延后 retire）。数据逐字节相同 ⇒ 分歧必然来自**调度侧**：
1. **物理槽位布局历史不同**：两臂释放/复用槽位的时刻不同 → 新页落入不同物理槽 → 若任何内核的归约序与物理布局相关（attention gather 分组 / MTP verify 批次形态 / CUDA Graph 拓扑），FP 求和序改变 → 首个分叉 token 后文本分流。
2. **速度差全机械解释**：OFF 臂每次 8 页批次的阻塞式 D2H 占据计算流（ledger44 定案的真凶，慢峰 3.4-7.8ms/批），decode 内核排队等待；ON 臂拷贝在传输流下与计算重叠。**2 倍速度 = 纯调度收益，与数值正确性无关。**
3. **复读盆地**：分叉后 OFF 臂 token 流进入重复区域，贪婪解码对重复具有自我放大性（上下文含重复段→更倾向续写重复→滚雪球），dup8=47.5%/max8=378 与"吸引子"图景一致；ON 臂从未落入。两臂各自跨重启逐字一致（台账 L14-15 vs L45-46：OFF sha 恒 `81749d21`/`2e13dd9c`；ON 恒 `35bbafa0`/`7b7e6eda`）——每个臂的（布局,调度）演化确定 ⇒ 输出确定，符合调度家族、不符随机竞态。

### 1.3 未闭合环节（如实声明，不影响主判定方向）

1. **归约序调度敏感性未静态验证**（下一个零机时读码点：attention gather / MTP verify / graph 捕获拓扑）——它解释"为什么两臂文本必不同"；本判定已证明的是"不是数据损坏"，尚差"差异确切源头内核"。
2. **分叉点 diff 无材料**（挂账 #55：输出全文未落盘，gate json 只有 sha+len）——两臂首个分叉 token 位置未知。
3. **单样本统计局限**：每臂仅 2 cycle（逐字一致），"良性雪崩恰好落入复读盆地"无法统计排除恶性小概率——但恶性说已无机制支撑，举证责任反转。

### 1.4 推论（待 1.3-① 闭合后可正式翻案）

若 FP/调度家族成立：**无损门失败（跨臂 sha 不同）= 调度敏感性的体现，而非"异步算错"**；两臂各自算术正确；"2 倍速度"可以恢复为"真实收益"引用（口径仍受 r3 超时破例限制）。

---

## 二、#54 简判（sym3/offi 适用域，部分完成）

demote/staging/restore 机器为本 src-tree 同源代码（context.cpp/kv_store.h/materialization.cpp），sym3/offi 与 S13 系共享同一同步路径与同一套守卫；源码层无 build 特化分叉机制。定性预期：同族行为（同步路径深超池=慢+潜在复读风险）。
**边界**：①sym3/offi 的实测退化文本未测（零机时冻结中）；②本判定本身尚有 §1.3-① 未闭合环节。适用域表述维持：**"OFF 臂退化发现仅成立于 S13 系件+152K 超池+贪婪"** 不变。

---

## 三、#56 天花板算术（XTier 节奏器）

**输入来源声明**：台账 `.temp\async_abab_20261025_202705.txt`（§164 已入库数字）+ ledger44 常数（构建史 L1484：慢峰 3.4-7.8ms/批）。未读引擎日志正文（门问题见 §五）。

| 项 | 数值 | 来源 |
|---|---|---|
| ON 臂 decode-only 时长 | r1: 8321/53.1=156.7s；r2: 8434/54.4=155.0s；**合计 311.7s** | 台账 L24-25 |
| 点火计数（保守上界） | **994**（台账 logstat=全部 demote profile 行，含 retire 行） | 台账 L29/L40 |
| ledger44 慢峰上界 | 7.8ms/批（每批 8 页） | 构建史 L1484 |
| **最大可省** | 994 × 7.8ms = **7.75s**（把每一行都当成慢峰同步批的夸张上界） | 本判定算术 |
| **占比** | 7.75 / 311.7 = **2.49%** | 本判定算术 |
| 精化下界 | 真正可省的仅是 ON 臂残余 sync flush 批（批次行 625 = off_c1 实测同型计数，其中还含非阻塞 submit）× 7.8ms = 4.9s → **1.6%** | 本判定算术 |

**结论：2.49%（夸张上界）< 5%，精化口径 ≈1.6%。按预登记决策规则（>5% 才装极简节奏器）⇒ 不装，异步保持现状。** 节奏器议题关闭，理由：ON 臂残余同步 D2H 开销不足 decode 时长的 2.5%，节奏器复杂度无回报。

**计数口径对账**（供复核）：§164"点火 OFF 584/624 vs ON 994/994"= 台账 logstat 的 demote_profile 计数 = 全部 `[ninfer] demote profile` 行。TELE 复数（Select-String）：off_c1 `demote profile: batch=`=584 ✓（OFF 无 retire 行，两口径重合）；on_c1 batch 行=625，625+369（retire/其他）=994 ✓ 完全对账。

---

## 四、本轮方法声明

- 零机时：无引擎点火、无新实验、无 GPU 占用。
- 读码范围：context.cpp（demote 机器全函数）、kv_store.h（页状态机）、materialization.cpp（流归属 grep）、paged_kv_cache.cpp/arena.cu（拷贝语义）。
- 未动 git；两份文件改动（本文档 + 构建史 §166/挂账行）待用户审后随下一批 commit 入库。

## 五、#57 状态：被 log_verify 门拦住，等用户裁定

```
[LOG_VERIFY] verdict=FAIL_ANOMALY file=test_abab_off_c2.log size=2341.2KB age=4577s mtime=2026-10-25 23:50:20
[LOG_VERIFY] tail: 2026-10-25 22:31:57.848  INFO  req#3 done | openai-chat | cancelled | prompt 228,024 | output 0 | ... | total 15m 0.5s
```

TELE 事实层读法（供裁定，非结论）：尾行 = r3 请求在 a2gate 900s 上限被取消（prompt 228,024 / output 0 / total 15m）——与 §164"r3 四臂全部工具超时"预记录一致，属已知收尾形态，非数据损坏迹象。**按 T-LOG-VERIFY，AI 不得自行判"可采信"，等用户裁定**：回"继续"= 采信并跑 10-21 四份日志（test_async_on/off.log、test_q2_on/off.log）点火计数；回"跳过验证直接看"= 同前；或先不查。
