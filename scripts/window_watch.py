# -*- coding: utf-8 -*-
"""window_watch.py v2 -- 跨天"窗口 Watch"（每分钟一行：主机态 × 引擎态时间线）。只读、不碰引擎。

v2 修的三处（2026-10-16 07:1x，按 TELE 审核：tools 侧缺陷已认）：
  ① **新鲜度**：v1 取"文件里最后一条 target-split"⇒ 引擎一旦不再打印（空闲/健康），
     该字段永远复读旧值（台账 0410 段 157 行恒 228.32，实测铁证）。
     v2 改为**按字节偏移只解析自上次采样以来新增的行**；无新增 ⇒ 写 `stale`（显式）。
     同时支持日志轮转（文件变小 ⇒ 偏移归零重读）。
  ② **单位 bug**：`Win32_OperatingSystem.FreePhysicalMemory` 单位是 **KB**，v1 却 `/1MB`（÷1048576）⇒
     数值**小 1024 倍**（台账里的"98MiB"实为 ~98 GiB，曾致我把宿主内存误读为"几乎耗尽"）。
     v2 用 `/1024` 得 MiB，列名改为显式 `freemem_mib=`；`pf_mib=` 直接用 `Win32_PageFileUsage.CurrentUsage`（本就是 MB）。
  ③ **语义标注**（TELE 要求明确）：`target-split` 的**打印门**（源码 `speculative_round.cu:268-306`）为
        verbose（`NINFER_SPIN_STAMP_VERBOSE`）⇒ 每轮都打；
        否则 **慢轮（总跨度 >100 ms）最多打 60 次**，**健康轮只打前 3 次**。
     ⇒ `verify` 字段**能"发现谷"（慢轮会打点），但不能"判定健康"**（无新点 ≠ 健康，是"无新信息"）；
     ⇒ **60 次用满后即使深谷也不再打点**（遥测盲区）——自然窗观测必须开 VERBOSE（本脚本据此给 `ts_lines=` 便于估测用量）。
  ④ **decode 口径（2026-10-17 06:1x 实测修正，勿混用）**：本脚本的 decode 取自引擎 `throughput | <win>s | … decode X tok/s (N tok)`，
     是**固定窗口（实测 5.0 s）内的平均**：轻探针 199 tok / 5.0 s ⇒ 报 **39.8**；
     而 a2gate 探针报的是**单请求生成速率**（同为 200 tok，实耗 ~1.2 s ⇒ 报 **165**）。
     ⇒ **两者不是同一个量，差约 4 倍**；判据 "decode<60 = 谷" 指的是 **a2gate 的口径**，
     **拿本字段去套会把健康（39.8）误判成谷** ⇒ 字段已改名 `decode_win5s=` 以示区别。

行格式（`w2` 版本标记；v1 行无标记，其 freemem/pf 需 ×1024 解读、verify/decode 需按"最后写入行"解读）：
  MM-DD HH:MM:SS | w2 | up=<h> cpu=<%> freemem_mib=<MiB> pf_mib=<MB> top=<a/b/c> | gpu=<sm,pwr,util,mem> | \
  verify=<ms|stale> decode_win5s=<tok/s|stale> newlines=<n> ts_lines=<n> | s13=<cyN:ok|stale>
"""
import io
import os
import re
import subprocess
import time

ROOT = r'J:\ninfer-kvmem'
LOG = os.path.join(ROOT, 'logs', 'test_valleywatch.log')
OUT = os.path.join(ROOT, '.temp', 'windowwatch_%s.txt' % time.strftime('%Y%m%d_%H%M'))
HOURS = float(os.environ.get('WATCH_HOURS', '12'))
INTERVAL = float(os.environ.get('WATCH_INTERVAL', '60'))
VER = 'w2'
RE_VERIFY = re.compile(r'verify=([\d.]+)')
RE_DECODE = re.compile(r'throughput \| [\d.]+s \| (?:prefill [\d.]+ tok/s \([\d,]+ tok\) \| )?decode ([\d.]+) tok/s')


def sh(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=25)
        return (r.stdout or '').strip()
    except Exception:
        return ''


