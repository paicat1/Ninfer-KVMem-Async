# -*- coding: utf-8 -*-
"""delete_manifest.py -- 删除/移动的【唯一下手路径】（2026-10-18 建 · 堵 L4）

为什么存在：
  2026-10-18 我把 _safety_backups 里 4 个 1.27GB 引擎 exe（**唯一副本**，T-TRACE 明令禁删）
  当成"可回收空间"混进清理清单请用户授权 —— 若用户点头就会删掉 4 个不可重建的构建。
  当时的防线全是纯文本：T-TRACE 无机械强制、删除四步无 manifest、环境阈值只数个数不认成品。

本脚本把删除变成"过不了就删不掉"：
  ① sha 留痕（每个待删文件）
  ② 引用扫描（跟踪件 + structure.json + scripts/ + .git/hooks + .codebuddy/sda）
  ③ 活件判定（live_artifact_check：近 300 s 写过 ⇒ 拒）
  ④ **T-TRACE 硬判据**：命中 never_delete / 成品扩展名（.exe/.dll/.ninfer/.bin/.safetensors/.zip/.7z/.bundle）
     ⇒ **一律拒删**，除非 --token 里【点名该物】（用户原话含该文件名/路径）
  ⑤ 生成清单件 + token ⇒ 真实删除必须带 token，且 bypass_guard 拦"没走本路径的删除原语"

用法：python -X utf8 scripts\delete_manifest.py --paths <...> --reason "..." --token "<用户原话>"
      默认【只出清单不删】；确认无误再加 --apply
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

R = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUD = os.path.join(R, 'evidence', 'audits')
WORK = os.path.join(R, 'work')
SJ = os.path.join(R, 'structure.json')

# 成品扩展名（T-TRACE：任何成品严禁删除）
ARTIFACT_EXT = ('.exe', '.dll', '.pdb', '.ninfer', '.bin', '.safetensors', '.zip', '.7z',
                '.bundle', '.patch', '.whl', '.tar', '.gz', '.msi', '.iso')


def sha(p, chunk=1 << 22):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_never_delete():
    try:
        j = json.load(io.open(SJ, encoding='utf-8'))
        return list(((j.get('backup_policy') or {}).get('never_delete')) or [])
    except Exception:
        return []


def expand(paths):
    out = []
    for p in paths:
        ap = p if os.path.isabs(p) else os.path.join(R, p)
        if os.path.isdir(ap):
            out += [os.path.join(dp, f) for dp, dn, fn in os.walk(ap) for f in fn]
        elif os.path.isfile(ap):
            out.append(ap)
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--paths', nargs='+', required=True)
    ap.add_argument('--reason', default='')
    ap.add_argument('--token', default='')
    ap.add_argument('--apply', action='store_true')
    a = ap.parse_args()

    files = expand(a.paths)
    if not files:
        print('（没匹配到文件）')
        return 0
    nd = load_never_delete()
    recs = []
    for f in files:
        try:
            rel = os.path.relpath(f, R).replace('\\', '/')
            recs.append({'path': rel, 'bytes': os.path.getsize(f), 'sha256': sha(f)})
        except Exception as e:
            recs.append({'path': os.path.relpath(f, R).replace('\\', '/'), 'err': str(e)[:80]})

    # ④ T-TRACE 硬判据
    for r in recs:
        low = r['path'].lower()
        is_art = low.endswith(ARTIFACT_EXT)
        in_nd = any(re.match('^' + re.escape(p.rstrip('/')).replace(r'\*', '.*') + '(/|$)', low) for p in nd)
        r['is_artifact'] = is_art
        r['in_never_delete'] = in_nd
        if is_art or in_nd:
            named = (os.path.basename(low) in (a.token or '').lower()) or (low in (a.token or '').lower())
            r['t_trace'] = 'ALLOWED(用户点名)' if named else 'BLOCKED(T-TRACE 成品禁删)'
        else:
            r['t_trace'] = 'ok'

    # ② 引用扫描（简化：在跟踪件 + 关键目录里找文件名）
    names = [os.path.basename(r['path']) for r in recs]
    ref_hits = {}
    try:
        for nm in names[:60]:
            rc = subprocess.run(['git', 'grep', '-l', '-F', '--', nm], cwd=R, capture_output=True)
            hits = [l.strip() for l in rc.stdout.decode('utf-8', 'replace').splitlines() if l.strip()]
            if hits:
                ref_hits[nm] = hits[:3]
    except Exception:
        pass
    for r in recs:
        r['referenced_by'] = ref_hits.get(os.path.basename(r['path']), [])

    # ③ 活件判定
    now = time.time()
    for r in recs:
        try:
            r['age_s'] = int(now - os.path.getmtime(os.path.join(R, r['path'])))
            r['live'] = r['age_s'] < 300
        except Exception:
            r['live'] = False

    blocked = [r for r in recs if r.get('live') or r.get('referenced_by') or r['t_trace'].startswith('BLOCKED')]
    ok = [r for r in recs if r not in blocked]

    ts = time.strftime('%Y%m%d_%H%M%S')
    man = os.path.join(AUD, 'DELETE_MANIFEST_%s.md' % ts)
    io.open(man, 'w', encoding='utf-8', newline='\n').write('\n'.join([
        '# 删除清单（%s）' % ts,
        '',
        '- 理由：%s' % (a.reason or '（未填）'),
        '- 用户批准原话：%s' % (a.token or '（未填）'),
        '- 待删 %d 个 · %.1f MiB' % (len(recs), sum(r.get('bytes', 0) for r in recs) / 1048576),
        '- **拒绝删**（活件/被引用/T-TRACE 成品）%d 个；可删 %d 个' % (len(blocked), len(ok)),
        '',
        '## 拒绝删明细',
        '',
        '\n'.join('- %s | %s | 引用=%s | 活件=%s' % (r['path'], r.get('t_trace'), (r.get('referenced_by') or ['-'])[0], r.get('live')) for r in blocked[:100]) or '- （无）',
        '',
        '## 可删明细（前 200 条）',
        '',
        '\n'.join('- %s | %d B | sha=%s' % (r['path'], r.get('bytes', 0), (r.get('sha256') or '')[:16]) for r in ok[:200]),
    ]) + '\n')
    tokf = os.path.join(WORK, 'DELETE_TOKEN_%s.txt' % ts)
    io.open(tokf, 'w', encoding='utf-8', newline='\n').write(
        'manifest=%s\nreason=%s\napproval=%s\ntotal=%d\nblocked=%d\nok=%d\n' % (
            os.path.relpath(man, R), a.reason, a.token, len(recs), len(blocked), len(ok)))

    print('清单 = %s' % os.path.relpath(man, R))
    print('token = %s' % os.path.relpath(tokf, R))
    print('待删 %d 个 · %.1f MiB；拒绝删 %d 个（活件/被引用/成品）；可删 %d 个' % (
        len(recs), sum(r.get('bytes', 0) for r in recs) / 1048576, len(blocked), len(ok)))
    if a.apply:
        if not a.token:
            print('拒绝 --apply：缺 --token（用户批准原话）')
            return 2
        n = 0
        for r in ok:
            try:
                os.remove(os.path.join(R, r['path']))
                n += 1
            except Exception:
                pass
        print('已删 %d 个（拒删 %d 个已跳过）' % (n, len(blocked)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
