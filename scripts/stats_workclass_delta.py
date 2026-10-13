# -*- coding: utf-8 -*-
"""stats_workclass_delta.py -- per-interval delta of every work class from a stats_poller timeline.

Usage:
  python scripts\\stats_workclass_delta.py [timeline.jsonl]

Prints for each consecutive pair: committed/prefill token deltas, decode rounds delta, and the
seconds accumulated per class (decode_host / decode_device_wait / prefill_host /
prefill_device_wait), plus program_submit and host total. Use DELTAS only: the engine's
..._per_round fields carry an inconsistent denominator (observed during the 2026-10-13 valley).
"""

import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = sys.argv[1] if len(sys.argv) > 1 else r'J:\ninfer-kvmem\logs\ea1c_stats_timeline.jsonl'

rows = []
with open(path, 'r', encoding='utf-8') as handle:
    for line in handle:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        st = row.get('stats')
        if not st:
            continue
        hw = st.get('host_work') or {}
        el = hw.get('elapsed_seconds') or {}
        wc = hw.get('work_class_seconds') or {}
        rows.append({
            't': row.get('t'),
            'committed': (st.get('counters') or {}).get('committed_decode_tokens'),
            'prefill': (st.get('counters') or {}).get('computed_prefill_tokens'),
            'rounds': (st.get('counters') or {}).get('decode_rounds'),
            'host': wc.get('decode_host'),
            'dh': wc.get('decode_device_wait'),
            'ph': wc.get('prefill_host'),
            'pdw': wc.get('prefill_device_wait'),
            'totsub': el.get('program_submit'),
            'tottot': el.get('total'),
        })

print('%-8s %8s %8s %7s %8s %8s %8s %8s %8s %8s' % (
    'time', 'dComm', 'dPref', 'dRnd', 'd_decH', 'd_decDW', 'd_preH', 'd_preDW', 'd_submit', 'd_total'))
prev = None
for r in rows:
    if prev:
        def d(k):
            a, b = prev.get(k), r.get(k)
            return (b - a) if (a is not None and b is not None) else None
        print('%-8s %8s %8s %7s %8s %8s %8s %8s %8s %8s' % (
            r['t'], d('committed'), d('prefill'), d('rounds'),
            ('%.1f' % d('host')) if d('host') is not None else '',
            ('%.2f' % d('dh')) if d('dh') is not None else '',
            ('%.1f' % d('ph')) if d('ph') is not None else '',
            ('%.1f' % d('pdw')) if d('pdw') is not None else '',
            ('%.1f' % d('totsub')) if d('totsub') is not None else '',
            ('%.1f' % d('tottot')) if d('tottot') is not None else ''))
    prev = r
