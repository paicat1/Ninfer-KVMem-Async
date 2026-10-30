# -*- coding: utf-8 -*-
"""smart_push main-flow probes."""
import io

P = r'J:\ninfer-kvmem\smart_push.ps1'
t = io.open(P, 'rb').read().decode('utf-8')
lines = t.split('\r\n')

anchors = [
    ('# 1. proxy detect', 'proxy-detect-qian'),
    ('# 2. uncommitted check', 'uncommitted-qian'),
    ('# 2.7 regression gate', 'regression-qian'),
    ('# 2.8 tongyi-menjin', 'gates-qian'),
    ('# 3. push with retry', 'push-qian'),
]
inserts = {}
for frag, name in anchors:
    for i, ln in enumerate(lines):
        if frag in ln:
            inserts[i] = name
            break

out = []
for i, ln in enumerate(lines):
    if i in inserts:
        out.append('Write-Output ("[P] %s t=" + [int]$__pT.Elapsed.TotalMilliseconds)' % inserts[i])
    out.append(ln)

for i, ln in enumerate(out):
    if ln.startswith('# smart_push.ps1'):
        out.insert(i + 1, '$__pT = [Diagnostics.Stopwatch]::StartNew()')
        break
out.append('Write-Output ("[P] TOTAL ms=" + [int]$__pT.Elapsed.TotalMilliseconds)')
io.open(P, 'wb').write('\r\n'.join(out).encode('utf-8'))
print('probes: %d' % len(inserts))
