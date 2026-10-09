# -*- coding: utf-8 -*-
"""NInfer 启动器（本线 ninfer-kvmem / 模型 Coder390）

用途：点选参数 → 实时预览启动命令 → 起服（可见窗口，关窗=停服）→ 就绪自测。
零外部依赖（仅 Python 自带 tkinter / urllib / json / subprocess）。

对照施工方案：
  · S1 起服：定稿档 = MTP（--spec mtp --draft-tokens 4）；构造出的参数与实测起服成功的命令逐字一致
    （见 docs\\ninfer-kvmem-项目构建史.md §4.4 与三·九）
  · S2 就绪判据：判活必须真发请求（/v1/models 200 ≠ 能服务）
  · 参数铁律：KVMem 五环境变量自动注入；--max-shared-prefixes 0 / --max-concurrency 1 强制

版本：v1（覆盖起服 + 自检/就绪自测）。
沿革：本文件最初为前序 Bonsai 线所写；2026-10-09（P0）迁移到 Coder390，2026-10-10 按用户裁决
      清除全部 Bonsai 口径（档位 / 脚本 / UI 文本），本线不再保留任何 Bonsai 引用。
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import urllib.request
import urllib.error

# ---------------------------------------------------------------
# 常量：路径与基础参数
# ---------------------------------------------------------------
ROOT        = os.path.dirname(os.path.abspath(__file__))          # 项目根（便携：不写死盘符）
ENGINE      = os.path.join(ROOT, "engine", "ninfer-serve-120a.exe")            # 官方成品（无 Design C）
ENGINE_DIR  = os.path.dirname(ENGINE)
ENGINE_SELF = os.path.join(ROOT, "engine", "self-built-20261008", "ninfer-serve.exe")   # 自编·现役（20261008 + 全部补丁）
ENGINE_PREV = os.path.join(ROOT, "engine", "self-built", "ninfer-serve.exe")           # 前序回退锚（20261003）——P0 实测：本线 engine\ 下**无** self-built\ 目录，此路径**不存在**（GUI 选中会给出"未找到引擎"提示，不会崩）
# 2026-10-10 用户裁决后的收口：下拉只留【自编·现役】一项。原三项的两个问题：
#   · self_prev（engine\self-built\ninfer-serve.exe）—— **该目录本线不存在**，选中只会报"未找到引擎"（死项）；
#   · official（engine\ninfer-serve-120a.exe）—— 文件在，但 P0b 已裁定本线统一用 self-built：
#     它含 Design C（思考停止强制进 answer）而官方件没有 -> 行为路径不同，混用污染 A/B 对照；
#     且官方件是否支持 rk2v4-e8 / --spec mtp 从未验证（选了可能是第二个坑）。
#   ENGINE / ENGINE_PREV 两个常量保留（供将来临时改回或命令行引用），只是不再进下拉。
ENGINE_OPTIONS = {
    "self": ("自编·现役(20261008)", ENGINE_SELF),
}
# P0 (2026-10-09): 本线模型换成 Coder390（旧值 Ternary-Bonsai-2-27B-ninfer-v3.ninfer 属前序 Bonsai 线，本线 models\ 不存在该文件）
# P1b (2026-10-09): 指向【自转 iq4_nl 版】。原件 MTP 头是 gguf_q4_0（引擎不支持，--spec mtp 必失败），
#   .mtp-iq4nl.ninfer 把该头转成 gguf_iq4_nl（与原件等长，全量 L1 通过），**裸解码与 MTP 两种模式都用它**。
#   实测定稿（同模型同 prompt，唯一变量 --spec mtp）：散文 decode 55.4→73.2 tok/s（接受率 22.6%）、
#   代码 184.3 tok/s（接受率 93.8%）；输出语义一致无劣化。
MODEL       = os.path.join(ROOT, "models", "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer")

# ---------------------------------------------------------------
# 模型档（2026-10-10 用户裁决新增）
#   WHY: GUI 必须能切模型。否则"要用视觉就得换官方版"这条只能靠 bat 实现，
#        而实际上没人用 bat，全在启动器上选 —— 那样 vision 就是死功能。
#   iq4nl : 自转 MTP 头（gguf_iq4_nl，239 MB）—— ★定稿；**无 vision 组件**
#   q8mtp : 官方 Q8MTP 版（MTP 头 q8_0 = 451 MB，比 iq4nl 多 212 MB）—— **唯一含 vision 组件**；
#           选它时 GUI 会自动把 --kv-capacity 降到 20480（否则 40K 池起不来，实测过）
#   orig  : 原件（MTP 头是引擎不支持的 gguf_q4_0 -> 只能裸解码，做纯基线）
#   注：这里的 argv 列表留空 —— 模型是引擎的**位置参数**（第一个），不走 --flag。
# ---------------------------------------------------------------
MODEL_OPTIONS = {
    "iq4nl": ("★iq4_nl 定稿（自转 MTP 头 · 无视觉）", []),
    "q8mtp": ("官方 Q8MTP（含视觉 · 选它自动降池 20K）", []),
    "orig":  ("原件（纯基线 · MTP 不可用）", []),
}
MODEL_PATHS = {
    "iq4nl": os.path.join(ROOT, "models",
                          "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"),
    "q8mtp": os.path.join(ROOT, "models",
                          "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-Q8MTP.ninfer"),
    "orig":  os.path.join(ROOT, "models",
                          "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"),
}
# 选官方 Q8MTP 时自动降到的池（实测：40K 起不来，20K 起服 free 663 MiB）
MODEL_KVCAP_MAX = {"q8mtp": "20480"}
CONFIG_FILE = os.path.join(ROOT, "ninfer_launcher_profiles.json")
LOG_DIR = os.path.join(ROOT, "logs")
TEE_SCRIPT = os.path.join(ROOT, "serve_tee.py")
PORT_DEFAULT = 8094
# tee 需要“带控制台”的 python.exe（GUI 以 pythonw 运行，用它起 tee 会得空白窗口）
PYTHON_EXE = sys.executable.replace("pythonw.exe", "python.exe").replace("pythonw", "python")

# 池 token 数（= config 里的 --kv-capacity）。硬约束 = 单请求的【prompt_tokens + 输出(max_tokens) ≤ 池】：
# 超过则 (a) 未开止血 → worker 崩且不自愈；或 (b) 开了 --kv-lease-growth（E5 止血）→ 被静默截断(finish_reason=length、
# 内容像正常但只有半截)。--default-max-tokens 只是服务端默认上限，不是硬约束。
# P1b (2026-10-09) 定稿值 = 40960（对应 --kv-capacity 40960）。实测：40960 起服成功（runtime 1.71 GiB /
#   free 449.6 MiB）；49152 缺 49 MiB（临界）、65536 缺 320 MiB。池扩容极便宜（rk2v4-e8 下 ≈0.83 MB/页）。
#   ⚠️ 池 < 逻辑上下文（--max-context 262144）是**设计如此**：池外的页由 KVMem 环下沉到 host
#   （--host-kv-mib 16384）；实测 20,203 tokens prompt 检索答案正确（ring retrieve restored=128）。
KV_POOL_TOKENS = 40960

# KVMem 五开关：缺一 = 起得来但静默答错（缓存命中率高、中段答错、零报错）。GUI 内固定注入。
# ⚠️ NINFER_KV_WINDOW 同时是"允许 --kv-capacity < --max-context"的开关（serve_options.cpp:1124-1132）：
#    不设它，引擎强制要求 kv-capacity ≥ max-context 并拒绝启动（--kv-capacity must be at least --max-context）。
KV_ENV = {
    "NINFER_KV_WINDOW":          "32768",
    "NINFER_KV_RETRIEVE":        "8192",
    "NINFER_KV_RING":            "1",
    "NINFER_HOST_PAGEABLE":      "1",
    "NINFER_KV_REUSE_HOSTBACKED": "1",
}

# ---------------------------------------------------------------
# 维度定义：key -> {value: (显示名, 附加参数列表)}
# ---------------------------------------------------------------
# 投机解码：键 -> (显示名, 参数)。k0=无, k1..k5=MTP, d1..d15=DFlash2
# 对齐旧项目写法：MTP 与 DFlash2 都提供完整 K 值 1..N，不写死单一档。
SPEC_OPTIONS = {"k0": ("无（裸档 · 慢 · A/B 对照用）", [])}
SPEC_OPTIONS.update({f"k{i}": (f"MTP K={i}" + ("（★本线定稿）" if i == 4 else ""),
                               ["--spec", "mtp", "--draft-tokens", str(i)])
                     for i in range(1, 6)})
SPEC_OPTIONS.update({f"d{i}": (f"DFlash2 K={i}（本线不可行·包内无该组件）",
                               ["--spec", "dflash2", "--draft-tokens", str(i), "--lm-head-draft"])
                     for i in range(1, 16)})
KV_OPTIONS = {
    "k8v4":     ("k8v4（官方默认）", ["--kv-dtype", "k8v4"]),
    "rk8v4":    ("rk8v4",           ["--kv-dtype", "rk8v4"]),
    "rk4v4":    ("rk4v4",           ["--kv-dtype", "rk4v4"]),
    "rk4v4-e8": ("rk4v4-e8",        ["--kv-dtype", "rk4v4-e8"]),
    "rk2v4-e8": ("rk2v4-e8（★本线定稿 · 5080 最省）", ["--kv-dtype", "rk2v4-e8"]),
    "nvfp4":    ("nvfp4",           ["--kv-dtype", "nvfp4"]),
    "fp8":      ("fp8",             ["--kv-dtype", "fp8"]),
    "int8":     ("int8",            ["--kv-dtype", "int8"]),
    "bf16":     ("bf16",            ["--kv-dtype", "bf16"]),
}
CTX_OPTIONS = {
    "32k":  ("32K",   ["--max-context", "32768"]),
    "64k":  ("64K",   ["--max-context", "65536"]),
    "128k": ("128K",  ["--max-context", "131072"]),
    "150k": ("150K",  ["--max-context", "153600"]),
    "160k": ("160K",  ["--max-context", "163840"]),
    "170k": ("170K",  ["--max-context", "174080"]),
    "180k": ("180K",  ["--max-context", "184320"]),
    "200k": ("200K",  ["--max-context", "204800"]),
    "224k": ("224K",  ["--max-context", "229376"]),
    "256k": ("256K（★本线定稿 · 模型原生上限）", ["--max-context", "262144"]),
}
KVCAP_OPTIONS = {
    "40960": ("40960（★本线定稿 · 40K 全速池）", ["--kv-capacity", "40960"]),
    "49152": ("49152（48K · 需清 GPU 占用才起得来）", ["--kv-capacity", "49152"]),
    "20480": ("20480（20K · 更省显存）",      ["--kv-capacity", "20480"]),
    "17920": ("17920（官方默认）",         ["--kv-capacity", "17920"]),
    "auto":  ("auto（按剩余显存）",   ["--kv-capacity", "auto"]),
    "16k":     ("16K",  ["--kv-capacity", "16384"]),
    "32k":     ("32K",  ["--kv-capacity", "32768"]),
    "64k":     ("64K",  ["--kv-capacity", "65536"]),
    "128k":    ("128K", ["--kv-capacity", "131072"]),
    "150k":    ("150K", ["--kv-capacity", "153600"]),
    "160k":    ("160K", ["--kv-capacity", "163840"]),
    "170k":    ("170K", ["--kv-capacity", "174080"]),
    "180k":    ("180K", ["--kv-capacity", "184320"]),
    "200k":    ("200K", ["--kv-capacity", "204800"]),
    "224k":    ("224K", ["--kv-capacity", "229376"]),
    "256k":    ("256K", ["--kv-capacity", "262144"]),
}
HOSTKV_OPTIONS = {
    "16384": ("16384（★本线定稿）", ["--host-kv-mib", "16384"]),
    "8192":  ("8192",            ["--host-kv-mib", "8192"]),
    "32768": ("32768（主机内存够大时可试）", ["--host-kv-mib", "32768"]),
}
PREFILL_OPTIONS = {
    "1024": ("1024（官方默认）", ["--prefill-chunk", "1024"]),
    "512":  ("512（★本线定稿 · 省 workspace）", ["--prefill-chunk", "512"]),
    "2048": ("2048",           ["--prefill-chunk", "2048"]),
}
# ⚠️ 本模型是 Coder390-**EfficientThink**：思考是它的核心能力，定稿必须开。
#    "思考不额外占显存"（只是多生成 token）—— 关思考既不省显存、也没好处。
THINK_OPTIONS = {
    "none":   ("none（关思考 · 仅 A/B 对照）", ["--default-reasoning-effort", "none"]),
    "low":    ("low",                      ["--default-reasoning-effort", "low"]),
    "medium": ("medium（省 token）",        ["--default-reasoning-effort", "medium"]),
    "high":   ("high（★本线定稿 · EfficientThink 必开）", ["--default-reasoning-effort", "high"]),
    "off":    ("--no-thinking（强制关 · 仅对照）", ["--no-thinking"]),
}
MAXOUT_OPTIONS = {
    "default": ("默认(65535)", []),
    "4096":    ("4096",     ["--default-max-tokens", "4096"]),
    "8192":    ("8192",     ["--default-max-tokens", "8192"]),
    "16384":   ("16384",    ["--default-max-tokens", "16384"]),
    "32768":   ("32768（★本线定稿）", ["--default-max-tokens", "32768"]),
    "1024":    ("1024",     ["--default-max-tokens", "1024"]),
}
# 视觉：**只有【官方 Q8MTP 版】含 vision 组件**（本线的 .mtp-iq4nl.ninfer 与原件都没有 -> 任何 --vision* 都会
# "missing component vision" 起不来）。实测（构建史 §三·十，2026-10-10）：官方版 + --vision-cpu 起服成功，
# weights 12.3→12.5 GiB、runtime 1.44 GiB、free 663.4 MiB，**设备视觉显存占用为零**；
# 代价：图片被压到 256 merged tokens（约 512x512）、CPU 编码慢（one to a few seconds）。
VISION_OPTIONS = {
    "on":      ("开·GPU 编码器（视觉塔常驻显存 ~1.4G；需官方版模型）", ["--vision"]),
    "overlay": ("开·主机内存 overlay（视觉塔驻 host，按图借设备内存）", ["--vision", "--vision-residency", "overlay"]),
    "cpu":     ("开·CPU 编码器（★不占设备视觉显存；需官方版模型）", ["--vision-cpu"]),
    "off":     ("关（★本线定稿 · 纯文本配置）",   []),
}
SAMPLE_OPTIONS = {
    "shipped":  ("官方(0.7/0.9/20, presence0)（★本线定稿）", ["--presence-penalty", "0", "--temperature", "0.7", "--top-p", "0.9", "--top-k", "20"]),
    "thinking": ("思考档(1.0/0.95/20)",          ["--presence-penalty", "0", "--temperature", "1.0", "--top-p", "0.95", "--top-k", "20"]),
    "greedy":   ("贪心(greedy)",                 ["--greedy"]),
}
# 官方 B01 止血开关（官方出厂件已有、官方启动器未写）：防“超池+大输出租约 -> worker 崩/进程静默退出”。
HEMOSTAT_OPTIONS = {
    "on":  ("开（★本线定稿 · 防 B01 崩溃）", ["--kv-lease-growth", "--recover-invariant-failures"]),
    "off": ("关（官方 bat 原样）", []),
}
# 思考预算档：--default-thinking-budget N —— 治“思考墙死循环”（xhigh 思考烧光输出预算 → 空正文）。
# 这是服务端(argv)级设置；OpenAI chat 端点不解析请求里的 thinking_budget 字段（仅 Anthropic 的 thinking.budget_tokens 读它）。
TB_OPTIONS = {
    "none":   ("无（不设上限 · 有思考墙风险）",      []),
    "8000":   ("8000",          ["--default-thinking-budget", "8000"]),
    "12000":  ("12000",         ["--default-thinking-budget", "12000"]),
    "16000":  ("16000（★本线定稿 · 防思考墙）",  ["--default-thinking-budget", "16000"]),
    "24000":  ("24000",         ["--default-thinking-budget", "24000"]),
    "32000":  ("32000",         ["--default-thinking-budget", "32000"]),
}
CONC_OPTIONS = {
    "1": ("1（★本线定稿 · 单路确定性）", ["--max-concurrency", "1"]),
    "2": ("2",                ["--max-concurrency", "2"]),
    "4": ("4",                ["--max-concurrency", "4"]),
}
PRESERVE_OPTIONS = {
    "off": ("关（★本线定稿）", []),
    "on":  ("开（保留思考）", ["--preserve-thinking"]),
}

DIMENSIONS = [
    ("model",  "模型",            MODEL_OPTIONS),   # 2026-10-10: 模型是第一选择（视觉只有官方版有）
    ("spec",   "档位 / 投机解码", SPEC_OPTIONS),
    ("kv",     "KV 类型",         KV_OPTIONS),
    ("ctx",    "上下文",          CTX_OPTIONS),
    ("kvcap",  "KV 容量",         KVCAP_OPTIONS),
    ("hostkv", "主机 KV (MiB)",   HOSTKV_OPTIONS),
    ("prefill","prefill 块",      PREFILL_OPTIONS),
    ("think",  "思考模式",         THINK_OPTIONS),
    ("tb",     "思考预算",         TB_OPTIONS),
    ("maxout", "输出上限",        MAXOUT_OPTIONS),
    ("vision", "视觉",            VISION_OPTIONS),
    ("sample", "采样",            SAMPLE_OPTIONS),
    ("conc",   "并发",            CONC_OPTIONS),
    ("preserve","保留思考",        PRESERVE_OPTIONS),
    ("hemostat", "止血(B01)",     HEMOSTAT_OPTIONS),
]

# 默认组合（P0 2026-10-09 适配 Coder390；P1b 2026-10-09 按实测参数定稿）：
#   spec   : "k4" = MTP K=4（本线已跑通；要裸解码基线请显式选 "k0"）
#   vision : "off"——Coder390 容器**没有 vision 组件**，置 on 会让引擎在 companion("vision") 处抛
#            "missing component vision" 而启动失败（这是硬阻塞，不是"省显存"选项）
# 沿革：前序 Bonsai 口径（spec="d12" + vision="on"）的档位已于 2026-10-10 按用户裁决整批删除。
DEFAULTS = {
    # ★P1b 定稿（2026-10-09 实测定型，详见 docs\ninfer-kvmem-项目构建史.md §4.4）：
    #   spec    k4       = MTP K=4（本线已通；要裸解码对照请选 "k0"）
    #   kv      rk2v4-e8 = 最省 KV 格式（2bit key + 4bit value；5080 实测可用，输出与 k8v4 语义一致）
    #   ctx     256k     = 262144 = 模型原生上限（逻辑上下文；池外部分下沉 host）
    #   kvcap   40960    = 40K 全速池（显存内直接可读的范围）
    #   prefill 512      = 比官方 1024 省 workspace（实测起服余量更大）
    #   think   high     = ★2026-10-10 用户裁决：本模型是 Coder390-**EfficientThink**，
    #                      **思考是它的核心能力**（"不思考没法用"）。原定稿 "none" 是照抄
    #                      旧 Bonsai 口径的残留，属错误配置，已改。
    #                      ⚠️ **思考不额外占显存**（只是多生成 token），关思考既不省显存也没好处。
    #   tb      16000    = 思考预算上限，防"思考墙死循环"（思考烧光输出预算 → 空正文）。
    #                      OpenAI chat 端点不转发请求里的 thinking_budget，只能靠服务端此参数。
    "model": "iq4nl",
    "spec": "k4", "kv": "rk2v4-e8", "ctx": "256k", "kvcap": "40960", "hostkv": "16384",
    "prefill": "512", "think": "high", "tb": "16000", "maxout": "32768", "vision": "off",
    "sample": "shipped", "conc": "1", "preserve": "off", "hemostat": "on",
}

# v1 旧档位值 -> 新档位值 迁移表：旧 profile 的 spec 存的是 "dflash2"/"mtp"，
# 新档位内部值已改为 "d12"/"k4" 等；加载时自动迁移，避免旧命名组合失效。
LEGACY_VALUE_MAP = {
    ("spec", "dflash2"): "d12",
    ("spec", "mtp"):     "k4",
}

DIM_TIPS = {
    "spec":   "投机解码（只加速解码）。k0=无；k1..k5=MTP；d1..d15=DFlash2（K 越大猜得越多，d12=官方首起档）。改档需重启 serve。",
    "kv":     "KV 缓存精度。★本线定稿 rk2v4-e8（2bit key + 4bit value，最省；5080 实测可用，输出与 k8v4 语义一致）。官方默认 k8v4；异常时换一档试。",
    "ctx":    "上下文长度（--max-context，**逻辑上限**）。★定稿 256K = 262144（模型原生上限）。注意：池外的页由 KVMem 环下沉到 host，实测 20K prompt 检索仍正确且不慢。",
    "kvcap":  "KV 池容量（--kv-capacity）= 显存里能直接读的 KV token 数（即\"全速区间\"）。★定稿 40960（40K）；扩容极便宜（rk2v4-e8 下 ≈0.83 MB/页）：48K 需先清 GPU 占用、64K 缺 320 MiB。auto = 按剩余显存最大化。",
    "hostkv": "Host 侧 KV 预算（MiB，--host-kv-mib）。官方默认 16384。",
    "prefill":"文本 prefill 分块（--prefill-chunk，128 的倍数）。官方默认 1024。",
    "think":  "思考模式。官方默认 none（关思考）。启用思考后注意 §4.2 的“思考完空正文”已知问题。",
    "tb":     "思考预算上限（--default-thinking-budget，每回合最多思考 token）。治“思考墙死循环”：xhigh 思考烧光输出预算→空正文。越小越省时，审核/批量建议小；长逻辑建议大。⚠ OpenAI 端点不转发请求里的 thinking_budget，只能靠服务端此参数。",
    "maxout": "服务端默认输出上限（--default-max-tokens）。⚠ 定稿池 = 40960 tokens；单请求【prompt_tokens + 输出】留在池内可避免 host 往返；开了 --kv-lease-growth 时超池会被静默截断(finish_reason=length)。",
    "vision": "视觉（多模态）。GPU 编码器=默认，视觉塔常驻显存(~1.4G)；overlay=视觉塔驻 pinned 主机内存、仍走 GPU 算（折中，需可驱逐尾部支撑）；cpu=视觉塔走 CPU 线程、无设备视觉显存（引擎自动把 --vision-max-merged 压到 256，每图慢）。显存紧：优先 overlay，其次 cpu；不用视觉就关。",
    "sample": "采样预设。默认 = 官方值 0.7/0.9/20、presence 0。",
    "conc":   "并发请求数（--max-concurrency）。多请求吞吐用大值；单会话保持 1（确定性）。",
    "preserve":"保留已关闭回合的 assistant 推理（--preserve-thinking）。多轮长对话要前序思考时开。",
    "hemostat":"官方 B01 止血：--kv-lease-growth（租约按需增长，掐掉“超池+大输出 -> worker 崩”的触发条件）+ --recover-invariant-failures（出问题只废当前请求、不弄死引擎）。官方出厂件有，官方 bat 未写。",
}

# 命名组合预置（首次运行若无配置文件则落盘）
PRESET_PROFILES = {
    # —— ★本线 Coder390 定稿（P1b 2026-10-09 实测定型，见构建史 §4.4）——
    # 注：Bonsai 线的全部预设（起服-dflash档 / 备用-MTP档 / 省显存-视觉* / 思考预算-16000 /
    #     长文档-224K / 并发4-吞吐）已按用户裁决（2026-10-10）**整批删除**：
    #     本线模型无 dflash2 / vision 组件，那些档位选中必失败；且它们引用的是 Bonsai 口径的
    #     旧参数，留着只会与下面的定稿档混淆。Bonsai 相关内容一律不进本线。
    "Coder390-MTP 定稿":    dict(DEFAULTS),                        # MTP K4 + 256K ctx + 40K 池 + rk2v4-e8
    "Coder390-裸解码对照":  dict(DEFAULTS, spec="k0"),              # 无投机（所有 A/B 的对照臂）
    "Coder390-MTP 大池":    dict(DEFAULTS, kvcap="49152"),          # 48K 池（实测缺 49 MiB；清 GPU 占用后可能过）
    "Coder390-MTP 省显存":  dict(DEFAULTS, kvcap="20480"),          # 20K 池（余量最大，长上下文靠 host）
    "Coder390-思考 medium":  dict(DEFAULTS, think="medium", tb="16000", sample="thinking"),
    "Coder390-关思考对照":    dict(DEFAULTS, think="none", tb="none"),   # 仅 A/B 对照：本模型不思考没法用
    "Coder390-视觉档":       dict(DEFAULTS, model="q8mtp", vision="cpu", kvcap="20480"),  # 官方版 + CPU 视觉（零设备视觉显存）
}


# ---------------------------------------------------------------
# 校验 / 命令构造
# ---------------------------------------------------------------
def validate(combo, exe=None):
    """返回告警列表（空 = 无告警）。"""
    exe = exe or ENGINE_SELF     # 2026-10-10: 与"下拉只留自编现役"一致（原为官方件）
    warns = []
    mx = str(combo.get("maxout", "default"))
    mx_val = 65535 if mx == "default" else (int(mx) if mx.isdigit() else 0)  # "default"=65535；非数字安全跳过（照老项目：不裸 int 转换）
    if mx_val > KV_POOL_TOKENS:
        warns.append(f"输出上限({mx}) > 池 token 数({KV_POOL_TOKENS})——官方默认如此；"
                     f"真正的硬约束 = 单请求【prompt_tokens + 输出(max_tokens) ≤ {KV_POOL_TOKENS}】："
                     f"超过会在 prefill 阶段超池——(a)未开止血→worker 崩且不自愈、(b)已开 --kv-lease-growth→"
                     f"被静默截断(finish_reason=length、内容像正常但只有半截)。发请求时请确保 prompt 长度 + max_tokens ≤ {KV_POOL_TOKENS}。")
    if not os.path.exists(exe):
        warns.append(f"未找到引擎：{exe}")
    _mp = MODEL_PATHS.get(combo.get("model", "iq4nl"), MODEL)
    if not os.path.exists(_mp):
        warns.append(f"未找到模型：{_mp}")
    if combo.get("model") == "q8mtp" and str(combo.get("kvcap", "20480")) != "20480":
        warns.append("官方 Q8MTP 的 MTP 头是 q8_0（451 MB，比 iq4_nl 多 212 MB）-> 池大于 20480 起不来"
                     "（实测 40K 缺 100+ MiB）。选它时 GUI 会自动把池降到 20480。")
    if combo.get("model") == "orig" and str(combo.get("spec", "k0")) != "k0":
        warns.append("原件（-MTP.ninfer）的 MTP 头是引擎不支持的 gguf_q4_0 -> 只能裸解码（档位选 k0）。")
    if any(ord(c) > 127 for c in ROOT):
        warns.append("项目路径含非 ASCII 字符——引擎会以 invalid UTF-8 byte 启动即挂")
    return warns


def _argv_of(table, value, fallback_key):
    """安全取某维度参数（照老项目 D8）：未知/缺失值回退到默认项，避免裸下标 KeyError 崩 GUI。"""
    ent = table.get(value)
    if ent is None:
        ent = table.get(fallback_key)
    return ent[1] if ent else []


def build_command(combo, port=PORT_DEFAULT, exe=None):
    """返回 (exe, argv)。argv 为引擎参数（不含 exe）；与实测起服成功的定稿命令逐字一致（构建史 §4.4 / 三·九），另含 B01 止血两旗（hemostat=on，可关）。
    取值一律经 _argv_of() 回退（照老项目 D8），profile 含旧/未知键值也不 KeyError。
    exe=None 时用自编现役（ENGINE_SELF，本线唯一现役引擎）。"""
    exe = exe or ENGINE_SELF     # 2026-10-10: 与"下拉只留自编现役"一致（原为官方件）
    model_path = MODEL_PATHS.get(combo.get("model", "iq4nl"), MODEL)   # 2026-10-10: 模型档（位置参数）
    argv = [model_path, "--host", "127.0.0.1", "--port", str(port), "--model-id", "qwen3.8-27b-coder390"]
    argv += _argv_of(CTX_OPTIONS,     combo.get("ctx", "256k"),      "256k")
    argv += _argv_of(KVCAP_OPTIONS,   combo.get("kvcap", "40960"),   "40960")  # P1b: 回退对齐 DEFAULTS（原 "17920"）
    argv += _argv_of(KV_OPTIONS,      combo.get("kv", "rk2v4-e8"),   "rk2v4-e8")  # P1b: 回退对齐 DEFAULTS（原 "k8v4"）
    argv += _argv_of(HOSTKV_OPTIONS,  combo.get("hostkv", "16384"),  "16384")
    argv += _argv_of(PREFILL_OPTIONS, combo.get("prefill", "512"),   "512")    # P1b: 回退对齐 DEFAULTS（原 "1024"）
    argv += _argv_of(SPEC_OPTIONS,    combo.get("spec", "k4"),       "k4")     # P1b: 回退对齐 DEFAULTS（原 "k0"；要裸解码请显式选 k0）
    argv += _argv_of(VISION_OPTIONS,  combo.get("vision", "off"),    "off")    # P0: 回退与 DEFAULTS 对齐（原为 "on"，Coder390 无 vision 组件会启动失败）
    argv += _argv_of(MAXOUT_OPTIONS,  combo.get("maxout", "32768"),  "32768")
    argv += _argv_of(THINK_OPTIONS,   combo.get("think", "none"),    "none")
    argv += _argv_of(TB_OPTIONS,      combo.get("tb", "none"),       "none")
    argv += _argv_of(CONC_OPTIONS,    combo.get("conc", "1"),        "1")
    argv += _argv_of(PRESERVE_OPTIONS, combo.get("preserve", "off"), "off")
    argv += ["--max-shared-prefixes", "0"]   # 铁律：防打砖
    argv += _argv_of(SAMPLE_OPTIONS,  combo.get("sample", "shipped"), "shipped")
    argv += _argv_of(HEMOSTAT_OPTIONS, combo.get("hemostat", "on"),  "on")   # B01 止血（E5 决定：默认开）
    return exe, argv


def env_for_launch(exe=None):
    env = dict(os.environ)
    env.update(KV_ENV)
    # P0b (2026-10-09): PATH 必须同时含 exe 所在目录 **与 engine\ 根目录**。
    #   理由：自编件在 engine\self-built-20261008\，但它**动态依赖 cublas64_13.dll**
    #   （实测：全文件搜索 1.27GB exe 命中 "cublas64_13"），而该 DLL **只在 engine\ 根**
    #   （自编子目录只有 cudart64_13）。只加 dirname(exe) 时，自编件会回退到系统 PATH 的
    #   cublas —— 实测本机系统 PATH 首个命中 = J:\Bonsai\landing\cuda-13.3\bin\x64
    #   （**前序已封存线的目录**），版本 6.14.11.1360 ≠ 打包版 6.14.11.1351
    #   -> 结果不确定、且隐式依赖外部线。加入 ENGINE_DIR 后固定用打包版（确定性 + 自包含）。
    _parts, _seen, _uniq = [os.path.dirname(exe or ENGINE_SELF), ENGINE_DIR], set(), []
    for _p in _parts:
        if _p and _p not in _seen:
            _seen.add(_p)
            _uniq.append(_p)
    env["PATH"] = os.pathsep.join(_uniq) + os.pathsep + env.get("PATH", "")
    return env


# ---------------------------------------------------------------
# 组合持久化
# ---------------------------------------------------------------
def load_profiles():
    """读取命名组合。损坏时**留痕不静默**（照老项目 D5：避免“一次崩溃后组合无声消失”），原文件不改动。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                return data
            print(f"[profiles] 文件为空/格式异常（{CONFIG_FILE}）——回退内置预设；原文件未改动，可手工修复。")
        except Exception as e:
            print(f"[profiles] 读取失败（{CONFIG_FILE}）：{e}")
            print("[profiles] 已回退内置预设；原文件未改动，可手工修复。")
    return dict(PRESET_PROFILES)


