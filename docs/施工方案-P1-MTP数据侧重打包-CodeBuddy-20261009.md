# 施工方案 · P1：MTP 数据侧重打包（q4_0 → q8_0 严格无损）

> **署名**：CodeBuddy｜**日期**：2026-10-09｜**工作区**：`J:\ninfer-kvmem`
> **状态**：**待用户批准**（未执行、未改任何文件、未 commit）
> **上游依据**：`docs\调研-项目目标实现路径-CodeBuddy-20261009.md`（含二轮修订）、`docs\交叉审核-CodeBuddy审TELE调研报告-20261009.md`、TeleAgent 两份报告
> **适用范围**：只解决 **MTP 投机**（G1）。DFlash2 / ngram / KVMem / 部署适配不在本方案内（见 §9）。

---

## §0 交叉审核第二轮：对 TELE 复核的复核（先裁定，再施工）

TELE 对我的 9 条给出 7 ✅ / 2 ⚠️ / 1 ❌。我逐条独立复核后裁定如下：

| # | TELE 的裁定 | 我的复核结果 |
|---|---|---|
| **#8** `strip_components.py` 不存在 | **我认错，已撤回**。实测存在于 `official-repo\ninfer-fusion-kvmem\tools\strip_components.py`（8.13 KB）。根因 = 我的检索只覆盖 `src-tree` 子树。TELE 的假阴性归因（`.gitignore` 排除目录 glob 不进入）**成立**。已写入纪律：`official-repo/ refs/ models/ engine/` 内检索一律用 PowerShell。 |
| **#5** 对齐证据归属 | **接受纠正**。执行点是 `src/artifact/layouts.cpp:12`（`object.offset % geometry.alignment`），`weight_view.h:39` 只是默认值定义。已改。 |
| **#6** KVMem "唯一真值"不精确 | **接受，并再收紧一层**。我复核发现比 TELE 更精确的定性：`serve_options.cpp:1118-1122` 的 **B30 修复（2026-10-07）** 说明该 gate **曾读 `NINFER_KV_RING`、现已改为读 `NINFER_KV_WINDOW`**，且引擎自己的提示曾"命名了错误的变量"。⇒ `NINFER_KV_RING` 不是"空转"，是**被废弃的旧名**。另新增一条双方都未记的：**启动器已固定注入 5 个 KV 环境变量**（`ninfer_launcher.py:54-60`），KVMem 无需我方配置，但必须判活（`kvmem_score: SELECT`）。 |
| **#4** 探针选 `q8_0` | TELE 认同，并建议**保留 `q4_k` 作交叉验证**（若与 q8_0 接受率接近 ⇒ 转换损失可忽略；若明显更低 ⇒ 损失致命）。**采纳**，见 §3.2 的三档设计。 |
| 新发现 `auxiliary/000000` | **证实并采纳**：`inspect --objects` 实测 `13272524288  24576  tensor  int32/contiguous_le_v1 [6144]  auxiliary/000000`（6144 = 24 heads × 256 head_dim）。它**是 800 tensor 之一、不是 resource，重打包必须保留**。已写入我的报告 §2.3。 |
| 其余 1/2/3/7/9 | 双方一致，无需再论。 |

**结论：双方无方案级冲突，差异已全部收敛。** TELE 判断"无需停止操作报告差异级别分歧"——我同意。

---

## §1 目标与成功判据

**目标**：产出一个 **`--spec mtp` 能装得上** 的 Coder390 容器副本，并拿到 MTP 的**真实读数**（drafted/accepted、tok/s）。

**成功判据（缺一不算完成）**：
1. **L0** 新容器通过 `tools.artifact.inspect --objects --bindings`，且 `formats` 中 `gguf_q4_0: 0`、`gguf_q8_0: 5`，对象总数仍 804、tensor 仍 800。
2. **L1 数值 oracle**：抽样块反解比对，**q4_0 解出的值与 q8_0 解出的值逐位相等（误差 = 0）**。
3. **L2 负控**：故意写错 `bytes` → 必须被 writer 拒绝（证明不是静默通过）。
4. **L3** 引擎 `--spec mtp` 装得上、单条 prompt 冒烟出字。
5. **L4** A/B：裸解码 vs `--spec mtp`，记录 tok/s 与 drafted/accepted。

