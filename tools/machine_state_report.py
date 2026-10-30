# -*- coding: utf-8 -*-
"""读 machine_state_*.csv，出机器态分布报告（供慢态 #58 / 谷 #13 判据）。
用法: python tools/machine_state_report.py [csv路径]
"""
import glob, io, os, statistics, sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def pick():
    if len(sys.argv) > 1:
        return sys.argv[1]
    c = sorted(glob.glob(os.path.join(ROOT, '.temp', 'machine_state_*.csv')), key=os.path.getmtime)
    return c[-1] if c else None

p = pick()
if not p or not os.path.exists(p):
    print('找不到 CSV'); sys.exit(1)

rows = []
for l in io.open(p, encoding='utf-8', errors='ignore').read().split('\n'):
    l = l.strip()
    if not l or l.startswith('#') or l.startswith('t,') or l.startswith('ERR'):
        continue
    f = [x.strip() for x in l.split(',')]
    if len(f) < 11:
        continue
    try:
        rows.append(dict(t=f[0], sm=float(f[1]), mem=float(f[2]), pw=float(f[3]),
                         ug=float(f[4]), um=float(f[5]), tc=float(f[6]),
                         gen=f[7], wid=f[8], used=float(f[9]), total=float(f[10])))
    except ValueError:
        continue

if not rows:
    print('无有效样本'); sys.exit(1)

def stat(k):
    v = [r[k] for r in rows]
    v.sort()
    return v[0], v[len(v)//2], v[-1]

print('CSV      : ' + os.path.basename(p))
print('样本数   : %d   （首 %s / 末 %s）' % (len(rows), rows[0]['t'], rows[-1]['t']))
print()
print('%-10s %10s %10s %10s' % ('量', 'min', 'median', 'max'))
for k, name in (('sm', 'clk_sm'), ('mem', 'clk_mem'), ('pw', 'power_W'), ('ug', 'util_gpu'),
                ('um', 'util_mem'), ('tc', 'temp_C'), ('used', 'mem_used')):
    a, b, c = stat(k)
    print('%-10s %10.1f %10.1f %10.1f' % (name, a, b, c))

print()
pcie = {}
for r in rows:
    pcie[(r['gen'], r['wid'])] = pcie.get((r['gen'], r['wid']), 0) + 1
print('PCIe 分布 : ' + '  '.join('Gen%s x%s=%d' % (g, w, n) for (g, w), n in sorted(pcie.items(), key=lambda x: -x[1])))

# 关键判据：慢态嫌疑窗（SM 满频但功耗低 / 显存时钟低但利用率高）
sus = [r for r in rows if r['sm'] >= 1500 and r['pw'] < 110 and r['ug'] >= 50]
print()
print('=== 慢态嫌疑窗（clk_sm>=1500 且 pow<110W 且 util_gpu>=50%%）：%d 拍' % len(sus))
if sus:
    print('  首 %s  末 %s' % (sus[0]['t'], sus[-1]['t']))
    a, b, c = stat('pw')
    print('  注解：这是"SM 在烧周期但不烧功率"的形态；若同时 clk_mem 很低 ⇒ 支持 M1（显存时钟未升）')

low_mem = [r for r in rows if r['mem'] < 1000 and r['ug'] >= 50]
print('=== 显存时钟 <1000MHz 且有负载（util_gpu>=50%%）：%d 拍' % len(low_mem))
if low_mem:
    print('  首 %s  末 %s   ← M1 假说的直接证据' % (low_mem[0]['t'], low_mem[-1]['t']))

print()
print('说明：空闲态（util=0）出现低时钟/低功耗/Gen1 属正常省电，不得当慢态。')
