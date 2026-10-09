# ninfer-kvmem · 项目构建史

> 本文件记录本线（`J:\ninfer-kvmem`）**逐轮构建过程**：时间 + 做了什么 + 证据 + 教训 + 待续。
> 纪律（T-EVIDENCE）：关键数字与结论必须带 `[EVIDENCE] 文件:行:原文` 或命令输出摘要；证据不足标【待补】；订正旧条目必须显式标注（⚠️ 原表述已证伪→改为…），禁静默改写。
> 文件名带项目名前缀，避免与同族另一条线（`Bonsai-27B-NInfer-kvmem`）的同名文档混淆。

## 修订记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-10-09 | v1 | 建文件；补录建线、git 基线、私库、首份调研报告 |
| 2026-10-09 | v2 | 补录与 CodeBuddy 的交叉审核（含 1 处证伪、2 处收紧） |
| 2026-10-09 | v3 | 交叉审核第二轮收敛：MTP 探针定 q8_0（弃 q4_k）；完成 DFlash2 零成本几何核对（通过） |
| 2026-10-09 | v4 | 审核 CodeBuddy 施工方案 P1：判可批准，附 4 处必改（脚本落位冲突/决策规则/oracle 口径/L0 断言） |
| 2026-10-09 | v5 | 第三轮：独立复现"q4_0 的 d 可为负"；确认损失三前提；标出方案 3 处未落实 |
| 2026-10-09 | v6 | 最终对齐：方案 5 点全部落实（实证复核）；交叉审核全收敛，静待用户裁决 |

---

## 〇、项目定位

把模型 `Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer` 搬进 **NInfer + KVMem** 架构，尽量适配 **MTP / DFlash2 / ngram** 三种投机。单开本线以避免污染已封存、可复现的 `J:\Bonsai-Official`。

- **引擎底座**：`official-repo\ninfer-fusion-kvmem\`（NInfer 融合 KVMem 环）
- **现役引擎**：`engine\self-built-20261008\ninfer-serve.exe`（自编，含 MSVC 兼容补丁 + Design C）；官方对照 `engine\ninfer-serve-120a.exe`
- **模型**：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`

---

## 一、2026-10-09 · 建线与 git 基线

