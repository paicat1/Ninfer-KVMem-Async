param([int]$HoldMiB = 1200, [int]$HoldSec = 40)
# eviction_check.ps1 -- does the DRIVER evict the engine's own vram when another process takes vram?
# If the engine's per-process local usage drops during the pressure and returns after, eviction is shown.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\evict_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Snap($tag) {
    $apps = (nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader) -join ' ; '
    $g = (nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits) -join '/'
    Say ("  " + $tag + " | gpu=" + $g + " MiB | apps: " + $apps)
}
$eng = (Get-Process ninfer-serve -ErrorAction SilentlyContinue | Select-Object -First 1).Id
Say ("EVICTION CHECK: engine pid=" + $eng + ", pressure=" + $HoldMiB + " MiB x " + $HoldSec + "s")
Snap 'before'
Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
Start-Sleep -Seconds 6
Snap 'during'
Start-Sleep -Seconds 8
Snap 'during+8s'
for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
Start-Sleep -Seconds 6
Snap 'after'
Say "EVICTION CHECK end"
