@echo off
REM FarmsyncSolver - drives farmsync.cloud accounts through the Arkose API
cd /d "%~dp0"
if not exist ".deps_installed" (
    echo Installing Python deps from requirements.txt ...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo pip install failed.
        pause & exit /b 1
    )
    type nul > ".deps_installed"
)
python -m src %*
