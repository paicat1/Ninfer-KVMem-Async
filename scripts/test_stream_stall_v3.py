# -*- coding: utf-8 -*-
"""test_stream_stall_v3.py - 挂账41 第三次复现（v3 规模修正版）

前两次失败教训（构建史 §14）：
  ① 昨晚: output 4,000 在 20s 内被读光 -> 请求已 done, "冻结"是伪象;
  ② 上午: 请求未达引擎(无 started 行), harness 自身故障;
  ③ 机理: 停读后 OS 接收缓冲(~64KB autotuning)仍在收, SSE 载荷必须 > 缓冲
     才可能让引擎 send 阻塞 —— 4K output(~16KB) 物理上不可能复现。

v3 关键参数:
  - output 上限 16,000 (req#4 现场规模 16,213; SSE 载荷 ~64-100KB, 临界可堵);
  - 20s 真停读(应用层不再 read, socket 保持打开) —— 模拟 DSH 停读;
  - 判据 A: 引擎日志出现 req#N started (上次核心修正: 请求到达判据);
  - 判据 B(冻结): 停读后引擎 throughput 行停止 + CPU 双采样 delta≈0;
  - 判据 C(恢复): close 后引擎 cancel/abort + 新请求可服务。

用法: python test_stream_stall_v3.py
"""
import http.client
import json
import subprocess
import sys
import time

HOST, PORT = "127.0.0.1", 8094
LOG = r"J:\ninfer-kvmem\logs\serve_20261011_v1c2_resume.log"

PROMPT = ("Write a 4000-word lighthouse story with rich atmosphere. " * 8)


def tail_log(n=3):
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              f"Get-Content '{LOG}' -Tail {n} -Encoding UTF8"],
                             capture_output=True, text=True, timeout=15)
        return out.stdout.strip().splitlines()
    except Exception:
        return []


def engine_running_marker():
    """日志里找本实验的 req started/done/cancel 行(与本地时间戳同钟可对齐)。"""
    lines = tail_log(12)
    return [l.strip()[:150] for l in lines if any(
        k in l for k in ("req#", "cancel", "abort", "throughput"))]


def cpu_sample():
    p = subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(Get-Process ninfer-serve -ErrorAction SilentlyContinue).CPU"],
                       capture_output=True, text=True, timeout=15)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def main():
    print(f"[{time.strftime('%H:%M:%S')}] v3: open stream, output cap 16000, read 20s then STALL")
    conn = http.client.HTTPConnection(HOST, PORT, timeout=600)
    body = json.dumps({
        "model": "qwen3.8-27b-coder390", "stream": True,
        "max_tokens": 16000,
        "messages": [{"role": "user", "content": PROMPT}],
    }).encode()
    conn.request("POST", "/v1/chat/completions", body=body,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    print(f"[{time.strftime('%H:%M:%S')}] HTTP {resp.status}; reading 20s ...")
    t_end = time.time() + 20
    got = 0
    while time.time() < t_end:
        chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
        if not chunk:
            break
        got += len(chunk)
    print(f"[{time.strftime('%H:%M:%S')}] read-phase done ({got} bytes). NOW STOP READING (socket kept open).")

    # ---- 停读观察 100s: 每 20s 采样引擎 CPU + 日志 ----
    c0 = cpu_sample()
    for i in range(5):
        time.sleep(20)
        c1 = cpu_sample()
        delta = (c1 - c0) if (c1 is not None and c0 is not None) else None
        marks = engine_running_marker()
        tp = [l for l in marks if "throughput" in l]
        print(f"[{time.strftime('%H:%M:%S')}] stall t+{(i+1)*20}s  CPU-delta={delta}  "
              f"last-tp={tp[-1][:110] if tp else 'NONE'}")
        c0 = c1 if c1 is not None else c0

    print(f"[{time.strftime('%H:%M:%S')}] closing connection (client gives up) ...")
    conn.close()
    time.sleep(15)
    print("[after close] engine marks:")
    for l in engine_running_marker():
        print("   ", l)

    # ---- 恢复判据: 新请求可服务 ----
    try:
        c2 = http.client.HTTPConnection(HOST, PORT, timeout=120)
        b2 = json.dumps({"model": "qwen3.8-27b-coder390", "stream": False,
                         "max_tokens": 8,
                         "messages": [{"role": "user", "content": "Say OK."}]}).encode()
        c2.request("POST", "/v1/chat/completions", body=b2,
                   headers={"Content-Type": "application/json"})
        r2 = c2.getresponse()
        d2 = r2.read()
        print(f"[RECOVERY-PROBE] HTTP {r2.status} -> {'SERVED OK' if r2.status == 200 else 'FAILED'}")
        c2.close()
    except Exception as e:
        print(f"[RECOVERY-PROBE] EXCEPTION: {e} -> ENGINE STILL STUCK")


if __name__ == "__main__":
    main()
