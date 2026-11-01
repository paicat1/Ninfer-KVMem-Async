# engine\lineage\retired\ 退役件索引

> 退役区：历史编译件、未参与现役链。按 canonical_dirs / 结构规范登记。
> 新增件必须在此登记（名称 / 来源 / SHA256 / 状态 / 备注）。
> 登记时间：2026-11-01（A 方案：engine-src 10-18 构建副本快照入库）

## snapshot-20261101-engine-src-build

- 来源：`engine-src/src-tree/fusion-engine-src/build/apps`（10-18 16:08 编译，CMakeCache 证明 `CMAKE_HOME_DIRECTORY=J:/ninfer-kvmem/engine-src/src-tree/fusion-engine-src`）
- 遗留路径：`_worktrees/engine-main/src-tree/fusion-engine-src/build`（`publish_tree.ps1` 的 `robocopy /E` 遗留副本）
- 处置：2026-11-01 快照入库（4 exe + 4 pdb），worktree 已移除

| 件 | 大小 (B) | SHA256 | 状态 |
|---|---|---|---|
| `snapshot-20261101-engine-src-build/ninfer-serve.exe` | 1618544128 | `6ed2f396f955d9e51f9a028f0e81875d6b8f583dc013ddd889f8f439298efcfa` | retired（未参与现役链） |
| `snapshot-20261101-engine-src-build/ninfer.exe` | 1616308736 | `8a42c258a94dbbef927d0af233f13c2d7173373ec752b3ac67e0297422c655e7` | retired |
| `snapshot-20261101-engine-src-build/ninfer-perplexity.exe` | 1616273920 | `aecff1ec80b63d7a372f03ac7b74a01456771b235f0431da9f6e3c7c9714719a` | retired |
| `snapshot-20261101-engine-src-build/ninfer-calibrate.exe` | 1244541952 | `05c7954fa82d8668a11fe3fb75ae603e38bf4c11f77ba0773c5c3b3b19bb1db8` | retired |
| `snapshot-20261101-engine-src-build/*.pdb`（4 件） | ~0.68 GB | 随对应 exe | retired（调试符号） |

## 备注

- 这 4 个 exe 原未在 BUILD_LEDGER 登记；2026-11-01 补登 4 行（status=retired）。
- 源码在 `engine-src`（line-coder390 @2336ba3），可重建。
- 不参与现役链（现役 = `engine/lineage/ninfer-serve-PG3-20261031.exe`，含 FIXED_W）。
