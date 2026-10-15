param([int]$Minutes = 45)
# valley_catch_test.ps1 -- catch the valley, measure external metrics, then try to clear it with load.
# Bounded: default 45 minutes, at most 2 episodes.
# Valley criterion: probe decode < 60 on the 45KB/200-token shape (healthy band is 100-175).
# NOTE: the verify stamp is NOT used as a criterion -- with verbose off, healthy rounds print nothing,
#       so the last target-split line can be stale. decode is fresh by construction.
Set-Location J:\ninfer-kvmem
$stamp = Get-Date -Format 'yyyyMMdd_HHmm'
$led = ".temp\catchtest_$stamp.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("ct" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match '([\d.]+)s\s+decode=([\d.]+)') { return @([double]$Matches[2], [double]$Matches[1]) }
    return @(-1, -1)
}
function LastStamps() {
    return (Select-String -Path 'logs\test_valleywatch.log' -Pattern 'target-split|layer-ops mtp: L3' -Encoding UTF8 | Select-Object -Last 2 | ForEach-Object { $_.Line.Trim() }) -join ' ;; '
}
function Bench() {
    for ($i = 1; $i -le 2; $i++) { $r = (& 'tools\concur_bench.exe' 100 2>&1) -join ''; Say ("  bench" + $i + " " + $r) }
}

Say ("CATCHTEST start, budget " + $Minutes + " min; criterion = decode < 60 (fresh probe); engine should be up")
$deadline = (Get-Date).AddMinutes($Minutes)
$episodes = 0
while ((Get-Date) -lt $deadline -and $episodes -lt 2) {
    $p = Probe
    $dec = $p[0]; $wall = $p[1]
    if ($dec -ge 60 -or $dec -lt 0) {
        Say ("ok decode=" + $dec + " wall=" + $wall + "s")
        Start-Sleep -Seconds 25
        continue
    }
    $episodes++
    Say ("VALLEY#" + $episodes + " decode=" + $dec + " wall=" + $wall + "s")
    Say ("  stamps: " + (LastStamps))
    Say "  [1] external metrics during the valley:"
    Bench
    Say "  [2] applying heavy load (S12 shape, 3 rounds x 3) ..."
    python -X utf8 scripts\a2gate.py --arm ("ctload" + $episodes) --port 8094 --runs 3 --rounds 3 --filler-kb 220 --max-tokens 600 2>&1 | Out-Null
    $p2 = Probe
    Say ("  [3] after load: decode=" + $p2[0] + " wall=" + $p2[1] + "s")
    if ($p2[0] -gt 120) { Say "  VERDICT: load cleared the valley" }
    elseif ($p2[0] -lt 60) { Say "  VERDICT: still in the valley after load" }
    else { Say "  VERDICT: intermediate after load" }
    Say "  [4] external metrics after load:"
    Bench
    Start-Sleep -Seconds 20
}
Say ("CATCHTEST end, episodes=" + $episodes)
