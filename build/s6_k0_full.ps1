# S6 全图 -k 0 全量扫错（不带 target，扫全部 build target 至收敛）
# 日志保留到 CODE 复核销账后方可清理（2026-10-07 铁律）
$ErrorActionPreference = "Continue"
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$ninja  = "J:\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$build  = "J:\Bonsai-Official\.temp\build-120a"

Set-Location $build
# 全图扫描（不带 target）：-k 0 不因单错停止，一次暴露全部错误；默认 target=all
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$ninja`" -k 0 -j 16"
exit $LASTEXITCODE