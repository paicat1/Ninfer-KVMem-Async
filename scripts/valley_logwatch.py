# -*- coding: utf-8 -*-
"""valley_logwatch.py -- 死亡谷**日志通道**检测器（2026-10-17 09:0x，CB）

为什么需要它：猎人（valley_hunter.ps1）只看**它自己那根 200-token 轻探针**；
而深谷发生在**用户的真实请求**里 —— 猎人对那些请求完全失明（本夜实测：日志里 decode 0.2~10 tok/s、
running=1/waiting=1，猎人却一发未立）。本脚本补上这个通道。

- **只读**：解析引擎日志新增行 + nvidia-smi 采样；**不发请求、不注入压力、不改配置、不重启**。
- **口径**：`throughput | 5.0s | ... decode X tok/s (N tok) | running R` 且 **R>=1**（有请求在飞）
  ⇒ X<60 = 谷档 / X<6 = 深档 / X<1.5 = 极深档（本项目分档：谷 6-14、深 ~1.5）。
  ⚠ 5.0s 窗对**短请求**会稀释 ⇒ 只在 running>=1（请求在飞）时才采信。
- **立案**：连续 3 次采样中至少 2 次过线 ⇒ 落案卷 + 冻结锁 + 队列置顶行。
"""
import io
import os
import re
import subprocess
import sys
import time

ROOT = r'J:\ninfer-kvmem'
LOG = os.path.join(ROOT, 'logs', 'test_valleywatch.log')
CASEDIR = os.path.join(ROOT, '.temp', 'cases')
LEDGER = os.path.join(CASEDIR, 'logwatch_ledger.txt')
LOCK = os.path.join(CASEDIR, 'CASE_LOCKED.json')
QUEUE = os.path.join(ROOT, 'docs', '协作状态-当前待办与交接-20261016.md')
INTERVAL = 60
MAX_HOURS = float(os.environ.get('LOGWATCH_HOURS', '12'))

RE_TP = re.compile(r'throughput \| [\d.]+s \| .*decode (?P<d>[\d.]+) tok/s \((?P<n>\d+) tok\).*running (?P<r>\d+)')


def say(msg):
    line = '%s | %s' % (time.strftime('%H:%M:%S'), msg)
    try:
        with io.open(LEDGER, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


def snap_gpu():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=clocks.sm,utilization.gpu,power.draw,memory.used',
                              '--format=csv,noheader'], capture_output=True, timeout=20).stdout.decode()
        return out.strip().replace('\r\n', ' | ')
    except Exception as e:
        return 'gpu-query-failed: %s' % e


def freeze_lock(tag, excerpt):
    """立案即冻结：写 CASE_LOCKED.json + 队列置顶行（与猎人同规格）。"""
    d = os.path.join(CASEDIR, tag)
    try:
        os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(d, 'log_excerpt.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(excerpt))
        q = subprocess.run(['nvidia-smi', '-q'], capture_output=True, timeout=40).stdout.decode('utf-8', 'replace')
        with io.open(os.path.join(d, 'nvidia_smi_q.txt'), 'w', encoding='utf-8') as f:
            f.write(q)
    except Exception as e:
        say('WARN: case dir write failed: %s' % e)
    try:
        import json
        with io.open(LOCK, 'w', encoding='utf-8') as f:
            json.dump({'case': tag, 'time': time.strftime('%m-%d %H:%M:%S'),
                       'prohibit': ['NO restart', 'NO config change', 'NO pressure injection', 'NO cache clear'],
                       'release_by': 'user only', 'dir': d, 'channel': 'logwatch'}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        say('WARN: CASE_LOCKED.json write failed: %s' % e)
    try:
        with io.open(QUEUE, 'a', encoding='utf-8') as f:
            f.write('\n> CASE-LOCKED: %s @ %s -- NO restart / NO config change / NO pressure / NO cache clear; '
                    'release_by=user only (channel=logwatch)\n' % (tag, time.strftime('%m-%d %H:%M:%S')))
    except Exception:
        pass
    return d


def main():
    say('logwatch start | criteria: decode<60 (running>=1) | tiers: <60 valley / <6 deep / <1.5 vdeep | '
        '3 samples with >=2 hits | NO pressure, NO restart, NO config change')
    try:
        off = os.path.getsize(LOG)
    except Exception:
        off = 0
    hist = []
    t0 = time.time()
    while (time.time() - t0) / 3600.0 < MAX_HOURS:
        time.sleep(INTERVAL)
        try:
            sz = os.path.getsize(LOG)
            if sz < off:
                off = 0
            with io.open(LOG, 'r', encoding='utf-8', errors='replace') as f:
                f.seek(off)
                new = f.read()
            off = sz
        except Exception as e:
            say('WARN: log read failed: %s' % e)
            continue
        vals = []
        for m in RE_TP.finditer(new):
            try:
                d = float(m.group('d'))
                r = int(m.group('r'))
            except Exception:
                continue
            if r >= 1:
                vals.append(d)
        if not vals:
            hist.append(None)
            hist = hist[-3:]
            continue
        mn = min(vals)
        tier = 'vdeep' if mn < 1.5 else ('deep' if mn < 6 else ('valley' if mn < 60 else 'ok'))
        say('decode_min=%.1f tok/s (%s) | n_samples=%d | gpu=%s' % (mn, tier, len(vals), snap_gpu()))
        hist.append(mn)
        hist = hist[-3:]
        recent = [h for h in hist if h is not None]
        hits = sum(1 for h in recent if h < 60)
        if len(recent) >= 3 and hits >= 2:
            tag = 'case_%s_logwatch' % time.strftime('%Y%m%d_%H%M%S')
            d = freeze_lock(tag, new.splitlines()[-200:])
            say('VALLEY CONFIRMED (log channel) -> %s | tier=%s | recent=%s | scene frozen' % (tag, tier, recent))
            hist = []
    say('logwatch stop (max hours reached)')


if __name__ == '__main__':
    main()
