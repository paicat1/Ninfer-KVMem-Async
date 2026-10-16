# -*- coding: utf-8 -*-
"""Delta analysis across the stall: which work-class seconds accumulate per poller interval."""
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

path = r'J:\ninfer-kvmem\.temp\ea1_stats.jsonl'
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
            'dw': hw.get('device_wait_seconds'),
            'host': wc.get('decode_host'),
            'dh': wc.get('decode_device_wait'),
            'ph': wc.get('prefill_host'),
            'pdw': wc.get('prefill_device_wait'),
            'totsub': el.get('program_submit'),
            'tottot': el.get('total'),
        })

print('%-8s %8s %8s %7s %7s %7s %7s %7s %8s %8s' % (
    'time', 'dComm', 'dPref', 'dRnd', 'd_decH', 'd_decDW', 'd_preH', 'd_preDW', 'd_submit', 'd_total'))
prev = None
for r in rows:
    if prev:
        def d(k):
            a, b = prev.get(k), r.get(k)
            return (b - a) if (a is not None and b is not None) else None
        print('%-8s %8s %8s %7s %7s %7s %7s %7s %8s %8s' % (
            r['t'], d('committed'), d('prefill'), d('rounds'),
            ('%.1f' % d('host')) if d('host') is not None else '',
            ('%.2f' % d('dh')) if d('dh') is not None else '',
            ('%.1f' % d('ph')) if d('ph') is not None else '',
            ('%.1f' % d('pdw')) if d('pdw') is not None else '',
            ('%.1f' % d('totsub')) if d('totsub') is not None else '',
            ('%.1f' % d('tottot')) if d('tottot') is not None else ''))
    prev = r
