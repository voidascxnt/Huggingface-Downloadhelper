@echo off
setlocal enabledelayedexpansion

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
