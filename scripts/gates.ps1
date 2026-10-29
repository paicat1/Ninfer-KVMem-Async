# gates.ps1 -- 统一门禁（2026-10-17 立）：**一道门跑全部检查器**




#




# 为什么统一：此前只有引用完整性一道门（ref_gate.ps1），结构乱账无人管；




#             而"一类一个家"要靠门禁执行 ⇒ 两个检查器合成一道门，推送前必跑。




# 含两项：




#   ① scripts/check_refs.py      引用完整性（仓内路径是否都存在；断链 > 基线即拦）




#   ② scripts/check_structure.py 结构合规（根目录白名单 + 禁则；**新违规即拦**）




# 规则数据：structure.json（白名单/禁则/已知待清/活件判定三源）—— 规则改了改数据，不改代码。




param([string]$PyExe = '')




$ErrorActionPreference = 'Continue'




$root = Split-Path -Parent $PSScriptRoot




# —— 解释器解析（2026-10-17 修：硬编码 python 会在 PATH 缺失时造成"假拦截"）——



$PyExe = 'python'



if (-not (Get-Command 'python' -ErrorAction SilentlyContinue)) {



    $cands = @(



        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),



        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),



        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),



        'py'



    )



    foreach ($c in $cands) {



        if ($c -and (Get-Command $c -ErrorAction SilentlyContinue)) { $PyExe = $c; break }



    }



}



if (-not (Get-Command $PyExe -ErrorAction SilentlyContinue)) {



    Write-Host "WARN: python not found -- gates SKIPPED (not blocked)" -ForegroundColor Yellow



    exit 0



}







$fail = 0









$refs = Join-Path $root 'scripts\check_refs.py'




if (Test-Path $refs) {




    $o = & $PyExe -X utf8 $refs 2>$null




    $os_ = ($o | Out-String)




    $n = 0




    if ($os_ -match '断链 (\d+) 条') { $n = [int]$Matches[1] }




    if ($n -gt 16) {




        Write-Host ("BLOCKED[refs]: 断链 {0} 条 > 基线 16（新断链）" -f $n) -ForegroundColor Red




        $o | Select-Object -Last 20 | ForEach-Object { Write-Host ("  " + $_) }




        $fail = 1




    } else { Write-Host ("refs: {0} 断链（基线 16）-- OK" -f $n) -ForegroundColor DarkGray }




}









$st = Join-Path $root 'scripts\check_structure.py'




if (Test-Path $st) {




    $o2 = & $PyExe -X utf8 $st 2>$null




    if ($LASTEXITCODE -ne 0) {




        Write-Host 'BLOCKED[structure]: 出现新违规（不在根白名单、也不在已知待清）' -ForegroundColor Red




        $o2 | Select-Object -Last 25 | ForEach-Object { Write-Host ("  " + $_) }




        $fail = 1




    } else { Write-Host 'structure: 无新违规 -- OK' -ForegroundColor DarkGray }




}









