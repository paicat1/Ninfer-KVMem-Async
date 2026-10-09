"""graft_vision.py -- append one component (the vision tower) of a NInfer v3 artifact onto another.

WHY
    The factory Q8MTP build carries a vision tower, but its MTP head is the 451 MB
    q8_0 one, which does not fit next to a large KV pool on this 16 GB machine.
    Our iq4_nl build has a 239 MB MTP head (it fits) but no vision tower.  The engine
    resolves a companion component only from the SAME artifact
    (`config.cpp:48-54` companion() / `:323`), so the tower cannot be loaded from a
    second file -- it has to live inside the container.

    This script therefore APPENDS the donor's vision component to our skeleton:
    skeleton + vision => one artifact with both the small MTP head and vision.

WHY THIS IS "PURE APPEND" (measured, not assumed)
    bindings : donor 1420 vs skeleton  979 -> +441,  skeleton-only  0
    uses     : donor  784 vs skeleton  619 -> +165,  skeleton-only  0
    objects  : donor 1139 vs skeleton  804 -> +335,  skeleton-only  0
    Every extra key starts with `vision/`, and every extra object id is either
    `weight/vNNNNNN` (its own namespace, disjoint from `weight/NNNNNN`) or one of the
    two vision resources.  The skeleton's ids/bindings/uses are a strict SUBSET of
    the donor's, so nothing has to be rebuilt or renamed -- the graft is additive.
    (Re-measure with --dry-run before trusting these numbers on other artifacts.)

HOW
    * read both artifacts with the upstream reader (validates header/length/directory),
    * select the graft: component by name, bindings/uses by key prefix,
      objects as the id difference (donor - skeleton),
    * copy every payload VERBATIM via iter_range() -- no decode, no re-quantisation,
      so BOTH halves are byte-identical to their sources,
    * hand the specs to the upstream ArtifactWriter: it recomputes the aligned object
      layout and refuses to publish unless every declared byte was written.

SAFETY
    Writes a NEW file only; ArtifactWriter raises FileExistsError on an existing
    destination.  Neither source is ever opened for writing.  --verify re-reads the
    product and compares EVERY object against its source with a streaming SHA-256
    (no sampling).  --negative-control proves the writer still refuses a short write.

USAGE
    python scripts/graft_vision.py --skeleton A.ninfer --donor B.ninfer --dst C.ninfer [--dry-run]
    python scripts/graft_vision.py --skeleton A.ninfer --donor B.ninfer --dst C.ninfer --verify
    python scripts/graft_vision.py --skeleton A.ninfer --donor B.ninfer --dst C.ninfer --negative-control
"""

import argparse
import hashlib
import os
import sys
from datetime import datetime

# The upstream engine source tree ships the official Python artifact SDK.
UPSTREAM = r"J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
if UPSTREAM not in sys.path:
    sys.path.insert(0, UPSTREAM)

from tools.artifact.reader import Artifact  # noqa: E402
from tools.artifact.writer import ArtifactWriter  # noqa: E402
from tools.artifact.schema import (  # noqa: E402
    ResourceObject,
    ResourceSpec,
    TensorObject,
    TensorSpec,
    binding_parts,
)

DEFAULT_COMPONENT = "vision"
DEFAULT_PREFIX = "vision/"

# metadata.name marker: the product is no longer the factory artifact (T-RECORD).
NAME_MARKER = "+vision"


def spec_of(obj):
    """Rebuild the ObjectSpec a writer needs from an already-planned object.

    Offsets are NOT carried over: `plan_objects` recomputes them (with the layout
    alignment) from the order the specs are handed in.
    """
    if isinstance(obj, TensorObject):
        return TensorSpec(obj.id, obj.shape, obj.format, obj.layout, obj.divisors)
    if isinstance(obj, ResourceObject):
        return ResourceSpec(obj.id, obj.bytes, obj.encoding)
    raise TypeError("unsupported object %r" % type(obj).__name__)


