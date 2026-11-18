# DP-0 需求确认 · C7 KV 检索打分 kernel 优化

- 问题：120K 填充 520.9-531.0 s，其中 `kvmem_retrieve_scores_kernel` 占 GPU 忙碌 86.5%（455.5-465.7 s / 2,432 次 / 187-191.5 ms）
- 目标：刀1a 向量化 + 刀1b per-head 一趟化，填充 → 约 6.2-6.3 min（F1/F2 线）
- 依据：构建史 §242；施工书 v2（L76 已更正）
- 范围：3 文件（kvmem_retrieve_launch.cu / kvmem_score.h / work\data\bench 新增微基准）
- 用户令牌: [待用户补签]
