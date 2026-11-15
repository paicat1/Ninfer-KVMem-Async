# 技术审计记录（2026-11-14）

> 外部独立复核对本项目**技术结论**的验证。治理流程类讨论不在本文件。
> 记录时间：2026-11-14

## 一、发布状态验证

| 项 | 实测 | 判定 |
|---|---|---|
| `origin/engine-main` | `b9a9cc6`，`src-tree` 树哈希本地 = 远端（`89afe6d4…`） | 一致 |
| `main` | 与 `origin/main` 同步，`dirty=0` | 同步 |
| `gates.ps1` 全量 | `exit 0` | 全绿 |

## 二、基准数字复核

| 声称 | 独立重算 | 判定 |
|---|---|---|
| conv 场景 GSQ DFlash2 `131.5` 略高于 SWIFT `129.1` | ledger 重算：`gsq-df2-90k conv=131.5` / `swift-df2-90k conv=129.1` | 逐位一致 |
| 六臂同口径收口了旧速度矛盾 | 未见反证 | 认可 |
| 双写日志优于原采样方案 | 实测数据见 `serve_tee.py` 头注 | 认可 |

## 三、`engine-main` 快照发布（`352f27a`）

`asset-unpublished` 门的语义是**源码可复现性**（树同一性判据）：`352f27a` 虽只动转换工具，但树不一致即指标转红。

预检结果：`delta=1`、`patch` 正反向 `apply --check` 均 `exit 0`；发布流程落 `work\publish-wt-<ts>`（项目内）+ 台账自管。

## 四、其他技术项

| 项 | 结论 |
|---|---|
| `logs` 10-22~11-07 归档 | 按既有流程：`tar.gz` → 校验条目数 + 抽查解压 → 删原文件；一周观察期已过，增量极小 |
| `selftest` 标记 | 采用索引文件方案（`evidence/audits/SELFTEST_INDEX.md`），不动治理基线 |
| 126,976 / 90,112 等池上限 | 与实测 FATAL 边界（131,072 / 94,208）吻合 |

## 五、SDA v2.6 升版验收（机械件与对账）

| 项 | TELE 独立实测 | 判定 |
|---|---|---|
| MANIFEST 重算 | 80 条与实际文件 1:1（`missing=0 extra=0`），分布 deploy-kit 42 / apply 13 / baselines 8 / history 10 / 根散 6 / 纲要 1 | 通过 |
| `T-AUTHORITY-ENTRY` 追加 | 铁律 129 行 LF，与请批稿逐字一致（T1、五条硬约束） | 通过 |
| v2.6 快照 | 27 行，六节结构与 v2.5 对齐；"已知未解"如实登记 | 通过 |
| 备份 | 铁律 / 部署指南 / VERSION 三件 pre-备份在 `_safety_backups` | 齐全 |

## 六、`manifest_recalc.ps1` 固化验收

- UTF-8 BOM、解析 0 错误；排除规则三常量写死（`_safety_backups/`、`MANIFEST.json` 自身、`*.tmp`）
- 计入范围括注两处落位（铁律 / 项目硬规则），指向固化脚本为单一真相源
- `-Check` TELE 独立复跑：`old=81 new=81 added=0 changed=0 removed=0`（零漂移）
- 终态：`manifest=81 actual=81 missing=0 extra=0`
- 脚本内建两项机械义务：重算前自动备份旧 MANIFEST、重算后自动产出三类差异清单——"靠人记得"环节归零

## 七、SDA 权威侧执行方式裁决（技术面）

分两批：纯新增先做（模板 + 横幅脚本，出错可删），改既有受管件逐项请批；外部复核方保持独立复核位、不转执行者（施工与审核分离）。`J:\sda管理` 纳入 git 暂缓（自研 MANIFEST+history+备份区已承担对账职能，git 化属重复治理）；代偿兜底 = 独立方夜巡定期跑 `-Check`，漂移必被发现。

## 八、对话层门禁方案审核（4 道）

| 门 | 技术判定 |
|---|---|
| A 起服条件对账（已落地） | 设计正确：只认日志 CMD 行与 env dump、不认自述；双向实测（正向 PASS / 反向 BLOCKED）。定位 = 防静默、非事前预防。挂入 `gates.ps1` 走 rebuild 流程；增强：`-Expect` 预期表须附来源引用（上次日志 CMD 行或指令原文），防预期表本身凭记忆写错 |
| B 复现门 | 同意做；强制点建议放落盘侧——含归因词（退化/上限/崩塌/唯一解释）的结论落盘为报告/审计件时，由提交侧门强制要求 `evidence/repro/<case>.md`（≥2 次同条件数据 + 对比表） |
| C 证据编号 / D 因果词扫描 | 缓行一周：执行者缺口（AI 自查自己仍属软约束，外部锚 = 独立复核方跑门或提交侧 hook）+ D 噪声率待观察 |

