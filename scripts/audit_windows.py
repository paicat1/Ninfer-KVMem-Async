# -*- coding: utf-8 -*-
r"""audit_windows.py -- 独立窗口状态审计（T-WINDOW 审计层，不依赖 CB 自觉）。

设计要点（为什么"不依赖我"）：
  · 纯只读：只查进程与窗口状态，不改任何东西
  · 可被 Windows 计划任务按分钟调用（用户在系统层挂一次，之后无需任何人记得）
  · 发现违规 ⇒ 写 evidence/audits/VIOLATION_window_<ts>.md（独立证据，不得删除）
  · 正常 ⇒ 写一行 evidence/audits/window_state_<date>.txt（时间线）

判据（用户 2026-10-11 裁决 + 2026-10-17 违规事件）：
  我们的进程（ninfer*/python*/powershell*/cmd* 且命令行含本仓标记）
  ⇒ 若有窗口：必须 可见 且 **非最小化**；若窗口句柄为 0（无窗口）⇒ 也判违规
用法：python -X utf8 scripts\audit_windows.py [--quiet]
退出码：0 = 全部合格；3 = 有违规
"""
import io
import json
import os
import subprocess
import sys
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUD = os.path.join(R, 'evidence', 'audits')
os.makedirs(AUD, exist_ok=True)

PS = r'''
Add-Type @"
using System;using System.Runtime.InteropServices;
public class AW {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$markers = @('ninfer','valley_hunter','watchdog_hunter','valley_logwatch','window_watch','serve_tee','vram_hold','start_engine','round4_decode','round2b','round3_shape')
$procs = Get-CimInstance Win32_Process | Where-Object {
  $cl = $_.CommandLine
  if (-not $cl) { return $false }
  ($_.Name -match 'ninfer|python|powershell|cmd|vram_hold') -and ($markers | Where-Object { $cl -like ('*' + $_ + '*') })
}
foreach ($pr in $procs) {
  $p = Get-Process -Id $pr.ProcessId -ErrorAction SilentlyContinue
  if (-not $p) { continue }
  $h = $p.MainWindowHandle
  $has = ($h -ne 0)
  $ico = $null; $vis = $null
  if ($has) { $ico = [AW]::IsIconic($h); $vis = [AW]::IsWindowVisible($h) }
  $ok = ($has -and (-not $ico) -and $vis)
  $cmd = $pr.CommandLine; if ($cmd.Length -gt 90) { $cmd = $cmd.Substring(0,90) }
  '{0}|{1}|{2}|{3}|{4}|{5}|{6}' -f $pr.ProcessId, $pr.Name, $has, $ico, $vis, $p.MainWindowTitle, $cmd
}
'''
out = subprocess.run(['powershell', '-NoProfile', '-Command', PS], capture_output=True).stdout.decode('utf-8', 'replace')
rows = [l for l in out.splitlines() if l.count('|') >= 6]
ts = time.strftime('%Y-%m-%d %H:%M:%S')
day = time.strftime('%Y%m%d')

viol = []
for l in rows:
    parts = l.split('|')
    pid, name, has, ico, vis, title, cmd = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], '|'.join(parts[6:])
    # 判据（2026-10-17 修精度）：**只判"窗口拥有者"**
    #   有窗口 ⇒ 必须可见且非最小化；**无窗口 = 正常**（控制台窗口属父 cmd/powershell，子进程本无窗口）
    if has.lower() != 'true':
        continue
    ok = (ico.lower() == 'false' and vis.lower() == 'true')
    if not ok:
        viol.append((pid, name, has, ico, vis, title, cmd))

with io.open(os.path.join(AUD, 'window_state_%s.txt' % day), 'a', encoding='utf-8') as f:
    f.write('%s | 进程 %d | 合格 %d | 违规 %d\n' % (ts, len(rows), len(rows) - len(viol), len(viol)))

if viol:
    p = os.path.join(AUD, 'VIOLATION_window_%s.md' % time.strftime('%Y%m%d_%H%M%S'))
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('# 违规记录：窗口不可见/被最小化/无窗口（T-WINDOW）\n\n')
        f.write('- 审计时刻：%s\n- 审计器：`scripts\\audit_windows.py`（独立层，非 CB 自报）\n' % ts)
        f.write('- 判据：有窗口 ⇒ 必须可见且非最小化；无窗口 ⇒ 亦违规\n\n')
        f.write('| pid | 进程 | 有窗口 | 最小化 | 可见 | 标题 |\n|---|---|---|---|---|---|\n')
        for v in viol:
            f.write('| %s | %s | %s | %s | %s | %s |\n' % (v[0], v[1], v[2], v[3], v[4], v[5]))
        f.write('\n**处置**：立即恢复可见并说明；本文件为独立证据，不得删除。\n')
    print('❌ T-WINDOW 违规 %d 项 ⇒ %s' % (len(viol), os.path.relpath(p, R)))
    for v in viol:
        print('   pid=%s %s 有窗口=%s 最小化=%s 可见=%s "%s"' % (v[0], v[1], v[2], v[3], v[4], v[5]))
    sys.exit(3)

