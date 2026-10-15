param([int]$HoldMiB = 1200, [int]$HoldSec = 40)
# pretrim_immunity.ps1 -- after a pressure episode the engine trims ~1.1 GiB and keeps it trimmed.
# Does that make it immune to the NEXT episode? If yes, a dummy pressure at start-up is a mitigation.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\pretrim_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("pt" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function MemUsed() {
    $v = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    return [int]($v -replace '\s', '')
}
function Episode($tag, $n) {
    $pre = Probe
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$HoldMiB), ([string]$HoldSec) | Out-Null
    Start-Sleep -Seconds 5
    $during = @()
    foreach ($i in 1..$n) { $during += (Probe) }
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    Start-Sleep -Seconds 5
    $post = Probe
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $ds = ($during | Sort-Object)
    Say ("  " + $tag + " pre=" + $pre + " during=" + ($during -join '/') + " min=" + $ds[0] + " slow=" + $slow + "/" + $during.Count + " post=" + $post)
    return $slow
}
$m0 = MemUsed
Say ("PRE-TRIM IMMUNITY TEST: mem=" + $m0 + " MiB")
Say "-- episode 1 (should trigger the engine's own trim) --"
$s1 = Episode 'ep1' 3
$m1 = MemUsed
Say ("  mem after ep1 = " + $m1 + " MiB (was " + $m0 + ", delta " + ($m1 - $m0) + ")")
Start-Sleep -Seconds 10
Say "-- episode 2 (the immunity question) --"
$s2 = Episode 'ep2' 6
$m2 = MemUsed
Say ("  mem after ep2 = " + $m2 + " MiB")
Say ("RESULT ep1 slow=" + $s1 + " ep2 slow=" + $s2)
if ($s2 -eq 0) { Say "VERDICT: IMMUNE after the first episode (pre-trim could be a mitigation)" }
else { Say "VERDICT: not immune (the trim does not protect)" }
