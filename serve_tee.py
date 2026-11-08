# -*- coding: utf-8 -*-
"""serve_tee.py <logfile> <command...>

以"可见控制台窗口"运行 <command...>（引擎），把它的 stdout+stderr **实时转发到控制台**
并**同时落盘**到 <logfile> —— 供 grep 取证（如 `kvmem_score: SELECT`）。
关闭本控制台窗口 = 终止本进程 = 引擎随控制台退出（**关窗=停服**）。
颜色：控制台窗口给关键数字上色（decode 绿 / prefill 黄 / 接受率红）；**日志文件始终原文**（不带色，保 grep）。

窗口显示模式（环境变量 SERVE_TEE_MODE，默认 slim）：
  slim = 精简：
    · 整段隐藏：KVMem KEPT 刷屏行 + 引擎硬编码诊断行（[ring] budgets / [ninfer] mask hidden /
      [ninfer] demote-other short）；
    · 同段只留首末：kvmem_score: SELECT / [ninfer] ring retrieve: / [ninfer] kvmem harvest:；
    · 业务行（INFO/WARN/ERROR、decode/prefill/accept 读数）全显。
  full = 全部：不过滤（查错用）。

日志文件分级采样（环境变量 SERVE_TEE_LOG_MODE，默认 slim）：
  slim = 分级：ERROR/WARN/FATAL 及其**前 50 行上下文**、生命周期行（engine ready / capacity /
         memory ledger / listening / loading weights / req#N done）、启动 DEBUG 全留；
         仪表心跳（[ring] budgets / [ninfer] ensure profile / mask hidden / demote-other /
         kvmem_score KEPT / 纯数字续行）按「同 pattern 的**极大连续序列**」采样：
         **段首必留 + 段内每 200 留 1 + 段末补写**。
  full = 全文落盘（grep 取证 / 时序分析用）。
强制 full 的四种情形（同步写进 项目硬规则.mdc「日志分级纪律」）：
  ① 死亡谷探针 / 慢态排查（心跳时序是判据）
  ② KVMem 判活 / 检索验证（kvmem_score 行是判据本身）
  ③ 一切预登记实验（判据测前写死，采样版日志违约）
  ④ 起服命令带 --log-level debug（本脚本自动切 full，不靠人记）
⚠ 心跳行（[ninfer] ensure profile / [ring] budgets）**没有时间戳前缀**，采样后是孤立点，
  只能看趋势；任何时序分析必须 full。

colorama 可选：有则启用 Windows ANSI/VT 色码；无则降级无色，不阻断 serve。
"""
import collections
import os
import re
import subprocess
import sys
import time

try:
    import colorama  # 可选依赖：启用 Windows ANSI/VT 色码渲染（缺失时降级为无色）
    colorama.init()
except ImportError:
    colorama = None

