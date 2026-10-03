#Requires -Version 3.0
# Asset Allocation - 서버 업데이트: git pull -> 패키지 갱신 -> 서비스 재시작
# 재시작은 관리자 권한일 때만 자동 (아니면 안내만)

$TaskName = "HAA-Allocation"
$ProjectDir = if ($env:_HAA_ROOT) { $env:_HAA_ROOT } else { Split-Path -Parent $PSScriptRoot }
Set-Location $ProjectDir

Write-Output "[1/3] git pull"
git pull --ff-only
if ($LASTEXITCODE -ne 0) {
    Write-Output "[오류] git pull 실패 — 서버에서 파일을 직접 수정했다면 git status 로 확인하세요."
    Read-Host "`n계속하려면 Enter"; exit 1
}

Write-Output "[2/3] 패키지 갱신"
$venvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Output "[오류] .venv 가 없습니다. install_service.bat 을 먼저 실행하세요."
    Read-Host "`n계속하려면 Enter"; exit 1
}
& $venvPy -m pip install -q -r requirements.txt

Write-Output "[3/3] 서비스 재시작"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
schtasks /query /tn $TaskName 2>$null | Out-Null
$registered = ($LASTEXITCODE -eq 0)
if ($registered -and $isAdmin) {
    schtasks /end /tn $TaskName 2>$null | Out-Null
    $venvDir = (Join-Path $ProjectDir ".venv").ToLower()
    Get-WmiObject Win32_Process -Filter "name='pythonw.exe' or name='python.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLower().StartsWith($venvDir) } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    schtasks /run /tn $TaskName | Out-Null
    Write-Output "       재시작 완료"
} elseif ($registered) {
    Write-Output "       관리자 권한이 아니라 재시작하지 못했습니다. update.bat 을 '관리자로 실행' 하세요."
} else {
    Write-Output "       서비스 미등록 — install_service.bat 으로 설치하거나 run.bat 으로 실행하세요."
}
Write-Output ""
Write-Output "업데이트 완료."
Read-Host "`n계속하려면 Enter"
