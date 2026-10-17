# -*- coding: utf-8 -*-
r"""count_watch.py -- 值守进程计数（**带正确过滤，避免"监视命令自匹配"陷阱**）

由来：CB 多次用 `Get-CimInstance ... -like '*xxx*'` 统计进程数，**把执行该查询的 powershell 自身也数进去** ⇒ 误报"重复实例"。
本工具把过滤写死：① 只数目标解释器（python/pwsh）② 排除命令行里含 Get-CimInstance/Where-Object 的查询进程 ③ 判存活**以台账/日志是否更新为准**。

用法：python -X utf8 scripts/count_watch.py
"""
import os
import subprocess
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = [
    ('猎人 valley_hunter', 'powershell', 'valley_hunter.ps1', os.path.join(R, 'evidence', 'cases')),
    ('看门狗 watchdog_hunter', 'powershell', 'watchdog_hunter.ps1', os.path.join(R, 'evidence', 'cases')),
    ('日志通道 valley_logwatch', 'python', 'valley_logwatch.py', os.path.join(R, 'evidence', 'cases')),
    ('采样器 window_watch', 'python', 'window_watch.py', os.path.join(R, 'evidence', 'samples')),
]
PS = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(python|pwsh|powershell)' } | "
      "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.Name + '|' + $_.CommandLine }")


def procs():
    out = subprocess.run(['powershell', '-NoProfile', '-Command', PS], capture_output=True).stdout.decode('utf-8', 'replace')
    rows = []
    for l in out.splitlines():
        if l.count('|') < 2:
            continue
        pid, name, cmd = l.split('|', 2)
        # **排除查询自身**：命令行里含 CIM/Where-Object 的都是"监视命令"
        if 'Get-CimInstance' in cmd or 'Where-Object' in cmd or 'count_watch' in cmd:
            continue
        rows.append((pid.strip(), name.strip(), cmd))
    return rows


def newest_mtime(d):
    best = 0
    try:
        for f in os.listdir(d):
            if f.startswith(('hunter_ledger_', 'logwatch_ledger', 'windowwatch_', 'watchdog')):
                best = max(best, os.path.getmtime(os.path.join(d, f)))
    except Exception:
        pass
    return best


def main():
    rows = procs()
    print('== 值守进程（已排除监视命令自匹配）==')
    ok = True
    for label, interp, pat, watchdir in TARGETS:
        hits = [(p, n, c) for p, n, c in rows if pat in c and interp in n.lower()]
        age = time.time() - newest_mtime(watchdir) if watchdir else -1
        state = '✅ 1' if len(hits) == 1 else ('⚠ %d 个' % len(hits))
        if len(hits) != 1:
            ok = False
        print('   %-26s %-8s pid=%s  最新产出 %s' % (
            label, state, ','.join(h[0] for h in hits) or '-',
            ('%.0fs 前' % age) if age >= 0 else '—'))
    print('\n   引擎 =', len([r for r in rows if 'ninfer-serve' in r[2]]) or
          subprocess.run(['powershell', '-NoProfile', '-Command', "@(Get-Process ninfer-serve -ErrorAction SilentlyContinue).Count"],
                         capture_output=True).stdout.decode().strip())
    print('   ⇒ 判存活以"最新产出时间"为准，不以进程数为唯一依据（自匹配陷阱）')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
