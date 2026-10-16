# -*- coding: utf-8 -*-
"""深谷窗（10-16 01:00–01:45）1 分钟分辨率对齐：引擎深读数 vs 我方工具活动。
   数据源：logs/test_valleywatch*.log*（用最近的带日期行给 target-split 打时间戳）+ .temp 台账 mtime。
"""
import io
import os
import re
import glob
from datetime import datetime

ROOT = r'J:\ninfer-kvmem'
LOGD = os.path.join(ROOT, 'logs')
TEMPD = os.path.join(ROOT, '.temp')
RE_TS = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
RE_VER = re.compile(r'target-split.*verify=([\d.]+)')

T0 = datetime(2026, 10, 16, 1, 0)
T1 = datetime(2026, 10, 16, 1, 45)

# ① 引擎读数（按分钟）
eng = {}
for p in sorted(glob.glob(os.path.join(LOGD, 'test_valleywatch*.log*'))):
    cur = None
    try:
        for line in io.open(p, encoding='utf-8', errors='replace'):
            m = RE_TS.match(line)
            if m:
                try:
                    cur = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
                continue
            mv = RE_VER.search(line)
            if mv and cur is not None and T0 <= cur <= T1:
                k = cur.replace(second=0, microsecond=0)
                d = eng.setdefault(k, [0, 0.0, 0.0])   # n, max, min
                v = float(mv.group(1))
                d[0] += 1
                d[1] = max(d[1], v)
                d[2] = v if d[2] == 0.0 else min(d[2], v)
    except Exception:
        continue

# ② 我方工具活动（按分钟；只看施加类）
APPLY = ('vram_hold', 'memhold', 'submit_load', 'pageable_bench', 'concur_bench', 'longhold',
         'sustain', 'dose', 'trigger', 'night_ab', 'arm_', 'interleave', 'mitig', 'pretrim',
         'deepreach', 'headroom', 'catchtest', 'aba_', 'pdl_', 'evict', 'throttle', 'restore_and')
act = {}
for f in os.listdir(TEMPD):
    p = os.path.join(TEMPD, f)
    try:
        if not os.path.isfile(p):
            continue
        st = os.stat(p)
    except Exception:
        continue
    low = f.lower()
    if not any(a in low for a in APPLY):
        continue
    t = datetime.fromtimestamp(st.st_mtime)
    if T0 <= t <= T1:
        act.setdefault(t.replace(second=0, microsecond=0), []).append(f)

print('== 10-16 01:00–01:45 逐分钟：引擎深读数 vs 我方施加类活动 ==')
print('  分钟   n   max_verify   min_verify   我方施加类台账（mtime 落该分钟）')
for i in range(46):
    k = T0.replace(minute=T0.minute) 
    k = T0 + (T1 - T0) * 0 + __import__('datetime').timedelta(minutes=i)
    k = k.replace(second=0, microsecond=0)
    e = eng.get(k)
    a = act.get(k, [])
    es = ('%3d  %8.1f  %8.1f' % (e[0], e[1], e[2])) if e else '  -         -         -'
    tag = ''
    if e and e[1] >= 500:
        tag = ' <<极深'
    elif e and e[1] >= 226:
        tag = ' <<深'
    print('  %s %s %s%s' % (k.strftime('%H:%M'), es, (','.join(sorted(set(a)))[:52] if a else ''), tag))
