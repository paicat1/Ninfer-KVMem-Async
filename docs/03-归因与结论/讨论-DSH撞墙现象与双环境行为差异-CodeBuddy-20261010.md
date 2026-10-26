# 讨论记录：DSH 撞墙现象与双环境行为差异（分析稿）

> 署名：**CodeBuddy**（办公室讨论环境，H 盘 clone）｜日期：2026-10-10｜状态：**讨论中**
> 用途：汇总 2026-10-10 全天讨论（用户 + 两个智能体），防止遗忘；供回家后验证与继续讨论。
> 口径：[源码] = 逐字读源码；[实测] = 已有实测读数；[推测] = 待验证；[待查] = 未知数。
> 源码基准：`engine-main`（20261008 基线 + 本项目同款补丁，与现役引擎 `self-built-20261008` 同源）。

---

## 一、现象汇总（用户现场观察）

1. 模型（Coder390-EfficientThink-Q2LynnStyle-MTP）在 **DSH（DEEPSEEK HARNESS）** 里跑时，**不断报"超过输出上限"**。
2. **每次都是 30 秒左右撞墙**（时间观察，关键线索）。
3. 用户对模型说"不要老是思考，要及时调用工具落盘"→ 模型**能遵循一次**（及时落盘后继续），**但马上忘记**。
4. 用户记忆：DSH 输出设置 = **32K**（与快速池对齐）；**回去再查**（记忆待实证）。
5. **天然对照实验**（同一模型、同一任务"多边形飞机驾驶"）：
   - **纯 KVMem 项目**（无 NInfer）：~50 tok/s、常掉个位数、很慢——**但行为逻辑正常**（思考/落盘/工具交替有序），把项目明显收敛；
   - **本项目（NInfer KVMem）**：快——但**老撞墙、不停要"继续"**；最后由 NInfer 接手把项目跑通。
6. 用户的原始怀疑：**"思考时没有用到 256K 上下文，只用了显存里的快速区"**。

---

## 二、三方讨论要点（保留分歧）

### 2.1 用户怀疑（原话）
> "是不是思考的时候没有用到256K上下文，而是只使用了在显存里的快速区？"

### 2.2 智能体 A（另一环境）的分析要点
- 三量区分：`--max-context`（逻辑）/ `--kv-capacity`（真池）/ `NINFER_KV_WINDOW`（开关）。
- 算账：prompt + 思考 + 正文**累加进同一 40960 池** → 超池。
- 判断："40K 快速区是硬边界，思考是最吃 KV 的那个"；候选①"**思考预算 16000 > DSH max_tokens**"最强（理由："不断报" = 结构性矛盾而非过载）。
- 建议：读源码钉死"**`--default-thinking-budget` 与 max_tokens 是包含还是相加**"。

### 2.3 CodeBuddy（本环境）的分析要点
- **双假设框架**：容量链（输出 KV 需求 > 池 → 截断）vs 可见性链（生成阶段超窗内容不可见/检索不触发 → 思考打转膨胀 → 撞上限）——**两者都能造成"报超过输出上限"，判据不同**。
- **"30 秒"算术**：按实测速度（60–105 tok/s，MTP 代码场景 184）→ 30 秒 ≈ **1,200–3,000 token** ⇒ **烧不完 16K 思考预算**（需 160s+）。
- 修正智能体 A 两处：①"256K 是装饰性的"过于绝对（构建史 §4.2 实测长 prompt 检索正确）；② `--max-shared-prefixes 0` **不应重评估**（Bonsai G16 已闭环：不影响轮间复用；且为防打砖铁律）。

---

## 三、源码取证结果（2026-10-10，本环境；钉死性问题）

### 3.1 【已钉死】thinking_budget 与 max_tokens = **包含关系**（不是相加）

证据链（逐字）：

1. `translate.cpp:425`：`options.execution.requested_output_tokens = static_cast<std::uint32_t>(request.max_tokens);`
2. `engine_core.h:251-255`：
   ```cpp
   const std::uint32_t capacity_output =
       max_context_ - prompt_summary.prompt_tokens + static_cast<std::uint32_t>(1);
   output.validate_generation_capacity(
       std::min(options.execution.requested_output_tokens, capacity_output));
   ```
