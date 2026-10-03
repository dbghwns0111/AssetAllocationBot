#Requires -Version 3.0
# Asset Allocation - 개발 PC 에서 GitHub 배포 (add -> 커밋 메시지 -> commit -> push)
# 커밋 메시지는 claude CLI 가 있으면 자동 생성, 없으면 직접 입력.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectDir = if ($env:_HAA_ROOT) { $env:_HAA_ROOT } else { Split-Path -Parent $PSScriptRoot }
Set-Location $ProjectDir

Write-Output "[1/4] 변경 파일 스테이징"
git add -A
$staged = (git diff --cached --stat) -join "`n"
if (-not $staged.Trim()) { Write-Output "       커밋할 변경사항이 없습니다."; Read-Host "`n계속하려면 Enter"; exit 0 }
Write-Output $staged

Write-Output "`n[2/4] 커밋 메시지"
$msg = $null
if (Get-Command claude -ErrorAction SilentlyContinue) {
    $prompt = "다음은 git 변경 파일 목록이야. 'feat: ' 또는 'fix: ' 같은 접두사를 붙여 한국어 커밋 메시지를 한 줄만 써줘. 메시지만 출력해.`n`n$staged"
    $msg = (($prompt | claude -p 2>$null) -join "").Trim()
}
if (-not $msg) { $msg = Read-Host "커밋 메시지" }
if (-not $msg) { Write-Output "[오류] 커밋 메시지가 비었습니다."; exit 1 }
Write-Output "       $msg"

Write-Output "`n[3/4] 커밋"
git commit -m $msg
if ($LASTEXITCODE -ne 0) { Write-Output "[오류] 커밋 실패"; Read-Host "`n계속하려면 Enter"; exit 1 }

Write-Output "`n[4/4] 푸시"
git push
if ($LASTEXITCODE -ne 0) { Write-Output "[오류] 푸시 실패 — 네트워크/인증 확인"; Read-Host "`n계속하려면 Enter"; exit 1 }

Write-Output "`n완료! 클라우드 PC 에서 update.bat 을 관리자로 실행하세요."
Read-Host "`n계속하려면 Enter"
