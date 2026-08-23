@echo off
setlocal
cd /d "%~dp0"
set "TIMESEND_VENV=%~dp0.venv"
set "TIMESEND_PYTHON=%TIMESEND_VENV%\Scripts\python.exe"

where py >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python launcher ^(py^) was not found.
    echo Install Python 3.11 or newer and enable the Python launcher.
    pause
    exit /b 1
)

if not exist "%TIMESEND_PYTHON%" (
    echo Creating an isolated build environment in .venv ...
    py -3.12 -m venv "%TIMESEND_VENV%" 2>nul
    if errorlevel 1 py -m venv "%TIMESEND_VENV%"
    if errorlevel 1 goto :failed
)

"%TIMESEND_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :failed
"%TIMESEND_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
"%TIMESEND_PYTHON%" -m PyInstaller --noconfirm --clean DingTalkAutoSend.spec
if errorlevel 1 goto :failed

echo.
echo Build completed: dist\DingTalkAutoSend.exe
pause
exit /b 0

:failed
echo.
echo [ERROR] Build failed. Review the output above.
pause
exit /b 1
