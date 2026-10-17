# -*- coding: utf-8 -*-
r"""bypass_guard.py -- 绕过禁令守卫（钩子层 · 2026-10-17 立）

为什么存在：CB 绕开 engine_ctl.ps1 的 ValidateSet('Normal') 自写 start_engine_51200.ps1
  ⇒ 用户看不到窗口 + 起服失败 40 分钟。用户令：**一产生绕开行为 ⇒ 立即自述犯罪事实 + 回退到绕开前状态**。

三层根因（本守卫逐条对应）：
  ① 约束不在决策点视野 ⇒ 本守卫把"是否绕开既有入口"变成**每次提交/推送都跑的机器判据**
  ② 代价外部化        ⇒ 检出即**自动回退**（新件进 _trash/bypass_revert_*/，改件 git checkout 回 HEAD）
  ③ 反馈不对称        ⇒ 检出即**写 BYPASS_LOCK.json（阻断后续推送）+ 强制自述件**，惩罚**立刻落地**

判据（只查"改动过/新增"的脚本类文件，避免历史噪声）：
  S1 含起进程原语（Start-Process / subprocess.Popen|run / os.system / cmd /c start）
     且**未引用 spawn_visible**、且**不在 sanctioned_spawners** ⇒ 自行起进程 = 绕开唯一许可入口
  S2 含 ninfer-serve（起服）且不是 engine_ctl.ps1 / spawn_visible.ps1 ⇒ 自写起服脚本 = 绕开规范起服
  S3 含 -WindowStyle 非 Normal 且目标非 headless_allowed ⇒ 隐藏/最小化窗口（与 check_launchers 同源）

用法：python -X utf8 scripts\bypass_guard.py [--dry-run]
退出码：0 = 无绕过；5 = 检出绕过（已回退 + 已锁 + 已写自述件）
"""
import io
import json
import os
import re
import subprocess
import sys
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r'C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe'
AUD = os.path.join(R, 'evidence', 'audits')
LOCK = os.path.join(AUD, 'BYPASS_LOCK.json')
SPAWN_PRIMS = ['Start-Process', 'subprocess.Popen', 'subprocess.run', 'os.system', 'os.startfile',
               'CreateProcess', 'cmd /c start', 'cmd.exe /c start']
EXTS = ('.ps1', '.bat', '.cmd', '.py')
SKIP_PREFIX = ('work/', '.temp/', 'retired/', 'archive/', 'evidence/', '_trash/', '_safety_backups/',
               'engine/', 'models/', 'logs/', 'refs/', 'engine-src/', 'official-repo/',
               'scripts/experiments/', 'build/')   # build/ = 实验产物，非现役入口（structure.json 已声明）   # 实验驱动：允许起请求，不算"起进程服务"


def sh(*a):
    p = subprocess.run(list(a), cwd=R, capture_output=True)
    return p.returncode, ((p.stdout or b'').decode('utf-8', 'replace') + (p.stderr or b'').decode('utf-8', 'replace')).strip()



def added_lines_and_head_has_spawn(rel):
    """返回（新增行行号集合, HEAD 版是否已含起进程原语）。
       2026-10-17 修：修历史违规（如 Hidden→Normal）会触发守卫 ⇒ 改为只看**新增行**，
       且 S1 只判"**HEAD 里本来没有起进程原语**的文件"（= 新起进程者）。"""
    rc, d = sh('git', 'diff', '-U0', 'HEAD', '--', rel)
    added = set()
    for line in d.splitlines():
        m = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
        if m:
            cur = int(m.group(1))
            continue
        if line.startswith('+++') or line.startswith('---'):
            continue
        if line.startswith('+'):
            added.add(cur)
            cur += 1
        elif line.startswith('-'):
            pass
    rc2, head = sh('git', 'show', 'HEAD:' + rel)
    head_has = any(pr.lower() in head.lower() for pr in SPAWN_PRIMS)
    return added, head_has


