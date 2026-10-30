# -*- coding: utf-8 -*-
"""A3 probe: cold-prefill comparison across engine arms.
- 每 (size, run) 用唯一 seed => 每次都是全量冷 prefill（无前缀缓存复用）
- 同 seed 公式跨臂一致 => 同一文本两种配置（可直比）
- 引擎侧 prefill tok/s / TTFT 从 logs\test_<tag>.log 的 req# done 行读取
Usage: python scripts\\a3probe.py --arm a3off --port 8094 --sizes 180,260 --runs 2
"""
import argparse
# 招牌名解析（2026-10-14）：--model-id 随底座变，禁止写死
try:
    from _modelid import model_id as _model_id
except Exception:  # 极端情况下回退旧名
    def _model_id(*_a, **_k):
        return "qwen3.8-27b-coder390"

import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

WORDS = ('alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike '
         'november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu').split()


def make_filler(kb, seed):
    target = kb * 1024
    state = seed
    parts = []
    size = 0
    while size < target:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        word = WORDS[state % len(WORDS)]
        parts.append(word)
        size += len(word) + 1
    return ' '.join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True)
    ap.add_argument('--port', type=int, default=8094)
    ap.add_argument('--sizes', default='180,260')
    ap.add_argument('--runs', type=int, default=2)
    ap.add_argument('--max-tokens', type=int, default=32)
    args = ap.parse_args()
    url = 'http://127.0.0.1:%d/v1/chat/completions' % args.port
    out = []
    for kb in [int(x) for x in args.sizes.split(',')]:
        for run in range(1, args.runs + 1):
            seed = 20261012 + kb * 10 + run
            filler = make_filler(kb, seed)
            prompt = filler + '\n\n[probe %dKB run %d] 用一句话总结上面文字的模式。' % (kb, run)
            body = json.dumps({
                'model': _model_id(),
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': args.max_tokens,
                'temperature': 0.7, 'top_p': 0.9, 'top_k': 20,
            }).encode('utf-8')
            request = urllib.request.Request(url, data=body,
                                             headers={'Content-Type': 'application/json'})
            started = time.time()
            record = {'arm': args.arm, 'size_kb': kb, 'run': run, 'seed': seed}
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    payload = json.loads(response.read().decode('utf-8'))
                record['elapsed_s'] = round(time.time() - started, 1)
                record['usage'] = payload.get('usage')
            except Exception as exc:  # noqa: BLE001
                record['error'] = '%s: %s' % (type(exc).__name__, exc)
            out.append(record)
            print('arm=%s size=%dKB run=%d  %.1fs  usage=%s%s' % (
                args.arm, kb, run, record.get('elapsed_s', 0),
                record.get('usage'), record.get('error', '')))
    _outdir = r'J:\ninfer-kvmem\work\data'
    os.makedirs(_outdir, exist_ok=True)
    path = os.path.join(_outdir, 'a3probe_%s.json' % args.arm)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print('written: %s' % path)


if __name__ == '__main__':
    main()
