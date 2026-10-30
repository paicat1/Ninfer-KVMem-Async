# -*- coding: utf-8 -*-
"""2026-10-30 物理层 §2.2 B 组：编译输出 .temp\build-* → build-out\build-* 改道。"""
import io
import re
import sys

ROOT = r'J:\ninfer-kvmem'
FILES = ['build/README.md', 'build/_inc54v2.bat', 'build/_rebuild_54_20261013.bat',
         'build/designc_build_frontend.ps1', 'build/designc_build_test.ps1',
         'build/designc_build_tests.ps1', 'build/designc_rebuild_serve.ps1',
         'build/s6_1208a.bat', 'build/s6_1208a_test.ps1', 'build/s6_build.bat',
         'build/s6_build_runtime.bat', 'build/s6_configure.bat',
         'build/s6_k0_full.ps1', 'build/s6_k0_scan.ps1']

PAT = re.compile(r'\.temp([\\/]+)(?=build[-_])')

for f in FILES:
    p = ROOT + '\\' + f.replace('/', '\\')
    t = io.open(p, 'rb').read().decode('utf-8')
    t2, n = PAT.subn(lambda m: 'build-out' + m.group(1), t)
    if n == 0:
        print('SKIP(0 命中): %s' % f)
        continue
    io.open(p, 'wb').write(t2.encode('utf-8'))
    print('OK: %s (x%d)' % (f, n))
print('B 组改道完成')
