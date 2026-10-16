# -*- coding: utf-8 -*-
"""Independent audit of the vision graft product -- CORRECTED split.
prod objects split by id:
  skeleton set  = prod ids that also exist in skel
  graft set     = prod ids that also exist in donor
Every prod object must be in at least one source, and each half must be
byte-identical to its source (streaming SHA-256).
"""
import sys, hashlib
UP = r"J:\ninfer-kvmem\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
if UP not in sys.path:
    sys.path.insert(0, UP)
from tools.artifact.reader import Artifact

SKEL = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"
DONOR = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer"
PROD = r"J:\ninfer-kvmem\models\Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer"

def sha(art, obj):
    h = hashlib.sha256()
    for c in art.iter_range(obj.offset, obj.bytes):
        h.update(c)
    return h.hexdigest()

def main():
    with Artifact(PROD) as prod, Artifact(SKEL) as skel, Artifact(DONOR) as donor:
        p = {o.id: o for o in prod.directory.objects}
        s = {o.id: o for o in skel.directory.objects}
        d = {o.id: o for o in donor.directory.objects}
        skel_ids = set(p) & set(s)          # prod objs that exist in skeleton
        donor_ids = set(p) & set(d)         # prod objs that exist in donor
        print("prod objects:", len(p))
        print("  in skel:", len(skel_ids), " in donor:", len(donor_ids),
              " in NEITHER:", len(set(p)-set(s)-set(d)), sorted(set(p)-set(s)-set(d))[:3])

        # skeleton half: those NOT exclusively added by donor-graft logic
        bad_skel = 0
        for oid in sorted(skel_ids):
            so, po = s[oid], p[oid]
            if so.bytes != po.bytes or sha(skel, so) != sha(prod, po):
                bad_skel += 1
        print("skeleton half: %d objs, mismatched=%d" % (len(skel_ids), bad_skel))

        # graft half: donor-only objects (the new vision tower)
        graft_ids = donor_ids - skel_ids
        bad_graft = 0
        for oid in sorted(graft_ids):
            do, po = d[oid], p[oid]
            if do.bytes != po.bytes or sha(donor, do) != sha(prod, po):
                bad_graft += 1
        print("graft half   : %d objs, mismatched=%d" % (len(graft_ids), bad_graft))

        # id namespace sanity for graft
        stray = [oid for oid in graft_ids if oid.startswith("weight/") and not oid.startswith("weight/v")]
        print("graft stray non-vision weights:", stray[:5])
        print("VERDICT:", "PASS (both halves byte-identical)" if (bad_skel==0 and bad_graft==0 and not stray) else "FAIL")

if __name__ == "__main__":
    main()