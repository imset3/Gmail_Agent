@echo off
setlocal
cd /d "%~dp0"

echo ======================================================
echo Gmail Multi-Agent Email Assistant
echo ======================================================
echo.

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
) else (
    where python >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    ) else (
        echo Python이 설치되어 있지 않습니다.
        echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
        echo 설치할 때 "Add python.exe to PATH"를 체크해야 합니다.
        pause
        exit /b 1
    )
)

%PYTHON_CMD% start.py
echo.
pause
