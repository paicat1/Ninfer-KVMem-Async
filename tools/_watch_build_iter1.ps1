# visible monitor window for the iterate-1 INCREMENTAL rebuild.
# Unlike the first monitor, the log already contains BUILD-EXIT lines from run 1, so this one
# waits for the COUNT to grow past the baseline recorded at start. ASCII only (PS 5.1 codepage).
$host.ui.RawUI.WindowTitle = 'iter-1 rebuild [running] - auto-close on new BUILD-EXIT'
$log = 'J:\ninfer-kvmem\.temp\build_20261013_54fix.log'
$baseline = @(Select-String -Path $log -Pattern 'BUILD-EXIT=' -ErrorAction SilentlyContinue).Count
$deadline = (Get-Date).AddHours(2)
$done = $false
while (-not $done -and (Get-Date) -lt $deadline) {
  Clear-Host
  Write-Host ('== iter-1 rebuild watch ==  ' + (Get-Date -Format 'HH:mm:ss') + '  baseline=' + $baseline)
  $f = Get-Item $log -ErrorAction SilentlyContinue
  if ($f) {
    Write-Host ('log MiB=' + [math]::Round($f.Length/1MB,2) + '  lastWrite=' + $f.LastWriteTime)
    Get-Content $log -Tail 3 -Encoding Default -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('   ' + $_) }
    $now = @(Select-String -Path $log -Pattern 'BUILD-EXIT=' -ErrorAction SilentlyContinue).Count
    if ($now -gt $baseline) { $done = $true; Write-Host ''; Write-Host ('NEW BUILD-EXIT seen (count ' + $now + ') -- done.') }
  }
  $procs = @(Get-Process ninja,cl,link -ErrorAction SilentlyContinue)
  Write-Host ('compile procs=' + $procs.Count)
  Start-Sleep 5
}
Write-Host ''
Write-Host 'closing in 8s.'
Start-Sleep 8