## 九、挂账（技术项）

- 横幅动作的 SDA 侧批量部署（下批，带 `py_compile` + `[scriptblock]::Create` 双后置断言）
- 门 B 落地 + 门 A 挂入 `gates.ps1`（rebuild 流程）
- C/D 一周后按 A/B 实际效果再定
- `J:\sda管理` git 化（暂缓；触发条件：需要版本历史 / 远端备份时再议）

## 十、边界说明（2026-11-14 更新）

本文件只登记**技术事实的第三方复核**。工作流程、协作机制、账目类内容不在本文件，按 2026-11-14 用户约定：**技术复核落盘，其余只留对话。**

## 十一、启动器面板修复与 A1–A6 问题清单逐条核验

### A1–A6 代码级核验

| 条目 | 独立核验（`ninfer_launcher.py`） | 判定 |
|---|---|---|
| A1 fallback 历史值 | L589 `KVCAP_OPTIONS.get(str(combo.get("kvcap","51200")), KVCAP_OPTIONS["51200"])`；L1217 / L1357 / L1434 同为字面 `"51200"`；L1364 `combo.get("graph","128")`。均未引用 L851 `DEFAULTS` | 证实 |
| A2 不经 LEGACY_VALUE_MAP | `LEGACY_VALUE_MAP`（L892）仅用于 profile 旧值迁移（L2539）；`build_command`（L1417）fallback 链不经过它 | 证实 |
| A3 vram_account fallback | L1357 kvcap `"51200"`、L1362 `.get(model, 12.30)`、L1379 hostkv `"16384"` | 证实 |
| A4 VRAM_WEIGHTS_GIB 不全 | L1289 仅 `{"orig": 12.40}`；swift/gsq/q2lynn 均落 12.30（L1362）。结构缺陷成立；"低估 1–1.7 GiB" 的定量未附逐件实测数据，幅度存疑 | 结构证实 / 数值存疑 |
| A5 readiness_test 硬编码 | L1597 `"model": "qwen3.8-27b"`；`model_ids.json` 四个 id 均不含该值 → 与服务端注册 id 必不匹配（"必然失败"成立；"404" 具体码取决于引擎校验，404/400 均可能） | 证实 |
| A6 MODEL_KVCAP_MAX 无 gsq | L244–260 仅 `q2lynn=86016 / swift=126976`；L2097–2099 `cap = MODEL_KVCAP_MAX.get(...)` 无键即 `return` → gsq 无强制降池联动；L1180 全局超限告警同样查该表 → gsq 亦无告警。通道级告警表（`MODEL_KVCAP_MAX_IGPU/DGPU`，L276/L291）未逐键核对，gsq 是否被覆盖待查 | 证实 |

### 治理基线机制核验

- `scripts/gates.ps1` 被 `.gitignore:127` 排除（无 git 回滚手段）；2026-11-14 19:28:37 修改（41,911 B），挂载点 L915（`start_cond_gate`）/ L954（`launcher_dim_gate`）确认在位
- post 基线快照 `scripts__gates.ps1`（37,977 B / 2026-11-05 21:46:38 / 无挂载点）= 当前 gates.ps1 的**改前内容**（gates.ps1 自 11-05 起无中间变更）→ 改前状态可由该快照完整恢复
- `work/data/rebuild_gov_baseline_multi.py` 设计上只替换 MANIFEST.json 内哈希 + 备份旧 MANIFEST + 更新外锚，**不刷新快照文件** → 快照与 MANIFEST 名实分离系脚本机制所致，非执行遗漏；MANIFEST 今日重建 4 次（17:26:57 / 17:28:48 / 18:10:56 / 19:28:45，均有 `.bak`）
- 风险：快照已不等于当前版本，"实体备份"语义失效；下次全量重建将覆盖旧快照，11-05 版不可恢复
- 本批 rebuild TARGETS 含 `structure.json`（哈希已更新）；structure.json 本批具体变更内容未列入交付说明，diff 未审（待补）

### model_ids.json 单一真源方案核验

- launcher 侧 L228–238：读 `model_ids.json`，失败即 `SystemExit`（fail-fast）
- `engine_ctl.ps1` diff：`Test-Path` 缺文件 `exit 1`；switch 四分支含 gsq；无匹配 `exit 1`。同时修复既有 bug：原 switch 无 gsq 分支，gsq 件落 default 得 coder390 id
- 残留：readiness_test payload（A5）未接入该真源；`bench.py` / `parlast.py` 的第三 id 是否同步未核

### claim_repro_gate.ps1 变更核验

