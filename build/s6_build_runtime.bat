@echo off
setlocal
call "j:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set "CMAKE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
"%CMAKE%" --build "J:\Bonsai-Official\.temp\build-120a" --target ninfer_runtime_support -j 16
echo BUILD_EXIT=%ERRORLEVEL%