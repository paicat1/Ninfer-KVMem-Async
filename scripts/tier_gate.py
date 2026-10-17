# -*- coding: utf-8 -*-
r"""tier_gate.py -- 档位门 + 审批留痕（T-ANTIHACK §四）

作用：读本地 SDA 档位（.codebuddy/sda/MODE.json）——
  tier >= 1（逐项批准）⇒ **提交信息必须含 `APPROVED: <用户原话>`（≥6 字）**，否则拒绝提交；
  通过则把"审批声明"追加到 APPROVAL_LOG.jsonl（供用户审计"我是否真拿到了那句话"）。

设计原则（不重犯今日之错）：
  · **不静默退宽松默认**：MODE.json 缺失 ⇒ **大声提示**（并注明按 tier 0 放行，原因写明）
  · **只读本地状态**：不依赖网络、不改任何文件（除追加审批日志）
用法（钩子调用）：python -X utf8 scripts/tier_gate.py <commit-msg-file>
退出码：0 放行；1 拒绝
"""
import io
import json
import os
import re
import sys
import time

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDA = os.path.join(R, '.codebuddy', 'sda')
MODE = os.path.join(SDA, 'MODE.json')
LOG = os.path.join(SDA, 'APPROVAL_LOG.jsonl')


def main():
    msgfile = sys.argv[1] if len(sys.argv) > 1 else ''
    msg = ''
    if msgfile and os.path.exists(msgfile):
        try:
            msg = io.open(msgfile, encoding='utf-8', errors='replace').read()
        except Exception:
            msg = ''
    tier = None
    if os.path.exists(MODE):
        try:
            tier = int(json.load(io.open(MODE, encoding='utf-8')).get('tier', 0))
        except Exception as e:
            print('BLOCKED[tier]: MODE.json 读取失败 ⇒ 按失败处理（不静默放行）：%s' % e)
            return 1
    else:
        # 明确提示 + 说明放行原因（不静默）
        print('NOTICE[tier]: 未找到 .codebuddy/sda/MODE.json（本地纪律档位）⇒ 本机无 SDA 状态，按 tier 0 放行。')
        print('              （本门只对装过 SDA 的机器生效；这是本地自律机制，非仓级策略）')
        return 0
    if tier < 1:
        return 0
    m = re.search(r'APPROVED:\s*(\S.{5,})', msg)
    if not m:
        print('BLOCKED[tier]: 当前档位 tier=%d（逐项批准）⇒ 提交信息必须含 `APPROVED: <用户原话>`（≥6 字）' % tier)
        print('  原因：T-ANTIHACK §四 档位门 —— "逐项批准"必须机械执行，不靠记忆。')
        return 1
    quote = m.group(1).strip().splitlines()[0][:120]
    try:
        with io.open(LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'ts': time.strftime('%Y-%m-%d %H:%M:%S'), 'tier': tier,
                                'approval_quote': quote}, ensure_ascii=False) + '\n')
    except Exception as e:
        print('WARN: 审批留痕写入失败：%s' % e)
    print('tier-gate: tier=%d · 审批声明已留痕（%s…）' % (tier, quote[:30]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
