<#
b_route_run.ps1 -- 死亡谷 B 路线：ETW 内核等待链【一键采集】（2026-10-18 v2）

v2 依据实测修正（work\20261018\etw_probe.log）：
  · xperf -on Latency -f  ⇒ 10 秒只 0.125 MiB（**采不到数据**，首轮 240 s 白抓）
  · xperf -start ... -on  ⇒ 无效标志 0x3ec（此路径不存在）
  · wpr -start ... -filemode / -stop ⇒ 10 秒 519 MiB（**能采到**，但需调窄防丢事件）
  ⇒ 本版改用 wpr；先用 8 秒试探体积，选合适 profile 再正式抓。

做什么（全自动，一次提权跑完）：
  ① 自检管理员
  ② 8 秒试探 wpr CPU profile 的体积 ⇒ 估算正式抓取体积
  ③ 起正式抓取（wpr，与造谷并行）
  ④ **立刻**施加 400 MiB 压力 + 长请求造谷（~150 s）
  ⑤ 释放 → 停 trace → 用 tracerpt 出 CSV（不用已废弃的 -tle）
  ⑥ 全程写日志（CB 看不到窗口文字，靠日志）

用法（管理员，可见窗口；**请不要点窗口**，点了会进"选择模式"暂停）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\b_route_run.ps1
#>
param(
    [int]$ValleySec = 150,
    [int]$Mib = 400,
    [string]$Profile = 'CPU',
    [string]$Tag = 'valley_etl',
    [string]$Root = 'J:\ninfer-kvmem'
)
$ErrorActionPreference = 'Continue'
$wpt = 'C:\Program Files (x86)\Windows Kits\10\Windows Performance Toolkit'
$wpr = Join-Path $wpt 'wpr.exe'
$py  = 'C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe'
$day = Get-Date -Format 'yyyyMMdd'
$dir = Join-Path $Root ('work\' + $day)
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir ($Tag + '_run.log')

function L($m) { $s = ('[' + (Get-Date -Format 'HH:mm:ss') + '] ' + $m); Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }

Set-Content -Path $log -Value ('=== b_route_run v2 ' + (Get-Date) + ' ===') -Encoding UTF8

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
L ('管理员 = ' + $isAdmin)
if (-not $isAdmin) { L '需管理员权限（NT Kernel Logger）。请以管理员重开。'; exit 2 }

# ---------- ② 8 秒试探 ----------
$probe = Join-Path $dir ($Tag + '_probe.etl')
Remove-Item $probe -ErrorAction SilentlyContinue
& $wpr -cancel 2>&1 | Out-Null
L ('试探 profile=' + $Profile + ' · 8 秒')
$o = & $wpr -start $Profile -filemode 2>&1 | Out-String
L ('  start rc=' + $LASTEXITCODE + ' ' + $o.Trim())
Start-Sleep -Seconds 8
$o = & $wpr -stop $probe 2>&1 | Out-String
L ('  stop rc=' + $LASTEXITCODE + ' ' + (($o -split "`n")[0..1] -join ' | '))
$probeMb = if (Test-Path $probe) { [math]::Round((Get-Item $probe).Length / 1MB, 1) } else { 0 }
L ('  ⇒ 8 秒 = ' + $probeMb + ' MiB ⇒ 预计 ' + $ValleySec + ' 秒约 ' + [math]::Round($probeMb / 8 * $ValleySec / 1024, 2) + ' GiB')
if ($probeMb -gt 200) {
    L ('  ⚠ 体积偏大（' + $probeMb + ' MiB/8s）—— **不缩短窗口**（两阶段爬升需 >=150 s），' +
       '改为提示：本次预计 ' + [math]::Round($probeMb / 8 * $ValleySec / 1024, 2) + ' GiB，磁盘需够')
}
Remove-Item $probe -ErrorAction SilentlyContinue

# ---------- ③ 正式抓取 ----------
$etl = Join-Path $dir ($Tag + '.etl')
Remove-Item $etl -ErrorAction SilentlyContinue
& $wpr -cancel 2>&1 | Out-Null
L ('正式抓取：profile=' + $Profile + ' ⇒ ' + $etl)
$o = & $wpr -start $Profile -filemode 2>&1 | Out-String
L ('  start rc=' + $LASTEXITCODE)
if ($LASTEXITCODE -ne 0) { L ('  ❌ 起 trace 失败：' + $o.Trim()); exit 3 }

# ---------- ③.5 ★ 造谷前置：先验证引擎【真的能服务】 ----------
L '前置检查：引擎可服务性（不通过就不造谷）'
$probeUrl = 'http://127.0.0.1:8094/v1/chat/completions'
$engineOk = $false
try {
    $body = @{ model = 'qwen3.8-27b-coder390';
               stream = $false; max_tokens = 4; messages = @(@{ role = 'user'; content = 'ping' }) } | ConvertTo-Json -Depth 5
    $r = Invoke-RestMethod -Uri $probeUrl -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 60
    $engineOk = $true
    L '  ✅ 引擎可服务'
} catch {
    L ('  ❌ 引擎不可服务：' + $_.Exception.Message)
    L '  ⇒ 终止本轮（不造谷、不留废数据）'
    & $wpr -cancel 2>&1 | Out-Null
    exit 4
}

# ---------- ④ 立刻造谷（并行：后台任务） ----------
L ('造谷：' + $Mib + ' MiB + 长请求，' + $ValleySec + ' 秒（与抓取并行）')
$drv = Join-Path $Root 'scripts\experiments\ee_threshold.py'
$job = Start-Job -ScriptBlock {
    param($py, $drv, $Mib, $sec, $wd)
    Set-Location $wd
    & $py -X utf8 $drv --levels $Mib --hold-sec $sec --sample-every 5 --max-min 4 --prompt long 2>&1
} -ArgumentList $py, $drv, $Mib, $ValleySec, $Root

$total = $ValleySec + 25
for ($i = $total; $i -gt 0; $i -= 15) {
    L ('  抓取中，剩余 ' + $i + ' s')
    Start-Sleep -Seconds ([Math]::Min(15, $i))
}
L '造谷任务输出（尾 8 行）：'
# ★ 等造谷任务【自然结束】—— 绝不在它还跑时 Remove-Job -Force（那会切断在飞请求 ⇒ HTTP 499）
L '等造谷任务自然结束…'
$waited = 0
while ((Get-Job -Id $job.Id -ErrorAction SilentlyContinue).State -eq 'Running' -and $waited -lt 600) {
    Start-Sleep -Seconds 5; $waited += 5
}
L ('  造谷任务已结束（等了 ' + $waited + ' s）')
Receive-Job $job | Select-Object -Last 12 | ForEach-Object { L ('  ' + $_) }
Remove-Job $job -Force

# ---------- ⑤ 停 trace + 出报告 ----------
L '停 trace'
$o = & $wpr -stop $etl 2>&1 | Out-String
L ('  stop rc=' + $LASTEXITCODE + ' ' + (($o -split "`n")[0..2] -join ' | '))
$size = if (Test-Path $etl) { [math]::Round((Get-Item $etl).Length / 1MB, 1) } else { 0 }
L ('✅ etl = ' + $etl + '  (' + $size + ' MiB)')

$csv = Join-Path $dir ($Tag + '_dump.csv')
L 'tracerpt 转 CSV（不用已废弃的 -tle）'
& tracerpt $etl -o $csv -of CSV -y 2>&1 | Out-Null
if (Test-Path $csv) {
    $lines = (Get-Content $csv | Measure-Object -Line).Lines
    L ('  ✅ CSV = ' + $csv + '（' + $lines + ' 行）')
} else { L '  ❌ CSV 未生成' }

L '=== 完成 ==='
Write-Host ''
Write-Host ('日志：' + $log) -ForegroundColor Green
