# pdl_aba_rt.ps1 -- RUNTIME PDL A-B-A (no engine restarts)
#   Why: measured 2026-10-15 00:57-00:59 -- the valley was live at 00:57:51 (verify 116 ms) and gone
#   by 00:59:07 when the first restarted arm probed. A restart resets the state we are measuring,
#   so the restart-based A-B-A can never observe it. S10 teaches the engine to read a flag file at
#   runtime (S10: pdl_kill_switch consults NINFER_PDL_FLAG_FILE / .temp\pdl_off.flag once per second).
#   Sequence: probe -> toggle -> probe -> ... over 5 phases: ON, OFF, ON, OFF, ON (starting from ON).
param(
    [string]$Tag = 'rt',
    [int]$ProbesPerPhase = 2,
    [string]$FlagFile = 'J:\ninfer-kvmem\.temp\pdl_off.flag',
    [int]$SettleSeconds = 3
)
$host.UI.RawUI.WindowTitle = 'KVMem 运行期 A-B-A [运行中] - 不重启切 PDL；关窗=停'
Set-Location J:\ninfer-kvmem
$log = 'logs\test_valleywatch.log'
$ledger = '.temp\pdl_rt_' + $Tag + '.txt'
function Say([string]$m) { Write-Output $m; Add-Content -LiteralPath $ledger -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
function Probe([string]$arm) {
    $out = ''
    try { $out = (python -X utf8 scripts\a2gate.py --arm $arm --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1) -join "`n" } catch { }
    $dec = -1.0; $wall = -1.0
    if ($out -match 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') { $wall = [double]$Matches[1]; $dec = [double]$Matches[2] }
    $l = ''
    try { $l = (Select-String -Path $log -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line }) } catch { }
    $ver = -1.0
    if ($l -match 'verify=([\d.]+)') { $ver = [double]$Matches[1] }
    return @($dec, $wall, $ver)
}
function Set-Pdl([bool]$off, [string]$phase) {
    if ($off) { [System.IO.File]::WriteAllText($FlagFile, "1`n") } else { Remove-Item -LiteralPath $FlagFile -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds $SettleSeconds
    $sw = (Select-String -Path $log -Pattern 'PDL: runtime switch' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line.Trim() })
    Say ('phase ' + $phase + ' flag=' + [int]$off + ' engine-said=' + $(if ($sw) { $sw } else { '(no switch line yet)' }))
}
Say ('RT-ABA start tag=' + $Tag + ' probes/phase=' + $ProbesPerPhase + ' flag=' + $FlagFile)
$phases = @(@{n = 'on1'; off = $false }, @{n = 'off2'; off = $true }, @{n = 'on3'; off = $false }, @{n = 'off4'; off = $true }, @{n = 'on5'; off = $false })
foreach ($ph in $phases) {
    Set-Pdl $ph.off $ph.n
    for ($i = 1; $i -le $ProbesPerPhase; $i++) {
        $r = Probe ($Tag + '_' + $ph.n + '_p' + $i)
        Say ('  ' + $ph.n + ' probe' + $i + ' decode=' + $r[0] + ' wall=' + $r[1] + 's verify=' + $r[2] + 'ms')
    }
}
# leave PDL ON
Remove-Item -LiteralPath $FlagFile -ErrorAction SilentlyContinue
Say ('RT-ABA done -> ' + $ledger)
