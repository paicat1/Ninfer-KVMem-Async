# -*- coding: utf-8 -*-
"""20261030: gates.ps1 段级 [T] 插桩，定位 31.8s 落在哪一段。
每段边界锚点前插 Write-Output [T] 行；$gSw 秒表在 HOOK-GIT-ENV END 后初始化。
newline='' 保行尾。锚点按唯一字符串匹配，全部命中才落盘。
"""
import sys

PATH = r"j:\ninfer-kvmem\scripts\gates.ps1"

with open(PATH, "r", encoding="utf-8-sig", newline="") as f:
    t = f.read()

if "[T] G" in t:
    print("ALREADY-PATCHED")
    sys.exit(0)

def tick(name):
    return 'Write-Output ("[T] G-' + name + ' t=" + [int]$gSw.Elapsed.TotalMilliseconds)\r\n'

ANCHORS = [
    # (锚点原文, 在其前插入的 tick 名)  顺序即段边界
    ("$st = Join-Path $root 'scripts\\check_structure.py'", "refs"),
    ("# —— 本地自律层（窗口纪律 / BOM / 绕过判据）—— **仅本机执行**", "structure"),
    ("# ===================== UNDERSCORE-GATE", "window"),
    ("# ===================== QUOTA-GATE", "underscore"),
    ("# ===================== SUBREPO-CLEAN-GATE", "quota"),
    ("# ===================== EOL-GATE", "subrepo"),
    ("# ===================== ASSET-DUAL-GATE", "eol"),
    ("# ===================== REPRO-CLAIM-GATE", "asset-dual"),
    ("# ===================== ASSET-CLASS-GATE", "repro-claim"),
    ("# ===================== BUILD-LEDGER-GATE", "asset-class"),
]
INIT_ANCHOR = "# ===================== HOOK-GIT-ENV END ====================="
INIT_LINE = '$gSw = [Diagnostics.Stopwatch]::StartNew()\r\n'

for a, _ in ANCHORS + [(INIT_ANCHOR, "")]:
    if a not in t:
        print("ANCHOR-MISSING: " + a[:60])
        sys.exit(1)

t = t.replace(INIT_ANCHOR, INIT_ANCHOR + "\r\n" + INIT_LINE, 1)
for a, name in ANCHORS:
    t = t.replace(a, tick(name) + a, 1)

with open(PATH, "w", encoding="utf-8-sig", newline="") as f:
    f.write(t)

print("PATCHED-OK: 11 ticks (init + 10 segment boundaries)")
