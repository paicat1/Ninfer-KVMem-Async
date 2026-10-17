# -*- coding: utf-8 -*-
r"""commit_scope.py -- 提交范围检查（2026-10-17 立）

由来：CB 两次用 `git add -A docs` 把**他方待批文件**带走（TELE 审核报告 10:34 版、A0 产物 docs/INDEX.md）。
规则（structure.json 的 `agent_owned`）：提交前检查**已暂存文件**，命中他方所属 ⇒ 报错并列出，除非显式 `--allow-agent-files`。

用法：
    python -X utf8 scripts/commit_scope.py           # 检查暂存区（rc=0 通过 / 1 越界）
    python -X utf8 scripts/commit_scope.py --list    # 只列暂存文件
"""
import fnmatch
import io
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def staged():
    o = subprocess.run(['git', 'diff', '--cached', '--name-only'], cwd=ROOT, capture_output=True).stdout.decode('utf-8', 'replace')
    return [l.strip() for l in o.splitlines() if l.strip()]


def unpushed():
    """未推提交里改动的全部文件（origin/main..HEAD）。"""
    rng = subprocess.run(['git', 'rev-list', 'origin/main..HEAD'], cwd=ROOT, capture_output=True).stdout.decode('utf-8', 'replace')
    shas = [l.strip() for l in rng.splitlines() if l.strip()]
    if not shas:
        return []
    o = subprocess.run(['git', 'diff', '--name-only'] + shas[-1] + '~1..HEAD', cwd=ROOT, capture_output=True)
    out = (o.stdout or b'').decode('utf-8', 'replace')
    if not out.strip():
        o2 = subprocess.run(['git', 'show', '--pretty=format:', '--name-only'] + shas, cwd=ROOT, capture_output=True)
        out = (o2.stdout or b'').decode('utf-8', 'replace')
    return [l.strip() for l in out.splitlines() if l.strip()]


def main():
    warn_only = '--warn' in sys.argv
    files = unpushed() if '--unpushed' in sys.argv else staged()
    scope = '未推提交' if '--unpushed' in sys.argv else '暂存区'
    if '--list' in sys.argv:
        for f in files:
            print('   ' + f)
        return 0
    p = os.path.join(ROOT, 'structure.json')
    rules = json.load(io.open(p, encoding='utf-8')) if os.path.exists(p) else {}
    owned = rules.get('agent_owned', {}).get('exclusive', {})
    shared = rules.get('agent_owned', {}).get('shared', [])
    bad = []
    for who, pats in owned.items():
        if who.startswith('_'):
            continue
        for pat in pats:
            for f in files:
                if fnmatch.fnmatch(f, pat):
                    bad.append((who, f))
    print('commit_scope: %s %d 个文件（shared 通道不计越界）' % (scope, len(files)))
    if bad:
        print('\n❌ 越界：暂存区含他方所属文件（等其本人攒批 + 用户批准）')
        for who, f in bad:
            print('   [%s] %s' % (who, f))
        if '--allow-agent-files' in sys.argv:
            print('   （--allow-agent-files 已显式放行）')
            return 0
        if warn_only:
            print('   （--warn：仅报告，不阻断）')
            return 0
        return 1
    print('✅ 未含他方专属文件（shared 通道 %d 类允许提交）' % len(shared))
    return 0


if __name__ == '__main__':
    sys.exit(main())
