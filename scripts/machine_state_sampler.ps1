# machine_state_sampler.ps1
# 1 Hz GPU 机器态采样，用于慢态(#58)/死亡谷(#13) 的 clocks.mem 判据（M1 假说）。
# 纯读 nvidia-smi，零 GPU 占用，可与任何实验并行。
# 用法：powershell -NoProfile -File scripts\machine_state_sampler.ps1 [-Hours 10] [-IntervalSec 1]
param(
    [double]$Hours = 10,
    [int]$IntervalSec = 1,
    [string]$OutDir = ''
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) { $OutDir = Join-Path $root '.temp' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$csv   = Join-Path $OutDir ("machine_state_{0}.csv" -f $stamp)
$log   = Join-Path $OutDir ("machine_state_{0}.log" -f $stamp)

$deadline = (Get-Date).AddHours($Hours)
$fields = 'timestamp,clocks.sm,clocks.mem,power.draw,utilization.gpu,utilization.memory,temperature.gpu,pcie.link.gen.current,pcie.link.width.current,memory.used,memory.total'

"# machine_state_sampler  start=$(Get-Date -Format 's')  hours=$Hours  interval=${IntervalSec}s" | Out-File -FilePath $csv -Encoding utf8
"t,clk_sm,clk_mem,pow_w,util_gpu,util_mem,temp_c,pcie_gen,pcie_width,mem_used,mem_total,engine_procs" | Out-File -FilePath $csv -Encoding utf8 -Append
"START $(Get-Date -Format 's')  target=$csv" | Out-File -FilePath $log -Encoding utf8

$n = 0
$err = 0
$t0 = Get-Date

while ((Get-Date) -lt $deadline) {
    $line = & nvidia-smi --query-gpu=$fields --format=csv,noheader,nounits 2>$null
    $eng = @(Get-Process -Name ninfer-serve -ErrorAction SilentlyContinue).Count
    if ($line) {
        $line = ($line -replace '\s*,\s*', ',')
        $line | Out-File -FilePath $csv -Encoding utf8 -Append
        "e,$eng" | Out-Null
    } else {
        $err++
        "ERR,$(Get-Date -Format 's')" | Out-File -FilePath $csv -Encoding utf8 -Append
    }
    $n++

    # 每 60 拍记一次引擎进程数与心跳，便于事后切分"有负载/无负载"窗口
    if ($n % 60 -eq 0) {
        $el = [int]((Get-Date) - $t0).TotalSeconds
        "HB n=$n elapsed=${el}s engine=$eng err=$err" | Out-File -FilePath $log -Encoding utf8 -Append
        $host.UI.RawUI.WindowTitle = "machine_state_sampler [RUNNING] n=$n  ${el}s / $([int]($Hours*3600))s -- auto-stop at $($deadline.ToString('HH:mm'))"
    }

    Start-Sleep -Milliseconds ([int]$IntervalSec * 1000)
}

"DONE $(Get-Date -Format 's')  samples=$n  errors=$err  -> $csv" | Out-File -FilePath $log -Encoding utf8 -Append
$host.UI.RawUI.WindowTitle = "machine_state_sampler [DONE] samples=$n -- safe to close"
