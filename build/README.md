# 自编引擎构建 · 复现说明（Windows / MSVC / CUDA 13.3 / sm_120a）

> 本目录 = 把 **NInfer v0.11.0（+KVMem 环）** 源码，在 **RTX 5080 / sm_120a** 上编成**我们自己的引擎与运行环境**的构建脚本。
> 目标：**任何人照此可重现** `ninfer-serve.exe`（含本项目补丁）及配套 DLL。
> ⚠️ **口径**：本仓**不含**引擎成品与模型制品（体积原因）。因此这里的"复现" = **可重编出**，**不是"下载即用"**。成品身份与哈希锚点见 `build/产物清单.md`。

## 一、依赖（版本）

| 组件 | 版本 / 说明 |
|---|---|
| CUDA | **13.3**（提供 `nvcc`） |
| vcpkg | triplet = **x64-windows** |
| MSVC | **Visual Studio 2022 BuildTools**（`vcvars64.bat`） |
| CMake / Ninja | VS 自带即可 |
| GPU | sm_120a（RTX 50 系） |

## 二、源码从哪来（任选一条）

| 方式 | 说明 |
|---|---|
| **`engine-main` 分支（推荐）** | 引擎源码**快照** = 上游 20261008 全树 + 本项目全部补丁。`git clone -b engine-main <repo>` 一条命令拿齐；**已含补丁，无需再打** |
| **`build/patches/`（看过程 / 从上游起步）** | 我们对上游的**全部改动**（3 个补丁 + 用法说明）。要"逐步 diff"或"从上游原始源码复现"用这条 |
| 本机开发用 | `official-repo\infer-fusion-kvmem\src-tree\fusion-engine-src`（本机 clone，**不入库**） |

## 三、构建步骤

1. 装齐 §一 依赖。
2. **按 §四 改掉脚本里写死的本机绝对路径**。
3. **新基线全图构建**：`cmd /c s6_1208a.bat` → 产物 `<BUILD>\apps\ninfer-serve.exe`（+ 同目录 DLL）。
   （旧基线 20261003 路径：`s6_configure.bat` → `s6_build.bat` / `s6_build_runtime.bat`）
