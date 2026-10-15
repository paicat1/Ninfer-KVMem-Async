# valley_s13_v2.ps1 -- S13 merged (office five elements + three local increments)
#   Office: old platform / one instrument build / long run with no restart inside the group /
#           night-shift load matrix / machine-state window with catch-and-reproduce.
#   Local : host telemetry every cycle / 5-second transient sampling with onset-offset /
#           --host-state-slots as an optional variable (candidate C11).
param(
    [double]$Hours = 3,
    [int]$CycleSeconds = 20,
    [int]$ReproSeconds = 5,
    [int]$HostStateSlots = 0,
    [string]$Exe     = 'engine\lineage\I3b_step11_gdn_residency_20261015.exe',
    [string]$Model   = 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer',
    [string]$KvDtype = 'rk2v4-e8',
    [int]$Pool       = 65536,
    [int]$VerifySlow = 30,
    [int]$DecodeSlow = 60
)
$host.UI.RawUI.WindowTitle = 'KVMem S13v2 [运行中] - 长跑 ' + $Hours + 'h 不重启；见谷即 5s 瞬态 + onset/offset；关窗=停'
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$log     = '.temp\s13v2_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.txt'
$engineLog = 'logs\test_valleywatch.log'
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | S13v2: ' + $m) }
function Say([string]$m) { Write-Output $m; Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
function Get-LastVerify { $l = ''; try { $l = (Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line }) } catch { }; if ($l -match 'verify=([\d.]+)') { return [double]$Matches[1] }; return -1.0 }
function Get-StampCount { return @(Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue).Count }
function Get-LastStamps { return (Select-String -Path $engineLog -Pattern 'spin-stamp|target-split|verify-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 3 | ForEach-Object { $_.Line.Trim() }) -join ' ;; ' }
function Get-HostState {
    $o = Get-CimInstance Win32_OperatingSystem
    $pf = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue
    $up = [math]::Round(((Get-Date) - $o.LastBootUpTime).TotalHours, 1)
    $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $free = [math]::Round($o.FreePhysicalMemory / 1MB, 0)
    $pfm = if ($pf) { [math]::Round($pf.CurrentUsage / 1MB, 0) } else { -1 }
    $top = (Get-Process | Sort-Object CPU -Descending | Select-Object -First 2 | ForEach-Object { $_.Name }) -join '/'
    $gpu = (nvidia-smi --query-gpu=clocks.sm,power.draw,utilization.gpu --format=csv,noheader,nounits 2>$null) -replace ' ', ''
    return ('host up=' + $up + 'h cpu=' + $cpu + '% free=' + $free + 'MiB pf=' + $pfm + 'MiB top=' + $top + ' gpu=' + $gpu)
}
function Probe([string]$arm) {
    $out = ''
    try { $out = (python -X utf8 scripts\a2gate.py --arm $arm --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join "`n" } catch { }
    $dec = -1.0; $wall = -1.0
    if ($out -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    return @($dec, $wall)
}

$env:NINFER_PDL_FLAG_FILE = 'J:\ninfer-kvmem\.temp\pdl_off.flag'
$env:NINFER_MAT_DEBUG = '1'
Remove-Item -LiteralPath 'J:\ninfer-kvmem\.temp\pdl_off.flag' -ErrorAction SilentlyContinue
$slotsArg = ''
if ($HostStateSlots -gt 0) { $slotsArg = ',--host-state-slots,' + $HostStateSlots }
J ('S13v2 start (long-run ' + $Hours + 'h, no restart inside the group, repro=' + $ReproSeconds + 's, hostStateSlots=' + $HostStateSlots + ')')
$deadline = (Get-Date).AddHours($Hours)
$cycle = 0; $valleyCycles = 0; $repro = $false; $onset = ''; $offset = ''
$script:stampPrev = 0
$shapes = @('idle', 'idle', 'deep60k', 'multiturn', 'longdecode')
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) {
        Say 'engine down -> restart (only allowed failure path)'
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $Exe -Tag valleywatch -Model $Model -KvDtype $KvDtype -Pool $Pool -Graph 64 -Vision overlay -StepProfile 1 -Extra ('--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' + $slotsArg) | Out-Null
        $rr = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
        Say ('  ready=' + $rr)
    }
    $cycle++
    $shape = $shapes[[int]((($cycle - 1) / 9) % 5)]
    $pr = Probe ('s13v2_' + $cycle)
    $dec = $pr[0]; $wall = $pr[1]
    $ver = Get-LastVerify
    $stampN = Get-StampCount
    $fresh = ($stampN -gt $script:stampPrev); $script:stampPrev = $stampN
    if (-not $fresh) { $ver = -1.0 }
    $hs = Get-HostState
    $slow = (($fresh -and $ver -ge $VerifySlow) -or ($dec -gt 0 -and $dec -lt $DecodeSlow))
    if ($slow) {
        $valleyCycles++
        if (-not $repro) {
            $repro = $true; $onset = (Get-Date -Format 'HH:mm:ss')
            J ('VALLEY onset ' + $onset + ' -> reproduce mode ON (no restart, no profile change, ' + $ReproSeconds + 's sampling)')
        }
        Say ('VALLEY cy' + $cycle + ' shape=' + $shape + ' decode=' + $dec + ' wall=' + $wall + ' verify=' + $ver + '(fresh) | ' + $hs + ' | stamps: ' + (Get-LastStamps))
    } else {
        if ($repro -and $offset -eq '') {
            $offset = (Get-Date -Format 'HH:mm:ss')
            $dur = ([datetime]$offset - [datetime]$onset).TotalSeconds
            J ('VALLEY offset ' + $offset + ' (duration ' + [math]::Round($dur,0) + 's) -> back to normal sampling')
            Say ('VALLEY-END onset=' + $onset + ' offset=' + $offset + ' duration=' + [math]::Round($dur,0) + 's')
        }
        Say ('cy' + $cycle + ' shape=' + $shape + ' decode=' + $dec + ' wall=' + $wall + ' verify=' + $ver + '(fresh=' + $fresh + ') repro=' + $repro + ' | ' + $hs)
    }
    if ($repro) { Start-Sleep -Seconds $ReproSeconds } else { Start-Sleep -Seconds $CycleSeconds }
    if ($shape -ne 'idle') {
        $nonce = 's13v2_' + $cycle + '_' + (Get-Date -Format 'HHmmss')
        try {
            switch ($shape) {
                'deep60k'   { $o = (python -X utf8 scripts\a2gate.py --arm ('s13v2dp' + $cycle) --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 200 --nonce $nonce 2>&1) -join "`n"; if ($o -match 'decode=([\d.]+)') { Say ('  [load deep60k] decode=' + $Matches[1] + ' | ' + (Get-HostState)) } }
                'multiturn' { $o = (python -X utf8 scripts\a2gate.py --arm ('s13v2mt' + $cycle) --port 8094 --runs 1 --rounds 6 --filler-kb 60 --max-tokens 150 --nonce $nonce 2>&1) -join "`n"; $rds = [regex]::Matches($o, 'run 1 round (\d+)\s+[\d.]+s\s+decode=([\d.]+)'); foreach ($m in $rds) { Say ('  [load multiturn r' + $m.Groups[1].Value + '] decode=' + $m.Groups[2].Value) } }
                'longdecode' { $o = (python -X utf8 scripts\a2gate.py --arm ('s13v2ld' + $cycle) --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 1200 --nonce $nonce 2>&1) -join "`n"; if ($o -match 'decode=([\d.]+)') { Say ('  [load longdecode] decode=' + $Matches[1]) } }
            }
        } catch { Say ('  [load threw] ' + $_.Exception.Message) }
    }
}
if ($repro -and $offset -eq '') { J ('VALLEY still open at end (onset ' + $onset + ')') }
J ('S13v2 end (cycles=' + $cycle + ' valleyCycles=' + $valleyCycles + ' repro=' + $repro + ' onset=' + $onset + ' offset=' + $offset + ')')
Say ('=== S13v2 end cycles=' + $cycle + ' valleyCycles=' + $valleyCycles + ' onset=' + $onset + ' offset=' + $offset + ' ===')