**明确的失败判据**：若 L3 装在上了但接受率 ≈ 0，也要如实记录——那也是有效结论（说明此路不通），**不得修改读数或换口径掩盖**。

---

## §2 前置检查（施工前逐项打勾）

| # | 检查项 | 命令 | 通过标准 |
|---|---|---|---|
| 1 | Python 可用 | `python --version` | 3.12.x（本机实测） |
| 2 | numpy 可用 | `python -c "import numpy;print(numpy.__version__)"` | 已装（torch/gguf **不需要**） |
| 3 | 官方读写器可 import | `cd …\src-tree\fusion-engine-src` 后 `python -c "from tools.artifact.writer import ArtifactWriter;print('OK')"` | 打印 OK |
| 4 | 磁盘余量 | `Get-PSDrive J` | ≥ 15 GB（实测 **235 GB** ✅） |
| 5 | 原件存在且未被改 | `Get-FileHash` 或文件大小比对 | 13,272,798,720 B |
| 6 | 备份策略 | 见 §8 —— **本方案不覆盖原件，故不强制备份** | 确认 |

---

## §3 方案设计

### 3.1 为什么"整包重写"而不是"原地手术"

| | 原地手术（改 5 段） | **整包重写（本方案）** |
|---|---|---|
| 写入量 | ~238 MB | ~13.5 GB |
| 耗时 | 秒级 | 顺序 IO，分钟级（J 盘 235 GB 余量，无压力） |
| 目标文件 | **原件本身**（唯一副本） | **新文件**，原件零写入 |
| 失败后果 | 原件损坏风险 | 删临时文件重来 |
| 资产保护 | 需先备份 13 GB | `ArtifactWriter` 天然拒绝已存在目标（`FileExistsError`） |

**[EVIDENCE] tools/artifact/writer.py:150-151:for target in self._destinations: if target.exists(): raise FileExistsError(target)**

⇒ **选整包重写**。多花几分钟换"原件绝对不动"，且能同时产出多个候选版本做 A/B。

### 3.2 三档目标格式（采纳 TELE 的交叉验证建议）

| 档 | 格式 | 5 张量新字节 | Δ | 数值 | 实现 | 角色 |
|---|---|---:|---:|---|---|---|
| **A（主）** | **`gguf_q8_0`** | 451,215,360 | **+202.5 MiB** | **严格无损** | 极低（nibble→int8，无浮点量化器） | **探针基准**，读数干净、可归因 |
| B（**降为可选·不推荐**） | `gguf_q4_k` | 238,878,720 | **0** | 有损（4bit→4bit 重量化） | **最高**（256 元素超块、8 子块 6-bit scale/min、分半 nibble 布局） | **除非有明确理由否则不做**（见 §3.2.1：不再用它代理 C） |
| C（定稿候选） | `gguf_iq4_nl` | 238,878,720 | **0** | 有损（但 4.5bpw 下质量优于 q4_0） | 中（16 项查表，块几何与 q4_0 **逐块对应**） | 若 B 与 A 接近 ⇒ 定稿用它 |