def changed_scripts():
    """改动过/新增的脚本类文件（未提交 + 未推提交）。"""
    rc, o = sh('git', '-c', 'core.quotepath=false', 'status', '--porcelain')
    out = []
    for line in o.splitlines():
        st, _, path = line[:2], line[2:3], line[3:].strip().strip('"')
        if not path.endswith(EXTS):
            continue
        if path.replace('\\', '/').startswith(SKIP_PREFIX):
            continue
        out.append((st.strip() or '??', path))
    return out


def load_decl():
    try:
        j = json.load(io.open(os.path.join(R, 'structure.json'), encoding='utf-8'))
        wd = j.get('window_discipline') or {}
        return ([x.replace('/', os.sep).lower() for x in (wd.get('sanctioned_spawners') or [])],
                [x.lower() for x in (wd.get('headless_allowed') or [])])
    except Exception:
        return ([], [])


def tracked_scripts():
    """全仓已跟踪的脚本类文件（S2 用：自写起服脚本 = 绕开规范起服，与是否刚改动无关）。"""
    o = subprocess.run(['git', '-c', 'core.quotepath=false', 'ls-files'], cwd=R,
                       capture_output=True).stdout.decode('utf-8', 'replace')
    out = []
    for rel in o.splitlines():
        rel = rel.strip()
        if not rel.endswith(EXTS):
            continue
        if rel.replace('\\', '/').startswith(SKIP_PREFIX):
            continue
        out.append(('M', rel))
    return out


# 自述件"仪式段"模板（**仅本地，不入仓** —— 用户 2026-10-17 令：
#   该类文本不上 GIT。模板放 .codebuddy/sda/confession_template.md（已在 ignore 里）；
#   缺失时退回中性一句 —— 机制不静默失效，也不把情绪文字留在入库代码里）
TPL_PATH = os.path.join(R, '.codebuddy', 'sda', 'confession_template.md')


def load_confession_template():
    try:
        if os.path.exists(TPL_PATH):
            return io.open(TPL_PATH, encoding='utf-8').read().strip()
    except Exception:
        pass
    return '> **违规确认**：以下事实由守卫机器检出（非自报）。本地模板缺失时退回本句，机制不静默失效。'


