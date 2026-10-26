# 审核报告 · P0 启动层适配（CodeBuddy 施工）

> **审核方**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-09
> **审核对象**：CodeBuddy P0 交付（启动器 + 5 bat + profiles 适配 Coder390，7 改 + 2 增）
> **方式**：只读，独立读 diff + 独立重跑验证（不复述交付方结论）
> **分工遵循**：按用户 2026-10-09 分工——施工/构建史归 CodeBuddy，审核报告归 TeleAgent；本报告由 TeleAgent 记录与提交。

---

## 〇、结论

**P0 技术改动正确、验证充分，判定通过。** 唯一实质问题 = 交付方已提出的**引擎不一致**，须在起测前裁定并统一；另 1 项为分工边界提醒。

---

## 一、独立验证（我重跑，非复述）

| 项 | 结果 |
|---|---|
| `py_compile ninfer_launcher.py` | exit=0 ✅ |
| `build_command(DEFAULTS)` 实跑 | `has_--vision: False`、`has_--spec: False`、`model-id: qwen3.8-27b-coder390`、`profiles: 10` ✅ |
| 新 bat 内容核对 | `start-coder390.bat`=裸解码基线（自编/8091/无 spec/无 vision）✅；`start-coder390-mtp.bat`=MTP K4（自编/8095/显式 q4_0 警告）✅ |
| `start-coder390.bat` 实际 EXE | `engine\self-built-20261008\ninfer-serve.exe` ✅ |
| 4 个旧 bat | 各 +4 行 ASCII 注释，**零行为改动** ✅ |
| `启动器.bat` | 解释器三级回退 + ASCII-only（`D:\Python311` 已消除）✅ |
| profiles.json | 3 个 Coder390 档 + 旧 7 档 `vision→off`、spec 保留（诚实）✅；JSON 可解析（10 档）✅ |
| 备份 | `_safety_backups\*_pre-p0-coder390.*` 存在（7 文件）✅ |

## 二、通过项（已核实，无需改）

- MODEL→Coder390、DEFAULTS `spec=k0/vision=off`、`build_command` 两处 fallback 对齐、`--model-id` 口径、`ENGINE_PREV` 缺失标注、GUI 标题、PRESET 两档——**均正确且注释充分**。
- profiles 旧档 spec 保留（`dflash2/k4` 等）不删不改：诚实反映"该档需 dflash2/视觉，本线未实现"，符合最小改动。
- 2 个新 bat 的 KV 环境变量 = 启动器 `KV_ENV` 同款（`NINFER_KV_WINDOW/RETRIEVE/RING/HOST_PAGEABLE/REUSE_HOSTBACKED`）。

## 三、⚠️ 必须裁定：A/B 引擎不一致（唯一实质问题）

- **现状**：GUI 默认引擎 = `engine\ninfer-serve-120a.exe`（官方）；新 `start-coder390*.bat` = `engine\self-built-20261008\ninfer-serve.exe`（自编·现役）。
- **风险**：若后续 A/B 用 GUI 起（官方）vs 用 bat 起（自编）对照，**比较的就不是同一引擎**，读数无效。
- **我的裁定（建议）**：**A/B 一律固定 self-built（自编·现役）**——它是交接文档指定的本线现役引擎，也是 `start-coder390.bat` 已用作的基线臂。**建议把 GUI 默认引擎也改为 self-built**（`ENGINE_OPTIONS` 默认），彻底消除"GUI 官方 vs bat 自编"的差异。
  - 待你确认：① 是否同意 A/B 统一为 self-built；② 是否同意把 GUI 默认引擎改为 self-built（一处小改，归 CodeBuddy 实施）。
  - **在起测（Step 8/9）前先定死这条规则**，避免 A/B 污染。

## 四、边界提醒（非缺陷，分工收口）

- 文档提交 `d2c9806` 由 CodeBuddy 完成，其中**包含我（TeleAgent）的审核报告与调研文档**——按 2026-10-09 分工，**审核报告应由我提交**。本次系用户一次性批准，可接受；**自本轮起**：我的审核/调研文档由我提交，CodeBuddy 不再代提交；CodeBuddy 的施工产物/构建史由 CodeBuddy 提交。互不越界。

## 五、结论与建议

- **P0 判定：通过**（附"引擎统一"须裁定）。
- 建议 CodeBuddy 采纳 §三裁定（默认引擎统一为 self-built，若用户同意）后，再做一次无关性提交；随后 Step 9 起服实测裸解码基线（由用户双击 BAT），作为后续 A/B 的对照臂。
- 本报告由 TeleAgent 记录并（经用户批准后）提交。

## 六、对 CodeBuddy 补充发现的复核（cublas 依赖，2026-10-09）

**这是 CodeBuddy 抓到、我未察觉的一处隐患——交叉检查起作用了。** 我独立核验后裁定：

