<#
cleanup_files_only.ps1 -- 【只删文件，绝不碰进程】（2026-10-18 建）

为什么存在：上一版 cleanup_elevated.ps1 用"窗口标题匹配"判残留 ⇒ 在提权会话里
            那些进程标题读成空 ⇒ **误杀了猎人（pid 10000）和 VALLEY-HUNTER 包装（26148）**，
            且它在杀到自己/父进程时中断 ⇒ 删数据那步没执行。
            ⇒ 本版**只删文件**，一个进程都不杀。

做什么：删 work\<日期>\valley_etl* 废数据（无谷 ⇒ 无价值），打印释放量 + 磁盘余量，写日志。

用法（管理员）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\cleanup_files_only.ps1
#>
param([string]$Root = 'J:\ninfer-kvmem')
$ErrorActionPreference = 'Continue'
$day = Get-Date -Format 'yyyyMMdd'
$dir = Join-Path $Root ('work\' + $day)
$log = Join-Path $dir 'cleanup_files_only.log'
function L($m) { $s = ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $m); Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }
Set-Content -Path $log -Value ('=== cleanup_files_only ' + (Get-Date) + ' ===') -Encoding UTF8

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
L ('管理员 = ' + $isAdmin)
if (-not $isAdmin) { L '需管理员权限（文件是提权进程创建的）'; exit 2 }

L '--- 删废数据（valley_etl*；不碰任何进程）---'
$freed = 0
$n = 0
# 2026-10-18 扩：不只 valley_etl*，也含 probe*（诊断探针产物）
$patterns = @('valley_etl*', 'probe*.etl', 'probe*.csv', 'probe*_dump.csv', '*.NGENPDB')
foreach ($pat in $patterns) {
Get-ChildItem $dir -Filter $pat -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $sz = $_.Length
        Remove-Item $_.FullName -Force -ErrorAction Stop
        $freed += $sz; $n++
        L ('  deleted ' + $_.Name + ' (' + [math]::Round($sz / 1MB, 1) + ' MiB)')
    } catch {
        L ('  SKIP ' + $_.Name + ' : ' + $_.Exception.Message)
    }
}
}
L ('  共删 ' + $n + ' 个 · 释放 ' + [math]::Round($freed / 1GB, 2) + ' GiB')

L '--- 磁盘 ---'
Get-PSDrive J | ForEach-Object { L ('  J: free=' + [math]::Round($_.Free / 1GB, 1) + ' GiB') }
L '--- 进程（只报告，不动）---'
Get-Process powershell,pwsh,tracerpt -ErrorAction SilentlyContinue | ForEach-Object { L ('  pid=' + $_.Id + ' ' + $_.ProcessName + ' [' + $_.MainWindowTitle + ']') }
L '=== 完成 ==='
Write-Host ''
Write-Host ('日志：' + $log) -ForegroundColor Green
