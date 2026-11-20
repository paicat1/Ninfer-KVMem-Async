# ChangeRecord · C7

| batch | 时间 | 改了什么 | 为什么 | 怎么改 | 门控 |
|---|---|---|---|---|---|
| 0 | 2026-11-18 23:0x | 立项文件五件 | SDA 强制 | 静态文件 | gate_check dp0/dp1/dp2 均 GATE_PASSED（2026-11-18 22:55）；已知门缺陷：令牌位未生效=假绿，已登记待修 |
| 1 | 2026-11-18 23:37 | `kvmem_retrieve_launch.cu` 的 `dot_q_bf16_sum` 向量化（+21/-2；备份 sha16 8833AE31） | 刀1a：微基准 M1 3.803× / M2' 0 失效 / M3 top-16=1.000 三线 PASS | float4 载入 8 元素（q=BF16 1×float4、ksum=F32 2×float4）+ 4 累加器 ILP；atomic/head_w/mask/候选集不动 | TU 0 错 → BUILD-EXIT=0 + ARCH-GATE OK → 换装 F184F1E0 → 中间 trace：kernel 191.5→175.6 ms（-8.3%）、fill 531.0→492.7 s（-7.2%）、429/truncated=0、RECALL=PASS |
| 1-判定 | 2026-11-19 | 刀1a **完成但收益有限（-8.3%）**，远低于微基准 3.803× | 微基准只测内环；真 kernel 份额未知（解释 A/B 待分段裁决） | 保留在役（零回退）、**刀1b 冻结至分段证据**；不得据此宣称"点积占 8%"为定论 | SASS 佐证：旧件 LDG.128=0 / 新件 42，指令 1712→2216、寄存器 56→46（占用率反升） |
