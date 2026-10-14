# pdl_aba.ps1 -- E1 决定性实验：PDL on/off/on 三臂 A-B-A（谷窗内判"target 段自旋"是否 PDL 依赖等待）
#   用法：powershell -NoProfile -File scripts\pdl_aba.ps1 -Tag valley1
#   判据：慢轮 target 段（及新增 target-split 的 prepare/verify 三分）在 off 臂是否塌回快带量级；
#         同时记录浅探针 decode 与深 60K 单轮墙钟。
param([string]$Pattern = 'on,off,on', [switch]$SkipDeep, [switch]$NoAbortIfHealthy, [string]$Tag = 'pdlrun', [string]$Model = 'swift15_iq3s_mtp.ninfer', [string]$KvDtype = 'rk8v4', [int]$Pool = 65536, [int]$Graph = 192)
Set-Location J:\ninfer-kvmem
$results = '.temp\pdl_aba_' + $Tag + '.txt'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*watch_launch*' -or $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output ('watcher stopped ' + $_.ProcessId) }
Start-Sleep -Seconds 2
# 两套协议（2026-10-14 夜，用户裁决：默认全量、短窗须标注）——
#   · 全量协议（默认）：3 臂 on,off,on，每臂 **浅探针 + 深 60K 探针**（~90s/臂）
#   · 短窗协议（-SkipDeep）：只浅探针，臂数加到 5（on/off/on/off/on）以补偿（~30s/臂）；
#     **仅当实测谷窗短于全量协议时长时使用**；台账里写明用的是哪套。
$arms = @()
$idx = 0
foreach ($p in ($Pattern -split ',')) {
    $idx++
    $arms += @{ n = ('pdl_' + $p.Trim() + $idx); off = ($p.Trim() -eq 'off') }
}
$armNo = 0
foreach ($a in $arms) {
    $armNo++
    $tag = $Tag + '_' + $a.n
    Write-Output ('  [arm ' + $armNo + '/' + $arms.Count + '] ' + $a.n)
    Write-Output ('==== ARM ' + $a.n + ' (NINFER_PDL_OFF=' + [int]$a.off + ') ====')
    if ($a.off) { $env:NINFER_PDL_OFF = '1' } else { [Environment]::SetEnvironmentVariable('NINFER_PDL_OFF', $null, 'Process') }
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
    powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step8_pdlreport_20261014.exe' -Tag $tag -Model $Model -Depth 2 -Port 8094 -Graph $Graph -Pool $Pool -KvDtype $KvDtype -StepProfile 1 -Vision overlay | Out-Host
    $r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag $tag -WaitSec 240) -join ' '
    Write-Output ('  ready=' + $r)
    if ($r -notmatch 'READY') { Add-Content -LiteralPath $results -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ' + $a.n + ' | START-FAILED'); continue }
    $shallow = (python -X utf8 scripts\a2gate.py --arm ($tag + '_sh') --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 200 2>&1 | Where-Object { $_ -match 'run 1 round 1' }) -join ' '
    $deep = ''
    if (-not $SkipDeep) {
        $deep = (python -X utf8 scripts\a2gate.py --arm ($tag + '_dp') --port 8094 --runs 1 --rounds 1 --filler-kb 240 --max-tokens 200 2>&1 | Where-Object { $_ -match 'run 1 round 1' }) -join ' '
    }
    $pdlrep = (Select-String -Path ('logs\test_' + $tag + '.log') -Pattern 'PDL: programmatic' -Encoding UTF8 | Select-Object -First 1 | ForEach-Object { $_.Line.Trim() })
    $stamps = (Select-String -Path ('logs\test_' + $tag + '.log') -Pattern 'spin-stamp|target-split' -Encoding UTF8 | Select-Object -Last 4 | ForEach-Object { $_.Line.Trim() }) -join ' ;; '
    $stamps = $pdlrep + ' ;; ' + $stamps
    $proto = if ($SkipDeep) { '短窗协议(浅探针x5臂)' } else { '全量协议(浅+深)' }
    Write-Output ('  shallow: ' + $shallow)
    Write-Output ('  deep60K: ' + $deep)
    Write-Output ('  stamps : ' + $stamps.Substring(0, [Math]::Min(300, $stamps.Length)))
    $envActual = if ($null -eq $env:NINFER_PDL_OFF -or $env:NINFER_PDL_OFF -eq '') { '0' } else { $env:NINFER_PDL_OFF }
    Add-Content -LiteralPath $results -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ' + $a.n + ' | 协议=' + $proto + ' 意图=' + [int]$a.off + ' 实际env=' + $envActual + ' | ' + $shallow + ' | ' + $deep + ' | ' + $stamps)
    # 首臂健康 ⇒ 谷已过（自愈）⇒ 提前收场，不烧余下臂（2026-10-14 夜教训：臂 1 慢、臂 2/3 全快 = 无效捕获）
    if (-not $NoAbortIfHealthy -and $armNo -eq 1 -and $shallow -match 'decode=([0-9.]+)' -and [double]$Matches[1] -ge 100) {
        Write-Output ('  ABORT: 首臂健康（decode=' + $Matches[1] + '）⇒ 判定谷已过，跳过余下臂')
        Add-Content -LiteralPath $results -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' ABORT: 首臂健康 decode=' + $Matches[1] + ' -> 跳过余下臂（无效捕获，等下一窗）')
        break
    }
}
Write-Output '==== 恢复平台（rk8v4 + 守望者）===='
[Environment]::SetEnvironmentVariable('NINFER_PDL_OFF', $null, 'Process')  # 2026-10-14: 真 unset（避开引号展开与 safe-delete 护栏）
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action stop | Out-Null
powershell -NoProfile -File scripts\engine_ctl.ps1 -Action start -Exe 'engine\lineage\I3b_step8_pdlreport_20261014.exe' -Tag valleywatch -Depth 2 -Port 8094 -Graph 192 -Pool 65536 -KvDtype rk8v4 -Model $Model -StepProfile 1 -Extra '--request-log-jsonl,.temp\reqlog_watch.jsonl,--request-log-max-mib,128,--request-log-keep,2' | Out-Null
$r = (powershell -NoProfile -File scripts\engine_ctl.ps1 -Action waitready -Tag valleywatch -WaitSec 240) -join ' '
Write-Output ('  ready=' + $r)
Start-Process -WindowStyle Normal -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\watch_launch.ps1'
Start-Sleep -Seconds 8
Write-Output '== 台账 =='
Get-Content $results -Tail 4 -Encoding UTF8
