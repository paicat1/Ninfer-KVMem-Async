# -*- coding: utf-8 -*-
"""valley_agentic.py -- agentic-shape multi-turn driver (death-valley repro).

Why: the death valley (decode <20 tok/s, self-healing bursts) reproduces under the DSH
agentic shape (many short turns, context 40-75K, occasional long outputs, periodic
conversation resets) and NOT under the one-shot deep probes of valley_bench. This driver
mimics the agentic shape so a valley can be produced on demand for profiling.

Shape (defaults):
  - base context ~9K tokens at round 1, grows +2-4K tokens per round;
  - when the estimated context reaches --compact-tokens, history is compacted to the last
    2 exchanges + a summary line (mimics the client's new-conversation/reset moments);
  - output budget: mostly --max-tokens; every 5th round 3x; every 13th round 10x (long turns).

Usage:
  python scripts\\valley_agentic.py --tag ea1 --port 8094 --rounds 30
"""

import argparse
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

WORDS = ('alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike '
         'november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu').split()


def make_text(kb, seed):
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


def est_tokens(messages):
    return len(json.dumps(messages, ensure_ascii=False)) // 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', required=True)
    ap.add_argument('--port', type=int, default=8094)
    ap.add_argument('--model', default='qwen3.8-27b-coder390')
    ap.add_argument('--rounds', type=int, default=30)
    ap.add_argument('--base-kb', type=int, default=36)
    ap.add_argument('--payload-kb', type=int, default=6)
    ap.add_argument('--max-tokens', type=int, default=1500)
    ap.add_argument('--compact-tokens', type=int, default=66000)
    ap.add_argument('--timeout', type=int, default=3600)
    args = ap.parse_args()

    url = 'http://127.0.0.1:%d/v1/chat/completions' % args.port
    history = []
    seed = 20261013

    for round_index in range(1, args.rounds + 1):
        if round_index == 1:
            payload = make_text(args.base_kb, seed)
            prompt = payload + '\n\n请概述上面文字的要点，并给出三个后续检查项。'
        else:
            seed += 7919
            if est_tokens(history) >= args.compact_tokens:
                keep = history[-4:]
                history = [{'role': 'user',
                            'content': '[前文摘要] 已在本地完成若干轮故障排查与代码修改；继续当前任务。'}] + keep
                print('  ** compact: history -> last %d messages, est %d tok **' % (len(history), est_tokens(history)))
            payload = make_text(max(1, args.payload_kb + (round_index % 3)), seed)
            prompt = payload + ('\n\n[round %d/agentic] 基于上下文继续：先分析这段材料的模式，'
                                '然后给出下一步操作清单（分点、尽量具体）。' % round_index)

        budget = args.max_tokens
        if round_index % 5 == 0:
            budget = args.max_tokens * 3
        if round_index % 13 == 0:
            budget = args.max_tokens * 10

        messages = history + [{'role': 'user', 'content': prompt}]
        body = json.dumps({
            'model': args.model,
            'messages': messages,
            'max_tokens': min(budget, 24000),
            'temperature': 0.7, 'top_p': 0.9, 'top_k': 20,
        }).encode('utf-8')
        request = urllib.request.Request(url, data=body,
                                         headers={'Content-Type': 'application/json'})
        started = time.time()
        status = 'ok'
        usage = {}
        timings = {}
        content = ''
        reasoning = ''
        try:
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                payload_out = json.loads(response.read().decode('utf-8'))
            usage = payload_out.get('usage') or {}
            timings = payload_out.get('timings') or {}
            choice = (payload_out.get('choices') or [{}])[0]
            message = choice.get('message') or {}
            content = message.get('content') or ''
            reasoning = message.get('reasoning_content') or ''
        except Exception as exc:  # noqa: BLE001
            status = '%s: %s' % (type(exc).__name__, exc)
        elapsed = time.time() - started

        history.append({'role': 'user', 'content': prompt})
        history.append({'role': 'assistant', 'content': (reasoning + '\n' + content)[:6000]})

        print('[%s] round %2d  %-7s %7.1fs  prompt=%s  out=%s  pred_tok/s=%s' % (
            args.tag, round_index, status, elapsed,
            usage.get('prompt_tokens'), usage.get('completion_tokens'),
            round(timings.get('predicted_per_second', 0) or 0, 1)))
        sys.stdout.flush()


if __name__ == '__main__':
    main()
