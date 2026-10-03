@echo off
title Asset Allocation - Uninstall Service
rem Relaunch as administrator if needed (service restart / firewall need admin rights)
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell -ExecutionPolicy Bypass -NoProfile -Command "$env:_HAA_ROOT='%~dp0'.TrimEnd('\'); & ([ScriptBlock]::Create([System.IO.File]::ReadAllText('%~dp0scripts\uninstall_service.ps1',[Text.Encoding]::UTF8)))"
if %errorlevel% neq 0 pause
