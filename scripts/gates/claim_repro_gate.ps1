# claim_repro_gate.ps1 -- 结论归因复现门（2026-11-14 立 · 落盘侧）
#
# 为什么立：2026-11-14 用一个单次异常数据点（prompt 42,205 三哨兵全丢）直接推出
#   "32K 预算装不下 36K prompt 的悬崖"，而同样条件下 36,687 三次全对 —— 结论是编的。
# 现有 gates.ps1 的 REPRO-CLAIM-GATE 只管 README 的 clone 分支 arch，不管结论归因。
#
# 本门挂在**落盘侧**（报告 / 审计件 / 审批包 / 构建史），不挂对话侧：
#   对话里 AI 仍可能乱说，但只要写成文件，就必须带可核对的复现记录。
#   （依 TELE 2026-11-14 审核建议：落盘侧接入现有提交门禁的机械强制力）
#
# 判据（三条同时成立）：
#   1) 落盘件里出现归因词（退化 / 上限 / 崩塌 / 唯一解释 / 根因是 / 必然 / 证明了 / 悬崖 / 卡死）
#   2) 该文件必须引用 evidence/repro/<name>.md
#   3) 被引用的 repro 文件必须含 `## 条件` 与 `## 运行记录` 两节，
#      且运行记录表的数据行 >= 2（单次数据不得归因）
#
# 用法：
#   scripts/gates/claim_repro_gate.ps1                 # 扫 git 差异中的 md（提交前默认）
#   scripts/gates/claim_repro_gate.ps1 -All            # 全量扫 docs/reports + evidence/audits + 审批包
#   scripts/gates/claim_repro_gate.ps1 -Paths a.md,b.md
#
# 退出码：0=PASS  4=BLOCKED  2=输入错误

param(
    [string[]]$Paths = @(),
    [switch]$All
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$AttribWords = '退化|上限|崩塌|唯一解释|根因是|必然|证明了|悬崖|卡死|瓶颈就是'
$ReproRefPat = 'evidence[/\\]repro[/\\]([A-Za-z0-9_\-\u4e00-\u9fa5]+\.md)'

function Get-TargetFiles {
    if ($Paths.Count -gt 0) {
        return $Paths | ForEach-Object { if ([IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $root $_ } } |
                Where-Object { Test-Path -LiteralPath $_ }
    }
    if ($All) {
        $dirs = @('docs\reports', 'evidence\audits', '.codebuddy\sda\approval')
        $out = @()
        foreach ($d in $dirs) {
            $p = Join-Path $root $d
            if (Test-Path $p) { $out += (Get-ChildItem $p -File -Filter '*.md' -Recurse -ErrorAction SilentlyContinue).FullName }
        }
        if (Test-Path (Join-Path $root 'docs\ninfer-kvmem-项目构建史.md')) {
            $out += (Join-Path $root 'docs\ninfer-kvmem-项目构建史.md')
        }
        return $out
    }
    # 默认：git 差异里的新增/修改 md
    $diff = & git -C $root -c core.quotepath=false diff --cached --name-only --diff-filter=AM 2>$null
    $diff2 = & git -C $root -c core.quotepath=false diff --name-only --diff-filter=AM 2>$null
    $names = @($diff) + @($diff2) | Where-Object { $_ -and $_ -match '\.md$' } | Select-Object -Unique
    return $names | ForEach-Object { Join-Path $root ($_ -replace '/', '\') } | Where-Object { Test-Path -LiteralPath $_ }
}

# 排除两类自身即证据的文件：
#   ① evidence\audits  —— 对既有结论的复核，本身不产出归因（2026-11-14 由 tech-audit 触发）
#   ② evidence\repro   —— 复现记录本身就是证据源，要求它引用自己会无限递归
$files = @(Get-TargetFiles) | Where-Object { $_ -notmatch '\\evidence\\audits\\' -and $_ -notmatch '\\evidence\\repro\\' }
if ($files.Count -eq 0) { Write-Output 'PASS[claim-repro]: 无待检落盘件'; exit 0 }

$fail = @()
foreach ($f in $files) {
    $txt = Get-Content -LiteralPath $f -Raw -Encoding UTF8
    if (-not $txt) { continue }

    $hits = [regex]::Matches($txt, $AttribWords)
    if ($hits.Count -eq 0) { continue }

    $rel = $f.Replace($root + '\', '')
    $refs = [regex]::Matches($txt, $ReproRefPat)
    if ($refs.Count -eq 0) {
        $fail += ("{0}: 含归因词 {1} 处，但未引用 evidence/repro/<name>.md" -f $rel, $hits.Count)
        continue
    }

    $okAny = $false
    $reasons = @()
    foreach ($m in $refs) {
        $name = $m.Groups[1].Value
        $cand = Join-Path $root ('evidence\repro\' + $name)
        if (-not (Test-Path -LiteralPath $cand)) { $reasons += ("引用 {0} 但文件不存在" -f $name); continue }
        $rt = Get-Content -LiteralPath $cand -Raw -Encoding UTF8
        if ($rt -notmatch '(?m)^##\s*条件') { $reasons += ("{0} 缺 `## 条件` 节" -f $name); continue }
        if ($rt -notmatch '(?m)^##\s*运行记录') { $reasons += ("{0} 缺 `## 运行记录` 节" -f $name); continue }
        # 运行记录节内统计表格数据行（跳过表头与分隔行）
        $sec = [regex]::Match($rt, '(?ms)^##\s*运行记录(.*?)(?:^##\s|\z)').Groups[1].Value
        $rows = ([regex]::Matches($sec, '(?m)^\s*\|.*\|\s*$')).Count
        $rows = [Math]::Max(0, $rows - 2)   # 去掉表头 + |---|
        if ($rows -lt 2) { $reasons += ("{0} 运行记录数据行 {1} < 2（单次数据不得归因）" -f $name, $rows); continue }
        $okAny = $true
        break
    }
    if (-not $okAny) {
        $fail += ("{0}: 归因证据不足 —— {1}" -f $rel, ($reasons -join '；'))
    }
}

if ($fail.Count -eq 0) { Write-Output ("PASS[claim-repro]: 检查 {0} 个落盘件，归因均有复现记录" -f $files.Count); exit 0 }

Write-Output 'BLOCKED[claim-repro]: 结论含归因词但复现证据不足（2026-11-14 立：单次异常不得归因）'
foreach ($x in $fail) { Write-Output ('  - ' + $x) }
Write-Output '   补法：写 evidence/repro/<case>.md，含 `## 条件`（逐项+来源）与 `## 运行记录`（>=2 次同条件数据）'
exit 4
