param(
    [int]$HoldMiB = 1200,
    [int]$HoldSec = 240,
    [int]$Port = 8094,
    [int]$SettleSec = 20
)
# valley_minrepro.ps1 -- one-command minimal reproduction of the on-demand valley (~3-4 minutes).
#
# Steps: baseline (2 probes) -> hold VRAM from a second process -> probes during the hold
#        -> release -> settle -> probes again (3, to read the trend).
# Requires: engine serving on $Port; tools\vram_hold.exe; scripts\a2gate.py
#
# Notes from the self-tests (2026-10-16 23:57 / 00:02, both 1200 MiB x 240 s):
#   * the hold reached valley and deep grade (during average 2.2 in the first test);
#   * after release the engine climbs back over roughly half a minute
#     (observed 36.5 -> 165 -> 161.9 at +20/+35/+50 s), so a single probe right after
#     release can read "still slow" while recovery is under way -- hence the settle window
#     and the three-probe trend below;
#   * if the baseline itself is below 120 tok/s the machine was already slow before the hold,
#     and the during-reading cannot be attributed to the hold alone.
Set-Location (Split-Path $PSScriptRoot -Parent)
$hold = "tools\vram_hold.exe"
$gate = "scripts\a2gate.py"
foreach ($f in @($hold, $gate)) {
    if (-not (Test-Path $f)) { Write-Output ("MISSING: " + $f + "  (publish/build it first)"); exit 2 }
}
# Probe returns ONLY the number; display is done by the caller (keeps the pipeline clean).
function Probe($tag) {
    $o = (python -X utf8 $gate --arm $tag --port $Port --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    $d = -1
    if ($o -match 'decode=([\d.]+)') { $d = [double]$Matches[1] }
    return $d
}
function Show($tag, $v) { Write-Output ("  " + $tag.PadRight(10) + " decode=" + $v) }
function GpuSnap {
    $s = (nvidia-smi --query-gpu=utilization.gpu,power.draw,memory.used --format=csv,noheader,nounits) -replace '\s', ''
    Write-Output ("  gpu(util,pwr,mem)=" + $s)
}
function Avg($a) {
    $v = @($a | Where-Object { $_ -ge 0 })
    if ($v.Count -eq 0) { return -1 }
    return ($v | Measure-Object -Average).Average
}
Write-Output ("== valley minimal reproduction: hold " + $HoldMiB + " MiB for " + $HoldSec + "s ==")
Write-Output "[1/5] baseline"
$b = @()
$v = Probe "base1"; Show "base1" $v; $b += $v
$v = Probe "base2"; Show "base2" $v; $b += $v
GpuSnap
$bm = Avg $b
if ($bm -lt 120) {
    Write-Output ("  WARNING: baseline avg " + [math]::Round($bm,1) + " is not healthy -- the machine is already slow;")
    Write-Output ("           the during-reading below cannot be attributed to this hold alone.")
}
Write-Output ("[2/5] holding " + $HoldMiB + " MiB from a second process")
$p = Start-Process -PassThru -WindowStyle Normal -FilePath $hold -ArgumentList ([string]$HoldMiB), ([string]$HoldSec)
Start-Sleep -Seconds 8
Write-Output "[3/5] probing DURING the hold"
$d = @()
$v = Probe "hold1"; Show "hold1" $v; $d += $v
$v = Probe "hold2"; Show "hold2" $v; $d += $v
GpuSnap
Write-Output ("[4/5] releasing, settling " + $SettleSec + " s")
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds $SettleSec
Write-Output "[5/5] probing AFTER release (trend of 3)"
$a = @()
$v = Probe "after1"; Show "after1" $v; $a += $v
$v = Probe "after2"; Show "after2" $v; $a += $v
$v = Probe "after3"; Show "after3" $v; $a += $v
GpuSnap
$dm = Avg $d
$last = $a[-1]
$shown = @($a | ForEach-Object { [math]::Round([double]$_, 1) })
Write-Output ""
Write-Output "== VERDICT =="
Write-Output ("  baseline avg = " + [math]::Round($bm,1) + "  |  during avg = " + [math]::Round($dm,1) + "  |  after: " + ($shown -join " / "))
$slow = ($dm -ge 0) -and ($dm -lt 60)
$rec = ($last -ge 0) -and ($last -gt 120)
Write-Output ("  during is valley-grade : " + $slow + "   (expect 3.6-14; sustained holds can reach ~1.5-2)")
Write-Output ("  release restores health : " + $rec + "   (last probe > 120; expect 160-170)")
if ($slow -and $rec) {
    Write-Output "  => REPRODUCED: the on-demand valley matches the published criteria."
} elseif ($slow -and -not $rec) {
    Write-Output "  => PARTIAL: valley reproduced, recovery slower than this window; re-probe after ~1 minute."
} else {
    Write-Output "  => NOT REPRODUCED: check engine health and free VRAM (threshold is absolute, >=400 MiB of added demand)."
}
Write-Output "  reference: docs/Minimal-Reproduction-Valley-On-Demand-20261016.md"
