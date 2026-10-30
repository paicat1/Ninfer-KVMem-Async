# valley_induce.ps1 -- 主动诱发谷 + A-B-A（2026-10-14 夜，用户令"主动诱发"）
#   周期：连续 DeepRepeats 发 60K 单轮（--filler-kb 240，in-pool）→ 短探针测 decode
#         → decode<80 ⇒ 谷 ⇒ 跑**全量协议** A-B-A（pdl_aba 默认 = 浅+深、3 臂；~4.5 min）
#   纪律：窗口可见 + 标题含任务与关闭条件；每周期台账（work\data\induce_<日期>.txt）；收工复岗守望者。
#   说明：本脚本不降任何测量标准——判据 = decode + spin-stamp/target-split + 引擎自报 + sha 逐字。
param([string]$KvDtype = 'nvfp4', [int]$Pool = 81920, [int]$DeepKb = 240, [int]$DeepRepeats = 3, [int]$LongTokens = 2500,
      [int]$Cycles = 6, [int]$MaxCaptures = 3, [double]$Hours = 3)
$host.UI.RawUI.WindowTitle = ('KVMem 谷诱发器 [运行中] - 连续深上下文逼谷，见谷即跑全量A-B-A（最多 ' + $MaxCaptures + ' 次，关窗=停）')
Set-Location J:\ninfer-kvmem
$journal = 'work\data\state_journal.txt'
$ledger = 'work\data\induce_' + (Get-Date -Format 'yyyyMMdd') + '.txt'
$deadline = (Get-Date).AddHours($Hours)
$captures = 0
function J([string]$m) { Add-Content -LiteralPath $journal -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' | ' + $m) }
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*valley_hunt*' -or $_.CommandLine -like '*watch_launch*' -or $_.CommandLine -like '*valley_watch*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Sleep -Seconds 2
J ('INDUCE start (deep=' + $DeepKb + 'KB x' + $DeepRepeats + ' cycles=' + $Cycles + ' kv=' + $KvDtype + '/' + $Pool + ')')
$cy = 0
while ((Get-Date) -lt $deadline -and $captures -lt $MaxCaptures -and $cy -lt $Cycles) {
    $cy++
    $decs = @()
    for ($i = 1; $i -le $DeepRepeats; $i++) {
        $nonce = 'cy' + $cy + 'r' + $i + '-' + (Get-Date -Format 'HHmmss')
        $out = (python -X utf8 scripts\a2gate.py --arm ('induce' + $cy + '_' + $i) --port 8094 --runs 1 --rounds 1 --filler-kb $DeepKb --max-tokens 300 --nonce $nonce 2>&1) -join "`n"
        $line = ([regex]::Matches($out, 'run 1 round 1\s+([\d.]+)s\s+decode=([\d.]+)') | Select-Object -Last 1)
        if ($line.Count -ge 1) { $decs += [double]$line[0].Groups[2].Value } else { $decs += 0.0 }
        Write-Output ('  [cy' + $cy + ' r' + $i + '] decode=' + $decs[-1])
    }
    # ---- 长生成相（v2）：与上一发同 prompt（nonce 复用）⇒ 命中缓存 ⇒ 纯解码 LongTokens 个 token（大量 MTP 轮）
    $longNonce = 'cy' + $cy + 'r' + $DeepRepeats + '-L'
    $outL = (python -X utf8 scripts\a2gate.py --arm ('inducelong' + $cy) --port 8094 --runs 1 --rounds 1 --filler-kb $DeepKb --max-tokens $LongTokens --nonce $longNonce 2>&1) -join "`n"
    $dl = 0.0
    if ($outL -match 'run 1 round 1\s+[\d.]+s\s+decode=([\d.]+)') { $dl = [double]$Matches[1] }
    Write-Output ('  [cy' + $cy + '] long-gen decode=' + $dl + '（' + $LongTokens + ' tok）')
    # ---- 打点判定：引擎日志最后一条 target-split 的 verify 毫秒（健康 ~18；谷 75–108）
    $ver = 0.0
    $vl = (Select-String -Path 'logs\test_valleywatch.log' -Pattern 'target-split' -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1 | ForEach-Object { $_.Line })
    if ($vl -match 'verify=([\d.]+)') { $ver = [double]$Matches[1] }
    $probe = (python -X utf8 scripts\a2gate.py --arm ('induceprobe' + $cy) --port 8094 --runs 1 --rounds 1 --filler-kb 45 --max-tokens 60 2>&1) -join "`n"
    $pd = 0.0
    if ($probe -match 'run 1 round 1\s+[\d.]+s\s+decode=([\d.]+)') { $pd = [double]$Matches[1] }
    $minDeep = ($decs | Measure-Object -Minimum).Minimum
    $tag = Get-Date -Format 'HH:mm:ss'
    Write-Output ('  [' + $tag + '] cycle ' + $cy + ' deep=' + ($decs -join '/') + ' probe=' + $pd)
    Add-Content -LiteralPath $ledger -Encoding UTF8 -Value ((Get-Date -Format 'MM-dd HH:mm:ss') + ' cy' + $cy + ' deep=' + ($decs -join '/') + ' long=' + $dl + ' verify=' + $ver + 'ms probe=' + $pd)
    if ((($pd -lt 80.0 -and $pd -gt 0.0) -or ($ver -ge 40.0) -or ($dl -lt 80.0 -and $dl -gt 0.0))) {
        J ('INDUCE: 谷检出（probe decode=' + $pd + '）-> 全量协议 A-B-A（3 臂 浅+深）')
        $atag = 'ind' + (Get-Date -Format 'HHmm')
        powershell -NoProfile -File scripts\pdl_aba.ps1 -Pattern 'on,off,on' -KvDtype $KvDtype -Pool $Pool -Tag $atag | Out-Host
        Add-Content -LiteralPath $ledger -Encoding UTF8 -Value ('   === 捕获 #' + ($captures + 1) + '（全量协议）见 .temp\pdl_aba_' + $atag + '.txt')
        $captures++
        J ('INDUCE: 全量协议捕获完成 #' + $captures)
    }
    Start-Sleep -Seconds 10
}
J ('INDUCE end (cycles=' + $cy + ' captures=' + $captures + ')')
Write-Output '==== 诱发台账 ===='
Get-Content $ledger -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 20
Write-Output '== 守望者复岗 =='
Start-Process -WindowStyle Normal -FilePath powershell -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'J:\ninfer-kvmem\scripts\watch_launch.ps1'
