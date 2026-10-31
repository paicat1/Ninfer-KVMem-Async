# tick.ps1 -- the ONLY allowed wait primitive for AI-driven interactive runs (2026-10-31).
#
# WHY (user order, 2026-10-31): a single tool call must never block the user for more
# than 5 seconds. A long Start-Sleep inside a command hides "the system is stuck" behind
# "the system is running", and the user ends up sitting there with no observable progress.
# => The wait becomes (a) short, (b) observable, (c) interruptible.
#
# CONTRACT:
#   - hard cap: -Seconds may not exceed 5 (exit 2 on violation; the WAIT-BUDGET gate in
#     scripts\gates.ps1 also rejects any interactive script that sleeps longer).
#   - every tick re-reads the ledger/log file and prints its size/mtime (+ last matching
#     line when -Pattern is given), so a stuck run is visible within one tick.
#   - exit 0 on completion.
#
# USAGE:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tick.ps1 `
#       -Seconds 5 -File work\data\pg2_cctrl_ab_20261031_095918.txt -Pattern 'waitready'
param(
    [double]$Seconds = 5,
    [string]$File = '',
    [string]$Pattern = '',
    [int]$StepMs = 500
)
$ErrorActionPreference = 'Continue'
$cap = 5
if ($Seconds -gt $cap) {
    Write-Host ("WAIT-BUDGET VIOLATION: requested {0}s > cap {1}s (interactive waits must be <= {1}s)" -f $Seconds, $cap) -ForegroundColor Red
    exit 2
}
if ($StepMs -lt 100 -or $StepMs -gt 1000) { $StepMs = 500 }
$sw = [Diagnostics.Stopwatch]::StartNew()
$n = 0
$lastHit = ''
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    Start-Sleep -Milliseconds $StepMs
    $n++
    $remain = [math]::Max(0, $Seconds - $sw.Elapsed.TotalSeconds)
    $hit = ''
    if ($File -and (Test-Path -LiteralPath $File)) {
        $fi = Get-Item -LiteralPath $File
        if ($Pattern) {
            try {
                $m = Select-String -LiteralPath $File -Pattern $Pattern -ErrorAction SilentlyContinue | Select-Object -Last 1
                if ($m) {
                    $ln = $m.Line
                    if ($ln.Length -gt 160) { $ln = $ln.Substring(0, 160) }
                    $hit = '| ' + $ln.Trim()
                }
            } catch { }
        }
        Write-Host ("TICK {0}/{1}s remain={2}s bytes={3} mtime={4} {5}" -f $n, $Seconds, [math]::Round($remain,1), $fi.Length, $fi.LastWriteTime.ToString('HH:mm:ss'), $hit)
    } else {
        Write-Host ("TICK {0}/{1}s remain={2}s (no ledger)" -f $n, $Seconds, [math]::Round($remain,1))
    }
    $lastHit = $hit
}
Write-Host ("TICK DONE total={0}s ticks={1} last={2}" -f [math]::Round($sw.Elapsed.TotalSeconds,2), $n, $lastHit)
exit 0