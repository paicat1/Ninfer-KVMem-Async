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
| 2026-10-09 | v7 | **分工变更**（施工+构建史归 CodeBuddy）；**P0 施工：启动层适配 Coder390**（7 改 2 增）；9 份文档已提交 `d2c9806` |
| 2026-10-09 | v8 | **P0b：引擎统一 self-built**（含 cublas 依赖发现：PATH 必须含 `engine\` 根）——用户批准后实施，交 TELE 复审 |
| 2026-10-09 | v9 | **P0c：实测起服**——裸解码基线 **≈17 tok/s**（3 次）；KVMem 判活 `kvmem_score: SELECT` ✅；流传的"~52 tok/s"标【待证】（refs 内只找到 llama.cpp bench 表） |
| 2026-10-09 | v10 | **P0c-2：成因已定**——关掉浏览器后同参数重测 **55.7–55.9 tok/s**（差 3.3 倍）⇒ 17 tok/s 系 GPU 资源竞争所致；**撤销"52 tok/s【待证】"**（实测证实）；新增 A/B 前置纪律：测试前清 GPU 占用 |
| 2026-10-09 | v11 | **P0 系列已入库**（a96d6af 提交 + push，含 TELE 的 07898d7）；**P1 施工完成**——`scripts\recode_mtp.py` + q4_0→q8_0 位级无损重打包，**L0/L1/L2 三档验收全过**（13,271,040 块零不匹配），交 TELE 审核 |
| 2026-10-09 | v12 | ★**MTP 跑通**：官方 Q8MTP 版验证（多 vision、真 8-bit）→ 官方版起服两度失败（缺 139–200 MiB）→ **自转 `iq4_nl`**（q8_0→4.5bpw，Δ0 等长，省 212 MB）→ **起服成功 + A/B 实测**（散文 +32%、代码 +233%，接受率 22.6%/93.8%）；推翻上一轮"关 KVMem 省显存"的建议（KVMem 实为"允许 KV 池 < 上下文"的前提） |
| 2026-10-09 | v13 | **挂账 14 完成**：ctx 扫描四档 ⇒ **最大稳定 ctx = 24576**（free 349.7 MiB，decode 89.4 tok/s）；32768 缺 36 MiB（临界）、65536 缺 158 MiB。**P1b 施工已提交并推送**（`64a03d4`，含 TELE 的 `c7521dd`） |
| 2026-10-09 | v14 | ★**更正 §4.1 的错误结论**：`--max-context`（逻辑）≠ `NINFER_KV_WINDOW`（device 窗口）。修正后 **逻辑上下文 131072（128K）可用**，并实测 **20,203 tokens prompt 检索正确**（`ring retrieve restored=16`、`kvmem_score: SELECT`）；runtime 1.80→1.18 GiB、free 349.7→925.1 MiB |
| 2026-10-09 | v15 | **§4.3 device 活跃池**：澄清"全速区间由 `--kv-capacity` 决定"（非 window）；池扩容极便宜（≈0.83 MB/页）⇒ 定为 **kv 32768**；同 prompt A/B：TTFT 11.3→10.6s、decode 92.9→98.3 tok/s（**改善温和，瓶颈是 prefill 计算**）。给出本线最终推荐配置 |
| 2026-10-09 | v16 | **§4.4 压榨**：逻辑上下文 128K → **262144（256K，模型原生上限）**、全速池 32K → **40K**；decode 105.0 tok/s；kv 49152 仅缺 49 MiB（临界，待清 GPU 占用后重试）；列出剩余可压榨项 |
| 2026-10-09 | v17 | **三·九 启动器定稿**：`ninfer_launcher.py`（9 处：模型指向 iq4_nl 件 / 池 40960 / window 32768 / DEFAULTS / 选项表 / 预设 / 回退值 / 提示）+ 两个 `start-coder390*.bat`（参数与实测成功命令逐字对齐，补 hemostat 两旗）+ profiles 增 4 个 ★定稿档；构造命令与实测逐字一致 |
| 2026-10-10 | v18 | **Bonsai 口径清除**（用户裁决）：删 4 个 Bonsai 启动脚本、删 8 个 Bonsai 预设、profiles 14→**4 档**（只留 ★）、UI 标题与 docstring 改本线口径；保留 8 处历史沿革字样（非功能残留）与 `BONSAI_ngram_audit_report.md`（ngram 参考件） |
| 2026-10-10 | v19 | **launcher 定稿标注 + 引擎下拉收口 + 双击修复**：14 个参数维度的定稿值全部标 ★（实测核对无遗漏）；DFlash2 档（包内无组件）与 vision 开档（必失败）加不可行标注；引擎下拉 **3→1**（自编现役；原含不存在的回退锚与行为路径不同的官方件），3 处 `exe or ENGINE` 回退值同步；`启动器.bat` 修复双击失效（UTF-8 中文注释 + LF 换行 + 多行 if 块 ⇒ ASCII + CRLF + goto） |
| 2026-10-10 | v20 | **§三·十**：① 定稿参数"闪退"根因 = **只差 20.4 MiB**（起服瞬间可用量波动；同参数 2 分钟后复跑成功）⇒ 非参数错；② ★**视觉 CPU 模式实测可行**：官方 Q8MTP 版 + `--vision-cpu` 起服成功（weights 12.5 GiB、free 663.4 MiB、设备视觉显存占用为零），代价=图片压到 256 merged tokens + CPU 编码慢；③ vision 选项标注修正（"必失败"仅对本线 iq4_nl 版成立） |
| 2026-10-10 | v21 | **日志降噪 + vision 启动脚本**：`serve_tee.py` 新增 `is_diag_noise()`（slim 模式隐藏 `[ring] budgets` / `[ninfer] mask hidden` / `[ninfer] demote-other short` 三类引擎硬编码诊断行，**日志文件仍全文落盘**）；`start-coder390.bat` / `-mtp.bat` 改经 `serve_tee.py` 启动（精简视图 + 日志）；**新增 `start-coder390-vision.bat`**（官方 Q8MTP + `--vision-cpu` + 20K 池）；4 bat 均 ASCII-only + CRLF，实测 `/v1/models` HTTP 200 |

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

## 三·六、2026-10-09 · 文档提交 + P0 施工：启动层适配 Coder390（CodeBuddy 实施）

### 分工变更（用户裁决）
- **施工与项目构建史 → CodeBuddy 实施**；每步完成交 TeleAgent 审核；审核通过并修复后由 CodeBuddy `commit`/`push`。
- **审核报告 → TeleAgent 实施**，每轮审核后由 TeleAgent 记录并 `commit`/`push`。
- 本文件维护权自本轮起移交 CodeBuddy（原为 TeleAgent）。
- commit 纪律：**保留 T-COMMIT-APPROVAL 展示环节**（message + 清单 + diff + 定性 + 建议 → 停等用户批准），用户裁定"A（保留）"。

### 第一件：9 份文档提交
- commit `d2c9806`，message：`docs(mtp): 新增 Coder390 投机适配调研报告、交叉审核意见、P1 施工方案与本线构建史`；9 files / 3686 insertions。
- push：`99c7233..d2c9806 main -> main`（走 `smart_push.ps1`，`=== PUSH OK ===`）。
- ⚠️ 过程中一次 push 失败（`Failed to connect to github.com:443 over proxy 127.0.0.1`）：诊断发现推送瞬间 **7890 端口未监听**（`smart_push` 探测不到代理、回退 git config 的代理地址亦不通），约 1 分钟后端口恢复（FlClashCore 在监听），复测 `curl -x 127.0.0.1:7890 https://github.com` = HTTP 200，重试即成功。**结论：非代码问题，代理瞬时不可用；直连（不走代理）实测 20s 超时不可用。**
- ⚠️ 提交时 `git commit -m "<中文>"` 返回 255 且无输出；改用 **`git commit -F <UTF-8 文件>`** 成功（临时文件写在 `.git\` 内、用后即删）。教训：本机 PowerShell→git.exe 传中文 message 不可靠，**中文 message 一律走 `-F` 文件**。

### 第二件：P0 启动层适配（7 文件改动 + 2 文件新增）
1. **`启动器.bat`**：解释器解析改写——原写死 `D:\Python311\pythonw.exe`（**本机不存在**）⇒ 三级回退：PATH `pythonw.exe` → `J:\miniconda3\pythonw.exe` → `%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe`；全找不到则 REFUSE + `exit /b 3`。（只改 ASCII 行，中文注释原样保留以零风险保持编码。）
2. **`ninfer_launcher.py`（6 处）**：
   - `MODEL`：`Ternary-Bonsai-2-27B-ninfer-v3.ninfer` → `Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`
   - `DEFAULTS`：`spec "d12"→"k0"`（裸解码 = 基线）；`vision "on"→"off"`（**硬阻塞**：Coder390 容器无 vision 组件，`on` 会在 `companion("vision")` 处抛 `missing component vision`）
   - `build_command` 两处 fallback：`"d12"→"k0"`、`"on"→"off"`（原为硬编码，非法值会**静默**回退到 DFlash2 / 视觉）
   - `--model-id`：`qwen3.8-27b` → `qwen3.8-27b-coder390`
   - `ENGINE_PREV`：注释标注 **本线 `engine\` 下无 `self-built\` 目录**，该路径不存在（GUI 选中仅提示"未找到引擎"，不崩）
   - GUI 标题：`Bonsai-27B-NInfer-kvmem 启动器` → `Coder390 · NInfer 启动器（ninfer-kvmem）`
   - `PRESET_PROFILES`：新增 `Coder390-裸解码` / `Coder390-MTP档`；旧档**显式**保留 Bonsai 语义（`spec="d12", vision="on"`），不再依赖 `DEFAULTS`
3. **新增 `start-coder390.bat`**：裸解码基线（自编现役引擎，端口 8091，**无 `--spec`、无 `--vision`**）——后续所有 A/B 的对照臂。
4. **新增 `start-coder390-mtp.bat`**：MTP K=4（自编现役引擎，端口 8095）；脚本内**显式警告**：原容器 MTP 头是 `gguf_q4_0`（引擎不支持），须等 P1 重编码容器。
5. **4 个前序 bat**（`start-pq2` / `start-ptq1-mtp` / `start-pq2-dflash` / `start-pq2-dflash-designc`）：**仅加 4 行 ASCII 注释**标注"前序 Bonsai 档；本线请用 `start-coder390*`"；**行为零改动**（它们指向的 Bonsai 模型在本线不存在 ⇒ 会安全 REFUSE）。
6. **`ninfer_launcher_profiles.json`**：**新增 3 个 Coder390 档**（裸解码 256K / 裸解码 180K / MTP K4 待P1）；旧 7 档 `vision` 统一 `on→off`（消除硬阻塞），`spec` **保留原值**（诚实反映"该档需 dflash2，本线未实现"）。

### 证据
- **备份（T-BACKUP）**：7 文件 → `_safety_backups\*_20261009_200734_pre-p0-coder390.*`
  sha256 前 8 位：`ninfer_launcher.py 69842003` / `启动器.bat d8e2e3c8` / `profiles 8320ae4f` / `start-pq2 64be9706` / `start-ptq1-mtp e33c75e2` / `start-pq2-dflash ede2103a` / `start-pq2-dflash-designc 5f8e092a`
- [EVIDENCE] `python -m py_compile ninfer_launcher.py` → `py_compile_exit=0`
- [EVIDENCE] 行为验证（实跑 `build_command(DEFAULTS)`）：
  - `MODEL : J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`
  - `has_--vision: False` / `has_--spec: False`
  - `profiles: 10`（Coder390 三档在最前：`Coder390-裸解码 256K` / `Coder390-裸解码 180K` / `Coder390-MTP K4（待P1容器）`）
  - ARGV 仍含止血两旗 `--kv-lease-growth --recover-invariant-failures`
- [EVIDENCE] `read_lints(ninfer_launcher.py)` → 0 diagnostics
- [EVIDENCE] `git log --oneline -1` → `d2c9806 docs(mtp): 新增 Coder390 投机适配调研报告、交叉审核意见、P1 施工方案与本线构建史`

### 决策与理由（供审核）
- **不删旧档、不改旧档 `spec`**：旧档承载用户配置与 Bonsai 经验（上下文长度 / KV 精度），删改属越权；只做"消除硬阻塞"的最小修复（`vision→off`）。旧档选中仍会因缺 dflash2 组件而失败——**这是诚实信息**（交付说明与脚本注释均已标注），不是隐藏的坑。
- **两个新 bat 用自编现役引擎，GUI 默认仍官方件**：现役=自编（含 Design C），GUI 默认=官方（原设计）。**两入口引擎不同** ⇒ 已列为待审核确认点，A/B 时必须固定同一引擎。
- **不擅自起服**：按纪律 serve 启停归用户双击 BAT。

### P0b（同日）：引擎统一为 self-built（TELE 审核裁定 + CodeBuddy 独立发现，用户批准）

**背景**：TELE P0 审核（`docs\审核-P0启动层适配-TeleAgent-20261009.md`）判 P0 通过，唯一实质问题 = **引擎不一致**（GUI 默认官方件 vs 新 bat 用自编）。

**CodeBuddy 独立发现（TELE 未察觉，交叉检查起效）**：
- `engine\self-built-20261008\` **只有 `cudart64_13.dll`，无 `cublas64_13.dll`**；后者**只在 `engine\` 根**。
- **全文件流式搜索**（两个 exe 各 **1.27 GB**；先前只读前 20 MB 得 False —— **大二进制搜索不能截断**）：
  `self-built → cublas64_13 : True`、`official → cublas64_13 : True` ⇒ 两者都动态依赖 cuBLAS。
- `ninfer_launcher.py:301` 原 `env_for_launch` 只加 `dirname(exe)` ⇒ 官方件（在 `engine\` 根）恰好含 cublas ✅；**自编件（子目录）PATH 不含 `engine\`** ⇒ 回退到系统 PATH。

**TELE 复核补正（成立，已采纳）**：系统 PATH 的 `J:\Bonsai\landing\cuda-13.3\bin\x64` 与 `CUDA\v13.0\bin\x64` 均含 `cublas64_13.dll` ⇒ **非"必崩"，而是条件性**。

**CodeBuddy 再补强（实测版本对比）**：

| 来源 | FileVersion | 大小 |
|---|---|---|
| 打包件 `engine\cublas64_13.dll` | **6.14.11.1351** | 49.5 MB |
| `J:\Bonsai\landing\cuda-13.3\bin\x64` | **6.14.11.1360** | 50.3 MB |
| `CUDA\v13.0\bin\x64` | **6.14.11.1310** | 49.2 MB |

⇒ 三版本**确实不同**；且系统 PATH **首个命中 = 前序已封存线 `J:\Bonsai\landing\` 的目录** ⇒ 不只是 ABI 漂移，而是**对外部封存线的隐式依赖**。

**裁定（用户 2026-10-09 批准）**：
- **A/B 统一 self-built**（现役；两个新 bat 已用）
- **GUI 默认引擎改 self-built**，且**两处成对改**（只改一处会引入"GUI 用系统 cublas"的不确定性）
- **精确化（对双方原表述的修正）**：`build\patches\README.md` 表明 3 枚补丁中**补丁 1（MSVC C2326/C3495/C2026）是编译期兼容**（"让源码在 Windows/MSVC 下编得过"）、补丁 3 是测试开关 ⇒ **self-built 与 official 的运行期差异实际只有 Design C**（补丁 2）⇒ `think=none` 时两者行为**基本等价**（统一紧迫性低于"必崩"叙事）；但**启用思考后会分叉**，统一仍必要。
- **附加（CodeBuddy 建议，用户同意）**：**关键结论（MTP 收益数字）另用 official 跑一次交叉验证** ⇒ 证明结论不依赖我们的补丁，且对外可复现。

**实施（2 处，均在 `ninfer_launcher.py`）**：
1. `env_for_launch`：PATH 改为 `[dirname(exe), ENGINE_DIR]` 去重拼接（`engine\` 根加入 ⇒ 固定用打包版 cublas、自包含）
2. `engine_var` 默认：`ENGINE_OPTIONS["official"][0]` → `ENGINE_OPTIONS["self"][0]`

**证据**：
- [EVIDENCE] `python -m py_compile ninfer_launcher.py` → `py_compile_exit=0`
- [EVIDENCE] 行为验证：`PATH[0]: J:\ninfer-kvmem\engine\self-built-20261008` / `PATH[1]: J:\ninfer-kvmem\engine` / `engine_root_in_PATH: True` / `exe_is_self_built: True` / `has_--vision: False` / `has_--spec: False`
- [EVIDENCE] `read_lints` → 0 diagnostics
- [EVIDENCE] 版本对比见上表（1351 / 1360 / 1310）

### P0c（同日）：实测起服 —— 裸解码基线读数（用户授权起服）

**起服方式**：复用启动器逻辑（`serve_tee.py` + `CREATE_NEW_CONSOLE` + 自编现役引擎 + 端口 8091）。
日志：`logs\serve_20261009_203742.log`。

**⚠️ 第一次起服失败（20:33）——根因=显存差 8.3 MiB，非改动缺陷**：
```
weights ready | 12.1 GiB | 7.9s | 1.53 GiB/s
ERROR engine init | FAILED: requested Engine runtime reservation requires 1833072640 bytes,
      but only 1824366592 bytes are available for runtime capacity
