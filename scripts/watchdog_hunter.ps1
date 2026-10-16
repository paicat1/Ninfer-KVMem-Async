# watchdog_hunter.ps1 -- 守望者的守望者：猎人"静默死亡"告警（只读，不碰引擎）
#
# 由来（2026-10-17 06:1x）：本轮曾差点把"猎人在跑"误判成"空转盲窗"——
#   判据真值应以**猎人台账**为准；台账停更即猎人已死，而"无谷"会变成假象。
#   本仓被 S13 计数停摆、陈旧值拖 12h 咬过；常驻件"静默死"比"死"更危险。
#
# 行为：每 120 s 查一次最新 hunter_ledger 的 mtime；超过 StaleSec（默认 420 s = 2 个探针周期 + 余量）
#       ⇒ 在 .temp\cases\WATCHDOG_ALERT.txt 追加一行，并在共享队列可发现处落一条（告警行）。
param([int]$StaleSec = 420, [int]$MaxHours = 10)
Set-Location J:\ninfer-kvmem
$host.UI.RawUI.WindowTitle = 'HUNTER-WATCHDOG [running] -- alert if hunter ledger silent > 420s; close window = stop'
$cases = '.temp\cases'
$alert = Join-Path $cases 'WATCHDOG_ALERT.txt'
$t0 = Get-Date
while (((Get-Date) - $t0).TotalHours -lt $MaxHours) {
    $led = Get-ChildItem $cases -File -Filter 'hunter_ledger_*' -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $alive = 0
    $alive = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*valley_hunter*' }).Count
    if ($led) {
        $age = ((Get-Date) - $led.LastWriteTime).TotalSeconds
        if ($age -gt $StaleSec) {
            $line = ('{0} | ALERT: hunter ledger silent {1}s (>{2}s) | proc={3} | ledger={4}' -f
                     (Get-Date -Format 'MM-dd HH:mm:ss'), [int]$age, $StaleSec, $alive, $led.Name)
            Add-Content -LiteralPath $alert -Value $line -Encoding UTF8
            Write-Output $line
        } else {
            Write-Output ('{0} | ok: ledger age {1}s, hunter proc={2}' -f (Get-Date -Format 'HH:mm:ss'), [int]$age, $alive)
        }
    } else {
        $line = ('{0} | ALERT: no hunter ledger found | proc={1}' -f (Get-Date -Format 'MM-dd HH:mm:ss'), $alive)
        Add-Content -LiteralPath $alert -Value $line -Encoding UTF8
        Write-Output $line
    }
    Start-Sleep -Seconds 120
}
Write-Output 'watchdog stop (max hours reached)'
