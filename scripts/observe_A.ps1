param(
    [int]$Minutes = 180,
    [int]$PcAtMin = 90,
    [int]$MemholdGiB = 32,
    [int]$MemholdSec = 300,
    [int]$LogCapMB = 500
)
# observe_A.ps1 -- step 3 group A: engine + one light probe per minute, no other tooling.
# Primary criterion (pre-registered): probe decode < 60.
# Secondary criterion (pre-registered): max verify among NEWLY APPENDED log lines >= 30 ms.
# Positive control at T+PcAtMin: controlled host-memory pressure (memhold), which also replicates
# the n=1 host-memory candidate from 夜研-3 section 5.2.
# Protection: stop if the engine log exceeds LogCapMB (verbose logging is unbounded otherwise).
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$led = ".temp\observeA_$ts.txt"
$LOG = 'logs\test_valleywatch.log'
$state = @{ offset = 0; size0 = 0 }
if (Test-Path $LOG) { $state.offset = (Get-Item $LOG).Length; $state.size0 = $state.offset }
function Say($t) { $line = (Get-Date -Format 'HH:mm:ss') + ' | ' + $t; Add-Content -LiteralPath $led -Encoding UTF8 -Value $line; Write-Host $line }
function ProbeOnce() {
    $o = (python -X utf8 scripts\a2gate.py --arm obs --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n"
    $dec = -1; $wall = -1
    if ($o -match '([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    elseif ($o -match 'decode=([\d.]+)') { $dec = [double]$Matches[1] }
    return @($dec, $wall)
}
function FreshVerify() {
    # returns @(max_verify, n_new_lines)
    if (-not (Test-Path $LOG)) { return @(-1, 0) }
    $sz = (Get-Item $LOG).Length
    if ($sz -lt $state.offset) { $state.offset = 0 }          # rotation
    if ($sz -le $state.offset) { return @(-1, 0) }
    $fs = [System.IO.File]::Open($LOG, 'Open', 'Read', 'ReadWrite')
    try {
        $fs.Seek($state.offset, 'Begin') | Out-Null
        $buf = New-Object byte[] ($sz - $state.offset)
        $n = $fs.Read($buf, 0, $buf.Length)
        $state.offset = $sz
        $txt = [System.Text.Encoding]::UTF8.GetString($buf, 0, $n)
    } finally { $fs.Close() }
    $mx = -1.0; $nl = 0
    foreach ($l in ($txt -split "`n")) {
        $nl++
        if ($l -match 'target-split.*verify=([\d.]+)') { $v = [double]$Matches[1]; if ($v -gt $mx) { $mx = $v } }
    }
    return @($mx, $nl)
}
Say ("OBSERVE-A start: minutes=$Minutes pcAt=$PcAtMin memhold=${MemholdGiB}GiB x ${MemholdSec}s logCap=${LogCapMB}MB")
Say ("  criteria: primary decode<60 | secondary fresh verify>=30ms | ledger=$led")
$pcFired = $false
$valleyMin = 0; $deepMin = 0; $vdeepMin = 0; $rows = 0
$t0 = Get-Date
for ($i = 1; $i -le $Minutes; $i++) {
    $sz = if (Test-Path $LOG) { (Get-Item $LOG).Length } else { 0 }
    if ($sz -gt ($LogCapMB * 1MB)) { Say ("STOP: engine log exceeded ${LogCapMB}MB (protection) at minute $i"); break }
    $p = ProbeOnce
    $fv = FreshVerify
    $g = (nvidia-smi --query-gpu=utilization.gpu,power.draw,memory.used --format=csv,noheader,nounits) -replace '\s', ''
    $note = ''
    $sinceMin = [int]((Get-Date) - $t0).TotalMinutes
    if (-not $pcFired -and $sinceMin -ge $PcAtMin) {
        $pcFired = $true
        Start-Process -WindowStyle Normal -FilePath python -ArgumentList '-X', 'utf8', '.temp\memhold.py', ([string]$MemholdGiB), ([string]$MemholdSec)
        $note = 'POSITIVE-CONTROL memhold applied'
        Say ("  [T+" + $sinceMin + "m] POSITIVE CONTROL: memhold $MemholdGiB GiB x ${MemholdSec}s")
    } elseif ($pcFired -and (Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*memhold*' })) {
        $note = 'memhold-active'
    }
    $v = if ($fv[0] -ge 0) { $fv[0] } else { 'stale' }
    $isValley = ($p[0] -ge 0 -and $p[0] -lt 60) -or ($fv[0] -ge 100)
    $isDeep = ($fv[0] -ge 226) -or ($p[0] -ge 0 -and $p[0] -lt 20)
    $isVDeep = ($fv[0] -ge 500)
    if ($isValley) { $valleyMin++ }
    if ($isDeep) { $deepMin++ }
    if ($isVDeep) { $vdeepMin++ }
    $rows++
    $mark = ''
    if ($isValley) { $mark = ' <<VALLEY' }
    Say ("m$i decode=" + $p[0] + " wall=" + $p[1] + "s verify=" + $v + " new=" + $fv[1] + " | gpu=" + $g + " | logMB=" + [math]::Round($sz / 1MB, 1) + " " + $note + $mark)
    Start-Sleep -Seconds 55
}
Say ("OBSERVE-A end: rows=$rows valleyMinutes=$valleyMin deepMinutes=$deepMin vdeepMinutes=$vdeepMin pcFired=$pcFired")
Say ("  AMENDMENT (recorded): secondary criterion raised from verify>=30 to >=100 ms because the 30 ms gate was written for the old print gate (slow rounds only) and misfires under VERBOSE where healthy rounds print at 18-30 ms; bands: valley>=100, deep>=226, vdeep>=500.")