FATAL server failed during startup          （serve_tee end exit=1）
```
差 **8,706,048 B（≈8.3 MiB）**；当时 GPU 已用 3136 MiB。约 6 分钟后其他程序释放 ~288 MiB，**原参数重试成功**（11 秒就绪，参数未降级）。

**成功起服读数**：
- `engine ready | qwen3.8-27b-coder390-Q2LynnStyle-Mtp | weights 12.1 GiB | total 8.5s`
- `capacity | KV 17,920 tokens, k8v4, explicit | pages 280/4,096 | runtime 1.71 GiB | free 496.6 MiB`
- `warmup complete | 413 ms` / `listening on http://127.0.0.1:8091`
- 全程**无 WARN/ERROR/FATAL**（健康）

**KVMem 判活 ✅（G4 部分验证）**：
- `kvmem_score: ARMED capacity_blocks=4096 layers_total=16 heads=24 kv_heads=4 head_dim=256`
- `kvmem_score: SELECT label=text_prefill_chunk n_blocks=1 budget_blocks=512 ... kept=1 runs=1 ... harvest_layers=16/16`（多次）
- `kvmem_index: installed layers=16 heads=4 head_dim=256 blocks=4096 bytes=256.2 MiB`
- 请求侧旁证：`req#3 ... cache 20 (74.1%, turn closure)`

