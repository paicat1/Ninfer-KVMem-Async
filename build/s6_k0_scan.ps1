# S6 -k 0 全量扫错脚本（vcvars64 环境初始化后跑 ninja）
$ErrorActionPreference = "Continue"
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$ninja  = "J:\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$build  = "J:\Bonsai-Official\.temp\build-120a"

Set-Location $build
# 用 cmd 初始化 vcvars 环境，然后跑 ninja -k 0（把所有编译错误一次暴露，不因单个失败停止）
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$ninja`" -k 0 ninfer-serve -j 16"
exit $LASTEXITCODE