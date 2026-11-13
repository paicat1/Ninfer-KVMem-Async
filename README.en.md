# Ninfer-KVMem-Async

**Running 27B-class models (three tiers: Coder390 / SWIFT-1.5 / GSQ-RCO IQ3_S) on an architecture proven across two prior generations of engineering — 16 GB consumer cards, long-context Agent sessions.**

> This is the full English edition, translated section-by-section from the Chinese README.
> **中文完整版 → [README.md](README.md)** — the authoritative project record (build history, per-decision evidence chains) is in Chinese.
> Hardware baseline: RTX 5080 16 GB + 128 GB RAM, Windows. **All numbers are measured, not projected.**

## What this repo does (30-second version)

Run a **27B model** on a **16 GB consumer GPU** for **long-context Agent sessions** — it does not fit natively (a million-token KV ≈ 32 GiB). **KVMem virtualization** (tiered KV storage + on-demand recall) makes it *"fit"*; this repo's core increment is the **Async Page Pipeline**: page movement and decode computation run **pipelined in parallel** (movement never waits for decode, decode never waits for pages), so "over-pool" no longer means "slower". It ships with the correctness engineering (in-pool vs over-pool outputs **byte-identical**) and a full set of measured calibrations (pool / KV precision tier / speculation tier).

- **Where it came from**: three generations of engineering in relay — Bonsai-27B-NInfer (engine & quantization) → Bonsai-27B-NInfer-kvmem (KVMem ring) → this repo (async page pipeline); see the three-generation table below.
- **Current status (2026-11-13)**: **multi-tier production-usable** — three model tiers (Coder390 / SWIFT-1.5 / GSQ-RCO IQ3_S), each with **both MTP and DFlash2 heads in one artifact** (`--spec` switch); **iGPU display channel is the #1 speed variable** (19–60% faster than dGPU at the same pool); pool ceilings **40,960–126,976** depending on artifact and head, the top tier hitting the 16 GB physical limit; two known open issues = ① the transient slow state (the "Death Valley": trigger pinned to three AND conditions = Gen5 + external pressure ≥400 MiB + pool-edge; line-level root cause pending) ② **C12 — the first request after a long idle may hang permanently** (never reproduced) — additionally: **the "hang" attribution is closed = missing symbol linkage** (symbol-linked builds are immune; see ★2026-10-18/19).
- **How to read this repo**: below are the key milestones and the complete campaign list (curated); the round-by-round full record (with the evidence chain behind every decision) is in the [Build History](docs/ninfer-kvmem-项目构建史.md) (Chinese);
- **Want it running**: three steps — build engine / download model / serve — in [Quick start](docs/00-入口与说明/快速上手-自助路径.md).

Three generations:

