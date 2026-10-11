# 本源码树：归属与来源（PROVENANCE）

> **归属**：这是 **Qwen3.8-27B-Coder390 线（仓三 `J:\ninfer-kvmem`）自持的引擎源码树**。
> 本目录（`J:\ninfer-kvmem\engine-src`）**只属于本仓**：只在本仓内读写、只给本仓构建。
> 铁律 **T-NO-FOREIGN-WRITE**（2026-10-12 立）：别人的仓一个字节都不许写；
> 本仓的树也不许被别的线当工地。跨线协作只走 **patch / bundle**。

## 一、这棵树怎么来的（可复核）

| 项 | 值 |
|---|---|
| 建立日期 | 2026-10-12（解耦施工） |
| 基 | 上游 `1314521gjy/ninfer-fusion-kvmem` + Bonsai 线 cherry-pick（MSVC 兼容 / Design C / 测试 STANDALONE），即 commit `3b9dc83` |
| 本线 checkpoint | `4c4dcfa`（"v2 async demote VERIFIED state"，10-11 20:36 部署版对应） |
| 还原手段 | 本仓归档 bundle `_safety_backups/qwenline_s6-20261008_20261012.bundle`（13,844,499 B，`git bundle verify` = records a complete history）+ 归档差分 `_safety_backups/qwenline_uncommitted_20261012.patch`（29,922 B） |
| 分支 | `line-coder390`（本线分支） |
| 远端 | `upstream` = 上游只读；**push URL 已置为 `DISABLED_NEVER_PUSH_UPSTREAM`**（防误推） |
| 工作状态校验 | 应用归档差分后，`git apply --check --reverse` 通过（= 树内完整含该差分，与一直被构建的源码一致） |

## 二、构建方式（只在本仓内）

- 脚本：`J:\ninfer-kvmem\build\s6_1208a.bat`（本仓路径，不再引用任何别的仓）
- 构建目录：`J:\ninfer-kvmem\.temp\build-1208a`（本仓，`.gitignore` 已排除）
- 日志：`J:\ninfer-kvmem\.temp\build_engine.log`
- 关键环境：`VSLANG=1033`（MSVC 输出英文 `Note: including file`，ninja 才能识别头依赖 —
  挂账45 根因是中文 `/showIncludes` 前缀未被 ninja 识别，导致改头不重编消费者）

## 三、外部只读依赖（不是"别人的仓"，是工具链）

- CUDA 13.3：`J:\Bonsai\landing\cuda-13.3`（**只读**引用；nvcc 与运行库）
- vcpkg：`J:\vcpkg`（共享包管理，只读引用）
- 这两条是工具链路径，**只读、不写入**；与本条线的源码/构建产物无关。

## 四、补丁链（内容锚在仓三 `patches/`，历史锚在本树提交）

| 补丁 | 说明 |
|---|---|
| `W1-W4_engine_fix.patch` | 上游对齐（tancau 24c8ea5） |
| `ledger42_cancel_checkpoint.patch` | 取消检查点前移（页边界可取消） |
| `ledger42_batch_demote.patch` | 批量 demote K=8 |
| `ledger42_v2_async_demote.patch` | 异步 demote（transfer stream + PendingDemote 槽） |
| `ledger44_demote_profile.patch` | demote 路径 profile 探针 |
| `ledger46_v2.1_multibatch.patch` | v2.1 多批 in-flight（N 槽环形队列） |
| `ledger47_overpool_abort_silent_death.patch` | 67K 超池静默 abort（0xC0000409）修复 |

> 说明：`patches/` 是**内容锚**（用于跨线交付与复核），本树的 **commit 历史是溯源锚**。
> 2026-10-12 体检发现部分 .patch 文件带 BOM/换行差异，`git apply` 双向不匹配 ——
> 这不影响内容（内容由 bundle + 本树 commit 权威包含），已在构建史 §三·二十一 记录。
