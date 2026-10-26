# 审核：H 盘两文档对照排查与"撞墙"机制定案

> 署名：**TeleAgent（本机复核环境）**｜日期：2026-10-10｜状态：**审核结论（待用户裁决）**
> 对象：`docs/03-归因与结论/调研-对比研究-tancau-ninfer-kvmem-ring-CodeBuddy-20261010.md`（下称【调研】）与 `docs/03-归因与结论/讨论-DSH撞墙现象与双环境行为差异-CodeBuddy-20261010.md`（下称【讨论】）
> 方法：两文档逐条与本机资源对照——引擎源码（逐字行号）、DSH 模块（逐串核对）、10-10 夜引擎日志 6 份（全量请求行）、DSH 生效配置（全文）、KVMem 对照线日志。结论分级：**证实 / 证伪 / 修正 / 存疑**。

---

## 〇、总体结论（先读）

| # | 结论 | 级别 |
|---|---|---|
| 1 | 【调研】§十/§十一 的 **W1–W5 引擎核对全部成立**（逐字命中，含"改前"原文）；一处计数差异：调用点本树为 **10 处**（文档写 9 处）；基线命名需更正（见 §二.3） | 证实（含 2 处修正） |
| 2 | 【讨论】§三/§八 引擎源码取证**全部成立**；§十一 asar 取证的关键值在**本机同代 DSH 模块中逐项复现**（含 UI 文案）；§四/§九"30 秒算术"的**类别判断成立、具体假设被本机数据证伪** | 证实（含 1 处证伪） |
| 3 | ⭐ **"30 秒撞墙"的真实机制已定案**（本机 10-10 夜日志 + 引擎源码 + 官方文档三方闭合）：**不是** DSH max_tokens（实测 65,536）、**不是** tb=16000、**不是** 300s watchdog，而是**引擎 `--kv-lease-growth` 在深超池构型下的"有界完成"（bounded completion）**——租约窗口（约 4,096 token）无法扩充时，请求在窗口覆盖处被砍、以 `finish_reason=length` 结束。实测墙位：**输出 ≈ 4,037–4,071 token、35–42 秒/轮**（"30 秒"即窗口 ÷ 思考速度）。 | **新发现（定案）** |
| 4 | 官方仓对此有**明文口径**：README 边界表"**超池构型要保住输出 → 不要开 `--kv-lease-growth`**"（2026-10-07 提交 347ca35）；Bug 账本记载"**增长路径第二处预留不变量未覆盖**（深超池）"= 已知未修。本项目**全部 5 个启动器都显式开了这个开关**。 | 证实（官方文档） |
| 5 | 双环境行为差异真因（收窄）：NInfer 侧有"租约窗口砍输出"（growth ON）；纯 KVMem（llama.cpp）无此机制 → 行为正常。同夜 KVMem 日志连续生成 2,700+ token 未断，对照成立。 | 证实 |
| 6 | W1–W5 仍应照排施工（tancau 已验证的潜在缺陷），但**均不是本墙的主因**；本机 10-10 夜 6 份日志**无 W1/W2/W3 触发实例**（无超预算、无 throw、无请求被杀）。**降 tb 不是本墙的解药。** | 修正 |
| 7 | 首要建议（待用户批准）：**启动器 A/B 去掉 `--kv-lease-growth`**（保留 `--recover-invariant-failures`），用同 prompt 验证墙消失；备选：抬 `--kv-capacity`。 | 建议 |

---

## 一、审核对象与基线

**对象**：两篇文档全文（314 + 362 行）。

**本机核对基准（对照排查实际使用的资源）**：

