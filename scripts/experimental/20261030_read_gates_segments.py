# -*- coding: utf-8 -*-
import io

t = io.open(r'J:\ninfer-kvmem\scripts\gates.ps1', 'rb').read().decode('utf-8')
lines = t.split('\n')
for i in range(413, 505):
    s = lines[i].rstrip()
    if s.strip():
        print(i + 1, s.strip()[:140])
