# 审核报告 · CodeBuddy 施工批（P1b 之后全量，2026-10-10）

> **审核方**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-10
> **审核范围**：CodeBuddy 自上次审核（P1b `c7521dd`）以来全部施工，覆盖提交 `be9625a / 17e2742 / 12d69df / ef58e14 / c5dd7c9 / 480245a / f244ef0 / 1f3cc5e / 0fc65f1 / a6338fa / eca2a8e / 5369e04 / eb8f7a3 / a38b5bd / 77c274f`（压榨定稿 / Bonsai 清除 / GUI 模型维度 / 视觉塔嫁接 / 定稿开思考 / 日志降噪 / bench 工具）
> **方式**：只读独立验证（不复述交付方结论；产物用独立 SHA/结构核验，命令行独立构造复跑）+ **视觉塔实机验证**（用户授权起服：20K/40K 双档 + 真实识图，2026-10-10 20:00–20:31）
> **分工遵循**：本报告由 TeleAgent 记录与提交；施工产物/构建史归 CodeBuddy（本次视觉验证数据交 CodeBuddy 补录构建史）。

---

## 〇、总体结论

**审核通过。** 6 项核心施工全部独立核验成立，无实质缺陷。两处如实披露（非阻塞）：

1. `build_command` 的 `think/tb` 防御性回退值仍为 `"none"`（L399-400）——但 DEFAULTS/PRESET 恒带 `high/16000`，实际不触发；仅当外部代码构造 combo 缺键时才会落到关思考，属防御兜底、非实际路径。
2. `serve_tee.py` 的 `is_kept_noise`（L44-47）把"8 字符以上纯数字/空格行"判为噪声隐藏——仅影响窗口显示、日志文件仍全文落盘，不伤数据。

---

## 一、逐项独立核验

### 1. ★视觉塔嫁接（`a38b5bd` + 产物，最高价值）

| 项 | 独立核验 | 结果 |
|---|---|---|
| 产物存在 | `.mtp-iq4nl.vision.ninfer` = **13,568,625,664 B**（2026/10/10 2:31） | ✅ 与构建史一致 |
| 结构 | 1139 objects / 1133 tensors / 6 resources / 1420 bindings / 784 uses / `mtp+text+vision` | ✅ |
| name 标记 | `…-Mtp+mtp-iq4nl+vision` | ✅ |
| **骨架半** | 804 对象与 iq4nl 骨架 **逐字节一致（独立 SHA-256）** | ✅ mismatched=0 |
| **graft 半** | 335 对象与官方 donor **逐字节一致** | ✅ mismatched=0 |
| 纯追加 | 无孤儿对象、无 stray 非 vision 权重、ID 命名空间 `weight/v*` 不冲突 | ✅ |
| 体积差 | prod − skel = 282.0 MiB（视觉塔），符合 | ✅ |

**审核方法**：独立脚本 `.temp/verify_graft.py`，不 import `graft_vision`，从 Artifact reader 对 1139 对象逐一 SHA-256 比对骨架/视觉塔两半。

#### 1.1 ★实机验证（2026-10-10 20:00–20:31，用户授权起服，TeleAgent 执行）

| 验证项 | 结果 | 证据 |
|---|---|---|
| **20K 池 + `--vision-cpu` 起服** | ✅ 成功（16s，weights 12.3 GiB，free 963.4 MiB） | `logs\serve_vision_cpu_test.log` |
| **40K 大池 + 视觉并存** | ✅ **成功**（干净环境：KV 40,960 tokens，runtime 1.72 GiB，free 898.4 MiB） | `logs\serve_vision_cpu_40k_clean.log` |
| 40K 首次失败复盘 | ⚠️ 非嫁接问题：GPU 被占用时 runtime 可用仅 0.81 GB < 需求 1.84 GB；**用户关闭占用程序后重试成功** | `logs\serve_vision_cpu_40k.log`（失败）→ `_clean.log`（成功） |
| **文字推理** | ✅ 正常（decode 75.9 tok/s，MTP 接受 27.3%，thinking 80/16,000） | 同上日志 `req#1 done` |
| **真实识图** | ✅ 准确描述测试图（"垂直彩色条纹渐变背景 + 层层嵌套同心圆环前景"） | 图像请求：prompt 316（含图像）、reasoning 221 + 可见回答 |
| 服务级证据 | ✅ `/v1/models` 返回 **`modalities: {"vision": true}`** | 实测响应 |

