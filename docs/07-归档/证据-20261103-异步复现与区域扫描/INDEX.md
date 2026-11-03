# 2026-11-03 实验台账

## 一、复现实验（+32% 格子）

档位：`rk2v4-e8 / pool 65,536 / depth 2 / filler 300KB（prompt 74,700）/ rounds 2 / max_tokens 2000 / 无前置请求`；件 `9453FFC6`（lineage `ninfer-serve-RC2.exe`）。

| cycle | 顺序 | 臂 | r1 | r2 | sha r1 | sha r2 |
|---|---|---|---|---|---|---|
| 1 | off→on | OFF | 244.2 | 215.3 | 81749d21fb20714a | 2e13dd9c06a9acb3 |
| 1 | | ON | 323.3 | 315.6 | 35bbafa0740511e8 | 7b7e6eda53a726fb |
| 2 | on→off | ON | 323.6 | 315.3 | 35bbafa0740511e8 | 7b7e6eda53a726fb |
| 2 | | OFF | 244.6 | 215.4 | 81749d21fb20714a | 2e13dd9c06a9acb3 |

- r1 配对差：+32.4% / +32.3%；r2：+46.6% / +46.4%
- 极差比：OFF 1.0016、ON 1.0009（门 ≤1.15）
- 与 2026-10-28 `test_sym3_{on,off}_nowarm.log`（322.x / 244.0）四个 sha 逐字节相同

| 文件 | 内容 |
|---|---|
| `repro32_20261103_055206.txt` | 四臂 ABBA 主台账（预登记判据、waitready、req 行、ARM-RESULT、SUMMARY、环境复原） |
| `repro32_DONE_20261103_055206.txt` | 完成标记 |
| `gate_repro32_c1_off.json` / `gate_repro32_c1_on.json` / `gate_repro32_c2_on.json` / `gate_repro32_c2_off.json` | 四臂 HTTP 侧计时与输出 sha（r1/r2） |

## 二、同日其他台账

| 文件 | 内容 |
|---|---|
| `async_region_20261103_043850.txt` / `async_region_DONE_20261103_043850.txt` | 区域扫描主台账 |
| `async_region_p65536_20261103_050557.txt` | 池 65,536 补充扫描台账 |
| `gate_c12_*.json` / `gate_c13_*.json` | 关键两格的计时与 sha |
| `three_arm_fixedw_20261103_031853.txt` | 生产档 rk8v4 三臂轮账（off/on/on_fixedw） |
| `oldbin_ab_20261103_051014.txt` | 旧件四臂对照（RC1_S13 / RC2_sym3 × on/off） |
