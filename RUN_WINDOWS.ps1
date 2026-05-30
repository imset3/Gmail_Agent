$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "======================================================"
Write-Host "Gmail Multi-Agent Email Assistant"
Write-Host "======================================================"
Write-Host ""

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 start.py
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python start.py
} else {
    Write-Host "Python이 설치되어 있지 않습니다."
    Write-Host "https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요."
    Write-Host "설치할 때 'Add python.exe to PATH'를 체크해야 합니다."
}

Read-Host "Enter를 누르면 종료합니다"
