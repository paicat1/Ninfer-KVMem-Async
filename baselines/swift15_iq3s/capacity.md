# SWIFT-1.5 IQ3_S 容量与判据（现行集 · 2026-10-14）

| 项 | 值（实测） |
|---|---|
| 模型件 | `models\swift15_iq3s_mtp.ninfer`（11.91 GiB；上卡权重 **11.3 GiB**；方言 `gguf_blocks_v1` 可载） |
| 起服 | **必须 `--cuda-graph-allowance-mib 192`**（64 时 WARN：`CUDA graphs used 236.8 MiB > allowed 64.0`）；载入 8.7–9.5 s |
| 池 × KV（65,536 固定） | **rk8v4 free 727.9 MiB** · nvfp4 free 1.09 GiB · rk2v4-e8 free 1.50 GiB |
| int8 | **57,344 → free 482.6 MiB**；折算 61,440≈347 MiB / 65,536≈213 MiB（贴边）⇒ **生产建议 57–61K** |
| 深 60K 单轮 | rk8v4 **37.3 s / decode 143.7 / 接受 64%** · nvfp4 46.7 s / 118.2 / 53% · rk2v4 37.1 s / 112.8 / 49% · int8 36.2 s / 117.1 / 60% |
| 逐字门（同底座内） | rk8v4 ≡ rk2v4 **8/8**（逐字相同）；nvfp4 与二者 **3/8**（格式特性，非底座特性） |
| 跨底座（vs Q2LYNN） | **1/8**（预期；golden SHA 不可跨模型比） |
| 谷负担（60K 上下文） | rk8v4 @65,536 ≈ 0（池 ≥ 上下文）；int8 @57,344 ≈ 940 MiB 量级（27.8K tok × 33.8 KiB） |
