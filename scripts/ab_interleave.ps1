param(
    [int]$Cycles = 3,
    [int]$HoldSec = 30,
    [int]$VramMiB = 600,
    [int]$Probes = 3
)
# ab_interleave.ps1 -- paired A/C comparison that cancels machine drift.
# Within ONE cycle: restart arm A (HP=1 RH=1) -> apply -> probe -> restart arm C (HP=1 RH=0) -> apply -> probe.
# The drift affects both arms inside the cycle, so the paired difference is the signal.
# Pre-registered: C's slow fraction should exceed A's in at least 2 of 3 cycles for the RH gate to count.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\interleave_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function Restart($hp, $rh) {
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 12; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 4
    $env:NINFER_HOST_PAGEABLE = $hp
    $env:NINFER_KV_REUSE_HOSTBACKED = $rh
    $env:NINFER_MAT_DEBUG = '1'
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step13_fourlayer_20261015.exe' -Tag valleywatch -Model 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer' -KvDtype 'rk2v4-e8' -Pool 65536 -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,work\data\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
    Say ("  ready=" + $r + " (HP=" + $hp + " RH=" + $rh + ")")
    return ($r -match 'READY')
}
function Probe() {
    $o = (python -X utf8 scripts\a2gate.py --arm ("il" + (Get-Random)) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    if ($o -match 'decode=([\d.]+)') { return [double]$Matches[1] }
    return -1
}
function ArmRun($name) {
    $vals = @()
    foreach ($i in 1..2) { $vals += (Probe) }           # pre
    Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList ([string]$VramMiB), ([string]$HoldSec)
    Start-Sleep -Seconds 5
    foreach ($i in 1..$Probes) { $vals += (Probe) }     # during
    for ($w = 1; $w -le ($HoldSec + 15); $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
    foreach ($i in 1..2) { $vals += (Probe) }           # after
    $during = $vals[2..(1 + $Probes)]
    $slow = @($during | Where-Object { $_ -ge 0 -and $_ -lt 60 }).Count
    $dmed = ($during | Sort-Object)[[int]($during.Count / 2)]
    Say ("  " + $name + ": all=" + ($vals -join '/') + " during_slow=" + $slow + "/" + $Probes + " during_median=" + $dmed)
    return @($slow, $dmed)
}

Say ("INTERLEAVE start cycles=" + $Cycles + " hold=" + $HoldSec + "s vram=" + $VramMiB + "MiB")
$cWins = 0
for ($c = 1; $c -le $Cycles; $c++) {
    Say ("=== cycle " + $c + " ===")
    $okA = Restart '1' '1'
    if (-not $okA) { Say "  arm A failed to start, skip cycle"; continue }
    $a = ArmRun 'A_hp1_rh1'
    $okC = Restart '1' '0'
    if (-not $okC) { Say "  arm C failed to start, skip cycle"; continue }
    $cc = ArmRun 'C_hp1_rh0'
    $delta = [double]$cc[0] - [double]$a[0]
    Say ("  paired delta slow(count, C-A) = " + $delta + " ; median " + $a[1] + " -> " + $cc[1])
    if ($delta -gt 0) { $cWins++ }
}
Say ("INTERLEAVE end: cycles where C > A = " + $cWins + "/" + $Cycles)
if ($cWins -ge 2) { Say "RESULT: RH is implicated (C worse than A in a majority of paired cycles)" }
else { Say "RESULT: RH not separated from drift (no consistent paired difference)" }
