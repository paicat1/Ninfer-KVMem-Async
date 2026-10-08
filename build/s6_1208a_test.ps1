# S6 new-baseline STANDALONE frontend test  (20261008 + our patch sets)
# Strategy: REUSE the existing full-build dir (.temp/build-1208a) instead of a fresh
#           configure+full rebuild (~40 min). Enabling BUILD_TESTING on this dir does
#           NOT recompile the engine: BUILD_TESTING only flips NINFER_BUILD_PRODUCT_SUPPORT
#           (CMakeLists.txt L202-205) which is already ON because NINFER_BUILD_APPS=ON.
#           So only tests/ is added and the single standalone target is compiled+linked.
# Steps: reconfigure in place (BUILD_TESTING=ON) -> build the standalone test target
#        -> run it.  No destructive ops.
# ASCII-only on purpose.
$ErrorActionPreference = "Continue"
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$cmake  = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$src    = "J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
$build  = "J:\Bonsai-Official\.temp\build-1208a"
$target = "ninfer_qwen3_5_frontend_test"

Write-Output "=== RECONFIGURE IN PLACE (BUILD_TESTING=ON) ==="
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$cmake`" -S `"$src`" -B `"$build`" -DBUILD_TESTING=ON"
Write-Output "CONFIGURE_EXIT=$LASTEXITCODE"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Output "=== BUILD (target: $target) ==="
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$cmake`" --build `"$build`" --target $target -- -j 16"
Write-Output "BUILD_EXIT=$LASTEXITCODE"

Write-Output "=== LOCATE + RUN ==="
$exe = Get-ChildItem -LiteralPath $build -Recurse -File -Filter "$target.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($exe) {
  Write-Output ("EXE: " + $exe.FullName)
  & $exe.FullName
  Write-Output "TEST_EXIT=$LASTEXITCODE"
} else {
  Write-Output "TEST_EXE_NOT_FOUND under $build"
}
