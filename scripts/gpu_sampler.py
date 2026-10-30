# -*- coding: utf-8 -*-
"""谷期 GPU 采样器（I3b S3b）：每 N 秒记 GPU util / mem util / vram / SM 时钟 -> work\\data\\gpu_samples.csv。

用法：python scripts\\gpu_sampler.py [--seconds 900] [--interval 1]
判读（与 step profile slow / ingraph 行按时间对齐）——TELE 校准（2026-10-14）：
  ★ 先读【稳态基线】（正常 decode 时采 10-30s，预期 GPU util 显著非零 65-85%、SM 时钟升满）：
     若稳态 ≈0，则"launch ≈ 图执行"的前提要重检。
  谷期三分：
    GPU≈100% + SM 满频           -> A  图执行本体慢（用 ingraph 四区间定位 ingress/target/draft/egress）
    GPU≈0%  / SM 掉频            -> B  提交/驱动/换页侧卡（WDDM 排队、页调入、降频）
    GPU 100% + PCIe 高            -> A' 图内读 host 页（查掩码与实际读集一致性）
  可并行 nvidia-smi dmon -s pucm 看 PCIe rx/tx。
"""
import argparse
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'work', 'data', 'gpu_samples.csv')


def sample():
    try:
        out = subprocess.run(
            ['nvidia-smi',
             '--query-gpu=utilization.gpu,utilization.memory,memory.used,clocks.current.sm,pstate',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=8)
        parts = [p.strip() for p in out.stdout.strip().split(',')]
        if len(parts) >= 5:
            return parts
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=900)
    ap.add_argument('--interval', type=float, default=1.0)
    args = ap.parse_args()
    new = not os.path.exists(OUT)
    utils = []
    with open(OUT, 'a', encoding='utf-8') as handle:
        if new:
            handle.write('time,gpu_util_pct,mem_util_pct,vram_used_mib,sm_mhz,pstate\n')
        end = time.time() + args.seconds
        n = 0
        while time.time() < end:
            s = sample()
            if s:
                handle.write('%s,%s,%s,%s,%s,%s\n' % (time.strftime('%H:%M:%S'), s[0], s[1], s[2], s[3], s[4]))
                handle.flush()
                try:
                    utils.append(float(s[0]))
                except ValueError:
                    pass
                n += 1
            time.sleep(args.interval)
    print('samples=%d -> %s' % (n, OUT))
    if utils:
        print('gpu_util: avg=%.1f%% min=%.0f%% max=%.0f%%'
              % (sum(utils) / len(utils), min(utils), max(utils)))


if __name__ == '__main__':
    main()