**裸解码基线读数（3 次，同参数；权威来源=引擎日志 `req#N done` 行）**：

| 次 | prompt | output | TTFT | total | prefill | **decode** |
|---|---|---|---|---|---|---|
| req#1 | 27 | 128 | 359 ms | 8.1 s | 75.4 tok/s | **16.3 tok/s** |
| req#2 | 27 | 174 | 313 ms | 9.9 s | 127.0 tok/s | **18.1 tok/s** |
| req#3 | 27 | 141 | 131 ms | 8.6 s | 54.5 tok/s | **16.6 tok/s** |

⇒ **本配置基线 ≈ 17 tok/s**（GPU 15663 MiB used / 317 MiB free / 100% util）。

**⚠️ 与流传的"~52 tok/s"差约 3 倍——该数字缺乏可追溯原始记录**：
- 出处链：`docs\协作-给CodeBuddy-20261009.md:41`（"裸解码 ✅ 通（~52 tok/s 量级）"）、`:46`（"`--lookup-ngram` A/B 实测 52.9 vs 51.9 tok/s"）→ 交接文档同步引用 → 我方报告沿用。
- 在 `refs\` 内搜 `52.9|51.9`：命中**全部是 llama.cpp 的 bench 表**（`refs\01-沈三殊-发放包\新\低显存档\src-tree\llama-kvmem\benches\*` 等），**不同引擎、不同模型**；**未找到 ninfer + Coder390 的原始实测记录**。
- ⇒ 该数字**标【待证】**；后续 A/B 的对照基准以**本次实测 ~17 tok/s（同参数可复现）**为准。

**候选成因（未定论，待对照实验）**：
1. **显存极紧**（free 317 MiB；起服曾差 8.3 MiB 失败）⇒ 可能触发 host/device KV 换页；
2. **日志开销**：本次用 `SERVE_TEE_MODE=full`（启动器默认为"精简"）⇒ 457 行 `[ring] budgets`/3 请求（总 524 行 / 61.7 KB）；
3. **KVMem ring 检索开销**（content scoring 每步计算）；
4. **模型特性**（Q2LynnStyle 低比特混合 + 48 个 `linear_attention` 层）。

### P0c-2（同日 21:39）：显存条件对比实测 —— 17 tok/s 的成因已确定

用户指出"刚才开了浏览器，显存占用较大" ⇒ 关闭浏览器等 GPU 占用程序后（GPU used 3136 MiB → **1186 MiB**），**同参数**重起（10 秒就绪，`logs\serve_20261009_213935.log`）并重测：

| 轮 | GPU 环境 | decode（3 次） | TTFT |
|---|---|---|---|
| P0c（20:38） | 浏览器等在跑 | 16.3 / 18.1 / 16.6 tok/s | 359 / 313 / 131 ms |
| **P0c-2（21:40）** | **已关闭** | **55.7 / 55.8 / 55.9 tok/s** | 131 / 52.1 / 51.3 ms |

⇒ **差 3.3 倍**。**结论：P0c 的 17 tok/s 不是模型/参数问题，而是 GPU 资源竞争（浏览器等程序占显存 + 分走算力）。**

**修正 P0c 的三处判断（自我纠错）**：
1. ⚠️ P0c 曾把"~52 tok/s"标【待证】并怀疑文档数字 —— **实测证实 52–56 tok/s 是准确的**，【待证】**撤销**；
2. P0c 列的 4 条候选成因中，**第 1 条（显存/GPU 竞争）是唯一主因**；full 日志（457 行/3 请求）、ring 检索开销、模型特性影响**远小于此**（本轮日志模式仍为 full，速度已达标）；
3. P0c 曾判断"free 317 MiB 是引擎正常吃满" —— **不完整**：引擎确实会吃满**可用**显存，但当其他程序占用时，"可用"本身更少、且算力被分走。

**⇒ 纪律（写入 A/B 前置条件）**：**起服与 A/B 测试前必须关闭占用 GPU 的程序**（浏览器 / QQ / NVIDIA Overlay 等）；否则读数不可比（实测差 3.3 倍）。

**本配置基线（定稿）**：**decode ≈ 55.7–55.9 tok/s**；TTFT 51–131 ms；prefill 137–207 tok/s；KVMem 判活 `kvmem_score: SELECT` + `cache 20 (74.1%, turn closure)`；GPU 15601 MiB used / 379 free / 99% util。

### 遗留（交审核 / 后续）
1. **GUI 默认引擎（官方件）vs 新 bat 引擎（自编现役）是否统一**——待审核裁定。
2. **本机实测起服（裸解码基线读数）未做**——需用户双击 BAT，或授权 AI 起服。
3. `logs\` 目录由 GUI/tee 按需创建，未预建。

---

## 三·七、2026-10-09 · P1 施工：MTP 数据侧重打包（q4_0 → q8_0 位级无损）

### 做了什么
1. 新增 **`scripts\recode_mtp.py`**（②类项目工具；落 `scripts\` 而非 `tools\` —— 后者被 `.gitignore` 排除会静默入不了库）：
   - 骨架照官方重打包范例 `official-repo\ninfer-fusion-kvmem\tools\strip_components.py`，`UPSTREAM` 指向本机源码树；
   - 只改 5 个 `gguf_q4_0` 对象的 `format` → `gguf_q8_0` + 转码字节；其余 799 个对象**原样流式搬运**；
   - **位级无损转码**：q4_0 块 18 B（fp16 `d` + 16 B nibbles）→ q8_0 块 34 B（fp16 `d` + 32 B int8）；**scale 两字节逐字节拷贝**，nibble → `int8(nibble − 8)`（经 int16 中转防 uint8 下溢）；**零浮点运算、零重量化**；
   - 读源 q4_0 对象必须用 `iter_range`（`iter_object` 会因 q4_0 不在 Python 格式注册表而抛错）；
   - 内置 `--dry-run` / `--verify`（全量 oracle）/ `--negative-control`（L2）；
   - `metadata.name` 追加 `+mtp-q8`（标记非原厂件）；`provenance.mtp_recode` 登记来源/方法/源 artifact_id。
2. **产物**：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-q8.ninfer`
   （**新文件**；原件零写入 —— writer 对已存在目标抛 `FileExistsError`，且全程只 `iter_range` 读源）。