3. `output_session.cpp:672-690`（`validate_generation_capacity`）：
   ```cpp
   if (!budget || !in_reasoning || effective_output_tokens <= *budget) return;
   const std::uint64_t remaining = effective_output_tokens - *budget;   // ← 减法 = 包含
   const std::uint64_t required  = thinking_control_tokens->size() + 1U;
   if (remaining < required) throw std::invalid_argument("effective output capacity
       after the thinking budget must fit the complete control suffix ...");
   ```

**⇒ 结论**：思考预算**从输出容量里扣**（`remaining = effective_output_tokens − budget`）。
- 思考 ≤ budget；**正文空间 = max_tokens − 思考**；
- 推论：**若 DSH 的 max_tokens < 16000（服务端 tb）→ 思考可烧到 max_tokens 被掐断 → 正文空**（候选①机制在源码层成立）。

### 3.2 【已钉死】两条"直接拒绝"路径（HTTP 400）

| 错误码 | 触发条件 | 位置 |
|---|---|---|
| `thinking_budget_capacity_insufficient` | `effective_output_tokens > budget` 且 `remaining < control_suffix+1`（即 max_tokens 略大于 tb 但装不下 control） | 抛出 `engine_core.h:256-259`；映射 400 `generation_service.cpp:54-57` |
| `context_length_exceeded` | prompt + 输出 > max_context（262144） | 同上文件 51-53 |

### 3.3 【已钉死】KV 页授权与输出上限（Bonsai 线 G17 的源码依据）

- **非 growth 模式**（`request_plan.cpp:264-266`）：
  ```cpp
  reserved_context_tokens = prompt_tokens + (effective_output_tokens - 1);
  text_kv_page_entitlement = kv_pages_for_tokens(reserved_context_tokens);
  ```
  ⇒ **prompt + 全部输出 一起预留页**——这就是 Bonsai 线 G17"`prompt + output ≤ 池`"的源码根源。
- **growth 模式**（本项目已开 `--kv-lease-growth`，`request_plan.cpp:276-290`）：
  ```cpp
  leased_output_tokens = min(effective_output_tokens, kv_lease_growth_margin_tokens());  // = min(eff, max(prefill_chunk,4096)) = min(eff, 4096)
  main_window_tokens   = max(leased_output_tokens, widest + 1U);
  text_kv_page_entitlement = kv_pages_for_tokens(min(capacity, prompt + main_window_tokens - 1));
  ```
  - 常量：`kKVLeaseGrowthMarginTokens = 4096`（`program_impl.h:55`）；
  - 租约注释（逐字）："The lease covers a bounded window of the remaining output, not the whole client budget … The window is extended at a decode-round boundary, up to the request's own output ceiling."
  ⇒ **租约只覆盖有界窗口（4096 token）**，decode 轮边界扩展；**页授权被池容量截断**（`min(capacity, ...)`）。

### 3.4 【修正一条旧知识】OpenAI 路由已支持 per-request thinking_budget

- `openai_chat_request.cpp:947-981`（**S3 修复，2026-10-07 落地**）：请求体 `thinking_budget` 被解析（须 ≥1024、非负整数）；`translate.cpp:428`：**请求值优先于服务端默认**（`request.thinking_budget ? request.thinking_budget : server.default_thinking_budget`）。
- ⇒ 智能体 A 引用的"OpenAI 端点不解析 thinking_budget"是 **20261003 旧基线**行为；**本线 20261008 引擎已支持**（若 DSH 带该字段会生效——agent 客户端通常不带）。

---

## 四、"30 秒"的更新判断

| 假设撞的墙 | 需要 token | 30 秒内可达？（按 60–105 tok/s，峰值 184） |
|---|---|---|
| DSH max_tokens = 2048 | 2,048 | ✅ 轻松 |
| DSH max_tokens = 4096 | 4,096 | ✅（需 137 tok/s，MTP 代码场景可达） |
| DSH max_tokens = 8192 | 8,192 | ⚠️ 需 273 tok/s，超出实测 |
| DSH max_tokens = 32768（用户记忆） | 32,768 | ❌ 需 1092 tok/s |
| 思考预算 16000 | 16,000 | ❌ 需 533 tok/s |

