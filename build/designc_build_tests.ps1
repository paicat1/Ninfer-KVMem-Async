# 编译 ninfer_tests bundle（含 Design C frontend 测试）并打印退出码
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$ninja  = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
Set-Location "J:\Bonsai-Official\.temp\build-120a-test"
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$ninja`" ninfer_tests -j 16"
exit $LASTEXITCODE