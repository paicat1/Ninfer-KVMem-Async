# -*- coding: utf-8 -*-
# Stream-stall (reader-stops-reading) reproduction probe.
# Opens a streaming request, reads a few chunks, then STOPS reading WITHOUT closing.
# Expected: engine decode hangs (CPU 0, log silence) while socket stays Established.
# Then closes the socket -> engine should cancel the request and recover.
import json
import socket
import sys
import time

HOST, PORT = '127.0.0.1', 8094
BODY = json.dumps({
    'model': 'qwen3.8-27b-coder390', 'stream': True, 'max_tokens': 4000,
    'messages': [{'role': 'user', 'content': 'Write a very long story about a lighthouse, at least 3000 words.'}],
}).encode()
REQ = (b'POST /v1/chat/completions HTTP/1.1\r\nHost: ' + HOST.encode() +
       b':%d\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n' % (PORT, len(BODY)) + BODY)

s = socket.create_connection((HOST, PORT), timeout=10)
s.sendall(REQ)
s.settimeout(5)
got = 0
try:
    for _ in range(20):
        chunk = s.recv(65536)
        if not chunk:
            break
        got += len(chunk)
except socket.timeout:
    pass
print('[probe] read %d bytes of stream, now STOP reading (socket stays open)...' % got)
t0 = time.time()
time.sleep(75)  # engine should hang during this window if bug present
print('[probe] 75s elapsed. closing socket now (RST/FIN) -> engine should cancel & recover.')
s.close()
print('[probe] done. check engine log/CPU for: hang during window, recovery after close.')
