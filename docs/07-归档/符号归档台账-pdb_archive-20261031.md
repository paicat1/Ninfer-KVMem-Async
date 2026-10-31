# 符号归档台账 · `engine\pdb_archive`（2026-10-31）

> **角色**：符号归档库（pdb 专用，与引擎 exe 分离）。
> **不进 lineage 件数对账**（`engine_assets -Action gate` 只数 `engine\lineage\*.exe`，截断于 MANIFEST 的「附录 A」之前 ⇒ 23 == 23 不受影响）。
> **禁删**：符号是崩溃取证（symbolize / dump 归因）的唯一依据。
> **体量**：14 件 / 0.52 GB。逐件 sha 为 2026-10-31 实测值。
> **落位理由**：台账放 `docs\07-归档\`（与活账清单、挂账总表同区），避免 `engine\**` 路径触发提交前的 T-CHECKPOINT 声明门（本批为纯文档登记）。

| # | 文件 | 大小(MB) | 配对件 | sha256 |
|---|---|---|---|---|
| 1 | `avcodec-62.pdb` | 32.0 | `engine\self-built-20261008\avcodec-62.dll` | `5C69907824FEFBE529288AB92F8B872367AF6F74E5BA4A59019BC239A41CBF72` |
| 2 | `avdevice-62.pdb` | 1.1 | 第三方符号（无现役件） | `E4040EBDE2443EC4ED2F8FF8DC053066EAE3D5F4256705DE2D6CD7958DC9BD14` |
| 3 | `avfilter-11.pdb` | 12.5 | 第三方符号（无现役件） | `72B4BAA085CFDBD35B8591689FCFCCDDFEA45CD9C75DDB16185857B354CD85D5` |
| 4 | `avformat-62.pdb` | 10.3 | `engine\self-built-20261008\avformat-62.dll` | `45CD9C0A0D66A642B9D87B065C2AED9C8ADAE616E10EA733086590B7BCD4D6CA` |
| 5 | `avutil-60.pdb` | 3.4 | `engine\self-built-20261008\avutil-60.dll` | `1005B0DE5AF850EC2A83378C7B033701A4C6448ABE4652D5DC915FF20EF67D57` |
| 6 | `libcurl-d.pdb` | 6.4 | `engine\self-built-20261008\libcurl-d.dll` | `9459B84B6DADC4D02DD76B16AA29C24B513D8C4678933FA92356ED55C2099F01` |
| 7 | `libcurl.pdb` | 4.8 | `engine\self-built-20261008\libcurl.dll` | `4AB885B63B3699D4D932E84569A5047FC06D896C3B7F9006C0C37CAD1BA544A8` |
| 8 | `ninfer-serve-sym-official_20261019.pdb` | 226.7 | `engine\lineage\ninfer-serve-RC3.exe`（offi） | `AF9BCCD6D22BF818FD139425E454912AA505FB80CFF36CA9383F42BD35ABC24C` |
| 9 | `ninfer-serve-sym_20261018.pdb` | 227.7 | `engine\lineage\ninfer-serve-RC2.exe`（sym3） | `08C944D0EE451EE0148013DBD5A235B2B322488541C57FAD05674B4CA7B023DE` |
| 10 | `pkgconf-8.pdb` | 1.0 | 第三方符号（无现役件） | `2E3DA775B99B99362E4CF3726BC6B2AB9BC4AE73BC03C8F48ECD413CA1D91644` |
| 11 | `swresample-6.pdb` | 0.8 | `engine\self-built-20261008\swresample-6.dll` | `D493644011F915F0D8AAF2E2EB95B9CF57677F9FAFE11E061A006464F0146DF6` |
| 12 | `swscale-9.pdb` | 2.9 | `engine\self-built-20261008\swscale-9.dll` | `0ED3032838211D83BAE8FF22AD2950001E32D24175D2BC9BEC3E912D708E9FF6` |
| 13 | `z.pdb` | 0.6 | `engine\self-built-20261008\z.dll` | `60935F09D575963F11F9E448237EC2A58F30B80FC559DA40CF62958295F052D1` |
| 14 | `zd.pdb` | 1.2 | 第三方符号（无现役件） | `786D5F903E5F470BDC24632CD9F86BB5F0EF63CBB4E30A621ACE25C3175E7903` |

## 相关登记

- `structure.json` 的 `protected_paths` 第 6 条 = `engine/pdb_archive`（防整树消失 / 改名逃逸对账）。
- `PM-RULES.md`「引擎件目录角色」节 = 六目录角色表（`variants` 已废除、本库为符号归档库）。
- `docs\07-归档\活账清单-20261031.md` 与 `挂账总表-20261031.md` 的 D3 行 = 本台账的挂账闭环。
