@echo off
REM 挂账54 fix v2 incremental rebuild (kv_store.h touched; deps tracking proven 2026-10-13).
set BUILD=J:\ninfer-kvmem\.temp\build-1208a
set LOG=J:\ninfer-kvmem\logs\build_54fix2.log
call J:\ninfer-kvmem\build\s6_1208a.bat
