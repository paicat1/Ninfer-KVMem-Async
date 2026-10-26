<#
start_engine_default.ps1 -- 引擎启动【唯一正确入口】（2026-10-18 建 · 用户令"正确启动必须固化"）

为什么存在：2026-10-18 我连续四轮起不来引擎，每轮凭印象拼 engine_ctl 的 17 个参数、一次漏一个：
  ① 漏 -Exe                        ⇒ L206 throw '-Exe 必填'
  ② 用后台 Start-Process           ⇒ **错误输出丢失** ⇒ 看不见为什么失败，只能靠猜
  ③ -Exe 传"运行位置"              ⇒ L235 Copy-Item 自己复制自己 ⇒ 失败
  ④ -Model 自己挑（挑到不带 vision）⇒ FATAL: missing component vision（-Vision 默认 overlay 要求 vision）
  而**正确参数一直写在成功启动的日志 CMD: 行里**，我却每次重新琢磨。

本脚本把正确参数焊死成一条命令（照 2026-10-17 23:43 与 2026-10-18 08:12 两次成功案例）：
  -Exe    engine\lineage\I3b_step13_fourlayer_20261015.exe   ← **源件**（engine_ctl 会复制到运行位置）
  -Pool   49152        （现役池）
  -Graph  64           （CUDA graph 允许量）
  -Spec   mtp          （MTP 投机）
  -KvDtype rk2v4-e8
  -Model  **不传** ⇒ 用 engine_ctl 默认 = ...mtp-iq4nl.**vision**.ninfer（与 -Vision overlay 配套）
  -Vision overlay（默认）
  -Tag    watch        ⇒ 日志 = logs\test_watch.log

铁律配套：
  · 前台执行并捕获输出（禁止后台 Start-Process —— 那会丢错误）
  · 轮询 ≤30 秒（铁律C）；每次查三项：进程 / 日志新增 / 端口
  · 早停判据：日志出现 FATAL/serve_tee end ⇒ 立即停；进程 0 + 日志无新增 + 过 15 s ⇒ 立即停
  · **轮询必须看对日志文件**（按 -Tag 推导，不是看旧日志）

用法（无参数）：
  powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\start_engine_default.ps1
可选：-Pool <n>（默认 49152）· -Graph <n>（默认 64）
#>
param(
    [int]$Pool = 49152,
    [int]$Graph = 64,
    [string]$Tag = 'watch',
    [string]$Root = 'J:\ninfer-kvmem'
)
$ErrorActionPreference = 'Continue'
$ctl = Join-Path $Root 'scripts\engine_ctl.ps1'
$src = Join-Path $Root 'engine\lineage\I3b_step13_fourlayer_20261015.exe'
$log = Join-Path $Root ('logs\test_' + $Tag + '.log')

# [GATE] 起服唯一门（T#0010/0013/0023/0054/0055/0059）
$gate = Join-Path $Root '.codebuddy\sda\gates\start_engine_gate.ps1'
if (Test-Path $gate) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $gate -Exe 'engine\lineage\I3b_step13_fourlayer_20261015.exe' -Pool $Pool -AllowSourceCopy
    if ($LASTEXITCODE -ne 0) { Write-Host '[GATE] start_engine_gate BLOCKED' -ForegroundColor Red; exit $LASTEXITCODE }
} else {
    Write-Host '[GATE] start_engine_gate.ps1 缺失（降级放行）' -ForegroundColor Yellow
}

if (-not (Test-Path $src)) { Write-Host ('❌ 源件不存在：' + $src) -ForegroundColor Red; exit 2 }

# ★ 幂等前置检查（2026-10-18 补）：引擎已在跑 ⇒ 跳过（否则 engine_ctl 的 Copy-Item 会撞"文件被占用"）
$exist = @(Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue).Count
$upNow = (Test-NetConnection -ComputerName 127.0.0.1 -Port 8094 -WarningAction SilentlyContinue).TcpTestSucceeded
if ($exist -ge 1 -and $upNow) {
    $pids = (Get-Process 'ninfer-serve*' | ForEach-Object { $_.Id }) -join ','
    Write-Host ('✅ 引擎已在跑（pid=' + $pids + ' · 端口 8094 已 listen）⇒ 幂等跳过，不重复启动') -ForegroundColor Green
    exit 0
}

