# 全库通读索引与时间线（CodeBuddy · 2026-10-12）

> 物理位置归属：本文件为 paicat1/Ninfer-KVMem-Async（沿革：ninfer-kvmem → 2026-10-12 改 Qwen38-27B-NInfer-kvmem 并转私库 → 2026-10-13 改本名）工作区内的通读产物，只读索引性质，不改动任何既有文档结论。
> 用途：一次全库通读的沉淀——时间线、文档索引、机制速查、挂账总表、收尾观察；后续会话可据此导航，不必重新通读。
> 状态：**已完成**（2026-10-12，本地 HEAD `4c9a75a`；参阅范围见 §七）；本文件未提交（待用户批准）。

---

## 一、库身份与血缘（一句话版）

- **本仓**（仓三）：`paicat1/Ninfer-KVMem-Async`（沿革：`ninfer-kvmem` → 2026-10-12 `Qwen38-27B-NInfer-kvmem` + 转私库 → 2026-10-13 本名），本地 `h:/个人/ninfer kvmem`
- **血缘**：前两仓成果已继承——① `paicat1/Bonsai-27B-NInfer`（三元线发布）、② `paicat1/Bonsai-27B-NInfer-kvmem`（三元+KVMem 环线）；本仓新增经验计划回馈前两仓
- **上游三条**：`1314521gjy/ninfer-fusion-kvmem`（Bonsai 官方线，引擎同源，唯一活跃跟踪对象）、`kvmem/kvmem-llama.cpp`（兄弟件 RC2，对照参照）、`tancau/ninfer-kvmem-ring`（环作者；参考树在 `refs/tancau-ninfer-kvmem-ring/`）；基座链 Neroued/ninfer → ashalliants/ninfer-3090 → iamwavecut/ninfer-all
- **双智能体协作**：CODE（CodeBuddy，施工+构建史）/ TELE（TeleAgent，独立审核）；铁律 T-NO-FOREIGN-WRITE（2026-10-12 立）；指代纪律禁止"官方"统称
- **设计目标**：Qwen 4 27B（Bonsai/NInfer 格式）的着陆预备——加工链与容器解耦（换容器只重跑 `recode_mtp.py` + `graft_vision.py`）

---

## 二、时间线（10-09 → 10-12，按构建史章节）

### 10-09（建线与 P0/P1）
| 时段 | 事件 | 章节 |
|---|---|---|
| 白天 | 建线、git 基线、首轮调研（CB/TELE 双份交叉审核） → 三目标（MTP 跑通 / 视觉 / ngram） | §一/二/三 |
| 全天 | 三轮交叉审核收敛 + 5 点落实；裁定 MTP 走"数据侧重打包"（探针 q8_0 无损） | §三 |
| — | P0 启动层适配 Coder390（7 改 2 增）；P0b 引擎统一 self-built；P0c 裸解码基线 **55.7-55.9 tok/s** | §三·六 |
| — | P1 MTP 数据侧重打包（q4_0→q8_0 位级无损，L0/L1/L2 三档全过；13,271,040 块零不匹配） | §三·七 |
| 夜 | ★**MTP 跑通**：官方 Q8MTP 验证 → 起服两度显存失败 → **自转 iq4_nl**（Δ0、省 212 MB，决定一步）→ 起服 + A/B（散文+32%/代码+233%） | §三·八 |
| 23:40 | ★池/窗口/上下文**三量澄清**：256K 逻辑 ctx + 40K 全速池（推翻"24K"误读；20,203 token prompt 答对） | §三·八§4.2-4.4 |
| — | 启动器定稿（9 处 + 2 bat + 4 档） | §三·九 |

### 10-10（视觉 + DSH 撞墙定案）
| 时段 | 事件 | 章节 |
|---|---|---|
| — | 定稿"闪退"根因 = 缺 20.4 MiB（非参数错）；视觉可行性（官方版+`--vision-cpu`） | §三·十 |
| — | 两处纠错（关思考误设 → high/tb16000；擅自起服立纪律） | §三·十一 |
| — | `--default-thinking-budget` 不占显存取证；**挂账 35 视觉塔嫁接**施工+实机验证闭环（12.94 GiB，小 202.5 MiB） | §三·十二 |
| — | ngram 实测：净贡献 ≈ 0（+2.7% 无显著性），保持默认 | §三·十三 |
| — | **本机 DSH 实证**（Tauri 载体；四项声称逐字实锤；cordis.patch.yml 活配置）→ 撞墙分支初判（后自纠） | §三·十四 |
| 晚 | **勘误 + TELE 交叉审核收敛**：撞墙真因 = **`--kv-lease-growth` bounded completion**（输出含思考 ~4,096 处被租约窗口砍断；tb 无关；22 次 output-limit 15 次落 3,900-4,400 带）⇒ 修法 **去 growth**（挂账 38 施工）；**双环境行为差异同题定案**（纯 KVMem 无租约机制） | §三·十五 |

