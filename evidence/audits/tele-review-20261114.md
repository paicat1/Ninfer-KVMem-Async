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
