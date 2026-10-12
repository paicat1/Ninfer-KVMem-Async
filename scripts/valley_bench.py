# -*- coding: utf-8 -*-
"""valley_bench.py -- 死亡谷测试台（长程验证基础设施）。

两个模式：
  1) drive  : 对引擎打固定工作负载（多轮累积 + 确定性填充），每轮记录 time/usage/timings；
              结果写 .temp\\bench_<tag>.json，并打印紧凑表格。
  2) parse  : 解析引擎日志里自报的 `throughput |` 序列（含 host%），给出死亡谷判据：
              判据 = decode < 20 tok/s 且持续 >= 2 个 5s 窗口（本仓 §3.1 口径的简化版）；
              输出：入谷时刻、谷内最低 decode、host 峰值、谷时长。

用法：
  python scripts\\valley_bench.py drive --tag g_d2 --port 8094 --rounds 3 --filler-kb 220 --max-tokens 3000
  python scripts\\valley_bench.py parse --tag g_d2                 # 解析 logs\\test_<tag>.log
  python scripts\\valley_bench.py parse --log logs\\test_x.log --since "08:30:00"
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

ROOT = r'J:\ninfer-kvmem'
WORDS = ('alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike '
         'november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu').split()

THROUGHPUT_RE = re.compile(
    r'(\d{2}:\d{2}:\d{2})\.\d+\s+INFO\s+throughput \| ([\d.]+)s \|(.*)$')
NUM_RE = re.compile(r'(prefill|decode) ([\d.km]+) tok/s \(([\d,]+) tok\)')


def make_filler(kb, seed=20261012):
    """确定性填充文本：线性同余伪随机词序列（token 密度稳定，便于跨版本对照）。"""
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


def drive(args):
    filler = make_filler(args.filler_kb)
    history = []
    results = []
    url = 'http://127.0.0.1:%d/v1/chat/completions' % args.port
    for round_index in range(1, args.rounds + 1):
        prompt = (filler + '\n\n[round %d] 请用尽量长的篇幅、分点详细解释你在上一段文字里看到的模式，'
                  '并给出一个可执行的自检清单。' % round_index)
        messages = history + [{'role': 'user', 'content': prompt}]
        body = json.dumps({
            'model': args.model,
            'messages': messages,
            'max_tokens': args.max_tokens,
            'temperature': 0.7, 'top_p': 0.9, 'top_k': 20,
        }).encode('utf-8')
        request = urllib.request.Request(url, data=body,
                                         headers={'Content-Type': 'application/json'})
        started = time.time()
        record = {'round': round_index, 'started': time.strftime('%H:%M:%S')}
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                payload = json.loads(response.read().decode('utf-8'))
            record['http'] = response.status
            record['elapsed_s'] = round(time.time() - started, 1)
            record['usage'] = payload.get('usage')
            record['timings'] = payload.get('timings')
            choice = (payload.get('choices') or [{}])[0]
            content = (choice.get('message') or {}).get('content') or ''
            reasoning = (choice.get('message') or {}).get('reasoning_content') or ''
            history.append({'role': 'user', 'content': prompt})
            history.append({'role': 'assistant', 'content': (reasoning + '\n' + content)[:20000]})
        except Exception as exc:  # noqa: BLE001
            record['error'] = '%s: %s' % (type(exc).__name__, exc)
            record['elapsed_s'] = round(time.time() - started, 1)
        results.append(record)
        timings = record.get('timings') or {}
        print('round %d  http=%s  %.1fs  prompt=%s  decode=%s  pred_tok/s=%s  accepted=%s/%s' % (
            round_index, record.get('http'), record.get('elapsed_s', 0),
            (record.get('usage') or {}).get('prompt_tokens'),
            (record.get('usage') or {}).get('completion_tokens'),
            round(timings.get('predicted_per_second', 0) or 0, 1),
            timings.get('draft_n_accepted'), timings.get('draft_n')))
        if record.get('error'):
            print('    error: %s' % record['error'])
    out = os.path.join(ROOT, '.temp', 'bench_%s.json' % args.tag)
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump({'tag': args.tag, 'port': args.port, 'filler_kb': args.filler_kb,
                   'max_tokens': args.max_tokens, 'rounds': results}, handle,
                  ensure_ascii=False, indent=2)
    print('written: %s' % out)


def parse(args):
    if args.log:
        path = args.log
    else:
        path = os.path.join(ROOT, 'logs', 'test_%s.log' % args.tag)
    if not os.path.exists(path):
        print('log not found: %s' % path)
        return
    snap = os.path.join(ROOT, '.temp', 'bench_parse_%s.txt' % (args.tag or 'x'))
    try:
        import shutil
        shutil.copyfile(path, snap)
    except OSError as exc:
        print('copy failed: %s' % exc)
        return
    series = []
    with open(snap, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            match = THROUGHPUT_RE.search(line)
            if not match:
                continue
            stamp, _window, rest = match.groups()
            if args.since and stamp < args.since:
                continue
            entry = {'t': stamp, 'decode': None, 'prefill': None, 'host': None}
            host = re.search(r'host ([\d.]+)%', rest)
            if host:
                entry['host'] = float(host.group(1))
            for kind, value, _tokens in NUM_RE.findall(rest):
                value = value.replace('k', '000')
                try:
                    entry[kind] = float(value)
                except ValueError:
                    pass
            if entry['decode'] is not None or entry['host'] is not None:
                series.append(entry)
    decodes = [e['decode'] for e in series if e['decode'] is not None]
    hosts = [e['host'] for e in series if e['host'] is not None]
    valley = [e for e in series if (e['decode'] is not None and e['decode'] < 20.0)]
    verdict = {
        'samples': len(series),
        'decode_samples': len(decodes),
        'decode_max': max(decodes) if decodes else None,
        'decode_min': min(decodes) if decodes else None,
        'decode_median': sorted(decodes)[len(decodes) // 2] if decodes else None,
        'valley_samples': len(valley),
        'valley_first': valley[0]['t'] if valley else None,
        'valley_min': min((e['decode'] for e in valley), default=None),
        'host_max': max(hosts) if hosts else None,
        'verdict': 'IN-VALLEY' if len(valley) >= 2 else ('healthy' if decodes else 'no-data'),
    }
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    print('--- first 8 decode samples ---')
    for entry in series[:8]:
        print('  %s  decode=%s prefill=%s host=%s' % (entry['t'], entry['decode'], entry['prefill'], entry['host']))
    print('--- last 8 decode samples ---')
    for entry in series[-8:]:
        print('  %s  decode=%s prefill=%s host=%s' % (entry['t'], entry['decode'], entry['prefill'], entry['host']))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    drive_p = sub.add_parser('drive')
    drive_p.add_argument('--tag', required=True)
    drive_p.add_argument('--port', type=int, default=8094)
    drive_p.add_argument('--model', default='qwen3.8-27b-coder390')
    drive_p.add_argument('--rounds', type=int, default=3)
    drive_p.add_argument('--filler-kb', type=int, default=220)
    drive_p.add_argument('--max-tokens', type=int, default=3000)
    drive_p.add_argument('--timeout', type=int, default=2400)
    drive_p.set_defaults(func=drive)
    parse_p = sub.add_parser('parse')
    parse_p.add_argument('--tag')
    parse_p.add_argument('--log')
    parse_p.add_argument('--since')
    parse_p.set_defaults(func=parse)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