# —— 本地自律层（窗口纪律 / BOM / 绕过判据）—— **仅本机执行**
#   2026-10-17：这些工具已撤出版本控制（只在本机跑，是我的纪律执行件，不是仓级规范）。
#   ⇒ 工具不在（别人 clone / 换机器）⇒ **整段跳过并明示**，仓级层（引用/结构）不受影响。
$LocalToolsOk = (Test-Path 'scripts\check_launchers.py') -and (Test-Path 'scripts\audit_windows.py') -and (Test-Path 'scripts\check_ps1_bom.py')
if (-not $LocalToolsOk) {
    Write-Host "window-layers: 本地自律工具不在本机（scripts\check_launchers.py 等）-- 本地层整段跳过（仓级层不受影响）" -ForegroundColor DarkGray
} else {
    # —— T-WINDOW 两层（2026-10-17 立：CB 绕开禁令自写 Minimized 启动脚本 ⇒ 用户看不到窗口）——


    $launcherOut = & $PyExe -X utf8 scripts\check_launchers.py 2>&1 | Out-String


    $m = [regex]::Match($launcherOut, '违规 (\d+) 处')


    $lv = if ($m.Success) { [int]$m.Groups[1].Value } else { 0 }


    $lb = $null   # 2026-10-17 修：不得硬编码默认（原 22 ⇒ 读失败时静默放宽）

    try { $lb = [int]((Get-Content structure.json -Raw -Encoding UTF8 | ConvertFrom-Json).window_discipline.launcher_baseline) } catch { $lb = $null }

    if ($null -eq $lb) {

        Write-Host "BLOCKED[window]: 无法读取基线（structure.json 读失败/字段缺失）⇒ 按失败处理（**不静默退宽松默认**）" -ForegroundColor Red

        $fail = 1

        $lb = 0   # 保守：读不到基线就按最严处理

    }

    if ($lv -gt $lb) {


        Write-Host ("BLOCKED[window]: 启动脚本窗口违规 " + $lv + " 处 > 基线 " + $lb + "（新增违规）") -ForegroundColor Red


        $launcherOut -split "`n" | Select-Object -First 8 | ForEach-Object { Write-Host ("   " + $_) }


        $script:fail = $true


    } else {


        Write-Host ("window-launchers: " + $lv + " 处（基线 " + $lb + "）-- OK")


    }


    $auditOut = & $PyExe -X utf8 scripts\audit_windows.py --quiet 2>&1 | Out-String


    $arc = $LASTEXITCODE


    if ($arc -ne 0) {


        Write-Host "BLOCKED[window]: 窗口审计发现违规（可见性/最小化）" -ForegroundColor Red


        $auditOut -split "`n" | Select-Object -First 8 | ForEach-Object { Write-Host ("   " + $_) }


        $script:fail = $true


    } else {


        Write-Host "window-audit: 全部可见且非最小化 -- OK"


    }






    # —— T-ANTIHACK：合规连击（门禁全绿 +1；由违规流程清零）——
    try {
        $compFile = '.codebuddy\sda\COMPLIANCE.txt'
        if (Test-Path $compFile) {
            $c = Get-Content $compFile -Raw -Encoding UTF8
            if ($c -match 'streak\s*=\s*(\d+)') { $st = [int]$Matches[1] }
            if ($fail -eq 0) { $st = $st + 1 } else { $st = 0 }
            $newC = ($c -replace 'streak\s*=\s*\d+', ('streak = ' + $st)) -replace 'last_pass\s*=\s*[^\r\n]*', ('last_pass = ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
            Set-Content -LiteralPath $compFile -Value $newC -Encoding UTF8 -NoNewline
            Write-Host ("compliance-streak: " + $st + "（门禁全绿计数）") -ForegroundColor DarkGray
        }
    } catch { Write-Host ("WARN: 连击计数失败：" + $_.Exception.Message) -ForegroundColor Yellow }


    # —— T-WINDOW：含中文 .ps1 必须带 BOM（2026-10-17 立）——
    $bomOut = & $PyExe -X utf8 scripts\check_ps1_bom.py 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) {
        Write-Host "BLOCKED[window]: 新增/修改的含中文 .ps1 缺 BOM（PowerShell 按 ANSI 读 ⇒ 乱码 ⇒ 解析失败）" -ForegroundColor Red
        $bomOut -split "`n" | Select-Object -First 6 | ForEach-Object { Write-Host ("   " + $_) }
        $fail = 1
    } else {
        Write-Host "window-bom: 无违规 -- OK" -ForegroundColor DarkGray
    }

}


