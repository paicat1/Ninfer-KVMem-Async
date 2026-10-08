# 引擎源码补丁 —— 本项目对上游改动（全部）

> 本目录 = 本项目对**上游引擎源码**的**全部**改动，导出为 3 个补丁（`git format-patch`）。
> **想看我们改了什么** → 直接读这里的 patch（§二）；**想把引擎编出来** → 见 §四（推荐直接取 `engine-main` 分支，**已含补丁、无需再打**）。

## 一、基准（这些补丁打在什么上面）

| 项 | 值 |
|---|---|
| 上游源码 | NInfer v0.11.0 基座 + KVMem 环融合（上游仓 `1314521gjy/ninfer-fusion-kvmem`） |
| 基准版本 | **20261008** 基线 |
| 基准 commit | `2852f6f`（= 本仓 tag `engine-v0.11.0-kvmem-20261008`） |
| 树布局 | **上游原始布局**，引擎源码位于 `src-tree/fusion-engine-src/`（**注意这一层前缀**） |
| 补丁作者 | paicat1（本仓） |

> 说明：`engine-main` 分支的树**已把前缀剥平**（根目录直接是 `CMakeLists.txt` / `src/`），且**已包含**这三处改动——所以本目录的补丁是给"想从**上游原始源码**起步、自己看/自己打"的人用的，**不是**给 `engine-main` 用的。

## 二、三个补丁（`git apply --stat <patch>` 可看摘要）

| # | 文件 | 原 commit | 主题 | 改文件数 |
|---|---|---|---|---|
| 1 | `0001-fix-engine-2026-120a-MSVC-C2326-C3495-C2026.patch` | `5b07bc1` | **MSVC 编译兼容**（C2326 / C3495 / C2026）——让上游源码在 Windows / MSVC / sm_120a 下**编得过** | 7 |
| 2 | `0002-feat-frontend-Design-C-thinking-stop-answer-thinking.patch` | `a25012b` | **Design C**：thinking 阶段 `stop` 强制进 answer，避免"**空正文**" | 2 |
| 3 | `0003-build-tests-frontend_test-STANDALONE-exe-bundle.patch` | `3b9dc83` | `frontend_test` 加 **STANDALONE** 开关（绕开上游坏测试 bundle） | 1 |

**合计 10 文件**。这三处也是本项目 README / NOTICE 所称的"3 组源码补丁（10 文件）"的**逐条原文**。
`[EVIDENCE]` 逐条 diff 直接读 patch 正文；可用 `git apply --check <patch>` 在被改源码树上先行校验（本项目导出后已对 `2852f6f` 树检过，`--check` 全过）。

## 三、怎么看（用途一：读过程）

```bash
git apply --stat build/patches/0001-*.patch   # 文件级摘要
git apply --numstat build/patches/0002-*.patch  # 行级增删
# 或直接用编辑器打开 patch 文件（含 commit message + 完整 diff）
```

## 四、怎么用（用途二：从上游原始源码复现我们这版）

> **不想打补丁？** 直接 `git clone -b engine-main <本仓地址>` —— 快照**已含**全部补丁，**直接可编**（见 `build/README.md`）。下面是从**上游原始源码**起步的等价流程。

```bash
# 1) 取本仓（拿到 build/patches/）
git clone <本仓地址> repo && cd repo

# 2) 取上游 20261008 源码树（tag 树，布局含 src-tree/fusion-engine-src/）
git worktree add ../upstream engine-v0.11.0-kvmem-20261008

# 3) 在源码树根按序应用（路径自洽，无需 -p 调整）
cd ../upstream
git apply ../repo/build/patches/0001-*.patch
git apply ../repo/build/patches/0002-*.patch
git apply ../repo/build/patches/0003-*.patch

# 或（推荐）用 git am 保留原 commit 作者与提交信息：
# git am ../repo/build/patches/*.patch
```

打完后的 `src-tree/fusion-engine-src/` 即 **= `engine-main` 分支的引擎树**。

## 五、版本串提示（`NINFER_BUILD_ID`）

上游 `cmake/GenerateBuildId.cmake` 默认用 `git describe --always --tags` 生成版本串；**若设置了环境变量 `NINFER_BUILD_ID`，则直接以之为 base**（覆盖 `git describe`，官方 `restamp build_*.bat` 机制即用此）。

⇒ 若你的复现树**没有完整 tag 血统**（例如已剥平前缀、或从本目录补丁起步），版本串会退化成 `g<短哈希>` 形态；**要自定义版本串，设 `NINFER_BUILD_ID` 即可**，与本仓的 tag 无关。

## 六、许可与归属

- 上游引擎源码随上游 **Apache-2.0**；本目录补丁同为 **Apache-2.0**。
- 上游归属与我们的修改清单见仓库根 `NOTICE.md`。
