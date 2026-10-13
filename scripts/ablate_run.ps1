param([string]$Arms = 'A', [int]$FillerKb = 45, [int]$MaxTokens = 200)
$ErrorActionPreference = 'Continue'
Set-Location J:\ninfer-kvmem
$results = '.temp\ablation_20261014.txt'
$defs = @{
    'A' = @{ graph = 64;    pool = 65536; spec = 'mtp'; note = 'baseline: graph64 + mtp + pool65536' }
    'B' = @{ graph = 0;     pool = 40960; spec = 'mtp'; note = 'graph OFF (eager; pool 40960 because eager needs +426MB runtime reservation)' }
    'C' = @{ graph = 64;    pool = 32768; spec = 'mtp'; note = 'pool 32768 (half)' }
    'D' = @{ graph = 64;    pool = 65536; spec = 'k0';  note = 'spec k0 (MTP off)' }
}
foreach ($arm in ($Arms -split ',')) {
    $arm = $arm.Trim()
    if (-not $defs.ContainsKey($arm)) { Write-Output ('unknown arm ' + $arm); continue }
    $d = $defs[$arm]
    $tag = 'abl_' + $arm
    Write-Output ('==== ARM ' + $arm + ' : ' + $d.note + ' (filler=' + $FillerKb + 'KB max=' + $MaxTokens + ')')
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Host
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step3b_20261014.exe' -Tag $tag -Depth 2 -Port 8094 -Pool $d.pool -Graph $d.graph -Spec $d.spec -StepProfile 0 | Out-Host
    $ready = powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $tag -WaitSec 300
    $rtext = ($ready -join ' ')
    Write-Output ('waitready: ' + $rtext)
    if ($rtext -notmatch 'READY') {
        Add-Content -LiteralPath $results -Encoding UTF8 -Value ('2026-10-14 arm=' + $arm + ' START-FAILED ' + $d.note)
        continue
    }
    $out = python -X utf8 scripts\a2gate.py --arm $tag --port 8094 --runs 1 --rounds 1 --filler-kb $FillerKb --max-tokens $MaxTokens
    $out | ForEach-Object { Write-Output $_ }
    Add-Content -LiteralPath $results -Encoding UTF8 -Value ('2026-10-14 arm=' + $arm + ' | ' + $d.note + ' | ' + ($out -join ' ;; '))
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Host
}
Write-Output '==== results file'
Get-Content $results -Tail 12