### 10-11（A 臂闭环 → W1-W4 → 页漂移定案 → 异步页流水 v2 突破）
| 时段 | 事件 | 章节 |
|---|---|---|
| 凌晨 | **A 臂实测闭环（挂账 38 销账）**：去 growth 后零撞墙（req#6=16,143 tok 旧墙 4 倍）；池标定 55,296✅/57,344✗；视觉三合一+识图 26.9s；挂账 39 发现（非 growth×视觉 scatter） | §三·十六 |
| — | **W1-W4 引擎施工**（84 行 patch）+ 四重验收全过（tb 熔断注入实测、SSE progress 实流）；push 假成功教训（ahead 0 唯一判据） | §三·十七 |
| 04:00-04:30 | **自主实验夜**：64K 池标定成功；★**掉速机理定案 = 页漂移**（轮数触发，非池深——34 轮 ~330 页滞留 host → 3 tok/s）；stream 挂起修正；挂账 39 销案；DSH maxTokens→24K；V1c 配置（vision+64K+无growth+graph128） | §三·十八 |
| 09:00-10:00 | 实机验证"三定一再现"：撞墙清零（51 请求/prompt 118K 零截断）；页漂移二次实证；DSH 压缩机制实锤（headroom 65,536；ctx 262,144→229,376 → 触发 94K）；sequence 重建风暴 + 恢复实操 | §三·十八§7-9 |
| — | ★官方已立案：**B34=页漂移 / B35=撞墙 / B33=429 / B37=压缩截断 / B39=缓存卡住**；**D-01 sink 缓解**（`NINFER_KV_SINK=5120`，五→**六开关**；官方数据 221s→1.4s） | §三·十八§10 |
| — | 谱系连环失误教训 + "开工必读"清单四条；上游 Bonsai 线 23 提交逐条评审（引擎行为级变更 = 0；可吸收 635a277）；KVMem 源头侦察（issue #114 同族缺陷；**tancau 作者级施工书**：复用深度由降级顺序决定/落袋与降级互斥/**host-backed anchor = 唯一真解**） | §三·十八§11-13 |
| 下午 | 挂账 41 三次复现（伪象→未达引擎→规模修正证伪）⇒ **并入挂账 42**（send 阻塞证伪） | §三·十八§14 |
| 14:35-21:10 | ★★**挂账 42 全链施工 + 44 定案**：取消检查点前移 → 批量 demote K=8 → **v2 异步 demote（PendingDemote 槽 + transfer stream）**；**实机 103-195 tok/s（前同区 4-6，提升 20-40 倍）、10+ 轮零降速**；峰值 decode 333.0 / prefill 991.4；**死亡谷解剖**（req#61 三段式，可自愈；demote copy 慢为主因） | §三·十九 |
| 夜 | v2.1 多批 in-flight 施工（单槽→N 槽环形，`NINFER_ASYNC_DEMOTE_DEPTH`）；restore 批量化（"挂账 46 第四步"，128 次串行→1 次并行） | 设计稿 + 状态归档 |

