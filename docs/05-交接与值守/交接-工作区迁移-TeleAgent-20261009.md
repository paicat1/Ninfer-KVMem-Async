# 工作区迁移交接 · TeleAgent（星辰超级智能体）

> **署名**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-09
> **收件人**：我（TeleAgent）在本工作区 `J:\ninfer-kvmem` 的后续会话
> **一句话**：我原来的工作区是 `J:\Bonsai-Official`（Bonsai 线，已封存只读）；**从今天起，我的主工作区迁到这里 `J:\ninfer-kvmem`**。这份文档是给"过去以后可能忘事的我"留的路标。

---

## §0 我现在站在哪（先看这条）

- **本会话（旧）的工作区 / 当前目录 = `J:\Bonsai-Official`**（Bonsai 线，**已封存、只读参照**，不再改动）。
  ⚠️ 我此前是拿**绝对路径**往新目录写文件——**"写文件的路径" ≠ "我的工作区"**，这是最容易犯的混淆。
- **目标工作区（迁移目的地）= `J:\ninfer-kvmem`**（本文档所在）。**工作区切换由用户执行**：用户把本 AI 切到该目录后，我才是"在那里工作"。
- **新私库现状 = 尚未建立**：本线定位为**全新、独立的私库**，与 `paicat1/Bonsai-27B-NInfer`、`paicat1/Bonsai-27B-NInfer-kvmem`、`paicat1/LiveAvatar-docs` **彻底分开**（历史不混、远端不串、内容不并）；**库名与远端待用户定**。
  ⇒ **在"切换到位 + 库定好"之前：不配远端、不建远端、不 commit、不 push。**
- **姊妹参照**：`J:\Bonsai`（自建线，Ambolio 移植树，冻结对照）、`J:\分发`（沈三殊发放包原件）、`J:\KVMem-GS` / `J:\KVMem-GSQ`（KVMem llama 分支线）。
- **协作者**：用户会在此工作区同时唤起 **CodeBuddy**，与我共同开发（见 `docs\05-交接与值守\协作-给CodeBuddy-20261009.md`）。

---

## §1 本项目（ninfer-kvmem）是什么

把新模型 **`Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`** 搬进 **NInfer + KVMem** 架构跑起来，并把 Bonsai 线的**全部能力**尽量适配到它身上：

> **NInfer 的核心解码（最快）＋ KVMem 的长上下文（把 KV 卸到主机内存、腾显存）＋ 三种投机解码（MTP / DFlash2 / ngram）**

用户原话（动机）："NInfer 核心解码超过其他所有架构，KVMem 可以把显存腾出来，三个投机解码是提升速度的关键，这个路子很对，唯一就是我们把这个新模型给在这个架构里跑起来。"

**为什么单开一条线**：不污染已封存、已可复现的 `J:\Bonsai-Official`；本线从零建立、`git init` 管理、本地结构与仓库对应。

---

## §2 与前工作区 `J:\Bonsai-Official` 的关系

