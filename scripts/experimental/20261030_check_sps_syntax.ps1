$errs = $null
[void][System.Management.Automation.Language.Parser]::ParseFile('j:\ninfer-kvmem\smart_push.ps1', [ref]$null, [ref]$errs)
if ($errs.Count -eq 0) { 'SYNTAX-OK' } else { $errs | Select-Object -First 5 | ForEach-Object { $_.Message } }