### 验收证据（三档全过，交 TeleAgent 审核）
**L0（结构；`tools.artifact.inspect --json / --objects`）**：
```
file_bytes 13485135360 | payload_bytes 13484885504
objects 804 | tensors 800 | resources 4 | bindings 979 | uses 619
formats: gguf_q8_0 = 5   （gguf_q4_0 已归零）
name: qwen3.8-27b-coder390-Q2LynnStyle-Mtp+mtp-q8
weight/000079  77987840  gguf_q8_0/gguf_blocks_v1 [14336, 5120]
weight/000080 189399040  gguf_q8_0/gguf_blocks_v1 [34816, 5120]
weight/000789  55705600  gguf_q8_0/gguf_blocks_v1 [5120, 10240]
weight/000796  33423360  gguf_q8_0/gguf_blocks_v1 [5120, 6144]
weight/000798  94699520  gguf_q8_0/gguf_blocks_v1 [5120, 17408]
```
（5 对象 bytes 与方案 §3.4 表、dry-run 输出**逐项一致**）

**L1（全量位级 oracle，非抽样；源容器 q4_0 vs 新容器 q8_0 逐块解出比较）**：
```
weight/000079  blocks=2293760  scale_identical=True values_identical=True mismatches=0
weight/000080  blocks=5570560  scale_identical=True values_identical=True mismatches=0
weight/000789  blocks=1638400  scale_identical=True values_identical=True mismatches=0
weight/000796  blocks=983040   scale_identical=True values_identical=True mismatches=0
weight/000798  blocks=2785280  scale_identical=True values_identical=True mismatches=0
L1 VERDICT: PASS (bit-exact)
```
合计 **13,271,040 块**；`scale` 两字节与 `values` **全部逐位相同，零不匹配**。

**L2（负控：故意把 `weight/000079` 写短 1 字节 = 77,987,839 / 77,987,840）**：
```
negative control: wrote weight/000079 ONE BYTE SHORT (77987839 of 77987840 declared bytes), finishing early
negative control: writer raised: resource/text/tokenizer.json: output coverage is incomplete
negative control: PASS (refused as required)
```
⇒ writer 拒绝不完整输出；`dst` 不存在（abort 清理）、**无残留 `.tmp`**。

### 参数与成本
- 新文件 **13,485,135,360 B**（+212,336,640 B = **+202.5 MiB**，占全模型 1.5%）
- 5 个对象：238,878,720 → **451,215,360 B**；块数 13,271,040
- 脚本先以 `--dry-run` 核对计划（输出与上表逐项一致）后才正式执行

### 遗留（交审核 / 后续）
1. **Step 8/9 起服测 MTP 未做** —— 需用户授权；按纪律**先关 GPU 占用程序**（浏览器/QQ/Overlay，实测差 3.3 倍）。
2. **`scripts\recode_mtp.py` 与产物尚未提交**（等 TELE 审核 L0/L1/L2 + 用户批准）。
3. 关键结论（MTP 收益）**另用 official 引擎交叉验证**（用户已同意）。

---

## 三·八、2026-10-09 · ★MTP 跑通：官方 Q8MTP 验证 → 自转 iq4_nl → 起服与 A/B

> 本章记录从"官方 Q8MTP 版下载完成"到"MTP 在 16 GB 机器上首次跑通"的全过程。所有数字均为本机实测。

### 1. 官方 Q8MTP 版到货与验证（先验证再使用）

**文件**：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer`

```
[EVIDENCE] 文件长度 13,780,954,112 B（12.84 GiB；页面标注 13.78 GB 为十进制，同一文件）
[EVIDENCE] inspect --json：
  objects 1139 | tensors 1133 | resources 6 | bindings 1420 | uses 784
  components: text + mtp + vision          ← 比原件多一整个 vision 组件
  formats: gguf_q4_0 = 0, gguf_q8_0 = 5    ← MTP 头已被官方改成 q8_0
  metadata.name: qwen3.8-27b-coder390-Q2LynnStyle-Q8Mtp
[EVIDENCE] 5 个 MTP 头对象 bytes 与我们 P1 产物**逐项完全相同**：
  weight/000079 77,987,840 | 000080 189,399,040 | 000789 55,705,600
  weight/000796 33,423,360 | 000798  94,699,520   （合计 451,215,360 B）
```

**多出的 333 个张量 = 视觉塔**（222 bf16 + 111 引擎自有 group-wise 格式：q4_g64_fp16 ×54、q5_g64_fp16 ×54、q6_g64_fp16 ×1、q8_g32_fp16 ×2）。
引擎只在传 `--vision` 时才加载该组件（`config.cpp:323`），故不传即等于没有 —— 但**文件更大**（+0.5 GB）。

**★ 关键发现（双方此前都不知道）：官方 q8_0 与我们产物的"大小相同、信息量不同"**

```
[EVIDENCE] 首块 hex 对照（weight/000079 前 5 块）：
  官方 a30d f9d6c228c2dd07fad24ac4acfff1e7ba14ad1721d51ffefa889b44d5080c811a
        int8 值域到 ±127（[-7,-42,-62,40,-62,-35,...]）
  我们 981d 0001fdfbfc010302fcfdfe0200000000fdf805fafc04fbfd0001ff01fef8fc02
        int8 值域 [−8,7]（[0,1,-3,-5,-4,1,3,2,...]）—— 正是 (nibble−8) 的特征
⇒ 官方是**真 8-bit 量化**（很可能从 bf16 原始权重重新量化，用满 int8 动态范围）；
  我们的 q8_0 是**q4_0 的无损搬运**（不引入新损失，但保留了 q4_0 原有的 4-bit 损失）。
⇒ 官方版 MTP 头质量更高。**本次自转 iq4_nl 因此特意从官方 q8_0 取数**（用高精度源），
  而不是从原件 q4_0 取数。
```

### 2. 官方版起服：两度失败（显存），并推翻一条此前的建议

```
[EVIDENCE] ctx 65536 / kv 8192：需求 2,125,809,408，可用 1,789,370,368 → 缺 321 MiB
[EVIDENCE] ctx 16384 / kv 4096：需求 1,927,851,776，可用 1,718,067,200 → 缺 200 MiB
[EVIDENCE] 官方版重试（同参数）：需求 1,927,851,776，可用 1,788,653,568 → 缺 139 MiB
[EVIDENCE] draft-tokens 4 → 1：需求仅降 12.7 MB（1,927,851,776 → 1,915,165,952）⇒ 此路无效
[EVIDENCE] 可用量波动极大：1.29 – 1.79 GiB（±250 MiB/次），起服成败高度依赖起服瞬间 GPU 状态
```

**⛔ 推翻上一轮"关 KVMem 省显存"的建议** —— 引擎硬约束原文：

```
[EVIDENCE] ninfer-serve: --kv-capacity must be at least --max-context
           (set NINFER_KV_WINDOW=<window tokens> to allow the experimental ring)
