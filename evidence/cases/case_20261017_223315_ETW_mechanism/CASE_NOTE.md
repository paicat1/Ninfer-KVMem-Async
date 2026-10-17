# ETW / 引擎内部计时：机理层定位（2026-10-17 22:2x–22:3x）

## 手段（预登记三件事全做到）
- 引擎内部计时：`NINFER_SPIN_STAMP_VERBOSE=1` + `NINFER_STEP_PROFILE=1`（window 64）
- **池不变 = 49152**（单变量：只开 trace）
- 全窗：基线 → 400 MiB 加压 → 谷 → 释放恢复
- 武装确认：`[ninfer] spin-stamp DEBUG: armed (mapped host buffer, 26 slots)` + `step graph DEBUG: armed, created 26/26 events`

## ★ 核心结果（分段定位）
| 段 | 基线 (n=1176) | 谷 (n=547) | 倍数 |
|---|---|---|---|
| ingress | 0.0 ms | 0.0 ms | — |
| **target** | **22.3 ms** | **249.9 ms** | **11×** |
| └ setup | 0.00 | 0.00 | — |
| └ prepare | 0.00 | 0.00 | — |
| └ **verify** | **22.33 ms** | **249.92 ms** | **11×** |
| draft | 6.4 ms | 114.8 ms | 18× |
| egress | 0.1 ms | 0.2 ms | — |
| **total** | **28.9 ms** | **364.9 ms** | **13×** |

## 结论（三层递进）
1. **慢点唯一**：全部在 `target` 阶段，且 `target-split` 显示 **100% 落在 `verify`**（setup/prepare 恒 0）。
2. **verify 是什么**：MTP 投机解码里"用目标模型验证草稿 token"的那一步 —— 它要**读草稿位置的 KV 页**。
3. **⇒ 机理假说（收窄到可验证）**：外压 ⇒ **verify 步的 KV 页读取路径**变慢 11×（候选：页在 host 侧需回搬 / 分配器在紧张态走慢路径 / 内核访存竞争）。
   —— `draft` 同步变慢 18× 佐证"读 KV 的路径都受影响"（draft 也要读 KV）。

## 与既有结论的关系
- 触发层（外压 ≥400 MiB 必中 / ~150 MiB 20%）不变；
- 机制层从"program_submit 变慢"**收窄到"target/verify 变慢"**；
- 仍解释：device_wait 不变（verify 的等待不在那个计数器里）、引擎搬页计数器为 0（ring retrieve 是另一条路）。

## 仍未闭合
- verify 内部**为什么**慢（需 CUDA 级 trace 或 kernel 计时）；
- draft 同步变慢是否同源；
- ring profile 的 mk/rs 在谷段是否跳（见本卷 engine_log_etw.txt）。

## 现场
- trace 已开（NINFER_STEP_PROFILE=1 + SPIN_STAMP_VERBOSE=1）；收尾时关回现役配置（**池仍 49152**）。

