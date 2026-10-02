@echo off
title HAA Allocation - Install Service
powershell -ExecutionPolicy Bypass -NoProfile -Command "$env:_HAA_ROOT='%~dp0'.TrimEnd('\'); & ([ScriptBlock]::Create([System.IO.File]::ReadAllText('%~dp0scripts\install_service.ps1',[Text.Encoding]::UTF8)))"
if %errorlevel% neq 0 pause
