<#
etw_capture.ps1 -- 死亡谷 B 路线：ETW 内核级等待链采集器（2026-10-18 建）

用途：抓「主机线程卡在 cudaGraphLaunch 时到底在等什么」所需的内核事件
      （Latency 组 = PROC_THREAD + LOADER + DISK_IO + HARD_FAULTS + DPC + INTERRUPT + CSWITCH + PROFILE）
      并带栈采样（Profile+CSwitch），抓完自动出报告。

**必须以管理员运行**（NT Kernel Logger 需要，实测不提权报 0x5 拒绝访问）。

用法（提权 PowerShell）：
    powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\etw_capture.ps1
    powershell ... -File ...\etw_capture.ps1 -Seconds 300 -Tag valley_etl

流程：起 trace → 等待 N 秒（此间由 CB 侧施加压力造谷）→ 停 trace → 出报告
产出：work\<日期>\<Tag>.etl + <Tag>_summary.txt（xperf 摘要）
      + <Tag>_cswitch.csv（上下文切换，供 CB 分析等待链）
#>
param(
    [int]$Seconds = 240,
    [string]$Tag = 'valley_etl',
    [string]$Root = 'J:\ninfer-kvmem'
)
$ErrorActionPreference = 'Stop'
$wpt = 'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit'
$xperf = Join-Path $wpt 'xperf.exe'
if (-not (Test-Path $xperf)) { throw "xperf 不在 $wpt" }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host '❌ 需要管理员权限（NT Kernel Logger）。请以管理员身份重开 PowerShell 再跑。' -ForegroundColor Red
    exit 2
}

$day = Get-Date -Format 'yyyyMMdd'
$outDir = Join-Path $Root ('work\' + $day)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$etl = Join-Path $outDir ($Tag + '.etl')

Write-Host ('== 起 trace（Latency + 栈采样）→ ' + $etl) -ForegroundColor Cyan
& $xperf -on Latency -stackwalk Profile+CSwitch -f $etl
if ($LASTEXITCODE -ne 0) { throw "xperf -on 失败（rc=$LASTEXITCODE）" }

Write-Host ('== 抓取中：' + $Seconds + ' 秒（此间请让 CB 施加压力造谷）…') -ForegroundColor Yellow
for ($i = $Seconds; $i -gt 0; $i -= 15) {
    Write-Host ('   剩余 ' + $i + ' s')
    Start-Sleep -Seconds ([Math]::Min(15, $i))
}

Write-Host '== 停 trace' -ForegroundColor Cyan
& $xperf -d $etl
if ($LASTEXITCODE -ne 0) { throw "xperf -d 失败（rc=$LASTEXITCODE）" }

$size = [math]::Round((Get-Item $etl).Length / 1MB, 2)
Write-Host ('✅ 已产出 ' + $etl + '  (' + $size + ' MiB)') -ForegroundColor Green

Write-Host '== 出报告（xperf 摘要 + 上下文切换 CSV）' -ForegroundColor Cyan
$sum = Join-Path $outDir ($Tag + '_summary.txt')
$csv = Join-Path $outDir ($Tag + '_cswitch.csv')
& $xperf -i $etl -a dumper -tle -o $sum 2>&1 | Out-Null
& $xperf -i $etl -a dumper -cswitch -o $csv 2>&1 | Out-Null

Write-Host '== 完成，产物：' -ForegroundColor Green
Get-ChildItem $outDir -Filter ($Tag + '*') | ForEach-Object {
    Write-Host ('   ' + $_.Name + '  ' + [math]::Round($_.Length / 1MB, 2) + ' MiB')
}
Write-Host ''
Write-Host '下一步（CB 侧）：' -ForegroundColor Yellow
Write-Host '  1) 分析等待链：看主机线程在 cudaGraphLaunch 期间的等待目标（同步对象/驱动例程）'
Write-Host '  2) 交叉核对：与 nsys 的 cudaGraphLaunch 时间窗对齐'
Write-Host '  3) 用 xperf -i <etl> -a dumper -cswitch / wpaexporter 均可继续下钻（不依赖 GUI）'