### 10-12（挂账 47 修复 → 解耦 → 改名 → 死亡谷回归修复）
| 时段 | 事件 | 章节 |
|---|---|---|
| 00:2x-02:5x | ★★**挂账 47 定位并修复**：67K 超池崩溃（0xC0000409 静默 abort）——三处根因链（commit_activation 快照断言 → 中止路径 stale reservation → `catch(...){terminate()}`）；修复 = 带原因终止 + 失效回滚跳过（仅 .cpp 可增量）；新预设 `★64K视觉稳（v2.1实测·nograph）`；取证工具 6 件（dump_stack/unwind/sym_resolve/find_exception/find_throw_string/range_check） | §三·二十 |
| 03:5x | 挂账 45 更正（中文 /showIncludes 根因**自撤**） | §三·二十一§6 |
| 凌晨 | ★★★**解耦施工**：本仓自持引擎树 `engine-src/`（不入库）+ build 脚本去跨仓路径 + **T-NO-FOREIGN-WRITE** 铁律；仓二完全恢复（对象库物理抹除我方提交） | §三·二十一 |
| 04:52 | 本仓全量重编完成（[1089/1089]）；07:30 部署起服（回退锚 .bak_20261012_073043） | §三·二十一§5 |
| 白天 | **改名** + 转私库（`Qwen38-27B-NInfer-kvmem`）；**死亡谷入谷回归定案 + 修复**：`NINFER_ASYNC_DEMOTE_DEPTH>=2` → 默认改回 1；G2 部署；V2 实测 54.8K→311.7 tok/s；**E4 多轮验证 41K/83K/125K 全通过（111-288 tok/s）**；挂账 45 证伪（ninja 依赖记录完好，增量重编可信） | docs/长程 + 最新提交 |

---

## 三、构建史章节索引（docs/ninfer-kvmem-项目构建史.md，1728 行）

| 章节 | 行号 | 一句话 |
|---|---|---|
| §〇 项目定位 | 47 | — |
| §一 建线与基线 | 57 | 10-09 git 基线 |
| §二 首轮调研 | 82 | 三目标路径 |
| §三 交叉审核 | ~110 | 三轮收敛 |
| §三·六 P0 启动层 | ~ | Coder390 适配 + self-built |
| §三·七 P1 MTP 打包 | ~ | q4_0→q8_0 |
| §三·八 ★MTP 跑通 | ~ | iq4_nl + 池机制澄清 |
| §三·九 启动器定稿 | ~ | — |
| §三·十 视觉可行性 | ~ | --vision-cpu |
| §三·十一 两处纠错 | ~ | 关思考/擅起服 |
| §三·十二 两项取证 | ~ | tb 不占显存 + 视觉嫁接闭环 |
| §三·十三 ngram 实测 | ~ | 净贡献≈0 |
| §三·十四 DSH 实证 | 1086 | Tauri + 活配置 |
| §三·十五 勘误+撞墙定案 | 1140 | **撞墙 = growth；去 growth** |
| §三·十六 A 臂闭环 | 1195 | 挂账 38 销账 |
| §三·十七 W1-W4 施工 | 1248 | 四重验收 |
| §三·十八 实验夜 | 1280 | **页漂移定案 + sink 六开关** |
| §三·十九 异步页流水 v2 | 1456 | **20-40 倍突破** |
| §三·二十 挂账 47 | 1544 | 超池崩溃修复 |
| §三·二十一 解耦 | 1595 | engine-src + T-NO-FOREIGN-WRITE |
| §四 挂账 | 1674 | 47 项状态表 |

---

## 四、机制速查（跨文档沉淀）

### 4.1 三个上限的分离（§三·八§4.2）
- `--max-context` 262,144 = 逻辑天花板（允许寻址）
- `--kv-capacity` 51,200 = 设备活跃池（全速区间；定稿值，历史 40,960→55,296→51,200）
- `NINFER_KV_WINDOW` 32,768 = 允许池<上下文的门（唯一真实作用；环窗口语义从未实现=死旋钮，但它是"门"）
- 输出侧：DSH maxTokens 24,000（DSH 侧配置）；tb 16,000（服务端 `--default-thinking-budget`）

### 4.2 KV 六开关（+2 调试开关）
`NINFER_KV_WINDOW / NINFER_KV_SINK=5120 / NINFER_KV_RETRIEVE / NINFER_KV_RING（空转旧名，防误导保留）/ NINFER_HOST_PAGEABLE / NINFER_KV_REUSE_HOSTBACKED`；调试：`NINFER_ASYNC_DEMOTE`（默认 1，深度已回 1）、`NINFER_DEMOTE_PROFILE`。**手写 bat 必须自带，否则拒启或静默答错。** 打分环一开默认 ON（无需 `NINFER_TERNARY_KVMEM*`）。

