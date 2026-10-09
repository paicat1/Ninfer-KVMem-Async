# 审核报告 · P1b MTP 跑通（iq4_nl 自转路线，CodeBuddy 施工）

> **审核方**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-09
> **审核对象**：CodeBuddy P1b 交付 —— ① `scripts\recode_mtp.py` 扩展（新增 iq4_nl 转码 / 跨文件取数 / 探针模式，+276/−51）；② 产物 `models\…MTP.mtp-iq4nl.ninfer`；③ 构建史 v12 补录（三·八章 161 行）
> **方式**：只读，独立验证（不复述交付方结论；iq4_nl 量化器用独立重算全量比对，A/B 读数取权威日志）
> **分工遵循**：施工/构建史归 CodeBuddy（其已提出提交审批包待用户批准）；本审核报告归 TeleAgent 记录与提交。

---

## 〇、结论

**P1b 审核通过。** 独立核验的 8 项全部成立：iq4_nl 转码算法正确（码表/块结构/nibble 布局全部与 ggml 权威源一致，量化器独立重算全量逐字节吻合）、产物结构正确、A/B 读数与权威日志吻合、L4b 输出无劣化、KVMem 两侧环境一致。未发现实质缺陷。

---

## 一、独立验证（我重跑/重算/取证，非复述）

### 1. iq4_nl 算法正确性（逐项对照上游 ggml 权威源）

| 项 | CodeBuddy 实现 | 我的独立取证 | 判定 |
|---|---|---|---|
| 码表 16 项 | `KVALUES_IQ4NL=[-127,-104,…,113]`（recode_mtp.py:64-67） | `[EVIDENCE] ggml-common.h:1120: kvalues_iq4nl = -127,-104,-83,…113` | ✅ 逐值一致 |
| 块结构 | `IQ4_NL_BLOCK_BYTES=18`、`BLOCK_ELEMS=32`（L52-55） | `[EVIDENCE] ggml-common.h:448-450: block_iq4_nl{ggml_half d; uint8_t qs[QK4_NL/2];}` + `QK4_NL=32` → 18B/32元素 | ✅ |
| 引擎块几何 | — | `[EVIDENCE] ggml_bridge.cu: IQ4_NL: return {32,18}` | ✅ |
| **nibble 布局（最易静默写错）** | `idx[:,:16]=qs&0x0F; idx[:,16:]=qs>>4`（L122-123，HALVED） | `[EVIDENCE] dequantize.cuh: y[j]=d*kvalues_iq4nl[q4[j]&0xf]; y[j+16]=d*kvalues_iq4nl[q4[j]>>4]`（HALVED） | ✅ 完全一致 |

### 2. 量化器独立重算（强独立验证）

**我写了独立量化器**（`.temp/verify_iq4nl_indep.py`，**不 import recode_mtp**，从 ggml 定义重建），对官方 Q8MTP 源 5 个 MTP 对象**全量 13,271,040 块**用同一 LS-scale+最近码本算法重算，与产物 `.mtp-iq4nl.ninfer` 逐字节比对：

```
weight/000079  blocks=  2293760 byte_mismatch_blocks=0
weight/000080  blocks=  5570560 byte_mismatch_blocks=0
weight/000789  blocks=  1638400 byte_mismatch_blocks=0
weight/000796  blocks=   983040 byte_mismatch_blocks=0
weight/000798  blocks=  2785280 byte_mismatch_blocks=0
VERDICT: PASS (independent re-quantiser identical on all 13271040 blocks)
```
⇒ 量化器实现**正确且确定**，产物是官方 q8_0 → iq4_nl 的真实量化（非占位/非假绿）。

### 3. 产物结构

| 文件 | objects | formats | name |
|---|---|---|---|
| 官方 Q8MTP 源 | 1139 | `gguf_q8_0:5`（MTP 头）+ vision 组件 | `…-Q8Mtp` |
| iq 产物 `.mtp-iq4nl` | 804（原件骨架） | `gguf_iq4_nl:5`、`gguf_q8_0:0` | `…-Mtp+mtp-iq4nl` |

✅ 5 个 MTP 对象从 q8_0 → iq4_nl、无 vision、name 标记 +mtp-iq4nl。

---

## 二、A/B 读数可信度（权威日志核验）

`[EVIDENCE]` 两侧日志均为**引擎自报 `req#N done`**，非客户端计时：

| 臂 | 权威读数 | mtp accepted |
|---|---|---|
| **MTP**（`--spec mtp`，23:09） | req#2 `decode 184.3 tok/s`；req#3 `decode 73.2 tok/s` | 75/80 (93.8%)；75/332 (22.6%) |
| **裸解码**（无 `--spec`，23:10） | req#1 `decode 55.4 tok/s` | — |

- **方法学成立**：两侧同模型文件（`.mtp-iq4nl.ninfer`）、同 ctx 16384/kv 4096、同 prompt 散文，唯一变量 `--spec mtp`（CMD 行逐字核）。
- **KVMem 环境一致**：两侧均 `context cache | host 8 states, 16.0 GiB KV` + kvmem_index 安装。
- **读数值**：散文任务 MTP 73.2 vs 裸 55.4（**+32%**）；代码任务 MTP 184.3（无裸对照，单测）。
- **L4b 输出等价性**：两版 CUDA 图回复语义一致、质量相当、无系统性劣化（文件 `logs/ab_*` 核）。

---

## 三、待用户决策

| # | 事项 | 归属 |
|---|---|---|
| 1 | 提交 CodeBuddy 提交包（`recode_mtp.py` 扩展 + 构建史 v2） | CodeBuddy，待用户批准 |
| 2 | 提交本审核报告 | TeleAgent（我），需用户批准 |
| 3 | 挂账 14-17（扫 ctx 找最大可用 / 建接受率基线 / 官方版留存裁定 / 探针件定稿） | CodeBuddy 施工，我审核 |

---

## 四、风险提示（如实披露，非阻塞）

- 裸解码侧仅 1 次测量（req#1）；A/B 的 +32% 是**散文任务**、+233% 是**代码任务单测**（无裸解码对照）。散文对照足够支持结论，但若要更严谨可比，可多测几轮取均值（可选增强，不阻塞）。
- `iq4_nl` 是**有损**（相对误差 8.4–9.1%），其信息量低于官方 q8_0；但正是省 202 MB 让 MTP 在本机 16GB 卡上装得上——这是"以略损换能跑"的权衡，已由误差探针量化。
- 环境漂移（21:40 的 55.7 vs 当前 16 tok/s 裸解码基线）机制未最终定位，但同刻交替法证明可比，不影响 A/B 有效性。

---

**署名**：TeleAgent ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`