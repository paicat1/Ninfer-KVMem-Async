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
#   evidence\cases\case_<时间戳>\ 内落：案发基线、nvidia-smi -q、引擎日志尾、reqlog 尾、
#   我方活动时间线（±30min：git log / 我方进程 / scripts·tools·.temp 的近期改动）、探针序列
# 护栏：探针 <=1 发/分钟；日志帽 500MB；每 10 分钟写心跳行（防静默死亡）；默认 12h 自停（可调）。
param(
    [int]$Port = 8094,
    [int]$MaxHours = 12,
    [int]$LogCapMB = 500,
    [string]$CaseDir = 'evidence\cases',
    [int]$PostHitWaitSec = 0
)
Set-Location (Split-Path $PSScriptRoot -Parent)
$Host.UI.RawUI.WindowTitle = 'VALLEY-HUNTER [running] -- 1 probe/min, case on decode<60+verify>=100 x2; auto-stop after $MaxHours h or log cap $LogCapMB MB'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$ledger = Join-Path $CaseDir ("hunter_ledger_$stamp.txt")
New-Item -ItemType Directory -Force -Path $CaseDir | Out-Null
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$STREAK_FILE = Join-Path $CaseDir 'streak_state.json'
$LOG = Join-Path $ROOT 'logs\test_valleywatch.log'   # 忙则让位判断用（只读日志尾）   # v4：streak 跨批持久化
# —— 解释器解析（2026-10-17 修：本机 PATH 无 python/py，探针会全部失败产出 decode=-1）——
$PyExe = $null
foreach ($c in @('python', 'py')) { if (Get-Command $c -ErrorAction SilentlyContinue) { $PyExe = $c; break } }
if (-not $PyExe) {
    $found = @()
    foreach ($pat in @("$env:LOCALAPPDATA\Programs\Python\*\python.exe",
                       "$env:ProgramFiles\Python*\python.exe",
                       "${env:ProgramFiles(x86)}\Python*\python.exe",
                       'C:\Python*\python.exe')) {
        $found += @(Get-ChildItem -Path $pat -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    if ($found.Count -gt 0) { $PyExe = $found[0] }
}
if (-not $PyExe -or -not (Get-Command $PyExe -ErrorAction SilentlyContinue)) {
    Write-Host 'FATAL: no python interpreter found (PATH/常见路径都没有)' -ForegroundColor Red; exit 1
}
function Say($m) { $t = (Get-Date -Format 'HH:mm:ss'); $line = "$t | $m"; Write-Output $line; Add-Content -LiteralPath $ledger -Value $line -Encoding UTF8 }
function ProbeOnce() {
    $o = (& $PyExe -X utf8 scripts\a2gate.py --arm hunt --port $Port --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
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
    if (Test-Path 'evidence\reqlogs\reqlog_watch.jsonl') { Get-Content 'evidence\reqlogs\reqlog_watch.jsonl' -Tail 60 | Out-File -FilePath (Join-Path $d 'reqlog_tail.txt') -Encoding utf8 }
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
    Say ("CRITERION v4.1 (effective now): decode<60 AND [power<thr_rel in >=2 of last 3 beats] AND 3 consecutive **by physical time**; streak persists across hunter restarts **only if gap <=180s** (longer outage breaks the chain and is disclosed in the plan); warmup = engine started <2min ago; thr_rel = idleBase + 0.5*(healthyRef - idleBase)")
while ($true) {
    if (((Get-Date) - $t0).TotalHours -ge $MaxHours) { Say "max hours reached, stop"; break }
    $log = 'logs\test_valleywatch.log'
    if ((Test-Path $log) -and ((Get-Item $log).Length/1MB -gt $LogCapMB)) { Say "LOG CAP hit ($LogCapMB MB), stop for safety"; break }
    $p = ProbeOnce
    $fv = FreshVerify
    $n++
    # —— v4：streak 持久化（跨"猎人批次"按物理时间连续计算，TELE 第七轮）——
    #   猎人重启 ≠ 引擎重启；引擎全程未重启 ⇒ 批次边界不应清零 streak，否则跨批事件永远立不了案。
    if (-not $script:stLoaded) {
        $script:streak = 0; $script:pwFlags = @()
        if (Test-Path $STREAK_FILE) {
            try {
                $j = Get-Content $STREAK_FILE -Raw | ConvertFrom-Json
                $last = [DateTimeOffset]::FromUnixTimeSeconds([int64]$j.last_ts).LocalDateTime
                if (((Get-Date) - $last).TotalSeconds -le 180) {
                    $script:streak = [int]$j.streak
                    $script:pwFlags = @($j.pwflags)
                } else {
                    # TELE 第九轮：长停机后机器态可能已变 ⇒ **不无条件续接**（会把两个事件拼成一个）；
                    #   保留固定阈值，但**断链时记一行**，使"断过链"这件事本身可审计。
                    $gap = [int]((Get-Date) - $last).TotalSeconds
                    if ([int]$j.streak -gt 0) {
                        Say ("STREAK-BREAK: previous streak={0} dropped after gap={1}s (>180s; machine state may have changed) -- auditable" -f $j.streak, $gap)
                    }
                }
            } catch { }
        }
        $script:stLoaded = $true
    }
    # —— 忙则让位（TELE 第十七轮）——
    #   max-concurrency=1：用户请求占槽时我们的探针会被排队（既抓不到、又给用户加延迟）。
    #   若近 30 s 日志里出现过 running >= 1，本拍**跳过探针**，交给零负载的日志通道。
    $busy = $false
    try {
        $tail = Get-Content $LOG -Tail 40 -ErrorAction SilentlyContinue
        $recent = $tail | Where-Object { $_ -match 'throughput' }
        if ($recent) {
            $lastRun = ($recent | Select-Object -Last 1)
            if ($lastRun -match 'running ([1-9])') { $busy = $true }
            $anyRun = $recent | Where-Object { $_ -match 'running ([1-9])' }
            if ($anyRun.Count -ge 6) { $busy = $true }   # 近 40 行里 >=6 条在飞 ⇒ 判定忙
        }
    } catch { }
    if ($busy) {
        Say ("defer: engine busy (user request in flight) -- probe skipped to avoid queueing behind it; log channel covers this window")
        $streak = $script:streak
        if ($n % 10 -eq 0) { Say ("heartbeat(busy): probes={0} cases={1}" -f $n, $cases) }
        Start-Sleep -Seconds 60
        continue
    }
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
    # v3（2026-10-17 07:2x）：**去掉 util>=90% 门槛** —— 谷的判别量是功耗（相对基线），
    #   util 是 nvidia-smi 的时段占比、会采样错位与抖动，实测误杀真谷（062707 #6 decode=37.7/power=174W 但 util=85% ⇒ 未立案）。
    $corrobRel = ($fp.pow -ge 0 -and $fp.pow -lt $thrRel)
    if ($fv.v -ge 0) {
        # 注：当前仪表档下 freshVerify 恒为 -1（target-split 打印门未开）⇒ 本分支实际不激活；
        #   若将来开启，它会优先于功耗辅证（但 pwFlags 仍记功耗）——口径需在开启时重新预登记。
        $corrob = ($fv.v -ge 100); $how = "freshVerify=$($fv.v)"
    } else {
        $corrob = $corrobRel
        $how = ("clk={0}MHz power={1}W util={2}% | thr_rel={3:N1}W (idle={4:N1} ref={5:N1}) | v1abs={6}" -f `
                $fp.clk, $fp.pow, $fp.util, $thrRel, $idleBasePow, $healthyRef, $corrobAbs)
    }
    # v4：warmup 只认**引擎自身**的启动（TELE：猎人重启≠引擎重启，批次首发慢并非必然"预热"——
    #     有的批次首发健康 165/169，有的慢 ⇒ 与机器态相关）。引擎起服 2 分钟内才算冷启动。
    $engStart = (Get-Process ninfer-serve -ErrorAction SilentlyContinue | Select-Object -First 1).StartTime
    $warmup = ($engStart -and ((Get-Date) - $engStart).TotalMinutes -lt 2)
    $hit = (-not $warmup -and $p.decode -ge 0 -and $p.decode -lt 60 -and $corrob)
    if ($hit) { $script:streak++ } else { $script:streak = 0 }
    $script:pwFlags = @(@($script:pwFlags) + $(if ($corrobRel) { 1 } else { 0 })) | Select-Object -Last 3
    $streak = $script:streak
    try {
        [pscustomobject]@{ last_ts = [int64]([DateTimeOffset]::Now.ToUnixTimeSeconds()); streak = $script:streak; pwflags = @($script:pwFlags) } |
            ConvertTo-Json | Set-Content -LiteralPath $STREAK_FILE -Encoding UTF8
    } catch {
        Say ("WARN: streak_state.json 写入失败（streak 将随本次进程结束丢失）：{0}" -f $_.Exception.Message)
    }
    $wtag = $(if ($warmup) { " [warmup: 起步探不计数]" } else { "" })
    Say ("probe #{0} decode={1} {2} (newlines={3}) streak={4}{5}" -f $n, $p.decode, $how, $fv.n, $streak, $wtag)
    # v4：连续 3 拍慢 **且** 近 3 拍里至少 2 拍功耗过线 ⇒ 容忍 1 次采样错位（TELE：功耗读数同样会错位）
    $recentPw = @($script:pwFlags) | Select-Object -Last 3
    $pwOk = @($recentPw | Where-Object { $_ -eq 1 }).Count
    if ($streak -ge 3 -and $pwOk -ge 2) {
        $cases++
        $cid = "case_{0:yyyyMMdd_HHmmss}" -f (Get-Date)
        $d = Snap $cid
        Say "VALLEY CONFIRMED -> case dir $d (decode=$($p.decode), $how); scene frozen: NO restart / NO config change / NO pressure"
        # —— 冻结锁机器化（2026-10-17 08:3x 补齐；CLI 草案 §3.1 与 TELE 意见④）——
        #   纪律行只"写给人看"；锁文件 + 队列表行是**机器可读**的，TELE/CLI 心跳即见。
        $Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
        $lockPath = Join-Path (Join-Path $Repo 'evidence') 'cases\CASE_LOCKED.json'
        $lock = [pscustomobject]@{
            case       = $cid
            time       = (Get-Date -Format 'MM-dd HH:mm:ss')
            prohibit   = @('NO restart', 'NO config change', 'NO pressure injection', 'NO cache clear')
            release_by = 'user only'
            dir        = $d
        }
        # ⚠ PS 5.1 的 `Set-Content -Encoding UTF8` **会写 BOM** ⇒ 机器可读的 JSON 必须用 .NET 无 BOM 写法
        #   （否则外部工具用普通 utf-8 解析会报 'Unexpected UTF-8 BOM'——2026-10-17 实测踩到）
        try {
            $json = $lock | ConvertTo-Json -Depth 3
            [System.IO.File]::WriteAllText($lockPath, $json, (New-Object System.Text.UTF8Encoding($false)))
        } catch { Say ("WARN: CASE_LOCKED.json 写入失败：{0}" -f $_.Exception.Message) }
        $qf = Join-Path $Repo 'docs\协作状态-当前待办与交接-20261016.md'
        try { Add-Content -LiteralPath $qf -Value ("`n> ⛔ CASE-LOCKED: {0} @ {1} —— 禁止重启 / 改配置 / 注入压力 / 清缓存；**解除权归用户**" -f $cid, (Get-Date -Format 'MM-dd HH:mm:ss')) -Encoding UTF8 } catch { }
        Say ("FREEZE LOCK written: {0} (queue line appended)" -f $lockPath)
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
