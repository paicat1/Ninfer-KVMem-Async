# ref_gate.ps1 -- 引用完整性门禁（2026-10-17 立；由 smart_push.ps1 调用，也可单独跑）
#
# 由来：本仓曾把引擎件误删，**只改了 1 处引用、漏了 11 处**，而且**过了很久没人发现**
#       （用户质问"删前不备份、删时不调整链接、删了也发现不了，一错再错"）。
# 行为：跑 scripts/check_refs.py，解析"断链 N 条"；**N > 基线即退出码 1**（新断链当场拦住推送）。
# 基线：16 条已知可接受项 —— 历史备份脚本（引用已下线的 120a 引擎）·
#       引用已移除量化模型的 3 个 verify 脚本 · 有 `Test-Path` 守卫的占位（tools\regression.py）。
# 维护：**修好一条就把基线减一**（基线只降不升）；新增断链必须当场修，不得抬基线。
param([int]$Baseline = 16, [string]$PyExe = 'python')
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$chk = Join-Path $root 'scripts\check_refs.py'
if (-not (Test-Path $chk)) { Write-Host 'ref-gate: check_refs.py 不存在 -- 跳过' -ForegroundColor Yellow; exit 0 }
$out = & $PyExe -X utf8 $chk 2>$null
$outStr = ($out | Out-String)
$n = 0
if ($outStr -match '断链 (\d+) 条') { $n = [int]$Matches[1] }
if ($n -gt $Baseline) {
    Write-Host ("BLOCKED: 引用完整性 -- 断链 {0} 条 > 基线 {1}（本次改动引入了新断链）" -f $n, $Baseline) -ForegroundColor Red
    $out | Select-Object -Last 25 | ForEach-Object { Write-Host ("  " + $_) }
    exit 1
}
Write-Host ("ref-integrity: {0} 断链（基线 {1}）-- OK" -f $n, $Baseline) -ForegroundColor DarkGray
exit 0