| 资源 | 本机位置 | 状态说明 |
|---|---|---|
| 引擎源码（主基准） | `J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem`（分支 `s6-20261008`，HEAD `3b9dc83`）**= 现役引擎 `self-built-20261008` 的实际构建来源**（build-120a/build-1208a 的 CMakeCache `CMAKE_HOME_DIRECTORY` 指向它） | ✅ 可用；与 `J:\ninfer-kvmem\official-repo\...` 为**同一提交的两份 clone**（两处 HEAD 逐字一致） |
| DSH（本机） | `C:\Users\PC\.dsh` + `dsh-tauri` 打包 `@deepseek-ai/dsh@0.2.0-rc.2` | 与办公室"DSH Desktop"（Electron 形态）**形态不同**，但关键模块同代（见 §三.2） |
| 撞墙实证 | `J:\ninfer-kvmem\logs\serve_20261010_00*.log` ~ `02*.log`（10-10 凌晨 6 条主运行，共 ~200 请求） | ✅ 用户当晚在 DSH 上实测留下的全量日志 |
| KVMem 对照线 | `J:\KVMem-GSQ\logs\serve_20261010_023405.log` 等（10-10 凌晨 2:21–2:43 运行） | ✅ 同夜对照 |
| tancau 源码 | ❌ **不在本机**（`refs/` 无 tancau clone） | tancau 侧引用未独立复核（文档声明其读取自 clone；本报告对 tancau 侧的核对=**未查**） |

**环境声明**：办公室 Electron 安装件（`C:\Program Files\DSH Desktop`）不在本机，无法对 asar 字节位复核；本机以**同代 0.2.0-rc.2 模块**对全部关键字符串逐项核对（结论见 §三.2）。另：办公室文档所称基线名"`engine-main` @ Bonsai clone"在本机**无对应**——`J:\Bonsai` 的 `origin/engine-main` 分支**不含** `src/models/qwen3_5` 路径（Test-Path=False）；但文档**全部引文**在本机 `s6-20261008` 树逐字命中 ⇒ 基线实际为 s6 系，**命名差异不影响核对结论**（详见 §二.3）。

---

## 二、【调研】文档核对（W1–W5 逐条）

### 2.1 核对总表（本机 s6-20261008 树逐字）

| # | 文档主张 | 本机核对 | 级别 |
|---|---|---|---|
| W1 | `output_session.cpp:581` 为 `==`（应为 `>=`） | ✅ `L581: impl_->preview_semantic.model_thinking_tokens == *impl_->preview_semantic.budget) {` 逐字命中 | **证实** |
| W2 | `output_session.cpp:524` `> budget → throw` | ✅ `L525: throw std::logic_error("model output exceeded the licensed thinking budget");` 逐字命中 | **证实** |
| W3 | `output_session.cpp:653/656` 两处 `throw` | ✅ L653 / L656 两行逐字命中（"canonical thinking control did not close the thinking phase / reasoning channel"） | **证实** |
| W4 | progress 保活需 3 处改动（含"delta 非空"） | ✅ 四处证据全命中：`openai_chat.h:30 bool return_progress = false;`；`openai_chat_http.cpp:54` 被门控；`:117 const bool return_progress = request.return_progress;`；`openai_chat_response.cpp:363/386` 两处均 `Json::array({stream_choice(Json::object())})`（**空 delta**） | **证实** |
| W5 | 自噬循环需实测；`restore_preferred` 缺失 | ✅ 全树 `restore_preferred` **0 命中**；`context.cpp:2389` 五拍体存在（注释 L2405-2412 逐条列 5 拍）；decode 三调用点 479/677/931 存在且未传"跳过"参数 | **证实**（churn 与否仍需实测，文档口径正确） |

### 2.2 支撑证据复核（§三/§十一 其余引用）

| 引用 | 核对 |
|---|---|
| `translate.cpp` requested_output_tokens / thinking budget | ✅ 内容命中；**行号微偏**：实际 L423（文档写 425）、L427-428（文档写 426-428） |
| `engine_core.h` capacity_output + validate 调用 + 抛错 | ✅ 实际 L252-259（文档写 251-255/251-259，内容一致） |
| `output_session.cpp:672-687` validate_generation_capacity（"包含关系"实锤） | ✅ `remaining = effective - budget` 减法语义逐字命中 |
| `request_plan.cpp` 非 growth/ growth 分支 | ✅ 实际 L262-297（文档写 264-266/276-290，内容一致） |
| `program_impl.h:55` `kKVLeaseGrowthMarginTokens = 4096`；`:1648-1649` margin=max(prefill_chunk,4096) | ✅ 逐字命中 |
| `generation_service.cpp` 错误码→HTTP 映射 | ✅ L50-57 命中（context_length_exceeded / thinking_budget_capacity_insufficient → 400） |
| `openai_chat_request.cpp` S3 thinking_budget 解析 | ✅ 函数体 L955-982 命中（文档写 947-981 ≈ 注释块 948-954 + 函数体） |

