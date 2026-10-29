# 结构单一真相：一条命令输出各仓/各分支的本地 vs 远端 vs 差，以及"真身是否已发布"
# 用法：powershell -NoProfile -File tools\repo_state.ps1
$ErrorActionPreference = 'Continue'
$ROOT = 'J:\ninfer-kvmem'
$SUB  = 'J:\ninfer-kvmem\engine-src'
Set-Location $ROOT

Write-Host '===== 主仓 branches (本地 / upstream / 差) ====='
git for-each-ref --format='  %(refname:short) | upstream=%(upstream:short) | %(upstream:track)' refs/heads

Write-Host ''
Write-Host '===== 主仓 远端分支 ====='
foreach ($r in (git branch -r)) { Write-Host ('  ' + $r) }

Write-Host ''
Write-Host '===== engine-src 分支 ====='
git -C $SUB branch -v

Write-Host ''
Write-Host '===== engine-src remotes ====='
$rm = git -C $SUB remote -v
if ($rm) { foreach ($l in $rm) { Write-Host ('  ' + $l) } } else { Write-Host '  (none)' }

Write-Host ''
Write-Host '===== 真身是否已发布（树同一性）====='
$local = (git -C $SUB rev-parse 'HEAD:src-tree/fusion-engine-src' 2>$null)
$pub   = (git rev-parse 'origin/engine-main:src-tree/fusion-engine-src' 2>$null)
if ($local -and $pub -and ($local -eq $pub)) {
    Write-Host ('  SAME  ' + $local + '  => 已发布')
} else {
    Write-Host ('  DIFF  local=' + $local + '  pub=' + $pub + '  => 未发布（会红）')
}

Write-Host ''
Write-Host '===== 锚点 tags ====='
foreach ($t in (git tag -l 'engine-*')) { Write-Host ('  ' + $t) }
foreach ($t in (git tag -l 'pre-scrub*')) { Write-Host ('  ' + $t + '  (仅本地，禁推)') }

Write-Host ''
Write-Host '===== worktrees ====='
git worktree list

Write-Host ''
Write-Host '===== 工作区 ====='
$s1 = git status --short
if ($s1) { foreach ($l in $s1) { Write-Host ('  main: ' + $l) } } else { Write-Host '  main: clean' }
$s2 = git -C $SUB status --short
if ($s2) { foreach ($l in $s2) { Write-Host ('  engine-src: ' + $l) } } else { Write-Host '  engine-src: clean' }