⇒ **"30 秒"与"32K"矛盾**；最自洽的是 **DSH 实际 max_tokens ≈ 2,048–4,096**（或撞别的墙）。
⇒ 回家第一查：**DSH 配置里的 max_tokens 实际值**（用户记忆须实证）。

---

## 五、候选机制总表（回家验证用）

| # | 候选 | 支持 | 判据 |
|---|---|---|---|
| 1 | **DSH max_tokens < tb**：思考烧光预算 → 正文空/截断 | "30 秒"算术 + "不断报"=结构性 + 源码包含关系成立 | 查 DSH max_tokens；日志 `thinking` 值 < 16000 且 `finish=length` |
| 2 | **thinking_budget_capacity_insufficient**（400 拒绝） | 源码存在该路径（§3.2） | 报错原文 / HTTP 状态码 |
| 3 | **超池（prompt+输出 > 池，G17 类）** | 源码页授权机制（§3.3） | 日志 `output` 远小于预期 + prompt 规模 |
| 4 | **检索退化 → 思考膨胀**（可见性链） | Bonsai B05/A5 先例 | 日志 `scored_kept=0`/`QUERY_TAIL` + thinking 膨胀 |
| 5 | DSH 侧其他限制 | — | 报错原文 |

---

## 六、双环境行为差异候选（同一模型，为何行为不同）

| # | 候选 | 说明 | 判据 |
|---|---|---|---|
| 1 | **截断模式差异** | NInfer 环境"每次被掐断"（max_tokens/预算冲突）→ 模型"没想完"→ 下一轮继续想 → 又掐断（循环）；纯 KVMem 若输出上限宽裕 → 模型自然完成"思考→落盘"循环 | 两环境各自的输出上限配置 |
| 2 | **推理回灌差异** | Bonsai F1：不回灌 reasoning = 防循环（唯一被单变量实测证实的触发器）；两环境对 reasoning 的处理可能不同 | 两环境是否回灌 `reasoning_content` |
| 3 | **思考管理策略差异** | NInfer：tb 16000 熔断 + control 注入；纯 KVMem：可能无此机制（模型自由） | 两环境 tb/control 配置 |
| 4 | **上下文可见性差异** | NInfer 检索式（40K 池）；纯 KVMem 若为全量注意力（慢但全）→ 可见性完整 | 纯 KVMem 的 KV 机制 |
| 5 | 采样差异 | 本项目 `--presence-penalty 0`；Bonsai F4：presence 1.0 减轻不归零 | 两环境采样配置 |

> **已确认（2026-10-10 下午）**：两个环境用**同一个 DSH 客户端、同一个窗口，直接切引擎**——客户端变量消除，差异锁定在服务端。"纯 KVMem"项目未上传（暂无法直接研究其实现）。

---

## 七、回家验证清单（按成本排序）

1. 【零成本】查 **DSH 配置**：max_tokens 实际值 + 请求体是否带 `thinking_budget` 字段；
2. 【零成本】翻 **日志** `logs\serve-coder390-mtp.log`：报错请求的 `req# done` 行（`thinking N/16000`、`output`、`finish`、`prompt_tokens`）+ 检索行（`scored_kept`、`QUERY_TAIL`）；
3. 【零成本】**DSH 报错原文**（截图/文字）；
4. 【低】对照**两环境配置**（tb / presence / preserve-thinking / reasoning 处理 / 输出上限）；
5. 【中】按定位结果调参（降 tb / 调 DSH / 抬池——**先不动模型**）。

---

## 八、源码证据索引（文件:行）

