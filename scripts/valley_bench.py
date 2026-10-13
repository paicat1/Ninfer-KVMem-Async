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


def _t2s(stamp):
    parts = [int(part) for part in stamp.split(':')]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _parse_dur(text):
    if not text:
        return None
    match = re.search(r'([\d.]+)\s*ms\b', text)
    if match:
        return float(match.group(1)) / 1000.0
    match = re.search(r'(?:(\d+)\s*m\s*)?([\d.]+)\s*s\b', text)
    if not match:
        return None
    return int(match.group(1) or 0) * 60 + float(match.group(2))


def _tok_s(raw):
    raw = (raw or '').strip()
    if raw.endswith('k'):
        return float(raw[:-1]) * 1000.0
    return float(raw)


def _num(text):
    if text is None:
        return None
    try:
        return float(str(text).replace(',', ''))
    except ValueError:
        return None


def _stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {'n': len(values), 'min': round(min(values), 1),
            'median': round(ordered[len(ordered) // 2], 1),
            'avg': round(sum(values) / len(values), 1), 'max': round(max(values), 1)}


def scan(args):
    """全量扫描：计数 / 请求统计 / 吞吐分布 / 峰值 / 谷段 / 分段(10min)阶段表；出 json 供对照。"""
    path = args.log
    if not os.path.exists(path):
        print('log not found: %s' % path)
        return
    tag = args.tag or os.path.splitext(os.path.basename(path))[0]
    snap = os.path.join(ROOT, '.temp', 'scan_%s.txt' % tag)
    import shutil
    shutil.copyfile(path, snap)
    counts = {key: 0 for key in ('req_done', 'req_started', 'http500', 'recovery', 'reconcile',
                                 'writer_blocked', 'unavailable', 'prompt_exceeds')}
    markers = {'failed during generation': 'http500', 'recovery rebuilt': 'recovery',
               'activation reconcile': 'reconcile', 'writer-blocked': 'writer_blocked',
               'unavailable Device page': 'unavailable', 'prompt exceeds': 'prompt_exceeds'}
    series = []
    reqs = []
    build = None
    first_ts = last_ts = None
    req_re = re.compile(r'(\d{2}:\d{2}:\d{2})\.\d+\s+INFO\s+req#(\d+) (done|started) \|(.*)$')
    with open(snap, 'r', encoding='utf-8', errors='replace') as handle:
        for line in handle:
            if build is None:
                match = re.search(r'INFO\s+build (\S+)', line)
                if match:
                    build = match.group(1)
            for marker, key in markers.items():
                if marker in line:
                    counts[key] += 1
            match = THROUGHPUT_RE.search(line)
            if match:
                stamp, _window, rest = match.groups()
                first_ts = stamp if first_ts is None or stamp < first_ts else first_ts
                last_ts = stamp if last_ts is None or stamp > last_ts else last_ts
                if args.since and stamp < args.since:
                    continue
                entry = {'t': stamp, 'decode': None, 'prefill': None, 'host': None,
                         'running': 0, 'waiting': 0, 'phase': 'idle'}
                host = re.search(r'host ([\d.]+)%', rest)
                if host:
                    entry['host'] = float(host.group(1))
                for kind, value, _tokens in NUM_RE.findall(rest):
                    entry[kind] = _tok_s(value)
                run_info = re.search(r'running (\d+)(?: \(([^)]*)\))?', rest)
                if run_info:
                    entry['running'] = int(run_info.group(1))
                    flags = run_info.group(2) or ''
                    if 'prefill' in flags:
                        entry['phase'] = 'prefill'
                    elif 'decode' in flags:
                        entry['phase'] = 'decode'
                    elif entry['running'] > 0:
                        entry['phase'] = 'other'
                wait_info = re.search(r'waiting (\d+)', rest)
                if wait_info:
                    entry['waiting'] = int(wait_info.group(1))
                series.append(entry)
                continue
            match = req_re.search(line)
            if match:
                stamp, number, kind, rest = match.groups()
                counts['req_done' if kind == 'done' else 'req_started'] += 1
                record = {'t': stamp, 'n': int(number), 'kind': kind, 'prompt': None, 'output': None,
                          'cache_pct': None, 'ttft': None, 'total': None}
                match = re.search(r'prompt ([\d,]+)', rest)
                if match:
                    record['prompt'] = int(match.group(1).replace(',', ''))
                match = re.search(r'output ([\d,]+)', rest)
                if match:
                    record['output'] = int(match.group(1).replace(',', ''))
                match = re.search(r'cache [\d,]+ \(([\d.]+)%', rest)
                if match:
                    record['cache_pct'] = float(match.group(1))
                match = re.search(r'TTFT ([^|]+)', rest)
                if match:
                    record['ttft'] = _parse_dur(match.group(1))
                match = re.search(r'total ([^|]+)', rest)
                if match:
                    record['total'] = _parse_dur(match.group(1))
                reqs.append(record)
    decodes = [e['decode'] for e in series if e['decode'] is not None]
    hosts = [e['host'] for e in series if e['host'] is not None]
    prefills = [e['prefill'] for e in series if e['prefill'] is not None]
    # 判据口径 v2（2026-10-13 夜）：低 decode 窗必须分类——idle（无请求）与 prefill 混合窗不是谷。
    #   真谷（host_bound）= decode 活跃 + host 饱和（decode<20 且 host>=70%）；unattributed = decode 活跃但 host 空闲（收尾/空转伪影，待查）。
    low = [e for e in series if e['decode'] is not None and e['decode'] < 20.0]
    idle_w = [e for e in low if e['phase'] == 'idle']
    mixed_w = [e for e in low if e['phase'] in ('prefill', 'other')]
    active_low = [e for e in low if e['phase'] == 'decode']
    host_bound = [e for e in active_low if (e['host'] or 0.0) >= 70.0]
    unattributed = [e for e in active_low if (e['host'] or 0.0) < 70.0]
    valley = host_bound
    peaks = [e for e in series if e['decode'] is not None and e['decode'] >= 400.0]
    active_windows = [e for e in series if e['decode'] is not None and e['running'] > 0]
    runs = []
    run = []
    for entry in host_bound:
        if not run or _t2s(entry['t']) - _t2s(run[-1]['t']) <= 30:
            run.append(entry)
        else:
            if len(run) >= 2:
                runs.append(run)
            run = [entry]
    if len(run) >= 2:
        runs.append(run)
    buckets = {}
    for entry in series:
        key = '%s:%s0' % (entry['t'][:2], entry['t'][3])
        bucket = buckets.setdefault(key, {'n': 0, 'dec': [], 'host': []})
        bucket['n'] += 1
        if entry['decode'] is not None:
            bucket['dec'].append(entry['decode'])
        if entry['host'] is not None:
            bucket['host'].append(entry['host'])
    phase_rows = [{'phase': key, 'windows': buckets[key]['n'],
                   'decode': _stats(buckets[key]['dec']),
                   'host_avg': round(sum(buckets[key]['host']) / len(buckets[key]['host']), 1)
                   if buckets[key]['host'] else None}
                  for key in sorted(buckets)]
    done = [r for r in reqs if r['kind'] == 'done']
    summary = {
        'log': path, 'tag': tag, 'build': build, 'span': [first_ts, last_ts],
        'counts': counts,
        'throughput': {'samples': len(series), 'decode': _stats(decodes), 'prefill': _stats(prefills),
                       'host_max': max(hosts) if hosts else None,
                       'valley_samples': len(low),
                       'valley_share_pct': round(100.0 * len(low) / len(decodes), 1) if decodes else None,
                       'valley_class': {'host_bound': len(host_bound), 'idle': len(idle_w),
                                        'prefill_mixed': len(mixed_w), 'unattributed': len(unattributed)},
                       'valley_share_true_pct': round(100.0 * len(host_bound) / len(active_windows), 1)
                       if active_windows else None,
                       'peak_ge400': len(peaks)},
        'valley_runs': [{'start': run[0]['t'], 'end': run[-1]['t'], 'windows': len(run),
                         'min': min(e['decode'] for e in run)} for run in runs],
        'reqs': {'done': counts['req_done']},
        'phase_buckets': phase_rows,
    }
    if done:
        summary['reqs'].update({
            'output': _stats([r['output'] for r in done if r.get('output') is not None]),
            'ttft': _stats([r['ttft'] for r in done if r.get('ttft') is not None]),
            'cache': _stats([r['cache_pct'] for r in done if r.get('cache_pct') is not None]),
        })
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if peaks:
        print('--- peak windows >=400 ---')
        for entry in peaks[-12:]:
            print('  %s  decode=%s host=%s' % (entry['t'], entry['decode'], entry['host']))
    if unattributed:
        print('--- unattributed slow windows (decode-active, host<70%%) ---')
        for entry in unattributed[-12:]:
            print('  %s  decode=%s host=%s running=%s waiting=%s' % (
                entry['t'], entry['decode'], entry['host'], entry['running'], entry['waiting']))
    notable = [r for r in done if r.get('cache_pct') == 0.0 or (r.get('ttft') or 0) >= 30.0]
    if notable:
        print('--- notable reqs (cache 0 or TTFT >=30s) ---')
        for record in notable[-12:]:
            print('  req#%s %s prompt=%s output=%s cache=%s ttft=%s' % (
                record['n'], record['t'], record.get('prompt'), record.get('output'),
                record.get('cache_pct'), record.get('ttft')))
    out = os.path.join(ROOT, '.temp', 'scan_%s.json' % tag)
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
    print('written: %s' % out)


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
    scan_p = sub.add_parser('scan')
    scan_p.add_argument('--log', required=True)
    scan_p.add_argument('--tag')
    scan_p.add_argument('--since')
    scan_p.set_defaults(func=scan)
    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
