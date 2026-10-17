# watchdog_hunter.ps1 -- 守望者的守望者：猎人"静默死亡"告警（只读，不碰引擎）
#
# 由来（2026-10-17 06:1x）：本轮曾差点把"猎人在跑"误判成"空转盲窗"——
#   判据真值应以**猎人台账**为准；台账停更即猎人已死，而"无谷"会变成假象。
#   本仓被 S13 计数停摆、陈旧值拖 12h 咬过；常驻件"静默死"比"死"更危险。
#
# 行为：每 120 s 查一次最新 hunter_ledger 的 mtime；超过 StaleSec（默认 420 s = 2 个探针周期 + 余量）
#       ⇒ 在 evidence\cases\WATCHDOG_ALERT.txt 追加一行，并在共享队列可发现处落一条（告警行）。
param([int]$StaleSec = 420, [int]$MaxHours = 10)
Set-Location J:\ninfer-kvmem
$host.UI.RawUI.WindowTitle = 'HUNTER-WATCHDOG [running] -- alert if hunter ledger silent > 420s; close window = stop'
$cases = 'evidence\cases'
$alert = Join-Path $cases 'WATCHDOG_ALERT.txt'
$t0 = Get-Date
while (((Get-Date) - $t0).TotalHours -lt $MaxHours) {
    $led = Get-ChildItem $cases -File -Filter 'hunter_ledger_*' -ErrorAction SilentlyContinue |
           Sort-Object LastWriteTime -Descending | Select-Object -First 1
    # v2（2026-10-17 09:1x）：**扩展为看全部同伴**（原只看猎人 ⇒ 日志通道/采样器静默死无人知）
    $logwatch = Get-Item 'evidence\cases\logwatch_ledger.txt' -ErrorAction SilentlyContinue
    $sampler  = Get-ChildItem 'evidence\samples' -File -Filter 'windowwatch_*' -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $logwatchAlive = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*valley_logwatch*' }).Count
    $samplerAlive  = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*window_watch*' }).Count
    foreach ($pair in @(@('logwatch', $logwatch, $logwatchAlive, 300), @('sampler', $sampler, $samplerAlive, 300))) {
        $nm = $pair[0]; $it = $pair[1]; $al = [int]$pair[2]; $lim = [int]$pair[3]
        if ($al -eq 0) {
            $m = ('{0} | ALERT({1}): process not running' -f (Get-Date -Format 'MM-dd HH:mm:ss'), $nm)
            Add-Content -LiteralPath $alert -Value $m -Encoding UTF8; Write-Output $m
        } elseif ($it -and ((Get-Date) - $it.LastWriteTime).TotalSeconds -gt $lim) {
            $m = ('{0} | ALERT({1}): output silent {2}s (>{3}s)' -f (Get-Date -Format 'MM-dd HH:mm:ss'), $nm, [int]((Get-Date) - $it.LastWriteTime).TotalSeconds, $lim)
            Add-Content -LiteralPath $alert -Value $m -Encoding UTF8; Write-Output $m
        } else { Write-Output ('{0} | ok: {1} alive={2}' -f (Get-Date -Format 'HH:mm:ss'), $nm, $al) }
    }
    $alive = 0
    $alive = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*valley_hunter*' }).Count
    # 前置（TELE 第四轮建议）：引擎进程是否还在 —— 引擎没了是另一类告警，不能混为"猎人静默死亡"
    $eng = @(Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue).Count
    if ($led) {
        $age = ((Get-Date) - $led.LastWriteTime).TotalSeconds
        if ($eng -eq 0) {
            $l2 = ("{0} | ALERT(ENGINE): ninfer-serve not running | ledger={1}" -f (Get-Date -Format "MM-dd HH:mm:ss"), $led.Name)
            Add-Content -LiteralPath $alert -Value $l2 -Encoding UTF8; Write-Output $l2
        } elseif ($age -gt $StaleSec) {
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
