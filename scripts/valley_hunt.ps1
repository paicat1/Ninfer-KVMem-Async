# valley_hunt.ps1 -- 主动猎谷机（2026-10-14 夜，用户令"抓紧时间攻关"）
#   逻辑：每 PollSec 秒跑一条**短探针**（浅 11K / 60 输出）；decode<80 判为谷 ⇒ 立即跑
#        **快档五臂 A-B-A**（pdl_aba.ps1 -Pattern on,off,on,off,on -SkipDeep，~30s/臂）
#        ⇒ 三明治（on/off 交替）可判 PDL 因果，且每臂日志带引擎自报 "PDL: ... ENABLED/DISABLED"。
#   纪律：窗口可见 + 标题含任务与关闭条件（关窗=停）；干完自动复岗守望者；台账 .temp\hunt_<日期>.txt
param([string]$KvDtype = 'nvfp4', [int]$Pool = 81920, [int]$PollSec = 20, [int]$MaxCaptures = 6, [double]$Hours = 6)
$host.UI.RawUI.WindowTitle = ('KVMem 猎谷机 [运行中] - 见谷即跑 PDL A-B-A（最多 ' + $MaxCaptures + ' 次 / ' + $Hours + 'h，关窗=停）')
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$ledger = '.temp\hunt_' + (Get-Date -Format 'yyyyMMdd') + '.txt'
$deadline = (Get-Date).AddHours($Hours)
$captures = 0
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*watch_launch*' -or $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
J ('HUNT start (poll=' + $PollSec + 's max=' + $MaxCaptures + ' kv=' + $KvDtype + '/' + $Pool + ')')
$probeNo = 0
while ((Get-Date) -lt $deadline -and $captures -lt $MaxCaptures) {
    $probeNo++
    $out = (python -X utf8 scripts\a2gate.py --arm hunt_probe --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join ' '
    $dec = 0.0
    $line = ($out -split "`n" | Where-Object { $_ -match 'run 1 round 1' } | Select-Object -First 1)
    if ($line -match 'decode=([0-9.]+)') { $dec = [double]$Matches[1] }
    $tag = Get-Date -Format 'HH:mm:ss'
    Write-Output ('  [' + $tag + '] probe#' + $probeNo + ' decode=' + $dec)
    if ($dec -lt 80.0 -and $dec -gt 0.0) {
        J ('HUNT: 谷检出（decode=' + $dec + '）-> 快档五臂 A-B-A')
        $atag = 'hunt' + (Get-Date -Format 'HHmm')
        powershell -NoProfile -File scripts\pdl_aba.ps1 -Pattern 'on,off,on,off,on' -SkipDeep -KvDtype $KvDtype -Pool $Pool -Tag $atag | Out-Host
        $captures++
        Add-Content -LiteralPath $ledger -Encoding UTF8 -Value ('=== 捕获 #' + $captures + ' @ ' + (Get-Date -Format 'MM-dd HH:mm:ss') + '（触发 decode=' + $dec + '）见 .temp\pdl_aba_' + $atag + '.txt')
        J ('HUNT: 捕获完成 #' + $captures + '（台账 .temp\pdl_aba_' + $atag + '.txt）')
        Start-Sleep -Seconds 30
    } else {
        Start-Sleep -Seconds $PollSec
    }
}
J ('HUNT end (probes=' + $probeNo + ' captures=' + $captures + ')')
Write-Output '==== 捕获台账 ===='
Get-Content $ledger -Encoding UTF8 -ErrorAction SilentlyContinue
Write-Output '== 守望者复岗 =='
Start-Process -WindowStyle Normal -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\watch_launch.ps1'
