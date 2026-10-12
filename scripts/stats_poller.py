# -*- coding: utf-8 -*-
"""stats_poller.py -- poll the engine /stats endpoint and append a timeline (one JSON row per tick).

Why: /stats already carries the RuntimeStats counters plus the host_work breakdown
(decode_host_ns / decode_device_wait_ns / program submit/post / device_wait) and the occupancy
(device_main_kv_occupied_pages / host_kv_bytes). Polling it during a drive yields a per-interval
timeline that can be aligned with the throughput log -- no rebuild needed.

Usage:
  python scripts\\stats_poller.py --port 8094 --out .temp\\ea1_stats.jsonl --interval 10 --minutes 90
"""

import argparse
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8094)
    ap.add_argument('--out', required=True)
    ap.add_argument('--interval', type=float, default=10.0)
    ap.add_argument('--minutes', type=float, default=90.0)
    ap.add_argument('--tag', default='')
    args = ap.parse_args()

    url = 'http://127.0.0.1:%d/stats' % args.port
    ticks = int(args.minutes * 60.0 / args.interval)
    with open(args.out, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps({'t': time.strftime('%H:%M:%S'), 'tag': args.tag,
                                 'event': 'poller_start'}) + '\n')
        handle.flush()
        for _ in range(ticks):
            row = {'t': time.strftime('%H:%M:%S')}
            try:
                with urllib.request.urlopen(url, timeout=10) as response:
                    row['stats'] = json.loads(response.read().decode('utf-8'))
            except Exception as exc:  # noqa: BLE001
                row['err'] = '%s: %s' % (type(exc).__name__, exc)
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            handle.flush()
            time.sleep(args.interval)


if __name__ == '__main__':
    main()
