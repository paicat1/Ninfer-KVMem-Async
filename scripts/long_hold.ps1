param(
    [int]$HoldMiB = 1200,
    [int]$HoldSec = 300,
    [int]$EverySec = 10
)
# long_hold.ps1 -- is the effect sustainable? Hold a large allocation for minutes and probe throughout.
# If the slow-probe rate stays ~1 per apply, the effect is a one-shot per demand; if it rises toward
# continuous, we have an on-demand sustained state (which is what the valley looks like).
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\longhold_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("lh" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
Say ("LONG-HOLD start: " + $HoldMiB + " MiB for " + $HoldSec + "s, probe every ~" + $EverySec + "s")
$pre = @(); foreach ($i in 1..3) { $pre += (Probe) }
Say ("  pre: " + ($pre -join '/'))
Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
Start-Sleep -Seconds 5
$during = @()
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $HoldSec) {
    $during += (Probe)
    Start-Sleep -Seconds $EverySec
}
$post = @(); foreach ($i in 1..3) { $post += (Probe) }
for ($w = 1; $w -le 20; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
$slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
$ds = ($during | Sort-Object)
Say ("  during n=" + $during.Count + " min=" + $ds[0] + " med=" + $ds[[int]($ds.Count/2)] + " slow=" + $slow + " (" + [math]::Round(100.0*$slow/$during.Count,1) + "%)")
Say ("  during raw: " + ($during -join ' / '))
Say ("  post: " + ($post -join '/'))
Say "LONG-HOLD end"
