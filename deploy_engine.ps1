# deploy_engine.ps1 <new-exe-path> [-Restart]
# 2026-10-11 纪律加固（用户裁决）：一切引擎部署必须走本脚本 —— 先备份、再部署、留记录。
# 教训：15:40/18:11 两次 xcopy /Y 直接覆盖，检查点版/批量版 exe 永久丢失（回退链断裂）。
param(
    [Parameter(Mandatory=$true)][string]$NewExe,
    [switch]$Restart
)
$ErrorActionPreference = 'Stop'
$target = 'J:\ninfer-kvmem\engine\self-built-20261008\ninfer-serve.exe'
$logDir = 'J:\ninfer-kvmem\engine\self-built-20261008\_deploy_log'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not (Test-Path $NewExe)) { throw "new exe not found: $NewExe" }

# 1. 备份当前 exe（时间戳 + 大小校验）
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
if (Test-Path $target) {
    $cur = Get-Item $target
    $bak = "$target.bak_$stamp"
    Copy-Item $target $bak
    $h = (Get-FileHash $bak -Algorithm SHA256).Hash.Substring(0,16)
    Write-Host "[backup] $($cur.Length) bytes -> $bak (sha256:$h)"
    Add-Content "$logDir\deploy_history.txt" "$stamp  backup=$bak  sha256=$h  size=$($cur.Length)"
} else {
    Write-Host "[backup] no existing exe (first deploy)"
}

# 2. 停引擎
$p = Get-Process -Name 'ninfer-serve' -ErrorAction SilentlyContinue
if ($p) { Stop-Process -Name 'ninfer-serve' -Force; Start-Sleep -Seconds 3; Write-Host "[stop] engine stopped (was PID $($p.Id))" }

# 3. 部署 + 校验
Copy-Item $NewExe $target -Force
$nh = (Get-FileHash $target -Algorithm SHA256).Hash.Substring(0,16)
$ns = (Get-Item $target).Length
Write-Host "[deploy] $NewExe -> $target (sha256:$nh size:$ns)"
Add-Content "$logDir\deploy_history.txt" "$stamp  deploy=$NewExe  sha256=$nh  size=$ns"

# 4. 可选重启
if ($Restart) {
    Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList '/c','start "" /max "J:\ninfer-kvmem\retired\launchers-20261017\start-v1c2-vision64k-graph64.bat"'
    Write-Host "[restart] launched (graph64)"
}
Write-Host "[done] 回退命令: Copy-Item `"$bak`" `"$target`" -Force"
