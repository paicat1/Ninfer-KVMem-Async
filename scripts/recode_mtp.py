"""recode_mtp.py -- recode an MTP head's `gguf_q4_0` tensors to `gguf_q8_0` (BIT-EXACT) inside a NInfer v3 artifact.

WHY
    The Coder390 artifact declares its MTP head as `gguf_q4_0`, which the engine's
    format whitelist does not accept (`unknown tensor format: gguf_q4_0`), so
    `--spec mtp` cannot load.  `gguf_q8_0` IS supported.

WHY IT IS BIT-EXACT (no re-quantisation)
    q4_0 block = fp16 `d` + 32 nibbles, value = (nibble - 8) * d      (nibble in [0,15])
    q8_0 block = fp16 `d` + 32 int8,    value = d * q                 (q is int8)
    (nibble - 8) is an integer in [-8, 7] -> fits int8 exactly, and the engine
    decodes q8_0 as `d * q` (ggml_bridge.cu: `__half2float(b.d) * b.qs[...]`).
    Therefore: copy the two scale bytes VERBATIM and store `nibble - 8` as int8
    => the decoded values are identical bit for bit.  No float maths at all.

HOW (no re-implementation of the container)
    * read the source with the upstream reader (validates header/length/directory),
    * keep every object; only the q4_0 ones get a new format + recoded bytes,
    * hand the specs to the upstream ArtifactWriter, which recomputes the aligned
      object layout and refuses to publish unless every object got full coverage,
    * stream the untouched objects across -- bounded memory.

SAFETY
    Writes a NEW file only.  The source is never opened for writing; the writer
    refuses to overwrite an existing destination (FileExistsError).

USAGE
    python scripts/recode_mtp.py --src <src.ninfer> --dst <dst.ninfer> [--dry-run]
    python scripts/recode_mtp.py --src <src.ninfer> --dst <dst.ninfer> --verify
    python scripts/recode_mtp.py --src <src.ninfer> --dst <dst.ninfer> --negative-control
"""

import argparse
import os
import sys
from datetime import datetime

import numpy as np

# The upstream engine source tree ships the official Python artifact SDK.
UPSTREAM = r"J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
if UPSTREAM not in sys.path:
    sys.path.insert(0, UPSTREAM)

from tools.artifact.reader import Artifact  # noqa: E402
from tools.artifact.writer import ArtifactWriter  # noqa: E402
from tools.artifact.schema import ResourceObject, TensorSpec, ResourceSpec  # noqa: E402

SRC_FORMAT = "gguf_q4_0"
DST_FORMAT = "gguf_q8_0"
IQ4_NL_FORMAT = "gguf_iq4_nl"
Q4_0_BLOCK_BYTES = 18
Q8_0_BLOCK_BYTES = 34
IQ4_NL_BLOCK_BYTES = 18
BLOCK_ELEMS = 32

# ggml-common.h:1120 `kvalues_iq4nl` -- the 16-entry non-linear codebook.
# NOTE: asymmetric (max 113, min -127), and the qs layout is HALVED, not
# interleaved (dequantize.cuh:418-419):
#     y[j + 0] = d * kvalues_iq4nl[qs[j] & 0xf]    # LOW  nibble -> element j
#     y[j + 16] = d * kvalues_iq4nl[qs[j] >> 4]    # HIGH nibble -> element j+16
# q4_0/q8_0 are INTERLEAVED (low nibble -> element 2j).  Mixing the two up
# scrambles the head silently: the artifact stays valid and loads fine.
KVALUES_IQ4NL = np.array(
    [-127, -104, -83, -65, -49, -35, -22, -10, 1, 13, 25, 38, 53, 69, 89, 113],
    dtype=np.float32,
)

# metadata.name marker: the product is no longer the factory artifact (T-RECORD).
NAME_MARKER = "+mtp-q8"
NAME_MARKER_IQ4NL = "+mtp-iq4nl"

# L1 acceptance bound for the LOSSY iq4_nl path (relative absolute error over all
# blocks).  Bit-exactness is impossible there, so the oracle reports the measured
# error and this bound decides pass/fail.  Calibrate against the --probe-error reading.
MAX_REL_ABS_ERR = 0.10