4. **可选验证**：`s6_1208a_test.ps1`（STANDALONE 前端单测，53 项断言，成功静默、退出码 0）。
5. **产物落位**：拷到正式目录（本机 = `engine\self-built-20261008\`）；**不要**把成品留在构建中间目录（见 §七）。

## 四、必改的绝对路径清单（脚本内写死的**本机**值）

> **为什么故意不参数化**：路径是**机器特定**的，没有哪个默认值对外人是对的；把 8 个脚本改成读变量，只是把"改 7 处"变成"改 1 处"，编辑量没省多少，却要给**已实测通过**的脚本引入回归风险。**写死 = 显式、好调试**。路径真变了，改完实测即可。
> **防漂移**：本表按**行号**列点，**改动脚本时请同步更新本表**。

### 4.1 复现必需（8 个文件）

| # | 文件 | 行 | 位置 / 变量 | 本机值（**改成你的**） |
|---|---|---|---|---|
| 1 | `s6_1208a.bat` | 10 | vcvars64（MSVC 环境） | `j:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat` |
| 2 | `s6_1208a.bat` | 11 / 12 | `CMAKE` / `NINJA` | `C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe` / `…\CMake\Ninja\ninja.exe` |
| 3 | `s6_1208a.bat` | 13 | `SRC`（引擎源码树） | `J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` |
| 4 | `s6_1208a.bat` | 14 | `BUILD`（中间目录，可任意） | `J:\Bonsai-Official\.temp\build-1208a` |
| 5 | `s6_1208a.bat` | 15 | `PATH` 里的 CUDA bin | `J:\Bonsai\landing\cuda-13.3\bin` |
| 6 | `s6_1208a.bat` | 18 | `nvcc` / vcpkg toolchain / `vcpkg_installed` | `J:/Bonsai/landing/cuda-13.3/bin/nvcc.exe` · `J:/vcpkg/scripts/buildsystems/vcpkg.cmake` · `J:/Bonsai-Official/.temp/build-120a/vcpkg_installed` |
| 7 | `s6_configure.bat` | 3 / 4 / 5 / 6 / 7 / 9 | vcvars · `CMAKE`/`NINJA` · `SRC` · `BUILD` · nvcc/vcpkg | 同 1–6；`BUILD` 默认 `J:\Bonsai-Official\.temp\build-120a` |
| 8 | `s6_build.bat` | 3 / 4 / 5 / 6 | vcvars · `CMAKE` · `BUILD` · `PATH` | 同 1–5；`BUILD` 默认 `…\.temp\build-120a` |
| 9 | `s6_build_runtime.bat` | 3 / 4 / 5 | vcvars · `CMAKE` · `BUILD`（写在内联命令行里） | 同上 |
| 10 | `s6_1208a_test.ps1` | 11 / 12 / 13 / 14 | `vcvars` · `cmake` · `src` · `build` | `…\BuildTools\…\vcvars64.bat` · `…\cmake.exe` · `…\fusion-engine-src` · `…\.temp\build-1208a` |
| 11 | `a4-arm-A.bat` | 12 | `PY`（Python 解释器） | `J:\miniconda3\python.exe` |
| 12 | `a4-arm-C.bat` | 10 | `PY` | 同上 |
| 13 | `a4-arm-D.bat` | 10 | `PY` | 同上 |

（11–13 是 A4 复测三臂的启动器，**只在做 A4 类压测时才需要**。）

### 4.2 legacy（6 个，**复现不需要**；用到再改）

| 文件 | 写死点（行） |
|---|---|
| `designc_build_frontend.ps1` | 2 / 5 / 6 |
| `designc_build_test.ps1` | 3 / 6 / 7 / 12 |
| `designc_build_tests.ps1` | 2 / 4 |
| `designc_rebuild_serve.ps1` | 2 / 4 |
| `s6_k0_full.ps1` | 4 / 5 / 6 |
| `s6_k0_scan.ps1` | 3 / 4 / 5 |

## 五、关键配置参数

```
-G Ninja
-DCMAKE_BUILD_TYPE=Release
-DCMAKE_CUDA_ARCHITECTURES=120a
-DNINFER_SM120_NATIVE=ON
-DNINFER_BUILD_APPS=ON -DBUILD_TESTING=OFF -DNINFER_BUILD_BENCHMARKS=OFF
```

- **必须先 init `vcvars64.bat`**，否则 MSVC 报 `c1083 cstddef`（环境问题，非代码问题）。
- 编译补丁（C2326 / C3495 / C2026）与 **Design C** 已含在源码里，**无需另打**。
- `.bat` 注释一律 **ASCII-only**（cmd 按 OEM/ANSI 码页解析，中文注释会乱码炸构建——本项目踩过）。

## 六、脚本清单

| 脚本 | 用途 | 类别 |
|---|---|---|
| `s6_1208a.bat` | **新基线（20261008 + 全部补丁）全图构建** | 复现必需 |
| `s6_configure.bat` / `s6_build.bat` / `s6_build_runtime.bat` | 旧基线（20261003）配置 / 编译 | 复现必需（旧） |
| `s6_1208a_test.ps1` | 新基线 STANDALONE 前端单测 | 验证 |
| `a4-arm-A.bat` / `a4-arm-C.bat` / `a4-arm-D.bat` | A4 双基线复测三臂启动器 | 验证 |
| `a4_load.py` | A4 / soak 负载客户端（req#30 类：32 tools / 10 msgs / `max_tokens=65536`） | 验证 |
| `designc_*.ps1`（4 个） | Design C 时期的一次性构建步骤 | legacy |
| `s6_k0_full.ps1` / `s6_k0_scan.ps1` | 构建 / 扫描辅助 | legacy |
| `产物清单.md` | 各引擎件的**身份标签** + SHA256 锚点 | 锚点 |

## 七、产物落位（重要）

- 编译产物（`ninfer-serve.exe` + DLL）是**我们要用的引擎与环境**，必须放在**正式目录**（本机 = `engine\self-built-20261008\`）。
- **不要**把成品留在构建中间目录里——构建目录是中间物，**产物是成品**，两者不能混。
