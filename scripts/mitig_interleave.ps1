param([int]$Cycles = 2, [int]$HoldMiB = 1200, [int]$HoldSec = 60)
# mitig_interleave.ps1 -- pool effect on the on-demand valley, with the drift cancelled inside each cycle.
# Within ONE cycle: pool 65536 -> apply -> probe; pool 49152 -> apply -> probe; pool 32768 -> apply -> probe.
# Pre-registered: if the slow counts are ordered the same way in every cycle, the pool is a real factor;
# if the order flips between cycles, the earlier monotone trend was drift.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\mitig_il_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("mi" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function RunPool($pool) {
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 12; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 3
    $env:NINFER_MAT_DEBUG = '1'
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step13_fourlayer_20261015.exe' -Tag valleywatch -Model 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer' -KvDtype 'rk2v4-e8' -Pool $pool -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
    if ($r -notmatch 'READY') { Say ("  pool=" + $pool + " FAILED to start"); return @(-1, -1) }
    $pre = Probe
    Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
    Start-Sleep -Seconds 5
    $during = @(); foreach ($i in 1..5) { $during += (Probe) }
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    $post = Probe
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $ds = ($during | Sort-Object)
    Say ("  pool=" + $pool + " pre=" + $pre + " during=" + ($during -join '/') + " min=" + $ds[0] + " slow=" + $slow + "/5 post=" + $post)
    return @($slow, $ds[0])
}
Say ("MITIG-INTERLEAVE start cycles=" + $Cycles + " hold=" + $HoldMiB + "x" + $HoldSec + "s")
for ($c = 1; $c -le $Cycles; $c++) {
    Say ("=== cycle " + $c + " ===")
    foreach ($p in @(65536, 49152, 32768)) {
        $res = RunPool $p
        Say ("  cycle" + $c + " pool=" + $p + " -> slow=" + $res[0] + " min=" + $res[1])
    }
}
Say "MITIG-INTERLEAVE end"
