<#
etw_probe.ps1 -- ETW 工具链诊断（2026-10-18 建）

为什么存在：B 路线首轮"抓了 240 秒只得到 0.12 MiB"（几乎没采到事件），且报告命令用了
            本版本不存在的 `-tle` 参数。**在跑大实验前，先用小规模把工具链验证清楚**。

做什么（每种抓 10 秒，比较产出，全部写日志）：
  ① xperf -on Latency -f …            （首轮用的方式）
  ② xperf -start … / -stop …          （老式两步）
  ③ wpr -start … -filemode / -stop    （WPR 现代方式）
  ④ 三种产出用 tracerpt 转 CSV 验证可解析
  ⑤ 打印各自 etl 大小与事件数 ⇒ 选出可用路径

**自己写日志**（因为 CB 看不到窗口文字）：
  work\<日期>\etw_probe.log

用法（管理员）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\etw_probe.ps1
#>
param(
    [int]$Sec = 10,
    [string]$Root = 'J:\ninfer-kvmem'
)
$ErrorActionPreference = 'Continue'
$wpt   = 'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit'
$xperf = Join-Path $wpt 'xperf.exe'
$wpr   = Join-Path $wpt 'wpr.exe'
$day   = Get-Date -Format 'yyyyMMdd'
$dir   = Join-Path $Root ('work\' + $day)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log   = Join-Path $dir 'etw_probe.log'

function L($m) { $s = ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $m); Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }

Set-Content -Path $log -Value ('=== etw_probe ' + (Get-Date) + ' ===') -Encoding UTF8

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
L ('管理员 = ' + $isAdmin)
if (-not $isAdmin) { L '❌ 需管理员'; exit 2 }

# ---------- ① xperf -on ... -f ----------
L '--- ① xperf -on Latency -stackwalk Profile+CSwitch -f probe1.etl ---'
$e1 = Join-Path $dir 'probe1.etl'
Remove-Item $e1 -ErrorAction SilentlyContinue
& $xperf -stop 2>&1 | Out-Null
$o = & $xperf -on Latency -stackwalk Profile+CSwitch -f $e1 2>&1 | Out-String
L ('   on 输出: ' + $o.Trim())
L ('   rc=' + $LASTEXITCODE)
Start-Sleep -Seconds $Sec
$o = & $xperf -d $e1 2>&1 | Out-String
L ('   d 输出: ' + $o.Trim())
L ('   rc=' + $LASTEXITCODE)
if (Test-Path $e1) { L ('   ⇒ probe1.etl = ' + [math]::Round((Get-Item $e1).Length/1MB,3) + ' MiB') } else { L '   ⇒ probe1.etl 不存在' }

# ---------- ② xperf -start / -stop ----------
L '--- ② xperf -start ... / -stop ... ---'
$e2 = Join-Path $dir 'probe2.etl'
Remove-Item $e2 -ErrorAction SilentlyContinue
$o = & $xperf -start NTKernelLogger -on Latency -stackwalk Profile+CSwitch 2>&1 | Out-String
L ('   start 输出: ' + $o.Trim() + ' rc=' + $LASTEXITCODE)
Start-Sleep -Seconds $Sec
$o = & $xperf -stop NTKernelLogger -d $e2 2>&1 | Out-String
L ('   stop 输出: ' + $o.Trim() + ' rc=' + $LASTEXITCODE)
if (Test-Path $e2) { L ('   ⇒ probe2.etl = ' + [math]::Round((Get-Item $e2).Length/1MB,3) + ' MiB') } else { L '   ⇒ probe2.etl 不存在' }

# ---------- ③ wpr ----------
L '--- ③ wpr -start / -stop ---'
$e3 = Join-Path $dir 'probe3.etl'
Remove-Item $e3 -ErrorAction SilentlyContinue
& $wpr -cancel 2>&1 | Out-Null
$o = & $wpr -start GeneralProfile -filemode 2>&1 | Out-String
L ('   wpr start 输出: ' + $o.Trim() + ' rc=' + $LASTEXITCODE)
Start-Sleep -Seconds $Sec
$o = & $wpr -stop $e3 2>&1 | Out-String
L ('   wpr stop 输出: ' + $o.Trim() + ' rc=' + $LASTEXITCODE)
if (Test-Path $e3) { L ('   ⇒ probe3.etl = ' + [math]::Round((Get-Item $e3).Length/1MB,3) + ' MiB') } else { L '   ⇒ probe3.etl 不存在' }

# ---------- ④ tracerpt 解析验证 ----------
L '--- ④ tracerpt 转 CSV（验证可解析）---'
foreach ($f in @($e1, $e2, $e3)) {
    if (-not (Test-Path $f)) { continue }
    $csv = $f -replace '\.etl$', '_dump.csv'
    $o = & tracerpt $f -o $csv -of CSV -y 2>&1 | Out-String
    $ok = Test-Path $csv
    L ('   ' + (Split-Path $f -Leaf) + ' → csv=' + $ok + '  ' + ($o.Trim() -split "`n" | Select-Object -First 1))
    if ($ok) {
        $lines = (Get-Content $csv -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
        L ('      行数 = ' + $lines)
    }
}

# ---------- ⑤ 结论 ----------
L '--- ⑤ 结论 ---'
$sizes = @()
foreach ($f in @($e1, $e2, $e3)) {
    if (Test-Path $f) { $sizes += [pscustomobject]@{ Name = (Split-Path $f -Leaf); MiB = [math]::Round((Get-Item $f).Length/1MB,3) } }
}
$sizes | ForEach-Object { L ('   ' + $_.Name + ' = ' + $_.MiB + ' MiB') }
$best = ($sizes | Sort-Object MiB -Descending | Select-Object -First 1)
if ($best) { L ('   ⇒ 采到数据最多的是 ' + $best.Name + '（' + $best.MiB + ' MiB）⇒ 大实验用这条路径') }
L '=== 完成 ==='
Write-Host ''
Write-Host ('日志：' + $log) -ForegroundColor Green
