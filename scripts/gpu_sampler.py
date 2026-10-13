# -*- coding: utf-8 -*-
"""谷期 GPU 采样器（I3b S3b）：每 N 秒记 GPU util / mem util / 显存占用 → .temp\\gpu_samples.csv。

用法：python scripts\\gpu_sampler.py [--seconds 900] [--interval 1]
判读（与 step profile slow 行按时间对齐）：
  GPU≈100%      -> 图执行本体慢（去图里找随上下文增长的项；含"图内读 host 页"嫌疑）
  GPU≈0%        -> 提交/驱动/换页侧卡（WDDM 排队、页调入）
  另可并行跑 nvidia-smi dmon -s pucm 看 PCIe rx/tx（若卡支持）区分 PCIe 流量。
"""
import argparse
import os
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, '.temp', 'gpu_samples.csv')


def sample():
    try:
        out = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,utilization.memory,memory.used',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=8)
        parts = [p.strip() for p in out.stdout.strip().split(',')]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seconds', type=int, default=900)
    ap.add_argument('--interval', type=float, default=1.0)
    args = ap.parse_args()
    new = not os.path.exists(OUT)
    with open(OUT, 'a', encoding='utf-8') as handle:
        if new:
            handle.write('time,gpu_util_pct,mem_util_pct,vram_used_mib\n')
        end = time.time() + args.seconds
        n = 0
        while time.time() < end:
            s = sample()
            if s:
                handle.write('%s,%s,%s,%s\n' % (time.strftime('%H:%M:%S'), s[0], s[1], s[2]))
                handle.flush()
                n += 1
            time.sleep(args.interval)
    print('samples=%d -> %s' % (n, OUT))


if __name__ == '__main__':
    main()
