# valley_hunter.ps1 -- 死亡谷"最小一级猎人"（猎人 v2 草案的一级实现：当场捕猎）
#
# 依据：docs\方案-猎人v2-死亡谷常驻捕猎系统-初步草案-CodeBuddyCLI-20261016.md（v0.1 草案）
#       + TELE 审核件（有条件通过，8 条：判据对齐补丁后口径 valley>=100/deep>=226/vdeep>=500）
# 门控：本脚本只做"一级"——自动冻结快照；**不注入压力、不改配置、不重启引擎**；二级扰动需用户另行明确批准。
#
# 判据（预登记，先写死）：
#   主判据  探针 decode < 60
#   辅证    FreshVerify（新追加日志行里的 target-split verify 最大值）>= 100 ms
#   确认    连续 2 拍都满足才立案（防单点噪声；宁慢十秒不冤枉一次）
# 动作（命中即秒级落案卷，不申请——现场易腐）：
#   .temp\cases\case_<时间戳>\ 内落：案发基线、nvidia-smi -q、引擎日志尾、reqlog 尾、
#   我方活动时间线（±30min：git log / 我方进程 / scripts·tools·.temp 的近期改动）、探针序列
# 护栏：探针 <=1 发/分钟；日志帽 500MB；每 10 分钟写心跳行（防静默死亡）；默认 12h 自停（可调）。
param(
    [int]$Port = 8094,
    [int]$MaxHours = 12,
    [int]$LogCapMB = 500,
    [string]$CaseDir = '.temp\cases',
    [int]$PostHitWaitSec = 0
)
Set-Location (Split-Path $PSScriptRoot -Parent)
$Host.UI.RawUI.WindowTitle = 'VALLEY-HUNTER [running] -- 1 probe/min, case on decode<60+verify>=100 x2; auto-stop after $MaxHours h or log cap $LogCapMB MB'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$ledger = Join-Path $CaseDir ("hunter_ledger_$stamp.txt")
New-Item -ItemType Directory -Force -Path $CaseDir | Out-Null
function Say($m) { $t = (Get-Date -Format 'HH:mm:ss'); $line = "$t | $m"; Write-Output $line; Add-Content -LiteralPath $ledger -Value $line -Encoding UTF8 }
function ProbeOnce() {
    $o = (python -X utf8 scripts\a2gate.py --arm hunt --port $Port --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    $dec = -1; $wall = -1
    if ($o -match '([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    elseif ($o -match 'decode=([\d.]+)') { $dec = [double]$Matches[1] }
    return @{ decode = $dec; wall = $wall; raw = $o }
}
function FreshVerify() {
    # 只解析"自上次采样以来新追加"的日志行（陈旧值不得当证据——TELE 审核第 3 条的落地）
    $log = 'logs\test_valleywatch.log'
    if (-not (Test-Path $log)) { return @{ v = -1; n = 0 } }
    $len = (Get-Item $log).Length
    if ($script:lastLen -eq $null) { $script:lastLen = 0 }
    if ($len -lt $script:lastLen) { $script:lastLen = 0 }   # 日志轮转：重置
    $n = 0; $mx = -1
    if ($len -gt $script:lastLen) {
        $fs = [System.IO.File]::Open($log, 'Open', 'Read', 'ReadWrite')
        try {
            $null = $fs.Seek($script:lastLen, 'Begin')
            $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
            while (($l = $sr.ReadLine()) -ne $null) {
                $n++
                if ($l -match 'target-split.*verify=([\d.]+)') { $v = [double]$Matches[1]; if ($v -gt $mx) { $mx = $v } }
            }
        } finally { $fs.Close() }
        $script:lastLen = $len
    }
    return @{ v = $mx; n = $n }
}
function PowerFingerprint() {
    # 2026-10-17 夜实测：谷档 GPU 功耗中位 63.6 W vs 健康 214.8 W；util/时钟几乎不区分。
    # 候选判据「功耗<100W 且 util>=90%」召回 97%、精确率 97% —— 用于 fresh verify 取不到时作辅证。
    # TELE 意见①：同时取 SM 时钟（空闲 ~952MHz vs 活动 ~2900MHz）⇒ 判据按基线归一化
    $csv = (nvidia-smi --query-gpu=clocks.sm,utilization.gpu,power.draw --format=csv,noheader) -join ""
    $m = [regex]::Match($csv, '([\d.]+)\s*MHz\s*,\s*(\d+)\s*%\s*,\s*([\d.]+)\s*W')
    if ($m.Success) { return @{ clk = [double]$m.Groups[1].Value; util = [int]$m.Groups[2].Value; pow = [double]$m.Groups[3].Value } }
    return @{ clk = -1; util = -1; pow = -1 }
}

function Snap($name) {
    $d = Join-Path $CaseDir $name
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    nvidia-smi -q -d CLOCK,POWER,MEMORY,UTILIZATION | Out-File -FilePath (Join-Path $d 'nvidia-smi_q.txt') -Encoding utf8
    nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu,power.draw --format=csv | Out-File -FilePath (Join-Path $d 'gpu_brief.csv') -Encoding utf8
    nvidia-smi --query-compute-apps=pid,used_memory --format=csv | Out-File -FilePath (Join-Path $d 'compute_apps.csv') -Encoding utf8
    if (Test-Path 'logs\test_valleywatch.log') { Get-Content 'logs\test_valleywatch.log' -Tail 400 | Out-File -FilePath (Join-Path $d 'engine_log_tail.txt') -Encoding utf8 }
    if (Test-Path '.temp\reqlog_watch.jsonl') { Get-Content '.temp\reqlog_watch.jsonl' -Tail 60 | Out-File -FilePath (Join-Path $d 'reqlog_tail.txt') -Encoding utf8 }
    Get-CimInstance Win32_Process -Filter "Name='ninfer-serve.exe'" | ForEach-Object { "pid=$($_.ProcessId) started=$($_.CreationDate)" } | Out-File -FilePath (Join-Path $d 'engine_proc.txt') -Encoding utf8
    # 我方活动时间线（±30min）——自诱导审计的第一问：案发时我们自己在干什么？
    $since = (Get-Date).AddMinutes(-30).ToString('yyyy-MM-dd HH:mm')
    git --no-pager log --since="$since" --date=format:'%H:%M' --pretty=format:'%h %ad %s' | Out-File -FilePath (Join-Path $d 'self_activity_commits.txt') -Encoding utf8
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ninfer-kvmem*' -or $_.CommandLine -like '*a2gate*' -or $_.CommandLine -like '*window_watch*' } | ForEach-Object { "$($_.Name) pid=$($_.ProcessId) $($_.CommandLine.Substring(0,[Math]::Min(90,$_.CommandLine.Length)))" } | Out-File -FilePath (Join-Path $d 'self_activity_procs.txt') -Encoding utf8
    Get-ChildItem scripts, tools, .temp -File -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -gt (Get-Date).AddMinutes(-30) } | Select-Object LastWriteTime, Name | Out-File -FilePath (Join-Path $d 'self_activity_files.txt') -Encoding utf8
    return $d
}
Say "hunter start | criteria: decode<60 AND freshVerify>=100 AND 2 consecutive | cap=${LogCapMB}MB | maxHours=$MaxHours | NO pressure, NO restart, NO config change"
$script:lastLen = $null
$t0 = Get-Date
$script:powHist = @()
$n = 0; $streak = 0; $cases = 0
    $base = PowerFingerprint   # TELE 意见①：起服时的**空闲基线**（判据按此归一化）
    Say ("IDLE BASELINE (pre-first-probe): clk={0}MHz util={1}% pow={2}W | criterion must be normalised against this" -f $base.clk, $base.util, $base.pow)
    $idleBasePow = [double]$base.pow   # 相对判据的空闲基座（TELE 第四轮：跨批次会漂移，必须每批重取）
    $idleBaseClk = [double]$base.clk
    Say ("CRITERION v2 (relative, effective now): thr_rel = idleBase + 0.5*(healthyRef - idleBase); healthyRef = rolling median of last 30 healthy-active powers (default 215W until 5 samples)"
while ($true) {
    if (((Get-Date) - $t0).TotalHours -ge $MaxHours) { Say "max hours reached, stop"; break }
    $log = 'logs\test_valleywatch.log'
    if ((Test-Path $log) -and ((Get-Item $log).Length/1MB -gt $LogCapMB)) { Say "LOG CAP hit ($LogCapMB MB), stop for safety"; break }
    $p = ProbeOnce
    $fv = FreshVerify
    $n++
    $fp = PowerFingerprint
    # —— 判据 v2（2026-10-17 06:2x 预登记，**相对基线**，取代 v1 的绝对 100 W）——
    #   起因（TELE 第四轮实测）：IDLE BASELINE 跨批次漂移（同引擎未重启：660MHz/2%/21.68W → 1770MHz/30%/30.94W）
    #   + probe#7 分歧行（decode=39 属谷档量级，但 109 W 未过绝对 100 W 门槛 ⇒ v1 漏判）。
    #   公式：thr_rel = idleBase + 0.5 × (healthyRef − idleBase)
    #        healthyRef = 近 30 条"健康活动"样本（util≥90 且 decode≥100）的功耗中位；样本 <5 条时用 215 W 默认。
    if ($fp.util -ge 90 -and $p.decode -ge 100 -and $fp.pow -gt 0) {
        $script:powHist = @(@($script:powHist) + $fp.pow) | Select-Object -Last 30
    }
    if (@($script:powHist).Count -ge 5) {
        $sorted = @([double[]]$script:powHist | Sort-Object)
        $healthyRef = [double]$sorted[[math]::Floor($sorted.Count / 2)]
    } else { $healthyRef = 215.0 }
    $thrRel = $idleBasePow + 0.5 * ($healthyRef - $idleBasePow)
    $corrobAbs = ($fp.pow -ge 0 -and $fp.pow -lt 100 -and $fp.util -ge 90)
    $corrobRel = ($fp.pow -ge 0 -and $fp.pow -lt $thrRel -and $fp.util -ge 90)
    if ($fv.v -ge 0) {
        $corrob = ($fv.v -ge 100); $how = "freshVerify=$($fv.v)"
    } else {
        $corrob = $corrobRel
        $how = ("clk={0}MHz power={1}W util={2}% | thr_rel={3:N1}W (idle={4:N1} ref={5:N1}) | v1abs={6}" -f `
                $fp.clk, $fp.pow, $fp.util, $thrRel, $idleBasePow, $healthyRef, $corrobAbs)
    }
    # 预登记排除：起步前两探 = 空闲后首发（冷启动本来就慢：实测 #1 decode 23-29、功耗 ~95W），
    # 不是谷 ⇒ 不计入 streak，避免把冷启动误判成案卷。
    $warmup = ($n -le 2)
    $hit = (-not $warmup -and $p.decode -ge 0 -and $p.decode -lt 60 -and $corrob)
    if ($hit) { $streak++ } else { $streak = 0 }
    $wtag = $(if ($warmup) { " [warmup: 起步探不计数]" } else { "" })
    Say ("probe #{0} decode={1} {2} (newlines={3}) streak={4}{5}" -f $n, $p.decode, $how, $fv.n, $streak, $wtag)
    if ($streak -ge 2) {
        $cases++
        $cid = "case_{0:yyyyMMdd_HHmmss}" -f (Get-Date)
        $d = Snap $cid
        Say "VALLEY CONFIRMED -> case dir $d (decode=$($p.decode), $how); scene frozen: NO restart / NO config change / NO pressure"
        $streak = 0
        if ($PostHitWaitSec -gt 0) {
            Start-Sleep -Seconds $PostHitWaitSec   # 仅当你显式开启：测'是否恢复'需先确认无我方压力注入
            $p2 = ProbeOnce; $fv2 = FreshVerify
            Say ("post-${PostHitWaitSec}s probe decode={0} freshVerify={1}" -f $p2.decode, $fv2.v)
            Add-Content -LiteralPath (Join-Path $d 'probe_series.txt') -Value ("trigger decode=$($p.decode) freshVerify=$($fv.v)`npost${PostHitWaitSec}s decode=$($p2.decode) freshVerify=$($fv2.v)") -Encoding UTF8
        } else {
            Say 'post-hit: no extra probe (default off; the action after a hit is for the finalised design to define, not for this fallback)'
        }
    }
    if ($n % 10 -eq 0) {
        # 先算变量再格式化：避免在 -f 串里嵌套引号（曾致 WQL 无效 + 空值做减法 ⇒ 心跳行报错）
        $ep = Get-CimInstance Win32_Process -Filter "Name='ninfer-serve.exe'" | Select-Object -First 1
        $uph = if ($ep) { [math]::Round(((Get-Date) - $ep.CreationDate).TotalHours, 2) } else { -1 }
        Say ("heartbeat: probes={0} cases={1} engine_uptime_h={2}" -f $n, $cases, $uph)
    }
    Start-Sleep -Seconds 60
}
Say "hunter stop"
