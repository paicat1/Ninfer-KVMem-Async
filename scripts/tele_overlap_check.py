# -*- coding: utf-8 -*-
"""TELE 独立检查：audit_dims 的口径——probe/other 箱与施加类是否重叠。
   用途：核"probe 8.8% vs other 5.8%"是否被"施加期探针"污染（重叠箱）。"""
import io, os, re, glob
from datetime import datetime, timedelta

ROOT = r'J:\ninfer-kvmem'
LOGD = os.path.join(ROOT, 'logs')
TEMPD = os.path.join(ROOT, '.temp')
BIN = 5
RE_TS = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
RE_VER = re.compile(r'target-split.*verify=([\d.]+)')

DIM = {
    'vram': ('vram_hold', 'trigger', 'dose', 'longhold', 'sustain', 'night_ab', 'arm_', 'interleave',
             'mitig', 'pretrim', 'deepreach', 'headroom', 'catchtest', 'aba_', 'pdl_', 'evict',
             'throttle', 'restore_and', 's13', 'loadinc', 'incidence'),
    'hostmem': ('memhold',),
    'gpu': ('pageable_bench', 'concur_bench', 'submit_load'),
}
PROBE_PAT = ('gate_', 'a2gate', 'windowwatch', 'reqlog')

def dim_of(name):
    low = name.lower()
    for d, pats in DIM.items():
        if any(p in low for p in pats):
            return d
    if any(p in low for p in PROBE_PAT):
        return 'probe'
    return 'other'

def scan_valleys():
    out = []
    files = sorted(glob.glob(os.path.join(LOGD, 'test_valleywatch*.log*')))
    n_parse_err = 0
    for p in files:
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
                if mv:
                    if cur is None:
                        n_parse_err += 1
                    else:
                        out.append((cur, float(mv.group(1))))
        except Exception:
            continue
    return out, n_parse_err

def scan_activity():
    bins = {}
    for f in os.listdir(TEMPD):
        p = os.path.join(TEMPD, f)
        try:
            if not os.path.isfile(p):
                continue
            st = os.stat(p)
        except Exception:
            continue
        t = datetime.fromtimestamp(st.st_mtime)
        if t < datetime(2026, 10, 14):
            continue
        b = t.replace(minute=(t.minute // BIN) * BIN, second=0, microsecond=0)
        bins.setdefault(b, set()).add(dim_of(f))
    return bins

vals, n_err = scan_valleys()
act = scan_activity()
t0 = min([t for t, _ in vals] + list(act.keys()))
t1 = max([t for t, _ in vals] + list(act.keys()))

def bof(t):
    return t.replace(minute=(t.minute // BIN) * BIN, second=0, microsecond=0)

vb = {}
for t, v in vals:
    d = vb.setdefault(bof(t), [0, 0, 0, 0])
    d[0] += 1
    if v >= 100: d[1] += 1
    if v >= 226: d[2] += 1
    if v >= 500: d[3] += 1

allbins = []
b = bof(t0)
while b <= t1:
    allbins.append(b)
    b += timedelta(minutes=BIN)

print('覆盖：文件谷行 %d | 无时间戳丢弃 %d' % (len(vals), n_err))

def has_valley(b, band=1):
    d = vb.get(b, [0, 0, 0, 0])
    return d[band] > 0

APPLY = {'vram', 'hostmem', 'gpu'}

# probe 箱分两类：与施加重叠 vs 纯
probe_bins = [b for b in allbins if 'probe' in act.get(b, set())]
probe_ov = [b for b in probe_bins if act.get(b, set()) & APPLY]
probe_pure = [b for b in probe_bins if not (act.get(b, set()) & APPLY)]
print('probe 箱 %d | 与施加重叠 %d | 纯 %d' % (len(probe_bins), len(probe_ov), len(probe_pure)))
for name, sel in (('probe 全部', probe_bins), ('probe(与施加重叠)', probe_ov), ('probe(纯)', probe_pure)):
    if sel:
        n100 = len([b for b in sel if has_valley(b, 1)])
        n500 = len([b for b in sel if has_valley(b, 3)])
        print('  %-22s n=%3d 谷≥100=%.1f%% 极深≥500=%.1f%%' % (name, len(sel), 100.0*n100/len(sel), 100.0*n500/len(sel)))

other_bins = [b for b in allbins if 'other' in act.get(b, set()) and not (act.get(b, set()) & (APPLY | {'probe'}))]
print('other 纯(无施加无probe) 箱 %d' % len(other_bins))
if other_bins:
    n100 = len([b for b in other_bins if has_valley(b, 1)])
    print('  other(纯) 谷≥100=%.1f%%' % (100.0*n100/len(other_bins)))

# 反例复查：非施加邻域有深谷
print('')
print('反例（±1 邻域无施加、深≥226）：')
cnt = 0
for b in allbins:
    s = set()
    for k in (-1, 0, 1):
        s |= act.get(b + timedelta(minutes=BIN*k), set())
    if not (s & APPLY) and has_valley(b, 2):
        d = vb[b]
        print('  %s | 谷行=%d 深=%d 极深=%d | 维度=%s' % (b.strftime('%m-%d %H:%M'), d[0], d[2], d[3], sorted(s)))
        cnt += 1
print('  反例箱数 = %d' % cnt)
