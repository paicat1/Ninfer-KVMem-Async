#!/usr/bin/env python3
"""wm_revert_check.py (toolchain-III, gitignored, never commit)

Detect tracked .md files whose ONLY difference vs the git index is AIGC
watermark ID values. The AIGC compliance hook re-injects fresh GUIDs into
.md files whenever they are rebuilt (merge / checkout), which dirties the
worktree and makes smart_push's uncommitted check block the push.

Output: one filepath per line -- only files that are SAFE to `git checkout --`
(pure watermark diff). Files with ANY real content change are never listed.
Exit code is always 0 (report-only; the caller decides whether to revert).

Judge rule: strip every watermark metadata line from both the worktree text
and the index blob; the results are equal => pure watermark diff.

Scope: unstaged worktree modifications only (" M" in porcelain XY). Staged
or renamed/deleted/untracked entries are never listed.
"""
import re
import subprocess
import sys

# watermark metadata lines: keys are fixed, values differ per injection
_WM = re.compile(
    r"^[ \t]*(ContentProducer|ContentPropagator|Label|ProduceID|PropagateID|"
    r"ReservedCode1|ReservedCode2):[^\n]*\n?", re.M)


def _strip_wm(text: str) -> str:
    """Strip the whole leading AIGC frontmatter block, then any residual ID lines.

    Two diff shapes must both normalize to the same body:
    - old IDs vs new IDs (both sides have the block) -> strip both blocks
    - clean vs injected (one side has no block) -> stripping only the existing
      block is required; ID-line-only stripping would leave a --- fence shell
      behind and fail the comparison (2026-09-09 field bug).
    """
    m = re.match(r"^---\s*\nAIGC:\s*\n(?:[ \t]+[^\n]*\n)+---\s*\n(?:\s*\n)?", text)
    if m:
        text = text[m.end():]
    return _WM.sub("", text)


def _norm_eol(text: str) -> str:
    """Normalize CRLF/CR to LF before comparing.

    Repo blobs may be CRLF (autocrlf history) while Python's universal-newlines
    read strips \r from the worktree copy (or vice versa) -- without this the
    comparison always fails on such files even when the diff is watermark-only
    (git diff normalizes eol itself, which is why it showed only 4 lines).
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def main() -> int:
    status = subprocess.run(
        ["git", "-c", "core.quotepath=off", "status", "--porcelain", "-z"],
        capture_output=True)
    if status.returncode != 0:
        return 0
    entries = status.stdout.decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        # rename/copy entries carry an extra NUL-separated orig-path field
        if "R" in xy:
            i += 1
            continue
        # only unstaged worktree modification of a tracked .md
        if xy != " M" or not path.lower().endswith(".md"):
            continue
        blob = subprocess.run(["git", "cat-file", "-p", ":" + path],
                              capture_output=True)
        if blob.returncode != 0:
            continue
        idx_text = blob.stdout.decode("utf-8", "replace")
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                wt_text = fh.read()
        except OSError:
            continue
        if _norm_eol(_strip_wm(wt_text)) == _norm_eol(_strip_wm(idx_text)):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
