# 调研：kvmem/kvmem（始祖线）—— 双后端架构、RAM/SSD 分层与对我们的价值

- 日期：2026-10-15 · 性质：**调研笔记**（第三方项目评估 + 与我们的实现对比 + 可吸收项）
- 作者：CodeBuddy（办公室侧）· 素材：`refs/kvmem-kvmem/`（clone @ 2026-10-15）+ `.temp/ninfer_patch_stat.txt`（补丁文件级统计）
- 一句话：**KVMem 论文团队的原生项目，0.18.0 已正式双后端化（llama.cpp + `iamwavecut/ninfer-all`）——"他的实现"= 引擎外公共层 + 166 文件/1MB 的 ninfer 集成补丁；与我们引擎内 v2 异步页流水是"同期独立收敛的同族解"（异步 + 配额 + 版本化所有权），且其 RC3 官方性能表 = 我们路线（IQ3_S + INT8 KV）在 16GB 卡上的直接数据点。**

---

## 1. 项目定位与血缘

| 项 | 内容 |
|---|---|
| 仓库 | `kvmem/kvmem`（原 `kvmem/kvmem-llama.cpp`，GitHub 自动跳转） |
| 版本 | **0.18.0 正式版**（双后端源码）+ **0.18.1 RC1**（RTX 20/V100 老卡试玩包） |
| 团队 | 论文《KVMem: Virtualizing Million-Token Agent Workspaces on a Consumer GPU》（arXiv 2609.04852）：Di Chai · **Leye Wang**（PKU，= WANG 维护者）· Zeshen Su · Zhiguo Xia · Zhihang Yu |
| 结构 | 公共层 `kvmem/`（内存契约/检索/Host 存储）+ `backends/llamacpp`（ggml-org/llama.cpp @7fe450e1）+ `backends/ninfer`（**iamwavecut/ninfer-all @8319e8f5**）+ `backends/patches/`（版本化集成补丁） |
| 集成补丁规模 | **ninfer：166 文件 / +12,130 / -795**（1MB）；llama：114KB |
| 发布包 | Windows NInfer 三架构（sm86/sm89/**sm120a**，859-971 MiB，含 Web UI）+ sm75/sm70 RC1 |
| 致谢链 | llama.cpp · **Neroued/ninfer** · **iamwavecut/ninfer-all（整合）** · **Ryan-gsq（Windows/GSQ-RCO 工作！）** · 自适应 MTP/快速 prefill/ngram 贡献者 · melis2023（LRFU/GQA max 参考，B 站 melis） |

**血缘要点**：他们挂的 ninfer 上游 = `iamwavecut/ninfer-all`——**与 XuanzhengZhou 线（paicat1/f90e30c1 基线）和我们（官方线系）是同一引擎生态的不同 fork 版本**；且其模型侧致谢了 GSQ-RCO（我们的 Swift-1.5 模型家族）。

## 2. 架构总览（0.18.0）

```
使用侧：Web UI (18200) + OpenAI chat/responses + Anthropic Messages + 工具约束（xgrammar 扩展）
公共层：kvmem/（kvmem_store.hpp 28KB / nvme_kv_tier.hpp 36KB / pinned_kv_tier / host_kv_storage /
        mean_key_retrieval / lrfu / snapshot —— "原生字节存储 + 配额 + 文件 I/O + 有界任务队列"）
后端：llama.cpp（q8_0 等 5 格式；block 可配默认 128）
      ninfer（9 格式：bf16/int8/fp8/nvfp4/k8v4/rk8v4/rk4v4/rk4v4-e8/rk2v4-e8；**固定 64-token 页**）
桥接：src/adapter/（llama 侧 243KB 主适配）+ ninfer 侧补丁内 program/storage/kvmem_window.cpp（+1407 行）
```

**0.18.0 默认配方**（`start-ninfer.ps1`）：context **204800** · **B/R = 36864/16384** · 输出上限 16384 · **Main/MTP KV = INT8/INT8** · 自适应 MTP4 + ngram31 · **sink=12288 / recent=1024** · Host KV **12288 MiB** · **SSD 默认关**（指定 DiskPath 时 D=4096）· LRFU(λ0.5, top-frac0.9) + GQA max · prefill 256 · 单并发。

## 3. 他的实现 vs 我们的（核心对比）

| 维度 | kvmem/kvmem（始祖） | 我们（Ninfer-KVMem-Async） |
|---|---|---|
| 架构位置 | **引擎外公共层**（独立 `kvmem/`）+ 每后端版本化补丁 | **引擎内**（program_impl/storage 的 v2 异步页流水） |
| ninfer 集成方式 | submodule 固定 + 应用 1MB 补丁（`prepare-backends.py`，可 `--check` 重建） | 直接改引擎树（我们的 patch 链） |
| 粒度 | **沿用引擎原生 64-token 页**（"一块对应一页"，10-06 明确决定不改进度）——**与我们同粒度** | 页（64 token） |
| 搬运单位 | 页（**text + MTP 双池一起搬**：`page_bytes = text.stride + mtp.stride`） | 页（我们 MTP 页池处理方式待对照） |
| 核心语义 | **版本化安全边界**：window session id / frontier / history_revision / host_versions / archive；`WindowMemoryBackend` **借用** Program 原生池（不拥有 allocator，生命周期 = 一个安全边界） | publish/drop 账本 + 在飞页计数（**流水线化**而非事务化） |
| 异步形态 | **有界 CPU I/O 任务队列**：调度线程提交、等待 lane 让出计算机会、完成后检查会话版本 → GPU 搬运发布；"排队取消可撤销、已开始 I/O 排空" | v2：提交即返回、下一步收割（单槽 depth=1；v2.1 深流水修法待复核） |
| 所有权 | **移动所有权**（活动↔闲置不复制、恢复不生成冷快照、不重新量化） | demote/restore 拷贝（host-backed anchor 是我们的挂账 42 方向） |
| 层级 | **RAM(H) + SSD(D)**；完整 K/V（含量化附属 + MTP KV）可下沉 | 设备↔host 两层（无 SSD） |
| 检索打分 | **LRFU 加权**（λ0.5 / top-frac 0.9，按 query 相关性更新历史分数）+ **GQA max**（同 head 组取最大）；mean-K 常驻 RAM | sink/window/检索召回（recency 策略） |
| 输出与 R | llama：输出截到 min(ctx,R)；**ninfer：输出不受 R 截断**（追加空间不足时归档、重选、继续生成） | 我们引擎的对应行为待对照（长输出预算） |
| 参数对齐 | B≥128 且 64 倍数；R≥64 且 64 倍数；prefill 为 128 倍数且 ≤R；**B+R ≤ context**；recent ≥64 按整页向下取整 | 与我们引擎参数约束同源（页对齐一致） |
| 统计纪律 | 配对统计（中位/95% 单侧上界，3→7 对）、记二进制 SHA/遥测/原始请求 | 仪表链强、统计弱（可抄其方法） |

## 4. 关键发现（对我们直接有用）

**① RC3 官方性能表 = 我们路线的 16GB 卡官方数据点**（RTX 5060 Ti + **Qwen3.8-27B GSQ-RCO IQ3_S** 图文/MTP）：

```
配置：context 262144 · B/R 36864/16384 · Main/MTP INT8 · GDN FP16 · MTP3（adaptive off）
      · prefill 512 · thinking 128 · LRFU · Host 12288 MiB · SSD off
结果：日常文本 50.08 tok/s｜代码生成 64.54｜长历史工具轮 53.24（32 轮）
      末轮首字 16.87s｜长历史总耗时 855.10s（33 请求，输入 261522 token）
      整卡显存峰值 ~14.12 GiB；长历史阶段系统可用 RAM 最低 8.78 MiB
```
⇒ 这是 **"IQ3_S + int8 KV + 16GB 卡 + 255K 输入"** 的官方实测——与我们精算 §7.7 的"IQ3_S + int8"路线完全对口；**Host 12288 MiB 常驻**与小可用 RAM 并存（内存压力），我们的 host 池配置可对照。

**② v0.18.0 默认 sink=12288 / recent=1024**——我们构建史里记的"env-level candidate"出处在此：**这是 KVMem 官方默认值**（作者视频配方 36K/16K 亦对应 B/R）。

**③ 实现了我们挂账 42 的"亲戚"**：`memory-backend-contract.md`（26.7KB）+ `kvmem_window.cpp`（1407 行）——"往返不复制、版本化恢复、frontier/history_revision、host_versions"——**分叉的完整设计就在我们的 `refs/` 里**。

**④ SSD 层（历史 + 验收）与优化两招**：写合并（96,689→6,447 次调用）+ 空闲区间索引（O(N²)→O(N)）——ninfer RAM→SSD 热成本 +11.1%（上界 +14.5%）、长上下文 +2.1%；**SSD 是进程临时存储（不重启恢复、不跨后端迁移）**。

**⑤ 组合约束（写死在我们引擎里的白名单）**："快速 prefill 只开放 INT8/RK8V4/RK4V4/RK4V4-E8/**RK2V4-E8**"——我们的现役 rk2v4-e8 在列；NInfer 不支持：视频、**overlay 视觉**、DFlash、并行 prefill、旧 --lookup-ngram。

**⑥ 论文与生态位**：arXiv 2609.04852 + QQ 群；本项目 = "KVMem" 品牌本体——我们用的"KVMem"名词的学术出处即此。

## 5. 可吸收项（按可操作性）

1. **`kvmem_window.cpp`（+1407）与 `program_impl.h`（+230）对照精读**——与我们 v2 异步流水的同文件/同域对照（这是全生态离我们最近的一份实现，就在 `refs/`）
2. **配对统计方法**（中位 + 95% 单侧上界；3 对筛查 7 对确认；记 SHA/遥测）→ 引入我们的池扫描/精度 A/B 设计
3. **LRFU + GQA max 检索**（melis2023/kvmem-actkv 参考实现）——研究是否对 DSH 召回有益（我们目前 recency 为主）
4. **"输出不受 R 截断"（归档重选继续生成）**——对照我们引擎的对应能力，作为长输出/unfinished-stream 场景参照
5. **RC3 性能表 + 默认配方**登记进精算/构建史引用（IQ3_S + int8 的官方外部数据点）
6. **SSD 层的代价与优化**（+11% 热成本 / 写合并 / 空闲索引）——我们若开 SSD 层的第一参照
7. **边界互证**：SSD"不重启恢复"、H/D"非 RSS 限制"——与 tancau、XuanzhengZhou 三方一致（KVMem 族共同边界）

## 6. 边界与注意

- 其 ninfer 适配边界 = **Qwen3.5/3.8 Dense**（`qwen4_exp`/suspend/graft/router 会被拒绝）——我们引擎版本关系需对齐（我们基于官方线系，他们基于 iamwavecut 整合系）
- 补丁基线 `iamwavecut/ninfer-all @8319e8f5` **与我们官方线 `f90e30c1` 不同 fork**——吸收前逐文件核对
- ninfer 侧多卡为"按层 pipeline 最多八卡"（同计算能力）；文本+图片 ≤8 并发
- 0.18.0 正式包范围仅 Windows NInfer；llama/Linux/ROCm 源码可构建

## 7. 待办

- [ ] 精读 `refs/kvmem-kvmem/backends/patches/ninfer-kvmem.patch` 的关键段（kvmem_window.cpp 全文 / program_impl.h / engine_core.h / prefill.cpp / planning/startup.cpp）
- [ ] `docs/memory-backend-contract.md`（26.7KB）与 `docs/ninfer-all-migration-validation.md` 精读
- [ ] 登记进 `docs/上游谱系与跟踪纪律`（新支线：**kvmem/kvmem = KVMem 品牌本体，双后端平台**）
- [ ] RC3 性能表与默认配方入精算 §10/§9 引用（第三方校准第三源）
- [ ] 若采纳：配对统计方法 → 池扫描设计更新

## 8. 素材位置

- clone：`refs/kvmem-kvmem/`（README.zh-CN 23.3KB / docs/ 39 篇 / kvmem/ 公共层 / src/adapter / backends/patches 两个补丁 / scripts）
- 补丁文件级统计：`.temp/ninfer_patch_stat.txt`（166 文件清单）
- 关键文档索引：`docs/active-kv-tiering.md` + 验收记录 / `docs/multi-backend-differences.md` / `docs/ninfer-all-migration-plan.md`（36KB）/ `docs/memory-backend-contract.md` / `docs/active-kv-tiering-plan.md`
