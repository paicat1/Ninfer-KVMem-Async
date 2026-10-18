#!/usr/bin/env python3
# backup_file.py - T-BACKUP machine gate (D2 handover, 2026-09-10 user approved,
# CodeBuddy dual-side reviewed). Byte-level pre-modification backups with SHA256
# idempotency and a JSONL manifest.
#
# Usage:
#   python tools/backup_file.py <file...> [--label LABEL] [--check] [--list [FILE...]] [--selftest]
#
# Behavior:
#   - backup: byte-level copy into safety_backups/<stem>_<YYYYMMDD_HHMMSS>[_<label>]<ext>
#   - idempotent: if source sha256 == latest manifest hash for that source -> SKIP
#     (iron rule "verified-repeat modifications may overwrite old backup" == no
#     redundant copies; rollback chain preserved, nothing is ever deleted)
#   - manifest: safety_backups/backup_manifest.jsonl, one JSON per line
#     {ts, source, backup_path, sha256, label}; source/backup_path are relative
#     to repo root. Legacy pre-D2 backups (~622 files) are NOT in the manifest
#     and NOT checked.
#   - no auto-pruning: user cleans up periodically (a --prune may come later)
#   - --check            : full manifest integrity (every backup file exists,
#                          hash matches). Legacy entries not covered.
#   - --check <file...>  : per-file current-vs-latest-backup: IN-SYNC (exit 0) /
#                          CHANGED (exit 1) / NO-BACKUP (exit 1, never silent)
#   - --list [file...]   : backup history from manifest
#   - --selftest         : built-in fixture, asserts backup/change/idempotency/
#                          check/tamper-detection end to end
#
# Exit codes: 0 ok; 1 any FAIL (including NO-BACKUP / CHANGED on --check file).
# NOTE (D2 vs D1): this tool guarantees "runs always succeed"; it does NOT
# enforce "runs happen before every risky edit" - that stays an iron-rule
# pointer obligation (no hard gate wiring, unlike smart_push 2.6 for D1).

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BACKUP_DIR = REPO / "safety_backups"
MANIFEST = BACKUP_DIR / "backup_manifest.jsonl"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_to(p, root):
    return Path(p).resolve().relative_to(Path(root).resolve()).as_posix()


def load_manifest(manifest=MANIFEST):
    if not manifest.exists():
        return []
    out = []
    with open(manifest, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def last_hash_for(records, rel_source):
    for r in reversed(records):
        if r.get("source") == rel_source:
            return r.get("sha256")
    return None


def sanitize_label(label):
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in label)


def backup_one(src, label, root=REPO, backup_dir=BACKUP_DIR, manifest=MANIFEST):
    srcp = Path(src)
    if not srcp.is_file():
        return "FAIL", "source not found: {}".format(srcp)
    rel = rel_to(srcp, root)
    digest = sha256_of(srcp)
    records = load_manifest(manifest)
    if last_hash_for(records, rel) == digest:
        return "SKIP", "{} identical to latest backup (sha256 {})".format(rel, digest[:8])
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = srcp.stem + "_" + ts
    lab = sanitize_label(label) if label else ""
    if lab:
        base += "_" + lab
    name = base + srcp.suffix
    i = 1
    while (backup_dir / name).exists():
        name = "{}_{}{}".format(base, i, srcp.suffix)
        i += 1
    dst = backup_dir / name
    shutil.copyfile(srcp, dst)  # byte-level copy: encoding-agnostic
    if sha256_of(dst) != digest:
        return "FAIL", "copy verification failed: {}".format(dst)
    rec = {
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source": rel,
        "backup_path": rel_to(dst, root),
        "sha256": digest,
        "label": lab,
    }
    with open(manifest, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=True) + "\n")
    return "OK", "{} -> {} (sha256 {})".format(rel, rec["backup_path"], digest[:8])


def check_file(src, records, root=REPO):
    srcp = Path(src)
    if not srcp.is_file():
        return "FAIL", "source not found: {}".format(srcp)
    rel = rel_to(srcp, root)
    last = last_hash_for(records, rel)
    if last is None:
        return "NO-BACKUP", "{} has no manifest record (run backup first)".format(rel)
    cur = sha256_of(srcp)
    if cur == last:
        return "IN-SYNC", rel
    return "CHANGED", "{} (current {} != latest backup {})".format(rel, cur[:8], last[:8])