- 在原 `evidence\audits` 排除上追加 `evidence\repro` 排除（复现记录自引用递归，理由成立）
- 影响：`evidence/repro` 下文件不再受"归因词 ≥2 次复现"约束，覆盖面缩小，如实登记

### 门禁工作流陷阱

- 项目内 `py_compile` 会生成 `__pycache__` → 触发 UNDERSCORE 门 → 全量 GATES BLOCKED；先清缓存再跑门即绿。处置方式（structure.json 登记白名单 / 固化清理步骤 / 维持现状）待裁决

### 本轮验证已过项

- kvwindow 已入 f2 渲染元组（L1915）；编译通过；面板渲染自检三件套在位（L1831/L1894/L1973–1977）；维度对账门独立实测 PASS（DIMENSIONS 25 项 / 面板 26 项 / 缺失提示 0）；启动器运行中、`launcher_errors.log` 未产生（无渲染缺项）

### 修复建议（审核方判定）

审核方判定：A1–A6 属**实际功能缺陷**而非风格问题，建议修复；方案0（不修）被否。理由：A5 使就绪自测信号永久失真（每次必败＝自检失效）；A6 使 gsq 档失去池护栏与超限告警（gsq 为最新双头件、常用档）；A1/A2/A3 使旧 profile 缺键时拼出历史命令（51200 池 / graph128 / k3 等）。

修复优先序（一批一变量、逐批审批、修复由 CODE 实施后本方复核）：

1. **A5**：payload `"model"` 改接 `MODEL_IDS`（1 行，真源方案收口）
2. **A1+A2+A3**：fallback 链改为引用 L851 `DEFAULTS`，spec 旧值经 `LEGACY_VALUE_MAP` 迁移（同一批，diff 全量展示）
3. **A4**：表内先入已核实实测权重（swift 11.91 GiB 注释在案；另一处 12.64 GiB 对应件名口径需核对文件大小后再入），gsq 权重待实测补
4. **A6**：先核 `MODEL_KVCAP_MAX_IGPU/DGPU` 是否已含 gsq 键（决定告警现状），再补 gsq 实测上限标定（起服实验）后添键——禁止借 swift 值冒充实测

## 十二、修复批复核（第二轮：A1–A6 + 三项基建修复）

### 已证实项（复核方独立核验）

| 项 | 独立核验 | 判定 |
|---|---|---|
| A5 | `readiness_test` 签名加 `model_id`（L1617），payload 改 `_probe_model = model_id or MODEL_IDS.get(DEFAULTS["model"])`（L1637-1640），无硬编码 id | 通过 |
| A1/A2 | `build_command` 统一 `_c = dict(DEFAULTS)` 兜底（L1452），全维度 fallback 引 `DEFAULTS[...]`（L1466-1483）；spec 旧值过 `LEGACY_VALUE_MAP`（L1454） | 通过 |
| A3 | `vram_account` fallback 对齐（L1384） | 通过 |
| A6 降池 | `_apply_model_coupling` 改按 `resolve_channel()` 取 `MODEL_KVCAP_MAX_IGPU/DGPU`（L2146-2151），通道不明用 DGPU 保守表 | 通过 |
| A6 表数据 | IGPU 含 gsq=126976 / gsq_dflash2=90112（L300-301），DGPU 含 gsq=65536 / gsq_dflash2=40960（L291-292）。**复核方更正**：此前"gsq 亦无告警"表述有误——通道告警一直存在（validate 查 IGPU/DGPU），缺失的仅是强制降池 | 更正采纳 |
| pycache 陷阱 | gates.ps1 L516-520 排除 `__pycache__`；复核方独立复跑：py_compile 生成缓存后直接跑全量门禁 exit=0 | 通过 |
| 外锚同步 | MANIFEST sha256 = `.gov_anchor` = E4C593FF… | 通过 |
| 快照归档 | `_history/20261114_201013/` 存在（37 件） | 通过 |
| 功能验收 | 用户面板肉眼确认 kvwindow 可见、自检 25/25、启动器 running=1 无错误日志 | 通过 |

### 不实/缺陷项