| 其论断 | 我的独立核验 |
|---|---|
| `env_for_launch` 只加 `dirname(exe)` | ✅ `[EVIDENCE] ninfer_launcher.py:301: env["PATH"] = os.path.dirname(exe or ENGINE) + os.pathsep + ...` |
| 自编目录缺 cublas | ✅ `engine\self-built-20261008\` 内**无** `cublas64_13.dll`（只有 cudart64_13 等）；`cublas64_13.dll` 只在 `engine\` 根 |
| 两个 exe 都引用 cublas | ✅ 全文件流式搜索（1.27 GB，**不能截断**）→ 自编与官方均含 `cublas64_13` |
| ⇒ GUI 起自编会找不到 cublas 而失败 | ⚠️ **在本机是条件性、非必崩**：`cublas64_13.dll` **在本机系统 PATH 可达**（`J:\Bonsai\landing\cuda-13.3\bin\x64`、`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\x64`）⇒ GUI 起自编大概率仍能启动，但**用的是系统 CUDA 的 cublas 版本**，可能与打包件版本/ABI 不符 |

**裁定**：CodeBuddy 的**修复建议成立并应采纳**（两处成对改：①默认引擎 official→self；②`env_for_launch` 把 `ENGINE_DIR`(engine\ 根) 加入 PATH）。但**定性修正**：这是"**确定性 + 自包含**"修复（保证用打包版 cublas、杜绝 ABI 漂移），而非"不改就启动即崩"（本机系统 PATH 兜底了 cublas）。理由不影响采纳，只影响表述与优先级。
**旁证**：`start-coder390*.bat` 已正确 `set "PATH=%ROOT%engine;..."`（自包含），GUI 缺这一步 ⇒ 应补齐，两入口一致。

## 七、对"引擎统一"的最终裁定（经二审）

1. **A/B 统一 self-built**：**同意**（self-built 含 MSVC 兼容补丁 + Design C，官方件无 Design C，行为路径不同，混用必污染对照）。
2. **GUI 默认改 self-built**：**同意**，但必须**两处成对**（引擎默认 + `env_for_launch` PATH 加 `ENGINE_DIR`），只改一处会引入"GUI 用系统 cublas"的不确定性。

## 八、结论（更新）

- P0 **审核通过**；引擎统一裁定明确为 **A/B= self-built + GUI 默认 self-built（两处成对改）**。
- 实施与提交归 CodeBuddy（施工/构建史），我此报告由我提交。

## 九、P0b 复审（2026-10-09，CodeBuddy 实施）

**判定：通过。** 独立核验：

| 项 | 结果 |
|---|---|
| `py_compile` | exit=0 ✅ |
| `env_for_launch(ENGINE_SELF)` PATH | `[0]=…\engine\self-built-20261008`、`[1]=…\engine`、`engine_root_in_PATH=True` ✅ |
| 默认引擎 | `engine_var` 默认 =「自编·现役(20261008)」✅ |
| 补丁性质（CB 精确化） | 已核 `build\patches\README.md`：补丁1=MSVC 编译兼容、补丁2=Design C、补丁3=测试开关 ⇒ **运行期差异仅 Design C** ✅ |

**CodeBuddy 的精确化成立**：补丁 1/3 不改运行行为 ⇒ `think=none` 下 self-built 与 official **基本等价**（统一紧迫性低于"必崩"叙事）；启用思考后因 Design C 分叉 ⇒ 统一仍必要。此修正对我上轮"混用必污染"的表述更精确，**采纳**。

**一处小观察（非缺陷）**：`build_command(combo, port, exe=None)` 的底层默认仍 `exe = exe or ENGINE`（official）——因 GUI 启动时总传入 `engine_var` 解析出的 exe，故不影响实际；仅当代码外部直接调 `build_command()` 不传 exe 时才用官方。可对齐（可选），不阻塞。

**结论：P0 + P0b 全部通过，可出提交包。** 施工与构建史提交归 CodeBuddy；本审核报告归我提交。

## 十、P0c（裸解码基线重测）独立复核（2026-10-09）

**结论：CodeBuddy 的重测结论成立，我已独立复现。** GPU 资源竞争确实是此前 `~17 tok/s` 的主因。

| 项 | 独立复核结果 |
|---|---|
| serve 在线 | `/v1/models` = 200 ✅ |
| 权威 decode（引擎日志 `req#3 done`） | **decode 55.9 tok/s**、TTFT 51.3 ms、prefill 139.1 ✅（复现 CB 的 55.7–55.9） |
| KVMem 判活 | `kvmem_score ... SELECT` 命中 11 次 ✅；req#3 `cache 20 (74.1%, turn closure)` ✅ |
| GPU | 15594 MiB used / 414 free / 94% util（与 CB 一致） |

**核对 CB 三处自我纠错**：①"52 tok/s【待证】"撤销——实测 55.7–55.9 准确 ✅；②日志开销非主因（full 日志仍达标）✅；③"free 317MiB 是引擎吃满"表述不完整（其他程序占可用显存+算力）✅。均成立。

**新增纪律采纳**：起服/A/B 前必须关闭占用 GPU 的程序（浏览器/QQ/Overlay），否则读数不可比（实测差 3.3 倍）——已入构建史。这条对后续 MTP A/B 是硬前置。

**一条过程提醒（非缺陷）**：本次 serve 由 CodeBuddy 以 `Start-Process` 拉起（应仍是可见控制台窗口，"关窗口=停服"语义保留，可接受）；但按纪律 serve 启停优先归用户双击 BAT。当前 serve 仍在 8091 运行，**测完请停干净并把 GPU 还给空机**（关窗口即停），再由用户管理后续。

**结论：P0 + P0b + P0c（基线 55.7–55.9 tok/s、KVMem 判活）全链路闭环，可出提交包。**

---
**署名**：TeleAgent ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`