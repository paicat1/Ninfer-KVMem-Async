# -*- coding: utf-8 -*-
# Multi-turn pool-overflow reproduction (mimics agentic session: history + tool results).
# Turn 1: ~40K prompt -> tool-call style output
# Turn 2: same history + ~27K "tool result" -> prompt ~67K (overflow) -> measure decode
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


def dump(seed, target_tokens):
    rnd = random.Random(seed)
    lines = []
    n = 0
    i = 0
    while n < target_tokens:
        i += 1
        ws = [rnd.choice(WORDS) for _ in range(14)]
        line = 'entry %07d | %s | crc %08d' % (i, ' '.join(ws), rnd.getrandbits(32))
        lines.append(line)
        n += int(len(line) / 2.8)  # calibrated: probe A gave 81K tok for 228K chars
    return '\n'.join(lines)


def stream_turn(tag, messages, max_output):
    body = json.dumps({'model': MODEL, 'stream': True, 'max_tokens': max_output,
                       'reasoning_effort': 'low',
                       'messages': messages}).encode('utf-8')
    req = urllib.request.Request(URL, data=body, headers={'Content-Type': 'application/json'})
    t0 = time.time()
    tokens = 0
    text_parts = []
    finish = '?'
    speeds = []
    last_t, last_tok = t0, 0
    resp = urllib.request.urlopen(req, timeout=1800)
    for raw in resp:
        line = raw.decode('utf-8', 'replace').strip()
        if not line.startswith('data: '):
            continue
        p = line[6:]
        if p == '[DONE]':
            finish = 'DONE'; break
        try:
            obj = json.loads(p)
        except ValueError:
            continue
        ch = obj.get('choices', [{}])[0]
        if ch.get('finish_reason'):
            finish = ch['finish_reason']
        d = ch.get('delta') or {}
        piece = (d.get('content') or '')
        if piece:
            tokens += max(1, int(len(piece) / 3.6))
            text_parts.append(piece)
        now = time.time()
        if now - last_t >= 5.0:
            speeds.append((now - t0, tokens - last_tok)); last_t, last_tok = now, tokens
    total = time.time() - t0
    print('[%s] total=%.1fs out~%d finish=%s' % (tag, total, tokens, finish))
    for el, tk in speeds:
        print('   t=%5.1fs  %6.1f tok/s' % (el, tk / 5.0))
    return ''.join(text_parts)


if __name__ == '__main__':
    t1 = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    t2 = int(sys.argv[2]) if len(sys.argv) > 2 else 27000
    hist_user = ('Here is the system log dump part 1. Call the analyze tool on it.\n\n'
                 + dump(11, t1))
    a1 = stream_turn('turn1', [{'role': 'user', 'content': hist_user}], 900)
    tool_result = ('TOOL RESULT (analyze output, full):\n' + dump(77, t2)
                   + '\n\nNow write a very long detailed final report (at least 900 words).')
    messages = [{'role': 'user', 'content': hist_user},
                {'role': 'assistant', 'content': a1 or 'I will analyze the log.'},
                {'role': 'user', 'content': tool_result}]
    stream_turn('turn2-overflow', messages, 1500)
