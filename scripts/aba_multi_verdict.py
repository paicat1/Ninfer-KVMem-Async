# -*- coding: utf-8 -*-
"""多探针 A-B-A 判读器：读 .temp\\pdl_aba_<tag>.txt，按臂统计"谷读数占比"，输出 ON vs OFF 判决。
   臂形状：45KB/200tok ⇒ 健康带 154–163、谷带 ~21；谷判据 decode < 100（形状内安全）。"""
import io
import re
import sys

tag = sys.argv[1] if len(sys.argv) > 1 else 'night0122'
P = r'J:\ninfer-kvmem\.temp\pdl_aba_%s.txt' % tag
lines = io.open(P, encoding='utf-8', errors='replace').read().splitlines()

arms = []
cur = None
for ln in lines:
    m = re.search(r'\|\s*MULTIPROBE\s+n=(\d+)\s*::(.*)$', ln)
    if m:
        name = ''
        nm = re.search(r'(pdl_\w+)\s*\|\s*MULTIPROBE', ln)
        if nm:
            name = nm.group(1)
        cur = {'name': name, 'mode': '?', 'dec': [float(d) for d in re.findall(r'decode=([\d.]+)', m.group(2))]}
        arms.append(cur)
        continue
    if cur is not None:
        m3 = re.search(r'(ENABLED|DISABLED|START-FAILED)', ln)
        if m3 and cur['mode'] == '?':
            cur['mode'] = m3.group(1)
            continue
        m4 = re.search(r'run 1 round 1\s+[\d.]+s\s+decode=([\d.]+)', ln)
        if m4:
            cur['dec'].append(float(m4.group(1)))

VALLEY = 100.0
print('== 台账 %s 的臂统计（谷判据 decode<%.0f）==' % (tag, VALLEY))
on_all, off_all = [], []
for a in arms:
    dec = a['dec']
    v = [d for d in dec if d < VALLEY]
    print('  %-10s %-9s n=%-3d 健康=%d 谷=%d  %s' % (a['name'], a['mode'], len(dec), len(dec) - len(v), len(v),
                                                     ('min=%.1f max=%.1f' % (min(dec), max(dec))) if dec else ''))
    if a['mode'] == 'ENABLED':
        on_all += dec
    elif a['mode'] == 'DISABLED':
        off_all += dec

def frac(x):
    return (len([d for d in x if d < VALLEY]) / len(x)) if x else float('nan')

print('\n== 汇总 ==')
print('  ON  臂: n=%d  谷占比=%.1f%%  中位=%.1f' % (len(on_all), 100 * frac(on_all), sorted(on_all)[len(on_all) // 2] if on_all else -1))
print('  OFF 臂: n=%d  谷占比=%.1f%%  中位=%.1f' % (len(off_all), 100 * frac(off_all), sorted(off_all)[len(off_all) // 2] if off_all else -1))
print('\n== 判定 ==')
if not on_all or not off_all:
    print('  数据不足（缺 ON 或缺 OFF 臂）')
elif frac(on_all) > 0.3 and frac(off_all) == 0.0:
    print('  **PDL 因果成立**：谷读数只出现在 ON 臂（%.0f%% vs 0%%）' % (100 * frac(on_all)))
elif frac(on_all) == 0.0 and frac(off_all) == 0.0:
    print('  无效捕获：两臂都没谷（窗内无谷）⇒ 等下一窗')
elif frac(on_all) == 0.0 and frac(off_all) > 0.3:
    print('  **反常**：谷只在 OFF 出现 ⇒ 与 PDL 假设相反（需复查环境/顺序效应）')
else:
    print('  混合：ON %.0f%% / OFF %.0f%% ⇒ 需更多臂或更长采样' % (100 * frac(on_all), 100 * frac(off_all)))