**决策规则（写死，避免事后择数）** —— **2026-10-09 修订：取消"B 代理 C"，直接量 C**
- **A 档**先跑，必须过 oracle（误差 = 0），得到**基准接受率** `acc_A`。
- **交叉验证直接用 C（`iq4_nl`）**，得到 `acc_C`。
- 若 **`acc_C ≥ acc_A − 噪声底** ⇒ 判定"4.5bit 转换损失可忽略" ⇒ **定稿用 C**（Δ0）。
- 若 **`acc_C < acc_A − 噪声底`** ⇒ 判定"低比特重存损失致命" ⇒ **定稿用 A（`q8_0`）**。

### 3.2.1 为什么不再用 B（q4_k）代理 C —— TELE 指出的逻辑漏洞，成立

原规则"用 B 的接受率决定 C"**把 B 的转换损失当作 C 的代理**，前提是 **B 实现正确**——而 B 恰恰是**我们自己判定最可能静默失败的那个**（难度最高的量化器）。**若 B 有 bug，`acc_B` 偏低会误杀 C。**

⇒ 修正为**直接量 C**，理由：
1. C（`iq4_nl`）块几何与 q4_0 **完全相同（32 元素/18 字节）、逐块一一对应**，不存在"B 那种超块重组"的错位风险；
2. C 的实现难度**比 B 低一个量级**（16 项查表 vs 子块 scale/min + 分半 nibble）；
3. 既然 B 与 C 同为 4.5 bpw、Δ0，**没有任何理由先做难的再推断容易的**；
4. B 因此**降为可选**：只有当"C 也失败、且怀疑是 iq4_nl 本身在引擎上不被支持"时才考虑。

**关于阈值（TELE 指出 90% 是拍脑袋，须对照噪声底）——采纳**：
- 接受率有 **run-to-run 波动**，固定 90% 会把噪声当信号。
- ⇒ **先测噪声底**：同一配置（建议 A 档）**跑 ≥3 次**，记录接受率的极差 `σ_run`。
- 阈值改为 **`acc_A − max(σ_run, 相对余量)`**，即"差异超出噪声底才算真差异"。具体数值**实测后填，不预先拍定**。

> 为什么不用 `bf16` 做基准：q4_0 的 scale 是 **fp16**，转 bf16（8-bit 尾数）会掉 ~0.4% 精度，**非严格无损**；而 `q8_0` 的 scale 仍是 fp16、整数精确落入 int8 ⇒ **误差严格为 0**，能自证。

### 3.3 脚本设计：`scripts\recode_mtp.py`（**待批准后创建**，转正目录不用 `.temp\`）

> **⛔ 落位更正（2026-10-09，TELE 指出 → 复核成立，且这是会"静默失败"的一处）**：
> 我首轮写"落 `tools\recode_mtp.py`、属②类可入库"——**自相矛盾且会静默失败**：根 `tools/` **已被 `.gitignore` 排除**，且其中正是③类 AI 工作流工具链。
> `[EVIDENCE] .gitignore:31-33:# 工作流工具链（类③，不入项目 git） / smart_push.ps1 / tools/`
> `[EVIDENCE] 实测根 tools\ 内容 = backup_file.py, commit_msg_denylist.txt, daily_append.py, gate_check.ps1, merge_verify.ps1, sda_trap.py, wm_revert_check.py`（全部③类）
> ⇒ 放进 `tools\` 会被 **git 静默忽略、根本提交不进去**，还不报错——与我批评 `q4_k` 的静默失败是同一类。**已改落 `scripts\`**（新目录、②类、未被排除、可入库）。

**骨架照抄 `official-repo\ninfer-fusion-kvmem\tools\strip_components.py`**（它就是官方重打包范例），改造 4 处：

| 原脚本 | 本方案改造 |
|---|---|
| `:25 UPSTREAM = r"E:\infer-build\..."` | 改为本机 `J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src` |
| `--drop dflash2,vision,proposal`（删组件） | **不删任何组件/对象**，全量保留（804 个） |
| `:161 TensorSpec(..., format=obj.format, ...)` | 对 5 个目标对象 **换成 `format=<目标格式>`**，其余原样 |
| `:187 writer.write_object(obj.id, art.iter_object(obj.id))` | 5 个对象写**转码后**字节；其余原样流式搬运 |

**伪代码（核心）**：
```python
TARGET_IDS = {"weight/000079","weight/000080","weight/000789","weight/000796","weight/000798"}
specs = []
for obj in d.objects:                     # 全部 804 个，一个不落
    if isinstance(obj, ResourceObject):
        specs.append(ResourceSpec(id=obj.id, bytes=obj.bytes, encoding=obj.encoding))  # 必须关键字传参
    else:
        fmt = TARGET_FMT if obj.id in TARGET_IDS else obj.format
        specs.append(TensorSpec(id=obj.id, shape=obj.shape, format=fmt,
                                layout=obj.layout, divisors=obj.divisors))
