# auto-archive build output: copy exe + sha256 + append lineage MANIFEST (Never overwrite).
# Called by build\s6_1208a.bat right after BUILD-EXIT is written.
param(
  [Parameter(Mandatory=$true)][string]$Source,
  [string]$Log = ''
)
$ErrorActionPreference = 'Continue'
$root = 'J:\ninfer-kvmem'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$day   = Get-Date -Format 'yyyyMMdd'
$destDir = Join-Path $root ("_safety_backups\exe_lineage_" + $day)
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
$name = 'ninfer-serve.exe.' + $stamp
$dest = Join-Path $destDir $name
Copy-Item -LiteralPath $Source -Destination $dest -Force
$hash = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
$size = (Get-Item -LiteralPath $dest).Length
$head = ''
try { $head = (git -C (Join-Path $root 'engine-src') rev-parse --short HEAD) } catch {}
$now = Get-Date -Format 'yyyy-MM-dd HH:mm'
$line = '{0} tag=auto_{1}_{2} sha256={3} size={4} note=auto-archive src={5} log={6}' -f $now, $stamp, $head, $hash, $size, $Source, $Log
Add-Content -LiteralPath (Join-Path $root 'engine\lineage\MANIFEST.txt') -Value $line -Encoding UTF8
Add-Content -LiteralPath (Join-Path $destDir 'MANIFEST.txt') -Value $line -Encoding UTF8
Write-Host ('ARCHIVED: ' + $dest)
Write-Host ('sha256=' + $hash + '  size=' + $size)
exit 0
