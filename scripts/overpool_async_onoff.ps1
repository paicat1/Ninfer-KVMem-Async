# overpool_async_onoff.ps1 -- user-scheduled ablation: does the async page pipeline
# (NINFER_ASYNC_DEMOTE) buy anything in the OVER-POOL regime?
#
#   ARM OFF: NINFER_ASYNC_DEMOTE=0 (sync batch fallback)
#   ARM ON : NINFER_ASYNC_DEMOTE=1 (default; left running afterwards as the restored
#            standard platform, tag = valleywatch, same config as the service platform)
#
# Load: a2gate deep over-pool probe -- filler 300 KB (~74.5K tokens > 65536 pool),
#       runs 3 x rounds 1, max-tokens 600. Same driver both arms; only env differs.
# Pre-registration: docs\02-实验与预登记\实验-超池异步ONOFF对照-预登记-CodeBuddyCLI-20261016.md
# Ledger: .temp\poolab_<ts>.txt   Raw: .temp\gate_pab_off.json / .temp\gate_pab_on.json
# Engine control: scripts\engine_ctl.ps1 (its window discipline applies; visible windows).
# This script window: visible; closes automatically when the run finishes (ledger kept).
# Authorized by the user via the mobile CLI (see docs\05-交接与值守\CLI致CB-用户安排说明-20261016.md).
param(
    [int]$FillerKb = 300,
    [int]$MaxTokens = 600,
    [int]$Runs = 3,
    [string]$Exe = 'engine\lineage\ninfer-serve-RC1.exe'
)
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
try { $Host.UI.RawUI.WindowTitle = 'KV over-pool A/B (async demote ON/OFF) - auto-closes when done - ledger .temp\poolab_*.txt' } catch {}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$led = '.temp\poolab_' + $ts + '.txt'
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }

Say ('OVERPOOL-ASYNC start: filler=' + $FillerKb + 'KB max=' + $MaxTokens + ' runs=' + $Runs)
Say ('engine exe: ' + $Exe)
Say ('VARIANT now: ' + ((Get-Content 'engine\test-run\VARIANT.txt' -EA 0) -join ' / '))
Say ('git HEAD: ' + ((git rev-parse --short HEAD) 2>$null))
Say 'authorized: user (mobile CLI), 2026-10-16; note: docs\05-交接与值守\CLI致CB-用户安排说明-20261016.md'

# insurance copy of the current watch log before the platform is replaced
try {
    Copy-Item 'logs\test_valleywatch.log' ('.temp\valleywatch_before_poolab_' + $ts + '.log') -Force
    Say 'watch log backup copied (.temp\valleywatch_before_poolab_' + $ts + '.log)'
} catch { Say ('watch log backup skipped: ' + $_.Exception.Message) }

$arms = @(
    @{ mode = 'off'; tag = 'pab_off';    env = '0'; extra = '--request-log-jsonl,.temp\reqlog_pab_off.jsonl,--request-log-max-mib,128,--request-log-keep,2' },
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

    Say ('driver: a2gate.py --arm pab_' + $a.mode + ' --runs ' + $Runs + ' --rounds 1 --filler-kb ' + $FillerKb + ' --max-tokens ' + $MaxTokens)
    $out = python -X utf8 scripts\a2gate.py --arm ('pab_' + $a.mode) --port 8094 --runs $Runs --rounds 1 --filler-kb $FillerKb --max-tokens $MaxTokens
    $out | ForEach-Object { Say ('  ' + $_) }

    $l = 'logs\test_' + $a.tag + '.log'
    if (Test-Path $l) {
        $exceed = @(Select-String -Path $l -Pattern 'prompt exceeds' -EA 0).Count
        $dn = @(Select-String -Path $l -Pattern 'req#\d+ done' -EA 0).Count
        $dmp = @(Select-String -Path $l -Pattern 'demote profile' -EA 0).Count
        $ring = @(Select-String -Path $l -Pattern '\[ring\]' -EA 0).Count
        $stall = @(Select-String -Path $l -Pattern 'STALL' -EA 0).Count
        Say ('log stat arm=' + $a.mode + ' exceeds=' + $exceed + ' done=' + $dn + ' demote_profile=' + $dmp + ' ring=' + $ring + ' stall=' + $stall)
        $ld = Select-String -Path $l -Pattern 'req#\d+ done' -EA 0 | Select-Object -Last 1
        if ($ld) { Say ('last done: ' + $ld.Line.Substring(0, [Math]::Min(260, $ld.Line.Length))) }
        $smp = Select-String -Path $l -Pattern 'demote profile' -EA 0 | Select-Object -Last 2
        foreach ($s in $smp) { Say ('  profile: ' + $s.Line.Substring(0, [Math]::Min(220, $s.Line.Length))) }
    } else { Say ('log missing: ' + $l) }
}

Say '==== arm results (from a2gate json) ===='
foreach ($m in 'off','on') {
    $p = '.temp\gate_pab_' + $m + '.json'
    if (Test-Path $p) {
        try {
            $j = Get-Content $p -Encoding UTF8 -Raw | ConvertFrom-Json
            $decs = @($j.runs | ForEach-Object { if ($_.timings.predicted_per_second) { [math]::Round([double]$_.timings.predicted_per_second, 1) } })
            $sorted = @($decs | Sort-Object)
            $med = 'n/a'
            if ($sorted.Count -gt 0) { $med = $sorted[[int]($sorted.Count / 2)] }
            $errs = @($j.runs | Where-Object { $_.error }).Count
            Say ('arm=' + $m + ' decode=[' + ($decs -join ',') + '] median=' + $med + ' errors=' + $errs)
        } catch { Say ('arm=' + $m + ' json parse failed: ' + $_.Exception.Message) }
    } else { Say ('arm=' + $m + ' gate json missing') }
}

Say 'note: last arm (ON) is left running as the restored standard platform (tag valleywatch).'
Say 'OVERPOOL-ASYNC end'
