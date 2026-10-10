# NOTICE

本仓 **ninfer-kvmem** 为**上游衍生的部署/验证工程**（非官方发布方）：在两代前序工程
（① Bonsai-2 on NInfer → ② NInfer×KVMem 融合）跑通的架构上，部署更大的模型
（Qwen3.8-27B-Coder390-EfficientThink，27B）。

## 一、上游组件与许可

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer（C++20 / CUDA 推理引擎） | `Neroued/ninfer` | Apache-2.0 |
| NInfer 融合引擎（KVMem 环 + host-backed 复用） | `1314521gjy/ninfer-fusion-kvmem` | Apache-2.0 |
| 模型（Coder390-EfficientThink 系，GGUF-NInfer 容器） | ModelScope `Merkyor/Qwen3.8-27B-Coder390-EfficientThink-...-RLOO-GGUF-NInfer`；HF `nerkyor` 同名系 | Apache-2.0（见其仓库页） |
| 三元量化工具链 / 转换 / 校验 | 沈三殊（shensanshu）· ModelScope `shensanshu/ninfer-ada-ternary` | 见其发布页 |
| 视觉塔（嫁接来源） | 上游模型自带 vision 组件（随嫁接件分发） | 随上游 |

## 二、本仓新增（Apache-2.0）

- `ninfer_launcher.py`（GUI 启动器，8 预设 + 校验告警）
- `scripts/`（MTP 头自转、视觉嫁接、A/B 与召回探针）
- `patches/W1-W4_engine_fix.patch`（思考预算熔断修复）
- `docs/`（构建史 v1-v32、交叉审核报告、调研与教程）
- `build/`（引擎构建脚本与补丁）

## 三、模型代际说明

```
MTP.ninfer（orig 原件 = 上表 ModelScope 下载件的 NInfer 容器）
  └─ recode_mtp.py（自转 MTP 头，iq4_nl）
       → mtp-iq4nl.ninfer（文本主力）
            └─ graft_vision.py（嫁接官方视觉塔）
                 → mtp-iq4nl.vision.ninfer（视觉主力）
```
