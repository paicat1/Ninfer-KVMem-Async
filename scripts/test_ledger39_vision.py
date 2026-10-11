# -*- coding: utf-8 -*-
# Ledger-39 retest: new engine (W1-W4, g3b9dc83-dirty) + NO growth + real image request.
# PASS criterion: HTTP 200 + non-empty answer. FAIL: scatter assertion / HTTP 500.
import base64, json, sys, urllib.request
from pathlib import Path

# 1) make a deterministic test image (gradient + concentric rings, PNG)
import struct, zlib
W, H = 640, 360
rows = b''
for y in range(H):
    row = b'\x00'
    for x in range(W):
        r = (x * 255) // W
        g = (y * 255) // H
        b = 128
        d = ((x - W//2)**2 + (y - H//2)**2) ** 0.5
        if int(d) % 40 < 8:
            r = g = b = 255 - (int(d)//40 % 2) * 200
        row += bytes((r, g, b))
    rows += row

def chunk(tag, data):
    c = struct.pack('>I', len(data)) + tag + data
    return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)

png = (b'\x89PNG\r\n\x1a\n'
       + chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0))
       + chunk(b'IDAT', zlib.compress(rows, 6))
       + chunk(b'IEND', b''))
out = Path(__file__).parent / '_ledger39_test_image.png'
out.write_bytes(png)
b64 = base64.b64encode(png).decode()
print('[prep] image %dx%d -> %s (%d B, b64 %d chars)' % (W, H, out.name, len(png), len(b64)))

# 2) vision request against the running engine (8094)
body = json.dumps({
    'model': 'qwen3.8-27b-coder390',
    'stream': False,
    'max_tokens': 300,
    'messages': [{
        'role': 'user',
        'content': [
            {'type': 'text', 'text': '用一句话描述这张图片。'},
            {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64}},
        ],
    }],
}).encode()
req = urllib.request.Request('http://127.0.0.1:8094/v1/chat/completions',
                             data=body, headers={'Content-Type': 'application/json'})
try:
    resp = json.loads(urllib.request.urlopen(req, timeout=600).read())
    ch = resp['choices'][0]
    txt = (ch['message'].get('content') or '')
    print('[RESULT] HTTP 200 | finish=%s | content[0:160]=%r' % (ch.get('finish_reason'), txt[:160]))
    print('[VERDICT] PASS (no scatter, request succeeded)')
except urllib.error.HTTPError as e:
    print('[RESULT] HTTP %d | body[0:300]=%r' % (e.code, e.read()[:300]))
    print('[VERDICT] FAIL (scatter/500 family)')
