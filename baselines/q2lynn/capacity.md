# Q2LYNN 容量与判据（冻结集 · 2026-10-14）

| 项 | 值（实测） |
|---|---|
| 模型件 | `Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer`（12.64 GiB；上卡权重 ~12.3 GiB） |
| 定稿档 | `rk2v4-e8` @ 51,200（生产稳定）；**65,536 实测可行（free ~490 MiB）**；**81,920 贴边（差 3.4 MB 曾拒启，勿用）** |
| rk8v4 上限 | 41,664 贴边 / 37,504 稳定（精算 §7.3） |
| int8 上限 | **32,192** |
| nvfp4 上限 | 实测 57,344 可起（free 260.5 MiB），预测稳定线 53,184 |
| 判据（守望者 v3） | decode < 80 tok/s = 降级；好带 decode ~124–230（随态），冷填 11K ≈ 5.3–5.5 s |
| 逐字门基准 | `verbatim_baseline_cur_a2.json` / `_cur_b2.json`：同配置两臂 8/8 全等（引擎 argmax 确定、噪声地板 0） |
| 谷负担（60K 上下文） | rk2v4 ≈ 0 MiB（池 65K 装得下） |
