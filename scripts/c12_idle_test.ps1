param([int]$IdleSec = 300)
# c12_idle_test.ps1 -- active reproduction of C12 (the idle-then-first-request hang).
# Protocol: ensure a healthy engine, then deliberately idle for IdleSec with no requests, then send ONE
# probe with a hard timeout. If the probe hangs, C12 is reproduced; if it answers (slow or fast), it is not
# (at this idle length). Then back-to-back probes to see whether a single request warms it up.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\c12_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function ProbeTimed($tag, $timeoutSec) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $job = Start-Job -ScriptBlock {
        param($p)
        $o = (python -X utf8 J:\ninfer-kvmem\scripts\a2gate.py --arm c12 --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
        return $o
    } -ArgumentList 0
    $done = Wait-Job $job -Timeout $timeoutSec
    $sw.Stop()
    if (-not $done) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        Say ("  " + $tag + ": NO RESPONSE within " + $timeoutSec + "s  (elapsed " + [math]::Round($sw.Elapsed.TotalSeconds,1) + "s)  => C12 reproduced")
        return -1
    }
    $out = Receive-Job $job; Remove-Job $job -Force -ErrorAction SilentlyContinue
    $dec = -1
    if ($out -match 'decode=([\d.]+)') { $dec = [double]$Matches[1] }
    Say ("  " + $tag + ": answered in " + [math]::Round($sw.Elapsed.TotalSeconds,1) + "s decode=" + $dec)
    return $dec
}
Say ("C12 IDLE TEST start; idle " + $IdleSec + "s then first request (hard timeout 30s)")
$pre = ProbeTimed 'warm-pre' 30
Say ("  (pre means the engine is serving normally before the idle)")
Say ("  idling " + $IdleSec + "s with no requests ...")
Start-Sleep -Seconds $IdleSec
$first = ProbeTimed 'first-after-idle' 30
$second = ProbeTimed 'second' 30
Say ("RESULT pre=" + $pre + " first_after_idle=" + $first + " second=" + $second)
if ($first -lt 0) { Say "VERDICT: C12 REPRODUCED (idle -> first request hung)" }
else { Say "VERDICT: no hang at this idle length (engine answered the first request)" }
