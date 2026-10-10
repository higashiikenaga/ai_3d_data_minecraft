@echo off
rem Basic install: free cloud APIs + model->schem conversion (no GPU needed)
setlocal
cd /d "%~dp0..\.."
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
if not exist .venv (
    %PY% -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e . || goto :error
echo.
echo [OK] mc3d installed. Next:
echo   scripts\windows\start_server.bat cloud    ^(free cloud APIs^)
echo   scripts\windows\setup_gpu.bat             ^(local V100 / TRELLIS^)
exit /b 0
:error
echo [NG] setup failed
exit /b 1
