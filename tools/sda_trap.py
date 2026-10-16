# -*- coding: utf-8 -*-
"""Append a trap record to .codebuddy/sda/TRAPS.txt, UTF-8 safe.

WHY THIS EXISTS
---------------
Two traps make the obvious `sda trap "..." "..."` unusable on this machine:

1. PowerShell 5.1 transcodes command-line args to GBK, so Chinese arguments
   arrive mangled (TRAPS #28). Passing the record via a UTF-8 *file* sidesteps
   the command line entirely.
2. `sda export` regenerates TRAPS.md FROM TRAPS.txt, so anything hand-written
   into TRAPS.md is silently destroyed on the next export. Records must live in
   TRAPS.txt, and this script is the safe way to put them there.

USAGE
-----
    .venv\\Scripts\\python.exe tools\\sda_trap.py <message_file> [--export]

<message_file> is a UTF-8 text file with three lines (blank lines and lines
starting with # are ignored):

    line 1 -> description (short title)
    line 2 -> root cause
    line 3 -> rule / what to do instead

Example:

    # trap_msg.txt
    用进程名匹配 python 进程误判主程序在跑
    根因: 只按 ProcessName 匹配，未查 CommandLine
    规则: 判断进程在跑必须取 CommandLine 确认

With --export, TRAPS.md is regenerated right after appending.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRAPS_TXT = ROOT / ".codebuddy" / "sda" / "TRAPS.txt"
SDA_PY = Path.home() / ".codebuddy" / "tools" / "sda.py"
SEP = "\u2502"  # the box-drawing vertical bar used by TRAPS.txt


def die(msg, code=1):
    print("ERROR: " + msg)
    sys.exit(code)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_export = "--export" in sys.argv[1:]

    if len(args) != 1:
        die("usage: sda_trap.py <message_file> [--export]")

    msg_path = Path(args[0])
    if not msg_path.is_file():
        die("message file not found: %s" % msg_path)

    raw = msg_path.read_text(encoding="utf-8")
    parts = [ln.strip() for ln in raw.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]

    if len(parts) < 3:
        die("message file needs 3 non-empty lines "
            "(description / root cause / rule), got %d" % len(parts))

    desc, root_cause, rule = parts[0], parts[1], parts[2]

    if not TRAPS_TXT.is_file():
        die("TRAPS.txt not found: %s" % TRAPS_TXT)

    lines = [ln for ln in TRAPS_TXT.read_text(encoding="utf-8").splitlines()
             if ln.strip()]
    if not lines:
        die("TRAPS.txt is empty, cannot determine next id")

    try:
        new_id = int(lines[-1].split(SEP)[0]) + 1
    except (ValueError, IndexError):
        die("cannot parse last TRAPS id from: %r" % lines[-1][:40])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    record = SEP.join([str(new_id), now, desc, root_cause, rule])

    with open(TRAPS_TXT, "a", encoding="utf-8") as f:
        f.write("\n" + record + "\n")

    print("appended trap #%d at %s" % (new_id, now))
    print("  desc: %s" % desc)

    if do_export:
        if not SDA_PY.is_file():
            print("WARN: sda.py not found, skipping export (%s)" % SDA_PY)
            return 0
        out = subprocess.run(
            [sys.executable, str(SDA_PY), "export"],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        print((out.stdout or "").strip())
        if out.returncode != 0:
            print((out.stderr or "").strip())
        return out.returncode

    print("NOTE: run `sda export` (or re-run with --export) to sync TRAPS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