| 位置 | 内容 |
|---|---|
| `src/serve/translate.cpp:425` | `requested_output_tokens = request.max_tokens` |
| `src/serve/translate.cpp:426-428` | `thinking.budget = request.thinking_budget ?: server.default_thinking_budget` |
| `src/runtime/engine/engine_core.h:251-259` | `capacity_output` 计算 + `validate_generation_capacity` 调用 + 抛 `ThinkingBudgetCapacityInsufficient` |
| `src/models/qwen3_5/frontend/output_session.cpp:672-690` | `validate_generation_capacity`（包含关系实锤） |
| `src/models/qwen3_5/frontend/output_session.cpp:523-526` | "model output exceeded the licensed thinking budget"（防御检查） |
| `src/models/qwen3_5/program/planning/request_plan.cpp:251-290` | `effective_output_tokens` 计算 + KV 页授权（G17 源码依据） |
| `src/models/qwen3_5/program/program_impl.h:55` | `kKVLeaseGrowthMarginTokens = 4096` |
| `src/models/qwen3_5/program/program_impl.h:1648-1650` | `kv_lease_growth_margin_tokens() = max(prefill_chunk, 4096)` |
| `src/serve/generation_service.cpp:45-70` | 错误码 → HTTP 映射（400/429/503/499） |
| `src/serve/openai_chat_request.cpp:947-981` | S3：per-request thinking_budget 解析（≥1024） |

---

## 九、第二轮讨论进展（2026-10-10 下午，追加）

### 9.1 "30 秒"精确算术（智能体 A）与本环境复核

**智能体 A 的算术**（速度均出自本仓实测：prefill 1.90k tok/s / decode 105 tok/s）：

```
prefill 20,000 ÷ 1,900 ≈ 10.5s
decode   2,048 ÷   105 ≈ 19.5s
合计                   ≈ 30.0s   ← 命中 DSH max_tokens = 2048
```

对照：4096 → 49.5s（排除）；8192 → 88s（排除）；16000 → 163s（排除）。

**本环境复核（成立性 + 敏感性）**：

- ✅ **方向与量级成立**：30 秒总预算对应的输出量级为 **约 1,000–3,000 token**——无论 prompt 大小，都远小于 16K/32K ⇒ **"墙在请求级输出上限"这一类别判断是稳的**。
- ⚠️ **"精确命中 2048"对 prompt 大小敏感**（prefill 占时不同）：

| prompt | prefill 耗时 | 剩余给 decode | 30s 对应输出 |
|---|---|---|---|
| 10,000 | 5.3s | 24.7s | ≈2,600 |
| 20,000 | 10.5s | 19.5s | ≈2,050 |
| 30,000 | 15.8s | 14.2s | ≈1,490 |
| 40,000 | 21.1s | 8.9s | ≈940 |

⇒ 合理区间 **~1,000–2,600**；"2048"是"prompt≈20K"假设下的点估计。

- ⚠️ 另有两个未计入因素：① **KV 复用**（续轮 cache 命中时 prefill 大减，TTFT 实测 0.18–0.29s）；② **思考场景 decode 速度**（MTP 接受率依语料，代码场景可达 184 tok/s）。两者扰动点估计，**不改变类别判断**。
- ⚠️ **"排除候选②③"（22,048 < 32K 窗口 < 40K 池）依赖"prompt ≈ 20K 且 ≤ 30K"假设**——若 DSH 实际 prompt 更大（>32K），候选③不能排除。**需验证 DSH 实际 prompt 规模**。

### 9.2 双环境行为差异——重大收窄（用户新信息）

**用户确认**："用的是同一个 DSH 客户端，同一个窗口，直接切引擎的"。
⇒ **客户端变量被消除**：两个环境的请求（prompt 结构、max_tokens、历史管理）完全一致——**行为差异 100% 由服务端（引擎+配置）决定**。

**更新后的候选排序**：

| # | 候选 | 说明 |
|---|---|---|
| **1★** | **两个引擎对"思考 token 是否计入输出预算"的处理不同** | NInfer：包含关系（源码实锤）→ 思考烧光 max_tokens（如 2048）→ 每轮撞墙、正文空；纯 KVMem：若思考不计入/不截断 → 同样的 2048 全给有效输出 → 模型能完成"思考→落盘"循环 → 行为正常。**同时解释"慢但正常" vs "快但撞墙"** |
| 2 | 响应格式差异 → DSH 行为差异 | 若两引擎对 `reasoning_content` 的返回/回灌处理不同（Bonsai F1：回灌是循环触发器），DSH 的后续请求组装会不同 |
| 3 | 思考管理机制差异 | NInfer：tb 16000 熔断 + control 注入；纯 KVMem：可能无 |
| 4 | 采样差异（服务端） | presence 0 vs 其他 |
| 5 | ~~上下文可见性~~ | 30 秒时点未越窗口（22K < 32K）⇒ 弱化（大 prompt 时复活） |

