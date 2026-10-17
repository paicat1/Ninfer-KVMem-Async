# install_window_audit_task.ps1 -- 安装"窗口审计"计划任务（每 5 分钟）
#
# 目的（用户 2026-10-17 授权）：让窗口纪律的审计层**不依赖任何人记得**地运行。
#   任务 → scripts\audit_windows_task.ps1 → audit_windows.py --quiet
#   违规 ⇒ 写 evidence\audits\VIOLATION_window_*.md；失败 ⇒ 记 scheduled_task.log
#
# 写法纪律（2026-10-17 踩坑）：**不用反引号续行、不在续行处写行内注释** —— 否则语句会被切断。
#
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_window_audit_task.ps1
$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
$taskName = 'NInferWindowAudit'
$wrapper = Join-Path $root 'scripts\audit_windows_task.ps1'

$arg = '-NoProfile -ExecutionPolicy Bypass -File "' + $wrapper + '"'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg

$daily = New-ScheduledTaskTrigger -Daily -At '00:00'
$once = New-ScheduledTaskTrigger -Once -At '00:00' -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 1)
$daily.Repetition = $once.Repetition

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$desc = 'T-WINDOW audit layer: every five minutes check that our process windows are visible and not minimised; a violation writes evidence\audits\VIOLATION_window_*.md'

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $daily -Settings $settings -Description $desc -Force | Out-Null

$t = Get-ScheduledTask -TaskName $taskName
Write-Output ('registered: ' + $taskName)
Write-Output ('  state  = ' + $t.State)
Write-Output ('  action = ' + $t.Actions[0].Execute + ' ' + $t.Actions[0].Arguments)
Write-Output ('  trigger= daily 00:00, repeat every 5 min for 1 day (renews daily)')
