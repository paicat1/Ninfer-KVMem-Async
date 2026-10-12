# 复现指南（REPRODUCE）— ninfer-kvmem

> 立档：2026-10-12（用户令，仓库可复现性审计后补齐）。
> 目标：任何人在一台干净机器上，**从本仓出发**重建引擎并跑起服务。
> 全部"钥匙" = 本文件 + `repro/qwenline_*.bundle` + `patches/` + `build/s6_1208a.bat` + `scripts/`。

## 0. 一句话

- **源码树不在本仓**（`.gitignore`，自持/体积考虑）→ 用 `repro/*.bundle` 重建；
- **配方在仓**（`build/s6_1208a.bat`）→ 但依赖三样**仓外前置**（第 2 步，含归属声明）；
- **模型不在仓**（约 49 GiB）→ 下载原始件 + 用 `scripts/` 生成派生件；
- **exe 不在仓**（单个 1.27 GiB）→ 重编后对照 `repro/MANIFEST.txt` 的 sha256。

## 1. 重建引擎源码树

```
git clone <本仓> ninfer-kvmem && cd ninfer-kvmem
git clone repro/qwenline_s6-20261008_20261012.bundle engine-src   # 13.2 MiB，含 .git 全历史
cd engine-src && git checkout line-coder390 && cd ..
```

- `qwenline_s6-20261008_20261012.bundle` = 本线自持树在 2026-10-12 03:15 的完整快照（分支 `line-coder390`）。
- 更早快照（未入库，本地留存）：`_safety_backups/engine-src_20261009.bundle`（13.18 MiB）。
- 树的历史 = 上游 + 前序 Bonsai 线 cherry-pick + 本线补丁（见 `engine-src/PROVENANCE.md`）。
- 跨线协作只走 patch/bundle/文档（铁律 T-NO-FOREIGN-WRITE）。

## 2. 仓外前置（**不在本仓**，需自备；路径为本机记录，可自行改）

| 前置 | 本机路径 | 说明 |
|---|---|---|
| Visual Studio 2022 Community | `C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat` | MSVC 工具链（`build\s6_1208a.bat` 里 `call` 它） |
| vcpkg | `J:\vcpkg`（`VCPKG_ROOT`，triplet `x64-windows`） | 提供 ninja（`downloads\tools\ninja-1.13.2-windows`）与第三方库 |
| CUDA 工具链 13.3 | `J:\Bonsai\landing\cuda-13.3\bin` | **外部只读依赖**：该目录属前序线工作区，本仓只读引用；自建环境请装 CUDA 13.3 后改 `build\s6_1208a.bat` 对应行 |

`build\s6_1208a.bat` 里这三处是绝对路径 —— 换机器改这三行即可（其余路径全在本仓内）。

## 3. 构建

```
build\s6_1208a.bat        # 配置 + ninja 全量；日志 .temp\build_engine.log；产物 .temp\build-1208a\apps\
```

- CUDA 架构 `-DCMAKE_CUDA_ARCHITECTURES=120a`（RTX 50 系）。
- **首轮一律全量**；此后改头文件可增量（2026-10-12 实测：改头 → 消费者入队 ✓，挂账45 证伪）。
- 产物 `ninfer-serve.exe` ≈ 1.27 GiB；构建目录 `.temp\build-1208a`（gitignore）。

## 4. 模型（不在仓）

1. 原始件：Qwen3.8-27B-Coder390（Q2 LynnStyle）`.ninfer` + MTP 头原始件（按来源下载）。
2. 派生件（脚本在仓 `/scripts`）：
   - MTP 头重编码 `recode_mtp.py`：原始 MTP 头是 `gguf_q4_0`（引擎不支持 ✗）→ 转 `iq4_nl` ✓；
   - 视觉塔嫁接 `graft_vision.py`。
3. 本机在用构建（供核对）：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer`（12.64 GiB）。

## 5. 部署与版本台账

```
powershell -File deploy_engine.ps1      # 自动备份 + 写台账；备份落在 engine\self-built-20261008\
```

- 版本仓：`engine\lineage\`（一版一 exe，永不覆盖）+ 入库副本 `repro\MANIFEST.txt`（G / G2 / G3 的 sha256）。
- 重编后请与 `repro\MANIFEST.txt` 对照哈希（exe 不入库，单文件 1.27 GiB ✗）。

## 6. 起服

- GUI：双击 `启动器.bat`（→ `ninfer_launcher.py`，含实时显存账）。
- 命令行：见根目录 `start-*.bat`（例 `start-v21-restorefix-nograph.bat`）。
- 纪律：**池 ≥ 预期最大 prompt**（超池 ⇒ 中段丢失、答案不可信）；小池勿压 `--cuda-graph-allowance-mib`。

## 7. 已知边界

- gitignore 区：`engine/`、`models/`、`_safety_backups/`、`logs/`、`.temp/`、`refs/`、`.codebuddy/`（分类注释见 `.gitignore`）。
- 与前序线的唯一耦合：`build\s6_1208a.bat` 里的 CUDA 工具链路径（只读 ✓，第 2 步已声明）。
- 测量工具已入库（`scripts/valley_bench.py`、`scripts/valley_history.py`）= 死亡谷 A/B 的口径工具。
