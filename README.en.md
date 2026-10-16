# Ninfer-KVMem-Async

**A 27B model (Qwen3.8-27B-Coder390) on a 16 GB consumer GPU — with an *Async Page Pipeline* that overlaps KV page movement with decoding.**

> This is a condensed English edition. The full project record (build history, per-decision evidence) is in Chinese:
> **中文完整版 → [README.md](README.md)**
> Hardware baseline: RTX 5080 16 GB + 128 GB RAM, Windows. **All numbers measured, not projected.**

## Latest (2026-10-16): same-condition proof for the async pipeline + valley manhunt milestone

**Deep multi-turn ON/OFF ablation** — multi-turn growth + partial prefix-cache reuse + long outputs; 2.3–3.5× over-pool (context ~75.3K → ~152K → ~229K vs pool 65,536); the two arms differ *only* by the `NINFER_ASYNC_DEMOTE` switch:

- Removing the async pipeline (sync fallback) costs **~20% decode** — deep-segment median **188.1 → 234.9 tok/s (r = 0.80)**; the **deepest segment (3.5× over-pool) is ≈ 2.0×** (119.4 → 235.6); ring stalls drop **33 → 2** (~16×);
- Shallow / one-shot over-pool: a tie (r = 1.13) ⇒ the async value **scales with working-set depth** — exactly what it was designed for;
- Honest bounds: n = 3 per arm, single machine, healthy period; the sync arm did not "die" (the stronger historical "multi-turn = death" claim did not reproduce — what we observe is "usable but slow").

**Valley (a transient slow state) manhunt** — after **120 hours of uninterrupted engineering stress testing**:

- **On-demand reproduction**: external VRAM pressure (~1.2 GiB) puts the engine into the valley on demand (probe speed drops to 1/25), recovers on release, repeatable ⇒ no more "waiting for the window";
- **Mechanism localized**: in-valley time is spent **entirely in host-side submit calls** (`submit ≈ wall`, `wait = sync ≈ 0`) ⇒ the blockage lives in the engine's own submission path (driver-internal blocking); **PDL (the former prime suspect) is ruled out** by an ON/OFF reversal counter-example; host paths / page tiers / pool size / throttling are all experimentally excluded;
- Remaining: pin the exact blocking point down to line level — a **~2-minute minimal reproduction protocol** is available for the community / upstream / driver side.

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
| Pool calibration | **81,920 tokens** (16 GB card, low-bit KV tier) |
| Deep over-pool | 74.4K context (pool ~65K) → **114.4 tok/s** |
| Peak / steady | peak **400+ tok/s**; 1-hour average **220 tok/s** |
| Lossless gate (A2) | in-pool vs first-over-pool outputs **byte-identical** |
| Same-condition ON/OFF (2026-10-16) | deep multi-turn: async **~20% faster** (r = 0.80); deepest segment ≈ **2.0×** |
| Valley status | **on-demand reproducible**; blocked in driver-internal submit; PDL ruled out |

## Materials

- **Slide deck** (18 pages, Chinese): [`.pptx`](docs/异步页流水-技术说明.pptx) · [**PDF — viewable directly on GitHub**](docs/异步页流水-技术说明.pdf)
- **Public technical note** (CN, plain-language): [`docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md`](docs/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md)
- **Build history** (the full record, the place to dig in): [`docs/ninfer-kvmem-项目构建史.md`](docs/ninfer-kvmem-项目构建史.md)

## Quick start (abridged)

Given an engine build and model file: serve via `engine_ctl.ps1` (or the GUI launcher's presets) and call the OpenAI-compatible endpoint at `http://127.0.0.1:8094/v1`.

- Current production profile: model `swift15_iq3s_mtp.ninfer` (IQ3_S, 11.3 GiB, loaded in 9.4 s) with `rk8v4` KV tier @ pool **65,536** (deep 60K: 143.7 tok/s, 64% acceptance);
- Full launch parameters: [`docs/引擎启动参数与配置档-20261014.md`](docs/引擎启动参数与配置档-20261014.md); step-by-step reproduction: see README.md "从零复现指南".

## Known limits (honest list)

- **Valley not closed** (trigger source unresolved): on-demand reproducible; the only confirmed mitigation is *avoid VRAM contention*; during a valley, bare decoding without speculation (~56 tok/s) is a workaround;
- **Single concurrency** (KVMem ring constraint); multi-session is not covered;
- 256K is the native context cap; **pool must be ≥ expected max prompt** (over-pool turns are usable, but middle content correctness depends on the retrieval switches — B28).

## Thanks

- **KVMem authors** — paper *KVMem: Virtualizing Million-Token Agent Workspaces on a Consumer GPU* (arXiv 2609.04852): Di Chai, Leye Wang, Zeshen Su, Zhiguo Xia, Zhihang Yu;
- **Shensanshu** — the first to combine NInfer with KVMem (the starting point of this line);
- **tancau** — the KVMem ring original implementation and our direct discussions; **nerkyor / Merkyor** — model weights.
- Full acknowledgement list: see [README.md § 致谢](README.md).

## License

Apache-2.0 (see `LICENSE` / `NOTICE.md`). This repository is an upstream-derived deployment & verification project, not an official distribution; upstream component licenses are listed in README.md.
