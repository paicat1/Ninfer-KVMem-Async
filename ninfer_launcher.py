# -*- coding: utf-8 -*-
"""Ninfer-KVMem-Async 启动器（本线：异步页流水 + KVMem 环；模型 Qwen3.8-27B-Coder390）

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

==== 2026-10-18 真实性整改（用户令"全部整改/整理正确启动器"）====
背景：启动器展示层四类失信被用户逐层揭穿——① 引擎标签写死"现役(20261008)"与实际内容
      （10/15 S13 件，= lineage/I3b_step13 同 sha 322A972D）长期脱节；② registry 8 条中
      2 条（v2_27dc746 / V2+overlay64K）指向的 _safety_backups/exe_lineage_20261013/
      目录已不存在=死项；③ ENGINE_OPTIONS 死常量+注释谎言（"下拉只留 self"，实际下拉 registry
      8 条）且选不到时静默 fallback；④ 进程探测只认进程名（生产件/sym 实验件同名，下午
      15:47-16:17 sym 废件冒充生产件绿灯，用户被界面欺骗近 1 小时）。
整改（本版）：engine_display 每条附**文件实况**（mtime+大小；件不存在=显式⚠，不再静默）；
      进程探测明示"进程名分辨不了件"+权威源指向。
未做（挂账待后续）：sha 级实时指纹（1.27GB 全文件哈希开销大，mtime+size 为当前真实层）。
2026-10-19：死项一律**删除**不做置灰——ENGINE_PREV（目录不存在）与 ENGINE_OPTIONS（全文无引用）
      两个死项已删除；registry 现存 6 条经路径实测全部存活。
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
# ⚠ 2026-10-17 修（TELE 第十七轮 B1）：原指向 engine\self-built-20261008\ninfer-serve.exe，
#   该文件已在 T2 清理中被处置（与 lineage\G2 同 sha）⇒ **启动器曾会直接起服失败**。
#   现改为谱系末端件（MANIFEST 末端、与在役 sha 322A972D 同件）。
# 2026-10-17 恢复：本行原指向 engine\self-built-20261008\ninfer-serve.exe；该文件被误删后我先改成谱系件，
#   但**正确修法是恢复文件**（已用同 sha 的 lineage\G2_default_depth1.exe 逐字节拷回）⇒ 指针一并改回原路径，行为不变。
ENGINE_SELF = os.path.join(ROOT, "engine", "self-built-20261008", "ninfer-serve.exe")   # 自编·现役（已恢复）
# ENGINE_PREV（engine\self-built\ninfer-serve.exe）已于 2026-10-19 删除：该目录本线不存在，属死项；
# 按用户令死项一律删除、不做置灰。
# 2026-10-10 用户裁决后的收口：下拉只留【自编·现役】一项。原三项的两个问题：
#   · self_prev（engine\self-built\ninfer-serve.exe）—— **该目录本线不存在**，选中只会报"未找到引擎"（死项）；
#   · official（engine\ninfer-serve-120a.exe）—— 文件在，但 P0b 已裁定本线统一用 self-built：
#     它含 Design C（思考停止强制进 answer）而官方件没有 -> 行为路径不同，混用污染 A/B 对照；
#     且官方件是否支持 rk2v4-e8 / --spec mtp 从未验证（选了可能是第二个坑）。
#   ENGINE_PREV 与 ENGINE_OPTIONS 均为死项，2026-10-19 已删除；ENGINE 保留（供 ENGINE_DIR 取 engine\ 根）。
# 2026-10-18 注记：本常量定义后**全文无人引用**
# （实际下拉来源 = engine_registry，见 load_engine_registry/_registry_seed）——原注释
# "下拉只留自编现役一项"与实际（registry 4 条）不符，属失信描述，已在此勘误。
# 保留仅为历史锚，禁止再按它的注释做判断。
# ENGINE_OPTIONS 已于 2026-10-19 删除：定义后全文无人引用（实际下拉来源 = engine_registry），属死常量。

# ---------------------------------------------------------------
# 引擎登记册（2026-10-13 用户令）：重要版本引擎的"标注 + 选择 + 基线对比"。
#   用途：把有代表性的引擎版本（如"谷深但均速/极速好"、"无极速但稳"）登记下来，
#   下拉里直接选、直接起服对比；同类迭代收敛后可把旧的标为【已归档】（replaced_by=新条目）。
#   持久化：engine_registry.json（本文件同目录；缺失自动种子 + 落盘）。
# 字段：label=显示名 / path=exe 路径 / tags=短标注（列表）/ note=说明 /
#       status=基线|候选|已归档 / added=登记日 / replaced_by=被谁替代（归档时填）
# ---------------------------------------------------------------
ENGINE_REGISTRY_PATH = os.path.join(ROOT, "engine_registry.json")


def _registry_seed():
    # 2026-10-19 整理（用户令"整理启动器：引擎下拉/异步深度/场景与引擎关系"）：
    #  ① 现役三件置顶（S13 生产 / sym3 判决件 / offi 官方链+符号判决件），label 短化（下拉一眼可读），
    #     tags ≤4 个关键性质；note 精确但不再轰炸；
    #  ② 4 条 I3b 中间调试件 + H1 回滚锚 status→"已归档"（历史价值保留，退出常用视野）；
    #  ③ label/时间/大小等冗长实况不再拼进下拉（见 engine_display），选中件实况在状态行展示。
    _VARIANTS = os.path.join(ROOT, "engine", "variants")
    return [
        {"label": "S13 · 生产件（官方链 14.44 · 无符号）", "path": ENGINE_SELF,
         "tags": ["生产", "官方链", "Gen5+外压卡死"],
         "note": "现役生产件：2026-10-15 部署 = lineage\\I3b_step13（sha 322A972D，S12-internal v3）。"
                 "出生证明在案（archive\\temp-root-20261016\\build_engine.log：官方链 14.44 Community + 4 dirty 文件，10-15 23:47，BUILD-EXIT=0）。"
                 "Gen5+外压400 = decode 0 卡死（5/5 探针超时）；Gen5 零外压 = 184 健康。",
         "status": "现役", "added": "2026-10-15", "replaced_by": "", "preset": ""},
        {"label": "offi · 官方链 14.44 + 符号（20261019）",
         "path": os.path.join(_VARIANTS, "ninfer-serve-sym-official.exe"),
         "tags": ["判决件", "官方链", "符号", "384×sm_120a"],
         "note": "D 项攻关件：官方链 s6_1208a.bat 原样 + env /Zi + LINK=/DEBUG（独立目录 build-d1208a）。"
                 "sha 3543AD18…，exe 1.28GB，pdb 226.7MB。Gen5+外压400 = 44.5 谷但完成（卡死未复现）——"
                 "与 S13 唯一差=符号链接 ⇒ 卡死元凶=符号链接缺失（布局敏感假说的实证角）。",
         "status": "现役", "added": "2026-10-19", "replaced_by": "", "preset": ""},
        {"label": "sym3 · 新构建链 + 符号（20261018）",
         "path": os.path.join(_VARIANTS, "ninfer-serve-sym.exe"),
         "tags": ["判决件", "新链", "符号", "384×sm_120a"],
         "note": "2026-10-18 编（build_sym.ps1 同参重编 S13 源码 be2c0f9）。sha 9453FFC6…，exe 1.28GB。"
                 "Gen5+外压400 = 41 谷但完成；Gen4+400 = 165 基本健康。带符号件的另一独立角。",
         "status": "现役", "added": "2026-10-18", "replaced_by": "", "preset": ""},
        {"label": "H1_54fix（历史件 · 回滚锚）",
         "path": os.path.join(ROOT, "engine", "lineage", "H1_54fix_20261013.exe"),
         "tags": ["首轮极速好", "谷深", "超池500风险(~11%)"],
         "note": "首轮峰 463.9；R2/R3 深谷 0.2-7.2；超池升级 500 约 11%（已由 v2 修复）。仅回滚锚，日常不用。",
         "status": "已归档", "added": "2026-10-13", "replaced_by": "", "preset": ""},
        {"label": "I3b_step1_step_profile（档案）",
         "path": os.path.join(ROOT, "engine", "lineage", "I3b_step1_20261013.exe"),
         "tags": ["步级仪表", "档案"],
         "note": "I3b P2/P3 平台件（2026-10-13 夜）：decode 轮 wall 四分解（submit/wait/post/rest）。开：NINFER_STEP_PROFILE=1。",
         "status": "已归档", "added": "2026-10-13", "replaced_by": "I3b_step2_step_profile_s2", "preset": ""},
        {"label": "I3b_step2_step_profile_s2（档案）",
         "path": os.path.join(ROOT, "engine", "lineage", "I3b_step2_20261013.exe"),
         "tags": ["S2五分", "档案"],
         "note": "I3b S2 平台件（2026-10-13 深夜）：提交段五分 rows/pre/launch/sync/harvest；稳态 wall≈launch（27-32ms/轮）。",
         "status": "已归档", "added": "2026-10-13", "replaced_by": "I3b_step3b_s3b_ingraph", "preset": ""},
        {"label": "I3b_step3b_s3b_ingraph（档案）",
         "path": os.path.join(ROOT, "engine", "lineage", "I3b_step3b_20261014.exe"),
         "tags": ["图内事件", "档案"],
         "note": "I3b S3b 修复版（2026-10-14 凌晨）：MTP 图内事件四区间 + capture 节点计数（1107）。ingraph 区间暂未出数（待修）。",
         "status": "已归档", "added": "2026-10-14", "replaced_by": "", "preset": ""},
        {"label": "I3b_step4_debug_diag（档案）",
         "path": os.path.join(ROOT, "engine", "lineage", "I3b_step4_debug_20261014.exe"),
         "tags": ["诊断件", "档案"],
         "note": "I3b S4 调试件（2026-10-14 05:2x）：谷态实测（05:26 单轮 142.9s）即用它。仅调试用。",
         "status": "已归档", "added": "2026-10-14", "replaced_by": "", "preset": ""},
    ]


def load_engine_registry():
    try:
        with open(ENGINE_REGISTRY_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list) and data:
            return data
    except (OSError, ValueError):
        pass
    registry = _registry_seed()
    save_engine_registry(registry)
    return registry


def save_engine_registry(registry):
    try:
        with open(ENGINE_REGISTRY_PATH, "w", encoding="utf-8", newline="\n") as handle:   # 2026-10-13: 固定 LF（防跨写 EOL 抖动）
            json.dump(registry, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


def engine_display(entry):
    # 2026-10-19 整理（用户令"引擎说明太复杂"）：下拉只留【短 label + 状态/性质标签】；
    # 冗长的件实况（时间/大小/sha）不再拼进下拉文本，改由 _on_engine_select 在状态行展示。
    bits = list(entry.get("tags") or [])
    status = entry.get("status") or "候选"
    if status and status != "现役":
        bits.insert(0, status)
    suffix = ("｜" + "·".join(bits)) if bits else ""
    # 边界：mtime 在 GUI 生命周期内不变 ⇒ display 稳定、_engine_path 反查自洽；
    # 跨天换件后需重启 GUI 刷新（已知边界，留证）。
    path = entry.get("path") or ""
    if path and not os.path.exists(path):
        return entry.get("label", "?") + " ｜ ⚠件已不存在" + suffix
    return entry.get("label", "?") + suffix


def registry_default_display(registry):
    for entry in registry:
        if entry.get("status") == "基线":
            return engine_display(entry)
    return engine_display(registry[0])
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
#   iq4nl    : 自转 MTP 头（gguf_iq4_nl，239 MB）—— ★定稿；**无 vision 组件**
#   iq4nlvis : ★iq4_nl 骨架 + 官方视觉塔（graft_vision.py 嫁接，2026-10-10 晚）
#              = 唯一"小 MTP 头 + 有视觉"的组合件；视觉塔 282 MiB，
#              整体比官方 Q8MTP 版小 202.5 MiB（差额正是 MTP 头 q8_0 -> iq4_nl）；
#              L1 全量 SHA-256：骨架 804 + 视觉 335 对象零不匹配
#              **实测（2026-10-10，TeleAgent）：40K 池 + 视觉并存成功**（free 898.4 MiB）、
#              **真实识图成功**；20K 亦成功（free 963.4 MiB）。代价：图片压 256 merged tokens、
#              CPU 编码 TTFT ~15.7s；**40K+视觉需干净 GPU**（有占用程序时缺 ~1 GB 起不来）
#   q8mtp    : 官方 Q8MTP 版（MTP 头 q8_0 = 451 MB，比 iq4nl 多 212 MB）—— 含 vision 组件；
#              选它时 GUI 会自动把 --kv-capacity 降到 20480（否则 40K 池起不来，实测过）
#   orig     : 原件（MTP 头是引擎不支持的 gguf_q4_0 -> 只能裸解码，做纯基线）
#   注：这里的 argv 列表留空 —— 模型是引擎的**位置参数**（第一个），不走 --flag。
# ---------------------------------------------------------------
# ── 品牌三选一（2026-10-14 用户令）：Q2LYNN / SWIFT 1.5 / BONSAI ──
#   Q2LYNN = 现役（与 iq4nlvis 同文件 · Coder390 Q2Lynn 3.89bpw + 视觉塔）
#   SWIFT  = swift15_iq3s_mtp.ninfer（GSQ-RCO IQ3_S · 11.3 GiB 上卡 · 含视觉塔+MTP）
#            实测：载入 ~9s、方言 gguf_blocks_v1 可载；65,536@rk8v4 free 727.9 MiB、
#            65,536@nvfp4 free 1.09 GiB、57,344@int8 free 482.6 MiB（起服须 -Graph 192，64 会告警）
#   BONSAI = 前序线（Ternary-Bonsai-2-27B-ninfer-v3.ninfer）· 件未下载，仅登记待测试
MODEL_OPTIONS = {
    "q2lynn":   ("★Q2LYNN（现役 · Q2Lynn 3.89bpw + 视觉）", []),
    "swift":    ("SWIFT 1.5（IQ3_S GSQ-RCO · 11.3 GiB 上卡 · 含视觉）", []),
    "bonsai":   ("BONSAI（前序线 · 件未下载 · 待测试）", []),
    "iq4nl":    ("★iq4_nl 定稿（自转 MTP 头 · 无视觉）", []),
    "iq4nlvis": ("★iq4_nl + 视觉塔（嫁接件 · 含 vision 组件）", []),
    # q8mtp（官方含视觉）已移除（2026-10-11 用户裁决）：被 iq4nlvis 全面取代（MTP 头小 212 MB、
    # 可配大池、视觉实测成功）；文件已删（13.78 GB），需要时重新下载。
    "orig":     ("原件（纯基线 · MTP 不可用）", []),
}
MODEL_PATHS = {
    "iq4nl": os.path.join(ROOT, "models",
                          "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.ninfer"),
    "iq4nlvis": os.path.join(
        ROOT, "models",
        "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer"),
    "q2lynn": os.path.join(
        ROOT, "models",
        "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer"),
    "swift":  os.path.join(ROOT, "models", "swift15_iq3s_mtp.ninfer"),
    "bonsai": os.path.join(ROOT, "models", "Ternary-Bonsai-2-27B-ninfer-v3.ninfer"),
    "orig":  os.path.join(ROOT, "models",
                          "Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.ninfer"),
}
# --model-id 按档映射（2026-10-19 用户撞见 BUG：选 SWIFT1.5 但 model-id 仍是 coder390——
#   原 L765 硬编码 qwen3.8-27b-coder390，模型文件选对但标识没跟档走，误导性极强）：
#   swift = 日志实证名（"engine ready | swift-1.5-qwen3.8-27b-gsq-rco-iq3s"，2026-10-19 20:47）；
#   Coder390 系（q2lynn/iq4nl/iq4nlvis/orig）共用 coder390（同骨架同命名域，原值正确）；
#   bonsai = 件未下载的按文件名合理默认——起服后以 engine ready 行校正（预登记，勿当实证）。
MODEL_IDS = {
    "swift":    "swift-1.5-qwen3.8-27b-gsq-rco-iq3s",
    "q2lynn":   "qwen3.8-27b-coder390",
    "iq4nl":    "qwen3.8-27b-coder390",
    "iq4nlvis": "qwen3.8-27b-coder390",
    "orig":     "qwen3.8-27b-coder390",
    "bonsai":   "ternary-bonsai-2-27b-ninfer-v3",
}
# 含 vision 组件的模型档 —— validate() 用它做「模型 ↔ 视觉」配对校验。
# （q8mtp 已随模型文件移除，2026-10-11：iq4nlvis 全面取代。）
VISION_CAPABLE_MODELS = frozenset(("iq4nlvis", "q2lynn", "swift"))  # swift 件含视觉塔（2026-10-14 实测 overlay 可起）
# 模型 -> 池上限的强制联动表（_apply_model_coupling 用）。q8mtp 移除后暂空；将来按实测加。
MODEL_KVCAP_MAX = {}
# ── 每模型一套参数（2026-10-14 用户令）：换模型 → 自动切整套（KV/池/Graph/视觉）──
#   方法与判据（守望者/逐字门/bisect/gpu_probe/窗口 SOP）跨模型通用，一套定稿；
#   参数与基准每模型一套：Q2LYNN 集=冻结（baselines/q2lynn），SWIFT 集=现行（baselines/swift15_iq3s）。
MODEL_BUNDLES = {
    "q2lynn": {"kv": "rk2v4-e8", "kvcap": "51200", "graph": "64",  "vision": "overlay",
               "note": "现役定稿（冻结基准）；实测池上限 65,536（free ~490 MiB）/ rk8v4 ≤ 41,664"},
    "swift":  {"kv": "rk8v4",    "kvcap": "64k",    "graph": "192", "vision": "overlay",
               "note": "实测 65,536@rk8v4 free 727.9 MiB；Graph 必须 192（64 会告警）；int8 档池取 57,344–61,440"},
    "bonsai": {"kv": "rk2v4-e8", "kvcap": "51200", "graph": "64",  "vision": "overlay",
               "note": "前序线 · 件未下载（仅登记待测试）"},
}
CONFIG_FILE = os.path.join(ROOT, "ninfer_launcher_profiles.json")
LOG_DIR = os.path.join(ROOT, "logs")
TEE_SCRIPT = os.path.join(ROOT, "serve_tee.py")
PORT_DEFAULT = 8094
# tee 需要“带控制台”的 python.exe（GUI 以 pythonw 运行，用它起 tee 会得空白窗口）
PYTHON_EXE = sys.executable.replace("pythonw.exe", "python.exe").replace("pythonw", "python")

# 池 token 数（= config 里的 --kv-capacity）。硬约束 = 单请求的【prompt_tokens + 输出(max_tokens) ≤ 池】：
# 超过则 (a) 未开止血 → worker 崩且不自愈；或 (b) 开了 --kv-lease-growth（旧 E5 止血）→ 被静默截断(finish_reason=length、
# 内容像正常但只有半截)。--default-max-tokens 只是服务端默认上限，不是硬约束。
# ⚠️ 2026-10-10 夜测定案（构建史 §三·十五，双环境收敛）：growth 在深超池构型下不止截"超池部分"——
#    租约窗口(~4,096)无法扩充时输出被砍在 ~4,037-4,071（bounded completion），与 max_tokens/tb 无关
#    ⇒ DSH 撞墙直接根因，已从 "on" 定稿档移除（官方 README:218：超池要保住输出 → 不要开 growth）。
# P1b (2026-10-09) 定稿值 = 40960；★2026-10-11 00:11 池上限标定（growth OFF）：65,536 缺 378 MiB、
#   57,344 差 17.3 MiB（临界）、55,296（864 页）当晚成功（free 534.4 MiB），
#   55K + 视觉（iq4nlvis + --vision-cpu）同样成功（free 490.4 MiB）。
# ★ 用户裁决（2026-10-11）：定稿 = **51200（800 页）**——55,296 为贴边上限，次日桌面负载 +25 MiB
#   即拒启（缺 23.6 MiB，`55k_underload_failed.log`），不可复现；51200 对其释放 55.6 MiB，日常稳定。
#   池扩容极便宜（rk2v4-e8 下 ≈0.83 MB/页）。起服必须带 KV_ENV 六开关（缺 NINFER_KV_WINDOW 直接拒启）。
#   ⚠️ 池 < 逻辑上下文（--max-context 262144）是**设计如此**：池外的页由 KVMem 环下沉到 host
#   （--host-kv-mib 16384）；实测 20,203 tokens prompt 检索答案正确（ring retrieve restored=128）。
KV_POOL_TOKENS = 51200

# KVMem 六开关：缺一 = 起得来但静默答错（缓存命中率高、中段答错、零报错）。GUI 内固定注入。
# ⚠️ NINFER_KV_WINDOW 同时是"允许 --kv-capacity < --max-context"的开关（serve_options.cpp:1124-1132）：
#    不设它，引擎强制要求 kv-capacity ≥ max-context 并拒绝启动（--kv-capacity must be at least --max-context）。
# ★ NINFER_KV_SINK（2026-10-11 官方 D-01 对标，docs/13）：attention-sink 骨架页（demotion 唯一不碰的区域，
#    context.cpp:1946/2033）。引擎默认 4 页=256 token ⇒ 老页毫无保护，多轮 replay 逐轮挤出早期上下文
#    （页漂移，122K 会话 hidden 931 页）。官方实测 sink 0→10240 把"深层埋针取回" 221.66s => 1.4s；
#    官方 agent 表面实测需求 2,808 token=44 页（context.cpp:2466 注释）。取 5120（80 页，RC2 同款默认）。
KV_ENV = {
    "NINFER_KV_WINDOW":          "32768",
    "NINFER_KV_SINK":            "5120",
    "NINFER_KV_RETRIEVE":        "8192",
    "NINFER_KV_RING":            "1",
    "NINFER_HOST_PAGEABLE":      "1",
    "NINFER_KV_REUSE_HOSTBACKED": "1",
}

# 异步页流水主开关（2026-10-17 用户要求：AB 测试直接入口）。
#   NINFER_ASYNC_DEMOTE = 1 异步（引擎默认，本线核心改进）；= 0 同步批回退（OFF 对照臂）。
#   实测依据（同 exe 单变量对照）：docs\实验-超池异步ONOFF对照-20261016（r=OFF/ON=1.13，单发打平）；
#   docs\实验-深轮重载ONOFF对照-20261016（r=0.801<0.85，深载净收益成立；最深段 ≈2×、ring STALL 33→2）。
#   ⚠️ 这是"环境变量"维度（不是 argv）：GUI 选 OFF 注入 NINFER_ASYNC_DEMOTE=0，选 ON 显式写 1（自证无歧义）。
ASYNC_OPTIONS = {
    "on":  ("异步页流水：开（默认 · 本线核心改进）", {"NINFER_ASYNC_DEMOTE": "1"}),
    "off": ("异步页流水：关（同步回退 · A/B 对照臂）", {"NINFER_ASYNC_DEMOTE": "0"}),
}

# 异步页流水深度（2026-10-19 用户令增加：A/B 开关之外，可选"几批在飞"）：
#   NINFER_ASYNC_DEMOTE_DEPTH = 同时 in-flight 的 demote 批数（搬运与计算的重叠深度）。
#   依据：docs\工程史挂账46 v2.1（深度=2 实测 10+ 轮零降速）；2026-10-19 浅载三档对照
#   （D2 avg 187.1 > D0 183.6 > D1 182.6：2 批在飞最优、1 批反而最差、深载收益待测）。
#   ⚠ 深载分档（1/3/4 批）尚未实测——调度要保守保守再保守，默认 2。
ASYNC_DEPTH_OPTIONS = {
    "1": ("1 批在飞（浅载实测最差档 · 谨慎选）", {"NINFER_ASYNC_DEMOTE_DEPTH": "1"}),
    "2": ("2 批在飞 · 默认（净收益成立）", {"NINFER_ASYNC_DEMOTE_DEPTH": "2"}),
    "3": ("3 批在飞（深载未实测 · 保守）", {"NINFER_ASYNC_DEMOTE_DEPTH": "3"}),
    "4": ("4 批在飞（深载未实测 · 保守）", {"NINFER_ASYNC_DEMOTE_DEPTH": "4"}),
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
    "51200": ("51200 ★定稿·50K稳定", ["--kv-capacity", "51200"]),
    "55296": ("55296 贴边·需净GPU", ["--kv-capacity", "55296"]),
    "49152": ("49152 · 48K", ["--kv-capacity", "49152"]),
    "40960": ("40960 · 40K旧档", ["--kv-capacity", "40960"]),
    "20480": ("20480 · 20K省显存", ["--kv-capacity", "20480"]),
    "17920": ("17920 · 官方默认", ["--kv-capacity", "17920"]),
    "auto":  ("auto · 按剩余显存", ["--kv-capacity", "auto"]),
    "16k":     ("16K",  ["--kv-capacity", "16384"]),
    "32k":     ("32K",  ["--kv-capacity", "32768"]),
    "64k":     ("64K ★20261011实测·需净GPU（配 graph128）", ["--kv-capacity", "65536"]),
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
# 视觉：含 vision 组件的模型 = 【iq4nlvis 嫁接件】与【官方 Q8MTP 版】（前者 2026-10-10 晚新增）。
#   .mtp-iq4nl.ninfer 与原件**没有** vision 组件 -> 对它们传任何 --vision* 都会启动即挂：
#   "Qwen3.5 config: missing component vision"（2026-10-10 实测，日志 serve_20261010_025432）。
#   => validate() 会对「模型不含视觉 + 开了视觉」直接告警，这是防该坑的关键。
# 实测（构建史 §三·十，2026-10-10）：官方版 + --vision-cpu 起服成功，
# weights 12.3→12.5 GiB、runtime 1.44 GiB、free 663.4 MiB，**设备视觉显存占用为零**；
# 代价：图片被压到 256 merged tokens（约 512x512）、CPU 编码慢（one to a few seconds）。
# iq4nlvis + 视觉：★2026-10-11 实测 55,296 池 + --vision-cpu 成功（free 490.4 MiB；DSH 识图 26.9s 正常）。
#   挂账 39 已销案（2026-10-11 凌晨 CodeBuddy 实测）：视觉 + hemostat=on 起服且功能正常
#   （scatter 断言在现役引擎 3b9dc83 不存在），视觉无需再强制 growth（growth 已判死）。
VISION_OPTIONS = {
    "on":      ("开·GPU 编码器（视觉塔常驻显存 ~1.4G；需含视觉模型）", ["--vision"]),
    # ★2026-10-13 本线定稿（用户令）：5 图 10 请求零错；稳态不占设备显存（塔住 host pinned 282 MiB）；
    # 打图窗口期设备借用实测峰值 +44 MiB（150ms 采样，短窗可能低估）；首图 prepared 0.3-0.7s、同图复用 40-60ms、
    # 首图 TTFT 1.3-6.3s / 复用轮 0.4-1.0s。对照：cpu=每图编码 15.7-26.9s 且图压 256 token；resident=16G 装不下（差 303MB）。
    "overlay": ("开·主机内存 overlay（★定稿：稳态 0 占用 / 打图窗借+44MiB / 首图 0.3-0.7s）", ["--vision", "--vision-residency", "overlay"]),
    "cpu":     ("开·CPU 编码器（★不占设备视觉显存；需含视觉模型）", ["--vision-cpu"]),
    "off":     ("关（★本线定稿 · 纯文本配置）",   []),
}
SAMPLE_OPTIONS = {
    "shipped":  ("官方(0.7/0.9/20, presence0)（★本线定稿）", ["--presence-penalty", "0", "--temperature", "0.7", "--top-p", "0.9", "--top-k", "20"]),
    "thinking": ("思考档(1.0/0.95/20)",          ["--presence-penalty", "0", "--temperature", "1.0", "--top-p", "0.95", "--top-k", "20"]),
    "greedy":   ("贪心(greedy)",                 ["--greedy"]),
}
# KV 止血档（2026-10-10 定案改三档，构建史 §三·十五）：growth 在深超池下把输出砍在 ~4,096 租约窗口
# （bounded completion）⇒ DSH 撞墙直接根因，已从定稿移除；"legacy" 仅留作 A/B 对照臂。
# CUDA Graph 预算档（2026-10-11，构建史 §三·十八 §1）：
#   机制 = 把"一步 decode 的全部 kernel 序列"录制成图重放，省逐 kernel 启动开销；
#   预算 = 驱动侧图状态显存。档位越大驻留图越多，runtime 预留越大。
#   实测（5080）：128 = 64K 池起服过线且 decode 101.1（基线 101-104，batch=1 零代价）——★定稿；
#   64/32 = 桌面挤时递降（32 = 视觉+64K+桌面 1.4GiB 极限档，2026-10-11 12:18 实测）；
#   off = --no-cuda-graph 完全禁用（省全部 graph 预算，decode 有损，最后手段）。
GRAPH_OPTIONS = {
    "192":  ("192 MiB（★SWIFT 档硬要求 · 2026-10-14 实测：64 会告警 CUDA graphs used 236.8 > 64.0）", ["--cuda-graph-allowance-mib", "192"]),
    "128":  ("128 MiB（★定稿·64K池实测零代价）", ["--cuda-graph-allowance-mib", "128"]),
    "64":   ("64 MiB（紧凑）",                   ["--cuda-graph-allowance-mib", "64"]),
    "32":   ("32 MiB（极限·桌面挤时）",           ["--cuda-graph-allowance-mib", "32"]),
    "off":  ("off（禁用·最后手段，decode 有损）", ["--no-cuda-graph"]),
    "auto": ("auto（按 profile 自动·大池时或拒启）", []),
}
HEMOSTAT_OPTIONS = {
    "on":     ("开（★定稿 20261010 · 仅防崩，去 growth）", ["--recover-invariant-failures"]),
    "legacy": ("旧E5止血(含growth·已判死:超池撞墙)",      ["--kv-lease-growth", "--recover-invariant-failures"]),
    "off":    ("关（官方 bat 原样）",                       []),
}
# 思考预算档：--default-thinking-budget N —— 治“思考墙死循环”（xhigh 思考烧光输出预算 → 空正文）。
# 这是服务端(argv)级设置；20261008 引擎 S3 起 OpenAI chat 端点**已解析**请求里的 thinking_budget 字段
# （openai_chat_request.cpp:955-982，≥1024、0/null=不设），且请求值优先于服务端默认（translate.cpp:426-428）
# —— 旧注释“OpenAI 不解析”已过时（2026-10-10 审核发现，构建史 §三·十四）。
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

REQLOG_OPTIONS = {
    # 2026-10-13 夜（TELE 复核缺口 #3 闭环）：Stage 0 请求/区间日志仪器。
    #   on = 写 .temp\reqlog_serve_<端口>.jsonl（逐窗 host_work / rounds / tok 分解；配套 scripts\stage0_read.py 读数）；
    #   文件名由 build_command 按端口动态生成（区分多实例）；纯观测，无性能影响。
    "off": ("关（默认）", []),
    "on":  ("开·写 .temp\\reqlog_serve_<端口>.jsonl（Stage 0 仪器）", []),
}

DIMENSIONS = [
    ("model",  "模型",            MODEL_OPTIONS),   # 2026-10-10: 模型是第一选择（iq4nlvis 含视觉组件，2026-10-11 实测）
    ("spec",   "档位 / 投机解码", SPEC_OPTIONS),
    ("asyncdepth", "异步深度(批)", ASYNC_DEPTH_OPTIONS),   # 2026-10-19 用户令：A/B 之外可选在飞批数（默认 2）
    ("kv",     "KV 类型",         KV_OPTIONS),
    ("ctx",    "上下文",          CTX_OPTIONS),
    ("kvcap",  "KV 容量",         KVCAP_OPTIONS),
    ("graph",  "CUDA Graph 预算", GRAPH_OPTIONS),
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
    ("reqlog", "请求日志（Stage 0 仪器）", REQLOG_OPTIONS),   # 2026-10-13 夜新增
]
DIMENSIONS_MAP = {key: table for key, _label, table in DIMENSIONS}  # 联动用（2026-10-14）

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
    #                      20261008 引擎 S3 起 OpenAI 端点已解析请求里的 thinking_budget（请求值优先于服务端默认）。
    "model": "iq4nl",
    "spec": "k4", "kv": "rk2v4-e8", "ctx": "256k", "kvcap": "51200", "hostkv": "16384",
    "prefill": "512", "think": "high", "tb": "16000", "maxout": "32768", "vision": "off",
    "sample": "shipped", "conc": "1", "preserve": "off", "hemostat": "on",
    "graph": "128", "reqlog": "off", "async": "on", "asyncdepth": "2",
}

# v1 旧档位值 -> 新档位值 迁移表：旧 profile 的 spec 存的是 "dflash2"/"mtp"，
# 新档位内部值已改为 "d12"/"k4" 等；加载时自动迁移，避免旧命名组合失效。
LEGACY_VALUE_MAP = {
    ("spec", "dflash2"): "d12",
    ("spec", "mtp"):     "k4",
}

DIM_TIPS = {
    "async": "异步页流水 A/B 开关（NINFER_ASYNC_DEMOTE）。**开**=默认（搬运与计算重叠，本线核心改进）；**关**=同步批回退（OFF 对照臂）。实测：单发超池打平（r=1.13）、深轮重载净收益成立（r=0.801，最深段≈2×）。改档需重启 serve；做 A/B 时只切这一项、其余不动。",
    "asyncdepth": "异步页流水深度（NINFER_ASYNC_DEMOTE_DEPTH）= 同时 in-flight 的 demote 批数，配合上面的 A/B 开关使用（开关关=同步回退，此时深度无效）。浅载三档实测（2026-10-19）：2 批 avg 187.1 > 同步 183.6 > 1 批 182.6——2 批最优、1 批半流水反而最差；**深载分档（3/4 批）尚未实测**，保守默认 2。",
    "spec":   "投机解码（只加速解码）。k0=无；k1..k5=MTP；d1..d15=DFlash2（K 越大猜得越多，d12=官方首起档）。改档需重启 serve。",
    "kv":     "KV 缓存精度。★本线定稿 rk2v4-e8（2bit key + 4bit value，最省；5080 实测可用，输出与 k8v4 语义一致）。官方默认 k8v4；异常时换一档试。",
    "ctx":    "上下文长度（--max-context，**逻辑上限**）。★定稿 256K = 262144（模型原生上限）。注意：池外的页由 KVMem 环下沉到 host，实测 20K prompt 检索仍正确且不慢。",
    "kvcap":  "KV 池容量（--kv-capacity）= 显存里能直接读的 KV token 数（即\"全速区间\"）。★定稿 51200（2026-10-11 用户裁决：55,296 为贴边上限——当晚可起、次日桌面负载 +25 MiB 即拒启，不可复现；稳定档 51200/49152）。扩容极便宜（rk2v4-e8 下 ≈0.83 MB/页）。auto = 按剩余显存最大化。",
    "graph":  "CUDA Graph 预算（--cuda-graph-allowance-mib）= decode kernel 图重放的驱动侧显存。★定稿 128（64K 池起服必要条件，decode 101.1 实测零代价）。桌面挤时降 64/32；off 完全禁用（decode 有损，最后手段）。",
    "hostkv": "Host 侧 KV 预算（MiB，--host-kv-mib）。官方默认 16384。",
    "prefill":"文本 prefill 分块（--prefill-chunk，128 的倍数）。官方默认 1024。",
    "think":  "思考模式。官方默认 none（关思考）。启用思考后注意 §4.2 的“思考完空正文”已知问题。",
    "tb":     "思考预算上限（--default-thinking-budget，每回合最多思考 token）。治“思考墙死循环”：xhigh 思考烧光输出预算→空正文。越小越省时，审核/批量建议小；长逻辑建议大。20261008 引擎 S3 起 OpenAI 端点已解析请求里的 thinking_budget（请求值优先于服务端默认）。",
    "maxout": "服务端默认输出上限（--default-max-tokens）。⚠ 定稿池 = 40960 tokens；单请求【prompt_tokens + 输出】留在池内可避免 host 往返；开了 --kv-lease-growth 时超池会被静默截断(finish_reason=length)。⚠ growth 已判死（深超池下输出被砍在 ~4,096 租约窗口 = DSH 撞墙根因，20261010 定案），hemostat 定稿档已移除之。",
    "vision": "视觉（多模态）。GPU 编码器=默认，视觉塔常驻显存(~1.4G)；overlay=视觉塔驻 pinned 主机内存、仍走 GPU 算（折中，需可驱逐尾部支撑）；cpu=视觉塔走 CPU 线程、无设备视觉显存（引擎自动把 --vision-max-merged 压到 256，每图慢）。显存紧：优先 overlay，其次 cpu；不用视觉就关。",
    "sample": "采样预设。默认 = 官方值 0.7/0.9/20、presence 0。",
    "conc":   "并发请求数（--max-concurrency）。多请求吞吐用大值；单会话保持 1（确定性）。",
    "preserve":"保留已关闭回合的 assistant 推理（--preserve-thinking）。多轮长对话要前序思考时开。",
    "hemostat":"KV 止血档（20261010 定案改三档）：on=★定稿，仅 --recover-invariant-failures（出问题只废当前请求、不弄死引擎）；legacy=旧 E5（--kv-lease-growth——深超池下把输出砍在 ~4,096 租约窗口 ⇒ DSH 撞墙直接根因，仅留作 A/B 对照臂）；off=全关（官方 bat 原样）。",
    "reqlog": "请求日志仪器（--request-log-jsonl 三旗，Stage 0）：开 = 逐窗落 .temp\\reqlog_serve_<端口>.jsonl"
              "（host_work / rounds / tok 分解，配套 scripts\\stage0_read.py 读数）。默认关；纯观测。",
}

# 命名组合预置（首次运行若无配置文件则落盘）
PRESET_PROFILES = {
    # ============================================================
    # 只有 4 个预设：**2 种模式 × 2 个模型**。其余参数请在下方维度区自行设置。
    #
    # 【生产模式】= 本卡实测定稿档：精度 × 池 × 上下文 三者的最优组合（不是"精度越高越好"）。
    #   ⚠ 关键取舍：KV 精度每升一档，每 token 显存就变贵 ⇒ 同样的 16 GB 能放的池就变小
    #     ⇒ 长上下文更多走 host 往返 ⇒ 反而更慢。所以"生产"取的是**实测最快的组合**，
    #     不是精度最高的组合（要更高精度：KV 类型那一档自己往上选，代价见显存账）。
    # 【压力模式】= 抓"死亡谷"用：把池压到 20K（逻辑上下文 256K ⇒ 12.8× 超池），
    #     强制大量 host 往返（谷的栖息地），并**打开 reqlog 仪器**以便事后取证。
    #     代价：吞吐明显低于生产档（这是故意的——要的是"能进谷"，不是"跑得快"）。
    #     ⚠ 压力模式不改异步臂（A/B 开关独立）：要对照就自己切"异步页流水(A/B)"那一档。
    # ============================================================
    "① 生产 · Q2LYNN（定稿 51200 池 · 最快）": dict(
        DEFAULTS, model="q2lynn", kv="rk2v4-e8", kvcap="51200", graph="64",
        vision="overlay", spec="k4", think="high", tb="16000", hemostat="on",
        reqlog="off", **{"async": "on"}
    ),
    "② 生产 · SWIFT（定稿 64K 池 · rk8v4）": dict(
        DEFAULTS, model="swift", kv="rk8v4", kvcap="64k", graph="192",
        vision="overlay", spec="k4", think="high", tb="16000", hemostat="on",
        reqlog="off", **{"async": "on"}
    ),
    "③ 压力 · Q2LYNN（20K 小池 · 强制 host 往返 · 抓深谷）": dict(
        DEFAULTS, model="q2lynn", kv="rk2v4-e8", kvcap="20480", graph="64",
        vision="overlay", ctx="256k", spec="k4", think="high", tb="16000",
        hemostat="on", reqlog="on", **{"async": "on"}
    ),
    "④ 压力 · SWIFT（20K 小池 · 强制 host 往返 · 抓深谷）": dict(
        DEFAULTS, model="swift", kv="rk8v4", kvcap="20480", graph="192",
        vision="overlay", ctx="256k", spec="k4", think="high", tb="16000",
        hemostat="on", reqlog="on", **{"async": "on"}
    ),
    # 2026-10-17 简化（用户令）：原先 13 个预设（大池64K/视觉×4/思考档/对照k0/贴边55296…）
    #   外部读者分不清用途 ⇒ 全部撤下。它们的**参数与实测记录仍在**：构建史（§4.4、三·十六、
    #   §三·十九）+ git 历史；需要用哪个配置，在下方维度区照抄即可。
}

# ---------------------------------------------------------------
# 预设专属环境变量（2026-10-12）：只对同名预设追加，其余预设零影响。
#   KV_ENV 六开关对所有预设生效；这里是"某个档额外要的"两项：
#     NINFER_ASYNC_DEMOTE_DEPTH=2 = 挂账 46 v2.1 多批 in-flight 深度（实测 10+ 轮零降速）；
#     NINFER_DEMOTE_PROFILE=1     = demote 批级 profile 日志（纯诊断，不需要可删这一行）。
PRESET_ENV = {
    # 生产档：v2.1 多批 in-flight 深度（挂账 46，实测 10+ 轮零降速）
    "① 生产 · Q2LYNN（定稿 51200 池 · 最快）":        {"NINFER_ASYNC_DEMOTE_DEPTH": "2"},
    "② 生产 · SWIFT（定稿 64K 池 · rk8v4）":         {"NINFER_ASYNC_DEMOTE_DEPTH": "2"},
    # 压力档：再加 demote 批级 profile 日志（纯诊断，抓谷后做差分归因用）
    "③ 压力 · Q2LYNN（20K 小池 · 强制 host 往返 · 抓深谷）": {
        "NINFER_ASYNC_DEMOTE_DEPTH": "2", "NINFER_DEMOTE_PROFILE": "1"},
    "④ 压力 · SWIFT（20K 小池 · 强制 host 往返 · 抓深谷）": {
        "NINFER_ASYNC_DEMOTE_DEPTH": "2", "NINFER_DEMOTE_PROFILE": "1"},
    # 2026-10-19 注：DEPTH 已是 GUI 独立维度（"异步深度(批)"，默认 2）。经 env_for_launch 时 combo
    # 后于本表注入 ⇒ GUI 选择覆盖上表；本表仅在"不经 GUI 的 preset 直载路径"上兜底为 2。
}


# ---------------------------------------------------------------
# 校验 / 命令构造
# ---------------------------------------------------------------
def _exe_guard(exe):
    """B1 护栏：起服件不存在时必须显式告警（原缺陷：指向已清理文件却无声失败）。"""
    if exe and not os.path.exists(exe):
        return "⚠ 起服件不存在：%s —— 请检查 ENGINE_SELF / 登记册路径（勿指向已清理的 self-built-20261008）" % exe
    return None


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
    if combo.get("model") == "bonsai" and not os.path.exists(_mp):
        warns.append("BONSAI 件未下载（前序线模型 Ternary-Bonsai-2-27B-ninfer-v3.ninfer 不在 models\\）——"
                     "已登记待测试，暂不可起服；测试前请先取得该件。Q2LYNN / SWIFT 1.5 两档可直接用。")
    elif not os.path.exists(_mp):
        warns.append(f"未找到模型：{_mp}")
    if combo.get("model") == "orig" and str(combo.get("spec", "k0")) != "k0":
        warns.append("原件（-MTP.ninfer）的 MTP 头是引擎不支持的 gguf_q4_0 -> 只能裸解码（档位选 k0）。")
    # ---- 2026-10-10 实测踩坑（日志 serve_20261010_025432）：模型与视觉必须配对 ----
    # 模型不含 vision 组件却传 --vision* -> 引擎启动即挂
    #   "Qwen3.5 config: missing component vision"（79 us 就失败，即"秒退"）。
    # 这是防该坑的关键告警：此前 GUI 没有 iq4nlvis 档，用户只能选无视觉模型 + 手动开视觉。
    _model = combo.get("model", "iq4nl")
    _vis = str(combo.get("vision", "off"))
    if _vis != "off" and _model not in VISION_CAPABLE_MODELS:
        warns.append(f"模型【{_model}】不含 vision 组件，但你开了视觉（{_vis}）-> 引擎启动即挂："
                     f"Qwen3.5 config: missing component vision。"
                     f"要识图请选【iq4nlvis】（iq4_nl 骨架 + 视觉塔）或【q8mtp】（官方版）。")
    if _vis == "off" and _model in VISION_CAPABLE_MODELS:
        warns.append(f"模型【{_model}】带视觉塔但视觉档是关 -> 塔不会被加载（也不占显存）。"
                     f"要识图请开视觉档（推荐 cpu：不占设备视觉显存）。")
    _kv = str(combo.get("kvcap", "51200"))
    try:
        if int(str(combo.get("conc", "1"))) > 1:
            warns.append("★架构约束：KVMem 环（NINFER_KV_WINDOW）只支持 --max-concurrency 1"
                         "（环无法回收另一 lane 的设备页，并发>1 启动即拒，2026-10-11 实测）。"
                         "要多并发必须放弃 KVMem 环（unset NINFER_KV_WINDOW => 池必须 ≥ 逻辑上下文，"
                         "本卡不可行）——并发与 256K 深度/检索互斥，保持 1。")
    except ValueError:
        pass
    if _kv.isdigit() and int(_kv) >= 55296:
        warns.append("★贴边池（≥55,296）：需桌面空闲到引擎可约 ~1.95 GiB（关浏览器/Overlay 等 ~1 GB 占用），"
                     "否则启动即缺 ~24 MiB 拒启（2026-10-11 实测两次：55,296 当晚成功、次日 +25 MiB 负载即败）。"
                     "日常请用 51200/49152。")
    if _model == "iq4nlvis" and _kv.isdigit() and int(_kv) > 55296:
        warns.append("iq4nlvis 的**实测上限是 55,296 池 + 视觉**（2026-10-11 实测成功，free 490.4 MiB）；"
                     "更高未验证（57,344 起服即失败：差 17.3 MiB）。需干净 GPU。")
    # 挂账 39 已销案（2026-10-11 凌晨 CodeBuddy 实测）：视觉 + on 起服且功能正常，告警移除。
    # growth 已判死（超池撞墙根因），视觉不再需要 legacy 联动。
    if any(ord(c) > 127 for c in ROOT):
        warns.append("项目路径含非 ASCII 字符——引擎会以 invalid UTF-8 byte 启动即挂")
    return warns


# ---------------------------------------------------------------
# 显存需求账（2026-10-12 用户要求：选什么选项，就自动加出显存需求总量）
#   口径经本机 20+ 次起服日志标定（《精算-显存账与KV池》§0/§1），非拍脑袋：
#     need = 权重 + 视觉塔(仅 vision=on) + KV池 + 运行时 + CUDA graph   ← “加载前需求”
#     页 = 64 token；每页 MiB：rk2v4-e8 0.83 / rk4v4-e8·nvfp4 1.11 /
#                              k8v4·rk8v4 1.59 / int8·fp8 2.11 / bf16 4.08
#   实测吻合：64K 池 rk2v4-e8 + graph128 → 需求 14.92 GiB，本卡 15.92 GiB
#   ⇒ 起服前须有 ≈1.0 GiB 空闲（与“64K 池需净 GPU、桌面 ≤~1.0 GiB”实测一致）。
# ---------------------------------------------------------------
VRAM_PAGE_MIB = {
    "rk2v4-e8": 0.83, "rk4v4-e8": 1.11, "nvfp4": 1.11,
    "k8v4": 1.59, "rk8v4": 1.59, "int8": 2.11, "fp8": 2.11, "bf16": 4.08,
}
VRAM_TOKENS_PER_PAGE = 64
VRAM_WEIGHTS_GIB = {"iq4nl": 12.30, "iq4nlvis": 12.30, "orig": 12.40}
VRAM_RUNTIME_GIB = 1.66          # 运行时/工作区（实测 runtime 行 1.44~1.66，取上界）
VRAM_VISION_GPU_GIB = 1.40       # vision=on 视觉塔常驻设备；overlay/cpu 走主机/CPU = 0

_VRAM_GPU_CACHE = {"t": 0.0, "val": (None, None, False)}


def _gpu_used_mib(max_age=5.0):
    """nvidia-smi 实测 (已用 MiB, 总 MiB, 是否有引擎在跑)；5 秒缓存（_refresh 每次选择都调）。"""
    now = time.time()
    cached = _VRAM_GPU_CACHE["val"]
    if cached[0] is not None and now - _VRAM_GPU_CACHE["t"] < max_age:
        return cached
    used = total = None
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        a, b = r.stdout.strip().splitlines()[0].split(",")
        used, total = int(a.strip()), int(b.strip())
    except Exception:
        pass
    running = False
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ninfer-serve*", "/NH"],
                           capture_output=True, text=True, timeout=10)
        running = "ninfer-serve" in r.stdout
    except Exception:
        pass
    _VRAM_GPU_CACHE.update({"t": now, "val": (used, total, running)})
    return used, total, running


def vram_account(combo):
    """按当前选择实时算显存账。返回 (文本, 判定色)；颜色：绿=OK，橙=紧张/不够/未知。"""
    model = str(combo.get("model", "iq4nl"))
    dtype = str(combo.get("kv", "rk2v4-e8"))
    page = VRAM_PAGE_MIB.get(dtype, 0.83)
    cap = str(combo.get("kvcap", "51200"))
    # 池值必须经 KVCAP_OPTIONS 取真实 token 数：档位键有 "64k"/"32k" 这类写法，本身不是数字
    # （真实值在 argv 里 = ["--kv-capacity", "65536"]）。2026-10-12 实测抓到该 bug。
    _cap_argv = _argv_of(KVCAP_OPTIONS, cap, "51200")
    cap_num = _cap_argv[1] if len(_cap_argv) >= 2 and _cap_argv[1].isdigit() else None
    weights = VRAM_WEIGHTS_GIB.get(model, 12.30)
    vis_gib = VRAM_VISION_GPU_GIB if str(combo.get("vision", "off")) == "on" else 0.0
    g = str(combo.get("graph", "128"))
    graph_gib = 0.0 if g == "off" else (int(g) if g.isdigit() else 64) / 1024.0
    if cap_num is not None:
        pages = int(cap_num) / float(VRAM_TOKENS_PER_PAGE)
        pool_gib = pages * page / 1024.0
        pool_txt = "池 %s tok %.2f" % (cap_num, pool_gib)
    else:
        pool_gib = 0.0
        pool_txt = "池 auto（按剩余显存最大化，无法预算）"
    need = weights + vis_gib + pool_gib + VRAM_RUNTIME_GIB + graph_gib
    parts = "权重 %.2f" % weights
    if vis_gib:
        parts += " + 视觉塔 %.2f" % vis_gib
    parts += " + %s + 运行时 %.2f + graph %.2f" % (pool_txt, VRAM_RUNTIME_GIB, graph_gib)
    used, total, running = _gpu_used_mib()
    if used is None:
        return ("显存：需求 ≈ %.2f GiB ＝ %s ｜（nvidia-smi 不可用，余量未知）" % (need, parts), "#b07a20")
    free = (total - used) / 1024.0
    margin = free - need
    verdict = "OK" if margin > 0.35 else ("紧张" if margin > 0.05 else "不够")
    color = "#4a6b4a" if verdict == "OK" else "#b07a20"
    tail = "｜⚠ 有引擎在跑，可用量含其占用（判余量请先停服）" if running else ""
    return ("显存：需求 ≈ %.2f GiB ＝ %s ｜ 可用 %.2f（已用 %d/%d MiB）→ 余量 %+.2f 【%s】%s"
            % (need, parts, free, used, total, margin, verdict, tail), color)


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
    model_id = MODEL_IDS.get(combo.get("model", "iq4nl"), "qwen3.8-27b-coder390")   # 2026-10-19 BUG 修复：按档映射
    argv = [model_path, "--host", "127.0.0.1", "--port", str(port), "--model-id", model_id]
    argv += _argv_of(CTX_OPTIONS,     combo.get("ctx", "256k"),      "256k")
    argv += _argv_of(KVCAP_OPTIONS,   combo.get("kvcap", "51200"),   "51200")  # 2026-10-11: 回退对齐 DEFAULTS（原 "55296"）
    argv += _argv_of(GRAPH_OPTIONS,   combo.get("graph", "128"),     "128")    # 2026-10-11: CUDA Graph 预算档（64K 池必要条件；定稿 128）
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
    if combo.get("reqlog", "off") == "on":   # 2026-10-13 夜：Stage 0 仪器（文件名按端口）
        argv += ["--request-log-jsonl", os.path.join(".temp", "reqlog_serve_%s.jsonl" % port),
                 "--request-log-max-mib", "256", "--request-log-keep", "2"]
    argv += ["--max-shared-prefixes", "0"]   # 铁律：防打砖
    argv += _argv_of(SAMPLE_OPTIONS,  combo.get("sample", "shipped"), "shipped")
    argv += _argv_of(HEMOSTAT_OPTIONS, combo.get("hemostat", "on"),  "on")   # B01 止血（E5 决定：默认开）
    return exe, argv


def env_for_launch(exe=None, profile=None, combo=None):
    """profile = 预设名（可选）：把 PRESET_ENV 里该档专属的环境变量一并合入（2026-10-12）。
    combo = 当前 GUI 组合（可选，2026-10-17）：把"环境变量类维度"（异步页流水 A/B 开关）合入；
    未传时行为与以前完全一致（向后兼容）。"""
    env = dict(os.environ)
    env.update(KV_ENV)
    if profile:
        env.update(PRESET_ENV.get(profile, {}))
    if combo:
        env.update(ASYNC_OPTIONS.get(combo.get("async", "on"), ASYNC_OPTIONS["on"])[1])
        # 2026-10-19：异步深度（几批在飞）独立注入；combo 后于 PRESET_ENV ⇒ 覆盖预设写死的 DEPTH，
        # 以 GUI 用户显式选择为准。开关关（同步回退）时深度由引擎视为无效（不删，保留选择态）。
        if combo.get("async", "on") != "off":
            env.update(ASYNC_DEPTH_OPTIONS.get(combo.get("asyncdepth", "2"), ASYNC_DEPTH_OPTIONS["2"])[1])
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
        # 2026-10-18 整改（整改 #0064）：进程名同形冒充事故（下午 sym 废件绿灯冒充生产件）
        # ⇒ 明示"进程名分辨不了件"，权威源=起服日志/CB 当轮报备，不替用户脑补成"生产件在跑"。
        lines.append("  ⚠ 进程名无法分辨具体装载件（生产件/sym 实验件同名）；"
                     "实际件以起服日志（logs\\test_*.log 首行 VARIANT/命令行）或 CodeBuddy 当轮报备为准")
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
        self.root.title("Ninfer-KVMem-Async · 启动器")   # 2026-10-17: 正式库名（原为 Coder390 · NInfer 启动器）
        self.root.geometry("1180x820")
        self.root.minsize(1020, 740)
        self.bg, self.fg = "#f4f8ff", "#1a3a6b"
        self.root.configure(bg=self.bg)

        self.profiles = load_profiles()
        self.selection = dict(DEFAULTS)
        # ★默认档 = SWIFT（2026-10-14 用户令）；Q2LYNN 集冻结为参照，用场景预设一键回切。
        try:
            _b = MODEL_BUNDLES.get("swift") or {}
            for _k in ("kv", "kvcap", "graph", "vision"):
                if _k in _b and _k in DIMENSIONS_MAP and _b[_k] in DIMENSIONS_MAP[_k]:
                    self.selection[_k] = _b[_k]
            if "swift" in MODEL_OPTIONS:
                self.selection["model"] = "swift"
            self._bundle_model = "swift"
        except Exception as _exc:
            print("[bundle] 默认档套用失败（回退 DEFAULTS）：" + str(_exc))
        self.var = {}
        self._label2key = {}
        self.port_var = tk.StringVar(value=str(PORT_DEFAULT))
        self.logmode_var = tk.StringVar(value="精简")
        # P0b (2026-10-09): 默认引擎 = 「自编·现役」；2026-10-13 起默认取登记册里 status=基线 的条目。
        #   理由：self-built 含 Design C（thinking stop 强制进 answer），官方件无 -> 行为路径不同，
        #   混用会污染对照；且 self-built 是本线现役（交接文档指定、两个 start-coder390*.bat 已用）。
        self.engine_registry = load_engine_registry()
        self.engine_var = tk.StringVar(value=registry_default_display(self.engine_registry))
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

        # ---- 头部（正式库名）----
        tk.Label(main, text="Ninfer-KVMem-Async · 启动器", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=self.bg, fg="#1b4d8a").pack(anchor="w")
        tk.Label(main, text="Ninfer-KVMem-Async · Qwen3.8-27B · MTP + KVMem 环 · 异步页流水 · RTX 5080 sm_120",
                 font=("Microsoft YaHei UI", 9), bg=self.bg, fg="#5a6b8a").pack(anchor="w", pady=(0, 8))

        # ---- 工具栏：端口 / 日志 / 引擎 ----
        bar = tk.Frame(main, bg=self.bg)
        bar.pack(fill="x", pady=(0, 10))
        tk.Label(bar, text="端口", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.port_entry = ttk.Entry(bar, textvariable=self.port_var, width=8, font=("Microsoft YaHei UI", 9))
        self.port_entry.pack(side="left", padx=(4, 14))
        ToolTip(self.port_entry, "引擎服务端口（官方默认 8094）。")
        tk.Label(bar, text="日志", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.logmode_cb = ttk.Combobox(bar, state="readonly", width=6, textvariable=self.logmode_var,
                                       values=["精简", "全部"], font=("Microsoft YaHei UI", 9))
        self.logmode_cb.pack(side="left", padx=(4, 14))
        ToolTip(self.logmode_cb, "窗口日志显示：精简=只留每段 SELECT 首末条 + 业务行；全部=不过滤（查错用）。日志文件两种模式都全文落盘。")
        tk.Label(bar, text="引擎", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.engine_cb = ttk.Combobox(bar, state="readonly", width=46, textvariable=self.engine_var,
                                      values=[engine_display(e) for e in self.engine_registry],
                                      font=("Microsoft YaHei UI", 9))
        self.engine_cb.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self.engine_cb.bind("<<ComboboxSelected>>", self._on_engine_select)
        ToolTip(self.engine_cb, "引擎二进制（登记册驱动）。带 preset 的条目：选中即自动套用（参数 + env 一键复现）。")

        # ---- 主体：左参数 / 右预览 ----
        body = tk.Frame(main, bg=self.bg)
        body.pack(fill="both", expand=True)

        left_outer = tk.Frame(body, bg=self.bg, width=560)
        left_outer.pack(side="left", fill="y", padx=(0, 14))
        left_outer.pack_propagate(False)
        canvas = tk.Canvas(left_outer, bg=self.bg, highlightthickness=0, width=540)
        scroll = ttk.Scrollbar(left_outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.bg)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # 维度表（async/asyncdepth 不在 DIMENSIONS…实已在：asyncdepth 2026-10-19 已入 DIMENSIONS；async 仍特殊）
        DIM_LABEL = {k: l for k, l, _t in DIMENSIONS}
        DIM_LABEL["async"] = "异步页流水(A/B)"
        DIM_TABLE = {k: t for k, _l, t in DIMENSIONS}
        DIM_TABLE["async"] = ASYNC_OPTIONS

        # 控件统一宽度 = 最长选项名 + 2（保证下拉收起时也看得全）
        _all = []
        for _t in DIM_TABLE.values():
            _all += [lbl for (lbl, _a) in _t.values()]
        CBW = min(52, max(30, max(len(x) for x in _all) + 2))

        def section(title, tip=""):
            f = ttk.LabelFrame(inner, text=title)
            f.pack(fill="x", pady=(0, 8), padx=2)
            if tip:
                ToolTip(f, tip)
            return f

        def row(parent, key):
            """标签在左（固定宽度）、下拉在右（统一宽度）——不会截断。"""
            table = DIM_TABLE[key]
            self._label2key[key] = {lbl: val for val, (lbl, _a) in table.items()}
            self.var[key] = tk.StringVar(value=table[self.selection.get(key, DEFAULTS[key])][0])
            fr = tk.Frame(parent, bg=self.bg)
            fr.pack(fill="x", padx=8, pady=3)
            tk.Label(fr, text=DIM_LABEL[key], bg=self.bg, fg="#2b3a6b", width=16, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(side="left")
            cb = ttk.Combobox(fr, state="readonly", width=CBW, textvariable=self.var[key],
                              font=("Microsoft YaHei UI", 9))
            cb["values"] = list(self._label2key[key].keys())
            cb.bind("<<ComboboxSelected>>", lambda _e: self._on_change())
            cb.pack(side="left", padx=(6, 0))
            if DIM_TIPS.get(key):
                ToolTip(cb, DIM_TIPS[key])
            return cb

        # ★ 全窗最醒目：异步页流水（本线拳头产品）A/B 开关 + 在飞深度
        star = ttk.LabelFrame(inner, text="★ 异步页流水（本线拳头产品 · A/B 开关 + 在飞深度）")
        star.pack(fill="x", pady=(0, 10), padx=2)
        row(star, "async")
        row(star, "asyncdepth")
        tk.Label(star, text="开=异步（搬运与计算重叠，默认）；关=同步批回退（OFF 对照臂）。"
                            "深度=同时 in-flight 的 demote 批数（关时无效）。"
                            "实测：单发超池 r=1.13（打平）、深轮重载 r=0.801（净收益成立，最深段≈2×）；"
                            "浅载三档 2批 187.1 > 同步 183.6 > 1批 182.6；深载分档（3/4 批）未实测，保守默认 2。"
                            "改档需重启 serve；A/B 只切这两项。",
                 bg=self.bg, fg="#8a6b3a", font=("Microsoft YaHei UI", 8),
                 wraplength=500, justify="left").pack(anchor="w", padx=8, pady=(0, 6))

        # 场景预设
        pf = section("场景预设（只 4 个：2 模式 × 2 模型）",
                     "**场景预设 = 参数档**（模型/池/KV精度/压力模式等运行参数），与顶部工具栏的**引擎下拉相互独立**——"
                     "引擎决定\"跑哪个二进制\"，场景决定\"用什么参数跑\"；两个下拉任意组合（例：offi 引擎 + ④压力场景 = 新件跑压力参数）。\n"
                     "【生产】= 本卡实测定稿档（精度×池×上下文 的最优组合，**不是**精度最高）；"
                     "【压力】= 把池压到 20K（逻辑 256K ⇒ 12.8× 超池）强制大量 host 往返，并开 reqlog 仪器；"
                     "代价是吞吐明显低于生产档。两种模式都不改异步臂（A/B 开关+深度在顶部独立切）。"
                     "其余参数请在下方维度区自行设置。")
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(pf, state="readonly", textvariable=self.preset_var,
                                      width=CBW, values=list(PRESET_PROFILES.keys()),
                                      font=("Microsoft YaHei UI", 9))
        self.preset_cb.bind("<<ComboboxSelected>>", self._apply_preset)
        self.preset_cb.pack(anchor="w", padx=8, pady=6)

        # 分区：模型与推理规格
        f1 = section("模型与推理规格")
        for k in ("model", "spec", "think", "tb", "maxout", "sample", "preserve", "conc"):
            if k == "spec":
                fr = tk.Frame(f1, bg=self.bg); fr.pack(fill="x", padx=8, pady=3)
                tk.Label(fr, text=DIM_LABEL["spec"], bg=self.bg, fg="#2b3a6b", width=16, anchor="w",
                         font=("Microsoft YaHei UI", 9)).pack(side="left")
                self._label2key["spec"] = {lbl: val for val, (lbl, _a) in SPEC_OPTIONS.items()}
                self.var["spec"] = tk.StringVar(value=SPEC_OPTIONS[self.selection.get("spec", DEFAULTS["spec"])][0])
                self.combo_spec_type = ttk.Combobox(fr, state="readonly", width=10,
                                                    textvariable=self.var_spec_type, font=("Microsoft YaHei UI", 9))
                self.combo_spec_type["values"] = ["无", "MTP", "DFlash2"]
                self.combo_spec_type.bind("<<ComboboxSelected>>", self._on_spec_change)
                self.combo_spec_type.pack(side="left", padx=(6, 4))
                self.combo_spec_k = ttk.Combobox(fr, state="readonly", width=6,
                                                 textvariable=self.var_spec_k, font=("Microsoft YaHei UI", 9))
                self.combo_spec_k.bind("<<ComboboxSelected>>", self._on_spec_change)
                self.combo_spec_k.pack(side="left")
                ToolTip(self.combo_spec_type, DIM_TIPS.get("spec", ""))
                self._update_spec_k_range()
            else:
                row(f1, k)

        # 分区：KV 与显存
        f2 = section("KV 与显存")
        for k in ("kv", "ctx", "kvcap", "hostkv", "graph", "vision"):
            row(f2, k)

        # 分区：仪器与稳定性
        f3 = section("仪器与稳定性")
        for k in ("reqlog", "hemostat", "prefill"):
            row(f3, k)

        # ---- 右侧：预览 + 状态 + 操作 ----
        right = tk.Frame(body, bg=self.bg)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="启动命令预览", bg=self.bg, fg="#9b8c5a",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(0, 2))
        self.cmd_box = tk.Text(right, height=14, width=64, wrap="word", bg="white", fg="#1a1a1a",
                               bd=1, relief="solid", font=("Consolas", 9))
        self.cmd_box.pack(fill="both", expand=True)
        self.cmd_box.configure(state="disabled")

        self.vram = tk.Label(right, text="", bg=self.bg, fg="#2b3a6b",
                             font=("Microsoft YaHei UI", 9, "bold"),
                             justify="left", anchor="w", wraplength=430)
        self.vram.pack(anchor="w", pady=(8, 0))

        self.status = tk.Label(right, text="", bg=self.bg, fg="#4a6b4a",
                               font=("Microsoft YaHei UI", 9), justify="left", anchor="w", wraplength=430)
        self.status.pack(anchor="w", pady=(6, 0))

        btns = tk.Frame(right, bg=self.bg)
        btns.pack(fill="x", pady=(10, 4))
        ttk.Button(btns, text="启 动", command=self._launch, width=14).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="环境自检", command=self._env_check, width=12).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="就绪自测", command=self._readiness, width=12).pack(side="left")

        combox = tk.Frame(right, bg=self.bg)
        combox.pack(fill="x", pady=(8, 2))
        tk.Label(combox, text="命名组合:", bg=self.bg, fg="#2b3a6b",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.profile_cb = ttk.Combobox(combox, state="readonly", width=22, values=list(self.profiles.keys()),
                                       font=("Microsoft YaHei UI", 9))
        self.profile_cb.pack(side="left", padx=(6, 0))
        ttk.Button(combox, text="加载", command=self._load_profile, width=8).pack(side="left", padx=6)
        ttk.Button(combox, text="保存当前", command=self._save_profile, width=10).pack(side="left", padx=4)
        ttk.Button(combox, text="删除", command=self._del_profile, width=8).pack(side="left", padx=4)

        tk.Label(right, text="提示：启动后引擎在“新控制台窗口”里运行 —— 关掉那个窗口 = 停服。",
                 bg=self.bg, fg="#8a6b3a", font=("Microsoft YaHei UI", 9), wraplength=430,
                 justify="left").pack(anchor="w", pady=(8, 0))

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
        """模型/维度联动（表驱动 + 视觉联动）。

        a) 池上限联动（2026-10-10 用户要求）：模型在 MODEL_KVCAP_MAX 表中时，
           池超过上限自动降（同步下拉显示）。表暂空（q8mtp 已移除），机制保留。
        b) 视觉联动（2026-10-11 用户实测闪退后加入）：开视觉（vision != off）但模型
           容器无 vision 组件（iq4nl / orig）时，自动切到 iq4nlvis（同系嫁接件）——
           否则引擎 "Qwen3.5 config: missing component vision" 启动即拒（闪退循环，
           logs/serve_20261011_0318*.log 四连）。validate 的同名告警保留（防 profile 手改）。
        """
        vis = str(self.selection.get("vision", "off"))
        if vis != "off":
            if self.selection.get("model", "iq4nl") not in VISION_CAPABLE_MODELS:
                self.selection["model"] = "iq4nlvis"
                if "model" in self.var and "iq4nlvis" in MODEL_OPTIONS:
                    self.var["model"].set(MODEL_OPTIONS["iq4nlvis"][0])   # 同步下拉显示
        # 挂账 39 已销案（2026-10-11 凌晨）：视觉 + on（无 growth）实测正常，不再强制 legacy
        # （growth 已判死，任何路径不再默认带 --kv-lease-growth）。
        # c) 每模型一套参数（2026-10-14 用户令）：模型变化时一次性套用整套，
        #    之后用户手改单项不被反复覆盖（只在"模型变化"这一拍应用）。
        _model_now = self.selection.get("model", "iq4nl")
        _bundle = MODEL_BUNDLES.get(_model_now)
        if _bundle and getattr(self, "_bundle_model", None) != _model_now:
            self._bundle_model = _model_now
            for _key in ("kv", "kvcap", "graph", "vision"):
                _val = _bundle.get(_key)
                _table = DIMENSIONS_MAP.get(_key)
                if not _val or not _table or _val not in _table:
                    continue
                self.selection[_key] = _val
                if _key in self.var:
                    self.var[_key].set(_table[_val][0])   # 同步下拉显示
            print("[bundle] " + _model_now + " -> " + str(_bundle))
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
        valid_keys = {d[0] for d in DIMENSIONS} | {"async"}   # async 不在 DIMENSIONS（顶部星窗），但预设/组合也要能切 A/B 臂
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
        want = self.engine_var.get()
        for entry in self.engine_registry:
            if engine_display(entry) == want:
                return entry.get("path") or ENGINE_SELF
        return ENGINE_SELF      # 2026-10-10: 回退改为自编现役（原为官方件，与"统一 self-built"的裁决矛盾）

    def _current_engine_entry(self):
        want = self.engine_var.get()
        for entry in self.engine_registry:
            if engine_display(entry) == want:
                return entry
        return self.engine_registry[0] if self.engine_registry else None

    def _env_profile_name(self):
        """env 配对名（2026-10-13 夜修）：预设优先，退回命名组合名。"""
        return self.preset_var.get() or self.profile_cb.get() or ""

    def _on_engine_select(self, _e=None):
        """2026-10-13 夜（用户令）：引擎条目带 preset 字段 = 选中即自动套用（参数 + env 一键复现）。
        2026-10-19 整理：状态行展示选中件的实况（时间/大小），下拉只留短标签。"""
        entry = self._current_engine_entry() or {}
        preset_name = entry.get("preset") or ""
        if preset_name and preset_name in PRESET_PROFILES:
            self.preset_var.set(preset_name)
            self._apply_preset()
            self.status.config(text=f"已随引擎条目套用预设「{preset_name}」（参数 + env 一键复现）", fg="#4a6b4a")
        _fact = ""
        _path = entry.get("path") or ""
        if _path and os.path.exists(_path):
            try:
                _st = os.stat(_path)
                _fact = " ｜ 件实况 {0} {1:.2f}GB".format(
                    time.strftime("%m-%d %H:%M", time.localtime(_st.st_mtime)), _st.st_size / (1024 ** 3))
            except OSError:
                _fact = " ｜ 件状态未知"
        elif _path:
            _fact = " ｜ ⚠件已不存在"
        self.status.config(text=("引擎：" + entry.get("label", "?") + "（" + (entry.get("status") or "候选") + "）"
                                 + (_fact if _fact else " ｜ 路径未填")), fg="#2b3a6b")
        self._refresh()

    def _reload_engine_values(self, select_label=None):
        self.engine_cb["values"] = [engine_display(e) for e in self.engine_registry]
        if select_label is not None:
            self.engine_var.set(select_label)
        self._refresh()

    def _edit_engine_entry(self):
        entry = self._current_engine_entry()
        if entry is None:
            return
        top = tk.Toplevel(self)
        top.title("引擎标注 — " + entry.get("label", ""))
        top.configure(bg=self.bg)
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="显示名", bg=self.bg, fg="#2b3a6b").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        label_var = tk.StringVar(value=entry.get("label", ""))
        ttk.Entry(top, textvariable=label_var, width=52).grid(row=0, column=1, padx=8, pady=4)
        tk.Label(top, text="路径", bg=self.bg, fg="#2b3a6b").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        path_var = tk.StringVar(value=entry.get("path", ""))
        ttk.Entry(top, textvariable=path_var, width=52).grid(row=1, column=1, padx=8, pady=4)
        tk.Label(top, text="标注（/ 分隔）", bg=self.bg, fg="#2b3a6b").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        tags_var = tk.StringVar(value="/".join(entry.get("tags") or []))
        ttk.Entry(top, textvariable=tags_var, width=52).grid(row=2, column=1, padx=8, pady=4)
        tk.Label(top, text="说明", bg=self.bg, fg="#2b3a6b").grid(row=3, column=0, sticky="nw", padx=8, pady=4)
        note_box = tk.Text(top, width=52, height=5, wrap="word")
        note_box.insert("1.0", entry.get("note", ""))
        note_box.grid(row=3, column=1, padx=8, pady=4)
        tk.Label(top, text="状态", bg=self.bg, fg="#2b3a6b").grid(row=4, column=0, sticky="w", padx=8, pady=4)
        status_var = tk.StringVar(value=entry.get("status", "候选"))
        ttk.Combobox(top, state="readonly", textvariable=status_var,
                     values=["基线", "候选", "已归档"], width=12).grid(row=4, column=1, sticky="w", padx=8, pady=4)
        tk.Label(top, text="被谁替代（归档时填）", bg=self.bg, fg="#2b3a6b").grid(row=5, column=0, sticky="w", padx=8, pady=4)
        repl_var = tk.StringVar(value=entry.get("replaced_by", ""))
        ttk.Entry(top, textvariable=repl_var, width=52).grid(row=5, column=1, padx=8, pady=4)

        def _save():
            entry["label"] = label_var.get().strip() or entry.get("label", "?")
            entry["path"] = path_var.get().strip() or entry.get("path", "")
            raw = tags_var.get().replace("、", "/").replace("，", "/").replace(",", "/")
            entry["tags"] = [t.strip() for t in raw.split("/") if t.strip()]
            entry["note"] = note_box.get("1.0", "end").strip()
            entry["status"] = status_var.get()
            entry["replaced_by"] = repl_var.get().strip()
            entry["preset"] = preset_var_d.get().strip()
            save_engine_registry(self.engine_registry)
            top.destroy()
            self._reload_engine_values(select_label=engine_display(entry))
            self.status.config(text="已保存引擎标注：" + engine_display(entry), fg="#4a6b4a")

        tk.Label(top, text="配套预设", bg=self.bg, fg="#2b3a6b").grid(row=6, column=0, sticky="w", padx=8, pady=4)
        preset_var_d = tk.StringVar(value=entry.get("preset", ""))
        ttk.Combobox(top, state="readonly", textvariable=preset_var_d, width=50,
                     values=[""] + list(PRESET_PROFILES.keys())).grid(row=6, column=1, padx=8, pady=4)
        btns = tk.Frame(top, bg=self.bg)
        btns.grid(row=7, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="保存", width=10, command=_save).pack(side="left", padx=6)
        ttk.Button(btns, text="取消", width=10, command=top.destroy).pack(side="left", padx=6)

    def _add_engine_entry(self):
        name = simpledialog.askstring("登记引擎", "显示名（如 H2_xxx_日期）：", parent=self)
        if not name:
            return
        path = simpledialog.askstring("登记引擎", "exe 路径：",
                                      initialvalue=self._engine_path(), parent=self)
        if not path:
            return
        entry = {"label": name.strip(), "path": path.strip(), "tags": [], "note": "",
                 "status": "候选", "added": time.strftime("%Y-%m-%d"), "replaced_by": "", "preset": ""}
        self.engine_registry.append(entry)
        save_engine_registry(self.engine_registry)
        self._reload_engine_values(select_label=engine_display(entry))
        self.status.config(text="已登记引擎条目：" + name, fg="#4a6b4a")

    def _refresh(self):
        self.selection = {k: self.selection.get(k, DEFAULTS[k]) for k in DEFAULTS}
        exe, argv = build_command(self.selection, self._port(), self._engine_path())
        envs = " ".join(f"{k}={v}" for k, v in KV_ENV.items())
        _async_env = ASYNC_OPTIONS.get(self.selection.get("async", "on"), ASYNC_OPTIONS["on"])[1]
        if _async_env:
            envs += " " + " ".join(f"{k}={v}" for k, v in _async_env.items())
        text = f"[env  {envs}]\n\n{exe}\n  " + "\n  ".join(argv)
        self.cmd_box.configure(state="normal")
        self.cmd_box.delete("1.0", "end")
        self.cmd_box.insert("1.0", text)
        self.cmd_box.configure(state="disabled")
        # 显存账：每次选择变更即重算（vram_account 自带 nvidia-smi 5 秒缓存，不会拖慢 GUI）
        try:
            vtxt, vcolor = vram_account(self.selection)
        except Exception as _e:          # 账算失败也绝不让 GUI 崩（老项目 D8 精神）
            vtxt, vcolor = "显存：计算失败（%s）" % _e, "#b07a20"
        self.vram.config(text=vtxt, fg=vcolor)
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
            env_profile = self._env_profile_name()   # 2026-10-13 夜修：预设优先（原传命名组合 -> PRESET_ENV 永不命中）
            env = env_for_launch(exe, env_profile, self.selection)
            env["SERVE_TEE_MODE"] = "full" if self.logmode_var.get() == "全部" else "slim"
            subprocess.Popen([PYTHON_EXE, TEE_SCRIPT, logfile, exe] + argv,
                             env=env, cwd=ROOT,
                             creationflags=CREATE_NEW_CONSOLE)
            applied_env = len(PRESET_ENV.get(env_profile, {}) or {})
            env_note = ("　[env 配对：%s（%d 项）]" % (env_profile, applied_env)) if applied_env else ""
            _arm = ASYNC_OPTIONS.get(self.selection.get("async", "on"), ASYNC_OPTIONS["on"])[0]
            self.status.config(text="✓ 已启动（控制台窗口 + 日志落盘）—— 关窗即停；首次见 calibrating routes 请勿杀\n"
                             "[A/B 臂: " + _arm + "]\n"
                                    "   日志：" + logfile + env_note, fg="#4a6b4a")
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
        valid_keys = {d[0] for d in DIMENSIONS} | {"async"}   # async 不在 DIMENSIONS（顶部星窗），但预设/组合也要能切 A/B 臂
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
#   · （2026-10-13 夜已补）stage0a reqlog 三旗已进启动器（reqlog 维度）；--max-shared-prefixes 0 早已内置（防打砖），勿误列。
#   · 端口可改、S3 KVMem 检索证据（kvmem_score: SELECT）采集
# ---------------------------------------------------------------