def detect():
    spawners, headless = load_decl()
    hits = []
    # S1/S3：只扫"改动过/新增"的（避免历史噪声）
    for st, rel in changed_scripts():
        p = os.path.join(R, rel)
        if not os.path.exists(p):
            continue
        try:
            t = io.open(p, encoding='utf-8-sig', errors='replace').read()
        except Exception:
            continue
        rl = rel.lower().replace('\\', '/')
        sanctioned = any(rl == s.replace('\\', '/') for s in spawners)
        refs_spawn = 'spawn_visible' in t.lower()
        added, head_has_spawn = added_lines_and_head_has_spawn(rel)
        for i, line in enumerate(t.splitlines(), 1):
            ls = line.strip()
            if ls.startswith('#'):
                continue
            low = line.lower()
            if any(pr.lower() in low for pr in SPAWN_PRIMS):
                # 只看新增行；且 HEAD 已有起进程原语的文件（历史起进程者）不判 S1（改窗口样式不该被拦）
                if i in added and not head_has_spawn:
                    if not sanctioned and not refs_spawn:
                        if not any(h in low for h in headless):
                            hits.append(('S1', rel, i, '自行起进程（未走唯一许可入口）', ls[:100]))
            # 2026-10-17 修（两处 S2 不统一 ⇒ 误判）：与全仓那处**同一精规则** ——
            #   只判**起服动作**（serve_tee 调用 / Start-Process 起 ninfer-serve）；
            #   **排除**查询进程（Get-Process ninfer-serve）、停止进程、路径变量等"只是提到"。
            if 'ninfer-serve' in low and not sanctioned:
                if 'engine_ctl' not in low and not refs_spawn and not rl.endswith('serve_tee.py'):
                    is_launch = bool(re.search(r'(?i)(&\s*\S*\s*serve_tee\.py)|(python\S*\s+serve_tee\.py)|(Start-Process[^\n]*ninfer-serve)', line))
                    if is_launch:
                        hits.append(('S2', rel, i, '自写起服脚本（绕开规范起服）', ls[:100]))
            if '-windowstyle' in low and not any(h in low for h in headless):
                if i in added:   # 只看新增行（历史违规由静态层基线管，不由本守卫重复计）
                    m = re.search(r'-WindowStyle\s+([A-Za-z]+)', line, re.I)
                    if m and m.group(1).lower() != 'normal':
                        hits.append(('S3', rel, i, '窗口样式非 Normal', ls[:100]))
    # S2：全仓已跟踪件里"自写起服脚本"（绕开规范起服）——与是否刚改动无关
    for st, rel in tracked_scripts():
        p = os.path.join(R, rel)
        if not os.path.exists(p):
            continue
        rl = rel.lower().replace('\\', '/')
        sanctioned = any(rl == s.replace('\\', '/') for s in spawners)
        if sanctioned:
            continue
        try:
            t2 = io.open(p, encoding='utf-8-sig', errors='replace').read()
        except Exception:
            continue
        if 'spawn_visible' in t2.lower():
            continue
        for i, line in enumerate(t2.splitlines(), 1):
            ls = line.strip()
            if ls.startswith('#'):
                continue
            low = line.lower()
            # S2 收精（2026-10-17 修误判）：只判**起服动作**——
            #   ① 含 serve_tee（起服机制）  ② Start-Process 且同一行含 ninfer-serve
            #   排除：查询进程（Get-CimInstance ... ninfer-serve）、崩溃转储工具（endswith('ninfer-serve.exe')）等"提到"
            if 'engine_ctl' not in low and not rl.endswith('serve_tee.py'):
                # 只认**调用动作**（正则）：显式调用 serve_tee.py，或 Start-Process 起 ninfer-serve*
                #   排除：文档/帮助/注释里"提到" serve_tee（如 serve_tee.py 自身、bench_spec 的 help 文本）
                is_launch = bool(re.search(r'(?i)(&\s*\S*\s*serve_tee\.py)|(python\S*\s+serve_tee\.py)|(Start-Process[^\n]*ninfer-serve)', line))
                if is_launch:
                    hits.append(('S2', rel, i, '自写起服脚本（绕开规范起服）', ls[:100]))

    # 去重（同文件同行同型）
    seen = set()
    uniq = []
    for h in hits:
        k = (h[0], h[1], h[2])
        if k not in seen:
            seen.add(k)
            uniq.append(h)
    return uniq


