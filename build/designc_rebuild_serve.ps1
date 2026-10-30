# S6 serve 重编（Design C 生效，build-120a 增量）
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$ninja  = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
Set-Location "J:\ninfer-kvmem\build-out\build-120a"
cmd /c "call `"$vcvars`" >nul 2>&1 && `"$ninja`" ninfer-serve -j 16"
exit $LASTEXITCODE