- `J:\Bonsai-Official` = **官方线**：NInfer v0.11.0 + KVMem 环（融合仓 `1314521gjy/ninfer-fusion-kvmem`）+ 沈三殊三元 v3 制品。**已完成可复现化收尾并推送，封存只读**。
- 本线 `J:\ninfer-kvmem` = **它的续作/衍生**：复用同一条引擎与 KVMem 技术底座，但**换了模型（Coder390 而非 Ternary-Bonsai v3）**，目标从"跑通 v3"变成"把 v3 的能力（三类投机等）适配到 Coder390"。
- 两边仍可互相访问；**但不要再指望"回去翻"**——本线需要的参考已集中到 `refs\`（见 §6）。

---

## §3 我在本线要做什么（任务 + 现状）

### 3.1 目标路线（按优先级）

| # | 目标 | 现状（2026-10-09） | 卡点根因（已取证） |
|---|---|---|---|
| 0 | **裸解码跑通** | ✅ 已通（约 52 tok/s 量级） | — |
| 1 | **MTP 投机** | ❌ 失败 | `weight/000789: unknown tensor format: gguf_q4_0` —— MTP 头里 5 个张量是 `gguf_q4_0`，引擎格式白名单**无 Q4_0** |
| 2 | **DFlash2 投机** | ❌ 失败 | `Qwen3.5 config: missing component dflash2` —— 该 `.ninfer` **包内没有 dflash2 组件** |
| 3 | **ngram 投机** | ❌ 失败 | `ngram requires --spec mtp\|dflash\|dflash2` —— 依赖 1 或 2 先通 |
| 4 | 集成（KVMem / 启动器 / 日志 / 复现材料） | ⬜ 待办 | 需 1–3 有结论后收口 |

> **纪律**：三条投机"**试到确认做不到为止**"，每条都要有**原文输出 + 读数 + 证据**，不许拍脑袋下结论。

### 3.2 攻法备忘（供我自己）

- **MTP（卡在 q4_0）**：两条路——
  - **路 A（引擎侧）**：给引擎补 `gguf_q4_0` 支持（`src/artifact/formats.cpp` 的 `kFormats` 白名单 + `src/ops/linear/gguf/ggml_bridge.h` 的 `GgmlType` 枚举与映射 + 反量化内核），**要重编**（自编链见 §5）。
  - **路 B（数据侧，较轻）**：把 MTP 组件里 5 个 q4_0 张量**反量化重存**为引擎已支持的格式（bf16 / q4_k …），重排/重打包 `.ninfer`。**容器无内容校验**（`reader.cpp` 只查 magic + json_bytes，offset16=artifact id 非哈希，payload 对齐 4096）⇒ 可安全重写。
  - **路 C**：请上游作者（沈三殊）用支持格式重导 MTP 头。
  - 先做**路 B 可行性探针**（不重编、见效快），再决定要不要走路 A。
- **DFlash2（卡在包内无组件）**：需另找 **DFlash2 草稿件**并注入（主仓 `DFlash2-FP8/` 或 NVFP4-Infer 仓的 `.ninfer`）。**最不确定项**。可参考沈三殊档位包里的"**自造 dflash2 注入件**"做法（`refs\01-沈三殊-发放包\新\急速档V2\`）。
- **ngram**：`--ngram-draft-tokens`（依赖 `--spec`，随 1/2 走）与 `--lookup-ngram`（独立，实测当前**空转无加速**，需真实请求复验）。ngram 审计见 `docs\03-归因与结论\BONSAI_ngram_audit_report.md`。

---

## §4 关键事实（当前口径，带证据）

### 4.1 模型

- 文件：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`
- 大小：**12,372,798,720 B**（≈12.36 GiB）；**SHA256 = `CDD82B69027FABA0BDA619224EE851CCD0ECF0DFB176BAD85A17D2DF07926921`**（源=副本一致）
- 容器：magic `NINFER\0\3`；架构 `Qwen3_5ForCausalLM`；**64 层 / hidden 5120 / vocab 248320 / max_pos 262144**
- 组件：**只有 `text` + `mtp`**（**无** vision、**无** dflash/dflash2）
- `text`：787 权重，**格式全支持、零 q4_0**；`mtp`：**5 个 `gguf_q4_0`**（`mtp/input_projection`、`mtp/layers/0/attention.{query,gate,key,value}`、`.../attention/output`、`.../mlp.{gate,up}`、`.../mlp/down`）
- metadata name：`qwen3.8-27b-coder390-Q2LynnStyle-Mtp`

### 4.2 引擎（两套，都在 `engine\`）

| 用途 | 路径 | 说明 |
|---|---|---|
| **自编（现役）** | `engine\self-built-20261008\ninfer-serve.exe` | 含 MSVC 兼容补丁 + Design C；用于实测 |
| 官方对照 | `engine\ninfer-serve-120a.exe` | sm_120a 官方件 |

- 格式白名单：`src\artifact\formats.cpp` 支持 `gguf_blocks_v1`，含 q2_k/q3_k/q4_k/q5_k/q6_k/q8_0，**无 `gguf_q4_0`**。
- GGUF 桥：`src\ops\linear\gguf\ggml_bridge.h` 的 `GgmlType` 枚举**无 Q4_0**。
- 投机枚举：`--spec mtp|dflash|dflash2`（`serve_options.cpp:260`）。
- 视觉省显存：`--vision-residency resident|overlay|cpu`、`--vision-cpu`（对**无视觉塔**的 Coder390 无意义）。

