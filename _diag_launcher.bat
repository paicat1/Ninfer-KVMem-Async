@echo on
rem ============================================================
rem  NInfer launcher GUI  (this line: ninfer-kvmem / model Coder390)
rem
rem  Double-click to open the GUI. "start" lets this CMD window close
rem  immediately, so no empty console is left behind.
rem  The GUI starts serve in a NEW console window: closing that = stopping
rem  the server.
rem
rem  ASCII-only ON PURPOSE: cmd parses a .bat in the OEM/ANSI codepage
rem  (GBK on this machine). Non-ASCII bytes in a .bat can swallow line
rem  breaks and silently break the script -- that is exactly what happened
rem  on 2026-10-10 when a UTF-8 Chinese comment was written into this file.
rem  Keep every line here 7-bit.
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
