# async_abab.ps1 -- FINAL VERDICT RUN for the async demote pipeline (NINFER_ASYNC_DEMOTE).
#
# Question: does async demote buy decode speed in the DEEP over-pool multi-turn regime
#           (the only regime where it ever claimed value, r=0.801 @ 74K deep over-pool)?
#
# Design (fairness rules, user-ordered 2026-10-25):
#   - ONE boot, arms interleaved and order-counterbalanced: cycle1 OFF->ON, cycle2 ON->OFF.
#   - Same engine binary / same workload bytes / same driver; ONLY the toggle flips.
#   - Every arm: fresh engine start (fresh log), argv (CMD line) + VARIANT registration line
#     captured, nvidia-smi clocks/temp/vram before+after, demote-profile firing count logged.
#   - A' comparability data (engine sha, config, concurrency, metric) recorded per arm.
#
# Pre-registered decision rule (REVISED 2026-10-26, three-way convergence CB/TELE/user):
#   The keep/retire agenda is CLOSED (user final ruling 2026-10-25 night: async pipeline is core
#   infrastructure; no去留 agenda). The original "AMBIGUOUS -> RETIRE BY DEFAULT" clause is
#   SUPERSEDED by §8.1 of the speed plan (never user-approved, retracted).
#   metric: deep decode = mean(round2, round3) tok/s per run (established caliber).
#   validity per arm: extreme ratio max/min <= 1.15 AND zero request errors AND demote fired > 0.
#   verdict:
#     validity holds + both paired deltas (ON - OFF) > +5% -> SIGNAL: paired positive
#                 (caliber valid; attribution judged separately via staging-code read)
#     both paired deltas < -5% -> paired negative both cycles -> investigate (NO auto-retire)
#     anything else (invalid arm, ratio gate fail, demote never fired in BOTH arms)
#                 -> CALIBER-INVALID / INCONCLUSIVE -> record as-is, NO keep/retire效力;
#                    hand over to attribution analysis (zero machine time).
#   If demote_profile count == 0 in both arms: record the fact "switch never exercised"
#     (no去留效力, noted separately from SIGNAL).
#
# Load: a2gate deep multi-turn, filler 300KB (~75.3K tok > 65536 pool), rounds 3
#       (ctx ~75K -> ~152K -> ~229K), max-tokens 2000. Engine: I3b_step13_fourlayer
#       (same platform as all prior async arms). NOTE: runs at NINFER_ASYNC_DEMOTE_DEPTH=2
#       (historical-comparability choice); code default is depth=1 (2026-10-12 regression tier).
# Ledger: .temp\async_abab_<ts>.txt   Raw: work\data\gate_abab_{off,on}_c{1,2}.json
# Window discipline: runner window visible, titled; engine windows via engine_ctl (visible).
# First run: 2026-10-25 20:27-22:31 (ledger .temp\async_abab_20261025_202705.txt) --
#   all four arms r3 timeout (a2gate 900s cap) -> prereg caliber broken -> verdict line of that
#   run is void; r2-only signal recorded with caliber footnote (see speed plan §8.6).
param(
    [int]$FillerKb = 300,
    [int]$MaxTokens = 2000,
    [int]$Rounds = 3,
    [switch]$PreflightOnly
)
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$led = ".temp\async_abab_$ts.txt"
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
try { $Host.UI.RawUI.WindowTitle = "ASYNC ABAB RUN $ts - visible - ledger .temp\async_abab_$ts.txt - auto-closes when done" } catch {}

# ---------- preflight ----------
$need = @(
    'engine\lineage\ninfer-serve-RC1.exe',
    'scripts\engine_ctl.ps1',
    'scripts\a2gate.py'
)
$ok = $true
foreach ($f in $need) {
    $p = Test-Path -LiteralPath $f
    Say ("preflight Test-Path " + $f + " = " + $p)
    if (-not $p) { $ok = $false }
}
Say ("preflight git HEAD = " + ((git rev-parse --short HEAD) 2>$null))
Say ("preflight VARIANT = " + ((Get-Content 'engine\test-run\VARIANT.txt' -EA 0) -join ' / '))
if (-not $ok) { Say 'PREFLIGHT FAILED - no engine start'; exit 1 }
if ($PreflightOnly) { Say 'PREFLIGHT-ONLY requested - exit'; exit 0 }

