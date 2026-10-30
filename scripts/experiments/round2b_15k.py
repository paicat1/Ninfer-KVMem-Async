# -*- coding: utf-8 -*-
r"""round2b_15k.py -- 第二轮 b：强制跑满 15k+ 输出（隔离"输出长度"这一个变量）
判据：host/round（reqlog）。若 15k token 仍 ~30 ms ⇒ 输出长度不是爬升的成因。
用法：python -X utf8 work/<当天>/round2b_15k.py
"""
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
FILLER = ('The memory subsystem moves key value blocks between the device and the host. ')


def reqlog_host_round():
    fs = sorted(glob.glob(os.path.join(R, 'work', 'data', 'reqlog_*.jsonl')), key=lambda f: os.path.getmtime(f))
    if not fs:
        return None
    try:
        for l in reversed(io.open(fs[-1], encoding='utf-8', errors='replace').read().splitlines()[-40:]):
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


def gpu():
    try:
        return subprocess.run(['nvidia-smi', '--query-gpu=utilization.gpu,power.draw,clocks.sm',
                               '--format=csv,noheader'], capture_output=True, timeout=30).stdout.decode().strip()
    except Exception:
        return '?'


msgs = [
    {'role': 'user', 'content': '我们要写一份超长技术手册。先确认你能持续输出长文，不需要总结。'},
    {'role': 'assistant', 'content': '可以。请给主题与结构要求，我会逐节展开，不省略、不提前收尾。'},
    {'role': 'user', 'content': '背景材料（只读）：\n\n' + (FILLER * (int(8500 * 5.6) // len(FILLER) + 1))[:int(8500 * 5.6)]},
    {'role': 'user', 'content': '请写《KV 页迁移记账与延迟归因技术手册》，**分 40 节**，每节 **不少于 800 字**，'
                                '总计不少于 32000 字。要求：逐节编号展开、每节含小标题与至少 3 条要点、'
                                '**不要省略、不要提前总结、不要说明你在写什么，直接从第 1 节开始**。'},
]

ts = time.strftime('%Y%m%d_%H%M%S')
jl = os.path.join(OUTDIR, 'round2b_15k_%s.jsonl' % ts)


def emit(rec):
    with io.open(jl, 'a', encoding='utf-8') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False)[:240], flush=True)


emit({'event': 'start', 'chars': sum(len(m['content']) for m in msgs), 'host_round_before': reqlog_host_round(),
      'gpu': gpu()})
payload = json.dumps({'model': MODEL, 'stream': True, 'max_tokens': 24000, 'temperature': 0.7,
                      'messages': msgs}).encode('utf-8')
req = urllib.request.Request(URL, data=payload, headers={'Content-Type': 'application/json'})
t0 = time.time()
n = nr = 0
ttft = None
last_s = last_c = t0
try:
    with urllib.request.urlopen(req, timeout=35 * 60) as resp:
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
            if now - last_s >= 30:
                emit({'event': 'sample', 't': round(now - t0, 1), 'host_round_us': reqlog_host_round(),
                      'content': n, 'reason': nr, 'gpu': gpu()})
                last_s = now
            if now - last_c > 240:
                emit({'event': 'hang', 't': round(now - t0, 1), 'content': n})
                break
            if now - t0 > 30 * 60:
                emit({'event': 'timeout', 't': round(now - t0, 1), 'content': n})
                break
    emit({'event': 'done', 'wall': round(time.time() - t0, 1), 'ttft': round(ttft, 2) if ttft else None,
          'content': n, 'reason': nr, 'host_round_end': reqlog_host_round(), 'gpu': gpu()})
except Exception as e:
    emit({'event': 'error', 'err': str(e)[:200], 't': round(time.time() - t0, 1), 'content': n})
