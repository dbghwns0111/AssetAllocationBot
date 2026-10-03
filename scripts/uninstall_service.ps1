#Requires -Version 3.0
# Asset Allocation - 서비스 제거 (관리자 권한)
# 주의: 같은 서버의 CryptoSplit 을 건드리지 않도록 "이 프로젝트 .venv 의 python" 프로세스만 종료한다.

$TaskName = "HAA-Allocation"
$ProjectDir = if ($env:_HAA_ROOT) { $env:_HAA_ROOT } else { Split-Path -Parent $PSScriptRoot }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Output "[오류] 관리자 권한이 필요합니다. uninstall_service.bat 을 우클릭 -> 관리자로 실행 하세요."
    Read-Host "`n계속하려면 Enter"; exit 1
}

Write-Output "[1/3] 작업 종료 및 프로세스 정리"
schtasks /end /tn $TaskName 2>$null | Out-Null
$venvDir = (Join-Path $ProjectDir ".venv").ToLower()
Get-WmiObject Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($venvDir) } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Output "       종료: PID $($_.ProcessId)" }

Write-Output "[2/3] 작업 스케줄러 제거"
schtasks /delete /tn $TaskName /f 2>$null | Out-Null

Write-Output "[3/3] 방화벽 규칙 제거"
$port = 5001
$envFile = Join-Path $ProjectDir ".env"
if ((Test-Path $envFile) -and ((Get-Content $envFile -Raw) -match "(?m)^\s*HAA_PORT\s*=\s*(\d+)")) { $port = [int]$Matches[1] }
netsh advfirewall firewall delete rule name="HAA Allocation $port" | Out-Null

Write-Output ""
Write-Output "완료. (.venv, data, .env 는 남겨둡니다)"
Read-Host "`n계속하려면 Enter"
