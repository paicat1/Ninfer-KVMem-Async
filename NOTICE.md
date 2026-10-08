# NOTICE

本仓 **Bonsai-27B-NInfer-kvmem** 是**上游衍生的部署 / 验证工程**，**非官方发布方**。

## 一、上游组件与许可

| 组件 | 来源 | 许可 |
|---|---|---|
| NInfer（C++20 / CUDA 推理引擎） | `Neroued/ninfer` | Apache-2.0 |
| NInfer 融合引擎（KVMem 环 + host-backed 复用） | `1314521gjy/ninfer-fusion-kvmem` | Apache-2.0 |
| 三元量化工具链 / 转换 / 校验 | 沈三殊（shensanshu）· ModelScope `shensanshu/ninfer-ada-ternary` | 见其发布页 |
| 模型制品 `Ternary-Bonsai-2-27B-ninfer-v3.ninfer` | 沈三殊（shensanshu） | 见其发布页 |

本仓的引擎源码（`engine-main` 分支）**原样包含上游源码**，并保留上游 `LICENSE` 与 `NOTICE`。

## 二、本仓相对上游的修改

**引擎层（源码树内）**
- MSVC 编译兼容 ×7（C2326 / C3495 / C2026）—— 让上游源码在 Windows / MSVC / sm_120a 下编得过；
- **Design C**：thinking 阶段 `stop` 强制进 answer，避免"空正文"；
- STANDALONE 前端单测开关（绕开上游坏测试 bundle）。

**项目层（本仓新增，非上游）**
- GUI 启动器（`ninfer_launcher.py`）、日志工具（`serve_tee.py`）、启动脚本；
- 构建脚本与复现材料（`build/`）、产物身份清单与哈希锚点；
- 文档：项目构建史、上游评估与复测报告、KVMem 教程。

## 三、许可

- **引擎源码部分**：随上游 **Apache-2.0**（全文见 `LICENSE`）。
- **项目层文档与工具**：同为本仓作者所有，按 **Apache-2.0** 发布。

## 四、无担保

本工程按"现状"提供，不附带任何明示或暗示的担保。模型输出与性能数字均带条件口径，**不构成对外承诺**。
