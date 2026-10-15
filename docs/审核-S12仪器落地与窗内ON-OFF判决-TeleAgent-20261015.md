# 审核：S12 仪器落地 + 窗内 ON/OFF 判决（TeleAgent）

- 日期：2026-10-15 23:3x · 审核方：TeleAgent · 性质：独立取证复核（不采信转述）
- 审核对象：CB 第 2 步（S12-internal 引擎打点补丁）落地 + 首次窗内 ON/OFF 判决
- 关联提交：engine-src 补丁（v1 轮转版→v2 固定首末层版）· 归档 `I3b_step12b_opsplitfix_20261015.exe`（sha 85A27EC6）· 主仓 `3074f99`
- 证据日志：`logs\evidence_ON_valley_20261015_2324.log`、`logs\evidence_OFF_healthy_20261015_2325.log`；台账 `gate_A_step11_*` / `gate_B_step12_off_*` / `gate_C_step12_on_*`

## 一、审核范围

1. 补丁实现（槽位 12→20、固定首/末层 op 组、MTP draft 三段、kStepSlots/arm/guard/report 同步）；
2. 三相验收（A=step11 profile off / B=step12b off / C=step12b on+VERBOSE）；
3. 窗内 ON/OFF 判决；
4. 归档与提交（`3074f99` 已推、工作区干净）。

## 二、核验结论（逐条实测）

| 项 | 核验结果 | 判定 |
|---|---|---|
| ON target 205–212 / OFF 28.8–29.1 ms | 日志：`target=208.0/206.4`（ON）vs `28.8/29.1`（OFF） | ✅ |
| 末层 mixer ON 4.2–12.2 / OFF 0.21 ms | 日志：`last mixer=10.22/11.32`（ON）vs `0.21`（OFF），48–54× | ✅ |
| 首层 mixer 不膨胀（恒 0.14） | ON 与 OFF 均 `first mixer=0.14 mlp_tail=0.22`（sum 0.36） | ✅ |
| draft 段 ON 21.6–57.5 / OFF 5.3–5.9 ms | ON `draft-split sum=41.75/28.86`；OFF `sum=5.91/5.25` | ✅ |
| 三臂 sha 逐字同 | `gate_A_step11_*`/`B_step12_off_*`/`C_step12_on_*` 全 = `f1626c594a78a9ce` | ✅ |
| PDL DISABLED 自报 | `evidence_OFF`：`PDL … DISABLED (NINFER_PDL_OFF=1)`；ON 报 `ENABLED` | ✅ |
| step12b 归档 + 提交 | `I3a_…exe` sha 85A27EC6 + MANIFEST 记 `slots 12->20`；提交已推 | ✅ |
| v1 轮转→拓扑崩 | C 相起服：`cudaGraphExecUpdateFailure result 2`（TopologyChanged） | ✅（自检门抓到真实缺陷） |

**结论：CB 报告的判决数字与工程事实全部属实，零行为门（sha 逐字同）与 PDL 自检核验均过。** 本轮是死亡谷攻关至今第一次"窗内 + 双向 + 逐字同 + 自报核验"的完整对照，方向强烈指向 C1（PDL 依赖自旋）。

## 三、放行前必须如实标注的三点

**① "病变遍布全层"是推断，不是实测。** 补丁只采**首/末两层**；末层 mixer 10.2 ms 仅占 208 ms target 的 ~5%，其余 ~197 ms 在未采样的 ~26 层里。CB 写"28 层若普遍如此≈+190 ms"系两样本外推——且与"首层不膨胀"存在张力（若全层普遍膨胀，首层也应慢）。**该条须从"已测"降格为"推断（两样本外推）"。**

**②【窗口混淆未关】单次 ON→OFF 是强证据，但"坐实 C1"还差一步。**"窗口"只能靠探针自身观测；OFF 臂在 23:25 健康，无法独立证明它仍在窗口内——存在"OFF 恰逢机器态离窗"（非 PDL 之功）的可能。CB 用"重启不复现"推翻重启混淆成立，但**未排除"离窗"**。**要关死 = Option 1（同窗回切 PDL ON）：若 ON 复慢、OFF 复快、来回可复现，才把"开关"与"时刻"分开。**

**③【方案文档漂移】`docs\方案-死亡谷处置-20261015.md` 仍为 v4.2/4.3 的旧设计**：轮转采样＋`step_stamp_note_layer`＋槽 12/13/14＋"12→17 槽"。实际实现为**固定首/末层、槽 12–19（12→20）、note_layer 已删**。照方案读会造错件，**需 v4.4 同步一次**（连同"6 处→实际 8 槽"）。

## 四、认可点

- 仪器按方案落地且工作（新印行 `layer-ops`/`draft-split` 出现，开销由零行为门把关）；
- 观察者自检门**实际抓到并暴露**了 v1 轮转设计的拓扑缺陷（验证了该门禁的价值）；
- 协议性正确：同机器、相邻分钟、同二进制、同探针、sha 逐字同，PDL 自报核验到位。

## 五、选项裁定（建议）

**先做 1 且做透**：ON/OFF 各再跑一轮（ON→OFF→ON 快速回切），关死窗口混淆（≈5 min，价值=判决从"一次对照"升级为"开关可复现"）。
- ON 复慢、OFF 复快 ⇒ C1 方向实锤；随后做 3 拿长效缓解证据。
- ON 不再慢（离窗）⇒ 本次降级为"疑似"，等下次谷窗。

选项 2（扩采样层）后做——正是为收拢①的外推；选项 3 等 1 定论后挂。

## 六、放行前置

- 写补丁：无阻塞（kStepSlots 同步已在实现中落实）；
- 判 C1 坐实前：须完成 §三② 的回切复现；
- 文档：补 v4.4 同步实现（固定首末层、槽 12–20、删 note_layer、补"打点须保持每次 capture 节点数恒定"约束）。

## 七、证据引用

- 日志（打点读数）：`logs\evidence_ON_valley_20261015_2324.log`、`logs\evidence_OFF_healthy_20261015_2325.log`
- 台账（sha）：`.temp\gate_A_step11_*.json`、`.temp\gate_B_step12_off_*.json`、`.temp\gate_C_step12_on_*.json`
- 构建史：`docs\ninfer-kvmem-项目构建史.md` §57；夜报告 `docs\谷攻关-夜间值守报告-20261015.md` §23
- 提交：`3074f99`（已推）；引擎件 `I3b_step12b_opsplitfix_20261015.exe`（sha256 85A27EC6…）

## 附：机器态

审核期间未动机器；OFF 臂仍在跑（PID 22232，23:24:41 起）。一切进一步动作（回切/继续守望）由用户裁。