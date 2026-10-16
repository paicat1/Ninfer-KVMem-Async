param(
    [int]$HoldMiB = 1200,
    [int]$HoldSec = 240,
    [int]$Port = 8094
)
# valley_minrepro.ps1 -- one-command minimal reproduction of the on-demand valley (~2 minutes).
# Steps: baseline probe -> hold VRAM from a second process -> probe during hold -> release -> probe again.
# Requires: engine serving on $Port; tools\vram_hold.exe; scripts\a2gate.py
Set-Location (Split-Path $PSScriptRoot -Parent)
$hold = "tools\vram_hold.exe"
$gate = "scripts\a2gate.py"
foreach ($f in @($hold, $gate)) {
    if (-not (Test-Path $f)) { Write-Output ("MISSING: " + $f + "  (publish/build it first)"); exit 2 }
}
function Probe($tag) {
    $o = (python -X utf8 $gate --arm $tag --port $Port --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    $d = -1
    if ($o -match 'decode=([\d.]+)') { $d = [double]$Matches[1] }
    Write-Output ("  " + $tag.PadRight(10) + " decode=" + $d)
    return $d
}
function GpuSnap {
    $s = (nvidia-smi --query-gpu=utilization.gpu,power.draw,memory.used --format=csv,noheader,nounits) -replace '\s', ''
    Write-Output ("  gpu=" + $s)
}
Write-Output ("== valley minimal reproduction: hold " + $HoldMiB + " MiB for " + $HoldSec + "s ==")
Write-Output "[1/4] baseline"
$b = @(); $b += Probe "base1"; $b += Probe "base2"; GpuSnap
Write-Output ("[2/4] holding " + $HoldMiB + " MiB from a second process")
$p = Start-Process -PassThru -WindowStyle Hidden -FilePath $hold -ArgumentList ([string]$HoldMiB), ([string]$HoldSec)
Start-Sleep -Seconds 8
Write-Output "[3/4] probing DURING the hold"
$d = @(); $d += Probe "hold1"; $d += Probe "hold2"; GpuSnap
Write-Output "[4/4] releasing and probing again"
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
Start-Sleep -Seconds 10
$a = @(); $a += Probe "after1"; $a += Probe "after2"; GpuSnap
$bm = ($b | Where-Object { $_ -ge 0 } | Measure-Object -Average).Average
$dm = ($d | Where-Object { $_ -ge 0 } | Measure-Object -Average).Average
$am = ($a | Where-Object { $_ -ge 0 } | Measure-Object -Average).Average
Write-Output ""
Write-Output "== VERDICT =="
Write-Output ("  baseline avg = " + [math]::Round($bm,1) + "  |  during avg = " + [math]::Round($dm,1) + "  |  after avg = " + [math]::Round($am,1))
$slow = ($dm -ge 0) -and ($dm -lt 60)
$rec = ($am -ge 0) -and ($am -gt 120)
Write-Output ("  during is valley-grade : " + $slow + "   (expect decode 3.6-14)")
Write-Output ("  release restores health : " + $rec + "   (expect 163-168)")
Write-Output ("  => " + $(if ($slow -and $rec) { "REPRODUCED: the on-demand valley matches the published criteria." } else { "NOT REPRODUCED here: check free VRAM (threshold is absolute, >=400 MiB of added demand) and engine health." }))