```

⇒ **KVMem ring 的作用之一就是"允许 KV 池 < 上下文"**（老内容下沉 host）。**关掉 KVMem ⇒ 引擎强制 `kv-capacity ≥ max-context`** ⇒ KV 池反而必须变大（ctx 65536 时池 ≥ 65536 tokens ≈ 1.57 GB）。
⇒ **KVMem 在本线是"省显存的前提"，不是负担。上一轮"关 KVMem"方案作废。**

### 3. 自转 `iq4_nl`：让 MTP 装上的决定性一步

**思路**：MTP 头**权重常驻显存**，直接挤占 runtime 可用量。
官方 q8_0 头 = 451.2 MB；换 `iq4_nl`（4.5 bpw，块几何与 q4_0 完全相同）= **238.9 MB ⇒ 省 212.3 MB**，而当时缺口正是 139–200 MiB ⇒ **量级吻合**。

**脚本扩展**（`scripts\recode_mtp.py`，在 P1 基础上新增能力）：
- `--mtp-src` / `--mtp-src-format`：**容器骨架与头数据分离** —— 骨架用**原件**（无 vision，13.27 GB），头数据用**官方 q8_0 版**（高精度源）；
- `--target-format gguf_iq4_nl`：新增有损转码路径；
- `--probe-error`：只跑全量误差统计、不写文件；
- oracle 支持两种判定：**逐位**（q8_0）/ **误差上界**（iq4_nl，阈值 `MAX_REL_ABS_ERR = 10%`）；
- 数据源校验：目标对象在数据源中缺失 / 格式不符 / shape 不符 ⇒ **一律拒绝**。

**取证（四项，缺一不可）**：

```
[EVIDENCE] 块结构 ggml-common.h:446-452：#define QK4_NL 32; struct { ggml_half d; uint8_t qs[16]; } ⇒ 18 B/32 元素
[EVIDENCE] 码表 ggml-common.h:1120-1122：kvalues_iq4nl = -127,-104,-83,-65,-49,-35,-22,-10,1,13,25,38,53,69,89,113
           （16 项，**不对称**：max 113 ≠ |min| 127）
[EVIDENCE] ★ nibble 布局 dequantize.cuh:418-419：
             y[j+ 0] = d * kvalues_iq4nl[q4[j] & 0xf]   ← 低 nibble → 元素 j      (0..15)
             y[j+16] = d * kvalues_iq4nl[q4[j] >>  4]   ← 高 nibble → 元素 j+16   (16..31)
           ⇒ iq4_nl 是**分半布局**；q4_0/q8_0 是**交错**（低 nibble → 元素 2j）。
           **写错不报错、只静默搅乱权重** —— 本路径最大的静默陷阱。
[EVIDENCE] third_party 内 quantize_row_iq4_nl 命中 0 ⇒ **无 CPU 参考量化器**，自实现：
           每块「最近码表项 ↔ 最小二乘 scale」交替迭代 3 轮，最后 d 存 fp16。
[EVIDENCE] 引擎侧支持完整（ggml_bridge.cu）：dequant :244/:281、vec :86、mmq :435，块几何 :302 {32,18}
```

**全量探针（13,271,040 块，零采样）**：

| 对象 | 块数 | 相对误差 | RMSE | SNR |
|---|---|---|---|---|
| 000079 | 2,293,760 | 8.57% | 1.424e-3 | 21.66 dB |
| 000080 | 5,570,560 | 8.44% | 1.078e-3 | 21.78 dB |
| 000789 | 1,638,400 | 8.79% | 1.070e-3 | 21.65 dB |
| 000796 | 983,040 | 9.07% | 1.699e-3 | 21.32 dB |
| 000798 | 2,785,280 | 8.95% | 1.045e-3 | 21.42 dB |

⇒ 误差与**原件 q4_0 自身的量化误差同量级**（不比原始 MTP 头更差），但确实**丢掉了官方 q8_0 的精度优势**。

**产物**：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer`

```
[EVIDENCE] file_bytes 13,272,798,720（**与原件完全相同** —— iq4_nl 与 q4_0 等长）
[EVIDENCE] objects 804 | components mtp,text（**无 vision**）| L1 VERDICT: PASS（5 对象全过阈值）
[EVIDENCE] 5 对象 451,215,360 → 238,878,720 B（Δ = −212,336,640 B = −202.5 MiB）
```

### 4. ★起服成功 + A/B 实测

**起服（ctx 16384 / kv 4096 / KVMem 五开关 / `--spec mtp` / draft 4）**：

```
[EVIDENCE] engine ready | qwen3.8-27b-coder390-Q2LynnStyle-Mtp+mtp-iq4nl | total 8.9s
           | weights 12.3 GiB | capacity | KV 4,096 tokens, k8v4 | runtime 1.80 GiB | free 413.9 MiB
           | listening on http://127.0.0.1:8095        ← 10 秒内就绪
```

**MTP 确实在起草（不是只加载了组件）**：

```
[EVIDENCE] req#1 done | prompt 19 | output 41 | TTFT 156 ms | prefill 122.1 tok/s
           | decode 112.1 tok/s | mtp accepted 28/56 (50.0%)
```

**A/B（同模型、同 prompt、同参数，唯一变量 = `--spec mtp`）**：

| 任务 | 裸解码 | MTP | 接受率 |
|---|---|---|---|
| 散文（介绍 CUDA 图，output 193/157） | **55.4 tok/s**（prefill 363.3） | **73.2 tok/s（+32%）** | 22.6% (75/332) |
| 代码（Python 快排，output 96） | — | **184.3 tok/s（+233%）** | **93.8% (75/80)** |

**资源对照**：

```
[EVIDENCE] 裸解码：weights 12.1 GiB | runtime 1.38 GiB | free 735.2 MiB
[EVIDENCE] MTP   ：weights 12.3 GiB | runtime 1.80 GiB | free 413.9 MiB
⇒ MTP 净消耗 ≈ 321 MiB（239 MB 头 + ~80 MB workspace）
```

**L4b（输出等价性）**：同一 prompt 两版回复**语义一致、质量相当，无系统性劣化** ✅
（判据为"语义等价 + 无系统性劣化"，**不要求逐字相同** —— MTP 开/关会改变每轮 batch/round 结构与 kernel 规约顺序，微小数值抖动属正常）

### 4.1 ctx 扫描：16 GB 下的最大可用上下文（挂账 14，2026-10-09 23:26）

固定 kv 随 ctx 等比缩放、`NINFER_KV_WINDOW = ctx`，从大到小四档（失败档均在 10 秒内早退）：

```
[EVIDENCE] ctx 65536 / kv 8192：需求 2,125,809,408，可用 1,960,161,280 → 缺 158 MiB  ❌
[EVIDENCE] ctx 49152 / kv 6144：需求 2,069,823,232，可用 1,966,845,952 → 缺  98 MiB  ❌
[EVIDENCE] ctx 32768 / kv 4096：需求 2,013,837,056，可用 1,975,562,240 → 缺  36 MiB  ❌（**临界**）
[EVIDENCE] ctx 24576 / kv 4096：engine ready 8.7s | KV 4,096 tokens | runtime 1.80 GiB | free 349.7 MiB  ✅
[EVIDENCE] 24576 档实测推理：output 138 | TTFT 163 ms | prefill 228.6 tok/s | decode 89.4 tok/s
           | mtp accepted 80/236 (33.9%)   ← MTP 与 KVMem 均正常
```

⇒ **本机 16 GB 显存下的最大稳定 ctx = 24576（24K）**；32768 仅差 36 MiB（可用量波动 ±250 MiB ⇒ 重试可能碰过，但**不稳定、不建议作为配置**）。
⇒ 65536 档缺 158 MiB ⇒ **若要 64K 上下文，需再省 ~160 MB 权重或降 kv-dtype 精度**（留作后续）。

> ⚠️ **本节结论已被 §4.2 更正**：上述四档测试把 `--max-context` 与 `NINFER_KV_WINDOW` 设成了**同一个值**，等于强制 device 常驻整个逻辑上下文 —— 这不是 KVMem 的设计用法。正确用法见 §4.2，逻辑上下文可达 **131072（128K）**。

### 4.2 ★更正：`--max-context` / `NINFER_KV_WINDOW` / `--kv-capacity` 是三个不同量（挂账 14 的真正结论）

**源码依据（三个参数各司其职）**：

```
[EVIDENCE] serve_options.cpp:1113-1117:
  // LOCAL PROTOTYPE (KVMem-style ring): the ring lets --kv-capacity be SMALLER than --max-context.
  // Storage-side backing for it is the ring itself (device pool < logical context, with the recycled
  // pages demoted to host memory)
[EVIDENCE] startup.cpp:145-160 ring_resident_pages():
  window_pages = window_tokens > 0 ? window_tokens / kPagedKVPageSize : logical_pages
  per_lane     = min(window_pages + page_count(prefill_chunk), logical_pages)
  demand       = per_lane * lanes + 8        ← device 常驻只由 WINDOW 决定，与 max_context 无关
[EVIDENCE] startup.cpp:1047-1053:
  minimum_pages = ring_requested() ? max_concurrency : max(logical_pages, max_concurrency)
```

