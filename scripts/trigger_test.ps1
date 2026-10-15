param(
    [ValidateSet('launch','copy','host','vram')][string]$Kind = 'vram',
    [int]$HoldSec = 60,
    [int]$VramMiB = 600,
    [int]$Probes = 3
)
# trigger_test.ps1 -- active-trigger A/B/A with release probes after BOTH applies (TELE three gates):
#   gate 1: apply  -> valley   (median decode < 60)
#   gate 2: release-> healthy  (median decode > 120)
#   gate 3: apply  -> valley again
# Same engine, no restart. Every step is timestamped into a ledger.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\trigger_${Kind}_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("tg" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function ProbeN($tag, $n) {
    $vals = @()
    for ($i = 1; $i -le $n; $i++) { $d = Probe; $vals += $d; Say ("  " + $tag + " probe" + $i + " decode=" + $d) }
    $s = ($vals | Sort-Object)
    return [double]$s[[int]($s.Count / 2)]
}
function Apply() {
    if ($Kind -eq 'vram') { Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$VramMiB), ([string]$HoldSec) }
    else { Start-Process -WindowStyle Hidden -FilePath 'tools\submit_load.exe' -ArgumentList $Kind, ([string]$HoldSec) }
    Say ("  applied kind=" + $Kind + " hold=" + $HoldSec + "s")
}
function WaitRelease() {
    $name = if ($Kind -eq 'vram') { 'vram_hold' } else { 'submit_load' }
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process $name -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    Say "  released (loader process gone)"
}

Say ("TRIGGER TEST kind=" + $Kind + " hold=" + $HoldSec + "s vram=" + $VramMiB + "MiB probes=" + $Probes)
$b = ProbeN 'baseline' $Probes
Say ("  baseline median = " + $b)
if ($b -lt 60) { Say "  ABORT: engine already in the valley, gates cannot be evaluated"; exit 1 }
Apply; Start-Sleep -Seconds 6
$m1 = ProbeN 'apply1' $Probes
WaitRelease; Start-Sleep -Seconds 4
$m2 = ProbeN 'release1' $Probes
Apply; Start-Sleep -Seconds 6
$m3 = ProbeN 'apply2' $Probes
WaitRelease; Start-Sleep -Seconds 4
$m4 = ProbeN 'release2' $Probes

Say ("RESULT baseline=" + $b + " apply1=" + $m1 + " release1=" + $m2 + " apply2=" + $m3 + " release2=" + $m4)
$g1 = $m1 -lt 60; $g2 = $m2 -gt 120; $g3 = $m3 -lt 60; $g4 = $m4 -gt 120
Say ("GATES: apply1->valley=" + $g1 + " release1->healthy=" + $g2 + " apply2->valley=" + $g3 + " release2->healthy=" + $g4)
if (($g1 -or $g3) -and ($g2 -and $g4)) { Say "VERDICT: ACTIVE TRIGGER (apply reproduces the valley, release restores health)" }
elseif (-not ($g1 -or $g3)) { Say "VERDICT: NOT a trigger (no apply produced a sustained valley)" }
else { Say "VERDICT: PARTIAL (valley reproduced but release did not restore)" }