def _blocks(raw, block_bytes):
    a = np.frombuffer(raw, dtype=np.uint8)
    if a.size % block_bytes:
        raise ValueError(f"payload {a.size} bytes is not a whole number of {block_bytes}-byte blocks")
    return a.reshape(-1, block_bytes)


def decode_q4_0(raw):
    """Return (scale_bytes[n,2], int8_values[n,32]) as stored on disk (no float maths)."""
    b = _blocks(raw, Q4_0_BLOCK_BYTES)
    d = np.ascontiguousarray(b[:, :2]).copy()
    nib = b[:, 2:]
    lo = ((nib & 0x0F).astype(np.int16) - 8).astype(np.int8)   # int16 first: uint8-8 would wrap
    hi = ((nib >> 4).astype(np.int16) - 8).astype(np.int8)
    q = np.empty((b.shape[0], BLOCK_ELEMS), dtype=np.int8)
    q[:, 0::2] = lo
    q[:, 1::2] = hi
    return d, q


def decode_q8_0(raw):
    """Return (scale_bytes[n,2], int8_values[n,32]) as stored on disk."""
    b = _blocks(raw, Q8_0_BLOCK_BYTES)
    d = np.ascontiguousarray(b[:, :2]).copy()
    q = np.ascontiguousarray(b[:, 2:]).view(np.int8).reshape(-1, BLOCK_ELEMS)
    return d, q


def q4_0_to_q8_0(raw):
    """Bit-exact q4_0 -> q8_0: scale copied verbatim, nibble -> int8(nibble - 8)."""
    d, q = decode_q4_0(raw)
    out = np.empty((q.shape[0], Q8_0_BLOCK_BYTES), dtype=np.uint8)
    out[:, :2] = d
    out[:, 2:] = q.view(np.uint8)
    return out.tobytes()


def decode_iq4_nl(raw):
    """Return (scale_bytes[n,2], table_index[n,32]) as stored on disk."""
    b = _blocks(raw, IQ4_NL_BLOCK_BYTES)
    d = np.ascontiguousarray(b[:, :2]).copy()
    qs = b[:, 2:]
    idx = np.empty((b.shape[0], BLOCK_ELEMS), dtype=np.uint8)
    idx[:, :16] = qs & 0x0F          # HALVED layout (not interleaved like q4_0/q8_0)
    idx[:, 16:] = qs >> 4
    return d, idx


def decode_any(raw, fmt):
    if fmt == SRC_FORMAT:
        return decode_q4_0(raw)
    if fmt == DST_FORMAT:
        return decode_q8_0(raw)
    if fmt == IQ4_NL_FORMAT:
        return decode_iq4_nl(raw)
    raise ValueError("no decoder for format %s" % fmt)


def _values(d_bytes, q):
    """Values implied by (fp16 scale bytes, integer codes), in float32."""
    d = np.ascontiguousarray(d_bytes).view(np.float16).astype(np.float32).reshape(-1, 1)
    return d * q.astype(np.float32)


