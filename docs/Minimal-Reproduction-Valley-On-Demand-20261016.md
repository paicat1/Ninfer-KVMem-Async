# Minimal reproduction: driving the engine into the "valley" on demand (~2 minutes)

> Audience: community, upstream engine maintainers, GPU driver engineers.
> Everything below is measured on this repository's machine (RTX 5080 16 GB, Windows/WDDM, engine resident ~14.3-15.7 GiB).
> Chinese original: [`研判-驱动提交阻塞-最小复现与可行动项-20261016.md`](研判-驱动提交阻塞-最小复现与可行动项-20261016.md)

## What this shows

The engine (KVMem ring + async page pipeline, single stream, long-context agent serving) periodically enters a **slow but correct** state we call the *valley*. The whole per-round time is spent **inside the host-side submission call** (`submit ≈ wall`, `wait = sync ≈ 0`, semantics read back from the engine source). The state can be **produced on demand by holding VRAM from another process**, and it **recovers immediately on release**.

## Prerequisites

- Engine serving and healthy (`decode` around 160-170 tok/s; probe: `python scripts\a2gate.py --arm base --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200`).
- `tools\vram_hold.exe` (published in this repository; source `tools\vram_hold.cu`, build script `tools\build_triggers.bat`).
- A GPU whose free VRAM is already small (the engine runs near the edge; ~0.6-0.9 GiB headroom is typical here).

## The protocol (one command)

```bat
powershell -ExecutionPolicy Bypass -File scripts\valley_minrepro.ps1 -HoldMiB 1200 -HoldSec 240
```

It performs: baseline probe -> hold 1200 MiB from a second process -> probe during the hold -> release -> probe again, and prints a verdict table.

## Criteria (pre-registered)

| stage | expected |
|---|---|
| baseline | `decode` **160-170** |
| during hold | `decode` **3.6-14** (one to many slow probes; a 4-5 minute hold makes **100 % of probes** slow, reaching **~1.5**) |
| after release | **immediate** recovery to **163-168** |

**Dose and saturation**: external added demand **200 MiB ⇒ no effect at all (0/9 slow)**; **400-600 MiB ⇒ exactly one valley-grade probe per application**; **≥400 MiB held 4-5 minutes ⇒ sustained valley (decode ~1.5)**. The threshold is **absolute, not relative to the engine's headroom** (600 MiB triggers even with 909 MiB headroom).

## Self-test of this protocol (in this repository)

| run | baseline | during hold | after release | verdict |
|---|---|---|---|---|
| #1 | 162 | **2.2** (deep band) | 105 at +10 s -> **misread as not recovered** | not reproduced (criterion defect) |
| #2 | - | - | 36.5 -> 165 -> 161.9 | script error (fixed) |
| **#3 (final script)** | **163.3** | **6.3 / 6.3** (GPU 100 %, **73.9 W**) | **38.7 -> 164.9 -> 164.8** | **REPRODUCED** |

Two lessons are baked into the script: **recovery takes roughly half a minute** after a 4-minute hold
(so a single probe right after release misreads it), and the probe helper must return only the number
(the first version polluted its own result pipeline). The script now settles 20 s, reads a three-probe
trend, and **warns explicitly when the baseline is already slow** (in that case the during-reading
cannot be attributed to the hold alone).

## Observed fingerprint (independent of the trigger)

| signal | healthy | valley |
|---|---|---|
| GPU utilisation / power | 99 % / **240-271 W** | 99 % / **~109 W** (busy but not working) |
| `submit` vs `wall` (from `step profile`) | submit is a fraction | **submit ≈ wall**, `wait = sync ≈ 0` |
| last-layer `mixer` time | 0.19-0.24 ms | **4-160 ms** (inflates 20-100×), earlier layers untouched |

## What has been ruled out by direct measurement

PDL overlap wait (the original prime suspect - excluded by an ON/OFF reversal) · pageable bounce-buffer staging (only 15-20 % difference) · host-device path slowdown as a whole (1.30-1.49×, while the engine slows 8-12×) · both host-page profile dimensions (interleaved pairing 0/3) · pool size (no consistent ordering) · driver throttling (throttle reasons `Not Active` throughout) · engine VRAM headroom as the threshold (my own pre-registered prediction, **falsified**) · idling up to 25 minutes · idling combined with pressure (2×2 all negative for the hang).

## What is *not* proven (please read before citing)

- The **deep grade** (~1.5, i.e. 1/100) is **window-dependent**: across 12 long holds in one evening, **4/4 inside a "machine-state window" hit it and 8/8 outside stayed at valley grade**; the **conditions that open or close that window are unknown**.
- The valley and the deep grade are **not proven to be the same mechanism** (same signature family, different amplitude).
- The relationship between this on-demand valley and the machine's spontaneous episodes is **correlation, not causation**.
- The hang ("C12": idle, then the first request never returns; needs a restart) is a **separate pathology** with **unknown trigger**.

## What would help most (for driver / upstream side)

1. **WDDM-side evidence at the moment of the stall**: `GPU Engine` / `Local Adapter Memory` counters, driver event log, and ideally a stack capture of the blocked `cudaLaunchKernel` / stream submission call.
2. Whether a **driver-side eviction/repaging** path is plausible for a submission blocked for seconds while utilisation reads 99 % at one third of the healthy power draw.
3. Engine side: the tree already contains a pressure planner (`planning\pressure.cpp`) that trades VRAM for host-backed reuse; its policy under pressure could be made explicit instead of relying on implicit eviction.

## Raw evidence

All ledgers behind these numbers: [`baselines/valley-20261016/`](../baselines/valley-20261016/README.md) (40 files, with an index stating which report cites which file).