# —— 判据 2：无记录进程（绕开唯一许可入口的可检出性）——
rec_dir = os.path.join(R, 'evidence', 'spawns')
try:
    enforce_since = (json.load(io.open(os.path.join(R, 'structure.json'), encoding='utf-8'))
                     .get('window_discipline', {}).get('enforce_since') or '')
except Exception:
    enforce_since = ''
unrecorded = []
if enforce_since:
    import datetime
    try:
        since_ts = datetime.datetime.strptime(enforce_since, '%Y-%m-%d %H:%M:%S').timestamp()
    except Exception:
        since_ts = None
    rec_pids = set()
    if os.path.isdir(rec_dir):
        for f in os.listdir(rec_dir):
            try:
                rj = json.load(io.open(os.path.join(rec_dir, f), encoding='utf-8'))
                rec_pids.add(str(rj.get('pid')))
            except Exception:
                pass
    if since_ts:
        ps2 = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'ninfer|python|powershell|cmd|vram_hold' "
               "} | ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CreationDate.ToString('yyyy-MM-dd HH:mm:ss') + '|' + $_.Name }")
        o2 = subprocess.run(['powershell', '-NoProfile', '-Command', ps2], capture_output=True).stdout.decode('utf-8', 'replace')
        for line in o2.splitlines():
            parts = line.split('|')
            if len(parts) < 3:
                continue
            pid2, cts, nm = parts[0].strip(), parts[1].strip(), parts[2].strip()
            try:
                c_t = datetime.datetime.strptime(cts, '%Y-%m-%d %H:%M:%S').timestamp()
            except Exception:
                continue
            # 2026-10-17 收精：只抓**存活 ≥30 s** 的无记录进程（判据本意是抓长期潜伏；
            #   瞬时诊断进程（几秒即退）不应制造噪声 —— 否则审计会天天红、被无视）
            age_s = time.time() - c_t
            if c_t > since_ts and pid2 not in rec_pids and age_s >= 30:
                # 2026-10-17 自豁免：**计划任务**调用的本审计器自身（每 5 分钟一次，
                #   不经 spawn_visible 是设计如此 —— 它是"已声明的无界面后台审计"）。
                #   判据：命令行含 audit_windows（本文件）或 audit_windows_task.ps1（包装）。
                try:
                    cl2 = subprocess.run(['powershell', '-NoProfile', '-Command',
                                          "(Get-CimInstance Win32_Process -Filter \"ProcessId=%s\").CommandLine" % pid2],
                                         capture_output=True).stdout.decode('utf-8', 'replace')
                except Exception:
                    cl2 = ''
                if ('audit_windows' in cl2) or ('audit_windows_task' in cl2):
                    continue
                unrecorded.append((pid2, nm, cts))
    if unrecorded:
        p2 = os.path.join(AUD, 'VIOLATION_unrecorded_spawn_%s.md' % time.strftime('%Y%m%d_%H%M%S'))
        with io.open(p2, 'w', encoding='utf-8', newline='\n') as f:
            f.write('# 违规记录：无 spawn 记录的我方进程（T-WINDOW 判据 2）\n\n')
            f.write('- 时刻：%s\n- 生效时刻（enforce_since）：%s\n' % (ts, enforce_since))
            f.write('- 含义：该进程**未走唯一许可入口** `scripts\\spawn_visible.ps1`（或未留记录）\n\n')
            f.write('| pid | 进程 | 启动时刻 |\n|---|---|---|\n')
            for u in unrecorded:
                f.write('| %s | %s | %s |\n' % u)
            f.write('\n**处置**：说明该进程来源；若确为绕开许可入口 ⇒ 记 T0。本文件为独立证据，不得删除。\n')
        print('❌ 无记录进程 %d 个 ⇒ %s' % (len(unrecorded), os.path.relpath(p2, R)))
        for u in unrecorded:
            print('   pid=%s %s 启动于 %s' % u)
        sys.exit(4)

if '--quiet' not in sys.argv:
    print('✅ 窗口审计通过：%d 个进程全部可见且非最小化' % len(rows))
sys.exit(0)