### 4.3 撞墙（DSH output limit）定案【两份一手文档已全读】
- 演进：10-10 办公室讨论（源码钉死"tb 与 max_tokens = **包含关系**"；"30 秒"算术 ≈1,000-2,600 token；DSH asar 取证 DEFAULT_MAX_TOKENS=32768/watchdog 300s）→ 当晚本机 TELE 定案
- 真因：`--kv-lease-growth` 深超池 **bounded completion**——租约窗口 ~4,096 扩充阶梯（4096→128→64）全败 → 静默结算 → OutputLimit；**与 tb 无关**（tb none/32k/16k/8k 墙位不变）、**与 prompt 规模无关**（16K-87K 同墙位）；35-42s/轮
- 判别：output-limit 集中 3,900-4,400 带；DSH 实发 max_tokens=**65,536**（证伪"2048 点估计"）
- 官方口径：README:218"超池要保住输出 → 不要开 growth"；Bug 账本"第二处预留不变量未覆盖"
- **双环境行为差异真因（同题定案）**：NInfer 侧有租约砍输出；纯 KVMem（llama.cpp）**无租约机制** → "慢但行为正常"；同夜对照日志连续 2,700+ token 未断 ⇒ 差异 100% 在服务端
- 修法：去 growth（零编译一行）→ A 臂实测零撞墙（§三·十六）；压 DSH maxTokens 为第二臂保险
- 官方同款：B35 立案（2e38810）

### 4.4 页漂移（长会话掉速）定案
- 触发 = **会话轮数**非池深：cache replay 逐轮把最早页挤出设备池 → 34 轮 ~330 页滞留 host → 每 token host 往返 → 3 tok/s
- 检验：decode 期 `mask hidden` 页数（不回组 ≤17 / 回组 329-334）；诊断配 `NINFER_DEMOTE_PROFILE=1`
- 根治 = 异步页流水 v2（ledger42 三步）；补充 = restore 批量化（128 次串行→1 次并行）
- 官方同款：B34 立案；tancau 施工书：host-backed anchor（capture 按引用 host 页，**未做，唯一真解方向**）；`depth = pool − working_set`"把池调大只是挪悬崖"

### 4.5 死亡谷（多轮深堆积 demote 风暴）
- 形态：decode 1-6 tok/s + host 200-318%，**可自愈爬出**；主因 = demote copy 慢（avg 11.5 / max 33.68 ms，PCIe 竞争）+ 需求暴增
- **入谷回归定案（10-12 08:40）**：v2.1 的 `NINFER_ASYNC_DEMOTE_DEPTH>=2`——批异步提交后页"在飞未发布"→ 空闲裁决看到更少空闲 → demote 自我放大；**修复 = 默认回 1**（保留旋钮 1..8）
- 验证矩阵：E1(depth2/55K)✗ 34-153 / E3(depth2+关打分)✗ 76.8（**与打分无关**）/ E2(depth1/41K)✓ 1.5k+79.6 / V1(G2/41K) decode 131.7 / **V2(G2/54.8K) decode 311.7**；**E4 多轮 41K→288 / 83K→143.7 / 125K→111.6 全通过、零崩溃**
- 附带收益：挂账 45 证伪 ⇒ **增量重编可信**（修复重编 ~40 秒）；新纪律：拷源码进树必须确认 mtime 已更新
- 解法排序：depth>=2 正式修法（在飞页计入空闲裁决）→ 早期页 pin（根本）→ 步级预算 → 异步 restore → 压缩平衡

### 4.6 超池崩溃（挂账 47，已修）
- 0xC0000409 静默 abort；根因链 = commit_activation 快照断言（环模式 residency 移动靶）→ 中止路径 stale reservation → catch(...){terminate()}
- 修复 = 带原因终止（5 处）+ 失效回滚跳过；**修复后超池请求仍失败（HTTP 500）但引擎不再崩**；头文件级彻底修法（reconcile 化/恒 defer）待裁决
- 崩溃取证标准流程：WER 取异常码/P9 → CrashDumps 取转储 → 同批 .obj 重链接 /MAP（先验 .text 逐字节一致）→ unwind.py 真调用链 → find_throw_string.py 定不变式原文

### 4.7 DSH 侧关键事实
- Tauri 载体；`DEFAULT_MAX_TOKENS=32768`；watchdog 只由事件产出重装（300s，可配 `streamIdleTimeoutMs`）；length → "已达到输出 token 上限"+"继续"；`isRecoverableLength` 自识"provider 侧截断"
- 活配置 cordis.patch.yml（快照）：maxTokens 24,000 / contextWindow 229,376 / streamIdleTimeoutMs 3600000 / reasoningEffort medium
- 自动压缩：`(prompt + headroom 65,536 + maxTokens 24,000) > 0.8 × ctx` 触发；压缩后首轮掉速（sequence 前缀失配）→ 重启引擎恢复（v2.1+ 效果待验证）；ctx 调小可把压缩触发压在漂移临界之前
- thinking 预算字段三种拼写（`thinking_token_budget/thinking_budget/thinking_budget_tokens`）默认不发；本线引擎（S3 起）支持 per-request `thinking_budget` 优先

