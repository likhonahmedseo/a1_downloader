@echo off
setlocal
cd /d "%~dp0"

set "VENV_DIR=%~dp0.venv"
set "PYTHON_CMD=python"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3.10+ and try again.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=py -3"
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Creating the virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo Could not create the virtual environment.
        pause
        exit /b 1
    )
)

echo Checking dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

rem Stop only an older NexaDrop/Uvicorn process using this app and port.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$matches = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn app:app.*--port 8000' }; $matches | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul

echo Starting NexaDrop at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
"%VENV_DIR%\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 8000

if errorlevel 1 (
    echo.
    echo The server stopped unexpectedly.
    pause
)
endlocal