writer = ArtifactWriter(dst, specs, components=d.components, bindings=d.bindings,
                        uses=d.uses, metadata=d.metadata, provenance=provenance_new)
for obj in d.objects:
    if obj.id in TARGET_IDS:
        raw = b"".join(art.iter_range(obj.offset, obj.bytes))   # ← 必须 iter_range，见陷阱①
        writer.write_object(obj.id, transcode(raw, obj.shape))  # 转码
    else:
        writer.write_object(obj.id, art.iter_object(obj.id))    # 原样搬运
directory = writer.finish()
```
异常处理照抄原脚本：`except BaseException: writer.abort(); raise`；写完后 `Artifact(dst)` 重开校验（`:200`）。
`provenance` 追加 `{"mtp_recode": {"from":"gguf_q4_0","to":TARGET_FMT,"by":"recode_mtp.py","when":...,"source_artifact_id":...}}`，**登记"不再是原厂件"**（T-RECORD）。

### 3.4 转码算法：`q4_0 → q8_0`（严格无损，这是本方案的技术核心）

**块结构**：
- q4_0：18 B/块 = `fp16 d` + 16 B（32 个 4-bit nibble）；
  `[EVIDENCE] third_party/ggml-quants/src/ggml-common.h:194-199:#define QK4_0 32 / ggml_half d; uint8_t qs[QK4_0 / 2];`
- q8_0：34 B/块 = `fp16 d` + 32 B（32 个 int8）；
  `[EVIDENCE] tools/artifact/formats.py:101:GGUF_Q8_0 = GgufFormat("gguf_q8_0", 8, 32, 34)`

**无损性证明**：q4_0 的值 = `(nibble − 8) × fp16(d)`，其中 `nibble ∈ [0,15]` ⇒ 整数值 ∈ **[−8, 7]**，**精确落入 int8**；`d` 是 fp16，q8_0 的 `d` 也是 fp16 ⇒ **scale 原样拷贝即无损**。
`[EVIDENCE] third_party/ggml-quants/src/ggml-cuda/dequantize.cuh:53-58:v.x = vui & 0xF; v.y = vui >> 4; v.x = (v.x - 8.0f) * d;`

### 3.4.1 ★ "无损"三前提的实证（TELE 反向质疑 → 已逐条自证，非假设）

| 前提 | 结论 | 证据 |
|---|---|---|
| **① 引擎 `gguf_q8_0` 解码 == 标准 ggml（value = d × int8_q）** | **已证实** | `[EVIDENCE] src/ops/linear/gguf/ggml_bridge.cu:218:y[i] = ggml_cuda_cast<dst_t>(__half2float(b.d) * b.qs[i % QK8_0]);`；块几何 `{32,34}` 见 `:292:case GgmlType::Q8_0: return {32, 34};` ⇒ 与标准 `block_q8_0`（`d`+32×int8）**一致** |
| **② 容器内 `q4_0` == 标准 ggml 布局（(nibble−8)×fp16(d)）** | **已实证**（不是推理） | 见下方实测 |
| **③ 写入时 fp16 `d` 位级拷贝** | **由脚本保证 + 断言** | `out[:, :2] = raw[:, :2]` 且加断言 `assert (out[:,:2] == raw[:,:2]).all()` |

**前提 ② 的实测（用官方 `Artifact.iter_range` 读原始字节，排除我手算 offset 出错的可能）**：

```
blocks 1000
d negative ratio = 0.5310
d abs: min/mean/max = 0.00166321 / 0.00385484 / 0.0100098
first 5 d = 0.00311, -0.00579, 0.00415, 0.00328, 0.00340
per-block max|val| / |d| ratio mean = 8.000   (q4_0 理论期望 ≤8)
```

