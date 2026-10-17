param(
    [string]$Tag = 'probe',
    [int]$Runs = 1,
    [int]$Rounds = 1,
    [int]$FillerKb = 90,
    [int]$MaxTokens = 600,
    [int]$WatchSeconds = 260
)
# valley_probe.ps1 -- one-shot valley capture: GPU sampler + timestamped dmon + one a2gate run.
# Usage: powershell -File scripts\valley_probe.ps1 -Tag morning -Runs 1 -Rounds 1
# Output: .temp\valley_<tag>_<HHmmss>_dmon.txt ; .temp\gpu_samples.csv (appended) ; .temp\gate_<tag>.json
Set-Location J:\ninfer-kvmem
$ts = Get-Date -Format 'HHmmss'
$dmon = '.temp\valley_' + $Tag + '_' + $ts + '_dmon.txt'
Start-Process -WindowStyle Normal -FilePath cmd -ArgumentList '/c', ('nvidia-smi dmon -o T -s pucmt -c ' + $WatchSeconds + ' > ' + $dmon + ' 2>&1')
Start-Process -WindowStyle Normal -FilePath python -ArgumentList '-X', 'utf8', 'scripts\gpu_sampler.py', '--seconds', ([string]($WatchSeconds + 10)), '--interval', '1'
Start-Sleep -Seconds 2
Write-Output ('== a2gate: runs=' + $Runs + ' rounds=' + $Rounds + ' filler=' + $FillerKb + 'KB')
python -X utf8 scripts\a2gate.py --arm $Tag --port 8094 --runs $Runs --rounds $Rounds --filler-kb $FillerKb --max-tokens $MaxTokens
Start-Sleep -Seconds 3
Write-Output ('== dmon tail (' + $dmon + ')')
Get-Content $dmon -Tail 12
Write-Output '== gpu_samples tail'
Get-Content '.temp\gpu_samples.csv' -Tail 5
Write-Output '== step profile (last 6, if profile on)'
$log = Get-ChildItem logs\test_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Select-String -Path $log.FullName -Pattern 'step profile' -Encoding UTF8 | Select-Object -Last 6 | ForEach-Object { $_.Line.Trim() }
