# -*- coding: utf-8 -*-
"""
P1 L1 INDEPENDENT oracle - verifies the .mtp-q8.ninfer artifact is a BIT-EXACT
q4_0 -> q8_0 recode of the source MTP artifact.

INDEPENDENCE: this file does NOT import recode_mtp.  It re-derives the q4_0/q8_0
block layout from the ggml format definition itself (via raw byte parsing), so a
bug shared between recode_mtp.write and recode_mtp.verify (e.g. swapped nibble
order) would be caught here.

ggml block definitions (from ggml-quants.h / ggml_bridge.cu):
  QK4_0 = QK8_0 = 32 elements per block.
  q4_0 block = [ggml_half d (2B, little-endian)] [16B nibble-quants = 32 nibbles]
       value_i = (nibble_i - 8) * d         nibble_i in [0,15]
       nibble layout: byte j holds two values; low nibble = element 2*j,
       high nibble = element 2*j+1.
  q8_0 block = [ggml_half d (2B, little-endian)] [32 int8 quants q]
       value_i = d * q_i                     q_i in [-128,127]
So the exact recode is: copy d verbatim, store q_i = nibble_i - 8  (an integer
in [-8,7], fits int8).  No re-quantisation, no float math.
"""
import sys, os
import numpy as np

UPSTREAM = r"J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
if UPSTREAM not in sys.path:
    sys.path.insert(0, UPSTREAM)
from tools.artifact.reader import Artifact  # official reader, read-only

SRC = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"
DST = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-q8.ninfer"

Q4_0_BLOCK = 18   # 2 d bytes + 16 nibble bytes
Q8_0_BLOCK = 34   # 2 d bytes + 32 int8 bytes
ELEMS = 32

def parse_q4_0(raw):
    """Return (d_bytes[:,2], values_int16[:,32]) with q8 layout order (i = byte 2*j low nibble)."""
    a = np.frombuffer(raw, dtype=np.uint8)
    n = a.size
    if n % Q4_0_BLOCK:
        raise SystemExit(f"q4_0 payload {n} not multiple of {Q4_0_BLOCK}")
    b = a.reshape(-1, Q4_0_BLOCK)
    d = np.ascontiguousarray(b[:, :2])
    nib = b[:, 2:]                      # (n,16) uint8
    lo = (nib & 0x0F).astype(np.int16)  # byte j low nibble  -> element 2j
    hi = (nib >> 4).astype(np.int16)    # byte j high nibble -> element 2j+1
    q = np.empty((b.shape[0], ELEMS), dtype=np.int16)
    q[:, 0::2] = lo
    q[:, 1::2] = hi
    q -= 8
    return d, q

def parse_q8_0(raw):
    """Return (d bytes:2, q int8:32)."""
    a = np.frombuffer(raw, dtype=np.uint8)
    n = a.size
    if n % Q8_0_BLOCK:
        raise ValueError(f"q8_0 payload {n} not multiple of {Q8_0_BLOCK}")
    b = a.reshape(-1, Q8_0_BLOCK)
    d = np.ascontiguousarray(b[:, :2])
    q = b[:, 2:].view(np.int8).reshape(-1, ELEMS).astype(np.int16)
    return d, q

def main():
    report = []
    with Artifact(SRC) as src, Artifact(DST) as dst:
        s_by = {o.id: o for o in src.directory.objects}
        d_by = {o.id: o for o in dst.directory.objects}
        # target = q4_0 in source
        src_q4 = sorted(o.id for o in src.directory.objects
                        if getattr(o, "format", None) == "gguf_q4_0")
        print("src q4_0 objects:", len(src_q4))
        if not src_q4:
            print("FATAL: no gguf_q4_0 objects in source")
            return 1
        # every q4 in src must be q8 in dst with same id
        for oid in src_q4:
            so, do = s_by[oid], d_by.get(oid)
            if do is None:
                print(f"FATAL: dst missing object {oid}")
                return 2
            if do.format != "gguf_q8_0":
                print(f"FATAL: {oid} dst format {do.format} != gguf_q8_0")
                return 3
            s_raw = b"".join(src.iter_range(so.offset, so.bytes))
            d_raw = b"".join(dst.iter_range(do.offset, do.bytes))
            sd, sq = parse_q4_0(s_raw)
            dd, dq = parse_q8_0(d_raw)
            n_blocks = sq.shape[0]
            scale_ok = bool((sd == dd).all())
            value_ok = bool((sq == dq).all())
            mism = int((sq != dq).sum())
            print(f"  {oid:16s} blocks={n_blocks:9d} scale_bytes_identical={scale_ok} "
                  f"values_identical={value_ok} mismatches={mism} ({so.bytes}->{do.bytes}B)")
            if not (scale_ok and value_ok and mism == 0):
                report.append((oid, n_blocks, scale_ok, value_ok, mism))
    if report:
        print("L1 VERDICT: FAIL", report)
        return 4
    print("L1 VERDICT: PASS (bit-exact, full-block oracle, independent decoder)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())