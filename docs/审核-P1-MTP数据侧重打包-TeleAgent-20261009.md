# 审核报告 · P1 MTP 数据侧重打包（CodeBuddy 施工）

> **审核方**：TeleAgent（星辰超级智能体）｜**日期**：2026-10-09
> **审核对象**：CodeBuddy P1 交付（`scripts\recode_mtp.py` + 产物 `models\…MTP.mtp-q8.ninfer`，q4_0 → q8_0 位级无损重打包）
> **方式**：只读，独立验证（不复述交付方结论；L1 用独立解码器，不 import `recode_mtp`）
> **分工遵循**：按用户 2026-10-09 分工——施工/构建史归 CodeBuddy，审核报告归 TeleAgent；本报告由 TeleAgent 记录与提交。P1 施工未 commit（`scripts/` 未跟踪 + 构建史 modified），提交归 CodeBuddy。

---

## 〇、结论

**P1 的 L0 / L1 / L2 三档验收全部通过，判定审核通过（可出提交包）。** 未发现实质缺陷。

关键说明：
- **L1 我是独立复现的**，不是复述施工方 `--verify` 输出——我写的解码器从 ggml 块定义独立重建、`不 import recode_mtp 任何函数`，排除了"写入与验证同源自洽出错（如 nibble 高低位索引反了）"这一类漏洞。
- **L3/L4（起服测 MTP + A/B 读数）未做**——按纪律 serve 启停归用户双击 BAT / 需授权；且 A/B 前必须关 GPU 占用程序（实测差 3.3 倍）。见 §四待办。

---

## 一、独立验证（我重跑，非复述）

| 项 | 结果 |
|---|---|
| 产物存在与字节数 | dst `…MTP.mtp-q8.ninfer` = **13,485,135,360 B**（2026/10/9 21:50）✅；src = **13,272,798,720 B**（2026/10/8 20:24，**未改动**）✅ |
| L0 结构（独立开容器） | objects=804、tensors=800、resources=4、bindings=979、uses=619；components=`mtp,text` ✅ |
| L0 格式 | **`gguf_q8_0=5`、`gguf_q4_0=0`** ✅；metadata.name=`…Q2LynnStyle-Mtp+mtp-q8` ✅ |
| L0 5 对象新 bytes | 000079=77,987,840 / 000080=189,399,040 / 000789=55,705,600 / 000796=33,423,360 / 000798=94,699,520 —— 与方案 §3.4 表逐项一致 ✅ |
| **L1 全量位级 oracle** | **13,271,040 块 scale 两字节 + int8 values 全部逐位相同，mismatches=0（独立解码器）** ✅ |
| L2 负控 | writer 拒绝 `output coverage is incomplete`，exit=0，dst 不存在、无 `.tmp` 残留 ✅ |
| 申报范围 | `scripts/` 仅 `recode_mtp.py`（12,545 B）+ `__pycache__`（已被 `.gitignore` `__pycache__/` 忽略，`check-ignore` 确认不入库）；构建史 +68/−6 ✅ |

---

## 二、L1 独立 oracle 的取证（为何不是复述）

**不依赖交付方结论**。我的验证脚本 `verify_p1_l1.py`（`.temp/`，一次性中间物）：
- **不 import** `recode_mtp`，直接 `from tools.artifact.reader import Artifact` 读两个容器的**原始字节**；
- 独立按 ggml 块定义解析 q4_0（18B/块：fp16 `d` + 16B nibble，低 4 位=元素 2i、高 4 位=元素 2i+1）与 q8_0（34B/块：fp16 `d` + 32 int8）；
- 逐块断言：**scale 两字节逐字节相同** 且 **`(nibble−8)` 的 int8 值与 q8_0 的 int8 值相同**。

实测（全量，非抽样）：
```
weight/000079  blocks=  2293760 scale_bytes_identical=True values_identical=True mismatches=0
weight/000080  blocks=  5570560 scale_bytes_identical=True values_identical=True mismatches=0
weight/000789  blocks=  1638400 scale_bytes_identical=True values_identical=True mismatches=0
weight/000796  blocks=   983040 scale_bytes_identical=True values_identical=True mismatches=0
weight/000798  blocks=  2785280 scale_bytes_identical=True values_identical=True mismatches=0
L1 VERDICT: PASS (bit-exact, full-block oracle, independent decoder)
```
合计 **13,271,040 块零不匹配**。此独立解码器与 `recode_mtp.py` 内部 oracle 不同源 ⇒ 排除了自洽假绿风险。

