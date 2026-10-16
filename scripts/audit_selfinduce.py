# -*- coding: utf-8 -*-
"""自诱导混淆审计（按 TELE 收紧判据）：
   ① 谷事件线：扫全部 logs/test_valleywatch*.log*，用"最近的带日期行"给每条 target-split 打时间戳；
   ② 活动线：.temp 下台账 mtime，按文件名分「施加类 / 探针类 / 其它」，落到 5 分钟箱；
   ③ 条件概率：P(谷|施加箱) vs P(谷|非施加箱)，另给 ±1 箱邻域口径；
   ④ 反例检查：施加了却没谷的箱（对应剂量阈值 200 MiB 已知无效）。
"""
import io
import os
import re
import glob
from datetime import datetime, timedelta

ROOT = r'J:\ninfer-kvmem'
LOGD = os.path.join(ROOT, 'logs')
TEMPD = os.path.join(ROOT, '.temp')
BIN = 5          # 分钟
RE_TS = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
RE_VER = re.compile(r'target-split.*verify=([\d.]+)')

APPLY_PAT = ('throttle', 'evict', 'vram_hold', 'memhold', 'submit_load', 'pageable_bench', 'concur_bench',
             'longhold', 'sustain', 'dose', 'dosefine', 'trigger', 'night_ab', 'arm_',
             'interleave', 'mitig', 'pretrim', 'deepreach', 'eviction', 'restore_and',
             'headroom', 'catchtest', 'aba_', 'pdl_')
PROBE_PAT = ('gate_', 'a2gate', 'windowwatch', 'reqlog')


def classify(name):
    low = name.lower()
    if any(p in low for p in APPLY_PAT):
        return 'apply'
    if any(p in low for p in PROBE_PAT):
        return 'probe'
    return 'other'


def scan_valleys():
    """返回 [(t, verify)]"""
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
    """返回 {(bin_start): set(class)}"""
    bins = {}
    try:
        names = os.listdir(TEMPD)
    except Exception:
        return bins
    for f in names:
        p = os.path.join(TEMPD, f)
        try:
            st = os.stat(p)
        except Exception:
            continue
        if not os.path.isfile(p):
            continue
        t = datetime.fromtimestamp(st.st_mtime)
        if t < datetime(2026, 10, 14):
            continue
        b = t.replace(minute=(t.minute // BIN) * BIN, second=0, microsecond=0)
        bins.setdefault(b, set()).add(classify(f))
    return bins


def main():
    vals, nfiles = scan_valleys()
    act = scan_activity()
    if not vals:
        print('no valley rows found')
        return
    t0 = min(t for t, _ in vals)
    t1 = max(t for t, _ in vals)
    # 也把活动时间范围并进来（活动可能早于/晚于首个谷）
    if act:
        ta0 = min(act.keys())
        ta1 = max(act.keys())
        t0 = min(t0, ta0)
        t1 = max(t1, ta1)
    print('== 覆盖 ==')
    print('  日志文件 = %d | 谷行(target-split) = %d | 时间跨度 %s → %s'
          % (nfiles, len(vals), t0.strftime('%m-%d %H:%M'), t1.strftime('%m-%d %H:%M')))

    def bin_of(t):
        return t.replace(minute=(t.minute // BIN) * BIN, second=0, microsecond=0)

    vb = {}
    for t, v in vals:
        b = bin_of(t)
        d = vb.setdefault(b, [0, 0, 0])   # n, >=100, >=226
        d[0] += 1
        if v >= 100:
            d[1] += 1
        if v >= 226:
            d[2] += 1
        if v >= 500:
            d.append(1) if len(d) < 4 else None
            if len(d) == 4:
                d[3] += 1
    # 补齐四元组
    for b, d in vb.items():
        while len(d) < 4:
            d.append(0)

    allbins = []
    b = t0 - timedelta(minutes=t0.minute % BIN, seconds=t0.second)
    while b <= t1:
        allbins.append(b)
        b += timedelta(minutes=BIN)
    print('  5 分钟箱 = %d（%s → %s）' % (len(allbins), allbins[0].strftime('%m-%d %H:%M'), allbins[-1].strftime('%m-%d %H:%M')))

    def is_apply(b, adj=0):
        for k in range(-adj, adj + 1):
            bb = b + timedelta(minutes=BIN * k)
            s = act.get(bb)
            if s and 'apply' in s:
                return True
        return False

    print('')
    print('== 条件概率（TELE 收紧判据）==')
    for lvl, idx in (('谷(>=100ms)', 1), ('深(>=226ms)', 2), ('极深(>=500ms)', 3)):
        for adj in (0, 1):
            ap = [b for b in allbins if is_apply(b, adj)]
            np_ = [b for b in allbins if not is_apply(b, adj)]
            ap_hit = [b for b in ap if vb.get(b, [0, 0, 0, 0])[idx] > 0]
            np_hit = [b for b in np_ if vb.get(b, [0, 0, 0, 0])[idx] > 0]
            pa = (100.0 * len(ap_hit) / len(ap)) if ap else float('nan')
            pn = (100.0 * len(np_hit) / len(np_)) if np_ else float('nan')
            print('  %-12s 邻域±%d箱 | 施加箱 %d 中有谷 %d (%.1f%%) | 非施加箱 %d 中有谷 %d (%.1f%%)'
                  % (lvl, adj, len(ap), len(ap_hit), pa, len(np_), len(np_hit), pn))

    print('')
    print('== 施加箱里"没谷"的（反例/剂量阈值线索）==')
    cnt = 0
    for b in allbins:
        if is_apply(b, 0) and vb.get(b, [0, 0, 0, 0])[1] == 0:
            cnt += 1
    print('  施加箱总数=%d | 其中无谷=%d' % (len([b for b in allbins if is_apply(b, 0)]), cnt))

    print('')
    print('== 非施加箱里"有深谷"的（自诱导假设的反例，逐条列）==')
    shown = 0
    for b in allbins:
        if not is_apply(b, 1) and vb.get(b, [0, 0, 0, 0])[2] > 0:
            d = vb[b]
            s = act.get(b)
            print('  %s  谷行=%d 深=%d 极深=%d | 该箱台账=%s'
                  % (b.strftime('%m-%d %H:%M'), d[0], d[2], d[3], sorted(s) if s else '无'))
            shown += 1
            if shown >= 20:
                print('  ...(截断)')
                break
    if shown == 0:
        print('  （无）⇒ 深谷 100% 落在施加窗邻域内')


if __name__ == '__main__':
    main()
