# -*- coding: utf-8 -*-
"""2026-10-30 物理层 §七#2：本地 structure.json 增补（不入库）。
新增：build-out / work/data / work/draft / scripts/experimental 目录矩阵
      + .temp 只读博物馆声明与撞墙路标（temp_readonly 段）。
"""
import io
import json

P = 'structure.json'
d = json.load(io.open(P, encoding='utf-8'))

d.setdefault('canonical_dirs', {})
d['canonical_dirs']['build-out'] = '编译输出（build-1208a / build-120a / vcpkg_installed）：.gitignore 排除，不进 git；vcpkg 首次需重新 bootstrap'
d['canonical_dirs']['work/data'] = '引擎/实验运行数据落盘（reqlog、gate json、探针输出、守望者 dmon/gpu_sampler 输出）：每日清，不进 git'
d['canonical_dirs']['work/draft'] = '真临时草稿：每日清，不进 git'
d['canonical_dirs']['scripts/experimental'] = '实验脚本默认出生地：文件名带日期前缀 YYYYMMDD_xxx；30 天无人引用→归档评审；入库（前缀标记）'

d['temp_readonly'] = {
    '_doc': ('2026-10-30 物理层治理（.temp 退役）：.temp 整体只读历史博物馆，不再增长。'
             '规则一句话：.temp 不许写——脚本写 scripts/experimental/，运行数据写 work/data/，'
             '编译输出写 build-out/，真草稿写 work/draft/。执行结果回填本文件（本地件，不入库）。'),
    'status': 'planned',  # planned -> readonly 后由 ACL 生效时改 'readonly'
    'lifecycle': {
        '.temp': '只读历史博物馆（存量按既有节奏清偿，不再增长）',
        'build-out/': '编译输出（按 build 生命周期）',
        'scripts/experimental/': '实验脚本（30 天评审）',
        'work/data/': '运行数据（每日清）',
        'work/draft/': '真临时草稿（每日清）',
        'archive/': '归档评审后保留件（永久，本地）',
    },
    'wall_sign': ('撞墙即教育：.temp 写入被拒绝时——脚本写 scripts/experimental/，数据写 work/data/，'
                  '编译输出写 build-out/，见 structure.json temp_readonly.lifecycle 目录矩阵。'),
    'acl_note': ('deny 对 Administrators 组无效；只读经 takeown+setowner SYSTEM 后 deny *S-1-5-32-545:(WD,AD,DC) 生效，'
                 '回滚顺序见方案附七（后做的先退）。'),
}

d['_updated'] = '2026-10-30 物理层 §七#2 本地增补：目录矩阵四项 + temp_readonly 段（structure.json 已退库，本文件纯本地维护）'

io.open(P, 'w', encoding='utf-8', newline='\n').write(
    json.dumps(d, ensure_ascii=False, indent=2))
print('OK: structure.json 增补完成')
