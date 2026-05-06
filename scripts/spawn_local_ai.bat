@echo off
setlocal enabledelayedexpansion

set DOCKER_FLAG=
set MODEL=
set PORT=11434

:parse
if "%~1"=="" goto :check
if /i "%~1"=="--docker" set DOCKER_FLAG=1& shift & goto :parse
if /i "%~1"=="--model" set MODEL=%~2& shift & shift & goto :parse
echo Unknown arg: %~1
exit /b 1

:check
if "%MODEL%"=="" (
    echo --model is required
    exit /b 1
)

set CMD=llama-server -hf "%MODEL%" --port %PORT%
if defined DOCKER_FLAG set CMD=%CMD% --host 0.0.0.0

echo %CMD%
%CMD%
