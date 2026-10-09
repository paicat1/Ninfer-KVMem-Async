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
Q4_0_BLOCK_BYTES = 18
Q8_0_BLOCK_BYTES = 34
BLOCK_ELEMS = 32

# metadata.name marker: the product is no longer the factory artifact (T-RECORD).
NAME_MARKER = "+mtp-q8"


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


def target_objects(directory):
    return [o for o in directory.objects if getattr(o, "format", None) == SRC_FORMAT]


def expected_bytes(obj):
    """q8_0 size for the same shape: elems/32*34."""
    elems = 1
    for dim in obj.shape:
        elems *= dim
    if elems % BLOCK_ELEMS:
        raise ValueError(f"{obj.id}: element count {elems} is not a multiple of {BLOCK_ELEMS}")
    return elems // BLOCK_ELEMS * Q8_0_BLOCK_BYTES


def oracle(src_path, dst_path, ids):
    """L1: full (not sampled) bit-level oracle over the written artifact."""
    report = []
    with Artifact(src_path) as src, Artifact(dst_path) as dst:
        src_by_id = {o.id: o for o in src.directory.objects}
        dst_by_id = {o.id: o for o in dst.directory.objects}
        for oid in ids:
            so, do = src_by_id[oid], dst_by_id[oid]
            s_raw = b"".join(src.iter_range(so.offset, so.bytes))
            d_raw = b"".join(dst.iter_range(do.offset, do.bytes))
            sd, sq = decode_q4_0(s_raw)
            dd, dq = decode_q8_0(d_raw)
            n_blocks = sq.shape[0]
            scale_ok = bool((sd == dd).all())
            value_ok = bool((sq == dq).all())
            mism = int((sq != dq).sum())
            report.append(
                {
                    "id": oid,
                    "blocks": n_blocks,
                    "scale_bytes_identical": scale_ok,
                    "values_identical": value_ok,
                    "mismatched_values": mism,
                    "src_bytes": so.bytes,
                    "dst_bytes": do.bytes,
                }
            )
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="source .ninfer (never modified)")
    ap.add_argument("--dst", required=True, help="destination .ninfer (must not exist)")
    ap.add_argument("--target-format", default=DST_FORMAT, choices=[DST_FORMAT])
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit without writing")
    ap.add_argument("--verify", action="store_true", help="after writing, run the FULL bit-level oracle")
    ap.add_argument("--negative-control", action="store_true",
                    help="L2: deliberately under-write one object; the writer MUST refuse")
    ap.add_argument("--no-name-marker", action="store_true", help="do not append the metadata.name marker")
    args = ap.parse_args(argv)

    if os.path.abspath(args.src) == os.path.abspath(args.dst):
        print("REFUSE: source and destination are the same file")
        return 2

    art = Artifact(args.src)
    d = art.directory
    targets = target_objects(d)

    print("source        : %s" % os.path.basename(args.src))
    print("  file bytes  : %d" % os.path.getsize(args.src))
    print("  artifact_id : %s" % art.artifact_id.hex())
    print("  payload     : %d" % d.payload_bytes)
    print("  objects     : %d (tensors %d, resources %d)"
          % (len(d.objects),
             sum(1 for o in d.objects if not isinstance(o, ResourceObject)),
             sum(1 for o in d.objects if isinstance(o, ResourceObject))))
    print("  components  : %s" % ", ".join(sorted(d.components.keys())))
    print("  metadata.name: %s" % d.metadata.get("name"))
    print("targets       : %d objects with format=%s" % (len(targets), SRC_FORMAT))
    if not targets:
        print("REFUSE: no %s objects found -- nothing to recode" % SRC_FORMAT)
        art.close()
        return 3

    total_src = 0
    total_dst = 0
    print("  %-16s %-18s %14s %14s" % ("id", "shape", "src bytes", "dst bytes"))
    for o in targets:
        exp = expected_bytes(o)
        total_src += o.bytes
        total_dst += exp
        print("  %-16s %-18s %14d %14d" % (o.id, str(list(o.shape)), o.bytes, exp))
    print("  total: src %d -> dst %d  (delta %+d B = %+.1f MiB)"
          % (total_src, total_dst, total_dst - total_src, (total_dst - total_src) / 1024 / 1024))

    if args.dry_run:
        art.close()
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
        metadata["name"] = str(metadata.get("name", "")) + NAME_MARKER
    provenance = dict(d.provenance)
    provenance["mtp_recode"] = {
        "by": "recode_mtp.py",
        "when": datetime.now().isoformat(timespec="seconds"),
        "from_format": SRC_FORMAT,
        "to_format": args.target_format,
        "method": "bit-exact: fp16 scale copied verbatim, nibble -> int8(nibble - 8); no re-quantisation",
        "objects": sorted(target_ids),
        "source_file": os.path.basename(args.src),
        "source_artifact_id": art.artifact_id.hex(),
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
            raw = b"".join(art.iter_range(o.offset, o.bytes))
            payload = q4_0_to_q8_0(raw)[:-1]
            writer.write_object(o.id, payload)
            written = len(payload)
            print("negative control: wrote %s ONE BYTE SHORT (%d of %d declared bytes), finishing early"
                  % (o.id, len(payload), expected_bytes(o)))
            directory = writer.finish()
        else:
            done = 0
            for obj in d.objects:
                if obj.id in target_ids:
                    raw = b"".join(art.iter_range(obj.offset, obj.bytes))   # iter_object would reject q4_0
                    writer.write_object(obj.id, q4_0_to_q8_0(raw))
                    written += expected_bytes(obj)
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
        if args.negative_control:
            msg = str(exc)
            ok = "output coverage is incomplete" in msg
            print("negative control: writer raised: %s" % msg)
            print("negative control: %s" % ("PASS (refused as required)" if ok else "FAIL (unexpected error text)"))
            return 0 if ok else 4
        raise

    art.close()
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
        print("--- L1 full bit-level oracle (all blocks, not sampled) ---")
        rep = oracle(args.src, args.dst, sorted(target_ids))
        all_ok = True
        for r in rep:
            ok = r["scale_bytes_identical"] and r["values_identical"]
            all_ok &= ok
            print("  %-16s blocks=%-9d scale_identical=%s values_identical=%s mismatches=%d  (%d -> %d B)"
                  % (r["id"], r["blocks"], r["scale_bytes_identical"], r["values_identical"],
                     r["mismatched_values"], r["src_bytes"], r["dst_bytes"]))
        print("L1 VERDICT: %s" % ("PASS (bit-exact)" if all_ok else "FAIL"))
        return 0 if all_ok else 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
