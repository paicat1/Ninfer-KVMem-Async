#!/usr/bin/env python3
"""Stage 0 reqlog 读数器：逐窗 host 记账 + 接受率解构（只读）。

输入：引擎 `--request-log-jsonl` 的 JSONL（取 event=throughput 记录）。
核心恒等式：tok/s ≈ (rounds/interval) × (tokens/round)
  - rounds/s 低 + host 饱和  -> 谷（host 税限制轮速）
  - rounds/s 正常 + tok/round 低 -> 接受率崩（多轮空转）
输出：总览（中位/极值）+ 最慢窗口分解表 + 最快对照 + host 饱和占比。
用法：python scripts/stage0_read.py [--log .temp/reqlog_stage0.jsonl] [--slow 15] [--since HH:MM:SS]
"""
import argparse
import datetime
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _f(x, nd=1):
    return None if x is None else round(x, nd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default=os.path.join(ROOT, '.temp', 'reqlog_stage0.jsonl'))
    ap.add_argument('--slow', type=int, default=15)
    ap.add_argument('--since', default=None)
    args = ap.parse_args()

    rows = []
    with open(args.log, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get('event') != 'throughput':
                continue
            stamp = datetime.datetime.fromtimestamp(rec['timestamp_unix_ms'] / 1000.0).strftime('%H:%M:%S')
            if args.since and stamp < args.since:
                continue
            interval = rec.get('interval_seconds') or 0.0
            host = rec.get('host_work') or {}
            total = (host.get('elapsed_seconds') or {}).get('total') or 0.0
            classes = host.get('work_class_seconds') or {}
            rounds = (rec.get('decode_batch') or {}).get('rounds') or 0
            tokens = (rec.get('tokens') or {}).get('committed_decode') or 0
            speed = (rec.get('throughput_tokens_per_second') or {}).get('decode') or 0.0
            submitted = (host.get('elapsed_seconds') or {}).get('program_submit') or 0.0
            rows.append({
                't': stamp, 'iv': interval, 'tp': speed, 'tok': tokens, 'rounds': rounds,
                'pf': (rec.get('tokens') or {}).get('computed_prefill') or 0,
                'tok_round': (tokens / rounds) if rounds else None,
                'rps': (rounds / interval) if interval else None,
                'host_s': total, 'host_pct': (100.0 * total / interval) if interval else None,
                'host_round_ms': (1000.0 * total / rounds) if rounds else None,
                'submit_s': submitted,
                'dec_host': classes.get('decode_host') or 0.0,
                'dev_wait': classes.get('decode_device_wait') or 0.0,
                'pf_host': classes.get('prefill_host') or 0.0,
            })
    if not rows:
        print('no throughput records in %s' % args.log)
        return

    def line(row):
        base = ('%s | %7s tok/s | %6s r/s x %5s tok/r (%d tok/%d r) | host %5s%% %6s ms/r | submit %ss'
                % (row['t'], _f(row['tp']), _f(row['rps'], 2), _f(row['tok_round'], 2), row['tok'], row['rounds'],
                   _f(row['host_pct']), _f(row['host_round_ms']), _f(row['submit_s'], 2)))
        if row['pf'] > 0:
            base += ' | PF %d tok' % row['pf']
        return base

    def stat(key):
        values = sorted(r[key] for r in rows if r[key] is not None)
        if not values:
            return '-'
        return '%s / %s / %s' % (_f(values[0], 2), _f(values[len(values) // 2], 2), _f(values[-1], 2))

    print('== %s ==' % args.log)
    print('windows: %d  span: %s..%s  (min/median/max)' % (len(rows), rows[0]['t'], rows[-1]['t']))
    print('decode tok/s   : %s' % stat('tp'))
    print('rounds/s       : %s' % stat('rps'))
    print('tokens/round   : %s' % stat('tok_round'))
    print('host %% of win  : %s' % stat('host_pct'))
    print('host ms/round  : %s' % stat('host_round_ms'))
    hot = [r for r in rows if (r['host_pct'] or 0) >= 95.0]
    print('host>=95%% windows: %d/%d (%.1f%%)' % (len(hot), len(rows), 100.0 * len(hot) / len(rows)))

    active = [r for r in rows if r['tok'] > 0]
    decode_only = [r for r in active if r['pf'] == 0]
    print('decode-only windows: %d / active %d (prefill-mixed %d)'
          % (len(decode_only), len(active), len(active) - len(decode_only)))
    by_speed = sorted(active, key=lambda r: r['tp'])
    print('')
    print('--- slowest %d decode-active windows ---' % args.slow)
    for row in by_speed[:args.slow]:
        print('  ' + line(row))
    print('--- fastest %d (对照) ---' % min(5, len(by_speed)))
    for row in by_speed[-5:]:
        print('  ' + line(row))

    fast = [r for r in decode_only if r['tp'] >= 300.0 and r['tok_round'] is not None]
    slow = [r for r in decode_only if r['tp'] < 40.0 and r['tok_round'] is not None]
    for name, group in (('fast>=300', fast), ('slow<40', slow)):
        if group:
            avg_tr = sum(r['tok_round'] for r in group) / len(group)
            avg_rps = sum(r['rps'] or 0.0 for r in group) / len(group)
            avg_hp = sum(r['host_pct'] or 0.0 for r in group) / len(group)
            print('%s: n=%d  avg tok/round=%.2f  avg rounds/s=%.2f  avg host=%.1f%%'
                  % (name, len(group), avg_tr, avg_rps, avg_hp))


if __name__ == '__main__':
    main()
