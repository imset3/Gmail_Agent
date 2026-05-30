@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py -3"
) else (
    set "PYTHON_CMD=python"
)

echo Gmail API 패키지를 확인/설치합니다.
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 (
    echo 패키지 설치에 실패했습니다. 인터넷 연결과 Python pip 설치 상태를 확인하세요.
    pause
    exit /b 1
)

%PYTHON_CMD% start.py --gmail --limit 20
echo.
pause