- **`max|val|/|d|` 恒等于 8.000（1000/1000 块全中）** ⇒ 每块都存在 |n−8| = 8 的元素 ⇒ **块边界（18 B）、nibble 高低位拆分、`(n−8)×d` 公式三项全部正确**。若任一环节错位，比值不可能恒定命中 8。
- **⚠️ 修正我自己的一个隐含假设**：我曾默认 `d > 0`。实测 **53% 的块 `d` 为负**——这是 **llama.cpp `quantize_row_q4_0` 的 `d = -amax/8` 约定**（量化端用负 scale，解码端 `(n−8)×d` 自动还原符号），**属标准行为、不是异常**。
- **对无损性的影响：无**。`q8_0` 值 = `d × (n−8)` 与 `q4_0` 值 = `(n−8) × d` **逐位相等，与 `d` 的符号无关**；且引擎 q8_0 解码（前提①）对 `d` **无符号假设**（直接相乘）。
- 副作用（正向）：`d` 为负**反而印证**数据出自 llama.cpp 生态的标准 q4_0 量化器 ⇒ 前提 ② 更可信。
- 唯一残留不确定性：**引擎 q8_0 的矩阵乘内核（mmq）是否对 `d` 有符号假设**。源码层面未发现（`vecdot`/`mmq` 均为 `sum × d` 直接相乘），但**无法穷尽所有内核** ⇒ 由 L4b（§5）端到端兜底。

**nibble 顺序**：`qs[i]` 的**低 4 位 = 元素 2i，高 4 位 = 元素 2i+1**（同上证据 `v.v` 与 `v.y` 的对应关系）。

**numpy 实现要点**（纯位操作，无浮点、无量化器）：
```python
raw = np.frombuffer(data, np.uint8).reshape(-1, 18)
d   = raw[:, :2].copy()                                    # fp16 scale 原样拷贝
nib = raw[:, 2:]                                           # (n,16)
lo  = ((nib & 0x0F).astype(np.int16) - 8).astype(np.int8)  # 偶数索引
hi  = ((nib >>  4).astype(np.int16) - 8).astype(np.int8)   # 奇数索引
q   = np.empty((raw.shape[0], 32), np.int8)
q[:, 0::2] = lo
q[:, 1::2] = hi
out = np.empty((raw.shape[0], 34), np.uint8)
out[:, :2] = d
out[:, 2:] = q.view(np.uint8)
```
> ⚠️ **必须经 int16 中转**：`uint8` 直接减 8 会下溢（`0-8` → 248）。这是最容易写错的一行。

**各对象新字节数**（`elems × 34/32`，供 L0 断言）：

| id | shape | 元素数 | 原 bytes | 新 bytes |
|---|---|---:|---:|---:|
| 000079 | [14336,5120] | 73,400,320 | 41,287,680 | 77,987,840 |
| 000080 | [34816,5120] | 178,257,920 | 100,270,080 | 189,399,040 |
| 000789 | [5120,10240] | 52,428,800 | 29,491,200 | 55,705,600 |
| 000796 | [5120,6144] | 31,457,280 | 17,694,720 | 33,423,360 |
| 000798 | [5120,17408] | 89,128,960 | 50,135,040 | 94,699,520 |
| **合计** | | **424,673,280** | **238,878,720** | **451,215,360** |

⇒ 新 payload = 13,272,548,864 + 212,336,640 = **13,484,885,504**；新文件 ≈ **13,485,135,360 B（12.56 GiB）**。
（⚠️ 2026-10-09 三度修订：括号里原写"payload 起点不变…仍 249,856"是**旧推断、已作废**——TELE 复核指出此处与 §5 L0 的新口径矛盾，成立。
**上述数字仅为磁盘占用预估**；实际 payload 起点由 writer **重新序列化 JSON** 决定（`writer.py:80,84`），且本方案还要往 `provenance` 追加登记项 ⇒ JSON 必变长 ⇒ **起点与总大小均不作断言**，以 §5 L0 为准。）

### 3.5 ★ 五个必须遵守的实现陷阱

1. **读源容器时，q4_0 对象必须用 `art.iter_range(offset, bytes)`，不能用 `iter_object()` / `.object()`** —— Python reader 会 `validate_encoding`，而 `gguf_q4_0` 不在 Python 格式注册表里，直接抛错。
   `[EVIDENCE] tools/artifact/reader.py:165-167:if object_id not in self._validated: validate_encoding(obj);`