**判据**：回家后对比两环境"同一请求"的行为——纯 KVMem 端返回的 output 结构（有没有 reasoning 通道、思考是否占输出预算）。

### 9.3 "技能提醒落盘"的落点（三方共识收敛）

- 智能体 A：落点应在 **harness（DSH）层**（轮次超 N token 未调工具 → 强制 checkpoint 回合），不是提示词（模型无 token 计数器，注定近似+衰减）。
- 本环境同意，并补**三层次按确定性排序**：
  1. **harness 强制交替**（最确定，不依赖模型自控）；
  2. **引擎 tb 硬熔断**（次选：tb 降到 DSH max_tokens 之下；注：服务端 `--default-thinking-budget` 无 1024 下限——那是**请求体**的校验；tb=1500 + max_tokens=2048 时 `validate_generation_capacity` 通过、正文空间 ≈523）；
  3. 提示词软引导（最弱，会衰减）。
- "agent harness + 长思考模型 + 小输出预算" = **三方错配**（智能体 A 定性准确）；解法优先级：**抬 DSH 预算 > harness 强制交替 > 降 tb > 提示词**。

### 9.4 更新后的行动清单（回家）

1. 【零成本】**查 DSH max_tokens 实际值**（唯一未知数、最强嫌疑——若=2048 则当场定案）；
2. 【零成本】日志 grep `req# done` 行：`output` 是否 = max_tokens、`finish` 是否 = length、`thinking` 值；
3. 【零成本】顺带看 prompt_tokens 规模（验证 §9.1 假设）+ 轮间走势（"忘记"判别：稳定增长→模型行为；突然回落→DSH 压缩）；
4. 【低】实验：tb 临时设 1500 重跑——若"超过输出上限"消失，双重确认墙在 max_tokens；
5. 【中】双环境对比：同一请求在纯 KVMem 端的响应结构（思考是否占输出预算）。

---

## 十一、第三轮：DSH Desktop 实机调查（2026-10-10，安装版 app.asar 逐字取证）

> 对象：`C:\Program Files\DSH Desktop`（用户 2026-10-10 安装；Electron 应用）。
> 方法：解析 `app.asar`（268 MB）header + Node 字符串搜索（工具：`refs/_tools/search_asar.cjs`，逐字命中）。

### 11.1 关键配置默认值（逐字）

| 项 | 值 | 证据（asar 字节位） |
|---|---|---|
| `DEFAULT_MAX_TOKENS`（pi-ai/自定义 provider） | **32768**（注释："Output capability assumed for a model neither configuration nor the catalog sizes"） | @57492960 |
| `DEFAULT_MAX_TOKENS`（deepseek provider） | 256000 | @57298808 |
| `DEEPSEEK_DEFAULT_MAX_TOKENS`（Anthropic Messages 路径） | **4096** | @73187149 |
| `DEFAULT_STREAM_IDLE_TIMEOUT_MS` | **300,000 ms（300 s）** | @57298808 / @57319307（`?? 3e5`） |
| `DEFAULT_CONTEXT_WINDOW`（pi-ai） | 262144 | @57492960 |
| `thinkingTokenBudgetField` | **默认 off**（"Off by default; not set on the generated catalog"） | @78592010 |
| `thinkingBudgets` | `{minimal, low, medium, high}`（可配） | @57493595 |
| `THINKING_LEVELS` | off/minimal/low/medium/high/xhigh/max | @57463576 |

### 11.2 "超过输出上限"报错的来源（实锤）

- `mapChatStopReason`：`finish_reason=length` → `stopReason: "length"`（无 errorMessage）（@75467076）
- **UI 文案（zh i18n，逐字）**（@27278934）：
  - `"message.maxTokens": "已达到输出 token 上限"`
  - `"message.maxTokens.hint": "回答被截断，已有输出保留在对话中。发送"继续"可让模型接着输出。"`
