# -*- coding: utf-8 -*-
r"""round4_decode_pressure.py -- 第四轮：**解码开始后**再施加 400 MiB 外压（复刻 437 解码期爬升）
流程：基线 → 发 437 形态请求 → 等出 token → 加压 400 MiB → 每 30 s 采 host/round → 释放 → 恢复
判据：加压后 host/round ≥150 ms（或爬升）⇒ 复现 437 解码期谷；仍 25–30 ms ⇒ 解码期不敏感
安全：剂量有界 · hold 有超时 · 240 s 零输出即判挂死并释放 · 不重启
"""
import argparse
import glob
import io
import json
import os
import subprocess
import time
import urllib.request

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTDIR = os.path.join(R, 'work', time.strftime('%Y%m%d'))   # 按当天日期（TELE 复核：原硬编码日期）
URL = 'http://127.0.0.1:8094/v1/chat/completions'
MODEL = 'qwen3.8-27b-coder390'
VRAM_HOLD = os.path.join(R, 'tools', 'vram_hold.exe')
FILLER = ('The memory subsystem moves key value blocks between the device and the host. ')


def sh(cmd, t=60):
    try:
        return subprocess.run(cmd, capture_output=True, timeout=t).stdout.decode('utf-8', 'replace').strip()
    except Exception as e:
        return 'fail: %s' % e


def gpu():
    return sh(['nvidia-smi', '--query-gpu=utilization.gpu,power.draw,clocks.sm,memory.free', '--format=csv,noheader'])


def host_round():
    fs = sorted(glob.glob(os.path.join(R, '.temp', 'reqlog_*.jsonl')), key=lambda f: os.path.getmtime(f))
    if not fs:
        return None
    try:
        for l in reversed(io.open(fs[-1], encoding='utf-8', errors='replace').read().splitlines()[-60:]):
            try:
                j = json.loads(l)
            except Exception:
                continue
            h = (j.get('host_work') or {}).get('decode_host_microseconds_per_round')
            if h:
                return float(h)
    except Exception:
        pass
    return None


def msgs_437():
    return [
        {'role': 'user', 'content': '我们要写一份超长技术手册。先确认你能持续输出长文，不需要总结。'},
        {'role': 'assistant', 'content': '可以。请给主题与结构要求，我会逐节展开，不省略、不提前收尾。'},
        {'role': 'user', 'content': '背景材料（只读）：\n\n' + (FILLER * (int(8500 * 5.6) // len(FILLER) + 1))[:int(8500 * 5.6)]},
        {'role': 'user', 'content': '请写《KV 页迁移记账与延迟归因技术手册》，**分 40 节**，每节 **不少于 800 字**，'
                                    '总计不少于 32000 字。逐节编号、每节含小标题与至少 3 条要点、'
                                    '**不要省略、不要提前总结，直接从第 1 节开始**。'},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mib', type=int, default=400)
    ap.add_argument('--hold-sec', type=int, default=900)
    ap.add_argument('--max-min', type=int, default=20)
    ap.add_argument('--trigger-tokens', type=int, default=200)
    a = ap.parse_args()
    ts = time.strftime('%Y%m%d_%H%M%S')
    jl = os.path.join(OUTDIR, 'round4_%s.jsonl' % ts)

    def emit(rec):
        with io.open(jl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(json.dumps(rec, ensure_ascii=False)[:250], flush=True)

    emit({'event': 'baseline', 'host_round_us': host_round(), 'gpu': gpu()})
    payload = json.dumps({'model': MODEL, 'stream': True, 'max_tokens': 24000, 'temperature': 0.7,
                          'messages': msgs_437()}).encode('utf-8')
    req = urllib.request.Request(URL, data=payload, headers={'Content-Type': 'application/json'})
    t0 = time.time()
    n = nr = 0
    ttft = None
    last_s = last_c = t0
    ph = None
    peak = 0.0
    pre_pressure = []
    try:
        with urllib.request.urlopen(req, timeout=a.max_min * 60 + 180) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'replace').strip()
                if not line.startswith('data:'):
                    continue
                data = line[5:].strip()
                if data == '[DONE]':
                    break
                try:
                    j = json.loads(data)
                except Exception:
                    continue
                d = ((j.get('choices') or [{}])[0].get('delta') or {})
                c = d.get('content') or ''
                rp = d.get('reasoning_content') or ''
                if c or rp:
                    if c:
                        n += 1
                    if rp:
                        nr += 1
                    if ttft is None:
                        ttft = time.time() - t0
                    last_c = time.time()
                now = time.time()
                # —— 触发条件：解码已开始（正文 token 达阈值）且尚未加压 ——
                if ph is None and n >= a.trigger_tokens:
                    hr = host_round()
                    emit({'event': 'decode_started', 't': round(now - t0, 1), 'content': n,
                          'host_round_us': hr, 'gpu': gpu()})
                    pre_pressure.append(hr)
                    emit({'event': 'pressure_start', 't': round(now - t0, 1), 'mib': a.mib, 'hold_sec': a.hold_sec})
                    ph = subprocess.Popen([VRAM_HOLD, str(a.mib), str(a.hold_sec)],
                                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    time.sleep(10)
                    emit({'event': 'pressure_applied', 't': round(time.time() - t0, 1), 'gpu': gpu(),
                          'proc_alive': ph.poll() is None})
                if now - last_s >= 30:
                    hr = host_round()
                    if hr:
                        peak = max(peak, hr)
                    emit({'event': 'sample', 't': round(now - t0, 1), 'host_round_us': hr, 'content': n,
                          'reason': nr, 'gpu': gpu(), 'pressured': ph is not None,
                          'hold_alive': (ph.poll() is None) if ph else None})
                    last_s = now
                if now - last_c > 240:
                    emit({'event': 'hang', 't': round(now - t0, 1), 'content': n})
                    break
                if now - t0 > a.max_min * 60:
                    emit({'event': 'timeout', 't': round(now - t0, 1), 'content': n})
                    break
        emit({'event': 'request_done', 'wall': round(time.time() - t0, 1),
              'ttft': round(ttft, 2) if ttft else None, 'content': n, 'reason': nr,
              'peak_host_round_us': peak, 'host_round_end': host_round(), 'gpu': gpu()})
    except Exception as e:
        emit({'event': 'error', 'err': str(e)[:200], 't': round(time.time() - t0, 1), 'content': n})
    if ph and ph.poll() is None:
        ph.terminate()
        emit({'event': 'pressure_terminated'})
    if ph:
        try:
            ph.wait(timeout=30)
        except Exception:
            ph.kill()
    for k in (10, 30, 60):
        time.sleep(10 if k == 10 else 20 if k == 30 else 30)
        emit({'event': 'recovery', 'after_s': k, 'host_round_us': host_round(), 'gpu': gpu()})
    emit({'event': 'end', 'peak_host_round_us': peak, 'content_total': n})


if __name__ == '__main__':
    main()
