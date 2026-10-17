# release_case_lock.ps1 -- 解除"案件冻结锁"（**仅用户可执行**）
#
# 用途：案卷取完证后，由用户显式解除，恢复"可以重启/改配置"的状态。
# 说明：锁由 valley_hunter.ps1 立案时自动写（.temp\cases\CASE_LOCKED.json + 队列 ⛔ CASE-LOCKED 行）；
#       **猎人不得自解** —— 自解等于冻结无意义。
Set-Location J:\ninfer-kvmem
$lockPath = '.temp\cases\CASE_LOCKED.json'
if (Test-Path $lockPath) {
    $j = Get-Content $lockPath -Raw | ConvertFrom-Json
    Write-Output ('当前锁: {0} @ {1}' -f $j.case, $j.time)
    Remove-Item $lockPath -Force
    Write-Output '已解除（CASE_LOCKED.json 已删除）。队列里的 ⛔ CASE-LOCKED 行请手动保留或标注"已解除"。'
} else {
    Write-Output '当前无冻结锁。'
}