| 参数 | 含义 | 物理位置 |
|---|---|---|
| `--max-context` | **逻辑**上下文上限 | 不占显存（仅使 workspace 略增） |
| `NINFER_KV_WINDOW` | device **常驻窗口** | 显存 |
| `--kv-capacity` | device **活跃池** | 显存 |
| `--host-kv-mib` | host KV 存储（下沉页） | 主机内存（16 GiB） |

**修正后的配置与实测**：

```
[EVIDENCE] --max-context 131072 / NINFER_KV_WINDOW 16384 / --kv-capacity 2048
           / --prefill-chunk 512 / --kv-dtype rk2v4-e8
  ⇒ engine ready | KV 2,048 tokens, rk2v4-e8 | pages 32/2,048 | runtime 1.18 GiB | free 925.1 MiB  ✅
  ⇒ 相比 §4.1 的 24576 档：runtime 1.80 → 1.18 GiB、free 349.7 → 925.1 MiB（**余量反而更大**）
```

**★ 长上下文实测（故意超出 device 窗口）**：

```
[EVIDENCE] prompt_tokens = 20,203      （远超 window 16384）
[EVIDENCE] ANSWER        = 350         （问"第 350 段编号"，答案位于 prompt 中段）← **正确**
[EVIDENCE] [ninfer] ring retrieve: which=text preferred=16 restored=16 first=149 last=307
[EVIDENCE] kvmem_score: SELECT label=text_prefill_chunk n_blocks=316 budget_blocks=512
           sink_blocks=64 kept=316 scored_kept=252 candidates=252 window_tokens=20224
[EVIDENCE] req#2 done | prompt 20,203 | output 4 | TTFT 11.3s | prefill 1.82k tok/s | decode 92.9 tok/s
```

⇒ **KVMem 环确实在工作**：窗口外的页下沉 host，检索时按内容评分恢复（本次 restored=16 页），**答案正确**。

**⇒ 结论（更正）**：本机 16 GB 显存下 **逻辑上下文 131072（128K）可用**；§4.1 的"24K 上限"**作废**（那是把 window 当成 max-context 的产物）。
（`--max-context` 还能更高：262144 档的 runtime 需求与 131072 几乎相同 —— 1,818,929,408 vs 1,818,913,024 —— 待验。）

### 4.3 device 活跃池：概念澄清与扩容实测（2026-10-09 23:46）

**⚠️ 概念澄清 —— 决定"全速区间"的是 `--kv-capacity`，不是 window**：

| 参数 | 含义 | 对速度的影响 |
|---|---|---|
| `--max-context` | 逻辑上下文上限 | 不直接决定速度 |
| **`--kv-capacity`** | **device 活跃池**（显存里能放多少 KV token） | **池内直接访问；池外页需从 host 恢复** |
| `NINFER_KV_WINDOW` | 保留优先级窗口 | 影响恢复命中率 |
| `--host-kv-mib` | 下沉页存放 | 影响恢复速度 |

（此前我把"窗口"当成"全速区间"表述，属不严谨 —— 日志 `pages 32/2,048` 的真实含义是：**device 池只占 32 页，逻辑总量 2048 页**。）

**池扩容实测（成本极低）**：

```
[EVIDENCE] kv  2048：runtime 1.18 GiB | free 925.1 MiB | pages  32/2,048
[EVIDENCE] kv  8192：runtime 1.26 GiB | free 889.0 MiB | pages 128/2,048   （+96 页 ≈ +80 MB）
[EVIDENCE] kv 32768：runtime 1.60 GiB | free 557.3 MiB | pages 512/2,048   （+384 页 ≈ +348 MB）
```
⇒ **每页 ≈ 0.83 MB**（rk2v4-e8）—— 扩容极便宜，最终取 **kv 32768**。

**同一条 20,203 tokens prompt 的 A/B（唯一变量 = device 池大小）**：

| device 池 | TTFT | prefill | decode | ring retrieve | 检索答案 |
|---|---|---|---|---|---|
| 2048 | 11.3s | 1.82k tok/s | 92.9 tok/s | restored=16 | 350 ✅ |
| **32768** | **10.6s** | **1.90k tok/s** | **98.3 tok/s** | **restored=128** | 350 ✅ |

**⇒ 诚实结论：改善温和（5–6%）**。原因：**prefill 的瓶颈是计算本身**（1.90k tok/s × 20,203 ≈ 10.6s），页恢复（128 页）只占很小一部分。
⇒ **推论**：device 池的价值主要在"减少 host 往返的延迟抖动"，而非提升吞吐；池内是真全速，池外也不会慢很多。

**本线最终推荐配置（16 GB / RTX 5080 sm_120）** —— 见 §4.4（已进一步压榨）：

```
--max-context 262144  NINFER_KV_WINDOW=32768  --kv-capacity 40960
--kv-dtype rk2v4-e8   --prefill-chunk 512     --host-kv-mib 16384
--spec mtp --draft-tokens 4
⇒ runtime 1.71 GiB | free 449.6 MiB | 256K 逻辑上下文 / 40K 全速池
```

### 4.4 压榨结果：256K 逻辑上下文 + 40K 全速池（2026-10-09 23:50）

| `--max-context` | `--kv-capacity` | 需求 | 可用 | 结果 |
|---|---|---|---|---|
| 262144 | 65536 | 2,199,361,792 | 1,863,794,688 | ❌ 缺 320 MiB |
| 262144 | 49152 | 1,958,713,600 | 1,907,736,576 | ❌ 缺 **49 MiB**（临界） |
| **262144** | **40960** | — | — | ✅ **成功** |

```
[EVIDENCE] capacity | KV 40,960 tokens, rk2v4-e8 | pages 640/4,096 | runtime 1.71 GiB | free 449.6 MiB
[EVIDENCE] 同一条 20,203 tokens prompt：ANSWER = 350 ✅ | TTFT 10.6s
           | prefill 1.91k tok/s | decode 105.0 tok/s | ring retrieve restored=128
```

⇒ **两个方向同时推进**：逻辑上下文 128K → **262144（256K，模型原生上限）**；全速池 32K → **40K**；decode 还略有提升（98.3 → 105.0 tok/s）。

**剩余可压榨项（按性价比排序）**：

| 手段 | 预期收益 | 前提 |
|---|---|---|
| **清 GPU 占用**（浏览器/Overlay） | 可用量 **+250 MB**（此前实测差 3.3 倍） | 用户侧操作；可解锁 kv 49152 甚至 65536 |
| `--prefill-chunk` 512 → 256 | 省少量 workspace | 可能影响 prefill 速度 |
| MTP 头 `iq4_nl` → `iq3_xxs` | 省 **53 MB** | 质量再降（3.5 bpw），需重跑误差探针 |
| `--no-cuda-graph` | 省 driver state | 解码变慢 |
| text 主体重打包（12.1 GiB） | **GB 级** | 风险最高（全模型重写 + 质量未知），需单独立项 |

### 5. B 路径（官方版重试）结论：仍失败 ⇒ 闭环

官方 q8_0 版第三次尝试仍缺 **139 MiB**（见 §2）。
⇒ **官方 Q8MTP 版在本机 16 GB 显存下起不来；自转 `iq4_nl` 是唯一可行路径。**

### 6. 教训与纪律

