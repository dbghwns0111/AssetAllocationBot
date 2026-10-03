#Requires -Version 3.0
# Asset Allocation - 서비스 설치 (클라우드 PC, 관리자 권한)
#  1) .venv 생성 + 패키지 설치
#  2) 작업 스케줄러 등록 (부팅 시 자동 시작, 비정상 종료 시 1분 후 재시작)
#  3) Windows 방화벽 인바운드 허용 (ZeroTier 대역만)
#  4) 즉시 시작

$TaskName = "HAA-Allocation"
$ProjectDir = if ($env:_HAA_ROOT) { $env:_HAA_ROOT } else { Split-Path -Parent $PSScriptRoot }

function Pause-Exit($code) { Read-Host "`n계속하려면 Enter"; exit $code }

Write-Output ""
Write-Output " ===================================="
Write-Output "   Asset Allocation - 서비스 설치"
Write-Output " ===================================="
Write-Output "   프로젝트: $ProjectDir"
Write-Output ""

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Output "[오류] 관리자 권한이 필요합니다. install_service.bat 을 우클릭 -> 관리자로 실행 하세요."
    Pause-Exit 1
}

# ── .env 확인 ──────────────────────────────────────────────────────────────
$envFile = Join-Path $ProjectDir ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $ProjectDir ".env.example") $envFile
    Write-Output "[안내] .env 파일을 만들었습니다. 메모장이 열리면 WEB_PASSWORD 등을 입력하고 저장한 뒤 닫으세요."
    Start-Process notepad.exe $envFile -Wait
}
$envText = Get-Content $envFile -Raw
$port = 5001
if ($envText -match "(?m)^\s*HAA_PORT\s*=\s*(\d+)") { $port = [int]$Matches[1] }
if ($envText -notmatch "(?m)^\s*WEB_PASSWORD\s*=\s*\S+") {
    Write-Output "[경고] .env 의 WEB_PASSWORD 가 비어 있습니다. 외부 접속 시 비밀번호 설정을 권장합니다."
}

# ── Python 찾기 (venv 생성용) ──────────────────────────────────────────────
$venvPy = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    $py = $null
    foreach ($exe in @("python.exe")) {
        $c = Get-Command $exe -ErrorAction SilentlyContinue
        if ($c -and $c.Path -and ($c.Path -notlike "*WindowsApps*")) { $py = $c.Path }   # PS 4.0 호환: .Source 대신 .Path
    }
    if (-not $py) {
        $roots = @("$env:USERPROFILE\miniconda3", "$env:USERPROFILE\anaconda3", "C:\ProgramData\miniconda3",
                   "C:\ProgramData\anaconda3", "$env:USERPROFILE\AppData\Local\Programs\Python\Python3*", "C:\Python3*")
        foreach ($root in $roots) {
            foreach ($r in (Resolve-Path $root -ErrorAction SilentlyContinue)) {
                $cand = Join-Path $r.Path "python.exe"
                if (Test-Path $cand) { $py = $cand; break }
            }
            if ($py) { break }
        }
    }
    if (-not $py) {
        $py = (Read-Host "python.exe 전체 경로를 입력하세요").Trim('"')
        if (-not (Test-Path $py)) { Write-Output "[오류] 경로가 올바르지 않습니다."; Pause-Exit 1 }
    }
    $ok = & $py -c "import sys; print(sys.version_info >= (3, 9))"
    if ($ok -ne "True") { Write-Output "[오류] Python 3.9 이상이 필요합니다: $py"; Pause-Exit 1 }

    Write-Output "[1/5] 가상환경 생성 ($py)"
    & $py -m venv (Join-Path $ProjectDir ".venv")
    if ($LASTEXITCODE -ne 0) { Write-Output "[오류] venv 생성 실패"; Pause-Exit 1 }
} else {
    Write-Output "[1/5] 가상환경 있음 (건너뜀)"
}

Write-Output "[2/5] 패키지 설치"
& $venvPy -m pip install -q --upgrade pip
& $venvPy -m pip install -q -r (Join-Path $ProjectDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Output "[오류] 패키지 설치 실패"; Pause-Exit 1 }

# ── 런처 + 작업 스케줄러 ───────────────────────────────────────────────────
Write-Output "[3/5] 작업 스케줄러 등록 ($TaskName)"
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectDir "logs") | Out-Null
$pythonw = Join-Path $ProjectDir ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $ProjectDir "run_service.bat"
"@echo off`r`ncd /d `"$ProjectDir`"`r`n`"$pythonw`" main.py" | Out-File -FilePath $launcher -Encoding ascii

schtasks /query /tn $TaskName 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    schtasks /end /tn $TaskName 2>$null | Out-Null
    schtasks /delete /tn $TaskName /f 2>$null | Out-Null
}

$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Asset Allocation 웹 (포트 $port)</Description></RegistrationInfo>
  <Triggers><BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger></Triggers>
  <Principals><Principal><UserId>SYSTEM</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>
  </Settings>
  <Actions><Exec><Command>$launcher</Command><WorkingDirectory>$ProjectDir</WorkingDirectory></Exec></Actions>
</Task>
"@
$xmlPath = [System.IO.Path]::GetTempFileName() + ".xml"
$taskXml | Out-File -FilePath $xmlPath -Encoding unicode
schtasks /create /tn $TaskName /xml $xmlPath /f | Out-Null
$rc = $LASTEXITCODE
Remove-Item $xmlPath -Force
if ($rc -ne 0) { Write-Output "[오류] 작업 등록 실패"; Pause-Exit 1 }

# ── 방화벽 (ZeroTier 대역만 허용) ──────────────────────────────────────────
Write-Output "[4/5] 방화벽 인바운드 규칙 (TCP $port)"
$remote = Read-Host "   허용할 원격 IP 범위 [기본: 10.73.56.0/24 = ZeroTier]"
if (-not $remote) { $remote = "10.73.56.0/24" }
$ruleName = "HAA Allocation $port"   # 기존 서버 규칙과 맞추기 위해 이름 유지
netsh advfirewall firewall delete rule name="$ruleName" | Out-Null
netsh advfirewall firewall add rule name="$ruleName" dir=in action=allow protocol=TCP localport=$port remoteip=$remote | Out-Null
Write-Output "       '$ruleName' : $remote -> TCP $port 허용"

Write-Output "[5/5] 시작"
schtasks /run /tn $TaskName | Out-Null

Write-Output ""
Write-Output " ===================================="
Write-Output "   설치 완료"
Write-Output "   - 서버에서:     http://localhost:$port"
Write-Output "   - 휴대폰/집 PC: http://<클라우드PC ZeroTier IP>:$port"
Write-Output "   - 부팅 시 자동 시작, 비정상 종료 시 1분 후 재시작"
Write-Output "   - 로그: logs\haa.log"
Write-Output " ===================================="
Pause-Exit 0
