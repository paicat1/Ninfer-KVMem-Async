# visible monitor window for the 54fix rebuild (ASCII only on purpose: PS 5.1 codepage safety)
$host.ui.RawUI.WindowTitle = '54fix FULL REBUILD [running] - auto-close on BUILD-EXIT'
$log = 'J:\ninfer-kvmem\.temp\build_20261013_54fix.log'
$deadline = (Get-Date).AddHours(3)
$done = $false
while (-not $done -and (Get-Date) -lt $deadline) {
  Clear-Host
  Write-Host ('== 54fix build watch ==  ' + (Get-Date -Format 'HH:mm:ss'))
  $f = Get-Item $log -ErrorAction SilentlyContinue
  if ($f) {
    Write-Host ('log MiB=' + [math]::Round($f.Length/1MB,2) + '  lastWrite=' + $f.LastWriteTime)
    $last = Select-String -Path $log -Pattern 'BUILD-EXIT=' -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($last) {
      Write-Host ('') ; Write-Host ('LAST: ' + $last.Line) ; Write-Host ''
      if ($last.Line -match '2026') { $done = $true }
    }
    Get-Content $log -Tail 3 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('   ' + $_) }
  } else {
    Write-Host 'log not yet created (waiting for task) ...'
  }
  $procs = @(Get-Process ninja,cl,link -ErrorAction SilentlyContinue)
  $cpu = ($procs | Measure-Object -Property CPU -Sum).Sum
  Write-Host ('compile procs=' + $procs.Count + '  cpuSeconds=' + [math]::Round($cpu,0))
  Start-Sleep 5
}
Write-Host ''
Write-Host 'DONE (or timeout). Closing in 8s.'
Start-Sleep 8
