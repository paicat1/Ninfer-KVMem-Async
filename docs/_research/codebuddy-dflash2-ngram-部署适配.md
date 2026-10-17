# CodeBuddy 调研报告 · DFlash2 注入 / ngram 启用条件 / 部署启动器适配现状

> 调研人：CodeBuddy（只读调研，**未修改任何代码**）
> 工作区：`J:\ninfer-kvmem`
> 引擎源码树基准：`official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src\`
> 目标模型：`models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`（13,272,798,720 字节）
> 证据格式：`[EVIDENCE] 相对路径:行号:原文摘录`

---

## 0. 结论速览（先给判断）

| # | 问题 | 结论 |
|---|---|---|
| A1 | `missing component dflash2` 从哪来 | `schema.cpp:91` 抛 `ArtifactError("missing component " + name)`，被 `config.cpp:340` 加前缀 `Qwen3.5 config: ` 后输出；触发点是 `config.cpp:335` 用 `speculative_component()`（=`"dflash2"`，`load_options.h:94-95`）去查目录 |
| A2 | dflash2 要哪些权重/字段 | draft 组件 config 必带 12 个字段 + `dflash_config`（6 项）；权重 13 类/层 + 3 个 selector 张量；**embedding 与 output head 直接复用 target** |
| A3 | 现成权重来源 | 工作区内**没有** `DFlash2-FP8/` 或 NVFP4 草稿件目录（已实测）；官方源是 `z-lab/Qwen3.8-27B-DFlash2`（rev `50307d4c…`）；Bonsai 线用的是 `ProCreations/Ternary-Bonsai-2-27B-DFlash2` |
| A4 | Coder390 注入 dflash2 是否成立 | **几何完全匹配**（64 层 / 5120 / 248320 / 262144 四项全对得上），**但必须有同源训练的草稿头**；否则"能跑、接受率低"，有实测反例（22%/47% vs 91.5–100%） |
| B5 | 两个 ngram 开关 | `--ngram-draft-tokens` = 引擎级 copy 提议器（`decode.cpp:232`），**要求 `--spec`**；`--lookup-ngram` = `lookup_draft()`，**只挂在 MTP 分支**（`prefill.cpp:997/1013`），配 dflash2 是死代码 |
| B6 | ngram 审计结论 | 可行；ngram 是引擎侧特征不需改权重；但对已高接受率的 MTP 只有 +3%~13%，"翻番"是 MTP 本身的贡献 |
| C7 | 启动器写死项 | 模型名 4 处、引擎路径 3 处、端口 3 个、`--model-id qwen3.8-27b` 5 处、`--vision` 2 处 —— 全部指向 Bonsai，需改 Coder390 |
| C8 | KVMem 开关 | 本线**纯环境变量驱动**（`NINFER_KV_WINDOW` / `NINFER_KV_RETRIEVE` / `NINFER_HOST_PAGEABLE` / `NINFER_KV_REUSE_HOSTBACKED`）；`NINFER_KV_RING` 已是**空转**；`--kvmem-*` CLI 选项在本树**未接线** |

---

# A. DFlash2

## A1. `missing component dflash2` 的产生点与组件机制

### A1.1 报错原文的产生

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/artifact/schema.cpp:88-94`:
```
const Component& Directory::component(std::string_view name) const {
    const auto found = components.find(name);
    if (found == components.end()) {
        throw ArtifactError("missing component " + std::string(name));
    }
    return found->second;
}
```

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/models/qwen3_5/config.cpp:339-341`:
```
    } catch (const std::exception& error) {
        throw ArtifactError(std::string("Qwen3.5 config: ") + error.what());
    }
```
→ 两行拼起来就是用户看到的 `Qwen3.5 config: missing component dflash2`。

### A1.2 调用链（为什么查的是 `dflash2`）

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/models/qwen3_5/config.cpp:333-337`:
```
        if (options.speculative == SpeculativeBackend::DFlash ||
            options.speculative == SpeculativeBackend::DFlash2) {
            out.draft = draft(companion(directory, options.speculative_component()).config,
                              out.text, options.speculative == SpeculativeBackend::DFlash2);
        }
```

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/models/load_options.h:86-97`:
```
    [[nodiscard]] std::string_view speculative_component() const noexcept {
        switch (speculative) {
        case SpeculativeBackend::None:
            return {};
        case SpeculativeBackend::Mtp:
            return "mtp";
        case SpeculativeBackend::DFlash:
            return "dflash";
        case SpeculativeBackend::DFlash2:
            return "dflash2";
        }
        return {};
    }
```

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/models/qwen3_5/config.cpp:48-54`:
```
const artifact::Component& companion(const artifact::Directory& directory, std::string_view name) {
    const auto& component = directory.component(name);
    if (component.target != "text") {
        throw ArtifactError(std::string(name) + ": target must be text");
    }
    return component;
}
```
→ 附带硬约束：**任何投机组件的 `target` 必须等于 `"text"`**。

