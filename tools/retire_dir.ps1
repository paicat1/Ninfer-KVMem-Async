# retire gate (T-TRACE / user order 2026-10-13: "任何成品严禁删除！")
# This script NEVER deletes. It only reports and refuses.
# Rule: all deletes (even garbage) are on hold; only the USER naming an item authorizes deletion.
param(
  [Parameter(Mandatory=$true)][string]$Target
)
$ErrorActionPreference = 'Continue'
if (-not (Test-Path -LiteralPath $Target)) { Write-Host ('NOT FOUND: ' + $Target); exit 2 }
$items = @(Get-ChildItem -LiteralPath $Target -Recurse -File -ErrorAction SilentlyContinue)
$exes  = @($items | Where-Object { $_.Extension -eq '.exe' })
$sum   = ($items | Measure-Object -Property Length -Sum).Sum
$newest = ($items | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
Write-Host ('== retire report: ' + $Target)
Write-Host ('files=' + $items.Count + '  totalMiB=' + [math]::Round($sum/1MB,2) + '  newest=' + $newest.LastWriteTime)
if ($exes.Count -gt 0) {
  Write-Host '-- exe present (products; NEVER delete without user naming):'
  foreach ($e in $exes) { Write-Host ('   ' + $e.FullName + '  ' + [math]::Round($e.Length/1MB,2) + ' MiB  ' + $e.LastWriteTime) }
  Write-Host 'REFUSED: directory contains exe(s).'
  exit 3
}
Write-Host 'NO exe present - but T-TRACE still applies: this script does NOT delete. Deletion needs the USER to name the target.'
exit 0