`[EVIDENCE] .temp/verify_p1_l1.py:66-92: 独立 parse_q4_0/parse_q8_0（不引用 recode_mtp）`
`[EVIDENCE] writer.py:256: if self._coverage[obj.id].ranges != [(0, obj.bytes)]: raise ArtifactError(f"{obj.id}: output coverage is incomplete")`

---

## 三、L2 负控独立复核

负控机制**代码级确认存在**（`writer.py:256`：未全覆盖 → 抛 `ArtifactError`），并实际复跑：

```
negative control: wrote weight/000079 ONE BYTE SHORT (77987839 of 77987840 declared bytes), finishing early
negative control: writer raised: resource/text/tokenizer.json: output coverage is incomplete
negative control: PASS (refused as required)
exit=0
```
> 注：负控写短的是 `weight/000079`，但 writer 报错的是**首个未覆盖对象** `resource/text/tokenizer.json`（它从未被写）。这恰好证明 coverage 检查对**任意**未覆盖对象都生效、按对象清单严格全覆盖，语义正确。
> 残留检查：dst 不存在、无 `.tmp`（writer `abort()` 清理，`writer.py:281-289`）。

---

## 四、通过项（已核实，无需改）

- **`scripts\recode_mtp.py` 落位正确**：根 `tools/` 被 `.gitignore:31-33` 排除（③类工作流工具链，`smart_push.ps1`/`tools/`），落 `scripts\` 才能入库（②类项目工具）——符合方案 §3.3。
- **用 `iter_range` 读源 q4_0**（`recode_mtp.py:118-119`），规避 `iter_object` 的 `validate_encoding` 对 q4_0 抛错（`reader.py:165-167`）。
- **`ResourceSpec` 关键字传参**（`recode_mtp.py:196`），避免把 encoding 喂进 bytes。
- **metadata.name 追加 `+mtp-q8`**（标记非原厂件，T-RECORD）；`provenance.mtp_recode` 登记来源/方法/源 artifact_id。
- **原件零写入**：`recode_mtp.py` 全程只读 src；writer 对已存在目标抛 `FileExistsError`（`writer.py:150-151`）。

---

## 五、待用户决策 / 待办

| # | 事项 | 状态 |
|---|---|---|
| 1 | **Step 8/9 起服测 MTP**（`.mtp-q8.ninfer` + `--spec mtp`） | 待授权；**先关 GPU 占用程序**（浏览器/QQ/Overlay，实测差 3.3 倍） |
| 2 | L4 A/B 读数（裸解码 vs MTP，同语料同参数、关思考；记录 tok/s + drafted/accepted） | 待起服后 |
| 3 | **提交 `scripts\recode_mtp.py` + 构建史**（CodeBuddy） | 本审核通过后、经用户批准由 CodeBuddy 提交/push |
| 4 | 本审核报告提交（TeleAgent） | 经用户批准后由我提交 |
| 5 | MTP 收益用 official 引擎交叉验证 | 已同意，后续 |

**注**：`models\*.ninfer` 产物属输入物料、不入库（方案 §10 裁决：仅脚本入库）。

---

## 六、风险提示（如实披露，非阻塞）

- 本模型此前**无任何 `gguf_q8_0` 张量**（首次启用引擎 q8_0 通路，方案 §6 明示）——L1 全量自证转码无损，但**引擎 q8_0 矩阵乘内核对负 `d` 的符号假设**未能穷尽源码验证（`ggml_bridge.cu` 的 `vecdot/mmq` 均为 `sum×d` 直接相乘，未见符号假设）。此残留由 **L3（装得上）+ L4b（无系统性劣化）** 端到端兜底——属起服后验证，不是本次审核的遗漏。

---

**署名**：TeleAgent ｜ 2026-10-09 ｜ `J:\ninfer-kvmem`