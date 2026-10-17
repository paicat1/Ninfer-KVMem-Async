<#
env_check.ps1 -- 工作环境彻查器（2026-10-18 建 · 用户铁律A）

用户铁律A（2026-10-18）：
  「每次开始工作，先彻查工作环境是否干净」—— 不许无数进程同时开干、废的也不关闭。

本脚本做什么（**只报告，不动手** —— 关什么由用户决定）：
  ① 列全部相关进程：powershell/pwsh/python/ninfer-serve/vram_hold/tracerpt/xperf/wpr/nsys
  ② 按"该留 / 残留 / 未知"三分类判定
  ③ 列显存占用与 GPU 状态
  ④ 列磁盘余量与今日工作目录体积
  ⑤ 列值守四工具状态
  ⑥ 给"是否干净"的结论 + 建议（不执行）

用法：powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\env_check.ps1
每次开始工作【第一步】跑它。
#>
param([string]$Root = 'J:\ninfer-kvmem')
$ErrorActionPreference = 'Continue'

# 该留的判据：窗口标题或命令行特征
$KEEP_TITLE = @('WATCH-HUNTER', 'WATCH-WATCHDOG', 'WATCH-LOGWATCH', 'WATCH-SAMPLER', 'VALLEY-HUNTER')
$KEEP_CMDLINE = @('valley_hunter', 'watchdog_hunter', 'valley_logwatch', 'window_watch',
                  'ninfer-serve', 'CodeBuddy', 'cb_heartbeat',
                  # 2026-10-18 补白名单（防误报）：
                  'Desktop\\proxy think',      # 用户自己的桌面代理程序
                  'thinking_proxy',             # 同上
                  '-NonInteractive',            # CodeBuddy automation（自动攻关轮）
                  'miniconda3',                 # 用户 conda 环境
                  'serve_tee')                  # 引擎日志 tee

Write-Host ''
Write-Host '================ 工作环境彻查 ================' -ForegroundColor Cyan
Write-Host ('时间 = ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Host ''

# ---------- ① 进程 ----------
Write-Host '--- ① 相关进程（该留 / 残留 / 未知）---' -ForegroundColor Yellow
$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(powershell|pwsh|python|pythonw|ninfer-serve|vram_hold|tracerpt|xperf|wpr|nsys)'
}
$keepN = 0; $resN = 0; $unkN = 0
foreach ($p in ($procs | Sort-Object CreationDate)) {
    $cmd = if ($p.CommandLine) { $p.CommandLine } else { '' }
    $title = ''
    try { $title = (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue).MainWindowTitle } catch {}
    $isKeep = $false
    foreach ($k in $KEEP_TITLE) { if ($title -like ('*' + $k + '*')) { $isKeep = $true } }
    foreach ($k in $KEEP_CMDLINE) { if ($cmd -like ('*' + $k + '*')) { $isKeep = $true } }
    # 本脚本自身 / 查询命令 / 瞬时进程（<2 分钟且是查询类）不算残留
    if ($cmd -like '*env_check*') { $isKeep = $true }
    if ($cmd -like '*count_watch*') { $isKeep = $true }
    if ($cmd -like '*Get-CimInstance*') { $isKeep = $true }
    if ($cmd -like '*\.temp\*') { $isKeep = $true }
    $ageMin = ((Get-Date) - $p.CreationDate).TotalMinutes
    if ($ageMin -lt 2) { $isKeep = $true }   # 刚起的 = 瞬时（含本次查询）

    $tag = '未知'
    if ($isKeep) { $tag = '该留'; $keepN++ } else { $tag = '残留?'; $resN++ }
    $age = [math]::Round(((Get-Date) - $p.CreationDate).TotalMinutes, 0)
    $short = $cmd.Substring(0, [Math]::Min(95, $cmd.Length))
    Write-Host ('  [' + $tag.PadRight(5) + '] pid=' + $p.ProcessId.ToString().PadRight(7) + ' ' + $p.Name.PadRight(14) + ' ' + $age.ToString().PadLeft(4) + 'min  ' + $short)
}
Write-Host ('  ⇒ 该留 ' + $keepN + ' · 疑似残留 ' + $resN)

# ---------- ② GPU / 显存 ----------
Write-Host ''
Write-Host '--- ② GPU / 显存 ---' -ForegroundColor Yellow
& nvidia-smi --query-gpu=utilization.gpu,power.draw,memory.used,memory.free --format=csv,noheader | ForEach-Object { Write-Host ('  ' + $_) }
$apps = & nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader 2>$null
$appN = @($apps).Count
Write-Host ('  CUDA 计算进程 = ' + $appN + ' 个（含桌面/overlay；引擎是 ninfer-serve 那个）')
$hold = @(Get-Process vram_hold -ErrorAction SilentlyContinue).Count
Write-Host ('  vram_hold（外压） = ' + $hold + ' 个' + $(if ($hold -gt 0) { '  ← ⚠ 有压力残留' } else { '' }))

# ---------- ③ 磁盘 ----------
Write-Host ''
Write-Host '--- ③ 磁盘 / 今日工作目录 ---' -ForegroundColor Yellow
Get-PSDrive J | ForEach-Object { Write-Host ('  J: free = ' + [math]::Round($_.Free / 1GB, 1) + ' GiB') }
$day = Join-Path $Root ('work\' + (Get-Date -Format 'yyyyMMdd'))
if (Test-Path $day) {
    $sz = (Get-ChildItem $day -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $n = (Get-ChildItem $day -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    Write-Host ('  ' + $day + ' = ' + $n + ' 个文件 · ' + [math]::Round($sz / 1MB, 1) + ' MiB')
    Get-ChildItem $day -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 100MB } | ForEach-Object {
        Write-Host ('    ⚠ 大文件：' + $_.Name + ' (' + [math]::Round($_.Length / 1MB, 1) + ' MiB)') -ForegroundColor Yellow
    }
}

# ---------- ④ 值守四工具 ----------
Write-Host ''
Write-Host '--- ④ 值守四工具 ---' -ForegroundColor Yellow
$py = 'C:\Users\PC\AppData\Local\Programs\Python\Python312\python.exe'
if (Test-Path (Join-Path $Root 'scripts\count_watch.py')) {
    & $py -X utf8 (Join-Path $Root 'scripts\count_watch.py') 2>&1 | Select-Object -First 8 | ForEach-Object { Write-Host ('  ' + $_) }
}

# ---------- ⑤ 结论 ----------
Write-Host ''
Write-Host '--- ⑤ 结论 ---' -ForegroundColor Cyan
$dirty = ($resN -gt 0) -or ($hold -gt 0)
if ($dirty) {
    Write-Host '  ⚠ 环境【不干净】：有疑似残留进程或压力残留' -ForegroundColor Yellow
    Write-Host '  ⇒ 建议（**不自动执行，等用户决定**）：把上面标 [残留?] 的逐条确认后关闭' -ForegroundColor Yellow
} else {
    Write-Host '  ✅ 环境干净（无残留进程 · 无压力残留）' -ForegroundColor Green
}
Write-Host '=============================================' -ForegroundColor Cyan
Write-Host ''