2. **`ResourceSpec` 必须关键字传参**（位置传参会把 encoding 喂进 bytes，上游会报 "expected integer"）。
   `[EVIDENCE] tools/strip_components.py:156-159:ResourceSpec(id=obj.id, bytes=obj.bytes, encoding=obj.encoding)`
3. **不要手算任何 offset / 对齐** —— 全部交给 `plan_objects` 重算；`finish()` 会强制全覆盖校验。
   `[EVIDENCE] tools/artifact/writer.py:255-257:for obj in self.objects: if self._coverage[obj.id].ranges != [(0, obj.bytes)]: raise ArtifactError(f"{obj.id}: output coverage is incomplete")`
4. **`auxiliary/000000` 与 4 个 `resource/text/*` 必须保留**（前者是 tensor 不是 resource，漏了引擎会报 missing parameter）。
5. **dtype 下溢**（见 §3.4 末尾）。

---

## §4 执行步骤（Step 0–9）

| Step | 动作 | 命令 / 要点 | 失败处置 |
|---|---|---|---|
| **0** | 记录原件状态 | `Get-Item models\…MTP.ninfer \| Select Length,LastWriteTime` | 不符即停 |
| **1** | 环境检查（§2 六项） | 见 §2 | 缺 numpy 则 `pip install numpy` |
| **2** | 创建脚本 `scripts\recode_mtp.py`（转正目录） | 按 §3.3/§3.4 | — |
| **3** | **dry-run** | `python scripts\recode_mtp.py --src <原件> --dst <新文件> --target-format gguf_q8_0 --dry-run` | 打印 804 对象 / 新体积 / 5 个目标对象新旧 bytes 对照，人工核对 §3.4 表 |
| **4** | 正式执行（A 档 q8_0） | 去掉 `--dry-run` | `writer.abort()` 自动清理临时文件；原件零写入 |
| **5** | L0 结构校验 | `python -m tools.artifact.inspect <新文件> --json --objects` | 断言 `gguf_q4_0:0`、`gguf_q8_0:5`、objects 804、tensors 800 |
| **6** | L1 数值 oracle | 脚本内置 `--verify N`：抽样 N 块，`(n−8)*d` vs `q*d` 逐位比对 | 误差必须 = 0；非 0 即停，查 §3.5 陷阱①⑤ |
| **7** | L2 负控 | 故意把某对象 `bytes` 写错（或漏写一段）→ 必须报 `output coverage is incomplete` | 若不报错 ⇒ 说明校验没生效，停止并报告 |
| **8** | L3 引擎冒烟 | 用**已关 vision** 的启动配置（P0 已修）起 `--spec mtp`，单条 prompt | 装不上 ⇒ 抄原文报错落盘，按 §6 处置 |
| **9** | L4 A/B 读数 | 同语料、同参数、关思考；记录 tok/s + drafted/accepted | — |

> Step 8/9 需要**起服务**——按纪律，serve 启停归用户双击 BAT，AI 起服需授权 ⇒ **Step 8 起需用户授权或由用户执行**。

---

## §5 验收判据（客观、可复现）

- **L0（2026-10-09 修订：收紧断言口径，只断言"格式决定的量"）**：
  - ✅ **硬断言**：`objects = 804`、`tensors = 800`、`resources = 4`、`formats` 中 **`gguf_q4_0: 0` 且 `gguf_q8_0: 5`**、5 个对象**各自的新 bytes**（§3.4 表逐项）、`components` 仍 `text+mtp`、`bindings 979`、`uses 619`。
  - ❌ **不得硬断言**：各对象 `offset`、payload 起点、文件总大小。
    **理由（TELE 指出，复核成立）**：writer **重新序列化**目录 JSON，输出 `json_bytes` 不保证等于源容器的 249,824：
    `[EVIDENCE] tools/artifact/writer.py:80:encoded = encode_directory(value)` / `:84:reserve = align_up(HEADER.size + len(encoded), PAYLOAD_ALIGNMENT) - HEADER.size`
    **并且我自己还引入了一个必然的变化源**：§3.3 要求往 `provenance` 追加 `mtp_recode` 登记项 ⇒ JSON **一定变长**。故"payload 起点不变"这一旧推断**不成立，已作废**。
