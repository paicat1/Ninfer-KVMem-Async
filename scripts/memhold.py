# -*- coding: utf-8 -*-
"""内存压力施加器（剂量-响应用）：吃住 N GiB 并逐页触碰（真正占物理页），保持 T 秒后释放。
用法：python memhold.py <GiB> <seconds>
"""
import ctypes
import mmap
import sys
import time

gib = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
n = int(gib * (1 << 30))
print('allocating %.1f GiB and touching every page ...' % gib, flush=True)
buf = mmap.mmap(-1, n)          # 匿名映射
step = 4096
t0 = time.time()
for off in range(0, n, step):
    buf[off] = 1                # 逐页触碰 ⇒ 真正驻留物理页
print('resident in %.1fs, holding %.0fs ...' % (time.time() - t0, secs), flush=True)
time.sleep(secs)
print('releasing', flush=True)
buf.close()
print('released', flush=True)
