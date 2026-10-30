# 运行时 DLL 部署（2026-10-30 立：补上"产物落位"缺失的另一半）
# 背景：build/s6_1208a.bat 不复制任何 DLL；build-out\apps 只有 7 个非 CUDA DLL；
#       engine\self-built-20261008 的 16 个 DLL 是历史手工件、来源无记录。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File build\deploy_dlls.ps1 -To <目标目录> [-From <源目录>] [-WhatIf]
# 判据：白名单内每个 DLL 复制后 sha256 与源一致；源缺失任一 => exit 1（不静默跳过）。
param(
    [Parameter(Mandatory = $true)][string]$To,
    [string]$From = 'J:\ninfer-kvmem\engine\self-built-20261008',
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

# 白名单 = 现役运行目录实际在用的 16 件（2026-10-30 实测）。新增依赖必须在此登记。
$WHITELIST = @(
    'avcodec-62.dll', 'avcodec-63.dll',
    'avformat-62.dll', 'avformat-63.dll',
    'avutil-60.dll', 'avutil-61.dll',
    'cublas64_13.dll', 'cublasLt64_13.dll', 'cudart64_13.dll',
    'libcurl-x64.dll', 'libcurl.dll',
    'swresample-6.dll', 'swresample-7.dll',
    'swscale-9.dll', 'swscale-10.dll',
    'z.dll'
)

if (-not (Test-Path -LiteralPath $To)) {
    New-Item -ItemType Directory -Force -Path $To | Out-Null
}

$missing = @()
foreach ($n in $WHITELIST) {
    if (-not (Test-Path -LiteralPath (Join-Path $From $n))) { $missing += $n }
}
if ($missing.Count -gt 0) {
    Write-Output ('DEPLOY-DLLS: FAILED source-missing -> ' + ($missing -join ', '))
    exit 1
}

$bad = 0
foreach ($n in $WHITELIST) {
    $src = Join-Path $From $n
    $dst = Join-Path $To $n
    $shaSrc = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
    if ($WhatIf) {
        Write-Output ('DEPLOY-DLLS: would-copy ' + $n + ' sha=' + $shaSrc.Substring(0, 12))
        continue
    }
    Copy-Item -LiteralPath $src -Destination $dst -Force
    $shaDst = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
    if ($shaDst -ne $shaSrc) {
        Write-Output ('DEPLOY-DLLS: FAILED sha-mismatch ' + $n)
        $bad++
    }
}
if ($bad -gt 0) {
    Write-Output ('DEPLOY-DLLS: FAILED count=' + $bad)
    exit 1
}
Write-Output ('DEPLOY-DLLS: OK files=' + $WHITELIST.Count + ' -> ' + $To)
exit 0
