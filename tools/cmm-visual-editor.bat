@echo off
setlocal EnableDelayedExpansion

REM CMM Visual Editor Launcher
REM Installs all dependencies automatically and launches the tool.
REM Flags:
REM   --update   Force reinstall to latest version
REM   --dev      Use the dev branch instead of main
set BAT_VERSION=1 &REM:launcher-version

set CMM_BRANCH=main
set FORCE_UPDATE=0
set EXTRA_ARGS=

REM Parse flags
:parse_args
if "%~1"=="" goto :args_done
if "%~1"=="--update" (
    set FORCE_UPDATE=1
    shift
    goto :parse_args
)
if "%~1"=="--dev" (
    set CMM_BRANCH=dev
    shift
    goto :parse_args
)
set EXTRA_ARGS=!EXTRA_ARGS! %1
shift
goto :parse_args
:args_done

set CMM_SPEC=git+https://github.com/conner-olsen/eu5-community-mod-menu@!CMM_BRANCH!#subdirectory=tools/cmm-visual-editor
set CMM_VERSION_URL=https://raw.githubusercontent.com/conner-olsen/eu5-community-mod-menu/!CMM_BRANCH!/tools/cmm-visual-editor/pyproject.toml
set CMM_BAT_URL=https://raw.githubusercontent.com/conner-olsen/eu5-community-mod-menu/!CMM_BRANCH!/tools/cmm-visual-editor.bat

REM Self-update check (skip for temp downloads)
echo "%~f0" | findstr /i /c:"%TEMP%" >nul 2>&1
if !errorlevel! neq 0 (
    set REMOTE_BAT_VER=
    for /f "delims=" %%v in ('curl.exe -sL --max-time 3 "!CMM_BAT_URL!" 2^>nul ^| findstr "launcher-version"') do (
        for /f "tokens=2 delims==" %%u in ("%%v") do (
            for /f %%w in ("%%u") do set "REMOTE_BAT_VER=%%w"
        )
    )
    if defined REMOTE_BAT_VER (
        if not "!BAT_VERSION!"=="!REMOTE_BAT_VER!" (
            echo Updating launcher v!BAT_VERSION! -^> v!REMOTE_BAT_VER!...
            curl.exe -sL --max-time 10 "!CMM_BAT_URL!" -o "%~f0.tmp" 2>nul
            if exist "%~f0.tmp" (
                move /y "%~f0.tmp" "%~f0" >nul 2>&1
                echo Launcher updated. Restarting...
                call "%~f0" %*
                exit /b
            )
        )
    )
)

REM Find Python
set PYTHON=
where python >nul 2>&1 && set PYTHON=python
if not defined PYTHON (
    where py >nul 2>&1 && set PYTHON=py
)

REM Install Python if not found
if not defined PYTHON (
    echo Python not found. Installing...
    where winget >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: Could not auto-install Python. winget is not available.
        echo Please install Python 3.9 or later from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install Python.
        echo Please install Python 3.9 or later from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    REM Find Python after install
    where py >nul 2>&1 && set PYTHON=py
    if not defined PYTHON (
        for /f "delims=" %%i in ('dir /b /ad "%LOCALAPPDATA%\Programs\Python\Python3*" 2^>nul') do (
            if exist "%LOCALAPPDATA%\Programs\Python\%%i\python.exe" set "PYTHON=%LOCALAPPDATA%\Programs\Python\%%i\python.exe"
        )
    )
    if not defined PYTHON (
        echo Python was installed successfully but the terminal needs to be restarted.
        echo Please close this window and run the script again.
        pause
        exit /b 0
    )
)

REM Install pipx if not available
"%PYTHON%" -m pipx --version >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing pipx...
    "%PYTHON%" -m pip install --user pipx >nul 2>&1
    if !errorlevel! neq 0 (
        "%PYTHON%" -m pip install pipx >nul 2>&1
        if !errorlevel! neq 0 (
            echo ERROR: Failed to install pipx.
            pause
            exit /b 1
        )
    )
)

REM Check if this is a local (persistent) launcher or a temp download
echo "%~f0" | findstr /i /c:"%TEMP%" >nul 2>&1
if !errorlevel! equ 0 (
    REM Temp download - run directly via pipx run, then clean up
    echo Starting CMM Visual Editor...
    "%PYTHON%" -m pipx run --spec "!CMM_SPEC!" cmm-visual-editor !EXTRA_ARGS!
    del "%~f0" >nul 2>&1
    goto :eof
)

REM Forced update
if !FORCE_UPDATE! equ 1 (
    echo Updating CMM Visual Editor from !CMM_BRANCH!...
    "%PYTHON%" -m pipx install --force "!CMM_SPEC!" >nul 2>&1
    goto :run
)

REM Local launcher - install if needed, check for updates, then run
"%PYTHON%" -m pipx list --short 2>nul | findstr /b "cmm-visual-editor" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing CMM Visual Editor...
    "%PYTHON%" -m pipx install --force "!CMM_SPEC!" >nul 2>&1
    if !errorlevel! neq 0 (
        echo ERROR: Failed to install CMM Visual Editor.
        pause
        exit /b 1
    )
    goto :run
)

REM Fast version check - compare local vs remote pyproject.toml version
for /f "delims=" %%v in ('"%PYTHON%" -m cmm_visual_editor --version 2^>nul') do set LOCAL_VER=%%v

set REMOTE_VER=
for /f "delims=" %%v in ('curl.exe -sL --max-time 3 "!CMM_VERSION_URL!" 2^>nul') do (
    echo %%v | findstr /c:"version" >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=3 delims= " %%u in ("%%v") do (
            set "REMOTE_VER=%%~u"
        )
    )
)

if defined LOCAL_VER if defined REMOTE_VER (
    if not "!LOCAL_VER!"=="!REMOTE_VER!" (
        echo Updating CMM Visual Editor !LOCAL_VER! -^> !REMOTE_VER!...
        "%PYTHON%" -m pipx install --force "!CMM_SPEC!" >nul 2>&1
    )
)

:run
echo Starting CMM Visual Editor...
"%PYTHON%" -m cmm_visual_editor !EXTRA_ARGS!