### 4.8 池标定史
40,960（10-09 定稿）→ 55,296（10-11 标定 ✅，后被取代）→ **51,200 定稿**（49,152 最稳）；64K 实测成功（需 `--cuda-graph-allowance-mib 64/128` + 桌面 ≤~1.0 GiB 净 GPU）；WDDM 显存归还不即时（滴流 ~36 MiB/30s）

### 4.9 模型加工链（一条进化链）
```
原件 MTP.ninfer（13.27 GB，ModelScope Merkyor 系，组件 text+mtp，MTP 头 q4_0）
  └─ recode_mtp.py 自转 MTP 头（q4_0 → iq4_nl，239 MB；P1 历史：先做 q8_0 无损探针 +202.5MiB 装不上 → iq4_nl Δ0 定稿）
       → mtp-iq4nl.ninfer（13.27 GB，文本主力）
            └─ graft_vision.py 逐字节嫁接视觉塔（333 对象，282.0 MiB，q4/q5/q8/bf16 混合）
                 → mtp-iq4nl.vision.ninfer（13.57 GiB，视觉主力；比官方 q8mtp 版小 202.5 MiB）
```
- 引擎格式白名单 26 项（无 q4_0，无 gguf_bf16）；拼写陷阱：`bf16`（无前缀）/`gguf_q8_0`/`gguf_iq4_nl`/`gguf_q4_k`
- roadA（引擎补 q4_0）= ~14 处小改 + 1 新 .cu（复刻 IQ1_M 的 dequant→BF16→cuBLAS 通路，不用写 GEMM）；roadB（数据侧重打包）已实际采用
- DFlash2：Coder390 几何完全匹配（64 层/5120/248320/262144），但草稿头吃 target 残差，**必须同源训练**（B18 实测反例 22%/47% vs 91.5-100%）⇒ 未投入
- ngram：`--ngram-draft-tokens` 默认随 `--spec` 开 15；`--lookup-ngram` 只挂 MTP 分支；对高接受率 MTP 仅 +3%~13%（非翻倍）

### 4.10 验证与运维工具
- 探针：`test_ab_arm1.py`（健康/速度）、`probe_recall*.py`（召回埋针）、`test_multiturn_overflow.py`（多轮超池）、`test_stream_stall*.py`（stream 挂起）、`test_ledger39_vision.py`、`bench_spec.py`
- 长程基础设施（tools/，gitignored）：`engine_ctl.ps1`（start/stop/status/waitready + 显存闸门 + 规范化进程名）、`valley_bench.py`（确定性死亡谷负载）、`engine/lineage` 版本仓（一版一 exe + MANIFEST，永不覆盖）
- 起服纪律：可见窗口；先告知用户；就绪判据 = 新日志 `listening on http`（端口 LISTEN≠就绪）；日志先 Copy-Item 快照再读（tee 独占）
- 部署：`deploy_engine.ps1`（备份+停引擎+部署+台账）；回退锚 = .bak + lineage

---

## 五、挂账总表（§四，截至 10-12；关键项）

| # | 事项 | 状态 |
|---|---|---|
| 38 | A/B 去 growth | ✅ 销账（零撞墙） |
| 39 | 非 growth×视觉 scatter | ✅ 销案（不复现） |
| 40 | 56K 池+召回实测 | 🔄 大半完成；**51,200 定稿** |
| 41 | stream 挂起 | 🔀 并入 42（send 阻塞证伪；取消检查点前移已施工） |
| 42 | 页漂移 | ✅ v2 全链部署（20-40 倍）+ v2.1 depth 修复；后续：depth>=2 正式修法/早期页 pin |
| 43 | 死锁看门狗 | 📋 立项（无取消信号死锁：步级看门狗） |
| 44 | demote profile | ✅ 定案（copy 排错队=compute stream 同步 D2H） |
| 45 | 依赖追踪缺失 | ✅ **证伪**（ninja 依赖记录完好，增量可信）；新纪律：拷贝源码须确认 mtime |
| 46 | 死亡谷 | ✅ 入谷回归 = depth>=2 已修 + E4 验证；多批 in-flight 正式修法待做 |
| 47 | 67K 超池崩溃 | ✅ 根因修复（增量编译）；头文件级遗留待裁决 |
| 19/29 | ngram | ✅ 净贡献≈0，保持默认 |
| 35 | 视觉塔嫁接 | ✅ 全链闭环 |
| 37 | DSH 止血 | 🔄 改判（对撞墙无效；留待思考墙场景） |
| — | 复现缺口 | 📋 3 个本地提交（5b07bc1/a25012b/3b9dc83）未整理进 patches/（README 自述待办） |
| — | README 同步 | 📋 v2/v2.1/G2/挂账47/E4 尚未全量写入 README 问题档案（见 §七观察 1） |