| Gen | Repo | Contribution |
|---|---|---|
| 1 | [**paicat1/Bonsai-27B-NInfer**](https://github.com/paicat1/Bonsai-27B-NInfer) (main=project layer / engine-main=engine layer, one repo, two branches) | **Bonsai-2-27B ternary quantization (2.125 bit, 9.81 GiB) running on NInfer**: Ambolio port + CraneBW kernels, CMake changes for `89\|120a`, self-produced v2 artifacts; Device/Host **two-tier KV** (passive capacity); MTP / DFlash2 speculation. Extremes: prefill 2,850 / decode 396.9 tok/s |
| 2 | [**paicat1/Bonsai-27B-NInfer-kvmem**](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem) | **KVMem ring (active retrieval)**: small VRAM pool + host offload, `--kv-capacity` may be smaller than the context, content-scored SELECT, five switches (six in this repo); **hybrid speculation**: dflash2 (K1-15) + MTP (K1-5) + ngram, **K=7 sweet spot** (collapse at K≥10), acceptance-rate corpus effect (counting numbers 91% vs prose 3.7–13.4%); a fully self-built engine (MSVC patches ×7 + Design C fixing "thinking-block stop with empty content") + dual-engine comparison; self-built GUI launcher and serve_tee log tool. Extremes: **prefill 3,820 / decode 748.6 tok/s** (real workload, 19 requests, acceptance 35.7–94.4%) |
| 3 | [**paicat1/Ninfer-KVMem-Async**](https://github.com/paicat1/Ninfer-KVMem-Async) (this repo; renamed from Qwen38-27B-NInfer-kvmem on 2026-10-13) | Bigger model: **Qwen3.8-27B-Coder390-EfficientThink** — self-converted MTP head (iq4_nl), three linked thinking-fuse defects fixed (W1-W4), growth verdict, pool calibration 51,200, vision-tower graft, 256K logical context; **and serves as the landing prep for Qwen 4 27B (Bonsai/NInfer formats)**. 2026-10-18/19 closing trio: arch miscompile root cause closed, **hang culprit verdict (missing symbol linkage)**, valley trigger three conditions pinned |

> Hardware baseline: RTX 5080 16 GB + 128 GB RAM, Windows; all conclusions are measured (not projected).

---

## From two repos' results to today: inheritance and the full campaign list

### Inheritance: the arsenal left by the two prior repos

| Weapon | From | Role in this repo |
|---|---|---|
| **Hybrid speculation (dflash2 + MTP + ngram) & tuning methodology** | Repo 2: K=7 sweet spot, collapse at K≥10, **acceptance rate is a strongly corpus-dependent metric** (synthetic text won't do), real-workload 748.6 peak | This repo's MTP k3 / DFlash2 K5 + ngram tiers and the acceptance/speed statistics of `test_ab_arm1.py` are all accepted in this pattern |
| **KVMem ring (active-retrieval KV offload)** | Repo 2: small VRAM pool + host offload, content-scored SELECT, five switches (this repo adds sink → six; missing any one silently answers wrong), needle-embedding liveness methodology (question in an independent turn, MAXQ=256) | The foundation of the 256K depth; this repo's recall probes (`probe_recall*.py`) and KV_ENV injection inherit it directly |
| **Self-built engine methodology** | Repos 1+2: MSVC compile-compat patches, dual branches (project layer/engine layer), artifact hash ledger, reproduction guide | This repo's W1-W4 patch and build/deployment follow the same pattern (`patches/` + artifact reconciliation + `.bak` rollback anchors) |
| **Thinking budget (Design C)** | Repo 2: the self-built serve honors `--default-thinking-budget` vs the distributed prebuilt exe not parsing that field | The precursor of this line's tb fuse — what W1-W4 fixed were exactly its three linked defects (`==` failing / out-of-bounds abort / handover refusal) |
| **GUI launcher + serve_tee** | Self-built in repo 2 (the author's package only had bat files) | Simplified in this repo to **4 scene presets (2 modes × 2 models)** + validation warnings + KV_ENV injection |

### Key milestones (curated)

> 📌 **Conclusion freshness & maturity reviews** (the six superseded-conclusion list, the four-layer maturity verdict, the cross-review convergence trail) are governance retrospectives and no longer occupy README space — see the research report §十七:
> [`docs/03-归因与结论/调研-上游对照-Strata与KVMem-v0.19-与prefill基准修正-CB-TELE-LUMMY-20261103.md`](docs/03-归因与结论/调研-上游对照-Strata与KVMem-v0.19-与prefill基准修正-CB-TELE-LUMMY-20261103.md)

> ## ★ 2026-11-06/07 · Long-prefix anchors: from "doesn't fit" to 50% / 66.7% measured hit rate
>
> **Mechanism**: `PrivateLongAnchor` — at every 32K multiple of the prompt (`frontend.cpp:575-582`, hard-coded 32,768 stride) it offers "this position is worth keeping a KV snapshot"; once banked, the next turn's prefix match skips that prefill span.
>
> **Key distinction**: it does **not speed up prefill — it makes the next turn do less prefill**; gain is linear (0.033 s/page), optimum = the deepest anchor the pool allows.
>
> | Scenario | Pool | Hit | Effect |
> |---|---|---|---|
> | Multi-session anchor (DFlash2) | 51,200 | **50.0% `long anchor`** | TTFT 9.8s / total 10.2s (saves 6.7s) |
> | Large-pool anchor (SWIFT) | 90,112 | **66.7%** | variant total **18.5s → 6.9s (saves 62.7%)** |
>
> **Three measured boundaries**:
> 1. **Over-pool anchors must be rejected**: a 65K anchor needs 1,021 pages, pool has 800 ⇒ `adopt host-backed: need=1021 usable=800` ⇒ **HTTP 429** (both arms alike, unrelated to fix A; see item #78)
> 2. **`turn closure` masquerades as an anchor hit**: a verbatim repeat shows `cache 100.0%` with no anchor involved ⇒ **the verdict must read the hit-type field** (`long anchor` vs `turn closure`)
> 3. **Anchors only pay off for "same prefix, different tail question"**: a one-shot long document has no next turn; "long→short two-round" was measured and retracted (short request shows `cache 0`; the anchor always hugs the prompt tail)
>
> **Two fixes** (`spare_prefix_pages` = fix A / `NINFER_KV_HOST_ANCHORS` = fix B): fix A landed and was promoted on 11-05 (`F814B07A`); **on 11-07 it was measured and judged a "defensive fix" — arms differ <0.4%, no observable performance gain**; fix B is still unimplemented.
>
> ## ★ 2026-11-05 · Fix A `spare_prefix_pages`: the cheap cure for page drift
>
> **Problem**: after 34 rounds, ~330 early-context pages linger in host ⇒ every token pays a host round-trip ⇒ **decode collapses to 3 tok/s** (a 99.9% hit rate doesn't help — that 0.1% is exactly the head every step must attend to).
>
> **Mechanism**: not triggered by "prompt > pool" but by **"session round count"** — each round's cache replay remaps history pages and pushes the earliest ones out of the device pool.
>
> **Fix A**: `demote_kv_pages_to_host` gains `spare_prefix_pages` — the first demotion pass **skips `[0, deepest pending capture)`** (the second pass still yields them, guaranteeing room is freed). Value = `kv_pages_for_frontier(capture_groups.back().frontier)`, identically 0 when no capture is pending ⇒ **zero decode cost**.
>
> **Measured**: <0.4% difference, judged "defensive fix" — **it prevents "banking broken by demotion", it does not speed anything up**.

> ## ★ 2026-11-07 · VRAM desktop floor released + dual-head artifacts unified + four measured pool ceilings (platform-migration dividend cashed in)
>
> **Background (re-checking the platform migration)**: on 2026-10-27/28 the platform moved from an **i5-12600KF + Gigabyte B760M DS3H DDR4** to an **i5-14700K + Gigabyte B760M AORUS ELITE WIFI6E DDR4 GEN5** (the CPU natively supports PCIe 5.0 **and carries an iGPU**). All three consequences have now landed: **① the WHEA storm went to zero** (1857 AER events/minute on the old platform with the same recipe → 0 under full load on the new one); **② the "death valley" slow state has not been encountered in real use since** (its AND-of-three trigger — Gen5 + ≥400 MiB external pressure + razor-thin free VRAM — no longer assembles by itself); **③ the iGPU can drive the display** — at the time this was treated as "one more output port"; today it proved to be a **cashable VRAM dividend**, and this milestone is the cashing-in.
>
> **① iGPU-path dividend: a single-variable comparison run by the user (same binary, same flags, only the display output path differs)**
>
> | | display on dGPU | display on iGPU | delta |
> |---|---|---|---|
> | `nvidia-smi used` with the engine stopped | 1145 MiB | **55 MiB** | **−1090** |
> | `used / free` after a `65536` pool boots | 15730 / 248 | **14612 / 1366** | **+1118 free** |
> | `available` reported by the `102400` FATAL | 3,335,987,200 (3180.5 MiB) | **3,599,761,408 (3432.6 MiB)** | **+252.1** |
>
> ⇒ Moving the display to the iGPU shifts the desktop / browser / overlay off the dGPU and frees 1118 MiB card-wide, but **the engine's budget only credits 252.1 MiB of it**. The gap exists because the budget is read from `cudaMemGetInfo` **after the weights are loaded** (`model_instance.cpp:144-148` / `:496-501`), by which point the engine's own startup allocations have already been subtracted. **"Free on the card" ≠ "money the engine can build a pool with"** — that is the problem this milestone solves.
>
> **② Main breakthrough of the day: releasing the VRAM floor from hard coding (`--wddm-budget-arithmetic-only`)**
>
> The only branch in the source that can credit someone else's VRAM back into the budget (`model_instance.cpp:167-175`: `max(free, total − weights − 512MiB)`) was gated by the same switch as the D3D12 resident heap; with `NINFER_D3D12_RESIDENCY=OFF` (the shipping binary's production configuration) enabling that switch throws immediately. **A new independent flag separates "budget arithmetic" from "heap residency lock"**: it only changes the paper budget, arenas stay on `cudaMalloc`, D3D12 is not touched. 9 files `+28/−2`, built in the independent tree `build-1208b`, `cuobjdump` 384/384/0, artifact `496D6070`.
>
> The decisive evidence is the `memory ledger` line printed at `--log-level debug`, which settles the accounting in one shot:
>
> ```
> no flag (98304):    after weights 3.35 GiB (measured cudaMemGetInfo)
> with flag (102400): after weights 4.12 GiB = 16303 − weights 11574 − 512   ← matches the formula MiB for MiB
> ```
>
> ⇒ **H2 confirmed**: `total` is CUDA's 16303 MiB, and everything beyond the `512 MiB` floor (including the constant 325 MiB of driver reservation and the desktop residue) is counted as oversubscribable. Paper budget **3433 → 4217 MiB (+787)**.
>
> **Honest boundary**: the +787 is a **paper** budget; what is actually obtainable is only **+56.6 MiB** (`102400`'s `requires 3486.6` just clears the real supply of `3430`, with WDDM absorbing the oversubscription); the `slack 730.4 MiB` is book-keeping only and reads `free 0 B` the moment startup completes. **The flag does not create supply — it removes a constraint; the real ceiling is set by how much oversubscription the system can absorb.**
>
> **③ Boundary sweep: 8 tiers, each booted and speed-tested (iGPU path / rk8v4 / graph64 / flag on)**
>
> | pool | `runtime` | `slack` | `nvidia used / free` | `decode` | vs baseline |
> |---|---|---|---|---|---|
> | 98,304 (baseline, no flag) | 3.30 GiB | 54.7 MiB | 15481 / 497 | 183.8 | 1.0000 |
> | 102,400 | 3.40 GiB | 730.4 MiB | 15591 / 387 | 183.7 | 0.9995 |
> | 110,592 | 3.62 GiB | 513.6 MiB | 15810 / 168 | 183.6 | 0.9989 |
> | 118,784 | 3.83 GiB | 296.9 MiB | 15962 / 16 | 183.7 | 0.9995 |
> | **126,976 (measured ceiling)** | **4.04 GiB** | **80.1 MiB** | **15964 / 14** | **183.6** | **0.9989** |
> | 131,072 | — | — | — | **FATAL** | — |
>
> The `131072` FATAL closed the last gap: `requires 4,451,516,672 (4245.3 MiB) > available 4,421,911,552 (4217.1 MiB)`, a 28.2 MiB shortfall — matching `16303 − 11574 − 512` for the second time, MiB for MiB. **The paper budget hard-caps at 4217 MiB.**
>
> **④ 3-minute soak (126,976 tier)**: **123 requests / 0 failures**; `decode 183.0–183.6` (first five 183.5–183.6 → last five 183.4–183.5, decay <0.15%); `TTFT` 500 ms averaged over both the first and last ten requests; `vram 15660 MiB` with zero drift throughout. ⇒ The 706 MiB of oversubscription **did not trigger paging** under short-run load, but at 126,976 the card has only 14 MiB left and `slack` is 80 MiB, i.e. **no buffer at all — a knife-edge tier, not recommended as a daily setting**. The recommendation is **102,400** (`free 387` / `slack 730`, verified with a 10-minute zero-drift run and A/B 0.9995).
>
> **⑤ Dual-head unification: one artifact, two speculative heads, switched by `--spec`**
>
> Previously MTP and DFlash2 each kept a separate 12–13 GiB artifact (CODER390 even had MTP only, no DFlash at all). `graft_dflash2.py` **keeps** the MTP head by default (`--drop-mtp` is what discards it), so a dual-head artifact can be produced directly:
>
> | model | dual-head artifact | size | MTP-mode weights | DFlash2-mode weights |
> |---|---|---|---|---|
> | CODER390 | `Qwen3.8-27B-Coder390-MTP+DFlash2.ninfer` | 14.02 GiB | 12.3 GiB (**identical** to the single-head artifact) | 13.5 GiB |
> | SWIFT15 | `swift15_iq3s_mtp+dflash2.ninfer` | 13.29 GiB | 11.3 GiB (**identical**) | 12.3 GiB |
>
> **MTP mode costs nothing extra** (only the selected head is loaded); DFlash2 mode costs 1.0–1.2 GiB more (the drafter's q/k/v live in BF16). **CODER390 thereby gains DFlash2 capability for the first time.** The model store shrank from 5 artifacts / 51.86 GiB to 2 artifacts / 27.31 GiB; the hashes of the three deleted single-head artifacts are recorded in `work/data/deleted-single-head-20261107.txt` and can be rebuilt from the graft recipe.
>
> **⑥ Four pool ceilings and the speed comparison (iGPU / rk8v4 / graph64 / flag on; same prompt, same max_tokens, median of 3 rounds)**
>
> | model | head | pool ceiling | boundary | `decode` (dGPU / **iGPU**) | acceptance (dGPU / **iGPU**) |
> |---|---|---|---|---|---|
> | **CODER390** | MTP k3 | **86,016** | 90,112 FATAL (need 3161.5 > avail 3116.7) | 130.3 / **154.9** tok/s | 56.4% / **64.2%** |
> | **CODER390** | DFlash2 k5 | **40,960** | 51,200 FATAL | 134.8 / **194.4** tok/s | 39.8% / **62.1%** |
> | **SWIFT15** | MTP k3 | **126,976** | 131,072 FATAL | 114.3 / **138.1** tok/s | 44.3% / **56.6%** |
> | **SWIFT15** | DFlash2 k5 | **90,112** | 94,208 FATAL (need 3146.7 > avail 3133.9) | 116.0 / **186.0** tok/s | 28.8% / **57.6%** |
> | **GSQ-RCO IQ3_S** | MTP k3 | **126,976** | 131,072 FATAL (need 4245.3 > avail 4217.1) | — / **152.7** tok/s | — / **64.3%** |
> | **GSQ-RCO IQ3_S** | DFlash2 k5 | **90,112** | 94,208 FATAL (need 3222.1 > avail 3133.9) | — / **202.6** tok/s | — / 59.3% |
>
> **⚠ Correction of 2026-11-08: the "DFlash2 only +3.5%/+1.5%" figures were an artefact of desktop-channel paging.** After a reboot freed VRAM completely and the display moved to the iGPU, a re-run (bold column) shows 19–60% higher throughput at identical piece and pool, and the **true DFlash2 gain over MTP is +25.5% (Coder390) / +34.7% (SWIFT) / +32.7% (GSQ)**. Pool ceilings are unchanged — the arith paper budget `total − weights − 512` is channel-independent and slack matches to the MiB — only the realised throughput at the same pool moves. **Display channel is the first-order speed variable; it matters more than head selection.**
>
> Choosing a head remains a speed-versus-context trade-off: DFlash2 costs 29% of the pool (SWIFT/GSQ) or 52% (Coder390) and returns +25%～+35% throughput.
>
> **⑦ Laying the ground for larger models**: the two things opened up today (reachability of a 4217 MiB paper budget, and the one-artifact-many-heads organisation) directly determine whether the next model tier can run at all — every extra 1 GiB of weights removes about 1 GiB of usable pool, and 126,976 already pushes a 16 GiB card down to 14 MiB of headroom. **The platform-migration and iGPU dividends were fully cashed in on this day, and the 16 GiB physical ceiling was reached at the same time.**
>
> **⑧ Governance items shipped alongside**: the single permitted process-spawn entry point `spawn_visible.ps1` was hardened against black-box windows (wrapper ban exit 3 / redirect ban exit 4 / the gate holds its own `serve_tee` with live console forwarding / content-non-empty check 3×2s / records extended with `tee_log` + `engine_pid` + `content_ok`); the day's 18 empty-window instances are all booked in `evidence/audits/VIOLATION_empty_window_20261107.md`; the shipping binary was promoted `F814B07A → 496D6070` (`build-1208b`, `engine-rc1-7e14453-6-g2755b24-dirty`); governance baseline rebuild#22/#23/#24 (anchor `F877965F`).
>
> **⑨ Open items**: no source-level localisation of the mechanism behind the gap between the paper slack and the real supply (which layer of CUDA/WDDM absorbs it); the 126,976 tier lacks a long-session plus concurrency stress run; the `thinking:false` field is not recognised by the engine (A/B symmetry holds, but "thinking fully off" does not).
>
> **⑩ 2026-11-08 addendum: GSQ-RCO IQ3_S promoted to a third tier** (stock base, no fine-tune). Source `Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf` (11.29 GB) passed `validate()` outright with `has_mtp=True` (the MTP head lives in the same GGUF under the same quantisation); `tools.convert` produced the single-head artifact in **59.9 s with zero patches and zero grafting**, then `graft_dflash2.py` took 85.0 s to make it dual-head `gsq_iq3s_dual.ninfer` (13.29 GiB). Measured: **MTP 126,976 + 152.7 tok/s + 64.3% acceptance (best of four); DFlash2 90,112 + 202.6 tok/s (fastest overall)**. Three quality probes (thread-safe LRU, train arrival time, GQA-vs-MQA) were answered correctly by all three artifacts — **style differs more than capability** (Coder390 writes a hand-rolled doubly linked list, SWIFT is the most production-shaped, GSQ the most compact).
> **⑪ 2026-11-08 re-measure and housekeeping**: GSQ also *starts* at 126,976 on the dGPU path (decode 87.3 / `free 0 B`), but **98,304 is the performance knee** (96.7 tok/s / `free 30.8 MiB`); the same pool reaches 152.7 on the iGPU path. **`gsq DFlash2 @ 90,112` on the dGPU drove `free 0 B`, starved the desktop compositor (dwm/explorer) and made the whole machine untypable**; killing the engine restored it. Rule: after any dGPU start, check `nvidia-smi free` and **drop the pool immediately below 1 GiB**; large-pool stress runs belong on the iGPU path. On the logging side, sampling was dropped for **dual-write**: plain-text essentials 2.08% + full gzip 1.42% = **3.50%** (the sampling scheme was 7.74% *and* lost evidence), with multi-member gzip so a hard kill only truncates the last member instead of raising `EOFError`.
>
> **Counter-example the same day**: unsloth `UD-Q3_K_XL` failing to convert is not a tooling gap — it compresses 96 GDN gate tensors `ssm_alpha/beta` from BF16 down to Q8_0 (the recipe hard-requires BF16 and has **no dequant fallback**), and ships its MTP head as a separate file under a different quantisation policy. With a patch it does convert, but MTP acceptance collapses to **13.7%** (d1 26.9% / d3 13.7% / d5 3.9%). **Conclusion: whether a GGUF converts cleanly depends on the publisher honouring the container's assumptions (norms and gates unquantised, MTP co-located and co-quantised with the main weights), not on tooling.**

> ## ★ 2026-10-18/19 · Hang attribution closed + valley trigger conditions pinned + arch incident root cause closed (three-binary verdict matrix)
>
> **① Hang culprit verdict (build history §136)**: three-binary comparison under identical conditions (Gen5 + external pressure 400 MiB + pool-edge) — **S13 production build (no symbols) = decode 0, 5/5 probes canceled at 30 s timeout (hangs, never returns)**; **sym3 / offi (symbol-linked builds) = 41 / 44.5 tok/s, deep valley but 6/6 all completed**. Across two compiler versions (14.43/14.44), both symbol-linked builds "valley but complete"; the only no-symbol build hangs ⇒ **hang culprit = missing symbol linkage** (`/Zi`+`/DEBUG` changes the linked layout itself — it is not "symbols let us see the hang", it is "adding symbols cured the hang"). **"Hang" and "valley" are two separate problems from here on**: hang = build problem (located, reproducible/avoidable); valley = load × environment phenomenon (not closed).
>
> **② Valley trigger conditions pinned (§135, six-batch full matrix)**: **AND of three conditions** — Gen5 PCIe + external VRAM pressure ≥400 MiB + free VRAM at pool-edge (<400 MB); missing any one, it does not trigger (zero-pressure × two builds × two PCIe generations, 8/8 healthy; on Gen4, pool-edge + 400 MiB, 0/68 probes entered the valley). WHEA storms (peak 1857/min) time-aligned shot-by-shot: **no causal link to the valley** (co-occurring phenomenon). The interim wrong conclusion "68 probes, 0 valleys = promise broken" has been retracted (truth = Gen4 environmental suppression + zero-pressure both outside the domain); the current honest wording: **"a stably triggerable dose exists inside the declared domain (3/3, n=3), not triggered under arbitrary conditions"**.
>
> **③ arch miscompile root cause closed (§128/T#0056)**: the sym build's "startup hang" was in fact a build missing `-DCMAKE_CUDA_ARCHITECTURES=120a` ⇒ CMake defaulted to sm_86 ⇒ RTX 5080 (sm_120a) cannot load directly ⇒ a PTX JIT grind masquerading as a hang (357 kernels). sym3 rebuilt to the recipe (`cuobjdump` acceptance: **384 cubins, all sm_120a, 0 sm_86**). Lesson mechanized: **every CUDA build must pass the arch flag explicitly and be accepted by a product-level cuobjdump check**.
>
> **④ Async DEPTH three-tier shallow-load comparison (§137)**: D2 (default) 187.1 > D0 (sync) 183.6 > D1 182.6 tok/s — **under shallow load the async page pipeline has no work to do** (differences at noise level); combined with the 10-16 deep multi-turn comparison (async net gain ~20%, deepest segment ≈2×), the framing = **async value emerges as working-set depth grows**; depth tiers 3/4 untested at deep load; default stays D2.
>
> **⑤ Launcher overhaul & engine line split (§130-139 / user directive)**: engine dropdown = **three active binaries** (S13 production build 322A972D / offi official chain + symbols 3543AD18 / sym3 new build chain + symbols 9453FFC6) + five archived; model dimension = **six tiers** (q2lynn / swift / bonsai / iq4nl / iq4nlvis / orig); async page pipeline = A/B switch × depth (1/2/3/4 batches in flight) as two independent dimensions; scene presets = 4 (2 modes × 2 models), orthogonal to the engine dropdown (engine = which binary runs, scene = with what parameters).
>
> **⑥ Environment event (same-tier fact)**: BIOS moved from PCIe **Gen5 down to Gen4** (WHEA storm mitigation: 6 h 12,305 AER entries → 0); data across the divide must be labeled with the PCIe generation explicitly. **Gen5 is a known high-risk operating state** — see "Known limitations".

> ## ★ 2026-10-16 · Same-condition A/B hard evidence for the async page pipeline + Death Valley manhunt milestone (120 hours of continuous stress)
>
> **① Deep multi-turn ON/OFF comparison** (progressive multi-turn + partial cache reuse + long outputs, 2.3–3.5× over-pool, 2026-10-16):
> - Tearing out async (sync fallback) **slows decode by ~20%** (deep segment median 188.1 vs 234.9, **r=0.80**); **deepest segment (3.5× over-pool) differs ≈2.0×** (119.4 vs 235.6); ring STALL **33 → 2** (≈16×);
> - Shallow-load comparison: single-shot over-pool is a tie (r=1.13) ⇒ framing: **async value emerges as working-set depth grows** (it was designed for deep loads);
> - Honest boundary: n=3/arm, single machine, healthy period; **triggering also requires free VRAM at pool-edge (<400 MB)** ("a stably triggerable dose exists inside the declared domain, not under arbitrary conditions"); the sync arm did not "die" (the stronger historical claim "multi-turn always dies" did not reproduce — observed as "usable but slow").
>
> **② Death Valley (transient slow state) manhunt milestone**:
> - **On-demand reproduction**: external VRAM pressure (~1.2 GiB) ⇒ apply to enter the valley (speed drops to 1/25), release to recover, repeatable across two rounds — no more "waiting for a window";
> - **Mechanism localized**: valley-time is spent **entirely in host-side submit calls** (`submit ≈ wall`, `wait = sync ≈ 0`) ⇒ the blockage is in the engine's own submit path (driver-internal blocking); **PDL (the former prime suspect) ruled out** by an on/off toggle counter-example; host path / page tiers / pool size / throttling each excluded by measurement;
> - **Deep tier (≈1/100) also manufactured, and governed by a "machine-state window"** (12 long holds overnight: **in-window 4/4 hit, out-of-window 8/8 valley** — the "reboot reproduces it" recipe was falsified; window opening/closing conditions under analysis);
> - Remaining: pin the exact blockage point on the submit path to line level — **an ≈2-minute minimal reproduction protocol is ready** (for the community / upstream / driver side).
>
> **③ Other progress in the interim (10-14~15)**: Swift-1.5 (IQ3_S) base swap and KV tier A/B (rk8v4 fast and stable); v2 promoted to the daily baseline (127-round run, 0×500, peak 403.7); S12 incidence comparison all-zero across 12 windows ⇒ discovered the "active window" structure; S11 GDN-resident fix (byte-identical output). See the [Build History](docs/ninfer-kvmem-项目构建史.md) §50-73 (Chinese).
>
> **📄 Presentation**: [`异步页流水-技术说明.pptx` (Chinese)](docs/99-附件/异步页流水-技术说明.pptx) · [**English brief**](docs/99-附件/Async-Page-Pipeline-Technical-Brief.pptx) · [Public note (MD, Chinese)](docs/00-入口与说明/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md)

> ## ★ 2026-10-13 07:15 · New peak 463.9 (H1 baseline · agentic first battle)
>
> The morning's first **agentic session** (30 tools / 28 turns; engine `build 35173e0` = baseline `H1_54fix_20261013`, 64K pool / draft4 / depth1):
> - **decode peak 463.9 tok/s, holding 451–464 across ≥6 consecutive windows** (07:15:47–07:16:12: 463.9/459.7/461.8/457.5/451.0/451.8, then 245.0; host ~98%);
>   **req#2: prompt 8,303 → output 23,869 tok, TTFT 5.1 s, prefill 2.23k, request-level decode 258.2 (hybrid speculation)**;
> - Mid-session multi-turn: **cache 99.3–100% (private endpoint)**, TTFT 311 ms–1.1 s (req#3–#26); **4 over-pool events with zero failures** (`unavailable Device page` / `recovery` / HTTP 500 all 0 ✓);
> - **Late in the same session, from 07:25:32, entered the valley and did not climb out for a long time** (rolling log): **second turn (07:26–07:30): 23 of 40 windows <20 (min 0.2, max 144, mean 34.7)**, two cache=0 full refills (TTFT 35–42 s); **third turn (from 07:32:24): prefill normal, decode deep valley 0.2–7.2 (90 s of watching without climbing out, as of 07:36:26)** — ledger #46 live version (valley floor 0.2 = lowest ever);
> Live log `logs\test_54fix1d.log` (session from 07:15:24).

> ## ★ 2026-10-11 20:39-21:18 · Major breakthrough: Async Page Pipeline first battle
>
> **Over-pool decoding from "single-digit deep valleys" to "stable high ground"** — v2 engine served at 20:39, first battle 20:43, multi-turn by 21:04:
> - **Peak decode 333.0 tok/s (20:48:58, host 98.2%); 40 consecutive seconds above 300** (20:48:53-20:49:33, 10 samples 296-333);
> - **First battle: median 100.5 tok/s over 130 samples** (same metric: the pre-dawn version before ledger #42 was **5.6** — **18×**; batch version 103.6 flat — but peak capability doubled 333 vs 155);
> - **74.4K deep over-pool (host 99%) decode still 114.4** (req#57); **16K-output long task decode 251.1** (req#7); **prefill extreme 991.4** (req#58);
> - **Multi-turn conversation usable (the core breakthrough — before v2 multi-turn always died: the second turn dropped to single digits)**: 5-6 turns progressing normally; deep valleys (page-operation storms, decode 1-6 tok/s) **self-heal and climb out** (req#61 instance: valley 100 s → peak 60 s → deep valley 155 s → peak → 16K output all completed, 6m0.3s); still 100-157 after auto-compaction.
>
> **Mechanism**: demote/restore page movement **pipelined in parallel** with decode kernels — batch page accumulation (8 pages/batch) + transfer-stream async submit + next-step harvesting (the wait is covered by the previous step's kernel time) → **decode never waits for pages**.
> The full ledger-42 chain (cancel-checkpoint moved forward → batch demote → async demote) + ledger-44 profile verdict; source delta `patches/ledger42_v2_async_demote.patch` (baseline s6-20261008@3b9dc83).
>
> **Relation to KVMem (two-layer architecture)**: KVMem = the **data layer** (where KV pages live + on-demand recall — "it fits");
> v2 = the **transport layer** (page movement decoupled from decoding, pipelined — "it moves"). OS analogy: KVMem = virtual memory + demand paging;
> v2 = asynchronous I/O (background dirty-page writeback / readahead) — **pages flow freely, decoding never stalls**.
>
> **📄 Full technical analysis** → [`docs/03-归因与结论/技术解析-异步页流水-v2-20261011.md`](docs/03-归因与结论/技术解析-异步页流水-v2-20261011.md) (Chinese)
> (problem background / mechanism / v2 implementation & correctness contract / **itemized KVMem comparison + common misconceptions clarified** / live verification /
> Death Valley analysis / construction archive & rollback anchors); engineering record in the [Build History](docs/ninfer-kvmem-项目构建史.md) §三·十九 (Chinese).

### The full campaign list (mapped to the [Build History](docs/ninfer-kvmem-项目构建史.md) section by section)

| # | Campaign | Result | Build history |
|---|---|---|---|
| 0 | Line setup & git baseline; first tech research; three rounds of cross-review convergence | Direction & division of work settled | §一/二/三 |
| 1 | P0 launch-layer adaptation for Coder390 + engine unified to self-built + bare-decode baseline (17 tok/s cause determined) | Deployment chain working | §三·六 |
| 2 | P1 MTP data repackaging (q4_0 → q8_0 bit-lossless, three-tier acceptance) | MTP head swappable | §三·七 |
| 3 | **MTP running**: official Q8MTP failed twice on VRAM → self-converted iq4_nl (saving 212 MB) → serve A/B; ctx scan; three quantities clarified (max-context / WINDOW / kv-capacity); 256K + 40K squeeze | **decode 105 → 256K context** | §三·八 |
| 4 | Launcher finalized (P1b parameter rewrite, 8→10 presets) | One-click serve | §三·九 |
| 5 | Vision feasibility + root cause of "flash exit" with finalized params (model container missing vision component) | Flash-exit root-fixed (launcher interlock) | §三·十 |
| 6 | Two finalized-spec corrections (user rulings) + thinking-budget VRAM forensics + vision-graft ledger entry | Parameter spec corrected | §三·十一/十二 |
| 7 | **Vision-tower graft**: 282 MiB (333 objects, q4/q5/q8/bf16 mixed) merged byte-by-byte into the self-converted head container; image recognition 26.9 s | Vision usable | §三·十二 + the third gate in the opening |
| 8 | ngram measured (two-arm comparison: +2.7%, not statistically significant) | Keep default | §三·十三 |
| 9 | **DSH wall verdict**: `--kv-lease-growth` deep over-pool bounded completion (same issue as upstream B35) — three rounds of cross-review converged | **Remove growth, wall eliminated** | §三·十四/十五 |
| 10 | **W1-W4 engine surgery** (three linked thinking-fuse defects, 84-line patch) + four-fold acceptance | Latent defects removed | §三·十七 |
| 11 | **Arm-A closure**: two rounds of DSH agentic with zero truncation (16,143/11,782 tok); pool ceiling calibrated; vision three-in-one | Ledger #38 closed | §三·十六 |
| 12 | **Autonomous experiment night**: 64K pool calibration (graph-allowance) + **page-drift verdict** (multi-turn replay squeezes out early pages → decode 3 tok/s) + **stream-hang dual defect** (ledger #41) + ledger #39 closed | Three new failure modes characterized | §三·十七 |
| 13 | Upstream 23 commits reviewed one by one (no duplicates; B34/B35/B37 mapped) + sink=5120 implemented (skeleton 4→80 pages) + KVMem source reconnaissance (issue #114 / tancau brief / ledger-42 blueprint) | Mitigation landed + construction design pending review | §12/§13 |
| 14 | DSH integration: auto-compaction trigger tuning (ctx 229,376) + maxTokens capped at 24,000 | Long-session workflow closed loop | §三·十七 §8 |
| 15 | **v2 promoted**: independent cross-review (2×40-round deep stress) + live 127-round run 0×500, peak 403.7 | Async pipeline becomes the daily operating tier | §三·十九~二十九 / 40-47 |
| 16 | **Base swap**: Swift-1.5 IQ3_S loaded (11.3 GiB / 9.4 s) + KV tier A/B (rk8v4 wins on both speed and acceptance) + request-line measurement (median 56,440 / max 96,430) | Production switched to IQ3_S + rk8v4 @ 65,536 | §36-39 |
| 17 | **Valley (transient slow state) manhunt S1-S13**: four-zone instrumentation → path convergence → item-by-item exclusion (PDL / page relay / host path / page tiers / pool size / throttling) → **on-demand reproduction (valley tier 1/25)** → **mechanism = host-side submit blocking (driver-internal)** → **deep tier governed by machine-state window (in-window 4/4, out-of-window 8/8)** | Controllable (detectable fingerprint / minutes-level self-heal / mitigations confirmed); window conditions & line-level root cause pending | §48-73 + night research 1/2/3 + deep-tier search |
| 18 | **Async contribution verdict experiment**: deep multi-turn ON/OFF same-condition comparison — tearing out async slows decode ~20% (r=0.80), deepest segment ≈2.0× | Async value claim backed by controlled hard evidence | 夜研-1/2/3 |
| 19 | **Public materials**: bilingual README + bilingual slide deck + public technical note | For the community / upstream collaboration | docs/ |
| 20 | **sym "hang" root cause closed**: build missing arch ⇒ sm_86 ⇒ JIT grind masquerading as hang; sym3 rebuilt with cuobjdump acceptance 384×sm_120a | Incident root cause closed + product acceptance gate | §128 / T#0056 |
| 21 | **Valley trigger verdict** (Gen5 × external pressure × pool-edge, six-batch matrix): AND of three conditions pinned; zero pressure never triggers; WHEA not causal to the valley | "On-demand reproduction" given its domain of validity | §134-135 |
| 22 | **Hang culprit verdict closed**: three-binary matrix (S13 no-symbol hangs vs sym3/offi symbol-linked "valley but complete") ⇒ culprit = missing symbol linkage | Hang identified as a build problem; manufacturable and avoidable | §136 / #0069 |
| 23 | **Async DEPTH three-tier shallow-load comparison + launcher overhaul** (three active engines / six model tiers / async × depth / scene-engine orthogonal) | Async value framing narrowed to "deep load" | §137-139 |

> The above are the **curated** major campaigns; the **round-by-round full record** (evidence chain per decision, failures and regressions) is in the **[Build History](docs/ninfer-kvmem-项目构建史.md)** (§1–§140, incl. ledger and instrumentation chain; Chinese).

### Squeezed: every parameter calibrated

| Parameter | Start | End | Method |
|---|---|---|---|
| High-speed pool (VRAM) | 40,960 | **51,200 stable** (55K pool-edge not reproducible; 56K short 17-50 MiB, abandoned; **64K measured success** — needs `--cuda-graph-allowance-mib 64/128` + a clean GPU, 2026-10-11) | Serve tier by tier, calibrate precisely by startup-reserved bytes |
| Logical context | 128K | **256K** | Model-native cap; over-pool KV sinks to a 16 GiB host arena |
| decode | ~100 tok/s | **105-233 tok/s** | MTP acceptance (hybrid speculation) |
| prefill | — | 1.5-2.2k tok/s | Over-pool recall absorbed by the pipeline (overhead only 8-23%, zero truncation) |
| VRAM ledger | — | 16 GB card: weights 12.3 GiB + pool/workspace 1.9 GiB + vision, 490 MiB free | Item-by-item accounting: weights/pool/workspace |

### Scorecard

| Item | Before (Bonsai line, same scenario) | This line today |
|---|---|---|
| Agentic coding tasks | thinking cut at 30 s, endless "continue" | **plane game complete in 4m33s (829 lines, playable as-is)**, Wuling Town 3D scene **1m39s** |
| Single-request continuous output | ~4,096 (lease window cuts it) | **16,143 tokens** |
| Logical context | 128K | **256K** |
| High-speed pool (VRAM-resident KV) | 40,960 | **51,200 stable** (55,296 pool-edge calibrated / **64K measured success**; full KV = pool + 16 GiB host arena, two tiers carrying 256K) |
| decode speed | ~100 tok/s | **105-233 tok/s** |
| Vision | none | **image recognition 26.9 s** (CPU encoding, zero VRAM) |

---

## Current production setup (updated 2026-11-13): **three model tiers × dual-head artifacts × display channel**

### Three tiers × two speculative heads (dual-head artifact, switched by `--spec`)

**One artifact carries both MTP and DFlash2 heads** (`graft_dflash2.py` keeps MTP by default; `--drop-mtp` discards it): MTP mode costs nothing (only the selected head loads), DFlash2 mode costs 1.0–1.2 GiB more.

| Tier | Dual-head artifact | Size | **MTP pool / decode / acceptance** | **DFlash2 pool / decode / acceptance** |
|---|---|---|---|---|
| **Coder390** | `Qwen3.8-27B-Coder390-MTP+DFlash2.ninfer` | 14.02 GiB | **86,016** / 154.9 tok/s / 64.2% | **40,960** / **194.4** tok/s / 62.1% |
| **SWIFT-1.5** | `swift15_iq3s_mtp+dflash2.ninfer` | 13.29 GiB | **126,976** / 138.1 / 56.6% | **90,112** / **186.0** / 57.6% |
| **GSQ-RCO IQ3_S** | `gsq_iq3s_dual.ninfer` | 13.29 GiB | **126,976** / 152.7 / **64.3%** (highest) | **90,112** / **202.6** (fastest overall) / 59.3% |

> All measured on the **iGPU display channel** (same table, ★2026-11-07 ⑥). dGPU channel is 19–60% slower at the same artifact and pool — **the channel is the first variable**.
> Head trade-off: **DFlash2 gives up 29% pool (SWIFT/GSQ) or 52% (Coder390) for +25%～+35% throughput.**

### Engine & channel

| Dimension | Current value |
|---|---|
| **Active binary** | `496D6070` (`build-1208b`, `engine-rc1-7e14453-6-g2755b24-dirty`, carries `--wddm-budget-arithmetic-only`) |
| Promotion order | `9453FFC6` (sym3/RC1) → `B93B1791` (RC8) → `F814B07A` (fix A) → **`496D6070`** (paper budget) |
| **Channel** | **`igpu` recommended** (display on iGPU ⇒ 5080 idle `used ~55 MiB`, engine gains **+1118 MiB free**); `dgpu` desktop holds ~1145 MiB; `auto` reads `nvidia-smi` |
| Launcher | channel is an **independent dimension** (emits no engine flag; used only for ceiling validation and hints) |

### Historical setups (archive note)

The 2026-10-19 and earlier engine/model tables (three candidate binaries S13 / offi / sym3, the RC6 runtime slot, six model tiers and 4 presets) are fully archived: **the active setup is `496D6070` + three dual-head artifacts** (see the section above). Pool ceilings, decode figures and `--model-id` semantics in those old tables are stale — copying them either fails to boot or misreads performance.

Full history (per-binary sha, verdict experiments, equivalence measurements, reasons for archiving) in [`docs/ninfer-kvmem-项目构建史.md`](docs/ninfer-kvmem-项目构建史.md) §130–§139 / §176–§178 and [`docs/01-构建与发布/引擎构建物版本台账-CB-20261026.md`](docs/01-构建与发布/引擎构建物版本台账-CB-20261026.md) (Chinese).

**Current shared parameters & discipline** (these belong with the three tiers above, not to the archive):

- Context 256K logical (262,144); over-pool KV auto-sinks to a 16 GiB host arena; speculation **DFlash2 K5 (sweet spot) or MTP k3**, switched by `--spec`, plus hybrid speculation (dflash2 + ngram, 59.5% acceptance); thinking high + budget 16000; hemostat `--recover-invariant-failures` (**no growth**); vision overlay/off; concurrency **1** (ring hard constraint)
- **Pool ≥ working set is the lower edge of the sweet spot, not a hard rule** (over-pool ⇒ retrieval subset intervenes ⇒ content may change; see "Key engineering conclusions")
- Per-tier baselines & measurements in `baselines/<tier>/` (frozen sets are append-only; golden SHA comparable only within the same tier)

## Quick start (when engine & model are already in place)

```
启动器.bat            # the single GUI entry; 4 scene presets (2 modes × 2 models)
```

Pick the preset **① 生产 · Coder390 (86,016 pool · MTP k3 · arith)** or **② 生产 · SWIFT (126,976 pool)** → serve → `http://127.0.0.1:8094/v1` (OpenAI-compatible).

The environment-variable half of the command line (⚠️ **all six KV_ENV switches are mandatory**: missing `NINFER_KV_WINDOW` the engine refuses to start; missing any other it "starts but silently answers wrong"; `NINFER_KV_SINK=5120` = attention-sink skeleton pages, added 2026-10-11 benchmarking the official D-01; banner `skeleton=80` is the effectiveness criterion):

```bat
set NINFER_KV_WINDOW=32768
set NINFER_KV_SINK=5120
set NINFER_KV_RETRIEVE=8192
set NINFER_KV_RING=1
set NINFER_HOST_PAGEABLE=1
set NINFER_KV_REUSE_HOSTBACKED=1
> The launcher (`ninfer_launcher.py`) injects the six switches above + the async page pipeline **A/B switch × depth tier (1/2/3/4 batches in flight, default 2)** (`NINFER_ASYNC_DEMOTE` / `NINFER_ASYNC_DEMOTE_DEPTH`) — measured basis: single-shot over-pool r=1.13 (tie), deep multi-turn r=0.801 (net gain holds, deepest segment ≈2×); shallow-load three-tier comparison D2 187.1 > D0 183.6 > D1 182.6 ⇒ async value emerges with working-set depth. For A/B flip only that switch and nothing else; changing tiers requires a serve restart.
```

**Do not hand-copy the engine command line**: the active binary, artifact, pool / graph / KV tier all follow the three-tier dual-head bundles (`MODEL_BUNDLES`), and hand-copied lines tend to carry historical values (old exe, single-head artifact, 65,536 pool, graph 192 are all stale). Pick a preset in the launcher and copy the command it generates, or check each flag against [`docs/01-构建与发布/引擎启动参数与配置档-20261014.md`](docs/01-构建与发布/引擎启动参数与配置档-20261014.md) (Chinese).

> `--model-id` is the **service display name** (the API `model` field) and may differ from the real weight name: the launcher switches it automatically by weight file (swift / gsq / default coder390), and tools read it from `/v1/models` (`scripts/_modelid.py`) — **no manual editing**. To change tiers, use the launcher's model dropdown (it brings the whole KV / pool / graph / vision set); do not hand-assemble the flags.

Clients: any OpenAI-compatible tool; for DSH integration see `docs/00-入口与说明/教程-KVMem与短测-给agent与使用者.md` (Chinese) and the build history (provider config includes `streamIdleTimeoutMs: 3600000`).

## Repository layout

This repo is **not** a self-contained engine distribution; it is a workspace overlay of "**upstream engine source + all of this line's work products**":

| Path | Contents | In repo |
|---|---|---|
| `docs/` | **Build history (§1–§140 full record)**, cross-review reports, research notes, tutorials + **`引擎启动参数与配置档-20261014.md`** (full parameter table / two-tier configs), `KV档A-B-*` (KV precision A/B), `深上下文池收益与A2适用域-20261014.md`, `Swift换底座-三臂结果与int8预算-20261014.md` | ✅ |
| `build/` | Engine build scripts (`s6_1208a.bat` etc.) + 3 baseline patches (`build/patches/0001-0003`) + artifact manifest | ✅ |
| `scripts/` | Model processing (`recode_mtp.py` / `graft_vision.py`) + probes (`test_ab_arm1.py` / `probe_recall*.py`) + valley measurement (`valley_bench.py` / `valley_history.py`) + **new tools**: `verbatim_gate.py` (verbatim-identity gate, 8 prompts), `bisect_env.ps1` (environment bisection), `gpu_probe.cu` (machine-level health probe), `_modelid.py` (display-name resolution), `valley_watch.ps1` + `watch_launch.ps1` (the watcher), `pdl_aba.ps1` + `valley_trigger_aba.ps1` (PDL on/off A-B-A) + **valley manhunt analysis pieces (shipped with the repo)**: `audit_selfinduce.py` / `audit_dims.py` (self-induction confusion audit: conditional-probability comparison + dimension split), `freemem_vs_valley.py` (host memory × valley: the ruler that retracted the old "no memory signal" negative result), `timeline_deep.py` (deep-valley window alignment at 1-minute resolution), `memhold.py` (host memory pressure applicator, group-A positive-control actuator) | ✅ |
| `tools/` | **Diagnostic instrument sources + engineering toolbox (shipped with the repo, for reproducibility)**: instruments = `concur_bench.cu` (cross-process: GPU core latency / host page-read latency / host page-read bandwidth, three tests) · `pageable_bench.cu` (pageable vs pinned copy comparison) · `vram_hold.cu` (**on-demand valley trigger**: external VRAM occupancy) · `submit_load.cu` (submit flooding) · `gpu_probe.cu` (machine-level health probe) + their `build_*.bat` + **5 prebuilt exes (~880 KiB, usable without a CUDA toolchain)**; toolbox = `dump_stack.py` / `sym_resolve.py` / `unwind.py` (crash-stack backtrace & symbol resolution) · `find_exception.py` / `find_throw_string.py` · `vram_model.py` / `bench_analyze.py` / `range_check.py` · `archive_build_output.ps1` etc. | ✅ |
| `patches/` | **19 engine patches**: the I3b chain (`i3b_p2/s2/s3b/s3b_fix/s4/s6/s7/s8/s9/s10/s11` — step-profile / submit split / sticky fix / in-graph events / **S6 segment-level stamps** / **S7 PDL switch + target tri-split** / **S8 PDL self-report** / **S9 verify subdivision** / **S10 runtime PDL** / **S11 GDN resident**) + W1-W4 fixes + ledger42×3 / 44 / 46×2 / 47 | ✅ |
| `baselines/` | **One baseline set per model** (est. 2026-10-14): `q2lynn/` (**frozen**: verbatim-gate noise floor 8/8, KV A/B ledger, deep-context ledger, capacity table) + `swift15_iq3s/` (current: four-arm verbatim files, capacity table) + a `README.md` discipline | ✅ |
| `repro/` | **Source-tree bundle snapshot** (branch `line-coder390` @ `79457af`, packed 2026-10-12) + version ledger copy `MANIFEST.txt` | ✅ |
| `ninfer_launcher.py` | The single GUI entry (**three-brand model selection**, scene presets, validation warnings, KV_ENV six-switch injection, `MODEL_BUNDLES` tier linkage) | ✅ |
| `serve_tee.py`, `start-coder390*.bat` | Serve helpers | ✅ |
| `engine-src/` | **Engine source-tree working copy** (the build actually reads `engine-src\src-tree\fusion-engine-src`; root has `PROVENANCE.md` and full git history) | ❌ untracked (the in-repo snapshot = `repro/*.bundle`) |
| `official-repo/` | Public upstream comparison clone (**this line's build does not read it** — the build reads `engine-src/`) | ❌ untracked |
| `engine/` | Built binaries (~6.5 GB) | ❌ local build |
| `models/` | The model trio (~40 GB, see below) | ❌ external download + processed by this repo's scripts |
| `refs/` | Distribution package & Bonsai-line reference material (**not in repo** → external reproducers can't get it; see the reproduction guide) | ❌ |

### The models/ trio (one evolution chain)

**Download address for this line's original file (measured source, ModelScope)**:
[`Merkyor/Qwen3.8-27B-Coder390-EfficientThink-...-RLOO-GGUF-NInfer/tree/master/GGUF-NInfer`](https://modelscope.cn/models/Merkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-GGUF-NInfer/tree/master/GGUF-NInfer)
(HuggingFace upstream reference: [the nerkyor namesake series](https://huggingface.co/nerkyor), Apache-2.0; "Q2LynnStyle" is a Lynn-style q2 mixed-precision quantization label)

```
MTP.ninfer (orig original, 13.27 GB, the NInfer container of the ModelScope download above; no head, no vision)
  └─ recode_mtp.py extracts & self-converts the MTP head (iq4_nl, 239 MB)
       → mtp-iq4nl.ninfer (13.27 GB, the text workhorse)
            └─ graft_vision.py grafts the vision tower built into the model author's container, byte by byte (333 objects, 282 MiB)
                 → mtp-iq4nl.vision.ninfer (13.57 GB, the vision workhorse)
```

**2026-11-07 convergence (dual-head artifacts, replacing the last item above)**: `graft_dflash2.py` **keeps** the MTP head by default (`--drop-mtp` is what discards it), so two speculative heads can live in a single artifact —
`Qwen3.8-27B-Coder390-MTP+DFlash2.ninfer` (14.02 GiB) replaces `mtp-iq4nl.vision.ninfer` above, and **`--spec mtp` / `--spec dflash2` selects which head is loaded**.
MTP-mode VRAM usage is **identical** to the trio's last artifact (weights 12.3 GiB, same pool ceiling); only DFlash2 mode costs 1.2 GiB more (the drafter's q/k/v live in BF16).
The SWIFT line works the same way: `swift15_iq3s_mtp+dflash2.ninfer` (13.29 GiB) replaces both the original single-MTP artifact and the pure-DFlash2 artifact.
The three superseded single-head artifacts have been deleted; hashes and the rebuild recipe are recorded in `work/data/deleted-single-head-20261107.txt`.

## Upstream repos

```
[Our family] GitHub user paicat1, three repos iterating generation by generation (see the three-repo table at the top of the README)
  Repo 1 [paicat1/Bonsai-27B-NInfer](https://github.com/paicat1/Bonsai-27B-NInfer)
       (main=project layer / engine-main=engine layer, one repo, two branches)
       Bonsai-2-27B ternary quantization (2.125 bit, 9.81 GiB) running on NInfer: Ambolio port +
       CraneBW kernels, CMake changes, self-produced v2 artifacts; Device/Host two-tier KV (passive capacity);
       MTP/DFlash2 speculation. Extremes: prefill 2,850 / decode 396.9 tok/s; 89|120a
    └─ Repo 2 [paicat1/Bonsai-27B-NInfer-kvmem](https://github.com/paicat1/Bonsai-27B-NInfer-kvmem)
         KVMem ring (active retrieval): small VRAM pool + host offload, capacity may be smaller than the context, content-scored
         SELECT, six switches; hybrid speculation dflash2(K1-15)+MTP(K1-5)+ngram, K=7 sweet spot
         (collapse at K≥10), acceptance-rate corpus effect (counting numbers 91% vs prose 3.7-13.4%);
         fully self-built engine (MSVC patches ×7 + Design C fixing "thinking-stop empty content") + dual-engine comparison;
         self-built GUI launcher and serve_tee. Extremes: prefill 3,820 / decode 748.6 tok/s
         (local deployment / working copy = J:\KVMem-GSQ)
       └─ Repo 3 [paicat1/Ninfer-KVMem-Async](https://github.com/paicat1/Ninfer-KVMem-Async)【★this repo, origin points to it★, renamed from Qwen38-27B-NInfer-kvmem on 2026-10-13】
            Bigger model Qwen3.8-27B-Coder390-EfficientThink: self-converted MTP head (iq4nl),
            three linked thinking-fuse defect fixes (W1-W4), growth verdict, pool calibration 51,200,
            vision-tower graft, 256K logical context; landing prep for Qwen 4 27B (Bonsai/NInfer formats)

[Upstream]
  [1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem) (source of the engine code; this line's s6-20261008 @3b9dc837
  → self-built self-built-20261008; 23 commits behind its main)
  [tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring) (ring algorithm) + [kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3) (strategy layer) → merged into that repo
  NInfer base: [Neroued/ninfer](https://github.com/Neroued/ninfer) → [ashalliants/ninfer-3090](https://github.com/ashalliants/ninfer-3090) (0.11.0-rtx3090) → [iamwavecut/ninfer-all](https://github.com/iamwavecut/ninfer-all)
  Official upstream: **[kvmem/kvmem](https://github.com/kvmem/kvmem)** (dual backend llama.cpp + NInfer; the former `kvmem/kvmem-llama.cpp` **declared retired, migrated into this repo**; the RC2 line = iamwavecut/ninfer-all + the KVMem integration pack)
```

- The upstream's 23 new commits were reviewed one by one (build history §12): no engine behavior-level changes; B34=page drift, B35=wall, B37=compaction-summary truncation each map to fixes or mitigations in this line; absorption via cherry-pick (see `docs/03-归因与结论/上游谱系与跟踪纪律-20261011.md`, Chinese).

## From-zero reproduction guide

**Prerequisites**: Windows · RTX 5080 16 GB (or similar) · 128 GB RAM · VS2022 BuildTools (C++20, CMake, Ninja) · vcpkg (on this machine `J:\vcpkg`) · CUDA 13.3 · Python 3.12 · **the PCIe slot should run at Gen4** (Gen5 + VRAM contention measurably triggers WHEA storms; this machine's BIOS is already downgraded to Gen4; data across PCIe generations is not directly comparable).

1. **Engine source** — the source must land at **`engine-src\src-tree\fusion-engine-src\`** (the `SRC` on line 34 of `build\s6_1208a.bat` reads from here). Two options:

   **A0. This repo's `engine-main` branch (most direct · isomorphic to the prior two repos; after going public no permission needed, clone directly)**: this repo = **one repo, two branches** (`main`=project layer / **`engine-main`**=engine layer; tag **`engine-20261013`**):
   ```bat
   git clone -b engine-main https://github.com/paicat1/Ninfer-KVMem-Async.git engine-src
   ```

   **A. This repo's snapshot bundle (offline alternative · full git history)**: `repro/` carries a self-contained source-tree bundle:
   ```bat
   git clone repro\qwenline_line-coder390_20261013_r2.bundle engine-src
   cd engine-src && git checkout line-coder390 && cd ..
   ```
   Snapshot = branch `line-coder390` @ `da5a710` (**packed 2026-10-13 · current baseline**, tag `H1_20261013_baseline`; includes the ledger-54 fix `35173e0`; iterate-1 `c800106` already reverted);
   sha256 = `9BF92C8C565F4289EC0417604A060E9E3B9C7BC9C3BBF09E954183248256E9EE` (**includes `refs/tags/H1_20261013_baseline`**); the repo root contains `PROVENANCE.md` (lineage/fork record) and `patches/`.
   *(Measured: `git bundle verify` passed + one real clone confirmed `src-tree` / `PROVENANCE.md` / `patches/` all present.)*
   *(Older snapshots remain in the repo: `repro\qwenline_line-coder390_20261012.bundle` @ `79457af`; and the first-cut `…_20261013.bundle` (no tag, sha `B25CD543…`).)*

   **B. Build from the public upstream (traceable)**: `git clone https://github.com/1314521gjy/ninfer-fusion-kvmem.git` →
   `git checkout engine-v0.11.0-kvmem-20261008` (**`2852f6f`**, upstream tag, verified to exist in `official-repo/ninfer-fusion-kvmem`) → place at `engine-src\src-tree\fusion-engine-src\` →
   apply in order `build/patches/0001-0003` (= the 3 local commits on the baseline: `5b07bc1` MSVC fixes / `a25012b` Design C / `3b9dc83` test STANDALONE, **curated into the repo**) + the **19 patches** under `patches/` (this line's I3b chain p2→s11 + ledger series + W1-W4, applied in order, yield the current engine: segment-level stamps + four-layer op-group stamps + runtime PDL switch).
   ⚠️ *Path B is **not step-by-step verified**; A is authoritative.*

   **Build-free alternative**: the distribution package (from Shen Sanshu) provides **prebuilt engine exes** (pick one for your GPU, ~1.1 GB) — if you just want to run it without coding, use that;
   overview at `refs/01-沈三殊-发放包/00-先读我-总纲（必下与选下）.md`, download list at `…\01-模型下载清单（推荐链接）.md` (addresses/sizes/sha256/acceleration);
   ⚠️ **`refs/` is not in the repo**; you must obtain it yourself (ask the author Shen Sanshu).

2. **Apply fixes**: `git apply patches/W1-W4_engine_fix.patch` (W1-W4: thinking-budget fuse `==`→`>=`, no more abort on overflow, control forced to close, prompt-progress gating relaxed — all four measured & accepted); other patches as needed (the 8 non-I3b: ledger42×3 / ledger44 / ledger46×2 / ledger47 / W1-W4).

3. **Build**: `build\s6_1208a.bat` (or a VS environment + `cmake --build <dir> --target ninfer-serve`; essentials in `build/README.md` and `build/patches/`); deploy artifacts to `engine/self-built-20261008/`.
   ⚠️ **Two hard disciplines added 2026-10-18/19** (cost: a scrapped 66-minute cold build + an entire verdict-experiment night):
   - **Always pass `-DCMAKE_CUDA_ARCHITECTURES=120a -DNINFER_SM120_NATIVE=ON` explicitly** — CMake's default lands on sm_86, which this machine (sm_120a) cannot load directly ⇒ the PTX JIT grind presents as a "startup hang" (§128 root cause);
   - **Product acceptance must check the arch with `cuobjdump --list-elf`** (384 cubins all sm_120a, 0 sm_86 to pass the gate);
   - **If the build will run Gen5 / external-pressure long holds: inject symbol linkage** (env `/Zi` + `LINK=/DEBUG`, the offi recipe) — the three-binary matrix verdict shows **no-symbol builds hang there while symbol-linked builds "valley but complete"** (§136; everyday Gen4 production unaffected).

4. **Model processing**: download the GGUF-NInfer container from the ModelScope address above (this is `--mtp-src`; it carries a built-in q8_0 MTP head and vision tower) and the original file →
   `python scripts/recode_mtp.py --src <original>.ninfer --mtp-src <download>.ninfer --mtp-src-format gguf_q8_0 --target-format gguf_iq4_nl --dst ...mtp-iq4nl.ninfer --verify` →
   `python scripts/graft_vision.py` (graft the vision tower from the same download).

5. **Serve & verify**: the command line above (or the launcher) → `curl 127.0.0.1:8094/v1/models` → `python scripts/test_ab_arm1.py` (health probe).

**Absolute paths to change when switching machines/directories** (34 files in this repo hardcode `J:\`; main concentrations): `build\s6_1208a.bat` (`SRC` / `VCPKG_ROOT` / CUDA 13.3 — on this machine `J:\Bonsai\landing\cuda-13.3`, **an external line directory · read-only reference**), `build\*.ps1` and `build\s6*.bat`, `deploy_engine.ps1`, `start-*.bat`, `ninfer_launcher.py`, `scripts\*.py`.

**Reproduction difficulty self-assessment: medium-low (path A fully measured).** Engine source available two ways (this repo's bundle snapshot measured clonable / public upstream + patches is the unverified path), the distribution package has prebuilt exes (the build-free path), model downloads include a sha256 manifest, build scripts/parameters/acceptance probes all in this repo — every avenue is explicit; the main work is the CUDA environment + model download + serving per `docs/00-入口与说明/教程-KVMem与短测-给agent与使用者.md`. The only non-public item is the distribution package itself (ask the author Shen Sanshu, or bypass it by building from source).

## Key engineering conclusions (all measured; lessons from real potholes)

- **`--kv-lease-growth` is the wall's root cause**: in the deep over-pool configuration (pool 49-55K ≪ logical 256K) the lease window (~4,096 tok) cannot expand and output gets cut (bounded completion, `finish_reason=length`) — to protect output in over-pool configurations **do not enable it** (same stance as the fusion engine's upstream README line 218). Removed from the final spec; wall eliminated (two rounds of DSH agentic measurement: 16,143/11,782 tok continuous output, zero truncation).
- **Pool calibration**: 57,344 ✗ (short 17-50 MiB, varies with desktop load) / 55,296 pool-edge not reproducible / **51,200 stable**; **65,536 measured success** (2026-10-11; needs `--cuda-graph-allowance-mib 64~128` + desktop ≤~1.0 GiB — WDDM returns are not immediate, varies day to day).
- **Ledger #39 (closed, 2026-10-11)**: vision requests + no-growth once triggered a `scatter.cpp:18` assertion (HTTP 500) — no longer reproduces on the active engine (V1b/V1c measured); vision uniformly hemostat=on (no growth); growth has exited all paths.
- **KVMem ring = single concurrency**: the ring cannot reclaim another lane's device pages; `--max-concurrency >1` is rejected at startup — **concurrency and 256K depth/retrieval are mutually exclusive**.
- **W1-W4 fixed** (three linked thinking-budget fuse defects + streaming keep-alive); patch and four-fold acceptance in `patches/`.
- **Over-pool framing (B28)**: treat over-pool prompts' middle answers as "unverified" — the `NINFER_KV_RETRIEVE` retrieval switch is the lifeline.
- **Recall overhead measured**: over-pool prefill is absorbed by the pipeline (~8-23%, 60K-scenario round trip ≈4-8 s), zero truncation.
- **Push lesson**: push success is judged solely by `git status -sb` showing ahead 0.

- **SWIFT base swap measured (2026-10-14)**: `rk8v4` is fastest on Swift with the highest acceptance (deep 60K 37.3 s / decode 143.7 / 64%), and **verbatim-identical** output to `rk2v4-e8`; `nvfp4` = the "free tier" (speed ≈ status quo); **int8 ceiling 61,440** (65,536 refused, 35 MB short); the base swap first unlocked "pool 81,920 + high-precision KV".
- **Pool ≥ context (not just speed — comparability)**: over-pool ⇒ retrieval/page-selection intervenes ⇒ the model sees "a selected subset" ⇒ **output changes** (measured same-format difference only in pool size: `78bcb798` vs `8b3a141f`); all content comparisons (verbatim gate / golden SHA) **must run with pool ≥ context**.
- **Two pool regimes and where each applies (adjudicated 2026-10-31, ledger C1)**: **not a conflict — two axes** — (1) **external quick-start (conservative)**: pool ≥ max prompt; use for deployment advice and cross-machine reproduction; cost = VRAM pressure (32K–64K typical on a 16 GB card); (2) **research-grade small pool**: a 4,032-token pool serving a 94.7K prompt with zero silent errors (10-28 matrix); use for internal experiments / teaching and mechanism probing; requires reading the `kvmem_score: SELECT` row count and treating over-pool middle answers as "unverified" (B28). ⇒ **Publish (1) to external users; (2) may be cited only together with "middle unverified + check SELECT"** — never cite "a small pool also works" as a deployment rule.
- **Valley (slow state) manhunt progress (updated 2026-10-19)**: **the trigger's three conditions are pinned** (§135 six-batch matrix) — **AND** (Gen5 PCIe + external VRAM pressure ≥400 MiB + free VRAM at pool-edge <400 MB); missing any one, no trigger (8/8 healthy at zero pressure; on Gen4, 68 probes, 0 valleys); **mechanism still converges on host-side submit calls** (`submit ≈ wall`, `wait = sync ≈ 0`, driver-internal blocking), **PDL ruled out by on/off toggle counter-example**; host path / page tiers / pool size / throttling each excluded by measurement; **WHEA storms time-aligned shot-by-shot: no causal link to the valley** (co-occurrence); **"hang" vs "valley" split** — no-symbol builds hang under Gen5+pressure (culprit = missing symbol linkage, §136), symbol-linked builds "slow but complete" under the same conditions; an ≈2-minute minimal reproduction protocol is ready (for community/upstream review). See the ★ 2026-10-18/19 record and the [public note](docs/00-入口与说明/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md) §5.1 (Chinese).
- **Display name ≠ real name**: `--model-id` switches automatically by weight file and tools read it from `/v1/models`; `.ps1` files containing Chinese must be saved as **UTF-8 with BOM** (PS 5.1 decodes them as GBK and breaks parsing).

## Model support boundary & evolution direction

| Status | Model | Notes |
|---|---|---|
| ✅ **Verified** | Qwen3.8-27B family (`Coder390-EfficientThink` Q2LynnStyle quantization, NInfer container) | every measurement in this repo (two rounds of DSH agentic on arm A, recall probes, vision recognition) ran on it |
| 🔶 **Theoretically loadable, unverified** | **other Qwen 3.8 27B NInfer containers** (e.g. the `neroued/Qwen3.8-27B-NInfer` upstream conversion listed in the distribution package) | the engine eats `.ninfer` containers; isomorphic containers should load; MTP head/vision need re-processing per model (scripts reusable) — **never run, no promises** |
| 🔶 **Theoretically loadable, unverified** | other Qwen series (e.g. NInfer conversions of Qwen3.6-27B/35B) | same; needs verification first when architecture params (KV layer layout / head_dim) differ |
| 🎯 **Design target** | **Qwen 4 27B in Bonsai and NInfer formats** | this repo's pool/ring/retrieval/processing chain exists as landing prep for the next-gen model: when the container arrives, re-run the processing scripts and board |

> Processing chain is container-decoupled: for any new NInfer container, just re-run `recode_mtp.py` (MTP head self-conversion) and `graft_vision.py` (vision graft) — parameters and acceptance probes are all ready.

## Resolved-issues archive (chronological)

> Every row is the complete closed loop of a real pothole: problem → symptom → root cause → fix → verification. Evidence chains in `docs/ninfer-kvmem-项目构建史.md` (Chinese).

| # | Problem | Symptom | Root cause | Fix | Test & verification |
|---|---|---|---|---|---|
| 1 | 27B onboarding | MTP head format incompatible with the engine, won't load | official container's MTP head is gguf_q4_0 (unsupported) | `recode_mtp.py` self-converts the MTP head to iq4_nl (202 MB smaller) | decode 105 tok/s; SHA-256 skeleton 804 objects, zero mismatch |
| 2 | Vision tower missing | base file has no vision capability | vision tower not shipped with the container | `graft_vision.py` grafts the whole 282 MiB vision tower (q4/q5 mixed, CPU-encoding optimal ratio) | real image recognition succeeds ("striped gradient + concentric rings"); modalities.vision=true |
| 3 | worker crash not self-healing (B01) | over-pool + large output → worker crash / silent exit, all later requests fail | lease-reservation failure path has no fallback | `--recover-invariant-failures`: on failure only the current request is discarded | deep over-pool probe: engine survives, request-level failure |
| 4 | E5 growth hemostat backfires (**DSH wall**) | output always cut at ~4,037-4,071 (the "30-second wall"), DSH shows "output limit reached" + "continue" loop | `--kv-lease-growth`: in deep over-pool the lease window (~4,096) cannot expand → bounded completion (finish=length) — **truncation, not throttling**; unrelated to max_tokens/tb | **remove growth** (official README:218 same stance); A/B measured verdict | wall eliminated: two rounds of DSH agentic 16,143/11,782 tok zero truncation; 22 wall-cut events → 0 |
| 5 | Thinking-wall loop | xhigh thinking burns the output budget → empty content | thinking tokens counted inside the output budget (inclusion) | `--default-thinking-budget 16000`; from engine S3 the OpenAI endpoint parses per-request `thinking_budget` (request value wins) | mid thinking closes normally; probe medium 2-4K natural stop |
| 6 | W1-W4 fuse/keep-alive defects | over-budget throw, fuse `==` never triggers, handover refusal, progress gated (DSH watchdog false-kill risk) | three linked defects in the engine's defensive paths + streaming empty choice | patch fix (`patches/W1-W4_engine_fix.patch`; W2/W3 accepted before W1) | four-fold acceptance (build-history construction batch) |
| 7 | Vision flash-exit loop | enabling vision at startup → `missing component vision` refused four times | model file (iq4nl) has no vision component, mismatched with the vision switch | launcher interlock: enabling vision auto-switches to the iq4nlvis grafted file | serve succeeds after interlock; validate warnings prevent manual edits |
| 8 | Six KV switches: missing one silently answers wrong | missing any one: starts, high cache hit, **answers wrong in the middle, zero errors** | missing any ring/retrieval/window switch silently degrades (the sixth, `NINFER_KV_SINK=5120`, added 10-11 benchmarking official D-01) | launcher injects the six `KV_ENV` switches (incl. `NINFER_KV_WINDOW` — without it, refuse to start) | 20,203-tok over-pool prompt retrieval answers correctly (restored=128) |
| 9 | Ledger #39: vision × no-growth | vision request HTTP 500 (`scatter.cpp:18` assertion) | old-engine scatter path defect | no longer reproduces after engine updates; launcher's three interlocks removed (vision uniformly on) | V1b/V1c serve + decode 108.2 functional verification; case closed |
| 10 | Pool calibration & 64K startup | 65,536 pool refused, 213 MiB short; after freeing VRAM still 149 short (WDDM returns not immediate, trickle ~36 MiB/30s) | runtime reservation (CUDA Graph driver state) auto-computes oversized per profile | `--cuda-graph-allowance-mib 128` squeezes the graph budget to close the gap | 64K serve in 25 s; decode 101.1 (baseline 101-104, **zero cost**); launcher 64k tier bound to this param |
| 11 | DSH maxTokens full reservation | single request reserves prompt+output in full; the 65,536 output cap enlarges the over-pool surface | thinking counted in output + DSH default 65,536 | DSH `maxTokens` → 24,000 (per-turn cap; with prompt ≤41,536 decode never over-pools) | verified: live started line `max output 24,000` |
| 12 | Long-session "page drift" slowdown | after 34-39 turns of agentic session, decode 122 → 3 tok/s, host 98-110% | cache replay re-maps history pages each turn, **earliest pages gradually squeezed out of the device pool** (after 34 turns ~330 pages stuck on host → per-token host round trips) — triggered by **turn count**, unrelated to over-pool depth (three comparisons: 81K/72K/72K all steady at 134/126/134) | mitigation: start new sessions periodically (mechanism-required) + pool growth (28→~38 turns before triggering) + maxTokens cap; **root fix = the full ledger-42 chain** (cancel-checkpoint moved forward + batch demote + **v2 async demote**) = deployed + live-verified ✓ (over-pool multi-turn 103-195 tok/s, 10+ turns no slowdown, §三·十九; v2.1 multi-batch in-flight built ✓ §三·二十四) | mechanism independently evidenced twice (hidden-page discrimination: no-slowdown ≤17 vs slowdown 329-334) |
| 13 | stream hang (formerly ledger #41) | request started, never done: silent log + CPU 0 / GPU idle + TCP Established; restart to recover (req#4 scene, DSH "thought-chain break") | 🔀 **merged into ledger #42** (third reproduction verdict; the v3 scale-corrected version falsified "send blocking"): root cause converges uniquely = **a sync point deep in page operations freezing in the extreme state of page drift** (§14.1) | the no-"cancel-signal" deadlock form split into **ledger #43** (step-level watchdog, undesigned ✗); not reproduced since the ledger-42 chain deployed (pending long-run observation) | third reproduction verdict: 16K output / 270KB payload / 20 s true read stop (v3 scale-corrected) ✓ |
| 14 | Valley (slow state) scope convergence | decode 25–28 (occasionally 11–12), SM 100% at full clock but only 63–98 W, barely touches VRAM, parallel cores **not** starved (2026-10-16 external-process measurement 6–8 µs; the old "starved 8×" wording retracted — **no original measurement record found**) | after excluding machine/driver/downclock/bandwidth, every config knob (bisection clean), and the KV/ring/demote main chain (bare decode full speed), locked onto the **MTP in-graph target segment** | S6 `%globaltimer` segment-level stamps (graph 1107→1112 nodes, capture-safe); disabling MTP cures it | in-valley A-B-A sandwich (44.2 s→9.3 s→44.6 s, not self-healing); **10-19 verdict: trigger = AND of three conditions (Gen5 + pressure ≥400 MiB + pool-edge); hang/valley split (culprit = missing symbol linkage, symbol-linked builds no longer hang); mechanism still on the host submit path (line-level pending)** |
| 15 | Launcher "two models" confusion | command line shows both `swift15_iq3s_mtp.ninfer` and `--model-id qwen3.8-27b-coder390` | display name hardcoded to the old line's name, not synced on swap | `engine_ctl` switches automatically by file + `scripts/_modelid.py` reads from `/v1/models` | measured `/v1/models` reports only the real name; tool side auto-resolves (a2gate single turn normal) |
| 16 | Chinese-containing `.ps1` instant exit | watcher scripts won't start: `Unexpected token '}'` | PS 5.1 decodes **BOM-less UTF-8** as GBK; Chinese strings mis-parsed | 5 scripts re-saved as UTF-8 with BOM | 5/5 `PS-SYNTAX-OK` |

> **Open items** (authoritative ledger = [build history §四·挂账表](docs/ninfer-kvmem-项目构建史.md) rows 1–28; current heads below): **valley line-level root cause** (the exact blockage point on the host submit path; the dump route is closed in favor of live observation: in-valley nsys stack sampling / spin-stamp segmentation); **Gen5 switch-back retest** (pre-registration stands: `docs\02-实验与预登记\实验-Gen5回切复测-预登记-CB-20261019.md`; stop if WHEA recurs); **deep-load long-run async ON/OFF comparison** (async's decisive test; shallow load already shown indifferent); **SWIFT1.5 visual re-verification** (user-side restart check after the model-id fix); **ledger table §60–§139 backfill** (table body lagging, to avoid old states contradicting new conclusions). Historical small-number ledger items (43/46/48/49/54/55/W5 etc.) are mostly merged into the above or closed; per-item status per the ledger.

## Known limitations

- **Valley (slow state) not closed** (trigger = three-condition AND pinned; line-level root cause pending): triggers only when **Gen5 PCIe + external VRAM pressure ≥400 MiB + free VRAM at pool-edge (<400 MB)** hold simultaneously (missing any one, no trigger); during it decode drops to 25–28 (occasionally 11–12) while the machine itself is healthy; mechanism converges on host-side submit blocking (driver-internal), PDL ruled out; **the only confirmed mitigation = avoid VRAM contention with the engine + (this host now runs Gen4)**; during a valley, bare decoding (no `--spec`, ~56 tok/s) works around it; the watcher records valley-window evidence automatically; within the trigger domain the wording is "a stably triggerable dose exists (3/3, n=3, single machine)", **not "triggers under arbitrary conditions"** — check the three conditions before attempting reproduction;
- **C12: first request after idle hangs (first observed 2026-10-16, never reproduced)** — after a long idle, the engine's first request **may never return**: zero stderr (not even stamps), GPU near-idle (util ~2%, ~26 W), request log has start but no completion, **26 minutes without self-heal; only a restart recovers**. Active reproduction attempted (idle 5 / 25 min × VRAM pressure, 2×2 grid) — **all answered normally** ⇒ **trigger unknown**. **If it happens, restarting the engine recovers**. Different from the "valley": the valley is "slow but self-heals", this is a "hang". **2026-10-19 clue**: the three-binary matrix verdict confirmed the same form as "no-symbol build × Gen5+pressure ⇒ hangs"; C12's relation to symbol linkage/Gen5 awaits re-judgment along that clue (**switching to symbol-linked builds offi/sym3 or staying on Gen4 greatly lowers the risk**). **Reproducible clues welcome**;

- Single concurrency (KVMem ring architectural constraint);
- 256K is the model-native cap — 512K is extrapolation territory, unusable (long-document scenarios fall back on KVMem retrieval);
- vision CPU encoding ~20 s/image (GPU encoding needs the vision tower resident at 1.4 GiB VRAM, requiring the pool to drop to ~20K);
- over-pool middle correctness depends on the retrieval switches (B28); **and "over-pool" itself has a risk surface**: `prompt > pool` ⇒ middle hidden + page-ledger risk (32K pool with 40-49K prompts measurably triggered device-page invariant failures (§三·二十二); a 64K pool with 72.7K escalated to request-level 500 in ~11% of cases (§三·二十五)) ⇒ **the pool must be ≥ the expected max prompt**.
- **Small-pool regime (parallel to the line above; pick by use case)**: the line above is the **deployment** rule; for **research/teaching** a far smaller device pool works — measured **4,032-token (63-page) pool serving a 94.7K prompt (23.5× over pool), both rounds correct, zero silent errors** (`docs/00-入口与说明/教程-KVMem与短测-给agent与使用者.md` §2/§3; 10-28 matrix). **Two preconditions**: (1) read the `kvmem_score: SELECT` row count (how much the model actually saw); (2) over-pool middle answers still count as "unverified" (B28), and pool-edge failures remain possible (device-page invariant failures / request-level 500) ⇒ **keep deployments on the previous rule (pool ≥ expected max prompt)**; treat small-pool results as research-grade citations only.

## Document index

- **`docs/00-入口与说明/快速上手-自助路径.md`** — **for those who want to get it running**: path overview (official kvmem pack / self-built engine / status of the Shen Sanshu channels, verified 2026-10-21), three-engine compatibility warnings, verified model sources, liveness check & common pitfalls (Chinese);
- **`docs/99-附件/异步页流水-技术说明.pptx`** (Chinese slide deck; English version `Async-Page-Pipeline-Technical-Brief.pptx`) / **`docs/00-入口与说明/公开说明-异步页流水原理与改进-CodeBuddy-20261015.md`** (public plain-language note, Chinese) — the outward introduction & principles;
- **`docs/ninfer-kvmem-项目构建史.md`** — §1–§140 complete record (evidence chain per decision + ledger), **read this first** (Chinese);
- **`docs/01-构建与发布/引擎启动参数与配置档-20261014.md`** — per-parameter explanations + two-tier configs (SWIFT current / Coder390 finalized) + the six env-var switches (Chinese);
- `docs/00-入口与说明/教程-KVMem与短测-给agent与使用者.md` — usage tutorial (Chinese);
- `docs/KV档A-B-*` / `docs/03-归因与结论/深上下文池收益与A2适用域-20261014.md` / `docs/03-归因与结论/Swift换底座-三臂结果与int8预算-20261014.md` — the precision-pool-base three measurement set
- `docs/判据-测量与轮次纪律-20261030.md` — pool / round discipline (incl. "a research-grade small pool must be checked via the `kvmem_score: SELECT` row count")s (Chinese);
- `docs/审核-*.md` ×19 (plus `交叉审核-*` ×2) — TeleAgent & CodeBuddy bidirectional cross-review records (Chinese);
- **`docs/00-入口与说明/FAQ-死亡谷-20261016.md`** — the **valley FAQ** (how to tell / will it answer wrong / how to recover / how to prevent / what's excluded) (Chinese);
- **`docs/03-归因与结论/Minimal-Reproduction-Valley-On-Demand-20261016.md`** (EN) + `docs/03-归因与结论/研判-驱动提交阻塞-最小复现与可行动项-20261016.md` (Chinese) — the **≈2-minute minimal reproduction protocol** (one command: `scripts\valley_minrepro.ps1`), for community / upstream / driver-side review;
- **`docs/03-归因与结论/工程史-死亡谷根因排查与确定-CB-20261017.md`** — the Death Valley root-cause engineering history (the complete 120h manhunt chain: trigger/mechanism/exclusion matrix; for the "hang vs valley" variable-separation verdict, build history §136 is authoritative) (Chinese);
- `docs/调研-*.md` ×3 — tancau same-source engine comparison, wall mechanism, target paths (Chinese);
- `build/README.md`, `build/产物清单.md` — engine build details.

## Acknowledgements

**Contribution attribution (details in the build history)**:

- **[Neroued/ninfer](https://github.com/Neroued/ninfer)** — the NInfer engine base (the ancestor of this repo's engine).
- **[1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem)** — the fusion engine source (the direct origin of this line's `self-built-20261008` engine); the engine-layer implementation of the KVMem ring + host-backed checkpoint (core mechanisms incl. `ensure_sequence_kv_mapped`); the B33-B39 bug-manual case files and the docs/13/14 fix libraries.
- **[tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring)** — the original implementation of the KVMem ring algorithm (merged into the fusion engine); **the diff reference for this line's W1-W4 fixes** (the repair template for the three linked thinking-fuse defects); author-level conclusions on ring-reuse depth / recall boundaries / the decode wall (the brief — an important reference for this line's page-drift localization).
- **[kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3) (Di Chai)** — the retrieval strategy-layer algorithm (merged into the fusion engine).
- **[kvmem/kvmem](https://github.com/kvmem/kvmem) (Leye Wang / wangleye et al.)** — the KVMem **official dual-backend repo** (llama.cpp + NInfer): the tuning-default comparison (source of D-01..D-08), [issue #114](https://github.com/kvmem/kvmem-llama.cpp/issues/114) as a fix lead (filed on the pre-rename `kvmem/kvmem-llama.cpp`; the author has declared that repo retired, consolidated into `kvmem/kvmem`).
- **Shen Sanshu (shensanshu, GitHub: [1314521gjy](https://github.com/1314521gjy))** — the engine distribution package, the ternary-quantization toolchain and the model conversion chain (ModelScope `shensanshu/ninfer-ada-ternary`); **the fusion-engine repo `1314521gjy/ninfer-fusion-kvmem` is his GitHub repository** (with prebuilt NInfer+KVMem-ring Release binaries).
- **Merkyor / nerkyor** — the model weights (Coder390-EfficientThink-family NInfer containers, with built-in vision tower).

**This line's own work** (build history §一–§十七): the Qwen3.8-27B onboarding path (self-converted MTP head + vision graft), W1-W4 patch surgery & four-fold acceptance, growth-wall forensics & verdict, discovery & measurement of the three failure modes (page drift / sequence-rebuild storm / stream hang), **the async page pipeline (v2 transport layer) surgery & first battle at 333 tok/s** (a full upstream-materials audit found no same-kind implementation; see `docs/03-归因与结论/上游谱系与跟踪纪律-20261011.md` §6.5), pool calibration (51,200/64K/graph64), DSH integration (compaction-trigger tuning, maxTokens cap), the A/B methodology and probe scripts. Lineage of the two prior repos: see the three-repo table at the top.

## License & upstream

| Component | Source | License |
|---|---|---|
| NInfer engine base | [Neroued/ninfer](https://github.com/Neroued/ninfer) (baseline [ashalliants/ninfer-3090](https://github.com/ashalliants/ninfer-3090), 0.11.0-rtx3090) | Apache-2.0 |
| KVMem ring (merged into the fusion engine) | [tancau/ninfer-kvmem-ring](https://github.com/tancau/ninfer-kvmem-ring) | Apache-2.0 |
| Retrieval strategy layer (merged into the fusion engine) | [kvmem/kvmem-qw3](https://github.com/kvmem/kvmem-qw3) (Di Chai) | Apache-2.0 |
| Fusion engine (KVMem ring + host-backed) | [1314521gjy/ninfer-fusion-kvmem](https://github.com/1314521gjy/ninfer-fusion-kvmem) | Apache-2.0 |
| KVMem official repo (upstream reference, not merged) | [kvmem/kvmem](https://github.com/kvmem/kvmem) (dual backend; the former kvmem-llama.cpp retired & migrated) | see that repo |
| Model (Coder390-EfficientThink family) | ModelScope [Merkyor/...-RLOO-GGUF-NInfer](https://modelscope.cn/models/Merkyor/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-GGUF-NInfer) (measured download); HF `nerkyor` namesake series | Apache-2.0 |
| Ternary-quantization toolchain / conversion / verification | Shen Sanshu (shensanshu) · ModelScope `shensanshu/ninfer-ada-ternary` | see its release page |

This repo is an upstream-derived deployment/verification project (not the official publisher); see `LICENSE` (Apache-2.0) and `NOTICE.md`.
