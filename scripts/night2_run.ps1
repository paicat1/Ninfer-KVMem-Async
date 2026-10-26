# night2_run.ps1 v3 -- 可续跑夜班：checkpoint + heartbeat + 收敛判据
param(
    [string]$NewExe = '.temp\build-1208a\apps\ninfer-serve.exe',
    [string]$S13Exe = 'engine\lineage\I3b_step13_fourlayer_20261015.exe',
    [int]$MaxHours = 4
)
$root = 'J:\ninfer-kvmem'
Set-Location $root
$dir = Join-Path $root '.temp\night2'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$log = Join-Path $dir 'night2.log'
$stateF = Join-Path $dir 'state.json'
$resF = Join-Path $dir 'results.jsonl'
$hbF = Join-Path $dir 'heartbeat.txt'

function Say([string]$m) {
    $l = (Get-Date -Format 'MM-dd HH:mm:ss') + '  ' + $m
    Add-Content -LiteralPath $log -Value $l -Encoding UTF8
    Write-Host $l
}
function HB { (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Set-Content -LiteralPath $hbF -Encoding ASCII }
function SetPhase([string]$p) {
    $dl = (Get-Date).AddHours($MaxHours).ToString('o')
    if (Test-Path $stateF) {
        try {
            $old = Get-Content $stateF -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($old.deadline) { $dl = [string]$old.deadline }
        } catch { }
    }
    $s = [ordered]@{ phase = $p; updated = (Get-Date -Format 'o'); deadline = $dl }
    [IO.File]::WriteAllText($stateF, ($s | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
}
function GetPhase { if (Test-Path $stateF) { (Get-Content $stateF -Raw -Encoding UTF8 | ConvertFrom-Json).phase } else { '' } }
function GetDeadline { if (Test-Path $stateF) { [datetime](Get-Content $stateF -Raw -Encoding UTF8 | ConvertFrom-Json).deadline } else { (Get-Date).AddHours($MaxHours) } }
# JSONL：每行一个对象，永不嵌套（旧版 ConvertTo-Json 对数组会输出 {value,Count} 包装）
function LoadResults {
    if (-not (Test-Path $resF)) { return @() }
    $lines = @(Get-Content $resF -Encoding UTF8 | Where-Object { $_.Trim() })
    $out = @()
    foreach ($l in $lines) { try { $out += ($l | ConvertFrom-Json) } catch { } }
    return $out
}
function SaveResult($r) {
    $line = ($r | ConvertTo-Json -Compress -Depth 6)
    Add-Content -LiteralPath $resF -Value $line -Encoding UTF8
}
function HasTag([string]$t) { return [bool](@(LoadResults) | Where-Object { $_.tag -eq $t -and $_.valid }) }

function Gpu {
    $g = (nvidia-smi --query-gpu=clocks.sm,temperature.gpu,power.draw,memory.used,memory.total --format=csv,noheader,nounits) -split ','
    return [pscustomobject]@{ clk = [double]$g[0].Trim(); temp = [double]$g[1].Trim(); pow = [double]$g[2].Trim(); mem = [double]$g[3].Trim(); total = [double]$g[4].Trim() }
}
function StopEngine { & powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop 2>&1 | Out-Null; Start-Sleep -Seconds 3; HB }
function StartEngine([string]$exe, [int]$pool, [string]$tag) {
    StopEngine
    & powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $exe -Tag $tag -Pool $pool -Graph 64 -Spec mtp -KvDtype rk2v4-e8 -Draft 4 -Experimental 2>&1 | Out-Null
    $r = (& powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $tag -WaitSec 300 2>&1) -join ' '
    HB
    return ($r -match 'READY')
}

# 单次跑（不重试）
function RunOnce([string]$tag, [string]$exe, [int]$pool, [int]$rounds) {
    if (-not (StartEngine $exe $pool $tag)) { return [pscustomobject]@{ tag = $tag; valid = $false; why = 'engine_not_ready' } }
    $d = @(); $p = @(); $c = @(); $errs = 0
    for ($i = 1; $i -le $rounds; $i++) {
        $out = (& python scripts\a2gate.py --arm $tag --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) | Out-String
        if ($out -match 'decode=([\d.]+)') { $d += [double]$Matches[1] } else { $errs++ }
        if ($out -match 'HTTPError|429') { $errs++ }
        $g = Gpu; $p += $g.pow; $c += $g.clk
        HB; Start-Sleep -Seconds 3
    }
    StopEngine
    if ($d.Count -eq 0) { return [pscustomobject]@{ tag = $tag; valid = $false; why = 'no_decode'; errs = $errs } }
    $mean = ($d | Measure-Object -Average).Average
    $mn = ($d | Measure-Object -Minimum).Minimum
    $mx = ($d | Measure-Object -Maximum).Maximum
    $ratio = if ($mn -gt 0) { $mx / $mn } else { 99 }
    $powMin = ($p | Measure-Object -Minimum).Minimum
    $clkMin = ($c | Measure-Object -Minimum).Minimum
    $valid = ($errs -eq 0 -and $powMin -ge 120 -and $clkMin -ge 2500 -and $ratio -le 1.15)
    return [pscustomobject]@{ tag = $tag; mean = [math]::Round($mean, 1); ratio = [math]::Round($ratio, 3); powMin = $powMin; clkMin = $clkMin; rounds = $rounds; valid = $valid; why = ''; raw = ($d -join '/') }
}

# 带诊断的自适应重试
function RunBase([string]$tag, [string]$exe, [int]$pool, [int]$rounds = 3, [int]$maxTry = 3) {
    if (HasTag $tag) { Say ('SKIP ' + $tag + ' (already done)'); return (@(LoadResults) | Where-Object { $_.tag -eq $tag })[0] }
    $r = $null
    for ($try = 1; $try -le $maxTry; $try++) {
        Say ('RUN ' + $tag + ' try=' + $try + ' pool=' + $pool + ' rounds=' + $rounds)
        $r = RunOnce $tag $exe $pool $rounds
        if ($r.valid) { Say ('OK  ' + $tag + ' mean=' + $r.mean + ' ratio=' + $r.ratio); SaveResult $r; return $r }
        # 诊断 -> 调整
        $why = [string]$r.why
        if ($why -match 'engine_not_ready') { Say ('  DIAG: start failed, retry same'); Start-Sleep -Seconds 20 }
        elseif ($why -match 'no_decode') { Say ('  DIAG: no decode, retry same'); Start-Sleep -Seconds 30 }
        elseif ($r.powMin -and $r.powMin -lt 120) { Say ('  DIAG: valley/low-power (' + $r.powMin + 'W), wait 300s'); Start-Sleep -Seconds 300 }
        elseif ($r.clkMin -and $r.clkMin -lt 2500) { Say ('  DIAG: low clock (' + $r.clkMin + 'MHz), wait 120s'); Start-Sleep -Seconds 120 }
        elseif ($r.ratio -and $r.ratio -gt 1.15) { Say ('  DIAG: unstable (ratio=' + $r.ratio + '), rounds 5'); $rounds = 5 }
        else { Start-Sleep -Seconds 20 }
    }
    Say ('FAIL ' + $tag + ' -> ' + ($r.why) + ' powMin=' + $r.powMin + ' clkMin=' + $r.clkMin + ' ratio=' + $r.ratio)
    SaveResult $r
    return $r
}

function Fmt($r) {
    if (-not $r) { return 'n/a' }
    if (-not $r.valid) { return ('{0}: INVALID ({1}) powMin={2} clkMin={3}' -f $r.tag, $r.why, $r.powMin, $r.clkMin) }
    return ('{0}: mean={1} ratio={2} powMin={3} clkMin={4} raw={5}' -f $r.tag, $r.mean, $r.ratio, $r.powMin, $r.clkMin, $r.raw)
}

Say '================ night2 v3 start ================'
HB
if (-not (Test-Path $stateF)) { SetPhase 'N0' }
$deadline = GetDeadline
Say ('deadline=' + $deadline.ToString('MM-dd HH:mm') + '  now=' + (Get-Date -Format 'MM-dd HH:mm'))
$env:NINFER_DEMOTE_PROFILE = '0'

# ---------- N0：归因 ----------
SetPhase 'N0'
$e1a = RunBase 'e1a' $NewExe 65536 3
$e1b = RunBase 'e1b' $NewExe 49152 3
$e2 = RunBase 'e2' $S13Exe 65536 3

$h1 = ($e1a.valid -and $e1b.valid -and $e1b.mean -ge $e1a.mean * 1.10)
$h2 = ($e1a.valid -and $e2.valid -and $e2.mean -ge $e1a.mean * 1.10)
$h3 = (-not $h1 -and -not $h2)
Say ('N0: H1=' + $h1 + ' H2=' + $h2 + ' H3=' + $h3)

# ---------- N2：核心（同跑双侧），放在 N1 之前保证核心拿到 ----------
SetPhase 'N2'
if (-not (HasTag 'n2')) {
    $env:NINFER_DEMOTE_PROFILE = '1'
    $env:NINFER_ASYNC_DEMOTE = '1'
    $env:NINFER_ASYNC_DEMOTE_DEPTH = '2'
    $ok = StartEngine $NewExe 65536 'n2'
    if ($ok) {
        $out = (& python scripts\a2gate.py --arm n2_on --port 8094 --runs 1 --rounds 3 --filler-kb 300 --max-tokens 200 2>&1) | Out-String
        Say ('N2 a2gate: ' + (($out -replace '\s+', ' ')).Substring(0, [Math]::Min(180, ($out -replace '\s+', ' ').Length)))
        $lg = Join-Path $root 'logs\test_n2.log'
        $dem = 0; $res = 0; $dev = 0
        if (Test-Path $lg) {
            $dem = (Select-String -Path $lg -Pattern 'demote profile' -EA 0 | Measure-Object).Count
            $res = (Select-String -Path $lg -Pattern 'restore profile' -EA 0 | Measure-Object).Count
            $dev = (Select-String -Path $lg -Pattern 'dev=' -EA 0 | Measure-Object).Count
        }
        Say ('N2: demote=' + $dem + ' restore=' + $res + ' dev=' + $dev)
        # demote=0 -> 提高 filler 重试一次
        if ($dem -eq 0) {
            Say 'N2 DIAG: demote=0 -> retry filler=400KB'
            $out2 = (& python scripts\a2gate.py --arm n2_on_b --port 8094 --runs 1 --rounds 3 --filler-kb 400 --max-tokens 200 2>&1) | Out-String
            if (Test-Path $lg) { $dem = (Select-String -Path $lg -Pattern 'demote profile' -EA 0 | Measure-Object).Count }
            Say ('N2 retry: demote=' + $dem)
        }
        SaveResult ([pscustomobject]@{ tag = 'n2'; valid = ($dem -gt 0); demote = $dem; restore = $res; dev = $dev; why = '' })
        StopEngine
    }
    else { Say 'N2: engine_not_ready'; SaveResult ([pscustomobject]@{ tag = 'n2'; valid = $false; why = 'engine_not_ready' }) }
}
else { Say 'SKIP n2 (already done)' }

# ---------- 收敛判据：核心目标达成则不再做扩展实验 ----------
$n2r = (@(LoadResults) | Where-Object { $_.tag -eq 'n2' })[0]
$coreDone = (($e1a.valid -or $e1b.valid) -and $e2.valid -and $n2r -and $n2r.valid)
Say ('CORE done=' + $coreDone + ' (N0 any-valid + e2 valid + n2 demote>0)')

$timeLeft = ($deadline - (Get-Date)).TotalMinutes
Say ('time left=' + [math]::Round($timeLeft, 0) + ' min')

# ---------- N1：仅在核心已达成且时间充足时做扩展 ----------
if ($coreDone -and $timeLeft -gt 30) {
    SetPhase 'N1'
    if ($h1) {
        Say '--- N1-H1: pool gradient (early stop) ---'
        $prev = $null
        foreach ($pool in @(49152, 40960, 32768, 24576)) {
            if (($deadline - (Get-Date)).TotalMinutes -lt 15) { Say 'N1: time low, stop gradient'; break }
            $r = RunBase ('h1_p' + $pool) $NewExe $pool 3
            if ($r.valid -and $prev -and $r.mean -lt $prev.mean * 0.95) { Say 'N1: knee passed, stop'; break }
            if ($r.valid) { $prev = $r }
        }
    }
    elseif ($h2) {
        Say '--- N1-H2: ABAB x5 ---'
        for ($i = 1; $i -le 5; $i++) {
            if (($deadline - (Get-Date)).TotalMinutes -lt 20) { Say 'N1: time low, stop ABAB'; break }
            RunBase ('h2_a' + $i) $NewExe 65536 1 | Out-Null
            RunBase ('h2_b' + $i) $S13Exe 65536 1 | Out-Null
        }
    }
    else {
        Say '--- N1-H3: fingerprint + 20min sampling x6 ---'
        $drv = ((nvidia-smi --query-gpu=driver_version --format=csv,noheader) -join '')
        Say ('H3 driver=' + $drv)
        for ($i = 1; $i -le 6; $i++) {
            if (($deadline - (Get-Date)).TotalMinutes -lt 25) { Say 'N1: time low, stop sampling'; break }
            RunBase ('h3_s' + $i) $NewExe 65536 1 | Out-Null
            if ($i -lt 6) { Start-Sleep -Seconds 1200; HB }
        }
    }
}
elseif (-not $coreDone) { Say 'N1: skipped (core not done -> prioritize core next run)' }
else { Say 'N1: skipped (time left <= 30 min)' }

# ---------- N3：缓存回查 ----------
SetPhase 'N3'
$py = @'
import json, glob, os
for f in sorted(glob.glob('.temp/gate_*.json')):
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception:
        continue
    seq = []
    for r in (d.get('runs') or []):
        u = r.get('usage') or {}
        seq.append((r.get('round'), (u.get('prompt_tokens_details') or {}).get('cached_tokens')))
    print(os.path.basename(f), seq)
'@
[IO.File]::WriteAllText((Join-Path $dir 'cache_scan.py'), $py, (New-Object Text.UTF8Encoding $false))
$cs = (& python (Join-Path $dir 'cache_scan.py') 2>&1) | Out-String
[IO.File]::WriteAllText((Join-Path $dir 'cache_scan.txt'), $cs, (New-Object Text.UTF8Encoding $false))
Say ('N3: files=' + (($cs -split "`n") | Where-Object { $_.Trim() }).Count)

# ---------- N4：报告 ----------
SetPhase 'N4'
$all = @(LoadResults)
$rep = @()
$rep += '# night2 report (v3)'
$rep += ''
$rep += ('deadline: ' + $deadline.ToString('yyyy-MM-dd HH:mm'))
$rep += ''
$rep += '## N0 attribution'
$rep += ('- ' + (Fmt $e1a))
$rep += ('- ' + (Fmt $e1b))
$rep += ('- ' + (Fmt $e2))
$rep += ('- H1=' + $h1 + ' H2=' + $h2 + ' H3=' + $h3)
$rep += ''
$rep += '## N2 same-run both sides'
$rep += ('- ' + (Fmt $n2r))
$rep += ''
$rep += '## ALL RESULTS'
foreach ($r in $all) { $rep += ('- ' + (Fmt $r)) }
$rep += ''
$rep += '## files'
$rep += '- night2.log / results.json / cache_scan.txt'
[IO.File]::WriteAllText((Join-Path $dir 'REPORT.md'), ($rep -join "`n"), (New-Object Text.UTF8Encoding $false))
Say ('REPORT written: ' + (Join-Path $dir 'REPORT.md'))
SetPhase 'DONE'
Say '================ night2 v3 end (DONE) ================'