---

## 六、文档索引（全仓；✅=已逐字/深读）

| 文档 | 规模 | 一句话 |
|---|---|---|
| `README.md`（根目录） | 301 行 | ✅ **权威总纲**（三仓表/全部战役/压榨参数/成绩单/定稿/复现指南/问题档案 13 项/已知限制/致谢） |
| `docs/ninfer-kvmem-项目构建史.md` | 1728 行 | ✅ **主叙事**（v1-v32 全过程，每决策带证据链） |
| `docs/讨论-DSH撞墙现象与双环境行为差异-CodeBuddy-20261010.md` | 363 行 | ✅ 撞墙讨论一手（源码取证/DSH asar/双环境差异收窄） |
| `docs/审核-两文档对照排查与撞墙机制定案-TeleAgent-20261010.md` | 218 行 | ✅ **撞墙定案**（growth bounded completion；墙位 4,037-4,071） |
| `docs/长程-20261012-死亡谷定位与v2.1验证.md` | 170 行 | ✅ 死亡谷闭环（入谷回归=depth>=2；E4 多轮全过） |
| `docs/状态归档-20261012凌晨-v2.1与崩溃待续.md` | 75 行 | ✅ 凌晨归档（v2.1+restore 批量化；崩溃现场；协作规则四条） |
| `docs/根因-67K超池崩溃-…-CodeBuddy-20261012.md` | 91 行 | ✅ 挂账 47 根因链+修复+取证工具 6 件 |
| `docs/技术解析-异步页流水-v2-20261011.md` | 230 行 | ✅ v2 机制（数据层/搬运层双架构；正确性契约；常见误解澄清） |
| `docs/上游谱系与跟踪纪律-20261011.md` | 97 行 | ✅ 谱系树+决策表+FORK 策略（cherry-pick 评审制） |
| `docs/教程-KVMem与短测-给agent与使用者.md` | 294 行 | ✅ 使用教程（15 分钟五件事/判活规矩/缺点清单/三条误判） |
| `docs/调研-对比研究-tancau-ninfer-kvmem-ring-CodeBuddy-20261010.md` | 315 行 | ✅ 环线对比（8 锁/自噬循环/W1-W5 逐字对照/过度思考对策/施工单） |
| `docs/调研-目标实现路径-Coder390接入NInfer-KVMem-20261009.md` | 294 行 | ✅ TELE 首轮调研（MTP 三路 A/B/C；等长重写算术；DFlash2 硬门） |
| `docs/调研-项目目标实现路径-CodeBuddy-20261009.md` | 324 行 | ✅ CB 首轮调研（q8_0 无损探针论证/ArtifactWriter 全量重排/KVMem 环境变量族） |
| `docs/_research/codebuddy-mtp-roadA-引擎侧补q4_0.md` | 373 行 | ✅ 路 A 可行性（14 处最小改动清单 + IQ1_M 先例通路） |
| `docs/_research/codebuddy-mtp-roadB-数据侧重打包.md` | 483 行 | ✅ 路 B 可行性（容器格式全解析/同构格式/JSON 长度陷阱/writer 用法） |
| `docs/_research/codebuddy-dflash2-ngram-部署适配.md` | 1161 行 | ✅ DFlash2 注入条件全表 + ngram 双开关差异 + 启动器适配清单 |
| `docs/设计-挂账42第三步-v2异步demote-20261011.md` | 136 行 | ✅ v2 设计（PendingDemote/时序/7 锚点/TELE 三缺口答复） |
| `docs/设计-挂账46-v2.1多批in-flight-20261011.md` | 121 行 | ✅ v2.1 设计（N 槽环形/非阻塞收割/保守起步 N=2） |
| `docs/施工-挂账42与41-页漂移与host路径-设计-20261011.md` | 127 行 | ✅ 挂账 42/41 施工设计（M1-M5 修法/病灶 file:line/验收判据） |
| 审核×11 + 交叉审核×2 + 交接 + 协作 + 施工方案 + 晨报 + ngram_audit + 规则-跨仓边界（19 份） | — | ✅ 子代理深读 → **`docs/通读摘要-审核与流程批-CodeBuddy-20261012.md`** |
| `refs/`（tancau-ninfer-kvmem-ring 参考树 + _tools） | — | ⚪ 未逐字读（第三方参考材料，非本线产物） |

