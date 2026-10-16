@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (echo VCVARS-FAILED & exit /b 1)
set "PATH=J:\Bonsai\landing\cuda-13.3\bin;%PATH%"
nvcc -O2 -arch=sm_120a -o "J:\ninfer-kvmem\tools\pageable_bench.exe" "J:\ninfer-kvmem\tools\pageable_bench.cu"
if errorlevel 1 (echo NVCC-FAILED & exit /b 1)
echo BUILD-OK