- **L1（2026-10-09 修订：抽样 → 全量）**：对 **5 个目标对象全量、逐块**断言：
  ① 原 q4_0 解码值 **==** 新 q8_0 解码值 **逐位相等（误差恒 0）**；
  ② 每个块的 fp16 `d` **两字节逐字节相同**。
  规模：238,878,720 B ÷ 18 = **13,271,040 块**，纯 numpy 位运算**秒级**完成 ⇒ 没有理由抽样，抽样只会留疑。
- **L2**：负控必须被拒。
- **L3**：`--spec mtp` 装得上 + 出字。
- **L4**：`drafted/accepted tokens` 有读数（引擎侧指标见 `apps/cli/main.cpp:245-248`）+ tok/s 与裸解码基线对比。
- **★ L4b（新增，端到端正确性兜底）**：同一 prompt、同参数，**裸解码 vs `--spec mtp` 的输出应「语义等价 + 无系统性劣化」**。
  **⚠️ 措辞收紧（2026-10-09，TELE 指出 → 成立）**：**不得写成"输出分布必须等价 / 逐字相同"**。
  - 理论上投机解码的输出分布与 target 一致；但**实测层面** MTP 开/关会改变**每轮 batch/round 结构与 kernel 规约顺序**，因而**存在微小数值差、偶发换 token**——这是正常现象，不是缺陷。
  - 若判据写成"逐字相同"，会把正常数值抖动**变成假警报**，反而掩盖真正的信号。
  ⇒ **正确判据**：① 语义一致（人工判读 + 若干固定 prompt 集）；② **无系统性劣化**（不是单次抖动，而是跨多条 prompt 的一致退化）；③ 若出现系统性劣化 ⇒ 判定转换有误，禁止进定稿。
  **为什么这条仍是硬判据**：它能抓住 L1/L3 抓不住的"权重数值被曲解"类错误（例如 §3.4.1 末尾"mmq 对负 `d` 是否有符号假设"的残留不确定性）——那类错误的症状**不是崩溃，而是输出质量劣化**。且**零额外成本**（同一次 A/B 顺带做）。
- **纪律**：不接受"看起来正常"。KVMem 要见 `kvmem_score: SELECT`；MTP 要见草稿/接受计数。**合成材料的接受率不可作决策依据。**

---

## §6 风险与处置

### ★ 必须明示的一条（2026-10-09，TELE 新观察 → 复核成立）

**本模型当前没有任何 `gguf_q8_0` 张量**（格式分布实测：`bf16 360｜fp32 96｜int32 1｜gguf_q4_k 67｜gguf_q5_k 2｜gguf_q2_k 2｜gguf_iq3_s 144｜gguf_iq3_xxs 26｜gguf_iq4_xs 76｜gguf_iq2_s 21｜gguf_q4_0 5`，**`gguf_q8_0 = 0`**）。
⇒ **选 `q8_0` 等于在本模型上首次启用引擎的 q8_0 通路**（此前该通路在本模型上从未被走过）。这是 `q8_0` 方案**唯一额外于其他格式的风险点**：格式白名单里有 ≠ 这条路径在本模型/本机 sm_120a 上被验证过。
- 已由 **L1（全量位级 oracle）+ L3（装得上）+ L4b（无系统性劣化）** 三层闭环；
- 若 L3/L4b 出现异常，**优先怀疑"q8_0 通路在本机首次启用"**，而不是先怀疑转码（转码已由 L1 全量自证）。

