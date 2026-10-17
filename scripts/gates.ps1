# gates.ps1 -- 统一门禁（2026-10-17 立）：**一道门跑全部检查器**
#
# 为什么统一：此前只有引用完整性一道门（ref_gate.ps1），结构乱账无人管；
#             而"一类一个家"要靠门禁执行 ⇒ 两个检查器合成一道门，推送前必跑。
# 含两项：
#   ① scripts/check_refs.py      引用完整性（仓内路径是否都存在；断链 > 基线即拦）
#   ② scripts/check_structure.py 结构合规（根目录白名单 + 禁则；**新违规即拦**）
# 规则数据：structure.json（白名单/禁则/已知待清/活件判定三源）—— 规则改了改数据，不改代码。
param([string]$PyExe = 'python')
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$fail = 0

$refs = Join-Path $root 'scripts\check_refs.py'
if (Test-Path $refs) {
    $o = & $PyExe -X utf8 $refs 2>$null
    $os_ = ($o | Out-String)
    $n = 0
    if ($os_ -match '断链 (\d+) 条') { $n = [int]$Matches[1] }
    if ($n -gt 16) {
        Write-Host ("BLOCKED[refs]: 断链 {0} 条 > 基线 16（新断链）" -f $n) -ForegroundColor Red
        $o | Select-Object -Last 20 | ForEach-Object { Write-Host ("  " + $_) }
        $fail = 1
    } else { Write-Host ("refs: {0} 断链（基线 16）-- OK" -f $n) -ForegroundColor DarkGray }
}

$st = Join-Path $root 'scripts\check_structure.py'
if (Test-Path $st) {
    $o2 = & $PyExe -X utf8 $st 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'BLOCKED[structure]: 出现新违规（不在根白名单、也不在已知待清）' -ForegroundColor Red
        $o2 | Select-Object -Last 25 | ForEach-Object { Write-Host ("  " + $_) }
        $fail = 1
    } else { Write-Host 'structure: 无新违规 -- OK' -ForegroundColor DarkGray }
}

exit $fail
