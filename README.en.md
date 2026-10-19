# Ninfer-KVMem-Async

**A 27B model (Qwen3.8-27B-Coder390) on a 16 GB consumer GPU — with an *Async Page Pipeline* that overlaps KV page movement with decoding.**

> This is a condensed English edition. The full project record (build history, per-decision evidence) is in Chinese:
> **中文完整版 → [README.md](README.md)**
> Hardware baseline: RTX 5080 16 GB + 128 GB RAM, Windows. **All numbers measured, not projected.**

## Latest (2026-10-19): hang root cause closed + valley trigger pinned — hang and valley are two different problems

**Three-binary verdict matrix (§135–§136)** — identical conditions (Gen5 PCIe + ~400 MiB external VRAM pressure + pool-edge, free VRAM <400 MB):

- **S13 production build (no symbols) = hang** — decode drops to **0**, probes time out, requests **never return** (5/5);
- **sym3 / offi (symbol-linked builds) = deep valley but finish** — **41 / 44.5 tok/s**, 6/6 requests completed.
  ⇒ **Hang culprit = missing symbol linkage** (the `/Zi` + `/DEBUG` link switches change the linked layout itself — it is not "symbols let us see the hang", it is "adding symbols fixed the hang"; toolchain version 14.43/14.44 ruled out). The **valley (slow but completes) exists in all three builds** — a load × environment phenomenon, not a build defect.

**Valley trigger = AND of three conditions** (six-batch full matrix): **Gen5 + external VRAM pressure ≥400 MiB + free VRAM <400 MB (pool-edge)** — miss any one and it does not trigger (8/8 healthy with zero pressure across both builds; Gen4: 0/68 probes entered the valley). WHEA AER storms (peak 1857/min) time-aligned shot-by-shot: **no causal link to the valley**. Host BIOS has been moved to PCIe **Gen4** (WHEA mitigation); numbers across the Gen5/Gen4 divide are not directly comparable.

**arch miscompile root cause closed (§128)**: the sym build's "startup hang" was a missing `-DCMAKE_CUDA_ARCHITECTURES=120a` — CMake defaulted to sm_86, and this sm_120a device fell into a PTX JIT grind (357 kernels, ~50 min) that looked exactly like a hang. Now mandatory: explicit arch flag + `cuobjdump` product acceptance (384 sm_120a cubins, 0 sm_86).

**Async pipeline DEPTH tiers (§137, shallow load)**: D2 (default) **187.1 > D0 (sync) 183.6 > D1 182.6 tok/s** — under shallow load the async pipeline has no work to do; its value scales with working-set depth (10-16 deep multi-turn: **~20% net**, deepest segment **≈2.0×**, ring stalls 33→2). Depth 3/4 remain untested at deep load; default stays 2.

**Valley manhunt milestones (2026-10-16, still standing)**: on-demand reproduction under the declared domain (probe speed drops to 1/25); mechanism localized to **entirely host-side submit calls** (`submit ≈ wall`, `wait = sync ≈ 0`); **PDL ruled out**; ≈2-minute [minimal reproduction protocol](docs/Minimal-Reproduction-Valley-On-Demand-20261016.md) available for the community / upstream / driver side.

## What it is

The **KVMem idea as the data layer** (KV pages virtualized; on-demand recall — *"it fits in"*) plus our **Async Page Pipeline as the transport layer** (page movement pipelined against decode — *"it never stalls for pages"*).

- OS analogy: KVMem = virtual memory + demand paging; the async pipeline = asynchronous I/O (background writeback / readahead).

Three generations:

