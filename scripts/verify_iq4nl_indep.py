# -*- coding: utf-8 -*-
"""
INDEPENDENT re-quantisation oracle for the iq4_nl MTP-head recode.

This does NOT import recode_mtp. It re-derives iq4_nl from the ggml definitions
(block_iq4_nl = {fp16 d; uint8 qs[16]}, 18 B / 32 elem; kvalues_iq4nl; HALVED
nibble layout) and re-quantises the OFFICIAL Q8MTP MTP head (src = true 8-bit)
with the same LS-scale + nearest-codebook algorithm, chunked & vectorised, then
byte-compares against the produced .mtp-iq4nl artifact. Determinism => identical.
"""
import sys
import numpy as np
UP = r"J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
if UP not in sys.path:
    sys.path.insert(0, UP)
from tools.artifact.reader import Artifact

OFFICIAL = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer"
ART = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"
IDS = ["weight/000079","weight/000080","weight/000789","weight/000796","weight/000798"]
Q8_BLOCK, IQ4_BLOCK, ELEMS = 34, 18, 32
KV = np.array([-127,-104,-83,-65,-49,-35,-22,-10,1,13,25,38,53,69,89,113], dtype=np.float32)
CHUNK = 1 << 16

def quant(v):  # v: [m,32] fp32 -> (out [m,18], idx [m,32])
    amax = np.abs(v).max(axis=1, keepdims=True)
    d = np.where(amax > 0, amax / 127.0, 0.0)
    d = np.where(d > 0, d, 1.0)
    for _ in range(3):
        t = v / d
        idx = np.abs(t[:, :, None] - KV[None, None, :]).argmin(axis=2).astype(np.uint8)
        kvi = KV[idx]
        num = (v * kvi).sum(axis=1, keepdims=True)
        den = (kvi * kvi).sum(axis=1, keepdims=True)
        d = np.where(den > 0, num / np.where(den > 0, den, 1.0), d)
    t = v / d
    idx = np.abs(t[:, :, None] - KV[None, None, :]).argmin(axis=2).astype(np.uint8)
    d = np.where(amax > 0, d, 0.0)
    d16 = d.astype(np.float16)
    out = np.empty((v.shape[0], IQ4_BLOCK), np.uint8)
    out[:, :2] = np.ascontiguousarray(d16.view(np.uint8).reshape(-1, 2))
    out[:, 2:] = (idx[:, :16] | (idx[:, 16:] << 4)).astype(np.uint8)
    return out

def main():
    total = mism_blocks = 0
    with Artifact(OFFICIAL) as of, Artifact(ART) as cl:
        om = {o.id: o for o in of.directory.objects}
        cm = {o.id: o for o in cl.directory.objects}
        for oid in IDS:
            so, co = om[oid], cm[oid]
            assert so.shape == co.shape, (oid, so.shape, co.shape)
            s_raw = b"".join(of.iter_range(so.offset, so.bytes))
            c_raw = b"".join(cl.iter_range(co.offset, co.bytes))
            n = len(s_raw) // Q8_BLOCK
            assert n == len(c_raw) // IQ4_BLOCK, (oid, len(s_raw), len(c_raw))
            total += n
            sarr = np.frombuffer(s_raw, np.uint8).reshape(-1, Q8_BLOCK)
            d_in = np.ascontiguousarray(sarr[:, :2]).view(np.float16).astype(np.float32).reshape(-1, 1)
            q_in = sarr[:, 2:].view(np.int8).reshape(-1, ELEMS)
            v = d_in * q_in.astype(np.float32)
            theirs = np.frombuffer(c_raw, np.uint8).reshape(-1, IQ4_BLOCK)
            mb = 0
            for st in range(0, n, CHUNK):
                en = min(st + CHUNK, n)
                my = quant(v[st:en])
                mb += int((my != theirs[st:en]).any(axis=1).sum())
            mism_blocks += mb
            print(f"{oid:16s} blocks={n:9d} byte_mismatch_blocks={mb}")
    if mism_blocks:
        print(f"VERDICT: FAIL ({mism_blocks}/{total} blocks differ)")
        return 1
    print(f"VERDICT: PASS (independent re-quantiser identical on all {total} blocks)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())