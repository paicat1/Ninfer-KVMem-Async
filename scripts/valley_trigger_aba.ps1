# valley_trigger_aba.ps1 -- 谷窗自动触发 PDL A-B-A（2026-10-14；用户令"都办"）
#   监视 .temp\state_journal.txt：出现 STATE=SLOW（或探针 decode<80）即自动跑 scripts\pdl_aba.ps1（on/off/on 三臂），
#   留证到 .temp\pdl_aba_<tag>.txt；冷却 CooldownSec 后再允许下一次捕获；捕获 MaxCaptures 次或到 Hours 后自关。
#   ⚠️ 触发时会停守望者并重启引擎 3 次（约 6-7 分钟，服务短暂不可用）——用户在用机时请关窗停止。
#   窗口纪律：可见窗口 + 标题含任务与关闭条件；脚本退出即窗口自动关闭。
param([int]$MaxCaptures = 3, [double]$Hours = 8, [int]$PollSec = 60, [int]$CooldownSec = 900)
$host.UI.RawUI.WindowTitle = ('KVMem 谷窗A-B-A触发器 [值守中] - 捕获 ' + $MaxCaptures + ' 次后自关（关窗=停值守）')
Set-Location J:\ninfer-kvmem
$journal = '.temp\state_journal.txt'
$deadline = (Get-Date).AddHours($Hours)
$captures = 0
$lastCapture = (Get-Date).AddSeconds(-$CooldownSec)
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
J ('ABA-TRIGGER start (max=' + $MaxCaptures + ' poll=' + $PollSec + 's cooldown=' + $CooldownSec + 's)')
while ((Get-Date) -lt $deadline -and $captures -lt $MaxCaptures) {
    Start-Sleep -Seconds $PollSec
    $tail = (Get-Content $journal -Tail 8 -Encoding UTF8) -join "`n"
    $slow = ($tail -match 'STATE=SLOW')
    if (-not $slow) { $slow = ($tail -match 'decode=([0-9.]+) tok/s' -and [double]$Matches[1] -lt 80.0) }
    $age = ((Get-Date) - $lastCapture).TotalSeconds
    # 用户活跃守卫（2026-10-14 夜）：reqlog 近 120s 有写入 ⇒ 正在跑实机请求 ⇒ 本次跳过（绝不打断会话）
    $req = '.temp\reqlog_watch.jsonl'
    $busy = (Test-Path $req) -and (((Get-Date) - (Get-Item $req).LastWriteTime).TotalSeconds -lt 120)
    if ($busy -and $slow) { J 'ABA-TRIGGER: SLOW 但检测到你正在用机（reqlog 活跃）-> 跳过捕获'; $lastCapture = Get-Date }
    if ($slow -and $age -ge $CooldownSec -and -not $busy) {
        $tag = 'auto' + (Get-Date -Format 'HHmm')
        J ('ABA-TRIGGER: SLOW 检出 -> 启动 ' + $tag + '（' + $captures + 1 + '/' + $MaxCaptures + '）')
        powershell -NoProfile -File scripts\pdl_aba.ps1 -Tag $tag | Out-Host
        $captures++
        $lastCapture = Get-Date
        J ('ABA-TRIGGER: ' + $tag + ' 完成（累计 ' + $captures + '/' + $MaxCaptures + '）')
    }
}
J ('ABA-TRIGGER end (captures=' + $captures + ')')
Write-Output ('done, captures=' + $captures)