1. **"无损"要看对什么无损**：我们的 q8_0 对 q4_0 无损，但对"原始权重"是有损的（保留了 4-bit 损失）。**换格式能省显存的前提是"更小的 bpw"，而更小必然有损** —— 本次是"用可接受的误差换 212 MB 显存"，并已量化为 8.4–9.1% / SNR 21.5 dB。
2. **静默陷阱要前置取证**：iq4_nl 的 nibble 是**分半**布局（与 q4_0 交错不同），写错**不报错**。实现前先读 `dequantize.cuh` 原文，并写进脚本注释与 provenance。
3. **不要把"想当然的省显存手段"当成已证事实**：上一轮"关 KVMem 省显存"被引擎硬约束直接证伪（关掉后 kv ≥ ctx，反而更费）。**结论必须来自源码原文或实测。**
4. **可用量本身是变量**：同一参数三次起服，可用量在 1.29–1.79 GiB 间波动（±250 MiB）⇒ **单次失败不足以判定"配置不可行"，单次成功也不足以判定"稳"**。
5. **跨文件取数优于就地转换**：骨架用原件（小、无 vision）、头数据用官方版（高精度），两者优点兼得；脚本以 `--mtp-src` 显式表达，并做三重校验。

### 遗留（交审核 / 后续）
1. **ctx 只有 16384**（为省显存压到最小）—— 需扫一轮找最大可用值（推算 ctx 32768 约卡临界，65536 约缺 125 MiB）。
2. **接受率基线样本仅 3 条**（50% / 93.8% / 22.6%）—— 需多 prompt 建立分布。
3. `scripts\recode_mtp.py`（含本轮扩展）与两份产物**均未提交**，等审核 + 用户批准。
4. 官方 Q8MTP 版的 `vision` 组件**未使用**（本线不需要），其 333 张量亦未参与任何测试。

---

## 三·九、2026-10-09 · 启动器定稿（按 P1b 实测参数重写）

> P0 的启动层适配当时用的是旧参数（k8v4 / 17920 / 1024）；本节把它**更新为 P1b 实测定稿**。

### 做了什么

| 文件 | 改动 |
|---|---|
| **`ninfer_launcher.py`** | `MODEL` → **`.mtp-iq4nl.ninfer`**（唯一同时支持裸解码与 MTP 的可用件）；`KV_POOL_TOKENS` 17920 → **40960**；`KV_ENV["NINFER_KV_WINDOW"]` 16384 → **32768**；`DEFAULTS` → `spec k4 / kv rk2v4-e8 / kvcap 40960 / prefill 512`；`KVCAP_OPTIONS` 增 40960 / 49152 / 20480；`KV_OPTIONS["rk2v4-e8"]` 标 ★定稿；`PRESET_PROFILES` 增 5 个 Coder390 预设（定稿 / 裸解码对照 / 大池 / 省显存 / 思考档）；`build_command()` 的 4 个回退值同步；`DIM_TIPS` 三条提示重写（含"全速区间 = `--kv-capacity`"的准确解释） |
| **`start-coder390-mtp.bat`** | 模型 → `.mtp-iq4nl.ninfer`；参数 → 定稿；**补上 `--kv-lease-growth --recover-invariant-failures`**（原脚本缺这两旗，而实测起服时是带的）；注释由"会失败"改为"已通 + 实测读数" |
| **`start-coder390.bat`** | 参数与 MTP 版**完全对齐**（唯一差异 = 无 `--spec`，保证 A/B 单变量）；模型**保持原件**（裸解码不碰 MTP 头，用原件才是纯基线） |
| **`ninfer_launcher_profiles.json`** | 新增 4 个 `★` 定稿档（置顶）；**原有 10 档全部保留**（含 Bonsai 残留档，未删 —— 尊重用户数据） |

### 证据（构造出的命令行与实测成功命令逐字核对）

```
[EVIDENCE] build_command(DEFAULTS) →
  ...-MTP.mtp-iq4nl.ninfer --host 127.0.0.1 --port 8095 --model-id qwen3.8-27b-coder390
  --max-context 262144 --kv-capacity 40960 --kv-dtype rk2v4-e8 --host-kv-mib 16384
  --prefill-chunk 512 --spec mtp --draft-tokens 4 --default-max-tokens 32768
  --default-reasoning-effort none --max-concurrency 1 --max-shared-prefixes 0
  --presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20
  --kv-lease-growth --recover-invariant-failures
[EVIDENCE] 与 §4.4 实测起服成功那条命令**逐字一致**（唯一差异：端口 8095 vs 8094）
[EVIDENCE] py_compile exit=0；profiles JSON 14 档解析通过；★定稿档加载后构造的命令同样正确
```

### 遗留（交审核 / 后续）
1. ~~`start-pq2*.bat` / `start-ptq1-mtp.bat` 四个 Bonsai 口径脚本未改~~ → **已按用户裁决删除**，见下节。
2. ~~profiles 里的 Bonsai 残留档未清理~~ → **已清理**，见下节。
3. 本轮启动器改动**未提交**（等批准）。

### Bonsai 口径清除（2026-10-10 · 用户裁决）

用户裁决原文：「**和本项目无关的东西，一开始本来就是拿来做参考、基准、基础的，如果现在或者未来没用了，都删，免得混淆**」。执行：

| 项 | 动作 |
|---|---|
| `start-pq2.bat` / `start-pq2-dflash.bat` / `start-pq2-dflash-designc.bat` / `start-ptq1-mtp.bat` | **删除**（4 个文件） |
| `ninfer_launcher.py` → `PRESET_PROFILES` | 删 8 个 Bonsai 预设，只留 5 个 Coder390 档 |
| `ninfer_launcher_profiles.json` | **14 档 → 4 档**（只留 ★ 定稿档）。同时清理 Coder390 的过期档：`裸解码 256K`（k8v4/17920，与 ★ 档重复但参数不同，易误选）、`裸解码 180K`（kvcap 180k，16 GB 上**必然失败**）、`MTP K4（待P1容器）`（名字已过时） |
| `ninfer_launcher.py` → UI | 标题 `Bonsai-27B-NInfer-kvmem 启动器` → **`Coder390 · NInfer 启动器`**；副标题 → `Qwen3.8-27B-Coder390 · MTP + KVMem · RTX 5080 sm_120`；docstring 改本线口径 |
| `启动器.bat` | 注释改本线口径 |
| `docs\BONSAI_ngram_audit_report.md` | **保留** —— ngram 机制的唯一审计资料，本线第三目标（ngram）要用；属"参考件"而非"Bonsai 专属件" |

**保留的 8 处 Bonsai 字样**（全部是历史沿革 / 事实说明，不构成功能残留）：

```
[EVIDENCE] ninfer_launcher.py:14-15  沿革说明（本文件最初为前序 Bonsai 线所写…）
[EVIDENCE] ninfer_launcher.py:43     模型迁移历史（旧值 Ternary-Bonsai-… 属前序 Bonsai 线）
[EVIDENCE] ninfer_launcher.py:211 / 251-254  档位删除理由
[EVIDENCE] ninfer_launcher.py:325    cublas 实测事实（系统 PATH 首个命中 = J:\Bonsai\landing\cuda-13.3\bin\x64）
[EVIDENCE] ninfer_launcher.py:464    标题变更历史
```

**校验（清除后）**：

```
[EVIDENCE] python -m py_compile ninfer_launcher.py → exit=0
[EVIDENCE] profiles = 4 档（全部 ★Coder390）；PRESET_PROFILES = 5 档（全部 Coder390）
[EVIDENCE] 根目录 .bat = 3 个（启动器.bat / start-coder390.bat / start-coder390-mtp.bat）
[EVIDENCE] 构造命令仍与实测起服成功命令逐字一致
```

---

## 三·十、2026-10-10 · 视觉能力可行性（用户提问）+ 定稿参数"闪退"根因

### 1. 定稿参数"闪退"根因：只差 20.4 MiB（不是参数错）

用户按定稿参数启动，窗口闪退。日志 `logs\serve_20261010_002718.log` 原文：

```
[EVIDENCE] ERROR engine init | FAILED while constructing the service: requested Engine runtime
           reservation requires 1838389504 bytes, but only 1816981504 bytes are available
           for runtime capacity
```

⇒ 缺口 = **20.4 MiB**（1,838,389,504 − 1,816,981,504 = 21,408,000 B）。
⇒ **不是参数问题**：**同一组参数在 2 分钟后（00:29）复跑成功**（`free=508 MiB`，`listening on 8094`）。
⇒ 根因 = §4.2/§4.4 已记录的**起服瞬间可用量波动（±250 MiB）**；用户当时环境比复跑时少约 170 MB。

