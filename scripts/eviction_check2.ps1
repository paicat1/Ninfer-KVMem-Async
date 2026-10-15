param([int]$HoldMiB = 1200, [int]$HoldSec = 35, [int]$Runs = 2)
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\evict2_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Used() { return [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits) -replace '\s','') }
Say ("EVICTION CHECK 2: " + $Runs + " runs of " + $HoldMiB + " MiB x " + $HoldSec + "s")
for ($i = 1; $i -le $Runs; $i++) {
    $b1 = Used; Start-Sleep -Seconds 3; $b2 = Used
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
    Start-Sleep -Seconds 7
    $d1 = Used; Start-Sleep -Seconds 7; $d2 = Used
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    Start-Sleep -Seconds 6
    $a1 = Used; Start-Sleep -Seconds 5; $a2 = Used
    Say ("run" + $i + ": before=" + $b1 + "/" + $b2 + " during=" + $d1 + "/" + $d2 + " after=" + $a1 + "/" + $a2 + "  (during-before=" + ($d1 - $b2) + ", after-before=" + ($a1 - $b2) + ")")
}
Say "EVICTION CHECK 2 end"
