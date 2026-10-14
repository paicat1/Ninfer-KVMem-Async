param(
    [int]$IntervalSec = 600,
    [double]$Hours = 8,
    [int]$FillerKb = 45,
    [int]$MaxTokens = 200,
    [int]$SlowSec = 40
)
# valley_watch.ps1 -- unattended valley sentinel (2026-10-14).
#   Keeps an INSTRUMENTED engine up (step3b, NINFER_STEP_PROFILE=1, reqlog), probes every IntervalSec
#   with one short greedy round; on a slow round (>= SlowSec) it starts gpu sampler + timestamped dmon
#   and keeps them for 300 s. Everything appends to .temp\state_journal.txt.
# Stop with: Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# Engine stop: scripts\engine_ctl.ps1 -Action stop
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$deadline = (Get-Date).AddHours($Hours)

function J([string]$msg) {
    Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $msg)
}

# ★平台=SWIFT-1.5 IQ3_S + rk8v4 + 池 65,536 + Graph 192（2026-10-14 用户令切换；
#   Q2LYNN 集已冻结于 baselines/q2lynn，回切只需改本行 -Model/-KvDtype/-Graph）
function Start-Engine {
    $r0 = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 5) -join ' '
    if ($r0 -match 'READY') { return $true }
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step6_stamp_20261014.exe' -Tag valleywatch -Depth 2 -Port 8094 -Graph 192 -Pool 65536 -KvDtype rk8v4 -Model 'swift15_iq3s_mtp.ninfer' -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 300) -join ' '
    return ($r -match 'READY')
}

J ('Ninfer-KVMem-Async守望者 start (interval=' + $IntervalSec + 's hours=' + $Hours + ' filler=' + $FillerKb + 'KB)')
$slowStreak = 0
while ((Get-Date) -lt $deadline) {
    if (-not (Start-Engine)) { J 'engine start FAILED; retry in 60s'; Start-Sleep -Seconds 60; continue }
    $gpu = (nvidia-smi --query-gpu=utilization.gpu,clocks.current.sm,memory.used --format=csv,noheader) -join ' '
    $stamp = Get-Date -Format 'HHmmss'
    Start-Process -WindowStyle Hidden -FilePath cmd -ArgumentList '/c', ('nvidia-smi dmon -o T -s pucmt -c 90 > J:\ninfer-kvmem\.temp\watch_dmon_' + $stamp + '.txt 2>&1')
    Start-Process -WindowStyle Hidden -FilePath python -ArgumentList '-X', 'utf8', 'scripts\gpu_sampler.py', '--seconds', '120', '--interval', '1'
    $out = python -X utf8 scripts\a2gate.py --arm watch --port 8094 --runs 1 --rounds 1 --filler-kb $FillerKb --max-tokens $MaxTokens 2>&1
    $line = ($out | Where-Object { $_ -match 'run 1 round 1' } | Select-Object -First 1)
    $sec = 0.0
    if ($line -and $line -match '([\d.]+)s') { $sec = [double]$Matches[1] }
    # 判据 v3（2026-10-14）：墙钟会被冷/暖填互换掩盖（冷填 5.4s+解码 174 与 暖填 0.4s+解码 28 同报 ~7s）。
    # 改用解码速率为主判据；decode<80 = 降级。基线：Q2LYNN 快带 ~124–230 / 慢 ~25–28；# Swift-IQ3_S+rk8v4 深 60K 实测 143.7（2026-10-14），阈值 80 通用。
    $dec = 0.0; $cached = 0; $pms = 0.0
    $parsed = python -X utf8 -c "import json;d=json.load(open('.temp/gate_watch.json',encoding='utf-8'));r=d['runs'][0];t=r['timings'];u=r['usage'];print('%.1f %d %.0f' % (t['predicted_per_second'], u['prompt_tokens_details']['cached_tokens'], t['prompt_ms']))" 2>$null
    if ($parsed -match '([\d.]+) (\d+) (\d+)') { $dec = [double]$Matches[1]; $cached = [int]$Matches[2]; $pms = [double]$Matches[3] }
    J ('probe sec=' + $sec + ' decode=' + $dec + ' tok/s | prompt_ms=' + $pms + ' cached=' + $cached + ' | gpu=' + $gpu)
    if ($dec -lt 80.0 -and $sec -ge 2.0) {
        $slowStreak += 1
        J ('STATE=SLOW streak=' + $slowStreak + ' -> sampler+dmon 300s')
        Start-Process -WindowStyle Hidden -FilePath cmd -ArgumentList '/c', 'nvidia-smi dmon -o T -s pucmt -c 300 > J:\ninfer-kvmem\.temp\watch_dmon.txt 2>&1'
        Start-Process -WindowStyle Hidden -FilePath python -ArgumentList '-X', 'utf8', 'scripts\gpu_sampler.py', '--seconds', '300', '--interval', '1'
        Start-Sleep -Seconds 300
    } else {
        if ($slowStreak -ge 2) { J ('STATE=RECOVERED after streak=' + $slowStreak) }
        $slowStreak = 0
        Start-Sleep -Seconds $IntervalSec
    }
}
J 'WATCHER end'
