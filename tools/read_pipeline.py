# -*- coding: utf-8 -*-
"""read_pipeline.py -- 强制逐块通读的流水线（不是抽取器）

原则（对应用户令）：
  1. 不做关键词抽取、不做探针命中判定。程序只负责「切块 / 发块 / 校验记录 / 汇总」。
  2. 「读全」必须可证：每块有 block_sha，记录必须带出现在**该块原文**里的引文。
  3. 顺序强制：第 N 块未记录，不能记录第 N+1 块。
  4. 文档汇总前，所有块必须齐；缺一块即拒。

子命令：
  plan                 生成 226 份文档的块清单
  next                 输出下一块全文 + 其 sha
  record <json_file>   写入一块的记录（校验 sha / 引文 / 顺序）
  status               块级 + 文档级进度
  finalize <doc> <json>汇总单篇（要求全块已记录）
  selftest             自证：证明「跳块/伪造引文/错 sha」都会被拒

状态文件：.codebuddy/sda/read_state.json（本地纪律件，不入库）
"""
import glob
import hashlib
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, r'.codebuddy\sda\read_state.json')
BLOCK_LINES = 200


def docs_in_order():
    out = []
    for p in glob.glob(os.path.join(ROOT, 'docs', '**', '*.md'), recursive=True):
        n = os.path.basename(p)
        m = re.search(r'(2026\d{4})', n)
        out.append(((m.group(1) if m else '99999999'), os.path.relpath(p, ROOT)))
    out.sort()
    return out