# ---------- pre-registration into ledger (before any start) ----------
Say 'PREREG decision rule (2026-10-26 revised): metric=mean(r2,r3) tok/s; validity=per-arm extreme-ratio<=1.15 AND 0 errors AND demote_fired>0;'
Say 'PREREG verdict: paired>+5% both cycles -> SIGNAL | paired<-5% both -> investigate | else record-as-is (NO keep/retire效力, agenda closed);'
Say 'PREREG demote_fired==0 both arms -> record "never exercised" fact (no去留效力).'

$gpuq = 'clocks.sm,temperature.gpu,memory.used,memory.total,power.draw'
function GpuSnap { return (nvidia-smi --query-gpu=$gpuq --format=csv,noheader,nounits 2>$null) -join ' | ' }

function RunArm($mode, $c) {
    $tag = 'abab_' + $mode + '_c' + $c
    $envv = '0'; if ($mode -eq 'on') { $envv = '1' }
    Say ("==== arm " + $mode + " cycle" + $c + " (NINFER_ASYNC_DEMOTE=" + $envv + ", tag=" + $tag + ") ====")
    [Environment]::SetEnvironmentVariable('NINFER_ASYNC_DEMOTE', $envv, 'Process')

    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 20; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 2

    $extra = '--request-log-jsonl,work\data\reqlog_' + $tag + '.jsonl,--request-log-max-mib,128,--request-log-keep,2'
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\ninfer-serve-RC1.exe' -Tag $tag -Depth 2 -Port 8094 -Pool 65536 -Graph 64 -KvDtype rk2v4-e8 -Vision overlay -Spec mtp -Draft 4 -Extra $extra -Experimental | Out-Null
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $tag -WaitSec 300) -join ' '
    if ($r -notmatch 'READY') { Say ("arm " + $mode + " cycle" + $c + " READY-FAILED: " + $r); return $null }
    $lg = 'logs\test_' + $tag + '.log'
    $cmd = Select-String -Path $lg -Pattern 'CMD:' -EA 0 | Select-Object -Last 1
    if ($cmd) { Say ('argv: ' + $cmd.Line.Substring(0, [Math]::Min(400, $cmd.Line.Length))) }
    $var = Get-Content 'engine\test-run\VARIANT.txt' -EA 0 | Select-Object -Last 1
    if ($var) { Say ('variant: ' + $var.Trim()) }
    Say ("pre-run gpu: " + (GpuSnap))

    $t0 = Get-Date
    $out = python -X utf8 scripts\a2gate.py --arm ('abab_' + $mode + '_c' + $c) --port 8094 --runs 1 --rounds $Rounds --filler-kb $FillerKb --max-tokens $MaxTokens 2>&1
    $el = [math]::Round(((Get-Date) - $t0).TotalSeconds, 0)
    $out | ForEach-Object { Say ('  ' + $_) }
    Say ("post-run gpu: " + (GpuSnap) + " | wall=" + $el + "s")

    if (Test-Path $lg) {
        $dmp = @(Select-String -Path $lg -Pattern 'demote profile' -EA 0).Count
        $ring = @(Select-String -Path $lg -Pattern '\[ring\]' -EA 0).Count
        $stall = @(Select-String -Path $lg -Pattern 'STALL' -EA 0).Count
        $exceed = @(Select-String -Path $lg -Pattern 'prompt exceeds' -EA 0).Count
        Say ("logstat " + $tag + " demote_profile=" + $dmp + " ring=" + $ring + " stall=" + $stall + " exceeds=" + $exceed)
    }
    return $true
}

# cycle1 OFF->ON, cycle2 ON->OFF (order counterbalance)
$plan = @(
    @{ c = 1; order = @('off','on') },
    @{ c = 2; order = @('on','off') }
)
foreach ($p in $plan) {
    Say ("=== cycle " + $p.c + " (order " + ($p.order -join '->') + ") ===")
    foreach ($m in $p.order) { $null = RunArm $m $p.c }
}