### 2.3 差异与修正清单（共 4 处，均不影响主结论）

1. **调用点计数：文档写"全部 9 个调用点"，本树实测 10 处**——多出 `hybrid_program.cpp:859`（`ProgramImpl::hybrid_activate` 内）。完整清单：`decode.cpp:479/677/931`、`prefill.cpp:690/1156/1246/1349`、`hybrid_program.cpp:859`、`capture.cpp:1060`、`commit.cpp:346`（+ 声明 `program_impl.h:1602`）。**施工时以 10 处为准**（加 `restore_preferred` 参数需同步全部 10 处）。
2. **基线命名**：文档"`engine-main` @ Bonsai clone"→ 本机实际核对基准为 `1314521gjy/ninfer-fusion-kvmem` clone、分支 `s6-20261008`、HEAD `3b9dc83`（两处 clone 同 HEAD）。`J:\Bonsai` 的 `origin/engine-main` 不含 qwen3_5 路径，勿混。
3. **行号微偏 2 处**（translate.cpp、openai_chat_request.cpp，见 §2.2）。
4. **一处外部报告表述**：文档 §10.4 已自行更正（"=`==` 应为 `>=`"方向），本机复核认同其更正结论。

### 2.4 亮点确认

- §十"用两边本地源码逐条核对"的方法论正确；W1-W5 的"改前"引文**逐字可靠**（本机全部命中，无一处编造）。
- §10.3 对"降 tb 前置条件"的三条（先修 throw、先修 `==`、先修超预算 throw）判断合理——**但请注意：这三条针对的是"思考预算类"故障；本墙（§四）是另一条路径，降 tb 不解决本墙**（见 §五）。

---

## 三、【讨论】文档核对

### 3.1 §三 引擎源码取证（逐条）

| 引用 | 核对 |
|---|---|
| thinking_budget 与 max_tokens = **包含关系**（translate + engine_core + validate 减法） | ✅ 全部逐字命中（同 §2.2） |
| 两条"直接拒绝"路径（400） | ✅ 源码在场（engine_core.h:257-259 抛 + generation_service.cpp:54-57 映射） |
| KV 页授权（非 growth：prompt+输出一起预留；growth：min(eff,4096) 租约） | ✅ 逐字命中（request_plan.cpp:262-297） |
| "OpenAI 路由已支持 per-request thinking_budget"（S3） | ✅ 命中（parse_thinking_budget 于 openai_chat_request.cpp:955-982） |
| `output_session.cpp:523-526` 防御检查 | ✅ 命中（即 W2） |

### 3.2 §十一 DSH Desktop 取证项（本机同代模块复现）

