# 产物级 arch 验收门（编译配方 §1 步骤 4 的机器化；2026-10-30）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File build\gates_arch_product.ps1 -Exe <exe> [-Log <logfile>]
# 判据（配方文档原文）：全部 cubin 为 sm_120a、0 个 sm_86、无 PTX-only；不达标 exit 1。
param(
    [Parameter(Mandatory = $true)][string]$Exe,
    [string]$Log = ''
)

$ErrorActionPreference = 'Stop'

function Emit([string]$text) {
    Write-Output $text
    if ($Log -ne '') {
        try {
            [IO.File]::AppendAllText($Log, $text + [char]13 + [char]10, (New-Object Text.UTF8Encoding $false))
        } catch {
        }
    }
}

if (-not (Test-Path -LiteralPath $Exe)) {
    Emit ('ARCH-GATE: FAILED exe-not-found -> ' + $Exe)
    exit 1
}

$cu = (Get-Command cuobjdump -ErrorAction SilentlyContinue).Source
if (-not $cu) {
    foreach ($cand in @('J:\Bonsai\landing\cuda-13.3\bin\cuobjdump.exe',
            'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.0\bin\cuobjdump.exe')) {
        if (Test-Path -LiteralPath $cand) { $cu = $cand; break }
    }
}
if (-not $cu) {
    Emit 'ARCH-GATE: FAILED cuobjdump-not-found'
    exit 1
}

$out = @(& $cu --list-elf $Exe 2>&1)
$tot = $out.Count
$sm120 = ($out | Select-String 'sm_120a' | Measure-Object).Count
$sm86 = ($out | Select-String 'sm_86' | Measure-Object).Count
$ptx = ($out | Select-String 'ptx' | Measure-Object).Count

Emit ('ARCH-GATE: exe=' + (Split-Path -Leaf $Exe) + ' ELF=' + $tot + ' sm_120a=' + $sm120 + ' sm_86=' + $sm86 + ' ptx=' + $ptx)

if ($sm120 -eq 0 -or $sm86 -gt 0 -or $ptx -gt 0 -or $tot -ne $sm120) {
    Emit 'ARCH-GATE: FAILED (need all-cubin sm_120a, zero sm_86, zero PTX)'
    exit 1
}

Emit 'ARCH-GATE: OK'
exit 0
