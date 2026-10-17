# -*- coding: utf-8 -*-
r"""check_refs.py -- 引用完整性检查器（2026-10-17 立）

为什么有它：本仓曾把引擎件误删，**只改了 1 处引用、漏了 10 处**（deploy_engine.ps1 / engine_registry.json /
9 个 .bat / 启动器），而且**过了很久没人发现**（"删了也发现不了"）。本脚本把这类断链变成**可自动检测**。

用法：
    python -X utf8 scripts/check_refs.py            # 检查，返回码 0=全通 / 1=有缺失
    python -X utf8 scripts/check_refs.py --quiet     # 只打印缺失

扫描范围：仓内**可执行/配置**类文件（.ps1 .bat .cmd .py .json），排除 .git/.temp/_trash/build/node_modules。
识别两类路径：
  ① 绝对路径   J:\ninfer-kvmem\...
  ② 仓内相对路径  engine\... / scripts\... / models\... / docs\... （带反斜杠或正斜杠）
判定：路径指向**带扩展名的文件**时做存在性检查；指向目录时检查目录存在。
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = ('.ps1', '.bat', '.cmd', '.py', '.json')
SKIP_DIRS = {'.git', '.temp', '_trash', 'build', 'node_modules', '__pycache__', 'logs', 'models',
             'archive',   # archive/ = 历史归档，允许引用旧路径（不参与门禁）
             'engine-src', 'official-repo', 'refs'}   # vendored 第三方源码树：其相对路径指它们自己的树
ABS = re.compile(r'J:\\ninfer-kvmem\\([^\s"\'`<>|*?]+)')
REL = re.compile(r'(?<![\w:\\])(engine|scripts|docs|patches|baselines|tools)\\([^\s"\'`<>|*?]+)')


def norm(p):
    return p.replace('/', os.sep).rstrip('.,);')


def _local_only():
    """只在本机、不入库的工具（structure.json: local_only_tools）—— 引用它们不算断链。"""
    try:
        j = json.load(io.open(os.path.join(ROOT, 'structure.json'), encoding='utf-8'))
        return set(x.replace('/', os.sep) for x in j.get('local_only_tools', {}).get('files', []))
    except Exception:
        return set()


def main():
    quiet = '--quiet' in sys.argv
    missing, checked = [], 0
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(EXTS):
                continue
            p = os.path.join(root, fn)
            if os.path.basename(p) == 'check_refs.py':
                continue
            try:
                t = io.open(p, encoding='utf-8', errors='replace').read()
            except Exception:
                continue
            for i, line in enumerate(t.splitlines(), 1):
                if line.lstrip().startswith('#'):
                    continue
                for m in list(ABS.finditer(line)) + list(REL.finditer(line)):
                    frag = norm(m.group(0) if m.re is ABS else (m.group(1) + '\\' + m.group(2)))
                    # 过滤：模板串（%s / {0}）、临时目标（.temp\）、纯描述性片段
                    if '%' in frag or '{' in frag or '\\' + '.temp' in frag or '.temp\\' in frag:
                        continue
                    if frag.count('\\') == 0:
                        continue
                    full = frag if os.path.isabs(frag) else os.path.join(ROOT, frag)
                    if not os.path.splitext(full)[1] and not os.path.isdir(full):
                        continue
                    checked += 1
                    if not os.path.exists(full):
                        if os.path.normpath(full) in _local_only() or frag.replace('/', os.sep) in _local_only():
                            if not quiet:
                                print('NOTICE: 引用本地件（不入库，optional）：%s' % frag)
                            continue
                        missing.append((os.path.relpath(p, ROOT), i, frag))
    if not quiet:
        print('扫描可执行/配置文件 · 检查引用 %d 条' % checked)
    if missing:
        print('\n❌ 断链 %d 条：' % len(missing))
        for f, i, frag in missing:
            print('   %-46s L%-4d %s' % (f[:46], i, frag[:90]))
        return 1
    if not quiet:
        print('✅ 无断链')
    return 0


if __name__ == '__main__':
    sys.exit(main())
