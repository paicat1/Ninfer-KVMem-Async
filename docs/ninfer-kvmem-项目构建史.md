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

## 四、待续事项（挂账）

| # | 事项 | 状态 |
|---|---|---|
| 1 | 9 份文档提交 | ✅ 已完成 `d2c9806`（已 push） |
| 2 | MTP 探针（数据侧重打包；探针格式 `gguf_q8_0`） | 待用户批准 P1 |
| 3 | 是否允许改写 `models\` 内 `.ninfer` | 待用户裁决（方案为**写新文件、不覆盖原件**） |
| 4 | 引擎补 Q4_0（方案 A） | 暂缓（用户已同意，留兜底） |
| 5 | DFlash2 是否投入 | 延后（零成本几何核对已通过；接受率门槛待定） |
| 6 | 启动层适配 Coder390 | ✅ 已完成（P0，本轮）——**交 TeleAgent 审核中** |
| 7 | 复算模型 SHA256 并补录 | 待办 |
| 8 | KVMem 检索判活（`kvmem_score: SELECT`）在 Coder390 上确认 | 待办 |
| 9 | P0 实测起服（裸解码基线读数） | 待用户双击 BAT，或授权 AI 起服 |
| 10 | GUI 默认引擎统一为 self-built（含 PATH 修复） | ✅ 已实施（P0b，用户批准）——**交 TeleAgent 复审中** |
| 11 | 关键结论（MTP 收益）用 official 交叉验证 | 待办（用户已同意该做法） |

> —— 构建史由 **CodeBuddy** 维护（2026-10-09 用户裁决移交，原为 TeleAgent）；每轮施工完成后**自动补录本文件**（不等催）。
> —— 施工/审核分工：**施工 + 构建史 = CodeBuddy**；**审核报告 = TeleAgent**（各自 commit/push；commit 前保留 T-COMMIT-APPROVAL 展示环节）。