**结论**：嫁接产物完整可用 —— **视觉塔（官方）+ iq4_nl 小 MTP 头 + 40K 大池三者同时成立**（官方 Q8MTP 版只能 20K 池）。"嫁接省 212 MB → 转给 KV 池"的核心设计**实机闭环**。

### 2. GUI 模型维度 + 配对校验（`5369e04` + `77c274f`）

- `MODEL_OPTIONS/PATHS` 4 档（iq4nl / iq4nlvis / q8mtp / orig），**4 个模型文件全部存在** ✅
- `VISION_CAPABLE_MODELS = {iq4nlvis, q8mtp}`（L88）✅
- `validate()` 模型↔视觉配对告警（L360-366）：无视觉模型+开视觉 → 报"missing component vision"；有视觉+关 → 提示塔不加载 ✅（这正是用户踩的坑）
- `_apply_model_coupling()`（L720-738）：选 q8mtp 自动降池到 20480 并同步下拉 ✅；iq4nlvis 无自动降池（`MODEL_KVCAP_MAX` 不含 → 不臆造耦合），靠 validate 提示 ✅
- 视觉档构造命令实测：`q8mtp + --vision-cpu + kvcap 20480 + high/16000 + hemostat 两旗` ✅

### 3. 定稿改开思考（`0fc65f1`，用户裁决）

- `DEFAULTS`：`think=high, tb=16000`（L282）✅；`PRESET_PROFILES` 各档 `dict(DEFAULTS,…)` 继承，实际恒带 ✅
- profiles.json 5 档全部 `think=high/tb=16000` ✅
- 2 bat（mtp / nongram）+ 启动器构造命令均 `--default-reasoning-effort high --default-thinking-budget 16000` ✅
- **思考不占显存**：构建史三·十二取证（27 处 thinking_budget 命中无一处用于资源分配）成立 ✅

### 4. serve_tee 日志降噪（`1f3cc5e` + `a6338fa`）

- `is_diag_noise()`（L80-82）：精确匹配 `[ring] budgets / [ninfer] mask hidden / demote-other short` 三类 ✅
- `is_select()`（L60-61）：SELECT + ring retrieve 同段首末压缩 ✅
- **日志文件 L174 `log.write(raw)` 始终原文全文落盘**（不经过滤）→ 窗口精简不伤取证 ✅
- `bufsize=0` + Popen 管道边读边显示（防管道阻塞引擎）✅

### 5. 压榨定稿参数一致性（`be9625a`/`12d69df` 等）

- DEFAULTS：`ctx=256k / kvcap=40960 / kv=rk2v4-e8 / prefill=512 / spec=k4`，与 mtp.bat 实测命令**逐字一致** ✅
- `start-coder390*.bat`（mtp / 裸解码 / nongram）参数对齐、仅 spec/ngram/端口差异 ✅
- v14 修正（max-context≠window）与代码注释一致 ✅

---

## 二、覆盖度声明

- **P1 全查**：视觉塔嫁接（全量 1139 对象 + **实机起服/识图/大池并存**）、GUI 模型维度、定稿开思考、serve_tee 降噪、压榨参数——均逐项代码级 + 独立重跑/独立构造/实机验证。
- **未实测（如实披露）**：① GUI 实际点击走查（构造命令行已验，但未实机双击 GUI 操作）；② 视觉档在 GUI 端的端到端（命令行路径已验证，GUI 仅是同一 build_command 的封装）。
- **已闭环**（原"未实测"项）：视觉塔实机识图（20:00–20:31 完成，含 40K 大池并存）；40K 池 + 视觉并存（干净环境实测成功）。

## 三、待用户决策项

| # | 事项 |
|---|---|
| 1 | ~~视觉塔产物实机验证~~ ✅ **已完成**（2026-10-10 20:31，20K/40K 双档 + 识图全过） |
| 2 | 挂账 15/16/17（MTP 接受率基线 / 官方版留存裁定 / 正式探针件裁定） |
| 3 | ~~越权提交 `31d3faf` 处置~~ ✅ 用户裁决**保留 + 补充说明**（说明已入构建史） |
| 4 | 本次视觉验证结果由 **CodeBuddy 补录构建史**（用户裁决；TeleAgent 不代录） |

---

**署名**：TeleAgent ｜ 2026-10-10 ｜ `J:\ninfer-kvmem`