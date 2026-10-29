# build_env_check.ps1 -- T-BUILD-VERIFY：构建前比对声明工具链与实际，不一致即 exit 1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$pres = Join-Path $root 'CMakePresets.json'
if (-not (Test-Path $pres)) { Write-Host 'BLOCKED[build-verify]: 缺 CMakePresets.json'; exit 1 }

$j = Get-Content $pres -Raw -Encoding UTF8 | ConvertFrom-Json
$cv = $j.configurePresets[0].cacheVariables
$bin = $root

function Fail([string]$m) { Write-Host ('BLOCKED[build-verify]: ' + $m); exit 1 }

# 1) 声明的工具链必须存在
foreach ($k in @('CMAKE_CXX_COMPILER', 'CMAKE_CUDA_COMPILER', 'CMAKE_MAKE_PROGRAM')) {
    $p = [string]$cv.$k
    if (-not $p) { Fail ("presets 未声明 $k") }
    if (-not (Test-Path $p)) { Fail ("$k 不存在: $p") }
    Write-Host ("  OK $k -> $p")
}

# 2) 若已有 CMakeCache，其编译器必须与声明一致
$cache = Join-Path $bin '.temp\build-sym120a\CMakeCache.txt'
if (Test-Path $cache) {
    foreach ($pair in @(@('CMAKE_CXX_COMPILER:', 'CMAKE_CXX_COMPILER'),
                        @('CMAKE_CUDA_COMPILER:', 'CMAKE_CUDA_COMPILER'),
                        @('CMAKE_MAKE_PROGRAM:', 'CMAKE_MAKE_PROGRAM'))) {
        $line = (Select-String -Path $cache -Pattern ('^' + $pair[0]) | Select-Object -First 1)
        if (-not $line) { continue }
        $actual = (($line.Line -split '=', 2)[1]) -replace '/', '\'
        $want = ([string]$cv.($pair[1])) -replace '/', '\'
        if ($actual -ine $want) {
            Fail ("cache 与 presets 不一致: " + $pair[1] + "`n      cache  = " + $actual + "`n      presets= " + $want)
        }
        Write-Host ("  OK cache==presets " + $pair[1])
    }
}

# 3) cl.exe 主版本必须与声明路径一致（防 PATH 抢先）
$clWant = Split-Path ([string]$cv.CMAKE_CXX_COMPILER) -Parent
$clEnv = (Get-Command cl.exe -ErrorAction SilentlyContinue)
if ($clEnv) {
    $clDir = Split-Path $clEnv.Source -Parent
    if ($clDir -ine $clWant) {
        Fail ("PATH 上的 cl.exe 不是声明的那一个`n      PATH  = " + $clEnv.Source + "`n      presets= " + [string]$cv.CMAKE_CXX_COMPILER)
    }
    Write-Host '  OK PATH 上的 cl.exe 与声明一致'
} else {
    Write-Host '  INFO PATH 上无 cl.exe（需先 vcvars64，且必须用声明的那条链）'
}

# 4) 版本记录（进台账）
$nv = & ([string]$cv.CMAKE_CUDA_COMPILER) '--version' 2>$null | Select-Object -Last 1
$nj = & ([string]$cv.CMAKE_MAKE_PROGRAM) '--version' 2>$null | Select-Object -First 1
Write-Host ('  nvcc: ' + $nv)
Write-Host ('  ninja: ' + $nj)
Write-Host 'BUILD-VERIFY: PASS'
exit 0
