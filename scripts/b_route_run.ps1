
<#
b_route_run.ps1 -- 死亡谷 B 路线【一键流程】（2026-10-18 建）

为什么存在：2026-10-18 首轮 B 路线失败 —— 我先起 ETW 捕获、再去准备造谷，
            中间空转把 240 s 窗口浪费掉 ⇒ 窗口内没有谷 ⇒ 数据无用。
            本脚本把"抓取 + 造谷"焊成一个流程，消灭人工对齐时序这一环。

做什么（全自动）：
  ① 自检管理员
  ② 起 ETW（Latency 组 + 栈采样 Profile+CSwitch）
  ③ 立即施加 400 MiB 外压 + 发长请求造谷（~180 s，与抓取并行）
  ④ 释放压力 → 停 trace → 出报告
  ⑤ 打印产物路径

用法（管理员 PowerShell，一条命令）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\b_route_run.ps1

参数：
  -ValleySec 180   造谷时长（默认 180）
  -Mib 400         外压剂量（默认 400 = 历史 100% 命中）
  -Tag valley_etl  产物名
#>
param(
    [int]$ValleySec = 180,
    [int]$Mib = 400,
    [string]$Tag = 'valley_etl',
    [string]$Root = 'J:\ninfer-kvmem'
)
$ErrorActionPreference = 'Stop'
$wpt   = 'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit'
$xperf = Join-Path $wpt 'xperf.exe'
$py    = 'C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Host '❌ 需管理员权限。请以管理员身份重开 PowerShell 再跑。' -ForegroundColor Red; exit 2 }

$day    = Get-Date -Format 'yyyyMMdd'
$outDir = Join-Path $Root ('work\' + $day)
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$etl = Join-Path $outDir ($Tag + '.etl')

# ② 起 trace（先清残留会话，防"NT Kernel Logger 已存在"）
& $xperf -stop 2>&1 | Out-Null
Write-Host '== 起 ETW（Latency + 栈采样）==' -ForegroundColor Cyan
& $xperf -on Latency -stackwalk Profile+CSwitch -f $etl
if ($LASTEXITCODE -ne 0) { throw "xperf -on 失败 rc=$LASTEXITCODE" }

# ③ 立刻造谷（并行：后台起驱动，本进程只等）
Write-Host ('== 造谷：' + $Mib + ' MiB 外压 + 长请求，持续 ' + $ValleySec + ' s（与抓取并行）==') -ForegroundColor Yellow
$drv = Join-Path $Root 'scripts\experiments\ee_threshold.py'
$job = Start-Job -ScriptBlock {
    param($py, $drv, $Mib, $sec, $wd)
    Set-Location $wd
    & $py -X utf8 $drv --levels $Mib --hold-sec $sec --sample-every 5 --max-min 4 --prompt long 2>&1
} -ArgumentList $py, $drv, $Mib, $ValleySec, $Root

# 抓取窗口 = 造谷时长 + 30 s 缓冲
$total = $ValleySec + 30
for ($i = $total; $i -gt 0; $i -= 15) {
    Write-Host ('   抓取中，剩余 ' + $i + ' s' + '（谷进度见另一窗口）')
    Start-Sleep -Seconds ([Math]::Min(15, $i))
}
Receive-Job $job | Select-Object -Last 6
Remove-Job $job -Force

# ④ 停 trace + 出报告
Write-Host '== 停 trace ==' -ForegroundColor Cyan
& $xperf -d $etl
if ($LASTEXITCODE -ne 0) { Write-Host ('⚠ xperf -d rc=' + $LASTEXITCODE + '（可能无残留会话）') -ForegroundColor Yellow }

$size = if (Test-Path $etl) { [math]::Round((Get-Item $etl).Length / 1MB, 2) } else { 0 }
Write-Host ('✅ etl = ' + $etl + '  (' + $size + ' MiB)') -ForegroundColor Green

$sum = Join-Path $outDir ($Tag + '_summary.txt')
$csv = Join-Path $outDir ($Tag + '_cswitch.csv')
& $xperf -i $etl -a dumper -tle -o $sum 2>&1 | Out-Null
& $xperf -i $etl -a dumper -cswitch -o $csv 2>&1 | Out-Null

Write-Host '== 产物 ==' -ForegroundColor Green
Get-ChildItem $outDir -Filter ($Tag + '*') | ForEach-Object {
    Write-Host ('   ' + $_.Name + '  ' + [math]::Round($_.Length / 1MB, 2) + ' MiB')
}
Write-Host ''
Write-Host '下一步（CB）：分析等待链 —— 主机线程在 cudaGraphLaunch 期间等哪个对象' -ForegroundColor Yellow