- ⇒ **用户所述"报超过输出上限 + 不停要继续" = DSH 对 `finish_reason=length` 的标准 UI 提示**（"继续"是 hint 建议操作）。

### 11.3 重要发现：DSH 的"可恢复 length 停止"检测

`isRecoverableLength(message, desiredMaxOutput)`（@78854866，逐字注释）：
> "Check whether a length stop ended **below the caller or model's intended output limit**. Such responses may be caused by **context pressure or provider-side truncation**, so callers can make one bounded compact-and-retry attempt."

- ⇒ DSH **明确知道**：length 停止可能"低于意图上限"（≠ maxTokens 打满），归因"上下文压力或 **provider 侧截断**"——**正对着我们的场景**。

### 11.4 思考预算的通路（重要）

- DSH 可选发**思考预算字段**（三种拼写）：`thinking_token_budget`（vLLM）/ `thinking_budget`（Qwen/DashScope/SGLang）/ `thinking_budget_tokens`（llama.cpp）（@57464353）
- **默认 off**——除非用户在 provider 配置显式设 `thinkingTokenBudgetField`
- 类型注释逐字（@78592010）："…the answer share `max_tokens` on these endpoints, so without a budget a reasoning-heavy turn can consume the whole response and emit no answer."——**DSH 自己证实"包含关系"**
- ⇒ 若用户配过 `thinkingBudgets` + `thinkingTokenBudgetField`：请求将带 `thinking_budget=<值>` → **引擎（20261008）解析并优先于服务端 tb**（已核对 `openai_chat_request.cpp:955-981`）

### 11.5 30 秒墙的收敛状态（更新）

| 候选 | 状态 |
|---|---|
| maxTokens=32768 打满 | ❌ 30 秒不可能（需 300+ s） |
| **DSH 请求级 max_tokens 实际值 ≈ 2048–4096**（provider 配置值，或 Anthropic 路径默认 4096） | ⭐ **待用户查 provider 配置** |
| **thinkingBudget ≈ 2048–4096（若用户配过）** | ⭐ **新候选**（待查） |
| 引擎侧截断（超池/lease） | 30 秒算术已排除（22K < 32K 窗口） |
| DSH watchdog 300s | ❌ 30 秒 ≠ 300s（但它是**独立存在的第二道墙**） |

### 11.6 回家核查清单（DSH 侧，更新）

1. DSH → 设置 → 模型（Models 页面）：本地引擎 provider 的 **maxTokens 实际值**（用户记忆 32K 需实证）；
2. 同页面：**thinkingBudgets**（是否配置过）+ **thinkingTokenBudgetField**（是否开启）；
3. 同页面：**streamIdleTimeoutMs**（是否覆盖默认 300000）；
4. 引擎日志：撞墙请求的 `output` / `finish` / `prompt`（定墙值）。

---

## 十二、第四轮：交叉复核收敛与"回家施工包"（2026-10-10）

### 12.1 对龙猫复核的审核（采纳 + 补强）

**采纳（它接受本环境的两处更正）**：① W2/W3 = "**消除 throw**"（非"类型化"）；② W4 必须含"**delta 非空**"（第三处，否则保活无效）。

**采纳（它对"锁定 2048"的自我降级）**：本环境同意——"2048"本就是"prompt≈20K"假设下的**点估计**（本报告 §9.1 敏感性表已标注），应表述为"**待 provider 配置确认**"。

**补强（本环境对"墙 = tb=16000"新候选的独立评估）**：

| 假设 | 速度要求（30 秒） | 与已知实测的匹配 |
|---|---|---|
| 墙 = DSH 请求 max_tokens（值 V） | V/30 tok/s | V=2048→68；4096→137；8192→273——**均在合理范围**（稳定 105，代码场景 184） |
| 墙 = tb=16000 | **533 tok/s 持续** | 748.6 是"5 秒窗口瞬时"（Bonsai A3，ngram 命中）；**持续 533 存疑**；且"输出耗尽"需再烧到 max_tokens（除非 max_tokens < 16000，见下） |

