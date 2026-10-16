# 基准库（每模型一套 · 2026-10-14 立）

**原则**：方法与判据**跨模型通用、一套定稿**（守望者 `Ninfer-KVMem-Async守望者` / 逐字门 `scripts\verbatim_gate.py` /
bisect `scripts\bisect_env.ps1` / 机器级探针 `tools\gpu_probe.exe` / 窗口 SOP / A2 适用域：池 ≥ 上下文）；
**参数与基准每模型一套**（模型件 / KV 档 / 池 / Graph / 视觉 / golden SHA / 判据阈值）。

| 套 | 状态 | 内容 |
|---|---|---|
| `q2lynn/` | **冻结（只读）** | Coder390-Q2Lynn 3.89bpw：逐字门基准（cur_a2/cur_b2，噪声地板 8/8）、KV A/B 台账、深上下文台账 |
| `swift15_iq3s/` | 现行 | Swift-1.5 IQ3_S：四臂逐字件（rk8v4/nvfp4/rk2v4/int8）、换底座台账 |

**纪律**：① 冻结集只增不改（新结论另起文件）；② 换模型 = 换一整套（启动器 `MODEL_BUNDLES` 自动切 KV/池/Graph/视觉）；
③ 跨档对比必须同池同上下文（池 ≥ 上下文，否则测到的是检索子集效应）；④ golden SHA 只在同模型同档内可比。

- `valley-20261016/` —— **死亡谷攻关证据链台账**（35 件 / 1.64 MiB，见其 README）。
