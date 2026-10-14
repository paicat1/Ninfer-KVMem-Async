# pdl_aba.ps1 -- E1 决定性实验：PDL on/off/on 三臂 A-B-A（谷窗内判"target 段自旋"是否 PDL 依赖等待）
#   用法：powershell -NoProfile -File scripts\pdl_aba.ps1 -Tag valley1
#   判据：慢轮 target 段（及新增 target-split 的 prepare/verify 三分）在 off 臂是否塌回快带量级；
#         同时记录浅探针 decode 与深 60K 单轮墙钟。
param([string]$Tag = 'pdlrun', [string]$Model = 'swift15_iq3s_mtp.ninfer', [string]$KvDtype = 'rk8v4', [int]$Pool = 65536, [int]$Graph = 192)
Set-Location J:\ninfer-kvmem
$results = '.temp\pdl_aba_' + $Tag + '.txt'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*watch_launch*' -or $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('watcher stopped ' + $_.ProcessId) }
Start-Sleep -Seconds 2
$arms = @(
    @{ n = 'pdl_on';  off = $false },
    @{ n = 'pdl_off'; off = $true },
    @{ n = 'pdl_on2'; off = $false }
)
foreach ($a in $arms) {
    $tag = $Tag + '_' + $a.n
    Write-Output ('==== ARM ' + $a.n + ' (NINFER_PDL_OFF=' + [int]$a.off + ') ====')
    if ($a.off) { $env:NINFER_PDL_OFF = '1' } else {  =  }
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step7_split_20261014.exe' -Tag $tag -Model $Model -Depth 2 -Port 8094 -Graph $Graph -Pool $Pool -KvDtype $KvDtype -StepProfile 1 -Vision overlay | Out-Host
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $tag -WaitSec 240) -join ' '
    Write-Output ('  ready=' + $r)
    if ($r -notmatch 'READY') { Add-Content -LiteralPath $results -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ' + $a.n + ' | START-FAILED'); continue }
    $shallow = (python -X utf8 scripts\a2gate.py --arm ($tag + '_sh') --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1 | Where-Object { $_ -match 'run 1 round 1' }) -join ' '
    $deep = (python -X utf8 scripts\a2gate.py --arm ($tag + '_dp') --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 200 2>&1 | Where-Object { $_ -match 'run 1 round 1' }) -join ' '
    $stamps = (Select-String -Path ('logs\test_' + $tag + '.log') -Pattern 'spin-stamp|target-split' -Encoding UTF8 | Select-Object -Last 4 | ForEach-Object { $_.Line.Trim() }) -join ' ;; '
    Write-Output ('  shallow: ' + $shallow)
    Write-Output ('  deep60K: ' + $deep)
    Write-Output ('  stamps : ' + $stamps.Substring(0, [Math]::Min(300, $stamps.Length)))
    Add-Content -LiteralPath $results -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ' + $a.n + ' | PDL_OFF=' + [int]$a.off + ' | ' + $shallow + ' | ' + $deep + ' | ' + $stamps)
}
Write-Output '==== 恢复平台（rk8v4 + 守望者）===='
 = 
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step7_split_20261014.exe' -Tag valleywatch -Depth 2 -Port 8094 -Graph 192 -Pool 65536 -KvDtype rk8v4 -Model $Model -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
$r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 240) -join ' '
Write-Output ('  ready=' + $r)
Start-Process -WindowStyle Normal -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\watch_launch.ps1'
Start-Sleep -Seconds 8
Write-Output '== 台账 =='
Get-Content $results -Tail 4 -Encoding UTF8
