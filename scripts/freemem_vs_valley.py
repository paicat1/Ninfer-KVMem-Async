# -*- coding: utf-8 -*-
"""用 watch 台账的 freemem 序列复核宿主内存维度（离线，不占机器）。
   注意：v1 台账的 freemem 单位错（KB÷1MB ⇒ 小 1024 倍），但【变化量】仍真实。
   目标：已知谷（00:31–00:38）期间 freemem 是否变化；对照 memhold 的 32 GiB。
"""
import io
import os
import re
import glob

ROOT = r'J:\ninfer-kvmem'
TEMPD = os.path.join(ROOT, '.temp')


def series(path):
    rows = []
    for line in io.open(path, encoding='utf-8', errors='replace'):
        m = re.match(r'^(\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?freemem(?:_mib)?=(\d+)', line)
        if not m:
            continue
        t = m.group(1)
        v = int(m.group(2))
        ver = '-1'
        mv = re.search(r'verify=([\d.]+)', line)
        if mv:
            ver = mv.group(1)
        dec = '-1'
        md = re.search(r'decode=([\d.]+)', line)
        if md:
            dec = md.group(1)
        rows.append((t, v, ver, dec))
    return rows


for name in ('windowwatch_20261016_0014.txt', 'windowwatch_20261016_0410.txt', 'windowwatch_20261016_0712.txt'):
    p = os.path.join(TEMPD, name)
    if not os.path.exists(p):
        continue
    rs = series(p)
    if not rs:
        continue
    vals = [r[1] for r in rs]
    print('== %s  rows=%d ==' % (name, len(rs)))
    print('   freemem 取值：min=%d max=%d 不同值=%d' % (min(vals), max(vals), len(set(vals))))
    # 找突变点（|Δ| > 5）
    print('   突变（|Δ|>5）：')
    for i in range(1, len(rs)):
        d = rs[i][1] - rs[i - 1][1]
        if abs(d) > 5:
            print('     %s  %d -> %d  (Δ=%+d)   verify=%s decode=%s   [前一行 %s]'
                  % (rs[i][0], rs[i - 1][1], rs[i][1], d, rs[i][2], rs[i][3], rs[i - 1][0]))
    # 打印 00:28–00:40 全段（若在范围内）
    print('   00:28–00:42 段：')
    for r in rs:
        if ' 00:2' in r[0] or ' 00:3' in r[0] or ' 00:4' in r[0]:
            print('     %s freemem=%d verify=%s decode=%s' % r)
