# -*- coding: utf-8 -*-
r"""check_ps1_bom.py -- "含中文的 .ps1 必须带 UTF-8 BOM"（门禁静态层 · 2026-10-17 立）

为什么：PowerShell 5.1 对**无 BOM** 的 .ps1 按 ANSI(GBK) 读 ⇒ 中文乱码 ⇒ 解析失败。
  今天因此坏了两个件（audit_windows_task.ps1、spawn_visible.ps1 —— 后者是"唯一许可入口"）。
  TELE 核：全仓 281 个缺 BOM，但**活跃且属我们的只有 ~11 个**（其余是 .temp/archive/别人的仓）。

判据（只查"改动过/新增"的 ⇒ 不翻 281 个旧账；存量单独处置）：
  · git status 里新增/修改的 .ps1，若**含中文**且**无 BOM** ⇒ 违规（阻断提交/推送）
用法：python -X utf8 scripts\check_ps1_bom.py [--all]
退出码：0 通过；1 有违规
"""
import io
import os
import subprocess
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTIVE = ('', 'scripts/', 'tools/', 'build/')


def changed_ps1():
    o = subprocess.run(['git', '-c', 'core.quotepath=false', 'status', '--porcelain'],
                         cwd=R, capture_output=True).stdout.decode('utf-8', 'replace')
    out = []
    for line in o.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if path.endswith('.ps1'):
            out.append(path)
    return out


def all_ps1_active():
    out = []
    for root, dirs, files in os.walk(R):
        dirs[:] = [d for d in dirs if d not in ('.git', '.temp', 'work', '_trash', '_safety_backups',
                                                'archive', 'retired', 'evidence', '__pycache__',
                                                'engine-src', 'official-repo', 'refs', 'models', 'engine', 'logs')]
        for fn in files:
            if fn.endswith('.ps1'):
                out.append(os.path.relpath(os.path.join(root, fn), R))
    return out


def check(paths):
    hits = []
    for rel in paths:
        p = os.path.join(R, rel)
        if not os.path.exists(p):
            continue
        b = io.open(p, 'rb').read()
        if b.startswith(b'\xef\xbb\xbf'):
            continue
        try:
            t = b.decode('utf-8')
        except Exception:
            continue
        if any('\u4e00' <= ch <= '\u9fff' for ch in t):
            hits.append(rel)
    return hits


def main():
    if '--all' in sys.argv:
        hits = check(all_ps1_active())
        print('check_ps1_bom(--all): 活跃区含中文但缺 BOM 的 .ps1 = %d 个' % len(hits))
        for h in sorted(hits):
            print('   %s' % h)
        return 1 if hits else 0
    hits = check(changed_ps1())
    print('check_ps1_bom: 扫改动/新增的 .ps1（窗口纪律 BOM 静态层）')
    if not hits:
        print('  ✅ 无违规（新增/修改的含中文 .ps1 均带 BOM）')
    else:
        print('  ❌ 违规 %d 个（含中文的 .ps1 必须带 UTF-8 BOM，否则 PowerShell 按 ANSI 读 ⇒ 乱码 ⇒ 解析失败）' % len(hits))
        for h in hits[:20]:
            print('     %s' % h)
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
