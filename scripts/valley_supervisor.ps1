# valley_supervisor.ps1 -- 闭环监工（2026-10-15 凌晨，用户令"别断线"）
#   循环：诱发器（6 周期，见谷即跑全量协议 A-B-A）→ 猎谷机（持续探针，见谷即跑短窗五臂）→ 回到诱发器。
#   纪律：可见窗口 + 标题含任务与关闭条件（关窗=停）；每轮写 journal；退出前复岗守望者。
param([string]$KvDtype = 'nvfp4', [int]$Pool = 81920, [int]$HunterMinutes = 30, [int]$Rounds = 12)
$host.UI.RawUI.WindowTitle = ('KVMem 谷攻关监工 [运行中] - 诱发/猎谷闭环（' + $Rounds + ' 轮后自关，关窗=停）')
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
J ('SUPERVISOR start (kv=' + $KvDtype + '/' + $Pool + ' hunter=' + $HunterMinutes + 'min rounds=' + $Rounds + ')')
for ($r = 1; $r -le $Rounds; $r++) {
    Write-Output ('==== 轮 ' + $r + '/' + $Rounds + '：诱发器（6 周期）' + (Get-Date -Format ' HH:mm:ss') + ' ====')
    J ('SUPERVISOR: 轮 ' + $r + ' 诱发器起')
    powershell -NoProfile -File scripts\valley_induce.ps1 -KvDtype $KvDtype -Pool $Pool -Cycles 6 | Out-Host
    J ('SUPERVISOR: 轮 ' + $r + ' 诱发器完，接猎谷机 ' + $HunterMinutes + 'min')
    Write-Output ('==== 轮 ' + $r + '：猎谷机 ' + $HunterMinutes + 'min ====')
    $h = Start-Process -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\valley_hunt.ps1', '-KvDtype', $KvDtype, '-Pool', $Pool, '-Hours', ([double]$HunterMinutes / 60.0) -PassThru -WindowStyle Minimized
    Start-Sleep -Seconds ($HunterMinutes * 60)
    if (-not $h.HasExited) { Stop-Process -Id $h.Id -Force }
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*valley_hunt*' -or $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
    Start-Sleep -Seconds 5
}
J ('SUPERVISOR end')
Write-Output '==== 监工完成，守望者复岗 ===='
Start-Process -WindowStyle Normal -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\watch_launch.ps1'
