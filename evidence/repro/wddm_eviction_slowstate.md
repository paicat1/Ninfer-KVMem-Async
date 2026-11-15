# WDDM 逐出+fault-back 慢态判别实验（2026-11-15/16）

> 归因对象：174K+ 大 prompt decode 崩塌（3.3-3.9 tok/s）与 prefill chunk 边界静默（§234）。当前为**待判别假说**，本文件随判别实验推进更新。

## 条件

| 项 | 值 | 来源 |
|---|---|---|
| 卡 | RTX 5080，16,303 MiB | nvidia-smi |
| 引擎 | self-built-20261008（rc1 系） | 日志 `build` 行 |
| 模型件 | `swift15_iq3s_mtp+dflash2.ninfer` | 日志 CMD 行 |
| `--kv-capacity` | 110,592（慢/重放轮）/ 122,880（快轮） | 日志 `capacity` 行 |
| `--host-kv-mib` | 16,384（三轮同） | 日志 CMD 行 |
| ENV | `NINFER_KV_WINDOW`/`RETRIEVE`/`SCORE_BUDGET`/`RING`/`HOST_PAGEABLE`/`ASYNC_DEMOTE*` 两轮逐项一致 | 日志 ENV 块 |
| 负载 | DSH 真实编码会话（tools 40，thinking medium，max output 32,768） | 日志 req 行 |
| 外部干扰变量 | 2026-11-15 14:29-14:44 DSH 便利店 WebGL 3D 场景多轮渲染 + 1M tok（用户口述时间线） | 用户确认 |

## 运行记录

| # | 运行 | prompt 峰值 | decode tok/s（>149K 段） | chunk 边界静默窗 | 判读 |
|---|---|---|---|---|---|
| 1 | 12:09 快轮（池 122,880） | 209,303 | 101-310 全程 | 无 | 负对照：同引擎族大 prompt 不崩 |
| 2 | 13:52 慢轮（池 110,592） | 176,854 | **2.7-10（#78 起 17 条零恢复）** | **每 chunk ~25-30s host 0.0%** | 案发轮；悬崖在 #77→#78（14:31→14:44 空档后） |
| 3 | 11-16 晨重放（池 110,592，GPU 独占 62 MiB 起服） | 95,227 | 快（TTFT 943ms-4.4s） | **零静默窗**（1.3-1.6k tok/s 连续） | 快态恢复；95K < 池，判别区间未进入，假说未定案 |

## 判据（预登记 §234）

- **实锤** = 重放进入 >110,592 判别区间后 chunk 边界静默段消失
- **证伪** = 同配置重放进入判别区间后静默段仍出现（转引擎内部状态，NINFER_DEMOTE_PROFILE=1 插桩）

数据源：`logs/serve_20261115_120900.log.gz`、`logs/serve_20261115_135226.log(.gz)`、`logs/test_wddm-judge2.log`；分析脚本 `work/data/chunk_anatomy.py` 等 12 件。
