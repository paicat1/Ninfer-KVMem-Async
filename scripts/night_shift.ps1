# night_shift.ps1 -- autonomous overnight valley watch (2026-10-15)
param(
    [string]$Model   = 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer',
    [string]$KvDtype = 'rk2v4-e8',
    [int]$Pool       = 65536,
    [int]$MaxCaptures = 5,
    [double]$Hours    = 8,
    [int]$VerifySlow  = 30,
    [int]$DecodeSlow  = 150
)
$host.UI.RawUI.WindowTitle = 'KVMem 夜间值守机 [运行中] - 自检谷/自捕A-B-A；关窗=停（' + $MaxCaptures + ' 次捕获或 ' + $Hours + ' 小时后自关）'
Set-Location J:\ninfer-kvmem
$state   = '.temp\night_state_' + (Get-Date -Format 'yyyyMMdd') + '.txt'
$journal = '.temp\state_journal.txt'
$log     = 'logs\test_valleywatch.log'
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | NIGHT: ' + $m) }
function Say([string]$m) { Write-Output $m; Add-Content -LiteralPath $state -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }

function Get-EnvProbe([string]$arm) {
    # returns @(decode, wall_seconds, stamp_lines_total)
    $out = ''
    try { $out = (python -X utf8 scripts\a2gate.py --arm $arm --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join "`n" } catch { }
    $dec = -1.0; $wall = -1.0
    if ($out -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    $n = @(Select-String -Path $log -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue).Count
    return @($dec, $wall, $n)
}
function Get-LastVerify {
    $l = ''
    try { $l = (Select-String -Path $log -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line }) } catch { }
    if ($l -match 'verify=([\d.]+)') { return [double]$Matches[1] }
    return -1.0
}
function Clear-ExtraWatchers {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*valley_watch*' -or $_.CommandLine -like '*watch_launch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

J ('NIGHT start (model=' + $Model + ' kv=' + $KvDtype + '/' + $Pool + ' maxcap=' + $MaxCaptures + ' hours=' + $Hours + ')')
$deadline = (Get-Date).AddHours($Hours)
$captures = 0; $cycle = 0; $strikes = 0; $script:stampPrev = 0
$shapes = @('idle', 'idle', 'deep60k', 'multiturn', 'longdecode')

while ((Get-Date) -lt $deadline -and $captures -lt $MaxCaptures) {
    $cycle++
    $shape = $shapes[[int]((($cycle - 1) / 9) % 5)]

    # ---- 状态采样（每循环一条）----
    if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) {
        Say 'engine down -> restart (old profile)'
        $env:NINFER_PDL_FLAG_FILE = 'J:\ninfer-kvmem\.temp\pdl_off.flag'
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step10_rtpdl_20261015.exe' -Tag valleywatch -Model $Model -KvDtype $KvDtype -Pool $Pool -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
        $rr = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
        Say ('  ready=' + $rr)
    }
    $pr = Get-EnvProbe ('ns_probe' + $cycle)
    $dec = $pr[0]; $wall = $pr[1]; $stampN = $pr[2]
    $ver = Get-LastVerify
    $verFresh = ($stampN -gt $script:stampPrev)
    $script:stampPrev = $stampN
    if (-not $verFresh) { $ver = -1.0 }
    $free = (nvidia-smi --query-gpu=memory.used --format=csv,noheader) -replace '[^0-9]', ''
    Say ('cy' + $cycle + ' shape=' + $shape + ' decode=' + $dec + ' wall=' + $wall + 's verify=' + $ver + '(fresh=' + $verFresh + ') vram=' + $free + 'MiB')

    # ---- 谷判据：双信号，连续 2 次 ----
    $slow = (($ver -ge $VerifySlow) -or (($dec -gt 0) -and ($dec -lt $DecodeSlow)) -or ($wall -ge 5))
    if ($slow) { $strikes++ } else { $strikes = 0 }
    if ($strikes -ge 2) {
        $strikes = 0
        J ('valley detected (decode=' + $dec + ' verify=' + $ver + ') -> fast 5-arm A-B-A')
        $atag = 'night' + (Get-Date -Format 'HHmm')
        try {
            powershell -NoProfile -File scripts\pdl_aba.ps1 -Pattern 'on,off,on,off,on' -SkipDeep -NoAbortIfHealthy -ProbeSeconds 120 -KvDtype $KvDtype -Pool 57344 -Model $Model -Tag $atag | Out-Host
            J ('A-B-A done -> .temp\pdl_aba_' + $atag + '.txt')
        } catch { J ('A-B-A threw: ' + $_.Exception.Message) }
        $captures++
        Clear-ExtraWatchers
        Start-Sleep -Seconds 120
        continue
    }

    # ---- 负载形状（触发矩阵）----
    try {
        switch ($shape) {
            'deep60k'   { $o = (python -X utf8 scripts\a2gate.py --arm ('ns_deep' + $cycle) --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 200 2>&1) -join "`n"; if ($o -match 'decode=([\d.]+)') { Say ('  [load deep60k] decode=' + $Matches[1]) } }
            'multiturn' { $o = (python -X utf8 scripts\a2gate.py --arm ('ns_multi' + $cycle) --port 8094 --runs 1 --rounds 6 --filler-kb 60 --max-tokens 150 --nonce ('ns' + $cycle) 2>&1) -join "`n"; $rds = [regex]::Matches($o, 'run 1 round (\d+)\s+[\d.]+s\s+decode=([\d.]+)'); foreach ($m in $rds) { Say ('  [load multiturn r' + $m.Groups[1].Value + '] decode=' + $m.Groups[2].Value) } }
            'longdecode' { $o = (python -X utf8 scripts\a2gate.py --arm ('ns_long' + $cycle) --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 1200 --nonce ('nsL' + $cycle) 2>&1) -join "`n"; if ($o -match 'decode=([\d.]+)') { Say ('  [load longdecode] decode=' + $Matches[1]) } }
            default      { Start-Sleep -Seconds 20 }
        }
    } catch { Say ('  [load threw] ' + $_.Exception.Message) }
    Start-Sleep -Seconds 5
}
J ('NIGHT end (cycles=' + $cycle + ' captures=' + $captures + ')')
Say ('=== NIGHT end cycles=' + $cycle + ' captures=' + $captures + ' ===')
