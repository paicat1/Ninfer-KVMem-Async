# promote_from_temp.ps1 -- "转正"入口（2026-10-18 建 · 用户令"好用有用的东西及时转正"）
#
# 解决的问题：我习惯把工具写进 .temp（gitignored ⇒ 零摩擦），结果：
#   * 有用的一次性脚本永远留在临时区，没人声明、没人门禁、一清理就没
#   * 两周堆了 800+ 个，项目真正依赖的东西和草稿混在一起分不清
#
# 本脚本把 .temp 里的脚本**转正**：
#   ① 挪到 scripts/（可声明、可门禁、可复现的家）
#   ② 按 -As 登记：local = 本地工具（ignore，只在这台机器）；repo = 入库（仓级规范）
#      若脚本含起进程原语 ⇒ 自动加进 sanctioned_spawners（守卫才不误判）
#   ③ 语法检查（.py 走 py_compile；.ps1 走 PowerShell 解析器）
#   ④ 跑门禁；全绿才算转正成功
#
# 用法：powershell -File scripts\promote_from_temp.ps1 -Name foo.py [-As local|repo] [-DryRun]

param(
    [Parameter(Mandatory = $true)][string]$Name,
    [ValidateSet('local', 'repo')][string]$As = 'local',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$root = 'J:\ninfer-kvmem'
Set-Location $root

$src = Join-Path $root ('.temp\' + $Name)
$dst = Join-Path $root ('scripts\' + $Name)
if (-not (Test-Path $src)) { Write-Output ('FATAL: .temp\' + $Name + ' 不存在'); exit 2 }
if (Test-Path $dst) { Write-Output ('FATAL: scripts\' + $Name + ' 已存在（不覆盖）'); exit 2 }

Write-Output ('待转正：.temp\' + $Name + '  (' + [math]::Round((Get-Item $src).Length/1KB,1) + ' KiB)')
Write-Output ('目标　：scripts\' + $Name + '  登记方式 = ' + $As)
if ($DryRun) { Write-Output '（-DryRun：只演示，不落盘）'; exit 0 }

# ① 挪
Move-Item -Path $src -Destination $dst -Force
Write-Output '  ① 已挪到 scripts/'

# ② 登记进 structure.json
$sj = Get-Content (Join-Path $root 'structure.json') -Raw | ConvertFrom-Json
$rel = 'scripts/' + $Name
$txt = [System.IO.File]::ReadAllText($dst).ToLower()
$hasSpawn = ($txt -match 'start-process|subprocess\.(popen|run)|os\.system')
if ($As -eq 'repo') {
    # 入库：从 local_only_tools 里移除（若在），并确保不被 ignore
    if ($sj.local_only_tools -contains $rel) { $sj.local_only_tools = @($sj.local_only_tools | Where-Object { $_ -ne $rel }) }
    Write-Output '  ② 登记为仓级件（入库）'
} else {
    if ($sj.local_only_tools -notcontains $rel) { $sj.local_only_tools = @($sj.local_only_tools) + @($rel) }
    Write-Output '  ② 登记为本地件（local_only_tools）'
}
if ($hasSpawn) {
    if ($sj.window_discipline.sanctioned_spawners -notcontains $rel) {
        $sj.window_discipline.sanctioned_spawners = @($sj.window_discipline.sanctioned_spawners) + @($rel)
    }
    Write-Output '  ② 含起进程原语 ⇒ 已加进 sanctioned_spawners（守卫不误判）'
}
$sj._updated = (Get-Date -Format 'yyyy-MM-dd') + '（promote_from_temp: ' + $Name + ' -> ' + $As + '）'
[System.IO.File]::WriteAllText((Join-Path $root 'structure.json'), ($sj | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
Write-Output '  ② structure.json 已更新'

# ③ 语法检查
if ($Name -like '*.py') {
    $py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    if (-not (Test-Path $py)) { $py = 'python' }
    & $py -X utf8 -c ("import py_compile,sys;py_compile.compile(r'" + $dst + "',doraise=True);print('  ③ py_compile OK')")
} else {
    $e = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($dst, [ref]$null, [ref]$e)
    if ($e) { Write-Output ('  ③ 语法 ERR: ' + $e[0].Message) } else { Write-Output '  ③ PowerShell 语法 OK' }
}

# ④ 门禁
Write-Output '  ④ 跑门禁…'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\gates.ps1')
if ($LASTEXITCODE -ne 0) { Write-Output '  ④ 门禁未过 ⇒ 转正未完成，请处理'; exit 3 }
Write-Output '  ④ 门禁全绿'
Write-Output ('== 转正完成：scripts\' + $Name + '（' + $As + '）==')
