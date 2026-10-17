# audit_windows_task.ps1 -- 计划任务用包装（每 5 分钟跑窗口审计）
#
# 为什么存在（2026-10-17，用户授权）：窗口纪律的"审计层"要能**不依赖任何人记得**地跑 ⇒ 挂计划任务。
# 本包装负责：① 自解析 python 解释器（本机 PATH 无 python）② 调 audit_windows.py --quiet
#
# 窗口声明（T-WINDOW 合规）：本件是**计划任务调用的后台审计**（每 5 分钟），**不产生交互窗口**；
#   属"已声明的无界面辅助件"。长驻进程必须走 scripts\spawn_visible.ps1（可见窗口）。
#
# 编码纪律：含中文的 .ps1 **必须 UTF-8 BOM**（否则 PowerShell 5.1 按 ANSI 读 ⇒ 中文乱码 ⇒ 解析失败）。
$ErrorActionPreference = 'Continue'
$root = 'J:\ninfer-kvmem'
Set-Location $root

$PyExe = $null
foreach ($c in @('python', 'py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $PyExe = $c; break } }
if (-not $PyExe) {
    $f = @(Get-ChildItem -Path "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    if ($f.Count -gt 0) { $PyExe = $f[0] }
}
$log = Join-Path $root 'evidence\audits\scheduled_task.log'
if (-not $PyExe) {
    Add-Content -LiteralPath $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' | FATAL: no python interpreter') -Encoding UTF8
    exit 1
}

& $PyExe -X utf8 scripts\audit_windows.py --quiet
$rc = $LASTEXITCODE
if ($rc -ne 0) {
    Add-Content -LiteralPath $log -Value ((Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' | audit rc=' + $rc + ' -- see VIOLATION_window_*.md') -Encoding UTF8
}
exit $rc
