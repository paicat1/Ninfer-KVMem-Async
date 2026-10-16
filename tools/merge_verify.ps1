# merge_verify.ps1 - T-MERGE-VERIFY machine gate (D1 handover, 2026-09-09 user approved)
# Verifies a dev->master merge is a REAL merge with FULL content absorption.
#
# Usage:
#   .\merge_verify.ps1 [-Base master] [-Head dev] [-MergeCommit <hash>] [-SelfTest]
#
# Checks (any failure -> exit 1 with [MERGE_VERIFY] FAIL evidence):
#   C1 merge-base non-empty          (unrelated-histories guard, 09-01 lesson)
#   C2 git diff Base Head is EMPTY   (content fully absorbed)
#   C3 merge commit has 2 parents AND parent2 == Head tip   (needs -MergeCommit)
#   C4 ancestor containment: Head tip IS ancestor of Base tip (post-merge)
#   C5 reflog evidence of a real merge command (best-effort, GC-tolerant)
#
# History:
#   09-01 fake-merge incident: merge commit existed but content was never
#   absorbed; undetected ~2 months; ended in FULL repository history rebuild.
#   T-MERGE-VERIFY iron rule born from it. 09-09 D1 machine handover: the
#   three manual checks became this script (user approved, dual-side reviewed).
#
# Windows pipe lesson (09-01): git filter-branch --msg-filter must use byte
# streams (sys.stdin.buffer / sys.stdout.buffer) or UTF-8 Chinese corrupts.
# NEVER use filter-repo (rewrites from root -> root hash changes -> branches
# become unrelated). Only filter-branch --msg-filter preserves chain topology.

param(
    [string]$Base = "master",
    [string]$Head = "dev",
    [string]$MergeCommit = "",
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
$script:Fails = @()
$script:Warns = @()

function Add-Fail([string]$check, [string]$detail) {
    $script:Fails += "  FAIL[$check] $detail"
}

function Add-Warn([string]$check, [string]$detail) {
    $script:Warns += "  WARN[$check] $detail"
}

function Invoke-Checks([string]$repoDir, [string]$b, [string]$h, [string]$mc) {
    $script:Fails = @()
    $script:Warns = @()
    Push-Location $repoDir
    try {
        # C1 merge-base non-empty
        $mb = git merge-base $b $h 2>$null
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($mb)) {
            Add-Fail "C1-merge-base" "empty -> unrelated histories between $b and $h"
        }

        # C2 content absorbed: diff must be empty
        $diff = git diff $b $h --stat 2>$null
        if ($diff) {
            Add-Fail "C2-content" ("git diff $b $h NOT empty: " + (($diff | Out-String).Trim() -replace "`r?`n", " | "))
        }

        # C3 merge commit structure (only when -MergeCommit provided)
        if ($mc) {
            $parents = (git log -1 --format=%P $mc 2>$null) -split '\s+' | Where-Object { $_ }
            if ($parents.Count -lt 2) {
                Add-Fail "C3-parents" "$mc has $($parents.Count) parent(s), not a merge commit"
            } else {
                $headTip = git rev-parse $h 2>$null
                if ($parents[1] -ne $headTip) {
                    Add-Fail "C3-parent2" "parent2 ($($parents[1])) != $h tip ($headTip)"
                }
            }
        }

        # C4 ancestor containment: head tip contained in base history
        git merge-base --is-ancestor $h $b 2>$null
        if ($LASTEXITCODE -ne 0) {
            Add-Fail "C4-ancestor" "$h tip is NOT an ancestor of $b (dev content NOT in master)"
        }

        # C5 reflog evidence of real merge (best-effort only, GC-tolerant;
        # core guarantee is C1/C2/C4 + C3, so C5 is a WARN, never a FAIL)
        if ($mc) {
            $entry = git reflog $b --format="%H|%gs" 2>$null |
                Where-Object { $_.StartsWith($mc) } |
                Select-Object -First 1
            if (-not ($entry -match "(?i)\bmerge\b")) {
                Add-Warn "C5-reflog" "no merge-command evidence in $b reflog for $mc (best-effort only; may be GC'd)"
            }
        }
    } finally {
        Pop-Location
    }
    return ($script:Fails.Count -eq 0)
}

function Invoke-SelfTest {
    # Fixture: temp repo -> base commit -> branch dev2 -> diverge -> merge --no-ff
    #          -> PASS expected. Then diverge again -> FAIL expected.
    $tmp = Join-Path $env:TEMP ("mvselftest_" + [Guid]::NewGuid().ToString('N').Substring(0, 8))
    $results = @()
    try {
        git init -q -b bra $tmp
        Push-Location $tmp
        try {
            git config user.name "selftest"; git config user.email "selftest@local"
            Set-Content -Path "a.txt" -Value "base" -Encoding ASCII
            git add -A; git commit -q -m "base"
            git checkout -q -b dev2
            Set-Content -Path "a.txt" -Value "feat" -Encoding ASCII
            git add -A; git commit -q -m "feat"
            git checkout -q bra
            $featTip = git rev-parse dev2
            git merge --no-ff dev2 -q -m "merge dev2" | Out-Null

            # PASS scenario
            $null = Invoke-Checks $tmp "bra" "dev2" (git rev-parse bra)
            $results += if ($script:Fails.Count -eq 0) { "PASS-scenario: OK" } else { "PASS-scenario: UNEXPECTED FAIL -> " + ($script:Fails -join " ; ") }

            # FAIL scenario: diverge bra from dev2 (new commit not in dev2)
            Set-Content -Path "b.txt" -Value "extra" -Encoding ASCII
            git add -A; git commit -q -m "extra on bra"
            $null = Invoke-Checks $tmp "bra" "dev2" ""
            $results += if ($script:Fails.Count -gt 0) { "FAIL-scenario: OK (detected: " + ($script:Fails[0]) + ")" } else { "FAIL-scenario: UNEXPECTED PASS" }
        } finally {
            Pop-Location
        }
    } finally {
        if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
    }
    $ok = -not ($results | Where-Object { $_ -match "UNEXPECTED" })
    Write-Output ("[MERGE_VERIFY] SELFTEST " + $(if ($ok) { "PASS" } else { "FAIL" }))
    $results | ForEach-Object { Write-Output ("  " + $_) }
    if (-not $ok) { exit 1 }
}

# --- main ---
if ($SelfTest) {
    Invoke-SelfTest
    exit $LASTEXITCODE
}

$repo = git rev-parse --show-toplevel 2>$null
if (-not $repo) { Write-Output "[MERGE_VERIFY] FAIL: not inside a git repository"; exit 1 }

$null = Invoke-Checks $repo $Base $Head $MergeCommit
$headTip = git rev-parse $Head 2>$null
Write-Output ("[MERGE_VERIFY] Base=$Base Head=$Head MergeCommit=" + $(if ($MergeCommit) { $MergeCommit } else { "(not given, C3/C5 skipped)" }))
if ($script:Fails.Count -eq 0) {
    Write-Output "[MERGE_VERIFY] PASS"
    if ($script:Warns.Count -gt 0) { $script:Warns | ForEach-Object { Write-Output $_ } }
    exit 0
} else {
    Write-Output "[MERGE_VERIFY] FAIL ($($script:Fails.Count) check(s)):"
    $script:Fails | ForEach-Object { Write-Output $_ }
    if ($script:Warns.Count -gt 0) { $script:Warns | ForEach-Object { Write-Output $_ } }
    exit 1
}
