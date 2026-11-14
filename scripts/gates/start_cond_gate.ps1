# start_cond_gate.ps1 -- 起服条件对账门（2026-11-14 立）
#
# 为什么立：2026-11-14 同一天两次失误都出在"起服条件与声称不一致"——
#   ① 复测 42,205 那次时凭印象给 -Pool，起成 window=32768，而出问题那次是 40960；
#   ② 少一个 -Env 却称"干净的原配置"。
# 现有 gates.ps1 十道门全在提交侧（文件状态），管不到起服参数。
# 本门只做一件事：**从实跑日志反解参数，与预先写好的预期表逐项比对**。
# 不看 AI 说了什么，只看日志里的 CMD 行与 env dump 里的实际值。
#
# 用法：
#   scripts/gates/start_cond_gate.ps1 -Expect evidence/start/<tag>.json `
#                                     -Log    logs/<tag>.log `
#                                     -EnvDump evidence/start/<tag>.env.txt
#
# Expect JSON 形如：
#   { "tag": "t7_42k_repro",
#     "expect": { "kv_capacity": 81920, "spec": "dflash2", "draft_tokens": 5,
#                 "model_file": "swift15_iq3s_mtp+dflash2.ninfer",
#                 "env_NINFER_KV_WINDOW": "40960" } }
#
# 退出码：0=PASS  3=BLOCKED  2=输入缺失

param(
    [Parameter(Mandatory = $true)][string]$Expect,
    [Parameter(Mandatory = $true)][string]$Log,
    [string]$EnvDump = ''
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Expect)) { Write-Output "BLOCKED[start-cond]: 预期表不存在: $Expect"; exit 2 }
if (-not (Test-Path -LiteralPath $Log))    { Write-Output "BLOCKED[start-cond]: 日志不存在: $Log"; exit 2 }

$e = Get-Content -LiteralPath $Expect -Raw -Encoding UTF8 | ConvertFrom-Json
$tag = ''
if ($e.PSObject.Properties.Name -contains 'tag') { $tag = [string]$e.tag }
if (-not $tag) { $tag = [IO.Path]::GetFileNameWithoutExtension($Expect) }

$cmdLine = ''
$m = Select-String -LiteralPath $Log -Pattern '^CMD:' -Encoding UTF8 | Select-Object -First 1
if ($m) { $cmdLine = $m.Line }
if (-not $cmdLine) { Write-Output "BLOCKED[start-cond]: $tag 日志里没有 CMD 行，无法反解参数"; exit 2 }

function Grab([string]$pattern) {
    if ($cmdLine -match $pattern) { return $matches[1] }
    return ''
}

$actKv    = Grab '--kv-capacity\s+(\d+)'
$actSpec  = Grab '--spec\s+(\S+)'
$actDraft = Grab '--draft-tokens\s+(\d+)'
$actModel = Grab '([^\\\/\s]+\.ninfer)'

$fail = @()

if ($e.expect.PSObject.Properties.Name -contains 'kv_capacity' -and $null -ne $e.expect.kv_capacity) {
    if ([string]$actKv -ne [string]$e.expect.kv_capacity) {
        $fail += ("kv_capacity 期望 {0} 实际 '{1}'" -f $e.expect.kv_capacity, $actKv)
    }
}
if ($e.expect.PSObject.Properties.Name -contains 'spec' -and $e.expect.spec) {
    if ([string]$actSpec -ne [string]$e.expect.spec) {
        $fail += ("spec 期望 {0} 实际 '{1}'" -f $e.expect.spec, $actSpec)
    }
}
if ($e.expect.PSObject.Properties.Name -contains 'draft_tokens' -and $null -ne $e.expect.draft_tokens) {
    if ([string]$actDraft -ne [string]$e.expect.draft_tokens) {
        $fail += ("draft_tokens 期望 {0} 实际 '{1}'" -f $e.expect.draft_tokens, $actDraft)
    }
}
if ($e.expect.PSObject.Properties.Name -contains 'model_file' -and $e.expect.model_file) {
    if ([string]$actModel -ne [string]$e.expect.model_file) {
        $fail += ("model_file 期望 {0} 实际 '{1}'" -f $e.expect.model_file, $actModel)
    }
}

# env 只能从起服时的 stdout dump 反解（engine_ctl 的 'env check:' 行不落日志）
if ($e.expect.PSObject.Properties.Name -contains 'env_NINFER_KV_WINDOW' -and $e.expect.env_NINFER_KV_WINDOW) {
    if (-not $EnvDump -or -not (Test-Path -LiteralPath $EnvDump)) {
        $fail += ("env NINFER_KV_WINDOW 期望 {0}，但未提供 -EnvDump，无法核对" -f $e.expect.env_NINFER_KV_WINDOW)
    }
    else {
        $dump = Get-Content -LiteralPath $EnvDump -Raw -Encoding UTF8
        $want = [string]$e.expect.env_NINFER_KV_WINDOW
        if ($dump -notmatch ('NINFER_KV_WINDOW=' + [regex]::Escape($want))) {
            $fail += ("env NINFER_KV_WINDOW 期望 {0}，dump 中未出现" -f $want)
        }
    }
}

# 预期表必须自证来源（防"预期表本身凭记忆写错"成为新的绕门路径 · TELE 2026-11-14 建议）
$srcMissing = @()
if (-not ($e.PSObject.Properties.Name -contains 'sources')) {
    $srcMissing += '整份预期表缺 sources 节'
}
else {
    foreach ($k in $e.expect.PSObject.Properties.Name) {
        if (-not ($e.sources.PSObject.Properties.Name -contains $k)) { $srcMissing += $k; continue }
        if (-not $e.sources.$k) { $srcMissing += $k }
    }
}
if ($srcMissing.Count -gt 0) {
    $fail += ('预期表来源缺失: ' + ($srcMissing -join ', ') + '（每项须注明来自哪个日志 CMD 行或哪次用户指令）')
}

if ($fail.Count -eq 0) {
    Write-Output ("PASS[start-cond]: {0} 逐项一致 (kv={1} spec={2} draft={3} env_kvwindow={4})" -f $tag, $actKv, $actSpec, $actDraft, $(if ($e.expect.env_NINFER_KV_WINDOW) { $e.expect.env_NINFER_KV_WINDOW } else { 'n/a' }))
    exit 0
}

Write-Output ("BLOCKED[start-cond]: {0} 条件与预期不符" -f $tag)
foreach ($f in $fail) { Write-Output ("  - " + $f) }
exit 3