| 风险 | 征兆 | 处置 |
|---|---|---|
| 转码下溢 / nibble 高低位颠倒 | L1 误差 ≠ 0 | 核 §3.4；先单块手算对照 |
| 容器合法但引擎拒载（`artifact object was not consumed…`） | L0 过、L3 报错 | 对象与绑定全保留，理论不会发生；若发生 ⇒ 抄原文报错，评估路 A |
| 装得上但接受率 ≈ 0 | L4 读数极差 | **如实记录**（有效结论）；再跑 B 档（q4_k）与 C 档排除"是不是 q8_0 本身的问题" |
| MTP 收益为负（每轮更贵） | tok/s 反降 | 记录并结案；这是"试到确认做不到为止"的正常终点 |
| 磁盘/中断 | 写入未完成 | `writer` 用临时文件 + `os.link` 原子发布 ⇒ **目标文件要么不存在要么完整**；直接重跑 |

---

## §7 回滚

- **原件从未被写入**（只 `iter_range` 读）⇒ 回滚 = **删除新文件**。
- 需要恢复时：删 `models\…mtp-q8.ninfer` 即可，原件保持 `13,272,798,720 B` 不变（Step 0 已记录）。
- `writer` 临时文件命名 `.{name}.*.tmp`，异常时 `abort()` 清理；残留可手动删。

---

## §8 资产保护与纪律

- **T-PROTECT-ASSET**：`models\` 内 **不覆盖、不删除、不移动原件**；产物写**新文件名**（建议 `…MTP.mtp-q8.ninfer`）。
- **T-NO-TEMP-WORK**：脚本落 `scripts\recode_mtp.py`（**转正**，不留 `.temp\`）；报告落 `docs\`。
- **T-BACKUP**：因不覆盖原件，不强制备份；若用户要求额外保险，可另存一份副本到 `_safety_backups\`（需 13.3 GB，需用户批准）。
- **T-EVIDENCE**：每一步读数落盘（`docs\`），带命令与原文输出。
- **T-COMMIT-APPROVAL**：**本方案未执行任何 commit/push**；脚本与产物入库与否由用户裁决。

---

## §9 本方案之外（后续，不在本次批准范围）

| 项 | 说明 |
|---|---|
| **P0 部署适配** | `vision:on` 必须关（`ninfer_launcher.py:193` + `:277`），否则 Coder390 启动即抛 `missing component vision` —— **这是 Step 8 的前置，需先完成** |
| **P2 交叉验证** | B 档 `q4_k`（若与 A 接近 ⇒ 定稿用 C 档 `iq4_nl`） |
| **P3 ngram** | MTP 通后 `--ngram-draft-tokens` + `--lookup-ngram` 同口径 A/B |
| **P4 DFlash2** | 先做**零成本**几何核对：本模型 `layer_types` 为 `index%4==3 → full_attention`，参照契约特征层 `[5,19,33,47,61]` 落在本模型是 **5→linear / 19→full / 33→linear / 47→full / 61→linear**，需逐位核对参照模型一致后再谈下载权重 |
| **P5 KVMem 判活** | 启动器已注入 5 个开关，长上下文实测需见 `kvmem_score: SELECT` |
| 兜底 路 A | 仅当本方案不可解时启用（vendored ggml 已有 Q4_0 内核，主要是接线 + clean 重编） |

---

## §10 请你裁决（我不擅自开工）

1. **是否批准执行本方案**（Step 0–7，不含起服；产物写新文件、原件不动）。
2. **是否批准创建 `scripts\recode_mtp.py`**（转正目录，非 `.temp\`）。
3. **Step 8/9 起服**：由你双击 BAT 执行，还是授权我起？（纪律默认归你）
4. **是否同时准备 B 档 `q4_k`**（交叉验证，成本 = 一次 13.3 GB 重写 + 一个较难实现的量化器）；我的建议：**先看 A 档读数再决定**，不必提前投入。
5. 关于 TELE 提出的**一次 commit 收录 7 份文档**：我此前建议"分歧收敛后再提交"。**现在分歧已收敛（见 §0）**，我支持提交；但**本方案的脚本与产物是否入库请单独裁决**（脚本属②项目工具可入，`.ninfer` 产物属输入物料、**不入库**）。

---

**署名**：CodeBuddy ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`
**当前状态**：方案已完成，**未创建脚本、未执行、未改动任何代码/模型、未 commit**。等批准。
