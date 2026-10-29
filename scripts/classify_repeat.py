#!/usr/bin/env python3
"""classify_repeat.py -- #53 定性：循环段四分类（quote_src / quote_prev / self / 结构）

规格来源:
  - docs/03-归因与结论/归因-异步防复读八轮推演终版与路线图-lummy-CODE-20261026.md §4.1b
  - max8 口径严格复刻 engine-src/.../request_log.cpp repeat_stats():
      空白分词 -> 8-token 滑窗 -> max8 = 最频 8-gram 的出现次数（连环次数，非连续段）
  - filler 口径复刻 scripts/a2gate.py make_filler(seed=20261012)

用法: python scripts/classify_repeat.py [--dir .temp]
"""
import argparse
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

WORDS = ('alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike '
         'november oscar papa quebec romeo sierra tango uniform victor whiskey xray yankee zulu').split()
WORSET = set(WORDS)
# 2026-10-29 (C0): 兼容旧 abab_text_abab_<arm>_r<N>.txt 与新 abab_text_<arm>_<inv>_r<N>.txt
NAME_RE = re.compile(r'^abab_text_(?P<base>.+)_r(?P<rnd>\d+)\.txt$')


def make_filler(kb, seed=20261012):
    target = kb * 1024
    state = seed
    parts = []
    size = 0
    while size < target:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        word = WORDS[state % len(WORDS)]
        parts.append(word)
        size += len(word) + 1
    return ' '.join(parts)


FILLER_N = ' '.join(re.sub(r'[^\w\s]', ' ', make_filler(400), flags=re.UNICODE).lower().split())


def norm(text):
    return ' '.join(re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE).lower().split())


def max8_stats(toks, n=8):
    if len(toks) < n:
        return 0, None
    counts = {}
    for i in range(len(toks) - n + 1):
        gram = ' '.join(toks[i:i + n])
        counts[gram] = counts.get(gram, 0) + 1
    max8 = max(counts.values())
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    return max8, best


def loop_region(toks, gram, n=8):
    """最频 8-gram 的等周期连续簇 => 循环区 [start, end)"""
    idxs = [i for i in range(len(toks) - n + 1) if ' '.join(toks[i:i + n]) == gram]
    if len(idxs) < 2:
        return None
    gaps = [idxs[i + 1] - idxs[i] for i in range(len(idxs) - 1)]
    period = max(set(gaps), key=gaps.count)
    # 最长的一段"相邻间隔都等于 period"的连续簇
    best_run = (0, 0)
    run_start = 0
    for i, g in enumerate(gaps):
        if g != period:
            if i - run_start > best_run[1] - best_run[0]:
                best_run = (run_start, i)
            run_start = i + 1
    if len(gaps) - run_start > best_run[1] - best_run[0]:
        best_run = (run_start, len(gaps))
    a, b = best_run
    if b - a < 1:
        return None
    return idxs[a], idxs[b] + n


def classify(seg_tokens, prev_text):
    if not seg_tokens:
        return 'none'
    seg_n = norm(' '.join(seg_tokens))
    if seg_n and seg_n in FILLER_N:
        return 'quote_src'
    if prev_text:
        probe = ' '.join(seg_tokens[:min(60, len(seg_tokens))])
        pn, pp = norm(probe), norm(prev_text)
        if pn and pn in pp:
            return 'quote_prev'
    joined = ' '.join(seg_tokens)
    if len(re.findall(r'\b\d+\s*[.、)]', joined)) >= 3:
        return '结构'
    return 'self'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default='.temp')
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, 'abab_text_*.txt')))
    if not files:
        print('未找到 abab_text_*.txt')
        return

    texts = {}
    for path in files:
        with open(path, encoding='utf-8') as handle:
            texts[os.path.basename(path)] = handle.read()

    print(f"{'file':36} {'tokens':>7} {'max8':>5} {'loop_tok':>9} {'loop%':>6} {'nato%':>6} {'class':>10}")
    print('-' * 82)
    tally = {}
    for path in files:
        name = os.path.basename(path)
        text = texts[name]
        match = NAME_RE.match(name)
        base = match.group('base') if match else '?'
        rnd = match.group('rnd') if match else '0'
        toks = text.split()
        max8, gram = max8_stats(toks)
        region = loop_region(toks, gram) if gram else None
        if region:
            seg = toks[region[0]:region[1]]
            cls = classify(seg, None)
        else:
            seg, cls = [], 'none'
        prev_key = (f'abab_text_{base}_r{int(rnd) - 1}.txt') if rnd.isdigit() else None
        prev_text = texts.get(prev_key) if prev_key else None
        if seg and prev_text:
            cls = classify(seg, prev_text)
        ratio = 100.0 * len(seg) / max(1, len(toks))
        seg_words = re.sub(r'[^\w\s]', ' ', ' '.join(seg)).lower().split()
        nato = 100.0 * sum(1 for w in seg_words if w in WORSET) / max(1, len(seg_words))
        print(f'{name:36} {len(toks):7d} {max8:5d} {len(seg):9d} {ratio:5.1f}% {nato:5.1f}% {cls:>10}')
        tally[cls] = tally.get(cls, 0) + 1

    print('-' * 82)
    print('分类计数:', ', '.join(f'{k}={v}' for k, v in sorted(tally.items())))


if __name__ == '__main__':
    main()
