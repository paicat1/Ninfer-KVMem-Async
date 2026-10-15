# 修正：window_watch 台账 verify/decode 字段陈旧误报（TELE 独立核验）

- 作者：TeleAgent（第二环境）· 2026-10-16 07:0x
- 背景：A 方案（高频追自然窗口）启动时，window_watch 台账显示"持续 155 分钟谷态"，经独立核验确认是**工具缺陷**。

---

## 1. 现象

`windowwatch_20261016_0410.txt`（04:10 起，155 行）显示引擎**持续处于谷**：
```
verify=228.32ms（恒定）decode=37.9（恒定）→ 看似 2 小时 40 分钟谷态
```

## 二、独立核验（回原件，不采信转述）

1. **实测 decode**（本机连续 5 探）：157.5 / 160.6 / 159.1 / 142.4 / 139.5 —— **全部健康**
2. **当前日志** `test_valleywatch.log`：
   - `req#45 done: decode 140.1 tok/s`（健康）
   - 尾部 200 行 verify≥200 次数=0
   - `step profile: avg submit=31.02 wall=31.08`（健康档 MTP 步）
3. **verify=228.32 的行号**：定位到 **行 1078**，且它是**最后一条 `target-split`**（其后 3345 行全是 ring 日志）
4. **字段分布铁证**：
   - **verify：155 行全部=228.32（一个不差）**
   - **decode：仅 4 个值（79.4/37.9/39.8/39.9）**
   - **GPU 显存：155 行有 16 个不同值（15371→15515，实时波动）** ✓
   - **s13：恒 cy71:ok（台账文件停在 10-15 20:32）**

## 三、根因（window_watch.py 缺陷）

`window_watch.py` 的 `engine_state()` 取**整文件尾部**的最后一条 `target-split` 作为 verify：
```python
for l in reversed(lines):
    m = re.search(r'verify=([\d.]+)', l)
    if m and 'target-split' in l:
        ver = m.group(1); break     # ← 取"全文最后一条"，但该行可能是历史深慢轮
```
**缺陷**：`target-split` 打点只在"慢轮/周期统计"时写；健康运行时几乎不写。当最后一条 target-split 是一条历史深慢轮（verify=228），watch 就会**持续重复报 228**，哪怕引擎早已健康。
- **decode 同理**：`throughput` 行在 idle 时不写 decode，或抓到旧 throughput → 陈旧。
- **s13**：`window_watch` 读最新 `s13_*.txt`，但那个文件停在 10-15 20:32（CB 后没用 s13）→ 恒 cy71。

## 四、影响（对整夜攻关的重要校正）

**关键**：window_watch 的 verify/decode 字段**不可信**（会误报长期谷态）。这直接影响：

1. **CB 夜研 §10 的"自然窗口谷期显存无抬升"负结果**：它用 window_watch 的 decode/verify 判定"在谷期"。若那些"谷期"实际是**健康态被陈旧值误标**，则"显存无抬升"的负结果**可能基于错误的窗口标定**，不能作为"外部压力源假设"的证伪依据。
2. **此前一切依赖 window_watch verify/decode 的"窗口谷"结论需要重审**。

**不推翻的部分**：
- GPU 显存字段实时（155 行 16 值）→ 显存占用数据本身可信。
- CB 的**主动实验**（三闸、长持、剂量）用的是**主动施加+探针**，不依赖 window_watch 的 verify/decode → **不受此缺陷影响**。
- 通过观察到的真实"持续慢态"（如果存在）需用**探针重测**确认，不能用 watch。

## 五、修正建议

1. **window_watch.py 修复**：verify/decode 应从**带时间戳的最近**（如取 60 秒内）行提取；`target-split` 优先取**最近 N 行内**且与当前时间接近的，否则报"idle/无近期打点"而非历史值。
2. **"自然窗口谷"的重新标定**：需用**探针**（a2gate decode）作为谷判定的真值，不能靠 window_watch 的 verify/decode。
3. **对 CB 的建议**：夜研 §10 负结果重审——若其"谷窗"由 watch 标定，需用探针重新确认是否存在真实谷期、以及显存是否真无变化。

## 四、诚实披露
- 本修正基于日志行号、字段分布、实测探针的交叉核验，非转述。
- 我未改动 window_watch.py（只读审核），仅建议修复。
- 不否定 CB 主动实验成果（三阶/长持/剂量均用探针判据，可靠）；仅指出 window_watch 被动观测字段不可信。