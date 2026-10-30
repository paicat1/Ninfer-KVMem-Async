# 引擎资产台账工具（2026-10-30 立 · PM-RULES §2/§3 的机器实现）
# 动作：
#   audit   磁盘 vs 台账：无台账件 / 重复件 / 孤儿 / test-run 超量 / 现役位不符
#   rotate  清 test-run 只留当前件（-Apply 才真删；默认干跑）
#   adopt   新件入封存库 + 写 MANIFEST 行（-Exe -Label -Note）
#   gate    台账完整性门（exe 数 == MANIFEST 行数），供 gates.ps1 调用；不符 exit 1
# 纪律：删只走 rotate -Apply，且要求 token NINFER_APPROVED_DELETE 有效。
param(
    [Parameter(Mandatory = $true)][ValidateSet('audit', 'rotate', 'adopt', 'gate')][string]$Action,
    [string]$Exe = '',
    [string]$Label = '',
    [string]$Note = '',
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$lin = Join-Path $root 'engine\lineage'
$run = Join-Path $root 'engine\test-run'
$live = Join-Path $root 'engine\self-built-20261008'
$man = Join-Path $lin 'MANIFEST.md'
$regPath = Join-Path $root 'engine_registry.json'
$tokFile = Join-Path $root '_safety_backups\.allow\NINFER_APPROVED_DELETE'

function Sha([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }

function ManNames {
    $names = @()
    if (Test-Path $man) {
        foreach ($ln in (Get-Content $man -Encoding UTF8)) {
            $m = [regex]::Match($ln, '`([^`]+\.exe)`')
            if ($m.Success) { $names += $m.Groups[1].Value }
        }
    }
    , $names
}

function TokenOk {
    if (-not (Test-Path $tokFile)) { return $false }
    try {
        $o = Get-Content $tokFile -Raw -Encoding UTF8 | ConvertFrom-Json
        $g = [datetime]::ParseExact([string]$o.granted, 'yyyy-MM-dd HH:mm:ss', $null)
        return (((Get-Date) - $g).TotalMinutes -le [int]$o.minutes)
    } catch { return $false }
}

switch ($Action) {

    'audit' {
        $diskLin = @(Get-ChildItem $lin -Filter '*.exe' -File -EA 0)
        $names = ManNames
        $diskNames = $diskLin | ForEach-Object { $_.Name }

        Write-Output ('[AUDIT] lineage: 磁盘 {0} 件 / MANIFEST {1} 行' -f $diskLin.Count, $names.Count)

        $noLedger = $diskNames | Where-Object { $names -notcontains $_ }
        if ($noLedger) {
            Write-Output '[AUDIT] 无台账件（磁盘有、MANIFEST 无）:'
            foreach ($n in $noLedger) { Write-Output ('   - ' + $n) }
        } else { Write-Output '[AUDIT] 无台账件: 0' }

        $orphan = $names | Where-Object { $diskNames -notcontains $_ }
        if ($orphan) {
            Write-Output '[AUDIT] 孤儿（MANIFEST 有、磁盘无）:'
            foreach ($n in $orphan) { Write-Output ('   - ' + $n) }
        } else { Write-Output '[AUDIT] 孤儿: 0' }

        # 重复：同 sha 多份（只算 lineage，1.3GB 级，逐件算 sha 较慢；用 size 先粗筛）
        $bySize = $diskLin | Group-Object Length | Where-Object { $_.Count -gt 1 }
        if ($bySize) {
            Write-Output '[AUDIT] 同尺寸疑似重复（size 相同）：'
            foreach ($g in $bySize) {
                $hs = $g.Group | ForEach-Object { Sha $_.FullName }
                $u = $hs | Select-Object -Unique
                if ($u.Count -lt $hs.Count) { Write-Output ('   - ' + (($g.Group | ForEach-Object { $_.Name }) -join ' == ') + '  (sha 相同)') }
            }
        } else { Write-Output '[AUDIT] 疑似重复: 0' }

        $runFiles = @(Get-ChildItem $run -Filter '*.exe*' -File -EA 0 | Where-Object { $_.Length -gt 100MB })
        Write-Output ('[AUDIT] test-run: {0} 件（规则 ≤1 件为当前件）' -f $runFiles.Count)
        foreach ($f in $runFiles) { Write-Output ('   - {0}  {1} MB' -f $f.Name, [int]($f.Length / 1MB)) }

        $liveExe = Join-Path $live 'ninfer-serve.exe'
        if (Test-Path $liveExe) {
            $lh = Sha $liveExe
            $match = $diskLin | Where-Object { (Sha $_.FullName) -eq $lh } | Select-Object -First 1
            if ($match) { Write-Output ('[AUDIT] 现役位 = lineage {0}（sha 一致）' -f $match.Name) }
            else { Write-Output '[AUDIT] 现役位 ≠ 任何 lineage 件（未封存的生产件）' }
        }
        exit 0
    }

    'rotate' {
        $runFiles = @(Get-ChildItem $run -Filter '*.exe*' -File -EA 0 | Where-Object { $_.Length -gt 100MB } | Sort-Object LastWriteTime -Descending)
        if ($runFiles.Count -le 1) { Write-Output '[ROTATE] test-run 已是 1 件，无需轮转'; exit 0 }
        $keep = $runFiles[0]
        Write-Output ('[ROTATE] 保留当前件: ' + $keep.Name)
        if (-not $Apply) {
            Write-Output '[ROTATE] 干跑：以下将被删除（加 -Apply 才执行）'
            $runFiles | Select-Object -Skip 1 | ForEach-Object { Write-Output ('   - ' + $_.Name) }
            exit 0
        }
        if (-not (TokenOk)) { Write-Output '[ROTATE] BLOCKED：缺有效 NINFER_APPROVED_DELETE 令牌'; exit 1 }
        $runFiles | Select-Object -Skip 1 | ForEach-Object {
            Remove-Item -LiteralPath $_.FullName -Force
            Write-Output ('   DELETED ' + $_.Name)
        }
        exit 0
    }

    'adopt' {
        if (-not $Exe -or -not $Label) { Write-Output '[ADOPT] 需要 -Exe <路径> -Label <代号>'; exit 1 }
        $src = $Exe
        if (-not (Test-Path $src)) { Write-Output ('[ADOPT] 源件不存在: ' + $src); exit 1 }
        $h = Sha $src
        $sizeMB = [math]::Round((Get-Item $src).Length / 1MB, 1)
        $stamp = Get-Date -Format 'yyyyMMdd'
        $target = Join-Path $lin ('ninfer-serve-{0}.exe' -f $Label)
        if (Test-Path $target) { Write-Output ('[ADOPT] 目标已存在，拒绝覆盖: ' + $target); exit 1 }
        Copy-Item -LiteralPath $src -Destination $target
        Write-Output ('[ADOPT] 已入封存库: ' + $target + '  sha=' + $h.Substring(0, 16))
        # 写 MANIFEST 行
        $line = '| **{0}** | - | `{1}` | {2} | `{3}` |' -f $Label, (Split-Path -Leaf $target), $sizeMB, $h
        Add-Content -LiteralPath $man -Value $line -Encoding UTF8
        Write-Output '[ADOPT] MANIFEST 已追加一行（请手工补「原代号」与用途说明）'
        exit 0
    }

    'gate' {
        $nDisk = @(Get-ChildItem $lin -Filter '*.exe' -File -EA 0).Count
        # 只算真实文件名：排除说明用条目（含反斜杠或尖括号）
        # 正文截断到「附录 A」之前再数：附录是 sha 底账，会重复列出同一批文件名
        $mtxt = [IO.File]::ReadAllText($man, [Text.Encoding]::UTF8)
        $aidx = $mtxt.IndexOf('## 附录 A')
        if ($aidx -gt 0) { $mtxt = $mtxt.Substring(0, $aidx) }
        $nMan = @([regex]::Matches($mtxt, '`[^`]+\.exe`') | ForEach-Object { $_.Value } | Where-Object { $_ -notmatch '[\\<>]' } | Sort-Object -Unique).Count
        if ($nDisk -ne $nMan) {
            Write-Output ('BLOCKED[assets]: lineage exe {0} 件 ≠ MANIFEST {1} 行（台账不完整）' -f $nDisk, $nMan)
            exit 1
        }
        Write-Output ('assets: lineage {0} 件 == MANIFEST {0} 行 -- OK' -f $nDisk)
        exit 0
    }
}
