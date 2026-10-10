#!/usr/bin/env python3
"""3-round heterogeneous recall probe (挂账 40): force a REAL host->device retrieve.

  round A: big prompt X (~58K tok) -- fills/overflows the pool, pages sink to host
  round B: big prompt Y (~58K tok, different topic) -- evicts X's pages fully
  round C: SAME prompt X + a DIFFERENT trailing question
           -> prefix matches the sunken pages (no response-replay shortcut, since
              the question differs) => the engine must restore them from host.

Recall cost ≈ C.elapsed - A.elapsed (same-token prefill baseline).
Authoritative numbers stay in the engine log (ring retrieve restored=..., req# TTFT).
"""
import json, sys, time, urllib.request

BASE = 'http://127.0.0.1:8094'
MODEL = 'qwen3.8-27b-coder390'
CHARS_PER_TOKEN = 4.0
TARGET_TOKENS = int(sys.argv[1]) if len(sys.argv) > 1 else 80000   # actual ≈ 0.725x (EN bias)


def material(tag):
    unit = ('The retrieval ring of the kv-mem engine keeps a resident device window over a '
            'paged host arena: pages evicted from the device pool remain addressable through '
            'their sequence ids, and a scoring pass prefers evidence pages whose content '
            'matches the current query before any decode step touches them. ')
    n = int(TARGET_TOKENS * CHARS_PER_TOKEN / len(unit)) + 1
    return '[' + tag + '] ' + unit * n


def ask(prompt, q, tag):
    body = {'model': MODEL, 'stream': False, 'max_tokens': 200, 'reasoning_effort': 'low',
            'messages': [{'role': 'user', 'content': prompt + '\n\n' + q}]}
    req = urllib.request.Request(BASE + '/v1/chat/completions',
                                 data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=900)
        obj = json.loads(r.read().decode('utf-8', 'replace'))
        u = obj.get('usage') or {}
        print('%s: %.1fs prompt=%s completion=%s' % (tag, time.time() - t0,
                                                     u.get('prompt_tokens'), u.get('completion_tokens')))
    except Exception as e:  # noqa: BLE001
        print('%s: EXC after %.1fs: %r' % (tag, time.time() - t0, e))


X = material('X')
Y = material('Y')
print('prompt X tokens ≈ %d' % int(len(X) / CHARS_PER_TOKEN))
ask(X, 'In one sentence, what is the main topic of this material?', 'A(fill/overflow)')
ask(Y, 'In one sentence, what is the main topic of this material?', 'B(evict)')
ask(X, 'Quote the very first sentence of this material verbatim, then explain the '
       'host arena in three sentences.', 'C(RECALL)  ')
