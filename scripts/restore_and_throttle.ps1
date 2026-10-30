param()
# restore_and_throttle.ps1 -- put the engine back on the production profile (pool 65536) and, while a
# pressure is applied, sample the driver-side signals (throttle reasons, pstate, clocks) for contrast.
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$led = ".temp\throttle_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
for ($w = 1; $w -le 12; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
Start-Sleep -Seconds 4
$env:NINFER_MAT_DEBUG = '1'
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step13_fourlayer_20261015.exe' -Tag valleywatch -Model 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer' -KvDtype 'rk2v4-e8' -Pool 65536 -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
$r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
Say ("engine restored to pool 65536, ready=" + $r)
function Snap($tag) {
    $q = 'clocks_throttle_reasons.active,clocks_throttle_reasons.sw_power_cap,clocks_throttle_reasons.hw_slowdown,pstate,clocks.sm,power.draw,utilization.gpu,memory.used'
    $v = (nvidia-smi --query-gpu=$q --format=csv,noheader) -join ' | '
    Say ("  " + $tag + ": " + $v)
}
$o = (python -X utf8 scripts\a2gate.py --arm thr_base --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
if ($o -match 'decode=([\d.]+)') { Say ("  baseline decode=" + $Matches[1]) }
Snap 'healthy'
Start-Process -FilePath 'tools\vram_hold.exe' -ArgumentList '1200','60' | Out-Null
Start-Sleep -Seconds 6
$o2 = (python -X utf8 scripts\a2gate.py --arm thr_press --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
if ($o2 -match 'decode=([\d.]+)') { Say ("  during-pressure decode=" + $Matches[1]) }
Snap 'during-pressure'
for ($i = 1; $i -le 3; $i++) { Start-Sleep -Seconds 8; Snap ("during-pressure+" + ($i*8) + "s") }
for ($w = 1; $w -le 40; $w++) { if (-not (Get-Process vram_hold -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 1 }
Start-Sleep -Seconds 5
$o3 = (python -X utf8 scripts\a2gate.py --arm thr_post --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
if ($o3 -match 'decode=([\d.]+)') { Say ("  post-release decode=" + $Matches[1]) }
Snap 'post-release'
Say "THROTTLE CHECK end"
