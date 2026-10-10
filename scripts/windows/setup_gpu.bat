@echo off
rem Local GPU install (TRELLIS + SDXL-Turbo). Add -Quality for texture baking extras.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_gpu.ps1" %*
