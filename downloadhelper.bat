@echo off
cd /d %~dp0
echo Starting Hugging Face Model Downloader...

:: Set up environment variables
set VENV_DIR=%~dp0hg_downloader_env
set REQUIREMENTS_MARKER=%VENV_DIR%\.requirements_installed

:: Check if virtual environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo Creating new virtual environment...
    python -m venv "%VENV_DIR%"
    if ERRORLEVEL 1 (
        echo Error: Failed to create virtual environment.
        echo Please make sure Python 3.6+ is installed and in your PATH.
        pause
        exit /b 1
    )
)

:: Activate the virtual environment
call "%VENV_DIR%\Scripts\activate.bat"
echo Using Python from: %PYTHON%

:: Check if requirements are installed
if not exist "%REQUIREMENTS_MARKER%" (
    echo First run detected. Installing required packages...
    pip install huggingface_hub PyQt5 requests
    if ERRORLEVEL 1 (
        echo Error: Failed to install required packages.
        pause
        exit /b 1
    )
    echo. > "%REQUIREMENTS_MARKER%"
    echo Requirements successfully installed.
)

:: Run the Python script
python hg-dlv2.py

:: Check for errors
if %ERRORLEVEL% NEQ 0 (
    echo Error running Hugging Face downloader.
    echo Error code: %ERRORLEVEL%
    pause
    exit /b %ERRORLEVEL%
)

:: If we get here, all is good
echo Script completed successfully.
pause
