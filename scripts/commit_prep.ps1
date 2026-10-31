# commit_prep.ps1 -- READ-ONLY one-screen panel for commit/push approval.
# Shows: changed files + numstat + EOL/audit facts + token validity + a commit message draft.
# Never writes, never commits, never pushes. Long waits are forbidden here (WAIT-BUDGET-GATE).
$ErrorActionPreference = 'Continue'
Set-Location 'J:\ninfer-kvmem'

Write-Host '=== 1. CHANGED FILES ==='
git --no-pager status --short | ForEach-Object { '  ' + $_ }

Write-Host ''
Write-Host '=== 2. NUMSTAT (+ / -) ==='
git --no-pager diff --numstat | ForEach-Object { '  ' + $_ }

Write-Host ''
Write-Host '=== 3. AUDIT FACTS ==='
$h = git show HEAD:'docs/ninfer-kvmem-项目构建史.md' 2>$null
$w = [IO.File]::ReadAllText('J:\ninfer-kvmem\docs\ninfer-kvmem-项目构建史.md')
$hb = git show HEAD:'docs/ninfer-kvmem-项目构建史.md' 2>$null | Out-String
Write-Host ('  构建史 marker 190 count = ' + ([regex]::Matches($w, '### 190\.')).Count)
Write-Host ('  构建史 §189.8 count      = ' + ([regex]::Matches($w, '#### 189\.8 ')).Count)
Write-Host ('  构建史 crlf lines        = ' + ([regex]::Matches($w, "`r`n")).Count)

Write-Host ''
Write-Host '=== 4. TOKENS (default 60 min) ==='
foreach ($n in 'NINFER_APPROVED_COMMIT', 'NINFER_APPROVED_PUSH') {
    $f = Join-Path 'J:\ninfer-kvmem\_safety_backups\.allow' $n
    if (Test-Path $f) {
        try {
            $o = Get-Content $f -Encoding UTF8 -Raw | ConvertFrom-Json
            $exp = [datetime]::ParseExact($o.granted, 'yyyy-MM-dd HH:mm:ss', $null).AddMinutes([int]$o.minutes)
            $left = [math]::Round(($exp - (Get-Date)).TotalMinutes, 1)
            $state = if ($left -gt 0) { ('OK, 剩 ' + $left + ' 分钟') } else { 'EXPIRED' }
            Write-Host ('  ' + $n + '  granted=' + $o.granted + ' minutes=' + $o.minutes + '  -> ' + $state)
        } catch { Write-Host ('  ' + $n + '  UNREADABLE: ' + $_.Exception.Message) }
    } else { Write-Host ('  ' + $n + '  MISSING (需用户运行 tools\grant_allow.ps1 -Name ' + $n + ')') }
}

Write-Host ''
Write-Host '=== 5. COMMIT MESSAGE DRAFT (no APPROVED: token) ==='
Write-Host '  fix(engine_ctl): 5.1 子进程 Get-FileHash 回落与 waitready 快照迁出只读目录'
Write-Host '  feat(scripts): 新增 tick.ps1 唯一等待入口'
Write-Host '  docs: 记录 C-ctrl PG2 插桩归因与台账状态'
Write-Host ''
Write-Host '=== 6. PUSH ==='
Write-Host '  tools\smart_push.ps1 origin main   (走 FlClash 代理；不裸 git push)'
Write-Host ''
Write-Host '面板结束（只读，未做任何写操作）。'