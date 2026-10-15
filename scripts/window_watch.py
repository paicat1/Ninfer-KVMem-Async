# -*- coding: utf-8 -*-
"""window_watch.py -- 跨天"窗口 Watch"（本线增量，来自 E5/E6/E2 三条发现）
   每分钟记一行：主机态（uptime/CPU/内存/页文件/后台Top3/GPU 时钟功耗）+ 引擎态（最后 verify 毫秒、
   最后 decode、S13 台账最新循环号）。只读、不碰引擎 ⇒ 可与 S13 并行跑，跨天连续。
   目的：把"活跃窗口"从推测变成可见——门什么时候开、开多久、和什么同现。"""
import io
import json
import os
import re
import subprocess
import time

ROOT = r'J:\ninfer-kvmem'
LOG = os.path.join(ROOT, 'logs', 'test_valleywatch.log')
S13 = None  # 动态找最新 s13_*.txt
OUT = os.path.join(ROOT, '.temp', 'windowwatch_%s.txt' % time.strftime('%Y%m%d_%H%M'))
HOURS = float(os.environ.get('WATCH_HOURS', '12'))
INTERVAL = float(os.environ.get('WATCH_INTERVAL', '60'))


def sh(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=25)
        return (r.stdout or '').strip()
    except Exception:
        return ''


def host_state():
    ps = ("$o=Get-CimInstance Win32_OperatingSystem;$p=Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue;"
          "$up=[math]::Round(((Get-Date)-$o.LastBootUpTime).TotalHours,1);"
          "$free=[math]::Round($o.FreePhysicalMemory/1MB,0);"
          "$pf=if($p){[math]::Round($p.CurrentUsage/1MB,0)}else{-1};"
          "$top=(Get-Process | Sort-Object CPU -Descending | Select-Object -First 3 | ForEach-Object { $_.Name }) -join '/';"
          "$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
          "Write-Output ($up.ToString()+'|'+$cpu.ToString()+'|'+$free.ToString()+'|'+$pf.ToString()+'|'+$top)")
    return sh('powershell -NoProfile -Command "' + ps.replace('"', "'") + '"')


def gpu_state():
    return sh('nvidia-smi --query-gpu=clocks.sm,power.draw,utilization.gpu,memory.used --format=csv,noheader,nounits')


def engine_state():
    if not os.path.exists(LOG):
        return '-1|-1|0'
    try:
        lines = io.open(LOG, encoding='utf-8', errors='replace').readlines()[-4000:]
    except Exception:
        return '-1|-1|0'
    ver = '-1'
    for l in reversed(lines):
        m = re.search(r'verify=([\d.]+)', l)
        if m and 'target-split' in l:
            ver = m.group(1)
            break
    dec = '-1'
    for l in reversed(lines):
        m = re.search(r'throughput \| [\d.]+s \| (?:prefill [\d.]+ tok/s \([\d,]+ tok\) \| )?decode ([\d.]+) tok/s', l)
        if m:
            dec = m.group(1)
            break
    stamps = sum(1 for l in lines if 'target-split' in l)
    return '%s|%s|%d' % (ver, dec, stamps)


def s13_state():
    d = os.path.join(ROOT, '.temp')
    fs = [f for f in os.listdir(d) if f.startswith('s13_') and f.endswith('.txt')]
    if not fs:
        return '-'
    p = os.path.join(d, sorted(fs)[-1])
    try:
        tail = io.open(p, encoding='utf-8', errors='replace').readlines()[-1].strip()
    except Exception:
        return '-'
    m = re.search(r'cy(\d+)', tail)
    v = 'VALLEY' if 'VALLEY' in tail else 'ok'
    return 'cy%s:%s' % (m.group(1) if m else '?', v)


def main():
    end = time.time() + HOURS * 3600
    io.open(OUT, 'w', encoding='utf-8').write(
        '# window watch (host x engine state timeline) -- %s\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    n = 0
    while time.time() < end:
        n += 1
        h = host_state().split('|')
        g = gpu_state().replace(' ', '')
        e = engine_state().split('|')
        s13 = s13_state()
        line = '%s | up=%sh cpu=%s%% freemem=%sMiB pf=%sMiB top=%s | gpu=%s | verify=%sms decode=%s stamps=%s | s13=%s' % (
            time.strftime('%m-%d %H:%M:%S'),
            h[0] if len(h) > 0 else '?', h[1] if len(h) > 1 else '?', h[2] if len(h) > 2 else '?',
            h[3] if len(h) > 3 else '?', (h[4] if len(h) > 4 else '?')[:60],
            g, e[0], e[1], e[2], s13)
        with io.open(OUT, 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
        if n % 10 == 0:
            print(line)
        time.sleep(INTERVAL)
    print('window watch done -> %s (%d samples)' % (OUT, n))


if __name__ == '__main__':
    main()
