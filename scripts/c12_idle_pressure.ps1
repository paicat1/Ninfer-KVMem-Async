param([int]$IdleSec = 1500, [int]$HoldMiB = 1200)
# c12_idle_pressure.ps1 -- 2x2 design for C12: is the hang "idle alone" or "idle plus vram pressure"?
# Conditions, each run once per script invocation (call twice for the other cell):
#   A: idle only                      -> first request
#   B: idle with a sustained pressure -> first request   (set -HoldMiB 0 to disable the pressure)
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\c12p_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function ProbeTimed($tag, $timeoutSec) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $job = Start-Job -ScriptBlock {
        $o = (python -X utf8 J:\ninfer-kvmem\scripts\a2gate.py --arm c12p --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
        return $o
    }
    $done = Wait-Job $job -Timeout $timeoutSec
    $sw.Stop()
    if (-not $done) {
        Stop-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -Force -ErrorAction SilentlyContinue
        Say ("  " + $tag + ": NO RESPONSE within " + $timeoutSec + "s (elapsed " + [math]::Round($sw.Elapsed.TotalSeconds,1) + "s) => HANG")
        return -1
    }
    $out = Receive-Job $job; Remove-Job $job -Force -ErrorAction SilentlyContinue
    $dec = -1
    if ($out -match 'decode=([\d.]+)') { $dec = [double]$Matches[1] }
    Say ("  " + $tag + ": answered in " + [math]::Round($sw.Elapsed.TotalSeconds,1) + "s decode=" + $dec)
    return $dec
}
$cond = if ($HoldMiB -gt 0) { "idle+pressure(" + $HoldMiB + " MiB)" } else { "idle-only" }
Say ("C12 2x2 cell: " + $cond + ", idle " + $IdleSec + "s, first-request timeout 30s")
$pre = ProbeTimed 'pre' 30
Say ("  pre decode = " + $pre)
if ($HoldMiB -gt 0) {
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]($IdleSec + 60)) | Out-Null
    Say ("  pressure applied for the whole idle window")
}
Start-Sleep -Seconds $IdleSec
$first = ProbeTimed 'first-after-idle' 30
$second = ProbeTimed 'second' 30
Say ("RESULT cell=" + $cond + " pre=" + $pre + " first=" + $first + " second=" + $second)
if ($first -lt 0) { Say "VERDICT: HANG reproduced in this cell" } else { Say "VERDICT: no hang in this cell" }
