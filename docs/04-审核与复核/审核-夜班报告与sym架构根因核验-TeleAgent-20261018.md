# 审核：夜班报告与 sym 架构根因核验（TeleAgent）

- 日期：2026-10-18（审核执行：16:54–17:15）
- 审核对象：① CB 夜班报告（15:4x–16:2x，用户睡前授权自主跑）② CB 根因调查（16:5x–17:1x：sym 件"挂死"= sm_86 架构错）
- 审核方式：全程只读；关键链独立复跑（不采信转述）；[EVIDENCE] 格式

## 一、总体结论

1. **根因成立（独立核验通过）**：sym 件"挂死"= 构建漏传 `-DCMAKE_CUDA_ARCHITECTURES=120a`，编成 sm_86 目标；本机 RTX 5080（sm_120）无法直载 sm_86 SASS → CUDA 回落 PTX JIT（357 kernel 逐个现编）→ 表现为"启动挂死"。五链独立复跑全部吻合。
2. **夜班报告定性修正一处**：受阻项"graph capture 阶段死循环"应更新为"**JIT 长征（有进展但极慢，非死循环）**"——dump 显示 44/45 线程合法等待 + 1 线程 JIT 编译器在工作。
3. **修复方向正确**：重编显式传 120a（其余不变）→ 产出真正的"S13 等价符号件"。审核侧无阻塞。
4. 夜班报告完成/瑕疵/终态各条：主体证实，2 处小校准（空窗时长、件体积口径）。

## 二、根因五链独立核验

| # | 环节 | CB 声称 | 独立核验 | 判定 |
|---|------|---------|----------|------|
| 1 | 本机 GPU | RTX 5080 = sm_120 | nvidia-smi：compute_cap 12.0，驱动 616.92 | ✓ |
| 2 | S13 生产件 | 384×sm_120a | cuobjdump 独立重跑：384/384 = sm_120a | ✓ |
| 3 | sym1/sym2 | 357×sm_86 | cuobjdump 独立重跑：357/357、357/357 = sm_86 | ✓ |
| 4 | 缺参数链 | build_sym.ps1 未传 arch；CMakeLists 默认 86；树缓存 86 | 三处原文比对全部吻合 | ✓ |
| 5 | dump 佐证 | JIT 长征非死循环 | MDMP 魔数合法；parse_dump.py 真解析（线程/模块/内存三流）；栈分析 RIP=nvptxJitCompiler64.dll+0xf80b3d，44/45 线程 ntdll 等待 | ✓ |

证据行：
- [EVIDENCE] cuobjdump 独立重跑（17:12）：ninfer-serve.exe=384×sm_120a；ninfer-serve-sym.exe=357×sm_86；ninfer-serve-sym2.exe=357×sm_86
- [EVIDENCE] CMakeLists.txt L8-9：`if(NOT DEFINED CMAKE_CUDA_ARCHITECTURES) set(CMAKE_CUDA_ARCHITECTURES 86 CACHE STRING ...)`
- [EVIDENCE] build_sym.ps1 L39：`cmake --preset release -DCMAKE_CUDA_HOST_COMPILER=... -DCMAKE_EXE_LINKER_FLAGS=...`（无 arch 参数）
- [EVIDENCE] engine-src build\CMakeCache.txt：`CMAKE_CUDA_ARCHITECTURES:STRING=86`
- [EVIDENCE] sym2_stack_analysis.txt：`RIP module distribution: {'nvptxJitCompiler64.dll': 1, 'ntdll.dll': 44}`

## 三、夜班报告逐条判定

**完成项（3 条：证实）**
- 锁释放：证实（CASE_LOCKED.json 已删=git 状态 D；内容留 git HEAD：case_20261018_124615_logwatch、release_by=user only）
- sym 双版本构建+冒烟：证实（v1 全量 65.8min；sym2 重链 0.3min；两冒烟卡死：15:51:52→16:03:44、16:12:43→16:17:13，均无 CUDA graphs ready）
- 符号化工具链：证实（symbolize.ps1 在；sym2 侧复现 5/5 成功——httplib multipart / ops / small_t_i8 / vector<_Tgt_state_t> / nlohmann json）

