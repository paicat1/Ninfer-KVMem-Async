# DeltaSpec · C7

## 刀1a（向量化）
- 现状：kvmem_retrieve_launch.cu:78-103 逐元素标量点积、单累加器
- 目标：float4 载入 + 4 累加器 ILP；累加结果与 atomic 次数不变
- 判据：M1 ≥15%↓、M2 ≤1e-5（vs 原版）、M3 top-k ≥99%

## 刀1b（per-head 一趟化）
- 现状：两趟点积（:179 phase1 max / :239 phase2 加权）
- 目标：每 head 16KB shared 存 logits，heads 顺序，点积只算一遍；每 b 恰一次 atomicAdd
- 判据：N1'≤340s、N3'<145ms、N6' 双线 oracle、N4 召回、N5 安全、N7≤5s
