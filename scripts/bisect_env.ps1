param([string]$Arms = 'A,B,C', [int]$FillerKb = 45, [int]$MaxTokens = 200)
# bisect_env.ps1 -- zero-code environment bisection for the decode-degradation state (2026-10-14).
# Arms: A baseline | B NINFER_TERNARY_KVMEM_SCORE=0 | C --spec k0 | D --host-state-slots 0 | E graph 0 (pool 40960)
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
$log = '.temp\bisect_20261014.txt'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('watcher stopped ' + $_.ProcessId) }
Start-Sleep -Seconds 2
foreach ($arm in ($Arms -split ',')) {
    $arm = $arm.Trim()
    $spec = 'mtp'; $pool = 65536; $graph = 64; $extra = ''; $desc = ''
    if ($arm -eq 'A') { $desc = 'baseline (step3b, no knob)' }
    elseif ($arm -eq 'B') { $desc = 'NINFER_TERNARY_KVMEM_SCORE=0'; $env:NINFER_TERNARY_KVMEM_SCORE = '0' }
    elseif ($arm -eq 'C') { $desc = 'spec k0 (MTP off)'; $spec = 'k0' }
    elseif ($arm -eq 'D') { $desc = 'host-state-slots 0'; $extra = '--host-state-slots,0' }
    elseif ($arm -eq 'E') { $desc = 'graph 0 (eager, pool 40960)'; $graph = 0; $pool = 40960 }
    Write-Output ('==== ARM ' + $arm + ' : ' + $desc)
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    $sa = @('-NoProfile', '-File', 'scripts\engine_ctl.ps1', '-Action', 'start', '-Exe', 'engine\lineage\I3b_step3b_20261014.exe',
        '-Tag', ('bis_' + $arm), '-Depth', '2', '-Port', '8094', '-Pool', [string]$pool, '-Graph', [string]$graph,
        '-Spec', $spec, '-StepProfile', '0')
    if ($extra -ne '') { $sa += @('-Extra', $extra) }
    powershell @sa | Out-Host
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag ('bis_' + $arm) -WaitSec 240) -join ' '
    Write-Output ('ready=' + $r)
    if ($r -match 'READY') {
        $out = python -X utf8 scripts\a2gate.py --arm ('bis_' + $arm) --port 8094 --runs 1 --rounds 1 --filler-kb $FillerKb --max-tokens $MaxTokens 2>&1
        $out | ForEach-Object { Write-Output $_ }
        $parsed = python -X utf8 -c "import json;d=json.load(open('.temp/gate_bis_$arm.json',encoding='utf-8'));r=d['runs'][0];t=r['timings'];u=r['usage'];print('%.1f %d %.0f %.1f' % (t['predicted_per_second'], u['prompt_tokens_details']['cached_tokens'], t['prompt_ms'], r['elapsed_s']))"
        Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' arm=' + $arm + ' | ' + $desc + ' | decode/cached/prompt_ms/wall = ' + (($parsed + '') -replace "`r|`n", ' '))
        Write-Output ('-> ' + $parsed)
    } else {
        Add-Content -LiteralPath $log -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' arm=' + $arm + ' | ' + $desc + ' | START-FAILED')
        Write-Output ('ARM ' + $arm + ' START-FAILED')
    }
    if ($arm -eq 'B') { Remove-Item Env:NINFER_TERNARY_KVMEM_SCORE -ErrorAction SilentlyContinue }
}
Write-Output '== bisect log 尾 =='
Get-Content $log -Tail 8 -Encoding UTF8
