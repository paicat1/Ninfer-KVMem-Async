# 施工书：C 步 restore extent 合并（2026-11-17 深夜 · 用户批准直接施工）

> 立项：§239 判决（用户 2026-11-17「全部同意」）+ §240 判决（判据③✅维持 C 步依据）。
> 用户令：「我不想用了，我成试验机器了。能不能直接C？」→ 直接施工，1/2 降级为后台零机时活。
> 授权链：用户对机器调度全面授权（「你该怎么用机器就用，我不用」）。

## 一、病灶与证据

- 小追加（cache≈100%、新 token 几百）TTFT 7-24s：restore 逐页串行提交，`copy_from_host` 每次调用一页，pageable bounce buffer 每次调用固定开销 ~8-13ms（§239 双臂线性闭环）。
- 冷填充（§240）：85,191 页 restore 对 2,123 页 prompt（40 倍轮转），逐页调用放大 40 倍。
- 源码自认：`context.cpp` 原 L1628-1635 注释（挂账46第四步，2026-10-12）——已上 transfer stream + 单次批等待，但**每页仍是一次独立 H2D 调用**。

## 二、修法（一行话）

把"每页一次 `copy_from_host`"合并成"每个 extent 连续段一次"：同 extent 内 offset 连续的 wanted 页并成一个 run，一次 staged H2D 拷贝整段（`copy_from_host` 本就支持 scatter 到任意 device 槽位，且内部自动按物理连续性分 run），每页的 reserve/publish/retain/block-table 流水线逐页保持不变。

## 三、三禁忌对表

| 禁忌（§239 立） | 对表 |
|---|---|
| 取消页边界安全 | `decode_cancelled()` 检查保留在 run 边界（pass B 顶部+扩展步内）；部分恢复语义安全不变 |
| 未搬回页不进 mask | 页只在拷贝**提交后**进 `resident`；失败/池满即留在 mask 外（"silently unreadable" 契约不变） |
| event 句柄不跨请求 | 唯一同步 = 原有的单次批等待（transfer_streams sync），未新增任何 event |

## 四、改动面（2 文件，纯追加+局部重写）

1. `kv_store.h`（+51 行）：新增 `restore_pages_from_host(handle, pages_in_run, source, stream)` —— 批量版 restore：逐页 reserve（异常时 unwind 已 reserve 页，不留 pinned），**一次** `copy_from_host`，逐页 publish/retain/block-table。单页 run 与原 `restore_page_from_host` 流水线完全一致。
2. `context.cpp`（restore_kv_pages_from_host 循环重写，+103/-30）：Pass A 按 extent 分桶（device_resident 页照旧直接进 resident）；Pass B 保持 best-first 走序，每个未处理页 seed 一个"本 extent 内 offset 连续"的 run（cap 128 页，按 `available_pages()` 钳制），一次调用恢复整段。
- 优先级语义：run 粒度的 best-first 不变；run 只拉自己的 extent 邻居（与 D-5 seam-neighbor"以广度换完备性"政策同向）。
- 池满语义：`free_runs().empty()` 破循环保留（与旧循环一致）；run 长 ≤ available_pages() 钳制，方法内异常 unwind 兜底。

## 五、验收判据（预注册，可证伪）

- L0 编译：全量 BUILD-EXIT=0 + gates_arch_product（全 sm_120a / 0 sm_86 / 0 PTX）+ deploy_dlls。
- L1 行为（换件后真实会话）：
  1. **追加税塌缩**：小追加（cache≈100%）TTFT 从 7-24s → **≤5s**（864 页×8-13ms≈7-11s 的税应基本消失；剩余为计算量本身）；
  2. **restore 事件数锐减**：同规模 wanted 集的事件数从 ~N 页 → ~N/run 均长（日志 `ring retrieve` 行数对比）；
  3. **召回不回退**：`kvmem_score KEPT`/`SELECT` 正常，长上下文回答无"中段丢失"类劣化（超池警告行的既有语义不变）；
  4. 池满/取消路径无崩溃（老 break 语义保留）。
- 证伪线：追加 TTFT 不降或事件数不降 → run 合并率不足（extent 碎片化），下一步在 demote 批量大化或 arena 连续分配上找油水。

## 六、回滚

- 备份：`_safety_backups\context_20261117_pre_cstep.cpp` + `kv_store_20261117_pre_cstep.h`（补丁前原件字节级）。
- 换件：`engine_ctl start -Exe <新件>` 自动归档旧现役件（lineage sha 去重），旧件随时可回。
- 新件 sha：待编译产物实测后记入 §241。

## 七、顺带样本（不另花机时）

换件重启后的首次填充 = 179 捕获判别实验的又一个样本（新实例/短间隔重启）。判据同 §240。

## 八、首次换件失败事故（2026-11-17 22:11，已归因，T#0086）

**症状**：新件（sha16 C986830004536B65，报 `7e14453-4-g2336ba3-dirty`）起服炸
`prefill_chunk must be a nonzero multiple of 128`；旧件（2755b24-dirty）用**一模一样的 CMD+ENV**（logs\test_a4-revert1.log vs test_cstep1.log 逐字段相同，含 `--prefill-chunk 512` + `--prefill-chunk 1024` 双旗）20:17 成功起服。

**归因（证据链）**：
1. serve 层校验（serve_options.cpp:1152）先过才会到引擎层校验（startup.cpp:1025），512/1024 都是 128 倍数 ⇒ 解析层值合法；
2. `startup.cpp.obj` 磁盘 mtime = **2026-11-03 23:22**（serve/model/context 的 obj 全是 11-17 21:3x）——本次增量构建**没有重编它**；其源 mtime 11-03 22:52 未变，ninja 只按 .cpp mtime 判新；
3. 今晚 HEAD 新提交 c5f48a8 往 `include/ninfer/types.h` 的 `EngineOptions` **中间插入** `wddm_budget_arithmetic_only`（L400），`prefill_chunk`（L405）声明在其后 ⇒ 布局偏移被推移；
4. 11-03 编译的 startup.obj 按旧偏移读新布局 struct ⇒ 读到错位垃圾 ⇒ `% 128 != 0` 必炸；旧 exe 全对象同 ABI 时代故自洽。
5. 版本串 `-4-g2336ba3`（构建期 GenerateBuildId.cmake 也没重跑）与 build-1208a 上次全量构建时代一致，旁证混链；旧 exe 版本串 `-6-g2755b24` 来自**另一棵编译树 build-1208b**。

**处置**：`build-1208a` 整树改名归档 `build-1208a_staleABI_20261117`（不删除），全新 configure + 全量重建（唯一正解——所有含 EngineOptions 布局、11-17 前编译的 TU 都可能陈旧 ABI，逐个挑不可靠）。陷阱记 T#0086：**改任何头文件必须 ninja -t clean 或全新 configure 全量重建，禁止增量编译混链出 exe**——这正是 s6_1208a.bat 头注释里挂着的"头文件消费者是否重排未验证"纪律，今晚证伪：不会重排。
