# -*- coding: utf-8 -*-
r"""check_structure.py -- 目录结构门禁（2026-10-17 立）

规则**不写在代码里，写在 `structure.json`**（规则即数据）：
  · root_whitelist     根目录白名单（只放现行入口；不在名单 = 违规）
  · forbidden          禁则（模式 × 位置）
  · known_violations   已知待清项（带 match glob；命中 ⇒ 记 known，不拦推送）
  · live_artifact_check 活件判定三源（清理前必做）

用法：
    python -X utf8 scripts/check_structure.py            # 检查（0=通过 / 1=有新违规）
    python -X utf8 scripts/check_structure.py --all      # 连 known 一起列出
"""
import fnmatch
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_rules():
    p = os.path.join(ROOT, 'structure.json')
    if not os.path.exists(p):
        print('check_structure: structure.json 不存在 -- 跳过')
        return None
    return json.load(io.open(p, encoding='utf-8'))


def is_known(rel, known):
    for kv in known:
        for g in kv.get('match', []):
            if fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(rel, g.rstrip('*') + '*'):
                return kv
    return None


def main():
    show_all = '--all' in sys.argv
    rules = load_rules()
    if rules is None:
        return 0
    wl = set(rules.get('root_whitelist', [])) | set(rules.get('canonical_dirs', {}).keys()) | {'.git'}
    # 白名单 = 根文件白名单 ∪ 规范目录（规范目录在 structure.json 的 canonical_dirs 里声明）
    known = rules.get('known_violations', [])
    blocking, knownhit, warnings = [], [], []

    # ① 根目录白名单
    for name in sorted(os.listdir(ROOT)):
        if name in wl or name == '.git':
            continue
        rel = name
        kv = is_known(rel, known)
        (knownhit if kv else blocking).append(('root', rel, kv))

    # ② 禁则（模式 × 位置）
    for f in rules.get('forbidden', []):
        where = f['where']
        base = ROOT if where == 'root' else os.path.join(ROOT, where)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if fnmatch.fnmatch(name, f['pattern']):
                rel = ('' if where == 'root' else where + '/') + name
                kv = is_known(rel, known)
                (knownhit if kv else blocking).append((where, rel, kv))

    # ③ git 边界：.gitignore 是否覆盖 must_ignore
    # **行为级**校验（2026-10-17 修：原为文本子串匹配 ⇒ 行内注释导致规则失效却仍判"通过"）
    #   逐项用 `git check-ignore` 实测：rc=0 才算真的被忽略。
    import subprocess as _sp
    miss = []
    for pat in rules.get('git_boundary', {}).get('must_ignore', []):
        probe = pat.rstrip('/')
        if probe.startswith('*'):
            probe = 'probe' + probe.lstrip('*')
        if not probe:
            continue
        rc = _sp.run(['git', 'check-ignore', '-q', probe], cwd=ROOT).returncode
        if rc != 0:
            miss.append(pat)
    if miss:
        blocking.append(('gitignore', '行为级未生效: ' + ', '.join(miss), None))

    # ④ 命名规范：scripts/ 下的"过程名"脚本（一次性脚本应在 work/）
    sc = os.path.join(ROOT, 'scripts')
    if os.path.isdir(sc):
        pats = rules.get('naming', {}).get('scripts_forbidden', [])
        for name in sorted(os.listdir(sc)):
            for p in pats:
                if fnmatch.fnmatch(name, p):
                    rel = 'scripts/' + name
                    kv = is_known(rel, known)
                    (knownhit if kv else blocking).append(('naming', rel, kv))
                    break

    # ⑤ 配额告警（**非阻断**，只提示；超线动作见 structure.json 的 quotas.action）
    for name, q in (rules.get('quotas', {}) or {}).items():
        if name.startswith('_') or not isinstance(q, dict):
            continue
        base = os.path.join(ROOT, name)
        if not os.path.isdir(base):
            continue
        tot = 0
        for r2, _d, fs in os.walk(base):
            for f2 in fs:
                try:
                    tot += os.path.getsize(os.path.join(r2, f2))
                except Exception:
                    pass
        mib = tot / 1048576
        lim = q.get('warn_mib') or (q.get('warn_gib', 0) * 1024)
        if lim and mib > lim:
            warnings.append('%s = %.0f MiB > 红线 %.0f MiB ⇒ %s' % (name, mib, lim, q.get('action', '')))

    print('check_structure: 根白名单 %d 项 · 禁则 %d 条 · 已知待清 %d 类' % (len(wl), len(rules.get('forbidden', [])), len(known)))
    if show_all and knownhit:
        print('\n[known] 已知待清（不拦推送）：')
        seen = set()
        for where, rel, kv in knownhit:
            key = kv.get('item', '') if kv else ''
            if key in seen:
                continue
            seen.add(key)
            print('   %-58s → %s' % (key[:58], (kv or {}).get('plan', '')))
    if warnings:
        print('\n⚠ 配额告警（非阻断）：')
        for w in warnings:
            print('   ' + w)
    if blocking:
        print('\n❌ 新违规 %d 条（不在白名单、也不在已知待清）：' % len(blocking))
        for where, rel, _kv in blocking[:40]:
            print('   [%s] %s' % (where, rel))
        return 1
    print('✅ 无新违规（结构合规）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