Write-Host '== 启动引擎（固化参数）==' -ForegroundColor Cyan
Write-Host ('   源件 = ' + $src)
Write-Host ('   池 = ' + $Pool + ' · Graph = ' + $Graph + ' · Spec = mtp · KvDtype = rk2v4-e8 · 模型 = 默认(vision)')
Write-Host ('   日志 = ' + $log)

# ★ 前台执行并捕获输出（禁止后台 —— 后台会丢错误）
# ★ 2026-10-18 修：-Exe 必须传**相对路径**（engine_ctl L239 Join-Path $root $Exe 拼根；
#   传绝对路径会拼出 J:\...\J:\... ⇒ GetFullPath "path's format is not supported" 起服失败）
$srcRel = 'engine\lineage\I3b_step13_fourlayer_20261015.exe'
$out = & powershell -NoProfile -ExecutionPolicy Bypass -File $ctl -Action start `
        -Exe $srcRel -Tag $Tag -Pool $Pool -Graph $Graph -Spec mtp -KvDtype rk2v4-e8 -Experimental 2>&1
$rc = $LASTEXITCODE
$out | ForEach-Object { Write-Host ('   | ' + $_) }
if ($rc -ne 0) { Write-Host ('❌ engine_ctl start rc=' + $rc + ' ⇒ 停下（不轮询）') -ForegroundColor Red; exit $rc }

# ★ ≤30 秒轮询（铁律C）+ 早停判据；**看对日志文件**
Write-Host '== 轮询（≤30 s · 铁律C）==' -ForegroundColor Yellow
$base = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }
$t0 = Get-Date
$ready = $false
while (((Get-Date) - $t0).TotalSeconds -lt 30) {
    Start-Sleep -Seconds 5
    $el = [math]::Round(((Get-Date) - $t0).TotalSeconds, 0)
    $cnt = @(Get-Process 'ninfer-serve*' -ErrorAction SilentlyContinue).Count
    $sz = if (Test-Path $log) { (Get-Item $log).Length } else { 0 }
    $up = (Test-NetConnection -ComputerName 127.0.0.1 -Port 8094 -WarningAction SilentlyContinue).TcpTestSucceeded
    Write-Host ('   +' + $el.ToString().PadLeft(3) + 's 进程=' + $cnt + ' · 日志' + [math]::Round(($sz - $base) / 1KB, 1) + ' KiB · 端口=' + $up)
    if ($up -and $cnt -eq 1) { $ready = $true; Write-Host ('   ⇒ 就绪（' + $el + ' s）') -ForegroundColor Green; break }
    if (Test-Path $log) {
        $txt = [IO.File]::ReadAllText($log)
        if ($txt -match 'FATAL|serve_tee end') { Write-Host '   ❌ 早停：日志出现 FATAL/serve_tee end' -ForegroundColor Red; break }
    }
    if ($cnt -eq 0 -and ($sz - $base) -lt 200 -and $el -ge 15) { Write-Host '   ❌ 早停：进程 0 + 日志无新增 + 过 15 s' -ForegroundColor Red; break }
}

if ($ready) {
    Write-Host ''
    Write-Host '✅ 引擎就绪。日志尾部：' -ForegroundColor Green
    Get-Content $log -Encoding UTF8 -Tail 4 | ForEach-Object { Write-Host ('   ' + $_) }
} else {
    Write-Host ''
    Write-Host '❌ 未就绪（≤30 s 已到）—— 日志尾部：' -ForegroundColor Red
    if (Test-Path $log) { Get-Content $log -Encoding UTF8 -Tail 10 | ForEach-Object { Write-Host ('   ' + $_) } }
    Write-Host '⇒ 若要继续轮询，必须给出理由（铁律C）' -ForegroundColor Yellow
    exit 3
}
