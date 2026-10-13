# -*- coding: utf-8 -*-
"""P5/谷现场快照：吞吐尾窗 + step profile + ring profile + 请求计数（只读）。

用法：python scripts\p5_snap.py [--log logs\test_p5_valley.log] [--tail 14]
"""
import argparse
import os
import re
import shutil
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', default=os.path.join(ROOT, 'logs', 'test_p5_valley.log'))
    ap.add_argument('--tail', type=int, default=14)
    args = ap.parse_args()
    snap = os.path.join(ROOT, '.temp', 'p5_now.txt')
    shutil.copyfile(args.log, snap)
    lines = open(snap, encoding='utf-8', errors='replace').read().split('\n')
    print('now %s | log %s' % (time.strftime('%H:%M:%S'), args.log))
    done = sum(1 for l in lines if re.search(r'req#\d+ done', l))
    bad = sum(1 for l in lines if 'failed during generation' in l)
    print('req done = %d | 500 = %d | lines = %d' % (done, bad, len(lines)))

    def tail(pattern, n, width=190):
        hits = [l.strip() for l in lines if pattern in l]
        print('== %s (last %d of %d) ==' % (pattern, n, len(hits)))
        for l in hits[-n:]:
            print('  ' + l[:width])

    tail('throughput', args.tail)
    tail('step profile', 10, 200)
    tail('ring profile window', 4, 200)
    tail('step profile slow', 4, 200)
    tail('req#', 4, 150)


if __name__ == '__main__':
    main()