### A1.3 组件在容器里怎么声明与查找

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/artifact/schema.cpp:251-262`:
```
void parse_components(Directory& out, const Json& values) {
    if (!values.is_object() || !values.contains("text")) {
        throw ArtifactError("components must contain text");
    }
    for (const auto& [name, value] : values.items()) {
        (void)require_id(Json(name), "component id");
        require_members(value, {"config"}, {"target", "resources", "proposal"}, name);
        Component component;
        component.config = value.at("config");
```

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/artifact/schema.cpp:280`:
```
            if (name != "text") { throw ArtifactError("only text may declare proposal"); }
```
→ 组件名在容器里是**自由字符串**（没有枚举白名单），约束只有三条：①必须有 `text`；②每个组件 `config` 必填、`target`/`resources`/`proposal` 可选；③只有 `text` 能带 `proposal`。
→ 所以"缺 dflash2"不是名字不合法，而是**该容器根本没写这个组件**。

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/src/artifact/schema.h:96-109`:
```
struct Directory {
    std::map<std::string, Component, std::less<>> components;
    ...
    [[nodiscard]] const Component& component(std::string_view name) const;
```

### A1.4 引擎支持的**全套组件名**（源码里出现过的全部）

| 组件名 | 引用位置 | 是否必需 |
|---|---|---|
| `text` | `config.cpp:322` `directory.component("text")`；`schema.cpp:252` "components must contain text" | **必需** |
| `vision` | `config.cpp:323` `companion(directory, "vision")` | 可选（`--vision`） |
| `mtp` | `config.cpp:325` `companion(directory, "mtp")`；`load_options.h:91` | 可选（`--spec mtp`） |
| `dflash` | `load_options.h:93` return "dflash" | 可选（`--spec dflash`） |
| `dflash2` | `load_options.h:95` return "dflash2" | 可选（`--spec dflash2`） |

补充：`proposal` **不是组件**，是 `text` 组件的子对象（`schema.cpp:280-292`），走 `--lm-head-draft` / `--proposal` 启用。

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/weight-conversion.md:103`:
```
  --components text,vision,mtp,dflash2 \
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/weight-conversion.md:46`:
```
`--components` defaults to `text`. Include only the optional components you want to distribute.
```

**Coder390 现状**：容器只有 `text` + `mtp`
[EVIDENCE] `docs/协作-给CodeBuddy-20261009.md:48`:
```
**关键事实**：该 `.ninfer` 容器 = `NINFER\0\3`、`Qwen3_5ForCausalLM`、64 层/hidden 5120/vocab 248320/max_pos 262144；组件**只有 `text` + `mtp`**；`text` 787 权重**零 q4_0**，**5 个 q4_0 全在 MTP**。
```

---

## A2. DFlash2 组件加载需要什么（配置字段 + 权重清单）

### A2.1 加载代码路径

```
config.cpp:302 parse_config(...)
  └─ config.cpp:333-337  选 dflash/dflash2 → companion(directory, "dflash2")
      └─ config.cpp:210-283  draft(value, target, dflash2=true)   解析 draft config
load.cpp:53 plan_load(...)
  └─ load.cpp:93-98   config.draft → loading::bind_draft(...)
      └─ src/models/qwen3_5/load/dflash.cpp:5-45   bind_draft()
          └─ dflash.cpp:43   if (config.dflash2) bind_dflash2(...)
              └─ src/models/qwen3_5/load/dflash2.cpp:5-29  bind_dflash2()
  └─ load.cpp:99-116  proposal head（--lm-head-draft）与 selector_top_k 域检查
```

### A2.2 必填 config 字段

[EVIDENCE] `.../src/models/qwen3_5/config.cpp:210-220`:
```
DraftConfig draft(const Json& value, const TextConfig& target, bool dflash2) {
    require_members(value,
                    {"architectures", "model_type", "intermediate_size", "num_attention_heads",
                     "num_key_value_heads", "head_dim", "num_hidden_layers",
                     "max_position_embeddings", "rms_norm_eps", "rope_parameters", "layer_types",
                     "dflash_config"},
                    {"sliding_window"}, "draft config");
    if (architecture(value) != (dflash2 ? "DFlash2DraftModel" : "DFlashDraftModel") ||
        value.at("model_type") != "qwen3") {
        throw ArtifactError("draft architecture/model_type mismatch");
    }
```
→ **草稿层数用的字段名是 `num_hidden_layers`，不是 `num_draft_layers`**（`config.cpp:225` `out.num_hidden_layers = dimension(value, "num_hidden_layers");`）。

[EVIDENCE] `.../src/models/qwen3_5/config.cpp:248-256`:
```
    const auto& config = value.at("dflash_config");
    if (dflash2) {
        require_members(config,
                        {"target_layer_ids", "mask_token_id", "conv_kernel_size", "conv_group_size",
                         "selector_rank", "selector_top_k"},
                        {}, "DFlash2 config");
    } else {
        require_members(config, {"target_layer_ids", "mask_token_id"}, {}, "DFlash config");
    }
```

[EVIDENCE] `.../src/models/qwen3_5/config.cpp:257-281`（三项与 target 的硬耦合校验）:
```
    for (const auto& tap : taps) {
        const auto index = integer(tap, "target layer index", false);
        if (index >= target.num_hidden_layers || !unique.insert(index).second) {
            throw ArtifactError("invalid target layer index");
        }
        out.target_layer_ids.push_back(index);
    }
    out.mask_token_id = integer(config.at("mask_token_id"), "mask token", false);
    if (out.mask_token_id >= target.vocab_size) {
        throw ArtifactError("mask token exceeds target embedding rows");
    }
    if (dflash2) {
        DFlash2Config extra{
            dimension(config, "conv_kernel_size"), dimension(config, "conv_group_size"),
            dimension(config, "selector_rank"), dimension(config, "selector_top_k")};
        if (target.hidden_size % extra.conv_group_size) {
            throw ArtifactError("DFlash2 conv group does not divide hidden width");
        }
        out.dflash2 = extra;
    }
```
→ 三条硬约束：**①`target_layer_ids` 每项 < target 层数；②`mask_token_id` < target 词表；③`hidden_size % conv_group_size == 0`**。

[EVIDENCE] `.../src/models/qwen3_5/config.cpp:222-223`:
```
    out.attention = attention(value);
    if (out.attention.head_dim % 2) { throw ArtifactError("draft head dimension must be even"); }
```

### A2.3 权重张量清单（`{C}` = 组件名，即 `dflash2`）

[EVIDENCE] `.../src/models/qwen3_5/load/dflash.cpp:12-42`:
```
    out.feature_projection = b.parameter(
        component + "/feature_projection",
        {h, artifact::checked_mul(config.target_layer_ids.size(), h, "target features")},
        {component + "/target_features"});
    out.context_norm    = b.direct(component + "/context_norm", {h});
    out.final_norm      = b.direct(component + "/final_norm", {h});
    out.token_embedding = weights.token_embedding;      // ← 直接复用 target
    out.output_head     = weights.output_head;          // ← 直接复用 target
    out.layers.reserve(config.num_hidden_layers);
    for (std::uint32_t i = 0; i < config.num_hidden_layers; ++i) {
        const auto p = component + "/layers/" + std::to_string(i) + "/";
        DraftBlockWeights layer;
        layer.input_norm          = b.direct(p + "input_norm", {h});
        layer.post_attention_norm = b.direct(p + "post_attention_norm", {h});
        layer.attention.query =
            b.parameter(p + "attention/query", {q, h}, {p + "query_projection_input"});
        layer.attention.key   = b.parameter(p + "attention/key",   {k, h}, ...);
        layer.attention.value = b.parameter(p + "attention/value", {k, h}, ...);
        layer.attention.context_key   = b.parameter(p + "attention/context_key",   {k, h}, ...);
        layer.attention.context_value = b.parameter(p + "attention/context_value", {k, h}, ...);
        layer.attention.query_norm = b.direct(p + "attention/query_norm", {d});
        layer.attention.key_norm   = b.direct(p + "attention/key_norm", {d});
        layer.attention.output =
            b.parameter(p + "attention/output", {h, q}, {p + "attention_output"});
        layer.mlp = bind_dense(b, h, config.intermediate_size, p, true);
```
→ **`token_embedding` 与 `output_head` 不单独存，直接共享 target 的**（这是"维度必须一致"的根因之一）。

[EVIDENCE] `.../src/models/qwen3_5/load/dflash.cpp:43`:
```
    if (config.dflash2) { bind_dflash2(b, out, config, target); }
```

[EVIDENCE] `.../src/models/qwen3_5/load/dflash2.cpp:5-29`（DFlash2 独有张量）:
```
void bind_dflash2(Bindings& b, DraftWeights& weights, const DraftConfig& config,
                  const TextConfig& target) {
    const auto& extra = config.dflash2.value();
    const auto h      = target.hidden_size;
    const auto rows =
        artifact::checked_mul(2ULL * extra.conv_kernel_size, h / extra.conv_group_size,
                              "DFlash2 dynamic projection rows");
    for (std::uint32_t i = 0; i < config.num_hidden_layers; ++i) {
        const auto p           = "dflash2/layers/" + std::to_string(i) + "/";
        const auto convolution = [&](const std::string& name) {
            return DynamicConvWeights{
                b.direct(p + name + "/base_kernel", {2, extra.conv_kernel_size, h}),
                b.parameter(p + name + "/kernel_projection", {rows, h}, {p + name + "_input"})};
        };
        weights.layers[i].attention_conv = convolution("attention_conv");
        weights.layers[i].mlp_conv       = convolution("mlp_conv");
    }
    weights.selector =
        SelectorWeights{b.parameter("dflash2/candidate_selector/hidden_projection",
                                    {extra.selector_rank, h}, {"dflash2/final_hidden"}),
                        b.direct("dflash2/candidate_selector/predecessor_codebook",
                                 {target.vocab_size, extra.selector_rank}),
                        b.direct("dflash2/candidate_selector/successor_codebook",
                                 {target.vocab_size, extra.selector_rank})};
```
→ **codebook 形状 = `[target.vocab_size, selector_rank]`**：词表必须与 target 逐行对齐。
（注：`bind_dflash2` 里前缀写死为 `"dflash2/"`（`dflash2.cpp:13`、`:22-27`），与本线组件名同为 `dflash2`，无冲突。）

### A2.4 proposal 头（`--lm-head-draft`）与 selector 域检查

[EVIDENCE] `.../src/models/qwen3_5/load.cpp:99-113`:
```
    if (options.proposal_enabled()) {
        const auto& proposal = reader.directory().component("text").proposal;
        if (!proposal) {
            throw artifact::ArtifactError("selected proposal head is absent from artifact");
        }
        out->weights.proposal = loading::bind_proposal(bindings, *proposal, text, options,
                                                       out->resources.public_token_count);
        if (out->config.draft && out->config.draft->dflash2) {
            const auto domain =
                proposal->indexed ? proposal->rows : out->resources.public_token_count;
            if (out->config.draft->dflash2->selector_top_k > domain) {
                throw artifact::ArtifactError(
                    "proposal domain is smaller than DFlash2 selector_top_k");
```
[EVIDENCE] `.../src/models/qwen3_5/load.cpp:114-115`:
```
        if (out->weights.mtp) { out->weights.mtp->output_head = out->weights.proposal->head; }
        if (out->weights.draft) { out->weights.draft->output_head = out->weights.proposal->head; }
```

工程侧（非源码校验，但实测硬要求）：
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/07-模型与制品.md:10`:
```
sha256 与 `SHA256SUMS.txt` 一致；按后端选件（`mtp` 要 MTP 头；`dflash2` 要带 `dflash2/*` 载荷的件且 `--lm-head-draft` 必开）。
```
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/start-8085-dflash2.bat:27-28`:
```
echo   NOTE  : --lm-head-draft is MANDATORY. Without it the engine dies at startup with
echo           FATAL server failed during startup ^| linear_topk: unsupported head profile
```

### A2.5 启动期宽度约束

[EVIDENCE] `.../src/product/speculative_options.h:88-95`:
```
    case SpeculativeBackend::DFlash2:
        if (options.draft_tokens == 0 || options.draft_tokens > 15) {
            throw std::invalid_argument("--spec dflash2 requires --draft-tokens in [1,15]");
        }
```

### A2.6 官方 DFlash2 几何（对照基准）

[EVIDENCE] `.../docs/maintainer/dflash.md:21-32`:
```
| Quantity | Official 35B-A3B DFlash | Official 27B DFlash2 |
|---|---:|---:|
| Hidden width H | 2048 | 5120 |
| Draft layers | 6 | 5 |
| Intermediate width | 6144 | 17408 |
| Q heads / KV heads / head dimension | 32 / 8 / 128 | 32 / 8 / 128 |
| Target block IDs | `[1,6,11,16,22,27,32,37]` | `[5,19,33,47,61]` |
| Attention pattern | Five local layers, then one full layer | Five local layers |
| Sliding-window scalar S | 4096 | 2048 |
| Norm epsilon / RoPE theta | `1e-6` / `1e7` | `1e-6` / `1e7` |
| Dynamic convolution | — | Two taps, group width 16 |
| Candidate selector | Per-position argmax | Top-16 conditional path, rank 256 |
```

---

## A3. 现成的 dflash2 权重来源线索

### A3.1 工作区内**没有** `DFlash2-FP8/` 或 NVFP4 草稿件目录（实测）

实测命令（PowerShell）：
```
Get-ChildItem -Path "J:\ninfer-kvmem" -Directory -Recurse -Filter "*DFlash*"
```
→ **返回为空（exitCode 0，stdout 空）**。即整个 `J:\ninfer-kvmem`（含 `official-repo\`、`refs\`、`models\`、`engine\`）下没有任何名为 `*DFlash*` 的目录。

文本侧交叉验证：`DFlash2-FP8|NVFP4-Infer|DFlash2-NVFP4` 全工作区仅 2 处命中，且都在本线自己的交接文档里作为"待核实项"，不是实际存在的目录：
[EVIDENCE] `docs/协作-给CodeBuddy-20261009.md:72`:
```
3. **DFlash2**：核实主仓 `DFlash2-FP8/` 或 NVFP4-Infer 仓是否有可用的 `.ninfer` 草稿件，参考沈三殊"自造 dflash2 注入件"做法（`refs\01-沈三殊-发放包\新\急速档V2\`）。
```
[EVIDENCE] `docs/交接-工作区迁移-TeleAgent-20261009.md:62`:
```
- **DFlash2（卡在包内无组件）**：需另找 **DFlash2 草稿件**并注入（主仓 `DFlash2-FP8/` 或 NVFP4-Infer 仓的 `.ninfer`）。**最不确定项**。可参考沈三殊档位包里的"**自造 dflash2 注入件**"做法（`refs\01-沈三殊-发放包\新\急速档V2\`）。
```

### A3.2 官方 DFlash2 权重源（Qwen3.8-27B 专用）

[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/model-cards/Qwen3.8-27B-nvfp4-NInfer/artifact-manifest.json:30-34`:
```
    "dflash2": {
      "repo_id": "z-lab/Qwen3.8-27B-DFlash2",
      "revision": "50307d4c4cde6860d4eee73e2547cd786fe8e8a4",
      "license": "Apache-2.0"
    }
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/model-cards/Qwen3.8-27B-nvfp4-NInfer/README.md:150-153`:
```
This release includes the complete DFlash2 companion weights from
`z-lab/Qwen3.8-27B-DFlash2` at revision
`50307d4c4cde6860d4eee73e2547cd786fe8e8a4`. Select
`--spec dflash2 --draft-tokens 7 --lm-head-draft`; draft counts 1..15 are supported.
```
（同样内容见 `model-cards/Qwen3.8-27B-NInfer/artifact-manifest.json:25-29` 与 `README.md:134-137`）

### A3.3 急速档V2「自造 dflash2 注入件」到底怎么造

**(1) 产物声明**
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/README.md:14-16`:
```
**本档携带的模型制品（逐个点名）**
- `model\bonsai2_27b_ternary_v2.ninfer`（格式 **PQ2_0**）—— 基座三元制品
- `model\bonsai2_27b_ternary_v2-dflash2.ninfer`（PQ2_0 + 自造 dflash2 注入件）
```
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/agent/manifest.json:333-334`:
```
                                      "`model\\bonsai2_27b_ternary_v2.ninfer`（格式 **PQ2_0**）—— 基座三元制品",
                                      "`model\\bonsai2_27b_ternary_v2-dflash2.ninfer`（PQ2_0 + 自造 dflash2 注入件）"
```

**(2) 关键：用的不是 z-lab 原版，而是「在本基座上重训的」草稿头**
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/weight-conversion.md:128-134`:
```
resources come from the Qwen3.8-27B checkpoint, which shares the geometry. The published artifact
takes its MTP head and DFlash2 adapter from ProCreations' heads trained on Bonsai 2 itself
([MTP](https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-MTP),
[DFlash2](https://huggingface.co/ProCreations/Ternary-Bonsai-2-27B-DFlash2)), which accept more drafts
than the vanilla ones. The recipe stores the adapter's feature, output and MLP projections in Q4,
since against a 2.125-bit target the drafter is a large share of every draft step's bytes; the
fused query/key/value projection stays Q8, which its three-output op requires.
```
→ **"自造"= 用在该基座上训练过的 DFlash2 适配器**（`ProCreations/Ternary-Bonsai-2-27B-DFlash2`），不是拿 vanilla 硬套。

**(3) 官方转换/注入命令（两条路）**
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/tools/README.md:55-61`:
```
python3 -m tools.convert \
  --model /path/to/Qwen3.8-27B \
  --recipe qwen3_8_27b --components text,vision,mtp,dflash2 --proposal \
  --source dflash2=/path/to/Qwen3.8-27B-DFlash2 \
  --resource chat_template.jinja=tools/chat_templates/qwen3_8.jinja \
  --name qwen3.8-27b \
  --out out/qwen3_8_27b.ninfer
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/weight-conversion.md:139-147`（三元 Bonsai 线）:
```
  --recipe bonsai2_27b_ternary \
  --source ternary=/path/to/Ternary-Bonsai-2-27B-PQ2_0.gguf \
  --source mtp=/path/to/Ternary-Bonsai-2-27B-MTP/model_mtp.safetensors \
  --source dflash2=/path/to/Ternary-Bonsai-2-27B-DFlash2 \
  --components text,vision,mtp,dflash2 \
  --resource chat_template.jinja=tools/chat_templates/qwen3_8.jinja \
  --proposal \
  --name bonsai2-27b \
  --out models/bonsai2_27b.ninfer
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/docs/weight-conversion.md:472-478`:
```
- **DFlash2** needs no GGUF-specific code at all in the cases seen so far: it's
  a small enough draft head that a plain Safetensors checkpoint for it is the
  normal way to get one, and `tools.convert` already reads that natively via
  `--source dflash2=PATH` plus `--components ...,dflash2` -- the same mechanism
  `qwen3_8_27b_nvfp4`'s example in this doc already uses.
```

**(4) 现成脚本（急速档V2 仓内的 Qwen3.8-27B DFlash2 注入件）**
- 转换器入口：`refs/01-沈三殊-发放包/新/急速档V2/src-tree/ninfer-4090w-ternary/tools/convert/qwen3_8_27b/convert.py`
  [EVIDENCE] `.../qwen3_8_27b/convert.py:5-8`:
  ```
      python3 -m tools.convert.qwen3_8_27b.convert \
        --model /path/to/Qwen3.8-27B \
        --dflash2-model /path/to/Qwen3.8-27B-DFlash2 \
        --out out/qwen3_8_27b.ninfer
  ```
  [EVIDENCE] `.../qwen3_8_27b/convert.py:288-300`:
  ```
          with ShardReader.from_file(
              preflight.dflash2_model_dir / "model.safetensors"
          ) as dflash2_reader:
              for spec in DFLASH2_TENSOR_SPECS:
                  index += 1
                  tensor = dflash2_recipe.materialize_tensor(
                      spec.name, dflash2_reader
                  )
                  payload = encode_tensor_payload(tensor, spec, resolved_device)
  ```
- 张量清单：`.../tools/convert/qwen3_8_27b/dflash2_inventory.py`
  [EVIDENCE] `.../dflash2_inventory.py:13-14`:
  ```
          tensor_spec("dflash2/feature_projection", (5120, 25600), W8),
          tensor_spec("dflash2/context_norm", (5120,), BF16),
  ```
  [EVIDENCE] `.../dflash2_inventory.py:68-75`:
  ```
              tensor_spec(
                  "dflash2/candidate_selector/predecessor_codebook",
                  (248320, 256),
                  BF16,
              ),
              tensor_spec(
                  "dflash2/candidate_selector/successor_codebook",
                  (248320, 256),
                  BF16,
              ),
  ```
- 源与 config：`.../tools/convert/qwen3_8_27b/dflash2_recipe.py`
  [EVIDENCE] `.../dflash2_recipe.py:17-18`:
  ```
  REPOSITORY = "z-lab/Qwen3.8-27B-DFlash2"
  REVISION = "50307d4c4cde6860d4eee73e2547cd786fe8e8a4"
  ```
  [EVIDENCE] `.../dflash2_recipe.py:25-55`:
  ```
      "hidden_size": 5120,
      "intermediate_size": 17408,
      "num_hidden_layers": 5,
      "num_attention_heads": 32,
      "num_key_value_heads": 8,
      "head_dim": 128,
      ...
      "sliding_window": 2048,
      "vocab_size": 248320,
      "num_target_layers": 64,
      "max_position_embeddings": 262144,
      "rms_norm_eps": 1e-6,
  ...
  _DRAFT_CONFIG = {
      "block_size": 8,
      "conv_group_size": 16,
      "conv_kernel_size": 2,
      "mask_token_id": 248070,
      "selector_rank": 256,
      "selector_top_k": 16,
      "target_layer_ids": [5, 19, 33, 47, 61],
  }
  ```
- 官方仓的等价物（v2→v3 升级器里也有同一份 dflash2 config 生成逻辑）
  [EVIDENCE] `official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/tools/upgrade_ninfer_v2_to_v3.py:131-150`:
  ```
      if second:
          draft.update(
              conv_kernel_size=2, conv_group_size=16, selector_rank=256, selector_top_k=16
          )
      return {
          "architectures": ["DFlash2DraftModel" if second else "DFlashDraftModel"],
          "model_type": "qwen3",
          "intermediate_size": 17408 if second else 6144,
          ...
          "dflash_config": draft,
      }
  ```

**(5) 参考启动档（急速档V2 自带的 dflash2 启动件）**
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/start-8085-dflash2.bat:86-90`:
```
"%ENGINE%" "%MODEL%" ^
  --host 127.0.0.1 --port 8085 --model-id qwen3.8-27b ^
  --max-context 32768 --kv-capacity 32768 --kv-dtype fp8 ^
  --max-concurrency 1 --no-thinking ^
  --spec dflash2 --draft-tokens 7 --lm-head-draft
```

---

## A4. 判断：给 Coder390 注入 dflash2 技术上是否成立

### A4.1 几何：**完全匹配**（可加载的必要条件全部满足）

| 校验项 | Coder390 实测 | DFlash2 要求 | 出处 | 结论 |
|---|---|---|---|---|
| `num_hidden_layers`（= num_target_layers） | 64 | 64 | `dflash2_recipe.py:38` vs `协作-给CodeBuddy-20261009.md:48` | ✅ |
| `hidden_size` | 5120 | 5120 | `dflash2_recipe.py:25` vs 同上 | ✅ |
| `vocab_size` | 248320 | 248320 | `dflash2_recipe.py:37` vs 同上 | ✅ |
| `max_position_embeddings` | 262144 | 262144 | `dflash2_recipe.py:39` vs 同上 | ✅ |
| `target_layer_ids` 上界 | — | `[5,19,33,47,61]` 全部 < 64 | `dflash2_recipe.py:54`；`config.cpp:264` | ✅ |
| `mask_token_id` | — | 248070 < 248320 | `dflash2_recipe.py:51`；`config.cpp:270` | ✅ |
| `hidden % conv_group_size` | 5120 % 16 = 0 | 必须整除 | `config.cpp:277` | ✅ |
| codebook 行数 | 248320 | 248320 | `dflash2.cpp:25-28` | ✅ |

转换器的官方兼容性校验也正好逐项比对这几条：
[EVIDENCE] `refs/01-沈三殊-发放包/新/急速档V2/src-tree/ninfer-4090w-ternary/tools/convert/qwen3_8_27b/dflash2_recipe.py:155-175`:
```
    pairs = (
        ("hidden_size", text.get("hidden_size"), dflash2_summary.get("hidden_size")),
        ("vocab_size", text.get("vocab_size"), dflash2_summary.get("vocab_size")),
        (
            "num_target_layers",
            text.get("num_hidden_layers"),
            dflash2_summary.get("num_target_layers"),
        ),
        (
            "max_position_embeddings",
            text.get("max_position_embeddings"),
            dflash2_summary.get("max_position_embeddings"),
        ),
        ("rope_theta", rope.get("rope_theta"), draft_rope.get("rope_theta")),
    )
    for name, base_value, draft_value in pairs:
        if base_value != draft_value:
            raise ValueError(
                f"base/DFlash2 {name} mismatch: {base_value!r} != "
                f"{draft_value!r}"
            )
```
→ Coder390 是 **Qwen3.8-27B 的同几何微调**，因此 `z-lab/Qwen3.8-27B-DFlash2` 在"能不能写进去、能不能加载"这一层**是成立的**。

### A4.2 但：草稿头消费的是 target 的**残差特征**，必须同源

[EVIDENCE] `.../docs/maintainer/dflash.md:46-58`:
```
For each processed position t, let `r_t^l` be the complete residual output of zero-based target
block l, after both mixer and FFN residual additions. Conditioning is:

s_t = concat(r_t^l for l in target_layer_ids, in recorded order)
c_t = plain_rmsnorm(W_feature s_t, context_norm)
```
[EVIDENCE] `.../load/dflash.cpp:12-15`（feature_projection 的输入维 = `len(target_layer_ids) * h`）：
```
    out.feature_projection = b.parameter(
        component + "/feature_projection",
        {h, artifact::checked_mul(config.target_layer_ids.size(), h, "target features")},
        {component + "/target_features"});
```
→ 草稿头的输入就是 **target 第 5/19/33/47/61 层的残差拼接**。Coder390 是 Qwen3.8-27B 的**微调**（`EfficientThink` / `Q2LynnStyle`），这些层的残差分布已经偏离 base ⇒ vanilla DFlash2 的 `W_feature`/`context_norm`/selector 都是按 base 分布拟合的，**接受率会掉**。

**实测反例（同族但不同权重档）**：
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/已知问题-初期版本.md:323`:
```
- **B18 dflash2 头质量**：社区报告 C（3090）实测 swift-qwen38-rco-iq3s 的 dflash2 接受率 **22% / 47%**，而 PQ2 全量（8.87 GB 含头）**91.5–100%**；目录速度：`无 MTP 57.1 / 56.9`、`MTP2 96.6 / 125.0 t/s`、`dflash2-7 69.5 / 116.1 t/s`。另：**引擎不支持外挂 draft 模型**（z-lab / HyperQwen 的 DFlash2 只兼容 vLLM / SGLang）。
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/README.md:222`:
```
| 用 dflash2 当投机头（B18） | 其头质量明显低于 PQ2（接受率 22%/47% vs 91.5–100%），且**引擎不支持外挂 draft 模型** ⇒ 要高质量请用 PQ2 档的件 |
```
→ 同一族里，"非为该权重档训练的 dflash2 头"实测接受率只有 22%/47%，**目录速度甚至低于 MTP2（69.5 vs 96.6 t/s）**。

### A4.3 另外两条硬边界

[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1041-1044`（多卡切分禁用 DFlash/DFlash2）：
```
        if (options.speculative.backend == SpeculativeBackend::DFlash ||
            options.speculative.backend == SpeculativeBackend::DFlash2) {
            unsupported("DFlash speculative decoding");
        }
```

[EVIDENCE] `docs/协作-给CodeBuddy-20261009.md:50`（容器可重写 ⇒ 数据侧注入是可行的）：
```
**容器可重写**：`reader.cpp` 无内容校验（offset16 = artifact id 非哈希；payload 对齐 4096）⇒ 数据侧重打包安全。
```

### A4.4 结论

- **"能不能加载"：成立。** 四项几何全对得上；源码的三条硬校验（`target_layer_ids < 64`、`mask_token_id < 248320`、`5120 % 16 == 0`）全部通过；容器可重写（协作文档:50）。
- **"值不值得"：存疑，且必须区分两种注入件：**
  - 用 `z-lab/Qwen3.8-27B-DFlash2`（vanilla，为 base 训练）⇒ 能跑，但按 B18 同族实测外推，**接受率大概率落在 22%–47% 量级，可能比 MTP 还慢**，属于"能起但负收益"。
  - 用**在 Coder390 本体上训练出来的** DFlash2 适配器（对应 Bonsai 线的 `ProCreations/Ternary-Bonsai-2-27B-DFlash2` 做法，`weight-conversion.md:128-134`）⇒ 才有意义；但我们**没有**这样的权重，也没有现成训练脚本。
- **必须同源吗？** 严格说不是"必须"，但**源码与实测都指向"不同源 ⇒ 接受率崩塌"**：DFlash2 直接吃 target 残差（`dflash.md:46-58`）、共享 target 的 embedding/output head（`dflash.cpp:18-19`）、codebook 按 target 词表逐行对齐（`dflash2.cpp:25-28`）。任何偏离都只影响"接受率"，不影响"能不能启动"。
- **当前阻塞**：`models\` 下只有 Coder390 一个 13.27 GB 件，工作区**没有任何 dflash2 草稿件**（A3.1 实测），也没有 `DFlash2-FP8/`。

---

# B. ngram

## B5. `--ngram-draft-tokens` 与 `--lookup-ngram` 的实现位置与启用条件差异

### B5.1 `--ngram-draft-tokens`（引擎级 copy 提议器，`ngram_draft_window`）

**选项解析**：
[EVIDENCE] `.../src/serve/serve_options.cpp:506-509`:
```
        } else if (arg == "--ngram-draft-tokens") {
            options.speculative.ngram_draft_tokens = static_cast<std::uint32_t>(
                parse_nonnegative_int(require_value("--ngram-draft-tokens"), "ngram-draft-tokens"));
            ngram_width_explicit = true;
```
（CLI 侧同源：`.../apps/cli/options.cpp:353-356`）

**帮助文本**：
[EVIDENCE] `.../src/serve/serve_options.cpp:270-274`:
```
           "  --ngram-draft-tokens N        copy up to N tokens (1..63) per round from\n"
           "                                earlier prompt, tool-result or output text,\n"
           "                                verified alongside --spec; on with 15 whenever\n"
           "                                --spec is set, 0 disables it, above 15 needs\n"
           "                                --max-concurrency 1\n"
```

**默认值（只要设了 `--spec` 就自动开 15）**：
[EVIDENCE] `.../src/product/speculative_options.h:32-41`:
```
// Copy drafting rides along with every drafter unless the command line sets its width. Fifteen
// drafts is the widest a multi-request batch verifies, so the default holds at any concurrency.
inline constexpr std::uint32_t kDefaultNgramDraftTokens = 15;

inline void apply_default_ngram_draft_tokens(SpeculativeOptions& options,
                                             bool width_explicit) noexcept {
    if (!width_explicit && options.backend != SpeculativeBackend::None) {
        options.ngram_draft_tokens = kDefaultNgramDraftTokens;
    }
}
```
[EVIDENCE] `.../src/serve/serve_options.cpp:1152-1153`:
```
    product::apply_default_ngram_draft_tokens(options.speculative, ngram_width_explicit);
    product::validate_speculative_cli_options(options.speculative);
```

**校验（就是用户看到的那条报错）**：
[EVIDENCE] `.../src/product/speculative_options.h:50-58`:
```
    if (options.ngram_draft_tokens != 0 &&
        ((options.backend != SpeculativeBackend::DFlash2 &&
          options.backend != SpeculativeBackend::DFlash &&
          options.backend != SpeculativeBackend::Mtp) ||
         options.ngram_draft_tokens > 63 || options.ngram_min_match < 4 ||
         options.ngram_min_match > 64)) {
        throw std::invalid_argument(
            "ngram requires --spec mtp|dflash|dflash2, drafts 1..63 and match 4..64");
    }
```
[EVIDENCE] `.../src/serve/serve_options.cpp:1170-1174`（并发侧附加约束）：
```
    // The GDN conv-record workspace admits at most 16 verification columns when the batch holds
    // more than one request, so a wider ngram proposal is admitted only for one active request.
    if (options.speculative.ngram_draft_tokens > 15 && options.max_concurrency != 1) {
        throw std::invalid_argument("--ngram-draft-tokens above 15 requires --max-concurrency 1");
    }
```
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1178-1188`（引擎侧二次校验，措辞更全）：
```
    if (options.speculative.ngram_draft_tokens != 0 &&
        ((options.speculative.backend != SpeculativeBackend::DFlash2 &&
          options.speculative.backend != SpeculativeBackend::DFlash &&
          options.speculative.backend != SpeculativeBackend::Mtp) ||
         options.speculative.ngram_draft_tokens > 63 || options.speculative.ngram_min_match < 4 ||
         options.speculative.ngram_min_match > 64 ||
         (options.speculative.ngram_draft_tokens > 15 && options.max_concurrency != 1))) {
        throw std::invalid_argument(
            "ngram requires MTP/DFlash/DFlash2, K1..63 and match 4..64; the GDN conv-record "
            "workspace admits at most 16 verification columns for a multi-request batch, so K "
            "above 15 requires concurrency one");
    }
```

**运行时实现**：
[EVIDENCE] `.../src/models/qwen3_5/program/decode.cpp:232-247`:
```
std::vector<NgramProposer::Match>
ProgramImpl::propose_ngram(std::span<const std::uint32_t> lanes,
                           std::span<const runtime::RoundBudget> budgets) {
    std::vector<NgramProposer::Match> matches(lanes.size());
    if (ngram_draft_window == 0) { return matches; }
```
[EVIDENCE] `.../src/models/qwen3_5/program/decode.cpp:249-298`（`propose_ngram_one`：ingest ledger → 查 archive 快照 → 查请求内语料 → `finish_round`）：
```
    const auto maximum = std::min({ngram_draft_window, remaining > 1 ? remaining - 1U : 0U, room});
    ...
    match = NgramProposer::finish_round(std::move(match), maximum, draft_window);
```
[EVIDENCE] `.../src/models/qwen3_5/program/ngram_proposer.h:66-89`:
```
    [[nodiscard]] Match propose_for_round(std::span<const Token> history, std::uint32_t maximum,
                                          std::uint32_t neural_drafts,
                                          std::uint32_t minimum_match = 12) const {
        ...
        return finish_round(propose(history, maximum + 2U, minimum_match), maximum, neural_drafts);
    }
    ...
        if (available < maximum + 2U && drafts <= neural_drafts) { return {}; }
```
**关键行 `ngram_proposer.h:86`** —— ngram 只在"能超过神经草稿数"时才提议，否则让位。这就是它必须与 `--spec` 共存的结构性原因。

[EVIDENCE] `.../src/models/qwen3_5/program/ngram_proposer.h:144`（n-gram 宽度固定 16/8/4）：
```
    static constexpr std::array<std::uint32_t, 3> widths_{16, 8, 4};
```
[EVIDENCE] `.../src/models/qwen3_5/ngram.h:34-39`（archive 预算）：
```
struct NgramArchiveLimits {
    std::size_t session_bytes = 128ULL << 20;
    std::size_t total_bytes   = 512ULL << 20;
    std::uint32_t sessions    = 32;
    std::uint32_t sources     = 1024;
};
```
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1585`:
```
        .ngram_draft_window         = options.speculative.ngram_draft_tokens,
```

### B5.2 `--lookup-ngram`（context-lookup 提议器，`lookup_ngram`）

**选项解析**：
[EVIDENCE] `.../src/serve/serve_options.cpp:641-643`:
```
        } else if (arg == "--lookup-ngram") {
            options.speculative.lookup_ngram = static_cast<std::uint32_t>(
                parse_nonnegative_int(require_value("--lookup-ngram"), "lookup-ngram"));
```
（CLI 侧：`.../apps/cli/options.cpp:388-389`）

**帮助文本**：
[EVIDENCE] `.../src/serve/serve_options.cpp:283-286`:
```
           "  --lookup-ngram N              context-lookup drafting alongside --spec: the\n"
           "                                last N tokens are matched against the sequence\n"
           "                                so far and what followed is proposed (default 0:\n"
           "                                off)\n"
```

**实现（只有一处调用点）**：
[EVIDENCE] `.../src/models/qwen3_5/program/prefill.cpp:1013-1018`:
```
                    if (lookup_ngram != 0) {
                        const auto found = ::ninfer::qwen3_5::lookup_draft(std::span<const TokenId>(sequence.ledger),
                                                                 lookup_ngram, draft_window,
                                                                 sequence.mtp_drafts.data());
                        if (found != 0) { sequence.mtp_draft_count = found; }
                    }
```
**⚠️ 这段被包在 MTP 分支里**：
[EVIDENCE] `.../src/models/qwen3_5/program/prefill.cpp:997`:
```
            if (speculative_backend == SpeculativeBackend::Mtp) {
```
→ **`--lookup-ngram` 只在 `--spec mtp` 下真正生效；配 `--spec dflash2` 是死代码**（`prefill.cpp:1020` 起的 else 分支是 DFlash 路径，完全不读 `lookup_ngram`）。这也解释了交接文档里"启动了但空转"的实测。
[EVIDENCE] `docs/协作-给CodeBuddy-20261009.md:46`:
```
| `--lookup-ngram` | ⚠️ 启动但空转 | A/B 实测 52.9 vs 51.9 tok/s，无差异 |
```

[EVIDENCE] `.../src/models/qwen3_5/program/speculative/lookup_draft.h:46-49`:
```
[[nodiscard]] inline std::uint32_t lookup_draft(std::span<const TokenId> ledger,
                                                std::uint32_t ngram, std::uint32_t max_drafts,
                                                TokenId* out) {
    if (ngram == 0 || max_drafts == 0 || out == nullptr) { return 0; }
```

### B5.3 两者启用条件的差异汇总

| 维度 | `--ngram-draft-tokens N` | `--lookup-ngram N` |
|---|---|---|
| 解析行 | `serve_options.cpp:506-509` | `serve_options.cpp:641-643` |
| 引擎字段 | `ngram_draft_window`（`startup.cpp:1585`） | `lookup_ngram`（`startup.cpp:1583`） |
| 是否校验"必须有 `--spec`" | **是**（`speculative_options.h:50-58` + `startup.cpp:1178-1188`） | **否**（无任何 backend 校验） |
| 默认值 | `--spec` 一设就自动 15（`speculative_options.h:36-41`） | 0（关） |
| 取值范围 | 1..63；>15 需 `--max-concurrency 1` | 未校验上界（只受 `draft_window` 裁剪） |
| 生效分支 | **MTP / DFlash / DFlash2 都生效**（`decode.cpp:236` 只看 `ngram_draft_window`，无 backend 分支） | **仅 MTP**（`prefill.cpp:997`） |
| 数据来源 | prompt + 工具结果 + 已生成输出 + 跨请求 archive（`decode.cpp:263-290`） | 仅本请求 ledger（`lookup_draft.h:50-75`） |
| 是否有存档 | 有（`NgramArchive`，`--ngram-archive-mib`） | 无 |
| 默认最小匹配 | 12（`--ngram-min-match`，`ngram.h:45`） | n-gram 宽度 = N 本身 |

### B5.4 为什么 ngram 必须依赖 `--spec`

1. **结构原因（源码注释直接写明）**：
[EVIDENCE] `.../src/include/ninfer/types.h:128-138`:
```
    // Context-lookup drafting: match this many trailing tokens against the sequence so far and
    // propose whatever followed the last time they appeared. 0 disables it. It costs no device
    // work, it is exact (verify rejects a wrong guess), and it is strongest exactly where a draft
    // head is weakest -- output that repeats the input. Used as a draft source alongside the
    // configured backend, preferred whenever it finds a match.
    std::uint32_t lookup_ngram = 0;
    ...
    // Optional target-verified copy proposals with MTP, DFlash or DFlash2, C1 only.
    // Zero disables the proposer; enabled draft width is 1..63 and minimum match 4..64.
    std::uint32_t ngram_draft_tokens = 0;
```
→ 关键词 **"alongside the configured backend"** —— ngram 是"叠加"在神经草稿头之上的补充源，不是独立后端。

2. **让位逻辑**：`ngram_proposer.h:86` `if (available < maximum + 2U && drafts <= neural_drafts) { return {}; }`，`neural_drafts` 实参就是 `draft_window`（`decode.cpp:291`）。没有 `--spec` ⇒ `draft_window=0` ⇒ 语义退化。
3. **验证宽度由神经后端决定**：
[EVIDENCE] `.../src/models/qwen3_5/program/program_impl.h:770-773`:
```
    // The widest round the decode frame verifies: the draft window, or the copy window when wider.
    [[nodiscard]] std::uint32_t widest_verify_window() const noexcept {
        return std::max(draft_window, ngram_draft_window);
    }
```
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:461-479`:
```
    const auto drafts = static_cast<std::int32_t>(plan.draft_window);
    // A copy round verifies up to the widest window; the neural drafter still proposes drafts.
    const auto verify_drafts = static_cast<std::int32_t>(widest_verify_window(plan));
    const auto verify        = verify_drafts + 1;
    // Neural rounds verify the draft window and copy rounds the ngram window.
    std::vector<std::int32_t> round_widths{drafts + 1};
    if (plan.ngram_draft_window != 0 && plan.ngram_draft_window != plan.draft_window) {
        round_widths.push_back(static_cast<std::int32_t>(plan.ngram_draft_window) + 1);
    }
```
→ copy round 与 neural round 共用**同一个 target 验证通道**（`target_verification`）；没有神经后端就没有可复用的 verify 帧。

**对本线的直接推论**：Coder390 现在 `--spec mtp` 起不来（MTP 头 5 个 `q4_0` 张量不被支持，`协作-给CodeBuddy-20261009.md:42`）、`--spec dflash2` 缺组件 ⇒ **`--ngram-draft-tokens` 在两条路上目前都开不了**；`--lookup-ngram` 虽然能启动（无 backend 校验），但因为它只挂在 MTP 分支，实际空转。

---

## B6. `docs/BONSAI_ngram_audit_report.md` 的结论提炼

### B6.1 三条核心结论（原文）

[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:14`:
```
| ngram 能不能加到这个模型上？ | **能**。ngram 是引擎侧特征，不需要模型权重改动；"模型没有 ngram"不构成障碍。 | 源码证实 |
```
[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:15`:
```
| ngram 能否与 MTP / DFLASH 共存？ | **能共存**。ngram 与 MTP/DFLASH 处在同一投机子系统的不同层，源码明确"优先用 ngram 命中覆盖草稿头"。 | 源码证实 |
```
[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:16`:
```
| 加上 ngram 解码速度是否翻番？ | **需修正预期**：在本模型同族（Qwen3.8-27B）上，ngram 叠加 MTP 仅 **+3%~13%**（仓库自带 2026-09-19 实测）；你观察到的"翻番"几乎可确定是 **MTP 本身的贡献**（MTP≈2.3–2.5× vs 无投机，与目标模型文档的 2.5× 一致）。 | 源码实测 + 目标文档交叉印证 |
```
[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:19`:
```
**一句话**：ngram 可加、可与 MTP/DFLASH 配合，但它是对 MTP 的"修剪式"增强（+几个百分点），不是独立的翻倍开关。把"翻番"归因给 ngram 是测量混淆，应隔离 MTP-only vs MTP+ngram 复测确认。
```

### B6.2 收益依据（报告 §5.1 的表，源自源码注释）

[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:92-98`:
```
n-gram    2      3      4      6      8     16     off
decode  135.6  148.9  143.5  145.2  148.7  148.5  144.9 tok/s
accept   0.87   1.00   0.96   0.97   1.00   1.00   0.964
- **n-gram=8 起每次命中都正确（accept=1.00）**，decode 较 off 仅 **+2.6%**（148.7 vs 144.9）。
```
→ 与源码注释逐字一致：
[EVIDENCE] `.../src/models/qwen3_5/program/speculative/lookup_draft.h:23-38`:
```
// MEASURED, 2026-09-19, Qwen3.8-27B on one 3090, `-pg 4096,256`, MTP with the optimised draft head,
// lookup preferred over the head's proposal whenever it matches:
//
//   n-gram    2      3      4      6      8     16     off
//   decode  135.6  148.9  143.5  145.2  148.7  148.5  144.9 tok/s
//   accept   0.87   1.00   0.96   0.97   1.00   1.00   0.964
...
// **The gain is small because there was little to win.** The draft head already accepts 95-96% on
// this model, so a perfect drafter is worth +5.5% at K=3 and +13% at K=5 and no more; this takes
// about half of that (K=5: 182.7 -> 191.0 tok/s).
```

### B6.3 ngram 真正能赢的场景

[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:17`:
```
| ngram 最大价值在哪？ | 输出"重复输入"的场景（摘要/编辑/RAG 作答/复用名字与结构的代码），以及 MTP 草稿窗口受限（高 K）时。 | 源码注释 |
```
[EVIDENCE] `.../src/models/qwen3_5/program/speculative/lookup_draft.h:13-17`:
```
// A draft model guesses what comes next from weights; this guesses it from the text already in
// front of it, which costs no device work at all. It is worthless on free-form prose and close to
// perfect wherever the output repeats the input -- summarising, editing, answering from a retrieved
// passage, or emitting code that reuses names and structure already on screen. Those are the cases
// a draft head is weakest on, which is why the two are complements rather than alternatives.
```

### B6.4 限制与风险（报告 §6）

[EVIDENCE] `docs/BONSAI_ngram_audit_report.md:116-120`:
```
1. **内存预算**：`NgramArchive` 默认 512MB 总量 / 128MB 单会话 / 32 会话 / 1024 来源；...
2. **冷启动收益低**：首个无重复模式的请求 ngram 几乎不贡献；收益随会话/来源积累上升。
3. **不要误以为 ngram 替代 MTP**：二者是正交增强。关掉 MTP 只开 ngram，在自由生成文本上接近纯解码...
4. **格式兼容仍是落地前提**：目标 `.ninfer` 包需 BONSAI 引擎能读 `gguf_blocks_v1`（见 4.3）。
5. **姊妹仓无 ngram**：确认 ngram 代码仅 BONSAI 有；...
```
（第 1 条与源码 `ngram.h:34-39` 的 `NgramArchiveLimits{512MB/128MB/32/1024}` 完全一致。）

### B6.5 对本线的可操作结论
1. 报告说"能加"是**引擎侧成立**，但本线当前 `--ngram-draft-tokens` 被 `--spec` 依赖卡死（B5.4），需先通 MTP 或 DFlash2 任一条。
2. 报告 §5.2 要求**隔离复测**（A: `--spec mtp` 关 ngram；B: `--spec mtp` + ngram），预期 B/A = 1.03–1.13（`BONSAI_ngram_audit_report.md:106`）。
3. 报告 §8.4 建议"优先调大 MTP 草稿窗口 K"，比单纯开 ngram 收益更大（`BONSAI_ngram_audit_report.md:137`）。

---

# C. 部署 / 启动器适配现状

## C7. 写死的模型名、路径、档位参数（逐条）

### C7.1 `ninfer_launcher.py`（42,207 字节）

| 行号 | 原文 | 是否需改 |
|---|---|---|
| 31 | `ENGINE = os.path.join(ROOT, "engine", "ninfer-serve-120a.exe")` | 路径随 ROOT 自适应；文件名仍指向**官方 sm_120a 件**，Coder390 无 dflash2 组件 ⇒ 用它跑 `--spec dflash2` 必失败 |
| 33 | `ENGINE_SELF = os.path.join(ROOT, "engine", "self-built-20261008", "ninfer-serve.exe")` | 目录**存在**（实测 `engine\self-built-20261008`），保留 |
| 34 | `ENGINE_PREV = os.path.join(ROOT, "engine", "self-built", "ninfer-serve.exe")` | 目录**不存在**（实测 `engine\` 下只有 `self-built-20261008`）⇒ 该选项必失败 |
| **40** | `MODEL = os.path.join(ROOT, "models", "Ternary-Bonsai-2-27B-ninfer-v3.ninfer")` | **必改** → `Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer` |
| 44 | `PORT_DEFAULT = 8094` | 与 `start-pq2-dflash.bat` 撞端口 |
| **51** | `KV_POOL_TOKENS = 17920` | 提示/告警文案用的池大小，随 `--kv-capacity` 走 |
| 54-60 | `KV_ENV = {NINFER_KV_WINDOW:16384, NINFER_KV_RETRIEVE:8192, NINFER_KV_RING:1, NINFER_HOST_PAGEABLE:1, NINFER_KV_REUSE_HOSTBACKED:1}` | 五开关（详见 C8）；`NINFER_KV_RING` 已空转 |
| 67-73 | `SPEC_OPTIONS`: `k1..k5` = MTP（`--spec mtp --draft-tokens i`），`d1..d15` = DFlash2（`--spec dflash2 --draft-tokens i --lm-head-draft`） | Coder390 两路当前都不通；MTP 档位上限写死 5（`range(1,6)`），源码允许 1..15 |
| 74-84 | `KV_OPTIONS`（k8v4/rk8v4/rk4v4/rk4v4-e8/rk2v4-e8/nvfp4/fp8/int8/bf16） | 可保留 |
| 85-96 | `CTX_OPTIONS`（32K…256K） | 可保留 |
| 97-111 | `KVCAP_OPTIONS`（17920 / auto / 16K…256K） | 可保留 |
| 112-116 | `HOSTKV_OPTIONS`（16384/8192/32768 → `--host-kv-mib`） | 可保留 |
| 117-121 | `PREFILL_OPTIONS`（1024/512/2048 → `--prefill-chunk`） | 可保留 |
| 122-128 | `THINK_OPTIONS`（`--default-reasoning-effort none/low/medium/high`、`--no-thinking`） | 可保留 |
| 129-136 | `MAXOUT_OPTIONS`（`--default-max-tokens`） | 可保留 |
| 137-142 | `VISION_OPTIONS`（on/overlay/cpu/off） | **默认必须改 off**（Coder390 无 vision 组件，见下） |
| 143-147 | `SAMPLE_OPTIONS`（shipped = 0.7/0.9/20 + presence 0 …） | 可保留 |
| 149-152 | `HEMOSTAT_OPTIONS`（on = `--kv-lease-growth --recover-invariant-failures`） | 注意官方 README 警告：超池构型下**不要**开 `--kv-lease-growth`（`README.md:218`） |
| 155-162 | `TB_OPTIONS`（`--default-thinking-budget`） | 可保留 |
| 163-167 | `CONC_OPTIONS`（`--max-concurrency`） | 环模式必须 1 |
| 168-171 | `PRESERVE_OPTIONS`（`--preserve-thinking`） | 可保留 |
| **192-194** | `DEFAULTS = {"spec": "d12", "kv": "k8v4", "ctx": "256k", "kvcap": "17920", "hostkv": "16384", "prefill": "1024", "think": "none", "tb": "none", "maxout": "32768", "vision": "on", "sample": "shipped", "conc": "1", "preserve": "off", "hemostat": "on"}` | **必改**：`spec` 默认 dflash2（Coder390 无组件）、`vision: "on"`（无 vision 组件） |
| 199-202 | `LEGACY_VALUE_MAP = {("spec","dflash2"):"d12", ("spec","mtp"):"k4"}` | 旧 profile 迁移表 |
| 222-231 | `PRESET_PROFILES`（起服-dflash档 / 备用-MTP档 / 省显存-无视觉 / 省显存-视觉CPU / 省显存-视觉overlay / 思考预算-16000 / 长文档-224K / 并发4-吞吐） | 与 json 里那批**不一致**（json 是磁盘上的真值，见 C7.2） |
| **270** | `argv = [MODEL, "--host", "127.0.0.1", "--port", str(port), "--model-id", "qwen3.8-27b"]` | **必改** `--model-id` |
| 283 | `argv += ["--max-shared-prefixes", "0"]   # 铁律：防打砖` | 保留 |
| 250-253 | `validate()` 检查 `MODEL` 是否存在 + ROOT 非 ASCII 告警 | ROOT = `J:\ninfer-kvmem` 纯 ASCII，OK |

**Coder390 无 vision 组件 ⇒ `--vision` 会直接抛 `missing component vision`**
依据：`ninfer_launcher.py:193` `"vision": "on"` + `VISION_OPTIONS["on"] = ["--vision"]`（`ninfer_launcher.py:138`）→ `--vision` → `config.cpp:323` `companion(directory, "vision")` → `schema.cpp:91` throw。而 `协作-给CodeBuddy-20261009.md:48` 明确"组件只有 `text` + `mtp`"。

### C7.2 `ninfer_launcher_profiles.json`（磁盘上的真值，8 个档位）

```
2-13   "起服-dflash档"     : spec=dflash2, kv=k8v4, ctx=256k, kvcap=17920, hostkv=16384, prefill=1024,
                            think=none, maxout=32768, vision=on,  sample=shipped
14-25  "备用-MTP档"        : spec=mtp,     kv=k8v4, ctx=256k, kvcap=17920, hostkv=16384, prefill=1024,
                            think=none, maxout=32768, vision=on,  sample=shipped
26-37  "省显存-无视觉"      : spec=dflash2, kv=k8v4, ctx=256k, kvcap=17920, hostkv=16384, prefill=1024,
                            think=none, maxout=32768, vision=off, sample=shipped
38-53  "180k k8v4 关视觉"   : spec=d7, kv=k8v4,  ctx=180k, kvcap=180k, hostkv=16384, prefill=1024,
                            think=medium, tb=16000, maxout=32768, vision=off, sample=shipped,
                            conc=1, preserve=on, hemostat=on
54-69  "160K K8V4 开视觉"   : spec=d7, kv=k8v4,  ctx=160k, kvcap=160k, … vision=on, conc=1, preserve=on, hemostat=on
70-85  "150K K8V4 开视觉"   : spec=d7, kv=k8v4,  ctx=150k, kvcap=150k, … vision=on, conc=1, preserve=on, hemostat=on
86-101 "224K NVFP4 视觉 "   : spec=d7, kv=nvfp4, ctx=224k, kvcap=224k, … vision=on, conc=1, preserve=on, hemostat=on
```
（逐行见 `ninfer_launcher_profiles.json:2`–`:101`）

**必须改的点**：
- 所有 `spec`：`dflash2` / `d7` / `mtp` → Coder390 当前只能 `k0`（无投机）或修好后的 `mtp`。
- 所有 `vision: "on"`：4 处（`起服-dflash档:11`、`备用-MTP档:23`、`160K K8V4 开视觉:64`、`150K K8V4 开视觉:79`、`224K NVFP4 视觉 :96`）→ 必须 `off`。
- `kvcap=17920` 与 `ctx=256k` 组合：靠 `NINFER_KV_WINDOW` 环才合法（C8）。
- `hemostat=on`（`--kv-lease-growth`）在超池构型下官方明确不建议（`README.md:218`）。

### C7.3 四个 `.bat`

**`start-pq2.bat`**（53 行）
| 行 | 原文 | 需改 |
|---|---|---|
| 18 | `if not defined MODEL set "MODEL=%ROOT%models\\Ternary-Bonsai-2-27B-ninfer-v3-mtponly.ninfer"` | **必改** |
| 38 | `set "ENGINE=%ROOT%engine\ninfer-serve-120a.exe"` | 文件存在，保留 |
| 27-31 | `NINFER_KV_WINDOW=16384 / NINFER_KV_RETRIEVE=8192 / NINFER_KV_RING=1 / NINFER_HOST_PAGEABLE=1 / NINFER_KV_REUSE_HOSTBACKED=1` | 五开关 |
| 44 | `--host 127.0.0.1 --port 8091 --model-id qwen3.8-27b` | `--model-id` **必改** |
| 45 | `--max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384` | 档位 |
| 46 | `--prefill-chunk 1024 --spec mtp --draft-tokens 4` | `--spec mtp` 当前不通（q4_0） |
| 47 | `--default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1` | 档位 |
| 48 | `--max-shared-prefixes 0` | 保留 |
| 49 | `--presence-penalty 0 --temperature 0.7 --top-p 0.9 --top-k 20` | 保留 |

**`start-pq2-dflash.bat`**（80 行）
| 行 | 原文 | 需改 |
|---|---|---|
| 45 | `set "MODEL=%ROOT%models\\Ternary-Bonsai-2-27B-ninfer-v3.ninfer"` | **必改** |
| 65 | `set "ENGINE=%ROOT%engine\ninfer-serve-120a.exe"` | 保留 |
| 71 | `--host 127.0.0.1 --port 8094 --model-id qwen3.8-27b` | `--model-id` **必改** |
| 72 | `--max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384` | 档位 |
| 73 | `--prefill-chunk 1024 --spec dflash2 --draft-tokens 12 --lm-head-draft --vision` | **必改**：`dflash2` 无组件、`--vision` 无组件 |
| 74 | `--default-max-tokens 32768 --default-reasoning-effort none --max-concurrency 1` | 档位 |

**`start-pq2-dflash-designc.bat`**（65 行）
| 行 | 原文 | 需改 |
|---|---|---|
| 31 | `set "MODEL=%ROOT%models\\Ternary-Bonsai-2-27B-ninfer-v3.ninfer"` | **必改** |
| 32 | `set "ENGINE=%ROOT%engine\\self-built-20261008\\ninfer-serve.exe"` | 目录存在，保留 |
| 56 | `--host 127.0.0.1 --port 8095 --model-id qwen3.8-27b` | **必改** `--model-id`；8095 与 `start-ptq1-mtp.bat` 撞端口 |
| 58 | `--prefill-chunk 1024 --spec dflash2 --draft-tokens 12 --lm-head-draft --vision` | **必改** |

**`start-ptq1-mtp.bat`**（54 行）
| 行 | 原文 | 需改 |
|---|---|---|
| 18 | `if not defined MODEL set "MODEL=%ROOT%models\\bonsai2_27b_ternary_ptq1_native_mtp.ninfer"` | **必改** |
| 32 | `set "NINFER_TERNARY_PTQ1_FAST=1"` | Coder390 非三元档 ⇒ 无意义（可删） |
| 45 | `--host 127.0.0.1 --port 8095 --model-id qwen3.8-27b` | **必改** |
| 47 | `--prefill-chunk 1024 --spec mtp --draft-tokens 4` | `--spec mtp` 当前不通 |

**`启动器.bat`**（8 行）
| 行 | 原文 | 需改 |
|---|---|---|
| 7 | `start "NInfer-Launcher" "D:\Python311\pythonw.exe" "%~dp0ninfer_launcher.py"` | **必改**为实际 pythonw 路径（`D:\Python311` 未必存在） |

### C7.4 必改清单汇总（最小改动集）

1. `ninfer_launcher.py:40` `MODEL` → `models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer`
2. `ninfer_launcher.py:193` `DEFAULTS["vision"]` → `"off"`；`DEFAULTS["spec"]` → `"k0"`（待 MTP 修好后改 `"k4"`）
3. `ninfer_launcher.py:270` `--model-id qwen3.8-27b` → Coder390 的 id
4. `ninfer_launcher.py:34` `ENGINE_PREV` 指向不存在的 `engine\self-built\` → 删或改指 `self-built-20261008`
5. 四个 bat 的 `MODEL`（`:18`/`:45`/`:31`/`:18`）与 `--model-id qwen3.8-27b`
6. 两个 dflash bat 的 `--spec dflash2 … --lm-head-draft --vision` → 去掉 `--vision`，`--spec` 待定
7. `ninfer_launcher_profiles.json` 全部 `vision:on` → `off`；`spec` 值重定
8. `启动器.bat:7` pythonw 路径

---

## C8. KVMem 相关开关：怎么给、在哪读、长上下文需要哪些

### C8.1 五开关（启动器/ bat 里给的六个环境变量）

[EVIDENCE] `ninfer_launcher.py:53-60`:
```
# KVMem 五开关：缺一 = 起得来但静默答错（缓存命中率高、中段答错、零报错）。GUI 内固定注入。
KV_ENV = {
    "NINFER_KV_WINDOW":          "16384",
    "NINFER_KV_RETRIEVE":        "8192",
    "NINFER_KV_RING":            "1",
    "NINFER_HOST_PAGEABLE":      "1",
    "NINFER_KV_REUSE_HOSTBACKED": "1",
}
```

| 变量 | 源码读取点 | 含义（原文） |
|---|---|---|
| `NINFER_KV_WINDOW` | `startup.cpp:48-52`、`serve_options.cpp:1124-1127`、`context.cpp:2022-2025`、`startup.cpp:145-159` | 设备常驻窗口（token 数，按页整除）；**>0 即开环**，唯一被两道门共同读取的开关 |
| `NINFER_KV_RETRIEVE` | `context.cpp:2045-2049`、`:2054-2057`、`:2062-2068`、`:2089-2092` | 每次查询从 Host 取回的页数预算；未设时走自动回退 |
| `NINFER_KV_RING` | **源码里已无任何 getenv**（仅在 `serve_options.cpp:1118-1123` 的注释中被提及） | **空转**。B30 已修：两道门曾读不同变量，现统一读 `NINFER_KV_WINDOW` |
| `NINFER_HOST_PAGEABLE` | `program_impl.cpp:400-407`、`arena.cu:636-644` | Host KV 用可分页内存（不计入 WDDM 显存上限），代价是 memcpy 走 bounce buffer |
| `NINFER_KV_REUSE_HOSTBACKED` | `startup.cpp:58-61`、`materialization.cpp:825` | 允许"设备池装不下的检查点整段登记、按需物化" |

**环开关的唯一真值**：
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:43-52`:
```
// LOCAL PROTOTYPE (KVMem-style ring): the experimental ring is opt-in through the same
// environment switch the engine-side gate reads (NINFER_KV_WINDOW). Defined once here so both
// validation sites stay in step.
...
bool ring_requested() {
    const char* text = std::getenv("NINFER_KV_WINDOW");
    if (text == nullptr || text[0] == '\0') { return false; }
    return std::strtol(text, nullptr, 10) > 0;
}
```
[EVIDENCE] `.../src/serve/serve_options.cpp:1124-1132`:
```
    const bool kv_ring_enabled = [] {
        const char* text = std::getenv("NINFER_KV_WINDOW");
        return text != nullptr && std::strtol(text, nullptr, 10) > 0;
    }();
    if (!kv_ring_enabled && options.kv_capacity.mode == KvCapacityMode::Explicit &&
        options.kv_capacity.explicit_tokens < options.max_context) {
        throw std::invalid_argument("--kv-capacity must be at least --max-context "
                                    "(set NINFER_KV_WINDOW=<window tokens> to allow the experimental ring)");
    }
```
→ **`--kv-capacity 17920 < --max-context 262144` 之所以合法，全靠 `NINFER_KV_WINDOW=16384`**。去掉它就启动即拒。

**`NINFER_KV_RING` 是空转的铁证**：
[EVIDENCE] `.../src/serve/serve_options.cpp:1118-1123`:
```
    // B30 (fixed 2026-10-07): this gate used to read NINFER_KV_RING, while the engine-side gate
    // (models/qwen3_5/program/planning/startup.cpp, ring_requested()) reads NINFER_KV_WINDOW. The
    // engine's own advice therefore named the WRONG variable: setting only NINFER_KV_RING passed here
    // and then died at startup with "kv_capacity must be at least max_context", never serving. Both
    // ends now read NINFER_KV_WINDOW with the same predicate (present, non-empty, strtol > 0), and the
    // message below names that variable.
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/README.md:224`:
```
| 其它已知边界（B20） | … 一条「仅设 `NINFER_KV_RING` 才崩」的反馈**已核、属实、已修** —— 环的两道门读的不是同一个环境变量，照引擎自己的提示操作必崩，见 **B30** |
```
（实测：全 `src\` 搜索 `getenv("NINFER_KV_RING"` → 0 命中，只在上述注释里出现。）

### C8.2 其它 KVMem 环境变量

| 变量 | 位置 | 说明 |
|---|---|---|
| `NINFER_KV_SINK` | `startup.cpp:108-114`、`context.cpp:2036-2040` | attention sink 钉住的页数，**默认 4 页 = 256 token** |
| `NINFER_KV_NEIGHBOR_PAGES` | `context.cpp:1701` | 邻居页扩展 |
| `NINFER_KV_RETRIEVE_AUTO` | `context.cpp:2062-2068` | 检索预算自动回退的关闭开关（默认开） |
| `NINFER_KV_RETRIEVE_SHARE` | `context.cpp:2089-2092` | 取回预算占池百分比，默认 50 |
| `NINFER_TERNARY_KVMEM` / `NINFER_TERNARY_KVMEM_SCORE` | `startup.cpp:1242-1268` | 内容打分总开关；**环一开就默认 ON** |
| `NINFER_TERNARY_KVMEM_SCORE_QUERY_TAIL` | `official-repo/ninfer-fusion-kvmem/README.md:87` | 打分看的查询尾部 token 数（示例 64） |
| `NINFER_TERNARY_PTQ1_FAST` | `start-ptq1-mtp.bat:32`；`src/ops/linear/t2/t2_dispatch.cpp:112` | 三元 PTQ1 快路，Coder390 非三元 ⇒ 无意义 |

打分默认开的证据：
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1261-1267`:
```
    if (ring_requested() && ops::detail::kvmem_score_enabled() &&
        std::getenv("NINFER_TERNARY_KVMEM_SCORE") == nullptr) {
        std::fprintf(stderr,
                     "[ring] content scoring ON by default (the ring is configured): retrieval ranks pages "
                     "by the query-conditioned content score. Set NINFER_TERNARY_KVMEM_SCORE=0 (or the "
                     "master switch NINFER_TERNARY_KVMEM=0) to fall back to the lexical ranking (that is "
                     "the negative control, not a tuning knob).\n");
```

### C8.3 `--kvmem-*` CLI 选项在本树**未接线**（重要）

`--kvmem-method` / `--kvmem-budget` / `--kvmem-block-tokens` / `--kvmem-sink-blocks` 等"17 个新命令行开关"只存在于 qw3 策略层头文件，**`serve_options.cpp` 里没有任何解析**：
[EVIDENCE] `.../src/ops/kvmem/qw3/kvmem_store.hpp:246-258`:
```
struct KvMemStoreConfig {
    KvMemGcConfig gc;
    uint32_t block_tokens = 128;     // --kvmem-block-tokens
    uint32_t select_budget = 131072; // --kvmem-budget (semantic window tokens)
    ...
    KvMemMethod select_method = KvMemMethod::Retrieval; // --kvmem-method
```
（实测：`src\serve\serve_options.cpp` 全文搜索 `kvmem` → 0 命中；`src\` 全树搜索 `"--kvmem` → 只命中上述 qw3 头文件与注释。）
→ **本线 ninfer-serve 不接受任何 `--kvmem-*` 参数**，写了会 `unknown argument` + exit 1（`serve_options.cpp:709-711` 的 `else { throw }`，见 `已知问题-初期版本.md` B22 复核）。

### C8.4 长上下文必需的 CLI 参数与组合约束

必需/关键项：
- `--max-context N`（上下文上界）
- `--kv-capacity N|auto`（设备池 token 数；`< --max-context` **仅在 `NINFER_KV_WINDOW>0` 时合法**，`serve_options.cpp:1128-1132`）
- `--host-kv-mib N`（Host KV 预算，`serve_options.cpp:866-872`，默认 8192；启动器给 16384）
- `--kv-dtype k8v4|nvfp4|fp8|…`（`serve_options.cpp:158-171` 帮助文本）
- `--prefill-chunk N`（必须是 128 的正整数倍，`serve_options.cpp:1145-1147`）
- `--max-shared-prefixes 0`（防 B01 打砖，`README.md:212`）

组合约束（启动守卫，违反即抛）：
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1269-1276`:
```
    if (ring_requested() && inputs.max_concurrency > 1) {
        std::fprintf(stderr,
                     "[ring] NINFER_KV_WINDOW (KVMem ring) serves ONE active sequence: the ring cannot "
                     "reclaim another lane's Device pages.\n"
                     "       Run with --max-concurrency 1, or unset NINFER_KV_WINDOW.\n");
        throw std::invalid_argument(
            "NINFER_KV_WINDOW (KVMem ring) requires --max-concurrency 1");
    }
```
[EVIDENCE] `.../src/models/qwen3_5/program/planning/startup.cpp:1299-1308`:
```
    if (impl->context_cache.enabled && impl->context_cache.mode == ContextCacheMode::Hybrid) {
        if (ring_requested()) {
            // LOCAL PROTOTYPE (KVMem-style ring): this branch zeroes the Host KV budget below, so
            // `host_kv_arena` is never created and the ring loses its only demotion target -
            // attention would silently stay dense. Refuse loudly instead of degrading in silence.
            ...
                         "[ring] NINFER_KV_WINDOW (KVMem ring) conflicts with ContextCacheMode::Hybrid: "
                         "Hybrid zeroes the Host KV budget, so the ring has no demotion target.\n"
                         "       Use Legacy mode with --host-kv-mib, or unset NINFER_KV_WINDOW.\n");
```
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/README.md:210-211`:
```
| 开环或内容打分时需要多并发 | 当前实现只支持 `--max-concurrency 1`；源码启动守卫会拒绝不支持的组合（B06） |
| KVMem 环与 hybrid prefix cache 同开 | 不支持；环需要 Legacy Host KV 层，启动示例不使用 `--use-alt-prefix-caching` |
```

**本线启用长上下文的最小参数集**：
```
set NINFER_KV_WINDOW=16384
set NINFER_KV_RETRIEVE=8192
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
（NINFER_KV_RING=1 可留作历史兼容，但已空转）

ninfer-serve.exe models\Qwen3.8-27B-Coder390-...-MTP.ninfer ^
  --max-context 262144 --kv-capacity 17920 --kv-dtype k8v4 --host-kv-mib 16384 ^
  --prefill-chunk 1024 --max-concurrency 1 --max-shared-prefixes 0
```
⚠️ 附加告警（官方实测，与本线超池构型直接相关）：
[EVIDENCE] `official-repo/ninfer-fusion-kvmem/README.md:218-219`:
```
| 超池构型（设备池 < 逻辑上下文）要保住输出 | **不要开 `--kv-lease-growth`**（本仓默认**关**；F2 之后的批次默认开，照抄会命中"输出被砍到 2 个 token"那条回归）。⚠️ 反过来，`--no-kv-lease-growth` 这类**否定式开关在本仓不存在**，写了会**启动即拒**（见 B22） |
| **超池 + 检索**（任何 dtype） | 超池题的**对错取决于检索是否开着**：`rk4v4` 实测 **检索关 ⇒ 0/6 全静默错、检索开(8192) ⇒ 6/6 命中**（B28）。⇒ 超池时**别关检索**；并且读引擎那行 over-pool 告警（`prompt > pool`）——**它出现就说明该请求的答案不许当已核** |
```
→ 本线 launcher 的 `hemostat=on` 默认带 `--kv-lease-growth`（`ninfer_launcher.py:150`），**在 17920 池 + 256K 上下文这种超池构型下与官方建议冲突**，需重新裁决。

---

## 附：本次调研用到的实测命令（可复现）

```
# 1) 工作区内是否存在 DFlash 权重目录
Get-ChildItem -Path "J:\ninfer-kvmem" -Directory -Recurse -Filter "*DFlash*"
#   → 空（无任何结果）

# 2) 根与关键资产
Get-ChildItem -Path "J:\ninfer-kvmem" -Force
#   → engine/ models/ refs/ official-repo/ build/ docs/ tools/ safety_backups/ .temp/ .git/
Get-ChildItem -Path "J:\ninfer-kvmem\models"
#   → Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer  (13,272,798,720 bytes)
Get-ChildItem -Path "J:\ninfer-kvmem\engine"
#   → self-built-20261008\ , ninfer-serve-120a.exe, cublas64_13.dll ...
```

## 附：证据来源索引（本报告引用的主要文件）

引擎源码（`official-repo/ninfer-fusion-kvmem/src-tree/fusion-engine-src/`）
- `src/artifact/schema.cpp` · `src/artifact/schema.h`
- `src/models/qwen3_5/config.cpp`
- `src/models/qwen3_5/load.cpp` · `load/dflash.cpp` · `load/dflash2.cpp` · `load/text.cpp`
- `src/models/load_options.h`
- `src/models/qwen3_5/program/planning/startup.cpp` · `startup.h`
- `src/models/qwen3_5/program/decode.cpp` · `prefill.cpp` · `program_impl.cpp` · `program_impl.h`
- `src/models/qwen3_5/program/storage/context.cpp`
- `src/models/qwen3_5/program/transactions/materialization.cpp`
- `src/models/qwen3_5/program/ngram_proposer.h` · `src/models/qwen3_5/ngram.h` · `src/models/qwen3_5/ngram.cpp`
- `src/models/qwen3_5/program/speculative/lookup_draft.h`
- `src/models/qwen3_5/frontend/frontend.cpp` · `prepared_prompt.h`
- `src/serve/serve_options.cpp` · `src/product/speculative_options.h` · `src/include/ninfer/types.h`
- `src/core/arena.cu` · `src/ops/kvmem/qw3/kvmem_store.hpp`
- `docs/maintainer/dflash.md` · `docs/weight-conversion.md` · `tools/README.md` · `tools/upgrade_ninfer_v2_to_v3.py` · `tools/convert/*`
- `model-cards/Qwen3.8-27B-NInfer/*` · `model-cards/Qwen3.8-27B-nvfp4-NInfer/*`

融合仓文档（`official-repo/ninfer-fusion-kvmem/`）
- `README.md` · `已知问题-初期版本.md` · `我方-新增能力与已解决问题.md` · `编译指南-怎么编.md`

参考发放包（`refs/01-沈三殊-发放包/新/急速档V2/`）
- `README.md` · `07-模型与制品.md` · `agent/manifest.json` · `start-8085-dflash2.bat` · `start-8088-dflash2-128k.bat`
- `src-tree/ninfer-4090w-ternary/tools/convert/qwen3_8_27b/{convert.py,dflash2_inventory.py,dflash2_recipe.py}`

本线（`J:\ninfer-kvmem/`）
- `ninfer_launcher.py` · `ninfer_launcher_profiles.json` · `启动器.bat`
- `start-pq2.bat` · `start-pq2-dflash.bat` · `start-pq2-dflash-designc.bat` · `start-ptq1-mtp.bat`
- `docs/BONSAI_ngram_audit_report.md` · `docs/协作-给CodeBuddy-20261009.md` · `docs/交接-工作区迁移-TeleAgent-20261009.md` · `docs/教程-KVMem与短测-给agent与使用者.md`
