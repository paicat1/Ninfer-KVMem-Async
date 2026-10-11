@echo off
REM ============================================================
REM  s6_1208a.bat -- 本仓（Qwen3.8-27B-Coder390 线）引擎全量构建
REM
REM  归属（2026-10-12 解耦后，T-NO-FOREIGN-WRITE）：
REM   本脚本只读写本仓目录；源码树与构建目录都在本仓内。
REM   · SRC   : J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src
REM             本仓自持源码树，分支 line-coder390
REM             基 = 上游 1314521gjy/ninfer-fusion-kvmem + Bonsai 线 cherry-pick
REM                  + 本线补丁（见 patches/ 与 构建史 三·十九/三·二十）
REM   · BUILD : J:\ninfer-kvmem\.temp\build-1208a （本仓构建目录，.gitignore 已排除）
REM   · VSLANG=1033 : MSVC 输出英文 "Note: including file"，ninja 才能识别头依赖
REM             （挂账45 根因：中文 /showIncludes 前缀未被识别 => 改头后不重编消费者）
REM   · 日志  : J:\ninfer-kvmem\.temp\build_engine.log
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (echo VCVARS-FAILED & exit /b 1)
REM VSLANG 必须在 vcvars 之后设：vcvars64.bat 会按 VS 界面语言覆盖它
REM （2026-10-12 实测：设在之前时 /showIncludes 仍是中文"注意: 包含文件:"）
set "VSLANG=1033"
set "PATH=J:\vcpkg\downloads\tools\ninja-1.13.2-windows;J:\Bonsai\landing\cuda-13.3\bin;%PATH%"
set "VCPKG_ROOT=J:\vcpkg"
set "VCPKG_TARGET_TRIPLET=x64-windows"
set "SRC=J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src"
set "BUILD=J:\ninfer-kvmem\.temp\build-1208a"
set "LOG=J:\ninfer-kvmem\.temp\build_engine.log"
if not exist "%BUILD%" mkdir "%BUILD%"

echo === build started %DATE% %TIME% === > "%LOG%"
if not exist "%BUILD%\CMakeCache.txt" (
  echo [configure] Ninja Release 120a ... >> "%LOG%"
  cmake -G Ninja -S "%SRC%" -B "%BUILD%" ^
    -DCMAKE_BUILD_TYPE=Release ^
    -DCMAKE_CUDA_ARCHITECTURES=120a ^
    -DCMAKE_CUDA_COMPILER=J:/Bonsai/landing/cuda-13.3/bin/nvcc.exe ^
    -DNINFER_SM120_NATIVE=ON ^
    -DCMAKE_PREFIX_PATH="J:\vcpkg\installed\x64-windows" ^
    -DCMAKE_TOOLCHAIN_FILE=J:/vcpkg/scripts/buildsystems/vcpkg.cmake ^
    -DVCPKG_TARGET_TRIPLET=x64-windows ^
    -DNINFER_BUILD_APPS=ON -DBUILD_TESTING=OFF -DNINFER_BUILD_BENCHMARKS=OFF >> "%LOG%" 2>&1
  if errorlevel 1 (echo CONFIGURE-FAILED >> "%LOG%" & echo CONFIGURE-FAILED & exit /b 1)
  echo CONFIGURE-OK >> "%LOG%"
)
echo [build] full graph, 6 jobs ... >> "%LOG%"
cmake --build "%BUILD%" --parallel 6 >> "%LOG%" 2>&1
echo BUILD-EXIT=%ERRORLEVEL% >> "%LOG%"
echo BUILD-EXIT=%ERRORLEVEL%
