@echo off
rem ============================================================
rem  NInfer 官方线启动器（Bonsai-27B-NInfer-kvmem）
rem  双击即开 GUI；用 start 让本 CMD 窗口立即关闭（不留空窗）。
rem  serve 由 GUI 以「新控制台窗口」拉起：关窗 = 停服。
rem ============================================================
rem P0 (2026-10-09): interpreter resolution. Old hardcode was "D:\Python311\pythonw.exe" (absent on this machine).
rem Order: PATH pythonw.exe -> J:\miniconda3 -> %LOCALAPPDATA%\Programs\Python\Python312
set "PYW="
for %%P in (pythonw.exe) do if not defined PYW set "PYW=%%~$PATH:P"
if not defined PYW if exist "J:\miniconda3\pythonw.exe" set "PYW=J:\miniconda3\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not defined PYW (
  echo REFUSE: pythonw.exe not found (PATH / J:\miniconda3 / %%LOCALAPPDATA%%\Programs\Python\Python312).
  pause
  exit /b 3
)
start "NInfer-Launcher" "%PYW%" "%~dp0ninfer_launcher.py"
