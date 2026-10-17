# -*- coding: utf-8 -*-
"""一次性补丁：ninfer_launcher.py 加 stage0a 基线预设 + 配对 env + TODO 补旗（2026-10-13 夜）。"""
import ast
import io

P = r'J:\ninfer-kvmem\ninfer_launcher.py'
s = io.open(P, encoding='utf-8').read()
orig = s

# 1) 新预设
anchor = '    "★视觉 overlay 定稿（2026-10-13·5图零错）": dict(DEFAULTS, model="iq4nlvis", vision="overlay", kvcap="64k", graph="off"),'
assert s.count(anchor) == 1, 'anchor1=%d' % s.count(anchor)
add = anchor + '''
    # 2026-10-13 夜 用户令：stage0a 实况轮（102 轮 / 0×500 / 超池 10 次零故障 / 真谷 0）整档固定为基线。
    #   = stage0a 起服逐字：64K 池 + iq4nlvis(overlay) + --cuda-graph-allowance-mib 64 + MTP K4
    #     + 思考 high/16000 + 官方采样 + hemostat on；reqlog 仪器旗（--request-log-jsonl …）启动器暂不支持，需另加。
    #   实测：decode median 152.7 / 峰 406.2；TTFT max 57.2s（前档 464.9s）；真谷（host 饱和型）= 0。
    "★64K overlay stage0a 基线（10-13 实测）": dict(DEFAULTS, model="iq4nlvis", vision="overlay", kvcap="64k", graph="64"),'''
s = s.replace(anchor, add, 1)

# 2) PRESET_ENV 配对
anchor2 = '''PRESET_ENV = {
    "★64K视觉稳（v2.1实测·nograph）": {
        "NINFER_ASYNC_DEMOTE_DEPTH": "2",
        "NINFER_DEMOTE_PROFILE": "1",
    },
}'''
assert s.count(anchor2) == 1, 'anchor2=%d' % s.count(anchor2)
new2 = '''PRESET_ENV = {
    "★64K视觉稳（v2.1实测·nograph）": {
        "NINFER_ASYNC_DEMOTE_DEPTH": "2",
        "NINFER_DEMOTE_PROFILE": "1",
    },
    # stage0a（10-13）：PROFILE=1 已实证（该轮日志有 "demote profile" 行）；DEPTH=2 随 v2.1 定稿配对（stage0a 未单独取证）。
    "★64K overlay stage0a 基线（10-13 实测）": {
        "NINFER_ASYNC_DEMOTE_DEPTH": "2",
        "NINFER_DEMOTE_PROFILE": "1",
    },
}'''
s = s.replace(anchor2, new2, 1)

# 3) TODO 补旗
anchor3 = '#   · 日志落盘（serve_tee 等价物，写 logs\\serve_<时间戳>.log）'
assert s.count(anchor3) == 1, 'anchor3=%d' % s.count(anchor3)
add3 = anchor3 + '\n#   · stage0a 实测旗：--request-log-jsonl / --request-log-max-mib / --request-log-keep（reqlog 仪器）、--max-shared-prefixes 0'
s = s.replace(anchor3, add3, 1)

ast.parse(s)
io.open(P, 'w', encoding='utf-8', newline='').write(s)
print('OK: 3 patches applied, AST valid, bytes %d -> %d' % (len(orig), len(s)))
