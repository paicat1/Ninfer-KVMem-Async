# -*- coding: utf-8 -*-
import io

P = r'J:\ninfer-kvmem\scripts\gates.ps1'
t = io.open(P, 'rb').read().decode('utf-8')
lines = t.split('\n')
out = [l for l in lines
       if '[T]' not in l and "$__gT = '" not in l and '$__gsw' not in l]
removed = len(lines) - len(out)
io.open(P, 'wb').write('\n'.join(out).encode('utf-8'))
print('拆除插桩 %d 行' % removed)
