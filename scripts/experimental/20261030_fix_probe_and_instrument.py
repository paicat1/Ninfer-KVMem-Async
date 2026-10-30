# -*- coding: utf-8 -*-
"""2026-10-30 提速双修：
① smart_push.ps1 代理探测 Get-NetTCPConnection(CIM 慢) → TcpClient 150ms
② gates.ps1 插桩每段计时（[T] 行，诊断后拆除）
"""
import io
import re

# ---------- ① smart_push 探测 ----------
P1 = r'J:\ninfer-kvmem\smart_push.ps1'
t = io.open(P1, 'rb').read().decode('utf-8')

pat = re.compile(
    r'(\$listening = Get-NetTCPConnection -State Listen -LocalPort \$p[^\r\n]*\r?\n)'
    r'(\s*?)if \(\$listening\) \{ return \[int\]\$p \}')
new_probe = (
    '$c = New-Object Net.Sockets.TcpClient\n'
    '\\2try {\n'
    '\\2    $ar = $c.BeginConnect(\'127.0.0.1\', $p, $null, $null)\n'
    '\\2    if ($ar.AsyncWaitHandle.WaitOne(150) -and $c.Connected) { return [int]$p }\n'
    '\\2} catch {\n'
    '\\2} finally {\n'
    '\\2    $c.Close()\n'
    '\\2}')
t2, n1 = pat.subn(lambda m: new_probe.replace('\\2', m.group(2)), t)
print('① smart_push 探测替换: %d 处' % n1)
if n1 == 1:
    io.open(P1, 'wb').write(t2.encode('utf-8'))

# ---------- ② gates 插桩 ----------
P2 = r'J:\ninfer-kvmem\scripts\gates.ps1'
g = io.open(P2, 'rb').read().decode('utf-8')
lines = g.split('\n')
out, cur = [], None
count = 0
for ln in lines:
    m_start = re.match(r'# =+ ([A-Z][A-Z-]+-GATE[^=]*)=+ *$', ln.strip())
    m_end = re.match(r'# =+ ([A-Z][A-Z-]+-GATE[^=]*)END =+ *$', ln.strip())
    if m_start:
        if cur:
            out.append('Write-Host ("[T] %s ms=" + [int]$__gsw.Elapsed.TotalMilliseconds)' % cur)
        name = m_start.group(1).strip()
        out.append("$__gT = '%s'; $__gsw = [Diagnostics.Stopwatch]::StartNew()" % name)
        cur = name
        count += 1
    elif m_end and cur:
        out.append('Write-Host ("[T] %s ms=" + [int]$__gsw.Elapsed.TotalMilliseconds)' % cur)
        cur = None
        count += 1
    out.append(ln)
# 未标记区（HOOK-GIT-ENV END 之后 → UNDERSCORE-GATE 之前）
for i, ln in enumerate(out):
    if 'HOOK-GIT-ENV END' in ln:
        out.insert(i + 1, "$__gT = 'refs-structure-window'; $__gsw = [Diagnostics.Stopwatch]::StartNew()")
        count += 1
        break
for i, ln in enumerate(out):
    if " $__gT = 'UNDERSCORE-GATE'" in ln:
        out.insert(i, 'Write-Host ("[T] refs-structure-window ms=" + [int]$__gsw.Elapsed.TotalMilliseconds)')
        count += 1
        break
io.open(P2, 'wb').write('\n'.join(out).encode('utf-8'))
print('② gates 插桩: %d 处' % count)
