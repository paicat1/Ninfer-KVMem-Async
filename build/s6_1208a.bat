@echo off
REM ============================================================
REM  s6_1208a.bat -- full engine build for THIS repo (Qwen3.8-27B-Coder390 line)
REM
REM  Ownership (2026-10-12 decoupling, T-NO-FOREIGN-WRITE):
REM    this script reads/writes ONLY inside this repo.
REM   . SRC   : J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src
REM             repo-owned source tree, branch line-coder390
REM             base = upstream 1314521gjy/ninfer-fusion-kvmem + Bonsai-line cherry-picks
REM                    + this line's patches (see patches/ and build history 3.19 / 3.20)
REM   . BUILD : J:\ninfer-kvmem\build-out\build-1208a   (repo-owned build dir, gitignored)
REM   . LOG   : J:\ninfer-kvmem\build-out\build_engine.log
REM   . VSLANG=1033 : kept for legibility only. MEASURED 2026-10-12 03:5x:
REM             (a) it does NOT switch cl to English here (build log = 29857 Chinese
REM                 include lines / 0 English ones), so it fixes nothing;
REM             (b) it is NOT needed for dependency tracking anyway: CMake auto-detects
REM                 the localized prefix (CMakeFiles/rules.ninja -> msvc_deps_prefix =
REM                 "<localized>") and the rules use "deps = msvc", and .ninja_deps
REM                 does grow during the build => header deps ARE recorded.
REM             => earlier claim "ledger45 root cause = Chinese /showIncludes prefix"
REM                is RETRACTED (see build history section 3.21 correction).
REM             => discipline "edit a header => full rebuild" STAYS until the decisive
REM                test (touch a header, then "ninja -n") confirms consumers requeue.
REM   . parallel 16 : this box has 16 threads (i5-12600KF, 128 GiB); 6 was far too slow.
REM  ASCII-only on purpose: cmd parses a .bat in the OEM/ANSI codepage.
REM ============================================================
setlocal
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (echo VCVARS-FAILED & exit /b 1)
set "VSLANG=1033"
set "PATH=J:\vcpkg\downloads\tools\ninja-1.13.2-windows;J:\Bonsai\landing\cuda-13.3\bin;%PATH%"
set "VCPKG_ROOT=J:\vcpkg"
set "VCPKG_TARGET_TRIPLET=x64-windows"
set "SRC=J:\ninfer-kvmem\engine-src\src-tree\fusion-engine-src"
if not defined BUILD set "BUILD=J:\ninfer-kvmem\build-out\build-1208a"
if not defined LOG set "LOG=J:\ninfer-kvmem\build-out\build_engine.log"
if not exist "%BUILD%" mkdir "%BUILD%"

REM append (not overwrite): every resumed run leaves a trace
echo === build started %DATE% %TIME% === >> "%LOG%"
REM IMPORTANT: this file must stay LF-safe: NO caret continuations, NO "( )" blocks,
REM NO goto/labels. 2026-10-12 lesson: this file is written with LF endings; cmd
REM mis-splits "^" continuations and parenthesised blocks => stray tokens executed
REM ("'D_TYPE' is not recognized") and a bogus CONFIGURE-FAILED echo, while the real
REM cmake calls still ran. Keep every command on ONE line.
echo [configure if needed] ... >> "%LOG%"
if not exist "%BUILD%\CMakeCache.txt" cmake -G Ninja -S "%SRC%" -B "%BUILD%" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES=120a -DCMAKE_CUDA_COMPILER=J:/Bonsai/landing/cuda-13.3/bin/nvcc.exe -DNINFER_SM120_NATIVE=ON -DCMAKE_PREFIX_PATH=J:/vcpkg/installed/x64-windows -DCMAKE_TOOLCHAIN_FILE=J:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows -DNINFER_BUILD_APPS=ON -DBUILD_TESTING=OFF -DNINFER_BUILD_BENCHMARKS=OFF >> "%LOG%" 2>&1
if not exist "%BUILD%\build.ninja" echo CONFIGURE-MISSING-BUILD-NINJA >> "%LOG%"
if exist "%BUILD%\build.ninja" echo CONFIGURE-OK >> "%LOG%"
echo [build] full graph, 16 jobs ... >> "%LOG%"
cmake --build "%BUILD%" --parallel 16 >> "%LOG%" 2>&1
echo BUILD-EXIT=%ERRORLEVEL% %DATE% %TIME% >> "%LOG%"
echo BUILD-EXIT=%ERRORLEVEL%
if exist "%BUILD%\apps\ninfer-serve.exe" powershell -NoProfile -ExecutionPolicy Bypass -File "J:\ninfer-kvmem\scripts\archive_build_output.ps1" -Source "%BUILD%\apps\ninfer-serve.exe" -Log "%LOG%"
