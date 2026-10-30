# 引擎关键版本封存清单

> 每个版本在 `engine\lineage\` 各存一份**只读**副本（`ninfer-serve-<代号>-<sha8>.exe`）。
> 校验：`powershell -File scripts\check_engine_versions.ps1`
> 规则：**任何脚本不得覆盖 lineage**；新版本追加新文件，不替换旧的。

| RC | 原代号 | 文件 | 大小 (MB) | SHA256 |
|---|---|---|---|---|
| **RC1** | S13 / I3b_step13 | `ninfer-serve-RC1.exe` | 1272 | `322A972D6596A16D384A7565F2071978F98CBF7EBA52F32B85546E247F9E9495` |
| **RC2** | SYM3 | `ninfer-serve-RC2.exe` | 1313.2 | `9453FFC6FF077252C6102EE43A77F684A25294E937C1A3420A30A93B1995E89B` |
| **RC3** | OFFI | `ninfer-serve-RC3.exe` | 1314 | `3543AD189D2F7A763F69125CE9E67DFE0781EA4BDCC420754A8F6F13A8FACE91` |
| **RC4** | PG1 | `ninfer-serve-RC4.exe` | 1272.2 | `1000EAAA486F2A52569098ED8C90B201614726583DB195164092A93919FBB0D9` |
| **RC5** | PG2 | `ninfer-serve-RC5.exe` | 1272.2 | `5B34F211D7C6990931C823B1FC5D52A16B8E6CDA5C6874B9F0F2B0833BEEA5D0` |

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

## RC 对照（2026-10-30 改名）

| RC | 原代号 | 说明 |
|---|---|---|
| RC1 | S13 | 旧生产件（10-15） |
| RC2 | SYM3 | 带符号实验件（10-18，当前现役） |
| RC3 | OFFI | 官方链对照件（10-19） |
| RC4 | PG1 | 打点件① demote/restore（10-26） |
| RC5 | PG2 | 打点件② P-g2 计时（10-26） |

## 档案件（步级仪表 · 已归档，不进 RC 序列）

> 这些不是发布候选，是谷攻关期的观测/复现入口。删除前必须先改掉依赖方（见末列）。

| 代号 | 文件 | 大小 (MB) | SHA256 | 用途 / 依赖方 |
|---|---|---|---|---|
| I3b_step1_20261013 | `I3b_step1_20261013.exe` | 1272 | `C5BE13603A88D3326C051900B19D07EBB2921A29A84C84C37623C413F419BDAA` | 步级仪表 · decode 轮 wall 四分解（submit/wait/post/rest），NINFER_STEP_PROFILE=1（依赖方：registry 档案） |
| I3b_step2_20261013 | `I3b_step2_20261013.exe` | 1272 | `AE81E9FC5D02C880AAF2ECD389BE2EDD3AF4895A2E7007B3E13C06E8ABE014DE` | 步级仪表 · 提交段五分（rows/pre/launch/sync/harvest）（依赖方：registry 档案） |
| I3b_step3b_20261014 | `I3b_step3b_20261014.exe` | 1272 | `E8FEE6B63D5A745185237D73BEB62A6EB1A7FE38F91605F11FFA29B24468A01B` | 图内事件四区间 + capture 节点计数（1107）（依赖方：ablate_run / bisect_env 默认件） |
| I3b_step4_debug_20261014 | `I3b_step4_debug_20261014.exe` | 1272 | `DAC82A481D1B8976CD6C2718DC6B9FE9CBA68101B0C3F6E6D812AB63A1BFB745` | 谷态实测调试件（依赖方：registry 档案） |
| I3b_step7_split_20261014 | `I3b_step7_split_20261014.exe` | 1272 | `8EA8F08B9D9D0591C01E5474E4728D50C438C54B3F22B5BB276195748C711591` | 拆分件（谷监视起服）（依赖方：valley_watch 写死） |
| I3b_step9_verifysplit_20261014 | `I3b_step9_verifysplit_20261014.exe` | 1272 | `CFE36B75ABA559E57323C6419E6B245DDDCC4CB8FBB328250703397A72137F6E` | 校验拆分件（PDL A-B-A）（依赖方：pdl_aba 写死） |
| I3b_step10_rtpdl_20261015 | `I3b_step10_rtpdl_20261015.exe` | 1272 | `888316002BDABB4B4DA2B7D3046EEEB7CB3AF6DD869268DAC07826AA8FCB5A36` | rtpdl 件（夜班 / 谷发生率）（依赖方：night_shift / valley_incidence / valley_load_incidence 默认） |
| I3b_step11_gdn_residency_20261015 | `I3b_step11_gdn_residency_20261015.exe` | 1272 | `4CC934701291D94E3892A858F77D73F4FE5D7E1FB49B6512FAB89E1484F37A6D` | GDN 驻留件（S13 谷实验）（依赖方：valley_s13 / valley_s13_v2 默认） |
| G2_default_depth1 | `G2_default_depth1.exe` | 1272.4 | `0BCF764682AC236425EC5D37E02F8EDE1A76500BB22DB87DB663FD393CF12647` | depth=1 默认件（曾被同 sha 逐字节恢复）（依赖方：纪律记录） |
| H1_54fix_20261013 | `H1_54fix_20261013.exe` | 1272.5 | `F8267B60286AEF011E30092E0CAB8A9DF4A4CF58DFA03A3D0136570FA274844F` | 首轮极快 / 谷深 / 超池 500 风险约 11%（v2 已修）；仅回滚锚（依赖方：registry 档案） |

## patch23 验收候选件（2026-10-31 提取归档）

> 来源：`BUILD_LEDGER` L24 `status=candidate` / L25 `status=parked`；`source=engine-src p23 @ 641ea18`；`preset=sym-120a`
> 原件位置：`.temp\build-sym120a\apps\ninfer-serve.exe`（p23 编译现场，冻结中）

| 代号 | 文件 | 大小 (MB) | SHA256 | 用途 / 来源 |
|---|---|---|---|---|
| p23-candidate | `ninfer-serve-p23-candidate.exe` | 1313 | `DC54AE08BE88ECBF52D38AF5EC90165AD53C497CA22204C4521D2D9E58BD9DB4` | patch23 验收候选（配套 pdb 同目录） |

## 谱系快照件（2026-10-31 从 safety_backups 封存）

> 来源：`safety_backups\exe_lineage_2026101[3/4/5]\`；五件 sha 均未在旧台账出现，属 10-13~15 当时的现役件快照。

| 代号 | 文件 | 大小 (MB) | SHA256 | 说明 |
|---|---|---|---|---|
| legacy-20261013_025429 | `ninfer-serve-legacy-20261013_025429.exe` | 1273 | `A070A62D420CFFA830065B7F31A087FF3E63B353DF8FF8F8B3E6FA7413D44E86` | 10-13~15 谱系快照（原 safety_backups\exe_lineage_*），2026-10-31 封存 |
| legacy-20261013_085713 | `ninfer-serve-legacy-20261013_085713.exe` | 1272 | `0B4D1B65121E933B0FC26520A64113E409DBAF04B47483100AC5EBCDA11C236E` | 10-13~15 谱系快照（原 safety_backups\exe_lineage_*），2026-10-31 封存 |
| legacy-20261014_000017 | `ninfer-serve-legacy-20261014_000017.exe` | 1273 | `174F4DEF6332C5EC38B57F2D0421131F0A21EFE3ED69073F02BC5068D88FD581` | 10-13~15 谱系快照（原 safety_backups\exe_lineage_*），2026-10-31 封存 |
| legacy-20261015_191745 | `ninfer-serve-legacy-20261015_191745.exe` | 1272 | `CA364B1B1566AB7288080FA33F8A598306A5A6EEDE98F0CC79C950BC12A0BAE3` | 10-13~15 谱系快照（原 safety_backups\exe_lineage_*），2026-10-31 封存 |
| legacy-20261015_234626 | `ninfer-serve-legacy-20261015_234626.exe` | 1272 | `7D7B9489124CE5F2FE6278B708389DF400042C95292EBA517EE3BFAD5FB0772F` | 10-13~15 谱系快照（原 safety_backups\exe_lineage_*），2026-10-31 封存 |

## B2 件（2026-10-31 从 .temp\build-1208a 提取封存）

> 10-27 07:33 构建；patch23 回退前状态。唯一副本原在 `.temp\build-1208a\apps\ninfer-serve.exe`（该树已于 2026-10-31 07:0x 移入 `_quarantine\20261031\A2\`，7 天观察期）。

| 代号 | 文件 | 大小 (MB) | SHA256 | 说明 |
|---|---|---|---|---|
| B2-20261027 | `ninfer-serve-B2-20261027.exe` | 1272.2 | `A81C843F5256E669C8FE9E0DAA3786C26A19805966CCE3A5E2EB3238587645C4` | 唯一副本，已从 .temp 树提取 |


### 保留裁决（2026-10-31，用户令）

- **结论：这 11 件保留，不动。**
- 理由：谷的现象学判定至今未闭合（构建史 §136 一带：卡死已定性，**谷本身未结案**）；这 11 件是谷攻关的测量基础设施，自带打点（decode 四分解 / 提交段五分 / 图内事件 / rtpdl / GDN 驻留 / 四层拆分），**重建不出来**（源码已推进到 7e14453，打点代码不在主线）。
- **禁止的做法**：不得把脚本 `-Exe` 改指 RC 系件来代替——RC 件没有这些打点，跑出来的数是假复现（看似有效、实则不可比），比删掉更危险。
- **重提条件**：只有当谷正式结案（书面结论 + 引用点改毕）后，才可以按删除纪律重新提案；仅以「占空间」为由不得再提（本机磁盘 free 已 126.65 GB，空间不是约束）。

## 现役件封存（2026-10-31）

| 代号 | 文件 | 大小 (MB) | SHA256 | 说明 |
|---|---|---|---|---|
| RC6 | `ninfer-serve-RC6.exe` | 1272.2 | `35D9E6B1915837597207EDBD71AD17A3E83C7004F4C6A71668B904900A428838` | 主线 s6-1208a-release，source engine-src 7e14453（p23 未包含）；四环验证：arch 384/384 sm_120a、listen@57344、推理 838ms、ninja -n 7；现役件封存副本 |

## 附录 A：全量 sha 底账（2026-10-31 实测）

> 用途：lineage 建库以来第一次全件 sha 实测底账；今后任何改名/替换/删除都以本表为对照基准。
> 纪律：同一字节只许一个名义（一字节一名字），禁止双名义并存。

| # | 文件 | 大小 (MB) | SHA256 |
|---|---|---|---|
| 1 | `G2_default_depth1.exe` | 1272.4 | `0BCF764682AC236425EC5D37E02F8EDE1A76500BB22DB87DB663FD393CF12647` |
| 2 | `H1_54fix_20261013.exe` | 1272.5 | `F8267B60286AEF011E30092E0CAB8A9DF4A4CF58DFA03A3D0136570FA274844F` |
| 3 | `I3b_step1_20261013.exe` | 1272 | `C5BE13603A88D3326C051900B19D07EBB2921A29A84C84C37623C413F419BDAA` |
| 4 | `I3b_step10_rtpdl_20261015.exe` | 1272 | `888316002BDABB4B4DA2B7D3046EEEB7CB3AF6DD869268DAC07826AA8FCB5A36` |
| 5 | `I3b_step11_gdn_residency_20261015.exe` | 1272 | `4CC934701291D94E3892A858F77D73F4FE5D7E1FB49B6512FAB89E1484F37A6D` |
| 6 | `I3b_step2_20261013.exe` | 1272 | `AE81E9FC5D02C880AAF2ECD389BE2EDD3AF4895A2E7007B3E13C06E8ABE014DE` |
| 7 | `I3b_step3b_20261014.exe` | 1272 | `E8FEE6B63D5A745185237D73BEB62A6EB1A7FE38F91605F11FFA29B24468A01B` |
| 8 | `I3b_step4_debug_20261014.exe` | 1272 | `DAC82A481D1B8976CD6C2718DC6B9FE9CBA68101B0C3F6E6D812AB63A1BFB745` |
| 9 | `I3b_step7_split_20261014.exe` | 1272 | `8EA8F08B9D9D0591C01E5474E4728D50C438C54B3F22B5BB276195748C711591` |
| 10 | `I3b_step9_verifysplit_20261014.exe` | 1272 | `CFE36B75ABA559E57323C6419E6B245DDDCC4CB8FBB328250703397A72137F6E` |
| 11 | `ninfer-serve-legacy-20261013_025429.exe` | 1272.5 | `A070A62D420CFFA830065B7F31A087FF3E63B353DF8FF8F8B3E6FA7413D44E86` |
| 12 | `ninfer-serve-legacy-20261013_085713.exe` | 1272 | `0B4D1B65121E933B0FC26520A64113E409DBAF04B47483100AC5EBCDA11C236E` |
| 13 | `ninfer-serve-legacy-20261014_000017.exe` | 1272.5 | `174F4DEF6332C5EC38B57F2D0421131F0A21EFE3ED69073F02BC5068D88FD581` |
| 14 | `ninfer-serve-legacy-20261015_191745.exe` | 1272 | `CA364B1B1566AB7288080FA33F8A598306A5A6EEDE98F0CC79C950BC12A0BAE3` |
| 15 | `ninfer-serve-legacy-20261015_234626.exe` | 1272 | `7D7B9489124CE5F2FE6278B708389DF400042C95292EBA517EE3BFAD5FB0772F` |
| 16 | `ninfer-serve-p23-candidate.exe` | 1313.2 | `DC54AE08BE88ECBF52D38AF5EC90165AD53C497CA22204C4521D2D9E58BD9DB4` |
| 17 | `ninfer-serve-RC1.exe` | 1272 | `322A972D6596A16D384A7565F2071978F98CBF7EBA52F32B85546E247F9E9495` |
| 18 | `ninfer-serve-RC2.exe` | 1313.2 | `9453FFC6FF077252C6102EE43A77F684A25294E937C1A3420A30A93B1995E89B` |
| 19 | `ninfer-serve-RC3.exe` | 1314 | `3543AD189D2F7A763F69125CE9E67DFE0781EA4BDCC420754A8F6F13A8FACE91` |
| 20 | `ninfer-serve-RC4.exe` | 1272.2 | `1000EAAA486F2A52569098ED8C90B201614726583DB195164092A93919FBB0D9` |
| 21 | `ninfer-serve-RC5.exe` | 1272.2 | `5B34F211D7C6990931C823B1FC5D52A16B8E6CDA5C6874B9F0F2B0833BEEA5D0` |

合计：21 件。生成时刻：2026-10-31 01:40:45

### 判决（2026-10-31）：判废弃

- 依据：串行四工况零收益（§182，差 ≤0.71% 且方向有正有负）+ **多路并发零收益**（conc4/conc8 三件冷启 TTFT 极差 <2%）+ host CPU 无差异
- §182 唯一未验场景（并发 host CPU 瓶颈）已验：无差异
- 状态：`parked` → **`abandoned`**；编译现场 `.temp\build-sym120a` 随之解冻
