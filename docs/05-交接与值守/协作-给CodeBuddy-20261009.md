# 给 CodeBuddy 的协作对接文档 · ninfer-kvmem

> **致**：CodeBuddy（IDE 环境）｜**发**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-09
> **背景**：用户已把本线主工作区迁到 `J:\ninfer-kvmem`，并会在此工作区**同时唤起你与我**共同开发。这份文档让你快速对齐：这是什么项目、现有资产、卡在哪、怎么协作。
> **用户分工制**：**哪边写代码由用户逐案决策**（不预设固定分工）；两侧接到任务直接执行，不比对该谁做。本文只提供事实与协作纪律，不替用户分派。

---

## 一、项目目标

把新模型 **`Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`** 搬进 **NInfer + KVMem** 架构跑起来，并把已封存的前序线（`J:\Bonsai-Official`）**全部能力**尽量适配到它身上：

> **NInfer 核心解码（最快）＋ KVMem 长上下文（KV 卸主机内存、腾显存）＋ 三种投机解码（MTP / DFlash2 / ngram）**

单开本线的目的 = **不污染**已可复现、已封存的 `J:\Bonsai-Official`。

---

## 二、工作区资产盘点（`J:\ninfer-kvmem`）

| 路径 | 是什么 | 入库？ |
|---|---|---|
| `ninfer_launcher.py` / `启动器.bat` / `serve_tee.py` | 启动器、入口、日志中转（从 Bonsai 线迁来，**待适配 Coder390**） | ✅ |
| `ninfer_launcher_profiles.json` / `start-*.bat`（4 个） | 档位与部署脚本（**现写的是 Bonsai 模型名与旧路径，待改**） | ✅ |
| `build\` | 自编引擎复现材料（构建脚本 + 3 枚引擎补丁 + 产物清单） | ✅ |
| `docs\` | 教程、ngram 审计、**本交接文档** | ✅ |
| `official-repo\ninfer-fusion-kvmem\` | 融合仓全库（源码树 docs / patches / tools / verify / src-tree） | ❌（输入物料） |
| `engine\` | 自编引擎 `self-built-20261008\`（4.68 GB）+ 官方对照件（~1.9 GB） | ❌ |
| `models\` | Coder390 `.ninfer`（12.36 GB） | ❌ |
| `refs\` | 参考资料区（沈三殊发放包 / 技术论文 / 两条前序线文档） | ❌（第三方输入） |
| `_safety_backups\` | 备份（含引擎源码 bundle） | ❌ |

> 分类原则（工具三分法）：①产品代码 ②项目工具 ③AI 工作流工具链——**③类永不入库**；`refs\`、`official-repo\`、`engine\`、`models\` 属**输入物料**，不入库。

---

## 三、现状与卡点（已取证）

| 目标 | 结果 | 根因（原文） |
|---|---|---|
| 裸解码 | ✅ 通（~52 tok/s 量级） | — |
| MTP 投机 | ❌ | `weight/000789: unknown tensor format: gguf_q4_0`（MTP 头 5 张量是 `gguf_q4_0`，引擎白名单无 Q4_0） |
| DFlash2 投机 | ❌ | `Qwen3.5 config: missing component dflash2`（包内无 dflash2 组件） |
| DFlash(v1) | ❌ | `missing component dflash` |
| ngram（`--ngram-draft-tokens`） | ❌ | `ngram requires --spec mtp\|dflash\|dflash2`（需先通 MTP/DFlash2） |
| `--lookup-ngram` | ⚠️ 启动但空转 | A/B 实测 52.9 vs 51.9 tok/s，无差异 |

**关键事实**：该 `.ninfer` 容器 = `NINFER\0\3`、`Qwen3_5ForCausalLM`、64 层/hidden 5120/vocab 248320/max_pos 262144；组件**只有 `text` + `mtp`**；`text` 787 权重**零 q4_0**，**5 个 q4_0 全在 MTP**。
**引擎能力**：`formats.cpp` 支持 `gguf_blocks_v1`（含 q2_k…q8_0，**无 q4_0**）；`ggml_bridge.h` 的 `GgmlType` **无 Q4_0**；`--spec mtp|dflash|dflash2`。
**容器可重写**：`reader.cpp` 无内容校验（offset16 = artifact id 非哈希；payload 对齐 4096）⇒ 数据侧重打包安全。

**攻法**（详见 `docs\05-交接与值守\交接-工作区迁移-TeleAgent-20261009.md` §3.2）：MTP 有"引擎补 q4_0（重编）"与"数据侧重存 q4_0→bf16/q4_k（不重编）"两路；DFlash2 需另找草稿件注入（最不确定）；ngram 随后。

---

## 四、协作机制与纪律

1. **写代码由用户逐案决策**；两侧直接执行、不比该谁做；我（TELE）不做无授权改动。
2. **提交纪律（T-COMMIT-APPROVAL）**：任何 commit 前须把**完整 message + 文件清单 + diff** 交用户、做定性说明 + 提交建议、**停在等批准**；未获明确同意禁止 `commit`/`push`。**git 只收产品本身**（不当日记本）。
3. **推送**走 `smart_push.ps1`，**禁裸 `git push`**。
4. **T-PROTECT-ASSET**：`models\`、`engine\` 等 `.gitignore` 排除的 >1G 资产**禁止同树删除/移动**。
5. **T-EVIDENCE**：结论带 `[EVIDENCE] 文件:行:原文`；`T-NO-TEMP-WORK`：产物落正式目录。
6. **质疑精神（用户严令）**：对彼此方案/报告**默认先找反例**，不做应声虫、不当彼此影子；审查≠背书。
7. **两边共享**同一套铁律/门禁/记忆库；**内容不一致时停止操作并报告差异**，同步须经用户授权。

---

## 五、建议的起步动作（供两侧与用户参考，非分派）

1. **路径/模型适配**：把 `start-*.bat`、`ninfer_launcher_profiles.json`、启动器默认模型从 Bonsai 名改为 Coder390 名与 `J:\ninfer-kvmem` 路径。
2. **MTP 路 B 探针**：对 MTP 5 张量做反量化重存 + 重打包的可行性探针（先证明能起 MTP、拿读数）。
3. **DFlash2**：核实主仓 `DFlash2-FP8/` 或 NVFP4-Infer 仓是否有可用的 `.ninfer` 草稿件，参考沈三殊"自造 dflash2 注入件"做法（`refs\01-沈三殊-发放包\新\急速档V2\`）。
4. **每次有结论**：带证据落盘（报告进 `docs\`），并按需更新本线文档。

---

## 六、待决（请用户裁决）

- 本线 **git 基线 commit** 是否现在提交、纳入哪些文件（现暂存 36 文件 + 新交接文档）。
- `refs\` 是否保持"仅本地参考、不入库"（我的建议：保持不入库，作为第三方输入物料）。
- 三条投机的**优先级**与**是否允许重编引擎**（路 A vs 数据侧路 B）——影响工作量与风险。

> 有疑问先停、先取证；两侧交叉纠错 > 互相盖章。
