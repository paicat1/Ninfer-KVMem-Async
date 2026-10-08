@echo off
REM ============================================================
REM  s6_1208a.bat -- S6 new baseline (20261008 + our 3 patch sets) full build
REM  SRC   : official-repo\infer-fusion-kvmem\src-tree\fusion-engine-src
REM          (current checkout branch = s6-20261008)
REM  BUILD : .temp\build-1208a   (reuses vcpkg_installed from .temp\build-120a)
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
call "j:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set "CMAKE=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
set "SRC=J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
set "BUILD=J:\Bonsai-Official\.temp\build-1208a"
set "PATH=J:\Bonsai\landing\cuda-13.3\bin;%PATH%"

echo === CONFIGURE ===
"%CMAKE%" -S "%SRC%" -B "%BUILD%" -G Ninja -DCMAKE_MAKE_PROGRAM="%NINJA%" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=120a -DCMAKE_CUDA_COMPILER=J:/Bonsai/landing/cuda-13.3/bin/nvcc.exe -DNINFER_SM120_NATIVE=ON -DCMAKE_TOOLCHAIN_FILE=J:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows -DVCPKG_INSTALLED_DIR=J:/Bonsai-Official/.temp/build-120a/vcpkg_installed -DNINFER_BUILD_APPS=ON -DBUILD_TESTING=OFF -DNINFER_BUILD_BENCHMARKS=OFF
echo CONFIGURE_EXIT=%ERRORLEVEL%
if not "%ERRORLEVEL%"=="0" exit /b 1

echo === BUILD (full graph, ninja -k 0 -j 16) ===
"%CMAKE%" --build "%BUILD%" -- -k 0 -j 16
echo BUILD_EXIT=%ERRORLEVEL%
