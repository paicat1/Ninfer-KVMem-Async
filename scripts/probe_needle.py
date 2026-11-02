#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""probe_needle.py -- needle recall probe for the async x scoring composition fork (P3-20 quality leg).

Approved design (2026-11-02):
  material X (~72K tok actual) carries 6 unique needle codes at spread depths;
    A_fill  : X + topic question  -> fills/overflows the device pool, pages sink to host
    B_evict : Y (different topic) -> evicts X pages
    C_recall: X + needle question -> same prefix, different question => real host->device retrieve
  judge  : needle codes found in the C answer (argmax sampling, thinking off, identical client every arm)
  serve-side evidence: "kvmem_score: KEPT <ids...>" lines in the serve log (parsed by the matrix driver)

usage:
  python -X utf8 scripts\\probe_needle.py --arm <tag> --port 8094
output:
  work\\data\\needle_<tag>.json
guard: all-arm zero hits = probe defect (material/question broken), NOT an engine verdict.
"""
import argparse
import io
import json
import os
import time
import urllib.request

try:
    from _modelid import model_id as _model_id
except Exception:
    def _model_id(*_a, **_k):
        return 'qwen3.8-27b-coder390'

BASE = 'http://127.0.0.1:%d'
CHARS_PER_TOKEN = 4.0
TARGET_TOKENS = 100000                      # nominal; actual ~= 0.725x (EN bias) => ~72K tok
NEEDLE_FRACTIONS = (0.04, 0.22, 0.40, 0.58, 0.76, 0.94)

NEEDLES = [
    ('NEEDLE-71-QUARTZ',  'Field note NEEDLE-71-QUARTZ: the spring survey calibrated the rain gauge against a brass standard.'),
    ('NEEDLE-23-EMBER',   'Field note NEEDLE-23-EMBER: the packing list for the autumn depot run was signed by the quartermaster.'),
    ('NEEDLE-58-MARSH',   'Field note NEEDLE-58-MARSH: the drainage blueprint for the east marsh was revised twice in June.'),
    ('NEEDLE-94-LANTERN', 'Field note NEEDLE-94-LANTERN: the lantern oil ration for the winter watch was cut by one fifth.'),
    ('NEEDLE-12-COMET',   'Field note NEEDLE-12-COMET: the comet sighting log from the ridge station was filed under weather.'),
    ('NEEDLE-37-IVORY',   'Field note NEEDLE-37-IVORY: the ivory tag inventory was reconciled against the freight manifest.'),
]

X_UNIT = ('The greenhouse ledger records weekly readings for each orchid bench: temperature, humidity, '
          'misting schedule, and the delivery dates of bark substrate. The keeper files every sheet in the '
          'chronological binder and cross-references the yearly summary before the board review. ')
Y_UNIT = ('The coastal station publishes tide tables for the harbour channel: spring ranges, neap ranges, '
          'sandbar soundings, and the dredging windows granted to the work barges. The pilot office files '
          'each bulletin in the chart room and reconciles the almanac before the season opens. ')

TOPIC_Q = 'In one sentence, what is the main topic of this material?'
NEEDLE_Q = ('The material above hides several field notes whose codes look like NEEDLE-12-MAPLE. '
            'List every field-note code that appears in the material, one per line. '
            'Output only the codes, nothing else.')
DECOY_CODE = 'NEEDLE-12-MAPLE'              # appears only in the question; echoing it = hallucination marker


def build_material(unit, tag, needles=()):
    body = '[' + tag + '] ' + unit * (int(TARGET_TOKENS * CHARS_PER_TOKEN / len(unit)) + 1)
    text = body
    spans = []
    for frac, (code, sentence) in zip(NEEDLE_FRACTIONS, needles):
        pos = int(len(text) * frac)
        text = text[:pos] + ' ' + sentence + text[pos:]
        spans.append({'code': code, 'char_pos': pos,
                      'est_token': int(pos / CHARS_PER_TOKEN),
                      'est_block64': int(pos / CHARS_PER_TOKEN / 64)})
    return text, spans


def one_request(port, prompt, max_tokens, timeout=900):
    body = json.dumps({
        'model': _model_id(),
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens,
        'temperature': 0, 'top_p': 1.0, 'top_k': 1,
        'stream': False,
        'chat_template_kwargs': {'enable_thinking': False},
    }).encode('utf-8')
    req = urllib.request.Request(BASE % port + '/v1/chat/completions', data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8', 'replace'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True)
    ap.add_argument('--port', type=int, default=8094)
    args = ap.parse_args()
    out_dir = r'J:\ninfer-kvmem\work\data'
    os.makedirs(out_dir, exist_ok=True)

    X, spans = build_material(X_UNIT, 'X', NEEDLES)
    Y, _ = build_material(Y_UNIT, 'Y')
    plan = [('A_fill', X, TOPIC_Q, 120),
            ('B_evict', Y, TOPIC_Q, 120),
            ('C_recall', X, NEEDLE_Q, 300)]

    records = []
    for name, mat, q, mt in plan:
        t0 = time.time()
        try:
            payload = one_request(args.port, mat + '\n\n' + q, mt)
            choice = (payload.get('choices') or [{}])[0]
            content = ((choice.get('message') or {}).get('content')) or ''
            finish = choice.get('finish_reason')
            error = ''
        except Exception as exc:                      # noqa: BLE001
            payload, content, finish, error = {}, '', '', repr(exc)
        elapsed = time.time() - t0
        usage = payload.get('usage') or {}
        records.append({'req': name, 'elapsed_s': round(elapsed, 2),
                        'prompt_tokens': usage.get('prompt_tokens'),
                        'completion_tokens': usage.get('completion_tokens'),
                        'finish_reason': finish, 'error': error, 'content': content})
        print('%s %s %.1fs in=%s out=%s finish=%s%s' % (
            args.arm, name, elapsed, usage.get('prompt_tokens'),
            usage.get('completion_tokens'), finish or '-',
            (' ERR=' + error[:80]) if error else ''))

    answer = records[-1]['content'] or ''
    hits = [code for code, _ in NEEDLES if code in answer]
    missed = [code for code, _ in NEEDLES if code not in answer]
    summary = {'arm': args.arm,
               'hits': hits, 'missed': missed, 'hits_n': len(hits),
               'decoy_echoed': DECOY_CODE in answer,
               'needles': [{'code': c, 'sentence': s} for c, s in NEEDLES],
               'needle_spans_in_X': spans,
               'prompt_X_chars': len(X), 'prompt_Y_chars': len(Y)}
    out_path = os.path.join(out_dir, 'needle_%s.json' % args.arm)
    with io.open(out_path, 'w', encoding='utf-8') as fh:
        json.dump({'summary': summary, 'records': records}, fh, ensure_ascii=False, indent=1)
    print('NEEDLEJUDGE arm=%s hits=%d/6 missed=%s decoy_echoed=%s'
          % (args.arm, len(hits), ','.join(missed) if missed else '-', summary['decoy_echoed']))
    print('written: %s' % out_path)


if __name__ == '__main__':
    main()
