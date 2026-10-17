# gates.ps1 -- 统一门禁（2026-10-17 立）：**一道门跑全部检查器**
#
# 为什么统一：此前只有引用完整性一道门（ref_gate.ps1），结构乱账无人管；
#             而"一类一个家"要靠门禁执行 ⇒ 两个检查器合成一道门，推送前必跑。
# 含两项：
#   ① scripts/check_refs.py      引用完整性（仓内路径是否都存在；断链 > 基线即拦）
#   ② scripts/check_structure.py 结构合规（根目录白名单 + 禁则；**新违规即拦**）
# 规则数据：structure.json（白名单/禁则/已知待清/活件判定三源）—— 规则改了改数据，不改代码。
param([string]$PyExe = '')
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
# —— 解释器解析（2026-10-17 修：硬编码 python 会在 PATH 缺失时造成"假拦截"）——
$PyExe = 'python'
if (-not (Get-Command 'python' -ErrorAction SilentlyContinue)) {
    $cands = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        'py'
    )
    foreach ($c in $cands) {
        if ($c -and (Get-Command $c -ErrorAction SilentlyContinue)) { $PyExe = $c; break }
    }
}
if (-not (Get-Command $PyExe -ErrorAction SilentlyContinue)) {
    Write-Host "WARN: python not found -- gates SKIPPED (not blocked)" -ForegroundColor Yellow
    exit 0
}

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

# —— T-WINDOW 两层（2026-10-17 立：CB 绕开禁令自写 Minimized 启动脚本 ⇒ 用户看不到窗口）——
$launcherOut = & $PyExe -X utf8 scripts\check_launchers.py 2>&1 | Out-String
$m = [regex]::Match($launcherOut, '违规 (\d+) 处')
$lv = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }
$lb = 22
try { $lb = [int]((Get-Content structure.json -Raw | ConvertFrom-Json).window_discipline.launcher_baseline) } catch {}
if ($lv -gt $lb) {
    Write-Host ("BLOCKED[window]: 启动脚本窗口违规 " + $lv + " 处 > 基线 " + $lb + "（新增违规）") -ForegroundColor Red
    $launcherOut -split "`n" | Select-Object -First 8 | ForEach-Object { Write-Host ("   " + $_) }
    $script:fail = $true
} else {
    Write-Host ("window-launchers: " + $lv + " 处（基线 " + $lb + "）-- OK")
}
$auditOut = & $PyExe -X utf8 scripts\audit_windows.py --quiet 2>&1 | Out-String
$arc = $LASTEXITCODE
if ($arc -ne 0) {
    Write-Host "BLOCKED[window]: 窗口审计发现违规（可见性/最小化）" -ForegroundColor Red
    $auditOut -split "`n" | Select-Object -First 8 | ForEach-Object { Write-Host ("   " + $_) }
    $script:fail = $true
} else {
    Write-Host "window-audit: 全部可见且非最小化 -- OK"
}