| Gen | Repo | Contribution |
|---|---|---|
| 1 | [paicat1/Bonsai-27B-NInfer](https://github.com/paicat1/Bonsai-27B-NInfer) | Bonsai-2 quantization, MTP head, vision graft; the engine line |
| 2 | [paicat1/Bonsai-27B-NInfer-kvmem](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem) | **KVMem ring** (active retrieval): small device pool + host offload |
| 3 | [paicat1/Ninfer-KVMem-Async](https://github.com/paicat1/Ninfer-KVMem-Async) — this repo | **Async Page Pipeline** + pool calibration + correctness engineering |

## Key measured results

| Item | Value |
|---|---|
| Pool calibration | **65,536** (SWIFT 1.5 + `rk8v4`, graph 192; Q2LYNN baseline 51,200; 64K needs graph allowance ≥64 MiB + clean desktop) |
| Deep over-pool | 74.4K context (pool ~65K) → **114.4 tok/s** |
| Peak / steady | peak **400+ tok/s**; 1-hour average **220 tok/s** |
| Lossless gate (A2) | in-pool vs first-over-pool outputs **byte-identical** |
| Same-condition ON/OFF (2026-10-16) | deep multi-turn: async **~20% faster** (r = 0.80); deepest segment ≈ **2.0×**; shallow load: a tie (r = 1.13) |
| Valley status | **trigger pinned: AND of Gen5 + ≥400 MiB + pool-edge (<400 MB free)**; blocked in driver-internal submit; PDL ruled out; line-level root cause pending |
| Hang status | **root cause closed = missing symbol linkage** (no-symbol build hangs under Gen5+pressure; symbol-linked builds complete at 41–44.5 tok/s); C12 idle-first-request hang still open |
| Environment | host runs PCIe **Gen4** (Gen5 triggered WHEA AER storms); any CUDA build must pass explicit `sm_120a` arch + `cuobjdump` acceptance |

## Materials

- **Slide deck (English, 18 pages)**: [`.pptx`](docs/Async-Page-Pipeline-Technical-Brief.pptx)
- **Slide deck (Chinese)**: [`.pptx`](docs/异步页流水-技术说明.pptx)
- **Public technical note** (CN, plain-language): [`docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md`](docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md)
- **Build history** (the full record, the place to dig in): [`docs/ninfer-kvmem-项目构建史.md`](docs/ninfer-kvmem-项目构建史.md)（§1–§140）
- **Valley root-cause engineering history** (CN): [`docs/工程史-死亡谷根因排查与确定-CB-20261017.md`](docs/工程史-死亡谷根因排查与确定-CB-20261017.md)（the crash-vs-valley separation verdict: build history §136）

## Quick start (abridged)

Given an engine build and model file: serve via `engine_ctl.ps1` (or the GUI launcher's presets) and call the OpenAI-compatible endpoint at `http://127.0.0.1:8094/v1`.

- Current production profile: model `swift15_iq3s_mtp.ninfer` (IQ3_S, 11.3 GiB, loaded in 9.4 s) with `rk8v4` KV tier @ pool **65,536** (deep 60K: 143.7 tok/s, 64% acceptance);
- **Build/run hard rules (2026-10-18/19)**: any CUDA build must pass explicit `-DCMAKE_CUDA_ARCHITECTURES=120a` and be accepted by `cuobjdump` (384 sm_120a cubins, 0 sm_86); for Gen5 / external-pressure runs use **symbol-linked builds** (`/Zi` + `LINK=/DEBUG`) — the no-symbol build hangs there while symbol-linked builds complete;
- Full launch parameters: [`docs/引擎启动参数与配置档-20261014.md`](docs/引擎启动参数与配置档-20261014.md); step-by-step reproduction: see README.md "从零复现指南".

## Known limits (honest list)

- **Valley not closed** (line-level root cause pending): triggers only under the **declared domain — Gen5 + external VRAM pressure ≥400 MiB + pool-edge (free <400 MB)**, not under arbitrary conditions (reported as "a stably triggerable dose exists inside the declared domain, 3/3, n=3, single machine"); the only confirmed mitigation is *avoid VRAM contention* (this host now runs Gen4); during a valley, bare decoding without speculation (~56 tok/s) is a workaround;
- **Hang (requests never return)** — root-caused to **missing symbol linkage** in no-symbol builds under Gen5+pressure (2026-10-19 verdict matrix); use symbol-linked builds (`offi` / `sym3`) in that scenario. **C12** (hang on the first request after long idle; never reproduced, 2×2 attempts all normal) stays open — restart the engine to recover;
- **WHEA / PCIe**: Gen5 + VRAM contention triggered WHEA AER storms on this machine; BIOS downgraded to Gen4. Numbers across the Gen5/Gen4 divide are not directly comparable;
- **Single concurrency** (KVMem ring constraint); multi-session is not covered;
- 256K is the native context cap; **pool must be ≥ expected max prompt** (over-pool turns are usable, but middle content correctness depends on the retrieval switches — B28).

## Thanks

- **KVMem authors** — paper *KVMem: Virtualizing Million-Token Agent Workspaces on a Consumer GPU* (arXiv 2609.04852): Di Chai, Leye Wang, Zeshen Su, Zhiguo Xia, Zhihang Yu;
- **Shensanshu** — the first to combine NInfer with KVMem (the starting point of this line);
- **tancau** — the KVMem ring original implementation and our direct discussions; **nerkyor / Merkyor** — model weights.
- Full acknowledgement list: see [README.md § 致谢](README.md).

## License

Apache-2.0 (see `LICENSE` / `NOTICE.md`). This repository is an upstream-derived deployment & verification project, not an official distribution; upstream component licenses are listed in README.md.
