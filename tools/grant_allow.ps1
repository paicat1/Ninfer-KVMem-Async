# 授权令牌生成器（用户侧工具）
# 用法：powershell -NoProfile -File tools\grant_allow.ps1 -Name NINFER_ALLOW_ASSET_SINGLE [-Minutes 30]
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [int]$Minutes = 30
)
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root '_safety_backups\.allow'
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$f = Join-Path $dir $Name
$obj = [ordered]@{ name = $Name; granted = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); minutes = $Minutes }
[IO.File]::WriteAllText($f, ($obj | ConvertTo-Json -Compress), (New-Object Text.UTF8Encoding $false))
Write-Host ('[ALLOW] 已授权 ' + $Name + '  ' + $Minutes + ' 分钟 -> ' + $f)
Write-Host '   用法：设同名环境变量为 1 后运行 gates/repo 命令'
