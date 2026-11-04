# 审计：`engine\self-built-20261008\` 下 16 份 `.bak` 删除安全报告

> 用户令：「那几个可以安全删除的？报告。并审计 `engine\self-built-20261008\` 下 16 份 `.bak`」
> 依据：项目硬规则 §6、决策 #0090 / #0091、《绝对安全意见书》六项判据。
> **本报告只审计、只报告，不删除、不移动、不覆盖任何文件。** 第 ⑥ 项（用户书面结论）仍缺，按 #0091「缺一项＝提案无效禁止提交」，**不构成删除提案**。

## 0. 结论摘要

| 类别 | 份数 | 体积 | 判定 |
|---|---|---|---|
| **A. 字节层面可安全删除候选**（有 lineage 同 sha 只读副本） | **10** | ≈12.46 GiB | ①–⑤ 项达成、⑥ 缺点名 token ⇒ **当前不可执行** |
| **B. 全项目唯一副本** | **6** | ≈7.39 GiB | **严禁删除**（删后字节永久消失） |
| 合计 | 16 | 19.85 GiB | 无现役进程占用 |

另有 `engine\test-run\` 8 份（不在本次审计范围，结论见 §5）：6 份已登记属 A 类候选、2 份未登记属 B 类严禁。**全仓 A 类候选合计 16 份 ≈ 19.9 GiB，B 类严禁合计 8 份。**

## 1. 逐件身份与判定（16 份，SHA256 全部实测）

| # | 文件（`ninfer-serve.exe.` 前缀省略） | size (B) | sha16 | lineage 对应件 | 判定 |
|---|---|---|---|---|---|
| 1 | `bak_20261011_203641` | 1,333,438,976 | `B8F62A38` | — | **B 唯一副本** |
| 2 | `bak_20261011_233701` | 1,317,075,968 | `8FCA9146` | — | **B 唯一副本** |
| 3 | `bak_20261011_235516` | 1,317,261,824 | `16698451` | — | **B 唯一副本** |
| 4 | `bak_20261012_024944` | 1,317,262,848 | `B0E9B1A1` | — | **B 唯一副本** |
| 5 | `bak_20261012_073043` | 1,317,263,872 | `298948C4` | — | **B 唯一副本** |
| 6 | `bak_20261101_231713` | 1,333,820,928 | `322A972D` | `ninfer-serve-RC1.exe` | A 候选 |
| 7 | `bak_20261102_013216` | 1,333,992,960 | `90FB3869` | `ninfer-serve-PG3-20261031.exe` | A 候选 |
| 8 | `bak_20261102_062139` | 1,333,992,960 | `90FB3869` | 同上 | A 候选 |
| 9 | `bak_20261102_080630` | 1,333,992,960 | `90FB3869` | 同上 | A 候选 |
| 10 | `bak_20261102_204422` | 1,333,992,960 | `90FB3869` | 同上 | A 候选 |
| 11 | `bak_20261102_205127` | 1,333,991,424 | `35D9E6B1` | `ninfer-serve-RC6.exe` | A 候选 |
| 12 | `bak_20261103_032314` | 1,333,992,960 | `90FB3869` | `ninfer-serve-PG3-20261031.exe` | A 候选 |
| 13 | `bak_20261103_050538` | 1,333,992,960 | `90FB3869` | 同上 | A 候选 |
| 14 | `bak_20261103_050957` | 1,333,992,960 | `90FB3869` | 同上 | A 候选 |
| 15 | `bak_20261103_051325` | 1,376,953,856 | `9453FFC6` | `ninfer-serve-RC2.exe` | A 候选 |
| 16 | `bak_pre_W1W4` | 1,333,439,488 | `65516EEE` | — | **B 唯一副本** |

16 份只有 **10 种不同 sha**：`90FB3869`（PG3）独占 7 份，是冗余主体。

`[EVIDENCE] 命令输出: count=16 distinct_sha=10 ;; UNREGISTERED = 6 ;; ARCHIVED_IN_LINEAGE = 10`
`[EVIDENCE] work\data\audit_selfbuilt_bak.json: 逐件 sha256 / manifest_entries / lineage_artifacts / verdict`

## 2. A 类 10 份：六项意见书判定 **5/6**

| 项 | 判定 | 依据 |
|---|---|---|
| ① 身份判定 | ✅ | 全为历史引擎备份，非活件本体；10/10 在 `MANIFEST.md` 有行、lineage 有实体 |
| ② 产物归档 sha | ✅ | RC1/PG3/RC6/RC2 四个 lineage 件在 2026-11-05 审计中已实测 sha 与对应 `.bak` **逐字相同**；本轮台账对账 10/10 命中且实体存在 |
| ③ 引用扫描 0 命中 | ✅ | `dep_files=318 / dep_bak_mentions=12 / read_type_hits=0`；12 条全为记录类台账或 `engine_ctl.ps1:301` 写入型备份名前缀 |
| ④ 活件三源未命中 | ✅ | 现役位 `ninfer-serve.exe` = `B93B179176A0DC23`（RC8）；`engine_registry.json` 四条 path 指向 `build-out\build-1208a\apps\` / `engine\lineage\RC2` / `engine\lineage\RC3` / `engine\self-built-20261008\ninfer-serve.exe`，**均不指向 `.bak`**；无 `ninfer-serve` 进程 |
| ⑤ 重建时长评估 | ✅ 已评估 | 冷编 55–66 min（#0090/#0091）属长重建成本件与成品，**默认禁删**；副本可由 lineage `Copy-Item` 秒级还原，但 #0090 豁免需三条全满足 |
| ⑥ 用户书面结论 | ❌ **缺** | 无「绝对不再重建 / 永久替代」书面结论、未点名到具体文件、无 `NINFER_APPROVED_DELETE` |

**⇒ 按 #0091，本报告不构成有效删除提案，A 类 10 份当前一份都不能删。**

`[EVIDENCE] 命令输出: dep_files=318 ;; dep_bak_mentions=12 ;; read_type_hits=0`
`[EVIDENCE] 命令输出: live_sha16=B93B179176A0DC23 ;; registry 基线/生产/判决件/封存 四条 path`
`[EVIDENCE] 命令输出: ninfer-serve-RC6.exe sha16=35D9E6B191583759 ;; ninfer-serve-PG3-20261031.exe sha16=90FB3869D4312756 ;; ninfer-serve-RC2.exe sha16=9453FFC6FF077252 ;; ninfer-serve-RC1.exe sha16=322A972D6596A16D`

## 3. B 类 6 份：**全项目唯一副本，严禁删除**

判据按 T#0079 三段式：

- [方法] ① 台账对账：`MANIFEST.md` 51 行 64-hex sha 集合无命中；② `archive\temp-root-20261030\hash_cache.json` 查同 sha 的其他路径；③ **全项目（排除 `refs`/`engine-src`/`logs`）按 size 扫所有文件**——同 sha 必同 size，这是严格的必要判据；④ 在正确的台账路径（`docs\01-构建与发布\BUILD_LEDGER.jsonl`、`engine\BUILD_LEDGER.jsonl`、`engine\lineage\MANIFEST.txt`、`deploy_history.txt`）复扫 sha 字面量
- [输出] 同 sha 的其他缓存路径 **全部 `exists=False`**；`size_matched_files=6` 且**恰好只指向这 6 份自己**；`lineage 26 exe min=1333769216 max=1377789952 / overlap_with_6_sizes=0`；`hash_cache` 对 lineage 覆盖率仅 `10/26`（故不能靠缓存下否定结论）；记录类登记存在（`deploy_history.txt` 5 个 sha 命中、`65516EEE` 在 `产物清单.md` 与 `MANIFEST.txt` 有行），但**无实体副本**
- [能证明] 在本机被扫描范围内，这 6 个 sha 的字节只存在于这 6 份 `.bak`；[不能证明] 不排除外部机器、未挂载介质或本次未扫描的二进制容器

`[EVIDENCE] 命令输出: size_matched_files=6 ;; lineage=26 min=1333769216 max=1377789952 ;; overlap_with_6_sizes=0`
`[EVIDENCE] 命令输出: lineage_exe=26 cache_covered=10 ;; J:\ninfer-kvmem\engine\lineage\... 之外的同 sha 路径 exists=False`
`[EVIDENCE] 命令输出: 65516EEE ledger_hits=0 ;; B8F62A38 ledger_hits=3 (deploy_history.txt) ;; 8FCA9146 ledger_hits=6`

**取证价值**：这 6 份是 10 月初 v2 异步 demote / v2.1 / W1W4 等代际的唯一实物，`deploy_history.txt`、`night_watch_snapshot_0412.md`、`valley_history.md`、`ninfer-kvmem-项目构建史.md:1665` 均引用其 sha 作为历史判据；`65516EEE` 是 10-08 初始基线（`MANIFEST.txt:1`）。删掉即永久丢失按现源码无法重建的字节（退役台账 2026-10-30 已有同型教训：「不可回滚：这些件按现源码无法重建同一字节」）。

## 4. 两处更正与一个方法论坑

- 上一轮我猜 `BUILD_LEDGER.jsonl` 在项目根并报 `Cannot find path`——按证据纪律只能记为「该路径未查到」；本轮定位到实际两处：`docs\01-构建与发布\BUILD_LEDGER.jsonl`（39 行）与 `engine\BUILD_LEDGER.jsonl`（24 行）。
- `hash_cache.json` 只覆盖 lineage 26 件中的 **10 件**，用它下「没有归档副本」会误判；本轮改用 size 全扫这一严格判据才闭合（记 T#0081）。
- 16 份无 `ninfer-serve` 进程占用（`Get-Process` 空），但「未被占用」不等于「可删」——⑥ 仍缺。

## 5. 与 `engine\test-run\` 8 份的合并总账

| 位置 | 类别 | 份数 | 处置 |
|---|---|---|---|
| `self-built-20261008` | A 已归档候选 | 10 | ①–⑤ 达成、⑥ 缺 ⇒ 待点名 |
| `test-run` | A 已登记候选（上一轮意见书 5/6） | 6 | 同上 |
| `self-built-20261008` | **B 唯一副本** | 6 | 严禁 |
| `test-run` | **B 未登记唯一副本**（`C1972DCB` / `02B5E65F`） | 2 | 严禁 |
| `engine\lineage\` | 26 件只读封存 | 26 | 永久只读，反溯链权威，严禁 |

**A 类合计 16 份 ≈ 19.9 GiB**（`J` 盘可用 37.3 GiB）。若 ⑥ 满足，释放这批是唯一有实质空间收益且字节无损的动作；但按 #0090 需「绝对不再重建」书面结论，按 #0091 需点名到具体文件 + `NINFER_APPROVED_DELETE` 令牌。

## 6. 边界

本轮**未删除、未移动、未覆盖任何文件**。要推进须用户：① 点名到 A 类具体文件（不含任何 B 类）② 签发 `NINFER_APPROVED_DELETE` ③ 对涉及既有「保留」书面结论的件给新证据 + 差异说明。执行后须逐件复核 sha 并回填 `.codebuddy\sda\engine-retired-20261030.md` 与本报告。