def save_profiles(profiles):
    """原子写：先写临时文件 + fsync，再 os.replace（照老项目 D5），避免崩溃/断电把全部组合写坏或写空。"""
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_FILE)


# ---------------------------------------------------------------
# 探测：S0 环境自检 / S2 就绪自测（全部只读）
# ---------------------------------------------------------------
def env_check():
    lines = []
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=20)
        lines.append("GPU: " + (r.stdout.strip() or r.stderr.strip()))
    except Exception as e:
        lines.append("GPU: 探测失败 " + str(e))
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ninfer-serve*", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=20)
        out = r.stdout.strip()
        lines.append("ninfer-serve 进程: " + (out if out else "(无)"))
    except Exception as e:
        lines.append("ninfer-serve 进程: 探测失败 " + str(e))
    return lines


def readiness_test(port=PORT_DEFAULT):
    """S2：/v1/models + 真发一条请求。返回 [ (标题, 结果, 摘要) ]。"""
    res = []
    base = f"http://127.0.0.1:{port}"
    # 1) /v1/models
    try:
        with urllib.request.urlopen(base + "/v1/models", timeout=15) as r:
            body = r.read().decode("utf-8", "replace")
            res.append(("GET /v1/models", str(r.status), body[:400]))
    except Exception as e:
        res.append(("GET /v1/models", "ERR", str(e)))
    # 2) 真发请求（判活必须真发；max_tokens 取安全小值）
    payload = json.dumps({
        "model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "用一句话回答：1+1 等于几？"}],
        "max_tokens": 64, "temperature": 0,
    }).encode("utf-8")
    req = urllib.request.Request(base + "/v1/chat/completions", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            j = json.loads(r.read().decode("utf-8", "replace"))
            ch = (j.get("choices") or [{}])[0]
            content = (ch.get("message") or {}).get("content", "")
            fin = ch.get("finish_reason", "?")
            res.append(("POST /v1/chat/completions", str(r.status),
                        f"finish_reason={fin}\ncontent={content[:300]}"))
    except Exception as e:
        res.append(("POST /v1/chat/completions", "ERR", str(e)))
    return res


# ---------------------------------------------------------------
# 悬停提示
# ---------------------------------------------------------------
class ToolTip:
    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _e=None):
        if not self.text or self.tip is not None:
            return
        try:
            self.tip = tk.Toplevel(self.widget)
        except Exception:
            return
        try:
            self.tip.wm_overrideredirect(True)
            self.tip.attributes("-topmost", True)
        except Exception:
            pass
        try:
            tk.Label(self.tip, text=self.text, bg="#ffffe4", fg="#222",
                     font=("Microsoft YaHei UI", 9), wraplength=340, justify="left",
                     padx=8, pady=6).pack()
            x, y = self.widget.winfo_rootx(), self.widget.winfo_rooty()
            self.tip.wm_geometry(f"+{x+24}+{y+self.widget.winfo_height()+6}")
        except Exception:
            pass

    def _hide(self, _e=None):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


