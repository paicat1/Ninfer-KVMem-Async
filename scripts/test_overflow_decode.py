# -*- coding: utf-8 -*-
# Decode-stage pool-overflow reproduction probe (engine-side, no DSH needed).
# Probe A: prompt ~62K (inside 64K pool) -> expect decode ~100 tok/s
# Probe B: prompt ~70K (exceeds pool)   -> expect "prompt exceeds" + decode collapses to ~3-8 tok/s
# Usage: python scripts/test_overflow_decode.py <target_tokens> <max_output>
import json
import random
import sys
import time
import urllib.request

URL = 'http://127.0.0.1:8094/v1/chat/completions'
MODEL = 'qwen3.8-27b-coder390'

WORDS = ['alpha','bravo','charlie','delta','echo','foxtrot','golf','hotel','india',
         'juliet','kilo','lima','mike','november','oscar','papa','quebec','romeo',
         'sierra','tango','uniform','victor','whiskey','xray','yankee','zulu']


def make_prompt(target_tokens):
    rnd = random.Random(20261011)
    lines = []
    n = 0
    i = 0
    while n < target_tokens:
        i += 1
        ws = [rnd.choice(WORDS) for _ in range(14)]
        line = 'log entry %07d | %s | checksum %08d' % (i, ' '.join(ws), rnd.getrandbits(32))
        lines.append(line)
        n += int(len(line) / 3.6)  # mixed alnum+numbers ~3.6 chars/token
    return 'Below is a long log dump. Read it carefully and then summarize its structure in detail.\n\n' + '\n'.join(lines)


def run(tag, target_tokens, max_output):
    prompt = make_prompt(target_tokens)
    body = json.dumps({
        'model': MODEL,
        'stream': True,
        'max_tokens': max_output,
        'reasoning_effort': 'low',
        'messages': [{'role': 'user', 'content': prompt}],
    }).encode('utf-8')
    req = urllib.request.Request(URL, data=body,
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    speeds = []          # (elapsed, tokens_this_second)
    tokens = 0
    last_t = t0
    last_tokens = 0
    first_chunk_t = None
    finish = '?'
    try:
        resp = urllib.request.urlopen(req, timeout=1800)
        for raw in resp:
            line = raw.decode('utf-8', 'replace').strip()
            if not line.startswith('data: '):
                continue
            payload = line[6:]
            if payload == '[DONE]':
                finish = 'DONE'
                break
            try:
                obj = json.loads(payload)
            except ValueError:
                continue
            if first_chunk_t is None:
                first_chunk_t = time.time() - t0
            ch = obj.get('choices', [{}])[0]
            if ch.get('finish_reason'):
                finish = ch['finish_reason']
            d = ch.get('delta') or {}
            piece = d.get('content') or ''
            if piece:
                tokens += max(1, int(len(piece) / 3.6))
            now = time.time()
            if now - last_t >= 5.0:
                speeds.append((now - t0, tokens - last_tokens))
                last_t = now
                last_tokens = tokens
    except Exception as e:  # noqa: BLE001
        finish = 'ERR:' + str(e)[:80]
    total = time.time() - t0
    print('[%s] prompt_chars=%d (~%d tok) ttft=%s total=%.1fs out_tokens~%d finish=%s'
          % (tag, len(prompt), target_tokens,
             ('%.1fs' % first_chunk_t) if first_chunk_t else 'N/A', total, tokens, finish))
    for el, tk in speeds:
        print('   t=%5.1fs  %6.1f tok/s' % (el, tk / 5.0))
    return speeds


if __name__ == '__main__':
    tgt = int(sys.argv[1]) if len(sys.argv) > 1 else 62000
    out = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    run('A-inside' if tgt < 64000 else 'B-overflow', tgt, out)
