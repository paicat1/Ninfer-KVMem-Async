# valley_load_incidence.ps1 -- load-plus-incidence comparison (S12)
param(
    [int]$WindowMinutes = 40,
    [int]$Pairs = 6,
    [int]$LoadKb = 60,
    [int]$LoadRounds = 8,
    [int]$LoadMaxTokens = 200,
    [string]$Exe     = 'engine\lineage\I3b_step10_rtpdl_20261015.exe',
    [string]$Model   = 'Qwen3.8-27B-Coder390-EfficientThink-Q2LynnStyle-MTP.mtp-iq4nl.vision.ninfer',
    [string]$KvDtype = 'rk2v4-e8',
    [int]$Pool       = 65536,
    [int]$VerifySlow = 30,
    [int]$DecodeSlow = 60
)
$host.UI.RawUI.WindowTitle = 'KVMem 负载+发生率对照 [运行中] - ON/OFF 各 ' + $WindowMinutes + ' 分钟 × ' + $Pairs + ' 对（多轮增长跨池负载）；关窗=停'
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$log     = '.temp\loadinc_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.txt'
$engineLog = 'logs\test_valleywatch.log'
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | LOADINC: ' + $m) }
function Say([string]$m) { Write-Output $m; Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }

function Start-LoadEngine([bool]$off) {
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    for ($w = 1; $w -le 15; $w++) { if (-not (Get-Process ninfer-serve -ErrorAction SilentlyContinue)) { break }; Start-Sleep -Seconds 2 }
    Start-Sleep -Seconds 3
    if ($off) { $env:NINFER_PDL_OFF = '1' } else { [Environment]::SetEnvironmentVariable('NINFER_PDL_OFF', $null, 'Process') }
    $env:NINFER_PDL_FLAG_FILE = 'J:\ninfer-kvmem\.temp\pdl_off.flag'
    $env:NINFER_MAT_DEBUG = '1'
    Remove-Item -LiteralPath 'J:\ninfer-kvmem\.temp\pdl_off.flag' -ErrorAction SilentlyContinue
    $ok = $false
    for ($try = 1; $try -le 4 -and -not $ok; $try++) {
        powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe $Exe -Tag valleywatch -Model $Model -KvDtype $KvDtype -Pool $Pool -Graph 64 -Vision overlay -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
        $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 180) -join ' '
        if ($r -match 'READY') { $ok = $true } else { Start-Sleep -Seconds 10 }
    }
    $rep = (Select-String -Path $engineLog -Pattern 'PDL: programmatic' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line.Trim() })
    $repTxt = '(no self-report)'
    if ($rep) { $repTxt = $rep }
    Say ('engine start (pdl_off=' + [int]$off + ') ready=' + $ok + ' | ' + $repTxt)
    return $ok
}
function Get-LastVerify { $l = ''; try { $l = (Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line }) } catch { }; if ($l -match 'verify=([\d.]+)') { return [double]$Matches[1] }; return -1.0 }
function Get-StampCount { return @(Select-String -Path $engineLog -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue).Count }
function Probe([string]$arm) {
    $out = ''
    try { $out = (python -X utf8 scripts\a2gate.py --arm $arm --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join "`n" } catch { }
    $dec = -1.0; $wall = -1.0
    if ($out -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    return @($dec, $wall)
}

J ('LOADINC start (window=' + $WindowMinutes + 'min pairs=' + $Pairs + ' load=' + $LoadKb + 'KBx' + $LoadRounds + ' rounds)')
$script:stampPrev = 0
$summary = @()
for ($p = 1; $p -le $Pairs; $p++) {
    foreach ($off in @(0, 1)) {
        $offBool = [bool]$off
        $started = Start-LoadEngine $offBool
        if (-not $started) { Say 'engine failed to start; skipping'; continue }
        $t0 = Get-Date; $cyc = 0; $valley = 0; $n = 0; $deep = 0; $loadSlow = 0; $loadN = 0
        while (((Get-Date) - $t0).TotalMinutes -lt $WindowMinutes) {
            $cyc++
            $nonce = 'li_p' + $p + '_' + $off + '_' + $cyc + '_' + (Get-Date -Format 'HHmmss')
            $outL = (python -X utf8 scripts\a2gate.py --arm ('load' + $p + '_' + $off + '_' + $cyc) --port 8094 --runs 1 --rounds $LoadRounds --filler-kb $LoadKb --max-tokens $LoadMaxTokens --nonce $nonce 2>&1) -join "`n"
            $rds = [regex]::Matches($outL, 'run 1 round (\d+)\s+[\d.]+s\s+decode=([\d.]+)')
            foreach ($m in $rds) { $loadN++; if ([double]$m.Groups[2].Value -lt 60) { $loadSlow++ }; Say ('  load r' + $m.Groups[1].Value + ' decode=' + $m.Groups[2].Value) }
            if ($cyc % 3 -eq 0) {
                $outLong = (python -X utf8 scripts\a2gate.py --arm ('loadlong' + $p + '_' + $off + '_' + $cyc) --port 8094 --runs 1 --rounds 1 --filler-kb $LoadKb --max-tokens 2500 --nonce $nonce 2>&1) -join "`n"
                if ($outLong -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $loadN++; if ([double]$Matches[2] -lt 60) { $loadSlow++ }; Say ('  loadlong wall=' + $Matches[1] + 's decode=' + $Matches[2]) }
            }
            $pr = Probe ('lip' + $p + '_' + $off + '_' + $cyc)
            $dec = $pr[0]; $wall = $pr[1]
            $ver = Get-LastVerify
            $stampN = Get-StampCount
            $fresh = ($stampN -gt $script:stampPrev); $script:stampPrev = $stampN
            if (-not $fresh) { $ver = -1.0 }
            $n++
            $isValley = (($fresh -and $ver -ge $VerifySlow) -or ($dec -gt 0 -and $dec -lt $DecodeSlow))
            if ($isValley) { $valley++ }
            if ($fresh -and $ver -ge 100) { $deep++ }
            Say ('pair' + $p + ' pdl=' + [int]$off + ' cyc' + $cyc + ' probe decode=' + $dec + ' wall=' + $wall + ' verify=' + $ver + '(fresh=' + $fresh + ') valley=' + [int]$isValley + ' | loadSlow=' + $loadSlow + '/' + $loadN)
            Start-Sleep -Seconds 10
        }
        $rate = $(if ($n -gt 0) { [math]::Round(100.0 * $valley / $n, 1) } else { -1 })
        $lrate = $(if ($loadN -gt 0) { [math]::Round(100.0 * $loadSlow / $loadN, 1) } else { -1 })
        Say ('WINDOW pair=' + $p + ' pdl_off=' + [int]$off + ' n=' + $n + ' valley=' + $valley + ' rate=' + $rate + '% deep=' + $deep + ' | load rounds=' + $loadN + ' loadSlow=' + $loadSlow + ' (' + $lrate + '%)')
        $summary += ('pair=' + $p + ' pdl_off=' + [int]$off + ' n=' + $n + ' valley=' + $valley + ' rate=' + $rate + '% deep=' + $deep + ' loadSlow=' + $loadSlow + '/' + $loadN)
    }
}
Say '==== SUMMARY ===='
$summary | ForEach-Object { Say '  ' + $_ }
J ('LOADINC done -> ' + $log)
