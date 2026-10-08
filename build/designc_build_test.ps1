# Design C fork 测试构建：独立 build 目录 BUILD_TESTING=ON，只编 ninfer_qwen3_5_frontend_test
$ErrorActionPreference = "Continue"
$vcvars = "J:\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$cmake  = "C:\Program Files\CMake\bin\cmake.exe"
$ninja  = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
$src    = "J:\Bonsai-Official\official-repo\ninfer-fusion-kvmem\src-tree\fusion-engine-src"
$build  = "J:\Bonsai-Official\.temp\build-120a-test"

if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Path $build | Out-Null

cmd /c "call `"$vcvars`" >nul 2>&1 && cd /d `"$build`" && `"$cmake`" -G Ninja `"$src`" -DCMAKE_MAKE_PROGRAM=`"$ninja`" -DCMAKE_CUDA_ARCHITECTURES=120a -DNINFER_SM120_NATIVE=ON -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON -DCMAKE_TOOLCHAIN_FILE=J:/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_INSTALLED_DIR=J:/Bonsai-Official/.temp/build-120a/vcpkg_installed >nul 2>&1 && `"$ninja`" ninfer_qwen3_5_frontend_test -j 16"
Write-Output "CMake 配置+编译退出码: $LASTEXITCODE"
exit $LASTEXITCODE