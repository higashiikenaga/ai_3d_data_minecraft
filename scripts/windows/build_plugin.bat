@echo off
rem Build the Minecraft plugin. Usage: build_plugin.bat [path\to\server\plugins]
setlocal
cd /d "%~dp0..\..\minecraft-plugin"
call gradlew.bat build || (echo [NG] build failed & exit /b 1)
for %%f in (build\libs\AI3D-*.jar) do set JAR=%%f
echo [OK] %JAR%
if not "%~1"=="" (
    copy /Y "%JAR%" "%~1\" && echo copied to %~1
)
