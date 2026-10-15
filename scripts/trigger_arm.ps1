param(
    [string]$Arm = 'A',
    [int]$Cycles = 5,
    [int]$HoldSec = 30,
    [int]$VramMiB = 600,
    [int]$Probes = 3,
    [int]$PostProbes = 2
)
# trigger_arm.ps1 -- one arm of the depth-detector protocol against the CURRENT engine.
# Per cycle: 1 baseline probe -> apply (vram hold) -> ProbeN during -> release -> PostProbes after.
# Writes every decode value plus a summary (slow fraction, min, median) into one ledger.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\arm_${Arm}_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("arm" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function SlowStamps($n) {
    $s = Select-String -Path 'logs\test_valleywatch.log' -Pattern 'layer-ops mtp: L3' -Encoding UTF8 | Select-Object -Last $n
    return (($s | ForEach-Object { $_.Line.Trim() }) -join ' ;; ')
}
Say ("ARM " + $Arm + " cycles=" + $Cycles + " hold=" + $HoldSec + "s vram=" + $VramMiB + "MiB")
$during = @(); $after = @(); $base = @()
for ($c = 1; $c -le $Cycles; $c++) {
    $b = Probe; $base += $b; Say ("  cycle" + $c + " baseline=" + $b)
    Start-Process -WindowStyle Hidden -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$VramMiB), ([string]$HoldSec)
    Start-Sleep -Seconds 5
    for ($i = 1; $i -le $Probes; $i++) { $d = Probe; $during += $d; Say ("    during" + $i + "=" + $d) }
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    Say "    released"
    for ($i = 1; $i -le $PostProbes; $i++) { $d = Probe; $after += $d; Say ("    after" + $i + "=" + $d) }
    Say ("    stamps(L3 last3): " + (SlowStamps 3))
}
function Stat($arr, $name) {
    if ($arr.Count -eq 0) { Say ("  " + $name + ": none"); return }
    $s = ($arr | Sort-Object)
    $slow = @($arr | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    Say ("  " + $name + ": n=" + $arr.Count + " min=" + $s[0] + " median=" + $s[[int]($s.Count / 2)] + " slow(<60)=" + $slow + "/" + $arr.Count + " (" + [math]::Round(100.0 * $slow / $arr.Count, 1) + "%)")
}
Say "SUMMARY"
Stat $base 'baseline'
Stat $during 'during_apply'
Stat $after 'after_release'
Say ("LEDGER " + $led)
