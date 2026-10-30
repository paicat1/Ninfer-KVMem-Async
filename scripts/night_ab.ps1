param(
    [int]$Cycles = 5,
    [int]$HoldSec = 30,
    [int]$VramMiB = 600
)
# night_ab.ps1 -- four arms of the depth-detector protocol, each with its own engine restart.
# Arms differ only in the host-page profile; the trigger (vram hold) and the probe shape are fixed.
# Fully active: every arm applies and releases, nothing waits for the machine window.
# Hard stop: after the four arms it writes SUMMARY.txt and exits.
Set-Location J:\ninfer-kvmem
$sw = [Diagnostics.Stopwatch]::StartNew()
$summary = ".temp\night_ab_summary_" + (Get-Date -Format 'HHmmss') + ".txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $summary -Encoding UTF8 -Value $line; Write-Host $line }

$arms = @(
    @{ name = 'A_hp1_rh1'; hp = '1'; rh = '1' },
    @{ name = 'B_hp0_rh1'; hp = '0'; rh = '1' },
    @{ name = 'C_hp1_rh0'; hp = '1'; rh = '0' },
    @{ name = 'D_hp0_rh0'; hp = '0'; rh = '0' }
)
Say ("NIGHT_AB start cycles=" + $Cycles + " hold=" + $HoldSec + "s vram=" + $VramMiB + "MiB arms=" + $arms.Count)

foreach ($a in $arms) {
    Say ("=== arm " + $a.name + " (HOST_PAGEABLE=" + $a.hp + " REUSE_HOSTBACKED=" + $a.rh + ") ===")
    # restart the engine with this arm's profile
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 12; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 4
    $env:NINFER_HOST_PAGEABLE = $a.hp
    $env:NINFER_KV_REUSE_HOSTBACKED = $a.rh
    $env:NINFER_MAT_DEBUG = '1'
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\ninfer-serve-RC1.exe' -Tag valleywatch -Model 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer' -KvDtype 'rk2v4-e8' -Pool 65536 -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
    Say ("  ready=" + $r)
    if ($r -notmatch 'READY') { Say "  arm aborted (engine did not come up)"; continue }
    # run the arm protocol
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\trigger_arm.ps1 -Arm $a.name -Cycles $Cycles -HoldSec $HoldSec -VramMiB $VramMiB
    $f = Get-ChildItem '.temp' -File | Where-Object { $_.Name -like ("arm_" + $a.name + "_*") } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($f) {
        Say ("  arm ledger: " + $f.Name)
        Get-Content $f.FullName -Encoding UTF8 | Where-Object { $_ -match 'SUMMARY|baseline:|during_apply:|after_release:' } | ForEach-Object { Say ("    " + $_) }
    }
}
Say ("NIGHT_AB end, elapsed " + [math]::Round($sw.Elapsed.TotalMinutes, 1) + " min")
