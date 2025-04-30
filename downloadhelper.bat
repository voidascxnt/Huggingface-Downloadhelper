@echo off
setlocal enabledelayedexpansion

:: Check for Python environment
set ENV_DIR=env
set REQUIREMENTS=requirements.txt

:: Create requirements file if it doesn't exist
if not exist "%REQUIREMENTS%" (
    echo Creating requirements file...
    echo huggingface_hub>=0.14.1 > "%REQUIREMENTS%"
    echo PyQt5>=5.15.0 >> "%REQUIREMENTS%"
    echo requests>=2.28.0 >> "%REQUIREMENTS%"
    echo tqdm>=4.66.0 >> "%REQUIREMENTS%"
)

:: Check if virtual environment exists
if not exist "%ENV_DIR%\Scripts\activate.bat" (
    echo Creating Python virtual environment...
    python -m venv "%ENV_DIR%"
    if errorlevel 1 (
        echo Failed to create virtual environment. Please ensure Python is installed.
        exit /b 1
    )
    
    :: Install dependencies
    call "%ENV_DIR%\Scripts\activate.bat"
    echo Installing required packages...
    pip install -r "%REQUIREMENTS%"
    if errorlevel 1 (
        echo Failed to install required packages.
        exit /b 1
    )
) else (
    :: Activate existing environment
    call "%ENV_DIR%\Scripts\activate.bat"
)

:: Parse command line arguments
set MODEL_ID=
set NO_AUTO_NEXT=false

:parse_args
if "%~1"=="" goto :done_parsing
if "%~1"=="--no-auto-next" (
    set NO_AUTO_NEXT=true
    shift
    goto :parse_args
)
if not defined MODEL_ID (
    set MODEL_ID=%~1
    shift
    goto :parse_args
)
shift
goto :parse_args

:done_parsing

:: If no model ID is provided, launch the UI
if "%MODEL_ID%"=="" (
    echo Launching Huggingface Downloadhelper UI...
    python ui.py
    goto :eof
)

:: Add the --no-auto-next flag to the Python command if needed
set AUTO_NEXT_FLAG=
if "%NO_AUTO_NEXT%"=="true" set AUTO_NEXT_FLAG=--no-auto-next

:: Call Python script with processed arguments
python -m downloadhelper %MODEL_ID% %AUTO_NEXT_FLAG% %*

endlocal
