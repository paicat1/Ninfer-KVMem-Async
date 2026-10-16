@echo off
REM 编译并发核微基准（用引擎构建同一套 CUDA 13.3 便携 toolkit + VS2022 环境）
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (echo VCVARS-FAILED & exit /b 1)
set "PATH=J:\Bonsai\landing\cuda-13.3\bin;%PATH%"
nvcc -O2 -arch=sm_120a -o "J:\ninfer-kvmem\tools\concur_bench.exe" "J:\ninfer-kvmem\tools\concur_bench.cu"
if errorlevel 1 (echo NVCC-FAILED & exit /b 1)
echo BUILD-OK
