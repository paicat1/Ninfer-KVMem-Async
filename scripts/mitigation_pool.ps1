param([int]$HoldMiB = 1200, [int]$HoldSec = 90)
# mitigation_pool.ps1 -- does leaving more vram headroom reduce the on-demand valley?
# Arms: pool 65536 (current, ~0.6 GiB headroom) / 49152 / 32768. Same apply, same probes.
# Pre-registered: if the during-decode rises (less slow) with the smaller pool, footprint headroom is
# a mitigation knob; if all arms are equally slow, the footprint does not matter.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\mitig_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("mg" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
Say ("MITIGATION start hold=" + $HoldMiB + " MiB x " + $HoldSec + "s")
foreach ($pool in @(65536, 49152, 32768)) {
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 12; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 4
    $env:NINFER_MAT_DEBUG = '1'
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step13_fourlayer_20261015.exe' -Tag valleywatch -Model 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer' -KvDtype 'rk2v4-e8' -Pool $pool -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
    $g = (nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits) -split ','
    $headroom = [int]$g[0] - [int]$g[1]
    Say ("pool=" + $pool + " ready=" + $r + " headroom=" + $headroom + " MiB")
    if ($r -notmatch 'READY') { continue }
    $pre = @(); foreach ($i in 1..2) { $pre += (Probe) }
    Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
    Start-Sleep -Seconds 5
    $during = @(); foreach ($i in 1..6) { $during += (Probe) }
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    $post = @(); foreach ($i in 1..3) { $post += (Probe) }
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $ds = ($during | Sort-Object)
    Say ("pool=" + $pool + " pre=" + ($pre -join '/') + " during=" + ($during -join '/') + " min=" + $ds[0] + " med=" + $ds[[int]($ds.Count/2)] + " slow=" + $slow + "/" + $during.Count + " post=" + ($post -join '/'))
}
Say "MITIGATION end"
