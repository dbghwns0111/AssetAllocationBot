@echo off
title HAA Allocation - Update
powershell -ExecutionPolicy Bypass -NoProfile -Command "$env:_HAA_ROOT='%~dp0'.TrimEnd('\'); & ([ScriptBlock]::Create([System.IO.File]::ReadAllText('%~dp0scripts\update.ps1',[Text.Encoding]::UTF8)))"
if %errorlevel% neq 0 pause