### 做了什么
- 用户将主工作区迁至 `J:\ninfer-kvmem`；确认 `Get-Location = J:\ninfer-kvmem`。
- `git init -b main`（`core.autocrlf false`、`core.quotepath false`）。
- **基线 commit `99c7233`**：message `chore(repo): 建立 ninfer-kvmem 工程基线`；37 文件；3336 insertions。
  - 定性（工具三分法）：①产品代码=启动器/日志工具；②项目工具=部署脚本/`build\` 复现材料；文档=教程/ngram 审计/交接与协作说明。
  - `.gitignore` 排除输入物料：`engine/ models/ official-repo/ refs/ _safety_backups/ logs/ .temp/ tools/ smart_push.ps1 .codebuddy/`，另排除 `docs/仓库建议.txt`（评的是姊妹仓，非本线产品，经用户裁决排除）。
- **新建私有库并推送**：`paicat1/ninfer-kvmem`（`private=True`，`default_branch=main`）。
  - 建库方式：本机无 `gh` CLI，走 GitHub REST API（`POST /user/repos`），凭据取自 Windows 凭据管理器（`git credential fill`，scope 含 `repo`）；**token 未打印、未落盘、未进 remote URL**。
  - 推送走 `smart_push.ps1`（遵守 T-0001「禁裸 push」，pre-push 门戳）。

### 证据
- `git log --oneline -n 1` → `99c7233 chore(repo): 建立 ninfer-kvmem 工程基线`
- `git rev-parse HEAD` = `99c7233a8d0b585670d441463949c4630e1af825`
- `git ls-remote origin` → `99c7233a8d0b… refs/heads/main`（与本地 HEAD 逐字一致）
- GitHub API：`full_name=paicat1/ninfer-kvmem private=True default_branch=main`
- 提交前扫描：`NO_SECRET_HIT` / `NO_AIGC_HIT`
- [EVIDENCE] `.gitignore:19: docs/仓库建议.txt`（排除项）

### 教训
- 执行期工具调用出现**并发/重复回放**，引发瞬时 `.git/index.lock` 与 `.gitignore` 重复写入；已停下核实并还原，最终提交**干净（规则仅一条）**、37 文件正确。**处理原则：遇锁/异常先停下核实真实状态，不盲目继续或重试。**

---

## 二、2026-10-09 · 首轮技术调研（目标实现路径）

### 做了什么
产出调研报告：`docs\调研-目标实现路径-Coder390接入NInfer-KVMem-20261009.md`（署名 TeleAgent，供与 CodeBuddy 交叉审核）。关键取证：

1. **直读本机模型容器**（脚本 `.temp\peek_ninfer*.py`）：
   - 单文件；`payload_bytes=13,272,548,864`；**文件总长 13,272,798,720 B（12.36 GiB）**。
   - **804 对象**（800 张量 + 4 资源）；组件**只有 `text` + `mtp`**；**无 dflash/dflash2**。
   - **5 个 `gguf_q4_0` 张量，经 bindings 反查全部且仅属于 MTP**：`weight/000079`(attn qkv+gate)、`weight/000080`(mlp gate_up)、`weight/000789`(input_projection)、`weight/000796`(attn output)、`weight/000798`(mlp down)。
   - provenance：converter `ninfer-v3`，recipe `qwen3_8_27b_gguf`。
2. **引擎格式缺口**：`formats.cpp` 白名单无 `gguf_q4_0`；`ggml_bridge.h` 的 `GgmlType` 无 Q4_0；引擎源码全树 `q4_0` 命中 0。
3. **vendored ggml 已自带 Q4_0 内核**（`GGML_TYPE_Q4_0=2`、`dequantize_q4_0`、ampere/blackwell MMQ 配置）。
4. **关键算术**：Q4_0 = 18 B/32 元素 = 0.5625 B/元素；Q4_K = 144 B/256 元素 = **同样 0.5625 B/元素**；5 个 MTP 对象元素数均被 256 整除 ⇒ **q4_0→q4_k 是"等长重写"**（不改 offset/长度、不重编）。
5. **容器无内容哈希**（`reader.cpp:50` 仅长度校验）⇒ 改写 payload 安全；重打包有先例 `tools\strip_components.py`。
6. **本机引擎自带转换器**含 `qwen3_8_27b_gguf` 配方（逐字导入 GGUF 块格式）与 **dflash2 逐字节嫁接先例**（`quasar_nvfp4.py:_collect_dflash2`）。
7. **DFlash2 是独立来源**（`z-lab/Qwen3.8-27B-DFlash2`），作 66 对象后缀注入；绑定强依赖组件几何 ⇒ 不能随手灌注。

### 结论（报告的推荐顺序）
先做 **MTP 方案 B（等长重写 q4_0→q4_k，先备份原模型）** 拿读数 → 不满意再上 **方案 A（引擎补 Q4_0，重编）** → MTP 稳后启 **ngram**（同口径 A/B）→ 最后评估 **DFlash2**（最重、最不确定，可结案）。并附**方案 0**（只做集成、不碰投机）。

### 证据
- [EVIDENCE] `src/artifact/formats.cpp:22: std::pair{QType::GGUF_Q8_0, std::string_view{"gguf_q8_0"}},`（表中无 q4_0）
- [EVIDENCE] `src/artifact/formats.cpp:59: throw ArtifactError("unknown tensor format: " + std::string(name));`
- [EVIDENCE] `src/ops/linear/gguf/ggml_bridge.h:16: enum class GgmlType : int {`（无 Q4_0）
- [EVIDENCE] `third_party/ggml-quants/include/ggml.h:392: GGML_TYPE_Q4_0    = 2,`
- [EVIDENCE] `src/artifact/reader.cpp:50: if (expected != file->bytes()) {`（仅长度校验）
- [EVIDENCE] `src/models/qwen3_5/config.cpp:321: out.mtp  = options.speculative == SpeculativeBackend::Mtp;`
- [EVIDENCE] `src/models/qwen3_5/load/mtp.cpp:8: out.input_projection = b.parameter("mtp/input_projection", {h, 2ULL * h}, {"mtp/stem_input"});`
- [EVIDENCE] `tools/convert/gguf_blocks.py:475: RECIPES = {"qwen3_8_27b_gguf": qwen3_8_27b_gguf}`
- [EVIDENCE] `tools/convert/quasar_nvfp4.py:115: def _collect_dflash2(official: Artifact) -> dict:`

### 订正（旧文档笔误）
- ⚠️ `docs\交接-工作区迁移-TeleAgent-20261009.md` §4.1 记模型大小 `12,372,798,720 B`，**实测为 `13,272,798,720 B`**（13 误作 12；"≈12.36 GiB"换算正确）。以本构建史为准。
- 【待补】交接文档所给 SHA256 `CDD82B69…6921` 本轮未复算。

---

## 三、2026-10-09 · 与 CodeBuddy 交叉审核

### 做了什么
- CodeBuddy 产出主报告 `docs\调研-项目目标实现路径-CodeBuddy-20261009.md` + 三份子报告（`docs\_research\`）。
- TeleAgent 逐条独立复核（读源码 / 直读容器 / 文件系统核对），产出 `docs\交叉审核-TeleAgent对CodeBuddy-20261009.md`。

### 裁定要点
- **认同**对方核心判断：MTP 走数据侧重打包（路 B）不重编、探针选 `gguf_q8_0`（逐位无损）、暂缓路 A、ngram 随 MTP 通、先 MTP 后 DFlash2 且不先自训。
- **证伪 1 处（对方错）**：其称 `tools/strip_components.py` 不存在（搜索 0 命中）——实为存在（`official-repo\infer-fusion-kvmem\tools\strip_components.py`）；漏报根因=**检索工具跳过 `.gitignore` 排除目录**。教训：`official-repo/ refs/ models/ engine/` 内检索一律用 PowerShell。
- **收紧 2 处**：①对象 offset 对齐的执行点在 `src/artifact/layouts.cpp:12`（非 `weight_view.h:39`，后者是 `WeightGeometry` 默认值定义）；②KVMem **不是** `NINFER_KV_WINDOW` "唯一真值"，而是一族 `NINFER_KV_*`，且本线启动器自身 `KV_ENV` 注入 5 个（含 no-op 的 `NINFER_KV_RING`）。
- **双方独立印证同数**：模型 13,272,798,720 B；5 个 q4_0 全属 mtp；`vision:on` 为硬阻塞。

### 证据
- [EVIDENCE] `src/artifact/layouts.cpp:12: if (geometry.bytes != object.bytes || object.offset % geometry.alignment) {`
- [EVIDENCE] `ninfer_launcher.py:54: KV_ENV = {`（KV_WINDOW/KV_RETRIEVE/KV_RING/HOST_PAGEABLE/KV_REUSE_HOSTBACKED）
- [EVIDENCE] `src/product/speculative_options.h:57: "ngram requires --spec mtp|dflash|dflash2, drafts 1..63 and match 4..64"`
- [EVIDENCE] `tools/artifact/writer.py:270: os.link(self._temporary[index], target)`（原子发布、不覆盖源）
- 文件系统：`official-repo\infer-fusion-kvmem\tools\strip_components.py` 存在

### 独立新发现
- `auxiliary/000000`（int32，24,576 B = 6,144）实为 **GDN 的 `input_columns`**，属 800 tensor 之一，重打包必须保留（勿误当 resource）。
- 本机 `tools/artifact/{reader,writer,inspect,formats,layouts}.py` **齐备可用** ⇒ 路 B 工具链可行性得到正面证实。

---

### 第二轮收敛（CodeBuddy 复审后）
- **核心分歧（目标格式）已收敛**：MTP 探针 = **`gguf_q8_0`（逐位无损）**，**弃用 q4_k**（对方"q4_K 编码器静默失败"反例成立——容器合法能加载但草稿变垃圾、接受率骤降，且 MTP 输出被主模型验证 ⇒ 不污染最终答案却污染归因）。定稿格式（q8_0 或 iq4_nl）待探针读数后定。
- 我方保留质疑：q8_0"无损"须**自证**——前提①引擎 q8_0 解码==标准 ggml、②引擎 q4_0 值约定==(nibble−8)×d、③fp16 d 位级拷贝；建议 P1 加**块级自证**：误差恒为 0。
- **完成 DFlash2 零成本几何核对：通过**——本机 `full_attention idx [3,7,11,…,63]` 与参照契约 `qwen3.8-27b-artifact.md:92` **逐项一致**；特征层 `[5,19,33,47,61]` 类型 linear/full/linear/full/linear 一致 ⇒ 特征捕捉**必要**几何条件成立（**充分**性=接受率仍需实测）。
- KVMem **再更正**：是一族 `NINFER_KV_*` + 启动器 `KV_ENV` 注入 5 个（`ninfer_launcher.py:54-59`），非"`NINFER_KV_WINDOW` 唯一真值"；`NINFER_KV_RING` 为 no-op 这一点双方一致。
- 四项待决双方已一致（详见 `docs\交叉审核-TeleAgent对CodeBuddy-20261009.md` §6.4）。

### 证据（本轮）
- [EVIDENCE] 本机解析输出：`MATCH full_attention : True` / `MATCH feature-layer types: True`
- [EVIDENCE] `ninfer_launcher.py:54-59: KV_ENV = {...}`（5 项）

### 施工方案（P1）审核（2026-10-09）
- CodeBuddy 落盘 `docs\施工方案-P1-MTP数据侧重打包-CodeBuddy-20261009.md`（待批准）。TELE 独立核验后判**可批准**，附 4 处必改：
  1. **脚本落位冲突**：本仓根 `tools/` 已被 `.gitignore` 排除（`.gitignore:33`）且内容为③类工具链 ⇒ ②类脚本 `recode_mtp.py` 放此**静默入不了库**；建议改 `scripts\`。
  2. **决策规则漏洞**：用 B(q4_k) 接受率决定 C(iq4_nl) 去留，前提"B 实现正确且不优于 C"未证 ⇒ 建议规则仅在 B 过 oracle 后生效，否则直接量 C。
  3. **L0 断言口径**：writer 会**重序列化 JSON**（`writer.py:80,84` / `schema.py:427`）⇒ "payload 起点不变/总大小不变"未证；硬断言应只放格式决定的量（对象/张量数、格式计数、5 对象 bytes）。
  4. **事实更正**：auxiliary 6144 = **GDN 48×128**（`ternary.py:48-51`），非"24×256"（那是注意力的 24×256）。
- TELE **收回**"`NINFER_KV_RING` 空转"：CB 更精确，它是**被废弃旧名**（`serve_options.cpp:1118-1123` B30 修复）。

### 第三轮（2026-10-09）：无损三前提的独立复核
- CB 实证三前提（①引擎 q8_0 解码==标准 ggml；②容器内 q4_0==标准布局；③d 位级拷贝），并自查出**其"d 恒正"假设错误**（实测 ~50% 块 d 为负；llama.cpp `d=max/-8` 约定）——由 TELE 上轮"无损须自证"质疑逼出。
- TELE **独立复现**（自读 `weight/000798` 区域 4096 块）：`d negative ratio=0.5054`、`max|val|/|d|=8.0000 全中`、首块 d hex `089e`（负）⇒ 事实成立。
- TELE 保留：①`d=max/-8` 的**归因**标【待证】（本机 refs 未找到公式原文）；②L4b 判据应写"**语义等价 + 无系统性劣化**"而非"输出必须等价"（batch/round 结构差异会致微小数值差）；③新观察：本模型**无其它 q8_0 张量** ⇒ q8_0 通路属首次启用（L1/L3/L4b 覆盖）。
- **仍开**：方案 3 处未落实（脚本落位仍 `tools\`；决策规则仍硬 90%；L0 仍写"payload 起点不变"）——见审核文档 §8.4。

### 最终对齐（2026-10-09）：5 点全部落实
- TELE 以**当前方案文件行号**实证复核，裁定：§7.1（脚本落位）✅ 已为 `scripts\recode_mtp.py`（L102/230/231/298/321；L105 是撤回引文）；§7.3（噪声底）✅（L82-83/95-98）；§7.4（L0 断言）✅（L208-209 显式作废旧推断；L246-247 硬/软断言分离）；§8.2（L4b 措辞）✅（L258-261）；§8.3（q8_0 首次启用）✅（L273-275）。
- **我方同步更正**：上轮"仍开"基于更早版本（旧版行号 85/206/257/280 吻合），现以最新口径为准——避免"已声明作废≠全文一致"的同类不一致。
- **结论：交叉审核全收敛，无停止操作级分歧。** 静待用户裁决 P0/P1/文档提交/起服归属。

---

## 四、待续事项（挂账）

| # | 事项 | 状态 |
|---|---|---|
| 1 | 调研报告 commit（T-COMMIT-APPROVAL 审批后） | 待用户批准 |
| 2 | MTP 方案 B 探针（等长重写 q4_0→q4_k；**先备份原模型**） | 待用户裁决 |
| 3 | 是否允许改写 `models\` 内 `.ninfer` | 待用户裁决 |
| 4 | 引擎补 Q4_0（方案 A）与否 | 待用户裁决 |
| 5 | DFlash2 是否投入（需 z-lab DFlash2 + 转换 + 几何证明） | 待用户裁决 |
| 6 | `start-*.bat` / 启动器 适配 Coder390（现仍写 Bonsai 名与旧路径） | 待办 |
| 7 | 复算模型 SHA256 并补录 | 待办 |
| 8 | KVMem 检索判活（`kvmem_score: SELECT`）在 Coder390 上确认 | 待办 |

> —— 构建史由 TeleAgent 维护；每轮施工完成后**自动补录本文件**（不等催）。
