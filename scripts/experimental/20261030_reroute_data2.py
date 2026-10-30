# -*- coding: utf-8 -*-
"""2026-10-30 物理层 §2.2 A 组改道 v2：正则保分隔符（兼容 1/2 层反斜杠与正斜杠）。"""
import io
import py_compile
import re
import sys

ROOT = r'J:\ninfer-kvmem'
FILES = ['ninfer_launcher.py', r'scripts\ab_interleave.ps1', r'scripts\async_abab.ps1',
         r'scripts\deeppool_async_onoff.ps1', r'scripts\valley_watch.ps1',
         r'scripts\valley_induce.ps1', r'scripts\gpu_sampler.py', r'scripts\a2gate.py',
         r'scripts\experiments\round2b_15k.py']

# 白名单前缀：只有这些输出物改道（其余 .temp 引用不动）
PREFIX = r'(?:watch_dmon|state_journal|induce_|abab_text|gate_|gpu_samples|reqlog_)'
PAT = re.compile(r'\.temp([\\/]+)(?=' + PREFIX + ')')

EXACT = [
    ('ninfer_launcher.py',
     'os.path.join(".temp", "reqlog_serve_%s.jsonl" % port)',
     'os.path.join("work", "data", "reqlog_serve_%s.jsonl" % port)', 1),
    ('scripts\\gpu_sampler.py',
     "os.path.join(ROOT, '.temp', 'gpu_samples.csv')",
     "os.path.join(ROOT, 'work', 'data', 'gpu_samples.csv')", 1),
    ('scripts\\experiments\\round2b_15k.py',
     "os.path.join(R, '.temp', 'reqlog_*.jsonl')",
     "os.path.join(R, 'work', 'data', 'reqlog_*.jsonl')", 1),
]

texts = {f: io.open(ROOT + '\\' + f, 'rb').read().decode('utf-8') for f in FILES}

# 先精确替换（os.path.join 形态）
for f, old, new, expect in EXACT:
    n = texts[f].count(old)
    if n != expect:
        print('MISS(exact): %s | %r x%d (期望 %d)' % (f, old[:50], n, expect))
        sys.exit(1)
    texts[f] = texts[f].replace(old, new)
    print('OK(exact): %s (x%d)' % (f, expect))

# 再正则改道（保分隔符）
total = 0
for f in FILES:
    texts[f], n = PAT.subn(lambda m: 'work' + m.group(1) + 'data' + m.group(1), texts[f])
    print('OK(regex): %s (x%d)' % (f, n))
    total += n
if total == 0:
    print('正则零命中——白名单或模式有误')
    sys.exit(1)

for f in FILES:
    io.open(ROOT + '\\' + f, 'wb').write(texts[f].encode('utf-8'))

for f in ('ninfer_launcher.py', 'scripts\\gpu_sampler.py', 'scripts\\a2gate.py',
          'scripts\\experiments\\round2b_15k.py'):
    py_compile.compile(ROOT + '\\' + f, doraise=True)
    print('py_compile PASS:', f)
print('A 组改道完成')
