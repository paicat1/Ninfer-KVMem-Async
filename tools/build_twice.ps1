# build_twice.ps1 -- T-BUILD-TWICE：连编两次，产物 sha256 相同方可入库
param([string]$Target = 'ninfer-serve')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$out = @()

& (Join-Path $PSScriptRoot 'build_env_check.ps1')
if ($LASTEXITCODE -ne 0) { exit 1 }

for ($i = 1; $i -le 2; $i++) {
    Write-Host ("=== build pass " + $i + " ===")
    $env:SOURCE_DATE_EPOCH = '1761782400'
    cmake --build (Join-Path $root '.temp\build-sym120a') --target $Target --parallel 16
    if ($LASTEXITCODE -ne 0) { Write-Host ("BLOCKED[build-twice]: 第 " + $i + " 次编译失败"); exit 1 }
    $exe = Join-Path $root ('.temp\build-sym120a\apps\' + $Target + '.exe')
    if (-not (Test-Path $exe)) { Write-Host ('BLOCKED[build-twice]: 产物缺失 ' + $exe); exit 1 }
    $h = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
    if (-not $h) {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        $fs = [System.IO.File]::OpenRead($exe)
        try { $h = ([System.BitConverter]::ToString($sha.ComputeHash($fs)) -replace '-', '').ToLower() } finally { $fs.Dispose(); $sha.Dispose() }
    }
    $out += $h
    Write-Host ('  pass ' + $i + ' sha256 = ' + $h)
}

if ($out[0] -eq $out[1]) {
    Write-Host ('BUILD-TWICE: IDENTICAL (' + $out[0].Substring(0, 16) + ')')
    exit 0
} else {
    Write-Host ('BLOCKED[build-twice]: 两次产物不同')
    Write-Host ('  pass1 = ' + $out[0])
    Write-Host ('  pass2 = ' + $out[1])
    exit 1
}
