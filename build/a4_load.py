# -*- coding: utf-8 -*-
"""a4_load.py -- A4 / soak load client for a local ninfer-serve (OpenAI-compatible).

Profile matches the A4 on-site request (logs/serve_20261007_163541.log req#30):
  32 tools, ~10 messages, per-request max_tokens=65536 (CLIENT OVERRIDE; the server
  default is 32768 -- this override is required for the A4 A/B to be "same-args").
thinking medium + budget 16000 come from SERVER defaults
(--default-reasoning-effort medium --default-thinking-budget 16000), so the client
sends no thinking field.  preserve-thinking is also a server flag.

Usage:
  python a4_load.py --port 8094                     # one A4-class request
  python a4_load.py --port 8097 --turns 30          # soak: 30 sequential requests
  python a4_load.py --port 8094 --doc-chars 100000 --messages 10 --tools 32

Evidence: one JSON per turn under logs/a4_requests/ (request size + usage + finish).
NOTE: an assistant turn can carry its body in EITHER the `content` channel OR the
`tool_calls` channel. Counting only `content` reports `chars=0` for a legitimate
tool-call turn, which is NOT an empty body. Both are counted separately below.
Stdlib only.
"""
import argparse
import json
import os
import socket
import sys
import time
import urllib.request

SHORT_TURNS = [
    "Continue with the next edit.",
    "Now explain what you changed and why.",
    "Apply the same fix to the other call site.",
    "What is the remaining risk?",
    "Summarise the diff in 3 lines.",
    "Proceed to the next function.",
    "Any test I should run now?",
    "Re-check the boundary condition.",
    "Show the final version.",
    "Continue.",
]


def make_tools(n):
    tools = []
    for i in range(n):
        tools.append({
            "type": "function",
            "function": {
                "name": "tool_%02d_%s" % (i, "probe" if i % 2 == 0 else "patch"),
                "description": "Test tool %d used only to enlarge the request tool set." % i,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "target path"},
                        "line": {"type": "integer", "description": "target line"},
                        "mode": {"type": "string", "enum": ["view", "edit"]},
                    },
                    "required": ["path"],
                },
            },
        })
    return tools


def make_doc(chars):
    """Deterministic code-like filler so the prompt reaches ~27-35K tokens."""
    lines = []
    total = 0
    i = 0
    while total < chars:
        ln = ("    obj_%06d = transform_layer(state, weights[%d], bias=%d)  "
              "# keep the accumulation in fp32 to avoid drift\n") % (i, i, i * 7 % 251)
        lines.append(ln)
        total += len(ln)
        i += 1
    return "".join(lines)


def build_messages(n, doc):
    msgs = [
        {"role": "system", "content": "You are a coding agent editing a local repository."},
        {"role": "user", "content": "Here is the module to work on:\n\n" + doc +
         "\n\nFind the bug and fix it step by step."},
    ]
    k = 0
    while len(msgs) < n:
        role = "assistant" if k % 2 == 0 else "user"
        msgs.append({"role": role, "content": SHORT_TURNS[k % len(SHORT_TURNS)]})
        k += 1
    if msgs[-1]["role"] != "user":
        msgs[-1] = {"role": "user", "content": "Continue."}
    return msgs


def one_request(host, port, payload, stall_timeout, verbose):
    url = "http://%s:%d/v1/chat/completions" % (host, port)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    ttft = None
    parts = []
    n_tool_calls = 0
    finish = None
    usage = None
    stall = False
    err = None
    try:
        resp = urllib.request.urlopen(req, timeout=stall_timeout)
        last = t0
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if ttft is None:
                ttft = time.time() - t0
            for ch in (obj.get("choices") or []):
                d = ch.get("delta") or {}
                c = d.get("content")
                if c:
                    parts.append(c)
                tc = d.get("tool_calls")
                if tc:
                    n_tool_calls += len(tc)
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
            if obj.get("usage"):
                usage = obj["usage"]
            if verbose and time.time() - last > 5.0:
                last = time.time()
                print("    ... %.0fs, %d chars" % (time.time() - t0, sum(len(p) for p in parts)),
                      flush=True)
    except socket.timeout:
        stall = True
        err = "stall: no bytes for %ss" % stall_timeout
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
    return {
        "elapsed_s": round(time.time() - t0, 2),
        "ttft_s": None if ttft is None else round(ttft, 2),
        "finish_reason": finish,
        "usage": usage,
        "answer_chars": sum(len(p) for p in parts),
        "tool_calls": n_tool_calls,
        "answer_head": "".join(parts)[:200],
        "stall": stall,
        "error": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--model-id", default="qwen3.8-27b")
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--messages", type=int, default=10)
    ap.add_argument("--tools", type=int, default=32)
    ap.add_argument("--doc-chars", type=int, default=100000)
    ap.add_argument("--max-tokens", type=int, default=65536)
    ap.add_argument("--stall-timeout", type=float, default=600.0)
    ap.add_argument("--outdir", default=os.path.join("logs", "a4_requests"))
    ap.add_argument("--print-payload", action="store_true")
    args = ap.parse_args()

    tools = make_tools(args.tools)
    doc = make_doc(args.doc_chars)
    messages = build_messages(args.messages, doc)
    os.makedirs(args.outdir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")

    print("target http://%s:%d/v1/chat/completions" % (args.host, args.port))
    print("profile: tools=%d messages=%d doc_chars=%d max_tokens=%d turns=%d"
          % (len(tools), len(messages), args.doc_chars, args.max_tokens, args.turns), flush=True)

    for turn in range(1, args.turns + 1):
        payload = {
            "model": args.model_id,
            "messages": messages,
            "tools": tools,
            "max_tokens": args.max_tokens,
            "stream": True,
        }
        print("[turn %d/%d] sending ..." % (turn, args.turns), flush=True)
        r = one_request(args.host, args.port, payload, args.stall_timeout, True)
        tag = "STALL" if r["stall"] else ("ERR" if r["error"] else "OK")
        print("[turn %d] %s elapsed=%ss ttft=%ss finish=%s usage=%s content_chars=%d tool_calls=%d"
              % (turn, tag, r["elapsed_s"], r["ttft_s"], r["finish_reason"], r["usage"],
                 r["answer_chars"], r["tool_calls"]), flush=True)
        if r["error"]:
            print("        error: %s" % r["error"], flush=True)
        if r["answer_head"]:
            print("        head: %s" % r["answer_head"].replace("\n", " ")[:160], flush=True)
        rec = dict(r)
        rec.update({"turn": turn, "port": args.port, "model": args.model_id,
                    "n_tools": len(tools), "n_messages": len(messages),
                    "doc_chars": args.doc_chars, "max_tokens": args.max_tokens})
        with open(os.path.join(args.outdir, "%s-turn%02d.json" % (stamp, turn)), "w",
                  encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
        if args.print_payload and turn == 1:
            with open(os.path.join(args.outdir, "%s-payload.json" % stamp), "w",
                      encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
        if r["stall"] or r["error"]:
            print("[stop] turn %d not OK -- stopping the run." % turn, flush=True)
            return 2
    print("done: %d turn(s)." % args.turns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