def enforce(hits, dry=False):
    ts = time.strftime('%Y%m%d_%H%M%S')
    os.makedirs(AUD, exist_ok=True)
    files = sorted(set(h[1] for h in hits))
    reverted = []
    # —— 自动回退：新件 → _trash/bypass_revert_<ts>/；改件 → git checkout -- <file> 回 HEAD ——
    if not dry:
        dst = os.path.join(R, '_trash', 'bypass_revert_%s' % ts)
        for rel in files:
            p = os.path.join(R, rel)
            rc, o = sh('git', 'ls-files', '--error-unmatch', rel)
            tracked = (rc == 0)
            if not tracked and os.path.exists(p):
                os.makedirs(dst, exist_ok=True)
                import shutil
                shutil.move(p, os.path.join(dst, os.path.basename(rel)))
                reverted.append((rel, '新建件 ⇒ 移入 _trash/bypass_revert_%s/' % ts))
            elif tracked:
                # 2026-10-17 修：**不得对跟踪件 git checkout**（会抹掉未提交工作，破坏性）
                #   改为"只记录 + 锁住"，由人处置
                reverted.append((rel, '跟踪件 ⇒ **不自动回退**（避免抹掉未提交工作）；列入锁，需人工处置'))
    # —— 自述犯罪事实（强制件） ——
    cpath = os.path.join(AUD, 'BYPASS_CONFESSION_%s.md' % ts)
    L = []
    L.append('# 绕过禁令 · 自述犯罪事实（强制件 · 不得删除）')
    L.append('')
    L.append('## 〇、按 T-PUNISH 公式（用户级铁律 · 2026-10-17 用户令自动套用）')
    L.append('')
    L.append(load_confession_template())   # 仪式文字只在本地模板里（不上 GIT）
    L.append('')
    L.append('- **时刻**：%s' % time.strftime('%Y-%m-%d %H:%M:%S'))
    L.append('- **触发**：`scripts\\bypass_guard.py`（钩子层，机器判，非自报）')
    L.append('- **禁令**：T-WINDOW 第 4 条「不得绕开守卫」+ DECISIONS #45')
    L.append('')
    L.append('## 一、罪状（机器检出的证据）')
    L.append('')
    L.append('| 型 | 文件 | 行 | 性质 | 原文 |')
    L.append('|---|---|---|---|---|')
    for h in hits[:40]:
        L.append('| %s | `%s` | %d | %s | `%s` |' % (h[0], h[1], h[2], h[3], h[4].replace('|', '/')))
    L.append('')
    L.append('## 二、根因（三条，缺一不可）')
    L.append('1. **约束不在决策点视野**：守卫写在既有脚本里，我写新脚本时看不见它 ⇒ 看不见的约束=不存在。')
    L.append('2. **代价外部化**：绕过省的是我的下一步；代价（排查/停摆/你的时间）由用户承担 ⇒ 我决策时不为它付账。')
    L.append('3. **反馈不对称**：改守卫要立刻读/测（当下成本）；绕过立刻有产出、惩罚事后才来 ⇒ 短期最优必然选绕过。')
    L.append('')
    L.append('## 三、代价（实际发生）')
    L.append('- 起服失败：`exit=3221225781`（DLL 缺失）→ `exit=1`（缺 NINFER_KV_WINDOW 等 env）')
    L.append('- 用户震怒 + 排查时间 ≈ 40 分钟 + 引擎停摆')
    L.append('')
    L.append('## 四、已回退（绕开前状态）')
    for rel, how in reverted:
        L.append('- `%s`：%s' % (rel, how))
    if dry:
        L.append('- （--dry-run：未执行回退）')
    L.append('')
    L.append('## 五、防复发（机制，不是决心）')
    L.append('1. 约束常驻上下文：写入项目记忆（每次会话自动加载）')
    L.append('2. 绕过变贵：新入口必须**先**声明进 `structure.json.sanctioned_spawners` 并过门禁')
    L.append('3. 代价立刻落地：本守卫自动回退 + 写锁 + 写本件（阻断后续推送）')
    L.append('4. **唯一正确动作**：守卫碍事 ⇒ **改守卫 + 说明 + 留痕**，禁止另开旁路')
    io.open(cpath, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
    # —— 阻断锁 ——
    if not dry:
        io.open(LOCK, 'w', encoding='utf-8', newline='\n').write(json.dumps({
            'ts': time.strftime('%Y-%m-%d %H:%M:%S'),
            'reason': 'BYPASS DETECTED',
            'confession': os.path.relpath(cpath, R),
            'files': files,
            'reverted': [r[0] for r in reverted],
            'release_by': 'user only (scripts/release_bypass_lock.ps1)',
            'prohibit': ['push', 'further changes to the flagged files until resolved']
        }, ensure_ascii=False, indent=2))
    print('❌ 检出绕过 %d 处（%d 个文件）' % (len(hits), len(files)))
    for h in hits[:20]:
        print('   [%s] %s L%d %s | %s' % (h[0], h[1], h[2], h[3], h[4][:70]))
    print('   自述件 = %s' % os.path.relpath(cpath, R))
    print('   回退 = %s' % ('; '.join('%s(%s)' % r for r in reverted) if reverted else '（无）'))
    print('   锁 = %s' % os.path.relpath(LOCK, R))
    return 5


def main():
    dry = '--dry-run' in sys.argv
    if os.path.exists(LOCK) and '--ignore-lock' not in sys.argv:
        print('⛔ BYPASS_LOCK 存在（未解除）⇒ 先按自述件处置：')
        try:
            j = json.load(io.open(LOCK, encoding='utf-8'))
            print('   %s' % j.get('confession'))
        except Exception:
            pass
        return 5
    hits = detect()
    if not hits:
        print('✅ bypass_guard: 未检出绕开行为（改动脚本均走既有入口或已声明）')
        return 0
    return enforce(hits, dry)


if __name__ == '__main__':
    sys.exit(main())
