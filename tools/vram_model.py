# -*- coding: utf-8 -*-
"""vram_model.py -- 显存需求账（启动器用；口径经本机日志标定，非估算）。

引擎自报口径（`capacity |` 行）：`权重 + 池 + runtime + graph + free`，其中 free 是**加载后**余量。
本模型计算**加载前需求** `need = 权重 + 池 + runtime + graph`，再由 `nvidia-smi` 实测当场可用量，
给出 `余量 = 可用 − need` 与判定。标定样本（本机 20+ 次起服）：need 与引擎自报口径吻合 ±0.1 GiB。

口径（同《精算-显存账与KV池》§0/§1）：1 页 = 64 token；每页 = 该精度 (K+V+scales) × 16 全注意力层。
  rk2v4-e8 0.83 MiB/页 | rk4v4-e8/nvfp4 1.11 | k8v4/rk8v4 1.59 | int8/fp8 2.11 | bf16 4.08

用法：
  python tools\\vram_model.py --calibrate
  python tools\\vram_model.py --pool 32768 --dtype rk4v4-e8 [--used-mib 1000] [--json]
"""
import argparse
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'J:\ninfer-kvmem'

PAGE_MIB = {
    'rk2v4-e8': 0.83, 'rk4v4': 1.11, 'rk4v4-e8': 1.11, 'nvfp4': 1.11,  # rk4v4 未实测：借 rk4v4-e8 作保守上界
    'k8v4': 1.59, 'rk8v4': 1.59, 'int8': 2.11, 'fp8': 2.11, 'bf16': 4.08,
}
TOKENS_PER_PAGE = 64
DEFAULT_RUNTIME_GIB = 1.66
DEFAULT_WEIGHTS_GIB = 12.30
REF_CONTEXT = 60000.0   # 谷负担参考上下文（《精算》§7.4 场景）

RE_CAP = re.compile(r'capacity \| KV ([\d,]+) tokens, ([A-Za-z0-9_\-]+), (\w+) \| pages ([\d,]+)/([\d,]+) \| runtime ([\d.]+) GiB \| free ([\d.]+) MiB')
RE_W = re.compile(r'loading weights \| ([\d.]+) GiB')
RE_G = re.compile(r'--cuda-graph-allowance-mib\s+(\d+)')


def valley_burden_mib(pool_tokens, dtype, context=REF_CONTEXT):
    """§7.4 口径：谷负担 ∝ (上下文 − 池) × 每 token 字节。单位 MiB。"""
    page = PAGE_MIB[dtype]
    overflow = max(0.0, context - pool_tokens)
    return overflow * (page / TOKENS_PER_PAGE)


def estimate(pool_tokens, dtype, weights_gib=DEFAULT_WEIGHTS_GIB, graph_mib=64,
             runtime_gib=DEFAULT_RUNTIME_GIB, context=262144):
    page = PAGE_MIB.get(dtype)
    if page is None:
        raise SystemExit('unknown kv-dtype: %s' % dtype)
    pages = pool_tokens / float(TOKENS_PER_PAGE)
    pool_gib = pages * page / 1024.0
    need = weights_gib + pool_gib + runtime_gib + graph_mib / 1024.0
    return {
        'pool_tokens': pool_tokens, 'dtype': dtype, 'page_mib': page, 'pages': pages,
        'weights_gib': weights_gib, 'pool_gib': pool_gib, 'runtime_gib': runtime_gib,
        'graph_gib': graph_mib / 1024.0, 'need_gib': need, 'context': context,
        'burden_mib': valley_burden_mib(pool_tokens, dtype),
    }


