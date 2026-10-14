# valley_incidence.ps1 -- matched-window incidence comparison (PDL ON vs OFF)
#   Why this exists (measured 2026-10-15 overnight): the valley lives inside a long-running engine
#   and every freshly started arm probed healthy (three captures in a row: pre-capture verify
#   125/116/212 ms, then five arms with no deep reading), and the PDL attribute is baked into the
#   captured graph so it cannot be toggled at replay time. The only causal instrument left is the
#   valley *rate* over matched windows: run PDL-ON for W minutes, then PDL-OFF for W minutes,
#   probe every 20 s with the same 45KB/60-token probe, and compare valley fractions.
param(
    [int]$WindowMinutes = 45,
    [int]$Pairs = 4,
    [string]$Exe     = 'engine\lineage\I3b_step10_rtpdl_20261015.exe',
    [string]$Model   = 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer',
    [string]$KvDtype = 'rk2v4-e8',
    [int]$Pool       = 65536,
    [int]$VerifySlow = 30,
    [int]$DecodeSlow = 60
)
$host.UI.RawUI.WindowTitle = 'KVMem 发生率对照 [运行中] - ON/OFF 各 ' + $WindowMinutes + ' 分钟 × ' + $Pairs + ' 对；关窗=停'
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$log     = '.temp\incidence_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.txt'
$engineLog = 'logs\test_valleywatch.log'
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | INCIDENCE: ' + $m) }
function Say([string]$m) { Write-Output $m; Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }

function Start-IncidenceEngine([bool]$off) {
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 15; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 3
    if ($off) { $env:NINFER_PDL_OFF = '1' } else { [Environment]::SetEnvironmentVariable('NINFER_PDL_OFF', $null, 'Process') }
    $env:NINFER_PDL_FLAG_FILE = 'J:\ninfer-kvmem\.temp\pdl_off.flag'
    Remove-Item -LiteralPath 'J:\ninfer-kvmem\.temp\pdl_off.flag' -ErrorAction SilentlyContinue
    $ok = $false
    for ($try = 1; $try -le 4 -and -not $ok; $try++) {
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $Exe -Tag valleywatch -Model $Model -KvDtype $KvDtype -Pool $Pool -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
        $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
        if ($r -match 'READY') { $ok = $true } else { Start-Sleep -Seconds 10 }
    }
    $rep = (Select-String -Path $engineLog -Pattern 'PDL: programmatic' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line.Trim() })
    $repTxt = '(no self-report)'
    if ($rep) { $repTxt = $rep }
    Say ('engine start (pdl_off=' + [int]$off + ') ready=' + $ok + ' | ' + $repTxt)
    return $ok
}
function Probe([string]$arm) {
    $out = ''
    try { $out = (python -X utf8 scripts\a2gate.py --arm $arm --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join "`n" } catch { }
    $dec = -1.0; $wall = -1.0
    if ($out -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    $n = @(Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue).Count
    return @($dec, $wall, $n)
}
function Get-LastVerify { $l = ''; try { $l = (Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line }) } catch { }; if ($l -match 'verify=([\d.]+)') { return [double]$Matches[1] }; return -1.0 }

J ('INCIDENCE start (window=' + $WindowMinutes + 'min pairs=' + $Pairs + ')')
$script:stampPrev = 0
$summary = @()
for ($p = 1; $p -le $Pairs; $p++) {
    foreach ($off in @(0, 1)) {
        $offBool = [bool]$off
        $started = Start-IncidenceEngine $offBool
        if (-not $started) { Say 'engine failed to start; skipping this window'; continue }
        $t0 = Get-Date; $i = 0; $valley = 0; $n = 0; $deep = 0
        while (((Get-Date) - $t0).TotalMinutes -lt $WindowMinutes) {
            $i++
            $pr = Probe ('inc_p' + $p + '_' + $off + '_' + $i)
            $dec = $pr[0]; $wall = $pr[1]; $stampN = $pr[2]
            $ver = Get-LastVerify
            $fresh = ($stampN -gt $script:stampPrev); $script:stampPrev = $stampN
            if (-not $fresh) { $ver = -1.0 }
            $n++
            $isValley = (($fresh -and $ver -ge $VerifySlow) -or ($dec -gt 0 -and $dec -lt $DecodeSlow))
            if ($isValley) { $valley++ }
            if ($fresh -and $ver -ge 100) { $deep++ }
            Say ('pair' + $p + ' pdl=' + [int]$off + ' probe' + $i + ' decode=' + $dec + ' wall=' + $wall + ' verify=' + $ver + '(fresh=' + $fresh + ') valley=' + [int]$isValley)
            Start-Sleep -Seconds 20
        }
        $rate = $(if ($n -gt 0) { [math]::Round(100.0 * $valley / $n, 1) } else { -1 })
        Say ('WINDOW pair=' + $p + ' pdl_off=' + [int]$off + ' n=' + $n + ' valley=' + $valley + ' rate=' + $rate + '% deep(>=100ms)=' + $deep)
        $summary += ('pair=' + $p + ' pdl_off=' + [int]$off + ' n=' + $n + ' valley=' + $valley + ' rate=' + $rate + '% deep=' + $deep)
    }
}
Say '==== SUMMARY ===='
$summary | ForEach-Object { Say '  ' + $_ }
J ('INCIDENCE done -> ' + $log)
