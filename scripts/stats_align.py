# -*- coding: utf-8 -*-
"""stats_align.py -- align a stats_poller timeline with the engine log's throughput series.

Prints per-sample rows: decode rate (from counters delta), decode rounds delta, the host_work
per-round breakdown at that sample, occupancy (device pages / host KV bytes), and flags rows
where the interval decode rate < --low (default 50 tok/s).

Usage:
  python scripts\\stats_align.py --stats .temp\\ea1_stats.jsonl --log logs\\test_ea1c_agentic.log --low 50
"""

import argparse
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

TP = re.compile(r'(\d{2}:\d{2}:\d{2})\.\d+\s+INFO\s+throughput \| ([\d.]+)s \|(.*)$')
DEC = re.compile(r'decode ([\d.]+) tok/s')


def load_throughput(path):
    rows = []
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            for line in handle:
                m = TP.search(line)
                if not m:
                    continue
                d = DEC.search(m.group(3))
                rows.append((m.group(1), float(d.group(1)) if d else None))
    except OSError:
        pass
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stats', required=True)
    ap.add_argument('--log', required=True)
    ap.add_argument('--low', type=float, default=50.0)
    args = ap.parse_args()

    samples = []
    with open(args.stats, 'r', encoding='utf-8') as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            st = row.get('stats')
            if not st:
                continue
            hw = st.get('host_work') or {}
            occ = st.get('occupancy') or {}
            cnt = st.get('counters') or {}
            samples.append({
                't': row.get('t'),
                'committed': cnt.get('committed_decode_tokens'),
                'rounds': cnt.get('decode_rounds'),
                'host_us_round': hw.get('decode_host_microseconds_per_round'),
                'devwait_us_round': hw.get('decode_device_wait_microseconds_per_round'),
                'pages': occ.get('device_main_kv_pages'),
                'host_bytes': occ.get('host_kv_bytes'),
            })

    tp = load_throughput(args.log)
    print('stats samples=%d  throughput rows=%d' % (len(samples), len(tp)))
    print('%-8s %8s %7s %8s %10s %12s %6s %11s  %s' % (
        'time', 'dkTok/Δt', 'rounds', 'h_us/rd', 'dw_us/rd', 'pages', 'hostMB', 'flag', 'log decode'))
    prev = None
    for s in samples:
        rate = ''
        drds = ''
        if prev and s['committed'] is not None and prev['committed'] is not None:
            from datetime import datetime
            try:
                dt = (datetime.strptime(s['t'], '%H:%M:%S') -
                      datetime.strptime(prev['t'], '%H:%M:%S')).total_seconds()
            except ValueError:
                dt = 0
            if dt > 0:
                rate = '%.1f' % ((s['committed'] - prev['committed']) / dt)
                drds = '%d' % ((s['rounds'] or 0) - (prev['rounds'] or 0))
        flag = ''
        try:
            if rate != '' and float(rate) < args.low:
                flag = '<-- LOW'
        except ValueError:
            pass
        recent = [d for (t, d) in tp if d is not None and s['t'] and t <= s['t']][-3:]
        print('%-8s %8s %7s %8s %10s %12s %6s %11s  %s' % (
            s['t'], rate, drds,
            round(s['host_us_round'] or 0), round(s['devwait_us_round'] or 0),
            s['pages'], round((s['host_bytes'] or 0) / 1e6, 1), flag,
            ','.join('%.0f' % x for x in recent)))
        prev = s


if __name__ == '__main__':
    main()