def calibrate():
    print('== 标定：`权重 + 池 + runtime + graph + free` 反推可用预算 ==')
    print('%-40s %-10s %7s %6s %7s %6s %7s %9s' % ('log', 'dtype', 'pool', 'pages', 'runtime', 'graph', 'free', '预算 GiB'))
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'logs', '*.log'))):
        name = os.path.basename(path)
        weights = None
        graph = None
        try:
            with open(path, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    m = RE_W.search(line)
                    if m:
                        weights = float(m.group(1))
                    m = RE_G.search(line)
                    if m:
                        graph = int(m.group(1))
                    m = RE_CAP.search(line)
                    if m and weights:
                        pool = int(m.group(1).replace(',', ''))
                        dtype = m.group(2)
                        pages = int(m.group(4).replace(',', ''))
                        runtime = float(m.group(6))
                        free_mib = float(m.group(7))
                        page = PAGE_MIB.get(dtype)
                        if page is None:
                            continue
                        budget = weights + pages * page / 1024.0 + runtime + \
                            (graph if graph is not None else 64) / 1024.0 + free_mib / 1024.0
                        rows.append((name, dtype, pool, pages, runtime, graph or 64, free_mib, budget))
                        break
        except OSError:
            continue
    for row in rows[:24]:
        print('%-40s %-10s %7d %6d %7.2f %6d %7.0f %9.3f' % row)
    if rows:
        budgets = sorted(r[7] for r in rows)
        print('\n样本 %d；可用预算 %.3f .. %.3f GiB（中位 %.3f，波动 %.2f）'
              % (len(budgets), budgets[0], budgets[-1], budgets[len(budgets) // 2],
                 budgets[-1] - budgets[0]))
        print('=> 可用预算随桌面/WDDM 状态波动 ~0.6 GiB：启动器必须实测当场值。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--calibrate', action='store_true')
    parser.add_argument('--pool', type=int, default=65536)
    parser.add_argument('--dtype', default='rk2v4-e8')
    parser.add_argument('--weights', type=float, default=DEFAULT_WEIGHTS_GIB)
    parser.add_argument('--graph', type=int, default=64)
    parser.add_argument('--runtime', type=float, default=DEFAULT_RUNTIME_GIB)
    parser.add_argument('--context', type=int, default=262144)
    parser.add_argument('--used-mib', type=int, default=-1)
    parser.add_argument('--total-mib', type=int, default=16303)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.calibrate:
        calibrate()
        return
    est = estimate(args.pool, args.dtype, args.weights, args.graph, args.runtime, args.context)
    free_gib = (args.total_mib - args.used_mib) / 1024.0 if args.used_mib >= 0 else None
    margin = (free_gib - est['need_gib']) if free_gib is not None else None
    verdict = '-' if margin is None else ('OK' if margin > 0.35 else ('紧张' if margin > 0.05 else '不够'))
    if args.json:
        print(json.dumps({'need_gib': round(est['need_gib'], 2), 'free_gib': None if free_gib is None else round(free_gib, 2),
                          'margin_gib': None if margin is None else round(margin, 2), 'verdict': verdict,
                          'burden_mib': round(est['burden_mib'], 0), 'pages': est['pages'],
                          'pool_gib': round(est['pool_gib'], 2)}, ensure_ascii=False))
        return
    print('显存需求账（加载前需求 = 权重 + 池 + runtime + graph）')
    print('  权重（上卡）            %6.2f GiB' % est['weights_gib'])
    print('  KV 池 %6d tok %-10s %6.2f GiB（%d 页 × %.2f MiB）'
          % (est['pool_tokens'], est['dtype'], est['pool_gib'], est['pages'], est['page_mib']))
    print('  运行时/工作区          %6.2f GiB' % est['runtime_gib'])
    print('  CUDA graph 配额        %6.2f GiB' % est['graph_gib'])
    print('  ------------------------------------')
    print('  合计需求               %6.2f GiB' % est['need_gib'])
    if free_gib is not None:
        print('  实测可用               %6.2f GiB（nvidia-smi：已用 %d / %d MiB）'
              % (free_gib, args.used_mib, args.total_mib))
        print('  余量                   %+6.2f GiB   【%s】' % (margin, verdict))
    print('  谷负担（60K 上下文）   %6.0f MiB（∝(60000−池)×每token字节；现状 65536+rk2v4 = 0）'
          % est['burden_mib'])


if __name__ == '__main__':
    main()
