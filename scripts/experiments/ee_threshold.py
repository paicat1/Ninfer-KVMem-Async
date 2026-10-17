# -*- coding: utf-8 -*-
r"""ee_threshold.py -- E-E 阈值标定：分级外部显存压力，找"踩谷边界"（2026-10-17）

背景（四轮实验链）：外压 ⇒ host/round 爆 10–130× ⇒ 解码塌陷 + 功耗腰斩。
  E-D 已证明"谷深随池单调但都仍谷"；E-E 要回答：**外部占用到多少 MB 会踩谷？**

设计（TELE 4 条建议全采纳）：
  ① 每级**独立**（施加 → 请求 → 采样 → **释放** → 等恢复），不累积
  ② 每级 hold 200 s、采样 15 s 一次（对齐 E-C/E-D 的 300 s 量级、压缩总时长）
  ③ **先记自然基线**（无压时的自由显存与 host/round）
  ④ 判据：host/round 中位 <100 ms = 健康；≥150 ms 或阶跃到秒级 = 谷；记功耗/自由显存/decode 速率

用法：python -X utf8 scripts\experiments\ee_threshold.py [--levels 200,300,400,500] [--dry-run]
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
OUTDIR = os.path.join(R, 'work', time.strftime('%Y%m%d'))
MODEL = 'qwen3.8-27b-coder390'
URL = 'http://127.0.0.1:8094/v1/chat/completions'
VRAM_HOLD = os.path.join(R, 'tools', 'vram_hold.exe')
REQLOG_DIRS = [os.path.join(R, 'evidence', 'reqlogs'), os.path.join(R, '.temp')]
FILLER = ('KV 页迁移记账与延迟归因：引擎在解码期需要把命中页从 host 侧搬回 device 侧，'
          '并把冷页 demote 回 host；这一进一出由调度器按 ring 预算推进。' * 3)


def sh(c):
    return subprocess.run(c, capture_output=True).stdout.decode('utf-8', 'replace').strip()


def gpu():
    return sh(['nvidia-smi', '--query-gpu=utilization.gpu,power.draw,clocks.sm,memory.free', '--format=csv,noheader'])


def free_mib():
    g = gpu()
    try:
        return int(g.split(',')[-1].strip().replace(' MiB', ''))
    except Exception:
        return None


def host_round_ex():
    fs = []
    for d in REQLOG_DIRS:
        fs += glob.glob(os.path.join(d, 'reqlog_*.jsonl'))
    if not fs:
        return None, None
    f = sorted(fs, key=lambda p: os.path.getmtime(p))[-1]
    age = time.time() - os.path.getmtime(f)
    try:
        for l in reversed(io.open(f, encoding='utf-8', errors='replace').read().splitlines()[-80:]):
            try:
                j = json.loads(l)
            except Exception:
                continue
            h = (j.get('host_work') or {}).get('decode_host_microseconds_per_round')
            if h:
                return float(h), age
    except Exception:
        pass
    return None, age


def msgs_437():
    return [
        {'role': 'user', 'content': '我们要写一份超长技术手册。先确认你能持续输出长文，不需要总结。'},
        {'role': 'assistant', 'content': '可以。请给主题与结构要求，我会逐节展开，不省略、不提前收尾。'},
        {'role': 'user', 'content': '背景材料（只读）：\n\n' + (FILLER * (int(8500 * 5.6) // len(FILLER) + 1))[:int(8500 * 5.6)]},
        {'role': 'user', 'content': '请写《KV 页迁移记账与延迟归因技术手册》，**分 40 节**，每节 **不少于 800 字**，'
                                    '总计不少于 32000 字。逐节编号、每节含小标题与至少 3 条要点、'
                                    '**不要省略、不要提前总结，直接从第 1 节开始**。'},
    ]


def run_level(mib, hold_sec, sample_every, max_min, emit):
    """一级：基线 → 加压 → 请求+采样 → 释放 → 恢复。返回判据 dict。"""
    res = {'level_mib': mib}
    res['free_before'] = free_mib()
    hr, age = host_round_ex()
    res['host_round_before'] = hr
    emit({'event': 'level_start', 'mib': mib, 'free_before': res['free_before'],
          'host_round_before': hr, 'gpu': gpu()})

    ph = None
    if mib > 0:
        ph = subprocess.Popen([VRAM_HOLD, str(mib), str(hold_sec + 60)],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        time.sleep(12)
        emit({'event': 'pressure_applied', 'mib': mib, 'proc_alive': ph.poll() is None,
              'free_after_pressure': free_mib(), 'gpu': gpu()})

    payload = json.dumps({'model': MODEL, 'stream': True, 'max_tokens': 24000, 'temperature': 0.7,
                          'messages': msgs_437()}).encode('utf-8')
    req = urllib.request.Request(URL, data=payload, headers={'Content-Type': 'application/json'})
    t0 = time.time()
    n = 0
    samples = []
    last_s = t0
    last_c = t0
    verdict = 'healthy'
    try:
        with urllib.request.urlopen(req, timeout=max_min * 60 + 120) as resp:
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
                if c:
                    n += 1
                    last_c = time.time()
                now = time.time()
                if now - last_s >= sample_every:
                    hr, age = host_round_ex()
                    stale = (age is not None and age > 45)
                    fm = free_mib()
                    s = {'event': 'sample', 't': round(now - t0, 1), 'content': n,
                         'host_round_us': hr, 'host_round_age_s': (round(age, 1) if age is not None else None),
                         'stale': stale, 'free_mib': fm, 'gpu': gpu(), 'mib': mib}
                    emit(s)
                    if hr and not stale:
                        samples.append(hr)
                    last_s = now
                if now - last_c > 150:
                    emit({'event': 'hang', 't': round(now - t0, 1), 'content': n})
                    verdict = 'stalled'
                    break
                if now - t0 > max_min * 60:
                    emit({'event': 'timeout', 't': round(now - t0, 1), 'content': n})
                    break
    except Exception as e:
        emit({'event': 'request_error', 'err': str(e)[:200]})

    # 释放压力
    if ph:
        try:
            ph.kill()
        except Exception:
            pass
        emit({'event': 'pressure_released', 'mib': mib, 'gpu': gpu()})
    time.sleep(30)
    hr2, _ = host_round_ex()
    res.update({
        'content': n,
        'wall_s': round(time.time() - t0, 1),
        'host_round_samples': [round(v) for v in samples],
        'host_round_median': (sorted(samples)[len(samples) // 2] if samples else None),
        'host_round_max': (max(samples) if samples else None),
        'host_round_recovered': hr2,
        'free_after_release': free_mib(),
        'gpu_end': gpu(),
        'verdict': verdict,
    })
    # 判据
    med = res['host_round_median']
    if verdict == 'stalled':
        res['verdict'] = 'STALLED(谷-停顿)'
    elif med is None:
        res['verdict'] = 'UNKNOWN(无有效样本)'
    elif med >= 150000:
        res['verdict'] = 'VALLEY(≥150ms)'
    elif med >= 100000:
        res['verdict'] = 'DEGRADED(100-150ms)'
    else:
        res['verdict'] = 'HEALTHY(<100ms)'
    emit({'event': 'level_end', **{k: v for k, v in res.items() if k != 'host_round_samples'}})
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--levels', default='200,300,400,500')
    ap.add_argument('--hold-sec', type=int, default=200)
    ap.add_argument('--sample-every', type=int, default=15)
    ap.add_argument('--max-min', type=int, default=4)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    jl = os.path.join(OUTDIR, 'ee_%s.jsonl' % time.strftime('%Y%m%d_%H%M%S'))

    def emit(rec):
        with io.open(jl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        print(json.dumps(rec, ensure_ascii=False)[:230], flush=True)

    print('== E-E 阈值标定 == levels=%s hold=%ss sample=%ss max-min=%s' % (a.levels, a.hold_sec, a.sample_every, a.max_min))
    print('   台账 = %s' % os.path.relpath(jl, R))
    print('   **自然基线（无压）**：free=%s MiB · host/round=%s µs · GPU=%s' % (free_mib(), host_round_ex()[0], gpu()))
    if a.dry_run:
        print('   --dry-run：不发请求、不加压')
        emit({'event': 'dry_run', 'levels': a.levels, 'free_baseline_mib': free_mib(),
              'host_round_baseline_us': host_round_ex()[0]})
        return

    results = []
    for lv in [int(x) for x in a.levels.split(',') if x.strip()]:
        r = run_level(lv, a.hold_sec, a.sample_every, a.max_min, emit)
        results.append(r)
        print('   ⇒ 级 %d MiB：%s（host/round 中位 %s µs · free %s→%s）' % (
            lv, r['verdict'], r['host_round_median'], r['free_before'], r['free_after_release']))
        time.sleep(20)

    print('\n== E-E 汇总 ==')
    print('   %-8s %-22s %-14s %-10s %-10s' % ('级(MiB)', '判据', 'host/round中位', 'free前', 'free后'))
    for r in results:
        print('   %-8d %-22s %-14s %-10s %-10s' % (
            r['level_mib'], r['verdict'], r['host_round_median'], r['free_before'], r['free_after_release']))
    emit({'event': 'summary', 'results': [{k: v for k, v in r.items() if k != 'host_round_samples'} for r in results]})


if __name__ == '__main__':
    main()
