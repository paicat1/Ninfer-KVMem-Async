# Design C STANDALONE frontend_test 单编（重配 build-120a-test 后只编独立 exe）
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$cmake  = "C:\Program Files\CMake\bin\cmake.exe"
$ninja  = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$src    = "J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
$build  = "J:\Bonsai-Official\.temp\build-120a-test"

Set-Location $build
# 重配（增量，保持已有 obj）+ 只编 frontend standalone exe
cmd /c "call `"$vcvars`" >nul 2>&1 && cd /d `"$build`" && `"$cmake`" `"$src`" >nul 2>&1 && `"$ninja`" ninfer_qwen3_5_frontend_test -j 16"
Write-Output "standalone frontend build exit: $LASTEXITCODE"
exit $LASTEXITCODE