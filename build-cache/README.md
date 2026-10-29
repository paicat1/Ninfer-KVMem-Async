# build-cache/（长重建成本构建树）

本目录用于存放**重建成本 ≥30 分钟的构建树**。属 `structure.json` 的 `asset_class = long-rebuild`：
- `may_clear = false`，`delete = proof-required`
- 删除前必须举证"重建需求永久废弃"，并经用户书面同意

## 现存件（实际位置见备注）

| 件 | 重建成本 | 实际位置 |
|---|---|---|
| sym3 构建树 | 55–66 min | **仍在 `.temp/build-sym120a`**（未挪：CMakeCache 含绝对路径，挪动会废掉增量能力） |

> 已由 `ASSET-CLASS-GATE` 保护：该路径消失即阻断推送。
