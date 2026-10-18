# 实验-带符号构建抓现场-预登记-CodeBuddy-20261018

> 状态：**待 TELE 审核署 + 用户批准**（流程：预登记 → TELE 审 → 用户批 → CB 执行）
> 定向依据：挂账 #12/#17；TELE 2026-10-18 裁决"先①——成本最小、直接给函数名，函数名出来后②插桩点才有靶子"；用户 2026-10-18"下一轮同意建议"。
> 对应问题：A-B-A 判决与挂死深挖已锁定 **host 提交/同步路径停摆**，自有码等待点 5 偏移（`+0x70183`×16 / `+0x1ab01a5`×16 / `+0x1cc2c44`×2 / `+0x5e188`×1 / `+0x157f37`×1）因现役件无符号无法落函数名。

## §1 目标与产出

1. 构建**抓现场专用件**：与现役引擎同源码、同配置、仅加调试信息生成（MSVC `/Zi` + 链接 `/DEBUG`），产出 `ninfer-serve-sym.exe` + `ninfer-serve-sym.pdb`。
2. 用该件复跑 250 级施压（或下次自然/受控挂死）→ `dump_hang.ps1` 转储 → 符号化解析，把 5 偏移落到**函数名+源码行**。
3. 明确**不作生产件**：生产件保持 `engine\lineage\I3b_step13_fourlayer_20261015.exe` 不动（可比性优先，TELE 复议 3 既定）。

## §2 关键事实（2026-10-18 13:5x 侦察实据）