def check_manifest_integrity(records, root=REPO):
    bad = []
    for r in records:
        bp = Path(root) / r["backup_path"]
        if not bp.is_file():
            bad.append(("missing", r["backup_path"]))
        elif sha256_of(bp) != r["sha256"]:
            bad.append(("hash-mismatch", r["backup_path"]))
    return bad


def cmd_check(args):
    records = load_manifest()
    if args.files:
        rc = 0
        for f in args.files:
            st, msg = check_file(f, records)
            print("{}: {}".format(st, msg))
            if st != "IN-SYNC":
                rc = 1
        return rc
    if not records:
        print("[BACKUP] CHECK PASS: manifest empty (nothing to verify)")
        return 0
    bad = check_manifest_integrity(records)
    for kind, p in bad:
        print("CHECK FAIL[{}]: {}".format(kind, p))
    if bad:
        print("[BACKUP] CHECK FAIL ({}/{} record(s) bad)".format(len(bad), len(records)))
        return 1
    print("[BACKUP] CHECK PASS ({} record(s); legacy pre-D2 backups not in manifest)".format(len(records)))
    return 0


def cmd_list(args):
    records = load_manifest()
    if args.files:
        rels = {rel_to(f, REPO) for f in args.files}
        records = [r for r in records if r.get("source") in rels]
    if not records:
        print("LIST: no manifest records" + (" for given file(s)" if args.files else ""))
        return 0
    for r in records:
        print("{}  {}  label={}  {} -> {}".format(
            r["ts"], r["sha256"][:8], r["label"] or "-", r["source"], r["backup_path"]))
    return 0


def selftest():
    base_tmp = REPO / ".temp"
    base_tmp.mkdir(exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="bkselftest_", dir=str(base_tmp)))
    bdir = tmp / "_safety_backups"
    mani = bdir / "backup_manifest.jsonl"
    results = []
    try:
        src = tmp / "demo.py"
        src.write_bytes(b"version one\n")
        st, _ = backup_one(src, "v1", root=tmp, backup_dir=bdir, manifest=mani)
        results.append(("backup-1 new file OK", st == "OK"))
        src.write_bytes(b"version two\n")
        st, _ = backup_one(src, "v2", root=tmp, backup_dir=bdir, manifest=mani)
        results.append(("backup-2 after change OK", st == "OK"))
        st, _ = backup_one(src, "v2b", root=tmp, backup_dir=bdir, manifest=mani)
        results.append(("idempotent SKIP on identical", st == "SKIP"))
        recs = load_manifest(mani)
        results.append(("manifest has exactly 2 records", len(recs) == 2))
        st_sync, _ = check_file(src, recs, root=tmp)
        src.write_bytes(b"version three\n")
        st_chg, _ = check_file(src, recs, root=tmp)
        other = tmp / "never.py"
        other.write_bytes(b"x\n")
        st_no, _ = check_file(other, recs, root=tmp)
        results.append(("check trio IN-SYNC/CHANGED/NO-BACKUP",
                        (st_sync, st_chg, st_no) == ("IN-SYNC", "CHANGED", "NO-BACKUP")))
        bp0 = tmp / recs[0]["backup_path"]
        bp0.write_bytes(b"tampered\n")
        bad = check_manifest_integrity(recs, root=tmp)
        results.append(("tamper detection works", len(bad) == 1 and bad[0][0] == "hash-mismatch"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(r for _, r in results)
    for name, r in results:
        print("  {}: {}".format("OK" if r else "UNEXPECTED", name))
    return ok


def main():
    ap = argparse.ArgumentParser(description="T-BACKUP machine gate (D2)")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--label", default="")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--list", dest="list_", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        ok = selftest()
        print("[BACKUP] SELFTEST " + ("PASS" if ok else "FAIL"))
        sys.exit(0 if ok else 1)
    if a.check:
        sys.exit(cmd_check(a))
    if a.list_:
        sys.exit(cmd_list(a))
    if not a.files:
        print("usage: backup_file.py <file...> [--label L] [--check] [--list [FILE...]] [--selftest]")
        sys.exit(1)
    rc = 0
    for f in a.files:
        st, msg = backup_one(f, a.label)
        print("{}: {}".format(st, msg))
        if st == "FAIL":
            rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