### 4.3 本线已有的前序成果（来自 Bonsai 线，可直接借用）

- **启动器** `ninfer_launcher.py`（GUI，零外部依赖）+ `启动器.bat`；日志工具 `serve_tee.py`。
- **部署脚本** `start-pq2*.bat` / `start-ptq1-mtp.bat`（**注意**：目前写的是 Bonsai 模型名与旧路径，本线要适配成 Coder390）。
- **复现材料** `build\`（自编引擎构建脚本 + 3 枚引擎补丁 + 产物清单）。
- **引擎源码** `official-repo\ninfer-fusion-kvmem\`（融合仓全库）。

---

## §5 自编引擎链（要改引擎时必须）

- 素材：`official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src\`（源码树）+ `build\`（脚本与补丁）。
- 工具链：Windows + **CUDA 13.3** + MSVC（VS2022 BuildTools）+ CMake + Ninja + vcpkg；`sm_120a`。
- **构建脚本里写死了本机绝对路径**（vcvars / CUDA / vcpkg / SRC / BUILD），改路径照 `build\README.md` §四。
- **红线（前序教训）**：**一个架构一个空目录 clean build**——增量构建会产出"启动即崩"的二进制。
- 产物落**正式目录**，**不要留 `.temp\`**（T-NO-TEMP-WORK）。

---

## §6 参考在哪（本线自足）

- `refs\00-参考资料索引.md` —— **参考总索引**（上游发放包、技术论文、两条前序线文档）。
- `refs\01-沈三殊-发放包\` —— 上游作者（沈三殊）的**全部部署/转换/排错/技术路线文档 + 档位包源码树**。
- `refs\03-技术论文\三元-Bonsai-27B-NInfer-移植-技术论文.pdf` —— **技术融合的"思路与实践"总纲**。
- `refs\04-自建线-J-Bonsai\` / `refs\05-官方线-J-Bonsai-Official\` —— 两条前序线的构建史、评估报告、交叉审核。
- `official-repo\ninfer-fusion-kvmem\` —— 融合仓全库（复现白皮书 / 已知问题 B01–B20 / tools\ / verify\）。
- `docs\03-归因与结论\BONSAI_ngram_audit_report.md` —— ngram 源码级审计与"Coder390 上加 ngram"的可行性。

---

## §7 纪律（会在我身上生效的铁律，摘要）

- **T-PROTECT-ASSET**：`.gitignore` 排除的 >1G 资产（`models\`、`engine\`）**禁止同树删除/移动**；删除前列清单 + 备份 + 用户批准。
- **T-NO-TEMP-WORK**：任务产物（引擎/模型/成果）**落正式目录**，严禁 `.temp\`。
- **T-COMMIT-APPROVAL**：**每个 commit 前把完整内容（message + 文件清单 + diff）打给用户看，做定性说明 + 提交建议，停等批准**；未获明确同意**禁止** `git commit`/`git push`。
- **T-BACKUP**：有退化风险的改动前先备份（`tools\backup_file.py`，若可用）；git 已 track 亦可作回滚。
- **T-EVIDENCE**：任何"日志显示/测试通过/已备份"的结论必须紧跟 `[EVIDENCE] 文件:行:原文`。
- **触发即停**：`T-QUESTION`（提问≠指令）、`T-STOP`（先停查证）、`T-CHECKPOINT`（改共享代码前先答影响面）。
- **推送**：一律走 `smart_push.ps1`（禁裸 `git push`）。serve 启停归用户双击 BAT，AI 起服需授权。

---

## §8 会话启动须知（给下一个我）

1. **先确认工作区**：`Get-Location` 应显示 `J:\ninfer-kvmem`；若仍显示 `J:\Bonsai-Official`，说明**还没被切换**——不要假设自己已在新目录。
2. 读**本文件** → `refs\00-参考资料索引.md` → 按需读 `refs\05-...\docs\官方全库导读`。
3. 需要引擎/格式级细节时，进 `official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src\`。
4. **继续未竟事项**：三种投机适配（§3.1 的 1→2→3→4）。
5. **不确定就停、先取证再动手**；远端 / commit / push 一律先请示用户。

> —— 迁移到此，交接完毕。**别忘：原型在 `J:\Bonsai-Official`，成果在这里。**
