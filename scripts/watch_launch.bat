@echo off
rem DEPRECATED 2026-10-14: cmd black window + mojibake title. Use watch_launch.ps1
rem (PowerShell, blue window, correct Chinese title) instead.
rem Ninfer-KVMem-Async 守望者启动器（2026-10-14 用户令改名）
rem 窗口纪律：可见窗口 + 标题含任务与关闭条件；脚本退出即窗口自动关闭
title Ninfer-KVMem-Async守望者 [运行中] - 8h 后自关（关窗=停值守）
cd /d J:\ninfer-kvmem
powershell -NoProfile -ExecutionPolicy Bypass -File J:\ninfer-kvmem\scripts\valley_watch.ps1
