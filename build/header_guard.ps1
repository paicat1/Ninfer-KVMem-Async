# HEADER GUARD (T#0086): any change to ANY .h under the source tree forces a full
# clean rebuild. ninja only tracks .cpp mtime, so a changed header leaves stale
# ABI-mismatched .obj files linked into a fresh exe (2026-11-17 incident: startup.cpp.obj
# from 11-03 linked against a new EngineOptions layout => boot-time validation crash).
# Fail-closed by design: a MISSING baseline also wipes the build dir (no baseline =
# no proof of continuity = full rebuild).
param(
    [Parameter(Mandatory=$true)][string]$Src,
    [Parameter(Mandatory=$true)][string]$Build,
    [string]$Log = ""
)
$ErrorActionPreference = 'Stop'
$snapPath = Join-Path $PSScriptRoot 'HEADER_SNAPSHOT.json'
function Log-Line([string]$s) { if ($Log) { Add-Content -LiteralPath $Log -Value ("[gate:header] " + $s) } }
function Wipe-Build([string]$why) {
    if (Test-Path -LiteralPath $Build) { Remove-Item -LiteralPath $Build -Recurse -Force }
    Log-Line ($why + ' (build dir wiped, next run reconfigures from scratch)')
}
$files = Get-ChildItem -LiteralPath $Src -Recurse -File -Filter '*.h'
$current = @{}
foreach ($f in $files) {
    $rel = $f.FullName.Substring($Src.Length).TrimStart('\').Replace('\', '/')
    $current[$rel] = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
}
if (-not (Test-Path -LiteralPath $snapPath)) {
    Wipe-Build 'HEADER-SNAPSHOT-INIT (no baseline)'
    $current | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $snapPath -Encoding UTF8
    Write-Output 'HEADER-SNAPSHOT-INIT-FORCED-CLEAN'
    exit 0
}
$bj = Get-Content -LiteralPath $snapPath -Raw -Encoding UTF8 | ConvertFrom-Json
$changed = @()
foreach ($k in $current.Keys) {
    $old = $bj.PSObject.Properties[$k]
    if ($null -eq $old -or $old.Value -ne $current[$k]) { $changed += ('M ' + $k) }
}
foreach ($p in $bj.PSObject.Properties) {
    if (-not $current.ContainsKey($p.Name)) { $changed += ('D ' + $p.Name) }
}
if ($changed.Count -gt 0) {
    Wipe-Build ('HEADER-REBUILD-FORCED files=' + $changed.Count)
    $current | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $snapPath -Encoding UTF8
    Write-Output ('HEADER-REBUILD-FORCED files=' + $changed.Count)
    $changed | Select-Object -First 5 | ForEach-Object { Write-Output ('  ' + $_) }
    exit 0
}
Write-Output 'HEADER-GUARD-CLEAN'
Log-Line 'HEADER-GUARD-CLEAN'
exit 0
