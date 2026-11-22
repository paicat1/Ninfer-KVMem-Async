# check_engine_versions.ps1 -- 校验 lineage 封存的 3 个关键引擎版本是否完好
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check_engine_versions.ps1
$root = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $root 'engine\lineage'

$expect = [ordered]@{
    'ninfer-serve-RC1.exe'  = '322A972D6596A16D384A7565F2071978F98CBF7EBA52F32B85546E247F9E9495'
    'ninfer-serve-RC2.exe' = '9453FFC6FF077252C6102EE43A77F684A25294E937C1A3420A30A93B1995E89B'
    'ninfer-serve-RC3.exe' = '3543AD189D2F7A763F69125CE9E67DFE0781EA4BDCC420754A8F6F13A8FACE91'
}

$bad = 0
foreach ($k in $expect.Keys) {
    $p = Join-Path $dir $k
    if (-not (Test-Path $p)) {
        Write-Host ('MISSING   ' + $k) -ForegroundColor Red
        $bad++
        continue
    }
    $h = (Get-FileHash $p -Algorithm SHA256).Hash
    if ($h -ne $expect[$k]) {
        Write-Host ('MISMATCH  ' + $k) -ForegroundColor Red
        Write-Host ('  expect ' + $expect[$k])
        Write-Host ('  actual ' + $h)
        $bad++
    }
    else {
        $item = Get-Item $p
        Write-Host ('OK        {0}  {1} MB  readonly={2}' -f $k, [math]::Round($item.Length / 1MB, 1), $item.IsReadOnly) -ForegroundColor Green
    }
}

if ($bad -gt 0) {
    Write-Host ('FAIL: ' + $bad + ' 个版本异常') -ForegroundColor Red
    exit 1
}
Write-Host 'ALL OK（3 个关键版本完好）' -ForegroundColor Green
exit 0