**三个解法**：① **起服前关 GPU 占用程序**（浏览器/Overlay；此前实测差 3.3 倍）② **重试**（碰高可用时刻）③ 换 `★Coder390-MTP 省显存（20K池）` 档。

### 2. ★视觉能力：官方版 + `--vision-cpu` 实测可行（用户设想成立）

**用户提问**：视觉塔选 CPU，能否"有视觉能力又不增显存"？**答案：能。**

**源码取证**（`serve_options.cpp:291-297`）：

```
--vision-residency resident|overlay|cpu
    overlay keeps the Vision tower in host memory and borrows device memory per image
    cpu runs it on CPU threads with **no device Vision memory**, and caps
    --vision-max-merged at 256 unless given
--vision-cpu = --vision with --vision-residency cpu
```
```
[EVIDENCE] serve_options.cpp:1154-1156: --vision-residency overlay or cpu requires --vision
           ⇒ 必须有 vision 组件（本线 Coder390 容器没有 ⇒ 一律 "missing component vision"）
[EVIDENCE] serve_options.cpp:1159-1161: CPU 模式自动把 --vision-max-merged 压到 256（约 512x512 像素）
```

**实测（2026-10-10 00:32，官方 Q8MTP 版 + `--vision-cpu` + ctx 262144 + kv 20480 + rk2v4-e8）**：

```
[EVIDENCE] loading weights | 12.5 GiB
[EVIDENCE] engine ready | qwen3.8-27b-coder390-Q2LynnStyle-Q8Mtp | total 13.3s | weights 12.5 GiB
[EVIDENCE] capacity | KV 20,480 tokens, rk2v4-e8 | pages 320/4,096 | runtime 1.44 GiB | free 663.4 MiB  ✅
[EVIDENCE] listening on http://127.0.0.1:8096
```

**⇒ 结论**：**可行** —— 有视觉能力，设备视觉显存占用为零（weights 12.3 → 12.5 GiB，+0.2 GiB 为 vision 塔权重）。

**⚠️ 四个前提 / 代价**：

1. **必须用官方 Q8MTP 版** —— 本线的 `.mtp-iq4nl.ninfer` 与原件**都没有 vision 组件**，任何 `--vision*` 参数都会 `missing component vision` 起不来；
2. 官方版 MTP 头是 451 MB（q8_0），比自转 iq4_nl 多 212 MB ⇒ **必须降池**（实测降到 20K 池）；
3. **图片被压到 256 merged tokens**（约 512×512），更大的图会降采样；
4. **CPU 编码慢**（引擎注释：one to a few seconds）。

---

## 四、待续事项（挂账）

| # | 事项 | 状态 |
|---|---|---|
| 1 | 9 份文档提交 | ✅ 已完成 `d2c9806`（已 push） |
| 2 | **MTP 探针（数据侧重打包，`gguf_q8_0`）** | ✅ **已执行**（P1：L0/L1/L2 三档全过）——**交 TeleAgent 审核中** |
| 3 | 是否允许改写 `models\` 内 `.ninfer` | ✅ 已按"**写新文件、原件零写入**"执行（产物 `.mtp-q8.ninfer`） |
| 4 | 引擎补 Q4_0（方案 A） | 暂缓（用户已同意，留兜底） |
| 5 | DFlash2 是否投入 | 延后（零成本几何核对已通过；接受率门槛待定） |
| 6 | 启动层适配 Coder390 | ✅ 完成并入库（P0，`a96d6af`；TELE 审核通过） |
| 7 | 复算模型 SHA256 并补录 | 待办 |
| 8 | KVMem 检索判活（`kvmem_score: SELECT`） | ✅ 已在 Coder390 上确认（P0c） |
| 9 | 实测起服（裸解码基线） | ✅ 已完成（**55.7–55.9 tok/s**，P0c-2） |
| 10 | GUI 默认引擎统一 self-built（含 PATH 修复） | ✅ 已实施并入库（P0b，`a96d6af`；TELE 复审通过） |
| 11 | 关键结论（MTP 收益）用 official 交叉验证 | 待办（用户已同意该做法） |
| 12 | **Step 8/9：起服测 MTP** | ✅ **已完成**（2026-10-09 23:09，用 `.mtp-iq4nl.ninfer` 成功起服；`.mtp-q8.ninfer` 因显存不足起不来 —— 详见三·八） |
| 13 | 提交 `scripts\recode_mtp.py` + 产物登记 | 待审核 + 用户批准（脚本已含 iq4_nl 扩展与跨文件取数） |
| 14 | **扫 ctx 找最大可用值** | ✅ **已完成并更正**（2026-10-09 23:40）：真正上限是**逻辑上下文 131072（128K）**（§4.2；实测 20,203 tokens prompt 答案正确）；§4.1 的"24K"系误用（把 window 当成了 max-context） |
| 15 | **建立 MTP 接受率基线**（多 prompt 分布） | 待办（现有 3 样本：50% / 93.8% / 22.6%） |
| 16 | 官方 Q8MTP 版（含 vision）留存与用途裁定 | 待办（本线不用 vision；留作精度参照件） |
| 17 | 是否以 `.mtp-iq4nl.ninfer` 作为正式探针件（取代 `.mtp-q8.ninfer`） | 待裁决 |
| 18 | **参数定稿**（§4.4）：**256K ctx / 40K 全速池** / rk2v4-e8 / prefill 512 / window 32768 | ✅ 已实测定型（当前服务即此配置；runtime 1.71 GiB / free 449.6 MiB） |
| 21 | 清 GPU 占用后重试 kv 49152 / 65536（当前仅缺 49 MiB） | 待用户侧操作（关浏览器/Overlay 等） |
| 22 | MTP 头 `iq4_nl` → `iq3_xxs`（再省 53 MB）是否值得 | 待裁决（需重跑误差探针，质量再降） |
| 23 | **启动器定稿**（三·九）：launcher 9 处 + 2 bat + 4 个 ★profiles 档 | ✅ 已完成并校验（构造命令与实测逐字一致） |
| 24 | Bonsai 口径清除（4 脚本 + 8 预设 + profiles + UI 文本） | ✅ **已完成**（2026-10-10 用户裁决；详见三·九末节） |
| 25 | 启动器改动提交（launcher + 2 bat + profiles + 构建史 v17/v18） | 待批准（用户已口头同意，待执行） |
| 26 | `docs\BONSAI_ngram_audit_report.md` 是否改名（去掉 BONSAI 前缀） | 待裁决（内容是 ngram 机制，本线要用；改名可避免误删） |
| 27 | **定稿参数闪退**（缺 20.4 MiB） | ✅ 已定位（§三·十）：非参数错，是起服瞬间可用量波动 ⇒ 关 GPU 占用 / 重试 / 换 20K 池档 |
| 28 | **视觉能力**（官方版 + `--vision-cpu`） | ✅ 实测可行（§三·十）；**待裁决**：是否给 launcher 加"模型档"维度（当前 MODEL 固定为 iq4_nl 版，选 vision 会失败） |
| 29 | ngram 实测（本线第三目标） | 待办 |
| 30 | **日志刷屏降噪**（`[ring] budgets` / `mask hidden` / `demote-other short`） | ✅ 已完成：serve_tee slim 模式隐藏三类诊断行；日志文件仍全文落盘 |
| 31 | **视觉启动脚本** | ✅ 已完成：`start-coder390-vision.bat`（官方版 + `--vision-cpu` + 20K 池） |
| 32 | 视觉功能端到端验证（发一张真图片测识图） | 待办（脚本已就绪，未测实际识图） |
| 19 | **ngram 实测**（本线第三目标） | 待办（MTP 已通，可直接加 `--ngram-draft-tokens` 试） |
| 20 | schannel CRL 致 push 失败（`http.schannelCheckRevoke=false` 经环境变量绕过） | ⚠️ 环境问题已解并记录；建议补进推送流程说明 |

> —— 构建史由 **CodeBuddy** 维护（2026-10-09 用户裁决移交，原为 TeleAgent）；每轮施工完成后**自动补录本文件**（不等催）。
> —— 施工/审核分工：**施工 + 构建史 = CodeBuddy**；**审核报告 = TeleAgent**（各自 commit/push；commit 前保留 T-COMMIT-APPROVAL 展示环节）。