**代码与补丁/脚本**：
| 路径 | 一句话 |
|---|---|
| `patches/W1-W4_engine_fix.patch` | 思考熔断四修（`==`→`>=` / 删越界 throw / control 防御闭合 / progress 去门控） |
| `patches/ledger42_cancel_checkpoint.patch` + `ledger42_batch_demote.patch` + `ledger42_v2_async_demote.patch`（623 行） | 异步页流水 v2 三步 |
| `patches/ledger44_demote_profile.patch` | demote 四段 profile（默认零开销） |
| `patches/ledger46_v2.1_multibatch.patch` | v2.1 多批 in-flight（N 槽环形） |
| `patches/ledger47_overpool_abort_silent_death.patch` | 超池崩溃修复（81+/21-） |
| `engine-src/`（不入库） | 本仓自持引擎树（家里机器；分支 line-coder390；PROVENANCE.md 归属） |
| `build/s6_1208a.bat` + 11 脚本 | 本仓全量构建（VSLANG 注释已更正） |
| `build/patches/0001-0003` | 上游基线补丁（MSVC C2326/C3495/C2026 + Design C + STANDALONE） |
| `scripts/recode_mtp.py` / `graft_vision.py` | MTP 头自转 / 视觉塔嫁接 |
| `scripts/test_*.py` / `probe_recall*.py` | 各类探针（详见 §4.10） |
| `serve_tee.py` / `deploy_engine.ps1` / `ninfer_launcher.py`（+profiles.json） | 起服工具 / 部署 / GUI 启动器 |
| `start-*.bat` ×11 | 定稿档（含 `start-v21-restorefix-nograph.bat`、`start-v1c2-vision64k-graph64.bat` 等） |

---

## 七、阅读完成度与收尾观察

**完成度**：构建史 + README 权威文档全读；docs/ 核心 19 份深读（时间线/撞墙/死亡谷/根因/技术解析/谱系/教程/调研×3/_research×3/设计×3/施工设计）；19 份流程类文档子代理深读并落盘摘要；全仓文件清单/补丁/脚本/构建脚本清点。未逐字读：`refs/` 第三方参考树（非本线产物）、各 `.py` 脚本逐行（已过接口与用途）、`images/`（1 张截图）。

**收尾观察（文档同步缺口，供后续会话注意）**：
1. **README 与最新进展的同步缺口**：README 靠顶横幅同步到 v2 首战（10-11 21:18），但"已解决问题档案"#12/#13 仍写"挂账 42/41 待修"，且未含 10-12 的：G2 死亡谷修复（depth 回 1）、E4 验证、挂账 47、解耦、改名。**后续更新 README 时优先补这几项**。
2. **预设数**：README"快速开始"写"8 个预设"；launcher 实际已有更多（10+，含 `★64K视觉稳（v2.1实测·nograph）`——构建史注明 GUI 需重启才可见新档）。
3. **复现缺口的自述**：README 自述 3 个本地提交（5b07bc1/a25012b/3b9dc83）未整理进 `patches/`——若做对外复现整理，这是第一优先。
4. **挂账 45 双重口径**：证伪后"增量编译可信"，但历史文档（设计-挂账46、v2.1 施工纪律）仍写"必须全量重编"——**按时间序理解，最新口径为准**（增量可信 + mtime 纪律）。
5. **`NINFER_KV_WINDOW` 口径**：README 快速开始用 32768（文首口径），launcher 历史 KV_ENV 为 16384——以 launcher/实机脚本现值为准。
6. **本文件与摘要文件均为本次通读产物**（未提交）：`docs/全库通读索引与时间线-CodeBuddy-20261012.md`（本文件）+ `docs/通读摘要-审核与流程批-CodeBuddy-20261012.md`。

