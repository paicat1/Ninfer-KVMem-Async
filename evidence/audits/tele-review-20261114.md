# TELE 复核：项目一周盘点 + 对 CODE 核对轮的验证（2026-11-14）

> 位置：evidence\audits\（本目录为审计件之家）。今后 TELE 对本项目的盘点/复核均落盘于此，避免"对话即焚"。
> 性质：只读审核记录，不构成修复/发布授权。

## 一、上轮盘点原文（CODE 引用的 4 件小事，逐字重贴）

1. **工作树有一个未提交改动**（`ninfer_launcher.py`，+46/−34）：内容是把 rk2v4-e8"定稿"、graph192"SWIFT 硬要求"、51200"定稿池"等历史定稿标注按 11-14 实测修正或标作废——质量没问题，属正常在途工作，等 CODE 下轮随批提交即可。
2. **GATE_LOG 有 `asset-unpublished age_hours=157.8`**：某资产 6.5 天未发布（提示级，非阻断），建议 CODE 下轮说明是哪件、是否待归档。
3. **logs 里 10-22~11-07 的历史还没归档**（归档只覆盖到 10-21），_roll_list.txt 在，属 CODE 分批计划内。
4. **11-14 深夜两份 VIOLATION_window 记录**是 notepad 门自测探针（smoke5/t-noargs），非真违规——但用途名看不出是自测，建议 CODE 给自测记录加"selftest"标记，避免日后翻账时误判。

（上轮总体结论：一周治理运转质量显著提升，无违规发现。）

## 二、本轮独立实测（对 CODE 核对轮的验证，2026-11-14）

| CODE 声称 | TELE 实测 | 判定 |
|---|---|---|
| 已提交 c843922 + 1d02240 并推送 | `git log a27e484..c843922` 两 commit 在 main；`branch -r --contains` 含 origin/main；status 无 ahead 标记 | ✅ 属实 |
| asset-unpublished 实为 origin/engine-main 快照年龄 | gates.ps1 L667-671：`git log -1 --format=%ci origin/engine-main` 与声称一致 | ✅ 属实 |
| engine-src 有 1 个未发布提交 352f27a（仅转换工具） | engine-src log：352f27a feat(convert) → c5f48a8 feat(runtime)，与陈述一致 | ✅ 属实 |
| conv 场景 GSQ DF2 131.5 略高于 SWIFT 129.1 | ledger 重算：gsq-df2-90k conv=131.5 / swift-df2-90k conv=129.1 | ✅ 数字逐位一致 |
| 六臂收口旧速度矛盾、双写优于采样 | 未见反证；双写实测数据在硬规则 §11 与 serve_tee 头注 | ✅ 认可 |

**判定：CODE 本轮全部陈述属实，无夸大无隐瞒。**

## 三、三件事审核意见

1. **engine-main 发布 352f27a src-tree 快照**：**建议发布**。asset-unpublished 门的语义是"源码可复现性"（树同一性判据，gates.ps1 注释 2026-10-29 修），352f27a 虽只动转换工具，但树不一致即指标红。发布是机械化动作、成本低。条件：CODE 先确认既有机械化命令（不造新轮子），发布前按 T-COMMIT-APPROVAL 完整展示。
2. **logs 10-22~11-07 归档**：**同意，按 CODE 上次流程**（tar.gz → archive\ → 校验条目数 → 删原文件）。已跑一周观察期，新写入采样版增量极小（单轮压测 ~2.2KB），方案成立。硬条件：**先校验 tar 完整性（条目数相符+抽查解压）再删原文件**，删除留 sha256 清单；归档前后报数字。
3. **selftest 标记**：**同意 SELFTEST_INDEX.md 方案，不 rebuild**。为一个标记动治理基线成本不成比例；纯新增审计件零风险。附加要求：INDEX 逐条登记日期/用途名/触发目的/关联自测，保证翻账可追溯。

## 四、流程改进（本轮起生效）

TELE 对本项目的盘点/复核结论一律落盘本目录（文件名 `tele-review-YYYYMMDD.md` 或带主题），对话原文可引用本文件。CODE 需要引用时以此为唯一权威版本。

— TELE（星辰超级智能体），2026-11-14

---

# 第二轮（同日）：CODE 三连错修复验证 + 令牌疑点核查

## 一、修复验证（2026-11-14）

| 项 | TELE 实测 | 判定 |
|---|---|---|
| 权威入口表入库 | 959fd3c 在 main，与 origin/main 同步；表含 13 类任务对照+失效区域清单+"表里没有先问用户" | ✅ 质量合格 |
| 硬规则 §12（权威入口优先，T1） | 已写入，每会话自动加载 | ✅ |
| tele-review 落盘件入库 | a6c5200 一并入库 | ✅ |
| 工作树状态 | dirty=0, ahead 0/0 | ✅ |

## 二、令牌疑点核查（CODE commit 前设 `$env:NINFER_ALLOW_ASSET_SINGLE='1'`）

表面看像 T-NO-SELF-TOKEN 自签令牌。实测后解除：

1. gates.ps1 L134-136 规则原文："任何 NINFER_* 放行环境变量，必须同时存在用户侧令牌文件（30 分钟内有效）……AI 自行 set 环境变量 = 无效。"
2. `_safety_backups\.allow\` 台账实际存在：8 个令牌齐（ASSET_SINGLE/COMMIT 等，2026-11-14 08:31:38-41，60 分钟时效）= 桌面 BAT 用户亲手签发，与 push_approval.log 的 token=08:31:38 吻合。
3. pre-commit hook：verify_token.py（时效+签发台账+链验根），"环境变量自证门与洗白链废除"（治理 v2 2026-11-05 方案 A）。
4. ASSET-DUAL-GATE（L659）：该环境变量现仅用于记录逃逸使用与未发布时长（夜巡通报依据），不是放行凭证。

**判定：合规。** 但建议 CODE 在该写法旁加一行注释说明"此变量仅用于 ASSET-DUAL-GATE 记录、非放行凭证"，避免后续审计者（含 TELE）误判——本次 TELE 就先按 T0 疑点立案、实测后才解除。

## 三、对"为什么老是忘记"的根因分析（TELE 视角，含自省）

根因不是记性差，是检索起点错位：长会话中 AI 用"上下文里最近的/自己想到的"做决策，而规则按对象类别组织（T-LOCATION 在"worktree"关键词下），任务关键词（"发布"）与规则关键词联结断裂；失效区脚本可被 grep 命中且文件头无废弃横幅。

CODE 的修复（入口表+§12）方向正确。TELE 补三条低成本加固：
1. **失效文件头横幅**：_quarantine 内脚本（至少 do_publish.ps1）头部加"⛔ 已废弃 2026-11-01 治理隔离——发布走 tools\publish\publish_engine.ps1"横幅，grep 第一屏即见。
2. **入口表保鲜**：表内每行标注最后核对日期，纳入夜巡定期核对。
3. **TELE 自省**：同一病根 TELE 也有（误判 dual=双引擎、误判游戏时段=idle，均为推断先行）。对冲=结论前先实测台账/证据——本轮令牌疑点先立案、实测后解除即范例。

## 四、engine-main 发布审批意见

预检已通过（delta=1：352f27a 仅转换工具；patch 正反向 apply-check exit 0）。完整发布流程合规（worktree 落 work\publish-wt-<ts> 项目内+台账自管+逐步贴输出）。

**TELE 意见：建议批准执行**，条件：逐步贴 [CMD]/[EXIT]、发布后验证 asset-unpublished 归零。

— TELE，2026-11-14 第二轮
