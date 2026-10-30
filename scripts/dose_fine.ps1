param()
# dose_fine.ps1 -- pin the trigger threshold (the headroom-relative prediction failed).
# Doses 200 / 400 / 600 MiB, two applies each, four probes during each apply.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\dosefine_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("df" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
$g = (nvidia-smi --query-gpu=memory.total,memory.used --format=csv,noheader,nounits) -split ','
$headroom = [int]$g[0] - [int]$g[1]
Say ("DOSE-FINE start; headroom = " + $headroom + " MiB")
foreach ($d in @(200, 400, 600)) {
    for ($c = 1; $c -le 2; $c++) {
        $base = Probe
        Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$d), '25' | Out-Null
        Start-Sleep -Seconds 4
        $during = @()
        foreach ($i in 1..4) { $during += (Probe) }
        for ($w = 1; $w -le 40; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
        $after = Probe
        $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
        Say ("dose=" + $d + " run" + $c + ": base=" + $base + " during=" + ($during -join '/') + " slow=" + $slow + "/4 after=" + $after)
    }
}
Say "DOSE-FINE end"