1. **"gates.ps1 快照已刷新、快照=工作区一致"不成立**。实测：快照 `scripts__gates.ps1` 哈希 5E475B93（仍为 2026-11-05 旧版），工作区 979E7AC5。根因：`rebuild_gov_baseline_multi.py` L66 `dst = os.path.join(SNAP_DIR, os.path.basename(tgt))` 将 `scripts/gates.ps1` 错映射为 `SNAP_DIR\gates.ps1`（孤儿文件），真快照 `scripts__gates.ps1` 未被触碰；`structure.json` 因 basename 恰等于快照名而"一致"为真。交付方报告的对比输出读的是孤儿文件——单步输出皆真、对照对象错误。名实分离未修复，形态变为：MANIFEST=新哈希 + 真快照=11-05 + 基线目录多孤儿文件。
2. **MANIFEST size 字段失真**：登记 gates.ps1 size=37977，实际 42404（rebuild 仅字符串替换哈希，不更新 size）。
3. **基线目录新增 4 个未登记文件**：`gates.ps1`（孤儿）+ `start_cond_gate.ps1` / `claim_repro_gate.ps1` / `launcher_dim_gate.ps1`（EXTRA_SNAPSHOT 只复制不登记）——快照与 MANIFEST 不再 1:1。
4. **A4"6 条实测值"标注不符**：swift 12.3 引 `test_win65k_42k.log`（该日志对应件未证）、gsq 11.30 为注释推导（交付方已自报）、q2lynn MTP 12.30 出处不明（疑沿用旧默认）；表内矛盾未解：q2lynn 14.02−12.30=1.72 与 MODEL_BUNDLES 注释"DFlash2 比 MTP 多 1.2 GiB"（L340）冲突。
5. **审批包缺口**：`scripts/engine_ctl.ps1`（model_ids 真源配套改造，修 gsq 落 coder390 id 既有 bug）未暂存——仅提交 staged 七件将造成库内 launcher 读真源而 engine_ctl 仍为旧硬编码 switch 的不一致状态。

### 结论

修复代码本体（A1/A2/A3/A5/A6 + pycache 排除）质量合格；**快照覆盖声称不实**（basename bug，名实分离未修复）；A4 数字来源需标注澄清；engine_ctl 入包待决。commit 批准建议待上述三项澄清后作出。

### 修订 2 复核（快照真修 + A4 来源标注 + engine_ctl 入包）

| 项 | 独立核验 | 判定 |
|---|---|---|
| 三方对账（亲测） | gates.ps1：登记 979E7AC5 / 42404 B = 工作区实算 = 快照本体 `scripts__gates.ps1` 实算；structure.json：E8EE94C1 / 29835 B 三处一致（旧登记 29813 为 stale size 修正，哈希自始未变，自洽） | 通过 |
| 外锚 | `.gov_anchor` = MANIFEST sha256 = 6BC835A7… | 通过 |
| 孤儿清理 | 基线根目录 4 个孤儿（gates.ps1 / 三个门脚本）全部消失，移入 `_history/20261114_204308_orphans`（0.1 MB） | 通过 |
| 体积 | `_safety_backups` 6.22 GiB（quota 门内） | 通过 |
| rebuild 新脚本 | 无 EXTRA_SNAPSHOT 残留；按 MANIFEST `snapshot` 字段刷新快照 + 块内替换（保留 4 空格排版）+ 写盘前三重自检（条数/键集合/snapshot 不可改写）+ 孤儿检出 | 通过 |
| A4 标注 | 五档来源标注（实测/注释/推导/未核）逐条落位；1.72 vs 1.2 矛盾如实写入注释并附使用限制（14.02 仅作保守上界，禁用于池上限判断）；swift 12.3 [实测] 锚点亲核：`logs/test_win65k_42k.log` L3 CMD=swift15_iq3s_mtp+dflash2（swift 双头件）、L9 `loading weights | 12.3 GiB` | 通过 |
| GATES | 独立复跑全量门禁 exit=0 | 通过 |
| 审批包 | tree-hash 63d132e0…（`git write-tree` 独立复算一致）；staged 8 文件含 engine_ctl.ps1（+16 −9，model_ids 真源 switch 四分支 + 双 exit 1） | 通过 |
| 门脚本归属 | claim_repro / launcher_dim / start_cond 三件均 git 跟踪（具备回滚管理层，基线不登记可接受） | 通过 |
| launcher staged 变化 | 264/58 → 215/55：全部 hunk 区域逐一归属已申报功能点（A1–A6 / kvwindow 面板 / 渲染自检 / model_ids 真源），无独立夹带功能块；净减 49 行系交付方两轮间对 fallback 与迁移块的重构精简 | 通过 |

### 风险与未了事项

1. A4 的 gsq 11.30（[推导]）/ q2lynn 12.30（[未核]）待起服日志校正；1.72 vs 1.2 矛盾未定位——已标注使用限制，挂账。
2. `20261114_201013` 归档目录被整目录删除（清理 >8MB 件时小文件一并被删）：gates.ps1 的 11-05 版改前原件（5E475B93）失去最后副本（该文件无 git 跟踪）。新版已三方验证，实际回滚需求低；但"归档跳过 >8MB"规则对将来大文件覆盖存在丢失改前副本的边界，已备案。
3. 启动器进程复核时实测 0 个（与交付方"pid 12584 已起"不符；`launcher_errors.log` 不存在）——按服务窗口纪律由用户手动拉起复核面板。
