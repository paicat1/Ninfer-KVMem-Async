# Contract · C7

- 只改：src\ops\kvmem\kvmem_retrieve_launch.cu、src\ops\kvmem\kvmem_score.h、work\data\bench\*
- 禁触：official-repo\、refs\、work\publish-wt-*
- 语义不变项：head_w(1/(L*H))、mask early-return、候选集、每 b 一次 atomicAdd
- 单刀验收，禁合并；改前 tools\backup_file.py 备份
