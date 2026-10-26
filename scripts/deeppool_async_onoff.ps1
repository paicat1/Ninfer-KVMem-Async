# deeppool_async_onoff.ps1 -- user-scheduled HEAVY follow-up ablation: does the async page
# pipeline (NINFER_ASYNC_DEMOTE) buy anything in the DEEP over-pool MULTI-TURN regime?
# (the historical value claims: 74.4K deep over-pool decode 114.4 tok/s; multi-turn alive)
#
#   ARM OFF: NINFER_ASYNC_DEMOTE=0 (sync batch fallback)
#   ARM ON : NINFER_ASYNC_DEMOTE=1 (default; left running afterwards as the restored
#            standard platform, tag = valleywatch, same config as the service platform)
#
# Load: a2gate deep multi-turn probe -- filler 300 KB (~75.3K tokens > 65536 pool),
#       rounds 3 (context grows ~75K -> ~152K -> ~229K; partial prefix-cache reuse
#       between rounds = turn closure), max-tokens 2000. Same driver both arms;
#       only env differs. a2gate is invoked once per run (--runs 1) and its json is
#       copied per run, because one 3-round run is long.
# Pre-registration: docs\02-实验与预登记\实验-深轮重载ONOFF对照-预登记-CodeBuddyCLI-20261016.md
# Ledger: .temp\deeppool_<ts>.txt  Raw: .temp\gate_dp_{off,on}_run{1..3}.json
# Engine control: scripts\engine_ctl.ps1 (its window discipline applies; visible windows).
# Authorized by the user via the mobile CLI, 2026-10-16.
param(
    [int]$FillerKb = 300,
    [int]$MaxTokens = 2000,
    [int]$Rounds = 3,
    [int]$Runs = 3,
    [string]$Exe = 'engine\lineage\I3b_step13_fourlayer_20261015.exe'
)
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
try { $Host.UI.RawUI.WindowTitle = 'KV deep over-pool multi-turn A/B (async demote ON/OFF) - auto-closes when done - ledger .temp\deeppool_*.txt' } catch {}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$led = '.temp\deeppool_' + $ts + '.txt'
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }

Say ('DEEPPOOL-ASYNC start: filler=' + $FillerKb + 'KB max=' + $MaxTokens + ' rounds=' + $Rounds + ' runs=' + $Runs)
Say ('engine exe: ' + $Exe)
Say ('VARIANT now: ' + ((Get-Content 'engine\test-run\VARIANT.txt' -EA 0) -join ' / '))
Say ('git HEAD: ' + ((git rev-parse --short HEAD) 2>$null))
Say 'authorized: user (mobile CLI), 2026-10-16; heavy follow-up of the over-pool ablation'

# insurance copy of the current watch log before the platform is replaced
try {
    Copy-Item 'logs\test_valleywatch.log' ('.temp\valleywatch_before_deeppool_' + $ts + '.log') -Force
    Say 'watch log backup copied (.temp\valleywatch_before_deeppool_' + $ts + '.log)'
} catch { Say ('watch log backup skipped: ' + $_.Exception.Message) }

$arms = @(
    @{ mode = 'off'; tag = 'dp_off';      env = '0'; extra = '--request-log-jsonl,.temp\reqlog_dp_off.jsonl,--request-log-max-mib,128,--request-log-keep,2' },
    @{ mode = 'on';  tag = 'valleywatch'; env = '1'; extra = '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' }
)

