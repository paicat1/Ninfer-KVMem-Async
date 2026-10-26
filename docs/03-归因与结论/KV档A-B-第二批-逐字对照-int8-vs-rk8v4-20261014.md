# 逐字一致门报表 q8_32k vs rk8v4_40k

| 提示 | content 全等 | reasoning 全等 | 首处差异 |
|---|---|---|---|
| p1_code | N | Y | 位 42: pairs):
    if not pairs -> pairs):
    pairs.sort() |
| p2_code | N | Y | 位 118: r<int,int>> items;
    s -> r<int,int>> cache;
    s |
| p3_json | Y | Y | — |
| p4_json | Y | Y | — |
| p5_quote | Y | Y | — |
| p6_fact | N | Y | 位 19: aph 将一系列内核启动操作预先捕获并编译为单个 -> aph 将一系列内核启动预先捕获并编译为单个图对 |
| p7_open | N | Y | 位 38: 数据完全就绪前即可响应，显著提升了应用的感知性能 -> 数据完全就绪前即可响应，从而显著提升应用的感知性 |
| p8_shell | N | Y | 位 0: du -h --max- -> ls -lhS / he |

**一致 = 3/8 => 拒（<=4/8）**
