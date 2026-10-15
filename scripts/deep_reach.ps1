param([int]$HoldMiB = 2400, [int]$HoldSec = 300, [int]$EverySec = 15)
# deep_reach.ps1 -- can the on-demand state reach the natural DEEP valley grade (verify 1.5-2.5 s)?
# Push the dose up and hold it: 2400 MiB for 5 minutes, probing throughout, and record the engine's
# own verify stamps (the natural deep valley was 1539-2532 ms; the 30 s / 1200 MiB setup only reached ~650 ms).
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\deepreach_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("dr" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function MaxVerify() {
    $hits = Select-String -Path 'logs\test_valleywatch.log' -Pattern 'target-split.*verify=([\d.]+)' -Encoding UTF8 | Select-Object -Last 40
    $mx = 0.0
    foreach ($h in $hits) { if ($h.Line -match 'verify=([\d.]+)') { $v = [double]$Matches[1]; if ($v -gt $mx) { $mx = $v } } }
    return $mx
}
Say ("DEEP REACH start: " + $HoldMiB + " MiB x " + $HoldSec + "s, probe every ~" + $EverySec + "s")
$pre = @(); foreach ($i in 1..2) { $pre += (Probe) }
Say ("  pre: " + ($pre -join '/') + " | maxVerify(recent)=" + (MaxVerify))
Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
Start-Sleep -Seconds 6
$during = @(); $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt $HoldSec) { $during += (Probe); Start-Sleep -Seconds $EverySec }
$mv = MaxVerify
for ($w = 1; $w -le 25; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
Start-Sleep -Seconds 5
$post = @(); foreach ($i in 1..2) { $post += (Probe) }
$slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
$ds = ($during | Sort-Object)
Say ("  during n=" + $during.Count + " min=" + $ds[0] + " med=" + $ds[[int]($ds.Count/2)] + " slow=" + $slow + " | maxVerify during hold = " + $mv + " ms")
Say ("  post: " + ($post -join '/'))
if ($mv -ge 1000) { Say "VERDICT: the on-demand state reaches the DEEP grade (>=1000 ms)" }
else { Say "VERDICT: on-demand stays below the deep grade (max " + $mv + " ms)" }
Say "DEEP REACH end"
