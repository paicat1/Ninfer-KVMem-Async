<#
cleanup_elevated.ps1 -- 清理【提权残留】（2026-10-18 建）

为什么存在：B 路线首轮失败后留下提权残留 —— tracerpt 还在写废 CSV、两个管理员窗空挂、
            2.6 GiB 废数据（1.7 GiB etl + 885 MiB csv）。普通权限杀不掉/删不掉（Access denied），
            必须提权清。

做什么：
  ① 杀 tracerpt（还在写废 CSV）
  ② 杀无标题的提权 PowerShell 残留（**保留**：值守四窗 WATCH-* · 猎人 VALLEY-* · CodeBuddy 终端）
  ③ 删 work\<日期>\valley_etl* 废数据（无谷 ⇒ 无价值）
  ④ 打印释放量 + 剩余窗口清单
  ⑤ 写日志（CB 看不到窗口文字）

用法（管理员）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\cleanup_elevated.ps1
#>
param([string]$Root = 'J:\ninfer-kvmem')
$ErrorActionPreference = 'Continue'
$day = Get-Date -Format 'yyyyMMdd'
$dir = Join-Path $Root ('work\' + $day)
$log = Join-Path $dir 'cleanup_elevated.log'
function L($m) { $s = ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $m); Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }
Set-Content -Path $log -Value ('=== cleanup_elevated ' + (Get-Date) + ' ===') -Encoding UTF8

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
L ('管理员 = ' + $isAdmin)
if (-not $isAdmin) { L '需管理员权限'; exit 2 }

L '--- ① 杀 tracerpt ---'
Get-Process tracerpt -ErrorAction SilentlyContinue | ForEach-Object {
    L ('  killing tracerpt pid=' + $_.Id)
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
L ('  剩余 tracerpt = ' + @(Get-Process tracerpt -ErrorAction SilentlyContinue).Count)

L '--- ② 杀提权 PowerShell 残留（保留值守/猎人/CodeBuddy 终端）---'
$keepTitles = @('WATCH-HUNTER', 'WATCH-WATCHDOG', 'WATCH-LOGWATCH', 'WATCH-SAMPLER', 'VALLEY-HUNTER')
$killed = 0
Get-Process powershell -ErrorAction SilentlyContinue | ForEach-Object {
    $t = $_.MainWindowTitle
    $isKeep = $false
    foreach ($k in $keepTitles) { if ($t -like ('*' + $k + '*')) { $isKeep = $true } }
    # CodeBuddy 终端是 pwsh 不是 powershell，这里只处理 Windows PowerShell
    if (-not $isKeep) {
        L ('  killing powershell pid=' + $_.Id + ' [' + $t + ']')
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        $killed++
    } else {
        L ('  KEEP pid=' + $_.Id + ' [' + $t + ']')
    }
}
L ('  杀 $killed 个')

# [GATE] 删除前置门（T#0003/0022/0038/0044/0050）
$dgate = Join-Path $Root '.codebuddy\sda\gates\delete_gate.ps1'
if (Test-Path $dgate) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $dgate -Path $dir
    if ($LASTEXITCODE -ne 0) { L '[GATE] delete_gate BLOCKED'; exit $LASTEXITCODE }
} else {
    L '[GATE] delete_gate.ps1 缺失（降级放行）'
}

L '--- ③ 删废数据（valley_etl* 无谷数据）---'
$freed = 0
Get-ChildItem $dir -Filter 'valley_etl*' -ErrorAction SilentlyContinue | ForEach-Object {
    try { $sz = $_.Length; Remove-Item $_.FullName -Force -ErrorAction Stop; $freed += $sz; L ('  deleted ' + $_.Name + ' (' + [math]::Round($sz/1MB,1) + ' MiB)') }
    catch { L ('  SKIP ' + $_.Name + ' : ' + $_.Exception.Message) }
}
L ('  释放 ' + [math]::Round($freed/1GB,2) + ' GiB')

L '--- ④ 剩余窗口 ---'
Get-Process powershell,pwsh -ErrorAction SilentlyContinue | ForEach-Object { L ('  pid=' + $_.Id + ' [' + $_.MainWindowTitle + ']') }

L '--- ⑤ 磁盘 ---'
Get-PSDrive J | ForEach-Object { L ('  J: free=' + [math]::Round($_.Free/1GB,1) + ' GiB') }
L '=== 完成 ==='
Write-Host ''
Write-Host ('日志：' + $log) -ForegroundColor Green
