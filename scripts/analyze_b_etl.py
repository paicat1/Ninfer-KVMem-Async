# -*- coding: utf-8 -*-
"""分析 4.2 GB etl：① 先看 etl 元信息（时间范围/事件数）② 按谷期窗口 dump CSwitch ③ 找引擎线程等待
   铁律B：先估体积，超预期即 5 秒轮询"""
import io
import os
import subprocess
import time

R = r'J:\ninfer-kvmem'
D = os.path.join(R, 'work', '20261018')
ETL = os.path.join(D, 'valley_etl.etl')
WPT = r'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit'


def ps(cmd, timeout=180):
    r = subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, timeout=timeout)
    return ((r.stdout or b'').decode('utf-8', 'replace') + (r.stderr or b'').decode('utf-8', 'replace')).strip()


print('== ① etl 元信息（tracestats）==')
o = ps("& '" + os.path.join(WPT, 'xperf.exe') + "' -i '" + ETL + "' -a tracestats 2>&1 | Select-Object -First 30")
for l in o.splitlines()[:22]:
    print('   ' + l.strip()[:130])

print('\n== ② 尝试按谷期窗口 dump CSwitch（只出 CSwitch，不含栈，体积可控）==')
# 谷期：抓取 07:49:46 起，谷在 07:50:00–07:52:46
# xperf -range 需绝对时间；先用 -a dumper -cswitch 全量试，并监控体积
out = os.path.join(D, 'cswitch.csv')
if os.path.exists(out):
    os.remove(out)
cmd = ("Start-Process -FilePath '" + os.path.join(WPT, 'xperf.exe') + "' "
       "-ArgumentList '-i','" + ETL + "','-a','dumper','-cswitch','-o','" + out + "' -NoNewWindow -PassThru | "
       "ForEach-Object { 'started pid=' + $_.Id }")
print('   ' + ps(cmd)[:120])

print('\n== ③ 铁律B：先等 20 s，然后 5 秒轮询体积 ==')
time.sleep(20)
prev = 0
for i in range(60):
    sz = os.path.getsize(out) / 1048576 if os.path.exists(out) else 0
    proc = ps("@(Get-Process xperf -ErrorAction SilentlyContinue).Count").strip()
    print('   +%3ds %8.1f MiB (Δ%+7.1f) · xperf=%s' % (20 + i * 5, sz, sz - prev, proc))
    if proc == '0' and sz > 0:
        print('   ⇒ dump 完成')
        break
    if sz > 8000:
        print('   ⚠ 超 8 GB ⇒ 中止（防膨胀）')
        ps("Get-Process xperf -ErrorAction SilentlyContinue | Stop-Process -Force")
        break
    prev = sz
    time.sleep(5)
