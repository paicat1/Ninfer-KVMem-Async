# -*- coding: utf-8 -*-
"""20261030: 拆除 gates.ps1 段级 [T] 插桩（保留 build-ledger 汇总行）。
按行过滤，newline='' 保行尾。"""
import sys

PATH = r"j:\ninfer-kvmem\scripts\gates.ps1"

with open(PATH, "r", encoding="utf-8-sig", newline="") as f:
    lines = f.readlines()

out = []
removed = 0
for ln in lines:
    s = ln.strip()
    if "[T] G-" in s or s == '$gSw = [Diagnostics.Stopwatch]::StartNew()':
        removed += 1
        continue
    out.append(ln)

if removed == 0:
    print("NOTHING-TO-STRIP")
    sys.exit(0)

with open(PATH, "w", encoding="utf-8-sig", newline="") as f:
    f.writelines(out)

print("STRIPPED %d lines" % removed)
