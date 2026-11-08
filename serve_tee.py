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

日志文件双写（环境变量 SERVE_TEE_LOG_MODE，默认 slim）：
  slim = 双写：
    · 明文 `<logfile>`：ERROR/WARN/FATAL 及其**前 50 行上下文**、生命周期行（engine ready /
      capacity / memory ledger / listening / loading weights / req#N done）、启动 DEBUG
      —— 体量约 2%，可直接 grep；
    · gzip `<logfile>.gz`：**全部原始行**，零损失，事后 DEBUG / 时序分析的唯一完整来源
      —— 体量约 1.4%（心跳行重复度极高，压缩比约 94x）。
    实测同一份 28,049 行日志：双写合计 3.50%，而"采样丢弃"方案是 7.74% —— 采样用更大
    的体积换了更少的证据，故弃用。
  full = 只写明文全量，不生成 .gz（grep 取证 / 时序分析用）。
强制 full 的四种情形（同步写进 项目硬规则.mdc「日志分级纪律」）：
  ① 死亡谷探针 / 慢态排查（心跳时序是判据）
  ② KVMem 判活 / 检索验证（kvmem_score 行是判据本身）
  ③ 一切预登记实验（判据测前写死，slim 模式的明文不含心跳，违约）
  ④ 起服命令带 --log-level debug（本脚本自动切 full，不靠人记）
⚠ slim 模式下心跳行（[ninfer] ensure profile / [ring] budgets）只在 .gz 里，明文没有；
  需要看它们请 `zcat <logfile>.gz | grep ...`，或事前切 full。

colorama 可选：有则启用 Windows ANSI/VT 色码；无则降级无色，不阻断 serve。
"""
import collections
import gzip
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


# ============ 日志双写（2026-11-08 用户批准：明文关键行 + gzip 全量）============
# 实测：单个压测日志 28,049 行里 98.6% 是两类心跳（[ninfer] ensure profile 18,112 +
# [ring] budgets 9,056），关键行仅 0.5%。
# 同一份日志三种写法体积：明文采样 7.74% / 全量 gzip 1.06% / 双写合计约 3.2%。
# gzip 比采样更小且零损失，故弃用采样：明文只留关键行，gzip 收全量。
CONTEXT_LINES = 50        # ERROR/FATAL 命中时向前保留进明文的上下文行数
GZ_ROTATE_EVERY = 128     # 每 N 行关闭并重开 gzip 成员（多成员文件），强杀最多丢 N 行

_LIFECYCLE_MARKS = (
    "engine ready", "capacity |", "memory ledger", "listening on",
    "loading weights", "req#", "done |", "serve_tee start", "serve_tee end",
    "LAUNCH FAILED", "artifact inspected", "device profile",
)
_ERROR_RE = re.compile(r"(?:^|\s)(ERROR|FATAL|WARN|WARNING)(?:\s|$)")


def classify_line(text):
    """返回 (kind, pattern)。

    kind: keep=进明文（错误/生命周期）/ plain=进明文（其余正常行）/ sample=只进 gzip（仪表噪声）。
    """
    if _ERROR_RE.search(text):
        return "keep", "error"
    for mark in _LIFECYCLE_MARKS:
        if mark in text:
            return "keep", "lifecycle"
    # 纯仪表噪声：只进 gzip，不进明文（否则明文会被心跳淹没）
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
    """双写日志器。

    明文（<logfile>）：ERROR/WARN/FATAL 及其前 CONTEXT_LINES 行、生命周期行、启动 DEBUG
                     —— 体量小、可直接 grep。
    gzip（<logfile>.gz）：全部原始行，零损失，事后 DEBUG 的唯一完整来源。

    为什么不再"采样丢弃"：实测同一份 28,049 行日志，明文采样方案 7.74%、全量 gzip 仅 1.06%
    —— gzip 反而小 7 倍且一行不丢（心跳行重复度极高，压缩比约 94x）。采样等于用更大的体积
    换更少的证据。
    """

    def __init__(self, plain, gz_path):
        self.plain = plain
        self.gz_path = gz_path
        self.gz = None
        self.context = collections.deque(maxlen=CONTEXT_LINES)
        self.plain_lines = 0
        self.total_lines = 0
        self._since_rotate = 0
        if gz_path:
            self._open_gz()

    def _open_gz(self):
        try:
            # "ab" 追加新成员：多成员 gzip 文件，zcat / gzip -dc / python gzip 都能顺序读。
            # 这样 tee 被强杀时最多丢最后一个成员，已写成员各自带完整尾部标记，仍可解压。
            self.gz = gzip.open(self.gz_path, "ab", compresslevel=6)
        except Exception:
            self.gz = None

    def _rotate_gz(self):
        if self.gz is None:
            return
        try:
            self.gz.close()      # 写完整尾部（CRC32 + ISIZE）
        except Exception:
            pass
        self._open_gz()

    def _w_gz(self, raw):
        if self.gz is None:
            return
        try:
            self.gz.write(raw)
            self._since_rotate += 1
            if self._since_rotate >= GZ_ROTATE_EVERY:
                self._rotate_gz()
                self._since_rotate = 0
        except Exception:
            pass

    def _w_plain(self, raw):
        try:
            self.plain.write(raw)
            self.plain_lines += 1
        except Exception:
            pass

    def _flush_context(self):
        while self.context:
            self._w_plain(self.context.popleft())

    def feed(self, raw, text):
        self.total_lines += 1
        self._w_gz(raw)                     # 全量先落 gzip：任何情况下都不丢证据
        kind, pat = classify_line(text)
        if kind == "keep":
            if pat == "error":
                self._flush_context()       # 洞①：报错前因一并写进明文
            self._w_plain(raw)
        elif kind == "plain":
            self._w_plain(raw)
        else:
            self.context.append(raw)        # 心跳只在内存候命当错误前因，gzip 里已有全量

    def finish(self):
        if self.gz is not None:
            try:
                self.gz.close()      # 写完整尾部，正常退出时零损失
            except Exception:
                pass


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
    # 双写：明文只留关键行；gzip 收全量（零损失，事后 DEBUG 靠它）。full 模式只写明文。
    sampler = LogSampler(log, (logfile + ".gz") if log_mode != "full" else None)
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

    code = proc.wait()
    tail = ("===== serve_tee end (exit={}) {} =====\n".format(
        code, time.strftime("%Y-%m-%d %H:%M:%S"))).encode("utf-8", "replace")
    # 收尾行走统一路径：同时进明文与 gzip，保证两条时间线都完整
    if log_mode == "full":
        try:
            log.write(tail)
        except Exception:
            pass
    else:
        sampler.feed(tail, tail.decode("utf-8", "replace"))
    sampler.finish()     # 关闭 gzip 成员（写完整尾部）

    try:
        sys.stdout.buffer.write(tail)
        sys.stdout.buffer.flush()
    except Exception:
        pass
    log.close()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