def select_graft(skel_dir, donor_dir, component, prefix):
    """Return (vision_objects, vision_bindings, vision_uses) selected from the donor.

    Everything is cross-checked against the skeleton so a silent half-graft cannot
    happen: the objects must be disjoint from the skeleton, and every binding the
    graft brings must resolve against (skeleton + graft) objects.
    """
    skel_by_id = {o.id: o for o in skel_dir.objects}
    donor_by_id = {o.id: o for o in donor_dir.objects}

    extra_ids = sorted(set(donor_by_id) - set(skel_by_id))
    graft_objs = [donor_by_id[i] for i in extra_ids]

    # Every graft object must look like it belongs to the grafted component.
    stray = [o.id for o in graft_objs if o.id.startswith("weight/") and not o.id.startswith("weight/v")]
    if stray:
        raise SystemExit(
            "REFUSE: %d donor-only objects are not in the graft namespace (e.g. %s); "
            "an id-space change would mean the two artifacts are not comparable"
            % (len(stray), stray[:3])
        )

    vision_bindings = {k: v for k, v in donor_dir.bindings.items() if k.startswith(prefix)}
    vision_uses = [u for u in donor_dir.uses if u["parameter"].startswith(prefix)]

    if not vision_bindings:
        raise SystemExit("REFUSE: no donor binding starts with %r -- nothing to graft" % prefix)

    # A binding may only reference objects that will exist in the product.
    available = dict(skel_by_id)
    available.update({o.id: o for o in graft_objs})
    for name, binding in vision_bindings.items():
        try:
            binding_parts(binding, available, name)
        except Exception as exc:
            raise SystemExit("REFUSE: graft binding %s does not resolve: %s" % (name, exc))
    for use in vision_uses:
        if use["parameter"] not in dict(skel_dir.bindings, **vision_bindings):
            raise SystemExit("REFUSE: graft use %s has no binding" % use["parameter"])
        for role, binding in use.get("auxiliaries", {}).items():
            try:
                binding_parts(binding, available, "%s/%s" % (use["parameter"], role))
            except Exception as exc:
                raise SystemExit("REFUSE: graft auxiliary %s/%s does not resolve: %s"
                                 % (use["parameter"], role, exc))

    return graft_objs, vision_bindings, vision_uses


def stream_sha(art, obj):
    h = hashlib.sha256()
    for chunk in art.iter_range(obj.offset, obj.bytes):
        h.update(chunk)
    return h.hexdigest()


