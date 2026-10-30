# -*- coding: utf-8 -*-
"""2026-10-30 物理层 §2.2 A 组：运行数据 .temp → work\data 改道。
字节级替换（保 BOM/行尾）；每条断言命中数，漏改即报错。
"""
import io
import py_compile
import sys

ROOT = r'J:\ninfer-kvmem'

# (相对路径, 旧串, 新串, 期望命中数)
EDITS = [
    # 1. launcher：reqlog 默认路径 + 描述文字
    ('ninfer_launcher.py',
     r'os.path.join(".temp", "reqlog_serve_%s.jsonl" % port)',
     r'os.path.join("work", "data", "reqlog_serve_%s.jsonl" % port)', 1),
    ('ninfer_launcher.py',
     r'写 .temp\\reqlog_serve_<端口>.jsonl',
     r'写 work\\data\\reqlog_serve_<端口>.jsonl', 1),
    ('ninfer_launcher.py',
     r'写 .temp\reqlog_serve_<端口>.jsonl',
     r'写 work\data\reqlog_serve_<端口>.jsonl', 1),
    ('ninfer_launcher.py',
     r'逐窗落 .temp\\reqlog_serve_<端口>.jsonl',
     r'逐窗落 work\\data\\reqlog_serve_<端口>.jsonl', 1),
    # 2. 实验脚本 --request-log-jsonl 指向
    (r'scripts\ab_interleave.ps1',
     r'.temp\reqlog_watch.jsonl', r'work\data\reqlog_watch.jsonl', 1),
    (r'scripts\async_abab.ps1',
     r'--request-log-jsonl,.temp\reqlog_',
     r'--request-log-jsonl,work\data\reqlog_', 1),
    (r'scripts\deeppool_async_onoff.ps1',
     r'--request-log-jsonl,.temp\reqlog_',
     r'--request-log-jsonl,work\data\reqlog_', 2),
    # 3. 守望者 dmon 输出
    (r'scripts\valley_watch.ps1',
     r'J:\\ninfer-kvmem\\.temp\\watch_dmon_',
     r'J:\\ninfer-kvmem\\work\\data\\watch_dmon_', 1),
    (r'scripts\valley_watch.ps1',
     r'J:\\ninfer-kvmem\\.temp\\watch_dmon.txt',
     r'J:\\ninfer-kvmem\\work\\data\\watch_dmon.txt', 1),
    # 4. valley_induce 台账与 journal
    (r'scripts\valley_induce.ps1',
     r"'.temp\\state_journal.txt'", r"'work\\data\\state_journal.txt'", 1),
    (r'scripts\valley_induce.ps1',
     r"'.temp\\induce_'", r"'work\\data\\induce_'", 1),
    (r'scripts\valley_induce.ps1',
     r'.temp\\induce_<日期>.txt', r'work\\data\\induce_<日期>.txt', 1),
    # 5. gpu_sampler 输出
    (r'scripts\gpu_sampler.py',
     r"os.path.join(ROOT, '.temp', 'gpu_samples.csv')",
     r"os.path.join(ROOT, 'work', 'data', 'gpu_samples.csv')", 1),
    (r'scripts\gpu_sampler.py',
     r'.temp\\gpu_samples.csv', r'work\\data\\gpu_samples.csv', 1),
    # 6. a2gate 全文落盘 + gate json
    (r'scripts\a2gate.py',
     r'J:\\ninfer-kvmem\\.temp\\abab_text_',
     r'J:\\ninfer-kvmem\\work\\data\\abab_text_', 1),
    (r'scripts\a2gate.py',
     r'J:\\ninfer-kvmem\\.temp\\gate_%s.json',
     r'J:\\ninfer-kvmem\\work\\data\\gate_%s.json', 1),
    # 7. 读取方跟进（round2b 读最新 reqlog）
    (r'scripts\experiments\round2b_15k.py',
     r"os.path.join(R, '.temp', 'reqlog_*.jsonl')",
     r"os.path.join(R, 'work', 'data', 'reqlog_*.jsonl')", 1),
]

PY_FILES = {'ninfer_launcher.py', 'scripts\\gpu_sampler.py', 'scripts\\a2gate.py',
            'scripts\\experiments\\round2b_15k.py'}

cache = {}
for rel, old, new, expect in EDITS:
    p = ROOT + '\\' + rel
    if p not in cache:
        cache[p] = io.open(p, 'rb').read().decode('utf-8')
    n = cache[p].count(old)
    if n != expect:
        print('MISS: %s | %r 命中 %d（期望 %d）' % (rel, old[:60], n, expect))
        sys.exit(1)
    cache[p] = cache[p].replace(old, new)
    print('OK: %s | %s -> %s (x%d)' % (rel, old[:44], new[:44], expect))

for p, txt in cache.items():
    io.open(p, 'wb').write(txt.encode('utf-8'))

for rel in sorted(PY_FILES):
    py_compile.compile(ROOT + '\\' + rel, doraise=True)
    print('py_compile PASS:', rel)
print('A 组改道全部完成')
