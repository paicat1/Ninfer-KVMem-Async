# start_hunter.ps1 -- 起猎人的**唯一入口**（硬门：先语法体检，失败即拒绝启动）
#
# 由来（2026-10-17，TELE 第九轮建议 → CB 固化）：本夜已有**两次语法事故**——
#   ① v2：CRITERION 行少一个右括号 ⇒ 之后三次重启全部静默失败（我还被"进程=1"自匹配骗了）；
#   ② v4.1：替换 catch 块时吃掉 Set-Content 行 ⇒ L153 悬挂管道符 ⇒ 猎人起不来。
#   两次的共同点：**改完直接重启**，没有"重启前先体检"的硬门。
param([int]$MaxHours = 12)
Set-Location J:\ninfer-kvmem
$host.UI.RawUI.WindowTitle = 'VALLEY-HUNTER [running] -- metered driver 1 probe/min; case on decode<60 + rel-power x3 (gap<=180s); close window = stop'
$tgt = (Resolve-Path 'scripts\valley_hunter.ps1').Path
$errs = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($tgt, [ref]$null, [ref]$errs)
if ($errs) {
    $lines = @()
    foreach ($e in $errs) { $lines += ('L{0}: {1}' -f $e.Extent.StartLineNumber, $e.Message) }
    $msg = ('{0} | GATE-BLOCK: valley_hunter.ps1 syntax error, NOT started | {1}' -f (Get-Date -Format 'MM-dd HH:mm:ss'), ($lines -join ' ; '))
    Add-Content -LiteralPath '.temp\cases\GATE_ALERT.txt' -Value $msg -Encoding UTF8
    Write-Output $msg
    Write-Output 'GATE: SYNTAX FAIL -- hunter NOT started. Fix the script first.'
    exit 1
}
Write-Output ('GATE: SYNTAX OK ({0}) -- starting hunter, MaxHours={1}' -f $tgt, $MaxHours)
& powershell -NoProfile -ExecutionPolicy Bypass -File $tgt -MaxHours $MaxHours
