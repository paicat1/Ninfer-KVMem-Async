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
INTERVAL = 20        # 日志读取节奏 20 s（GPU 环缓冲 5 s 一跳；见主循环）——深档事件约 4 分钟，60 s 太粗
MAX_HOURS = float(os.environ.get('LOGWATCH_HOURS', '12'))

RE_TP = re.compile(r'(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+.*?throughput \| [\d.]+s \| .*decode '
                      r'(?P<d>[\d.]+) tok/s \((?P<n>\d+) tok\).*running (?P<r>\d+)')


def say(msg):
    line = '%s | %s' % (time.strftime('%H:%M:%S'), msg)
    try:
        with io.open(LEDGER, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


GPUHIST = []          # v2：GPU 环形缓冲（每 10s 采一次），供"按慢读数时刻就近配对"


def gpu_sample():
    try:
        out = subprocess.run(['nvidia-smi', '--query-gpu=clocks.sm,utilization.gpu,power.draw,memory.used',
                              '--format=csv,noheader'], capture_output=True, timeout=20).stdout.decode()
        vals = [x.strip() for x in out.strip().replace('\r\n', '\n').split('\n')[0].split(',')]
        return {'t': time.time(), 'clk': vals[0], 'util': vals[1], 'pow': vals[2], 'mem': vals[3]}
    except Exception:
        return None


def gpu_nearest(ts, tol=25.0):
    """按日志行时间戳就近取 GPU 采样（±25s），避免"采样落在间隙"造成的错配。"""
    if not GPUHIST:
        return None
    best = min(GPUHIST, key=lambda g: abs(g['t'] - ts))
    return best if abs(best['t'] - ts) <= tol else None


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
        # TELE 第十六轮：与猎人案卷对齐 —— 补引擎日志尾 / reqlog 尾 / 我方活动时间线
        try:
            tail = io.open(LOG, 'r', encoding='utf-8', errors='replace').read().splitlines()[-300:]
            with io.open(os.path.join(d, 'engine_log_tail.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(tail))
        except Exception:
            pass
        try:
            rl = os.path.join(ROOT, '.temp', 'reqlog_serve_8094.jsonl')
            if os.path.exists(rl):
                tail = io.open(rl, 'r', encoding='utf-8', errors='replace').read().splitlines()[-200:]
                with io.open(os.path.join(d, 'reqlog_tail.txt'), 'w', encoding='utf-8') as f:
                    f.write('\n'.join(tail))
        except Exception:
            pass
        try:
            git = subprocess.run(['git', 'log', '-8', '--date=format:%H:%M', '--pretty=%h %ad %s'],
                                 cwd=ROOT, capture_output=True, timeout=30).stdout.decode('utf-8', 'replace')
            with io.open(os.path.join(d, 'self_activity_commits.txt'), 'w', encoding='utf-8') as f:
                f.write(git)
            procs = subprocess.run(['powershell', '-NoProfile', '-Command',
                                    "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ninfer*' -or $_.CommandLine -like '*valley*' } | ForEach-Object { $_.ProcessId.ToString() + ' | ' + $_.Name + ' | ' + $_.CommandLine.Substring(0,[Math]::Min(110,$_.CommandLine.Length)) }"],
                                   capture_output=True, timeout=40).stdout.decode('utf-8', 'replace')
            with io.open(os.path.join(d, 'self_activity_procs.txt'), 'w', encoding='utf-8') as f:
                f.write(procs)
        except Exception:
            pass
    except Exception as e:
        say('WARN: case dir write failed: %s' % e)
    try:
        import json
        with io.open(LOCK, 'w', encoding='utf-8') as f:
            json.dump({'case': tag, 'time': time.strftime('%m-%d %H:%M:%S'),
                       'prohibit': ['NO restart', 'NO config change', 'NO pressure injection', 'NO cache clear'],
                       'release_by': 'user only', 'dir': os.path.relpath(d, ROOT), 'channel': 'logwatch'},
                      f, ensure_ascii=False, indent=2)
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
    hist = []          # 只存 (ts, value) 的**有效读数**；None 不入窗口（TELE 第十五轮：原写法把窗口占满 ⇒ 永不触发）
    t0 = time.time()
    tick = 0
    while (time.time() - t0) / 3600.0 < MAX_HOURS:
        time.sleep(5)      # 5 s 一跳：GPU 环缓冲加密 ⇒ 配对精度 ±5 s
        tick += 1
        g = gpu_sample()
        if g:
            GPUHIST.append(g)
            del GPUHIST[:-80]          # 近 80 个（约 6-7 分钟）
        if tick % 4:                   # 每 20 s 读一次日志
            continue
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
        slow_lines = []
        for m in RE_TP.finditer(new):
            try:
                d = float(m.group('d'))
                r = int(m.group('r'))
            except Exception:
                continue
            if r >= 1:
                vals.append(d)
                if d < 60:
                    try:
                        ts = time.mktime(time.strptime(m.group('ts'), '%Y-%m-%d %H:%M:%S')) - 2.5
                    except Exception:
                        ts = time.time()
                    slow_lines.append((d, ts, m.group(0)[:120]))
        if not vals:
            # 无在飞请求 ⇒ 既不算谷也不算健康；**不写入窗口**（原写法 append(None) 会把窗口占满 ⇒ 永不触发）
            continue
        mn = min(vals)
        tier = 'vdeep' if mn < 1.5 else ('deep' if mn < 6 else ('valley' if mn < 60 else 'ok'))
        ref_ts = min(slow_lines, key=lambda x: x[0])[1] if slow_lines else time.time()
        gg = gpu_nearest(ref_ts, tol=20.0)
        gtxt = ('clk=%s util=%s pow=%s mem=%s' % (gg['clk'], gg['util'], gg['pow'], gg['mem'])) if gg else 'gpu=no-match'
        say('decode_min=%.1f tok/s (%s) | n=%d | %s' % (mn, tier, len(vals), gtxt))
        if slow_lines:
            say('   slow lines: ' + ' ;; '.join('%.1f@%s' % (a, time.strftime('%H:%M:%S', time.localtime(b))) for a, b, _c in slow_lines[:3]))
        now_ts = time.time()
        hist.append((now_ts, mn))
        hist = [(t, v) for (t, v) in hist if now_ts - t <= 300.0]   # 只留近 5 分钟（时间连续性）
        recent = [v for (_t, v) in hist]
        hits = sum(1 for v in recent if v < 60)
        if len(recent) >= 3 and hits >= 2:
            tag = 'case_%s_logwatch' % time.strftime('%Y%m%d_%H%M%S')
            d = freeze_lock(tag, new.splitlines()[-200:])
            say('VALLEY CONFIRMED (log channel) -> %s | tier=%s | recent=%s | scene frozen' % (tag, tier, ['%.1f' % v for v in recent]))
            hist = []
    say('logwatch stop (max hours reached)')


if __name__ == '__main__':
    main()
