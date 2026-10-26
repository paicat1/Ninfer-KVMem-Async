# 引擎关键版本封存清单

> 每个版本在 `engine\lineage\` 各存一份**只读**副本（`ninfer-serve-<代号>-<sha8>.exe`）。
> 校验：`powershell -File scripts\check_engine_versions.ps1`
> 规则：**任何脚本不得覆盖 lineage**；新版本追加新文件，不替换旧的。

| 代号 | 文件 | 大小 (MB) | SHA256 |
|---|---|---|---|
| **S13** | `ninfer-serve-S13-322A972D.exe` | 1272 | `322A972D6596A16D384A7565F2071978F98CBF7EBA52F32B85546E247F9E9495` |
| **SYM3** | `ninfer-serve-SYM3-9453FFC6.exe` | 1313.2 | `9453FFC6FF077252C6102EE43A77F684A25294E937C1A3420A30A93B1995E89B` |
| **OFFI** | `ninfer-serve-OFFI-3543AD18.exe` | 1314 | `3543AD189D2F7A763F69125CE9E67DFE0781EA4BDCC420754A8F6F13A8FACE91` |
| **PG1** | `ninfer-serve-PG1-1000EAAA.exe` | 1272.2 | `1000EAAA486F2A52569098ED8C90B201614726583DB195164092A93919FBB0D9` |
| **PG2** | `ninfer-serve-PG2-5B34F211.exe` | 1272.2 | `5B34F211D7C6990931C823B1FC5D52A16B8E6CDA5C6874B9F0F2B0833BEEA5D0` |

## 代号含义

| 代号 | 含义 |
|---|---|
| S13 | 生产件（`test-run\ninfer-serve.exe`，10-15 构建） |
| SYM3 | 第三代 sym 实验件（`variants\ninfer-serve-sym.exe`，10-18） |
| OFFI | 官方对照件（`variants\ninfer-serve-sym-official.exe`，10-19） |
| PG1 | 加 P-f/P-g 打点（demote `step=`、restore 四字段），10-26 21:01 |
| PG2 | 再加 P-g2 事件计时（`dev=`/`submitted=`），10-26 23:59 |

## 历史事故

- 2026-10-18：SYM3 覆盖生产件约 30 分钟（`engine_ctl` 注释有记）。
- 2026-10-27：`engine_ctl` 旧逻辑每次起服都整份备份（不查哈希），累积 29 份重复备份 36 GB；已加哈希查重并把 `test-run` 去重到 3 份。
