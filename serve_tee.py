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
**两种模式日志文件都全文落盘**（保 grep 取证）。

colorama 可选：有则启用 Windows ANSI/VT 色码；无则降级无色，不阻断 serve。
"""
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
    d = os.path.dirname(logfile)
    if d:
        os.makedirs(d, exist_ok=True)
    log = open(logfile, "ab", buffering=0)
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
        try:
            log.write(raw)  # 日志文件始终原文全文（不带色，保 grep 取证）
        except Exception:
            pass
    if mode == "slim":
        flush_sel()  # 收尾最后一段

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