# ---------- summary ----------
Say '==== SUMMARY (deep decode = mean(r2,r3) tok/s) ===='
$deep = @{}
$errsByArm = @{}
foreach ($m in 'off','on') {
    foreach ($c in 1,2) {
        $jp = 'work\data\gate_abab_' + $m + '_c' + $c + '.json'
        if (-not (Test-Path $jp)) { Say ("json missing: " + $jp); $deep[$m + $c] = -1; $errsByArm[$m] = [int]$errsByArm[$m] + 1; continue }
        try {
            $j = Get-Content $jp -Encoding UTF8 -Raw | ConvertFrom-Json
            $ds = @(); $errs = 0
            foreach ($rr in $j.runs) {
                if ($rr.error) { $errs++; Say ("  ERROR " + $m + "_c" + $c + " r" + $rr.round + ": " + $rr.error); continue }
                if ($rr.round -ge 2) { $ds += [double]$rr.timings.predicted_per_second }
            }
            $errsByArm[$m] = [int]$errsByArm[$m] + $errs
            $v = -1; if ($ds.Count -gt 0) { $v = [math]::Round(($ds | Measure-Object -Average).Average, 1) }
            $deep[$m + $c] = $v
            Say ("arm=" + $m + " cycle=" + $c + " deep=" + $v + " (rounds2-3=[" + (($ds | ForEach-Object { [math]::Round($_,1) }) -join ',') + "]) errors=" + $errs)
        } catch { Say ("json parse failed " + $jp + ": " + $_.Exception.Message); $deep[$m + $c] = -1; $errsByArm[$m] = [int]$errsByArm[$m] + 1 }
    }
}
$d1 = $deep['on1'] - $deep['off1']
$d2 = $deep['on2'] - $deep['off2']
Say ("paired deltas (ON-OFF): cycle1=" + [math]::Round($d1,1) + " cycle2=" + [math]::Round($d2,1))
$offAll = @($deep['off1'], $deep['off2']) | Where-Object { $_ -gt 0 }
$onAll  = @($deep['on1'],  $deep['on2'])  | Where-Object { $_ -gt 0 }
$offRatio = 'n/a'; if ($offAll.Count -eq 2) { $offRatio = [math]::Round(($offAll | Measure-Object -Maximum).Maximum / ($offAll | Measure-Object -Minimum).Minimum, 3) }
$onRatio = 'n/a'; if ($onAll.Count -eq 2) { $onRatio = [math]::Round(($onAll | Measure-Object -Maximum).Maximum / ($onAll | Measure-Object -Minimum).Minimum, 3) }
Say ("validity extreme-ratio: OFF=" + $offRatio + " ON=" + $onRatio + " (gate <=1.15)")
$errTotal = ($errsByArm.Values | Measure-Object -Sum).Sum
Say ("total request errors = " + $errTotal + " (0-errors gate is part of validity)")
$ratioOk = ($offRatio -ne 'n/a' -and $onRatio -ne 'n/a' -and [double]$offRatio -le 1.15 -and [double]$onRatio -le 1.15)
if (-not $ratioOk -or $errTotal -gt 0) {
    Say ('VERDICT: CALIBER-INVALID (ratio gate ok=' + $ratioOk + ', errors=' + $errTotal + ') -> record as-is; NO keep/retire效力; attribution analysis takes over (staging-code read, zero machine time)')
} elseif ($d1 -gt 0 -and $d2 -gt 0 -and (($d1 / $deep['off1']) -gt 0.05) -and (($d2 / $deep['off2']) -gt 0.05)) {
    Say 'VERDICT: SIGNAL — paired positive both cycles (>+5%), caliber valid; attribution judged separately (staging-code read)'
} elseif ($d1 -lt 0 -and $d2 -lt 0) {
    Say 'VERDICT: paired negative both cycles — investigate before any action (NO auto-retire)'
} else {
    Say 'VERDICT: INCONCLUSIVE — record as-is; NO keep/retire效力; attribution analysis takes over'
}
$whea = 0
try { $whea = @(Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'; StartTime=(Get-Date).AddHours(-2)} -EA 0).Count } catch {}
Say ("WHEA events last 2h = " + $whea)
# prereg 2026-10-26: 跑完停引擎归还显存（无人值守夜班必做）
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
Start-Sleep -Seconds 3
if (Get-Process ninfer-serve -ErrorAction SilentlyContinue) {
    Say 'WARN: engine still alive after stop (manual teardown needed)'
} else {
    Say 'engine stopped; vram freed'
}
Say ('vram after teardown = ' + (nvidia-smi --query-gpu=memory.used --format=csv,noheader))
Say 'ASYNC-ABAB end (unattended night run; no commit/push; data to TELE for reconciliation)'
