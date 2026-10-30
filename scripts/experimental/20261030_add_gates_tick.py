# -*- coding: utf-8 -*-
"""20261030: 给 smart_push.ps1 插两个 [P] 计时锚点，二分定位推送 31.4s 真凶。
锚点1: '# 2.8 统一门禁' 前 -> scope2.8-qian（regression段结束到范围报告开始）
锚点2: '$gatePs = Join-Path' 前 -> scope-hou（范围报告结束，gates 开始前）
gates 耗时 = push-qian - scope-hou；范围报告耗时 = scope-hou - scope2.8-qian。
newline='' 保行尾（文件 CRLF=2064/bare_LF=7 混杂，禁全文改写）。
"""
import sys

PATH = r"j:\ninfer-kvmem\smart_push.ps1"

with open(PATH, "r", encoding="utf-8-sig", newline="") as f:
    t = f.read()

A1 = "# 2.8 统一门禁（引用完整性 + 结构合规）—— 逻辑在入库脚本 scripts\\gates.ps1"
A2 = "$gatePs = Join-Path $repo \"scripts\\gates.ps1\""
T1 = 'Write-Output ("[P] scope2.8-qian t=" + [int]$__pT.Elapsed.TotalMilliseconds)\r\n'
T2 = 'Write-Output ("[P] scope-hou t=" + [int]$__pT.Elapsed.TotalMilliseconds)\r\n'

if "scope2.8-qian" in t:
    print("ALREADY-PATCHED")
    sys.exit(0)
if A1 not in t or A2 not in t:
    print("ANCHOR-MISSING: A1=%s A2=%s" % (A1 in t, A2 in t))
    sys.exit(1)

t = t.replace(A1, T1 + A1, 1)
t = t.replace(A2, T2 + A2, 1)

with open(PATH, "w", encoding="utf-8-sig", newline="") as f:
    f.write(t)

print("PATCHED-OK: inserted scope2.8-qian (before '# 2.8') + scope-hou (before $gatePs)")
