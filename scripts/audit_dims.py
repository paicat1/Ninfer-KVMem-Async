# -*- coding: utf-8 -*-
"""自诱导审计 v2：按 TELE 要求把"施加类"**拆成独立维度**：
   vram    = 显存压力类（vram_hold / trigger / dose / long_hold / night_ab / arm_ / interleave /
             mitig / pretrim / deepreach / headroom / catchtest / aba_ / evict / throttle / restore_and）
   hostmem = 宿主内存压力类（memhold）
   gpu     = 带宽/提交类（pageable_bench / concur_bench / submit_load）
   另给 no-apply 基线；并列出 hostmem 箱的逐条结果（TELE 的 memhold@00:33:39→谷@00:34 时序）。
"""
import io
import os
import re
import glob
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
    # ① probe 前缀优先（含 gate_ 一律算探针；旧词表曾把 gate_s13_* 误归 vram）
    if low.startswith('gate_') or any(p in low for p in PROBE_PAT):
        return 'probe'
    # ② 再做维度匹配，但排除 s13/loadinc/incidence（那是 S12 推理负载，不是显存压力工具）
    if any(p in low for p in ('s13', 'loadinc', 'incidence')):
        return 'other'
    for d, pats in DIM.items():
        if any(p in low for p in pats):
            return d
    return 'other'


def scan_valleys():
    out = []
    files = sorted(glob.glob(os.path.join(LOGD, 'test_valleywatch*.log*')))
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
                if mv and cur is not None:
                    out.append((cur, float(mv.group(1))))
        except Exception:
            continue
    return out, len(files)


def scan_activity():
    bins = {}
    try:
        names = os.listdir(TEMPD)
    except Exception:
        return bins
    for f in names:
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


def main():
    vals, nfiles = scan_valleys()
    act = scan_activity()
    if not vals:
        print('no rows')
        return
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

    def dims_at(b, adj=0):
        s = set()
        for k in range(-adj, adj + 1):
            s |= act.get(b + timedelta(minutes=BIN * k), set())
        return s

    print('== 覆盖 ==')
    print('  日志文件 %d | 谷行 %d | 箱 %d（%s → %s）'
          % (nfiles, len(vals), len(allbins), allbins[0].strftime('%m-%d %H:%M'), allbins[-1].strftime('%m-%d %H:%M')))
    print('')
    print('== 各维度：P(箱有谷 | 该箱属该维度) ==')
    print('  %-10s %8s %10s %10s %10s' % ('维度', '箱数', '谷≥100', '深≥226', '极深≥500'))
    for dim in ('vram', 'hostmem', 'gpu', 'probe', 'other'):
        for adj in (0, 1):
            sel = [b for b in allbins if dim in dims_at(b, adj)]
            if not sel:
                continue
            n100 = len([b for b in sel if vb.get(b, [0, 0, 0, 0])[1] > 0])
            n226 = len([b for b in sel if vb.get(b, [0, 0, 0, 0])[2] > 0])
            n500 = len([b for b in sel if vb.get(b, [0, 0, 0, 0])[3] > 0])
            print('  %-10s %8d %9.1f%% %9.1f%% %9.1f%%   (邻域±%d)'
                  % (dim, len(sel), 100.0 * n100 / len(sel), 100.0 * n226 / len(sel), 100.0 * n500 / len(sel), adj))
    print('')
    print('== 纯口径（箱内维度唯一，消除重叠）==')
    for dim in ('vram', 'hostmem', 'gpu', 'probe', 'other'):
        sel = [b for b in allbins if dims_at(b, 0) == {dim}]
        if not sel:
            print('  %-8s 箱数=0' % dim)
            continue
        n100 = len([b for b in sel if vb.get(b, [0, 0, 0, 0])[1] > 0])
        n226 = len([b for b in sel if vb.get(b, [0, 0, 0, 0])[2] > 0])
        print('  %-8s 箱数=%3d 谷>=100 %5.1f%%  深>=226 %5.1f%%'
              % (dim, len(sel), 100.0 * n100 / len(sel), 100.0 * n226 / len(sel)))
    print('')
    print('== hostmem（memhold）逐箱明细（TELE 要求的独立维度）==')
    rows = [b for b in allbins if 'hostmem' in dims_at(b, 0)]
    for b in rows:
        d = vb.get(b, [0, 0, 0, 0])
        print('  %s | 谷行=%d 谷=%d 深=%d 极深=%d | 同箱其它维度=%s'
              % (b.strftime('%m-%d %H:%M'), d[0], d[1], d[2], d[3],
                 sorted(dims_at(b, 0) - {'hostmem'}) or '无'))
    print('  hostmem 箱数 = %d' % len(rows))
    print('')
    print('== 纯 hostmem（该箱/邻域无 vram/gpu）==')
    pure = [b for b in allbins if 'hostmem' in dims_at(b, 1) and not ({'vram', 'gpu'} & dims_at(b, 1))]
    for b in pure:
        d = vb.get(b, [0, 0, 0, 0])
        print('  %s | 谷行=%d 谷=%d 深=%d 极深=%d' % (b.strftime('%m-%d %H:%M'), d[0], d[1], d[2], d[3]))
    print('  纯 hostmem 箱数 = %d' % len(pure))
    print('')
    print('== 反例：非施加（无 vram/hostmem/gpu）却有深谷 ==')
    cnt = 0
    for b in allbins:
        if not ({'vram', 'hostmem', 'gpu'} & dims_at(b, 1)) and vb.get(b, [0, 0, 0, 0])[2] > 0:
            d = vb[b]
            print('  %s | 谷行=%d 深=%d 极深=%d | 维度=%s' % (b.strftime('%m-%d %H:%M'), d[0], d[2], d[3], sorted(dims_at(b, 1))))
            cnt += 1
    if cnt == 0:
        print('  （无）')
    print('  反例箱数 = %d' % cnt)


if __name__ == '__main__':
    main()
