# start_watch.ps1 -- 值守层【唯一起服入口】（2026-10-18 建 · 用户令"规范点"）
#
# 解决的问题（都是实测踩过的）：
#   ① 四个工具被用不同方式起（PowerShell 包装 / 完整路径 / 裸名 python）⇒ 窗口样式三种混着来
#   ② 裸名 python 不在 PATH ⇒ Start-Process 直接失败（2026-10-18 恢复采样器时踩到）
#   ③ 标题每次不一样（且旧标题里带未展开的 $MaxHours 字样）
#   ④ 缺了哪个全靠人眼数窗口
#
# 本脚本保证：
#   a) 一律 PowerShell 窗口、一律固定标题 WATCH-XXX [running]（不再有三种样式）
#   b) 自解析 python 路径（不接受裸名，从根上消灭"找不到文件"）
#   c) 幂等：已在跑的不动；缺的才起（-Force 才全部重启）
#   d) 起后 20 s 逐个验活，缺一个就 exit 3（不静默通过）
#   e) 写 evidence/spawns/<时间>_watch-<key>.json（无 BOM，审计器可严格解析）
#
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_watch.ps1 [-VerifyOnly] [-Force]

param(
    [switch]$VerifyOnly,     # 只验活，不起
    [switch]$Force           # 强制全部重启（默认幂等：缺的才补）
)

$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root

# ---------- a) 自解析 python（不接受裸名） ----------
$PyExe = ''
foreach ($cand in @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
                    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
                    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe")) {
    if (Test-Path $cand) { $PyExe = $cand; break }
}
if (-not $PyExe) {
    $c = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\*\python.exe" -ErrorAction SilentlyContinue |
         Sort-Object FullName -Descending | Select-Object -First 1
    if ($c) { $PyExe = $c.FullName }
}
if (-not $PyExe) { Write-Output 'FATAL: 找不到 python 解释器'; exit 2 }
Write-Output ("python = " + $PyExe)

# ---------- b) 四个工具：固定 key / 固定标题 / 匹配式 ----------
$tools = @(
    @{ Key='hunter';   Name='WATCH-HUNTER';   Script='scripts\valley_hunter.ps1';   Kind='ps1'; Match='*valley_hunter.ps1*' },
    @{ Key='watchdog'; Name='WATCH-WATCHDOG'; Script='scripts\watchdog_hunter.ps1'; Kind='ps1'; Match='*watchdog_hunter.ps1*' },
    @{ Key='logwatch'; Name='WATCH-LOGWATCH'; Script='scripts\valley_logwatch.py';  Kind='py';  Match='*valley_logwatch*' },
    @{ Key='sampler';  Name='WATCH-SAMPLER';  Script='scripts\window_watch.py';     Kind='py';  Match='*window_watch*' }
)

function Get-Alive([string]$match) {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -like $match }).Count
}

# ---------- c) 幂等起服（一律 PowerShell 窗 + 固定标题） ----------
$started = @()
if (-not $VerifyOnly) {
    foreach ($t in $tools) {
        $alive = Get-Alive $t.Match
        if ($alive -gt 0 -and -not $Force) {
            Write-Output ("  [skip]  {0} 已在跑（{1} 个进程）" -f $t.Name, $alive)
            continue
        }
        if ($alive -gt 0 -and $Force) {
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -like $t.Match } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        }
        $title = "{0} [running]" -f $t.Name
        if ($t.Kind -eq 'ps1') {
            $inner = "`$host.UI.RawUI.WindowTitle='{0}'; & '{1}\{2}'" -f $title, $root, $t.Script
        } else {
            $inner = "`$host.UI.RawUI.WindowTitle='{0}'; & '{1}' -X utf8 '{2}\{3}'" -f $title, $PyExe, $root, $t.Script
        }
        $p = Start-Process -FilePath 'powershell' `
             -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $inner) `
             -WorkingDirectory $root -WindowStyle Normal -PassThru
        $started += [pscustomobject]@{ Key = $t.Key; Name = $t.Name; Pid = $p.Id }
        Write-Output ("  [start] {0}  pid={1}" -f $t.Name, $p.Id)
        Start-Sleep -Seconds 2
    }
}

# ---------- e) 写 manifest / spawn 记录（无 BOM） ----------
if ($started.Count -gt 0) {
    $dir = Join-Path $root 'evidence\spawns'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    foreach ($s in $started) {
        $rec = [ordered]@{
            ts      = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
            purpose = ('watch-' + $s.Key)
            pid     = $s.Pid
            entry   = 'start_watch.ps1'
            title   = ($s.Name + ' [running]')
        }
        $json = ($rec | ConvertTo-Json -Compress)
        $f = Join-Path $dir ((Get-Date -Format 'yyyyMMdd_HHmmss') + '_watch-' + $s.Key + '.json')
        [System.IO.File]::WriteAllText($f, $json, (New-Object System.Text.UTF8Encoding($false)))
    }
}

# ---------- d) 验活 ----------
Write-Output '== 验活（20 s 后逐个查）=='
Start-Sleep -Seconds 20
$bad = 0
foreach ($t in $tools) {
    $n = Get-Alive $t.Match
    if ($n -lt 1) { $bad++ }
    $mark = if ($n -ge 1) { 'OK  ' } else { 'DEAD' }
    Write-Output ("  [{0}] {1}（{2} 个进程）" -f $mark, $t.Name, $n)
}
Write-Output ("== 结果：{0}/{1} 正常 ==" -f ($tools.Count - $bad), $tools.Count)
if ($bad -gt 0) { exit 3 }
