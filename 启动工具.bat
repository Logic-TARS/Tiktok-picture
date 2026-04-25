@echo off
setlocal

cd /d "%~dp0"
title Douyin Publisher

set "CONDA_BAT="

if exist "%UserProfile%\miniconda3\condabin\conda.bat" set "CONDA_BAT=%UserProfile%\miniconda3\condabin\conda.bat"
if not defined CONDA_BAT if exist "%UserProfile%\anaconda3\condabin\conda.bat" set "CONDA_BAT=%UserProfile%\anaconda3\condabin\conda.bat"
if not defined CONDA_BAT if exist "C:\ProgramData\miniconda3\condabin\conda.bat" set "CONDA_BAT=C:\ProgramData\miniconda3\condabin\conda.bat"
if not defined CONDA_BAT if exist "C:\ProgramData\anaconda3\condabin\conda.bat" set "CONDA_BAT=C:\ProgramData\anaconda3\condabin\conda.bat"

if defined CONDA_BAT (
    call "%CONDA_BAT%" activate douyin-publisher >nul 2>nul
    ver >nul
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"

if errorlevel 1 (
    echo.
    echo Startup failed.
    echo Check whether conda environment douyin-publisher exists.
    echo.
    pause
)

endlocal
