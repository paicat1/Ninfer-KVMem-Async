@echo off
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
rem
rem  Interpreter resolution order (explicit paths FIRST, PATH search last):
rem    J:\miniconda3\pythonw.exe
rem    %LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe
rem    first pythonw.exe on PATH
rem  A goto label is used instead of a multi-line "if (...)" block: cmd's
rem  block parsing is the fragile part, and this file must never break the
rem  double-click path again.
rem ============================================================
setlocal
set "PYW="
if exist "J:\miniconda3\pythonw.exe" set "PYW=J:\miniconda3\pythonw.exe"
if not defined PYW if exist "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not defined PYW for %%P in (pythonw.exe) do if not defined PYW set "PYW=%%~$PATH:P"
if not defined PYW goto no_pyw
start "NInfer-Launcher" "%PYW%" "%~dp0ninfer_launcher.py"
exit /b 0

:no_pyw
echo REFUSE: pythonw.exe not found.
echo   tried: J:\miniconda3\pythonw.exe
echo          %%LOCALAPPDATA%%\Programs\Python\Python312\pythonw.exe
echo          PATH
pause
exit /b 3
