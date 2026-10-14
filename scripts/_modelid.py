# -*- coding: utf-8 -*-
"""服务招牌名（API model 字段）解析器（2026-10-14 立）。

为什么需要：`--model-id` 是"招牌名"，与权重真身名可以不同（engine_ctl 现按件自动切：
swift -> swift-1.5-qwen3.8-27b-gsq-rco-iq3s / 其余 -> qwen3.8-27b-coder390）。
工具若把招牌名写死，换底座后就会 404/误读 —— 这里统一从服务端读。
"""
import json
import urllib.request

FALLBACK = 'qwen3.8-27b-coder390'


def model_id(port=8094):
    """读 http://127.0.0.1:<port>/v1/models 的第一个 id；失败回退 FALLBACK。"""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=3) as r:
            data = json.load(r)
        ids = [m.get('id') for m in data.get('data', []) if m.get('id')]
        return ids[0] if ids else FALLBACK
    except Exception:
        return FALLBACK