### 12.2 ⭐ 关键洞察：两分支决策树（症状机制取决于 max_tokens vs tb）

```
分支 A：max_tokens < tb（如 DSH 请求 4096 < 服务端 16000）
  → 思考烧光 max_tokens 即 length（control 永不触发——"包含关系"的直接 return 路径）
  → 30 秒 = max_tokens 的生成时间（68–137 tok/s，合理）
  → 解药 = 抬 max_tokens（DSH 侧）/ 或降 tb 到 < max_tokens（需 W2/W3 前置）
  → W1（==→>=）无关（control 根本不参与）

分支 B：max_tokens > tb（如 DSH 请求 32768 > 16000）
  → 思考到 tb=16000 → control 注入（== 恰好命中才触发；overshoot 则失灵）
  → 30 秒要求 533 tok/s（存疑，但 748 峰值说明高速段存在）
  → 解药 = W1（== → >=）+ W3（交接被拒不 throw）
  → 若思考交接成功：正文 ≤ max_tokens − 16000

⇒ **先查 max_tokens 实际值**——它决定走哪个分支、W1 是不是解药。
```

### 12.3 回家施工包（最终版）

**第 0 步（DSH 侧，3 分钟，零成本）**：
1. DSH → 设置 → 模型页：查 **maxTokens**（实际值）/ **thinkingBudgets**（是否配过）/ **streamIdleTimeoutMs**（是否改过）；
2. 引擎日志：grep 撞墙请求的 `req# done` 行（`output` / `finish` / `thinking` / `prompt`）；
3. ⇒ 定"30 秒墙"与分支（A 或 B）。

**第 1 步（引擎补丁，一次重编）**——4 项均为确定性缺陷，无条件执行：
- **W1**：`output_session.cpp:581` `==` → `>=`（1 字符）；
- **W2**：`:524` 超预算 throw → 消除（OutputLimit 结束回合 + 保留已产出）；
- **W3**：`:653/656` 交接拒绝 throw → 消除（同上模式）；
- **W4**：progress 保活 3 处（`openai_chat_http.cpp:54/117` 去门控 + `openai_chat_response.cpp:363/386` **delta 非空**）；
- 精确改前改后：见 `调研-对比研究-tancau-ninfer-kvmem-ring-CodeBuddy-20261010.md` **§十一**；
- 纪律：clean build / T-BACKUP / 编译+单测+lint / 产物落正式目录。

**第 2 步（DSH 侧配置，视分支）**：
- 分支 A：抬 maxTokens 到 ≥ 32768（若 UI 可改）；或降 tb（**W2/W3 完成后**）；
- 分支 B：不动 maxTokens（W1 修复后思考在 16000 熔断）；
- 通用：`streamIdleTimeoutMs` 调大（如 3600000）——防第二道墙（300s watchdog）。

**第 3 步（验证）**：
- W1 验收：tb=2000 + max_tokens=4096，思考 >2000 的请求 → 日志出现 control、finish 不应为 length；**负对照**：恰好 == 预算仍应触发；
- W2/W3 验收：故意触发超预算/交接拒绝 → **只废当前请求，引擎不崩**（并发请求仍服务）；
- W4 验收：长 prefill 流式请求 → DSH 不超时；抓包见每 chunk progress 事件。

**第 4 步（可选，W5）**：自噬循环实测（decode 每轮 restore 计数 / 时间分布）。

### 12.4 交叉复核记录

- 本环境 → 龙猫：更正 W2/W3 方向（"消除 throw"）+ W4 补第三处（delta 非空）——**龙猫全认**；
- 龙猫 → 本环境：提出"默认 32768 动摇 2048 假设"（**采纳，降级为待确认**）+ "tb=16000 候选"（**本环境补强为两分支决策树**，见 §12.2）；
- 双方收敛于同一结论：**唯一未知 = 用户现场 provider 配置（maxTokens 实际值）**，其值一查即定案。

---

*本稿为讨论记录（非施工文档）；源码引用基于 `engine-main`（20261008 基线 + 本项目补丁）与 DSH Desktop 安装版 `app.asar` 逐字读取，命令均为 `git show`/`git grep`/Node asar 搜索。*
