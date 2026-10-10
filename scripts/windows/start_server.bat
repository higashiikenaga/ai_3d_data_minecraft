@echo off
rem Usage: start_server.bat [local^|cloud] [extra mc3d serve options...]
rem   e.g. start_server.bat local --quality
rem        start_server.bat cloud
setlocal
cd /d "%~dp0..\.."
if not exist .venv\Scripts\activate.bat (
    echo .venv not found. Run scripts\windows\setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat
set BACKEND=%1
if "%BACKEND%"=="" set BACKEND=local
if not "%~1"=="" shift
if "%MC3D_TRELLIS_DIR%"=="" set MC3D_TRELLIS_DIR=%CD%\third_party\TRELLIS
set PYTHONUTF8=1
set ARGS=
:collect
if "%~1"=="" goto run
set ARGS=%ARGS% %1
shift
goto collect
:run
echo Starting mc3d serve --backend %BACKEND%%ARGS%  (Ctrl+C to stop)
mc3d serve --backend %BACKEND%%ARGS%