办公室对 Electron `app.asar` 取证的**关键值**，本机在 `dsh-tauri\dependencies\dsh\node_modules\@deepseek-ai\` 与 `@earendil-works\pi-ai`（0.2.0-rc.2）中**逐项命中**：

| 项 | 办公室 asar 值 | 本机同代模块 | 级别 |
|---|---|---|---|
| `DEFAULT_MAX_TOKENS`（pi-ai/自定义 provider） | 32768 + 注释"Output capability assumed…" | ✅ `dsh-llm-pi-ai\lib\index.js`：`const DEFAULT_MAX_TOKENS = 32768;` + 同注释逐字 | 证实 |
| `DEFAULT_MAX_TOKENS`（deepseek provider） | 256000 | ✅ `dsh-llm-deepseek`：`256e3` | 证实 |
| `DEFAULT_STREAM_IDLE_TIMEOUT_MS` | 300000（3e5） | ✅ 两个包均 `3e5`；schema `.default(DEFAULT_STREAM_IDLE_TIMEOUT_MS)` | 证实 |
| `isRecoverableLength` | "length stop ended below the intended limit…" | ✅ `pi-ai\dist\utils\overflow.js`：函数逐字在场（`stopReason==="length" && desiredMaxOutput>0 && output<desiredMaxOutput`） | 证实 |
| `thinkingTokenBudgetField` 默认 off | "Off by default…" | ✅ `resolveThinkingTokenBudgetField`：未配 `compat.thinkingTokenBudgetField` 即 undefined（不发字段） | 证实 |
| `thinkingBudgets` {minimal,low,medium,high} | 可配 | ✅ schema 逐字在场 | 证实 |
| UI 文案"已达到输出 token 上限"+"继续"提示 | @27278934 | ✅ `dsh-client-ui-chat\lib\client.js`：`"message.maxTokens": "已达到输出 token 上限"` + hint 逐字 | 证实 |
| **新增（办公室未记）**：设置系统迁移机制 | — | ✅ `dsh-settings`：启动时把遗留 `settings.yaml` 改名 `.imported` 并**导入 active profile**（`importLegacyDocument()`）⇒ 这解释了本机"无当前 settings.yaml"之谜，**当前生效配置 = `profiles\core-020\cordis.patch.yml`** | 新发现 |

### 3.3 §11.6 / §12.3 回家清单——本机执行结果（回填办公室未知数）

**生效配置全文核对**（`C:\Users\PC\.dsh\profiles\core-020\cordis.patch.yml`，10-10 02:45 修改，晚于夜测 ⇒ 为**当前**配置；另对照 9-27 版 `settings.yaml.imported`）：

| 问题 | 答案 |
|---|---|
| **maxTokens 实际值** | **65536**（`llm-pi-ai.providers.ninfer.models`：`qwen3.8-27b-coder390` = 65536；`qwen3.8-27b`(224K) = 65536 + `maxOutputTokens: 32768`；`qwen3.8-27b128k` = 65536。**coder390 无 maxOutputTokens 字段**） |
| thinkingBudgets 是否配过 | **未配置**（providers 无该节） |
| thinkingTokenBudgetField 是否开启 | **未设置**（默认 off）⇒ **请求不带 `thinking_budget`** ⇒ 服务端 `--default-thinking-budget 16000` 生效 |
| streamIdleTimeoutMs | **未覆盖**（默认 300,000 ms；引擎日志未见 300s 类中断） |
| 默认模型 | `agent-default-model: provider=ninfer, model=qwen3.8-27b-coder390, reasoningEffort=medium`（L154-159） |
| 供应商端点 | ninfer `http://127.0.0.1:8094/v1`（L57）——与夜测 serve 端口一致 |

### 3.4 §四/§九"30 秒算术"的复核（修正）

- 办公室判断"**墙在请求级输出上限**"（类别）→ **方向对，指认错**：墙不在"请求级 max_tokens"，在**引擎租约窗口**（§四）。
- 办公室点估计"DSH max_tokens ≈ 2,048–4,096" → **证伪**：实际 65,536（配置 + 引擎日志 `max output 65,536` 双重实证）。
- 办公室"排除 2048/4096/8192/32768 打满"的推理前提（按 60–105 tok/s 算）→ 本机墙请求实测 decode **98–125 tok/s**（MTP+ngram），**30–42 秒 ≈ 4,050 token**，与"窗口 4,096"吻合（详见 §四.3）。
- §12.2"两分支决策树"（max_tokens vs tb）→ 实际落在**分支 B 区间**（65536 > 16000），但**本墙与该分支的 W1/W3 机制无关**——本墙在思考烧到 4,096 处就被租约砍断，**根本没走到 tb=16000 的熔断点**。

---

## 四、⭐ 撞墙机制定案（本机数据，三方闭合）

### 4.1 现象（10-10 夜实测，共 20+ 次）

引擎日志（`logs\serve_20261010_011659.log` 等）逐字：

```
req#7  done | output limit | prompt 16,647 | output 24,226 | ... | thinking 24,226/32,000     （01:16 运行）
req#8  done | output limit | prompt 16,653 | output 4,060  | cache 16,642 (99.9%, response replay) | total 36.3s
req#32 done | output limit | prompt 70,147 | output 4,070  | ... | thinking 4,070/16,000       （01:44 运行）
req#38 done | output limit | prompt 36,738 | output 4,071  | cache 0 (0.0%) | TTFT 40.0s | total 1m 15.1s
```

**规律**：墙位在**输出 ≈ 4,037–4,071 token**（全为思考），**与 prompt 规模无关**（16K–87K 的 prompt 全部同一墙位），每轮 **35–42 秒**；finish= `output limit`（引擎侧）→ DSH 显示"已达到输出 token 上限"+"继续"提示 → 用户点继续 → 下一轮同位置再砍 → **"老撞墙、不停要继续"**。

### 4.2 机制（源码链）