def quantize_q8_0_to_iq4_nl(raw, iters=3, chunk=1 << 16):
    """LOSSY q8_0 -> iq4_nl: per block, alternate (a) nearest codebook entry for
    the current scale and (b) the least-squares optimal scale for the current
    assignment, then emit the fp16 scale + packed nibbles.

    Returns (bytes, stats).  stats carries the error measures the caller needs to
    judge whether the loss is acceptable -- this path is NOT bit-exact.
    """
    b = _blocks(raw, Q8_0_BLOCK_BYTES)
    d_in = np.ascontiguousarray(b[:, :2]).copy()
    q_in = np.ascontiguousarray(b[:, 2:]).view(np.int8).reshape(-1, BLOCK_ELEMS)
    n = q_in.shape[0]
    out = np.empty((n, IQ4_NL_BLOCK_BYTES), dtype=np.uint8)
    kv = KVALUES_IQ4NL
    err_abs = err_sq = val_abs = val_sq = 0.0
    max_abs_err = 0.0
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        v = _values(d_in[start:stop], q_in[start:stop])                    # [m,32]
        amax = np.abs(v).max(axis=1, keepdims=True)
        d = amax / 127.0
        d = np.where(d > 0, d, 1.0)                                        # guard div-by-zero
        for _ in range(iters):
            t = v / d
            idx = np.abs(t[:, :, None] - kv[None, None, :]).argmin(axis=2).astype(np.uint8)
            kvi = kv[idx]
            num = (v * kvi).sum(axis=1, keepdims=True)
            den = (kvi * kvi).sum(axis=1, keepdims=True)
            d = np.where(den > 0, num / np.where(den > 0, den, 1.0), d)
        t = v / d
        idx = np.abs(t[:, :, None] - kv[None, None, :]).argmin(axis=2).astype(np.uint8)
        d = np.where(amax > 0, d, 0.0)                                     # all-zero block -> d = 0
        d16 = d.astype(np.float16)
        err = d16.astype(np.float32) * kv[idx] - v
        err_abs += float(np.abs(err).sum())
        err_sq += float((err * err).sum())
        val_abs += float(np.abs(v).sum())
        val_sq += float((v * v).sum())
        max_abs_err = max(max_abs_err, float(np.abs(err).max()))
        out[start:stop, :2] = np.ascontiguousarray(d16.view(np.uint8).reshape(-1, 2))
        out[start:stop, 2:] = (idx[:, :16] | (idx[:, 16:] << 4)).astype(np.uint8)
    elems = max(1, n * BLOCK_ELEMS)
    stats = {
        "blocks": int(n),
        "values": int(n * BLOCK_ELEMS),
        "mean_abs_err": err_abs / elems,
        "rmse": (err_sq / elems) ** 0.5,
        "mean_abs_value": val_abs / elems,
        "relative_abs_err": err_abs / max(1e-30, val_abs),
        "snr_db": 10.0 * float(np.log10(max(1e-30, val_sq) / max(1e-30, err_sq))),
        "max_abs_err": max_abs_err,
    }
    return out.tobytes(), stats


def target_objects(directory, src_format=SRC_FORMAT):
    return [o for o in directory.objects if getattr(o, "format", None) == src_format]


_BLOCK_BYTES_BY_FORMAT = {DST_FORMAT: Q8_0_BLOCK_BYTES, IQ4_NL_FORMAT: IQ4_NL_BLOCK_BYTES}


def expected_bytes(obj, fmt=DST_FORMAT):
    """Encoded size for the same shape under `fmt` (both targets are 32-elem blocks)."""
    elems = 1
    for dim in obj.shape:
        elems *= dim
    if elems % BLOCK_ELEMS:
        raise ValueError(f"{obj.id}: element count {elems} is not a multiple of {BLOCK_ELEMS}")
    return elems // BLOCK_ELEMS * _BLOCK_BYTES_BY_FORMAT[fmt]


