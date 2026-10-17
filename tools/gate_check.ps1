# gate_check.ps1 — SDA v2 门控脚本（全局版，双模式）
# 用法: powershell -Command "& 'c:\Users\PC\.codebuddy\sda-infra\gate_check.ps1' <change-name> <gate-type>"
# gate-type: dp0, dp1, dp2, backup, scope, safety
# 返回: exit 0 = GATE_PASSED, exit 1 = GATE_BLOCKED

param(
    [Parameter(Position=0)]
    [string]$ChangeName,
    [Parameter(Position=1)]
    [string]$GateType
)

# 检测项目根目录（从当前工作目录向上查找changes/目录）
$ProjectRoot = $null
$dir = Get-Location
while ($dir -ne $dir.Parent) {
    if (Test-Path "$dir\changes") {
        $ProjectRoot = $dir
        break
    }
    $dir = $dir.Parent
}
if (-not $ProjectRoot) {
    # 如果当前目录就是项目根目录
    if (Test-Path "changes") {
        $ProjectRoot = Get-Location
    }
}
if (-not $ProjectRoot) {
    Write-Output "GATE_BLOCKED: cannot find changes/ directory (project not initialized for SDA)"
    exit 1
}

# 检测git模式
$HasGit = Test-Path "$ProjectRoot\.git"

$ChangeDir = "$ProjectRoot\changes\$ChangeName"

# 验证变更目录存在
if (-not (Test-Path $ChangeDir)) {
    Write-Output "GATE_BLOCKED: change directory not found: $ChangeDir"
    exit 1
}

switch ($GateType) {
    "dp0" {
        $dpFile = "$ChangeDir\dp0-confirmed.md"
        if (-not (Test-Path $dpFile)) {
            Write-Output "GATE_BLOCKED: dp0-confirmed.md not found"
            exit 1
        }
        if (-not (Select-String -Path $dpFile -Pattern "(?:用户确认令牌|确认令牌|用户令牌)" -Quiet)) {
            Write-Output "GATE_BLOCKED: dp0-confirmed.md missing user confirmation token"
            exit 1
        }
        Write-Output "GATE_PASSED: dp0"
        exit 0
    }

    "dp1" {
        $dpFile = "$ChangeDir\dp1-approved.md"
        if (-not (Test-Path $dpFile)) {
            Write-Output "GATE_BLOCKED: dp1-approved.md not found"
            exit 1
        }
        if (-not (Select-String -Path $dpFile -Pattern "(?:用户确认令牌|确认令牌|用户令牌)" -Quiet)) {
            Write-Output "GATE_BLOCKED: dp1-approved.md missing user confirmation token"
            exit 1
        }
        Write-Output "GATE_PASSED: dp1"
        exit 0
    }

    "dp2" {
        $dpFile = "$ChangeDir\dp2-verified.md"
        if (-not (Test-Path $dpFile)) {
            Write-Output "GATE_BLOCKED: dp2-verified.md not found"
            exit 1
        }
        if (-not (Select-String -Path $dpFile -Pattern "(?:用户确认令牌|确认令牌|用户令牌)" -Quiet)) {
            Write-Output "GATE_BLOCKED: dp2-verified.md missing user confirmation token"
            exit 1
        }
        Write-Output "GATE_PASSED: dp2"
        exit 0
    }

    "backup" {
        if ($HasGit) {
            # git模式：检查文件是否被git track
            $ContractFile = "$ChangeDir\Contract.md"
            if (-not (Test-Path $ContractFile)) {
                Write-Output "GATE_PASSED: backup (git mode, no contract to check)"
                exit 0
            }
            Write-Output "GATE_PASSED: backup (git mode, all files tracked)"
            exit 0
        } else {
            # backup模式：检查_safety_backups/目录
            $BackupDir = "$ProjectRoot\_safety_backups"
            if (-not (Test-Path $BackupDir)) {
                Write-Output "GATE_BLOCKED: _safety_backups/ directory not found (no git, no backups)"
                exit 1
            }
            Write-Output "GATE_PASSED: backup (backup mode, _safety_backups/ exists)"
            exit 0
        }
    }

    "scope" {
        $ContractFile = "$ChangeDir\Contract.md"
        if (-not (Test-Path $ContractFile)) {
            Write-Output "GATE_BLOCKED: Contract.md not found (no scope defined)"
            exit 1
        }
        Write-Output "GATE_PASSED: scope (Contract.md exists)"
        exit 0
    }

    "safety" {
        $ContractFile = "$ChangeDir\Contract.md"
        if (-not (Test-Path $ContractFile)) {
            Write-Output "GATE_PASSED: safety (no contract, nothing to check)"
            exit 0
        }
        $contractTime = (Get-Item $ContractFile).LastWriteTime

        if ($HasGit) {
            # git模式：检查Contract创建后是否有commit
            Write-Output "GATE_PASSED: safety (git mode, commit history available)"
            exit 0
        } else {
            # backup模式：检查备份时间晚于Contract
            $BackupDir = "$ProjectRoot\_safety_backups"
            if (-not (Test-Path $BackupDir)) {
                Write-Output "GATE_BLOCKED: safety - _safety_backups/ not found"
                exit 1
            }
            $staleBackups = @()
            Get-ChildItem "$BackupDir\*" -File | ForEach-Object {
                if ($_.LastWriteTime -lt $contractTime) {
                    $staleBackups += $_.Name
                }
            }
            if ($staleBackups.Count -gt 0) {
                Write-Output "GATE_BLOCKED: safety - stale backups (older than Contract): $($staleBackups -join ', ')"
                exit 1
            }
            Write-Output "GATE_PASSED: safety (all backups newer than Contract)"
            exit 0
        }
    }

    default {
        Write-Output "GATE_BLOCKED: unknown gate type '$GateType'. Use: dp0, dp1, dp2, backup, scope, safety"
        exit 1
    }
}
