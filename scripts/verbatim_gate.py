#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""verbatim_gate.py -- 逐字一致门（4-bit KV / 换模型 的 agent 红线判据）。

方法（对齐精算文档 §10.2 与第三方口径）：
  同一批 8 组固定提示 · temperature=0 / top_p=1 / top_k=1（argmax） · 每臂独立起服（冷缓存）
  → 逐字对比 content 与 reasoning（两字段都必须全等），出一致率报表。

用法：
  python -X utf8 scripts\\verbatim_gate.py --arm cur_a --port 8094
  python -X utf8 scripts\\verbatim_gate.py --arm cur_b --port 8094
  python -X utf8 scripts\\verbatim_gate.py --compare cur_a cur_b
判据（借第三方）：>=7/8 过 · 5-6/8 条件 · <=4/8 拒。

产物：work\\data\\verbatim\\<arm>_p<i>.json（原始响应）+ <arm>.json（汇总）+ compare_<a>_<b>.md
"""
import argparse
# 招牌名解析（2026-10-14）：--model-id 随底座变，禁止写死
try:
    from _modelid import model_id as _model_id
except Exception:  # 极端情况下回退旧名
    def _model_id(*_a, **_k):
        return "qwen3.8-27b-coder390"

import hashlib
import io
import json
import os
import time
import urllib.request

OUT = r'J:\ninfer-kvmem\work\data\verbatim'

PROMPTS = [
    ('p1_code', '写一个 Python 函数 merge_intervals(pairs)，合并重叠区间并返回排序后的列表。只给代码和一行示例。', 320),
    ('p2_code', '用 C++ 写一个最小 LRU 缓存的类定义（含 get/put），不要解释。', 320),
    ('p3_json', '把下面信息抽成 JSON 对象（字段 name/age/city，不要额外文字）：张三，34 岁，住在杭州。', 200),
    ('p4_json', '输出一个 JSON 数组，含 3 个对象，字段 id/name/score，score 取 60-99 的整数。只给 JSON。', 200),
    ('p5_quote', '逐字复述下面这句话，不要改动任何标点或字：'
                 '异步页流水把搬运从关键路径上摘下来，于是池从容量门槛降级为搬运频率旋钮。', 200),
    ('p6_fact', '用两句话解释为什么 CUDA graph 能降低每步启动开销。', 300),
    ('p7_open', '用三句话描述异步页流水的优势。', 300),
    ('p8_shell', '给出一条 shell 命令：列出当前目录下最大的 5 个文件，按人类可读大小排序。只给命令。', 200),
]


def one_request(port, prompt, max_tokens, timeout=900):
    url = 'http://127.0.0.1:%d/v1/chat/completions' % port
    body = json.dumps({
        'model': _model_id(),
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': max_tokens,
        'temperature': 0, 'top_p': 1.0, 'top_k': 1,
        'stream': False,
        # 逐请求关思考（2026-10-14 实测有效）：思考块会先吃输出预算，令 content 截断为空。
        'chat_template_kwargs': {'enable_thinking': False},
    }).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode('utf-8'))


def fields(payload):
    choice = (payload.get('choices') or [{}])[0]
    message = choice.get('message') or {}
    content = message.get('content') or ''
    reasoning = message.get('reasoning_content') or message.get('reasoning') or ''
    return content, reasoning, choice.get('finish_reason')


def sha8(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


def run_arm(port, arm):
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for index, (pid, prompt, max_tokens) in enumerate(PROMPTS, start=1):
        started = time.time()
        try:
            payload = one_request(port, prompt, max_tokens)
            content, reasoning, finish = fields(payload)
            error = ''
        except Exception as exc:                     # noqa: BLE001
            payload, content, reasoning, finish, error = {}, '', '', '', str(exc)
        elapsed = time.time() - started
        usage = (payload.get('usage') or {})
        record = {'prompt_id': pid, 'prompt': prompt, 'content': content, 'reasoning': reasoning,
                  'finish_reason': finish, 'error': error, 'elapsed_s': round(elapsed, 2),
                  'sha_content': sha8(content), 'sha_reasoning': sha8(reasoning), 'usage': usage}
        with io.open(os.path.join(OUT, '%s_%s.json' % (arm, pid)), 'w', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=1)
        rows.append(record)
        print('%s %-8s %6.1fs in=%s out=%s finish=%s sha=%s%s'
              % (arm, pid, elapsed, usage.get('prompt_tokens'), usage.get('completion_tokens'),
                 finish or '-', record['sha_content'], (' ERR=' + error[:60]) if error else ''))
    with io.open(os.path.join(OUT, '%s.json' % arm), 'w', encoding='utf-8') as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=1)
    print('arm %s written: %s' % (arm, os.path.join(OUT, '%s.json' % arm)))


def compare(arm_a, arm_b):
    with io.open(os.path.join(OUT, '%s.json' % arm_a), encoding='utf-8') as handle:
        rows_a = {row['prompt_id']: row for row in json.load(handle)}
    with io.open(os.path.join(OUT, '%s.json' % arm_b), encoding='utf-8') as handle:
        rows_b = {row['prompt_id']: row for row in json.load(handle)}
    same = 0
    lines = ['# 逐字一致门报表 %s vs %s' % (arm_a, arm_b), '',
             '| 提示 | content 全等 | reasoning 全等 | 首处差异 |', '|---|---|---|---|']
    for pid, prompt, _max_tokens in PROMPTS:
        ra, rb = rows_a.get(pid, {}), rows_b.get(pid, {})
        same_content = ra.get('content') == rb.get('content')
        same_reasoning = ra.get('reasoning') == rb.get('reasoning')
        if same_content and same_reasoning:
            same += 1
            diff = '—'
        else:
            ca, cb = ra.get('content', ''), rb.get('content', '')
            limit = min(len(ca), len(cb))
            index = next((i for i in range(limit) if ca[i] != cb[i]), limit)
            if ca == cb:
                diff = 'reasoning 不同（content 相同）'
            else:
                diff = '位 %d: %s -> %s' % (index, ca[max(0, index - 12):index + 12],
                                            cb[max(0, index - 12):index + 12])
        lines.append('| %s | %s | %s | %s |' % (pid, 'Y' if same_content else 'N',
                                                'Y' if same_reasoning else 'N', diff.replace('|', '/')))
    verdict = '过（>=7/8）' if same >= 7 else ('条件（5-6/8）' if same >= 5 else '拒（<=4/8）')
    lines += ['', '**一致 = %d/8 => %s**' % (same, verdict), '']
    text = '\n'.join(lines)
    out_path = os.path.join(OUT, 'compare_%s_%s.md' % (arm_a, arm_b))
    with io.open(out_path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    print(text)
    print('written: %s' % out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arm')
    parser.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    parser.add_argument('--port', type=int, default=8094)
    args = parser.parse_args()
    if args.compare:
        compare(args.compare[0], args.compare[1])
    elif args.arm:
        run_arm(args.port, args.arm)
    else:
        parser.error('specify --arm <name> or --compare A B')


if __name__ == '__main__':
    main()
