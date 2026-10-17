# -*- coding: utf-8 -*-
r"""check_launchers.py -- 扫描全部启动脚本，抓"窗口纪律"违规写法（T-WINDOW 静态层）。

为什么存在：2026-10-17 CB 绕开 engine_ctl.ps1 的 ValidateSet('Normal') 自写脚本用
  -WindowStyle Minimized ⇒ 用户看不到窗口。**静态层的作用 = 让这种写法进不了仓**。

禁则（任一命中 ⇒ 违规，门禁拦截）：
  1. -WindowStyle <非 Normal>（Minimized / Hidden / Maximized）
  2. CreateNoWindow / WindowStyle = 'Hidden'（.NET ProcessStartInfo）
  3. （已删除：原"非许可入口 Start-Process"规则过宽 —— 正常 Normal 起窗被误判 ⇒ 只保留"窗口样式"两条）

用法：python -X utf8 scripts\check_launchers.py [--json]
退出码：0 = 通过；1 = 有违规
"""
import io
import json
import os
import re
import sys

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_SELF = os.path.join('scripts', 'spawn_visible.ps1')

# 扫描范围：入库的启动/工具脚本（不含 work/、.temp/、archive/、vendored）
SCAN_DIRS = ['scripts', 'tools', '.']
SKIP_DIRS = {'.git', '.temp', 'work', '_trash', '_safety_backups', 'archive', 'retired',
             'engine-src', 'official-repo', 'refs', '__pycache__', 'models', 'engine', 'logs', 'evidence'}
EXTS = ('.ps1', '.bat', '.cmd')

PAT_WINDOWSTYLE = re.compile(r'-WindowStyle\s+([A-Za-z]+)', re.I)
PAT_NOWINDOW = re.compile(r'CreateNoWindow|WindowStyle\s*=\s*[\'"]Hidden[\'"]', re.I)
PAT_STARTPROC = re.compile(r'\bStart-Process\b', re.I)
PAT_SANCTIONED = re.compile(r'spawn_visible\.ps1', re.I)


def _load_decl():
    try:
        j = json.load(io.open(os.path.join(R, 'structure.json'), encoding='utf-8'))
        wd = j.get('window_discipline') or {}
        return ([x.replace('/', os.sep).lower() for x in (wd.get('sanctioned_spawners') or [])],
                [x.lower() for x in (wd.get('headless_allowed') or [])])
    except Exception:
        return ([], [])


def scan():
    spawners, headless = _load_decl()
    hits = []
    for d in SCAN_DIRS:
        base = os.path.join(R, d) if d != '.' else R
        for root, dirs, files in os.walk(base):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for fn in files:
                if not fn.endswith(EXTS):
                    continue
                p = os.path.join(root, fn)
                rel = os.path.relpath(p, R)
                rl = rel.lower()
                try:
                    t = io.open(p, encoding='utf-8-sig', errors='replace').read()
                except Exception:
                    continue
                is_spawner = any(rl == s for s in spawners)
                for i, line in enumerate(t.splitlines(), 1):
                    ls = line.strip()
                    if ls.startswith('#'):
                        continue
                    m = PAT_WINDOWSTYLE.search(line)
                    if m and m.group(1).lower() != 'normal':
                        # 白名单：目标是已声明的无界面件 ⇒ 允许（但必须在同一声明体系里）
                        low = line.lower()
                        if any(h in low for h in headless):
                            continue
                        hits.append((rel, i, 'WindowStyle=' + m.group(1), ls[:110]))
                    if PAT_NOWINDOW.search(line):
                        low = line.lower()
                        if not any(h in low for h in headless):
                            hits.append((rel, i, 'CreateNoWindow/Hidden', ls[:110]))
    return hits


def main():
    hits = scan()
    as_json = '--json' in sys.argv
    if as_json:
        print(json.dumps({'violations': [{'file': h[0], 'line': h[1], 'kind': h[2]} for h in hits]},
                         ensure_ascii=False))
    else:
        print('check_launchers: 扫描启动脚本（窗口纪律 T-WINDOW 静态层）')
        if not hits:
            print('  ✅ 无违规')
        else:
            print('  ❌ 违规 %d 处（禁则：窗口非 Normal / 无窗口 / 未许可入口 Start-Process）' % len(hits))
            for f, ln, kind, txt in hits[:25]:
                print('     %-46s L%-4d [%s] %s' % (f, ln, kind, txt))
            if len(hits) > 25:
                print('     …（还有 %d 处）' % (len(hits) - 25))
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