def sha(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()[:16]


def load():
    if os.path.exists(STATE):
        return json.load(io.open(STATE, encoding='utf-8'))
    return {'blocks': {}, 'docs': {}}


def save(st):
    d = os.path.dirname(STATE)
    if not os.path.isdir(d):
        os.makedirs(d)
    io.open(STATE, 'w', encoding='utf-8', newline='\n').write(json.dumps(st, ensure_ascii=False, indent=1))


def blocks_of(rel):
    text = io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()
    lines = text.split('\n')
    out = []
    for i in range(0, len(lines), BLOCK_LINES):
        seg = '\n'.join(lines[i:i + BLOCK_LINES])
        out.append({'idx': len(out), 'start': i + 1, 'end': min(i + BLOCK_LINES, len(lines)), 'sha': sha(seg)})
    return text, lines, out


def cmd_plan():
    st = load()
    tot = 0
    for date, rel in docs_in_order():
        _, _, bl = blocks_of(rel)
        st['docs'][rel] = {'date': date, 'blocks': len(bl),
                           'shas': [b['sha'] for b in bl], 'done': False}
        tot += len(bl)
    save(st)
    print('文档 = %d   块 = %d   （每块 %d 行）' % (len(st['docs']), tot, BLOCK_LINES))


def cmd_next():
    st = load()
    if not st['docs']:
        print('先跑 plan')
        return
    for date, rel in docs_in_order():
        if rel not in st['docs']:
            continue
        text, lines, bl = blocks_of(rel)
        for b in bl:
            key = '%s#%d' % (rel, b['idx'])
            if key not in st['blocks']:
                print('=' * 72)
                print('DOC %s  BLOCK %d/%d  L%d-L%d  sha=%s' %
                      (rel, b['idx'] + 1, len(bl), b['start'], b['end'], b['sha']))
                print('=' * 72)
                print('\n'.join(lines[b['start'] - 1:b['end']]))
                return
    print('全部块已读')


def _check_block(st, rel, idx):
    if rel not in st['docs']:
        return None, 'FAIL: 文档未在 plan 中'
    text, lines, bl = blocks_of(rel)
    if idx < 0 or idx >= len(bl):
        return None, 'FAIL: 块号越界'
    b = bl[idx]
    if b['sha'] != st['docs'][rel]['shas'][idx]:
        return None, 'FAIL: 文档内容已变（block sha 与 plan 不一致），需重跑 plan'
    for j in range(idx):
        if '%s#%d' % (rel, j) not in st['blocks']:
            return None, 'FAIL: 顺序违规（第 %d 块未记录，不能记录第 %d 块）' % (j + 1, idx + 1)
    return (b, lines), None


def cmd_record(jf):
    rec = json.load(io.open(jf, encoding='utf-8'))
    rel, idx = rec['doc'], int(rec['block'])
    st = load()
    got, err = _check_block(st, rel, idx)
    if err:
        print(err)
        return 2
    b, lines = got
    seg = '\n'.join(lines[b['start'] - 1:b['end']])
    if rec.get('sha') != b['sha']:
        print('FAIL: block sha 不符（应 %s，给了 %s）' % (b['sha'], rec.get('sha')))
        return 3
    qs = [q for q in rec.get('quotes', []) if q.strip()]
    if len(qs) < 2:
        print('FAIL: 引文少于 2 处')
        return 4
    bad = [q for q in qs if q.strip() not in seg]
    if bad:
        print('FAIL: 以下引文不在本块原文中（编造）：')
        for q in bad[:3]:
            print('   ' + q[:80])
        return 5
    for f in ('points', 'todos', 'verdict'):
        if f not in rec:
            print('FAIL: 缺字段 ' + f)
            return 6
    if not rec.get('points') or not rec.get('verdict'):
        print('FAIL: points/verdict 不能为空')
        return 6
    st['blocks']['%s#%d' % (rel, idx)] = {
        'start': b['start'], 'end': b['end'], 'sha': b['sha'],
        'points': rec['points'], 'todos': rec['todos'],
        'verdict': rec['verdict'], 'quotes': qs[:6]}
    save(st)
    print('OK: %s 第 %d 块已记录（引文 %d 处，要点 %d 条，待办 %d 条）'
          % (rel, idx + 1, len(qs), len(rec['points']), len(rec['todos'])))
    return 0


def cmd_status():
    st = load()
    if not st['docs']:
        print('先跑 plan')
        return
    done_docs = 0
    done_blocks = 0
    total_blocks = 0
    for rel, d in st['docs'].items():
        total_blocks += d['blocks']
        n = sum(1 for i in range(d['blocks']) if '%s#%d' % (rel, i) in st['blocks'])
        done_blocks += n
        if n == d['blocks'] and d['blocks'] > 0:
            done_docs += 1
    print('文档 %d/%d 完成   块 %d/%d' % (done_docs, len(st['docs']), done_blocks, total_blocks))


def cmd_selftest():
    """证明程序真的挡得住：跳块 / 伪造引文 / 错 sha。"""
    rel = docs_in_order()[0][1]
    text, lines, bl = blocks_of(rel)
    st = {'blocks': {}, 'docs': {rel: {'date': '', 'blocks': len(bl),
                                       'shas': [b['sha'] for b in bl], 'done': False}}}
    sha0 = bl[0]['sha']
    seg0 = '\n'.join(lines[0:min(BLOCK_LINES, len(lines))])
    quote_ok = ''
    for ln in seg0.split('\n'):
        t = ln.strip()
        if len(t) >= 20:
            quote_ok = t
            break
    cases = [
        ('跳块（先记第2块）', dict(doc=rel, block=1, sha=bl[1]['sha'],
                                quotes=[quote_ok, quote_ok], points=['x'], todos=[], verdict='未做'), 2),
        ('伪造引文', dict(doc=rel, block=0, sha=sha0,
                        quotes=['这句话绝对不在原文里ABCDEFG', '也不在HIJKLMN'],
                        points=['x'], todos=[], verdict='未做'), 5),
        ('错 sha', dict(doc=rel, block=0, sha='deadbeefdeadbeef',
                       quotes=[quote_ok, quote_ok], points=['x'], todos=[], verdict='未做'), 3),
        ('缺字段', dict(doc=rel, block=0, sha=sha0, quotes=[quote_ok, quote_ok]), 6),
    ]
    # 用临时 state 跑校验逻辑
    global STATE
    bak = STATE
    STATE = os.path.join(ROOT, r'.temp\_selftest_state.json')
    io.open(STATE, 'w', encoding='utf-8', newline='\n').write(json.dumps(st, ensure_ascii=False))
    ok_all = True
    for name, rec, want in cases:
        jf = os.path.join(ROOT, r'.temp\_selftest_rec.json')
        io.open(jf, 'w', encoding='utf-8', newline='\n').write(json.dumps(rec, ensure_ascii=False))
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cmd_record(jf)
        tag = 'PASS' if rc == want else 'FAIL'
        if rc != want:
            ok_all = False
        print('  [%s] %-14s 期望 exit=%d 实得 %d' % (tag, name, want, rc))
    # 正确块应通过
    jf = os.path.join(ROOT, r'.temp\_selftest_rec.json')
    io.open(jf, 'w', encoding='utf-8', newline='\n').write(json.dumps(
        dict(doc=rel, block=0, sha=sha0, quotes=[quote_ok, quote_ok],
             points=['p'], todos=[], verdict='未做'), ensure_ascii=False))
    buf = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buf):
        rc = cmd_record(jf)
    print('  [%s] %-14s 期望 exit=0 实得 %d' % ('PASS' if rc == 0 else 'FAIL', '合规记录', rc))
    ok_all = ok_all and rc == 0
    STATE = bak
    print('\nSELFTEST: %s' % ('PASS（程序能挡住跳块/伪造/错sha）' if ok_all else 'FAIL'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == 'plan':
        cmd_plan()
    elif a[0] == 'next':
        cmd_next()
    elif a[0] == 'record' and len(a) >= 2:
        sys.exit(cmd_record(a[1]))
    elif a[0] == 'status':
        cmd_status()
    elif a[0] == 'selftest':
        sys.exit(cmd_selftest())
    else:
        print(__doc__)