---

## 八、回家行动清单（通读 + 上游登记产出，按优先级）

> 全部为"家里硬件条件恢复后"的动作；与 `docs/上游谱系与跟踪纪律-20261011.md` §6.6 互为姊妹清单（那边管"上游跟踪"，本单管"回家动手"）。

1. **cache% 轮型自查**（~10 分钟，零成本）——受 issue #101 启发：
   - 用 DSH 长会话日志 `req# done` 行的 cache% 字段，按"轮型"分组（尾改型 vs 追加型——DSH 若有每轮变化的尾部消息）；
   - 判据：是否出现"特定轮型骤降"（某类轮 cache 掉到 0/低值）；本线实测命中 97-100%，**预计正常**——以数据排除；
   - 若异常：对照 #101 的 trace 判据（`no_recurrent_checkpoint` 类错位）与我们 sequence replay 机制深挖。
2. **ngram 31 试点**（一次 A/B，低成本）——RC3 默认 ngram 31/min-match 12（单并发允许 >15，本线现 15）；
   - 同语料 A/B，**含代码型 agent 负载**（我们此前 ngram≈0 的结论来自故事型语料，真实 agent 负载下复测）。
3. **约束解码现状查证**（~30 分钟，纯查证）——查 `engine-src` 是否有 constrained decoding / grammar 支持（对照 Neroued 10-07 的 choice/regex 与 RC3 工具调用约束）；
   - 若有：评估开启方式（对口 DSH 工具调用质量）；若无：评估移植成本（中期项，结合 #113）。
4. **RC3 参数对照复核**（~30 分钟）——context 200k / budget 36k / 输出 16k / thinking 8192 / prefill chunk 256 / ngram 31 vs 本线（51,200 池 / tb 16,000 / chunk 512 / ngram 15）——逐项记录差异与理由，**不改动**。
5. **（可选）#101 式回归探针**——若第 1 项发现异常，仿制 `prefix-reuse-regression.py` 的三轮回放 + trace 判据，设计本线版。
6. **⭐ 视觉 residency（overlay）实测**（2026-10-12 网络调研完成 → `docs/_research/网络调研-视觉塔与MTP显存动态调换-先例与原理-20261012.md`）：
   - **调研结论**："多模态时 MTP 让位、视觉上显存"**已被完整实现过**（NInfer 生态 on-demand vision residency：设计 issue #74 / 实现 PR #72 / 24G 版 Don-Chad#21 / **已并入 ashalliants#8 → 本线血统**）；机制 = 视觉塔驻 pinned host、按图开窗**借设备内存**（优先零拷贝借空闲 KV 页、可与 decode 并行；不足按秩驱逐 **MTP head → draft head → embedding → lm_head**，毫秒级、CUDA graph 不失效、输出逐位一致）；上游未合（判定"不值得"）、**Windows/sm_120 未测**；
   - **第一步 = 实测现成旗标（非自研）**——launcher 已有 overlay 档；六条验收（详见调研报告 §5.4）：
     a) **旗标可用性**：`--vision-residency overlay` 起服（不支持时在加载期**显式报错拒绝**——确认本构建含 overlay 路径 + iq4nlvis 是否有"可驱逐尾部"layout）；
     b) **窗口行为与借用账**：单图编码时间（目标：从 15-20s 压到秒级；先例窗口 0.4-0.5s/图）、设备占用、文本 lane gap（预期 p99 ~340ms）；
     c) **组合兼容**：× MTP / ngram / KVMem 六开关 / hemostat；**特别试 dflash2**（未验证项）；
     d) **容量结算**：overlay 应"恢复无 vision 容量"（先例 +20% 级）+ free 增量（+260MiB 级）——把池往 55,296 顶一顶找新平衡；
     e) **Windows 稳定性**：连续多图/长会话（pinned 内存增长、crash 迹象）；
     f) **回退预置**：保留 `--vision-cpu` / 无视觉预设（现状即保底）。
   - 失败路径：若缺 overlay commit → 对照 ashalliants#8 / mgscreativa `5a331eb` 评估移植（Windows 未测=风险）；仍不行 → 静态换位实验（GPU 常驻 vision + 缩池的账）。

---

> 维护：本文件由 CodeBuddy 在 2026-10-12 全库通读中完成；后续若引用，注意区分"文档记录时的口径"与"最新实机口径"（以构建史最新章节 + README 顶横幅为准）。
