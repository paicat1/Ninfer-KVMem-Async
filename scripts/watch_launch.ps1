# Ninfer-KVMem-Async 守望者启动器（PowerShell 蓝窗；2026-10-14）
#   窗口纪律：可见 + 标题含任务与关闭条件；脚本退出即窗口自动关。
$host.UI.RawUI.WindowTitle = 'Ninfer-KVMem-Async守望者 [运行中] - 8h 后自关（关窗=停值守）'
Set-Location J:\ninfer-kvmem
& 'J:\ninfer-kvmem\scripts\valley_watch.ps1'