def oracle(src_path, dst_path, ids, src_fmt=SRC_FORMAT, dst_fmt=DST_FORMAT, chunk=1 << 16):
    """L1 over the written artifact: every block, never sampled.

    * bit-exact target (q8_0): scale bytes and integer codes must be identical;
    * lossy target (iq4_nl): cannot be bit-exact, so measure the reconstruction
      error of the WRITTEN artifact against the SOURCE values and report it --
      the caller applies the threshold.

    `src_path` is the file the MTP head DATA came from (may differ from the file
    whose container skeleton was reused).
    """
    report = []
    with Artifact(src_path) as src, Artifact(dst_path) as dst:
        src_by_id = {o.id: o for o in src.directory.objects}
        dst_by_id = {o.id: o for o in dst.directory.objects}
        for oid in ids:
            so, do = src_by_id[oid], dst_by_id[oid]
            s_raw = b"".join(src.iter_range(so.offset, so.bytes))
            d_raw = b"".join(dst.iter_range(do.offset, do.bytes))
            sd, sq = decode_any(s_raw, src_fmt)
            dd, dq = decode_any(d_raw, dst_fmt)
            entry = {
                "id": oid,
                "blocks": int(sq.shape[0]),
                "src_bytes": so.bytes,
                "dst_bytes": do.bytes,
                "src_format": src_fmt,
                "dst_format": dst_fmt,
            }
            if dst_fmt == IQ4_NL_FORMAT:
                err_abs = err_sq = val_abs = val_sq = 0.0
                max_abs_err = 0.0
                for start in range(0, sq.shape[0], chunk):
                    stop = min(start + chunk, sq.shape[0])
                    v = _values(sd[start:stop], sq[start:stop])
                    r = _values(dd[start:stop], KVALUES_IQ4NL[dq[start:stop]])
                    e = r - v
                    err_abs += float(np.abs(e).sum())
                    err_sq += float((e * e).sum())
                    val_abs += float(np.abs(v).sum())
                    val_sq += float((v * v).sum())
                    max_abs_err = max(max_abs_err, float(np.abs(e).max()))
                elems = max(1, int(sq.shape[0]) * BLOCK_ELEMS)
                entry.update(
                    {
                        "bit_exact": False,
                        "mean_abs_err": err_abs / elems,
                        "rmse": (err_sq / elems) ** 0.5,
                        "relative_abs_err": err_abs / max(1e-30, val_abs),
                        "snr_db": 10.0 * float(np.log10(max(1e-30, val_sq) / max(1e-30, err_sq))),
                        "max_abs_err": max_abs_err,
                    }
                )
            else:
                entry.update(
                    {
                        "bit_exact": True,
                        "scale_bytes_identical": bool((sd == dd).all()),
                        "values_identical": bool((sq == dq).all()),
                        "mismatched_values": int((sq != dq).sum()),
                    }
                )
            report.append(entry)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="container skeleton .ninfer (never modified)")
    ap.add_argument("--dst", default=None, help="destination .ninfer (must not exist)")
    ap.add_argument("--mtp-src", default=None,
                    help="file the MTP head DATA is read from (default: --src).  Point it at a "
                         "higher-precision artifact (e.g. the factory Q8MTP build) to keep the "
                         "smaller container skeleton of --src while taking the head from there")
    ap.add_argument("--mtp-src-format", default=SRC_FORMAT, choices=[SRC_FORMAT, DST_FORMAT],
                    help="format of the target objects inside --mtp-src (default %s)" % SRC_FORMAT)
    ap.add_argument("--target-format", default=DST_FORMAT, choices=[DST_FORMAT, IQ4_NL_FORMAT])
    ap.add_argument("--probe-error", action="store_true",
                    help="measure the conversion error over ALL blocks and exit without writing")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit without writing")
    ap.add_argument("--verify", action="store_true", help="after writing, run the FULL oracle")
    ap.add_argument("--negative-control", action="store_true",
                    help="L2: deliberately under-write one object; the writer MUST refuse")
    ap.add_argument("--no-name-marker", action="store_true", help="do not append the metadata.name marker")
    args = ap.parse_args(argv)

    if not args.probe_error and not args.dst:
        ap.error("--dst is required unless --probe-error is given")
    if args.dst and os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("REFUSE: source and destination are the same file")
        return 2

    art = Artifact(args.src)
    d = art.directory
    targets = target_objects(d)          # the SKELETON decides WHICH objects get recoded

    data_path = args.mtp_src or args.src
    data_art = art if os.path.abspath(data_path) == os.path.abspath(args.src) else Artifact(data_path)
    data_by_id = {o.id: o for o in data_art.directory.objects}

    print("skeleton      : %s" % os.path.basename(args.src))
    print("  file bytes  : %d" % os.path.getsize(args.src))
    print("  artifact_id : %s" % art.artifact_id.hex())
    print("  payload     : %d" % d.payload_bytes)
    print("  objects     : %d (tensors %d, resources %d)"
          % (len(d.objects),
             sum(1 for o in d.objects if not isinstance(o, ResourceObject)),
             sum(1 for o in d.objects if isinstance(o, ResourceObject))))
    print("  components  : %s" % ", ".join(sorted(d.components.keys())))
    print("  metadata.name: %s" % d.metadata.get("name"))
    print("data source   : %s  (declared format %s)" % (os.path.basename(data_path), args.mtp_src_format))
    print("target format : %s" % args.target_format)
    print("targets       : %d objects with skeleton format=%s" % (len(targets), SRC_FORMAT))
    if not targets:
        print("REFUSE: no %s objects found -- nothing to recode" % SRC_FORMAT)
        art.close()
        if data_art is not art:
            data_art.close()
        return 3

    for o in targets:                    # validate the data source BEFORE writing anything
        do = data_by_id.get(o.id)
        bad = None
        if do is None:
            bad = "missing from the data source"
        elif getattr(do, "format", None) != args.mtp_src_format:
            bad = "data source format is %s, expected %s" % (getattr(do, "format", None), args.mtp_src_format)
        elif list(do.shape) != list(o.shape):
            bad = "shape %s in the data source vs %s in the skeleton" % (list(do.shape), list(o.shape))
        if bad:
            print("REFUSE: %s: %s" % (o.id, bad))
            art.close()
            if data_art is not art:
                data_art.close()
            return 6

    total_src = 0
    total_dst = 0
    print("  %-16s %-18s %14s %14s" % ("id", "shape", "src bytes", "dst bytes"))
    for o in targets:
        exp = expected_bytes(o, args.target_format)
        total_src += o.bytes
        total_dst += exp
        print("  %-16s %-18s %14d %14d" % (o.id, str(list(o.shape)), o.bytes, exp))
    print("  total: src %d -> dst %d  (delta %+d B = %+.1f MiB)"
          % (total_src, total_dst, total_dst - total_src, (total_dst - total_src) / 1024 / 1024))

    def _encode(obj):
        """Encoded payload for a target object, read from the DATA source."""
        do = data_by_id[obj.id]
        raw = b"".join(data_art.iter_range(do.offset, do.bytes))   # iter_object rejects q4_0
        if args.target_format == IQ4_NL_FORMAT:
            if args.mtp_src_format != DST_FORMAT:
                raw = q4_0_to_q8_0(raw)                            # normalise the source first
            payload, st = quantize_q8_0_to_iq4_nl(raw)
            return payload, st
        return (raw if args.mtp_src_format == DST_FORMAT else q4_0_to_q8_0(raw)), None

    if args.probe_error:
        print("--- probe: conversion error over ALL blocks (nothing is written) ---")
        worst = None
        for o in targets:
            _, st = _encode(o)
            if st is None:
                print("  %-16s target format %s is BIT-EXACT by construction (no error to measure)"
                      % (o.id, args.target_format))
                continue
            print("  %-16s blocks=%-9d rel_abs_err=%.4f%%  rmse=%.3e  snr=%.2f dB  max_abs_err=%.3e"
                  % (o.id, st["blocks"], 100.0 * st["relative_abs_err"], st["rmse"], st["snr_db"], st["max_abs_err"]))
            worst = st if worst is None or st["relative_abs_err"] > worst["relative_abs_err"] else worst
        if worst is not None:
            print("  WORST object: rel_abs_err=%.4f%%  snr=%.2f dB  (accept bound %.2f%%)"
                  % (100.0 * worst["relative_abs_err"], worst["snr_db"], 100.0 * MAX_REL_ABS_ERR))
        art.close()
        if data_art is not art:
            data_art.close()
        print("[probe] nothing written")
        return 0

    if args.dry_run:
        art.close()
        if data_art is not art:
            data_art.close()
        print("[dry-run] nothing written")
        return 0

    target_ids = {o.id for o in targets}
    specs = []
    for obj in d.objects:
        if isinstance(obj, ResourceObject):
            specs.append(ResourceSpec(id=obj.id, bytes=obj.bytes, encoding=obj.encoding))
        else:
            fmt = args.target_format if obj.id in target_ids else obj.format
            specs.append(TensorSpec(id=obj.id, shape=obj.shape, format=fmt,
                                    layout=obj.layout, divisors=obj.divisors))

    metadata = dict(d.metadata)
    if not args.no_name_marker:
        metadata["name"] = str(metadata.get("name", "")) + (
            NAME_MARKER if args.target_format == DST_FORMAT else NAME_MARKER_IQ4NL)
    provenance = dict(d.provenance)
    provenance["mtp_recode"] = {
        "by": "recode_mtp.py",
        "when": datetime.now().isoformat(timespec="seconds"),
        "from_format": args.mtp_src_format,
        "to_format": args.target_format,
        "method": ("bit-exact: fp16 scale copied verbatim, nibble -> int8(nibble - 8); no re-quantisation"
                   if args.target_format == DST_FORMAT else
                   "lossy: least-squares fp16 scale + nearest kvalues_iq4nl entry, 3 sweeps per block; "
                   "iq4_nl nibbles are HALVED (qs[j] low -> element j, high -> element j+16)"),
        "objects": sorted(target_ids),
        "skeleton_file": os.path.basename(args.src),
        "skeleton_artifact_id": art.artifact_id.hex(),
        "data_source_file": os.path.basename(data_path),
        "data_source_artifact_id": data_art.artifact_id.hex(),
    }

    writer = ArtifactWriter(
        args.dst,
        specs,
        components=d.components,
        bindings=d.bindings,
        uses=d.uses,
        metadata=metadata,
        provenance=provenance,
    )

    written = 0
    try:
        if args.negative_control:
            # L2: write ONE target one byte short, then finish() early -- the writer MUST refuse.
            o = targets[0]
            payload = _encode(o)[0][:-1]
            writer.write_object(o.id, payload)
            written = len(payload)
            print("negative control: wrote %s ONE BYTE SHORT (%d of %d declared bytes), finishing early"
                  % (o.id, len(payload), expected_bytes(o, args.target_format)))
            directory = writer.finish()
        else:
            done = 0
            for obj in d.objects:
                if obj.id in target_ids:
                    payload, _ = _encode(obj)
                    writer.write_object(obj.id, payload)
                    written += len(payload)
                else:
                    writer.write_object(obj.id, art.iter_object(obj.id))
                    written += obj.bytes
                done += 1
                if done % 200 == 0:
                    print("  ... %d/%d objects written" % (done, len(d.objects)))
            directory = writer.finish()
    except BaseException as exc:                                        # incl. ArtifactError from finish()
        writer.abort()
        art.close()
        if data_art is not art:
            data_art.close()
        if args.negative_control:
            msg = str(exc)
            ok = "output coverage is incomplete" in msg
            print("negative control: writer raised: %s" % msg)
            print("negative control: %s" % ("PASS (refused as required)" if ok else "FAIL (unexpected error text)"))
            return 0 if ok else 4
        raise

    art.close()
    if data_art is not art:
        data_art.close()
    print("written       : %d bytes" % written)
    print("destination   : %s" % args.dst)
    print("  file bytes  : %d" % os.path.getsize(args.dst))
    print("  payload     : %d" % directory.payload_bytes)

    check = Artifact(args.dst)          # re-open: validates header, length, directory, layout
    print("re-open OK    : artifact_id=%s payload=%d objects=%d components=%s"
          % (check.artifact_id.hex(), check.payload_bytes, len(check.directory.objects),
             ",".join(sorted(check.directory.components.keys()))))
    check.close()

    if args.verify:
        print("--- L1 oracle over the written artifact (ALL blocks, not sampled) ---")
        rep = oracle(data_path, args.dst, sorted(target_ids),
                     src_fmt=args.mtp_src_format, dst_fmt=args.target_format)
        all_ok = True
        for r in rep:
            if r["bit_exact"]:
                ok = r["scale_bytes_identical"] and r["values_identical"]
                print("  %-16s blocks=%-9d BIT-EXACT scale_identical=%s values_identical=%s mismatches=%d  (%d -> %d B)"
                      % (r["id"], r["blocks"], r["scale_bytes_identical"], r["values_identical"],
                         r["mismatched_values"], r["src_bytes"], r["dst_bytes"]))
            else:
                ok = r["relative_abs_err"] < MAX_REL_ABS_ERR
                print("  %-16s blocks=%-9d LOSSY rel_abs_err=%.4f%% rmse=%.3e snr=%.2f dB max_abs_err=%.3e  (%d -> %d B) %s"
                      % (r["id"], r["blocks"], 100.0 * r["relative_abs_err"], r["rmse"], r["snr_db"],
                         r["max_abs_err"], r["src_bytes"], r["dst_bytes"], "PASS" if ok else "FAIL"))
            all_ok &= ok
        print("L1 VERDICT: %s" % ("PASS" if all_ok else "FAIL"))
        return 0 if all_ok else 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
