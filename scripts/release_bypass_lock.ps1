# release_bypass_lock.ps1 -- 解除"绕过禁令"阻断锁（**解除权归用户**）
#
# 依据：用户 2026-10-17 令「一产生绕开行为 ⇒ 自述犯罪事实 + 回退到绕开前状态」；
#       锁由 scripts\bypass_guard.py 检出绕过时自动写，**解除权只归用户**（与 CASE_LOCKED 同精神）。
#
# 解除前置（脚本会逐条检查，缺一不解除）：
#   ① 自述件存在（evidence\audits\BYPASS_CONFESSION_*.md）
#   ② 被标记的文件已处置（新件已移出仓 / 跟踪件已由人说明并处置）
#
# 用法：powershell -File scripts\release_bypass_lock.ps1 [-Reason "说明"]
param([string]$Reason = '')
$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root

$lock = Join-Path $root 'evidence\audits\BYPASS_LOCK.json'
if (-not (Test-Path $lock)) { Write-Output '（无锁，无需解除）'; exit 0 }

$j = Get-Content $lock -Raw -Encoding UTF8 | ConvertFrom-Json
Write-Output ('当前锁：' + $j.ts + ' · 原因：' + $j.reason)
Write-Output ('自述件：' + $j.confession)
Write-Output ('涉及文件：' + ($j.files -join ', '))

$conf = Join-Path $root ($j.confession -replace '/', '\')
if (-not (Test-Path $conf)) { Write-Output ('拒绝解除：自述件不存在 ' + $conf); exit 1 }
Write-Output '① 自述件存在 ✓'

$still = @()
foreach ($f in $j.files) {
    $p = Join-Path $root ($f -replace '/', '\')
    if (Test-Path $p) { $still += $f }
}
if ($still.Count -gt 0) {
    Write-Output ('⚠ 以下文件仍在仓内（需人确认已按 T-WINDOW 第4条处置）：' + ($still -join ', '))
    Write-Output '   —— 若你确认可解除，请加 -Reason 说明后重跑；本脚本不自动删任何文件。'
    if ([string]::IsNullOrWhiteSpace($Reason)) { exit 1 }
}

$arch = $lock + '.released_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
Move-Item $lock $arch
$rec = @()
$rec += '解除时刻：' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
$rec += '解除人：用户（本脚本由用户运行）'
$rec += '说明：' + $(if ([string]::IsNullOrWhiteSpace($Reason)) { '（未填）' } else { $Reason })
$rec += '原锁已归档：' + (Split-Path $arch -Leaf)
($rec -join "`n") | Set-Content -LiteralPath ($arch + '.release_note.txt') -Encoding UTF8
Write-Output ('② 已解除（原锁归档为 ' + (Split-Path $arch -Leaf) + '）')
Write-Output '   注意：解除 ≠ 免罪；自述件保留为独立证据（不得删除）。'
exit 0
