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


def traverse_rules(paths, token):
    """铁律B（用户 2026-10-18 令）：申请清理前必须【遍历所有规则】⇒ 逐条给判定。
    返回 [(rule, verdict, detail)]；verdict ∈ {OK, BLOCK, ASK}。任一 BLOCK ⇒ 不可删；任一 ASK ⇒ 需申请。
    """
    import fnmatch
    j = {}
    try:
        j = json.load(io.open(SJ, encoding='utf-8'))
    except Exception:
        pass
    out = []
    lows = [os.path.relpath(p, R).replace('\\', '/').lower() for p in paths]

    def hit(cond, rule, verdict, detail):
        out.append((rule, verdict if cond else 'OK', detail if cond else '-'))

    # R1 T-TRACE：成品禁删
    art = [x for x in lows if x.endswith(ARTIFACT_EXT)]
    hit(bool(art), 'R1 T-TRACE（任何成品严禁删除）', 'BLOCK', '命中成品扩展名：%s' % (art[:3],))
    nd = list(((j.get('backup_policy') or {}).get('never_delete')) or [])
    in_nd = [x for x in lows for p in nd
             if fnmatch.fnmatch(x, p.rstrip('/').replace('*', '*') + ('' if p.endswith('*') else '/*'))]
    hit(bool(in_nd), 'R2 backup_policy.never_delete', 'BLOCK', '命中禁删区：%s' % (in_nd[:3],))
    # R3 活件判定
    now = time.time()
    live = []
    for p in paths:
        try:
            if now - os.path.getmtime(p) < ((j.get('live_artifact_check') or {}).get('recent_write_within_seconds') or 300):
                live.append(os.path.relpath(p, R))
        except Exception:
            pass
    hit(bool(live), 'R3 live_artifact_check（活件）', 'BLOCK', '近期有写入：%s' % (live[:3],))
    # R4 引用扫描
    ref = []
    for p in paths:
        nm = os.path.basename(p)
        try:
            rc = subprocess.run(['git', 'grep', '-l', '-F', '--', nm], cwd=R, capture_output=True)
            if rc.stdout.decode('utf-8', 'replace').strip():
                ref.append(nm)
        except Exception:
            pass
    hit(bool(ref), 'R4 引用扫描（跟踪件是否提到）', 'BLOCK', '被引用：%s' % (ref[:3],))
    # R5 canonical_dirs：删除是否破坏"一类一个家"
    can = j.get('canonical_dirs') or {}
    inc = [x for x in lows if any(x.startswith(k.lower() + '/') for k in can)]
    hit(bool(inc), 'R5 canonical_dirs（正式区）', 'ASK', '位于正式区：%s ⇒ 需向用户申请' % (inc[:3],))
    # R6 known_violations（挂账件不得私自清掉）
    kv = j.get('known_violations') or []
    kvp = [x for x in lows for v in kv for m in (v.get('match') or []) if fnmatch.fnmatch(x, m)]
    hit(bool(kvp), 'R6 known_violations（挂账证据）', 'ASK', '属挂账证据：%s ⇒ 私自删=销毁证据' % (kvp[:3],))
    # R7 铁律A：_ 前缀目录
    ud = [x for x in lows if x.startswith('_') or '/_' in x]
    decl = [ (d.get('name') or '').lower() for d in ((j.get('underscore_dirs') or {}).get('declared') or []) ]
    undecl = [x for x in ud if not any(x.startswith(d + '/') or x == d for d in decl)]
    hit(bool(ud), 'R7 铁律A（下划线目录）', ('ASK' if undecl else 'OK'),
        ('未声明的下划线目录：%s ⇒ 必须先查清 + 申请' % (undecl[:3],)) if undecl else '已声明目录内，仍需在报告中说明')
    # R8 配额相关性
    hit(True, 'R8 quotas（体量红线）', 'OK', '删除后体量变化已计入清单')
    return out


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

    # 铁律B：先遍历所有规则
    rules = traverse_rules(files, a.token)
    rule_block = [x for x in rules if x[1] == 'BLOCK']
    rule_ask = [x for x in rules if x[1] == 'ASK']
    print('== 规则遍历（铁律B：申请清理前必读全部规则）==')
    for rl, vd, dt in rules:
        print('   [%-5s] %-34s %s' % (vd, rl, dt))
    if rule_block:
        print('   ⇒ 有规则判【禁删】：%s' % ', '.join(x[0] for x in rule_block))
    if rule_ask:
        print('   ⇒ 有规则需【向用户申请】：%s' % ', '.join(x[0] for x in rule_ask))
    blocked = [r for r in recs if r.get('live') or r.get('referenced_by') or r['t_trace'].startswith('BLOCKED')]
    if rule_block:
        blocked = list(recs)   # 任一规则判禁删 ⇒ 整批不得删

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