# ---------------------------------------------------------------
# 图形界面
# ---------------------------------------------------------------
class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Coder390 · NInfer 启动器（ninfer-kvmem）")   # P0: 标题原为 "Bonsai-27B-NInfer-kvmem 启动器"
        self.root.geometry("900x700")
        self.root.minsize(780, 660)
        self.bg, self.fg = "#f4f8ff", "#1a3a6b"
        self.root.configure(bg=self.bg)

        self.profiles = load_profiles()
        self.selection = dict(DEFAULTS)
        self.var = {}
        self._label2key = {}
        self.port_var = tk.StringVar(value=str(PORT_DEFAULT))
        self.logmode_var = tk.StringVar(value="精简")
        # P0b (2026-10-09): 默认引擎 = 「自编·现役」——A/B 一律用它（官方件保留在下拉里作交叉验证选项）。
        #   理由：self-built 含 Design C（thinking stop 强制进 answer），官方件无 -> 行为路径不同，
        #   混用会污染对照；且 self-built 是本线现役（交接文档指定、两个 start-coder390*.bat 已用）。
        self.engine_var = tk.StringVar(value=ENGINE_OPTIONS["self"][0])
        # 投机档两级联动：类型 + K 值（照老项目；初值由 DEFAULTS["spec"] 解析）
        _d = DEFAULTS["spec"]
        if _d == "k0":
            _st, _sk = "无", ""
        elif _d.startswith("k"):
            _st, _sk = "MTP", _d[1:]
        else:
            _st, _sk = "DFlash2", _d[1:]
        self.var_spec_type = tk.StringVar(value=_st)
        self.var_spec_k = tk.StringVar(value=_sk)
        self._build_widgets()
        self._refresh()

    def _build_widgets(self):
        main = tk.Frame(self.root, bg=self.bg)
        main.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(main, text="Coder390 · NInfer 启动器", font=("Microsoft YaHei UI", 15, "bold"),
                 bg=self.bg, fg="#1b4d8a").pack(anchor="w")
        tk.Label(main, text="Qwen3.8-27B-Coder390 · MTP + KVMem · RTX 5080 sm_120",
                 font=("Microsoft YaHei UI", 9), bg=self.bg, fg="#5a6b8a").pack(anchor="w", pady=(0, 6))

        # 端口行
        portrow = tk.Frame(main, bg=self.bg)
        portrow.pack(anchor="w", pady=(0, 6))
        tk.Label(portrow, text="端口:", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.port_entry = ttk.Entry(portrow, textvariable=self.port_var, width=8)
        self.port_entry.pack(side="left", padx=(4, 0))
        tk.Label(portrow, text="（官方默认 8094）", bg=self.bg, fg="#9b8c5a",
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(6, 0))
        # 日志显示模式（传给 serve_tee 窗口；日志文件两种模式都全文落盘）
        tk.Label(portrow, text="日志:", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(16, 0))
        self.logmode_cb = ttk.Combobox(portrow, state="readonly", width=6, textvariable=self.logmode_var,
                                       values=["精简", "全部"], font=("Microsoft YaHei UI", 9))
        self.logmode_cb.pack(side="left", padx=(4, 0))
        ToolTip(self.logmode_cb, "窗口日志显示：精简=只留每段 SELECT 首末条 + 业务行（KEPT 隐藏）；全部=不过滤（查错用）。日志文件两种模式都全文落盘。")
        # 引擎版本（官方成品 / 自编 Design C）——我们自己的引擎在此可选
        tk.Label(portrow, text="引擎:", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10)).pack(side="left", padx=(16, 0))
        self.engine_cb = ttk.Combobox(portrow, state="readonly", width=14, textvariable=self.engine_var,
                                      values=[v[0] for v in ENGINE_OPTIONS.values()], font=("Microsoft YaHei UI", 9))
        self.engine_cb.pack(side="left", padx=(4, 0))
        self.engine_cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh())
        ToolTip(self.engine_cb, "用哪个引擎起服：官方成品 / 自编（含 Design C，治思考区空正文）。预览与启动都用所选引擎。")

        # 左：参数区（可滚动）
        left_outer = tk.Frame(main, bg=self.bg)
        left_outer.pack(side="left", fill="y", padx=(0, 14))
        canvas = tk.Canvas(left_outer, bg=self.bg, highlightthickness=0, width=210)
        scroll = ttk.Scrollbar(left_outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.bg)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="y")
        scroll.pack(side="right", fill="y")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 场景预设（一键推荐组合，照老项目；源 = 内置 PRESET_PROFILES）
        preset_box = tk.LabelFrame(inner, text="场景预设（推荐）", font=("Microsoft YaHei UI", 10),
                                   bg=self.bg, fg="#2b3a6b")
        preset_box.pack(fill="x", pady=4)
        ToolTip(preset_box, "按场景一键套用推荐组合（官方线专用）。选择后自动填充下方参数。")
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(preset_box, state="readonly", textvariable=self.preset_var,
                                      width=22, font=("Microsoft YaHei UI", 9))
        self.preset_cb["values"] = list(PRESET_PROFILES.keys())
        self.preset_cb.bind("<<ComboboxSelected>>", self._apply_preset)
        self.preset_cb.pack(anchor="w", padx=8, pady=4)

        for key, label, opts in DIMENSIONS:
            box = tk.LabelFrame(inner, text=label, font=("Microsoft YaHei UI", 10), bg=self.bg, fg="#2b3a6b")
            box.pack(fill="x", pady=4)
            ToolTip(box, DIM_TIPS.get(key, ""))
            self._label2key[key] = {lbl: val for val, (lbl, _) in opts.items()}
            self.var[key] = tk.StringVar(value=opts[DEFAULTS[key]][0])
            if key == "spec":
                # 投机档两级联动（照老项目）：类型（无/MTP/DFlash2）+ K 值
                f = tk.Frame(box, bg=self.bg)
                f.pack(anchor="w", padx=8, pady=4)
                self.combo_spec_type = ttk.Combobox(f, state="readonly", width=9,
                                                    textvariable=self.var_spec_type, font=("Microsoft YaHei UI", 9))
                self.combo_spec_type["values"] = ["无", "MTP", "DFlash2"]
                self.combo_spec_type.bind("<<ComboboxSelected>>", self._on_spec_change)
                self.combo_spec_type.pack(side="left", padx=(0, 6))
                self.combo_spec_k = ttk.Combobox(f, state="readonly", width=6,
                                                 textvariable=self.var_spec_k, font=("Microsoft YaHei UI", 9))
                self.combo_spec_k.bind("<<ComboboxSelected>>", self._on_spec_change)
                self.combo_spec_k.pack(side="left")
                self._update_spec_k_range()
            else:
                cb = ttk.Combobox(box, state="readonly", textvariable=self.var[key], width=24,
                                  font=("Microsoft YaHei UI", 9))
                cb["values"] = list(self._label2key[key].keys())
                cb.bind("<<ComboboxSelected>>", lambda _e: self._on_change())
                cb.pack(anchor="w", padx=8, pady=4)

        # 右：预览 + 操作
        right = tk.Frame(main, bg=self.bg)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="启动命令预览", bg=self.bg, fg="#9b8c5a",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
        self.cmd_box = tk.Text(right, height=10, width=62, wrap="word", bg="white", fg="#1a1a1a",
                               bd=1, relief="solid", font=("Consolas", 9))
        self.cmd_box.pack(fill="both", expand=True)
        self.cmd_box.configure(state="disabled")

        self.status = tk.Label(right, text="", bg=self.bg, fg="#4a6b4a",
                               font=("Microsoft YaHei UI", 9), justify="left", anchor="w", wraplength=560)
        self.status.pack(anchor="w", pady=(6, 0))

        # 操作按钮
        btns = tk.Frame(right, bg=self.bg)
        btns.pack(fill="x", pady=(10, 4))
        ttk.Button(btns, text="启 动", command=self._launch, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="环境自检", command=self._env_check, width=10).pack(side="left", padx=6)
        ttk.Button(btns, text="就绪自测", command=self._readiness, width=10).pack(side="left", padx=6)

        # 命名组合
        combox = tk.Frame(right, bg=self.bg)
        combox.pack(fill="x", pady=(6, 2))
        tk.Label(combox, text="命名组合:", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        self.profile_cb = ttk.Combobox(combox, state="readonly", width=20, values=list(self.profiles.keys()))
        self.profile_cb.pack(side="left", padx=(6, 0))
        ttk.Button(combox, text="加载", command=self._load_profile).pack(side="left", padx=4)
        ttk.Button(combox, text="保存当前", command=self._save_profile).pack(side="left", padx=4)
        ttk.Button(combox, text="删除", command=self._del_profile).pack(side="left", padx=4)

        tk.Label(right, text="提示：启动后引擎在“新控制台窗口”里运行 —— 关掉那个窗口 = 停服。",
                 bg=self.bg, fg="#8a6b3a", font=("Microsoft YaHei UI", 9), wraplength=560,
                 justify="left").pack(anchor="w", pady=(6, 0))

    # ---- 事件 ----
    def _on_change(self):
        for key, var in self.var.items():
            if key == "spec":
                self.selection["spec"] = self._spec_key_from_ui()
            elif key in self._label2key:
                self.selection[key] = self._label2key[key].get(var.get(), self.selection.get(key))
            else:
                self.selection[key] = var.get()
        self._apply_model_coupling()
        self._refresh()

    def _apply_model_coupling(self):
        """模型档联动（2026-10-10 用户要求）：选官方 Q8MTP -> 自动把池降到 20480。

        WHY: 官方版 MTP 头是 q8_0（451 MB），比 iq4_nl 多 212 MB —— 40K 池实测起不来
        （缺 100+ MiB）。用户明确要求"用官方版就降池"，所以这里直接改，并同步下拉显示，
        避免"界面显示 40K、实际命令 20K"的不一致。
        """
        cap = MODEL_KVCAP_MAX.get(self.selection.get("model", "iq4nl"))
        if not cap:
            return
        cur = str(self.selection.get("kvcap", ""))
        try:
            too_big = int(cur) > int(cap)
        except ValueError:            # auto / 非数字：不动
            too_big = False
        if too_big:
            self.selection["kvcap"] = cap
            if "kvcap" in self.var and cap in KVCAP_OPTIONS:
                self.var["kvcap"].set(KVCAP_OPTIONS[cap][0])      # 同步下拉显示

    # ---- 投机档两级联动（照老项目）----
    def _update_spec_k_range(self):
        """按类型更新 K 下拉范围（无/MTP:1-5/DFlash2:1-15）。"""
        t = self.var_spec_type.get()
        if t == "无":
            self.combo_spec_k["values"] = []
            self.combo_spec_k.set("")
            self.combo_spec_k.config(state="disabled")
        elif t == "MTP":
            self.combo_spec_k["values"] = [str(i) for i in range(1, 6)]
            self.combo_spec_k.config(state="readonly")
        else:  # DFlash2
            self.combo_spec_k["values"] = [str(i) for i in range(1, 16)]
            self.combo_spec_k.config(state="readonly")
        cur = self.var_spec_k.get()
        if cur not in self.combo_spec_k["values"]:
            self.var_spec_k.set(self.combo_spec_k["values"][0] if self.combo_spec_k["values"] else "")

    def _on_spec_change(self, event=None):
        self._update_spec_k_range()
        self.selection["spec"] = self._spec_key_from_ui()
        self._refresh()

    def _spec_key_from_ui(self):
        """由类型+K 生成 spec 内部键（k0 / k1..k5 / d1..d15）。"""
        typ = self.var_spec_type.get()
        k = self.var_spec_k.get()
        if typ == "无":
            return "k0"
        if typ == "MTP":
            return f"k{k}" if k.isdigit() and 1 <= int(k) <= 5 else "k4"
        if typ == "DFlash2":
            return f"d{k}" if k.isdigit() and 1 <= int(k) <= 15 else "d12"
        return "k0"

    def _apply_spec_to_ui(self, val):
        """把 spec 内部键反设到两级下拉（供 场景预设/加载组合 共用）。"""
        if val == "k0":
            self.var_spec_type.set("无"); self.var_spec_k.set("")
        elif val.startswith("k"):
            self.var_spec_type.set("MTP"); self.var_spec_k.set(val[1:])
        elif val.startswith("d"):
            self.var_spec_type.set("DFlash2"); self.var_spec_k.set(val[1:])
        self._update_spec_k_range()

    def _apply_preset(self, _e=None):
        """场景预设一键套用（照老项目；源 = 内置 PRESET_PROFILES）。"""
        name = self.preset_var.get()
        preset = PRESET_PROFILES.get(name) or {}
        valid_keys = {d[0] for d in DIMENSIONS}
        for key, val in preset.items():
            if key not in valid_keys:
                continue
            opts = next(d[2] for d in DIMENSIONS if d[0] == key)
            if val not in opts:
                continue
            if key == "spec":
                self._apply_spec_to_ui(val)
            else:
                self.var[key].set(opts[val][0])
        self._on_change()
        self.status.config(text=f"已应用场景预设「{name}」", fg="#4a6b4a")

    def _engine_path(self):
        for _k, (lbl, path) in ENGINE_OPTIONS.items():
            if lbl == self.engine_var.get():
                return path
        return ENGINE_SELF      # 2026-10-10: 回退改为自编现役（原为官方件，与"统一 self-built"的裁决矛盾）

    def _refresh(self):
        self.selection = {k: self.selection.get(k, DEFAULTS[k]) for k in DEFAULTS}
        exe, argv = build_command(self.selection, self._port(), self._engine_path())
        envs = " ".join(f"{k}={v}" for k, v in KV_ENV.items())
        text = f"[env  {envs}]\n\n{exe}\n  " + "\n  ".join(argv)
        self.cmd_box.configure(state="normal")
        self.cmd_box.delete("1.0", "end")
        self.cmd_box.insert("1.0", text)
        self.cmd_box.configure(state="disabled")
        warns = validate(self.selection, self._engine_path())
        if warns:
            self.status.config(text="⚠ " + "\n⚠ ".join(warns), fg="#b07a20")
        else:
            self.status.config(text="✓ 配置合法，可启动", fg="#4a6b4a")

    def _port(self):
        try:
            return int(self.port_var.get().strip() or PORT_DEFAULT)
        except Exception:
            return PORT_DEFAULT

    # ---- 异步执行小工具（避免 GUI 卡死）----
    def _run_async(self, fn, on_done):
        q = queue.Queue()

        def worker():
            try:
                q.put(("ok", fn()))
            except Exception as e:
                q.put(("err", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                kind, val = q.get_nowait()
            except queue.Empty:
                self.root.after(300, poll)
                return
            on_done(kind, val)

        self.root.after(300, poll)

    def _show_lines(self, title, lines):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=self.bg)
        win.geometry("760x420")
        t = tk.Text(win, wrap="word", bg="white", fg="#1a1a1a", font=("Consolas", 9))
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert("1.0", lines)
        t.configure(state="disabled")

    def _env_check(self):
        self.status.config(text="环境自检中…", fg="#2b3a6b")
        self._run_async(env_check, lambda k, v: self._show_lines(
            "环境自检（S0 只读）", "\n".join(v) if k == "ok" else "探测失败: " + v))

    def _readiness(self):
        self.status.config(text="就绪自测中…（首次请求可能较慢）", fg="#2b3a6b")

        def done(kind, val):
            if kind != "ok":
                self.status.config(text="自测失败: " + val, fg="#b03030")
                return
            lines = []
            ok = True
            for name, code,摘要 in val:
                lines.append(f"[{code}] {name}\n    {摘要}\n")
                if code == "ERR":
                    ok = False
            self._show_lines("就绪自测（S2）", "\n".join(lines))
            self.status.config(text=("✓ 就绪自测完成" if ok else "⚠ 就绪自测有问题（见弹窗）"),
                               fg=("#4a6b4a" if ok else "#b03030"))

        self._run_async(lambda: readiness_test(self._port()), done)

    # ---- 启动 ----
    def _launch(self):
        warns = validate(self.selection, self._engine_path())
        hard = [w for w in warns if "未找到" in w or "非 ASCII" in w]
        if hard:
            messagebox.showerror("无法启动", "\n".join(hard))
            return
        exe, argv = build_command(self.selection, self._port(), self._engine_path())
        if not messagebox.askyesno("启动确认", f"确认启动 serve？\n\n{exe}\n\n端口: {self._port()}\n\n"
                                               f"（会在新控制台窗口运行；关窗 = 停服）"):
            return
        try:
            CREATE_NEW_CONSOLE = 0x00000010
            logfile = os.path.join(LOG_DIR, "serve_" + time.strftime("%Y%m%d_%H%M%S") + ".log")
            env = env_for_launch(exe)
            env["SERVE_TEE_MODE"] = "full" if self.logmode_var.get() == "全部" else "slim"
            subprocess.Popen([PYTHON_EXE, TEE_SCRIPT, logfile, exe] + argv,
                             env=env, cwd=ROOT,
                             creationflags=CREATE_NEW_CONSOLE)
            self.status.config(text="✓ 已启动（控制台窗口 + 日志落盘）—— 关窗即停；首次见 calibrating routes 请勿杀\n"
                                    "   日志：" + logfile, fg="#4a6b4a")
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    # ---- 命名组合 ----
    def _load_profile(self):
        """加载命名组合：把 profile 里的**内部值**反查为**显示名**写回下拉（照老项目 _load_profile）。
        旧格式值（spec: dflash2/mtp）经 LEGACY_VALUE_MAP 迁移。"""
        name = self.profile_cb.get()
        if not name or name not in self.profiles:
            self.status.config(text="未选择或找不到组合", fg="#b03030")
            return
        combo = self.profiles[name]
        valid_keys = {d[0] for d in DIMENSIONS}
        applied = 0
        for key, val in combo.items():
            if key not in valid_keys:
                continue
            val = LEGACY_VALUE_MAP.get((key, val), val)     # 旧值迁移
            opts = next(d[2] for d in DIMENSIONS if d[0] == key)
            if val not in opts:
                continue
            if key == "spec":
                self._apply_spec_to_ui(val)                 # 反设投机档两级下拉
            else:
                self.var[key].set(opts[val][0])             # 内部值 -> 显示名
            applied += 1
        self._on_change()
        miss = len(combo) - applied
        msg = f"已加载组合 '{name}'"
        if miss > 0:
            msg += f"（{miss} 项无法识别，已跳过）"
        self.status.config(text=msg, fg="#4a6b4a")

    def _save_profile(self):
        name = simpledialog.askstring("保存组合", "输入组合名称：")
        if not name:
            return
        self.profiles[name] = dict(self.selection)
        save_profiles(self.profiles)
        self.profile_cb["values"] = list(self.profiles.keys())
        self.profile_cb.set(name)
        self.status.config(text=f"已保存组合 '{name}'", fg="#4a6b4a")

    def _del_profile(self):
        name = self.profile_cb.get()
        if not name or name not in self.profiles:
            return
        del self.profiles[name]
        save_profiles(self.profiles)
        self.profile_cb["values"] = list(self.profiles.keys())
        self.profile_cb.set("")


def main():
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------
# TODO（后续版本补齐，对齐自建线 ninfer_launcher.py 的全部功能）：
#   · 场景预设（一键推荐组合）
#   · 更多维度：spec draft 1..15 二级联动、--thinking-budget、--prefill-cublas、
#     --lookup-ngram、--vision-residency、--kv-headroom-mib、--seed 等
#   · 日志落盘（serve_tee 等价物，写 logs\serve_<时间戳>.log）
#   · 端口可改、S3 KVMem 检索证据（kvmem_score: SELECT）采集
# ---------------------------------------------------------------
