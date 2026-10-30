param([string[]]$Paths = @('j:\ninfer-kvmem\smart_push.ps1', 'j:\ninfer-kvmem\scripts\gates.ps1'))
foreach ($p in $Paths) {
    $errs = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$null, [ref]$errs)
    if ($errs.Count -eq 0) { "SYNTAX-OK: $p" } else { "SYNTAX-FAIL: $p"; $errs | Select-Object -First 5 | ForEach-Object { $_.Message } }
}
