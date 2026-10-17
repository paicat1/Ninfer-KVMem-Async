# spawn_visible.ps1 -- 唯一许可的"起进程/起窗口"入口（T-WINDOW 机械强制）
#
# 为什么存在：2026-10-17 CB 绕开 engine_ctl.ps1 的 ValidateSet('Normal')，
#   自写启动脚本用 -WindowStyle Minimized 起服/起工具 ⇒ 用户看不到窗口（违反 T0）。
#   教训：**写在单个脚本里的禁令拦不住"另写一个脚本"**。
#   ⇒ 本脚本是"起进程"的唯一许可入口；任何自写 Start-Process 一律视为违规。
#
# 机械强制（不接受任何窗口参数，调用者无法覆盖）：
#   ① 一律 -WindowStyle Normal（**本脚本不暴露该参数**）
#   ② 起后 2 s 验证：有窗口 ⇒ 必须 可见 且 **非最小化**（IsIconic=false）；无窗口 ⇒ 违规
#   ③ 写 spawn 记录 evidence/spawns/<时间戳>_<purpose>.json（含 pid/标题/窗口状态/命令行）
#   ④ 验证失败 ⇒ 写 VIOLATION 记录 + 非零退出（调用者无法"静默通过"）
#
# 用法：powershell -File scripts\spawn_visible.ps1 -Exe <路径> -Purpose <用途> [-Args <参数字符串>]
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [Parameter(Mandatory = $true)][string]$Purpose,
    [string]$Args = ''
)
$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root

Add-Type @"
using System;using System.Runtime.InteropServices;
public class VisW {
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@

$spawnDir = Join-Path $root 'evidence\spawns'
$auditDir = Join-Path $root 'evidence\audits'
New-Item -ItemType Directory -Force -Path $spawnDir, $auditDir | Out-Null

$before = @(Get-Process | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -ExpandProperty Id)

# ① 起进程（**窗口样式写死 Normal**；不暴露参数 ⇒ 无法覆盖）
if ([string]::IsNullOrWhiteSpace($Args)) {
    $p = Start-Process -FilePath $Exe -WorkingDirectory $root -WindowStyle Normal -PassThru
} else {
    $p = Start-Process -FilePath $Exe -ArgumentList $Args -WorkingDirectory $root -WindowStyle Normal -PassThru
}

# ② 起后验证（2 s 后；有窗口必须可见且非最小化）
Start-Sleep -Seconds 2
$proc = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
$title = ''
$iconic = $null; $visible = $null; $hasWin = $false
if ($proc) {
    $h = $proc.MainWindowHandle
    if ($h -ne 0) {
        $hasWin = $true
        $iconic = [VisW]::IsIconic($h)
        $visible = [VisW]::IsWindowVisible($h)
        $title = $proc.MainWindowTitle
    }
}
$ok = ($hasWin -and (-not $iconic) -and $visible)

# ③ 记录
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$rec = [ordered]@{
    ts           = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    purpose      = $Purpose
    exe          = $Exe
    args         = $Args
    pid          = $p.Id
    has_window   = $hasWin
    is_minimized = $iconic
    is_visible   = $visible
    title        = $title
    verdict      = $(if ($ok) { 'OK' } else { 'VIOLATION' })
    enforced_by  = 'scripts\spawn_visible.ps1 (T-WINDOW)'
}
# 2026-10-17 修：机器可读 JSON **不得带 BOM**（PS 的 Set-Content -Encoding UTF8 会加 BOM ⇒ 严格 JSON 解析器读不了
#   ⇒ 审计器 rec_pids 永远为空 ⇒ 所有进程被判"无记录" = 假阳性源）
$recPath = Join-Path $spawnDir ($stamp + '_' + ($Purpose -replace '[^\w\u4e00-\u9fa5-]', '_') + '.json')
$json = ($rec | ConvertTo-Json -Depth 4)
[System.IO.File]::WriteAllText($recPath, $json, (New-Object System.Text.UTF8Encoding($false)))

# ④ 失败即留违规记录 + 非零退出
if (-not $ok) {
    $v = @()
    $v += '# 违规记录：起进程后窗口不可见/被最小化（T-WINDOW）'
    $v += ''
    $v += ('- 时刻：' + $rec.ts)
    $v += ('- 用途：' + $Purpose)
    $v += ('- 命令：' + $Exe + ' ' + $Args)
    $v += ('- pid：' + $p.Id + ' · 有窗口=' + $hasWin + ' · 最小化=' + $iconic + ' · 可见=' + $visible)
    $v += '- 依据：用户 2026-10-11 裁决（窗口纪律，违反=T0）+ 2026-10-17 CB 违规事件'
    $v += '- 处置：**立即恢复窗口可见** 并说明原因；本文件为独立证据，不得删除'
    $vf = Join-Path $auditDir ('VIOLATION_window_' + $stamp + '.md')
    ($v -join "`n") | Set-Content -LiteralPath $vf -Encoding UTF8
    Write-Host ('T-WINDOW VIOLATION: 起进程后窗口状态不合格 ⇒ ' + $vf) -ForegroundColor Red
    exit 2
}

Write-Host ('spawn OK | pid=' + $p.Id + ' | 标题="' + $title + '" | 最小化=' + $iconic + ' | 可见=' + $visible)
exit 0