def host_state():
    ps = ("$o=Get-CimInstance Win32_OperatingSystem;$p=Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue;"
          "$up=[math]::Round(((Get-Date)-$o.LastBootUpTime).TotalHours,1);"
          "$free=[math]::Round($o.FreePhysicalMemory/1024,0);"
          "$pf=if($p){[math]::Round($p.CurrentUsage,0)}else{-1};"
          "$top=(Get-Process | Sort-Object CPU -Descending | Select-Object -First 3 | ForEach-Object { $_.Name }) -join '/';"
          "$cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
          "Write-Output ($up.ToString()+'|'+$cpu.ToString()+'|'+$free.ToString()+'|'+$pf.ToString()+'|'+$top)")
    return sh('powershell -NoProfile -Command "' + ps.replace('"', "'") + '"')


def gpu_state():
    return sh('nvidia-smi --query-gpu=clocks.sm,power.draw,utilization.gpu,memory.used --format=csv,noheader,nounits').replace(' ', '')


class LogTail(object):
    """按字节偏移只读新增行；处理轮转。"""

    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.ts_total = 0
        if os.path.exists(path):
            self.offset = os.path.getsize(path)
            try:
                with io.open(path, encoding='utf-8', errors='replace') as fh:
                    self.ts_total = sum(1 for l in fh if 'target-split' in l)
            except Exception:
                pass

    def poll(self):
        """返回 (verify 或 None, decode 或 None, 新增行数)。"""
        if not os.path.exists(self.path):
            return None, None, 0
        try:
            size = os.path.getsize(self.path)
        except Exception:
            return None, None, 0
        if size < self.offset:          # 轮转
            self.offset = 0
            self.ts_total = 0
        if size == self.offset:
            return None, None, 0
        try:
            with io.open(self.path, encoding='utf-8', errors='replace') as fh:
                fh.seek(self.offset)
                chunk = fh.read()
                self.offset = size
        except Exception:
            return None, None, 0
        lines = chunk.splitlines()
        ver, dec = None, None
        for l in lines:                                     # 只在【新增行】里找最后一条
            if 'target-split' in l:
                self.ts_total += 1
                m = RE_VERIFY.search(l)
                if m:
                    ver = m.group(1)
            m2 = RE_DECODE.search(l)
            if m2:
                dec = m2.group(1)
        return ver, dec, len(lines)


def s13_state():
    d = os.path.join(ROOT, '.temp')
    try:
        fs = [f for f in os.listdir(d) if f.startswith('s13_') and f.endswith('.txt')]
    except Exception:
        return '-'
    if not fs:
        return '-'
    p = os.path.join(d, sorted(fs)[-1])
    try:
        age = time.time() - os.path.getmtime(p)
        tail = io.open(p, encoding='utf-8', errors='replace').readlines()[-1].strip()
    except Exception:
        return '-'
    m = re.search(r'cy(\d+)', tail)
    tag = 'ok' if 'VALLEY' not in tail else 'VALLEY'
    if age > 300:
        return 'cy%s:%s/stale(%.0fm)' % (m.group(1) if m else '?', tag, age / 60.0)
    return 'cy%s:%s' % (m.group(1) if m else '?', tag)


def main():
    tail = LogTail(LOG)
    end = time.time() + HOURS * 3600
    io.open(OUT, 'w', encoding='utf-8').write(
        '# window watch v%s (freshness-aware) -- %s\n'
        '# verify/decode 只在【新增行】里取；无新增行写 stale。target-split 打印门见文件头注释。\n'
        % (VER, time.strftime('%Y-%m-%d %H:%M:%S')))
    n = 0
    while time.time() < end:
        n += 1
        h = host_state().split('|')
        ver, dec, added = tail.poll()
        line = '%s | %s | up=%sh cpu=%s%% freemem_mib=%s pf_mib=%s top=%s | gpu=%s | verify=%s decode_win5s=%s newlines=%d ts_lines=%d | s13=%s' % (
            time.strftime('%m-%d %H:%M:%S'), VER,
            h[0] if len(h) > 0 else '?', h[1] if len(h) > 1 else '?', h[2] if len(h) > 2 else '?',
            h[3] if len(h) > 3 else '?', (h[4] if len(h) > 4 else '?')[:60],
            gpu_state(),
            (ver if ver is not None else 'stale'), (dec if dec is not None else 'stale'),
            added, tail.ts_total, s13_state())
        with io.open(OUT, 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
        if n % 10 == 0:
            print(line, flush=True)   # 2026-10-17：不加 flush 时控制台按块缓冲 ⇒ 窗口长期空白
        time.sleep(INTERVAL)
    print('window watch v%s done -> %s (%d samples)' % (VER, OUT, n))


if __name__ == '__main__':
    main()
