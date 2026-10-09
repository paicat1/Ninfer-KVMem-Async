# -*- coding: utf-8 -*-
"""bench_spec.py -- 投机解码基线/对照测试（对**已经在跑**的 serve 发请求，从引擎日志读数）。

WHY
    接受率与 decode 速度随**任务类型**剧烈变化（实测：代码 93.8% vs 散文 22.6%），
    单条 prompt 的读数没有代表性。本脚本按固定任务集重复跑，给出**分布**，
    并支持两臂对比（例如 ngram 开/关、MTP 开/关）。

HOW IT READS NUMBERS
    不改引擎、不依赖 HTTP 头：直接解析引擎日志里的业务行
        req#N done | openai-chat | ... | prompt X | output Y | ... | decode D tok/s | mtp accepted A/B (P%)
    日志是 serve_tee.py 写的（起服脚本已默认落盘到 logs\\serve-coder390*.log）。

USAGE（服务必须已在跑；本脚本**不启动任何进程**）
    # 单臂：跑一轮任务集，汇总分布
    python scripts\\bench_spec.py --port 8095 --log logs\\serve-coder390-mtp.log --label "MTP+ngram(默认15)"

    # 双臂对比：跑完 A 臂后重启另一配置，再跑 B 臂，用 --baseline 比对
    python scripts\\bench_spec.py --port 8095 --log logs\\serve-coder390-mtp.log --label B --baseline A.json

    # 自定义轮数/输出长度
    python scripts\\bench_spec.py --port 8095 --log <log> --label X --runs 2 --max-tokens 400

WHAT IT DOES NOT DO
    · 不启动、不停止 serve（起服归用户：双击 start-coder390*.bat）
    · 不改任何文件（除 --save 指定的 JSON）
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

# 固定任务集：覆盖接受率的两端（代码=高接受率、散文=低接受率）+ 中间类型。
# 每条都要求较长输出，避免短输出把速度读数淹没在噪声里。
TASKS = [
    ("code",     "写一个 Python 快速排序函数，要求：类型注解、docstring、处理空列表与重复元素。只要代码。"),
    ("code2",    "写一个 bash 脚本：统计目录下所有 .log 文件的行数并按行数降序输出前 10 个。只要脚本。"),
    ("prose",    "请用大约 250 个汉字介绍 CUDA 图（CUDA Graphs）的原理、适用场景和局限。"),
    ("prose2",   "请用大约 250 个汉字解释什么是 KV 缓存（KV cache），以及它为什么占用显存。"),
    ("reason",   "一个水池有两个进水管和一个出水管。甲管单独注满需 6 小时，乙管单独注满需 8 小时，"
                 "出水管单独排空需 12 小时。三管同时开，多久注满？请写出推理过程。"),
    ("math",     "计算 1234 × 5678 与 98765 ÷ 4321 的结果，并说明你的计算步骤。"),
    ("translate","把下面这段英文翻译成中文，保持技术术语准确："
                 "Speculative decoding accelerates autoregressive generation by drafting several tokens "
                 "with a cheap model and verifying them in parallel with the target model, which "
                 "preserves the output distribution exactly."),
    ("summary",  "用 5 条要点总结：为什么投机解码能在不改变输出分布的前提下加速推理？每条不超过 40 字。"),
]

DONE_RE = re.compile(
    r"req#(?P<req>\d+)\s+done\s*\|\s*(?P<api>[^|]+)\|.*?"
    r"prompt\s+(?P<prompt>\d+)\s*\|\s*output\s+(?P<out>\d+)\s*\|.*?"
    r"TTFT\s+(?P<ttft>[\d.]+)\s*ms\s*\|\s*total\s+(?P<total>[\d.]+)(?P<tunit>ms|s)\s*\|.*?"
    r"prefill\s+(?P<prefill>[\d.]+k?)\s*tok/s\s*\|\s*decode\s+(?P<decode>[\d.]+)\s*tok/s"
    r"(?:\s*\|\s*(?P<acc_kind>[\w+]+)\s+accepted\s+(?P<acc_a>\d+)/(?P<acc_b>\d+)\s*\((?P<acc_p>[\d.]+)%\))?"
)


def read_new_lines(path, offset):
    """读日志文件 offset 之后的新内容，返回 (lines, new_offset)。"""
    if not os.path.exists(path):
        return [], offset
    size = os.path.getsize(path)
    if size < offset:          # 文件被截断/轮转
        offset = 0
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read()
    return data.decode("utf-8", "replace").splitlines(), offset + len(data)


def post_chat(port, model_id, prompt, max_tokens, temperature):
    body = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:%d/v1/chat/completions" % port,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_records(lines):
    out = []
    for line in lines:
        m = DONE_RE.search(line)
        if not m:
            continue
        d = m.groupdict()
        total = float(d["total"]) * (1000.0 if d["tunit"] == "s" else 1.0)
        rec = {
            "req": int(d["req"]),
            "prompt_tokens": int(d["prompt"]),
            "output_tokens": int(d["out"]),
            "ttft_ms": float(d["ttft"]),
            "total_ms": total,
            "prefill_tok_s": d["prefill"],
            "decode_tok_s": float(d["decode"]),
        }
        if d["acc_b"]:
            rec["acc_kind"] = d["acc_kind"]
            rec["accepted"] = int(d["acc_a"])
            rec["drafted"] = int(d["acc_b"])
            rec["accept_pct"] = float(d["acc_p"])
        out.append(rec)
    return out


def summarize(records, label):
    if not records:
        return None
    dec = [r["decode_tok_s"] for r in records]
    acc = [r["accept_pct"] for r in records if "accept_pct" in r]
    tot_out = sum(r["output_tokens"] for r in records)
    tot_ms = sum(r["total_ms"] for r in records)
    s = {
        "label": label,
        "runs": len(records),
        "decode_mean": round(sum(dec) / len(dec), 2),
        "decode_min": round(min(dec), 2),
        "decode_max": round(max(dec), 2),
        "output_tokens_total": tot_out,
        "wall_ms_total": round(tot_ms, 1),
        "aggregate_tok_s": round(tot_out / (tot_ms / 1000.0), 2) if tot_ms else None,
        "per_task": [
            {
                "req": r["req"],
                "decode_tok_s": r["decode_tok_s"],
                "accept_pct": r.get("accept_pct"),
                "accept": ("%d/%d" % (r["accepted"], r["drafted"])) if "accepted" in r else None,
                "output_tokens": r["output_tokens"],
            }
            for r in records
        ],
    }
    if acc:
        s["accept_mean"] = round(sum(acc) / len(acc), 2)
        s["accept_min"] = round(min(acc), 2)
        s["accept_max"] = round(max(acc), 2)
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8095)
    ap.add_argument("--model-id", default=None, help="默认取 /v1/models 里第一个")
    ap.add_argument("--log", required=True, help="serve_tee 写的日志路径（读 req#N done 行）")
    ap.add_argument("--label", default="arm", help="本次跑的标签（写进结果 JSON）")
    ap.add_argument("--runs", type=int, default=1, help="任务集重复轮数（默认 1）")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--save", default=None, help="结果 JSON 保存路径（默认 bench_<label>.json）")
    ap.add_argument("--baseline", default=None, help="已保存的 JSON：与之对比并打印差异")
    ap.add_argument("--dry-run", action="store_true", help="只打印将发送的任务，不真发请求")
    args = ap.parse_args(argv)

    if args.dry_run:
        for name, prompt in TASKS:
            print("  %-10s %s" % (name, prompt[:60]))
        print("[dry-run] nothing sent")
        return 0

    model_id = args.model_id
    if not model_id:
        with urllib.request.urlopen("http://127.0.0.1:%d/v1/models" % args.port, timeout=15) as resp:
            listing = json.loads(resp.read().decode("utf-8"))
        model_id = listing["data"][0]["id"]
    print("port      : %d" % args.port)
    print("model     : %s" % model_id)
    print("log       : %s" % args.log)
    print("label     : %s" % args.label)

    offset = os.path.getsize(args.log) if os.path.exists(args.log) else 0
    print("log offset: %d (只统计本次之后的新行)" % offset)

    started = time.time()
    for rnd in range(1, args.runs + 1):
        for name, prompt in TASKS:
            t0 = time.time()
            try:
                resp = post_chat(args.port, model_id, prompt, args.max_tokens, args.temperature)
                out = resp.get("usage", {}).get("completion_tokens")
                print("  [%d/%d] %-10s ok  out=%-5s %.1fs" % (rnd, args.runs, name, out, time.time() - t0))
            except Exception as exc:                                  # noqa: BLE001
                print("  [%d/%d] %-10s FAILED: %s" % (rnd, args.runs, name, exc))
    time.sleep(2.0)                                                   # 等日志 flush

    lines, _ = read_new_lines(args.log, offset)
    records = parse_records(lines)
    summary = summarize(records, args.label)
    if summary is None:
        print("\n[WARN] 日志里没解析到 req#N done 行 —— 检查 --log 是否指向本次起服的日志")
        return 4

    print("\n=== summary: %s ===" % args.label)
    print("  runs              : %d" % summary["runs"])
    print("  decode mean/min/max: %.2f / %.2f / %.2f tok/s" % (
        summary["decode_mean"], summary["decode_min"], summary["decode_max"]))
    if "accept_mean" in summary:
        print("  accept mean/min/max: %.2f%% / %.2f%% / %.2f%%" % (
            summary["accept_mean"], summary["accept_min"], summary["accept_max"]))
    print("  aggregate         : %.2f tok/s (%d tokens / %.1f s)" % (
        summary["aggregate_tok_s"] or 0, summary["output_tokens_total"], summary["wall_ms_total"] / 1000.0))
    print("  per task:")
    for t in summary["per_task"]:
        print("    req#%-3d decode %7.2f tok/s  accept %-14s out=%d" % (
            t["req"], t["decode_tok_s"], (t["accept"] or "-"), t["output_tokens"]))

    path = args.save or ("bench_%s.json" % re.sub(r"[^\w.-]+", "_", args.label))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print("\nsaved     : %s" % path)

    if args.baseline and os.path.exists(args.baseline):
        with open(args.baseline, encoding="utf-8") as fh:
            base = json.load(fh)
        print("\n=== vs baseline: %s ===" % base.get("label"))
        print("  decode : %.2f -> %.2f tok/s  (%+.1f%%)" % (
            base["decode_mean"], summary["decode_mean"],
            100.0 * (summary["decode_mean"] - base["decode_mean"]) / base["decode_mean"]))
        if "accept_mean" in summary and "accept_mean" in base:
            print("  accept : %.2f%% -> %.2f%%  (%+.1f pt)" % (
                base["accept_mean"], summary["accept_mean"],
                summary["accept_mean"] - base["accept_mean"]))
        print("  ⚠ 差异需大于 run-to-run 噪声底才算真差异（同配置多跑几轮测极差）")

    print("\nelapsed   : %.1fs" % (time.time() - started))
    return 0


if __name__ == "__main__":
    sys.exit(main())
