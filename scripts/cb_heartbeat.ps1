# cb_heartbeat.ps1 -- CB 心跳（用户 2026-10-18 令：双智能体夜间互督，不卡死）
# 只做：更新 cb.heartbeat · 读 tele.heartbeat · 追加 heartbeat_log.md · 对方超时记督促。
# **绝对不做**：实验 / 加压 / 重启 / trace / git / 删除 / 改配置。
$ErrorActionPreference = 'Stop'
$hb = 'J:\ninfer-kvmem\evidence\heartbeat'
New-Item -ItemType Directory -Force -Path $hb | Out-Null
$now = Get-Date
Set-Content -Path (Join-Path $hb 'cb.heartbeat') -Value @(
    'agent=CB',
    ('updated=' + $now.ToString('yyyy-MM-dd HH:mm:ss')),
    'status=up',
    'mode=night-watch'
) -Encoding UTF8

$t = Join-Path $hb 'tele.heartbeat'
$tState = 'missing'
$tAge = -1
if (Test-Path $t) {
    $lm = (Get-Item $t).LastWriteTime
    $tAge = [math]::Round(($now - $lm).TotalMinutes, 1)
    if ($tAge -le 40) { $tState = 'up' } elseif ($tAge -le 60) { $tState = 'late' } else { $tState = 'stale' }
}
$line = '[' + $now.ToString('MM-dd HH:mm') + '] CB=up | TELE=' + $tState + ' (age=' + $tAge + 'm)'
Add-Content -Path (Join-Path $hb 'heartbeat_log.md') -Value $line -Encoding UTF8

if ($tState -eq 'stale') {
    $col = 'J:\ninfer-kvmem\docs\05-交接与值守\协作状态-当前待办与交接-20261016.md'
    if (Test-Path $col) {
        Add-Content -Path $col -Value ('', '## 心跳督促（CB 自动）',
            ('- ' + $now.ToString('MM-dd HH:mm') + ' CB 检测 TELE 心跳超时（age=' + $tAge + ' 分钟）=> 请 TELE 恢复；CB 不重启对方进程，不越权。'))
    }
}
Write-Output $line
