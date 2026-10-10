#!/usr/bin/env python3
"""AB arm-A wall test (挂账 38): engine WITHOUT --kv-lease-growth.

Overnight baseline (growth ON, logs/serve_20261010_01*.log): 22 output-limit requests,
15 clamped at ~4,037-4,071 output tokens (bounded completion of the ~4,096 lease window).

Pass criterion: streamed output clearly exceeds the old wall (est > 4,100 est-tokens)
without receiving finish_reason=length there; no 400/429/queue-starvation form.
Client aborts the stream past the threshold to keep each probe ~1 min.
"""
import json, sys, time, urllib.request

BASE = 'http://127.0.0.1:8094'
MODEL = 'qwen3.8-27b-coder390'
CHARS_PER_TOKEN = 4.0
ABORT_AT_CHARS = 20400          # ~5,100 est tokens: safely past the old wall
PROMPT_TOKENS = 16000           # overnight req#8 had prompt 16,653 -> same league
WALL_BAND = (3900, 4400)        # overnight wall band (15/22 hits)


def make_prompt():
    unit = ('The retrieval-augmented cache maintains a paged ring of token blocks with per-page '
            'sequence ids, refcounts, and a resident device window that can be evicted to host '
            'memory under pressure; scoring prefers recently mapped pages while hysteresis keeps '
            'the previous selection stable between rescoring passes. ')
    n = int(PROMPT_TOKENS * CHARS_PER_TOKEN / len(unit)) + 1
    return unit * n


def run(i, max_tokens=65536, effort='medium'):
    body = {
        'model': MODEL,
        'stream': True,
        'max_tokens': max_tokens,
        'reasoning_effort': effort,   # overnight req#32/38: medium/16,000; req#7: xhigh/32,000
        'messages': [
            {'role': 'user',
             'content': make_prompt() + '\n\nSummarize the passage above in detail, then continue '
                                        'analyzing its implications at length.'},
        ],
    }
    req = urllib.request.Request(BASE + '/v1/chat/completions',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    t0, ttft, chars, chunks, finish, aborted = time.time(), None, 0, 0, None, False
    resp = None
    try:
        resp = urllib.request.urlopen(req, timeout=900)
        for raw in resp:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data: '):
                continue
            payload = line[6:]
            if payload == '[DONE]':
                finish = finish or 'done'
                break
            obj = json.loads(payload)
            choice = (obj.get('choices') or [{}])[0]
            delta = choice.get('delta') or {}
            piece = (delta.get('reasoning_content') or '') + (delta.get('content') or '')
            if piece and ttft is None:
                ttft = time.time() - t0
            if piece:
                chars += len(piece)
            chunks += 1
            if choice.get('finish_reason'):
                finish = choice['finish_reason']
            if chars >= ABORT_AT_CHARS and not finish:
                aborted = True
                break
    except Exception as e:  # noqa: BLE001 - report anything odd verbatim
        finish = 'EXC:' + repr(e)
    finally:
        if resp is not None:
            resp.close()
    est = max(chunks, chars / CHARS_PER_TOKEN)
    past = int(est) > WALL_BAND[1]
    in_band = WALL_BAND[0] <= int(est) <= WALL_BAND[1]
    print('run#%d: ttft=%ss elapsed=%ss est_output_tokens=%d finish=%s client_aborted=%s'
          % (i, ttft is not None and round(ttft, 1) or '-', round(time.time() - t0, 1),
             int(est), finish, aborted))
    print('        -> past_old_wall=%s in_wall_band=%s' % (past, in_band))
    return past


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    effort = sys.argv[2] if len(sys.argv) > 2 else 'medium'
    if len(sys.argv) > 3:
        ABORT_AT_CHARS = int(sys.argv[3])
    results = [run(i + 1, effort=effort) for i in range(n)]
    print('SUMMARY: past_wall %d/%d -> ARM-A %s'
          % (sum(results), n, 'PASS (wall gone)' if all(results) else 'NOT CLEAN - inspect logs'))
