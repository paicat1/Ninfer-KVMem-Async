# -*- coding: utf-8 -*-
"""bench_analyze.py -- 把各配置的引擎日志对齐成可比曲线（长程 A/B 的分析器）。

对每个 tag：
  * 从 logs\\test_<tag>.log 抽 throughput 行 → (t, prefill/decode tok/s, host%)
  * 用 prefill 段的每窗口 token 数累加出"累计 token"，把 prefill 速率画成 (累计token → tok/s) 曲线
    —— 不同提示长度/不同版本的**同位置**可比（这是 E1/E2/E3 比较的关键）。
  * decode 段给出速率序列 + 判据（<20 tok/s 且连续 ≥2 窗口 = 入谷）。

用法：python tools\\bench_analyze.py E1_d2 E2_d1 E3_d2_noscore
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'J:\ninfer-kvmem'
RE_LINE = re.compile(r'(\d{2}:\d{2}:\d{2})\.\d+\s+INFO\s+throughput \| ([\d.]+)s \|(.*)$')
RE_NUM = re.compile(r'(prefill|decode) ([\d.]+)(k?) tok/s \(([\d,]+) tok\)')


def load(tag):
    log = os.path.join(ROOT, 'logs', 'test_%s.log' % tag)
    if not os.path.exists(log):
        return None
    snap = os.path.join(ROOT, '.temp', 'an_%s.txt' % tag)
    try:
        import shutil
        shutil.copyfile(log, snap)
    except OSError:
        return None
    rows = []
    with open(snap, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            m = RE_LINE.search(line)
            if not m:
                continue
            stamp, _w, rest = m.groups()
            host = re.search(r'host ([\d.]+)%', rest)
            row = {'t': stamp, 'host': float(host.group(1)) if host else None,
                   'prefill': None, 'decode': None, 'tokens': 0}
            for kind, value, k, tokens in RE_NUM.findall(rest):
                row[kind] = float(value) * (1000.0 if k else 1.0)
                row['tokens'] += int(tokens.replace(',', ''))
            rows.append(row)
    return rows


def curve(rows, kind):
    """按累计 token 分桶的速率曲线：[(cum_tokens, tok/s 中位数)]"""
    out = []
    cum = 0
    bucket_sum = bucket_n = 0
    for row in rows:
        rate = row.get(kind)
        if rate is None:
            continue
        cum += row['tokens']
        bucket_sum += rate
        bucket_n += 1
        if cum % 4096 < row['tokens'] or cum >= 4096 * (len(out) + 1):
            out.append((cum, bucket_sum / max(1, bucket_n)))
            bucket_sum = bucket_n = 0
    return out


def summarize(tag):
    rows = load(tag)
    if not rows:
        print('%-16s MISSING' % tag)
        return
    pre = [r for r in rows if r['prefill'] is not None]
    dec = [r for r in rows if r['decode'] is not None]
    hosts = [r['host'] for r in rows if r['host'] is not None]
    valley = [r for r in dec if r['decode'] < 20.0]
    print('== %s ==' % tag)
    print('  prefill 窗口 %d  累计 %s tok  中位 %.0f tok/s  首 %.0f  末 %.0f' % (
        len(pre), sum(r['tokens'] for r in pre),
        sorted(r['prefill'] for r in pre)[len(pre) // 2] if pre else 0,
        pre[0]['prefill'] if pre else 0, pre[-1]['prefill'] if pre else 0))
    print('  decode 窗口 %d  中位 %s  最低 %s  谷窗口 %d' % (
        len(dec), sorted(r['decode'] for r in dec)[len(dec) // 2] if dec else '-',
        min((r['decode'] for r in dec), default='-'), len(valley)))
    if hosts:
        print('  host 中位 %.0f%%  峰值 %.0f%%' % (sorted(hosts)[len(hosts) // 2], max(hosts)))
    print('  prefill 曲线（累计token→tok/s）: ' + '  '.join('%dK:%.0f' % (c / 1000.0, v) for c, v in curve(rows, 'prefill')[:12]))
    if dec:
        print('  decode 序列: ' + ' '.join('%.0f' % r['decode'] for r in dec[:24]))


for tag in sys.argv[1:]:
    summarize(tag)
