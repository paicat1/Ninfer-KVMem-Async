param([int]$HoldMiB = 1200, [int]$HoldSec = 240, [int]$EverySec = 8)
# confirm_sustained.ps1 -- the three gates with a SUSTAINED hold, twice.
#   gate 1: sustained hold -> sustained deep slow state
#   gate 2: release        -> healthy
#   gate 3: hold again     -> slow again
# Also dumps the step profile slow lines captured during each hold (submit vs wall).
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\sustain_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("su" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function PreRelease() { for ($w = 1; $w -le 20; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 } }
Say ("SUSTAIN CONFIRM start: " + $HoldMiB + " MiB x " + $HoldSec + "s, probe every ~" + $EverySec + "s, two rounds")
for ($round = 1; $round -le 2; $round++) {
    $pre = @(); foreach ($i in 1..2) { $pre += (Probe) }
    Say ("round" + $round + " pre: " + ($pre -join '/'))
    $mark = (Get-Content 'logs\test_valleywatch.log').Count
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
    Start-Sleep -Seconds 5
    $during = @(); $t0 = Get-Date
    while (((Get-Date) - $t0).TotalSeconds -lt $HoldSec) { $during += (Probe); Start-Sleep -Seconds $EverySec }
    PreRelease
    $post = @(); foreach ($i in 1..3) { $post += (Probe) }
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $ds = ($during | Sort-Object)
    Say ("round" + $round + " during n=" + $during.Count + " min=" + $ds[0] + " med=" + $ds[[int]($ds.Count/2)] + " slow=" + $slow + "/" + $during.Count + " (" + [math]::Round(100.0*$slow/$during.Count,0) + "%)")
    Say ("round" + $round + " during raw: " + ($during -join ' / '))
    Say ("round" + $round + " post: " + ($post -join '/'))
    Say ("round" + $round + " slow-profile lines during hold:")
    Get-Content 'logs\test_valleywatch.log' -Encoding UTF8 | Select-Object -Skip $mark | Where-Object { $_ -match 'step profile slow' } | Select-Object -First 3 | ForEach-Object { Say ('    ' + $_.Trim()) }
}
Say "SUSTAIN CONFIRM end"