| 事实 | 证据 |
|---|---|
| 现役件无 .pdb/.map，`engine\pdb_archive` 只有依赖库 PDB（avcodec/avformat/libcurl 等，2026-10-13），**无主程序 PDB** | `Get-ChildItem engine\pdb_archive` 12 件全为依赖库 |
| ~~源码树在位且干净：`J:\Bonsai-Official\...fusion-engine-src`，HEAD `3b9dc83`~~ **【仅历史侦察记录，非编译树】**该树是上游 Bonsai 线的 clone，HEAD 停在 10-08、**不含我方任何后期 commit**（`f0ecab0` 等经 `git cat-file` 验证 MISSING）——10-12 解耦后我方代码已全部撤至本仓自持树；**严禁在此树编译/建 build/写任何字节（T-NO-FOREIGN-WRITE）**。真正编译树 = 下行 `engine-src` | 该树 `git cat-file f0ecab0` = MISSING（对照下行自持树 = commit） |
| **编译树（唯一）= 本仓自持源码树 `J:\ninfer-kvmem\engine-src`**（分支 `line-coder390`）：`f0ecab0` + `be2c0f9` 双 commit 固化现役件源码，工作区 0 脏行 | `git log -1`（be2c0f9 = S12-internal v3）+ `git status` 清零 |
| 构建目录 `build-1208a` **已被清理**（部署史 `engine\self-built-20261008\_deploy_log\deploy_history.txt` 最后指向 10-12 07:30）⇒ 本次为**冷 configure + 全量编译** | `Test-Path build-1208a = False`；`fusion-engine-src` 下无 build* 目录 |
| CMake 入口在位：`CMakePresets.json` ✓、`apps\CMakeLists.txt` ✓、`dist\` 存在 | Test-Path 三查 |
| deploy_history 停在 10-12 08:41，而现役件为 10-15 `I3b_step13_fourlayer_20261015.exe` ⇒ **10-12 后的部署未走 deploy 纪律**（历史缺口，另行挂账核对） | deploy_history.txt L24 止于 20261012_084132 |
| 现役件 sha256（引擎件核对锚）：`engine\self-built-20261008\ninfer-serve.exe` 与 `ninfer-serve-I3b322a.exe` 同尺寸 1,333,820,928 B | TELE C1 核验"引擎件 sha 一致 322A97…" |
| **现役件源码状态已 100% 固化（2026-10-18 14:0x 用户批"先做完再等我指示"后执行）**：本仓自持源码树 `J:\ninfer-kvmem\engine-src`（分支 `line-coder390`）HEAD=`f0ecab0`（S12-internal v2，10-15 23:15）→ step13 增量（4 文件 +71/-40：text.cpp/mtp.cpp/step_graph_profile.h/speculative_round.cu）已固化为 commit **`be2c0f9`**（工作区清零）+ patch 双保险 `patches\i3b_s12v3_fourlayer.patch`（16,062 B，与现役件逐项吻合 MANIFEST"four fixed layers; slots 12->26"）；历代源码锚 `35173e0`/`ee8f0ce`/`e3d9c26`/`f0ecab0` 经 `git cat-file` 全部验证存在 | engine-src git log/status + MANIFEST L48 + patches 清单 |
| 历史疑点澄清：Bonsai-Official 侧 clone 的 `build-1208a` 与本仓 `.temp\build-1208a` 均系**构建中间产物**（10-12 解耦轮 / 10-17 00:30 T1 清理轮〔用户批+安全 shim 进回收站，后被清空〕），**源码零损失**；从零重编成功先例 `[1089/1089] BUILD-EXIT=0`（构建史 L1825） | 本轮调查记录 |

## §3 执行步骤（每步亮灯，异常即停）

1. **源码一致性门（已确证通过，2026-10-18 14:0x）**：现役件源码 = 自持树 `engine-src` `f0ecab0`（v2 基线，git 提交）+ `be2c0f9`（v3 增量 4 文件，已固化）——即 step13 现役件的完整源码链。执行时编译 `be2c0f9` 状态即可；~~若无法确证补丁集合 ⇒ 本预登记作废上报~~（原风险已消除）。
2. **补丁复现**：在 src-tree 工作区按确认的补丁序列应用（`git stash`/分支方式，工作区从 0 脏行起步，逐步核对每补丁应用成功）。
3. **configure（冷）**：**编译树唯一 = `J:\ninfer-kvmem\engine-src` 自持树（`be2c0f9` 状态）**——build 目录建在自持树内（如 `engine-src\build-sym`）；**禁止**在 `J:\Bonsai-Official\` 任何路径下建 build/写文件/commit（T-NO-FOREIGN-WRITE 铁律，10-12 解耦成果不可倒退）。CMake preset + `-DCMAKE_CXX_FLAGS="/Zi"` + `-DCMAKE_EXE_LINKER_FLAGS="/DEBUG /OPT:REF,ICF /INCREMENTAL:NO"`（/Zi 不改代码生成；/DEBUG 生成 PDB）。**记录完整 configure 命令行**（复现锚）+ 编译器版本（cl.exe 版本号入账，R2 漂移对照锚）。
4. **build**：全量编译（预估 20–40 min，冷编译+third_party 可能更长；等待纪律：预计+5s 未完成即 5s 轮询，30s 上限周期报状态）。
5. **产物归位**：`ninfer-serve.exe` + `.pdb` 复制为 `engine\self-built-20261008\ninfer-serve-sym.exe` + `ninfer-serve-sym.pdb`（**不覆盖**现役 `ninfer-serve.exe` / `ninfer-serve-I3b322a.exe`，逐字节核对后才放行）；PDB 副本入 `engine\pdb_archive\`。登记 `deploy_history.txt`（补上纪律：sym 件部署走 deploy_engine.ps1 记录）。
6. **冒烟+行为等价门**：`engine_ctl.ps1 -Action start -Exe engine\self-built-20261008\ninfer-serve-sym.exe`（相对路径，T#0055）→ waitready → 探针 decode_tps ≥100 → **与现役件同负载探针对比**（tps 落同域 160–190 即等价通过；偏差 >20% 即停上报）。
7. **抓现场+符号化**：sym 件跑 250 级施压（ee_threshold 原班）→ 谷/挂死触发时 `dump_hang.ps1` 转储 → 符号化（dbghelp SymFromAddr / llvm-pdbutil，工具落 `scripts\`）→ 输出 5 偏移函数名清单 → **构建史记录 + TELE 复核**。
8. **现场还原**：实验完 stop sym 件 → 起生产件（`start_engine_default.ps1`）→ 核对 `CUDA graphs ready`。

## §4 风险与边界

- **R1 补丁复现不一致**（~~最高风险~~ **已消除 2026-10-18 14:0x**）：现役件源码链 `f0ecab0`+`be2c0f9` 双 commit 固化+patch 双保险——源码级重建保证成立。残余风险仅剩 R2 编译器版本漂移（见下）。
- **R2 编译改变行为**：/Zi+ /DEBUG 理论上不改代码生成（MSVC 文档），但链接 /OPT:ICF 等**可能**微调布局 ⇒ 行为等价门（§3.6）兜底；sym 件永不作生产/判决数据源，只作"抓现场+函数名"。
- **R3 时长**：冷全量编译可能 >40 min（third_party 冷编）⇒ 若 60 min 未出产物，停下报告（不改并行度硬救）。
- **R4 部署纪律缺口**：10-12 后部署未走 deploy_history（§2 末行）——本次 sym 件部署**必须**补记录；生产件不动不涉及。
- 边界：**T-NO-FOREIGN-WRITE——`J:\Bonsai-Official\`（上游 Bonsai 线仓）一个字节不写**（不建 build、不 commit、不碰工作区；10-12 解耦已把我方代码全部撤至本仓自持树 `engine-src`，本项目与上游仓零挂靠）；不改源码逻辑（be2c0f9 照抄）；不动生产件；不删 build 目录外任何件；全程窗口纪律+T-BACKUP。

## §5 验收门（全过才算完成）

1. `ninfer-serve-sym.pdb` 存在且与 sym exe 的 GUID 匹配（dbghelp 查询通过）；
2. 冒烟探针 ≥100 tok/s 且与现役件同域；
3. **至少 1 个偏移拿到函数名+源码行**（理想 5/5；若 250 级仅出谷不出挂死，则以谷态转储+符号化为准——谷即 host 提交路径慢轮，同样可落名）；
4. 现场还原完成（生产件回归+`CUDA graphs ready` 核验）；
5. 构建史 §记录 + SDA note + TELE 复核署。

## §6 变更记录

- v1（2026-10-18 13:5x）：初版落纸（侦察实据 §2 全部实测）。待 TELE 审 + 用户批。
