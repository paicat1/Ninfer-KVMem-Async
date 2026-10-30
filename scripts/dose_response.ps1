param(
    [int]$Cycles = 3,
    [int]$HoldSec = 30
)
# dose_response.ps1 -- does the transient's depth scale with the VRAM squeeze?
# Doses: 200 / 600 / 1200 MiB. Same engine (no restart), same probe shape, pre-registered:
#   depth (min decode during apply) and slow fraction should increase monotonically with dose
#   if the mechanism is driver-side eviction of the engine's allocations.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\dose_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("dose" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
$doses = @(200, 600, 1200)
Say ("DOSE start cycles=" + $Cycles + " hold=" + $HoldSec + "s doses=" + ($doses -join '/') + " MiB")
foreach ($d in $doses) {
    $during = @(); $after = @(); $base = @()
    for ($c = 1; $c -le $Cycles; $c++) {
        $base += (Probe)
        Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$d), ([string]$HoldSec) | Out-Null
        Start-Sleep -Seconds 5
        foreach ($i in 1..3) { $during += (Probe) }
        for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
        foreach ($i in 1..2) { $after += (Probe) }
    }
    $ds = ($during | Sort-Object); $as = ($after | Sort-Object)
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    Say ("dose=" + $d + " MiB : baseline med=" + (($base | Sort-Object)[[int]($base.Count/2)]) + " | during min=" + $ds[0] + " med=" + $ds[[int]($ds.Count/2)] + " slow=" + $slow + "/" + $during.Count + " | after med=" + $as[[int]($as.Count/2)] + " min=" + $as[0])
    Say ("  during raw: " + ($during -join ' / '))
}
Say "DOSE end"
