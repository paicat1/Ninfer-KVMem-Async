# 审核：build 目录事件 + 重建保证 + 带符号构建前置（TeleAgent 独立核验）

- 核验：TeleAgent · 2026-10-18 14:0x–14:3x · 对象：用户质问（"为什么 build 目录被清除/能否保证完全重建/是否影响下一步/会不会回退或破坏成果"）+ CB《全部做完》报告 + 带符号构建预登记
- 方式：**纯读**（未碰现场、未改任何文件）——git 原件直读 / 探针实测（vcvars 链 stdin 探针）/ 回收站与任务计划实查 / 独立复算；[EVIDENCE] 随文
- 边界：本件不授权任何修复、提交或推送；结论供用户与 CB 决策。本件落 `docs\`（CB 工作区可见）

---

## 一、四问直答

1. **能否安全编译成功：能（全要素实证在盘）**——编译树唯一 = 自持树 `engine-src`@`be2c0f9`（工作区 0 脏行）；工具链探针实测 cl/cmake/ninja 三条全部命中；vcpkg/源码入口/磁盘全在；冷编先例 `[1089/1089] BUILD-EXIT=0`（约 41 min）；已知编译坑（C2326/C3495/C2026）已修在树内。不可保证项仅剩"与 10-15 件**逐字节**同构"（物理上不可能）——**功能等价**由预登记 §3.6 行为门兜底。最终确认 = 执行时第一步环境门（5 秒，预期值见 §四）。
2. **对下一步风险：低**（明细见 §六）：R2 编译器漂移（痕迹支持未漂移 + 已加"版本入账"要求）；R3 时长（60 min 止损）；R4 部署记录（已要求补）；**锁释放（重启/施压前）**；预登记 1 处执行前小修（§3.2）。
3. **会不会回退：没有**（见 §五）：main 7 提交全部 = origin/main；无 reset/回绕（reflog 仅 1 次已披露的 C4 amend）；engine-src 干净前进 1 提交；生产件未动；外仓（Bonsai 侧）0 脏未动。
4. **会不会破坏成果：当前没有**——关键资产逐项在盘（见 §五清单）；唯一损失 = build 中间目录（**可重建**，且今日已把真正的单点风险"step13 增量未提交"固化为 commit+patch ⇒ **净状态比昨天更安全**）。

---

## 二、build 目录删除事实链（回答"为什么被清"）

**两处删除均系历史批准轮，非本轮、非偷删：**

1. **10-12 解耦轮**：源码树内建的那份 `build-1208a`（创建 10-11 22:31 = 我方）已删；源码以 bundle 归档 `safety_backups\qwenline_s6-20261008_20261012.bundle`（13,844,499 B）+ `qwenline_uncommitted_20261012.patch`（29,922 B）。[EVIDENCE] 构建史 L1633；两件实测在盘
2. **10-17 00:30–01:0x T1+T2 清理轮（用户已批）**：`.temp\build-1208a`（8.68 GiB）+ `build-20261013-54fix` 删除；走 CB 安全删除 shim ⇒ **全部进回收站**（$I 184 条 / $R 70 实体 / 54.73 GiB；构建史 §81 台账）；同轮 T3 另删 2 个无引用 lineage 件（用户点名"都删"，先备份 `safety_backups\exe_lineage_*`）。[EVIDENCE] 构建史 §81（L3005 区）
3. **现状（本轮实查）**：回收站仅剩 **7,141 件 / 3.83 GB**；54.73 GiB 大件**已不在回收站**（不可从回收站恢复）——构建史无清空记录；StorageSense 计划任务**启用中**（state=Ready，今日 11:49:49 运行 rc=0），但回收站留存件中含 2 月/3 月老件（02-08/02-27/03-17/03-21）与今晨件（08:15–09:54）——**成分与"按龄整站清理"不符，归因未闭合**（维持挂账④；如用户手动清过部分项，一句话即可销账）。[EVIDENCE] `$Recycle.Bin` 实查 + `Get-ScheduledTask DiskFootprint\StorageSense`
4. **"可重建"分档复核：成立**（见 §三）——删除时"安全"动作（shim + 回收站 + 台账）确实执行；丢的是"安全网"（回收站后来被清），不是"唯一副本"。

---

## 三、重建保证核验（逐项实测）

| # | 项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 编译树 = 自持树 `J:\ninfer-kvmem\engine-src`（分支 line-coder390） | ✅ 在位、**0 脏行** | `git status` 空；HEAD=`be2c0f9`（14:04:34，"S12-internal v3 … slots 12->26"） |
| 2 | `be2c0f9` = `f0ecab0` + step13 增量（4 文件 +71/-40） | ✅ 逐项吻合 | `git diff f0ecab0 be2c0f9 --stat` = text.cpp/mtp.cpp/step_graph_profile.h/speculative_round.cu，71/40 |
| 3 | 历代源码锚全在 | ✅ 6/6 | `git cat-file -t`：35173e0/ee8f0ce/e3d9c26/3b9dc83/f0ecab0/be2c0f9 全部 = commit；3b9dc83 是 f0ecab0 祖先（rc=0） |
| 4 | 补丁双保险（异地副本） | ✅ 逐字吻合 | `patches\i3b_s12v3_fourlayer.patch`（16,062 B）：`git apply --stat` 与 be2c0f9 完全一致 + `git apply --check --reverse` **rc=0**（=与树内状态逐字互逆可验） |
| 5 | 归档 bundle | ✅ 在盘 | `safety_backups\qwenline_s6-20261008_20261012.bundle`（13,844,499 B）+ `qwenline_uncommitted_20261012.patch`（29,922 B）+ `engine-src_20261009.bundle`（13,824,103 B） |
| 6 | lineage 台账锚 | ✅ | `engine\lineage\MANIFEST.txt`（48 行）：step13 条目 sha `322A972D…9495` / 1,272 MiB / auto-tag 内嵌源码 `f0ecab0` |
| 7 | 构建配方（已入库） | ✅ | `build\s6_1208a.bat`（+README/产物清单/patches 0001-0003）均在 `git ls-files` 在案 |
| 8 | 冷编先例 | ✅ | 构建史 L1825 节：清 `.temp/build-1208a`（8.68 GiB）→ 从零全量 → `[1089/1089]` + **BUILD-EXIT=0** + 零错误行（21:00:30→21:41:44 ≈ 41 min） |
| 9 | 生产件未动 | ✅ | `engine\lineage\I3b_step13_fourlayer_20261015.exe` = 1,333,820,928 B；`engine\self-built-20261008\ninfer-serve.exe` + `ninfer-serve-I3b322a.exe` 同尺寸（10-15 23:48:35） |

---

## 四、编译安全核验（"能否编"全链实测）

| 组件 | 要求 | 现状（实测） |
|---|---|---|
| vcvars64 | MSVC 环境 | ✅ `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat`（bat L10 实际引用；存在） |
| MSVC 工具集 | cl.exe | ✅ **14.44.35207**（唯一版本；目录时间 2026-08-21，10-15 后无更新痕迹） |
| CMake | ≥3.25 | ✅ VS 自带（`Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe`）；另有独立 `C:\Program Files\CMake` 副本 |
| Ninja | — | ✅ VS 自带 + `J:\vcpkg\downloads\tools\ninja-1.13.2-windows`（bat PATH 引用；1.13.2 可运行） |
| CUDA | 13.3 | ✅ `J:\Bonsai\landing\cuda-13.3\bin\nvcc.exe`（文件时间 2026-06-10 未动） |
| vcpkg | x64-windows | ✅ `J:\vcpkg\vcpkg.exe` + `installed\x64-windows`（bin/lib/include/tools…） |
| 源码入口 | — | ✅ `CMakeLists.txt` / `CMakePresets.json` / `apps\CMakeLists.txt` / `dist\` / `vcpkg.json` 全在 |
| 磁盘 | — | ✅ J: 余 **155.7 GB** |
| 已知编译坑 | — | ✅ C2326/C3495/C2026 修复已含树内（`build\patches\0001-…`，README §五"无需另打"） |
| 引擎现状 | — | ✅ 生产件运行中（pid 11528 @12:49 起；req#81 14:12 正常，decode 119.5；GPU 15.4/16.3 GiB） |

**环境门探针（本审核实测，stdin 方式跑 vcvars64 后 `where`）：**
```
cl.exe    -> …\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe
cmake.exe -> …\Community\Common7\IDE\…\CMake\bin\cmake.exe
ninja.exe -> …\Community\Common7\IDE\…\CMake\Ninja\ninja.exe
```
⇒ **构建环境自足可解析**（早前"cmake 不在 PATH"仅因未跑 vcvars；bat 第一步即 vcvars，链已验通）。

---

## 五、回退与资产核验

- **git 状态**：main=`f44b4f4`=`origin/main`（origin=paicat1/Ninfer-KVMem-Async），工作区 0 脏行；提交链 6735fcc→…→51d8f34→5a0332c→f44b4f4 全在；reflog 仅 1 次 amend（C4，已披露）；无 reset/回退
- **engine-src**：`be2c0f9` 干净；push URL 已禁用防误推（`DISABLED_NEVER_PUSH_UPSTREAM`）
- **外仓（Bonsai 侧 clone）**：`J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` = **0 脏行**、HEAD=3b9dc83（10-08）——本轮未被动 ✓；`f0ecab0` 在此树 cat-file = MISSING（证实"仅历史侦察记录、非编译树"）
- **关键资产清单（全部在盘）**：生产件 ×3（见 §三-9）· 源码树+锚+bundle+patch · 构建配方 · 工具链 · 模型 4 件（13.27/13.57/13.27/12.79 GB）· 证据（`ninfer_hang_20261018_22428.dmp` 254,376 B + `hang_stack_analysis_20261018.txt` 7,642 B + 22 案卷〔已入 C4〕+ VIOLATION×3）· `safety_backups` 75 件 · git 双仓历史
- **观察（非阻塞）**：① 本仓 `official-repo\ninfer-fusion-kvmem` 克隆有 **9 处历史脏行**（7 改：output_session.cpp/program.*/program_impl.h/context.cpp/engine_core.h/openai_chat_http.cpp + 2 未跟踪 `_build_configure.tmp.bat`/`_configure.log`；时间为 10-11 时代，**非本轮产生**，与重建链路无关——处置待定）② `.temp\em-wt3`（engine-main 临时工作树）目录已不在（git 标 prunable；分支本体完好）③ `build\README.md` §4.1 表与当前 bat 的 vcvars 路径不同步（README=J:\BuildTools，bat=C:\Community；以 bat 为准，低优先同步）

---

## 六、残余风险与诚实边界

- **R2 编译器漂移**：无法 100% 锚定（10-15 构建日志随 `.temp` 删除）；但三件痕迹（MSVC 14.44.35207 目录 8/21、CUDA 6/10、ninja 1.13.2）均支持"未漂移"；f44b4f4 已加"编译器版本入账"要求（执行时闭环）
- **R3 时长**：冷编 40–60 min（先例 41 min；若 vcpkg 依赖需重建可能更长）——60 min 止损线已在预登记
- **R4 部署纪律**：deploy_history 止于 10-12 08:41（10-13 后部署未走该记录）——sym 件部署已要求补记
- **锁**：CASE_LOCKED 激活中（case_20261018_124615 @12:46:18，release_by=user only）——重启/施压前需释放
- **字节级**：重编产物 hash 必不同于现役件（时间戳/PDB GUID 嵌入）——不追逐字节，只验功能等价
- **本审核未做**：真跑一次编译（未获批/耗时）——"能编"= 全要素在盘 + 先例可复现 + 探针全通；**最终确认 = 执行第一步环境门**

---

## 七、预登记审读意见（TELE 审）

**总体：建议批（附 1 处执行前修正）**。结构完整、判据先于数据、边界清晰；R1 已消除、R2/R3/R4 在案。

- **【须修·执行前】§3.2 与 §3.3 现相互矛盾**：§3.2 仍写"补丁复现：在 src-tree 工作区按确认的补丁序列应用"——但树已固化 `be2c0f9`（含全部增量），**再应用补丁会失败/双重应用**。建议改为："确认 `engine-src` 工作区在 `be2c0f9`、0 脏行即可；补丁链已含树内，无需再应用（patch 仅作异地副本）"。同时"src-tree 工作区"措辞易与上游树混淆，一并厘清
- **【已核安全】** §3.3 "build 目录建在自持树内（如 `engine-src\build-sym`）"：engine-src `.gitignore` 含 `build*/` ⇒ 不会污染源码仓状态 ✓
- **【已由 f44b4f4 补强】** 编译树钉死 = `engine-src`（唯一）+ 禁止 Bonsai 路径（T-NO-FOREIGN-WRITE 显式化）+ 编译器版本入账（R2 对照锚）——方向正确
- 说明：**审计期间（14:16）新增提交 `f44b4f4`**（1 文件 +4/-3，即上述预登记修正；门戳"APPROVED: 先做完再等我指示"；已推 origin/main）——晚于用户转述清单，供用户追认

---

## 八、待办与建议（待用户裁）

1. 批预登记（含 §3.2 修正）→ 点火（冷编 40–60 min 亮灯制）
2. 锁释放（重启/施压前，用户一句话）
3. 挂账④（回收站清空归因）；本仓 official-repo 9 脏行处置；em-wt3 prunable 清理（`git worktree prune`）；README 同步（低优先）

---

*TeleAgent · 2026-10-18 · 纯读核验，未改任何文件*