1. `--kv-lease-growth` 下，请求的输出租约只覆盖"**当前 frontier + 有界窗口（约 4,096 token）+ cushion**"，在 decode 轮边界尝试扩充（`docs/maintainer/paged-kv-cache.md:432-439` 逐字：*"Generation 只租用「当前 frontier 加一个 bounded window（约 4096 tokens）加一个 per-lane cushion」…**池已无法再扩充该 window 时，request 在 window 覆盖的 frontier 上以 length 结束（bounded completion）**"*）。
2. 扩充阶梯实现于 `context.cpp:2145-2222`（`ensure_sequence_kv_lease`：4096→128→64 三档尝试）；三档均不成 → `lease_settled=true`（**本机夜日志无任何"cannot grow"警告 ⇒ 走的是静默分支**）。
3. 结算：`engine_core.h:2043-2085`（`apply_device_kv_lease_settlements`）→ `budget->cap_remaining(covered − frontier − step)` → 预算耗尽 → **`FinishReason::OutputLimit`** → 日志 `output limit`。
4. 覆盖量算例：req#32 的 `[ninfer] mask hidden: … span=1160`（= entitlement 1,160 页）× 64 = **74,240 token = prompt 70,147 + 4,093** ⇒ 墙=窗口覆盖，**租约从未扩充**。req#7（另一形态）：租约成功扩到池上限（640 页 = 40,960 token），墙位 24,226 ≈ 40,960−16,647−87。

### 4.3 "30 秒"的重算（修正办公室算术）

4,050 token ÷ 35–42s = **96–116 tok/s**（与墙请求实测 decode 98–125 tok/s 一致）⇒ **"每次 30 秒左右" = 租约窗口（4,096）÷ 思考速度**，与 max_tokens/tb/watchdog 均无关。

### 4.4 官方口径（本项目内文档，决定性）

- **README.md:218**（提交 `347ca35`，2026-10-07）：*"超池构型（设备池 < 逻辑上下文）要保住输出 → **不要开 `--kv-lease-growth`**（本仓默认关；F2 之后的批次默认开，照抄会命中'输出被砍到 2 个 token'那条回归）"*。
- **Bug 账本（`已知问题-初期版本.md`）**：*"lease-growth 对浅超池有效，对'2.7× 深超池 + 8192'不够 ⇒ **增长路径第二处预留不变量未覆盖**"*（L177）；F2 回归行 L83/L116；开关语义 L198（*"池不够时走 bounded completion（finish_reason=length）而非抛不变量"*）。
- 本项目**全部 5 个启动器**（`start-coder390*.bat` ×4 + `ninfer_launcher.py`）均含 `--kv-lease-growth`；本机配置为 **6.4× 深超池**（40,960 池 vs 262,144 上下文），命中该已知缺口。

### 4.5 双环境差异真因（收窄）

- NInfer 侧：租约窗口砍输出（上述机制）→ "快但老撞墙、不停继续"。
- 纯 KVMem（llama.cpp 线）：**无租约机制** → 无此墙。同夜对照（`J:\KVMem-GSQ\logs\serve_20261010_023405.log`）：连续生成至 2,700+ token 未断（~10–23 tok/s）→ "慢但行为正常"。
- 办公室候选 1★（"思考是否计入输出预算"）**不是本墙主因**；真因是**引擎侧租约**（服务端差异方向正确，机制不同）。

### 4.6 一处待钉死（如实披露）

对 `prompt + 窗口 ≤ 池` 的个案（如 req#38：40,833 页-token < 49,152），静读阶梯代码**未能完全闭合**"为何三档均不扩充"（对 `prompt + 窗口 > 池` 的个案如 req#32，钳位算术已闭合：entitlement 1,161 > 池 768 ⇒ 阶梯目标被钳 ≤ 池 < 现有 ⇒ 必然静默结算）。**不影响主结论**（机制类别、墙位、修法方向均已实证）；如需钉死子条件，一次 3 行插桩运行即可（可选待办）。

---

## 五、对原方案的影响（修正）

