@echo off
chcp 65001 >nul
title Animal Experiment Manager v3.4

set "PYTHON_DIR=%LOCALAPPDATA%\Programs\Python\Python313"
set "PATH=%PYTHON_DIR%\Scripts;%PYTHON_DIR%;%PATH%"

cd /d "%~dp0"

echo.
echo   ========================================
echo     Animal Experiment Manager v3.4
echo     Diabetic Rat Wound Healing Study
echo   ========================================
echo.
echo   Python:
python --version
echo.
echo   Checking install...
python -c "from database import get_rats_alive_on_day; print('OK')" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [ERROR] Module import failed!
    python -c "from database import get_rats_alive_on_day"
    pause
    exit /b 1
)
echo   Starting server...
echo   Browser will open: http://localhost:8501
echo   Press Ctrl+C to stop
echo   ========================================
echo.

python -m streamlit run app.py

pause
