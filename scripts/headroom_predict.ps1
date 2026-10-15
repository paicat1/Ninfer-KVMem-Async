param()
# headroom_predict.ps1 -- falsifiable prediction of the headroom-threshold model.
# Current headroom was read as ~918 MiB (15385 used of 16303). Model says:
#   600 MiB fits in the headroom  -> NO slow probes
#   1200 MiB exceeds it           -> slow probe(s) appear
# Each dose is applied for 30 s and probed 4 times (plus 2 after) to keep it short.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\headroom_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("hr" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
$free = (nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits) -split ','
$headroom = [int]$free[0] - [int]$free[1]
Say ("HEADROOM TEST start; measured headroom = " + $headroom + " MiB (total " + $free[0] + " used " + $free[1] + ")")
foreach ($d in @(600, 1200)) {
    $during = @(); $after = @()
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$d), '30' | Out-Null
    Start-Sleep -Seconds 5
    foreach ($i in 1..4) { $during += (Probe) }
    for ($w = 1; $w -le 45; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    foreach ($i in 1..2) { $after += (Probe) }
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $ds = ($during | Sort-Object)
    Say ("dose=" + $d + " MiB (vs headroom " + $headroom + "): during=" + ($during -join '/') + " min=" + $ds[0] + " slow=" + $slow + "/" + $during.Count + " | after=" + ($after -join '/'))
}
Say "HEADROOM TEST end"
