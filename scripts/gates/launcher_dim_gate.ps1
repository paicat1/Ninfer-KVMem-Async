# launcher_dim_gate.ps1 -- 启动器维度渲染对账门（2026-11-14 立）
#
# 为什么立：同一天两次「数据层改了、界面层没改」——
#   上午 async 令六个场景预设全部退化（§226）；下午 kvwindow 加进 DIMENSIONS
#   却没加进 _build_widgets 的分区元组，面板一行都不出现。
#   面板不是遍历 DIMENSIONS，而是按 star/f1/f2/fa/f3 的手工元组逐个 row() 构造，
#   所以「DIMENSIONS 有」≠「面板上有」。这条只能靠静态对账拦。
#
# 判据（三条同时成立才 PASS）：
#   1) DIMENSIONS 里每个 key 都在面板渲染清单里（row(...) 调用 或 for k in (...) 元组）
#   2) DIMENSIONS 里每个 key 在 DEFAULTS 里都有默认值
#   3) DIMENSIONS 里每个 key 在 DIM_TIPS 里都有提示（async 例外，它不在 DIMENSIONS）
#
# 退出码：0=PASS  5=BLOCKED  2=输入错误

param([string]$Launcher = "")

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Launcher) { $Launcher = Join-Path $root 'ninfer_launcher.py' }
if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Output "BLOCKED[launcher-dim]: 启动器不存在 -> $Launcher"
    exit 2
}

$lines = Get-Content -LiteralPath $Launcher -Encoding UTF8

# ---- 1) 取 DIMENSIONS 的 key（("key", "label", TABLE), 形式）----
$dimKeys = @()
$inDim = $false
foreach ($ln in $lines) {
    if ($ln -match '^DIMENSIONS\s*=\s*\[') { $inDim = $true; continue }
    if ($inDim) {
        if ($ln -match '^\]') { break }
        $m = [regex]::Match($ln, '^\s*\("([A-Za-z_][A-Za-z0-9_]*)",')
        if ($m.Success) { $dimKeys += $m.Groups[1].Value }
    }
}
if ($dimKeys.Count -eq 0) {
    Write-Output 'BLOCKED[launcher-dim]: 解析不出 DIMENSIONS（格式变了？）'
    exit 2
}

# ---- 2) 取 DEFAULTS 的 key ----
$defaultKeys = @()
$inDef = $false
foreach ($ln in $lines) {
    if ($ln -match '^DEFAULTS\s*=\s*\{') { $inDef = $true; continue }
    if ($inDef) {
        if ($ln -match '^\}') { break }
        foreach ($m in [regex]::Matches($ln, '"([A-Za-z_][A-Za-z0-9_]*)"\s*:')) {
            $defaultKeys += $m.Groups[1].Value
        }
    }
}

# ---- 3) 取 DIM_TIPS 的 key ----
$tipKeys = @()
$inTip = $false
foreach ($ln in $lines) {
    if ($ln -match '^DIM_TIPS\s*=\s*\{') { $inTip = $true; continue }
    if ($inTip) {
        if ($ln -match '^\}') { break }
        foreach ($m in [regex]::Matches($ln, '^\s*"([A-Za-z_][A-Za-z0-9_]*)"\s*:')) {
            $tipKeys += $m.Groups[1].Value
        }
    }
}

# ---- 4) 取面板渲染清单 ----
$panelKeys = @()
$text = ($lines -join "`n")
foreach ($m in [regex]::Matches($text, 'row\(\w+,\s*"([A-Za-z_][A-Za-z0-9_]*)"\)')) {
    $panelKeys += $m.Groups[1].Value
}
# 分区元组一律形如 for k in ("a","b",...):  ——  不要求后面紧跟 row()，
# 因为 f1 的元组里 spec 走 if/else 自定义控件（中间夹约 18 行），正则跨不过去会误报。
foreach ($m in [regex]::Matches($text, 'for k in \(([^)]*)\)\s*:')) {
    foreach ($x in [regex]::Matches($m.Groups[1].Value, '"([A-Za-z_][A-Za-z0-9_]*)"')) {
        $panelKeys += $x.Groups[1].Value
    }
}
# spec 走自定义控件，代码里有显式登记
if ($text -match 'self\._panel_keys\.add\("spec"\)') { $panelKeys += 'spec' }
$panelKeys = $panelKeys | Sort-Object -Unique

# ---- 对账 ----
$missPanel = @($dimKeys | Where-Object { $panelKeys -notcontains $_ })
$missDefault = @($dimKeys | Where-Object { $defaultKeys -notcontains $_ })
$missTip = @($dimKeys | Where-Object { $tipKeys -notcontains $_ })

$fail = 0
if ($missPanel.Count -gt 0) {
    Write-Output ('BLOCKED[launcher-dim]: 以下维度在 DIMENSIONS 里但面板不渲染 -> ' + ($missPanel -join ', '))
    Write-Output '   修法：把它加进 _build_widgets 对应分区的 for k in (...) 元组（规则文件 §2 第 3 项）'
    $fail = 1
}
if ($missDefault.Count -gt 0) {
    Write-Output ('BLOCKED[launcher-dim]: 以下维度没有 DEFAULTS 默认值 -> ' + ($missDefault -join ', '))
    $fail = 1
}
if ($missTip.Count -gt 0) {
    Write-Output ('WARN[launcher-dim]: 以下维度没有 DIM_TIPS 悬停提示 -> ' + ($missTip -join ', '))
    Write-Output '   （不阻断提交，但操作者会不知道这参数干什么；规则文件 §2 第 5 项）'
}

if ($fail -eq 1) { exit 5 }

Write-Output ("PASS[launcher-dim]: DIMENSIONS {0} 项 · 面板 {1} 项 · 全对齐（提示缺失 {2} 项）" -f `
    $dimKeys.Count, $panelKeys.Count, $missTip.Count)
exit 0
