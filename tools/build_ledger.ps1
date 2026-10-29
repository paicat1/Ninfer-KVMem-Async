param(
    [Parameter(Mandatory=$true)][string]$Exe,
    [string]$Recipe = '',
    [string]$Source = '',
    [string]$Purpose = '',
    [string]$Result = '',
    [string]$Status = 'candidate',
    [string]$Note = '',
    [string]$Preset = '',
    [string]$PresetSha = ''
)
$root = Split-Path -Parent $PSScriptRoot
$p = Join-Path $root $Exe
if (-not (Test-Path $p)) { Write-Host ('exe 不存在: ' + $p); exit 1 }
$h = (Get-FileHash $p -Algorithm SHA256).Hash.ToLower()
$rec = [ordered]@{
    ts = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    artifact_name = (Split-Path $p -Leaf)
    artifact_sha256 = $h
    size = (Get-Item $p).Length
    status = $Status
    recipe = $Recipe
    source = $Source
    purpose = $Purpose
    result = $Result
    note = $Note
    preset = $Preset
    preset_sha256 = $(if ($PresetSha) { $PresetSha } elseif (Test-Path (Join-Path $root 'CMakePresets.json')) { (Get-FileHash (Join-Path $root 'CMakePresets.json') -Algorithm SHA256).Hash.ToLower() } else { '' })
}
$led = Join-Path $root 'docs\01-构建与发布\BUILD_LEDGER.jsonl'
Add-Content -LiteralPath $led -Value ($rec | ConvertTo-Json -Compress) -Encoding UTF8
Write-Host ('[LEDGER] 已登记 ' + $rec.artifact_name + '  ' + $h.Substring(0,16) + '  status=' + $Status)
