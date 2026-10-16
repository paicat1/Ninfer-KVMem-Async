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
    [string]$CaseDir = '.temp\cases'
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
$n = 0; $streak = 0; $cases = 0
while ($true) {
    if (((Get-Date) - $t0).TotalHours -ge $MaxHours) { Say "max hours reached, stop"; break }
    $log = 'logs\test_valleywatch.log'
    if ((Test-Path $log) -and ((Get-Item $log).Length/1MB -gt $LogCapMB)) { Say "LOG CAP hit ($LogCapMB MB), stop for safety"; break }
    $p = ProbeOnce
    $fv = FreshVerify
    $n++
    $hit = ($p.decode -ge 0 -and $p.decode -lt 60 -and $fv.v -ge 100)
    if ($hit) { $streak++ } else { $streak = 0 }
    Say ("probe #{0} decode={1} freshVerify={2}(n={3}) streak={4}" -f $n, $p.decode, $fv.v, $fv.n, $streak)
    if ($streak -ge 2) {
        $cases++
        $cid = "case_{0:yyyyMMdd_HHmmss}" -f (Get-Date)
        $d = Snap $cid
        Say "VALLEY CONFIRMED -> case dir $d (decode=$($p.decode), freshVerify=$($fv.v)); scene frozen: NO restart / NO config change / NO pressure"
        $streak = 0
        Start-Sleep -Seconds 120     # 现场留给二级（若获批）：不扰动，只等
        $p2 = ProbeOnce; $fv2 = FreshVerify
        Say ("post-120s probe decode={0} freshVerify={1} (释放即恢复? 与人造谷行为对照)" -f $p2.decode, $fv2.v)
        Add-Content -LiteralPath (Join-Path $d 'probe_series.txt') -Value ("trigger decode=$($p.decode) freshVerify=$($fv.v)`npost120s decode=$($p2.decode) freshVerify=$($fv2.v)") -Encoding UTF8
    }
    if ($n % 10 -eq 0) { Say "heartbeat: probes=$n cases=$cases engine_uptime_h=$([math]::Round(((Get-Date) - (Get-CimInstance Win32_Process -Filter \"Name='ninfer-serve.exe'\" | Select-Object -First 1).CreationDate).TotalHours,2))" }
    Start-Sleep -Seconds 60
}
Say "hunter stop"
