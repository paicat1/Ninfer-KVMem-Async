# 《绝对安全意见书》test-run 已登记 6 份 BAK · 六项重评

> 依据：项目硬规则 §6「删任何文件前：审计 → 《绝对安全意见书》 → 用户点名 token」、决策 #0090 / #0091。
> **本文件为评估稿，不构成删除提案**：第 ⑥ 项未满足，按 #0091「缺一项＝提案无效禁止提交」，**不得据以执行任何删除、移动或覆盖**。
> 触发背景：2026-11-05 用户令「同意你的123」——① 改守卫 ② 出意见书 ③ 用户点名后才执行。本文件是 ② 的产出。

## 0. 范围界定

评估对象 = `engine\test-run\` 下 **6 份已在 lineage MANIFEST 登记**的 `.bak`：

| # | 文件（日期戳） | size (B) | SHA256 (前16) |
|---|---|---|---|
| 1 | `ninfer-serve.exe.bak_20261030_230643` | 1,333,991,424 | `35D9E6B191583759` |
| 2 | `ninfer-serve.exe.bak_20261031_100224` | 1,334,034,944 | `5B34F211D7C69909` |
| 3 | `ninfer-serve.exe.bak_20261031_102850` | 1,333,992,448 | `442DF90635347D20` |
| 4 | `ninfer-serve.exe.bak_20261031_140145` | 1,333,992,960 | `90FB3869D4312756` |
| 5 | `ninfer-serve.exe.bak_20261102_002537` | 1,376,953,856 | `9453FFC6FF077252` |
| 6 | `ninfer-serve.exe.bak_20261103_051116` | 1,333,820,928 | `322A972D6596A16D` |

**明确排除**：`C1972DCB…`（`bak_20261031_123144`）与 `02B5E65F…`（`bak_20261031_125544`）。这 2 份全项目 11781 个文本文件复扫 0 命中、台账 0 命中，是**唯一副本**，与本意见书的"已登记"性质相反，严禁纳入任何处置范围。亦排除 `engine\self-built-20261008\` 下 16 份 `.bak`（未在本次审计范围，需另出意见书）。

## 1. 身份判定 ✅

6 份全部为历史引擎可执行文件的换装备份，非活件本体。逐件在 `engine\lineage\MANIFEST.md` 有登记行，`BUILD_LEDGER.jsonl` 有归档行。

| BAK sha16 | lineage 对应件 | MANIFEST.md 行 |
|---|---|---|
| `35D9E6B1` | `ninfer-serve-RC6.exe` | 98 |
| `5B34F211` | `ninfer-serve-RC5.exe` | 13 |
| `442DF906` | `ninfer-serve-RC7.exe` | 99 |
| `90FB3869` | `ninfer-serve-PG3-20261031.exe` | 100 |
| `9453FFC6` | `ninfer-serve-RC2.exe` | 10 |
| `322A972D` | `ninfer-serve-RC1.exe` | 9 |

`[EVIDENCE] 命令输出: 35D9E6B1 => MANIFEST.md:98: | RC6 | ninfer-serve-RC6.exe | ...`

## 2. 产物归档 sha ✅

实测 `engine\lineage\` 对应 6 件 SHA256，与 6 份 BAK **逐字相同**；封存件带 `ReadOnly, Archive` 属性。

`[EVIDENCE] 命令输出: ninfer-serve-RC6.exe | sha16=35D9E6B191583759 | 35D9E6B1915837597207EDBD71AD17A3E83C7004F4C6A71668B904900A428838`
`[EVIDENCE] 命令输出: ninfer-serve-PG3-20261031.exe | sha16=90FB3869D4312756 | 90FB3869D43127566171E08064EF72126B16BD5C8D2087E554FB936BD2FA287C`
`[EVIDENCE] 命令输出: (Get-Item 'engine\lineage\ninfer-serve-RC8.exe').Attributes = ReadOnly, Archive`

## 3. 引用扫描 0 命中 ✅（本轮守卫改造后达成）

**改造前不满足**：`scripts\engine_ctl.ps1:277` 用 `Get-ChildItem $runDir -Filter 'ninfer-serve.exe.bak_*'` 逐份哈希比对现役件，是 `scripts/` 下的**依赖类读取型活引用**（按 2026-10-30 退役台账判据口径，依赖类须 0 命中）。

**本轮改造**：`scripts/engine_ctl.ps1` 的去重源改为 lineage `MANIFEST.md` 的 sha 清单，只采信「台账有 sha 且 `engine\lineage\` 中实体文件仍在」的行；台账不可读/为空时**保守新建备份，不静默跳过**。`+22/-5`，仅动去重块，`-Experimental` 覆盖保护与 `Copy-Item $Exe $runExe -Force` 未改。

`[EVIDENCE] git diff -- scripts\engine_ctl.ps1: - $same = Get-ChildItem $runDir -Filter 'ninfer-serve.exe.bak_*' ...`
`[EVIDENCE] 命令输出: dep_files=317 ;; dep_bak_mentions=10 ;; read_type_hits=0`

按证据纪律三段式：

- [方法] 扫 `scripts/ tools/ build/ .codebuddy/` 下 317 个 `.ps1/.py/.bat/.json/.jsonl/.md`，分别匹配「所有 `.bak` 提及」与「读取型引用（`Get-ChildItem|Get-Content|Get-Sha256Hex|Test-Path|Import-Csv|Copy-Item` + `.bak`）」
- [输出] `dep_bak_mentions=10`、`read_type_hits=0`；10 条中 8 条为 `.codebuddy\sda\engine-retired-20261030.md` 的记录表、1 条为 `feedback_lineage_first.md` 记录、1 条为 `engine_ctl.ps1:301` 的**写入型**备份名前缀
- [能证明] 依赖类目录中不存在读取既有 `.bak` 的代码；[不能证明] 不排除未被本扫描扩展名覆盖的二进制配置、外部脚本或人工作业流

## 4. 活件三源未命中 ✅

- 现役位 `engine\self-built-20261008\ninfer-serve.exe` = RC8 `B93B179176A0DC23`，**不在这 6 份中**（现役回滚锚点是 `engine\lineage\ninfer-serve-RC8.exe`）
- `engine_registry.json` 的 `path` 指向 `build-out\build-1208a\apps\...` 与 `engine\lineage\ninfer-serve-RC2.exe` 等，**不指向 `test-run` 的 `.bak`**
- `engine\lineage\` 自身是只读封存库，不引用 `test-run`

`[EVIDENCE] engine_registry.json: "path": "J:\\ninfer-kvmem\\engine\\lineage\\ninfer-serve-RC2.exe"`

## 5. 重建时长评估 ✅（已评估，结论偏保守）

引擎冷编 **55–66 分钟**（决策 #0090/#0091），属「长重建成本件（≥30 min）与成品」，按 #0090 **默认禁删、不进删除候选池**。虽然这 6 份是副本、可由 lineage `Copy-Item` 秒级还原（无需重编），但 #0090 的豁免需三条全满足，其中第 ② 条要求「重建需求被永久替代/废弃的**书面结论**——不是『我觉得以后用不到』」，本轮无此结论。

## 6. 用户书面结论 ❌ **仍缺（关键缺项）**

- 无「绝对不再重建 / 永久替代」书面结论
- 用户未点名到具体文件
- 无 `NINFER_APPROVED_DELETE` 令牌

且既有权威台账 `.codebuddy\sda\engine-retired-20261030.md:38` 明写 `| ninfer-serve.exe.bak_20261030_230643 | 1272 | 保留（当前件副本） |`——该件是 T#0074 事故锚点（编排脚本默认 `RC6` 曾把现役件错置）。按 #0091 第 ② 条「同一物件被否决后不得以相同理由再次提案，只有新证据才可重开并说明差异」，要动它需新证据 + 说明差异。

`[EVIDENCE] engine-retired-20261030.md:38: | ninfer-serve.exe.bak_20261030_230643 | 1272 | 保留（当前件副本） |`

## 结论

| 项 | 状态 |
|---|---|
| ① 身份判定 | ✅ |
| ② 产物归档 sha | ✅ |
| ③ 引用扫描 0 命中 | ✅ **本轮守卫改造后达成** |
| ④ 活件三源未命中 | ✅ |
| ⑤ 重建时长评估 | ✅ 已评估（默认禁删类） |
| ⑥ 用户书面结论 | ❌ **缺** |

**六项 5/6，按 #0091 本文件不构成有效删除提案，不执行任何删除。** 本轮唯一已实施的动作是改守卫（`scripts/engine_ctl.ps1`），它解决的是"别再机械堆 1.27 GB 副本"（本次改造后，现役 RC8 的 sha 已在 lineage MANIFEST 中，起实验件时 `skipBackup=True`，不再生成重复备份），**不是**为删除放行。

若后续决定推进，需用户：① 点名到具体文件 ② 签发 `NINFER_APPROVED_DELETE` ③ 对 #1（RC6）给出新证据与差异说明；执行后回填 `.codebuddy\sda\engine-retired-20261030.md` 与本意见书结论。

## 附：守卫改造 T-VERIFY 记录

`PS SYNTAX OK` / `bytes=18831 crlf=495 bare_lf=0 bom=239,187,191` / 覆盖保护 `if (-not $Experimental)` 与 `Copy-Item $Exe $runExe -Force` 仍在 / 台账解析 `sha_rows=51 missing_artifact_filtered=0 accepted=51` / RC8 与 6 份已登记 sha 全命中、未登记件 `C1972DCB` 正确不命中 / 三态回归 `RC8_IN_LEDGER skipBackup=True`、`UNKNOWN_HASH skipBackup=False`、`LEDGER_MISSING skipBackup=False` / `check_refs.py` 断链 `24 = 基线 24` 零新增。