# ===================== UNDERSCORE-GATE（2026-10-18 铁律A）=====================
# 用户令：严禁随意建 `_` 前缀目录、严禁随意往里放文件；新建/放入前必须查清 + 向用户申请。
# 机械：凡 `_` 前缀且不在 structure.json.underscore_dirs.declared 里的目录 ⇒ 报违规。
$sjU = Get-Content (Join-Path $PSScriptRoot "..\structure.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$declaredU = @($sjU.underscore_dirs.declared | ForEach-Object { $_.name })
$uDirs = Get-ChildItem -Path (Join-Path $PSScriptRoot "..\") -Directory -Force -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "_*" }
$uBad = @()
foreach ($d in $uDirs) { if ($declaredU -notcontains $d.Name) { $uBad += $d.Name } }
if ($uBad.Count -gt 0) {
    Write-Output ("BLOCKED[underscore]: 未声明的下划线目录 " + ($uBad -join ", ") + " => 先查清用途 + 向用户申请，再登记进 structure.json")
    exit 1
} else {
    Write-Output ("underscore: " + $uDirs.Count + " 个 `_` 目录，全部已声明 -- OK")
}
# ===================== UNDERSCORE-GATE END ======================


# ===================== QUOTA-GATE / RULE-CHANGE-WARN / MODE-SHOW（2026-10-18 补）=====================
# L3 配额原来只"入每周审计告警" ⇒ 超线多日无人拦。现改为：超红线即阻断。
$quotaFail = 0
$sjQ = Get-Content (Join-Path $PSScriptRoot "..\structure.json") -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($q in @(@("logs", $sjQ.quotas.logs.warn_mib, "MiB"), @("_safety_backups", $sjQ.quotas._safety_backups.warn_gib, "GiB"))) {
    $name = $q[0]; $limit = $q[1]; $unit = $q[2]
    $dir = Join-Path $PSScriptRoot ("..\" + $name)
    if (Test-Path $dir) {
        $bytes = (Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        if (-not $bytes) { $bytes = 0 }
        $val = if ($unit -eq "GiB") { [math]::Round($bytes/1GB, 2) } else { [math]::Round($bytes/1MB, 1) }
        if ($null -eq $limit) {
            Write-Output ("WARN[quota]: " + $name + " 红线未配置（structure.json 里缺失）=> 跳过")
        } elseif ($val -gt $limit) {
            Write-Output ("BLOCKED[quota]: " + $name + " = " + $val + " " + $unit + " > 红线 " + $limit + " => logs 受保护（项目未结项前严禁删除），不清理")
            $quotaFail = 1
        } else {
            Write-Output ("quota: " + $name + " = " + $val + " " + $unit + " <= " + $limit + " -- OK")
        }
    }
}
# L2 规则簿可被受规则者改写 ⇒ 规则面相对 HEAD 有变更时醒目列出（禁止静默自赦）
$ruleDiff = (git diff HEAD -- structure.json) 2>$null
if ($ruleDiff) {
    $ruleKeys = @("forbidden","known_violations","root_whitelist","git_boundary","quotas","naming","minimize_allowed","sanctioned_spawners","local_only_tools")
    $hits = 0
    foreach ($l in $ruleDiff) { if ($l.StartsWith("+")) { foreach ($k in $ruleKeys) { if ($l -like ("*" + $k + "*")) { $hits++; break } } } }
    if ($hits -gt 0) { Write-Output ("WARN[rule-change]: structure.json 本轮改了 " + $hits + " 处规则面 => 必须逐条向用户说明（禁止静默自赦）") }
}
# L9 MODE.json 可被自降级 ⇒ 显示档位与改动时间
$modeP = Join-Path $PSScriptRoot "..\.codebuddy\sda\MODE.json"
if (Test-Path $modeP) {
    $mj = Get-Content $modeP -Raw -Encoding UTF8 | ConvertFrom-Json
    $tierShow = $mj.tier
if (-not $tierShow) { $tierShow = "(未配置)" }
Write-Output ("mode: tier=" + $tierShow + "（MODE.json 改于 " + (Get-Item $modeP).LastWriteTime.ToString("MM-dd HH:mm") + "）")
}
# 2026-10-18 修（设计病）：配额超线【不再直接阻断】—— 那会把"体量观察值"变成逼人删证据的闸。
# 规则：超线 ⇒ 醒目告警 + 记审计件；仅当"超线 且 已过该目录保留期仍未清理"才阻断。
if ($quotaFail -eq 1) {
    $nowD = Get-Date
    $overdue = 0
    foreach ($q2 in @(@("logs", 14), @("_safety_backups", 30))) {
        $dn2 = $q2[0]; $keep = $q2[1]
        $dir2 = Join-Path $PSScriptRoot ("..\" + $dn2)
        if (-not (Test-Path $dir2)) { continue }
        $oldest = Get-ChildItem $dir2 -Recurse -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -First 1
        if ($oldest -and (($nowD - $oldest.LastWriteTime).TotalDays -gt $keep)) { $overdue++ }
    }
    if ($overdue -gt 0) {
        Write-Output ("BLOCKED[quota]: 超线且已过保留期仍未清理（" + $overdue + " 项）=> 按保留规则滚动") 
        exit 1
    } else {
        Write-Output "WARN[quota]: 超线但未过保留期 => 只告警，不阻断（禁止为过闸而删证据）"
    }
}
# ===================== QUOTA-GATE END ======================


# ===================== SUBREPO-CLEAN-GATE（附属仓库未归档改动） =====================
# 规则：engine-src 等工作树若脏 => 阻断（改动未归档，源码树重克隆即丢）
# 放行：NINFER_ALLOW_SRC_DIRTY=1
if ($env:NINFER_ALLOW_SRC_DIRTY -ne '1') {
    $srRoot = $null
    foreach ($srCand in @((Join-Path $PSScriptRoot '..'), 'J:\ninfer-kvmem')) {
        if (Test-Path (Join-Path $srCand 'engine-src\.git')) { $srRoot = (Resolve-Path $srCand).Path; break }
    }
    if (-not $srRoot) { $srRoot = 'J:\ninfer-kvmem' }
    $srSub = Join-Path $srRoot 'engine-src'
    if (Test-Path (Join-Path $srSub '.git')) {
        $srDirty = @(git -C $srSub status --porcelain 2>$null)
        if ($srDirty.Count -gt 0) {
            Write-Output ('BLOCKED[subrepo]: engine-src 有未归档改动（' + $srDirty.Count + ' 项）')
            foreach ($sd in ($srDirty | Select-Object -First 6)) { Write-Output ('   ' + $sd) }
            Write-Output '   先本地 commit（禁推上游），或设 NINFER_ALLOW_SRC_DIRTY=1 放行'
            exit 1
        }
    }
}
# ===================== SUBREPO-CLEAN-GATE END =====================

# ===================== EOL-GATE（疑似行尾整体变更） =====================
# 规则：非新增文件、且 diff 变更行数 >= 该文件当前行数 × 0.9 ⇒ 阻断
# 放行：环境变量 NINFER_ALLOW_EOL=1（明知是整文件改写时）
if ($env:NINFER_ALLOW_EOL -ne '1') {
    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $numstat = @(git -C $repoRoot -c core.quotepath=false diff --numstat origin/main..HEAD 2>$null)
    $eolBad = @()
    foreach ($ln in $numstat) {
        $parts = $ln -split "`t"
        if ($parts.Count -lt 3) { continue }
        if ($parts[0] -eq '-' -or $parts[1] -eq '-') { continue }
        $changed = [int]$parts[0] + [int]$parts[1]
        $rel = $parts[2]
        git -C $repoRoot cat-file -e ("origin/main:" + $rel) 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { continue }
        $full = Join-Path $repoRoot $rel
        if (-not (Test-Path -LiteralPath $full)) { continue }
        $lines = 0
        try { $lines = (Get-Content -LiteralPath $full -ErrorAction Stop | Measure-Object -Line).Lines } catch { $lines = 0 }
        if ($lines -gt 50 -and $changed -ge ($lines * 0.9)) {
            $eolBad += ($rel + " (changed=" + $changed + " / lines=" + $lines + ")")
        }
    }
    if ($eolBad.Count -gt 0) {
        Write-Output ("BLOCKED[eol]: 疑似行尾整体变更 -> " + ($eolBad -join "; "))
        Write-Output "   先核 CRLF/bare_LF 是否与 origin/main 版本一致；确属整文件改写则设 NINFER_ALLOW_EOL=1 再推"
        exit 1
    }
}
# ===================== EOL-GATE END ======================

# ===================== ASSET-DUAL-GATE（资产双份） =====================
# 规则：engine-src 的 HEAD 必须能从某个远端分支可达；只有本地一份 = 资产不存在
# 放行：NINFER_ALLOW_ASSET_SINGLE=1
if ($env:NINFER_ALLOW_ASSET_SINGLE -ne '1') {
    $adRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $adSub = Join-Path $adRoot 'engine-src'
    if (Test-Path (Join-Path $adSub '.git')) {
        $adHead = (git -C $adSub rev-parse HEAD 2>$null)
        $adOk = 0
        foreach ($adRef in @(git -C $adSub for-each-ref --format='%(refname)' refs/remotes 2>$null)) {
            git -C $adSub merge-base --is-ancestor $adHead $adRef 2>$null
            if ($LASTEXITCODE -eq 0) { $adOk = 1; break }
        }
        if ($adOk -eq 0) {
            Write-Output ('BLOCKED[asset-dual]: engine-src HEAD ' + $adHead.Substring(0,8) + ' 不在任何远端分支可达 => 资产只有一份')
            Write-Output '   补法：给引擎树建我们自己的远端并推送；或设 NINFER_ALLOW_ASSET_SINGLE=1 临时放行'
            exit 1
        }
    }
}
# ===================== ASSET-DUAL-GATE END =====================

# ===================== REPRO-CLAIM-GATE（对外复现指引自证） =====================
# 规则：README 里 `clone -b <分支>` 指向的分支，其 CMakePresets 必须含 CMAKE_CUDA_ARCHITECTURES
# 放行：NINFER_ALLOW_REPRO_CLAIM=1
if ($env:NINFER_ALLOW_REPRO_CLAIM -ne '1') {
    $rcRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    $rcReadme = Join-Path $rcRoot 'README.md'
    if (Test-Path $rcReadme) {
        $rcTxt = Get-Content $rcReadme -Raw
        foreach ($rcM in [regex]::Matches($rcTxt, 'clone\s+-b\s+([A-Za-z0-9_\-]+)')) {
            $rcBr = $rcM.Groups[1].Value
            $rcPath = 'src-tree/fusion-engine-src/CMakePresets.json'
            $rcBody = git -C $rcRoot show ($rcBr + ':' + $rcPath) 2>$null
            if (-not $rcBody) { continue }
            if (($rcBody -join "`n") -notmatch 'CMAKE_CUDA_ARCHITECTURES') {
                Write-Output ('BLOCKED[repro-claim]: README 指引 clone -b ' + $rcBr + '，但该分支缺 CMAKE_CUDA_ARCHITECTURES => 复现链断')
                Write-Output '   补法：把 arch 参数同步进该分支并推送；或设 NINFER_ALLOW_REPRO_CLAIM=1 临时放行'
                exit 1
            }
        }
    }
}
# ===================== REPRO-CLAIM-GATE END =====================


exit $fail