| 原方案 | 复核 |
|---|---|
| 降 tb（< DSH max_tokens）作为解 | ❌ **不是本墙的解药**：墙在输出 ≈ 4,096 处，与 tb=16,000 无关；夜测已把 tb 从 none/32000/16000/8000 全试过，墙位不变。 |
| W1–W5 施工（照 tancau） | ✅ 仍应排（真实潜在缺陷），但**非本墙主因**；本机夜 6 日志**零 W1/W2/W3 触发实例**（无超预算、无 throw、无请求被杀、无 500）。W4（保活）对"长 prefill > 300s"场景仍有独立价值（本机未触发，因墙先至）。 |
| 修 W2/W3 后再降 tb 才安全（§10.3） | ✅ 该次序判断本身成立（tancau 实证），但与本墙解耦——可并入下批施工，不阻塞本墙修复。 |
| DSH 侧配置（调大 streamIdleTimeoutMs 等） | 零成本、可做（防第二道墙），但**本墙不在 DSH 侧**——改 DSH 配置不解决。 |

---

## 六、建议行动清单（待用户裁决）

| # | 动作 | 成本 | 预期/判据 |
|---|---|---|---|
| **1** | **启动器 A/B：去掉 `--kv-lease-growth`**（保留 `--recover-invariant-failures`），同 prompt/tb=16000/medium 重跑 | 零编译，改一行；需用户起服 | 官方口径指向的修法。判据：**同任务不再在 ~4,050 处被砍**；观察是否出现 429（B01 家族）或异常 |
| 2 | 备选/叠加：抬 `--kv-capacity`（40,960 → 49,152/65,536）；必要时按账本建议把 DSH maxTokens 压到 ≤ 池 token 数 | 零编译 | 把残余墙位抬高；深超池下优先级低于 #1 |
| 3 | W1–W5 照 tancau 模式进下批施工（调用点按本树 **10 处**） | 小（~70 行） | 消除潜在缺陷；**不为本墙服务** |
| 4 | DSH：`streamIdleTimeoutMs` 调大（如 3600000） | 零 | 防 300s 第二道墙（零成本保险） |
| 5 | （可选）3 行插桩钉死 §4.6 子条件 | 一次重编+一跑 | 仅提高机理完备度 |

**纪律提醒**：#1/#2 涉及用户启动器与起服流程，**实施前需用户批准**；A/B 由用户起服（可见窗口），TeleAgent 只出方案与判据。

---

## 七、覆盖度披露

- **全查**：两文档全文；W1–W5 及 §三/§十一全部源码引用点（逐字）；DSH 关键字符串 10 项（逐项）；生效配置全文；10-10 夜 6 条主日志的**全部** `req#` 行；KVMem 同夜日志。
- **抽验**：夜日志中非请求行的诊断（budgets/mask/retrieve 按窗口抽样）；00:56、02:44 运行以请求行为主。
- **未查**：tancau clone（不在本机）⇒ tancau 侧引用未独立复核；办公室 Electron 安装件本体（不在本机）⇒ asar 字节位未复核（以同代模块替代）；DSH 会话内容（session.v4.jsonl.zst 未解压，无解压工具）——撞墙证据已由引擎日志闭合，未必需。

## 附录 A：关键证据索引

| 证据 | 位置 |
|---|---|
| 墙位/时长（20+ 次） | `logs\serve_20261010_011659.log`（req#7/8/9/12-18）、`014459.log`（req#32/36/38/39/47/48）、`003927.log`（req#2） |
| 租约阶梯+结算 | `context.cpp:2145-2222`；`engine_core.h:2043-2085`；`context.cpp:2224-2247` |
| bounded completion 设计文 | `docs\maintainer\paged-kv-cache.md:432-439` |
| 官方警告 | 融合仓 `README.md:218`（347ca35）；`已知问题-初期版本.md:83/116/177/198` |
| DSH 生效配置 | `C:\Users\PC\.dsh\profiles\core-020\cordis.patch.yml`（10-10 02:45） |
| DSH 迁移机制 | `@deepseek-ai\dsh-settings\lib\index.js`（importLegacyDocument） |
| W1–W5 源码 | `output_session.cpp:581/525/653/656`；`openai_chat.h:30`；`openai_chat_http.cpp:54/117`；`openai_chat_response.cpp:363/386`；`context.cpp:2389` |
| 对照线 | `J:\KVMem-GSQ\logs\serve_20261010_023405.log`（kvmem=1 spec=draft-mtp n_ctx=184320 rbudget=4096） |

---

*本稿为审核结论（非施工文档）；全部引用均经本机逐字核对，命令为 `git grep/show`、PowerShell 日志检索与 Python 字符串核对。*
