# -*- coding: utf-8 -*-
"""A2 gate: greedy paired runs per engine arm.
- temperature=0 / top_p=1 / top_k=1  => argmax（若引擎支持则逐字确定）
- 每次 run：新会话 2 轮（filler 45K -> 续写 90K），记 timings + 内容 sha256
- 判定：同臂 3 跑 sha 全同（引擎确定性控制）+ 跨臂 sha 全同（旗无损门）+ decode/accept 对照
Usage: python .temp\\a2gate.py --arm a2on --port 8094 --runs 3
"""
import argparse
# 招牌名解析（2026-10-14）：--model-id 随底座变，禁止写死
try:
    from _modelid import model_id as _model_id
except Exception:  # 极端情况下回退旧名
    def _model_id(*_a, **_k):
        return "qwen3.8-27b-coder390"

import hashlib
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

WORDS = ('alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike '
         'november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu').split()


# 2026-10-29 (C0): 每次调用唯一标识——同名 arm 重跑不再覆盖历史全文/指标
INVOCATION = time.strftime('%Y%m%d_%H%M%S')


def make_filler(kb, seed=20261012):
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
    ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--filler-kb', type=int, default=180)
    ap.add_argument('--nonce', default='', help='非空时把该标记插到 filler 头部：前缀缓存全失效 ⇒ 真实长预填（诱发谷用）')
    ap.add_argument('--max-tokens', type=int, default=600)
    args = ap.parse_args()
    filler = make_filler(args.filler_kb)
    if args.nonce:
        filler = ('[nonce ' + args.nonce + '] ' + 'x' * 8 + '\n') + filler  # 头部标记：让整段上下文不进缓存
    url = 'http://127.0.0.1:%d/v1/chat/completions' % args.port
    results = []
    for run in range(1, args.runs + 1):
        history = []
        for round_index in range(1, args.rounds + 1):
            prompt = (filler + '\n\n[round %d] 请用尽量长的篇幅、分点详细解释你在上一段文字里看到的模式，'
                      '并给出一个可执行的自检清单。' % round_index)
            messages = history + [{'role': 'user', 'content': prompt}]
            body = json.dumps({
                'model': _model_id(),
                'messages': messages,
                'max_tokens': args.max_tokens,
                'temperature': 0, 'top_p': 1.0, 'top_k': 1,
            }).encode('utf-8')
            request = urllib.request.Request(url, data=body,
                                             headers={'Content-Type': 'application/json'})
            started = time.time()
            record = {'run': run, 'round': round_index, 'invocation': INVOCATION}
            try:
                # 2026-10-26: 900s cap truncated every r3 (229K) run; raised to 2700s (TELE/CB prereg).
                with urllib.request.urlopen(request, timeout=2700) as response:
                    payload = json.loads(response.read().decode('utf-8'))
                record['elapsed_s'] = round(time.time() - started, 1)
                record['usage'] = payload.get('usage')
                record['timings'] = payload.get('timings')
                choice = (payload.get('choices') or [{}])[0]
                message = choice.get('message') or {}
                content = (message.get('content') or '')
                reasoning = (message.get('reasoning_content') or '')
                record['sha'] = hashlib.sha256(
                    (reasoning + '\n' + content).encode('utf-8')).hexdigest()[:16]
                record['length'] = len(reasoning) + len(content)
                # 2026-10-26 (#55): persist full output text so OFF/ON divergence can be diffed.
                try:
                    text_path = ('J:\\ninfer-kvmem\\work\\data\\abab_text_%s_%s_r%d.txt'
                                 % (args.arm, INVOCATION, round_index))
                    with open(text_path, 'w', encoding='utf-8') as text_handle:
                        text_handle.write(reasoning + '\n' + content)
                    record['text_path'] = text_path
                except Exception as text_exc:  # noqa: BLE001
                    record['text_error'] = '%s: %s' % (type(text_exc).__name__, text_exc)
                history.append({'role': 'user', 'content': prompt})
                history.append({'role': 'assistant',
                                'content': (reasoning + '\n' + content)[:20000]})
            except Exception as exc:  # noqa: BLE001
                record['error'] = '%s: %s' % (type(exc).__name__, exc)
            results.append(record)
            timings = record.get('timings') or {}
            print('run %d round %d  %.1fs  decode=%s  accepted=%s/%s  len=%s  sha=%s%s' % (
                run, round_index, record.get('elapsed_s', 0),
                round(timings.get('predicted_per_second', 0) or 0, 1),
                timings.get('draft_n_accepted'), timings.get('draft_n'),
                record.get('length'), record.get('sha'), record.get('error', '')))
    out = 'J:\\ninfer-kvmem\\work\\data\\gate_%s.json' % args.arm
    # 2026-10-29 (C0): 合并而非覆盖——同名 arm 重跑时保留历史 runs
    merged = []
    try:
        with open(out, 'r', encoding='utf-8') as prev_handle:
            merged = (json.load(prev_handle) or {}).get('runs') or []
    except Exception:  # noqa: BLE001
        merged = []
    new_keys = {(r.get('invocation'), r.get('run'), r.get('round')) for r in results}
    merged = [r for r in merged
              if (r.get('invocation'), r.get('run'), r.get('round')) not in new_keys]
    merged.extend(results)
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump({'arm': args.arm, 'runs': merged}, handle, ensure_ascii=False, indent=2)
    print('written: %s (runs=%d)' % (out, len(merged)))


if __name__ == '__main__':
    main()