# ---- 颜色（ANSI 256 / VT100）----
C_RED    = "\033[91m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RESET  = "\033[0m"


def is_kept_noise(line):
    """判定是否为 KVMem KEPT 刷屏行（只在**控制台窗口**过滤，**日志文件仍全文落盘**保 grep）。两种形态：
    ① `kvmem_score: KEPT <数字...>`；
    ② 引擎把**超长 KEPT 拆行**后的**纯数字续行**（无前缀，如 " 1009 1010 … 1143"）——之前漏网就是漏了它。
    业务行都含时间戳/字母（`20xx-… INFO …`），不会被②误伤。"""
    if line.startswith("kvmem_score: KEPT"):
        return True
    s = line.strip()
    return len(s) >= 8 and all(ch.isdigit() or ch == " " for ch in s)


def is_select(line):
    """判定是否为 KVMem 的**逐块决策/恢复行** —— 精简模式下**同段只留首末条**（保留趋势、去掉刷屏）：

      · `kvmem_score: SELECT ...` 内容评分选页决策；
      · `[ninfer] ring retrieve: which=.. preferred=.. restored=.. first=.. last=..`
        host -> device 的页恢复（用户 2026-10-10 反馈它同样刷屏）。

    这两类在长上下文请求里会连续打几十行，但**都有诊断价值**（能看出某段恢复了多少页、
    评分选中了哪些块），所以按"同段首末压缩"处理，而不是像 budgets/mask hidden 那样整段隐藏。
    """
    return (line.startswith("kvmem_score: SELECT")
            or line.startswith("[ninfer] ring retrieve:"))


def is_diag_noise(line):
    """引擎的**硬编码 fprintf(stderr) 诊断行**：无开关、按步/按映射打印，实测严重刷屏。
    slim 模式下窗口隐藏；**日志文件仍全文落盘**（查错时切 SERVE_TEE_MODE=full 或直接 grep 日志）。

    三类及出处（2026-10-10 取证）：
      ① `[ring] budgets: skeleton=.. evidence=.. recent=.. free=.. (pool ..)`
         context.cpp:2481 —— **每次映射都打**，是刷屏主力；
      ② `[ninfer] mask hidden: which=.. site=.. span=.. resident=.. hidden=..`
         context.cpp:2136 —— 源码注释本意是"隐藏 0 页就静默（no per-step spam）"，
         但实测常态 hidden=1 -> **每步都打**；
      ③ `[ninfer] demote-other short: freed=.. want=.. slots=.. invalid=..`
         context.cpp:1925 —— 降级不足时打；常态 freed=0 want=1 每轮都出现。

    注意：这三类在**异常**场景下仍有信息量（如 host KV 不足、掩码异常），
    所以只在窗口的 slim 模式隐藏，日志文件与 full 模式一律保留。
    """
    return (line.startswith("[ring] budgets:")
            or line.startswith("[ninfer] mask hidden:")
            or line.startswith("[ninfer] demote-other short:"))


def is_harvest_note(line):
    """KVMem harvest 告警行（`[ninfer] kvmem harvest: ...`，chunk 未进索引）。
    精简模式下与 SELECT 同段处理，**不打断**首末压缩。"""
    return line.startswith("[ninfer] kvmem harvest:")


# ============ 日志分级采样（2026-11-08 用户批准修正版方案）============
# 实测：单个压测日志 28,049 行里 98.6% 是两类心跳（[ninfer] ensure profile 18,112 +
# [ring] budgets 9,056），关键行仅 0.5%。四个洞的处置见文件头 docstring。
SAMPLE_EVERY = 200        # 段内采样间隔
CONTEXT_LINES = 50        # ERROR/FATAL 命中时向前保留的上下文行数

_LIFECYCLE_MARKS = (
    "engine ready", "capacity |", "memory ledger", "listening on",
    "loading weights", "req#", "done |", "serve_tee start", "serve_tee end",
    "LAUNCH FAILED", "artifact inspected", "device profile",
)
_ERROR_RE = re.compile(r"(?:^|\s)(ERROR|FATAL|WARN|WARNING)(?:\s|$)")


def classify_line(text):
    """返回 (kind, pattern)。kind: keep=全留 / sample=按段采样 / plain=全留但非关键。"""
    if _ERROR_RE.search(text):
        return "keep", "error"
    for mark in _LIFECYCLE_MARKS:
        if mark in text:
            return "keep", "lifecycle"
    # 纯仪表噪声统一归一个 pattern：两类心跳每步交替出现，若按类型分 pattern 会碎片化成
    # 每段 1 行，"段首必留"就等于全留。合并后连续序列才够长，采样才有效。
    if (text.startswith("[ninfer] ensure profile")
            or is_kept_noise(text)
            or is_diag_noise(text)):
        return "sample", "heartbeat"
    if is_select(text):
        return "sample", "select"
    if is_harvest_note(text):
        return "sample", "harvest"
    return "plain", None


class LogSampler:
    """流式分级写入器。

    段 = 同一 pattern 的**极大连续序列**（当前行 pattern 与前一行相同 = 同段延续）。
    段内规则：第 1 条必留；之后每 SAMPLE_EVERY 条留 1；段结束时若末条未被上述采样点写过则补写。
    误差容忍：被丢弃的采样行仍进 context 缓冲，ERROR/FATAL/WARN 命中时先 flush 该缓冲，
    保证报错前因（栈前的诊断行）不会因为采样而失明。
    """

    def __init__(self, handle):
        self.log = handle
        self.context = collections.deque(maxlen=CONTEXT_LINES)
        self.pattern = None
        self.count = 0
        self.last_raw = None
        self.written = 0
        self.dropped = 0

    def _write(self, raw):
        try:
            self.log.write(raw)
            self.written += 1
        except Exception:
            pass

    def _flush_context(self):
        while self.context:
            self._write(self.context.popleft())

    def _close_segment(self):
        # 只补写段末那一条，绝不动 context —— context 是"错误前因"专用缓冲，
        # 正常收尾时若把它 flush 出去，等于把采样丢弃的心跳又全写回，采样彻底失效。
        if (self.pattern and self.count > 1
                and self.count % SAMPLE_EVERY != 0 and self.last_raw is not None):
            self._write(self.last_raw)          # 段末补写
        self.pattern = None
        self.count = 0
        self.last_raw = None

    def feed(self, raw, text):
        kind, pat = classify_line(text)
        if kind == "keep":
            self._close_segment()
            if pat == "error":
                self._flush_context()           # 洞①：仅报错时补前因（心跳不至于污染正常路径）
            self._write(raw)
            return
        if kind == "plain":
            self._close_segment()
            self._write(raw)
            return
        # sample
        if pat != self.pattern:
            self._close_segment()
            self.pattern = pat
            self.count = 0
        self.count += 1
        if self.count == 1 or self.count % SAMPLE_EVERY == 0:
            # 采样点只写本行，**绝不 flush context** —— 否则每 200 条就把前 199 条
            # 被丢弃的心跳整批写回，采样等于没做（首版实现就栽在这里）。
            self._write(raw)
        else:
            self.context.append(raw)   # 仅作为 ERROR 前因保留（deque 自动淘汰）
            self.dropped += 1
        self.last_raw = raw

    def finish(self):
        # 收尾同样不 flush context：那是被采样丢弃的心跳，写回去等于前功尽弃。
        # 只有真正发生 ERROR/FATAL 时才算"前因"，而那时 feed() 内部已即时 flush。
        self._close_segment()


def colorize(line):
    """给日志行中的关键数据上色：decode数值(绿)、接受率%(红)、prefill数值(黄)。
    直接输出 ANSI/VT 色码 —— 本终端原生支持，无需 colorama。"""
    # decode 数值 -> 绿："decode 129.6 tok/s"
    line = re.sub(r"(decode )(\d+(?:\.\d+)?)( tok/s)",
                  lambda m: m.group(1) + C_GREEN + m.group(2) + C_RESET + m.group(3), line)
    # 接受率（任意 "… accepted … (N%)"，如 mixed speculation / mtp / dflash2）-> 红
    line = re.sub(r"(accepted[^()]*\()(\d+(?:\.\d+)?%)\)",
                  lambda m: m.group(1) + C_RED + m.group(2) + C_RESET + ")", line)
    # prefill 数值 -> 黄："prefill 1.43k tok/s" / "prefill 146.7 tok/s"
    line = re.sub(r"(prefill )([\d.]+k?)( tok/s)",
                  lambda m: m.group(1) + C_YELLOW + m.group(2) + C_RESET + m.group(3), line)
    return line


def main(argv):
    if len(argv) < 3:
        sys.stderr.write("usage: serve_tee.py <logfile> <command...>\n")
        return 2
    logfile = argv[1]
    cmd = argv[2:]
    # 窗口显示模式（环境变量 SERVE_TEE_MODE，由启动器注入）：slim=精简 / full=全部（查错）
    #   slim：KEPT 刷屏行隐藏；SELECT 只保留**每段首条+末条**；业务行全显。
    #   full：不过滤，全部显示。**两种模式日志文件都全文落盘**（保 grep 取证）。
    mode = os.environ.get("SERVE_TEE_MODE", "slim").strip().lower()
    if mode not in ("slim", "full"):
        mode = "slim"
    # 日志文件模式（2026-11-08）：默认 slim = 分级采样；full = 全文（grep 取证 / 时序分析）
    log_mode = os.environ.get("SERVE_TEE_LOG_MODE", "slim").strip().lower()
    if log_mode not in ("slim", "full"):
        log_mode = "slim"
    # 洞④：起服命令显式带 --log-level debug 时自动切 full（要细看的人才会开 debug），不靠人记
    if log_mode != "full" and "--log-level" in cmd:
        try:
            if cmd[cmd.index("--log-level") + 1].strip().lower() == "debug":
                log_mode = "full"
        except (ValueError, IndexError):
            pass
    d = os.path.dirname(logfile)
    if d:
        os.makedirs(d, exist_ok=True)
    log = open(logfile, "ab", buffering=0)
    sampler = LogSampler(log)
    header = ("\n===== serve_tee start {} =====\nCMD: {}\n".format(
        time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(cmd))).encode("utf-8", "replace")
    log.write(header)
    try:
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.flush()
    except Exception:
        pass

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
    except Exception as e:
        log.write(("LAUNCH FAILED: {}\n".format(e)).encode("utf-8", "replace"))
        log.close()
        return 1

    def emit(text):
        """窗口显示一行（上色后）。"""
        try:
            sys.stdout.buffer.write(colorize(text).encode("utf-8", "replace"))
            sys.stdout.buffer.flush()
        except Exception:
            pass

    sel_buf = []

    def flush_sel():
        """把本段连续 SELECT 的**首条+末条**打到窗口，中间重复的丢弃（精简模式）。"""
        if not sel_buf:
            return
        emit(sel_buf[0])
        if len(sel_buf) > 1:
            emit(sel_buf[-1])
        sel_buf.clear()

    out = proc.stdout
    while True:
        raw = out.readline()
        if not raw:
            break
        text = raw.decode("utf-8", "replace")
        if mode == "full":
            emit(text)                       # 全部：不过滤
        else:                                # 精简
            if is_kept_noise(text) or is_diag_noise(text):
                pass                         # KEPT 刷屏行 + 引擎诊断行（budgets / mask hidden / demote-other short）：窗口隐藏
            elif is_select(text) or is_harvest_note(text):
                sel_buf.append(text)         # SELECT / harvest 告警：同段攒着，段末只留首末
            else:
                flush_sel()
                emit(text)
        if log_mode == "full":
            try:
                log.write(raw)      # 全文模式：原文落盘（grep 取证 / 时序分析）
            except Exception:
                pass
        else:
            sampler.feed(raw, text)  # 分级模式：按类采样，ERROR 前因完整
    if mode == "slim":
        flush_sel()      # 收尾最后一段（窗口）
    sampler.finish()     # 收尾：补段末 + flush 上下文缓冲

    code = proc.wait()
    tail = ("===== serve_tee end (exit={}) {} =====\n".format(
        code, time.strftime("%Y-%m-%d %H:%M:%S"))).encode("utf-8", "replace")
    try:
        sys.stdout.buffer.write(tail)
        sys.stdout.buffer.flush()
    except Exception:
        pass
    log.write(tail)
    log.close()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