foreach ($a in $arms) {
    Say ('==== ARM ' + $a.mode + ' (NINFER_ASYNC_DEMOTE=' + $a.env + ', tag=' + $a.tag + ') ====')
    [Environment]::SetEnvironmentVariable('NINFER_ASYNC_DEMOTE', $a.env, 'Process')
    Say ('env check: NINFER_ASYNC_DEMOTE=' + $env:NINFER_ASYNC_DEMOTE)

    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Host
    for ($w = 1; $w -le 20; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2

    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $Exe -Tag $a.tag -Depth 2 -Port 8094 -Pool 65536 -Graph 64 -KvDtype rk2v4-e8 -Vision overlay -Spec mtp -Draft 4 -Extra $a.extra | Out-Host
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $a.tag -WaitSec 300) -join ' '
    if ($r -notmatch 'READY') {
        Say ('arm ' + $a.mode + ' ready=FAILED (' + $r + ') -> retry once in 12s')
        Start-Sleep -Seconds 12
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Host
        for ($w2 = 1; $w2 -le 20; $w2++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
        Start-Sleep -Seconds 3
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $Exe -Tag $a.tag -Depth 2 -Port 8094 -Pool 65536 -Graph 64 -KvDtype rk2v4-e8 -Vision overlay -Spec mtp -Draft 4 -Extra $a.extra | Out-Host
        $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $a.tag -WaitSec 300) -join ' '
    }
    if ($r -notmatch 'READY') { Say ('ARM ' + $a.mode + ' START-FAILED - skip arm'); continue }
    $vram = (nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>$null) -join ' '
    Say ('arm ' + $a.mode + ' READY; vram=' + $vram)

    for ($k = 1; $k -le $Runs; $k++) {
        Say ('driver run ' + $k + '/' + $Runs + ': a2gate.py --arm dp_' + $a.mode + ' --runs 1 --rounds ' + $Rounds + ' --filler-kb ' + $FillerKb + ' --max-tokens ' + $MaxTokens)
        $t0 = Get-Date
        $out = python -X utf8 scripts\a2gate.py --arm ('dp_' + $a.mode) --port 8094 --runs 1 --rounds $Rounds --filler-kb $FillerKb --max-tokens $MaxTokens 2>&1
        $el = [math]::Round(((Get-Date) - $t0).TotalSeconds, 0)
        $out | ForEach-Object { Say ('  ' + $_) }
        Copy-Item ('.temp\gate_dp_' + $a.mode + '.json') ('.temp\gate_dp_' + $a.mode + '_run' + $k + '.json') -Force -EA 0
        Say ('  run ' + $k + ' wall=' + $el + 's')
    }

    $l = 'logs\test_' + $a.tag + '.log'
    if (Test-Path $l) {
        $exceed = @(Select-String -Path $l -Pattern 'prompt exceeds' -EA 0).Count
        $dn = @(Select-String -Path $l -Pattern 'req#\d+ done' -EA 0).Count
        $dmp = @(Select-String -Path $l -Pattern 'demote profile' -EA 0).Count
        $ring = @(Select-String -Path $l -Pattern '\[ring\]' -EA 0).Count
        $stall = @(Select-String -Path $l -Pattern 'STALL' -EA 0).Count
        $tc = @(Select-String -Path $l -Pattern 'turn closure' -EA 0).Count
        Say ('log stat arm=' + $a.mode + ' exceeds=' + $exceed + ' done=' + $dn + ' demote_profile=' + $dmp + ' ring=' + $ring + ' stall=' + $stall + ' turnClosure=' + $tc)
        $ld = Select-String -Path $l -Pattern 'req#\d+ done' -EA 0 | Select-Object -Last 1
        if ($ld) { Say ('last done: ' + $ld.Line.Substring(0, [Math]::Min(300, $ld.Line.Length))) }
    } else { Say ('log missing: ' + $l) }
}

Say '==== a2gate json: deep decode = mean(r2, r3) per run ===='
foreach ($m in 'off','on') {
    $deep = @(); $r1 = @(); $errs = 0
    foreach ($k in 1..$Runs) {
        $p = '.temp\gate_dp_' + $m + '_run' + $k + '.json'
        if (-not (Test-Path $p)) { Say ('run json missing: ' + $p); continue }
        try {
            $j = Get-Content $p -Encoding UTF8 -Raw | ConvertFrom-Json
            foreach ($r in $j.runs) {
                if ($r.error) { $errs++; Say ('  arm=' + $m + ' run' + $k + ' round' + $r.round + ' ERROR: ' + $r.error); continue }
                $d = [double]$r.timings.predicted_per_second
                if ($r.round -eq 1) { $r1 += [math]::Round($d, 1) }
                else { $deep += $d }
            }
        } catch { Say ('json parse failed ' + $p + ': ' + $_.Exception.Message) }
    }
    $medD = 'n/a'; if ($deep.Count -gt 0) { $s = @($deep | Sort-Object); $medD = [math]::Round($s[[int]($s.Count / 2)], 1) }
    $med1 = 'n/a'; if ($r1.Count -gt 0) { $s1 = @($r1 | Sort-Object); $med1 = $s1[[int]($s1.Count / 2)] }
    Say ('arm=' + $m + ' deep(r2-3) decode=[' + (($deep | ForEach-Object { [math]::Round($_, 1) }) -join ',') + '] median=' + $medD + ' | r1 decode=[' + ($r1 -join ',') + '] median=' + $med1 + ' errors=' + $errs)
}

Say 'note: last arm (ON) is left running as the restored standard platform (tag valleywatch).'
Say 'DEEPPOOL-ASYNC end'