def verify(skel_path, donor_path, dst_path, skel_ids, graft_ids):
    """L1: every object of the product compared with its source, byte for byte."""
    report = {"skeleton": [], "graft": [], "skeleton_bad": 0, "graft_bad": 0}
    with Artifact(skel_path) as skel, Artifact(donor_path) as donor, Artifact(dst_path) as dst:
        dst_by_id = {o.id: o for o in dst.directory.objects}
        skel_by_id = {o.id: o for o in skel.directory.objects}
        donor_by_id = {o.id: o for o in donor.directory.objects}
        for group, src_path, src_by_id, ids, key in (
            ("skeleton", skel_path, skel_by_id, skel_ids, "skeleton"),
            ("graft", donor_path, donor_by_id, graft_ids, "graft"),
        ):
            src = skel if group == "skeleton" else donor
            for oid in ids:
                so = src_by_id[oid]
                do = dst_by_id[oid]
                same_len = so.bytes == do.bytes
                ok = same_len and stream_sha(src, so) == stream_sha(dst, do)
                if not ok:
                    report[key + "_bad"] += 1
                report[key].append({"id": oid, "bytes": so.bytes, "identical": ok})
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skeleton", required=True, help="artifact that gets the new component (never modified)")
    ap.add_argument("--donor", required=True, help="artifact the component is taken from (never modified)")
    ap.add_argument("--dst", default=None, help="destination .ninfer (must not exist)")
    ap.add_argument("--component", default=DEFAULT_COMPONENT, help="component name to graft (default %(default)s)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX,
                    help="binding/use key prefix that marks the graft (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit without writing")
    ap.add_argument("--verify", action="store_true", help="after writing, compare EVERY object with its source")
    ap.add_argument("--negative-control", action="store_true",
                    help="L2: deliberately under-write one graft object; the writer MUST refuse")
    ap.add_argument("--no-name-marker", action="store_true", help="do not append the metadata.name marker")
    args = ap.parse_args(argv)

    if not args.dst:
        ap.error("--dst is required")
    for label, p in (("skeleton", args.skeleton), ("donor", args.donor)):
        if os.path.abspath(p) == os.path.abspath(args.dst):
            print("REFUSE: %s and destination are the same file" % label)
            return 2

    skel = Artifact(args.skeleton)
    donor = Artifact(args.donor)
    skel_dir, donor_dir = skel.directory, donor.directory

    if args.component not in donor_dir.components:
        print("REFUSE: donor has no %r component (has %s)"
              % (args.component, sorted(donor_dir.components)))
        return 3
    if args.component in skel_dir.components:
        print("REFUSE: skeleton already has a %r component -- grafting would collide" % args.component)
        return 4
    component = donor_dir.components[args.component]
    if component.get("target") != "text":
        print("REFUSE: component %r has target %r; the engine requires target 'text' "
              "(config.cpp:50-52)" % (args.component, component.get("target")))
        return 5

    graft_objs, vision_bindings, vision_uses = select_graft(
        skel_dir, donor_dir, args.component, args.prefix)

    print("skeleton      : %s" % os.path.basename(args.skeleton))
    print("  objects %d | bindings %d | uses %d | components %s"
          % (len(skel_dir.objects), len(skel_dir.bindings), len(skel_dir.uses),
             "+".join(sorted(skel_dir.components))))
    print("donor         : %s" % os.path.basename(args.donor))
    print("  objects %d | bindings %d | uses %d | components %s"
          % (len(donor_dir.objects), len(donor_dir.bindings), len(donor_dir.uses),
             "+".join(sorted(donor_dir.components))))
    print("graft         : component %r | objects %d | bindings %d | uses %d"
          % (args.component, len(graft_objs), len(vision_bindings), len(vision_uses)))
    print("  resources   : %s" % sorted(component.get("resources", {}).values()))
    graft_bytes = sum(o.bytes for o in graft_objs)
    skel_bytes = sum(o.bytes for o in skel_dir.objects)
    print("  payload     : skeleton %d + graft %d = %d B (%.1f + %.1f = %.1f MiB)"
          % (skel_bytes, graft_bytes, skel_bytes + graft_bytes,
             skel_bytes / 1048576, graft_bytes / 1048576, (skel_bytes + graft_bytes) / 1048576))

    if args.dry_run:
        skel.close()
        donor.close()
        print("[dry-run] nothing written")
        return 0

    specs = [spec_of(o) for o in skel_dir.objects] + [spec_of(o) for o in graft_objs]
    components = dict(skel_dir.components)
    components[args.component] = component
    bindings = dict(skel_dir.bindings)
    bindings.update(vision_bindings)
    if len(bindings) != len(skel_dir.bindings) + len(vision_bindings):
        print("REFUSE: graft bindings collide with skeleton bindings")
        return 6
    uses = list(skel_dir.uses) + list(vision_uses)

    metadata = dict(skel_dir.metadata)
    if not args.no_name_marker:
        metadata["name"] = str(metadata.get("name", "")) + NAME_MARKER
    provenance = dict(skel_dir.provenance)
    provenance["vision_graft"] = {
        "by": "graft_vision.py",
        "when": datetime.now().isoformat(timespec="seconds"),
        "component": args.component,
        "key_prefix": args.prefix,
        "method": ("pure append: component config/target/resources, %d objects, %d bindings, "
                   "%d uses; every payload copied VERBATIM with iter_range (no decode, no "
                   "re-quantisation) so both halves are byte-identical to their sources"
                   % (len(graft_objs), len(vision_bindings), len(vision_uses))),
        "objects": sorted(o.id for o in graft_objs),
        "skeleton_file": os.path.basename(args.skeleton),
        "donor_file": os.path.basename(args.donor),
        "skeleton_artifact_id": skel.artifact_id.hex(),
        "donor_artifact_id": donor.artifact_id.hex(),
    }

    written = 0
    writer = ArtifactWriter(
        args.dst, specs, components=components, bindings=bindings, uses=uses,
        metadata=metadata, provenance=provenance,
    )
    try:
        if args.negative_control:
            # L2: write the FIRST graft object one byte short, then finish() early --
            # the writer MUST refuse instead of publishing a truncated artifact.
            o = graft_objs[0]
            raw = b"".join(donor.iter_range(o.offset, o.bytes))
            writer.write_object(o.id, raw[:-1])
            written = len(raw) - 1
            print("negative control: wrote %s ONE BYTE SHORT (%d of %d declared bytes), finishing early"
                  % (o.id, len(raw) - 1, o.bytes))
            writer.finish()
        else:
            for obj in skel_dir.objects:
                writer.write_object(obj.id, skel.iter_range(obj.offset, obj.bytes))
                written += obj.bytes
            for obj in graft_objs:
                writer.write_object(obj.id, donor.iter_range(obj.offset, obj.bytes))
                written += obj.bytes
            writer.finish()
    except BaseException as exc:                                   # incl. ArtifactError from finish()
        writer.abort()
        skel.close()
        donor.close()
        if args.negative_control:
            msg = str(exc)
            ok = "output coverage is incomplete" in msg
            print("negative control: writer raised: %s" % msg)
            print("negative control: %s" % ("PASS (refused as required)" if ok else "FAIL (unexpected error text)"))
            return 0 if ok else 7
        raise

    skel.close()
    donor.close()
    print("written       : %d bytes" % written)

    if args.verify:
        print("--- L1: every object compared with its source (streaming SHA-256, no sampling) ---")
        rep = verify(args.skeleton, args.donor, args.dst,
                     [o.id for o in skel_dir.objects], [o.id for o in graft_objs])
        for key in ("skeleton", "graft"):
            bad = rep[key + "_bad"]
            print("  %-9s: %d objects, %d mismatched" % (key, len(rep[key]), bad))
            for r in rep[key][:5]:
                print("      %-46s %12d B  %s" % (r["id"], r["bytes"], "identical" if r["identical"] else "MISMATCH"))
            if len(rep[key]) > 5:
                print("      ... (%d more)" % (len(rep[key]) - 5))
        with Artifact(args.dst) as dst:
            print("  product: objects %d | bindings %d | uses %d | components %s | name %s"
                  % (len(dst.directory.objects), len(dst.directory.bindings), len(dst.directory.uses),
                     "+".join(sorted(dst.directory.components)), dst.directory.metadata.get("name")))
        ok = rep["skeleton_bad"] == 0 and rep["graft_bad"] == 0
        print("L1 VERDICT: %s" % ("PASS (both halves byte-identical)" if ok else "FAIL"))
        return 0 if ok else 8
    return 0


if __name__ == "__main__":
    sys.exit(main())
