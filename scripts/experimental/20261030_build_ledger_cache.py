# -*- coding: utf-8 -*-
"""20261030: BUILD-LEDGER-GATE 加 size+mtime 缓存（方案A）。
未变件跳过重哈希，变化件/新件/无缓存仍全量算；缓存损坏=当空（fail-closed 不变）。
缓存落 work\\.build-ledger-sha-cache.json（work/ 已 gitignore，不入库）。
newline='' 保行尾；锚点唯一匹配失败即退出不写。
"""
import sys

PATH = r"j:\ninfer-kvmem\scripts\gates.ps1"

OLD = """            $blSha = [System.Security.Cryptography.SHA256]::Create()
            $blMiss = @()
            foreach ($blF in (Get-ChildItem $blDir -Filter '*.exe' -File)) {
                $blFs = [System.IO.File]::OpenRead($blF.FullName)
                try { $blH = ([System.BitConverter]::ToString($blSha.ComputeHash($blFs)) -replace '-', '').ToLower() }
                finally { $blFs.Dispose() }
                if (-not $blKnown.ContainsKey($blH)) { $blMiss += $blF.Name }
            }
            $blSha.Dispose()""".replace("\n", "\r\n")

NEW = """            # 缓存（2026-10-30）：size+mtime 未变的已算件跳过重哈希——台账登记时已有 sha，
            # 身份不变则重算无新信息。变化件/新件/缓存缺失或损坏 => 全量重算，拦截语义不变。
            $blCacheP = Join-Path $blRoot 'work\\.build-ledger-sha-cache.json'
            $blCache = @{}
            if (Test-Path $blCacheP) {
                try {
                    $blRaw = Get-Content $blCacheP -Raw -Encoding UTF8 | ConvertFrom-Json
                    foreach ($p in $blRaw.PSObject.Properties) { $blCache[$p.Name] = [string]$p.Value }
                } catch { $blCache = @{} }
            }
            $blSha = [System.Security.Cryptography.SHA256]::Create()
            $blMiss = @()
            $blNewCache = @{}
            $blHit = 0
            $blCalc = 0
            foreach ($blF in (Get-ChildItem $blDir -Filter '*.exe' -File)) {
                $blSig = ([string]$blF.Length) + '|' + ([string]$blF.LastWriteTimeUtc.Ticks)
                $blCached = $null
                if ($blCache.ContainsKey($blF.Name)) {
                    $blParts = $blCache[$blF.Name] -split ' '
                    if ($blParts.Count -eq 2 -and $blParts[0] -eq $blSig) { $blCached = $blParts[1] }
                }
                if ($blCached) {
                    $blH = $blCached
                    $blHit++
                } else {
                    $blFs = [System.IO.File]::OpenRead($blF.FullName)
                    try { $blH = ([System.BitConverter]::ToString($blSha.ComputeHash($blFs)) -replace '-', '').ToLower() }
                    finally { $blFs.Dispose() }
                    $blCalc++
                }
                $blNewCache[$blF.Name] = $blSig + ' ' + $blH
                if (-not $blKnown.ContainsKey($blH)) { $blMiss += $blF.Name }
            }
            $blSha.Dispose()
            try { $blNewCache | ConvertTo-Json | Set-Content $blCacheP -Encoding UTF8 } catch {}
            Write-Output ("build-ledger: " + ($blHit + $blCalc) + " 件（缓存命中 " + $blHit + " / 重算 " + $blCalc + "）")""".replace("\n", "\r\n")

with open(PATH, "r", encoding="utf-8-sig", newline="") as f:
    t = f.read()

if "build-ledger-sha-cache" in t:
    print("ALREADY-PATCHED")
    sys.exit(0)
if OLD not in t:
    print("ANCHOR-MISSING: old block not found verbatim")
    sys.exit(1)

t = t.replace(OLD, NEW, 1)

with open(PATH, "w", encoding="utf-8-sig", newline="") as f:
    f.write(t)

print("PATCHED-OK: build-ledger cache (size+mtime) applied")
