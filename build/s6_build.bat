@echo off
setlocal
call "j:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set "CMAKE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "BUILD=J:\Bonsai-Official\.temp\build-120a"
set "PATH=J:\Bonsai\landing\cuda-13.3\bin;%PATH%"
"%CMAKE%" --build "%BUILD%" --target ninfer-serve -j 16
echo BUILD_EXIT=%ERRORLEVEL%