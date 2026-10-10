#!/usr/bin/env python3
"""Recall-latency probe (挂账: ring retrieve latency, Q3 follow-up).

Sends a prompt LARGER than the KV pool (default ~60K tokens vs 55,296 pool) to force
host-offload + ring-retrieve paths, then repeats the same prompt to observe the
retrieve/restored behaviour on the second pass. Authoritative numbers come from the
engine log (prompt exceeds / ring retrieve restored=N / req# done TTFT).
"""
import json, sys, time, urllib.request

BASE = 'http://127.0.0.1:8094'
MODEL = 'qwen3.8-27b-coder390'
CHARS_PER_TOKEN = 4.0
PROMPT_TOKENS = int(sys.argv[1]) if len(sys.argv) > 1 else 60000
ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
MAX_TOKENS = 200


def make_prompt():
    unit = ('The memory hierarchy of the retrieval ring keeps a resident device window backed '
            'by a pinned host arena; pages evicted from the device pool remain addressable and '
            'are restored on demand when a later request references their token range again. ')
    n = int(PROMPT_TOKENS * CHARS_PER_TOKEN / len(unit)) + 1
    return unit * n


def run(i):
    body = {
        'model': MODEL,
        'stream': False,
        'max_tokens': MAX_TOKENS,
        'reasoning_effort': 'low',
        'messages': [
            {'role': 'user',
             'content': make_prompt() + '\n\nReply with a one-sentence summary.'},
        ],
    }
    req = urllib.request.Request(BASE + '/v1/chat/completions',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=600)
        obj = json.loads(resp.read().decode('utf-8', 'replace'))
        elapsed = time.time() - t0
        usage = obj.get('usage') or {}
        print('round#%d: elapsed=%.1fs prompt_tokens=%s completion=%s' % (
            i, elapsed, usage.get('prompt_tokens'), usage.get('completion_tokens')))
    except Exception as e:  # noqa: BLE001
        print('round#%d: EXC after %.1fs: %r' % (i, time.time() - t0, e))


if __name__ == '__main__':
    for i in range(1, ROUNDS + 1):
        run(i)
