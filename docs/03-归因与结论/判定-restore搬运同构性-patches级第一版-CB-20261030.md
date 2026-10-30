# 判定：restore 回搬的同构性（patches 级第一版）

- 日期：2026-10-30（CB，办公室机零机时）
- 对应挂账：**P0-3**（读 staging 代码，判 restore 回搬是否损坏 KV 页）/ 来源：输出退化复核 §四「发现 D：host 存储格式假说」
- 证据等级：**patches 上下文级**（本机无 `src-tree`，未看 `copy_block` / `copy_block_to_host` 的 backend 实现）
- 结论效力：**第一版判定**，实现层待实验机 src-tree 全量确认

---

## 〇 一句话

**restore 的签名层是「host view → device page 的字节直拷」——无 dtype 转换、无 re-RoPE、无格式重排** ⇒ 「host 副本与 device 页异构」这一假说在签名层不成立；残余风险收敛到**两处**：`copy_block` 的实现语义、`host_replica_current` 的时效判据。

---

## 一 问题

「发现 D」提出：host 侧 KV 副本的**存储格式**若与 device 页不同构（dtype / 布局 / RoPE 帧 / 量化参数），restore 回搬时必然引入数值变化——这可以解释超池召回后的质量漂移与 `#53` 分叉。

判定方法：看 restore 路径是否存在**任何**格式转换步骤。

## 二 证据（`patches/23_restore_batch_publish.patch`，上下文行）

### 2.1 函数签名：只收一个 host view + 一个 device 页

```cpp
// kv_store.h（patch 23 修改后的签名）
[[nodiscard]] bool restore_page_from_host(KVAddressSpaceHandle handle, std::uint32_t page,
                                          HostKVAllocationConstView source,
                                          DeviceKVPageReservation& reservation,
                                          cudaStream_t stream = nullptr,
                                          bool defer_publish = false,
                                          DeviceKVPageHandle* published_out = nullptr) {
    ...
    // 调用点（patch 23 L69-71）：
    addresses.restore_page_from_host(address, page, source, reservation, transfer_streams[0], true, &restored_phys)
```

**签名里没有任何格式参数**——无 `dtype`、无 `scale`、无 `rope_pos`、无 `layout`。

### 2.2 传输后再标记副本有效

```cpp
pages_->publish_device_replica(logical);     // 标记 device 副本 current
pages_->retain_active_reference(logical);    // 增加活跃引用
```

⇒ 语义是「页已就位、可用」，而非「页已重编码」。

### 2.3 复制源是 host extent 的按页 subview

```cpp
// context.cpp（patch 23 L64-65 上下文）
host_kv_extents->view(replica.extent).subview(replica.page_offset, 1);
```

⇒ host 侧按**页偏移**取 view，与 device 页一一对应 ⇒ **假设同一页布局**。

### 2.4 新鲜度守卫（防回搬过期副本）

```cpp
// context.cpp（patch 23 L214-216 上下文）
// Already preserved on the Host (demoted before and then retrieved): no transfer needed.
if (!pages.host_replica_current(logical)) { continue; }
```

⇒ 若 host 副本过期则不传输（走"已 host 副本快速路径"）。

## 三 结论

| 检查项 | 结果 | 依据 |
|---|---|---|
| 是否存在 dtype 转换（如 rk2v4 → rk8v4） | **否** | 签名无 dtype 参数（2.1） |
| 是否存在 re-RoPE / 位置重编码 | **否** | 签名无位置参数（2.1）；无 rope 相关调用 |
| 是否存在布局重排（如 32-token 块重切） | **否** | 按页 subview 一对一（2.3） |
| 是否有副本时效守卫 | **是** | `host_replica_current`（2.4） |

⇒ **「host 与 device 同构」在签名层成立。** 若 `copy_block` 是纯字节拷贝，则 restore 的数值结果与 demote 前**逐位相同**，不存在量化级损失。

## 四 残余风险（两条，均需 src-tree）

| # | 风险 | 为何本机判不了 | 实验机动作 |
|---|---|---|---|
| R1 | `copy_block` / `copy_block_to_host` 的实现是否纯字节（是否做了 scale/pack 变换） | 实现在 `backend_*`（本机无 `src-tree`） | 读 backend 的 `copy_block` 实现，确认无 dereference/repack |
| R2 | `host_replica_current` 的判据是否覆盖 **epoch / 内容版本**（还是只看 flag） | 实现在 `kv_store.h` 的 store 侧（patch 只露调用点） | 读 `LogicalKVPageStore::host_replica_current` 与 `publish_device_replica` 的版本字段 |

## 五 与既有结论的关系

- **`#53` 分叉**：若 R1 成立（纯字节），则 restore 不是分叉源；分叉仍在**页集合/页序**（`#53` 收敛于逻辑决策差异）。
- **超池召回质量漂移**：若 R1 成立且 R2 无洞，则漂移来自**检索选页**（选错块），不是**搬运损坏**——与 `§168 无损坏机制` 一致。
- **`#8` 页漂移族**：本判定不覆盖"页漂移"（那是长会话轮次导致的设备页滞留），仅覆盖单次 demote→restore 的数值一致性。

## 六 边界

- 本判定**只基于 patch 上下文行**，未看 `src-tree` 全量；
- 未覆盖 `NINFER_HOST_PAGEABLE=1` 的 staged 路径（可算 staging 阻塞，但不算数值变换）；
- 未覆盖多 GPU（本树单卡）；
- 结论若与实验机 src-tree 冲突，以 src-tree 为准。

---

## 附：实验机补全清单（P0-3 第二版）

1. `copy_block` 实现（是否 `cudaMemcpyAsync` 纯字节）
2. `copy_block_to_host` 实现（D2H 后是否做整理）
3. `host_replica_current` 判据（版本字段 / epoch）
4. `publish_device_replica` 写入的版本信息
5. `HostKVAllocationConstView` 的内存布局定义（是否与 device 页 stride 一致）
