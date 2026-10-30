# -*- coding: utf-8 -*-
"""valley_history.py -- 批 0（零成本先导）：从既有实机日志统计"池配置 / 构建版本 -> 谷指标"。

判据（与 valley_bench.parse 同口径）：decode < 20 tok/s 且连续 >= 2 个 5s 窗口 = 一次谷事件。
版本归属：用 engine\\self-built-20261008\\_deploy_log\\deploy_history.txt 的部署时间线，
把日志行时间映射到当时在跑的 exe sha（测试日志 test_<tag>.log 直接按 tag 标注）。

用法：python scripts\\valley_history.py [--glob logs\\*.log] [--out .temp\\valley_history.md]
"""
import argparse
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'J:\ninfer-kvmem'
RE_TP = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+\s+INFO\s+throughput \|')
RE_DEC = re.compile(r'decode ([\d.]+)(k?) tok/s')
RE_HOST = re.compile(r'host ([\d.]+)%')
RE_CAP = re.compile(r'capacity \| KV ([\d,]+) tokens, ([A-Za-z0-9_\-]+), (\w+) \| pages ([\d,]+)/([\d,]+)')


def deploy_timeline():
    path = os.path.join(ROOT, 'engine', 'self-built-20261008', '_deploy_log', 'deploy_history.txt')
    events = []
    if not os.path.exists(path):
        return events
    for line in open(path, encoding='utf-8', errors='replace'):
        m = re.match(r'\s*(\d{8})_(\w{4,6})\s+deploy=\S+\s+sha256=([0-9A-Fa-f]{8})', line)
        if m:
            when = m.group(1) + (m.group(2) + '0000')[:4]
            events.append((when, m.group(3).upper()))
    events.sort()
    return events


def build_for(stamp, events):
    key = stamp.replace('-', '').replace(' ', '').replace(':', '')[:12]
    label = '?'
    for when, sha in events:
        if when <= key:
            label = sha
        else:
            break
    return label


def scan(path, events):
    valleys = []
    current = None
    caps = set()
    with open(path, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            cap = RE_CAP.search(line)
            if cap:
                caps.add('KV %s tok, %s' % (cap.group(1), cap.group(2)))
            m = RE_TP.match(line)
            if not m:
                continue
            stamp = m.group(1)
            dec = RE_DEC.search(line)
            host = RE_HOST.search(line)
            rate = None
            if dec:
                rate = float(dec.group(1)) * (1000.0 if dec.group(2) else 1.0)
            if rate is not None and rate < 20.0:
                if current is None:
                    current = {'start': stamp, 'end': stamp, 'n': 1, 'min': rate,
                               'host': float(host.group(1)) if host else None}
                else:
                    current['end'] = stamp
                    current['n'] += 1
                    current['min'] = min(current['min'], rate)
                    if host:
                        current['host'] = max(current['host'] or 0.0, float(host.group(1)))
            else:
                if current is not None and current['n'] >= 2:
                    valleys.append(current)
                current = None
    if current is not None and current['n'] >= 2:
        valleys.append(current)
    return valleys, caps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--glob', default='logs\\*.log')
    parser.add_argument('--out', default='work\\data\\valley_history.md')
    args = parser.parse_args()
    events = deploy_timeline()
    print('部署时间线 %d 条；最新: %s' % (len(events), events[-1] if events else '-'))
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, args.glob))):
        name = os.path.basename(path)
        if name.startswith('test_'):
            label = 'EXP:' + name[5:-4]
        else:
            label = 'prod'
        try:
            valleys, caps = scan(path, events)
        except OSError:
            continue
        if not valleys:
            continue
        total = sum(v['n'] * 5 for v in valleys)
        worst = min(v['min'] for v in valleys)
        host = max((v['host'] or 0) for v in valleys)
        first = valleys[0]['start']
        build = build_for(first, events) if label == 'prod' else label
        rows.append((name, build, len(valleys), total, worst, host, first, sorted(caps)[:2]))
    rows.sort(key=lambda r: r[6])
    lines = ['# 批 0：既有日志的谷事件统计（池/版本 -> 谷指标）', '',
             '判据：decode<20 tok/s 且连续 >=2 个 5s 窗口。版本 = 部署台账映射（prod）或实验 tag。', '',
             '| 日志 | 版本/sha8 | 谷次数 | 谷总时长(s) | 最低 decode | host 峰值% | 首个谷时刻 | 池配置线索 |',
             '|---|---|---:|---:|---:|---:|---|---|']
    for name, build, count, total, worst, host, first, caps in rows:
        lines.append('| %s | %s | %d | %d | %.1f | %.0f | %s | %s |' % (
            name, build, count, total, worst, host, first, ' ; '.join(caps) if caps else '-'))
    out = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')
    print('logs with valleys: %d' % len(rows))
    for row in rows[:40]:
        print('  %-38s %-14s valleys=%-3d total=%-5ds worst=%5.1f host=%3.0f%% first=%s' % (
            row[0][:38], row[1], row[2], row[3], row[4], row[5], row[6]))
    print('written: %s' % out)


if __name__ == '__main__':
    main()