**受阻项（3 条）**
- sym 不可用：现象证实；定性更新（见总体结论 2）
- 落名被否证（两套 PDB 落点全不同）：成立；补注 v1 侧当前不可复现（见发现 1）
- 三案定向：待裁决；审核建议见第五节

**瑕疵项（1 条：证实+校准）**
- 空窗：实测 16:12:37（生产停写）→16:17:25（还原）= **4 分 48 秒**；报告"~4 分钟（16:12–16:17）"基本吻合

**终态（5 条）**
- 生产 16:17:25 还原：证实（test_watch.log；build -1-g27dc746；CUDA graphs ready 1.8s）
- 181.1 tok/s：**原始输出未定位**（work/logs/.temp/docs/evidence 全域搜索无独立出处，仅见报告转述）→ 待补证
- 未推=0：证实（HEAD=origin/main=4364b60）
- "约 3GB"：校准——实测 4 件合计 **3.56GB**
- 未提交 2 项：证实（构建史 M + 锁删除 D；"预登记配方"修改已在 4364b60 提交，非未提交项）

## 四、审核方独立发现（4 项）

1. **v1 符号化当前不可复现**：复跑 symbolize.ps1（v1 参数）5/5 FAIL（err=126/487）。机制：dbghelp 按映像内嵌路径加载 PDB，16:08 sym2 重链覆盖 build 目录 ninfer-serve.pdb（241MB），v1 exe 签名匹配链断；且 symbolize.ps1 的 `-Pdb` 参数为死参数（未传入 SymInitialize/SymLoadModuleEx）。影响：v1 落点不可独立验证（架构根因查明后此路线重要性已降）；工具修复建议：显式传搜索路径或修复后重验。
2. **pdb_archive v1 副本被覆盖**：infer-serve-sym_20261018.pdb 现为 sym2 版（241,561,600B @16:08:21）——同名覆盖，v1 归档丢失（仅剩 self-built 121MB 副本）。
3. **锁释放留痕缺口**：无 released 留档副本（124615 案件目录无；唯一 released 副本属 225943 旧案）；授权句无机械留痕（APPROVAL_LOG 搜索"睡觉"0 命中）——user-only 操作缺留痕门（流程改进建议）。
4. **探针数值证据链**：181.1 tok/s 与 503 的原始输出均未落盘——建议后续探针输出固定落盘（证据链完整性）。

## 五、对三项决定的审核意见

① **未提交 2 项**：构建史 §126/§127 + 锁删除——内容与事实核对一致（本报告第二、三节），可按 T-COMMIT-APPROVAL 流程批。注：§127 中"graph capture 死循环"表述建议随根因更新为"JIT 长征"后再提交。
② **重编（加 -DCMAKE_CUDA_ARCHITECTURES=120a）**：根因成立，**建议批准**；验收要求：重编后先 cuobjdump 验 arch=120a（预期 384 个）再冒烟；建议将 arch 参数固化进 build_sym.ps1（或构建规程）防再漏。
③ **三案定向**：建议顺序调整——**先重编验证**（约 66min）；若 sym 件修复后可用，直接重走"sym 冒烟 + 挂死 dump 自证"原路线（零布局假设拿函数名）；若仍不可用，再在 (a)/(b)/(c) 中定向。理由：架构修复可能直接消解本问题，避免过早投入插桩改造。
④ **sym 件处置**：建议待重编验证后一并处置（3.56GB）。

## 六、审核时点与状态注记

- 审核基线：夜班报告 16:17:25 终态 + 根因调查（至 17:11）
- 当前系统状态：17:02:30 生产件已再还原（pid 25416；sm_120a 直载，11.0s ready，free 654.6MiB）
- 本报告为审核意见，不构成修复授权；重编/处置由用户裁决。
